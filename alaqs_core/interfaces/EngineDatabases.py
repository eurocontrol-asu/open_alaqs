from collections import OrderedDict

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.Engine import EngineEmissionIndex, \
    HelicopterEngineEmissionIndex
from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.tools.Singleton import Singleton

logger = get_logger(__name__)


class EngineEmissionFactorsStartDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to emission factors that are related to an engine start
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="default_aircraft_start_ef",
                 table_columns_type_dict=None,
                 primary_key=""):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY"),
                ("aircraft_group", "VARCHAR(23) NOT NULL"),
                ("aircraft_code", "VARCHAR(13)"),
                ("emission_unit", "VARCHAR(16)"),
                ("co", "DOUBLE PRECISION NULL"),
                ("hc", "DOUBLE PRECISION NULL"),
                ("nox", "DOUBLE PRECISION NULL"),
                ("sox", "DOUBLE PRECISION NULL"),
                ("pm10", "DOUBLE PRECISION NULL"),
                ("p1", "DOUBLE PRECISION NULL"),
                ("p2", "DOUBLE PRECISION NULL"),
            ])

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key)

        if self._db_path:
            self.deserialize()


class EngineModeDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to aircraft-engine-emission indices
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="default_aircraft_engine_mode",
                 table_columns_type_dict=None,
                 primary_key=""):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY"),
                ("mode", "VARCHAR(2)"),
                ("thrust", "DECIMAL NULL"),
                ("description", "TEXT")
            ])

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key)

        if self._db_path:
            self.deserialize()


class HelicopterEngineEmissionIndicesDatabase(SQLSerializable,
                                              metaclass=Singleton):

    """
    Class that grants access to aircraft-engine-emission indices
    """
    def __init__(self,
                 db_path_string,
                 table_name_string="default_helicopter_engine_ei",
                 table_columns_type_dict=None,
                 primary_key=""):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY"),
                ("engine_name", "TEXT"),
                ("engine_type", "TEXT"),
                ("max_shp_per_engine", "DECIMAL"),
                ("shp_correction_factor", "DECIMAL"),
                ("number_of_engines", "INTEGER"),
                ("gi1_time_min", "DECIMAL"),
                ("gi2_time_min", "DECIMAL"),
                ("to_time_min", "DECIMAL"),
                ("ap_time_min", "DECIMAL"),
                ("gi1_ff_per_engine_kg_s", "DECIMAL"),
                ("gi2_ff_per_engine_kg_s", "DECIMAL"),
                ("to_ff_per_engine_kg_s", "DECIMAL"),
                ("ap_ff_per_engine_kg_s", "DECIMAL"),
                ("gi1_einox_g_kg", "DECIMAL"),
                ("gi2_einox_g_kg", "DECIMAL"),
                ("to_einox_g_kg", "DECIMAL"),
                ("ap_einox_g_kg", "DECIMAL"),
                ("gi1_eihc_g_kg", "DECIMAL"),
                ("gi2_eihc_g_kg", "DECIMAL"),
                ("to_eihc_g_kg", "DECIMAL"),
                ("ap_eihc_g_kg", "DECIMAL"),
                ("gi1_eico_g_kg", "DECIMAL"),
                ("gi2_eico_g_kg", "DECIMAL"),
                ("to_eico_g_kg", "DECIMAL"),
                ("ap_eico_g_kg", "DECIMAL"),
                ("gi1_eipm_g_kg", "DECIMAL"),
                ("gi2_eipm_g_kg", "DECIMAL"),
                ("to_eipm_g_kg", "DECIMAL"),
                ("ap_eipm_g_kg", "DECIMAL")
            ])

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key)

        self._heli_emission_indices = OrderedDict()
        self._modes = ['GI1', 'GI2', 'TO', 'AP']

        if self._db_path:
            self.deserialize()
            self.initEmissionIndices()

    def getModes(self):
        return self._modes

    def initEmissionIndices(self):
        for ei_key, ei_val in list(self.getEntries().items()):
            id_name = ei_val["engine_name"] if ei_val["engine_name"] else ei_val["engine_full_name"]
            self.addEngineEmissionIndex(id_name, ei_val)

    def addEngineEmissionIndex(self, icaoIdentifier, ei_dict):
        if not icaoIdentifier in self._heli_emission_indices:
            self._heli_emission_indices[icaoIdentifier] = HelicopterEngineEmissionIndex()
        for mode in self.getModes():
            self._heli_emission_indices[icaoIdentifier].setObject(mode, ei_dict)

    def getHeliEngineEmissionIndices(self):
        return self._heli_emission_indices

    def hasHeliEngineEmissionIndex(self, icaoIdentifier, mode=""):
        if icaoIdentifier in self._heli_emission_indices:
            if mode:
                if mode in self._heli_emission_indices[icaoIdentifier].getModes():
                    return True
            else:
                return True
        return False

    def getHeliEngineEmissionIndex(self, icaoIdentifier="", mode="", defaultIfNotFound=False):
        if not icaoIdentifier:
            return self._heli_emission_indices
        if self.hasHeliEngineEmissionIndex(icaoIdentifier):
            if not mode:
                return self._heli_emission_indices[icaoIdentifier]
            else:
                if mode in self._heli_emission_indices[icaoIdentifier].getModes():
                    return self._heli_emission_indices[icaoIdentifier].getEmissionIndexByMode(mode)

        if not defaultIfNotFound:
            return None
        else:
            #ToDo: default
            return None


class EngineEmissionIndicesDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to aircraft-engine-emission indices
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="default_aircraft_engine_ei",
                 table_columns_type_dict=None,
                 primary_key=""):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY"),
                ("engine_type", "VARCHAR(1)"),
                ("engine_full_name", "TEXT"),
                ("engine_name", "TEXT"),
                ("thrust", "DECIMAL"),
                ("mode", "VARCHAR(2)"),
                ("fuel_kg_sec", "DECIMAL"),
                ("co_ei", "DECIMAL"),
                ("hc_ei", "DECIMAL"),
                ("nox_ei", "DECIMAL"),
                ("sox_ei", "DECIMAL"),
                ("pm10_ei", "DECIMAL"),
                ("p1_ei", "DECIMAL"),
                ("p2_ei", "INTEGER"),
                ("smoke_number", "DECIMAL"),
                ("smoke_number_maximum", "DECIMAL"),
                ("fuel_type", "TEXT"),
                ("manufacturer", "TEXT"),
                ("source", "TEXT"),
                ("remark", "TEXT"),
                ("status", "TEXT"),
                ("engine_name_type", "TEXT"),
                ("coolant", "VARCHAR(5)"),
                ("combustion_technology", "TEXT"),
                ("technology_age", "TEXT"),
                ("pm10_prefoa3", "DECIMAL"),
                ("pm10_nonvol", "DECIMAL"),
                ("pm10_sul", "DECIMAL"),
                ("pm10_organic", "DECIMAL"),
                ("nvpm_ei", "DECIMAL"),
                ("nvpm_number_ei", "DECIMAL"),
            ])

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key)

        self._emission_indices = OrderedDict()

        if self._db_path:
            self.deserialize()
            self.initEmissionIndices()

    def initEmissionIndices(self) -> None:
        for ei_key, ei_val in self.getEntries().items():
            id_name = ei_val["engine_name"] if ei_val["engine_name"] else \
                ei_val["engine_full_name"]
            self.addEngineEmissionIndex(id_name, ei_val)

    def addEngineEmissionIndex(self, icaoIdentifier: str,
                               ei_dict: dict) -> None:

        # Create an emission index
        if icaoIdentifier not in self._emission_indices:
            self._emission_indices[icaoIdentifier] = EngineEmissionIndex()

        # Set the values of the emission index
        self._emission_indices[icaoIdentifier].setObject(
            ei_dict.get("mode", "unknown"), ei_dict)

    def getEngineEmissionIndices(self):
        return self._emission_indices

    def hasEngineEmissionIndex(self, icaoIdentifier, mode=""):
        if icaoIdentifier in self._emission_indices:
            if mode:
                if mode in self._emission_indices[icaoIdentifier].getModes():
                    return True
            else:
                return True
        return False

    def getEngineEmissionIndex(self, icaoIdentifier="", mode="", defaultIfNotFound=False):
        if not icaoIdentifier:
            return self._emission_indices
        if self.hasEngineEmissionIndex(icaoIdentifier):
            if not mode:
                return self._emission_indices[icaoIdentifier]
            else:
                if mode in self._emission_indices[icaoIdentifier].getModes():
                    return self._emission_indices[icaoIdentifier].getEmissionIndexByMode(mode)

        if not defaultIfNotFound:
            return None
        else:
            #ToDo: default
            return None


# if __name__ == "__main__":
#     # create a logger for this module
#     logging.basicConfig(level=logging.DEBUG)
#
#     logger.setLevel(logging.DEBUG)
#     # create console handler and set level to debug
#     ch = logging.StreamHandler()
#     ch.setLevel(logging.DEBUG)
#     # create formatter
#     formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
#     # add formatter to ch
#     ch.setFormatter(formatter)
#     # add ch to logger
#     logger.addHandler(ch)
#
#     # path_to_database = os.path.join("..", "..", "example", "testing_cases.alaqs")
#     path_to_database = os.path.join("..", "..", "example", "CAEPport_training", "caepport_out.alaqs")
#
#     #modes = EngineModeDatabase(path_to_database)
#     #logger.debug(modes.getEntries())
#
#     #start_ef = EngineEmissionFactorsStartDatabase(path_to_database)
#     #logger.debug(start_ef.getEntries())
#
#     ei_db = EngineEmissionIndicesDatabase(path_to_database)
#     heli_ei_db = HelicopterEngineEmissionIndicesDatabase(path_to_database)
#     # logger.debug("Found %i emission indices" % (len(ei_db.getEngineEmissionIndices())))
#
#     # for entry in ei_db.getEntries():
#     #     if ei_db.getEntries()[entry]["engine_name"] == "1AA003":
#     #         for key in ei_db.getEntries()[entry]:
#     #             print "%s:%s %s" % (str(key), str(ei_db.getEntries()[entry][key]), type(ei_db.getEntries()[entry][key]))
#     #         print "\n"
#     #         logger.info("\n")
#
#     # for entry in modes.getEntries():
#     #    print modes.getEntries()[entry]