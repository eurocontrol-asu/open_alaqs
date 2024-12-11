from datetime import datetime
from typing import Any, Optional, Union, cast

import geopandas as gpd
from qgis.core import QgsMapLayer
from qgis.PyQt.QtWidgets import QWidget
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.validation import make_valid

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import Emission, PollutantType, PollutantUnit
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.modules.ModuleConfigurationWidget import (
    ModuleConfigurationWidget,
    SettingsSchema,
)

logger = get_logger(__name__)


class OutputModule:
    """
    Abstract interface to handle calculation results (timestamp, source, emissions)
    """

    settings_schema: SettingsSchema = {}

    @staticmethod
    def getModuleName() -> str:
        return ""

    @staticmethod
    def getModuleDisplayName() -> str:
        return ""

    def __init__(self, values_dict: dict[str, Any]) -> None:
        self._database_path = values_dict.get("database_path", "")
        self._output_path = values_dict.get("output_path", "")
        self._name = values_dict.get("name", "")

    def setDatabasePath(self, val: str) -> None:
        self._database_path = val

    def getDatabasePath(self) -> str:
        return self._database_path

    def setOutputPath(self, val: str) -> None:
        self._output_path = val

    def getOutputPath(self) -> str:
        return self._output_path

    @classmethod
    def getConfigurationWidget2(cls) -> Optional[ModuleConfigurationWidget]:
        if not cls.settings_schema:
            return None

        return ModuleConfigurationWidget(cls.settings_schema)

    def beginJob(self):
        return None

    def process(
        self,
        timestamp: datetime,
        result: list[tuple[Source, list[Emission]]],
        **kwargs: Any,
    ):
        raise NotImplementedError()

    def endJob(self) -> Union[QWidget, QgsMapLayer, None]:
        return None


class GridOutputModule(OutputModule):
    def _process_grid(
        self, source: Source, emission: Emission, grid_df: gpd.GeoDataFrame
    ) -> gpd.GeoDataFrame:
        if emission.getGeometryText() is None:
            logger.error(
                "Did not find geometry for emissions '%s'. Skipping an emission of source '%s'",
                str(emission),
                str(source.getName()),
            )
            return grid_df

        # ensure geometry validity, otherwise the intersects operations might fail. Ideally the invalid geometries should be prevented.
        geom = make_valid(emission.getGeometry())
        intersecting_df = grid_df[grid_df.intersects(geom) == True]  # noqa: E712
        intersecting_df = cast(gpd.GeoDataFrame, intersecting_df)

        # Calculate Emissions' horizontal distribution
        if isinstance(geom, Point):
            factor = 1 / len(intersecting_df)
        elif isinstance(geom, (LineString, MultiLineString)):
            factor = intersecting_df.intersection(geom).length / geom.length
        elif isinstance(geom, (Polygon, MultiPolygon)):
            factor = intersecting_df.intersection(geom).area / geom.area
        else:
            raise NotImplementedError(
                "Usupported geometry type: {}".format(type(geom).__name__)
            )

        for pollutant_type in PollutantType:
            emission_value = emission.get_value(pollutant_type, PollutantUnit.KG)
            key = f"{pollutant_type.value}_kg"
            value = factor * emission_value

            intersecting_df.loc[intersecting_df.index, key] = value
            grid_df.loc[intersecting_df.index, key] += intersecting_df[key]

        return grid_df
