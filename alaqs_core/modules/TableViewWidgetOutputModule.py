from datetime import datetime
from typing import List, Tuple

from PyQt5 import QtWidgets

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.Emissions import Emission
from open_alaqs.alaqs_core.interfaces.OutputModule import OutputModule
from open_alaqs.alaqs_core.interfaces.Source import Source
from open_alaqs.alaqs_core.tools import conversion
from open_alaqs.ui.TableViewDialog import Ui_TableViewDialog

logger = get_logger(__name__)


class TableViewWidgetOutputModule(OutputModule):
    """
    Module to plot results of emission calculation in a table
    """

    @staticmethod
    def getModuleName():
        return "TableViewWidgetOutputModule"

    def __init__(self, values_dict = None):
        if values_dict is None:
            values_dict = {}
        OutputModule.__init__(self, values_dict)

        # Widget configuration
        self._parent = values_dict[
            "parent"] if "parent" in values_dict else None

        # Results analysis
        self._time_start = ""
        if "Start (incl.)" in values_dict:
            self._time_start = \
                conversion.convertStringToDateTime(values_dict["Start (incl.)"])
        self._time_end = conversion.convertStringToDateTime(
            values_dict["End (incl.)"]) if "End (incl.)" in values_dict else ""
        self._pollutant = values_dict.get("pollutant")

        self._widget = TableViewWidget(self._parent)

    def getWidget(self):
        return self._widget

    def beginJob(self):
        self._widget.setDataTableHeaders([
            "Time",
            "CO [kg]",
            "CO2 [kg]",
            "HC [kg]",
            "NOx [kg]",
            "SOx [kg]",
            "PM10 [kg]",
            "P1 [kg]",
            "P2 [kg]",
            "PM10Prefoa3 [kg]",
            "PM10Nonvol [kg]",
            "PM10Sul [kg]",
            "PM10Organic [kg]"
        ])

    def process(self, timeval: datetime, result: List[Tuple[Source, Emission]],
                **kwargs):

        # filter by configured time
        if self._time_start and self._time_end:
            if not (self._time_start <= timeval < self._time_end):
                return True

        # Calculate the total emissions
        total_emissions_ = sum(sum(emissions_) for (_, emissions_) in result)

        # Get the current row count
        current_row_count = self._widget.getTable().rowCount()

        # Add a new row to the table
        self._widget.getTable().setRowCount(current_row_count + 1)

        # Get the new row index
        new_row_index = current_row_count - 1

        # Write cells
        for index_col_, val_ in enumerate([
            (timeval, ""),
            total_emissions_.getCO(unit="kg"),
            total_emissions_.getCO2(unit="kg"),
            total_emissions_.getHC(unit="kg"),
            total_emissions_.getNOx(unit="kg"),
            total_emissions_.getSOx(unit="kg"),
            total_emissions_.getPM10(unit="kg"),
            total_emissions_.getPM1(unit="kg"),
            total_emissions_.getPM2(unit="kg"),
            total_emissions_.getPM10Prefoa3(unit="kg"),
            total_emissions_.getPM10Nonvol(unit="kg"),
            total_emissions_.getPM10Sul(unit="kg"),
            total_emissions_.getPM10Organic(unit="kg")
        ]):

            # Format the cell values
            if val_[0] is None:
                rval_ = ""
            elif isinstance(val_[0], float):
                rval_ = str(round(val_[0], 5))
            else:
                rval_ = str(val_[0])

            # Update the cells
            self._widget.getTable().setItem(
                new_row_index, index_col_, QtWidgets.QTableWidgetItem(rval_))

    def endJob(self):
        self._widget.resizeToContent()
        return self._widget


class TableViewWidget(QtWidgets.QDialog):
    """
    This class provides a dialog for visualizing ALAQS results.
    """
    def __init__(self, parent=None):
        super(TableViewWidget, self).__init__(parent)

        self._parent = parent

        self.ui = Ui_TableViewDialog()
        self.ui.setupUi(self)

        self._data_table_headers = []

        self.initTable()

    def initTable(self):
        self.getTable().setColumnCount(len(self._data_table_headers))
        self.getTable().setHorizontalHeaderLabels(self._data_table_headers)
        self.getTable().verticalHeader().setVisible(False)

    def resizeToContent(self):
        self.getTable().resizeColumnsToContents()
        self.getTable().resizeRowsToContents()

    def getTable(self):
        return self.ui.data_table

    def resetTable(self):
        self.getTable().clear()
        self.getTable().setHorizontalHeaderLabels(self._data_table_headers)
        self.getTable().setRowCount(0)

    def setDataTableHeaders(self, headers):
        self._data_table_headers = headers
        self.initTable()