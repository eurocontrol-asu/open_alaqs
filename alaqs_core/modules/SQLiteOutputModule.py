from __future__ import absolute_import
# from . import __init__ #setup the paths for direct calls of the module

import sys, os
import alaqslogging
logger = alaqslogging.logging.getLogger(__name__)
logger.setLevel('DEBUG')
file_handler = alaqslogging.logging.FileHandler(alaqslogging.LOG_FILE_PATH)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = alaqslogging.logging.Formatter(log_format)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

import alaqsutils           # For logging and conversion of data types
import alaqsdblite          # Functions for working with ALAQS database
from future.utils import with_metaclass
from collections import OrderedDict
from interfaces.SQLSerializable import SQLSerializable
from interfaces.OutputModule import OutputModule
from interfaces.Singleton import Singleton

# from qgis.PyQt import QtGui, QtWidgets
from PyQt5 import QtCore, QtGui, QtWidgets
class SQLiteOutputModule(OutputModule):
    """
    Module to handle sql writeout of emission-calculation results (timestamp, source, total_emissions_)
    """

    @staticmethod
    def getModuleName():
        return "SQLiteOutputModule"

    def __init__(self, values_dict = {}):
        OutputModule.__init__(self, values_dict)
        self._isDetailedOutput = values_dict["detailed_output"] if "detailed_output" in values_dict else False

        self.setConfigurationWidget(OrderedDict([
            ("detailed output" , QtWidgets.QCheckBox)
        ]))

        self.getConfigurationWidget().initValues({"detailed output": False})

    def beginJob(self):
        #initialize database connections
        self._db = None
        self.setOutputPath(QtWidgets.QFileDialog.getSaveFileName(None, 'Save results as SQLite file', ".","'SQLite (*.db)'"))

        if not self.getOutputPath()[0] is None:
            self._db = EmissionCalculationResultDatabase(self.getOutputPath()[0])

        if not self._db is None:
            self._db.create_table(self.getOutputPath()[0])

    def process(self, timeval, result, **kwargs):
        #result is of format [(Source, Emission)]

        rows_ = []
        if not self._isDetailedOutput:
            total_emissions_ = sum([sum(emissions_) for (source, emissions_) in result])
            rows_.append({
                "time":timeval,
                "source_id":"total",
                "co_kg":total_emissions_.getCO(unit="kg")[0],
                "co2_kg":total_emissions_.getCO2(unit="kg")[0],
                "hc_kg":total_emissions_.getHC(unit="kg")[0],
                "nox_kg":total_emissions_.getNOx(unit="kg")[0],
                "sox_kg":total_emissions_.getSOx(unit="kg")[0],
                "pm10_kg":total_emissions_.getPM10(unit="kg")[0],
                "pm1_kg":total_emissions_.getPM1(unit="kg")[0],
                "pm2_kg":total_emissions_.getPM2(unit="kg")[0],
                "pm10prefoa3_kg":total_emissions_.getPM10Prefoa3(unit="kg")[0],
                "pm10nonvol_kg":total_emissions_.getPM10Nonvol(unit="kg")[0],
                "pm10sul_kg":total_emissions_.getPM10Sul(unit="kg")[0],
                "pm10organic_kg":total_emissions_.getPM10Organic(unit="kg")[0]
                })
        else:
            for (source, emissions_) in result:
                rows_.append({
                    "time":timeval,
                    "source_id":source.getName(),
                    "co_kg":sum(emissions_).getCO(unit="kg")[0],
                    "co2_kg":sum(emissions_).getCO2(unit="kg")[0],
                    "hc_kg":sum(emissions_).getHC(unit="kg")[0],
                    "nox_kg":sum(emissions_).getNOx(unit="kg")[0],
                    "sox_kg":sum(emissions_).getSOx(unit="kg")[0],
                    "pm10_kg":sum(emissions_).getPM10(unit="kg")[0],
                    "pm1_kg":sum(emissions_).getPM1(unit="kg")[0],
                    "pm2_kg":sum(emissions_).getPM2(unit="kg")[0],
                    "pm10prefoa3_kg":sum(emissions_).getPM10Prefoa3(unit="kg")[0],
                    "pm10nonvol_kg":sum(emissions_).getPM10Nonvol(unit="kg")[0],
                    "pm10sul_kg":sum(emissions_).getPM10Sul(unit="kg")[0],
                    "pm10organic_kg":sum(emissions_).getPM10Organic(unit="kg")[0]
                })

        if rows_ and not self._db is None:
            self._db.insert_rows(self.getOutputPath()[0], rows_)

    def endJob(self):
        pass

class EmissionCalculationResultDatabase(with_metaclass(Singleton, SQLSerializable)):
    """
    Class that grants access to table in the spatialite database where results can be stored in
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="emission_calculation_result",
                 table_columns_type_dict=OrderedDict([
                    ("time" , "DATETIME"),
                    ("source_id" , "TEXT"),
                    ("co_kg", "DECIMAL"),
                    ("co2_kg", "DECIMAL"),
                    ("hc_kg", "DECIMAL"),
                    ("nox_kg", "DECIMAL"),
                    ("sox_kg", "DECIMAL"),
                    ("pm10_kg", "DECIMAL"),
                    ("pm1_kg", "DECIMAL"),
                    ("pm2_kg", "DECIMAL"),
                    ("pm10prefoa3_kg", "DECIMAL"),
                    ("pm10nonvol_kg", "DECIMAL"),
                    ("pm10sul_kg", "DECIMAL"),
                    ("pm10organic_kg", "DECIMAL")
                ]),
                 primary_key="time",
                 geometry_columns=[]
        ):
        SQLSerializable.__init__(self, db_path_string, table_name_string, table_columns_type_dict, primary_key, geometry_columns)
