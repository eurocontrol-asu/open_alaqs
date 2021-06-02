import math
import logging

import ogr
import osr
import shapely.wkt
import shapely.ops
import shapely.geometry
from geographiclib.geodesic import Geodesic

from open_alaqs.alaqs_core.tools import conversion, Iterator

logger = logging.getLogger("__alaqs__.%s" % __name__)


def getAngleXY(x, y, z=0., origin_x=0., origin_y=0., origin_z=0.,
               indegrees=False):
    '''returns the angle (in radians) between x and y relative to origin (origin_x,origin_y)'''
    res = 0.
    x = conversion.convertToFloat(x)
    y = conversion.convertToFloat(y)
    z = conversion.convertToFloat(z)
    origin_x = conversion.convertToFloat(origin_x)
    origin_y = conversion.convertToFloat(origin_y)
    origin_z = conversion.convertToFloat(origin_z)

    if not (x - origin_x):
        res = math.pi / 2.
    else:
        res = math.atan((y - origin_y) / (x - origin_x))
    if indegrees:
        res = rad2deg(res)
    return res


def getDistanceXY(x, y, z=0., origin_x=0., origin_y=0., origin_z=0.) -> float:
    """
    Determine the radius for the circle by x and y relative to origin
    (origin_x,origin_y)
    """
    x = conversion.convertToFloat(x)
    y = conversion.convertToFloat(y)
    return math.sqrt(x ** 2 + y ** 2)


def rad2deg(val: float) -> float:
    return math.degrees(val)


def deg2rad(val: float) -> float:
    return math.radians(val)


def getDistance(
        lat1: float,
        lon1: float,
        azimuth: float,
        distance: float,
        epsg_id: int = 4326) -> dict:
    geod = getGeodesic(epsg_id)

    # Solve the direct geodesic problem where the length of the geodesic is
    # specified in terms of distance.
    return geod.Direct(lat1, lon1, azimuth, distance)


def getGeodesic(epsg_id=4326):
    return Geodesic(getSpatialReference(epsg_id).GetSemiMajor(),
                    1. / getSpatialReference(epsg_id).GetInvFlattening())


def getGeodesicLine(inverseDistance_dic, EPSG_id=4326):
    geod = getGeodesic(EPSG_id)
    line = geod.Line(inverseDistance_dic['lat1'], inverseDistance_dic['lon1'],
                     inverseDistance_dic['azi1'])
    return line


def getInverseDistanceLine(
        inv_distance_dict: dict,
        number_points: int,
        epsg_id: int = 4326) -> list:
    geod = getGeodesic(epsg_id)
    line = geod.Line(inv_distance_dict['lat1'], inv_distance_dict['lon1'],
                     inv_distance_dict['azi1'])
    val = []
    for i in range(number_points + 1):
        point = line.Position(inv_distance_dict['s12'] / number_points * i)
        val.append((point['lat2'], point['lon2']))
    return val


def getInverseDistance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        epsg_id: int = 4326) -> dict:
    geod = getGeodesic(epsg_id)

    # Solve the inverse geodesic problem
    return geod.Inverse(lat1, lon1, lat2, lon2)


def getDistanceOfLineStringXYZ(
        geometry_wkt,
        distance_z: float = 0.,
        epsg_id_source: int = 3857,
        epsg_id_target: int = 4326) -> float:
    distance = getDistanceOfLineStringXY(geometry_wkt, epsg_id_source,
                                         epsg_id_target)

    return math.sqrt(distance * distance + distance_z * distance_z)


def getDistanceOfLineStringXY(
        geometry_wkt,
        epsg_id_source: int = 3857,
        epsg_id_target: int = 4326) -> float:
    if isinstance(geometry_wkt, ogr.Geometry):
        geometry_wkt = geometry_wkt.ExportToWkt()

    (geometry_wkt, swap) = reproject_geometry(geometry_wkt, epsg_id_source,
                                              epsg_id_target)
    points_tuple_list = getAllPoints(geometry_wkt, swap)
    res = 0.

    # calculate length pairwise and sum the result
    for (start_point_, end_point_) in Iterator.pairwise(points_tuple_list):
        res_ = getInverseDistance(start_point_[0], start_point_[1],
                                  end_point_[0], end_point_[1])
        if "s12" in res_:
            res_ = conversion.convertToFloat(res_["s12"])
            if res_ is None:
                res_ = 0.
        res += res_
    return res


