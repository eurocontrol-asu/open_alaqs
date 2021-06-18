import copy
import itertools
import math
import os
from collections import OrderedDict
from datetime import datetime, timedelta

import geopandas as gpd
import numpy as np
from PyQt5 import QtGui, QtWidgets
from dateutil import rrule

from open_alaqs.alaqs_core import alaqslogging
from open_alaqs.alaqs_core.interfaces.DispersionModule import DispersionModule
from open_alaqs.alaqs_core.tools import SQLInterface, Spatial, conversion

# logger = logging.getLogger(__name__)
logger = alaqslogging.logging.getLogger(__name__)
# To override the default severity of logging
logger.setLevel('DEBUG')
# Use FileHandler() to log to a file
file_handler = alaqslogging.logging.FileHandler(alaqslogging.LOG_FILE_PATH)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = alaqslogging.logging.Formatter(log_format)
file_handler.setFormatter(formatter)
# Don't forget to add the file handler
logger.addHandler(file_handler)


class AUSTAL2000DispersionModule(DispersionModule):
    """
    Module for the preparation of the input files needed for AUSTAL2000
    dispersion calculations.
    """

    @staticmethod
    def getModuleName():
        return "AUSTAL2000"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        DispersionModule.__init__(self, values_dict)

        self._name = values_dict.get("name", "")
        self._model = "AUSTAL2000"
        self._pollutant = values_dict.get("pollutant", "NOx")
        self._receptors = values_dict.get("receptors", gpd.GeoDataFrame())
        self._output_path = values_dict.get("output_path")

        # Create the output directory if it does not exist
        if self._output_path is not None:
            # self._def_output_path = copy.deepcopy(self._output_path)
            if not os.path.isdir(self._output_path):
                os.mkdir(self._output_path)

        self._sequ = values_dict.get("index sequence", "k+,j-,i+")
        self._grid = values_dict.get("grid", "")

        self._pollutants_list = values_dict.get("pollutants_list")
        if self._pollutant:
            self._pollutants_list = [self._pollutant]

        # "----------------- general parameters",
        # "ti\t'grid source'\t' title of the project",
        self._title = values_dict.get("add title", "no title")
        # "qs\t1\t' quality level",
        self._quality_level = values_dict.get("quality level", 1)
        # for non-standard calculations
        self._options = values_dict.get("options string", "SCINOTAT")

        # "----------------- meteorology",
        # ToDo: Modify AmbientCondition.py or derive z0, d0, and ha from main
        #  dialog (airport info)
        # "z\t0.2\t' roughness length (m)",
        self._roughness_level = float(values_dict.get(
            "roughness length (in m)", 0.2))
        # d0: default 6z0    # "d0\t1.2\t' displacement height (m)",
        self._displacement_height = float(values_dict.get(
            "displacement height (in m)", 6 * self._roughness_level))
        # 10 m + d0 (6z0)  # "ha\t11.2\t' anemometer height (m)",
        self._anemometer_height = float(values_dict.get(
            "anemometer height (in m)", 10.0 + 6 * self._roughness_level))

        self._reference_x = None
        self._reference_y = None
        self._reference_z = None
        # receptor points
        self.xp_, self.yp_, self.zp_ = [], [], []

        # "----------------- concentration grid -----------------"
        self._x_left_border_calc_grid = None  # "x0\t-200\t' left border (m)",
        self._y_left_border_calc_grid = None  # "y0\t-200\t' lower border (m)",

        # general parameters set from Widget
        widget_parameters = OrderedDict({
            ("enable", QtWidgets.QCheckBox,),
            ("add title", QtWidgets.QLineEdit,),
            ("roughness length (in m)", QtWidgets.QLineEdit,),
            ("anemometer height (in m)", QtWidgets.QLineEdit,),
            ("displacement height (in m)", QtWidgets.QLineEdit,),
            ("options string", QtWidgets.QLineEdit,),
            ("quality level", QtWidgets.QLineEdit,),
            ("index sequence", QtWidgets.QLineEdit,),
        })
        self.setConfigurationWidget(OrderedDict(
            sorted(list(widget_parameters.items()), key=lambda t: len(t[0]))))

        self.getConfigurationWidget().initValues({
            "roughness length (in m)": 0.2,
            "displacement height (in m)": 1.2,
            "anemometer height (in m)": 11.2,
            "add title": "",
            "quality level": 1,
            "index sequence": "k+,j-,i+",
            "enable": False,
            "options string": "NOSTANDARD;SCINOTAT;Kmax=1"
        })

        self._configuration_widget.getSettings()["enable"].setToolTip('Enable to create AUSTAL2000 input files')

        self._configuration_widget.getSettings()["index sequence"].setToolTip('index sequence in which the data values are listed (comma separated)')
        self._configuration_widget.getSettings()["index sequence"].setEnabled(False)

        self._configuration_widget.getSettings()["quality level"].setValidator(QtGui.QDoubleValidator())
        # ToDo: QL Range between -4 and 4
        self._configuration_widget.getSettings()["roughness length (in m)"].setValidator(QtGui.QDoubleValidator())
        self._configuration_widget.getSettings()["displacement height (in m)"].setValidator(QtGui.QDoubleValidator())
        self._configuration_widget.getSettings()["anemometer height (in m)"].setValidator(QtGui.QDoubleValidator())

        self._configuration_widget.getSettings()["quality level"].setToolTip('+1 doubles the number of simulation particles')
        self._configuration_widget.getSettings()["options string"].setToolTip('options must be defined successively and separated by a semicolon')

        # self._configuration_widget.getSettings()["quality level"].setValidator(QtGui.QRegExpValidator(QtCore.QRegExp(r'^[0-9]')))
        # self.setValidator(QtGui.QIntValidator()) # now edit will only accept integers
        # self._configuration_widget.getSettings()["title"].setStyleSheet("QWidget {background-color:rgba(255, 107, 107, 150);}")

    # ToDo: Define the get set functions for all parameters
    def getTitle(self):
        return self._title

    def setTitle(self, var):
        self._title = var

    # Quality Level
    def getQualityLevel(self):
        return self._quality_level

    def setQualityLevel(self, var):
        self._quality_level = var

    # Roughness Length
    def getRoughnessLength(self):
        return self._roughness_level

    def setRoughnessLength(self, var):
        self._roughness_level = var

    def getGrid(self):
        return self._grid

    def setGrid(self, var):
        self._grid = var

    def isEnabled(self):
        return self._enable

    def getModel(self):
        return self._model

    def setModel(self, val):
        self._model = val

    def getSequ(self) -> str:
        """
        Index sequence in which the data values are listed (comma separated)
        (from AUSTAL2000 grid source example)

        :return:
        """
        return self._sequ

    def getDistanceXY(self, x_1, y_1, x_2, y_2) -> float:
        """
        Get the distance between two coordinates.

        todo: Fix

        :param x_1:
        :param y_1:
        :param x_2:
        :param y_2:
        :return:
        """
        p1 = Spatial.getPoint("", x_1, y_1, 0.)
        p2 = Spatial.getPoint("", x_2, y_2, 0.)

        x_y_distance = Spatial.getDistanceOfLineStringXY(
            Spatial.getLine(p1, p2), epsg_id_source=3857, epsg_id_target=4326)
        if x_y_distance is None:
            x_y_distance = 0.
        # logger.debug("Distance xy: %f" % (x_y_distance))
        return math.sqrt(x_y_distance ** 2.)

    def setOutputPath(self, val):
        self._output_path = val

    def getOutputPath(self):
        return self._output_path

    def getSortedResults(self):
        return OrderedDict(
            sorted(list(self._results.items()), key=lambda t: t[0]))

    def getSortedSeries(self):
        return OrderedDict(
            sorted(list(self._series.items()), key=lambda t: t[0]))

    def getDataPoint(self, x_, y_, z_, isPolygon, grid_):
        data_point_ = {
            "coordinates":{
                "x":x_,
                "y":y_,
                "z":z_}
        }
        if isPolygon:
            data_point_.update({
                "coordinates":{
                    "x_min":x_-grid_.getResolutionX()/2.,
                    "x_max":x_+grid_.getResolutionX()/2.,
                    "y_min":y_-grid_.getResolutionY()/2.,
                    "y_max":y_+grid_.getResolutionY()/2.,
                    "z_min":z_-grid_.getResolutionZ()/2.,
                    "z_max":z_+grid_.getResolutionZ()/2.
            }})
        return data_point_

    def getBoundingBox(self, geometry_wkt):
        bbox = Spatial.getBoundingBox(geometry_wkt)
        return bbox

    def getCellBox(self, x_,y_,z_, grid_):
        cell_bbox = {
                    "x_min":x_-grid_.getResolutionX()/2.,
                    "x_max":x_+grid_.getResolutionX()/2.,
                    "y_min":y_-grid_.getResolutionY()/2.,
                    "y_max":y_+grid_.getResolutionY()/2.,
                    "z_min":z_-grid_.getResolutionZ()/2.,
                    "z_max":z_+grid_.getResolutionZ()/2.
        }
        return cell_bbox

    def getEfficiencyXY(self, emissions_geometry_wkt, cell_bbox, isPoint, isLine, isPolygon, isMultiPolygon):
        #efficiency = relative area of geometry in the cell box
        efficiency_ = 0.
        if isPoint or isPolygon or isMultiPolygon:
            efficiency_ = Spatial.getRelativeAreaInBoundingBox(emissions_geometry_wkt, cell_bbox)
        elif isLine:
            #get relative length (X,Y) in bounding box (assumes constant speed)
            efficiency_ = Spatial.getRelativeLengthXYInBoundingBox(emissions_geometry_wkt, cell_bbox)
        return efficiency_

    def getEfficiencyZ(self, geometry_wkt, z_min, z_max, cell_box, isPoint, isLine, isPolygon, isMultiPolygon):
        efficiency_ = 0.
        if isPoint:
            #points match each cell exactly once
            efficiency_ = Spatial.getRelativeHeightInBoundingBox(z_min, z_max, cell_box)
        elif isPolygon or isLine or isMultiPolygon:
            efficiency_ = Spatial.getRelativeHeightInBoundingBox(z_min, z_max, cell_box)
        return efficiency_

    def getGridXYFromReferencePoint(self):
        """
        This method gets the origin of the grid to the bottom-left corner.
        "Reference" coordinates need to be related to the center of the grid.
        """
        try:
            reference_point_wkt = "POINT (%s %s)" % (self._grid._reference_longitude, self._grid._reference_latitude)
            logger.info("AUSTAL2000: Grid reference point: %s" % reference_point_wkt)

            # Convert the ARP into EPSG 3857
            sql_text = "SELECT X(ST_Transform(ST_PointFromText('%s', 4326), 3857)), Y(ST_Transform(ST_PointFromText('%s', 4326), 3857));" % \
                       (reference_point_wkt, reference_point_wkt)
            result = SQLInterface.query_text(self._grid._db_path, sql_text)
            if result is None:
                raise Exception("AUSTAL2000: Could not reset reference point as coordinates could not be transformed. The query was\n'%s'" % (sql_text))
                return None

            self._reference_x = conversion.convertToFloat(result[0][0])
            self._reference_y = conversion.convertToFloat(result[0][1])
            self._reference_z = self._grid._reference_altitude
            # logger.info("self._reference_x: %s, self._reference_y: %s, self._reference_z: %s"%(self._reference_x, self._reference_y, self._reference_z))

            # Calculate the coordinates of the bottom left of the grid
            grid_origin_x = float(self._reference_x) - (float(self._grid._x_cells) / 2.) * float(self._grid._x_resolution)
            grid_origin_y = float(self._reference_y) - (float(self._grid._y_cells) / 2.) * float(self._grid._y_resolution)
            # logger.info("getGridXYFromReferencePoint: bottom left of the EMIS grid: x0=%.0f, y0=%.0f" % (grid_origin_x, grid_origin_y))

            # conc grid
            user_set_factor = 2.0  # ToDo: Enlarge Calculation Grid by Factor set by the user?
            self._x_left_border_calc_grid = float(grid_origin_x) - user_set_factor*float(self._grid._x_resolution)
            self._y_left_border_calc_grid = float(grid_origin_y) - user_set_factor*float(self._grid._y_resolution)
            # logger.info("getGridXYFromReferencePoint: bottom left of the CONC grid: xq=%.0f, yq=%.0f" % (self._x_left_border_calc_grid, self._y_left_border_calc_grid))

            # emissions grid == coordinates of the bottom left of the grid
            self._x_left_border_em_grid = float(grid_origin_x)
            self._y_left_border_em_grid = float(grid_origin_y)
            # logger.info("emissions grid corner: (%s, %s)"%(self._x_left_border_em_grid, self._y_left_border_em_grid))

            try:
                if not self._receptors.empty:
                    for idp in self._receptors.index:
                        self._receptors.crs = {'init': 'epsg:%s' % self._receptors.loc[idp, "crs"]}
                        rec_point = self._receptors.to_crs({'init': 'epsg:3857'}).loc[idp, "geometry"]
                        self.xp_.append(round(rec_point.x-self._reference_x, 2))
                        self.yp_.append(round(rec_point.y-self._reference_y, 2))
                        self.zp_.append(rec_point.z)
            except Exception as exc_:
                logger.warning("Couldn't add receptor points to dispersion study (%s)"%exc_)
            return True

        except Exception as e:
            logger.error("AUSTAL2000: Could not reset 3D grid origin from reference point: %s" % e)
            return False

    def InitializeEmissionGridMatrix(self):
        if (self._grid is None) or (self._sequ is None):
            raise Exception("No 3DGrid or Sequence found. Cannot initialize the emissions grid")

        index_i = self._z_meshes if self.getSequ().split(",")[0].startswith("k") else self._y_meshes if \
            self.getSequ().split(",")[0].startswith("j") else self._x_meshes
        index_j = self._z_meshes if self.getSequ().split(",")[1].startswith("k") else self._y_meshes if \
            self.getSequ().split(",")[1].startswith("j") else self._x_meshes
        index_k = self._z_meshes if self.getSequ().split(",")[2].startswith("k") else self._y_meshes if \
            self.getSequ().split(",")[2].startswith("j") else self._x_meshes

        self._emission_grid_matrix = np.zeros(shape=(index_i, index_j, index_k))
        # self._coordinates_grid_matrix = np.zeros(shape=(index_i, index_j, index_k),dtype='i,i,i')
        # self._coordinates_grid_matrix = np.zeros(shape=(index_i, index_j, index_k),dtype='i,i,i').tolist()

        return (index_i, index_j, index_k)

    def emptyOutputPath(self):
        import shutil, stat, errno

        def handleRemoveReadonly(func, path, exc):
            excvalue = exc[1]
            if func in (os.rmdir, os.remove) and excvalue.errno == errno.EACCES:
                os.chmod(path, stat.S_IRWXU| stat.S_IRWXG| stat.S_IRWXO) # 0777
                func(path)
            else:
                raise Exception("handleRemoveReadonly error")

        if os.listdir(self.getOutputPath()):
            # QtWidgets.QMessageBox.warning(self, "Folder contents", os.listdir(self.getOutputPath()))
            answer = QtWidgets.QMessageBox.question(None, "Warning", "A2K Destination folder is not empty!\nDelete existing files?",
                                                    QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
            if answer == QtWidgets.QMessageBox.Yes:
                try:
                    for dir_content in os.listdir(self.getOutputPath()):
                        delete_content = os.path.join(str(self.getOutputPath()), dir_content)
                        # if "QGIS" not in delete_content:
                        try:
                            if os.path.isdir(delete_content):
                                shutil.rmtree(delete_content, ignore_errors=False, onerror=handleRemoveReadonly)
                            elif os.path.isfile(delete_content):
                                os.remove(delete_content)
                        except:
                            logger.warning("Could not delete %s" % os.path.join(str(self.getOutputPath()), dir_content))
                            pass
                        # else:
                        #     logger.error("A2K files were not deleted, folder is output in %s" % str(self.getOutputPath()))
                except Exception as exc_:
                    logger.error(exc_)
            else:
                logger.warning("Previous A2K files were not deleted, verify output in %s" %str(self.getOutputPath()))




    # def getTimeSeries(self, db_path=""):
    #     from datetime import timedelta, date
    #     from dateutil import rrule
    #     from dateutil.relativedelta import relativedelta
    #
    #     if db_path:
    #         try:
    #             time_series_ = [datetime.strptime(t_[1], "%Y-%m-%d %H:%M:%S") for t_ in alaqsutils.inventory_time_series(db_path)]
    #             time_series_.sort()
    #             return time_series_
    #         except Exception, e:
    #             logger.error("Database error: '%s'" % (e))
    #             (time_start_calc_,time_end_calc_) = self.getMinMaxTime(db_path)
    #             time_series_ = []
    #             for _day_ in rrule.rrule(rrule.DAILY, dtstart=time_start_calc_, until=time_end_calc_):
    #                 for hour_ in rrule.rrule(rrule.HOURLY, dtstart=_day_, until=_day_ + timedelta(days=+1, hours=-1)):
    #                     time_series_.append(hour_.strftime('%Y-%m-%d.%H:%M:%S'))
    #             return time_series_

    def checkTimeIntervalinResults(self):
        if not (list(self.getSortedResults().keys()) == list(self.getSortedSeries().keys())):
            logger.debug("AUSTAL2000 Error: Contradictory data for series.dmna and austal.txt files")
            return False
        else:
            return True

    def checkHoursinResults(self):

        if datetime.strptime(list(self.getSortedResults().keys())[0], '%Y-%m-%d.%H:%M:%S').hour != 1 or \
            datetime.strptime(list(self.getSortedSeries().keys())[0], '%Y-%m-%d.%H:%M:%S').hour != 1:
            logger.warning("AUSTAL2000 Warning: The time series must start at time 01 (found %s)"%list(self.getSortedResults().keys())[0])

        start_date = datetime.strptime(list(self.getSortedResults().keys())[0], '%Y-%m-%d.%H:%M:%S')#.replace(hour=1, minute=0)
        end_date = datetime.strptime(list(self.getSortedResults().keys())[-1], '%Y-%m-%d.%H:%M:%S')

        timedelta_ = end_date - start_date
        if timedelta_.total_seconds() < 86400:
            logger.warning("A2K warning: The time series must cover at least one day. End date will be changed from %s to %s"%(end_date, start_date+timedelta(hours=24)))
            end_date = start_date + timedelta(hours=23)

        missed_hours = []
        for _day_ in rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date):
            for hour_ in rrule.rrule(rrule.HOURLY, dtstart=_day_, until=_day_ + timedelta(days=+1, hours=-1)):
                if hour_.strftime('%Y-%m-%d.%H:%M:%S') not in list(self.getSortedResults().keys()) and hour_ <= end_date:
                    missed_hours.append(hour_.strftime('%Y-%m-%d.%H:%M:%S'))
                    self._results.setdefault(hour_.strftime('%Y-%m-%d.%H:%M:%S'),OrderedDict())
                    self._series.setdefault(hour_.strftime('%Y-%m-%d.%H:%M:%S'),OrderedDict())

                    series_fill = {
                           "WindDirection": 999,
                           "WindSpeed": 0.7,
                           "ObukhovLength": 99999.0 # ambient_conditions.getObukhovLength()
                           }
                    self._series[hour_.strftime('%Y-%m-%d.%H:%M:%S')].update(series_fill)

                    results_fill = {'01':
                                    {'timeID': 1,
                                    "source":"",
                                     "pollutant":"",
                                     "emission_rate":0.0}
                                    }
                    self._results[hour_.strftime('%Y-%m-%d.%H:%M:%S')].update(results_fill)
        return missed_hours

    def resetDate(self, startTime, endTime, timeval):

        # A2K always should start from yyyy-01-01.01.00.00
        if (self._dayID == 0 and not self._dateID):
            self._dateID = timeval
            self._timedelta_from_start = (timeval - timeval.replace(month=1, day=1, hour=0, minute=0,second=0))
            # self._timedelta_from_start = relativedelta(timeval, timeval.replace(month=1, day=1, hour=0, minute=0,second=0))
            logger.info("AUSTAL2000 Begin Job: Timedelta from start: %s"%(self._timedelta_from_start))

            self._startTimeSeries = startTime.getTimeAsDateTime() - self._timedelta_from_start
            self._endTimeSeries = endTime.getTimeAsDateTime() - self._timedelta_from_start

            # logger.info("\t %s - %s"%(self._startTimeSeries, self._endTimeSeries))

        else:
            self._startTimeSeries = self._startTimeSeries + timedelta(hours=+1)
            self._endTimeSeries = self._endTimeSeries + timedelta(hours=+1)

    def CalculateCellHashEfficiency(self, EmissionsValue, SourceGeometryText, Bbox, cells_matched, isPoint_element_,
                                        isLine_element_, isPolygon_element_, isMultiPolygon_element_):

        debug_efficiency_ = 0.
        debug_efficiency_xy = 0.

        z_min = Bbox["z_min"]
        z_max = Bbox["z_max"]

        cell_efficiency = OrderedDict()
        for xy_rect in cells_matched:
            debug_efficiency_z = 0.
            if not xy_rect:
                logger.info("No matched_cells (%s) for Bbox: %s (Geo: %s) ? " % (xy_rect, Bbox, SourceGeometryText))
                continue

            efficiency_xy_ = 0.
            for index_height_level, cell_hash in enumerate(xy_rect):

                x_, y_, z_ = 0., 0., 0.
                (x_, y_, z_) = self.getGrid().convertCellHashListToCenterGridCellCoordinates([cell_hash])[cell_hash]

                cell_bbox = self.getCellBox(x_, y_, z_, self.getGrid())

                # calculate once for each x,y pair (and all z levels):
                if not index_height_level:
                    efficiency_xy_ = self.getEfficiencyXY(SourceGeometryText, cell_bbox, isPoint=isPoint_element_,
                                                          isLine=isLine_element_, isPolygon=isPolygon_element_, isMultiPolygon=isMultiPolygon_element_)
                    debug_efficiency_xy += efficiency_xy_

                # get relative height (Z) in bbox
                efficiency_z_ = self.getEfficiencyZ(SourceGeometryText, z_min, z_max, cell_bbox,
                                                    isPoint=isPoint_element_, isLine=isLine_element_,isPolygon=isPolygon_element_, isMultiPolygon=isMultiPolygon_element_)
                efficiency_ = 1. * float(efficiency_xy_) * float(efficiency_z_)

                debug_efficiency_z += efficiency_z_
                debug_efficiency_ += efficiency_

                cell_efficiency[cell_hash] = float(efficiency_)

                # emission_value_ = copy.deepcopy(EmissionsValue)
                # if emission_value_ is None:
                #     emission_value_ = 0.
                # else:
                #     emission_value_ *= float(efficiency_)
                #     cell_efficiency[cell_hash] = emission_value_

                # cell_efficiency[cell_hash] = emission_value_

                # if cell_hash in self.total_emissions_per_cell_dict:
                #     self.total_emissions_per_cell_dict[cell_hash] += emission_value_
                # else:
                #     self.total_emissions_per_cell_dict[cell_hash] = emission_value_
        return cell_efficiency

    def calculate_emissions_per_grid_cell(self, edf_row):
        geom = edf_row.geometry
        EmissionValue = edf_row.emissions
        cells = matched_cells_2D[matched_cells_2D.intersection(geom).is_empty == False]

        if geom.type == 'LineString':
            cells.loc[cells.index, 'Emission'] = EmissionValue * cells.intersection(geom).length / geom.length
        elif geom.type == 'Point':
            cells.loc[cells.index, 'Emission'] = EmissionValue / cells.shape[0]
        elif geom.type == 'Polygon':
            cells.loc[cells.index, 'Emission'] = EmissionValue * cells.intersection(geom).area / geom.area

        self._grid.loc[cells.index, 'Emission'] += cells["Emission"]


    def beginJob(self):
        if self.isEnabled():

            if self._grid is None:
                raise Exception("No 3DGrid found. Use parameter 'grid' to configure one on AUSTAL2000OutputModule "
                                "initialization (e.g. from instantiated EmissionCalculation.")
            else:
                # self._data = self._grid.get_df_from_2d_grid_cells()
                # # self._data = self._grid.get_df_from_3d_grid_cells()
                # # self._grid3D = self._grid3D.assign(Emission=pd.Series(0, index=self._grid3D.index))
                # # self._grid3D = self._grid3D.assign(EmissionSource=pd.Series("", index=self._grid3D.index))
                # # self._grid2D = self._grid3D[self._grid3D.zmin == 0]
                # # self._grid2D = self._grid2D.assign(Emission=pd.Series(0, index=self._grid2D.index))
                #
                # # self._data = self._data[self._data.zmin == 0]
                # self._data = self._data.assign(Emission=pd.Series(0, index=self._data.index))

                self.getGridXYFromReferencePoint()
                # logger.info("Reference  grid origin: x_ref=%.0f, y_ref=%.0f" % (self._reference_x, self._reference_y))

                self._emission_grid_matrix = None
                # self._coordinates_grid_matrix = None

                self._x_meshes = self._grid._x_cells
                self._y_meshes = self._grid._y_cells
                self._z_meshes = self._grid._z_cells

                # AUSTAL2000 cannot take non square grid cells, choose finer resolution
                self._mesh_width = min(self._grid.getResolutionX(), self._grid.getResolutionY()) # dd for austal2000.txt
                self._grid._x_resolution = self._mesh_width
                self._grid._y_resolution = self._mesh_width

                if not self._output_path:
                    OutputPath = QtWidgets.QFileDialog.getExistingDirectory(None, "AUSTAL2000: Select Output directory")
                    self.setOutputPath(OutputPath)
                    if (not os.path.isdir(self.getOutputPath())):
                        raise Exception("AUSTAL2000: Not a valid path for grid source file %s'" % (self.getOutputPath()))
                    else:
                        self.emptyOutputPath()
                        self._grid_db_path = self.getOutputPath()

                # Store results
                # self._matched_cells = None
                self.source_counter = 0
                # self._geometries = OrderedDict()
                self._results = OrderedDict()
                self._series = OrderedDict()
                self._total_sources = OrderedDict()
                self._timeID_per_source = OrderedDict()
                self._dayID = 0
                self._dateID = None
                self._dates = OrderedDict()
                self._startTimeSeries, self._endTimeSeries = None, None

                self._source_geometries = OrderedDict()
        # logger.debug("Begin Job / Time elapsed: %s"%(time2-time1))

    def process(self, startTimeSeries, endTimeSeries, timeval, result, ambient_conditions=None, **kwargs):
        """
        Here we define the rest of the parameters for the austal2000.txt file (iq, xq, yq, hq, emission_rate).
        Moreover, we define the parameters for the grid source file (e????.dmna). The index can be specified as time dependent,
        hence an index running from 1 to 8760 for example (grid files e0001.dmna to e8760.dmna).
        This allows to specifiy a different relative spatial distribution of emissions for every hour of the year.
        Likewise, the overall emission rate of the grid can be specified as time-dependent with hourly means
        for every hour of the year. This combination provides a high flexibility.
        timeval: the actual date
        """
        if not (timeval>=startTimeSeries.getTimeAsDateTime() and timeval<endTimeSeries.getTimeAsDateTime()):
            return [(timeval, self, None)]

        self._lowb = "1 1 1" # (i1 j1 k1, in this order)
        self._hghb = " ".join([str(self._x_meshes), str(self._y_meshes), str(self._z_meshes)]) #(i2 j2 k2, in this order)

        self.resetDate(startTimeSeries, endTimeSeries, timeval)

        if timeval not in self._dates:
            self._dates[timeval] = [self._startTimeSeries, self._endTimeSeries]
        fdate = self._dates[list(self._dates.keys())[0]][0]

        self.source_counter += +1
        self._results.setdefault(self._endTimeSeries.strftime('%Y-%m-%d.%H:%M:%S'),OrderedDict())

        self._series.setdefault(self._endTimeSeries.strftime('%Y-%m-%d.%H:%M:%S'),OrderedDict())
        # ToDo: Add Obukhov length to ambient conditions
        ac_ = {
               "WindDirection": ambient_conditions.getWindDirection(),
               "WindSpeed": ambient_conditions.getWindSpeed(),
               "ObukhovLength": ambient_conditions.getObukhovLength()
               }
        self._series[self._endTimeSeries.strftime('%Y-%m-%d.%H:%M:%S')].update(ac_)

        # ToDo: how much finer/coarser is the emission dd ?
        dd_ = self._mesh_width#/float(3) #horizontal mesh width in m
        sk_ = " ".join([str(self._grid.getResolutionZ()*z) for z in range(0, self._z_meshes+1)]) #vertical grid (h0 h1 h2 ...), heights above ground in m
        mode_ = '"text"'
        form_ = '"Eq%5.1f"'
        vldf_ = '"V"'
        artp_ = '"M"'
        dims_ = 3
        sequ_ = self.getSequ()
        axes_ = '"xyz"'

        # Loop over all emissions and append one data point for every cell to total_emissions_per_cell_dict
        source_counter = 0

        self.total_emissions_per_cell_dict = {} # for the specific result

        for (source_, emissions__) in result:
            # fig, ax = plt.subplots()

            fill_results = OrderedDict()

            self._source_height = source_.getHeight() if (hasattr(source_, 'getHeight') and source_.getHeight()>0) else 0

            for emissions_ in emissions__:
                if emissions_.getGeometryText() is None:
                    # if not emissions_.isZero():
                    logger.warning("AUSTAL2000: Did not find geometry for source: %s"%(str(source_.getName())))
                    continue

                # # geom__ = Spatial.ogr.CreateGeometryFromWkt(str(emissions_.getGeometryText()))
                geom = emissions_.getGeometry()
                # ax.set_title(source_.getName())
                # gpd.GeoSeries(geom).plot(ax=ax, color='r', alpha=0.25)

                # Some convenience variables
                isPoint_element_ = bool("POINT" in emissions_.getGeometryText())
                isLine_element_ = bool(("LINE" in emissions_.getGeometryText())&(not "MULTI" in emissions_.getGeometryText()))
                isMultiLine_element_ = bool("MULTILINE" in str(emissions_.getGeometryText()))
                isPolygon_element_ = bool(("POLYGON" in emissions_.getGeometryText())&(not "MULTI" in emissions_.getGeometryText()))
                isMultiPolygon_element_ = bool("MULTIPOLYGON" in emissions_.getGeometryText())

                # if isMultiPolygon_element_ and len(list(geom))==1:
                #     eps = 0.01
                #     geom = cascaded_union([
                #         Polygon(component.exterior).buffer(eps).buffer(-eps) for component in geom])
                #     print("Simplify geom to %s"%geom.wkt)
                #     isMultiPolygon_element_ = False
                #     isPolygon_element_ = True

                if isMultiPolygon_element_ or isMultiLine_element_:
                    MultiPolygonEmissions = 1/len(list(geom)) * emissions_
                    # MultiPolygonEmissions = 1/geom.GetGeometryCount() * emissions_
                    for i in range(0, len(list(geom))):
                        g = geom[i]
                        g_wkt = g.wkt
                        # for i in range(0, geom.GetGeometryCount()):
                        #     g = geom.GetGeometryRef(i)
                        #     bbox = self.getBoundingBox(g.ExportToWkt())
                        if g_wkt not in self._source_geometries.keys():
                            bbox = self.getBoundingBox(g_wkt)
                            # Take into account the effective vertical source extent and shift
                            bbox["z_max"] = bbox["z_max"]+emissions_.getVerticalExtent()['delta_z'] if \
                                "delta_z" in emissions_.getVerticalExtent() else bbox["z_max"]
                            matched_cells = self.getGrid().matchBoundingBoxToCellHashList(bbox, z_as_list=True)
                            matched_cells_coeff = self.CalculateCellHashEfficiency(MultiPolygonEmissions,
                                                             g_wkt, bbox, matched_cells, isPoint_element_,
                                                             isLine_element_, isPolygon_element_,
                                                             isMultiPolygon_element_)

                            self._source_geometries[g_wkt] = {'bbox': bbox,
                                                              'matched_cells': matched_cells,
                                                              "efficiency": matched_cells_coeff}
                        else:
                            # bbox = self._source_geometries[g_wkt]['bbox']
                            # matched_cells = self._source_geometries[g_wkt]['matched_cells']
                            matched_cells_coeff = self._source_geometries[g_wkt]['efficiency']

                        emission_value_ = copy.deepcopy(MultiPolygonEmissions)
                        # if emission_value_ is None:
                        #     emission_value_ = 0.
                        # else:
                        #     emission_value_ *= float(efficiency_)

                        for cell_hash in matched_cells_coeff:
                            emission_value_ *= matched_cells_coeff[cell_hash]
                            if cell_hash in self.total_emissions_per_cell_dict:
                                self.total_emissions_per_cell_dict[cell_hash] += emission_value_
                                # self.total_emissions_per_cell_dict[cell_hash] += matched_cells_coeff[cell_hash]
                            else:
                                self.total_emissions_per_cell_dict[cell_hash] = emission_value_
                                # self.total_emissions_per_cell_dict[cell_hash] = matched_cells_coeff[cell_hash]
                        # self.CalculateCellHashEfficiency(MultiPolygonEmissions,
                        #                                  g_wkt, bbox, matched_cells, isPoint_element_,
                        #                                  isLine_element_, isPolygon_element_, isMultiPolygon_element_)

                else:
                    if emissions_.getGeometryText() not in self._source_geometries.keys():
                        bbox = self.getBoundingBox(emissions_.getGeometryText())
                        if "delta_z" in emissions_.getVerticalExtent() and emissions_.getVerticalExtent()['delta_z'] > 0:
                            bbox["z_max"] = bbox["z_max"] + emissions_.getVerticalExtent()['delta_z']
                        matched_cells = self.getGrid().matchBoundingBoxToCellHashList(bbox, z_as_list=True)
                        matched_cells_coeff = self.CalculateCellHashEfficiency(emissions_,
                                                                               emissions_.getGeometryText(), bbox, matched_cells,
                                                                               isPoint_element_,
                                                                               isLine_element_, isPolygon_element_,
                                                                               isMultiPolygon_element_)

                        self._source_geometries[emissions_.getGeometryText()] = {'bbox': bbox,
                                                          'matched_cells': matched_cells,
                                                          "efficiency": matched_cells_coeff}
                    else:
                        # bbox = self._source_geometries[emissions_.getGeometryText()]['bbox']
                        # matched_cells = self._source_geometries[emissions_.getGeometryText()]['matched_cells']
                        matched_cells_coeff = self._source_geometries[emissions_.getGeometryText()]['efficiency']

                    emission_value_ = copy.deepcopy(emissions_)
                    for cell_hash in matched_cells_coeff:
                        emission_value_ *= matched_cells_coeff[cell_hash]
                        if cell_hash in self.total_emissions_per_cell_dict:
                            self.total_emissions_per_cell_dict[cell_hash] += emission_value_
                            # self.total_emissions_per_cell_dict[cell_hash] += matched_cells_coeff[cell_hash]
                        else:
                            self.total_emissions_per_cell_dict[cell_hash] = emission_value_
                            # self.total_emissions_per_cell_dict[cell_hash] = matched_cells_coeff[cell_hash]


                    # for cell_hash in matched_cells_coeff:
                    #     if cell_hash in self.total_emissions_per_cell_dict:
                    #         self.total_emissions_per_cell_dict[cell_hash] += matched_cells_coeff[cell_hash]
                    #     else:
                    #         self.total_emissions_per_cell_dict[cell_hash] = matched_cells_coeff[cell_hash]
                    # self.CalculateCellHashEfficiency(emissions_,emissions_.getGeometryText(), bbox, matched_cells,
                    #                     isPoint_element_, isLine_element_, isPolygon_element_, isMultiPolygon_element_)

        # import pickle
        # pickle.dump([timeval, self.total_emissions_per_cell_dict], open("total_emissions_per_cell_dict.p", "wb"))

        # Fill Emissions Matrix with emission rate (normalised to 1)
        poll_cnt = 0
        # matrix_done = False
        for _pollutant in self._pollutants_list:
            # t_1 = time.time()

            hashed_emissions = 0.
            source_counter += +1
            if not os.path.isdir(os.path.join(str(self.getOutputPath()),str(source_counter).zfill(2))):
                os.mkdir(os.path.join(str(self.getOutputPath()),str(source_counter).zfill(2)))

            # initialize emission matrix for each pollutant
            # (x_dim, y_dim, z_dim) = self.InitializeEmissionGridMatrix()

            hashed_emissions = sum([self.total_emissions_per_cell_dict[hash_].transposeToKilograms().getValue(_pollutant, "kg")[0]
                                    for hash_ in list(self.total_emissions_per_cell_dict.keys())])

            # if total_emissions_per_mov.transposeToKilograms().getValue(_pollutant, "kg")[0] and \
            #         abs(hashed_emissions - total_emissions_per_mov.transposeToKilograms().getValue(_pollutant, "kg")[0])>0.1 :
            #     if source_counter == 2:
            #         logger.warning("AUSTAL2000: Grid may have to be enlarged for source:'%s'"%(source_.getName()))
            #         logger.warning("\t Hashed emissions are <%s> instead of <%s>" %
            #                    (hashed_emissions, total_emissions_per_mov.transposeToKilograms().getValue(_pollutant)[0]))

            (x_dim, y_dim, z_dim) = self.InitializeEmissionGridMatrix()

            if hashed_emissions > 0:
                # initialize emission matrix for each pollutant
                # (x_dim, y_dim, z_dim) = self.InitializeEmissionGridMatrix()
                for hash in list(self.total_emissions_per_cell_dict.keys()):
                    i_, j_, k_ = None, None, None
                    ii, jj, kk = None, None, None

                    if not (self.total_emissions_per_cell_dict[hash].getValue(_pollutant)[0] > 0):
                        continue

                    i_, j_, k_ = self._grid.convert_CellHash_To_XYZIndices(hash)

                    if i_ >= self._x_meshes or j_ >= self._y_meshes or k_ >= self._z_meshes:
                        # logger.debug("AUSTAL2000 Error: Grid needs to be enlarged. Hash '%s' out of grid. Source:'%s'"%(hash, source_.getName()))
                        continue

                    ii = k_ if self.getSequ().split(",")[0].startswith("k") else j_ if \
                        self.getSequ().split(",")[0].startswith("j") else i_
                    jj = k_ if self.getSequ().split(",")[1].startswith("k") else j_ if \
                        self.getSequ().split(",")[1].startswith("j") else i_
                    kk = k_ if self.getSequ().split(",")[2].startswith("k") else j_ if \
                        self.getSequ().split(",")[2].startswith("j") else i_

                    # Reverse order if '-'
                    # A sequence 'k +, j -, i +' means north-oriented
                    if (self.getSequ().split(",")[0][1]== "-"):
                        ii = x_dim - (ii + 1)
                    if (self.getSequ().split(",")[1][1] == "-"):
                        jj = y_dim - (jj + 1)
                    if (self.getSequ().split(",")[2][1] == "-"):
                        kk = z_dim - (kk + 1)

                    try:
                        self._emission_grid_matrix[ii, jj, kk] += \
                            self.total_emissions_per_cell_dict[hash].getValue(_pollutant)[0]/hashed_emissions
                    except Exception as e:
                        pass

            self._total_sources.setdefault(str(source_counter).zfill(2), [])
            if _pollutant.startswith("PM"):
                _pollutant = "PM-2" if _pollutant == "PM10" else "PM-1"
            if _pollutant not in self._total_sources[str(source_counter).zfill(2)]:
                self._total_sources.setdefault(str(source_counter).zfill(2), []).append(_pollutant)

            if str(source_counter).zfill(2) in self._timeID_per_source:
                time_id = self._timeID_per_source[str(source_counter).zfill(2)]
                self._timeID_per_source.update({str(source_counter).zfill(2): time_id + 1})
            else:
                self._timeID_per_source.update({str(source_counter).zfill(2): 1})

            # Emission rate in AUSTAL2000 is in g/s (kg x 1000/3600), hashed_emissions are given in kg/h
            fill_results.setdefault(str(source_counter).zfill(2), {})

            pollutant_dic = {"source": source_.getName(), _pollutant: hashed_emissions * (10.0 / 36.0),
                             "timeID": self._timeID_per_source[str(source_counter).zfill(2)]}
            fill_results.setdefault(str(source_counter).zfill(2), []).update(pollutant_dic)

            self._results[self._endTimeSeries.strftime('%Y-%m-%d.%H:%M:%S')].update(fill_results)

            # Start writing to file
            try:
                time_interval = "e"+str(self._timeID_per_source[str(source_counter).zfill(2)]).zfill(4)
                text_file = open(os.path.join(str(self.getOutputPath()),str(source_counter).zfill(2),"%s.dmna"%time_interval), "w")

                start_ = "%s.%s"%((self._startTimeSeries-fdate).days, self._startTimeSeries.strftime("%H:%M:%S"))
                text_file.write("t1\t%s\n" % start_)
                end_ = "%s.%s"%((self._endTimeSeries-fdate).days, self._endTimeSeries.strftime("%H:%M:%S"))
                text_file.write("t2\t%s\n" % end_)

                text_file.write("dd\t%s\n" % dd_)
                text_file.write("sk\t%s\n" % sk_)
                text_file.write("-\n")
                text_file.write("mode\t%s\n" % mode_)
                text_file.write("form\t%s\n" % form_)
                text_file.write("vldf\t%s\n" % vldf_)
                text_file.write("artp\t%s\n" % artp_)
                text_file.write("dims\t%s\n" % dims_)
                text_file.write("axes\t%s\n" % axes_)
                text_file.write("sequ\t%s\n" % self.getSequ())
                text_file.write("-\n")
                text_file.write("lowb\t%s\n" %self._lowb)
                text_file.write("hghb\t%s\n" %self._hghb)
                text_file.write("*\n")

                for x, y in itertools.product(*list(map(range, (x_dim, y_dim)))):
                    text_file.write("%s\n"%("\t").join([str(elem) for elem in self._emission_grid_matrix[x,y].tolist()]))
                    if y+1 == y_dim:
                       text_file.write("\n")
                text_file.write("***\n")
                text_file.close()

            except Exception as exc_:
                logger.error(exc_)

        # # provide file with more information
        # text_file = open(os.path.join(str(self.getOutputPath()),str(source_counter).zfill(2),"%s_%s.info"%(time_interval, _pollutant)), "w")
        # text_file.write("***\n")
        # text_file.write("t1\t%s\n" % startTimeSeries.getTimeAsDateTime().strftime('%Y-%m-%d.%H:%M:%S'))
        # text_file.write("t2\t%s\n" % endTimeSeries.getTimeAsDateTime().strftime('%Y-%m-%d.%H:%M:%S'))
        # text_file.write("----\n")
        # text_file.write("source name\t%s\n" % source_.getName())
        # text_file.write("----\n")
        # text_file.write("bbox\t%s\n" % bbox)
        # text_file.write("***\n")
        # text_file.close()


    def endJob(self):
        # logger.debug("End Job")
        if self.isEnabled():
            try:
                if not self.checkTimeIntervalinResults():
                    raise Exception("AUSTAL2000: Time Interval Error")
                    return None

                try:
                # --------------------- austal2000.txt ------------------------------------------------------
                    text_file = open(os.path.join(str(self.getOutputPath()),"austal.txt"), "w")
                    self._austal2000_txt = os.path.join(str(self.getOutputPath()),"austal.txt")
                    # text_file = open(os.path.join(str(self.getOutputPath()), "austal2000.txt"), "w")
                    # self._austal2000_txt = os.path.join(str(self.getOutputPath()), "austal2000.txt")
                    text_file.write("----------------- general parameters\n")
                    text_file.write("ti\t%s\t' title\n" % self._title)
                    text_file.write("qs\t%s\t' quality level\n" % self._quality_level)
                    text_file.write("----------------- meteorology\n")
                    text_file.write("z0\t%s\t' roughness length (m)\n" % self._roughness_level)
                    text_file.write("d0\t%s\t' displacement height (m)\n" % self._displacement_height)
                    text_file.write("ha\t%s\t' anemometer height (m)\n" % self._anemometer_height)
                    text_file.write("----------------- calculation grid\n")
                    text_file.write("dd\t%s\t' mesh width\n" % self._mesh_width)
                    text_file.write("x0\t%s\t' left border (m)\n" % (self._x_left_border_calc_grid - self._reference_x))
                    text_file.write("y0\t%s\t' lower border (m)\n" % (self._y_left_border_calc_grid - self._reference_y))

                    # Add receptor points
                    if (len(self.xp_) == len(self.yp_)) and (len(self.xp_) == len(self.zp_)) and (len(self.xp_)>0) :
                        text_file.write("xp\t%s\t' x-receptor\n" % ("\t").join([str(rx) for rx in self.xp_]))
                        text_file.write("yp\t%s\t' y-receptor\n" % ("\t").join([str(ry) for ry in self.yp_]))
                        text_file.write("hp\t%s\t' z-receptor\n" % ("\t").join([str(rz) for rz in self.zp_]))
                        # text_file.write("xp\t%s\t' x-receptor\n" % ("\t").join([str(rx) for rx in xp_ for ry in yp_]))
                        # text_file.write("yp\t%s\t' y-receptor\n" % ("\t").join([str(ry) for rx in xp_ for ry in yp_]))
                        # text_file.write("hp\t%s\t' z-receptor\n" % ("\t").join([str(0) for rx in xp_ for yr in yp_]))

                    text_file.write("nx\t%s\t' number of meshes\n" % self._x_meshes)
                    text_file.write("ny\t%s\t' number of meshes\n" % self._y_meshes)
                    text_file.write("----------------- source definitions\n")

                    if self._options:
                        text_file.write('os\t"%s"\n'%self._options)
                    text_file.write("iq\t%s\t' file index (set in series.dmna)\n" % ("\t").join(["?" for _iq_ in list(self._total_sources.keys())]))
                    text_file.write("hq\t%s\t' source height (ignored)\n" % ("\t").join([str(self._source_height) for _iq_ in list(self._total_sources.keys())]))
                    text_file.write("xq\t%s\t' x-lower left (south-west) corner of the source\n" % ("\t").join([str(self._x_left_border_em_grid - self._reference_x) for _iq_ in list(self._total_sources.keys())]))
                    text_file.write("yq\t%s\t' y-lower left (south-west) corner of the source\n" % ("\t").join([str(self._y_left_border_em_grid - self._reference_y) for _iq_ in list(self._total_sources.keys())]))

                    for poll in self._pollutants_list:
                        if poll.startswith('PM'):
                            poll = "PM-2" if poll == "PM10" else "PM-1"
                        text_file.write("%s\t%s\t' total %s (in g/s) (set in series.dmna)\n" \
                            %(poll.lower(), ("\t").join(["?" if poll in self._total_sources[src] else "0" for iq, src in enumerate(self._total_sources.keys())]), poll))

                    text_file.close()

                except Exception as e:
                    logger.error("AUSTAL2000: Cannot write 'austal.txt' : %s" % e)
                    return False

                # ----------------------------------------------------------------------------------------
                self.checkHoursinResults()

                try:
                    # ------------------------Series.dmna (for time-dependent parameters)---------------------
                    text_file = open(os.path.join(str(self.getOutputPath()),"series.dmna"), "w")
                    self._series_dmna = os.path.join(str(self.getOutputPath()),"series.dmna")
                    # ----------------------------------------------------------------------------------------
                    form_line = ['"te%20lt"','"ra%5.0f"','"ua%5.1f"','"lm%7.1f"']

                    for iq_ in list(self._total_sources.keys()):
                        form_line.append('"%s.iq%%3.0f"'%str(iq_))
                    for iq_ in list(self._total_sources.keys()):
                        for poll in self._total_sources[iq_]:
                            form_line.append('"%s.%s%%10.3e"'%(str(iq_), poll.lower()))
                    # ----------------------------------------------------------------------------------------
                    text_file.write('form\t%s\n'%('\t').join(form_line))
                    text_file.write('mode\t"text"\n')
                    text_file.write('sequ\t"i"\n')
                    text_file.write('dims\t%s\n'%1)
                    text_file.write('lowb\t%s\n'%1)
                    text_file.write('hghb\t%s\n'%(len(list(self.getSortedResults().keys()))))
                    text_file.write('*\n')
                    # ----------------------------------------------------------------------------------------
                    for dt in self.getSortedResults():
                        iqs = [self.getSortedResults()[dt][iq]['timeID'] if iq in list(self.getSortedResults()[dt].keys()) else 1 \
                               for iq in list(self._total_sources.keys())]
                        emission_rates = []
                        for iq_ in list(self._total_sources.keys()):
                            for poll in self._total_sources[iq_]:
                                if (iq_ in self.getSortedResults()[dt] and poll in self.getSortedResults()[dt][iq_]):
                                    emission_rates.append("{:10.3e}".format(self.getSortedResults()[dt][iq_][poll]))
                                else:
                                    emission_rates.append("{:10.3e}".format(0))
                    # ----------------------------------------------------------------------------------------
                        text_file.write("%s\t%5.0f\t%5.1f\t%7.1f\t%s\t%s\n"%(dt, self._series[dt]['WindDirection'],self._series[dt]['WindSpeed'], self._series[dt]['ObukhovLength'], \
                            ('\t').join([ "%3.0f"%(iq) for iq in iqs]),\
                            ('\t').join([er for er in emission_rates]))
                            )
                    text_file.write('\n')
                    text_file.write('***\n')
                    text_file.close()
                    # logger.debug("Finished <series.dmna>")
                    # ----------------------------------------------------------------------------------------
                    return True
                except Exception as e:
                    logger.error("AUSTAL2000: Cannot write 'Series.dmna' %s" % e)
                    return False

            except Exception as e:
                logger.error("AUSTAL2000: Cannot endJob: %s" % e)
                return False


    # Available Substances in AUSTAL2000
    # so2: Sulphur dioxide, SO2
    # no: Nitrogen monoxide, NO
    # no2: Nitrogen dioxide, NO2
    # nox: Nitrogen oxides, NOx (specified as NO2 )
    # bzl: Benzene
    # tce: Tetrachloroethylene
    # f: Hydrogen fluoride (specified as F)
    # nh3: Ammonia, NH3
    # hg: Mercury, Hg, according to TA Luft (vd =0.005 m/s) hg0 Elementary mercury, Hg(0) (vd =0.0003 m/s)
    # xx: Unspecified
    # odor: Unrated odorant
    # odor:_nnn Rated odorant with a rate factor resulting from the identifier nnn,
    # see Section 3.10. Possible values for nnn are: 050 (in the fed- eral state Baden-Württemberg: 040),
    # 075 (in the federal state Baden- Württemberg: 060), 100, 150
