from collections import OrderedDict

from qgis.PyQt import QtWidgets

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)


class SQLiteOutputModule(OutputModule):
    """
    Module to handle sql writeout of emission-calculation results (timestamp,
     source, total_emissions_)
    """

    @staticmethod
    def getModuleName():
        return "SQLiteOutputModule"

    @staticmethod
    def getModuleDisplayName():
        return "SQLite"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        OutputModule.__init__(self, values_dict)
        self._isDetailedOutput = values_dict.get(
            "Detailed Output", values_dict.get("detailed output", False)
        )

        self.setConfigurationWidget(
            OrderedDict([("Detailed Output", QtWidgets.QCheckBox)])
        )

        self.getConfigurationWidget().initValues({"Detailed Output": False})

    def beginJob(self):
        # initialize database connections
        self._db = None
        self.setOutputPath(
            QtWidgets.QFileDialog.getSaveFileName(
                None, "Save results as SQLite file", ".", "'SQLite (*.db)'"
            )
        )

        if self.getOutputPath()[0] is not None:
            self._db = EmissionCalculationResultDatabase(self.getOutputPath()[0])

        if self._db is not None:
            self._db.create_table(self.getOutputPath()[0])

    def process(self, timeval, result, **kwargs):
        # result is of format [(Source, Emission)]

        rows_ = []
        if not self._isDetailedOutput:
            total_emissions_ = sum([sum(emissions_) for (source, emissions_) in result])
            rows_.append(
                {
                    "time": timeval,
                    "source_id": "total",
                    "co_kg": total_emissions_.getCO(unit="kg")[0],
                    "co2_kg": total_emissions_.getCO2(unit="kg")[0],
                    "hc_kg": total_emissions_.getHC(unit="kg")[0],
                    "nox_kg": total_emissions_.getNOx(unit="kg")[0],
                    "sox_kg": total_emissions_.getSOx(unit="kg")[0],
                    "pmtotal_kg": total_emissions_.getPM10(unit="kg")[0],
                    "pm01_kg": total_emissions_.getPM1(unit="kg")[0],
                    "pm25_kg": total_emissions_.getPM2(unit="kg")[0],
                    "pmsul_kg": total_emissions_.getPM10Sul(unit="kg")[0],
                    "pmvolatile_kg": total_emissions_.getPM10Organic(unit="kg")[0],
                    "pmnonvolatile_kg": total_emissions_.getnvPM(unit="kg")[0],
                    "pmnonvolatilenumber_kg": total_emissions_.getnvPMnumber(unit="kg")[
                        0
                    ],
                }
            )
        else:
            for (source, emissions_) in result:
                rows_.append(
                    {
                        "time": timeval,
                        "source_id": source.getName(),
                        "co_kg": sum(emissions_).getCO(unit="kg")[0],
                        "co2_kg": sum(emissions_).getCO2(unit="kg")[0],
                        "hc_kg": sum(emissions_).getHC(unit="kg")[0],
                        "nox_kg": sum(emissions_).getNOx(unit="kg")[0],
                        "sox_kg": sum(emissions_).getSOx(unit="kg")[0],
                        "pmtotal_kg": sum(emissions_).getPM10(unit="kg")[0],
                        "pm01_kg": sum(emissions_).getPM1(unit="kg")[0],
                        "pm25_kg": sum(emissions_).getPM2(unit="kg")[0],
                        "pmsul_kg": sum(emissions_).getPM10Sul(unit="kg")[0],
                        "pmvolatile_kg": sum(emissions_).getPM10Organic(unit="kg")[0],
                        "pmnonvolatile_kg": sum(emissions_).getnvPM(unit="kg")[0],
                        "pmnonvolatilenumber_kg": sum(emissions_).getnvPMnumber(
                            unit="kg"
                        )[0],
                    }
                )

        if rows_ and self._db is not None:
            self._db.insert_rows(self.getOutputPath()[0], rows_)

    def endJob(self):
        pass


class EmissionCalculationResultDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to table in the spatialite database where results
     can be stored in
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="emission_calculation_result",
        table_columns_type_dict=None,
        primary_key="time",
        geometry_columns=None,
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("time", "DATETIME"),
                    ("source_id", "TEXT"),
                    ("co_kg", "DECIMAL"),
                    ("co2_kg", "DECIMAL"),
                    ("hc_kg", "DECIMAL"),
                    ("nox_kg", "DECIMAL"),
                    ("sox_kg", "DECIMAL"),
                    ("pmtotal_kg", "DECIMAL"),
                    ("pm01_kg", "DECIMAL"),
                    ("pm25_kg", "DECIMAL"),
                    ("pmsul_kg", "DECIMAL"),
                    ("pmvolatile_kg", "DECIMAL"),
                    ("pmnonvolatile_kg", "DECIMAL"),
                    ("pmnonvolatile_number", "DECIMAL"),
                ]
            )
        if geometry_columns is None:
            geometry_columns = []

        SQLSerializable.__init__(
            self,
            db_path_string,
            table_name_string,
            table_columns_type_dict,
            primary_key,
            geometry_columns,
        )
