import csv
import os
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union, cast

import geopandas as gpd
import pandas as pd
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWidgets import QTableWidgetItem
from qgis.PyQt.uic import loadUiType
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import Emission, PollutantType, PollutantUnit
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.tools.Grid3D import Grid3D
from open_alaqs.core.tools.sql_interface import insert_into_table

Ui_TableViewDialog, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "..", "..", "ui", "ui_table_view_dialog.ui")
)

logger = get_logger(__name__)


class ViewType(str, Enum):
    BY_AGGREGATION = "by aggregation"
    BY_SOURCE = "by source"
    BY_GRID_CELL = "by grid cell"


class TableViewWidgetOutputModule(OutputModule):
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

    fields = {
        "timestamp": "Timestamp",
        "source_type": "Source Type",
        "source_name": "Source Name",
        "co_kg": "CO [kg]",
        "co2_kg": "CO2 [kg]",
        "hc_kg": "HC [kg]",
        "nox_kg": "NOX [kg]",
        "sox_kg": "SOX [kg]",
        "pm10_kg": "PMTotal [kg]",
        "p1_kg": "PM01 [kg]",
        "p2_kg": "PM25 [kg]",
        "pm10_sul_kg": "PMSUL [kg]",
        "pm10_organic_kg": "PMVolatile [kg]",
        # "nvpm_kg": "PMNonVolatile [kg]",
        # "nvpm_number": "PMNonVolatileNumber [er]",
        "wkt": "Source WKT",
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
        self._view_type: ViewType = values_dict["view_type"]
        self._grid: Grid3D = values_dict["grid"]

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
                emissions_sum = cast(Emission, sum(emissions))

                self.rows.append(
                    self._prepare_source_row(timestamp, emissions_sum, source)
                )
        elif self._view_type == ViewType.BY_GRID_CELL:
            for source, emissions in result:
                for emission in emissions:
                    self.grid_df = foo(source, emission, self.grid_df)
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
        return {
            "timestamp": None,
            "wkt": df_row["geometry"].wkt,
            "source_type": None,
            "source_name": None,
            "co_kg": df_row["co_kg"],
            "co2_kg": df_row["co2_kg"],
            "hc_kg": df_row["hc_kg"],
            "nox_kg": df_row["nox_kg"],
            "sox_kg": df_row["sox_kg"],
            "pm10_kg": df_row["pm10_kg"],
            "p1_kg": df_row["p1_kg"],
            "p2_kg": df_row["p2_kg"],
            "pm10_sul_kg": df_row["pm10_sul_kg"],
            "pm10_organic_kg": df_row["pm10_organic_kg"],
        }

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
            source_type = source.__class__.__name__
            source_name = source.getName()

            if hasattr(source, "getGeometryText"):
                wkt = source.getGeometryText()
            else:
                wkt = None

        return {
            "timestamp": timestamp.isoformat(),
            "wkt": wkt,
            "source_type": source_type,
            "source_name": source_name,
            "co_kg": emissions.get_value(PollutantType.CO, PollutantUnit.KG),
            "co2_kg": emissions.get_value(PollutantType.CO2, PollutantUnit.KG),
            "hc_kg": emissions.get_value(PollutantType.HC, PollutantUnit.KG),
            "nox_kg": emissions.get_value(PollutantType.NOx, PollutantUnit.KG),
            "sox_kg": emissions.get_value(PollutantType.SOx, PollutantUnit.KG),
            "p1_kg": emissions.get_value(PollutantType.PM1, PollutantUnit.KG),
            "p2_kg": emissions.get_value(PollutantType.PM2, PollutantUnit.KG),
            "pm10_kg": emissions.get_value(PollutantType.PM10, PollutantUnit.KG),
            "pm10_sul_kg": emissions.get_value(PollutantType.PM10Sul, PollutantUnit.KG),
            "pm10_organic_kg": emissions.get_value(
                PollutantType.PM10Organic, PollutantUnit.KG
            ),
            # "nvpm_kg": emissions.get_value(PollutantType.nvPM, PollutantUnit.KG),
            # "nvpm_number": emissions.get_value(
            #     PollutantType.nvPMnumber, PollutantUnit.NONE
            # ),
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
                "pm10_kg": "DECIMAL",
                "p1_kg": "DECIMAL",
                "p2_kg": "DECIMAL",
                "pm10_sul_kg": "DECIMAL",
                "pm10_organic_kg": "DECIMAL",
                # "nvpm_kg": "DECIMAL",
                # "nvpm_number": "DECIMAL",
                "wkt": "TEXT",
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

    def add_rows(self, rows: list[list[str]]) -> None:

        for columns in rows:
            row_idx = self.ui.data_table.rowCount()
            self.ui.data_table.setRowCount(self.ui.data_table.rowCount() + 1)

            for col_idx, column in enumerate(columns):
                self.ui.data_table.setItem(row_idx, col_idx, QTableWidgetItem(column))

        self.ui.data_table.resizeColumnsToContents()
        self.ui.data_table.resizeRowsToContents()


def foo(source: Source, emission: Emission, grid_df: gpd.GeoDataFrame):
    if emission.getGeometryText() is None:
        logger.error(
            "Did not find geometry for emissions '%s'. Skipping an emission of source '%s'",
            str(emission),
            str(source.getName()),
        )
        return grid_df

    geom = emission.getGeometry()
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
            "Usupported geometry type: {}".format(geom.__class__.name)
        )

    for pollutant_type in PollutantType:
        if pollutant_type == PollutantType.nvPM:
            continue

        emission_value = emission.get_value(pollutant_type, PollutantUnit.KG)
        key = f"{pollutant_type.value}_kg"
        value = factor * emission_value

        intersecting_df.loc[intersecting_df.index, key] = value
        grid_df.loc[intersecting_df.index, key] += intersecting_df[key]

    return grid_df
