import os

from qgis.PyQt import QtWidgets

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.modules.TabularOutputModule import TabularOutputModule
from open_alaqs.core.tools.sql_interface import insert_into_table

logger = get_logger(__name__)


class SQLiteOutputModule(TabularOutputModule):
    """
    Module to handle sql writeout of emission-calculation results (timestamp,
    source, total_emissions_)
    """

    @staticmethod
    def getModuleName():
        return "SQLiteOutputModule"

    @staticmethod
    def getModuleDisplayName():
        return "SQLite"

    def endJob(self):
        # initialize database connections
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
                "SQLiteOutputModule",
                f"Results saved as SQLite file at `{filename}`",
            )
