from __future__ import absolute_import
from builtins import object
from . import __init__ #setup the paths for direct calls of the module

import os
import alaqsutils           # For logging and conversion of data types
import alaqsdblite          # Functions for working with ALAQS database
import os
import sys

import alaqslogging
# logger = logging.getLogger(__name__)
logger = alaqslogging.logging.getLogger(__name__)
# To override the default severity of logging
logger.setLevel('DEBUG')
# Use FileHandler() to log to a file
file_handler = alaqslogging.logging.FileHandler(alaqslogging.LOG_FILE_PATH)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = alaqslogging.logging.Formatter(log_format)
file_handler.setFormatter(formatter)
# Don't forget to add the file handler
logger.addHandler(file_handler)

# from qgis.PyQt import QtGui, QtWidgets
from PyQt5 import QtCore, QtGui, QtWidgets
from modules.ui.ModuleConfigurationWidget import ModuleConfigurationWidget

class OutputModule(object):
    """
    Abstract interface to handle calculation results (timestamp, source, emissions)
    """

    @staticmethod
    def getModuleName():
        return ""

    def __init__(self, values_dict = {}):
        self._database_path = values_dict["database_path"] if "database_path" in values_dict else None
        self._output_path = values_dict["output_path"] if "output_path" in values_dict else None
        self._name = values_dict["name"] if "name" in values_dict else None
        self._configuration_widget = None

    def setDatabasePath(self, val):
        self._database_path = val
    def getDatabasePath(self):
        return self._database_path

    def setOutputPath(self, val):
        self._output_path = val
    def getOutputPath(self):
        return self._output_path

    def getConfigurationWidget(self):
        return self._configuration_widget
    def setConfigurationWidget(self, var):
        if isinstance(var, QtWidgets.QWidget):
            self._configuration_widget = var
        else:
            self._configuration_widget = ModuleConfigurationWidget(var)

    def beginJob(self):
        return NotImplemented

    def process(self, timeval, result, **kwargs):
        #result is of format [(Source, Emission)]
        return NotImplemented

    def endJob(self):
        return NotImplemented