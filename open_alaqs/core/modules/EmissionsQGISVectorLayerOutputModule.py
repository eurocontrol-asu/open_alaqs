from datetime import datetime
from typing import Any, Optional

import pandas as pd
from qgis.core import QgsVectorLayer
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QVariant
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.plotting.ContourPlotVectorLayer import ContourPlotVectorLayer

pd.set_option("chained_assignment", None)

logger = get_logger(__name__)


class EmissionsQGISVectorLayerOutputModule(OutputModule):
    """
    Module to that returns a QGIS vector layer with representation of emissions.
    """

    settings_schema = {
        "projection": {
            "label": "Projection",
            "widget_type": QtWidgets.QLabel,
            "initial_value": "EPSG:3857",
        },
        "use_centroid_symbol": {
            "label": "Show Centroid Symbols Instead of Polygons",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": False,
        },
        "should_add_labels": {
            "label": "Add Labels with Values to Cell Boxes",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": False,
        },
        "should_add_title": {
            "label": "Add Title",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": True,
        },
    }

    @staticmethod
    def getModuleName():
        return "EmissionsQGISVectorLayerOutputModule"

    @staticmethod
    def getModuleDisplayName():
        return "Vector Layer"

    def __init__(self, values_dict: dict[str, Any]):
        OutputModule.__init__(self, values_dict)

        # Results analysis
        self._time_start = values_dict["start_dt_inclusive"]
        self._time_end = values_dict["end_dt_inclusive"]
        self._pollutant = values_dict["pollutant"]

        self._layer_name = ContourPlotVectorLayer.LAYER_NAME
        self._use_centroid_symbol = values_dict["use_centroid_symbol"]
        self._enable_labels = values_dict["should_add_labels"]

        self._total_emissions = 0.0

        self._grid = values_dict["grid"]

        self._header = []

    def getTimeStart(self):
        return self._time_start

    def getTimeEnd(self):
        return self._time_end

    def getPollutant(self):
        return self._pollutant

    def getTotalEmissions(self):
        return self._total_emissions

    def beginJob(self):
        # prepare the attributes of each point of the vector layer
        self._total_emissions = 0.0
        self._header = [(self._pollutant, QVariant.Double)]
        self._data = self._grid.get_df_from_2d_grid_cells()
        self._data = self._data.assign(Q=pd.Series(0, index=self._data.index))

    def process(
        self,
        timestamp: datetime,
        result: list[tuple[Source, Emission]],
        **kwargs: Any,
    ):
        # result is of format [(Source, Emission)]

        if self._grid is None:
            raise Exception("No 3DGrid found.")

        # filter by configured time
        if self._time_start and self._time_end:
            if not (timestamp >= self._time_start and timestamp < self._time_end):
                return True

        self._all_matched_cells = []

        # loop over all emissions and append one data point for every grid cell
        for source_, emissions__ in result:
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

    def endJob(self) -> Optional[QgsVectorLayer]:
        if self._data.empty:
            return None

        layer_wrapper = ContourPlotVectorLayer(
            layer_name=self._layer_name,
            enable_labels=self._enable_labels,
            field_name=self._pollutant,
            use_centroid_symbol=self._use_centroid_symbol,
        )
        layer_wrapper.addHeader(self._header)
        # TODO pre-OPENGIS.ch: replace with data from grid3D, `contour_layer.addData(self._grid3D[self._grid3D.Emission>0])``
        layer_wrapper.addData(self._data)
        layer_wrapper.setColorGradientRenderer(
            classes_count=7,
        )

        return layer_wrapper.layer
