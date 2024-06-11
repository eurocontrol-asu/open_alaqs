from typing import Any, Optional

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.modules.ModuleConfigurationWidget import (
    ModuleConfigurationWidget,
    SettingsSchema,
)

logger = get_logger(__name__)


class OutputModule:
    """
    Abstract interface to handle calculation results (timestamp, source, emissions)
    """

    settings_schema: SettingsSchema = {}

    @staticmethod
    def getModuleName() -> str:
        return ""

    @staticmethod
    def getModuleDisplayName() -> str:
        return ""

    def __init__(self, values_dict: dict[str, Any]) -> None:
        self._database_path = values_dict.get("database_path", "")
        self._output_path = values_dict.get("output_path", "")
        self._name = values_dict.get("name", "")

    def setDatabasePath(self, val: str) -> None:
        self._database_path = val

    def getDatabasePath(self) -> str:
        return self._database_path

    def setOutputPath(self, val: str) -> None:
        self._output_path = val

    def getOutputPath(self) -> str:
        return self._output_path

    @classmethod
    def getConfigurationWidget2(cls) -> Optional[ModuleConfigurationWidget]:
        if not cls.settings_schema:
            return None

        return ModuleConfigurationWidget(cls.settings_schema)

    def beginJob(self):
        raise NotImplementedError()

    def process(self, timeval, result, **kwargs):
        # result is of format [(Source, Emission)]
        raise NotImplementedError()

    def endJob(self):
        raise NotImplementedError()
