import json
from typing import Optional, TypedDict

from qgis import processing, utils
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsNetworkAccessManager,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import QMessageBox

from open_alaqs.alaqs_config import LAYERS_CONFIG
from open_alaqs.enums import AlaqsLayerType

OSM_DEFAULT_SEARCH_RADIUS_M = 1000


class OsmLayersOutput(TypedDict):
    OUTPUT_POINTS: QgsVectorLayer
    OUTPUT_LINES: QgsVectorLayer
    OUTPUT_MULTIPOLYGONS: QgsVectorLayer


class NominatimAerodrome(TypedDict):
    type: str
    osm_id: str
    lat: str
    lon: str
    boundingbox: tuple[str, str, str, str]


def get_nominatum_feature_by_icao_code(icao_code: str) -> Optional[NominatimAerodrome]:
    """Searches Nominatum for object that matches the passed string.

    Args:
        icao_code (str): ICAO airport code to search for

    Returns:
        NominatimAerodrome | None: dict containing the Nominatum's first response object or None if no mathes found
    """
    url = QUrl(
        f"https://nominatim.qgis.org/search?q=aerodrome+{icao_code}&format=json&limit=1"
    )

    nam = QgsNetworkAccessManager.instance()
    request = QNetworkRequest(url)
    reply = nam.blockingGet(request)

    if reply.error() != QNetworkReply.NoError:
        raise Exception(
            "Failed Nominatim search: [{}] {}".format(
                reply.error(), reply.errorString()
            )
        )

    payload = json.loads(bytes(reply.content()))

    if not payload:
        return None

    aerodrome = payload[0]

    if aerodrome["type"] != "aerodrome" or aerodrome["class"] != "aeroway":
        return None

    return aerodrome


def format_within_osm_feature(set_name: str) -> str:
    return f"area.{set_name}"


def format_coords_for_overpass_api(
    coords: tuple[float, float], buffer_m: Optional[int] = None
) -> str:
    """Returns coordinates formatted to be used in Overpass API

    Args:
        lat (tuple[float, float]): latitude and longitude
        buffer_m (int | None, optional): buffer around the given coordinates. Defaults to None.

    Returns:
        str: formatted coordinates, e.g. around:1000, 43.21,95.43
    """
    formatted_coords = ""

    if buffer_m > 0:
        formatted_coords += f"around:{buffer_m}, "

    formatted_coords += f"{coords[0]},{coords[1]}"

    return formatted_coords


def get_query_body(
    layer_types: list[AlaqsLayerType],
    coords: tuple[float, float],
    aerodrome: NominatimAerodrome,
) -> str:
    """Returns Overpass query body.

    Args:
        layer_types (list[AlaqsLayerType]): list of ALAQS query we want to query on OSM
        coords (tuple[float, float]): latitude and longitude
        aerodrome (Optional[NominatumFeature]): aerodrome feature from Nominatum result

    Returns:
        str: resulting Overpass API query body.

    Examples:
        nwr[building="residential"][height=1](around: 1000, 43.21,95.43)
        nwr[building="residential"][height=10](around: 3000, 43.21,95.43)
    """
    query_body = ""

    if aerodrome:
        if aerodrome["osm_type"] == "relation":
            osm_id = f'36{aerodrome["osm_id"]}'
        else:
            osm_id = aerodrome["osm_id"]

        query_body += f"area({osm_id}) -> .airport_geom;\n"

    query_body += "(\n"

    for layer_type in layer_types:
        layer_config = LAYERS_CONFIG[layer_type]

        for osm_filter in layer_config.get("osm_filters", []):
            if aerodrome and osm_filter.get("within_aerodrome", False):
                overpass_filter = format_within_osm_feature("airport_geom")
            else:
                radius = osm_filter.get("search_radius_m", OSM_DEFAULT_SEARCH_RADIUS_M)
                overpass_filter = format_coords_for_overpass_api(coords, radius)

            tags_combo_str = ""

            for tag, value in osm_filter["tags"].items():
                if value is None:
                    tags_combo_str += f'["{tag}"]'
                else:
                    tags_combo_str += f'["{tag}"="{value}"]'

            if not tags_combo_str:
                continue

            query_body += f"nwr{tags_combo_str}({overpass_filter});\n"

    query_body += ");\n"

    return query_body


def download_osm_airport_data(
    layer_types: list[AlaqsLayerType],
    coords: tuple[float, float],
    icao_code: str,
) -> tuple[QgsVectorLayer, QgsVectorLayer, QgsVectorLayer]:
    aerodrome = get_nominatum_feature_by_icao_code(icao_code)

    query_body = get_query_body(layer_types, coords, aerodrome)
    query = f"""
        [out:xml] [timeout:25];
        {query_body}
        (._;>;);
        out body;
    """

    # exception if processing plugin if not active othewise would trigger error like
    # Error: Algorithm qgis:checkvalidity not found when importing OSM data
    if "processing" not in utils.plugins:
        message = "Please activate Processing plugin in Plugin Manager"
        title = "Failed OSM dependency"
        QMessageBox.critical(
            (
                utils.iface.mainWindow()
                if utils.iface and utils.iface.mainWindow()
                else None
            ),
            title,
            message,
        )
        return (QgsVectorLayer(), QgsVectorLayer(), QgsVectorLayer())

    osm_result = processing.run(
        "quickosm:downloadosmdatarawquery",
        {
            "QUERY": query,
            "TIMEOUT": 25,
            "SERVER": "https://overpass-api.de/api/interpreter",
            "EXTENT": "0.000000000,1.000000000,0.000000000,1.000000000 [EPSG:4326]",
            "AREA": "",
            "FILE": "TEMPORARY_OUTPUT",
        },
    )

    points = reproject_layer(osm_result["OUTPUT_POINTS"])
    lines = reproject_layer(osm_result["OUTPUT_LINES"])
    multipolygons = reproject_layer(osm_result["OUTPUT_MULTIPOLYGONS"])

    singleparts_result = processing.run(
        "native:multiparttosingleparts",
        {
            "INPUT": multipolygons,
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    polygons = singleparts_result["OUTPUT"]

    return points, lines, polygons


def reproject_layer(layer: QgsVectorLayer) -> QgsVectorLayer:
    result = processing.run(
        "native:reprojectlayer",
        {
            "INPUT": layer,
            "TARGET_CRS": QgsCoordinateReferenceSystem.fromEpsgId(3857),
            "CONVERT_CURVED_GEOMETRIES": False,
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    return result["OUTPUT"]
