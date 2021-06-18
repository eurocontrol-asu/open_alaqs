from collections import OrderedDict

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.tools import SQLInterface
from open_alaqs.alaqs_core.tools import conversion
from open_alaqs.alaqs_core.tools.PythonClasses import SizeLimitedDict

logger = get_logger(__name__)


class Grid3D(object):
    """
    Class that contains the grid definition (number of cells in x,y,z
    dimensions, the resolution, and the reference (middle) x, y coordinates)
    and provides helper methods to work with the grid
    """

    def __init__(self, db_path="", grid_config=None, deserialize=True):
        if grid_config is None:
            grid_config = {}

        self._db_path = db_path
        self._table_name_definition = "grid_3d_definition"
        self._table_name_cell_coordinates = "grid_3d_cell_coordinates"

        # Definition of the grid
        # number of cells in x,y,z dimensions
        self._x_cells = grid_config.get("x_cells", 1)
        self._y_cells = grid_config.get("y_cells", 1)
        self._z_cells = grid_config.get("z_cells", 1)

        # resolution of each cells in x,y,z dimensions
        self._x_resolution = grid_config.get("x_resolution", 1)
        self._y_resolution = grid_config.get("y_resolution", 1)
        self._z_resolution = grid_config.get("z_resolution", 1)

        # center of the grid
        self._reference_latitude = conversion.convertToFloat(
            grid_config.get("reference_latitude", 0.))
        self._reference_longitude = conversion.convertToFloat(
            grid_config.get("reference_longitude", 0.))
        self._reference_altitude = conversion.convertToFloat(
            grid_config.get("reference_altitude", 0.))

        if self._db_path and deserialize:
            self.deserialize()

        logger.info("3D Grid Definition:")
        logger.info("\t Number of cells in x-direction: %i" % self._x_cells)
        logger.info("\t Number of cells in y-direction: %i" % self._y_cells)
        logger.info("\t Number of cells in z-direction: %i" % self._z_cells)
        logger.info("\t Resolution in x-direction: %i" % self._x_resolution)
        logger.info("\t Resolution in y-direction: %i" % self._y_resolution)
        logger.info("\t Resolution in z-direction: %i" % self._x_resolution)
        logger.info("\t Reference latitude (center of grid): %.5f" %
                    self._reference_latitude)
        logger.info("\t Reference longitude (center of grid): %.5f" %
                    self._reference_longitude)
        logger.info("\t Reference altitude (center of grid): %.5f" %
                    self._reference_altitude)

        # calculate the grid origin from reference coordinates, which is the
        # bottom left
        self._grid_origin_x = 0.
        self._grid_origin_y = 0.
        self._grid_origin_z = 0.
        self.resetGridOriginXYFromReferencePoint()

        self._elements = OrderedDict()

        # Restrict this list to a certain length, can give memory buffer
        # overflow otherwise
        self._hash_coordinates_map = SizeLimitedDict(size=1000)

    def addElements(self, elements):
        for element in elements:
            if element.getName() in self._elements:
                self._elements[element.getName()].append(element)
            else:
                self._elements[element.getName()] = [element]

    def hasElement(self, id):
        if id in self._elements:
            return True
        else:
            return False

    def getElements(self, id=""):
        if not id:
            return self._elements
        else:
            if id in self._elements:
                return self._elements
            else:
                return []

    def getResolution(self):
        return (self._x_resolution, self._y_resolution, self._z_resolution)

    def getResolutionX(self):
        return self._x_resolution

    def getResolutionY(self):
        return self._y_resolution

    def getResolutionZ(self):
        return self._z_resolution

    def getAirportAltitude(self):
        return self._reference_altitude

    def getSortedElements(self):
        return OrderedDict(
            sorted(list(self._elements.items()), key=lambda t: t[0]))

    def serializeConfiguration(self):
        try:
            # Create a new table to hold the grid definition needed to
            # deserialize the Grid3D Object
            result = self.insert_3d_grid_definition_table(
                self._db_path, self._table_name_definition)
            if result is not True:
                raise ValueError(result)
        except Exception as e:
            logger.error(
                "Failed to serialize the 3D grid configuration: %s" % e)
            return False

    def serialize(self):
        try:
            self.serializeConfiguration()

            # Create a new 3D table to hold a 3D grid
            result = self.make_3d_grid_coordinates_table(
                self._db_path, self._table_name_cell_coordinates)
            if result is not True:
                raise ValueError(result)

            # insert all cells with hashes and coordinates
            result = self.insert_rows(self._db_path,
                                      self._table_name_cell_coordinates,
                                      self.get_3d_grid_cells())
            if result is not True:
                raise ValueError(result)

            return True
        except Exception as e:
            logger.error("Failed to serialize the 3D grid: %s" % e)
            return False

    def deserialize(self):
        sql_text = "SELECT table_name_cell_coordinates, x_cells, y_cells, " \
                   "z_cells, x_resolution, y_resolution, z_resolution, " \
                   "reference_latitude, reference_longitude FROM %s;" % (
                       self._table_name_definition)
        result = SQLInterface.query_text(self._db_path, sql_text)
        # result contains: [('grid_3d_cell_coordinates', 50, 50, 10, 250, 250,
        # 100, 49.916667, -6.316667)]

        if isinstance(result, str):
            raise Exception(result)
        elif not result:
            logger.error(
                "Deserialization failed. No data returned from database "
                "'%s' with table '%s'" % (
                self._db_path, self._table_name_definition))
        else:
            # if multiple entries found, take only the first
            table_id = 0
            self._table_name_cell_coordinates = result[table_id][0]
            self._x_cells = result[table_id][1]
            self._y_cells = result[table_id][2]
            self._z_cells = result[table_id][3]

            self._x_resolution = result[table_id][4]
            self._y_resolution = result[table_id][5]
            self._z_resolution = result[table_id][6]

            self._reference_latitude = result[table_id][7]
            self._reference_longitude = result[table_id][8]
            logger.info("Deserialized Grid3D definition from db '%s' " % (
                self._db_path))

    def resetGridOriginXYFromReferencePoint(self):
        """
        This method sets the origin of the grid to the bottom-left corner.
        "Reference" coordinates need to be related to the center of the grid.
        """
        try:
            reference_point_wkt = "POINT (%s %s)" % (
                self._reference_longitude, self._reference_latitude)
            # logger.debug("Grid reference point: %s" % reference_point_wkt)
            # reference_point_df = gpd.GeoDataFrame(index=range(0, 1), columns=["geometry"], crs={'init': 'epsg:4326'})
            # reference_point_df.loc[0, "geometry"] = Point(self._reference_longitude, self._reference_latitude)

            # Convert the ARP into EPSG 3857
            # apt_ref_point_crs3857 = reference_point_df.to_crs({'init': 'epsg:3857'}).geometry.iloc[0]

            sql_text = "SELECT X(ST_Transform(ST_PointFromText('%s', 4326), 3857)), Y(ST_Transform(ST_PointFromText('%s', 4326), 3857));" % \
                       (reference_point_wkt, reference_point_wkt)
            result = SQLInterface.query_text(self._db_path, sql_text)
            # #Grid reference point: POINT (-6.316667 49.916667) > [(-703168.1539506749, 6431856.52141244)]
            # result = [(apt_ref_point_crs3857.x, apt_ref_point_crs3857.y)]
            if result is None:
                raise Exception(
                    "Could not reset reference point as coordinates could not be transformed. The query was\n'%s'" % (
                        sql_text))

            # reference_x = apt_ref_point_crs3857.x
            reference_x = conversion.convertToFloat(result[0][0])
            # reference_y = apt_ref_point_crs3857.y
            reference_y = conversion.convertToFloat(result[0][1])

            # Calculate the coordinates of the bottom left of the grid
            self._grid_origin_x = float(reference_x) - (
                    float(self._x_cells) / 2.) * float(self._x_resolution)
            self._grid_origin_y = float(reference_y) - (
                    float(self._y_cells) / 2.) * float(self._y_resolution)
            # print "Grid origin: x=%.0f, y=%.0f" % (self._grid_origin_x, self._grid_origin_y)

            return True
        except Exception as e:
            logger.error(
                "Could not reset 3D grid origin from reference point: %s" % e)
            return False

    def polygonise_2Dcells(self, df_row):
        return Polygon([(df_row.xmin, df_row.ymin), (df_row.xmax, df_row.ymin),
                        (df_row.xmax, df_row.ymax), (df_row.xmin, df_row.ymax)])

    def get_df_from_2d_grid_cells(self):
        grid_cells_df = pd.DataFrame(list(self.get_3d_grid_cells()),
                                     columns=['hash', "xmin", "xmax", "ymin",
                                              "ymax", "zmin", "zmax"])
        grid_cells_2D = grid_cells_df[grid_cells_df.zmin == 0].reset_index(
            drop=True)
        polys = grid_cells_2D.apply(self.polygonise_2Dcells, axis=1)
        gdf = gpd.GeoDataFrame(grid_cells_2D, columns=["hash", "geometry"])
        gdf.loc[:, "geometry"] = polys
        return gdf

    def get_df_from_2d_grid_cells_with_z(self, zmn):
        grid_cells_df = pd.DataFrame(list(self.get_3d_grid_cells()),
                                     columns=['hash', "xmin", "xmax", "ymin",
                                              "ymax", "zmin", "zmax"])
        grid_cells_2D = grid_cells_df[grid_cells_df.zmin == zmn].reset_index(
            drop=True)
        polys = grid_cells_2D.apply(self.polygonise_2Dcells, axis=1)
        gdf = gpd.GeoDataFrame(grid_cells_2D, columns=["hash", "geometry"])
        gdf.loc[:, "geometry"] = polys
        return gdf

    def get_df_from_3d_grid_cells(self):
        grid_cells_df = pd.DataFrame(list(self.get_3d_grid_cells()),
                                     columns=['hash', "xmin", "xmax", "ymin",
                                              "ymax", "zmin", "zmax"])
        polys = grid_cells_df.apply(self.polygonise_2Dcells, axis=1)
        gdf = gpd.GeoDataFrame(grid_cells_df,
                               columns=["hash", "geometry", "zmin", "zmax"])
        gdf.loc[:, "geometry"] = polys
        return gdf

    def get_3d_grid_cells(self):
        """
        This function builds a table that contains the locations of every cell that make up the user defined 3D grid. The
        result is a list of cells, each with a unique ID and the coordinates of the minimum and maximum x, y, and z
        positions defined in meters according to the EPSG 3857 projection.
        """
        # Calculate the planar and ellipsoidal coordinates of every cell
        cell_coordinates = []
        for x_idx in range(self._x_cells):
            for y_idx in range(self._y_cells):
                for z_idx in range(self._z_cells):
                    cell = self.convertXYZIndicesToGridCellMinMax(x_idx, y_idx,
                                                                  z_idx)
                    cell_coordinates.append([
                        self.convertXYZIndicesToCellHash(
                            x_idx, y_idx, z_idx),
                        cell["x_min"], cell["x_max"],
                        cell["y_min"], cell["y_max"],
                        cell["z_min"], cell["z_max"]])
        return cell_coordinates

    def insert_rows(self, database_path, table_name, row_list):
        """
        This function inserts cell hashes into a 3D grid table.
        :param database_path: the path of the database to be written to
        :param table_name: the name of the 3D table to put data into
        :param cell_coordinates: the list of hashes to be inserted
        :return: bool of success
        :raise ValueError: if the database returns an error
        """
        try:
            values_str = ""
            if len(row_list) and len(row_list[0]):
                values_str = "?" + ", ?" * (len(row_list[0]) - 1)
                sql_text = "INSERT INTO %s VALUES (%s);" % (
                    table_name, values_str)
                result = SQLInterface.query_insert_many(database_path, sql_text,
                                                        row_list)
                if isinstance(result, str):
                    logger.error("Row was not inserted: %s" % result)
                    raise ValueError(result)
                elif result is False:
                    logger.error(
                        "Row was not inserted: function returned False")
                    return False

            # logger.debug("Row was inserted in table '%s'"%(table_name))
            return True
        except Exception as e:
            return e

    def insert_3d_grid_definition_table(self, database_path, table_name):
        """
        Create a new table to hold the definition of the Grid3D Object

        :param database_path: the path to the database being written to
        :param table_name: the name of the table to be created as a string
        :return: bool
        :raise ValueError: if the query generates a string response (an error)
        """
        try:
            # Create the table and drop existing tables
            sql_query = "DROP TABLE IF EXISTS \"%s\";" % (table_name)
            SQLInterface.query_text(database_path, sql_query)

            sql_query = "CREATE TABLE %s \
                (\"table_name_cell_coordinates\" VARCHAR,\
                \"x_cells\" DECIMAL,\
                \"y_cells\" DECIMAL,\
                \"z_cells\" DECIMAL,\
                \"x_resolution\" DECIMAL,\
                \"y_resolution\" DECIMAL,\
                \"z_resolution\" DECIMAL,\
                \"reference_latitude\" DECIMAL,\
                \"reference_longitude\" DECIMAL\
                );" % (table_name)
            result = SQLInterface.query_text(database_path, sql_query)

            if isinstance(result, str):
                logger.error(
                    "Table for grid definition not created: %s" % result)
                raise ValueError(result)
            elif result is False:
                logger.error(
                    "Table for grid definition not created: query returned False")
                return False
            else:
                logger.debug("Table for grid definition created")

            # Fill the table
            sql_query = "INSERT INTO %s VALUES (?,?,?,?,?,?,?,?,?);" % (
                table_name)
            values = [self._table_name_cell_coordinates, self._x_cells,
                      self._y_cells, self._z_cells, self._x_resolution,
                      self._y_resolution, self._z_resolution,
                      self._reference_latitude, self._reference_longitude]
            result = SQLInterface.query_insert_many(database_path, sql_query,
                                                    [values])

            if isinstance(result, str):
                logger.error("Grid definition not added to table '%s': %s" % (
                    table_name, result))
                raise ValueError(result)
            elif result is False:
                logger.error(
                    "Failed to add values for grid definition to table '%s'." % (
                        table_name))
                return False
            else:
                # logger.debug("Successfully added values for grid definition to table '%s'." % (table_name))
                return True
        except Exception as e:
            logger.error("Exception: " % e)

    @staticmethod
    def make_3d_grid_coordinates_table(database_path, table_name):
        """
        Create a new 3D table to hold a 3D grid
        :param database_path: the path to the database being written to
        :param table_name: the name of the table to be created as a string
        :return: bool
        :raise ValueError: if the query generates a string response (an error)
        """
        try:
            sql_query = "DROP TABLE IF EXISTS \"%s\";" % table_name
            SQLInterface.query_text(database_path, sql_query)

            sql_query = "CREATE TABLE %s (\"cell_hash\" VARCHAR(15),\"x_min\" DECIMAL,\"x_max\" DECIMAL, \"y_min\" DECIMAL," \
                        "\"y_max\" DECIMAL, \"z_min\" DECIMAL, \"z_max\" DECIMAL);" % table_name
            result = SQLInterface.query_text(database_path, sql_query)
            if isinstance(result, str):
                logger.error(
                    "Table for 3D cell hashes not created: %s" % result)
                raise ValueError(result)
            elif result is False:
                logger.error(
                    "Table for 3D cell hashes not created: query returned False")
                return False
            else:
                # logger.debug("Table for 3D cell hashes created")
                return True
        except Exception:
            pass

    def convertXYZIndicesToGridCellMinMax(self, x_idx, y_idx, z_idx):
        val = {
            "x_min": self._grid_origin_x + (x_idx * self._x_resolution),
            "y_min": self._grid_origin_y + (y_idx * self._y_resolution),
            "z_min": self._grid_origin_z + z_idx * self._z_resolution,
        }
        val.update({
            "x_max": val["x_min"] + self._x_resolution,
            "y_max": val["y_min"] + self._y_resolution,
            "z_max": val["z_min"] + self._z_resolution,
        })
        return val

    def convertCellHashListToCenterGridCellCoordinates(self, cellhash_list):
        val = {}

        for hash in cellhash_list:
            if not hash in val:
                if not (hash in self._hash_coordinates_map):
                    (x_idx, y_idx, z_idx) = self.convertCellHashToXYZIndices(
                        hash)
                    cell = self.convertXYZIndicesToGridCellMinMax(x_idx, y_idx,
                                                                  z_idx)

                    if not (
                            "x_min" in cell and "x_max" in cell and "y_min" in cell and "y_max" in cell and "z_min" in cell and "z_max" in cell):
                        logger.error(
                            "Could not convert cell hash '%s' because either x_min, x_max, y_min, y_max, z_min, or z_max was not found." % (
                                str(hash)))
                        logger.error("\t Output of '%s' was '%s'." % (
                            "self.convertXYZIndicesToGridCellMinMax(x_idx,y_idx,z_idx)",
                            str(cell)))
                    else:
                        self._hash_coordinates_map[hash] = (
                            (cell["x_min"] + cell["x_max"]) / 2.,
                            (cell["y_min"] + cell["y_max"]) / 2.,
                            (cell["z_min"] + cell["z_max"]) / 2.)

                val[hash] = self._hash_coordinates_map[hash]
        return val

    def convertIndexToCellHash(self, idx):
        return "%05.0f" % idx

    def convertXYZIndicesToCellHash(self, x_idx, y_idx, z_idx):
        """
        This function generates a unique cell hash based on an XYZ position
         within a grid. This reduces the complexity of cell lookups to O
         from O^3

        :param x_idx: the position of the cell on the x-axis (furthest west is 0)
        :param y_idx: the position of the cell on the y-axis (furthest south is 0)
        :param z_idx: the vertical interval
        :return cell_hash: the unique hash of the cell
        :rtype: int
        """
        return "%s%s%s" % (self.convertIndexToCellHash(x_idx),
                           self.convertIndexToCellHash(y_idx),
                           self.convertIndexToCellHash(z_idx))

    def convertCellHashToXYZIndices(self, cell_hash):
        """
        This function generates a unique cell hash based on an XYZ position
         within a grid.
        :param cell_hash: the unique hash of the cell
        :rtype: tuple with (x_idx, y_idx, z_idx)
        """
        x_idx, y_idx, z_idx = 0, 0, 0
        if len(cell_hash) == 15:
            x_idx = int(conversion.convertToFloat(cell_hash[0:5]))
            y_idx = int(conversion.convertToFloat(cell_hash[5:10]))
            z_idx = int(conversion.convertToFloat(cell_hash[10:15]))
        else:
            raise Exception("Cell hash '%s' has wrong format" % cell_hash)
        return x_idx, y_idx, z_idx

    def stripZCoordinateFromCellHash(self, val):
        if type(val) == type(""):
            return val[:-5]
        return ""

    def convertCoordinatesToXYZIndices(self, x, y, z):
        x_idx = int((x - self._grid_origin_x) / self._x_resolution)
        y_idx = int((y - self._grid_origin_y) / self._y_resolution)
        z_idx = int((z - self._grid_origin_z) / self._z_resolution)

        # linestr = "LINESTRING Z (%s %s %s,%s %s %s)"%(x, y, z, self._grid_origin_x, self._grid_origin_y, self._grid_origin_z)
        if x_idx < 0:
            # logger.error("'%s'=%i out of defined grid ... You should enlarge the grid! Coordinate is %s= %f,%s= %f,%s= %f" % ("x_idx", x_idx, "x", x, "y", y, "z", z))
            x_idx = 0
        if y_idx < 0:
            # logger.error("'%s'=%i out of defined grid ...You should enlarge the grid! Coordinate is %s= %f" % ("y_idx", y_idx, "y", y))
            y_idx = 0
        if z_idx < 0:
            # logger.error("'%s'=%i out of defined grid ... You should enlarge the grid! Coordinate is %s= %f" % ("z_idx", z_idx, "z", z))
            z_idx = 0
        return (x_idx, y_idx, z_idx)

    def matchBoundingBoxToXYZindices(self, bbox, z_as_list=False):
        keys_ = ["x_min", "y_min", "z_min", "x_max", "y_max", "z_max"]
        for e in keys_:
            if not e in bbox:
                logger.error(
                    "Expected bounding box as dictionary with keys '%s' but got '%s'" % (
                        ",".join(keys_), str(bbox)))
                logger.error("\t Return empty matches")
                return []

        x_idx_low, y_idx_low, z_idx_low = self.convertCoordinatesToXYZIndices(
            bbox["x_min"], bbox["y_min"], bbox["z_min"])
        x_idx_high, y_idx_high, z_idx_high = self.convertCoordinatesToXYZIndices(
            bbox["x_max"], bbox["y_max"], bbox["z_max"])

        matched_cells = []
        for x in range(x_idx_low, x_idx_high + 1):
            for y in range(y_idx_low, y_idx_high + 1):
                if z_as_list:
                    z_list = []
                    for z in range(z_idx_low, z_idx_high + 1):
                        if not x > self._x_cells or y > self._y_cells or z > self._z_cells:
                            z_list.append(z)
                    matched_cells.append((x, y, z_list))
                else:
                    for z in range(z_idx_low, z_idx_high + 1):
                        if not x > self._x_cells or y > self._y_cells or z > self._z_cells:
                            matched_cells.append((x, y, z))

        return matched_cells

    def matchBoundingBoxToCellHashList(self, bbox, max_height=None,
                                       z_as_list=False):
        matched_cells = []
        for (x, y, z) in self.matchBoundingBoxToXYZindices(bbox, z_as_list):
            if not z_as_list:
                matched_cells.append(
                    self.convertXYZIndicesToCellHash(x, y, z))
            else:
                z_list = []
                for z_idx in z:
                    z_list.append(
                        self.convertXYZIndicesToCellHash(x, y, z_idx))

                if len(z_list) > 0:
                    matched_cells.append(z_list)

        return matched_cells

    def getTotalAreaFromGeometryText(self, geometry_text):
        val = 0.
        if "POINT" in geometry_text:
            val = 0.
        else:
            element_geometry_ = "ST_GeomFromText('%s', 3857)" % (
                str(geometry_text))
            match_expression = "ST_Area" if not "LINESTRING" in element_geometry_ else "ST_Length"

            sql_text = "SELECT %s(%s);" % (match_expression, element_geometry_)
            result = SQLInterface.query_text(self._db_path, sql_text)

            if result and type(result[0]) == type(()) and not result[0][
                                                                  0] is None:
                val = conversion.convertToFloat(result[0][0])
        return val

    def getMatchedAreaWithCells(self, geometry_text, cell_list):
        values = {}

        element_geometry_ = "ST_GeomFromText('%s', 3857)" % (str(geometry_text))
        match_expression = "ST_AREA" if not "LINESTRING" in element_geometry_ else "ST_LENGTH"

        for i_, cell_hash in enumerate(cell_list):
            values[cell_hash] = 0.

            sql_text = "SELECT %s" % (match_expression)
            (x_idx, y_idx, z_idx) = self.convertCellHashToXYZIndices(
                cell_hash)
            cell_ = self.convertXYZIndicesToGridCellMinMax(x_idx, y_idx, z_idx)
            cell_geometry_ = "ST_PolygonFromText('POLYGON((%f %f, %f %f, %f %f, %f %f, %f %f))', 3857)" % (
                float(cell_["x_min"]), float(cell_["y_min"]),
                float(cell_["x_max"]), float(cell_["y_min"]),
                float(cell_["x_max"]), float(cell_["y_max"]),
                float(cell_["x_min"]), float(cell_["y_max"]),
                float(cell_["x_min"]), float(cell_["y_min"])
            )

            sql_text += "(ST_Intersection(%s, %s))" % (
                element_geometry_, cell_geometry_)
            sql_text += ";"

            result = SQLInterface.query_text(self._db_path, sql_text)

            if result:
                if type(result[0]) == type(()):
                    values[cell_hash] = conversion.convertToFloat(result[0][0])
                else:
                    logger.error(
                        "Query '%s' returned wrong result! Tuple (float,) expected for cell hash but got '%s' for cell hash '%s'" % (
                            str(sql_text), str(result[0][i_]), str(cell_hash)))

                if values[cell_hash] is None:
                    # logger.debug("cell_hash='%s'" %(str(cell_hash)))
                    # logger.debug("result='%s'" %(str(result)))

                    logger.warning(
                        "Matching of geometry '%s' with grid cell '%s' returned 'None'." % (
                            geometry_text, cell_hash))
                    # Currently, spatialite function 'ST_Area' is used for geometry 'POLYGON' and 'ST_Length' for geometry 'LINESTRING'. If geometry is neither 'POLYGON' nor 'LINESTRING' you should update the method 'getMatchedAreaWithCells' in class 'Grid3D'."
                    values[cell_hash] = 0.
            # raise Exception("getMatchedAreaWithCells SQL Query: Results do not match in length (len(cell_list)=%i and len(result)=%i)" % (len(cell_list), len(result)))

        if isinstance(result, str):
            raise Exception(result)
        elif not result:
            logger.error(
                "Error while matching cell hash and geometry with text '%s" % (
                    self.geometry_text))
        else:
            logger.debug(result)

        return values


