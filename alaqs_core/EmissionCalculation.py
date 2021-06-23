import inspect
from collections import OrderedDict

from PyQt5 import QtCore, QtWidgets

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.AmbientCondition import \
    AmbientConditionStore, AmbientCondition
from open_alaqs.alaqs_core.interfaces.DispersionModule import DispersionModule
from open_alaqs.alaqs_core.interfaces.Emissions import Emission
from open_alaqs.alaqs_core.interfaces.InventoryTimeSeries import \
    InventoryTimeSeriesStore
from open_alaqs.alaqs_core.interfaces.SourceModule import SourceModule
from open_alaqs.alaqs_core.modules.ModuleManager import SourceModuleManager, \
    DispersionModuleManager
from open_alaqs.alaqs_core.tools import Iterator, conversion
from open_alaqs.alaqs_core.tools.Grid3D import Grid3D

logger = get_logger(__name__)


class EmissionCalculation:
    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}

        self._database_path = values_dict.get("database_path")
        if self._database_path is None:
            raise Exception("Value '%s' not defined for class '%s'" %
                            ("database_path", "EmissionCalculation"))

        # Get the time series for this inventory
        self._inventoryTimeSeriesStore = InventoryTimeSeriesStore(
            self.getDatabasePath())
        self._emissions = OrderedDict()
        self._module_manager = SourceModuleManager()
        self._modules = OrderedDict()
        self._dispersion_modules = OrderedDict()
        self._dispersion_module_manager = DispersionModuleManager()
        self._ambient_conditions_store = \
            AmbientConditionStore(self.getDatabasePath())

        self._3DGrid = Grid3D(self.getDatabasePath(), values_dict.get(
            "grid_configuration",
            {
                'x_cells': 10,
                'y_cells': 10,
                'z_cells': 1,
                'x_resolution': 100,
                'y_resolution': 100,
                'z_resolution': 100,
                'reference_latitude': '0.0',  # airport_latitude
                'reference_longitude': '0.0',  # airport_longitude
                'reference_altitude': '0.0'  # airport_altitude
            }))

        self._debug = values_dict.get("debug", False)

    @staticmethod
    def ProgressBarWidget(dispersion_enabled=False):
        if dispersion_enabled:
            progressbar = QtWidgets.QProgressDialog(
                "Calculating emissions & writing input files for"
                " dispersion model ...", "Cancel", 0, 99)
        else:
            progressbar = QtWidgets.QProgressDialog(
                "Calculating emissions ...", "Cancel", 0, 99)
        progressbar.setWindowTitle("Emissions Calculation")
        # self._progressbar.setValue(1)
        progressbar.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        progressbar.setWindowModality(QtCore.Qt.WindowModal)
        progressbar.setAutoReset(True)
        progressbar.setAutoClose(True)
        progressbar.resize(350, 100)
        progressbar.show()
        return progressbar

    def getAmbientCondition(self, timestamp_datetime):
        t_ = conversion.convertTimeToSeconds(timestamp_datetime)
        ac_ = self._ambient_conditions_store.getAmbientConditions(scenario="")
        if ac_:
            # print "AC_ %s"%min(ac_, key=lambda x: abs(t_ - x.getDate()))
            return min(ac_, key=lambda x: abs(t_ - x.getDate()))
        else:
            return None

    def getModuleManager(self):
        # ModuleManger is a Singleton
        return self._module_manager

    def getDispersionModuleManager(self):
        # ModuleManger is a Singleton
        return self._dispersion_module_manager

    def addModule(self, name, obj=None, configuration=None, db_path=""):
        if configuration is None:
            configuration = {}
        if obj is None:
            found_ = self.getModuleManager().getModulesByName(name)
            if len(found_) == 0:
                logger.error("Did not find module with name '%s'" % name)
                return False
            elif len(found_) > 1:
                logger.warning("Found multiple matches for modules with name "
                               "'%s'. Using only first match." % name)
            obj = found_[0][1]  # returns tuple (name, obj)

        # instantiate objects
        if isinstance(obj, SourceModule):
            self._modules[name] = obj
            if db_path:
                obj.setDatabasePath(db_path)
            return True
        else:
            if inspect.isclass(obj):
                # ToDo: re-implement issubclass (it looks like instances of
                #  generic types are no longer instances of type ???)
                # if issubclass(obj, SourceModule):
                # if issubclass(obj, (list, SourceModule)):
                # logger.debug(issubclass(obj, (list, SourceModule)))
                try:
                    config_ = {
                        "database_path":
                            self.getDatabasePath() if not db_path else db_path
                    }
                    config_.update(configuration)
                    self._modules[name] = obj(values_dict=config_)
                    return True
                except Exception:
                    logger.error("issubclass(obj, SourceModule) failed for "
                                 "SourceModule")
                    return False

        return False

    def addDispersionModule(self, name, obj=None, configuration=None):
        if configuration is None:
            configuration = {}
        if obj is None:
            found_ = self.getDispersionModuleManager().getModulesByName(name)
            if len(found_) == 0:
                logger.error(
                    "Did not find dispersion module with name '%s'" % name)
                return False
            elif len(found_) > 1:
                logger.warning("Found multiple matches for dispersion modules "
                               "with name '%s'. Using only first match." % (
                                   name))
            obj = found_[0][1]  # returns tuple (name, obj)
        # instantiate objects
        if isinstance(obj, DispersionModule):
            self._dispersion_modules[name] = obj
            return True
        else:
            if inspect.isclass(obj):
                try:
                    # if issubclass(obj, DispersionModule):
                    config_ = {}
                    config_.update(configuration)
                    self._dispersion_modules[name] = obj(
                        values_dict=configuration)
                    return True
                except Exception as e:
                    logger.error("issubclass(obj, SourceModule) failed for "
                                 "DispersionModule")
                    return False
        return False

    # ToDo: More general configuration
    @staticmethod
    def CheckAmbientConditions(parameter, isa_value, tolerance):
        return 100 * float(abs(parameter - isa_value)) / isa_value > tolerance

    def run(self, source_names=None):
        if source_names is None:
            source_names = []

        default_emissions = {
            "fuel_kg": 0.,
            "co_g": 0.,
            "co2_g": 0.,
            "hc_g": 0.,
            "nox_g": 0.,
            "sox_g": 0.,
            "pm10_g": 0.,
            "p1_g": 0.,
            "p2_g": 0.,
            "pm10_prefoa3_g": 0.,
            "pm10_nonvol_g": 0.,
            "pm10_sul_g": 0.,
            "pm10_organic_g": 0.
        }

        # execute beginJob(..) of SourceModules
        for mod_name, mod_obj in self.getModules().items():
            mod_obj.beginJob()

        dispersion_enabled = False
        # execute beginJob(..) of dispersion modules
        for dispersion_mod_name, dispersion_mod_obj in \
                self.getDispersionModules().items():
            dispersion_enabled = True
            dispersion_mod_obj.beginJob()

        # execute process(..)
        try:
            progressbar = self.ProgressBarWidget(
                dispersion_enabled=dispersion_enabled)
            count_ = 0
            # loop on complete period
            for (start_, end_) in self.getTimeSeries():
                start_time = start_.getTimeAsDateTime()
                end_time = end_.getTimeAsDateTime()
                count_ += +1
                progressbar.setValue(conversion.convertToInt(
                    100 * conversion.convertToFloat(count_) / len(
                        self.getTimeSeriesStore().getObjects())))
                QtCore.QCoreApplication.instance().processEvents()
                if progressbar.wasCanceled():
                    break

                # ToDo: only run on (start_, end_) with emission sources?
                try:
                    ambient_condition = self.getAmbientCondition(
                        start_.getTime())
                except Exception:
                    ambient_condition = AmbientCondition()

                # ordinary sources
                for mod_name, mod_obj in self.getModules().items():
                    # process() returns a list of tuples for each specific
                    # time interval (start_, end_)
                    for (timestamp_, source_, emission_) in mod_obj.process(
                            start_, end_, source_names=source_names,
                            ambient_conditions=ambient_condition):
                        if emission_ is not None:
                            self.addEmission(timestamp_, source_, emission_)
                        else:
                            # logger.info("Adding default (empty) Emissions
                            # for '%s'"%(source_.getName()))
                            emission_ = [
                                Emission(initValues=default_emissions,
                                         defaultValues=default_emissions)]
                            self.addEmission(timestamp_, source_, emission_)

                # Dispersion Model
                for dispersion_mod_name, dispersion_mod_obj in \
                        self.getDispersionModules().items():
                    # row_cnt = 0
                    for timeval, rows in self.getEmissions().items():
                        if start_time <= timeval < end_time:
                            dispersion_mod_obj.process(
                                start_, end_, timeval, rows,
                                ambient_conditions=ambient_condition)

        except StopIteration:
            logger.info("Iteration stopped")
            pass

        # execute endJob(..)
        for mod_name, mod_obj in self.getModules().items():
            mod_obj.endJob

        # execute endJob(..) of dispersion modules
        for dispersion_mod_name, dispersion_mod_obj in \
                self.getDispersionModules().items():
            dispersion_mod_obj.endJob

    def getModules(self):
        return self._modules

    def getDispersionModules(self):
        return self._dispersion_modules

    def availableModules(self):
        return self.getModuleManager().getModules()

    def availableDispersionModules(self):
        return self.getDispersionModuleManager().getModules()

    def addEmission(self, timeval, source, emission, to=None):
        sort_ = False
        if to is None:
            to = self._emissions
            sort_ = True

        if timeval in to:
            to[timeval].append((source, emission))
        else:
            to[timeval] = [(source, emission)]

        if sort_:
            self.sortEmissionsByTime()

    def getEmissions(self):
        return self._emissions

    def sortEmissionsByTime(self):
        # sort emissions by index (which is a timestamp)
        self._emissions = OrderedDict(
            sorted(iter(self.getEmissions().items()), key=lambda x: x[0]))

    def setDatabasePath(self, val):
        self._database_path = val

    def getDatabasePath(self):
        return self._database_path

    def getTimeSeriesStore(self):
        return self._inventoryTimeSeriesStore

    def setTimeSeriesStore(self, var):
        self._inventoryTimeSeriesStore = var

    # returns a generator of TimeSeries objects
    def getTimeSeries(self):
        return Iterator.pairwise(self.getTimeSeriesStore().getTimeSeries())

    # returns a tuple of TimeSeries objects with (start, end)
    def getTimeSeriesTuple(self):
        return self.getTimeSeriesStore().getTimeSeries()

    def get3DGrid(self):
        return self._3DGrid

    def set3DGrid(self, var):
        self._3DGrid = var

