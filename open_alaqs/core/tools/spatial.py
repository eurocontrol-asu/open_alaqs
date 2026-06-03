import math
from typing import Optional, Union

import osgeo.ogr as ogr
import osgeo.osr as osr
import shapely.geometry
import shapely.ops
import shapely.wkt
from geographiclib.geodesic import Geodesic
from qgis.core import (
    QgsClipper,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
)

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.AircraftTrajectory import TrajectoryPoint
from open_alaqs.core.tools import conversion

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level caches
# ---------------------------------------------------------------------------

# Cache of osr.SpatialReference objects keyed by EPSG id.
_spatial_references: dict = {}

# Cache of osr.CoordinateTransformation objects keyed by (src_epsg, tgt_epsg).
_transformations_cache: dict = {}

# Cache of geographiclib.Geodesic objects keyed by EPSG id.
_geodesic_cache: dict = {}

# Small tolerance used for floating-point coordinate comparisons (metres).
_COORD_EPS = 1e-6


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def getSpatialReference(epsg_id: int) -> osr.SpatialReference:
    """Return a cached osr.SpatialReference for the given EPSG code."""
    if epsg_id not in _spatial_references:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(epsg_id)
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        _spatial_references[epsg_id] = srs
    return _spatial_references[epsg_id]


def _get_transform(
    epsg_id_source: int, epsg_id_target: int
) -> osr.CoordinateTransformation:
    """Return a cached osr.CoordinateTransformation between two EPSG codes."""
    key = (epsg_id_source, epsg_id_target)
    if key not in _transformations_cache:
        _transformations_cache[key] = osr.CoordinateTransformation(
            getSpatialReference(epsg_id_source),
            getSpatialReference(epsg_id_target),
        )
    return _transformations_cache[key]


