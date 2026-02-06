import math
from typing import Union

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
from open_alaqs.core.tools.iterator import pairwise

logger = get_logger(__name__)


def getDistanceBetweenPoints(x1, y1, z1=0.0, x2=0.0, y2=0.0, z2=0.0):
    """
    Determine the distance between two points.

    Args:
        x1: X coordinate of first point
        y1: Y coordinate of first point
        z1: Z coordinate of first point (default: 0.0)
        x2: X coordinate of second point (default: 0.0)
        y2: Y coordinate of second point (default: 0.0)
        z2: Z coordinate of second point (default: 0.0)

    Returns:
        Euclidean distance between the two points
    """
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2) ** 0.5


def getDistanceXY(x, y, z=0.0, origin_x=0.0, origin_y=0.0, origin_z=0.0) -> float:
    """
    Determine the radius for the circle by x and y relative to origin
    (origin_x,origin_y)
    """
    x = conversion.convertToFloat(x)
    y = conversion.convertToFloat(y)
    return math.sqrt(x**2 + y**2)


def getDistance(
    lat1: float, lon1: float, azimuth: float, distance: float, epsg_id: int = 4326
) -> dict:
    geod = getGeodesic(epsg_id)

    # Solve the direct geodesic problem where the length of the geodesic is
    # specified in terms of distance.
    return geod.Direct(lat1, lon1, azimuth, distance)


def getGeodesic(epsg_id=4326):
    return Geodesic(
        getSpatialReference(epsg_id).GetSemiMajor(),
        1.0 / getSpatialReference(epsg_id).GetInvFlattening(),
    )


def getInverseDistance(
    lat1: float, lon1: float, lat2: float, lon2: float, epsg_id: int = 4326
) -> dict:
    geod = getGeodesic(epsg_id)

    # Solve the inverse geodesic problem
    return geod.Inverse(lat1, lon1, lat2, lon2)


def getDistanceOfLineStringXYZ(
    geometry_wkt,
    distance_z: float = 0.0,
    epsg_id_source: int = 3857,
    epsg_id_target: int = 4326,
) -> float:
    distance = getDistanceOfLineStringXY(geometry_wkt, epsg_id_source, epsg_id_target)

    return math.sqrt(distance * distance + distance_z * distance_z)


def getDistanceOfLineStringXY(
    geometry_wkt, epsg_id_source: int = 3857, epsg_id_target: int = 4326
) -> float:
    if isinstance(geometry_wkt, ogr.Geometry):
        geometry_wkt = geometry_wkt.ExportToWkt()

    (geometry_wkt, swap) = reproject_geometry(
        geometry_wkt, epsg_id_source, epsg_id_target
    )
    points_tuple_list = getAllPoints(geometry_wkt, swap)
    res = 0.0

    # calculate length pairwise and sum the result
    for start_point_, end_point_ in pairwise(points_tuple_list):
        res_ = getInverseDistance(
            start_point_[0], start_point_[1], end_point_[0], end_point_[1]
        )
        if "s12" in res_:
            res_ = conversion.convertToFloat(res_["s12"])
            if res_ is None:
                res_ = 0.0
        res += res_
    return res


def getArea(val):
    if isinstance(val, str):
        p = ogr.CreateGeometryFromWkt(val)
        area = p.GetArea()
        return area
    raise Exception(
        "val with value '%s' is of type '%s', but only '%s' "
        "implemented." % (val, type(val), type(""))
    )


def getIntersectionXY(p1, p2):
    poly1 = p1
    poly2 = p2
    if not isinstance(p1, ogr.Geometry):
        poly1 = ogr.CreateGeometryFromWkt(p1)
    if not isinstance(p2, ogr.Geometry):
        poly2 = ogr.CreateGeometryFromWkt(p2)

    intersection = None
    if poly1 is None:
        logger.error("getIntersectionXY: Poly 1 '%s' is None.", p1)
    elif poly2 is None:
        logger.error("getIntersectionXY: Poly 2 '%s' is None.", p2)
    else:
        intersection = poly1.Intersection(poly2)

    if intersection is not None and not intersection.IsEmpty():
        return intersection.ExportToWkt()
    return ""