def getArea(val):
    if isinstance(val, str):
        p = ogr.CreateGeometryFromWkt(val)
        area = p.GetArea()
        return area
    else:
        raise Exception(
            "val with value '%s' is of type '%s', but only '%s' "
            "implemented." % (val, type(val), type("")))


def getIntersectionXY(p1, p2):
    poly1 = p1
    poly2 = p2
    if not isinstance(p1, ogr.Geometry):
        poly1 = ogr.CreateGeometryFromWkt(p1)
    if not isinstance(p2, ogr.Geometry):
        poly2 = ogr.CreateGeometryFromWkt(p2)

    intersection = None
    if poly1 is None:
        logger.error("getIntersectionXY: Poly 1 '%s' is None." % (str(p1)))
    elif poly2 is None:
        logger.error("getIntersectionXY: Poly 2 '%s' is None." % (str(p2)))
    else:
        intersection = poly1.Intersection(poly2)

    if intersection is not None and not intersection.IsEmpty():
        return intersection.ExportToWkt()
    return ""


def getPoint(wkt, x=0., y=0., z=0., swap_xy=False):
    wkt = wkt.replace("POINTZ", "POINT").replace("pointz", "point")
    point = ogr.Geometry(ogr.wkbPoint)

    if wkt:
        point2 = ogr.CreateGeometryFromWkt(wkt)
        if point2 is None:
            logger.error("Could not create ogr.wkbPoint from wkt='%s'" % wkt)
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


def getPointGeometryText(p1, p2, p3=0., swap_xy=False):
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


def getLineFromWkt(wkt):
    geom = ogr.CreateGeometryFromWkt(wkt)
    return geom


def getRectangleXYFromBoundingBox(bbox):
    # Create ring
    ringLower = ogr.Geometry(ogr.wkbLinearRing)
    ringLower.AddPoint(bbox["x_min"], bbox["y_min"])
    ringLower.AddPoint(bbox["x_max"], bbox["y_min"])
    ringLower.AddPoint(bbox["x_max"], bbox["y_max"])
    ringLower.AddPoint(bbox["x_min"], bbox["y_max"])
    ringLower.AddPoint(bbox["x_min"], bbox["y_min"])

    # Create polygon
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ringLower)

    return poly


def getRectangleXYZFromBoundingBox(
        left_line,
        right_line,
        epsg_id_source=3857,
        epsg_id_target=4326):
    new_geometry_wkt_left = \
        reproject_geometry(left_line, epsg_id_target, epsg_id_source)[0]
    new_points = getAllPoints(new_geometry_wkt_left)
    lon_l1, lat_l1, alt11 = new_points[0][0], new_points[0][1], new_points[0][2]
    lon_l2, lat_l2, alt12 = new_points[1][0], new_points[1][1], new_points[1][2]

    new_geometry_wkt_right = \
        reproject_geometry(right_line, epsg_id_target, epsg_id_source)[0]
    new_points = getAllPoints(new_geometry_wkt_right)
    lon_r1, lat_r1, alt21 = new_points[0][0], new_points[0][1], new_points[0][2]
    lon_r2, lat_r2, alt22 = new_points[1][0], new_points[1][1], new_points[1][2]

    # Create ring
    ringLower = ogr.Geometry(ogr.wkbLinearRing)
    ringLower.AddPoint(lon_l2, lat_l2, alt12)
    ringLower.AddPoint(lon_r2, lat_r2, alt22)
    ringLower.AddPoint(lon_r1, lat_r1, alt21)
    ringLower.AddPoint(lon_l1, lat_l1, alt11)
    ringLower.AddPoint(lon_l2, lat_l2, alt12)

    # Create polygon
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ringLower)
    return poly


def getLineGeometryText(p1, p2):
    return getLine(p1, p2).ExportToWkt()


def getBoundingBox(val):
    if isinstance(val, ogr.Geometry):
        bbox = val.GetEnvelope3D()
        return {
            "x_min": bbox[0],
            "x_max": bbox[1],
            "y_min": bbox[2],
            "y_max": bbox[3],
            "z_min": bbox[4],
            "z_max": bbox[5]
        }
    elif isinstance(val, str):
        return getBoundingBox(ogr.CreateGeometryFromWkt(val))
    else:
        return None


