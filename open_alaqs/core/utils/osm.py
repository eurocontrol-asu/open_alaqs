from typing import TypedDict

import requests
from qgis import processing
from qgis.core import QgsCoordinateReferenceSystem, QgsVectorLayer

from open_alaqs.alaqs_config import LAYERS_CONFIG
from open_alaqs.enums import AlaqsLayerType

OSM_DEFAULT_SEARCH_RADIUS_M = 1000


class OsmLayersOutput(TypedDict):
    OUTPUT_POINTS: QgsVectorLayer
    OUTPUT_LINES: QgsVectorLayer
    OUTPUT_MULTIPOLYGONS: QgsVectorLayer


def get_coords_for_icao_code(icao_code: str) -> tuple[float, float] | None:
    """Searches Nominatum for object that matches the passed string.

    Args:
        icao_code (str): ICAO airport code to search for

    Returns:
        tuple[float, float] | None: latitute and longiture, or None if no results found
    """
    url = f"https://nominatim.qgis.org/search?q={icao_code}&format=json&info=QgisQuickOSMPlugin"

    response = requests.get(url)
    response.raise_for_status()

    payload = response.json()

    if not payload:
        return None

    return payload[0]["lat"], payload[0]["lon"]


def format_coords_for_overpass_api(
    coords: tuple[float, float], buffer_m: int | None = None
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
    layer_types: list[AlaqsLayerType], coords: tuple[float, float]
) -> str:
    """Returns Overpass query body.

    Args:
        layer_types (list[AlaqsLayerType]): list of ALAQS query we want to query on OSM
        coords (tuple[float, float]): latitude and longitude

    Returns:
        str: resulting Overpass API query body.

    Examples:
        nwr[building="residential"][height=1](around: 1000, 43.21,95.43)
        nwr[building="residential"][height=10](around: 3000, 43.21,95.43)
    """
    query_body = ""

    for layer_type in layer_types:
        layer_config = LAYERS_CONFIG[layer_type]
        osm_tags = layer_config.get("osm_tags", [])
        radius = layer_config.get("osm_search_radius_m", OSM_DEFAULT_SEARCH_RADIUS_M)
        formatted_coords = format_coords_for_overpass_api(coords, radius)

        for osm_tags_combo in osm_tags:
            osm_tags_combo_str = ""

            for tag, value in osm_tags_combo.items():
                osm_tags_combo_str += f'["{tag}"="{value}"]'

            if not osm_tags_combo_str:
                continue

            query_body += f"nwr{osm_tags_combo_str}({formatted_coords});\r\n"

    return query_body


def download_osm_airport_data(
    layer_types: list[AlaqsLayerType],
    coords: tuple[float, float],
) -> tuple[QgsVectorLayer, QgsVectorLayer, QgsVectorLayer]:
    query_body = get_query_body(layer_types, coords)
    query = f"""
        [out:xml] [timeout:25];
        (
            {query_body}
        );
        (._;>;);
        out body;
    """

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
            "TARGET_CRS": QgsCoordinateReferenceSystem("EPSG:3857"),
            "CONVERT_CURVED_GEOMETRIES": False,
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    return result["OUTPUT"]