def getPoint(wkt, x=0.0, y=0.0, z=0.0, swap_xy=False):
    wkt = wkt.replace("POINTZ", "POINT").replace("pointz", "point")
    point = ogr.Geometry(ogr.wkbPoint)

    if wkt:
        point2 = ogr.CreateGeometryFromWkt(wkt)
        if point2 is None:
            logger.error("Could not create ogr.wkbPoint from wkt='%s'", wkt)
        else:
            p1 = point2.GetX()
            p2 = point2.GetY()
            p3 = point2.GetZ()
            if swap_xy:
                point.AddPoint(p2, p1, p3)
            else:
                point.AddPoint(p1, p2, p3)
    else:
        if not swap_xy:
            point.AddPoint(x, y, z)
        else:
            point.AddPoint(y, x, z)

    return point


def getPointGeometryText(p1, p2, p3=0.0, swap_xy=False):
    return getPoint("", p1, p2, p3, swap_xy).ExportToWkt()


def getLine(p1_wkt, p2_wkt, swap_xy=False):
    geom = ogr.Geometry(ogr.wkbLineString)

    p1 = p1_wkt
    if not isinstance(p1_wkt, ogr.Geometry):
        p1 = getPoint(p1_wkt, swap_xy=swap_xy)
    p2 = p2_wkt
    if not isinstance(p2_wkt, ogr.Geometry):
        p2 = getPoint(p2_wkt, swap_xy=swap_xy)

    geom.AddPoint(p1.GetX(), p1.GetY(), p1.GetZ())
    geom.AddPoint(p2.GetX(), p2.GetY(), p2.GetZ())

    return geom


def getRectangleXYFromBoundingBox(bbox):
    # Create ring
    ring_lower = ogr.Geometry(ogr.wkbLinearRing)
    ring_lower.AddPoint(bbox["x_min"], bbox["y_min"])
    ring_lower.AddPoint(bbox["x_max"], bbox["y_min"])
    ring_lower.AddPoint(bbox["x_max"], bbox["y_max"])
    ring_lower.AddPoint(bbox["x_min"], bbox["y_max"])
    ring_lower.AddPoint(bbox["x_min"], bbox["y_min"])

    # Create polygon
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring_lower)

    return poly


def getRectangleXYZFromBoundingBox(
    left_line, right_line, epsg_id_source=3857, epsg_id_target=4326
):
    new_geometry_wkt_left = reproject_geometry(
        left_line, epsg_id_target, epsg_id_source
    )[0]
    new_points = getAllPoints(new_geometry_wkt_left)
    lon_l1, lat_l1, alt11 = new_points[0][0], new_points[0][1], new_points[0][2]
    lon_l2, lat_l2, alt12 = new_points[1][0], new_points[1][1], new_points[1][2]

    new_geometry_wkt_right = reproject_geometry(
        right_line, epsg_id_target, epsg_id_source
    )[0]
    new_points = getAllPoints(new_geometry_wkt_right)
    lon_r1, lat_r1, alt21 = new_points[0][0], new_points[0][1], new_points[0][2]
    lon_r2, lat_r2, alt22 = new_points[1][0], new_points[1][1], new_points[1][2]

    # Create ring
    ring_lower = ogr.Geometry(ogr.wkbLinearRing)
    ring_lower.AddPoint(lon_l2, lat_l2, alt12)
    ring_lower.AddPoint(lon_r2, lat_r2, alt22)
    ring_lower.AddPoint(lon_r1, lat_r1, alt21)
    ring_lower.AddPoint(lon_l1, lat_l1, alt11)
    ring_lower.AddPoint(lon_l2, lat_l2, alt12)

    # Create polygon
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring_lower)
    return poly


def getLineGeometryText(p1, p2):
    return getLine(p1, p2).ExportToWkt()


