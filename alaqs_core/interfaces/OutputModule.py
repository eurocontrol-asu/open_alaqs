from PyQt5 import QtWidgets

from open_alaqs.alaqs_core import alaqslogging
from open_alaqs.alaqs_core.modules.ui.ModuleConfigurationWidget import \
    ModuleConfigurationWidget

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


class OutputModule:
    """
    Abstract interface to handle calculation results (timestamp, source, emissions)
    """

    @staticmethod
    def getModuleName():
        return ""

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}

        self._database_path = values_dict.get("database_path")
        self._output_path = values_dict.get("output_path")
        self._name = values_dict.get("name")
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
        # result is of format [(Source, Emission)]
        return NotImplemented

    def endJob(self):
        return NotImplemented
