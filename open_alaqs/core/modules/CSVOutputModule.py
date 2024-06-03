import csv
import os

from qgis.PyQt import QtWidgets

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.modules.TabularOutputModule import TabularOutputModule

logger = get_logger(__name__)


class CSVOutputModule(TabularOutputModule):
    """
    Module to handle csv writes of emission-calculation results
    (timestamp, source, total_emissions_)
    """

    @staticmethod
    def getModuleName():
        return "CSVOutputModule"

    @staticmethod
    def getModuleDisplayName():
        return "CSV"

    def endJob(self):
        """
        Write output to csv file
        """
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
                None, "CSVOutputModule", f"Results saved as CSV file at `{filename}`"
            )