def getBoundingBox(val: Union[ogr.Geometry, str]) -> Union[dict, None]:
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
        return getBoundingBox(ogr.CreateGeometryFromWkt(val))


def addHeightToGeometryWkt(geometry_wkt, height):
    geom = shapely.wkt.loads(geometry_wkt)
    shifted_geom = shapely.ops.transform(lambda x, y, z=None: (x, y, height), geom)
    # return shapely.wkt.dumps(shifted_geom)
    return str(shifted_geom)

    # geom = ogr.CreateGeometryFromWkt(geometry_wkt)
    # new_geom = ogr.Geometry(geom.GetGeometryType())
    # for i in range(0, geomCre.GetGeometryCount()):
    #    g = geom.GetGeometryRef(i)
    #    if geom.GetGeometryType() in [ogr.wkbPoint, ogr.wkbPoint25D]
    # g_ = ogr.CreateGeometryFromWkt(str(shapely.wkt.dumps(shifted_geom)))
    # print g_.GetGeometryType() == ogr.wkbPoint25D


def getRelativeAreaInBoundingBox(geometry_wkt, cell_bbox):
    total_area_of_geometry = getArea(geometry_wkt)

    bbox_polygon_ = getRectangleXYFromBoundingBox(cell_bbox)
    relative_area_in_cell_ = 0.0
    matched_area_ = getIntersectionXY(geometry_wkt, bbox_polygon_)
    if matched_area_:
        matched_area_geom = ogr.CreateGeometryFromWkt(matched_area_)

        # http://www.gdal.org/ogr__core_8h.html
        if matched_area_geom.GetGeometryType() in [
            ogr.wkbPoint,
            ogr.wkbMultiPoint,
            ogr.wkbPoint25D,
            ogr.wkbMultiPoint25D,
        ]:
            relative_area_in_cell_ = 1.0
        elif matched_area_geom.GetGeometryType() in [
            ogr.wkbPolygon,
            ogr.wkbMultiPolygon,
            ogr.wkbPolygon25D,
            ogr.wkbMultiPolygon25D,
        ]:
            relative_area_in_cell_ = (
                matched_area_geom.GetArea() / total_area_of_geometry
            )
        else:
            logger.error(
                "Matched area '%s' with type id '%i' is neither polygon nor "
                "point! Setting matching area to zero ... ",
                matched_area_,
                matched_area_geom.GetGeometryType(),
            )

    return relative_area_in_cell_


def getRelativeLengthXYInBoundingBox(
    geometry_wkt, cell_bbox, epsg_id_source=3857, epsg_id_target=4326
):
    bbox_polygon_ = getRectangleXYFromBoundingBox(cell_bbox)

    total_length = getDistanceOfLineStringXY(
        geometry_wkt, epsg_id_source=epsg_id_source, epsg_id_target=epsg_id_target
    )

    dist_xy = 0.0
    intersection_wkt = getIntersectionXY(geometry_wkt, bbox_polygon_)
    # logger.debug("Intersection: %s" % (intersection_wkt))

    if intersection_wkt:
        dist_xy = getDistanceOfLineStringXY(
            intersection_wkt, epsg_id_source, epsg_id_target
        )
        # logger.debug("Distance (x,y): %s" % (dist_xy))

    if dist_xy and total_length:
        return abs(dist_xy) / abs(total_length)
    return 0.0


def getRelativeHeightInBoundingBox(
    line_z_min: float, line_z_max: float, cell_bbox: dict
) -> float:
    total_height = float(abs(line_z_max - line_z_min))

    # if line.GetPointCount()==2:
    if line_z_max < cell_bbox["z_min"]:
        height_line_in_bbox = 0.0
    elif line_z_min > cell_bbox["z_max"]:
        height_line_in_bbox = 0.0
    else:
        if total_height == 0.0:
            height_line_in_bbox = 1.0
        else:
            height_line_in_bbox = (
                abs(
                    max(line_z_min, cell_bbox["z_min"])
                    - min(line_z_max, cell_bbox["z_max"])
                )
                / total_height
            )
    return height_line_in_bbox


