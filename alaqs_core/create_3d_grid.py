"""
This class is used to create a 3D grid of emissions ...
"""
from __future__ import absolute_import
from builtins import str
from builtins import range
from builtins import object
import os
import logging

from alaqs_core.tools import Grid3D

logger = logging.getLogger("__alaqs__.%s" % (__name__))

#import alaqs

from alaqs_core.tools.Grid3D import Grid3DElement

from .tools import SQLInterface
# Create a logger for this module. Can be commented out for distribution

class Grid3DEntries(object):
    def __init__(self, db_path):
        self._db_path = db_path
        self._table_name_source_grid_cell_matching = "grid_3d_source_grid_cell_matching"

        #ToDo: use class of Grid3DElements (with UserRecord)
        self._entries = {}

    def serialize(self):
        pass

    def deserialize(self):
        headers_ = ["source_id", "cell_hash", "relative_area"]
        sql_text = "SELECT %s FROM %s;" % (",".join(headers_), self._table_name_source_grid_cell_matching)
        result = SQLInterface.query_text(self._db_path, sql_text)

        if isinstance(result, str):
            raise Exception(result)
        elif not result:
            logger.error("Deserialization failed. No data returned from database '%s' with table '%s'" % (self._db_path, self._table_name_source_grid_cell_matching))
        else:
            #if multiple entries found, take only the first
            if type(result) == type([]):
                for row in result:
                    if not len(row) == 3:
                        raise Exception("Deserialization failed. Data returned from database '%s' with table '%s' has %i columns instead of " % (self._db_path, self._table_name_source_grid_cell_matching, len(row), len(headers_)))

                    #self.addEntry("source_id",{"cell_hash":"relative_area"})
                    self.addEntry(row[0],{row[1]:row[2]})

    def flush(self):
        raise NotImplemented

    def getEntries(self):
        return self._entries

    def getUniqueCellHashes(self):
        val = []
        for source_id in self.getEntries():
            for cell_hash in list(self.getEntries()[source_id].keys()):
                if not cell_hash in val:
                    val.append(cell_hash)
        return val

    def addEntry(self, source_id, cell_hash_relative_area_dict):
        if not source_id in self._entries:
            self._entries[source_id] = cell_hash_relative_area_dict
        else:
            for cell_hash in list(cell_hash_relative_area_dict.keys()):
                if not cell_hash in self._entries[source_id]:
                    self._entries[source_id][cell_hash] = cell_hash_relative_area_dict[cell_hash]

    def resetEntries(self, entry):
        self._entries = {}

    def getAllElements(self, sourceList=[]):
        """
        :param grid_meta_data: a dictionary that contains the grid definition (number of cells in x,y,z dimensions, the resolution, and the reference (middle) x, y coordinates)
        """
        map_table_columns = {
            "shapes_parking":"parking_id",
            "shapes_tracks":"track_id",
            "shapes_taxiways":"taxiway_id",
            "shapes_point_sources":"source_id",
            "shapes_runways":"runway_id",
            "shapes_roadways":"roadway_id",
            "shapes_area_sources":"source_id",
            "shapes_buildings":"building_id",
            "shapes_gates":"gate_id"
        }
        if not sourceList:
            sourceList = list(map_table_columns.keys())

        elements = []
        try:
            point_features = []
            for index, table in enumerate(sourceList):
                if not table in map_table_columns:
                    logger.error("Did not find column identifier for table '%s'." % (table))
                    raise Exception("Did not find column identifier for table '%s'." % (table))
                else:
                    sql_text = "SELECT %s, AsText(geometry), AsText(Envelope(geometry)) FROM %s;" % (map_table_columns[table], table)
                    logger.debug(sql_text)
                    point_features_ = SQLInterface.query_text(self._db_path, sql_text)

                    if type(point_features_) == type([]):
                        #logger.debug(point_features_)
                        for feat_ in point_features_:
                            point_features.append(feat_)

            for point_feature in point_features:
                ele = Grid3DElement(point_feature[0])
                ele.setGeometryText(point_feature[1])
                ele.setBoundingBox(point_feature[2], is2D=True)
                elements.append(ele)
        except Exception as e:
            logger.error(e)
        return elements

    def get_source_grid_match_table(self):
        """
        Read all entries from table that holds the association of each cell (within the bounding box) of a source_id and the relative area within that cell
        :return: bool
        :raise ValueError: if the query generates a string response (an error)
        """
        sql_text = "SELECT source_id, cell_hash, relative_area FROM %s;" % (self._table_name_source_grid_cell_matching)
        result = SQLInterface.query_text(self._db_path, sql_text)

        if isinstance(result, str):
            raise Exception(result)
        elif not result:
            logger.error("Deserialization of grid entries failed. No data returned from database '%s' with table '%s'" % (self._db_path, self._table_name_source_grid_cell_matching))
        else:
            #if multiple entries found, take only the first
            table_id = 0
            self.resetEntries()

            if len(result[table_id]) == 3:
                source_ids_ = result[table_id][0]
                cell_hash_ = result[table_id][1]
                relative_area_ = result[table_id][2]

            for i in range(0, len(source_ids_)):
                self.addEntry({
                    "source_id": source_ids_[i],
                    "cell_hash": cell_hash_[i],
                    "relative_area": relative_area_[i],
                })

            logger.info("Deserialized %i entries from table '%s' from db '%s' " % (len(self.getEntries()), self._table_name_source_grid_cell_matching, self._db_path))

    def insert_source_grid_match_table(self, entries):
        """
        Create a new table that holds the association of each cell (within the bounding box) of a source_id and the relative area within that cell
        :return: bool
        :raise ValueError: if the query generates a string response (an error)
        """
        try:
            #Create the table and drop existing tables
            sql_query = "DROP TABLE IF EXISTS \"%s\";" % (self._table_name_source_grid_cell_matching)
            SQLInterface.query_text(self._db_path, sql_query)

            sql_query = "CREATE TABLE %s (\
                \"source_id\" VARCHAR,\
                \"cell_hash\" VARCHAR(15),\
                \"relative_area\" DECIMAL\
                );"  % (self._table_name_source_grid_cell_matching)
            result = SQLInterface.query_text(self._db_path, sql_query)

            if isinstance(result, str):
                logger.error("Table for source-cell matching not created: %s" % result)
                raise ValueError(result)
            elif result is False:
                logger.error("Table for source-cell matching not created: query returned False")
                return False
            else:
                logger.debug("Table for source-cell matching created")

            #Fill the table
            if len(entries):
                for index,entry in enumerate(entries):
                    if not len(entry) == 3:
                        logger.error("Entry for table with source-cell matching has wrong dimension: List has length %i instead of %i" % (len(entry), 3))
                        logger.error("\t Entry is '%s'" % (str(entry)))
                        raise ValueError("Wrong dimension")
                sql_query = "INSERT INTO %s VALUES (?,?,?);" % (self._table_name_source_grid_cell_matching)
                result = SQLInterface.query_insert_many(self._db_path, sql_query, entries)

                if isinstance(result, str):
                    logger.error("Source-cell matching not added to table '%s': %s" % (self._table_name_source_grid_cell_matching, result))
                    raise ValueError(result)
                elif result is False:
                    logger.error("Failed to add values for source-cell matching to table '%s'." % (self._table_name_source_grid_cell_matching))
                    return False
                else:
                    logger.debug("Successfully added values for Source-cell matching to table '%s'." % (self._table_name_source_grid_cell_matching))
                    return True
        except Exception as e:
            logger.error("Exception: %s" % (str(e)))
            return False

