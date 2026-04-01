import csv
import os
from collections import OrderedDict
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union, cast

import pandas as pd
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWidgets import QTableWidgetItem
from qgis.PyQt.uic import loadUiType

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import Emission, PollutantType, PollutantUnit
from open_alaqs.core.interfaces.Movement import Movement
from open_alaqs.core.interfaces.OutputModule import GridOutputModule
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.tools.Grid3D import Grid3D
from open_alaqs.core.tools.Singleton import Singleton
from open_alaqs.core.tools.sql_interface import insert_into_table

Ui_TableViewDialog, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "..", "..", "ui", "ui_table_view_dialog.ui")
)

logger = get_logger(__name__)


class ViewType(str, Enum):
    BY_AGGREGATION = "by aggregation"
    BY_SOURCE = "by source"
    BY_GRID_CELL = "by grid cell"


class TableViewWidgetOutputModule(GridOutputModule):
    """
    Module to plot results of emission calculation in a table and export the results to CSV or SQLite
    """

    settings_schema = {
        "view_type": {
            "label": "Output view type",
            "widget_type": QtWidgets.QComboBox,
            "initial_value": ViewType.BY_AGGREGATION,
            "coerce": ViewType,
            "widget_config": {
                "options": [t.value for t in ViewType],
            },
        },
    }

    pollutant_unit = PollutantUnit.KG

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
        self._view_type: ViewType = values_dict["view_type"]
        self._grid: Grid3D = values_dict["grid"]

        self.fields = self._prepare_fields()

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

    def beginJob(self):
        self.grid_df = self._grid.get_df_from_2d_grid_cells()

    def process(
        self,
        timestamp: datetime,
        result: list[tuple[Source, list[Emission]]],
        **kwargs: Any,
    ) -> None:
        """
        Process the results and create the records of the csv
        """
        if self._start_dt and self._end_dt:
            if not (self._start_dt <= timestamp < self._end_dt):
                return None

        if self._view_type == ViewType.BY_AGGREGATION:
            emisisons_sums = []
            for source, emissions in result:
                emisisons_sums.append(cast(Emission, sum(emissions)))
            total_emissions_sum = cast(Emission, sum(emisisons_sums))

            self.rows.append(
                self._prepare_source_row(timestamp, total_emissions_sum, None)
            )
        elif self._view_type == ViewType.BY_SOURCE:
            for source, emissions in result:
                if isinstance(source, Movement):
                    # Export one row per emission segment for movements.
                    # Summing all segments into one row and then unary_union-ing their
                    # geometries loses the per-segment emission split, which forces an
                    # inaccurate equal-weight distribution in the AUSTAL grid step.
                    # One row per segment preserves the exact emission/geometry pairing
                    # that the direct OpenALAQS -> AUSTAL uses
                    for emission in emissions:
                        self.rows.append(
                            self._prepare_source_row(timestamp, emission, source)
                        )
                else:
                    emissions_sum = cast(Emission, sum(emissions))
                    self.rows.append(
                        self._prepare_source_row(timestamp, emissions_sum, source)
                    )
        elif self._view_type == ViewType.BY_GRID_CELL:
            for source, emissions in result:
                for emission in emissions:
                    self.grid_df = self._process_grid(source, emission, self.grid_df)
        else:
            raise NotImplementedError()

    def endJob(self) -> QtWidgets.QDialog:
        headers = list(self.fields.values())
        formatted_rows = []
        self.widget.set_headers(headers)

        if self._view_type == ViewType.BY_GRID_CELL:
            for _index, df_row in self.grid_df.iterrows():
                self.rows.append(self._prepare_grid_row(df_row))

        for row in self.rows:
            formatted_row = self._format_values(row)
            formatted_rows.append(formatted_row)

        self.widget.add_rows(formatted_rows)

        return self.widget

    def _prepare_fields(self) -> dict[str, str]:
        fields = {
            "timestamp": "Timestamp",
            "source_type": "Source Type",
            "source_name": "Source Name",
            # "nvpm_kg": "PMNonVolatile [kg]",
            # "nvpm_number": "PMNonVolatileNumber [er]",
        }

        for pollutant_type in PollutantType:
            column_name = f"{pollutant_type.value}_{self.pollutant_unit.value}"
            fields[column_name] = (
                f"{pollutant_type.name} [{self.pollutant_unit.value.upper()}]"
            )

        # NOTE we add the WKT column in the end, so it does not break the readability of the table
        fields["wkt"] = "WKT"

        return fields

    def _format_values(self, values: Union[dict[str, Any], pd.Series]) -> list[Any]:
        formatted_row = []

        for table_field in self.fields.keys():
            value = values[table_field]

            if value is None:
                formatted_value = "-"
            elif isinstance(value, float):
                formatted_value = f"{value:.5g}"
            else:
                formatted_value = str(value)

            formatted_row.append(formatted_value)

        return formatted_row

    def _prepare_grid_row(self, df_row: pd.Series) -> dict[str, Any]:
        row = {
            "timestamp": None,
            "wkt": df_row["geometry"].wkt,
            "source_type": None,
            "source_name": None,
        }

        for pollutant_type in PollutantType:
            column_name = f"{pollutant_type.value}_{self.pollutant_unit.value}"
            row[column_name] = df_row[column_name]

        return row

    def _prepare_source_row(
        self,
        timestamp: datetime,
        emissions: Emission,
        source: Optional[Source],
    ) -> dict[str, Any]:
        if source is None:
            source_type = "total"
            source_name = "total"
            wkt = None
        else:
            source_type = type(source).__name__
            source_name = source.getName()

            if isinstance(source, Movement):
                # For Movement sources use the geometry from the emission object, not
                # the source. The source geometry is the full trajectory; each emission
                # carries the geometry of its specific segment (already clipped and
                # scaled by FlightEmissionCalculator; taxi/gate assumed to be always within the
                # grid).
                wkt = emissions.getGeometryText()
            elif hasattr(source, "getGeometryText"):
                wkt = source.getGeometryText()
            else:
                wkt = None

        row = {
            "timestamp": timestamp.isoformat(),
            "wkt": wkt,
            "source_type": source_type,
            "source_name": source_name,
            # "nvpm_kg": emissions.get_value(PollutantType.nvPM, PollutantUnit.KG),
            # "nvpm_number": emissions.get_value(
            #     PollutantType.nvPMnumber, PollutantUnit.NONE
            # ),
        }
        for pollutant_type in PollutantType:
            column_name = f"{pollutant_type.value}_{self.pollutant_unit.value}"
            row[column_name] = emissions.get_value(pollutant_type, self.pollutant_unit)

        return row

    def export_to_csv(self, filename: str) -> None:
        if not filename:
            return

        with open(filename, "w") as f:
            writer = csv.DictWriter(f, list(self.fields.keys()))
            writer.writeheader()
            writer.writerows(self.rows)

    def _on_export_csv_clicked(self):
        filename, handler_ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Save results as CSV file", ".", "CSV (*.csv)"
        )

        self.export_to_csv(filename)

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

        serializer = EmissionCalculationResultDatabase(
            filename,
            primary_key="timestamp",
            pollutant_unit=self.pollutant_unit,
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
        serializer.recreate_table()

        insert_into_table(filename, serializer.TABLE_NAME, self.rows)

        if os.path.isfile(filename):
            QtWidgets.QMessageBox.information(
                None,
                "Export SQLite",
                f"Results saved as SQLite file at `{filename}`",
            )


class EmissionCalculationResultDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to emission calculation results in the spatialite database
    """

    TABLE_NAME = "emission_calculation_result"

    def __init__(
        self,
        db_path_string,
        primary_key="",
        pollutant_unit=PollutantUnit.KG,
    ):
        table_columns_type_dict = OrderedDict(
            [
                ("timestamp", "DATETIME"),
                ("source_type", "TEXT"),
                ("source_name", "TEXT"),
                ("wkt", "TEXT"),
            ]
        )

        for pollutant_type in PollutantType:
            column_name = f"{pollutant_type.value}_{pollutant_unit.value}"
            table_columns_type_dict[column_name] = "DECIMAL"

        SQLSerializable.__init__(
            self,
            db_path_string,
            self.TABLE_NAME,
            table_columns_type_dict,
            primary_key,
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

    def add_rows(self, rows: list[list[str]]) -> None:

        for columns in rows:
            row_idx = self.ui.data_table.rowCount()
            self.ui.data_table.setRowCount(self.ui.data_table.rowCount() + 1)

            for col_idx, column in enumerate(columns):
                self.ui.data_table.setItem(row_idx, col_idx, QTableWidgetItem(column))

        self.ui.data_table.resizeColumnsToContents()
        self.ui.data_table.resizeRowsToContents()
