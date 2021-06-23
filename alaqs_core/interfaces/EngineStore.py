import os.path

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.Engine import Engine
from open_alaqs.alaqs_core.interfaces.EngineDatabases import \
    EngineEmissionIndicesDatabase, EngineModeDatabase, \
    HelicopterEngineEmissionIndicesDatabase
from open_alaqs.alaqs_core.tools.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.Store import Store

logger = get_logger(__name__)


class EngineStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'Engine' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {
                "engine_emission_indices_db": None,
                "engine_modes_db": None,
                "engine_start_emission_factors_db": None}
        Store.__init__(self)

        self._db_path = db_path

        #Emission indices
        self._emission_indices_db = None
        if  "engine_emission_indices_db" in db:
            if isinstance(db["engine_emission_indices_db"], EngineEmissionIndicesDatabase):
                self._emission_indices_db = db["engine_emission_indices_db"]
            elif isinstance(db["engine_emission_indices_db"], str) and os.path.isfile(db["engine_emission_indices_db"]):
                self._emission_indices_db =EngineEmissionIndicesDatabase(db["engine_emission_indices_db"])

        if self._emission_indices_db is None:
            self._emission_indices_db =EngineEmissionIndicesDatabase(db_path)

        self._emission_indices = self._emission_indices_db.getEngineEmissionIndices()

        #Engine Modes
        self._emission_modes_db = None
        if  "emission_modes_db" in db:
            if isinstance(db["emission_modes_db"], EngineModeDatabase):
                self._emission_modes_db = db["emission_modes_db"]
            elif isinstance(db["emission_modes_db"], str) and os.path.isfile(db["emission_modes_db"]):
                self._emission_modes_db = EngineModeDatabase(db["emission_modes_db"])

        if self._emission_modes_db is None:
            self._emission_modes_db = EngineModeDatabase(db_path)

        #update all emission indices with default mode-power-setting association deserialized from the db
        #for key_, em_dict_ in self._emission_modes_db.getEntries().items():
        #    mode_ = em_dict_["mode"] if "mode" in em_dict_ else None
        #    power_setting_ = em_dict_["thrust"] if "thrust" in em_dict_ else None
        #    if not (mode_ is None or power_setting_ is None):
        #        for ei_key, ei_object in self._emission_indices.items():
        #            ei_object.setModePowerSetting(mode_, power_setting_)

        #instantiate all engine objects
        self.initEngines()

    def initEngines(self):
        for engine_name, ei in list(self.getEngineEmissionIndices().items()):
            #add engine to store
            self.setObject(engine_name, Engine({"name":engine_name}))
            #associate each engine an emission-index object
            self.getObject(engine_name).setEmissionIndex(ei)

            #self.getObject(engine_name).setStartEmissionFactors(ei) #association of start ef by aircraft group! but information only available for movements ->set emission factor when instantiating aircraft object

    def getEngineEmissionIndicesDatabase(self):
        return self._emission_indices_db

    def setEngineEmissionIndicesDatabase(self, val):
        self._emission_indices_db = EngineEmissionIndicesDatabase(val)

    def getEngineEmissionIndices(self):
        return self._emission_indices

    def getEngineModeDatabase(self):
        return self._emission_modes_db

    def getDefaultPowerSetting(self, mode):
        for key_, em_dict_ in list(self._emission_modes_db.getEntries().items()):
            mode_ = em_dict_["mode"] if "mode" in em_dict_ else None
            if mode_.lower() ==  mode.lower():
                power_setting_ = em_dict_["thrust"] if "thrust" in em_dict_ else None
                return power_setting_
        return None


class HeliEngineStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'Engine' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {
                "engine_emission_indices_db": None,
                "engine_modes_db": None,
                "engine_start_emission_factors_db": None}

        Store.__init__(self)

        self._db_path = db_path

        # Emission indices
        self._emission_indices_db = None
        if "engine_emission_indices_db" in db:
            if isinstance(db["engine_emission_indices_db"],
                          HelicopterEngineEmissionIndicesDatabase):
                self._emission_indices_db = db["engine_emission_indices_db"]
            elif isinstance(db["engine_emission_indices_db"],
                            str) and os.path.isfile(
                    db["engine_emission_indices_db"]):
                self._emission_indices_db = HelicopterEngineEmissionIndicesDatabase(
                    db["engine_emission_indices_db"])

        if self._emission_indices_db is None:
            self._emission_indices_db = HelicopterEngineEmissionIndicesDatabase(
                db_path)

        self._emission_indices = self._emission_indices_db.getHeliEngineEmissionIndices()
        # self._emission_indices = self._emission_indices_db._heli_emission_indices

        #Engine Modes
        self._emission_modes_db = None
        # if  "emission_modes_db" in db:
        #     if isinstance(db["emission_modes_db"], EngineModeDatabase):
        #         self._emission_modes_db = db["emission_modes_db"]
        #     elif isinstance(db["emission_modes_db"], str) and os.path.isfile(db["emission_modes_db"]):
        #         self._emission_modes_db = EngineModeDatabase(db["emission_modes_db"])
        #
        # if self._emission_modes_db is None:
        #     self._emission_modes_db = EngineModeDatabase(db_path)

        self.initEngines()

    def initEngines(self):
        # for engine_name, ei in self.getHeliEngineEmissionIndices().items():
        for engine_name, ei in list(self._emission_indices_db.getHeliEngineEmissionIndices().items()):
            #add engine to store
            self.setObject(engine_name, Engine({"name":engine_name}))
            #associate each engine an emission-index object
            self.getObject(engine_name).setEmissionIndex(ei)

            # association of start ef by aircraft group! but information only available for movements ->set emission factor when instantiating aircraft object
            #self.getObject(engine_name).setStartEmissionFactors(ei)

    def getEngineEmissionIndicesDatabase(self):
        return self._emission_indices_db

    def setEngineEmissionIndicesDatabase(self, val):
        self._emission_indices_db = HelicopterEngineEmissionIndicesDatabase(val)

    def getEngineEmissionIndices(self):
        return self._emission_indices

    def getEngineModeDatabase(self):
        return self._emission_modes_db

    def getDefaultPowerSetting(self, mode):
        # for key_, em_dict_ in self._emission_modes_db.getEntries().items():
        #     mode_ = em_dict_["mode"] if "mode" in em_dict_ else None
        #     if mode_.lower() ==  mode.lower():
        #         power_setting_ = em_dict_["thrust"] if "thrust" in em_dict_ else None
        #         return power_setting_
        return None


# if __name__ == "__main__":
#     # create a logger for this module
#     logging.basicConfig(level=logging.DEBUG)
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
#     path_to_database = os.path.join("..", "..", "example", "CAEPport", "old", "06042020_out.alaqs")
#
#     engine_store = EngineStore(path_to_database)
#     heli_engine_store = HeliEngineStore(path_to_database)
#
#     # #for key, ei in engine_store.getEngineEmissionIndices().items():
#     # #    logger.info("Engine '%s'" %(key))
#     # #    logger.info(ei)
#     # for engine_name, engine in engine_store.getObjects().items():
#     #     logger.info(engine_name, engine.__repr__())
#     # #print engine_store.get()EngineEmissionIndicesDatabase