#def create_3d_grid_data(database_path, table_name, grid_meta_data):
#    """
#    This function generates a blank 3D data table that can be used to create a new 3D data set. This table is used in
#    conjunction with the 3D cells table to create 3D grids.
#
#    :param database_path: a path to the database being written to
#    :param table_name: the name of the table to be created
#    :param grid_meta_data: a dictionary that contains the grid definition
#    """
#    try:
#        x = grid_meta_data['x_cells']
#        y = grid_meta_data['y_cells']
#        z = grid_meta_data['z_cells']
#
#        # Make a unique hash per cell and calculate coordinates
#        hash_list = []
#        for x_idx in range(x):
#            for y_idx in range(y):
#                for z_idx in range(z):
#                    cell_hash = make_3d_cell_hash(x_idx, y_idx, z_idx)
#                    co = random.random()
#                    hc = random.random()
#                    nox = random.random()
#                    sox = random.random()
#                    pm10 = random.random()
#                    p1 = random.random()
#                    p2 = random.random()
#                    cell_data = [cell_hash, co, hc, nox, sox, pm10, p1, p2]
#                    hash_list.append(cell_data)
#
#        # Create the 3D tables
#        result = make_3d_grid_data_table(database_path, table_name)
#        if result is not True:
#            raise ValueError(result)
#
#        # Insert cell hashes into new table
#        result = insert_rows(database_path, table_name, hash_list)
#        if result is not True:
#            raise ValueError(result)
#
#    except Exception, e:
#        logger.error("Failed to create a 3D grid definition: %s" % e)
#
#def dict_cell_data(cell_data):
#    """
#    Turns the values returned for a specific 3D cell into a dict
#    :param cell_data: the data returned from a database for a cell hash as a list
#    :return: a dict of this cell's data
#    """
#    try:
#        cell_dict = dict()
#        cell_dict["cell_hash"] = cell_data(0)
#        cell_dict["co"] = cell_data(1)
#        cell_dict["hc"] = cell_data(2)
#        cell_dict["nox"] = cell_data(3)
#        cell_dict["sox"] = cell_data(4)
#        cell_dict["pm10"] = cell_data(5)
#        cell_dict["p1"] = cell_data(6)
#        cell_dict["p2"] = cell_data(7)
#        return cell_dict
#    except:
#        return None


