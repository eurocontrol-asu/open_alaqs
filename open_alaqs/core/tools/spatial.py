import math
from typing import Union

import osgeo.ogr as ogr
import osgeo.osr as osr
import shapely.geometry
import shapely.ops
import shapely.wkt
from geographiclib.geodesic import Geodesic

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools import conversion
from open_alaqs.core.tools.iterator import pairwise

logger = get_logger(__name__)


def getDistanceBetweenPoints(x1, y1, z1, x2, y2, z2):
    """
    Determine the distance between two points
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