def addHeightToGeometryWkt(geometry_wkt, height):
    geom = shapely.wkt.loads(geometry_wkt)
    shifted_geom = shapely.ops.transform(lambda x, y, z=None: (x, y, height),
                                         geom)
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
    relative_area_in_cell_ = 0.
    matched_area_ = getIntersectionXY(geometry_wkt, bbox_polygon_)
    if matched_area_:
        matched_area_geom = ogr.CreateGeometryFromWkt(matched_area_)

        # http://www.gdal.org/ogr__core_8h.html
        if matched_area_geom.GetGeometryType() in [ogr.wkbPoint,
                                                   ogr.wkbMultiPoint,
                                                   ogr.wkbPoint25D,
                                                   ogr.wkbMultiPoint25D]:
            relative_area_in_cell_ = 1.
        elif matched_area_geom.GetGeometryType() in [ogr.wkbPolygon,
                                                     ogr.wkbMultiPolygon,
                                                     ogr.wkbPolygon25D,
                                                     ogr.wkbMultiPolygon25D]:
            relative_area_in_cell_ = matched_area_geom.GetArea() / total_area_of_geometry
        else:
            logger.error(
                "Matched area '%s' with type id '%i' is neither polygon nor "
                "point! Setting matching area to zero ... "
                % (matched_area_, matched_area_geom.GetGeometryType()))

    return relative_area_in_cell_


def getRelativeLengthXYInBoundingBox(
        geometry_wkt,
        cell_bbox,
                                     EPSG_id_source=3857,
        EPSG_id_target=4326):
    bbox_polygon_ = getRectangleXYFromBoundingBox(cell_bbox)

    total_length = getDistanceOfLineStringXY(geometry_wkt,
                                             epsg_id_source=EPSG_id_source,
                                             epsg_id_target=EPSG_id_target)

    dist_xy = 0.
    intersection_wkt = getIntersectionXY(geometry_wkt, bbox_polygon_)
    # logger.debug("Intersection: %s" % (intersection_wkt))

    if intersection_wkt:
        dist_xy = getDistanceOfLineStringXY(intersection_wkt, EPSG_id_source,
                                            EPSG_id_target)
        # logger.debug("Distance (x,y): %s" % (dist_xy))

    if dist_xy and total_length:
        return abs(dist_xy) / abs(total_length)
    else:
        return 0.


def getRelativeHeightInCell(matched_cell, z_min, z_max):
    # ToDo: add exceptions
    if z_min == z_max:
        return 1
    else:
        return abs(max(z_min, matched_cell["zmin"]) - min(z_max, matched_cell[
            "zmax"])) / (z_max - z_min)


def getRelativeHeightInBoundingBox(line_z_min, line_z_max, cell_bbox):
    total_height = float(abs(line_z_max - line_z_min))

    # if line.GetPointCount()==2:
    if line_z_max < cell_bbox["z_min"]:
        height_line_in_bbox = 0.
    elif line_z_min > cell_bbox["z_max"]:
        height_line_in_bbox = 0.
    else:
        if total_height == 0.:
            height_line_in_bbox = 1.
        else:
            height_line_in_bbox = abs(
                max(line_z_min, cell_bbox["z_min"]) - min(line_z_max, cell_bbox[
                    "z_max"])) / total_height
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


def getCoordinateTransformation(epsg_id_source, epsg_id_target):
    cache_id = "%s:%s" % (epsg_id_source, epsg_id_target)
    try:
        if cache_id not in transformations_cache:
            source = getSpatialReference(epsg_id_source)
            target = getSpatialReference(epsg_id_target)
            transformations_cache[cache_id] = \
                osr.CoordinateTransformation(source, target)
        return transformations_cache[cache_id]
    except Exception as xc:
        logger.error("getCoordinateTransformation: %s" % xc)


def reproject_Point(
        x: float,
        y: float,
        epsg_id_source: int = 3857,
        epsg_id_target: int = 4326) -> tuple:
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
        logger.error("reproject_Point: %s" % xc)


def reproject_geometry(geometry_wkt, EPSG_id_source=3857, EPSG_id_target=4326):
    source = osr.SpatialReference()
    source.ImportFromEPSG(EPSG_id_source)

    target = osr.SpatialReference()
    target.ImportFromEPSG(EPSG_id_target)

    transform = osr.CoordinateTransformation(source, target)

    geom = ogr.CreateGeometryFromWkt(geometry_wkt)
    geom.Transform(transform)

    new_wkt_ = geom.ExportToWkt()

    swap_coordinates = False
    if (source.IsGeographic() and not target.IsGeographic()) or (
            not source.IsGeographic() and target.IsGeographic()):
        swap_coordinates = True

    return new_wkt_, swap_coordinates


