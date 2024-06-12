import csv
import os
from datetime import datetime
from typing import Any, Optional

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWidgets import QTableWidgetItem
from qgis.PyQt.uic import loadUiType

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.tools.sql_interface import insert_into_table

Ui_TableViewDialog, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "..", "..", "ui", "ui_table_view_dialog.ui")
)

logger = get_logger(__name__)


class TableViewWidgetOutputModule(OutputModule):
    """
    Module to plot results of emission calculation in a table and export the results to CSV or SQLite
    """

    table_fields = [
        "timestamp",
        "co_kg",
        "co2_kg",
        "hc_kg",
        "nox_kg",
        "sox_kg",
        "pmtotal_kg",
        "pm01_kg",
        "pm25_kg",
        "pmsul_kg",
        "pmvolatile_kg",
        "pmnonvolatile_kg",
        "pmnonvolatile_number",
    ]

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

    @staticmethod
    def getModuleName():
        return "TableViewWidgetOutputModule"

    @staticmethod
    def getModuleDisplayName():
        return "Emissions table"

    def __init__(self, values_dict: dict[str, Any]) -> None:
        super().__init__(values_dict)

        self._start_dt = values_dict["start_dt_inclusive"]
        self._end_dt = values_dict["end_dt_inclusive"]
        self._has_detailed_output = values_dict["has_detailed_output"]

        # Output rows
        self.rows: list[dict[str, Any]] = []

        # Output UI
        self.widget = EmissionsTableViewDialog(values_dict["parent"])
        self.widget.ui.exportCsvBtn.clicked.connect(
            lambda: self._on_export_csv_clicked()
        )
        self.widget.ui.exportSqliteBtn.clicked.connect(
            lambda: self._on_export_sqlite_clicked()
        )

    def process(
        self,
        timestamp: datetime,
        result: list[tuple[Source, Emission]],
        **kwargs: Any,
    ) -> None:
        """
        Process the results and create the records of the csv
        """
        if self._start_dt and self._end_dt:
            if not (self._start_dt <= timestamp < self._end_dt):
                return None

        if self._has_detailed_output:
            for source, emissions in result:
                emissions_sum = sum(emissions)
                self.rows.append(self._format_row(timestamp, emissions_sum, source))
        else:
            emissions_total = sum(
                [sum(emissions_) for (_, emissions_) in result if emissions_]
            )

            self.rows.append(self._format_row(timestamp, emissions_total, None))

    def endJob(self) -> QtWidgets.QDialog:
        headers = [self.fields[k] for k in self.table_fields]
        self.widget.set_headers(headers)

        for row in self.rows:
            formatted_row = []

            for table_field in self.table_fields:
                value = row[table_field]

                if value is None:
                    formatted_value = "-"
                elif isinstance(value, float):
                    formatted_value = f"{value:.5g}"
                else:
                    formatted_value = str(value)

                formatted_row.append(formatted_value)

            self.widget.add_row(formatted_row)

        return self.widget

    def _format_row(
        self,
        timestamp: datetime,
        emissions: Emission,
        source: Optional[Source],
    ) -> dict[str, Any]:
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

    def _on_export_csv_clicked(self):
        filename, handler_ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Save results as CSV file", ".", "CSV (*.csv)"
        )

        if not filename:
            return

        with open(filename, "w") as f:
            writer = csv.DictWriter(f, list(self.fields.keys()))
            writer.writeheader()
            writer.writerows(self.rows)

        if os.path.isfile(filename):
            QtWidgets.QMessageBox.information(
                None, "Export CSV", f"Results saved as CSV file at `{filename}`"
            )

    def _on_export_sqlite_clicked(self):
        filename, handler_ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Save results as SQLite file", ".", "'SQLite (*.db)'"
        )

        if not filename:
            return

        table_name = "emission_calculation_result"
        serializer = SQLSerializable(
            filename,
            table_name,
            {
                "timestamp": "DATETIME",
                "source_type": "TEXT",
                "source_name": "TEXT",
                "co_kg": "DECIMAL",
                "co2_kg": "DECIMAL",
                "hc_kg": "DECIMAL",
                "nox_kg": "DECIMAL",
                "sox_kg": "DECIMAL",
                "pmtotal_kg": "DECIMAL",
                "pm01_kg": "DECIMAL",
                "pm25_kg": "DECIMAL",
                "pmsul_kg": "DECIMAL",
                "pmvolatile_kg": "DECIMAL",
                "pmnonvolatile_kg": "DECIMAL",
                "pmnonvolatile_number": "DECIMAL",
                "source_wkt": "TEXT",
            },
            primary_key="timestamp",
            # TODO OPENGIS.ch: add the geometry column
            # geometry_columns=[
            #     {
            #         "column_name": "source_geometry",
            #         "SRID": 3857,
            #         "geometry_type": "POLYGON",
            #         "geometry_type_dimension": 2,
            #     },
            # ],
        )
        serializer._recreate_table(filename)

        insert_into_table(filename, table_name, self.rows)

        if os.path.isfile(filename):
            QtWidgets.QMessageBox.information(
                None,
                "Export SQLite",
                f"Results saved as SQLite file at `{filename}`",
            )


class EmissionsTableViewDialog(QtWidgets.QDialog):
    """This class provides a dialog for visualizing ALAQS results."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.ui = Ui_TableViewDialog()
        self.ui.setupUi(self)

    def set_headers(self, headers: list[str]) -> None:
        self.ui.data_table.setColumnCount(len(headers))
        self.ui.data_table.setHorizontalHeaderLabels(headers)
        self.ui.data_table.verticalHeader().setVisible(False)

    def add_row(self, columns: list[str]) -> None:
        row_idx = self.ui.data_table.rowCount()
        self.ui.data_table.setRowCount(self.ui.data_table.rowCount() + 1)

        for col_idx, column in enumerate(columns):
            self.ui.data_table.setItem(row_idx, col_idx, QTableWidgetItem(column))

        self.ui.data_table.resizeColumnsToContents()
        self.ui.data_table.resizeRowsToContents()
