import json
import os
import tempfile
import urllib.parse
from typing import Optional, TypedDict

from qgis import processing, utils
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsNetworkAccessManager,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QByteArray, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import QMessageBox

from open_alaqs.alaqs_config import LAYERS_CONFIG
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.enums import AlaqsLayerType

logger = get_logger(__name__)

OSM_DEFAULT_SEARCH_RADIUS_M = 1000

# Overpass API public instances, tried in order.  As of April 2026 the
# admin of overpass-api.de added strict usage rules (custom UA, Referer,
# rate-limit awareness); the headers below comply with those rules so
# overpass-api.de is now first.  The other mirrors are kept as fallbacks
# for environments where overpass-api.de is unreachable.
#
#   * overpass-api.de       — main instance, ~10k queries/day quota
#   * private.coffee        — community mirror, no rate limit
#   * VK Maps (maps.mail.ru) — global, "no rate limit", but reachable only
#                              from networks that don't block .ru
#                              infrastructure (often blocked by corporate
#                              firewalls and Firefox Tracking Protection)
#
# private.coffee absorbed kumi.systems, so we no longer list the latter.
OVERPASS_SERVERS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)

# Timeout for the Overpass HTTP request, in milliseconds.  Larger studies
# can take well over the default 60s on community mirrors.
OVERPASS_REQUEST_TIMEOUT_MS = 120_000


