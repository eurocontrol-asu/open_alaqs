import os.path

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Engine import Engine
from open_alaqs.core.interfaces.EngineDatabases import (
    EngineEmissionIndicesDatabase,
    EngineModeDatabase,
)
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)


class EngineStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'Engine' objects
    """

    def __init__(self, db_path: str = "", db: dict = None):
        if db is None:
            db = {
                "engine_emission_indices_db": None,
                "engine_modes_db": None,
                "engine_start_emission_factors_db": None,
            }
        Store.__init__(self)

        self._db_path = db_path

        # Set the engine emission indices database
        self._emission_indices_db = None
        _engine_ei_db = db.get("engine_emission_indices_db")
        if isinstance(_engine_ei_db, EngineEmissionIndicesDatabase):
            self._emission_indices_db = _engine_ei_db
        elif isinstance(_engine_ei_db, str) and os.path.isfile(_engine_ei_db):
            self._emission_indices_db = EngineEmissionIndicesDatabase(_engine_ei_db)
        if self._emission_indices_db is None:
            self._emission_indices_db = EngineEmissionIndicesDatabase(db_path)

        # Get the emission indices
        self._emission_indices = self._emission_indices_db.getEngineEmissionIndices()

        # Set the engine modes database
        self._emission_modes_db = None
        _emission_modes_db = db.get("emission_modes_db")
        if isinstance(_emission_modes_db, EngineModeDatabase):
            self._emission_modes_db = _emission_modes_db
        elif isinstance(_emission_modes_db, str) and os.path.isfile(_emission_modes_db):
            self._emission_modes_db = EngineModeDatabase(_emission_modes_db)
        if self._emission_modes_db is None:
            self._emission_modes_db = EngineModeDatabase(db_path)

        # update all emission indices with default mode-power-setting association deserialized from the db
        # for key_, em_dict_ in self._emission_modes_db.getEntries().items():
        #    mode_ = em_dict_["mode"] if "mode" in em_dict_ else None
        #    power_setting_ = em_dict_["thrust"] if "thrust" in em_dict_ else None
        #    if not (mode_ is None or power_setting_ is None):
        #        for ei_key, ei_object in self._emission_indices.items():
        #            ei_object.setModePowerSetting(mode_, power_setting_)

        # instantiate all engine objects
        self.initEngines()

    def initEngines(self):
        for engine_name, ei in list(self.getEngineEmissionIndices().items()):
            # add engine to store
            self.setObject(engine_name, Engine({"name": engine_name}))
            # associate each engine an emission-index object
            self.getObject(engine_name).setEmissionIndex(ei)

            # self.getObject(engine_name).setStartEmissionFactors(ei) #association of start ef by aircraft group! but information only available for movements ->set emission factor when instantiating aircraft object

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
            if mode_.lower() == mode.lower():
                power_setting_ = em_dict_["thrust"] if "thrust" in em_dict_ else None
                return power_setting_
        return None