# if __name__ == "__main__":
#
#     import time
#     st_ = time.time()
#     # from qgis.PyQt import QtGui
#     from PyQt5 import QtCore, QtWidgets
#     # from python_qt_binding import QtGui, QtCore  # new imports
#     # app = QtWidgets.QApplication(sys.argv)
#
#     # from qgis.PyQt import QtGui
#     # # from python_qt_binding import QtGui, QtCore  # new imports
#     # app = QtGui.QApplication(sys.argv)
#     # app.processEvents()
#
#     app = QtWidgets.QApplication.instance()
#     if app is None:
#         app = QtWidgets.QApplication(sys.argv)
#         print('QApplication instance created: %s' % str(app))
#     else:
#         app.processEvents()
#         app.closeAllWindows()
#         print('QApplication instance already exists: %s' % str(app))
#
#     path_to_database = os.path.join("..", "example/", "CAEPport_training", "caepport_out.alaqs")
#     # path_to_database = os.path.join("..", "example/", "CAEPport", "CAEPport_out_test.alaqs")
#     if not os.path.isfile(path_to_database):
#         raise Exception("File %s doesn't exist !"%path_to_database)
#     print("Running Open-ALAQS for file: %s"%path_to_database)
#
#     # logging.getLogger().setLevel(logging.DEBUG)
#
#     # start a new emission calculation
#     ec = EmissionCalculation({"database_path": path_to_database, "debug": True})
#
#     # for (start_, end_) in ec.getTimeSeries():
#         # print ec.getAmbientCondition(start_.getTime())
#         # break
#
#     config={
#         'reference_altitude': ec.get3DGrid().getAirportAltitude(),
#         # 'Start (incl.)': '2004-01-01 04:00:00',
#         # 'End (incl.)': '2004-01-02 01:00:00',
#         'Vertical limit [m]': u'914.4',
#         'Apply NOx corrections': False,
#         'Source Dynamics': {"available": ["none", "default", "smooth & shift"], "selected": u'default'},
#         # 'Method': {'available': [u'BFFM2', u'bymode', u'matching', u'linear_scaling'], 'selected': u'BFFM2'}
#         'Method': {'available': [u'BFFM2', u'bymode'], 'selected': u'BFFM2'}
#     }
#
#     # ec.addModule("AreaSource")
#     ec.addModule("PointSource")
#     ec.addModule("RoadwaySource")
#     ec.addModule("ParkingSource")
#     ec.addModule("MovementSource", configuration=config)
#
#     # Sources_ = ["PointSource","RoadwaySource","ParkingSource","MovementSource"]
#     # for s_ in Sources_ :
#     #     if s_ == "MovementSource":
#     #         ec.addModule(s_, configuration=config)
#     #     else:
#     #         ec.addModule(s_)
#
#     # load receptors
#     from tools.CSVInterface import read_csv_to_geodataframe
#     filename_ = os.path.join("..", "example/", "CAEPport", "receptors_coords.csv")
#     if not os.path.isfile(filename_):
#         raise Exception("File %s doesn't exist !"%filename_)
#     else:
#         csv_gdf = read_csv_to_geodataframe(filename_)
#
#     # print("Adding Dispesion Module")
#     # work_dir = os.path.join("..", "example/", "CAEPport", "A2K")
#     # ec.addDispersionModule("AUSTAL2000", configuration={"enable": True, "grid":ec.get3DGrid(),
#     #                                                     "add title":"test",
#     #                                                     # "options string": "NOSTANDARD;SCINOTAT;Kmax=1;Average=1",
#     #                                                     "options string": "NOSTANDARD;SCINOTAT;Kmax=1",
#     #                                                     "pollutants_list":['CO2', 'CO', 'HC', 'NOx', 'SOx', 'PM10'],
#     #                                                     "output_path":work_dir,
#     #                                                     "receptors":csv_gdf}
#     #                        )
#     #
#     # # output_module_aus = DispersionModuleManager().getModuleByName("AUSTAL2000")\
#     # #     ({"output_path": "C:\Users\stav\.qgis2\python\plugins\open_alaqs\example\ATM4E\A2K\1"})
#
#     # timeit.timeit(ec.run(source_names=[]))
#     ec.run(source_names=[])
#
#     et_ = time.time()
#     # fix_print_with_import
#     print("Time elapsed: %s"%(et_-st_))
#
#     # # st_ = time.time()
#
#     import pandas as pd
#     import geopandas as gpd
#     # import datetime
#     # # from tools import Spatial
#     # from shapely.geometry import Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon
#     # # import matplotlib.pyplot as plt
#     import matplotlib
#     matplotlib.use('Qt5Agg')
#     import matplotlib.pyplot as plt
#     plt.ion()
#
#     # # import mplleaflet
#     # # from descartes import PolygonPatch
#     # # from tools.Spatial import getRelativeHeightInCell
#     from shapely.ops import unary_union
#
#
#     def calculate_emissions_per_grid_cell(edf_row):
#         geom = edf_row.geometry
#
#         EmissionValue = edf_row.emissions
#
#         cells = matched_cells_2D[matched_cells_2D.intersection(geom).is_empty == False]
#
#         if not cells.empty:
#             if geom.type == 'LineString':
#                 cells.loc[cells.index, 'Emission'] = EmissionValue * cells.intersection(geom).length / geom.length
#             elif geom.type == 'Point':
#                 cells.loc[cells.index, 'Emission'] = EmissionValue / cells.shape[0]
#             elif geom.type == 'Polygon':
#                 cells.loc[cells.index, 'Emission'] = EmissionValue * cells.intersection(geom).area / geom.area
#             elif geom.type == 'MultiPolygon':
#                 # print("EmissionValue %s"%EmissionValue)
#                 fig, ax = plt.subplots()
#                 matched_cells_2D.plot(ax=ax, column='Emission', cmap='jet', linewidth=0.5, alpha=0.5, legend=True)
#                 gpd.GeoSeries(geom).plot(ax=ax, color='r')
#
#                 try:
#                     tot_ems = 0
#                     for mp_ in geom:
#                         tot_ems += ((EmissionValue/len(geom)) * (cells.intersection(mp_).area / mp_.area)).sum()
#
#                     cells.loc[cells.index, 'Emission'] = tot_ems
#
#                 except Exception as exc:
#                     print(exc)
#                     print(mp_)
#                     gpd.GeoSeries(mp_).plot(ax=ax, color='r')
#
#             else:
#                 pass
#
#             if cells.Emission.sum() > 0:
#                 matched_cells_2D.loc[cells.index, 'Emission'] += cells["Emission"]
#
#
#
#
#     pollutant__ = "NOx"
#     # grid3D = ec.get3DGrid().get_df_from_3d_grid_cells()
#     # grid3D = grid3D.assign(Emission=pd.Series(0, index=grid3D.index))
#     # grid2D = grid3D[grid3D.zmin==0]
#     grid2D = ec.get3DGrid().get_df_from_2d_grid_cells()
#     grid2D = grid2D.assign(Emission=pd.Series(0, index=grid2D.index))
#
#     timeval_shapes = []
#     for timeval, rows in ec.getEmissions().items():
#
#         geometries_in_timeval = [em_.getGeometry() for (source, emissions) in rows for em_ in emissions if em_.getValue(pollutant__, unit="kg")[0]>0]
#         emissions_in_timeval = [em_.getValue(pollutant__, unit="kg")[0] for (source, emissions) in rows for em_ in emissions if em_.getValue(pollutant__, unit="kg")[0]>0]
#         sources_in_timeval = [source.getName() for (source, emissions) in rows for em_ in emissions if em_.getValue(pollutant__, unit="kg")[0]>0]
#         #
#         edf = gpd.GeoDataFrame(index=range(0, len(geometries_in_timeval)), columns=["timeval", "sources", "emissions", "geometry"])
#         edf.loc[0:len(geometries_in_timeval), "geometry"] = geometries_in_timeval
#         edf.loc[0:len(geometries_in_timeval), 'sources'] = sources_in_timeval
#         edf.loc[0:len(geometries_in_timeval), 'emissions'] = emissions_in_timeval
#         edf.loc[0:len(geometries_in_timeval), "timeval"] = timeval
#
#         # for xq, yq take unary_union(geometries_in_timeval).bounds[0], unary_union(geometries_in_timeval).bounds[1]
#         # or edf.geometry.total_bounds[0], edf.geometry.total_bounds[1]
#         # unary_union(geometries_in_timeval)
#
#         #ToDo: combine all geometries for this timeval and run calculate_emissions_per_grid_cell once?
#         allshapes = unary_union(geometries_in_timeval)
#         timeval_shapes.append(allshapes)
#
#         edf.apply(calculate_emissions_per_grid_cell, axis=1)
#
#         # fig, ax = plt.subplots()
#         # gpd.GeoSeries(allshapes).plot(ax=ax, color='k')
#         # gpd.GeoSeries(allshapes.envelope).plot(ax=ax, color='r', alpha=0.1)
#         # ax.plot(gpd.GeoSeries(allshapes).bounds.minx.iloc[0],
#         #         gpd.GeoSeries(allshapes).bounds.miny.iloc[0],
#         #         'kx')
#         # ax.plot(gpd.GeoSeries(allshapes).bounds.maxx.iloc[0],
#         #         gpd.GeoSeries(allshapes).bounds.maxy.iloc[0],
#         #         'kx')
#         # ax.set_title( str(timeval) )
#         #
#         # matched_cells_2D = grid2D[grid2D.intersects(allshapes) == True]
#         # matched_cells_2D.plot(ax=ax, column='Emission', cmap='jet', linewidth=0.5, alpha=0.5, legend=True)
#         ## matched_cells_2D.plot(ax=ax, column='Emission', cmap='jet', edgecolor='blue', facecolor='w', linewidth=0.5, alpha=0.5)
#
#         break
#
#
#
#
#
#         fig, ax = plt.subplots()
#
#         # for (source_, emissions__) in result:
#         for (source, emissions) in rows:
#             # print("---------")
#             # print(source.getName())
#             for em_ in emissions:
#                 # emissions_.getValue(self._pollutant, unit="kg")[0]
#                 EmissionValue = em_.getValue(pollutant__, unit="kg")[0]
#                 # print(EmissionValue)
#                 if EmissionValue == 0:
#                     print("No emissions found for %s"%source.getName())
#                     continue
#
#                 geom = em_.getGeometry()
#                 print((source.getName(), EmissionValue, geom.wkt))
#                 # ax.set_title(source.getName())
#                 # gpd.GeoSeries(geom).plot(ax=ax, color='r', alpha=0.25)
#
#                 # try:
#                 #     geom = em_.getGeometry()
#                 #     # fix_print_with_import
#                 #     # print((geom, EmissionValue))
#                 #     if not geom.is_valid:
#                 #         geom=unary_union(geom)
#                 #
#                 #     # some convenience variables
#                 #     isPoint_element_ = bool(isinstance(em_.getGeometry(), Point)) # bool("POINT" in emissions_.getGeometryText())
#                 #     isLine_element_ = bool(isinstance(em_.getGeometry(), LineString))
#                 #     isPolygon_element_ = bool(isinstance(em_.getGeometry(), Polygon))
#                 #     isMultiPolygon_element_ = bool(isinstance(em_.getGeometry(), MultiPolygon))
#                 #
#                 #     # if geom.has_z:
#                 #     #     if isLine_element_:
#                 #     #         coords = [Point(cc) for cc in geom._get_coords()]
#                 #     #         z_dim = [c_.z for c_ in coords]
#                 #     #     elif isPoint_element_:
#                 #     #         z_dim = [geom.z, geom.z]
#                 #     #     elif isPolygon_element_:
#                 #     #         coords = [Point(cc) for cc in geom.exterior._get_coords()]
#                 #     #         z_dim = [c_.z for c_ in coords]
#                 #     #     elif isMultiPolygon_element_:
#                 #     #         coords = [Point(cc) for gm in geom for cc in gm.exterior._get_coords()]
#                 #     #         z_dim = [c_.z for c_ in coords]
#                 #     #     else:
#                 #     #         print(em_.getGeometry())
#                 #     #         # ToDo: add other MultiGeos...
#                 #     #         print("Geometry %s not recognised"%em_.getGeometry())
#                 #     #         continue
#                 #
#                 #     # z_min = min(z_dim)
#                 #     # z_max = max(z_dim)
#                 #
#                 #     # 2D grid
#                 #     matched_cells_2D = grid2D[grid2D.intersects(geom)==True]
#                 #
#                 #     # Calculate Emissions' horizontal distribution
#                 #     if isLine_element_:
#                 #         # ToDo: Add if
#                 #         matched_cells_2D.loc[matched_cells_2D.index, "Emission"] = \
#                 #             EmissionValue * matched_cells_2D.intersection(geom).length / geom.length
#                 #     elif isPoint_element_:
#                 #         # ToDo: Add if
#                 #         matched_cells_2D.loc[matched_cells_2D.index, "Emission"] = EmissionValue / len(matched_cells_2D)
#                 #     elif isPolygon_element_ or isMultiPolygon_element_:
#                 #         matched_cells_2D.loc[matched_cells_2D.index, "Emission"] = \
#                 #             EmissionValue * matched_cells_2D.intersection(geom).area / geom.area
#                 #
#                 #     grid2D.loc[matched_cells_2D.index, "Emission"] += matched_cells_2D["Emission"]
#                 #
#                 # except Exception as exc_:
#                 #     print(exc_)
#                 #     continue
#         #
#         # break
#         #
#         # # # grid2D.loc[matched_cells_2D.index].plot().plot(ax=ax, column="Emission", legend=True, cmap='hot_r')
#         # # grid2D.plot(ax=ax, column="Emission", legend=True, cmap='hot_r')
#         # # ax.set_title("Source: %s "%(source.getName()))
#         # # plt.savefig("%s.png" % (source.getName().translate({ord(" "): "_", ord(":"): "_", ord("-"): "_"})), dpi=300, bbox_inches="tight")
#
#     et_ = time.time()
#     print("Time elapsed: %s"%(et_-st_))
#     #
#     # (minx, miny, maxx, maxy) = grid2D[grid2D['Emission'] > 0].total_bounds
#     #
#     # ll_corner = Point(minx, miny)
#     # lr_corner = Point(maxx, miny)
#     # rr_corner = Point(maxx, maxy)
#     # rl_corner = Point(minx, maxy)
#     # pointList = [ll_corner, lr_corner, rr_corner, rl_corner]
#     # poly = Polygon([[p.x, p.y] for p in pointList])
#     #
#     # # reduced grid - could this be used for A2K ?
#     # # grid2D[grid2D.intersects(poly) == True]
#     #
#     # # fig, ax = plt.subplots()
#     # # grid2D[grid2D['Emission'] > 0].plot(ax=ax, column="Emission", legend=True, cmap='jet')
#     # # ax.plot(ll_corner.x, ll_corner.y, 'r*')
#     # # ax.plot(lr_corner.x, lr_corner.y, 'r*')
#     # # ax.plot(rr_corner.x, rr_corner.y, 'r*')
#     # # ax.plot(rl_corner.x, rl_corner.y, 'r*')
#     #
#     # # matched_cells_2D.plot(ax=ax, column="Emission", legend=True, cmap='hot')
#     # # plt.show()
#     # # grid2D.to_excel("EmissionCalculation_%s_%s.xlsx"%(pollutant__, datetime.datetime.now().strftime("%Y_%m_%d_%H_%M")), index=False)
#     # # app.quit()
#     # # sys.exit(app.exec_())
#     #
#     # #             # 3D grid
#     # #             matched_cells_3D = grid3D[(grid3D.intersects(geom) == True)&(grid3D.zmax > z_min)&(grid3D.zmin <= z_max)]
#     # #             matched_cells_3D = matched_cells_3D.assign(z_efficiency=pd.Series(0, index=matched_cells_3D.index))
#     # #
#     # #             for cell2D in matched_cells_2D.index:
#     # #                 cell_geo = matched_cells_2D.loc[cell2D, "geometry"]
#     # #                 cell_em = matched_cells_2D.loc[cell2D, "Emission"]
#     # #
#     # #                 cells3D = matched_cells_3D[matched_cells_3D.geometry == cell_geo]
#     # #                 # Calculate coefficients for the vertical distribution of emissions
#     # #                 cells3D.loc[cells3D.index, "z_efficiency"] = \
#     # #                     matched_cells_3D[["zmin", "zmax"]].apply(getRelativeHeightInCell, args = (z_min,z_max), axis=1)
#     # #                 cells3D.loc[cells3D.index, "Emission"] = cell_em * cells3D["z_efficiency"]
#     # #
#     # #                 grid3D.loc[cells3D.index, "Emission"] += cells3D["Emission"]
#     # #
#     # #             # break
#     # #         # break
#     # #     # break
#     # #
#     # #
#     # #     # for k, grp in grid3D[grid3D.Emission > 0].groupby("zmin"):
#     # #     #     fig, ax = plt.subplots()
#     # #     #     grp.plot(ax=ax, column="Emission", legend=True, cmap='hot_r')
#     # #     #     ax.set_title("Altitude: %s-%s"%(grp.zmin.iloc[0], grp.zmax.iloc[0]))
#     # #     #     plt.savefig("grid3D_%s.png"%(k), dpi=300, bbox_inches="tight")
#     # #     #
#     # #     #     break
#     # #
#     # #     total_emissions_ = sum([sum(emissions) for (source, emissions) in rows])
#     # #     # print(total_emissions_)
#     #
#     # #     print "Timeval: %s \n Total '%s' emissions (all movs): %s"%(timeval, pollutant__, total_emissions_.getValue(pollutant__))
#     # # #
#     #
#     # #     for (source, emissions) in rows:
#     # #         _err_ = 0
#     # #         sources_ = source.getName()
#     # #
#     # #         if not emissions:
#     # #             print "Empty emissions for %s"%source.getName()
#     # #             _err_ = 1
#     # #             break
#     # #         if _err_ == 1:
#     # #             break
#     # #
#     # #         for em_ in emissions:
#     # #             if not hasattr(em_, 'getGeometryText'):
#     # #                 print "Source '%s' has no GeometryText!" % (em_)
#     # #                 break
#     # #             print "source.getName(): %s" % source.getName()
#     # #             print "\t GeometryText(): %s" % em_.getGeometryText()
#     # #             print em_.getValue(pollutant__)
#     # #             # print "\t Vertical Extent(): %s" % em_.getVerticalExtent()
#     # #
#     # #         total_emissions_per_mov = sum(emissions)
#     # #         # print "Timeval: %s \n Total '%s' emissions (all movs): %s"%(timeval, pollutant__, total_emissions_per_mov.getValue(pollutant__))
#     # #         # print "------------------"
#     # #     break
#     #
#     #
#     # # if path_to_database and DispersionModuleManager().hasModule("AUSTAL2000"):
#     # #     # print "----------------------------------"
#     # #     logger.info("Writing AUSTAL2000 input files")
#     # #     output_module_aus = DispersionModuleManager().getModuleByName("AUSTAL2000")\
#     # #          ({"enable": True, "add title":'TEST',"pollutant":'NOx', "quality level": 1, "options string":"SCINOTAT",\
#     # #             "index sequence": "k+,j-,i+", "grid":ec.get3DGrid()})
#     # #          # ({"enable": True, "add title":'"test"', "quality level": 1, "options string":"NOSTANDARD;SCINOTAT;Kmax=1",\
#     # #
#     # #     st_ = time.time()
#     # #     output_module_aus.beginJob()
#     # #     et_ = time.time()
#     # #     print("output_module_aus.beginJob - Time elapsed: %s" % (et_ - st_))
#     # #
#     # #     st_ = time.time()
#     # #     for (start_, end_) in ec.getTimeSeries():
#     # #         for timeval, rows in ec.getEmissions().items():
#     # #             # print(timeval," / ",len(rows))
#     # #             ambient_condition = ec.getAmbientCondition(start_.getTime())
#     # #             output_module_aus.process(start_, end_, timeval, rows, ambient_conditions=ambient_condition)
#     # #     et_ = time.time()
#     # #     print("output_module_aus.process - Time elapsed: %s" % (et_ - st_))
#     # #
#     # #     st_ = time.time()
#     # #     output_module_aus.endJob()
#     # #     et_ = time.time()
#     # #     print("output_module_aus.endJob() - Time elapsed: %s" % (et_ - st_))
#     #
#     # app.quit()
#     # # sys.exit(app.exec_())
#     #
#     # # # # work_dir = os.path.join("..","example/ATM4E/A2K/D%s-L%s"%(str(tr_).zfill(2),str(nv_).zfill(2)))
#     # # # if not os.path.isdir(work_dir):
#     # # #     # raise Exception("File %s doesn't exist !")
#     # # #     print "File %s doesn't exist !"
#     # # #
#     # # # ToDo: Get stdout, stderr, the "real" status code, better error handling, etc...)
#     # # opt_ = "D"
#     # # cmd = "%s -%s %s"%(austal_, opt_, work_dir)
#     # # p = Popen(cmd, stdout=PIPE, stderr=PIPE)
#     # #
#     # # while True:
#     # #     out = p.stdout.read(1)
#     # #     if out == '' and p.poll() != None:
#     # #         break
#     # #     if out != '':
#     # #         sys.stdout.write(out)
#     # #         sys.stdout.flush()
#     # #
#     # # stdout, stderr = p.communicate()
#     # # errcode = p.returncode
#     # # if errcode == 0:
#     # #     print stdout.splitlines()
#     # # else:
#     # #     raise Exception("Austal2K errorcode: %s"%errcode)
#     # # print "-------------------------------------"
#     # #
#     # # if path_to_database and work_dir and OutputModuleManager().hasModule("QGISVectorLayerDispersionModule"):
#     # #
#     # #     vector_layer_config_ = {
#     # #         "concentration_path":work_dir,
#     # #         "pollutant": 'NOx',
#     # #         "3DVisualization":True,
#     # #         "addTitleToLayer": False,
#     # #         "isPolygon" : True,
#     # #         "grid":ec.get3DGrid(),
#     # #     }
#     # #     # print vector_layer_config_
#     # #     VectorLayerOutputModule = OutputModuleManager().getModuleByName("QGISVectorLayerDispersionModule")(values_dict=vector_layer_config_)
#     # #
#     # #     VectorLayerOutputModule.beginJob()
#     # #
#     # #     VectorLayerOutputModule.process()
#     # #     # for timeval, rows in ec.getEmissions().iteritems():
#     # #     #     VectorLayerOutputModule.process(timeval, rows)
#     # #     conc_data = VectorLayerOutputModule.endJob()
#     #
#     # # sys.exit(app.exec_())
#     #
#     #     # # if path_to_database and OutputModuleManager().hasModule("CSVOutputModule"):
#     # # #      # csv_file = os.path.join("..", "example", "caepport_out.csv")
#     # # #      print "Writing results to CSV file '%s'"%path_to_database
#     # # #      output_module_csv = OutputModuleManager().getModuleByName("CSVOutputModule")({"output_path" : path_to_database, "detailed_output":True})
#     # # #      output_module_csv.beginJob()
#     # # #      for timeval, rows in ec.getEmissions().iteritems():
#     # # #          output_module_csv.process(timeval, rows)
#     # # #      output_module_csv.endJob()
#     #
#     # # table_config = {}
#     # # if OutputModuleManager().hasModule("TableViewWidgetOutputModule"):
#     # #      output_module_ = OutputModuleManager().getModuleByName("TableViewWidgetOutputModule")(values_dict=table_config)
#     # #      output_module_.beginJob()
#     # #      for timeval, rows in ec.getEmissions().iteritems():
#     # #          output_module_.process(timeval, rows)
#     # #      widget = output_module_.endJob()
#     # #      widget.show()
#     # #
#     #
#     #
#     # # if path_to_database and OutputModuleManager().hasModule("SQLiteOutputModule"):
#     # #     sql_file = os.path.join("..", "example", "caepport_out.sql")
#     # #     print "Writing results to SQLite file '%s'"%sql_file
#     # #     output_module_ = OutputModuleManager().getModuleByName("SQLiteOutputModule")({"output_path" : path_to_database, "detailed_output":True})
#     # #     output_module_.beginJob()
#     # #     for timeval, rows in ec.getEmissions().iteritems():
#     # #         output_module_.process(timeval, rows)
#     # #     output_module_.endJob()
#     #    # #    # #    # #    # #    # #    # #    # #    # #    # #
#     #
#     # # plot_config = {
#     # #         "title": "Total emissions of '%s' [kg]" % (pollutant),
#     # #         "x_title": "Time [hh:mm:ss]",
#     # #         "y_title": "Emission of 'test'",
#     # #         "options": "o",
#     # #         "parent" : None,
#     # #         "pollutant" : pollutant
#     # # }
#     # # if OutputModuleManager().hasModule("TimeSeriesWidgetOutputModule"):
#     # #     output_module_ = OutputModuleManager().getModuleByName("TimeSeriesWidgetOutputModule")(values_dict=plot_config)
#     # #
#     # #     output_module_.beginJob()
#     # #     for timeval, rows in ec.getEmissions().iteritems():
#     # #         output_module_.process(timeval, rows)
#     # #     widget = output_module_.endJob()
#     # #     if not widget is None:
#     # #         widget.show()
#     # #     sys.exit(app.exec_())
#     # # #    # #    # #    # #    # #    # #    # #    # #    # #    # #
#     #
#     # # pollutant = "NOx"
#     # # emission_vector_layer_config_ = {
#     # #     "database_path" : path_to_database,
#     # #     "pollutant": pollutant,
#     # #     "3DVisualization":True,
#     # #     "addTitleToLayer": False,
#     # #     "isPolygon" : True,
#     # #     "grid":ec.get3DGrid(),
#     # # }
#     # # if OutputModuleManager().hasModule("EmissionsQGISVectorLayerOutputModule"):
#     # #     VectorLayerOutputModule = \
#     # #         OutputModuleManager().getModuleByName("EmissionsQGISVectorLayerOutputModule")(values_dict=emission_vector_layer_config_)
#     # #     VectorLayerOutputModule.beginJob()
#     # #     for timeval, rows in ec.getEmissions().iteritems():
#     # #         VectorLayerOutputModule.process(timeval, rows)
#     # #     VectorLayerOutputModule.endJob()
#     # # sys.exit(app.exec_())
#     #
#     # # from subprocess import Popen, PIPE, STDOUT, call
#     # #
#     # # # austal_ = str(QtGui.QFileDialog.getOpenFileName(None, "Select AUSTAL2000 file", "", "austal2000.exe"))
#     # # austal_ = 'C:/Users/stav/.qgis2/python/plugins/open_alaqs/example/a2k-utils-2016-01-13/a2k/austal2000.exe'
#     # # # work_dir = str(QtGui.QFileDialog.getExistingDirectory(None, "Select Working directory"))
#     # #
#     # #     work_dir = os.path.join("..","example/ATM4E/A2K/D%s-L%s"%(str(tr_).zfill(2),str(nv_).zfill(2)))
#     # #     if not os.path.isdir(work_dir):
#     # #         # raise Exception("File %s doesn't exist !")
#     # #         print "File %s doesn't exist !"
#     # #         continue
#     # #
#     # #     # ToDo: Get stdout, stderr, the "real" status code, better error handling, etc...)
#     # #     opt_ = "D"
#     # #     cmd = "%s -%s %s"%(austal_, opt_, work_dir)
#     # #     p = Popen(cmd, stdout=PIPE, stderr=PIPE)
#     # #
#     # #     while True:
#     # #         out = p.stdout.read(1)
#     # #         if out == '' and p.poll() != None:
#     # #             break
#     # #         if out != '':
#     # #             sys.stdout.write(out)
#     # #             sys.stdout.flush()
#     # #
#     # #     stdout, stderr = p.communicate()
#     # #     errcode = p.returncode
#     # #     # if errcode == 0:
#     # #     #     print stdout.splitlines()
#     # #     # else:
#     # #     #     raise Exception("Austal2K errorcode: %s"%errcode)
