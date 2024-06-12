from datetime import datetime
from typing import Any, Optional

from qgis.PyQt import QtWidgets

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.interfaces.Source import Source

logger = get_logger(__name__)


class TabularOutputModule(OutputModule):
    """
    Module to handle tabular writes of emission-calculation results
    """

    settings_schema = {
        "has_detailed_output": {
            "label": "Detailed output",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": False,
        },
    }

    fields = {
        "timestamp": "Timestamp",
        "source_type": "Source Type",
        "source_name": "Source Name",
        "co_kg": "CO [kg]",
        "co2_kg": "CO2 [kg]",
        "hc_kg": "HC [kg]",
        "nox_kg": "NOX [kg]",
        "sox_kg": "SOX [kg]",
        "pmtotal_kg": "PMTotal [kg]",
        "pm01_kg": "PM01 [kg]",
        "pm25_kg": "PM25 [kg]",
        "pmsul_kg": "PMSUL [kg]",
        "pmvolatile_kg": "PMVolatile [kg]",
        "pmnonvolatile_kg": "PMNonVolatile [kg]",
        "pmnonvolatile_number": "PMNonVolatileNumber [er]",
        "source_wkt": "Source WKT",
    }

    def __init__(self, values_dict: dict[str, Any] = None):
        values_dict = values_dict or {}

        super().__init__(values_dict)

        self._has_detailed_output = values_dict.get("has_detailed_output", False)
        self.rows = []

    def process(
        self,
        timestamp: datetime,
        result: list[tuple[Source, Emission]],
        **kwargs: Any,
    ):
        """
        Process the results and create the records of the csv
        """
        # if self.start_dt and self.end_dt:
        #     if not (self.start_dt <= timestamp < self.end_dt):
        #         return None

        if self._has_detailed_output:
            for source, emissions in result:
                emissions_sum = sum(emissions)
                self.rows.append(self._format_row(timestamp, emissions_sum, source))
        else:
            emissions_total = sum(
                [sum(emissions_) for (_, emissions_) in result if emissions_]
            )

            self.rows.append(self._format_row(timestamp, emissions_total, None))

    def _format_row(
        self,
        timestamp: datetime,
        emissions: Emission,
        source: Optional[Source],
    ) -> None:
        if source is None:
            source_type = "total"
            source_name = "total"
            source_wkt = None
        else:
            source_type = source.__class__.__name__
            source_name = source.getName()

            if hasattr(source, "getGeometryText"):
                source_wkt = source.getGeometryText()
            else:
                source_wkt = None

        return {
            "timestamp": timestamp.isoformat(),
            "source_wkt": source_wkt,
            "source_type": source_type,
            "source_name": source_name,
            "co_kg": emissions.getCO(unit="kg")[0],
            "co2_kg": emissions.getCO2(unit="kg")[0],
            "hc_kg": emissions.getHC(unit="kg")[0],
            "nox_kg": emissions.getNOx(unit="kg")[0],
            "sox_kg": emissions.getSOx(unit="kg")[0],
            "pmtotal_kg": emissions.getPM10(unit="kg")[0],
            "pm01_kg": emissions.getPM1(unit="kg")[0],
            "pm25_kg": emissions.getPM2(unit="kg")[0],
            "pmsul_kg": emissions.getPM10Sul(unit="kg")[0],
            "pmvolatile_kg": emissions.getPM10Organic(unit="kg")[0],
            "pmnonvolatile_kg": emissions.getnvPM(unit="kg")[0],
            "pmnonvolatile_number": emissions.getnvPMnumber()[0],
        }
