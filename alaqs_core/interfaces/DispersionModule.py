import sys
import logging
from collections import OrderedDict

from PyQt5 import QtWidgets

from open_alaqs.alaqs_core.modules.ui.ModuleConfigurationWidget import \
    ModuleConfigurationWidget

sys.path.append("..")  # Adds higher directory to python modules path.
logger = logging.getLogger("alaqs.%s" % __name__)


class DispersionModule:
    """
    Abstract interface to run dispersion models on calculated emissions
    """

    @staticmethod
    def getModuleName():
        return ""

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        self._name = values_dict.get("name")
        self._model = None

        self._enable = values_dict.get("enable", False)
        self._configuration_widget = None

        self.setConfigurationWidget(OrderedDict([
            ("Enable", QtWidgets.QCheckBox,)
        ]))

        self.getConfigurationWidget().initValues({
            "Enable": False
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
        # result is of format [(Source, Emission)]
        return NotImplemented

    def endJob(self):
        return NotImplemented