if __name__ == "__main__":
    # create a logger for this module
    logger.setLevel(logging.DEBUG)
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # create formatter
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    # add formatter to ch
    ch.setFormatter(formatter)
    # add ch to logger
    logger.addHandler(ch)

    # ======================================================
    # ==================    UNIT TESTS     =================
    # ======================================================

    # Note: you might get errors with SRID 3857 missing. If this is the case, use the following query:
    # INSERT INTO "spatial_ref_sys" VALUES ("3857", "epsg" , "3857", "WGS 84 / Pseudo-Mercator",
    # "+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext  +no_defs")
    #


    # ==========================================================
    # Testing the total emissions for a single runway
    # ==========================================================
    test_db = "C:/tmp/working.alaqs"

    grid_configuration = {
        'x_cells' : 10,
        'y_cells' : 10,
        'z_cells' : 1,
        'x_resolution': 100,
        'y_resolution': 100,
        'z_resolution' :100,
        'reference_latitude' : '50.734444', #airport_latitude
        'reference_longitude' :'-3.413889' #airport_longitude
    }

    #Create a new grid instance
    grid = Grid3D(test_db, grid_configuration)
    #grid = Grid3D(test_db)
    #Save the instance to the database
    grid.serialize()

    #get all sources, i.e. runways, roadways, areas etc. from the database
    #available_tables = ["shapes_area_sources","shapes_buildings","shapes_gates","shapes_parking", "shapes_roadways", "shapes_point_sources", "shapes_runways", "shapes_taxiways"]
    available_tables = ["shapes_point_sources"]
    available_tables = ["shapes_area_sources"]
    available_tables = []

    path_to_database = os.path.join("..", "example", "exeter_out.alaqs")
    grid_entries = Grid3DEntries(path_to_database)
    grid_entries.deserialize()

    #elements = grid_entries.getAllElements(available_tables)
    #for ele in elements:
    #    #match the sources to the grid
    #    ele.setCellHashList(grid.matchBoundingBoxToCellHashList(ele.getBoundingBox()))
    #    logger.debug(ele)

    hash_coordinates_map = grid.convertCellHashListToCenterGridCellCoordinates(grid_entries.getUniqueCellHashes())
    #test_result = create_3d_grid_data(test_db, "grid_3d_cell_data", grid_meta_data)