def getGeodesic(epsg_id: int = 4326) -> Geodesic:
    """Return a cached Geodesic object for the ellipsoid of the given EPSG."""
    if epsg_id not in _geodesic_cache:
        srs = getSpatialReference(epsg_id)
        _geodesic_cache[epsg_id] = Geodesic(
            srs.GetSemiMajor(),
            1.0 / srs.GetInvFlattening(),
        )
    return _geodesic_cache[epsg_id]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def getDistanceBetweenPoints(
    x1: float,
    y1: float,
    z1: float = 0.0,
    x2: float = 0.0,
    y2: float = 0.0,
    z2: float = 0.0,
) -> float:
    """Euclidean distance between two 3-D points."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)


def getDistanceXY(
    x: float,
    y: float,
    z: float = 0.0,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    origin_z: float = 0.0,
) -> float:
    """
    2-D distance from point (x, y) to origin (origin_x, origin_y).

    The z / origin_z parameters are accepted for API compatibility but are
    not used in the distance calculation.
    """
    x = conversion.convertToFloat(x)
    y = conversion.convertToFloat(y)
    return math.sqrt((x - origin_x) ** 2 + (y - origin_y) ** 2)


def getDistance(
    lat1: float, lon1: float, azimuth: float, distance: float, epsg_id: int = 4326
) -> dict:
    """Solve the direct geodesic problem (given start, azimuth, distance)."""
    return getGeodesic(epsg_id).Direct(lat1, lon1, azimuth, distance)


def getInverseDistance(
    lat1: float, lon1: float, lat2: float, lon2: float, epsg_id: int = 4326
) -> dict:
    """
    Solve the inverse geodesic problem (given two points, return distance).

    Args:
        lat1, lon1: Geodetic latitude and longitude of the first point (degrees).
        lat2, lon2: Geodetic latitude and longitude of the second point (degrees).
        epsg_id:    EPSG code identifying the ellipsoid (default: 4326 = WGS 84).

    Returns:
        Dict from geographiclib containing at minimum ``s12`` (distance in metres).
    """
    return getGeodesic(epsg_id).Inverse(lat1, lon1, lat2, lon2)


def getDistanceOfLineStringXYZ(
    geometry_wkt,
    distance_z: float = 0.0,
    epsg_id_source: int = 3857,
    epsg_id_target: int = 4326,
) -> float:
    """Geodetic length of a LineString including a vertical component."""
    distance = getDistanceOfLineStringXY(geometry_wkt, epsg_id_source, epsg_id_target)
    return math.sqrt(distance * distance + distance_z * distance_z)


def getDistanceOfLineStringXY(
    geometry_wkt,
    epsg_id_source: int = 3857,
    epsg_id_target: int = 4326,
) -> float:
    """
    Geodetic length of a (Multi)LineString in metres.

    Handles both simple LineString and MultiLineString inputs.  The latter
    arises when getIntersectionXY clips a polyline that enters and leaves
    the same cell more than once (e.g. a V-shaped taxi-in segment crossing
    the same cell boundary twice): OGR returns the disjoint pieces as a
    MultiLineString.  Earlier versions of this function delegated to
    getAllPoints which is LineString-only, so MultiLineString inputs
    produced an empty points list and zero length.  That silently dropped
    mass for every cell a polyline re-entered, producing a ~50% loss for
    affected segments (a single E190 taxi-in observation showed ~0.96 kg
    CO lost per movement, ~4.5% of the per-week aircraft total).

    Reprojects from *epsg_id_source* to *epsg_id_target* (default: WGS 84)
    and sums the geodesic distances between consecutive vertices, treating
    each sub-line independently (no spurious "jump" distance between the
    end of one part and the start of the next).
    """
    if isinstance(geometry_wkt, ogr.Geometry):
        geometry_wkt = geometry_wkt.ExportToWkt()

    reprojected_wkt, swap = reproject_geometry(
        geometry_wkt, epsg_id_source, epsg_id_target
    )

    geom = ogr.CreateGeometryFromWkt(reprojected_wkt)
    if geom is None:
        return 0.0

    # Flatten to a list of single LineString parts.  Anything that is not
    # a LineString or MultiLineString contributes zero length (Point,
    # Polygon, empty geometry, etc.).
    parts: list = []
    gt = geom.GetGeometryType()
    if gt in (ogr.wkbLineString, ogr.wkbLineString25D):
        parts = [geom]
    elif gt in (ogr.wkbMultiLineString, ogr.wkbMultiLineString25D):
        parts = [geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())]
    elif gt in (ogr.wkbGeometryCollection, ogr.wkbGeometryCollection25D):
        for i in range(geom.GetGeometryCount()):
            sub = geom.GetGeometryRef(i)
            sub_gt = sub.GetGeometryType()
            if sub_gt in (ogr.wkbLineString, ogr.wkbLineString25D):
                parts.append(sub)
            elif sub_gt in (ogr.wkbMultiLineString, ogr.wkbMultiLineString25D):
                for j in range(sub.GetGeometryCount()):
                    parts.append(sub.GetGeometryRef(j))
    else:
        return 0.0

    total = 0.0
    for part in parts:
        n_pts = part.GetPointCount()
        if n_pts < 2:
            continue
        prev_x, prev_y, _ = part.GetPoint(0)
        if swap:
            prev_x, prev_y = prev_y, prev_x
        for i in range(1, n_pts):
            cur_x, cur_y, _ = part.GetPoint(i)
            if swap:
                cur_x, cur_y = cur_y, cur_x
            result = getInverseDistance(prev_x, prev_y, cur_x, cur_y)
            s12 = result.get("s12")
            if s12 is not None:
                s12 = conversion.convertToFloat(s12)
            total += s12 or 0.0
            prev_x, prev_y = cur_x, cur_y

    return total


def getArea(val: Union[ogr.Geometry, str]) -> float:
    """Return the area of a geometry (WKT string or ogr.Geometry)."""
    if isinstance(val, ogr.Geometry):
        return val.GetArea()
    if isinstance(val, str):
        geom = ogr.CreateGeometryFromWkt(val)
        if geom is None:
            raise ValueError(f"getArea: could not parse WKT: {val!r}")
        return geom.GetArea()
    raise TypeError(
        f"getArea: expected str or ogr.Geometry, got {type(val).__name__!r}"
    )


def getIntersectionXY(p1, p2) -> str:
    """Return the WKT of the intersection of two geometries, or ''."""
    poly1 = p1 if isinstance(p1, ogr.Geometry) else ogr.CreateGeometryFromWkt(p1)
    poly2 = p2 if isinstance(p2, ogr.Geometry) else ogr.CreateGeometryFromWkt(p2)

    if poly1 is None:
        logger.error("getIntersectionXY: geometry 1 is None (input: %s)", p1)
        return ""
    if poly2 is None:
        logger.error("getIntersectionXY: geometry 2 is None (input: %s)", p2)
        return ""

    intersection = poly1.Intersection(poly2)
    if intersection is not None and not intersection.IsEmpty():
        return intersection.ExportToWkt()
    return ""


def getPoint(
    wkt: str, x: float = 0.0, y: float = 0.0, z: float = 0.0, swap_xy: bool = False
) -> ogr.Geometry:
    wkt = wkt.replace("POINTZ", "POINT").replace("pointz", "point")
    point = ogr.Geometry(ogr.wkbPoint)

    if wkt:
        point2 = ogr.CreateGeometryFromWkt(wkt)
        if point2 is None:
            logger.error("getPoint: could not parse WKT %r", wkt)
        else:
            px, py, pz = point2.GetX(), point2.GetY(), point2.GetZ()
            point.AddPoint(py if swap_xy else px, px if swap_xy else py, pz)
    else:
        point.AddPoint(y if swap_xy else x, x if swap_xy else y, z)

    return point


def getPointGeometryText(
    p1: float, p2: float, p3: float = 0.0, swap_xy: bool = False
) -> str:
    return getPoint("", p1, p2, p3, swap_xy).ExportToWkt()


def getLine(p1_wkt, p2_wkt, swap_xy: bool = False) -> ogr.Geometry:
    geom = ogr.Geometry(ogr.wkbLineString)
    p1 = (
        p1_wkt
        if isinstance(p1_wkt, ogr.Geometry)
        else getPoint(p1_wkt, swap_xy=swap_xy)
    )
    p2 = (
        p2_wkt
        if isinstance(p2_wkt, ogr.Geometry)
        else getPoint(p2_wkt, swap_xy=swap_xy)
    )
    geom.AddPoint(p1.GetX(), p1.GetY(), p1.GetZ())
    geom.AddPoint(p2.GetX(), p2.GetY(), p2.GetZ())
    return geom


def getRectangleXYFromBoundingBox(bbox: dict) -> ogr.Geometry:
    ring = ogr.Geometry(ogr.wkbLinearRing)
    ring.AddPoint(bbox["x_min"], bbox["y_min"])
    ring.AddPoint(bbox["x_max"], bbox["y_min"])
    ring.AddPoint(bbox["x_max"], bbox["y_max"])
    ring.AddPoint(bbox["x_min"], bbox["y_max"])
    ring.AddPoint(bbox["x_min"], bbox["y_min"])
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring)
    return poly


def getRectangleXYZFromBoundingBox(
    left_line, right_line, epsg_id_source: int = 3857, epsg_id_target: int = 4326
) -> ogr.Geometry:
    # B4 fix: unpack swap and pass it to getAllPoints
    left_wkt, swap_l = reproject_geometry(left_line, epsg_id_target, epsg_id_source)
    right_wkt, swap_r = reproject_geometry(right_line, epsg_id_target, epsg_id_source)

    left_pts = getAllPoints(left_wkt, swap_l)
    right_pts = getAllPoints(right_wkt, swap_r)

    lon_l1, lat_l1, alt11 = left_pts[0]
    lon_l2, lat_l2, alt12 = left_pts[1]
    lon_r1, lat_r1, alt21 = right_pts[0]
    lon_r2, lat_r2, alt22 = right_pts[1]

    ring = ogr.Geometry(ogr.wkbLinearRing)
    ring.AddPoint(lon_l2, lat_l2, alt12)
    ring.AddPoint(lon_r2, lat_r2, alt22)
    ring.AddPoint(lon_r1, lat_r1, alt21)
    ring.AddPoint(lon_l1, lat_l1, alt11)
    ring.AddPoint(lon_l2, lat_l2, alt12)

    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring)
    return poly


def getLineGeometryText(p1, p2) -> str:
    return getLine(p1, p2).ExportToWkt()


def getBoundingBox(val: Union[ogr.Geometry, str]) -> Optional[dict]:
    """Return a bounding-box dict, or None if the geometry is invalid."""
    if isinstance(val, ogr.Geometry):
        bbox = val.GetEnvelope3D()
        return {
            "x_min": bbox[0],
            "x_max": bbox[1],
            "y_min": bbox[2],
            "y_max": bbox[3],
            "z_min": bbox[4],
            "z_max": bbox[5],
        }
    if isinstance(val, str):
        # B5 fix: guard None before recursing
        geom = ogr.CreateGeometryFromWkt(val)
        if geom is None:
            logger.error("getBoundingBox: could not parse WKT %r", val)
            return None
        return getBoundingBox(geom)
    return None


def addHeightToGeometryWkt(geometry_wkt: str, height: float) -> str:
    """Return a copy of the geometry WKT with all Z coordinates set to *height*."""
    geom = shapely.wkt.loads(geometry_wkt)
    shifted = shapely.ops.transform(lambda x, y, z=None: (x, y, height), geom)
    return str(shifted)


def getRelativeAreaInBoundingBox(geometry_wkt: str, cell_bbox: dict) -> float:
    total_area = getArea(geometry_wkt)
    # B6 fix: guard division by zero
    if total_area == 0:
        return 0.0

    bbox_polygon = getRectangleXYFromBoundingBox(cell_bbox)
    matched_wkt = getIntersectionXY(geometry_wkt, bbox_polygon)
    if not matched_wkt:
        return 0.0

    matched_geom = ogr.CreateGeometryFromWkt(matched_wkt)
    if matched_geom is None:
        return 0.0

    flat_type = matched_geom.GetGeometryType()
    if flat_type in (
        ogr.wkbPoint,
        ogr.wkbMultiPoint,
        ogr.wkbPoint25D,
        ogr.wkbMultiPoint25D,
    ):
        return 1.0
    if flat_type in (
        ogr.wkbPolygon,
        ogr.wkbMultiPolygon,
        ogr.wkbPolygon25D,
        ogr.wkbMultiPolygon25D,
    ):
        return matched_geom.GetArea() / total_area

    logger.error(
        "getRelativeAreaInBoundingBox: unexpected geometry type %d for %r",
        flat_type,
        matched_wkt,
    )
    return 0.0


def getRelativeLengthXYInBoundingBox(
    geometry_wkt: str,
    cell_bbox: dict,
    epsg_id_source: int = 3857,
    epsg_id_target: int = 4326,
) -> float:
    bbox_polygon = getRectangleXYFromBoundingBox(cell_bbox)
    total_length = getDistanceOfLineStringXY(
        geometry_wkt, epsg_id_source=epsg_id_source, epsg_id_target=epsg_id_target
    )
    if not total_length:
        return 0.0

    intersection_wkt = getIntersectionXY(geometry_wkt, bbox_polygon)
    if not intersection_wkt:
        return 0.0

    dist_xy = getDistanceOfLineStringXY(
        intersection_wkt, epsg_id_source, epsg_id_target
    )
    return abs(dist_xy) / abs(total_length) if dist_xy else 0.0


def getRelativeHeightInBoundingBox(
    line_z_min: float, line_z_max: float, cell_bbox: dict
) -> float:
    total_height = abs(line_z_max - line_z_min)
    if line_z_max < cell_bbox["z_min"] or line_z_min > cell_bbox["z_max"]:
        return 0.0
    if total_height == 0.0:
        return 1.0
    overlap = abs(
        max(line_z_min, cell_bbox["z_min"]) - min(line_z_max, cell_bbox["z_max"])
    )
    return overlap / total_height


def CreateGeometryFromWkt(geometry_wkt) -> ogr.Geometry:
    """Return an ogr.Geometry, accepting both WKT strings and existing geometries."""
    if isinstance(geometry_wkt, ogr.Geometry):
        return geometry_wkt
    return ogr.CreateGeometryFromWkt(geometry_wkt)


def getAllPoints(geometry_wkt, swap: bool = False) -> list:
    """
    Extract all vertices of a simple (single-part) LineString as a list of
    (x, y, z) tuples.  When *swap* is True the x and y values are exchanged,
    which is used after reprojecting from a projected CRS to a geographic CRS
    so that the tuples are in (lat, lon, z) order.

    Raises:
        ValueError: if *geometry_wkt* cannot be parsed or is a multipart geometry.
    """
    # B7 fix: guard None from invalid WKT
    if isinstance(geometry_wkt, ogr.Geometry):
        geom = geometry_wkt
    else:
        geom = ogr.CreateGeometryFromWkt(geometry_wkt)
        if geom is None:
            raise ValueError(f"getAllPoints: could not parse WKT: {geometry_wkt!r}")

    points = []
    for i in range(geom.GetPointCount()):
        x, y, z = geom.GetPoint(i)
        points.append((y, x, z) if swap else (x, y, z))
    return points


def reproject_Point(
    x: float,
    y: float,
    epsg_id_source: int = 3857,
    epsg_id_target: int = 4326,
) -> Optional[tuple]:
    """
    Reproject a single point from *epsg_id_source* to *epsg_id_target*.

    Returns:
        (ogr.Geometry, wkt_str) on success, or None on failure.
    """
    try:
        point = ogr.Geometry(ogr.wkbPoint)
        point.AddPoint(x, y)
        point.Transform(_get_transform(epsg_id_source, epsg_id_target))
        return point, point.ExportToWkt()
    except Exception as exc:
        logger.error("reproject_Point: %s", exc)
        return None


def reproject_geometry(
    geometry_wkt, epsg_id_source: int = 3857, epsg_id_target: int = 4326
) -> tuple:
    """
    Reproject a geometry from *epsg_id_source* to *epsg_id_target*.

    Returns:
        (reprojected_wkt, swap_coordinates) where *swap_coordinates* is True
        when one CRS is geographic and the other is projected, indicating that
        getAllPoints() should swap x and y to yield (lat, lon) order.

    Raises:
        ValueError: if *geometry_wkt* cannot be parsed.
    """
    # B8 fix: guard None from invalid WKT
    geom = (
        ogr.CreateGeometryFromWkt(geometry_wkt)
        if isinstance(geometry_wkt, str)
        else geometry_wkt
    )
    if geom is None:
        raise ValueError(f"reproject_geometry: could not parse WKT: {geometry_wkt!r}")

    # O2 fix: use cached transform
    geom.Transform(_get_transform(epsg_id_source, epsg_id_target))

    src = getSpatialReference(epsg_id_source)
    tgt = getSpatialReference(epsg_id_target)
    swap = bool(src.IsGeographic()) != bool(tgt.IsGeographic())

    return geom.ExportToWkt(), swap


def create_distance_area(epsg_id_source: int) -> QgsDistanceArea:
    source_crs = QgsCoordinateReferenceSystem.fromEpsgId(epsg_id_source)
    qgs_d = QgsDistanceArea()
    qgs_d.setSourceCrs(source_crs, QgsProject.instance().transformContext())
    qgs_d.setEllipsoid(source_crs.ellipsoidAcronym())
    return qgs_d


# Module-level cache for QgsDistanceArea instances keyed by EPSG id.
# QgsDistanceArea construction involves CRS resolution and ellipsoid setup,
# which is measurable overhead when called once per trajectory segment.
_distance_area_cache: dict[int, QgsDistanceArea] = {}


def ellipsoidal_2d_distance(
    start_point: TrajectoryPoint, end_point: TrajectoryPoint, epsg_id: int
) -> float:
    if epsg_id not in _distance_area_cache:
        _distance_area_cache[epsg_id] = create_distance_area(epsg_id)
    qgs_d = _distance_area_cache[epsg_id]
    return qgs_d.measureLine(
        QgsPointXY(start_point.getX(), start_point.getY()),
        QgsPointXY(end_point.getX(), end_point.getY()),
    )


def create_coordinate_transform(
    epsg_id_source: int, epsg_id_target: int
) -> QgsCoordinateTransform:
    return QgsCoordinateTransform(
        QgsCoordinateReferenceSystem.fromEpsgId(epsg_id_source),
        QgsCoordinateReferenceSystem.fromEpsgId(epsg_id_target),
        QgsProject.instance(),
    )


def get_line_vertices(line: QgsGeometry) -> list:
    """Return ordered vertices from a single-part or multipart line geometry."""
    points = []
    for part in line.parts():
        points.extend(part.points())
    return points


def get_intersection_point_runway_and_taxi_route(runway, taxi_route) -> QgsGeometry:
    """
    Returns the entry point of a Taxiway route on the Runway.
    May return an empty geometry if there is no intersection.

    Args:
        runway (Runway): Runway object.
        taxi_route (TaxiwayRoute): Taxiway route object.

    Returns:
        QgsGeometry: Geometry (point) object resulting from the intersection. It may be an EMPTY geometry.
    """
    runway_geom = QgsGeometry.fromWkt(runway.getGeometryText())
    taxi_route_geom = QgsGeometry.fromWkt(taxi_route.getSegmentsAsLineString().wkt)
    intersection = runway_geom.buffer(1, 10).intersection(taxi_route_geom)

    return intersection if intersection.isEmpty() else intersection.centroid().asPoint()


def clip_segment_to_grid(
    x1: float,
    y1: float,
    z1: float,
    x2: float,
    y2: float,
    z2: float,
    grid_bounds: dict,
) -> tuple:
    """
    Clip a single line segment to the axis-aligned bounding box *grid_bounds*.

    Returns:
        (clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, distance_fraction)
        where *distance_fraction* is the ratio of the clipped 2-D length to the
        original 2-D length.
        Returns (None, None, None, None, None, None, 0.0) if the segment is
        fully outside the grid.
    """
    original_distance = getDistanceBetweenPoints(x1, y1, 0.0, x2, y2, 0.0)

    # Zero-length segment (e.g. stationary point). A point has no length to clip;
    # return it unchanged with fraction=1.0 if it's inside the grid, or
    # fraction=0.0 (with None coords) if outside.
    if original_distance == 0:
        inside = (
            grid_bounds["x_min"] <= x1 <= grid_bounds["x_max"]
            and grid_bounds["y_min"] <= y1 <= grid_bounds["y_max"]
        )
        if inside:
            return x1, y1, z1, x2, y2, z2, 1.0
        return None, None, None, None, None, None, 0.0

    clip_rect = QgsRectangle(
        grid_bounds["x_min"],
        grid_bounds["y_min"],
        grid_bounds["x_max"],
        grid_bounds["y_max"],
    )
    clipped = QgsClipper.clippedLine(
        QgsLineString([QgsPoint(x1, y1), QgsPoint(x2, y2)]), clip_rect
    )

    if clipped.isEmpty() or len(clipped) < 2:
        return None, None, None, None, None, None, 0.0

    try:
        clip_x1, clip_y1 = clipped[0].x(), clipped[0].y()
        clip_x2, clip_y2 = clipped[-1].x(), clipped[-1].y()

        dx, dy = x2 - x1, y2 - y1
        if abs(dx) > abs(dy):
            t1 = (clip_x1 - x1) / dx if dx else 0.0
            t2 = (clip_x2 - x1) / dx if dx else 1.0
        else:
            t1 = (clip_y1 - y1) / dy if dy else 0.0
            t2 = (clip_y2 - y1) / dy if dy else 1.0

        t1 = max(0.0, min(1.0, t1))
        t2 = max(0.0, min(1.0, t2))
        clip_z1 = z1 + t1 * (z2 - z1)
        clip_z2 = z1 + t2 * (z2 - z1)

        clipped_distance = getDistanceBetweenPoints(
            clip_x1, clip_y1, 0.0, clip_x2, clip_y2, 0.0
        )
        fraction = clipped_distance / original_distance

        return clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction

    except Exception as exc:
        logger.error("clip_segment_to_grid: %s", exc)
        return None, None, None, None, None, None, 0.0


def clip_trajectory_segment_to_grid(
    start_point: TrajectoryPoint, end_point: TrajectoryPoint, grid_bounds: dict
) -> tuple:
    """
    Clip a trajectory segment to grid bounds, returning TrajectoryPoint objects.

    Returns:
        (clipped_start, clipped_end, distance_fraction) or (None, None, 0.0).
    """
    x1, y1, z1 = start_point.getX(), start_point.getY(), start_point.getZ()
    x2, y2, z2 = end_point.getX(), end_point.getY(), end_point.getZ()

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )
    if clip_x1 is None:
        return None, None, 0.0

    clipped_start = TrajectoryPoint(
        {
            "id": start_point.getIdentifier(),
            "x": clip_x1,
            "y": clip_y1,
            "z": clip_z1,
            "course": start_point.getCourse(),
        }
    )
    clipped_end = TrajectoryPoint(
        {
            "id": end_point.getIdentifier(),
            "x": clip_x2,
            "y": clip_y2,
            "z": clip_z2,
            "course": end_point.getCourse(),
        }
    )
    return clipped_start, clipped_end, fraction


def _points_close(a: tuple, b: tuple, eps: float = _COORD_EPS) -> bool:
    """Return True if two (x, y, z) coordinate tuples are within *eps* of each other."""
    return (
        abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps and abs(a[2] - b[2]) <= eps
    )


def clip_linestring_to_grid(geometry_wkt: str, grid_bounds: dict) -> tuple:
    """
    Clip a LineString or MultiLineString geometry to *grid_bounds*.

    Handles both single-part (LINESTRING) and multi-part (MULTILINESTRING)
    geometries.  Each sub-part is clipped segment-by-segment; the surviving
    segments are stitched back into a LINESTRING Z (contiguous) or
    MULTILINESTRING Z (non-contiguous).

    Args:
        geometry_wkt: WKT in the same CRS as grid_bounds (EPSG:3857).
        grid_bounds:  Dict with x_min, x_max, y_min, y_max.

    Returns:
        (clipped_wkt, length_fraction) or (None, 0.0) if fully outside.
    """
    try:
        geom = ogr.CreateGeometryFromWkt(geometry_wkt)
        if geom is None:
            logger.warning("clip_linestring_to_grid: could not parse WKT")
            return geometry_wkt, 1.0

        flat_type = ogr.GT_Flatten(geom.GetGeometryType())
        if flat_type == ogr.wkbLineString:
            parts = [geom]
        elif flat_type == ogr.wkbMultiLineString:
            parts = [geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())]
        else:
            return geometry_wkt, 1.0

        if not parts:
            return geometry_wkt, 1.0

        original_length = sum(getDistanceOfLineStringXY(p.ExportToWkt()) for p in parts)
        if original_length == 0:
            return geometry_wkt, 1.0

        all_clipped_segments = []
        for part in parts:
            n_pts = part.GetPointCount()
            if n_pts < 2:
                continue
            pts = [part.GetPoint(i) for i in range(n_pts)]
            for i in range(len(pts) - 1):
                result = clip_segment_to_grid(*pts[i], *pts[i + 1], grid_bounds)
                if result[0] is not None:
                    all_clipped_segments.append(result[:6])

        if not all_clipped_segments:
            return None, 0.0

        # B10 fix: use epsilon-tolerance for continuity check
        line_chains: list = []
        current_chain: list = []
        for seg in all_clipped_segments:
            p_start = seg[:3]
            p_end = seg[3:]
            if not current_chain or not _points_close(current_chain[-1], p_start):
                if len(current_chain) >= 2:
                    line_chains.append(current_chain)
                current_chain = [p_start, p_end]
            else:
                current_chain.append(p_end)
        if len(current_chain) >= 2:
            line_chains.append(current_chain)

        if not line_chains:
            return None, 0.0

        if len(line_chains) == 1:
            coords = ", ".join(f"{x} {y} {z}" for x, y, z in line_chains[0])
            clipped_wkt = f"LINESTRING Z({coords})"
        else:
            parts_str = ", ".join(
                "(" + ", ".join(f"{x} {y} {z}" for x, y, z in chain) + ")"
                for chain in line_chains
            )
            clipped_wkt = f"MULTILINESTRING Z({parts_str})"

        clipped_length = getDistanceOfLineStringXY(clipped_wkt)
        length_fraction = (
            clipped_length / original_length if original_length > 0 else 1.0
        )
        return clipped_wkt, length_fraction

    except Exception as exc:
        logger.error("clip_linestring_to_grid: %s", exc)
        return geometry_wkt, 1.0
