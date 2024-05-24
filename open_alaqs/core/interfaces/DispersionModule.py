import sys

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.modules.ModuleConfigurationWidget import (
    ModuleConfigurationWidget,
    SettingsSchema,
)

sys.path.append("..")  # Adds higher directory to python modules path.
logger = get_logger(__name__)


class DispersionModule:
    """
    Abstract interface to run dispersion models on calculated emissions
    """

    settings_schema: SettingsSchema = {}

    @staticmethod
    def getModuleName():
        return ""

    @staticmethod
    def getModuleDisplayName():
        return ""

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        self._name = values_dict.get("name")
        self._model = None

    def isEnabled(self):
        return self._enable

    @classmethod
    def getConfigurationWidget(cls):
        if not cls.settings_schema:
            return None

        return ModuleConfigurationWidget(cls.settings_schema)

    def getModel(self):
        return self._model

    def setModel(self, val):
        self._model = val

    def process(self, timeval, result, **kwargs):
        # result is of format [(Source, Emission)]
        return NotImplemented

    def endJob(self):
        return NotImplemented