if __name__ == "__main__":
    EPSG_id_source = 3857
    EPSG_id_target = 4326

    target_point_distance = 1000.
    target_point_azimuth_delta = 0.

    target_point = (0., 0., 0)
    target_point_distance = 1000.
    target_point_azimuth_delta = 0.

    # logger.info("Example to shift a point, which is the starting point of a line, by azimuth=%f and distance=%f" % (target_point_distance,target_point_azimuth_delta))
    # geometry_wkt = 'LINESTRING(-381575.883971 6574045.869323, -378514.289082 6574799.844183)'
    # geometry_wkt = 'LINESTRING Z (5283717.537279 -2130787.098558 0, 5286914.309731 -2131290.571928 0)'
    # linestringZ = "LINESTRING Z (802522.9287219999800000 5412293.0346990004000000 0.0000000000000000, \
    #                802566.7463620000100000 5412057.8531090003000000 0.0000000000000000,  \
    #                802569.4691520000300000 5412021.7873379998000000 0.0000000000000000, \
    #                802560.6113729999600000 5411989.1412330000000000 0.0000000000000000, \
    #                802541.5904579999600000 5411961.9034900004000000 0.0000000000000000)"

    #
    # geometry_wkt_linestringZ = ogr.CreateGeometryFromWkt(linestringZ)
    # all_points = getAllPoints(geometry_wkt_linestringZ.ExportToWkt())
    # for i, point_ in enumerate(all_points):
    #     if i + 1 == len(all_points):
    #         break
    #     print all_points[i], all_points[i+1]

    cell_bbox = {
        "x_min": -702515,
        "x_max": -700114,
        "y_min": 6431659,
        "y_max": 6433284,
        "z_min": 0.,
        "z_max": 100.}

    geometry_wkt = 'MULTIPOLYGON (((-700192.67432202795 6432957.8668220686 0,-700270.09652248421 6433092.5443868963 0,\
    -702515.64579305821 6431794.0028838804 0,-702438.19944851752 6431659.3670251323 0,-700192.67432202795 6432957.8668220686 0)),\
    ((-700144.60100104206 6433000.0305312127 0,-700250.23477982497 6433113.8068044037 0,-700284.2023906844 6433082.0931441719 0,\
    -700178.56854844943 6432968.3177361246 0,-700144.60100104206 6433000.0305312127 0)),\
    ((-700115.02072731219 6433066.1398939332 0,-700265.1580180655 6433104.854377497 0,-700272.48611001321 6433076.2754381429 0,\
    -700122.34929904691 6433037.561225648 0,-700115.02072731219 6433066.1398939332 0)),\
    ((-700121.80066872889 6433149.7483826876 0,-700274.89586863376 6433125.3115362506 0,-700266.63622290455 6433073.2788357707 0,\
    -700113.54195140419 6433097.7153740395 0,-700121.80066872889 6433149.7483826876 0)),\
    ((-700150.27059399022 6433215.6142809577 0,-700289.37334578461 6433146.9932222459 0,-700267.89919596107 6433103.2199053848 0,\
    -700128.79699519812 6433171.8402579064 0,-700150.27059399022 6433215.6142809577 0)),\
    ((-700196.22509095783 6433283.0764916642 0,-700323.25042050215 6433193.9624856226 0,-700283.33435914386 6433136.7474487275 0,\
    -700156.30947376427 6433225.8602378787 0,-700196.22509095783 6433283.0764916642 0)))'

    geom = ogr.CreateGeometryFromWkt(geometry_wkt)
    # fix_print_with_import
    print(getRelativeAreaInBoundingBox(geometry_wkt, cell_bbox))

    # print getRelativeAreaInBoundingBox(geom.ExportToWkt(), geom.GetEnvelope())

    # (geometry_wkt, swap)  = reproject_geometry(geometry_wkt, EPSG_id_source, EPSG_id_target)
    # for i in range(0, geom.GetGeometryCount()):
    #     g = geom.GetGeometryRef(i)
    #     print "%i). %s" % (i, g.ExportToWkt())

    (start_point_1, start_point_2) = (49.916667, -6.316667)
    # (end_point_1,end_point_2) = (49.907287176626703, -6.346888779001599)

    #       dx (+/- 90),     dy (0/180)
    # R1: 1620.26, 1629.06
    # R2: 537.72, 1003.62
    # R3: -544.808, 378.18
    # R4: 727.5, 3175.35

    # RECEPTORS
    # xp = [1620.26, 537.72, -544.808, 727.5]
    # yp = [1629.06, 1003.62, 378.18, 3175.35]
    #
    # for y in yp:
    #     # def getInverseDistance(lat1, lon1, lat2, lon2, EPSG_id=4326):
    #     # print "Distance: %s"%getInverseDistance(start_point_1,start_point_2, end_point_1,end_point_2)
    #     azimuth_delta = 90 if y > 0 else -90
    #     # print "azimuth_delta: %s"%azimuth_delta
    #     target_point_distance = abs(y)
    #     # print "Delta %s"%target_point_distance
    #     start_target_values = getDistance(start_point_1, start_point_2, azimuth_delta, target_point_distance)
    #     # print start_target_values
    #     target_point_wkt = getPointGeometryText(start_target_values["lat2"], start_target_values["lon2"], 0., swap)
    #     (target_point_wkt, swap_) = reproject_geometry(target_point_wkt, EPSG_id_target, EPSG_id_source)
    #     print target_point_wkt
    #
    # for x in xp:
    #     # def getInverseDistance(lat1, lon1, lat2, lon2, EPSG_id=4326):
    #     # print "Distance: %s"%getInverseDistance(start_point_1,start_point_2, end_point_1,end_point_2)
    #     azimuth_delta = 0 if x > 0 else -180
    #     # print "azimuth_delta: %s" % azimuth_delta
    #     target_point_distance = abs(x)
    #     # print "Delta %s" % target_point_distance
    #     start_target_values = getDistance(start_point_1, start_point_2, azimuth_delta, target_point_distance)
    #     # print start_target_values
    #     target_point_wkt = getPointGeometryText(start_target_values["lat2"], start_target_values["lon2"], 0., swap)
    #     (target_point_wkt, swap_) = reproject_geometry(target_point_wkt, EPSG_id_target, EPSG_id_source)
    #     print target_point_wkt

    # startPoint_wkt = "POINT(-703168 6431857)"
    # (geometry_s_wkt, swap) = reproject_geometry(startPoint_wkt, EPSG_id_source, EPSG_id_target)
    # print geometry_s_wkt
    # # POINT(-6.316665617037555    49.916669768275703)
    # endPoint_wkt = "POINT(-706532.427 6430235.068)"
    # (geometry_e_wkt, swap) = reproject_geometry(endPoint_wkt, EPSG_id_source, EPSG_id_target)
    # # -6.34689, 49.90729, -706532.427, 6430235.068
    # print geometry_e_wkt
    # # POINT(-6.346888779001599    49.907287176626703)

    # line = getLine(startPoint_wkt, endPoint_wkt)
    # bbox = getBoundingBox(line)
    #
    # intersection_wkt = getIntersectionXY(line, getRectangleXYFromBoundingBox(bbox))
    # print "Bounding box for points '%s' and '%s' is '%s'" % (startPoint_wkt, endPoint_wkt, sorted(bbox.items()))
    # print "Intersection: %s"%intersection_wkt
    # # logger.info("Bounding box for points '%s' and '%s' is '%s'" % (startPoint_wkt, endPoint_wkt, sorted(bbox.items())))
    # # print "Distance: %f" % (getDistanceOfLineStringXY('LINESTRING(6431857 -703168, 6430056.5214124396443367)', EPSG_id_source, EPSG_id_target))
    # # # logger.info("Distance: %f" % (getDistanceOfLineStringXY('LINESTRING(-381575.883971 6574045.869323, -378514.289082 6574799.844183)', EPSG_id_source, EPSG_id_target)))
    # print "Length XY of intersection: %f" % (getDistanceOfLineStringXY(intersection_wkt, EPSG_id_source, EPSG_id_target))
    #

    # points_tuple_list = getAllPoints(geometry_wkt, swap)
    # print "Points: %s" % (str(points_tuple_list))
    # logger.debug("Points: %s" % (str(points_tuple_list)))

    # if len(points_tuple_list)>=2:
    #     (start_point_1,start_point_2,start_point_3) = points_tuple_list[0]
    #     (end_point_1,end_point_2, end_point_3) = points_tuple_list[-1]
    #
    #     start_point_azimuth = getInverseDistance(start_point_1,start_point_2, end_point_1,end_point_2)["azi1"]
    #
    #     start_target_values = getDistance(start_point_1, start_point_2, start_point_azimuth+target_point_azimuth_delta, target_point_distance)
    #     target_point_wkt = getPointGeometryText(start_target_values["lat2"], start_target_values["lon2"], 0., swap)
    #
    #     (target_point_wkt, swap_) = reproject_geometry(target_point_wkt, EPSG_id_target, EPSG_id_source)
    #     # logger.info("Target point: '%s'" % (target_point_wkt))
    #     print "Target point: '%s'" % (target_point_wkt)
    # else:
    #     print "Did not find enough points for geometry '%s'" % (geometry_wkt)
    #     # logger.error("Did not find enough points for geometry '%s'" % (geometry_wkt))
    #
    # getAngleXY(10., 10., 0., 0., 0.,0., indegrees=True)
    #

    #
    # line = "LINESTRING (-380344.54955599998 6574349.2538649999 0,-376293.89817599999 6575345.899884 304.8)"
    # bbox = getBoundingBox(line)
    # cell_bbox = {
    #     "x_min":-500000.,
    #     "x_max":0.,
    #     "y_min":0.,
    #     "y_max":7000000.,
    #     "z_min":0.,
    #     "z_max":500.}
    # bbox_cell = getRectangleXYFromBoundingBox(cell_bbox)
    # print "Bounding box cell: %s" % (bbox_cell)
    # # logger.info("Bounding box cell: %s" % (bbox_cell))
    # intersection_wkt = getIntersectionXY(line, bbox_cell)
    # print "Intersection: %s" % (intersection_wkt)
    # # logger.info("Intersection: %s" % (intersection_wkt))
    #
    # #logger.info("Length XY of intersection: %f" % (getDistanceOfLineStringXY(intersection_wkt, EPSG_id_source, EPSG_id_target)))
    # #logger.info("Length XYZ of intersection: %f" % (getDistanceOfLineStringXY(intersection_wkt, EPSG_id_source, EPSG_id_target)))
    #
    #

    # bbox_cell = getRectangleXYFromBoundingBox(cell_bbox)
    # print "Bounding box of cell: %s" % (bbox_cell)
    # # logger.info("Bounding box of cell: %s" % (bbox_cell))
    #
    # point = "POINT(-0.5 -0.5 0.)"
    # point = "POINT(0.5 0.5 0.)"
    # print getRelativeAreaInBoundingBox(point, cell_bbox)
    # # logger.info(getRelativeAreaInBoundingBox(point, cell_bbox))
    #
    # # logger.info("------- Multipoint example -------")
    # print "------- Multipoint example -------"
    # #wkt_ = 'LINESTRING(-385424.208403 6573462.710644, -385284.264145 6573487.70069, -385124.327849 6573517.688746, -384719.489101 6573577.664857, -384179.704104 6573737.601152, -383849.835494 6573792.579254, -383594.937023 6573792.579254, -383435.000728 6573767.589207, -382900.213739 6573667.629023, -382630.321241 6573612.650921, -382280.460594 6573582.662866, -381880.619855 6573582.662866, -381222.540744 6573615.114395, -380889.545418 6573591.569271, -380267.281424 6573500.752364, -379883.832261 6573430.116991, -379638.290252 6573413.299046, -379238.023143 6573409.935457, -378868.028336 6573440.207759, -378387.035087 6573494.025185, -377774.861861 6573588.205682, -377085.326085 6573742.930783, -376698.513332 6573853.929225, -376227.610851 6574045.653807)'
    # #logger.info("Length XY of intersection: %f" % (getDistanceOfLineStringXY(wkt_, EPSG_id_source, EPSG_id_target)))
    #
    # #logger.info("Distance: %f" % (getDistanceOfLineStringXY('LINESTRING(-381575.883971 6574045.869323, -378514.289082 6574799.844183)', EPSG_id_source, EPSG_id_target)))
    #
    # getLineGeometryText    # getArea(wkt_)
    #
    # print addHeightToGeometryWkt("Point (1. 1.)", 5.)
