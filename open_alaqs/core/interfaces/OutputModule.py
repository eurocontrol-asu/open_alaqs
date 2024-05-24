from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.modules.ModuleConfigurationWidget import (
    ModuleConfigurationWidget2,
    SettingsSchema,
)

logger = get_logger(__name__)


class OutputModule:
    """
    Abstract interface to handle calculation results (timestamp, source, emissions)
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

        self._database_path = values_dict.get("database_path")
        self._output_path = values_dict.get("output_path")
        self._name = values_dict.get("name")

    def setDatabasePath(self, val):
        self._database_path = val

    def getDatabasePath(self):
        return self._database_path

    def setOutputPath(self, val):
        self._output_path = val

    def getOutputPath(self):
        return self._output_path

    @classmethod
    def getConfigurationWidget2(cls):
        if not cls.settings_schema:
            return None

        return ModuleConfigurationWidget2(cls.settings_schema)

    def beginJob(self):
        return NotImplemented

    def process(self, timeval, result, **kwargs):
        # result is of format [(Source, Emission)]
        return NotImplemented

    def endJob(self):
        return NotImplemented
