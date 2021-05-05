from __future__ import print_function
import sqlite3 as sqlite
# from pysqlite2 import dbapi2 as sqlite
import os
import sys

def connect(db_name):
    # spatial_dll = os.path.join(os.path.dirname("__file__"), "/mod_spatialite.dll")
    # spatial_folder = os.path.dirname(os.path.abspath("__file__"))
    #
    # _dll = os.path.join(os.path.dirname(os.path.abspath(__file__)),"/mod_spatialite.dll")
    spatial_dll = os.path.join(os.path.dirname(__file__), "/mod_spatialite.dll")
    spatial_folder = os.path.dirname(os.path.abspath(__file__))

    if spatial_folder not in sys.path:
        sys.path.append(spatial_folder)
    if spatial_folder not in os.environ['PATH']:
        os.environ['PATH'] = spatial_folder + ';' + os.environ['PATH']

    conn = sqlite.connect(db_name)
    conn.enable_load_extension(True)
    try:
        conn.execute('SELECT load_extension("./mod_spatialite.dll")')
    except Exception as e:
        # return e
        # fix_print_with_import
        print("Exception: %s"%e)
    # conn.execute("SELECT load_extension('libspatialite-4.dll')")

    #try:
    #    conn.execute("SELECT InitSpatialMetaData()")
    #except:
    #    pass
    curs = conn.cursor()
    return conn, curs
    
def query_string(db_name, sql_text):
    conn = None
    try:
        conn, curs = connect(db_name)
        curs.execute(sql_text)
        result = curs.fetchall()
        return result
    except Exception as e:
        return e
    finally:
        if not conn is None:
            conn.close()

