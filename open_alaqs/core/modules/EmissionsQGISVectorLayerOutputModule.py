import math
from collections import OrderedDict

import pandas as pd
from qgis.gui import QgsDoubleSpinBox
from qgis.PyQt import QtWidgets
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.plotting.ContourPlotVectorLayer import ContourPlotVectorLayer
from open_alaqs.core.tools import conversion, spatial

pd.set_option("chained_assignment", None)

logger = get_logger(__name__)


class EmissionsQGISVectorLayerOutputModule(OutputModule):
    """
    Module to that returns a QGIS vector layer with representation of emissions.
    """

    @staticmethod
    def getModuleName():
        return "EmissionsQGISVectorLayerOutputModule"

    @staticmethod
    def getModuleDisplayName():
        return "Vector Layer"

    def __init__(self, values_dict={}):
        OutputModule.__init__(self, values_dict)

        # Layer configuration
        self._options = values_dict["options"] if "options" in values_dict else ""

        # Results analysis
        self._time_start = (
            conversion.convertStringToDateTime(values_dict["Start (incl.)"])
            if "Start (incl.)" in values_dict
            else ""
        )
        self._time_end = (
            conversion.convertStringToDateTime(values_dict["End (incl.)"])
            if "End (incl.)" in values_dict
            else ""
        )
        self._pollutant = (
            values_dict["pollutant"] if "pollutant" in values_dict else None
        )

        self._layer_name = ContourPlotVectorLayer.LAYER_NAME
        self._layer_name_suffix = (
            values_dict["name_suffix"] if "name_suffix" in values_dict else ""
        )
        self._3DVisualization = (
            values_dict["3DVisualization"]
            if "3DVisualization" in values_dict
            else False
        )
        self._isPolygon = values_dict.get(
            "Use Polygons Instead of Points",
            values_dict.get("Shape of Marker: Polygons instead of Points", True),
        )
        self._enable_labels = values_dict.get(
            "Add Labels with Values to Cell Boxes",
            values_dict.get("Add labels with values to cell boxes", False),
        )

        self._contour_layer = None

        self._total_emissions = 0.0

        self._threshold_to_create_a_data_point = conversion.convertToFloat(
            values_dict.get("Threshold", values_dict.get("threshold", 0.0001))
        )

        self._grid = (
            values_dict["grid"] if "grid" in values_dict else None
        )  # ec.get3DGrid()

        self.setConfigurationWidget(
            OrderedDict(
                [
                    ("Projection", QtWidgets.QLabel),
                    ("Threshold", QgsDoubleSpinBox),
                    ("Use Polygons Instead of Points", QtWidgets.QCheckBox),
                    ("Add Labels with Values to Cell Boxes", QtWidgets.QCheckBox),
                    ("Add Title", QtWidgets.QCheckBox),
                ]
            )
        )

        widget = self._configuration_widget.getSettings()["Threshold"]
        widget.setDecimals(4)
        widget.setMinimum(0.0)
        widget.setMaximum(999.9999)

        self.getConfigurationWidget().initValues(
            {
                "Use Polygons Instead of Points": True,
                "Add Labels with Values to Cell Boxes": False,
                "Projection": "EPSG:3857",
                "Threshold": 0.0001,
                "Add Title": True,
            }
        )

        self._header = []

    def getGrid(self):
        return self._grid

    def setGrid(self, var):
        self._grid = var

    def getMinHeight(self):
        return self._min_height_in_m

    def setMinHeight(self, var, inFeet=False):
        if inFeet:
            self._min_height_in_m = conversion.convertFeetToMeters(var)
        else:
            self._min_height_in_m = var

    def getMaxHeight(self):
        return self._max_height_in_m

    def setMaxHeight(self, var, inFeet=False):
        if inFeet:
            self._max_height_in_m = conversion.convertFeetToMeters(var)
        else:
            self._max_height_in_m = var

    def getThresholdToCreateDataPoint(self):
        return self._threshold_to_create_a_data_point

    def setThresholdToCreateDataPoint(self, var):
        self._threshold_to_create_a_data_point = var

    def getTimeStart(self):
        return self._time_start

    def getTimeEnd(self):
        return self._time_end

    def getPollutant(self):
        return self._pollutant

    def getContourLayer(self):
        return self._contour_layer

    def getTotalEmissions(self):
        return self._total_emissions

    def addToTotalEmissions(self, var):
        self._total_emissions += var

    def getDataPoint(self, x_, y_, z_, isPolygon, grid_):
        data_point_ = {"coordinates": {"x": x_, "y": y_, "z": z_}}
        if isPolygon:
            data_point_.update(
                {
                    "coordinates": {
                        "x_min": x_ - grid_.getResolutionX() / 2.0,
                        "x_max": x_ + grid_.getResolutionX() / 2.0,
                        "y_min": y_ - grid_.getResolutionY() / 2.0,
                        "y_max": y_ + grid_.getResolutionY() / 2.0,
                        "z_min": z_ - grid_.getResolutionZ() / 2.0,
                        "z_max": z_ + grid_.getResolutionZ() / 2.0,
                    }
                }
            )
        return data_point_

    def getBoundingBox(self, geometry_wkt):
        bbox = spatial.getBoundingBox(geometry_wkt)
        return bbox

    def getCellBox(self, x_, y_, z_, grid_):
        cell_bbox = {
            "x_min": x_ - grid_.getResolutionX() / 2.0,
            "x_max": x_ + grid_.getResolutionX() / 2.0,
            "y_min": y_ - grid_.getResolutionY() / 2.0,
            "y_max": y_ + grid_.getResolutionY() / 2.0,
            "z_min": z_ - grid_.getResolutionZ() / 2.0,
            "z_max": z_ + grid_.getResolutionZ() / 2.0,
        }
        return cell_bbox

    # def getEfficiencyXY(self, emissions_geometry_wkt, cell_bbox, isPoint, isLine, isPolygon):
    #     #efficiency = relative area of geometry in the cell box
    #     efficiency_ = 0.
    #     if isPoint or isPolygon:
    #         efficiency_ = Spatial.getRelativeAreaInBoundingBox(emissions_geometry_wkt, cell_bbox)
    #     elif isLine:
    #         #get relative length (X,Y) in bounding box (assumes constant speed)
    #         efficiency_ = Spatial.getRelativeLengthXYInBoundingBox(emissions_geometry_wkt, cell_bbox)
    #     return efficiency_
    #
    # def getEfficiencyZ(self, geometry_wkt, z_min, z_max, cell_box, isPoint, isLine, isPolygon):
    #     efficiency_ = 0.
    #     if isPoint:
    #         #points match each cell exactly once
    #         efficiency_ = Spatial.getRelativeHeightInBoundingBox(z_min, z_max, cell_box)
    #     elif isPolygon or isLine:
    #         efficiency_ = Spatial.getRelativeHeightInBoundingBox(z_min, z_max, cell_box)
    #     return efficiency_

    # def ProgressBarWidget(self):
    #     progressbar = QtGui.QProgressDialog("Calculating emissions in grid cell", "Cancel", 0, 99)
    #     progressbar.setWindowTitle("EmissionsQGISVectorLayerOutputModule")
    #     progressbar.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
    #     progressbar.setWindowModality(QtCore.Qt.WindowModal)
    #     progressbar.setAutoReset(True)
    #     progressbar.setAutoClose(True)
    #     progressbar.resize(350, 100)
    #     progressbar.show()
    #     return progressbar

    def beginJob(self):
        # prepare the attributes of each point of the vector layer
        # self._data = {}
        self._total_emissions = 0.0
        self._header = [(self._pollutant, "double")]
        # self._data = pd.DataFrame()

        self._data = self._grid.get_df_from_2d_grid_cells()
        self._data = self._data.assign(Q=pd.Series(0, index=self._data.index))

        # self._data = self._grid.get_df_from_3d_grid_cells()
        # self._grid3D = self._grid3D.assign(Emission=pd.Series(0, index=self._grid3D.index))
        # self._grid3D = self._grid3D.assign(EmissionSource=pd.Series("", index=self._grid3D.index))
        # self._grid2D = self._grid3D[self._grid3D.zmin == 0]
        # self._grid2D = self._grid2D.assign(Emission=pd.Series(0, index=self._grid2D.index))

        # self._data = self._data[self._data.zmin == 0]

    def process(self, timeval, result, **kwargs):
        # result is of format [(Source, Emission)]

        if self.getGrid() is None:
            raise Exception("No 3DGrid found.")

        # filter by configured time
        if self._time_start and self._time_end:
            if not (timeval >= self._time_start and timeval < self._time_end):
                return True

        # total_emissions_ = sum([sum(emissions_) for (source, emissions_) in result])

        # Details of the projection
        # EPSG_id_source=3857
        # EPSG_id_target=4326

        # emission_value_list = []
        self._all_matched_cells = []

        # loop over all emissions and append one data point for every grid cell

        for (source_, emissions__) in result:
            for emissions_ in emissions__:

                if emissions_.getGeometryText() is None:
                    logger.error(
                        "Did not find geometry for emissions '%s'. Skipping an emission of source '%s'"
                        % (str(emissions_), str(source_.getName()))
                    )
                    continue

                EmissionValue = emissions_.getValue(self._pollutant, unit="kg")[0]
                if EmissionValue == 0:
                    continue

                try:
                    geom = emissions_.getGeometry()

                    # some convenience variables
                    isPoint_element_ = bool(
                        isinstance(emissions_.getGeometry(), Point)
                    )  # bool("POINT" in emissions_.getGeometryText())
                    isLine_element_ = bool(
                        isinstance(emissions_.getGeometry(), LineString)
                    )
                    isMultiLine_element_ = bool(
                        isinstance(emissions_.getGeometry(), MultiLineString)
                    )
                    isPolygon_element_ = bool(
                        isinstance(emissions_.getGeometry(), Polygon)
                    )
                    isMultiPolygon_element_ = bool(
                        isinstance(emissions_.getGeometry(), MultiPolygon)
                    )

                    # if geom.has_z:
                    #     if isLine_element_:
                    #         coords = [Point(cc) for cc in geom._get_coords()]
                    #         z_dim = [c_.z for c_ in coords]
                    #     elif isPoint_element_:
                    #         z_dim = [geom.z, geom.z]
                    #     elif isPolygon_element_:
                    #         coords = [Point(cc) for cc in geom.exterior._get_coords()]
                    #         z_dim = [c_.z for c_ in coords]
                    #     elif isMultiPolygon_element_:
                    #         coords = [Point(cc) for gm in geom for cc in gm.exterior._get_coords()]
                    #         z_dim = [c_.z for c_ in coords]
                    #     else:
                    #         logger.error("Error in Geometry for source %s"%str(source_.getName()))
                    #         logger.error("Geometry %s not recognised"%emissions_.getGeometry())
                    #         continue

                    # z_min = min(z_dim)
                    # z_max = max(z_dim)

                    # logger.info(str(source_.getName()))
                    # logger.info(EmissionValue)
                    # logger.info(z_dim)

                    # 2D grid
                    # ToDo: Add warning if geom extends beyond grid
                    # matched_cells_2D = self._grid2D[self._grid2D.intersects(geom)==True]
                    matched_cells_2D = self._data[
                        self._data.intersects(geom) == True  # noqa: E712
                    ]

                    # Calculate Emissions' horizontal distribution
                    if isLine_element_:
                        # ToDo: Add if
                        matched_cells_2D.loc[matched_cells_2D.index, "Q"] = (
                            EmissionValue
                            * matched_cells_2D.intersection(geom).length
                            / geom.length
                        )
                    elif isMultiLine_element_:
                        matched_cells_2D.loc[matched_cells_2D.index, "Q"] = (
                            EmissionValue
                            * matched_cells_2D.intersection(geom).length
                            / geom.length
                        )
                    elif isPoint_element_:
                        # ToDo: Add if
                        matched_cells_2D.loc[
                            matched_cells_2D.index, "Q"
                        ] = EmissionValue / len(matched_cells_2D)
                    elif isPolygon_element_ or isMultiPolygon_element_:
                        matched_cells_2D.loc[matched_cells_2D.index, "Q"] = (
                            EmissionValue
                            * matched_cells_2D.intersection(geom).area
                            / geom.area
                        )

                    # if matched_cells_2D["Emission"].sum() < EmissionValue:
                    #     # repls = (':', '_'), ('-', '_'), (' ', '_')
                    #     src_ = str(source_.getName())
                    #     # logger.warning("Geometry of %s out of bounds, domain too small?"%reduce(lambda a, kv: a.replace(*kv), repls, src_))
                    #     logger.warning("Geometry %s out of bounds"%(geom))

                    # if isLine_element_:
                    #     self._ax.plot(geom.xy[0], geom.xy[1], "r")
                    # elif isPoint_element_:
                    #     self._ax.plot(geom.x, geom.y, "r*")
                    # elif isPolygon_element_ or isMultiPolygon_element_:
                    #     from descartes import PolygonPatch
                    #     self._ax.add_patch(PolygonPatch(geom, fc="b", ec="k", alpha=0.5, zorder=2))
                    # self._grid2D[(self._grid2D.Emission > 0)].plot(ax=self._ax, column="Emission", legend=False, cmap='hot_r')
                    # plt.savefig("all_sources.png", dpi=300, bbox_inches="tight")

                    # self._grid2D.loc[matched_cells_2D.index, "Emission"] += matched_cells_2D["Emission"]

                    self._data.loc[matched_cells_2D.index, "Q"] += matched_cells_2D["Q"]

                    # if round(matched_cells_2D["Q"].sum(),4) > round(EmissionValue, 4):
                    #     logger.error("Sum (%s) exceeds initial Value (%s) for geom: %s"
                    #                  %(round(matched_cells_2D["Q"].sum(),4), round(EmissionValue, 4), geom))

                    # # 3D grid
                    # matched_cells_3D = self._grid3D[(self._grid3D.intersects(geom) == True)&
                    #                                 (self._grid3D.zmax > z_min)&(self._grid3D.zmin <= z_max)]
                    # matched_cells_3D = matched_cells_3D.assign(z_efficiency=pd.Series(0, index=matched_cells_3D.index))
                    #
                    # for cell2D in matched_cells_2D.index:
                    #     cell_geo = matched_cells_2D.loc[cell2D, "geometry"]
                    #     cell_em = matched_cells_2D.loc[cell2D, "Emission"]
                    #
                    #     cells3D = matched_cells_3D[matched_cells_3D.geometry == cell_geo]
                    #     # Calculate coefficients for the vertical distribution of emissions
                    #     cells3D.loc[cells3D.index, "z_efficiency"] = \
                    #         matched_cells_3D[["zmin", "zmax"]].apply(getRelativeHeightInCell, args = (z_min, z_max), axis=1)
                    #
                    #     cells3D.loc[cells3D.index, "Emission"] = cell_em * cells3D["z_efficiency"]
                    #     self._grid3D.loc[cells3D.index, "Emission"] += cells3D["Emission"]
                    #     # self._grid3D.loc[cells3D.index, "EmissionSource"] = str(source_.getName() + ";") + \
                    #     #                                         self._grid3D.loc[cells3D.index, "EmissionSource"].astype(str)
                except Exception as exc_:
                    logger.error(exc_)
                    continue

        # if self._header and not self._grid3D[self._grid3D.Emission > 0].empty:
        #     self._data = self._grid3D[self._grid3D.Emission>0]

        #             logger.info(cell2D, self._grid3D.loc[cells3D.index, "EmissionSource"])
        # # print("%s emissions for time interval: %s"%(self._pollutant, timeval.strftime("%Y-%m-%d %H")))
        #
        #
        # # fig, ax = plt.subplots()
        # # self._grid3D[(self._grid3D.Emission > 0)&(self._grid3D.zmin == 0)].plot(ax=ax, column="Emission", legend=True, cmap='hot_r')
        # # ax.set_title("%s emissions (z=0) for time interval: %s"%(self._pollutant, timeval.strftime("%Y-%m-%d %H")))
        # # plt.savefig("em3D_z0_%s_%s.png"%(self._pollutant, timeval.strftime("%Y_%m_%d_%H")), dpi=300, bbox_inches="tight")
        # #
        # # fig, ax = plt.subplots()
        # # self._grid2D[(self._grid2D.Emission > 0)].plot(ax=ax, column="Emission", legend=True, cmap='hot_r')
        # # ax.set_title("%s emissions for time interval: %s"%(self._pollutant, timeval.strftime("%Y-%m-%d %H")))
        # # plt.savefig("em2D_z0_%s_%s.png"%(self._pollutant, timeval.strftime("%Y_%m_%d_%H")), dpi=300, bbox_inches="tight")
        #
        #         # # # some convenience variables
        #         # isPoint_element_ = bool(isinstance(emissions_.getGeometry(), Point)) #bool("POINT" in emissions_.getGeometryText())
        #         # isLine_element_ = bool(isinstance(emissions_.getGeometry(), LineString))
        #         # isPolygon_element_ = bool(isinstance(emissions_.getGeometry(), Polygon))
        #         # isMultiPolygon_element_ = bool(isinstance(emissions_.getGeometry(), MultiPolygon))
        #         # #
        #         # # geom = Spatial.ogr.CreateGeometryFromWkt(emissions_.getGeometryText())
        #         # geom = emissions_.getGeometry()
        #         # if geom is None:
        #         #     continue
        #         #
        #         # matched_cells = []
        #         # if isMultiPolygon_element_:
        #         #     MultiPolygonEmissions = conversion.convertToFloat(emissions_.getValue(self._pollutant, unit="kg")[0])\
        #         #                             /conversion.convertToFloat(geom.GetGeometryCount())
        #         #
        #         #     for i in range(0, geom.GetGeometryCount()):
        #         #         g = geom.GetGeometryRef(i)
        #         #
        #         #         bbox = self.getBoundingBox(g.ExportToWkt())
        #         #         # Take into account the effective vertical source extent and shift
        #         #         bbox["z_max"] = bbox["z_max"]+emissions_.getVerticalExtent()['delta_z'] \
        #         #             if "delta_z" in emissions_.getVerticalExtent() else bbox["z_max"]
        #         #         matched_cells = self.getGrid().matchBoundingBoxToCellHashList(bbox, z_as_list=True)
        #         #
        #         #         self.CalculateCellHashEfficiency(MultiPolygonEmissions,
        #         #             g.ExportToWkt(), bbox, matched_cells, isPoint_element_, isLine_element_, isPolygon_element_)
        #         #
        #         # else:
        #         #
        #         #     bbox = self.getBoundingBox(emissions_.getGeometryText())
        #         #
        #         #     if "delta_z" in emissions_.getVerticalExtent() and "delta_z" > 0:
        #         #         bbox["z_max"] = bbox["z_max"] + emissions_.getVerticalExtent()['delta_z']
        #         #
        #         #     matched_cells = self.getGrid().matchBoundingBoxToCellHashList(bbox, z_as_list=True)
        #         #     # if len(matched_cells) > 0:
        #         #     # logger.debug("matched_cells: %s" % matched_cells)
        #         #     # logger.debug("Emissions: %s" % emissions_.getValue(self._pollutant, unit="kg")[0])
        #         #
        #         #     self.CalculateCellHashEfficiency(emissions_.getValue(self._pollutant, unit="kg")[0],
        #         #                                      emissions_.getGeometryText(), bbox, matched_cells,
        #         #                                          isPoint_element_, isLine_element_, isPolygon_element_)

    def endJob(self):
        # if not self._grid2D[self._grid2D["Emission"] > 0].empty:
        #     self._data = self._grid2D[self._grid2D["Emission"]>0]

        # create the layer
        # if self._header and not self._grid3D[self._grid3D.Emission>0].empty:
        if self._header and not self._data.empty:

            # if self._header and self._data:
            # create a new instance of a ContourPlotLayer
            contour_layer = ContourPlotVectorLayer(
                {
                    "isPolygon": self._isPolygon,
                    "Label_enable": self._enable_labels,
                    "fieldname": self._pollutant,
                    "name": self._layer_name,
                    "name_suffix": self._layer_name_suffix,
                }
            )
            contour_layer.addHeader(self._header)
            # ToDo: replace with data from grid3D
            # contour_layer.addData(self._grid3D[self._grid3D.Emission>0])
            contour_layer.addData(self._data)
            contour_layer_min = math.floor(self._data.Q.min())
            contour_layer_max = math.ceil(self._data.Q.max())

            # contour_layer.addData([self._data[k] for k in self._data.keys()])

            # contour_layer_min = math.floor(self._grid3D[self._grid3D.Emission>0].Emission.min())
            # contour_layer_max = math.ceil(self._grid3D[self._grid3D.Emission>0].Emission.max())

            # contour_layer_min = min([self._data[k]["attributes"][self._pollutant] for k in self._data.keys()])
            # contour_layer_max = max([self._data[k]["attributes"][self._pollutant] for k in self._data.keys()])

            contour_layer.setColorGradientRenderer(
                {
                    "numberOfClasses": 7,
                    "color1": "lightGray",
                    "color2": "darkRed",
                    "fieldname": self._pollutant,
                    "minValue": contour_layer_min,
                    "maxValue": contour_layer_max,
                }
            )
            self._contour_layer = contour_layer

            return self._contour_layer.getLayer()

        return None

    #

    # import matplotlib.pyplot as plt
    # from descartes import PolygonPatch