class Grid3DElement(object):
    """
    Class that represents a simple element of the grid
    """

    def __init__(self, name):
        self._name = name

        self._geometry_text = ""
        self._bbox = {
            'x_min': 0.,
            'x_max': 0.,
            'y_min': 0.,
            'y_max': 0.
        }
        self._bboxCellHashList = []

    def getCellHashList(self):
        return self._bboxCellHashList

    def setCellHashList(self, hashlist):
        self._bboxCellHashList = hashlist

    def removeFromCellHashList(self, hashlist):
        for hash in hashlist:
            if hash in self._bboxCellHashList:
                self._bboxCellHashList.pop(self._bboxCellHashList.index(hash))

    def getName(self):
        return self._name

    def setGeometryText(self, g):
        self._geometry_text = g

    def getGeometryText(self):
        return self._geometry_text

    def setBoundingBox(self, wkt, is2D=True):
        """
        Set minima and maxima in x and y directions for a generic object
        (POINT, LINESTRING, or POLYGON)

        :param wkt: String in well-known-text (WKN) notation
        """

        wkt = wkt.replace("(", "").replace(")", "")
        wkt = wkt.replace("POINT", "").replace("LINESTRING", "").replace(
            "POLYGON", "").strip()
        data_points = wkt.split(",")

        x_min = 99999999.
        x_max = -99999999.
        y_min = 99999999.
        y_max = -99999999.

        for data_point in data_points:
            xy = data_point.strip().split(" ")
            x = conversion.convertToFloat(xy[0])
            y = conversion.convertToFloat(xy[1])
            # original, FIXME?
            # x = conversion.convertToFloat(xy[1])
            # y = conversion.convertToFloat(xy[0])
            if x < x_min:
                x_min = x
            if y < y_min:
                y_min = y
            if x > x_max:
                x_max = x
            if y > y_max:
                y_max = y

        bbox = {
            'x_min': x_min,
            'x_max': x_max,
            'y_min': y_min,
            'y_max': y_max
        }

        # ToDo: Ignoring height for all sources
        if is2D:
            bbox.update({
                'z_min': 0,
                'z_max': 1
            })

        self._bbox = bbox

    def getBoundingBox(self):
        return self._bbox

    def __str__(self):
        output = ""
        output += "Element '%s'" % (self.getName())
        output += "\n"
        if self.getGeometryText():
            output += "\t Geometry text:"
            output += "\n"
            output += self.getGeometryText()
            output += "\n"
        if self.getBoundingBox():
            output += "\t Bounding box:"
            output += "\n"
            output += "\t\t xmin: %.5f" % (self.getBoundingBox()["x_min"])
            output += "\n"
            output += "\t\t xmax: %.5f" % (self.getBoundingBox()["x_max"])
            output += "\n"
            output += "\t\t ymin: %.5f" % (self.getBoundingBox()["y_min"])
            output += "\n"
            output += "\t\t ymax: %.5f" % (self.getBoundingBox()["y_max"])
            output += "\n"
        if self.getCellHashList():
            output += "\t Matched grid cells in bounding box:"
            output += "\n"
            for cell in self.getCellHashList():
                output += "\t\t %s" % (str(cell))
                output += "\n"
        return output