def CreateGeometryFromWkt(geometry_wkt):
    if isinstance(geometry_wkt, ogr.Geometry):
        return geometry_wkt
    return ogr.CreateGeometryFromWkt(geometry_wkt)


def getAllPoints(geometry_wkt, swap=False):
    """
    Note: Does not work for Multipart geometries
    (e.g., "MULTILINESTRING((0 0, 10 10),(20 20, 30 30))")
    """
    geom = geometry_wkt
    if not isinstance(geometry_wkt, ogr.Geometry):
        geom = ogr.CreateGeometryFromWkt(geometry_wkt)

    points_ = []
    for i in range(0, geom.GetPointCount()):
        # for i in xrange(0, geom.GetPointCount()):

        # GetPoint returns a tuple not a Geometry
        (x, y, z) = geom.GetPoint(i)
        if not swap:
            points_.append((x, y, z))
        else:
            points_.append((y, x, z))

    return points_


# cache
spatial_references = {}


def getSpatialReference(epsg_id):
    if epsg_id not in spatial_references:
        spatial_reference = osr.SpatialReference()
        spatial_reference.ImportFromEPSG(epsg_id)
        spatial_references[epsg_id] = spatial_reference
    return spatial_references[epsg_id]


# cache coordinate transformations
transformations_cache = {}


def reproject_Point(
    x: float, y: float, epsg_id_source: int = 3857, epsg_id_target: int = 4326
) -> tuple:
    try:
        # define point
        point = ogr.Geometry(ogr.wkbPoint)
        point.AddPoint(x, y)
        source = osr.SpatialReference()
        source.ImportFromEPSG(epsg_id_source)
        target = osr.SpatialReference()
        target.ImportFromEPSG(epsg_id_target)
        transform = osr.CoordinateTransformation(source, target)
        point.Transform(transform)
        return point, point.ExportToWkt()
    except Exception as xc:
        logger.error("reproject_Point: %s", xc)


def reproject_geometry(geometry_wkt, epsg_id_source=3857, epsg_id_target=4326):
    source = osr.SpatialReference()
    source.ImportFromEPSG(epsg_id_source)

    target = osr.SpatialReference()
    target.ImportFromEPSG(epsg_id_target)

    transform = osr.CoordinateTransformation(source, target)

    geom = ogr.CreateGeometryFromWkt(geometry_wkt)
    geom.Transform(transform)

    new_wkt_ = geom.ExportToWkt()

    swap_coordinates = False
    if (source.IsGeographic() and not target.IsGeographic()) or (
        not source.IsGeographic() and target.IsGeographic()
    ):
        swap_coordinates = True

    return new_wkt_, swap_coordinates


def create_distance_area(epsg_id_source: int) -> QgsDistanceArea:
    source_crs = QgsCoordinateReferenceSystem.fromEpsgId(epsg_id_source)
    qgs_d = QgsDistanceArea()
    qgs_d.setSourceCrs(source_crs, QgsProject.instance().transformContext())
    qgs_d.setEllipsoid(source_crs.ellipsoidAcronym())

    return qgs_d


def ellipsoidal_2d_distance(
    start_point: TrajectoryPoint, end_point: TrajectoryPoint, epsg_id: int
) -> float:
    qgs_d = create_distance_area(epsg_id)
    qgs_start_point = QgsPointXY(start_point.getX(), start_point.getY())
    qgs_end_point = QgsPointXY(end_point.getX(), end_point.getY())

    return qgs_d.measureLine(qgs_start_point, qgs_end_point)


def create_coordinate_transform(
    epsg_id_source: int, epsg_id_target: int
) -> QgsCoordinateTransform:
    return QgsCoordinateTransform(
        QgsCoordinateReferenceSystem.fromEpsgId(epsg_id_source),
        QgsCoordinateReferenceSystem.fromEpsgId(epsg_id_target),
        QgsProject.instance(),
    )


