from datetime import datetime
from typing import Any, Optional

import pandas as pd
from qgis.core import QgsVectorLayer
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QVariant

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import Emission, PollutantType, PollutantUnit
from open_alaqs.core.interfaces.OutputModule import GridOutputModule, OutputModule
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.plotting.ContourPlotVectorLayer import ContourPlotVectorLayer
from open_alaqs.core.tools import Grid3D

pd.set_option("chained_assignment", None)

logger = get_logger(__name__)


class EmissionsQGISVectorLayerOutputModule(GridOutputModule):
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
        self.pollutant_type = PollutantType(values_dict["pollutant"].lower())

        self._layer_name = ContourPlotVectorLayer.LAYER_NAME
        self._use_centroid_symbol = values_dict["use_centroid_symbol"]
        self._enable_labels = values_dict["should_add_labels"]

        self._total_emissions = 0.0

        self._grid: Grid3D = values_dict["grid"]

    def getTimeStart(self):
        return self._time_start

    def getTimeEnd(self):
        return self._time_end

    def getPollutant(self) -> str:
        return self.pollutant_type.value

    def getTotalEmissions(self):
        return self._total_emissions

    def beginJob(self):
        # prepare the attributes of each point of the vector layer
        self._total_emissions = 0.0
        self._grid_df = self._grid.get_df_from_2d_grid_cells()
        self._grid_df = self._grid_df.assign(Q=pd.Series(0, index=self._grid_df.index))

    def process(
        self,
        timestamp: datetime,
        result: list[tuple[Source, list[Emission]]],
        **kwargs: Any,
    ) -> Optional[QgsVectorLayer]:
        # filter by configured time
        if self._time_start and self._time_end:
            if not (timestamp >= self._time_start and timestamp < self._time_end):
                return None

        self._all_matched_cells = []

        # loop over all emissions and append one data point for every grid cell
        for source, emissions in result:
            for emission in emissions:
                self._grid_df = self._process_grid(source, emission, self._grid_df)

    def endJob(self) -> Optional[QgsVectorLayer]:
        if self._grid_df.empty:
            return None

        headers = []
        for pollutant_type in PollutantType:
            key = f"{pollutant_type.value}_{PollutantUnit.KG.value}"
            headers.append((key, QVariant.Double))

        layer_wrapper = ContourPlotVectorLayer(
            layer_name=self._layer_name,
            enable_labels=self._enable_labels,
            field_name=self.pollutant_type.value,
            use_centroid_symbol=self._use_centroid_symbol,
        )
        layer_wrapper.addData(self._grid_df)
        layer_wrapper.setColorGradientRenderer(
            classes_count=7,
        )

        return layer_wrapper.layer
