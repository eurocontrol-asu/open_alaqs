from __future__ import absolute_import
# from . import __init__ #setup the paths for direct calls of the module
import __init__
import sys, os
import alaqsutils           # For logging and conversion of data types
import alaqsdblite          # Functions for working with ALAQS database

import alaqslogging
logger = alaqslogging.logging.getLogger(__name__)
logger.setLevel('DEBUG')
file_handler = alaqslogging.logging.FileHandler(alaqslogging.LOG_FILE_PATH)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = alaqslogging.logging.Formatter(log_format)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

from collections import OrderedDict

from tools import CSVInterface

from interfaces.OutputModule import OutputModule

# from qgis.PyQt import QtGui, QtWidgets
from PyQt5 import QtCore, QtGui, QtWidgets

class CSVOutputModule(OutputModule):
    """
    Module to handle csv writeout of emission-calculation results (timestamp, source, total_emissions_)
    """

    @staticmethod
    def getModuleName():
        return "CSVOutputModule"

    def __init__(self, values_dict = {}):
        OutputModule.__init__(self, values_dict)
        self._isDetailedOutput = values_dict["detailed output"] if "detailed output" in values_dict else False

        self.setConfigurationWidget(OrderedDict([
            ("detailed output" , QtWidgets.QCheckBox)
        ]))

        self.getConfigurationWidget().initValues({"detailed output": False})

    def beginJob(self):
        #initialize rows object
        self._rows = []
        self._headers = [
            "Time",
            "Source name",
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
        ]

        self._rows.append(self._headers)
        file_, handler_ = QtWidgets.QFileDialog.getSaveFileName(None, 'Save results as csv file', '.', 'CSV (*.csv)')
        self.setOutputPath(file_)

    def process(self, timeval, result, **kwargs):
        #result is of format [(Source, Emission)]

        if not self._isDetailedOutput:
            total_emissions_ = sum([sum(emissions_) for (source, emissions_) in result if emissions_])
            self._rows.append([
                timeval,
                "total",
                total_emissions_.getCO(unit="kg")[0],
                total_emissions_.getCO2(unit="kg")[0],
                total_emissions_.getHC(unit="kg")[0],
                total_emissions_.getNOx(unit="kg")[0],
                total_emissions_.getSOx(unit="kg")[0],
                total_emissions_.getPM10(unit="kg")[0],
                total_emissions_.getPM1(unit="kg")[0],
                total_emissions_.getPM2(unit="kg")[0],
                total_emissions_.getPM10Prefoa3(unit="kg")[0],
                total_emissions_.getPM10Nonvol(unit="kg")[0],
                total_emissions_.getPM10Sul(unit="kg")[0],
                total_emissions_.getPM10Organic(unit="kg")[0]])
        else:
            for (source, emissions_) in result:
                self._rows.append([
                    timeval,
                    # emissions.getCategory()
                    source.getName(),
                    sum(emissions_).getCO(unit="kg")[0],
                    sum(emissions_).getCO2(unit="kg")[0],
                    sum(emissions_).getHC(unit="kg")[0],
                    sum(emissions_).getNOx(unit="kg")[0],
                    sum(emissions_).getSOx(unit="kg")[0],
                    sum(emissions_).getPM10(unit="kg")[0],
                    sum(emissions_).getPM1(unit="kg")[0],
                    sum(emissions_).getPM2(unit="kg")[0],
                    sum(emissions_).getPM10Prefoa3(unit="kg")[0],
                    sum(emissions_).getPM10Nonvol(unit="kg")[0],
                    sum(emissions_).getPM10Sul(unit="kg")[0],
                    sum(emissions_).getPM10Organic(unit="kg")[0]])

    def endJob(self):
        #write output to csv file
        if not self.getOutputPath() is None:
            CSVInterface.writeCSV(self.getOutputPath(), self._rows)
        if os.path.isfile(self.getOutputPath()):
            QtWidgets.QMessageBox.information(None, "CSVInterface Module", "Results saved as csv file")