def get_line_vertices(line: QgsGeometry) -> list[QgsPoint]:
    """
    Returns a list of ordered vertices from the  given line geometry.
    Line can be either single part or multipart.
    """
    points = []
    for part in line.parts():
        points.extend(part.points())

    return points


def clip_segment_to_grid(
    x1: float, y1: float, z1: float, x2: float, y2: float, z2: float, grid_bounds: dict
) -> tuple:
    """
    Clip a segment to grid bounds using point coordinates.

    Args:
        x1, y1, z1: Start point coordinates
        x2, y2, z2: End point coordinates
        grid_bounds: Dict with x_min, x_max, y_min, y_max (in EPSG:3857 or consistent CRS)

    Returns:
        tuple: (clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, distance_fraction)
        where distance_fraction is the ratio of clipped distance to original distance
        Returns (None, None, None, None, None, None, 0.0) if segment is fully outside grid bounds
    """

    grid_x_min = grid_bounds["x_min"]
    grid_x_max = grid_bounds["x_max"]
    grid_y_min = grid_bounds["y_min"]
    grid_y_max = grid_bounds["y_max"]

    # Calculate original distance using getDistanceBetweenPoints (2D distance, z=0)
    original_distance = getDistanceBetweenPoints(x1, y1, 0.0, x2, y2, 0.0)

    if original_distance == 0:
        # Points are the same, no clipping needed
        return x1, y1, z1, x2, y2, z2, 1.0

    # Create QgsRectangle for clipping bounds
    clip_rect = QgsRectangle(grid_x_min, grid_y_min, grid_x_max, grid_y_max)

    # Create QgsLineString from the segment
    line = QgsLineString([QgsPoint(x1, y1), QgsPoint(x2, y2)])

    # Use QgsClipper to clip the line segment which returns a QPolygonF object
    clipped_polygon = QgsClipper.clippedLine(line, clip_rect)

    # Check if line was clipped (empty polygon means fully outside)
    if clipped_polygon.isEmpty():
        return None, None, None, None, None, None, 0.0

    # Extract points from QPolygonF
    try:
        if len(clipped_polygon) < 2:
            return None, None, None, None, None, None, 0.0

        # Get clipped start and end points from the polygon
        clip_x1 = clipped_polygon[0].x()
        clip_y1 = clipped_polygon[0].y()
        clip_x2 = clipped_polygon[-1].x()
        clip_y2 = clipped_polygon[-1].y()

        # Interpolate Z coordinates based on how far along the original line the clipped points are
        # Calculate parametric t values for the clipped points
        dx = x2 - x1
        dy = y2 - y1

        if abs(dx) > abs(dy):
            # Use x coordinate for interpolation (more numerically stable)
            t1 = (clip_x1 - x1) / dx if dx != 0 else 0.0
            t2 = (clip_x2 - x1) / dx if dx != 0 else 1.0
        else:
            # Use y coordinate for interpolation
            t1 = (clip_y1 - y1) / dy if dy != 0 else 0.0
            t2 = (clip_y2 - y1) / dy if dy != 0 else 1.0

        # Clamp t values to [0, 1] and interpolate Z
        t1 = max(0.0, min(1.0, t1))
        t2 = max(0.0, min(1.0, t2))

        clip_z1 = z1 + t1 * (z2 - z1)
        clip_z2 = z1 + t2 * (z2 - z1)

        # Calculate distance fraction using getDistanceBetweenPoints (2D distance)
        clipped_distance = getDistanceBetweenPoints(
            clip_x1, clip_y1, 0.0, clip_x2, clip_y2, 0.0
        )
        distance_fraction = (
            clipped_distance / original_distance if original_distance > 0 else 1.0
        )

        return clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, distance_fraction

    except Exception as e:
        logger.error(f"Error clipping segment with QgsClipper: {e}")
        return None, None, None, None, None, None, 0.0