def _overpass_post(query: str) -> tuple[Optional[bytes], list[str]]:
    """POST an Overpass QL query to each mirror until one returns 2xx.

    Returns a tuple (xml_bytes_or_None, list_of_per_mirror_error_strings).
    """
    nam = QgsNetworkAccessManager.instance()

    # Percent-encode the query so special characters (brackets, colons,
    # newlines) survive the x-www-form-urlencoded body intact.  plus=True
    # is the standard form-encoding convention.
    encoded_query = urllib.parse.quote(query, safe="")
    body = QByteArray(("data=" + encoded_query).encode("utf-8"))

    errors: list[str] = []
    for server in OVERPASS_SERVERS:
        request = QNetworkRequest(QUrl(server))
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/x-www-form-urlencoded",
        )
        # Headers tuned to satisfy the overpass-api.de WAF rules announced
        # by the server admin (April 2026):
        #   * Custom, identifying User-Agent — not the QuickOSM signature,
        #     not a fake browser, no `+` prefix that some WAFs treat as
        #     crawler-style bait.
        #   * Referer pointing at the project so the WAF can attribute
        #     traffic if it needs to.  Required even for non-browser
        #     callers under the new rules.
        #   * Generic `Accept: */*` to stay clearly in the script bucket
        #     and avoid browser-content-negotiation heuristics.
        request.setRawHeader(
            b"User-Agent",
            b"open_alaqs/3 (https://github.com/eurocontrol-asu/open_alaqs; "
            b"contact-via-github-issues)",
        )
        request.setRawHeader(
            b"Referer", b"https://github.com/eurocontrol-asu/open_alaqs"
        )
        request.setRawHeader(b"Accept", b"*/*")
        request.setTransferTimeout(OVERPASS_REQUEST_TIMEOUT_MS)
        try:
            reply = nam.blockingPost(request, body)
        except Exception as exc:
            errors.append(f"{server}: exception {exc!r}")
            logger.warning("Overpass POST to %s threw: %s", server, exc)
            continue

        err_code = reply.error()
        if err_code == QNetworkReply.NetworkError.NoError:
            content = bytes(reply.content())
            if content and b"<osm" in content[:400]:
                logger.info("Overpass OK from %s (%d bytes)", server, len(content))
                return content, errors
            # 2xx but the body is not valid OSM XML — likely an error page
            snippet = (
                content[:200].decode("utf-8", errors="replace")
                if content
                else "(empty body)"
            )
            errors.append(f"{server}: HTTP OK but non-OSM body: {snippet!r}")
            logger.warning("Overpass %s returned non-OSM body: %s", server, snippet)
            continue

        # Inspect HTTP status code when possible
        http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        err_str = reply.errorString()
        errors.append(f"{server}: error {err_code} ({err_str}), http={http_status}")
        logger.warning(
            "Overpass %s failed: qt_error=%s http=%s msg=%s",
            server,
            err_code,
            http_status,
            err_str,
        )

    return None, errors


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

    if reply.error() != QNetworkReply.NetworkError.NoError:
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
    # [maxsize:64Mi] keeps the admission-control footprint well under the
    # default 512 MiB so the request passes overpass-api.de's resource gate
    # even under high load.  Airport-scale extracts comfortably fit in 64 MiB.
    query = f"""
        [out:xml] [timeout:25] [maxsize:67108864];
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

    # Download the Overpass response directly via QgsNetworkAccessManager
    # instead of through the QuickOSM processing algorithm.  QuickOSM appends
    # `?info=QgisQuickOSMPlugin` to the URL, which overpass-api.de has been
    # blocking with HTTP 406 since April 2026.  Going through QNAM also lets
    # us retry across multiple mirrors cleanly.
    osm_xml_bytes, mirror_errors = _overpass_post(query)
    if osm_xml_bytes is None:
        error_detail = (
            "\n".join(f"  - {e}" for e in mirror_errors)
            if mirror_errors
            else "  (no mirror-level error captured)"
        )
        message = (
            "Could not download OSM data from any of the configured Overpass "
            "mirrors.\n\n"
            "Per-mirror errors:\n" + error_detail + "\n\n"
            "If you are on a corporate network, check whether an HTTP proxy "
            "is configured in QGIS (Settings \u2192 Options \u2192 Network) "
            "and whether outbound HTTPS to the Overpass hosts is permitted."
        )
        logger.error("OSM download failed on all mirrors: %s", mirror_errors)
        QMessageBox.critical(
            (
                utils.iface.mainWindow()
                if utils.iface and utils.iface.mainWindow()
                else None
            ),
            "OSM download failed",
            message,
        )
        return (QgsVectorLayer(), QgsVectorLayer(), QgsVectorLayer())

    # Persist the XML to a temp file and open each OGR sub-layer via the
    # GDAL OSM driver.  The OSM driver exposes sub-layers named `points`,
    # `lines`, `multipolygons`, `multilinestrings`, and `other_relations`.
    #
    # We pass CONFIG_FILE pointing at our bundled osmconf.ini so the
    # `lines` sub-layer exposes `aeroway` and `ref` as proper columns.
    # The default /usr/share/gdal/osmconf.ini stuffs both into the
    # `other_tags` HSTORE blob, which breaks the import filter
    # `"aeroway" = 'taxiway'` (and the runway equivalent) downstream.
    tmp_dir = tempfile.mkdtemp(prefix="openalaqs_osm_")
    osm_path = os.path.join(tmp_dir, "overpass.osm")
    with open(osm_path, "wb") as fh:
        fh.write(osm_xml_bytes)

    osmconf_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "osmconf.ini"
    )
    if not os.path.isfile(osmconf_path):
        # Fail loud rather than silently falling back to the system default
        # which would re-introduce the taxiway/runway import bug.
        raise RuntimeError(
            f"Bundled OSM config file is missing at {osmconf_path}. "
            "Without it the GDAL OSM driver cannot expose aeroway/ref "
            "columns on the lines sub-layer and taxiway/runway imports "
            "will silently fail."
        )

    def _ogr_uri(layer_name: str) -> str:
        return f"{osm_path}|layername={layer_name}|option:CONFIG_FILE={osmconf_path}"

    points_layer = QgsVectorLayer(_ogr_uri("points"), "points", "ogr")
    lines_layer = QgsVectorLayer(_ogr_uri("lines"), "lines", "ogr")
    multipolygons_layer = QgsVectorLayer(
        _ogr_uri("multipolygons"), "multipolygons", "ogr"
    )

    points = reproject_layer(points_layer)
    lines = reproject_layer(lines_layer)
    multipolygons = reproject_layer(multipolygons_layer)

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