if __name__ == "__main__":
    
    """
    The below examples are intended to act as both a test and a tutorial for how to perform
    spatial queries on data using spatialite. The following geometries are defined
        
        line_two                    line_one is Exeter Airport main runway
            |                       line_two is a north-south line cutting this runway
            |                       line_the is the same as line_one but with EPSG 3857 coordinates
    ----------------- line_one
            |
            |
            
            +--------+              area_one is a 2x2 degree square whose lower left corner is located at [0 0]
            |area_two|              area_one is a 2x2 degree square whose lower left corner is located at [1 1]
        +--------+   |              line_fou is a 2 degree long linear feature heading directly east from [1 1]
        |   |    |   |
        |   +----|-------- line_four
        |area_one|
        +--------+
    """
    
    line_one = "LINESTRING (-3.427781 50.732117, -3.400245 50.73641)"
    line_two = "LINESTRING (-3.41 50.73, -3.41 50.74)"
    line_thr = "LINESTRING (-381578.819887 6574044.360475, -378513.534443 6574799.475787)"
    line_four = "LINESTRING (1 1, 3 1)"
    area_one = "POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0))"
    area_two = "POLYGON ((1 1, 3 1, 3 3, 1 3, 1 1))"

    # area_z = "POLYGON ((1 1 0, 3 1 0, 3 3 1, 1 3 1, 1 1 0))"

    # Linestring length (PLANAR-DEGREES)
    result = query_string("test.db", "SELECT ST_Length(ST_LineFromText('%s', 4326));" % line_one)
    # fix_print_with_import
    print("LINESTRING LENGTH (PLANAR-DEGREES):\t", result[0][0])



    # Linestring length (PLANAR-METERS)
    result = query_string("test.db", "SELECT ST_Length(ST_Transform(ST_LineFromText('%s', 4326), 3857));" % line_one)
    result = query_string("test.db", "SELECT ST_Length(ST_Transform(ST_LineFromText('%s', 4326), 3857));" % line_one)
    # fix_print_with_import
    print("LINESTRING LENGTH (PLANAR-METERS):\t", result[0][0])

    # Linestring length (Ellipsoid-METERS) starting with 3857
    result = query_string("test.db", "SELECT ST_Length(ST_LineFromText('%s', 4326), 1);" % line_one)
    # fix_print_with_import
    print("LINESTRING LENGTH (ELLIPSOID-METERS):\t", result[0][0])

    # Linestring length (Ellipsoid-METERS) starting with 3857
    result = query_string("test.db", "SELECT ST_Length(ST_Transform(ST_LineFromText('%s', 3857), 4326), 1);" % line_thr)
    # fix_print_with_import
    print("LINESTRING LENGTH (ELLIPSOID-METERS):\t", result[0][0])

    # Polygon area (PLANAR-DEGREES)
    result = query_string("test.db", "SELECT ST_Area(ST_PolygonFromText('%s', 4326));" % area_one)
    # fix_print_with_import
    print("POLYGON AREA (PLANAR-DEGREES):\t\t", result[0][0])

    # Polygon area (PLANAR-METERS)
    result = query_string("test.db", "SELECT ST_Area(ST_Transform(ST_PolygonFromText('%s', 4326), 3857));" % area_one)
    # fix_print_with_import
    print("POLYGON AREA (PLANAR-METERS):\t\t", result[0][0])

    # Linestring intersection
    result = query_string("test.db", "SELECT AsText(ST_Intersection(ST_LineFromText('%s', 4326), ST_LineFromText('%s', 4326)));" % (line_one, line_two))
    # fix_print_with_import
    print("LINE/LINE INTERSECTION:\t\t\t", result[0][0])

    # Area and linestring intersection
    result = query_string("test.db", "SELECT AsText(ST_Intersection(ST_PolygonFromText('%s', 4326), ST_LineFromText('%s', 4326)));" % (area_one, line_four))
    # fix_print_with_import
    print("AREA/LINE INTERSECTION:\t\t\t", result[0][0])

    # Area and area intersection
    result = query_string("test.db", "SELECT AsText(ST_Intersection(ST_PolygonFromText('%s', 4326), ST_PolygonFromText('%s', 4326)));" % (area_one, area_two))
    # fix_print_with_import
    print("AREA/AREA INTERSECTION:\t\t\t", result[0][0])
    #
    # # Area/Line Intersection length ellipsoidal
    # #result = query_string("test.db", "SELECT ST_Length(ST_Intersection(ST_PolygonFromText('%s', 4326), ST_LineFromText('%s', 4326)), 1);" % (area_one, line_four))
    # result = query_string("test.db", "SELECT ST_Length(ST_Intersection(ST_PolygonFromText('%s', 4326), ST_LineFromText('%s', 4326)));" % (area_one, line_four))
    # print "AREA/LINE INTERSECTION LENGTH:\t\t", result[0][0]
    #
    # # Area and area intersection area
    # result = query_string("test.db", "SELECT ST_Area(ST_Intersection(ST_PolygonFromText('%s', 4326), ST_PolygonFromText('%s', 4326)));" % (area_one, area_two))
    # print "AREA/AREA INTERSECTION AREA:\t\t", result[0][0]
    #
    # # Second example for area and area intersection area
    # result = query_string("test.db", "\
    # SELECT ST_Area(\
    #     ST_Intersection(\
    #         ST_GeomFromText('\
    #             POLYGON((-380582.074581 6573672.939408, \
    #                 -380590.196346 6573733.852645, \
    #                 -380578.326074 6573738.850654, \
    #                 -380579.887952 6573745.410541, \
    #                 -380502.418809 6573732.603143, \
    #                 -380476.804012 6573761.341696, \
    #                 -380462.122359 6573748.221922, \
    #                 -380455.250097 6573750.408551, \
    #                 -380453.063468 6573762.278823, \
    #                 -380429.947675 6573741.037283, \
    #                 -380431.821928 6573738.225903, \
    #                 -380404.332878 6573716.984364, \
    #                 -380408.081385 6573712.923481, \
    #                 -380389.33885 6573696.367576, \
    #                 -380382.466587 6573703.552214, \
    #                 -380369.971564 6573692.306693, \
    #                 -380325.614232 6573744.78579, \
    #                 -380299.999435 6573723.856627, \
    #                 -380300.936562 6573700.428458, \
    #                 -380364.973555 6573642.326601, \
    #                 -380410.580389 6573642.951352, \
    #                 -380515.850959 6573680.124046, \
    #                 -380582.074581 6573672.939408\
    #                 ))', 3857), \
    #         ST_PolygonFromText('\
    #             POLYGON((\
    #                 -880032.385105 6074453.691288, \
    #                 119967.614895 6074453.691288, \
    #                 119967.614895 7074453.691288, \
    #                 -880032.385105 7074453.691288, \
    #                 -880032.385105 6074453.691288))', 3857)\
    #                 ));")
    # print "AREA/AREA INTERSECTION AREA:\t\t", result[0][0]

    # import sys
    # for i in sys.path:
    #     print i