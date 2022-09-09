import os
from collections import OrderedDict
from datetime import datetime
from typing import List, Tuple

from PyQt5 import QtWidgets

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.Emissions import Emission
from open_alaqs.alaqs_core.interfaces.OutputModule import OutputModule
from open_alaqs.alaqs_core.interfaces.Source import Source
from open_alaqs.alaqs_core.tools.csv_interface import write_csv

logger = get_logger(__name__)


class CSVOutputModule(OutputModule):
    """
    Module to handle csv writes of emission-calculation results
    (timestamp, source, total_emissions_)
    """

    @staticmethod
    def getModuleName():
        return "CSVOutputModule"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        OutputModule.__init__(self, values_dict)
        self._isDetailedOutput = values_dict.get("detailed output", False)

        self.setConfigurationWidget(OrderedDict([
            ("detailed output", QtWidgets.QCheckBox)
        ]))

        self.getConfigurationWidget().initValues({"detailed output": False})

        self._rows = []
        self._headers = []

    def beginJob(self):
        """
        Initialize the module
        """

        # Set the header
        header = [
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
            "PM10Organic [kg]",
            "nvPM mass [kg]",
            "nvPM number"
        ]

        # Initialize rows attribute with the header
        self._rows = [header]

        # Ask the user to the set the output path
        file_, handler_ = QtWidgets.QFileDialog.getSaveFileName(
            None, 'Save results as CSV file', '.', 'CSV (*.csv)')

        # Set the output path
        self.setOutputPath(file_)

    def process(self, timeval: datetime, result: List[Tuple[Source, Emission]],
                **kwargs):
        """
        Process the results and create the records of the csv

        :param timeval:
        :param result:
        :param kwargs:
        """
        # result is of format [(Source, Emission)]

        if not self._isDetailedOutput:
            # Sum all emissions
            total_emissions_ = sum(
                [sum(emissions_) for (_, emissions_) in result if emissions_])

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
                total_emissions_.getPM10Organic(unit="kg")[0],
                total_emissions_.getnvPM(unit="kg")[0],
                total_emissions_.getnvPMnumber()[0],
            ])
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
                    sum(emissions_).getPM10Organic(unit="kg")[0],
                    sum(emissions_).getnvPM(unit="kg")[0],
                    sum(emissions_).getnvPMnumber()[0],
                ])

    def endJob(self):
        """
        Write output to csv file
        """

        try:

            if self.getOutputPath() is not None:
                write_csv(self.getOutputPath(), self._rows)

            if os.path.isfile(self.getOutputPath()):
                QtWidgets.QMessageBox.information(None, "CSVOutputModule",
                                                  "Results saved as CSV file")

        except Exception as e:
            QtWidgets.QMessageBox.critical(None, "CSVOutputModule",
                                           "Couldn't save results as CSV file")