def clip_trajectory_segment_to_grid(
    start_point: TrajectoryPoint, end_point: TrajectoryPoint, grid_bounds: dict
) -> tuple:
    """
    Clip a trajectory segment to grid bounds.
    Wrapper function that works with TrajectoryPoint objects.

    Args:
        start_point: The start TrajectoryPoint of the segment
        end_point: The end TrajectoryPoint of the segment
        grid_bounds: Dict with x_min, x_max, y_min, y_max

    Returns:
        tuple: (clipped_start_point, clipped_end_point, distance_fraction)
        where clipped points are TrajectoryPoint objects.
        Returns (None, None, 0.0) if segment is fully outside grid bounds
    """
    # Extract coordinates from TrajectoryPoint objects
    x1, y1, z1 = start_point.getX(), start_point.getY(), start_point.getZ()
    x2, y2, z2 = end_point.getX(), end_point.getY(), end_point.getZ()

    # Call core clipping function
    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    # Return None if segment is outside
    if clip_x1 is None:
        return None, None, 0.0

    # Create clipped TrajectoryPoint objects
    clipped_start_dict = {
        "id": start_point.getIdentifier(),
        "x": clip_x1,
        "y": clip_y1,
        "z": clip_z1,
        "course": start_point.getCourse(),
    }
    clipped_start = TrajectoryPoint(clipped_start_dict)

    clipped_end_dict = {
        "id": end_point.getIdentifier(),
        "x": clip_x2,
        "y": clip_y2,
        "z": clip_z2,
        "course": end_point.getCourse(),
    }
    clipped_end = TrajectoryPoint(clipped_end_dict)

    return clipped_start, clipped_end, fraction


def clip_linestring_to_grid(geometry_wkt: str, grid_bounds: dict) -> tuple:
    """
    Clip a LineString geometry to grid bounds.
    Wrapper function for clipping entire LineString geometries (e.g., roadways, runways).

    Args:
        geometry_wkt: WKT representation of the LineString
        grid_bounds: Dict with x_min, x_max, y_min, y_max

    Returns:
        tuple: (clipped_wkt, length_fraction) where length_fraction is the
               ratio of clipped length to original length.
               Returns (None, 0.0) if geometry is fully outside grid.
    """
    try:
        # Get original length
        original_length = getDistanceOfLineStringXY(geometry_wkt)

        if original_length == 0:
            return geometry_wkt, 1.0

        # Parse geometry to extract points
        points = getAllPoints(geometry_wkt)

        if len(points) < 2:
            return geometry_wkt, 1.0

        # Clip each segment and collect clipped segments with their lengths
        clipped_segments = []
        total_clipped_length = 0.0

        for i in range(len(points) - 1):
            x1, y1, z1 = points[i]
            x2, y2, z2 = points[i + 1]

            # Clip the segment using the core function
            clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
                clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
            )

            # If segment is partially or fully in grid, add to clipped segments
            if clip_x1 is not None:
                clipped_segments.append(
                    (clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2)
                )
                # Calculate the actual clipped segment length (2D distance)
                clipped_segment_length = getDistanceBetweenPoints(
                    clip_x1, clip_y1, 0.0, clip_x2, clip_y2, 0.0
                )
                total_clipped_length += clipped_segment_length

        if not clipped_segments:
            # Geometry is completely outside grid
            return None, 0.0

        # Reconstruct WKT from clipped segments
        points_list = []
        for seg in clipped_segments:
            x1, y1, z1, x2, y2, z2 = seg
            if not points_list or points_list[-1] != (x1, y1, z1):
                points_list.append((x1, y1, z1))
            points_list.append((x2, y2, z2))

        # Build WKT LineString
        coords_str = ", ".join([f"{x} {y} {z}" for x, y, z in points_list])
        clipped_wkt = f"LINESTRING Z({coords_str})"

        # Calculate length fraction from the actual clipped geometry
        clipped_wkt_length = getDistanceOfLineStringXY(clipped_wkt)
        length_fraction = (
            clipped_wkt_length / original_length if original_length > 0 else 1.0
        )

        return clipped_wkt, length_fraction

    except Exception as e:
        logger.error(f"Error clipping LineString to grid: {e}")
        # Return original geometry if clipping fails
        return geometry_wkt, 1.0
