from collections import OrderedDict

import pandas as pd
from qgis.core import Qgis
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

        self._total_emissions = 0.0

        self._threshold_to_create_a_data_point = conversion.convertToFloat(
            values_dict.get("Threshold") or values_dict.get("threshold") or 0.0001
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

    def beginJob(self):
        # prepare the attributes of each point of the vector layer
        self._total_emissions = 0.0
        self._header = [(self._pollutant, "double")]
        self._data = self._grid.get_df_from_2d_grid_cells()
        self._data = self._data.assign(Q=pd.Series(0, index=self._data.index))

    def process(self, timeval, result, **kwargs):
        # result is of format [(Source, Emission)]

        if self.getGrid() is None:
            raise Exception("No 3DGrid found.")

        # filter by configured time
        if self._time_start and self._time_end:
            if not (timeval >= self._time_start and timeval < self._time_end):
                return True

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
                    matched_cells_2D = self._data[
                        self._data.intersects(geom) == True  # noqa: E712
                    ]

                    # Calculate Emissions' horizontal distribution
                    if isinstance(geom, Point):
                        value = EmissionValue / len(matched_cells_2D)
                    elif isinstance(geom, (LineString, MultiLineString)):
                        value = (
                            EmissionValue
                            * matched_cells_2D.intersection(geom).length
                            / geom.length
                        )
                    elif isinstance(geom, (Polygon, MultiPolygon)):
                        value = (
                            EmissionValue
                            * matched_cells_2D.intersection(geom).area
                            / geom.area
                        )
                    else:
                        raise NotImplementedError(
                            "Usupported geometry type: {}".format(geom.__class__.name)
                        )

                    matched_cells_2D.loc[matched_cells_2D.index, "Q"] = value

                    self._data.loc[matched_cells_2D.index, "Q"] += matched_cells_2D["Q"]
                except Exception as exc_:
                    logger.error(exc_)
                    continue

    def endJob(self) -> None:
        if self._data.empty:
            return None

        geometry_type = (
            Qgis.GeometryType.Polygon if self._isPolygon else Qgis.GeometryType.Point
        )
        layer_wrapper = ContourPlotVectorLayer(
            layer_name=self._layer_name + self._layer_name_suffix,
            geometry_type=geometry_type,
            enable_labels=self._enable_labels,
            field_name=self._pollutant,
        )
        layer_wrapper.addHeader(self._header)
        # TODO pre-OPENGIS.ch: replace with data from grid3D, `contour_layer.addData(self._grid3D[self._grid3D.Emission>0])``
        layer_wrapper.addData(self._data)
        layer_wrapper.setColorGradientRenderer(
            classes_count=7,
        )

        return layer_wrapper.layer
