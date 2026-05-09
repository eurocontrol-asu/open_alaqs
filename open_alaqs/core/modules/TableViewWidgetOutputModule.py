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
from shapely.geometry import (LineString, MultiLineString, MultiPolygon, Point,
                              Polygon)
from shapely.strtree import STRtree
from shapely.validation import make_valid

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import (Emission, PollutantType,
                                                  PollutantUnit)
from open_alaqs.core.interfaces.Movement import Movement
from open_alaqs.core.interfaces.OutputModule import GridOutputModule
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

        # Store method name so beginJob() and exported rows are self-identifying
        self._calc_method: str = values_dict.get("method", "unknown")

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
        super().beginJob()
        self.rows = []  # reset between runs to prevent accumulation
        self.grid_df = self._grid.get_df_from_2d_grid_cells()

        # Grid cells from `Grid3D.get_df_from_2d_grid_cells()` are now built
        # in the local UTM CRS and tagged correctly.  Keep them as-is for
        # intersections; emissions (which are in EPSG:3857) are reprojected
        # to UTM below via `self._geom_transformer`.
        utm_epsg = self._grid.getUtmEpsg()
        self._grid_utm_epsg = utm_epsg

        self._grid_df_utm = self.grid_df[["hash", "geometry"]].copy()
        # Build an STRtree over the UTM grid cells for O(log n) spatial queries
        # instead of the O(n) linear scan used previously.
        self._grid_strtree = STRtree(self._grid_df_utm.geometry.values)

        # Pyproj transformer reused across all _process_grid calls to avoid
        # constructing a new one per emission.
        from pyproj import Transformer

        self._geom_transformer = Transformer.from_crs(
            "EPSG:3857", f"EPSG:{utm_epsg}", always_xy=True
        )

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
                if emissions:
                    emisisons_sums.append(cast(Emission, sum(emissions)))
            if not emisisons_sums:
                return
            total_emissions_sum = cast(Emission, sum(emisisons_sums))
            row = self._prepare_source_row(timestamp, total_emissions_sum, None)
            # Stamp the calculation method on the aggregated row so exported
            # CSVs are self-identifying — prevents bymode/BFFM2 confusion.
            row["source_name"] = f"total [{getattr(self, '_calc_method', 'unknown')}]"
            logger.debug(
                "TableView BY_AGGREGATION: method=%s, NOx=%.4f kg, CO=%.4f kg",
                getattr(self, "_calc_method", "unknown"),
                row.get("nox_kg", 0),
                row.get("co_kg", 0),
            )
            self.rows.append(row)
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

    def _process_grid(
        self, source: Source, emission: Emission, grid_df: gpd.GeoDataFrame
    ) -> gpd.GeoDataFrame:
        """
        Accumulate emission values into the grid cells that intersect the
        emission geometry.

        Replaces the per-emission gpd.GeoDataFrame().to_crs() + linear
        grid_df.intersects() scan with:
          - a pyproj Transformer built once in beginJob() for CRS conversion
          - an STRtree built once in beginJob() for O(log n) candidate selection
          - exact intersection only on the small candidate set from the tree
        """
        if emission.getGeometryText() is None:
            # See OutputModule._process_grid — zero placeholders are intentional sentinels
            # and do not warrant an error log. Only flag a real missing-geometry bug.
            if not emission.isZero():
                logger.error(
                    "Did not find geometry for '%s'. Skipping an emission of source '%s'",
                    str(emission),
                    str(source.getName()),
                )
            return grid_df

        from shapely.ops import transform as shapely_transform

        geom_3857 = make_valid(emission.getGeometry())

        # Reproject to UTM using the pre-built transformer — no GeoDataFrame
        # overhead, no CRS object construction per call.
        geom_utm = make_valid(
            shapely_transform(self._geom_transformer.transform, geom_3857)
        )

        # Query the STRtree for candidate cells (bounding-box pre-filter).
        candidate_indices = self._grid_strtree.query(geom_utm)
        if len(candidate_indices) == 0:
            if (
                not self._grid_coverage_warning_shown
                and self._parent
                and hasattr(self._parent, "message_bar")
            ):
                self._parent.message_bar.pushWarning(
                    "Grid Coverage Warning",
                    "Incomplete grid coverage: expand or adjust the grid to include all sources.",
                )
                self._grid_coverage_warning_shown = True
            return grid_df

        # Exact intersection test on the small candidate set only.
        utm_candidates = self._grid_df_utm.iloc[candidate_indices]
        intersecting_utm = utm_candidates[utm_candidates.geometry.intersects(geom_utm)]

        if len(intersecting_utm) == 0:
            if (
                not self._grid_coverage_warning_shown
                and self._parent
                and hasattr(self._parent, "message_bar")
            ):
                self._parent.message_bar.pushWarning(
                    "Grid Coverage Warning",
                    "Incomplete grid coverage: expand or adjust the grid to include all sources.",
                )
                self._grid_coverage_warning_shown = True
            return grid_df

        if isinstance(geom_utm, Point):
            factor = 1 / len(intersecting_utm)
        elif isinstance(geom_utm, (LineString, MultiLineString)):
            factor = intersecting_utm.intersection(geom_utm).length / geom_utm.length
        elif isinstance(geom_utm, (Polygon, MultiPolygon)):
            factor = intersecting_utm.intersection(geom_utm).area / geom_utm.area
        else:
            raise NotImplementedError(
                "Unsupported geometry type: {}".format(type(geom_utm).__name__)
            )

        for pollutant_type in PollutantType:
            emission_value = emission.get_value(pollutant_type, PollutantUnit.KG)
            key = f"{pollutant_type.value}_kg"
            grid_df.loc[intersecting_utm.index, key] += factor * emission_value

        return grid_df

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

        # newline="" is REQUIRED by the csv module to avoid double line
        # endings on Windows (GitHub #291). Without it, Python's text-mode
        # translates \n→\r\n while csv.writer emits \r\n, producing \r\r\n
        # that many tools interpret as a blank line between records.
        with open(filename, "w", newline="") as f:
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

        columns = {
            "timestamp": "DATETIME",
            "source_type": "TEXT",
            "source_name": "TEXT",
            "wkt": "TEXT",
        }

        for pollutant_type in PollutantType:
            column_name = f"{pollutant_type.value}_{self.pollutant_unit.value}"
            columns[column_name] = "DECIMAL"

        table_name = "emission_calculation_result"
        serializer = SQLSerializable(
            filename,
            table_name,
            columns,
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
        serializer.recreate_table(filename)

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
