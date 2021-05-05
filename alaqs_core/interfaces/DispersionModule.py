from __future__ import absolute_import
from builtins import object
import __init__ #setup the paths for direct calls of the module

import logging              # For unit testing. Can be commented out for distribution
import os, sys
sys.path.append("..") # Adds higher directory to python modules path.

from PyQt5 import QtCore, QtGui, QtWidgets
import alaqsutils
import alaqsdblite

import logging
logger = logging.getLogger("alaqs.%s" % (__name__))

from collections import OrderedDict

# from ..modules.ui.ModuleConfigurationWidget import ModuleConfigurationWidget
from modules.ui.ModuleConfigurationWidget import ModuleConfigurationWidget

class DispersionModule(object):
    """
    Abstract interface to run dispersion models on calculated emissions
    """

    @staticmethod
    def getModuleName():
        return ""

    def __init__(self, values_dict = {}):
        self._name = values_dict["name"] if "name" in values_dict else None
        self._model = None

        self._enable = values_dict["enable"] if "enable" in values_dict else False
        self._configuration_widget = None

        self.setConfigurationWidget(OrderedDict([
            ("Enable" , QtWidgets.QCheckBox,)
        ]))

        self.getConfigurationWidget().initValues({
            "Enable" : False
        })

    def isEnabled(self):
        return self._enable

    def getConfigurationWidget(self):
        return self._configuration_widget
    def setConfigurationWidget(self, var):
        if isinstance(var, QtWidgets.QWidget):
            self._configuration_widget = var
        else:
            self._configuration_widget = ModuleConfigurationWidget(var)

    def getModel(self):
        return self._model
    def setModel(self, val):
        self._model = val

    def process(self, timeval, result, **kwargs):
        #result is of format [(Source, Emission)]
        return NotImplemented

    def endJob(self):
        return NotImplemented

