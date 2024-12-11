import os
from collections import OrderedDict

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.APU import APUStore
from open_alaqs.core.interfaces.EmissionDynamics import (
    EmissionDynamicsStore,
    FlightStage,
)
from open_alaqs.core.interfaces.Emissions import Emission, PollutantType, PollutantUnit
from open_alaqs.core.interfaces.EngineDatabases import (
    EngineEmissionFactorsStartDatabase,
)
from open_alaqs.core.interfaces.EngineStore import EngineStore, HeliEngineStore
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.Singleton import Singleton
from open_alaqs.core.utils.utils import fuzzy_match

logger = get_logger(__name__)


class Aircraft:
    def __init__(self, val=None):
        if val is None:
            val = {}

        self._icao = str(val.get("icao", "unknown"))
        self._ac_group_code = str(val.get("ac_group_code") or "")
        self._ac_group = str(val.get("ac_group") or "")
        self._manufacturer = str(val.get("manufacturer") or "")
        self._name = str(val.get("name") or "")
        self._class = str(val.get("class") or "")
        self._mtow = int(val.get("mtow") or 0)
        self._engine_count = int(val.get("engine_count") or 0)
        self._departure_profile_name = str(val.get("departure_profile") or "")
        self._arrival_profile_name = str(val.get("arrival_profile") or "")
        self._bada_id = str(val.get("bada_id") or "")
        self._wake_category = str(val.get("wake_category") or "")
        self._apu_id = str(val.get("apu_id") or "")
        self._registration = str(val.get("aircraft_registration") or "")

        self._engine = None
        self._defaultengine = None
        self._apu = None
        self._dynamics = {"TX": None, "AP": None, "CL": None, "TO": None}

    def setRegistration(self, val: str):
        self._registration = val

    def getRegistration(self) -> str:
        return self._registration

    def getDefaultEngine(self) -> str:
        return self._defaultengine

    def setDefaultEngine(self, var):
        self._defaultengine = var

    def getDefaultDepartureProfileName(self):
        return self._departure_profile_name

    def setDefaultDepartureProfileName(self, var):
        self._departure_profile_name = var

    def getDefaultArrivalProfileName(self):
        return self._arrival_profile_name

    def setDefaultArrivalProfileName(self, var):
        self._arrival_profile_name = var

    def getApu(self):
        return self._apu

    def setApu(self, var):
        self._apu = var

    def getApuTimes(self):
        return self._apu_times

    def setApuTimes(self, var):
        self._apu_times = var

    def getApuEmissions(self):
        return self._apu_emissions

    def setApuEmissions(self, var):
        self._apu_emissions = var

    def getEmissionDynamicsByMode(self):
        return self._dynamics

    def setEmissionDynamicsByMode(self, mode, var):
        self._dynamics.update({mode: var})

    def getICAOIdentifier(self):
        return self._icao

    def setICAOIdentifier(self, val):
        self._icao = val

    def getType(self):
        return self.getICAOIdentifier()

    def setType(self, val):
        self.setICAOIdentifier(val)

    def getGroupCode(self):
        return self._ac_group_code

    def setGroupCode(self, var):
        self._ac_group_code = var

    def getManufacturer(self):
        return self._manufacturer

    def setManufacturer(self, var):
        self._manufacturer = var

    def getGroup(self) -> str:
        return self._ac_group

    def setGroup(self, var):
        self._ac_group = var

    def getClass(self):
        return self._class

    def setClass(self, var):
        self._class = var

    def getName(self):
        return self._name

    def getMTOW(self):
        return self._mtow

    def setMTOW(self, var):
        self._mtow = var

    def getEngineCount(self) -> int:
        return self._engine_count

    def setEngineCount(self, var: int):
        self._engine_count = var

    def getWakeCategory(self):
        return self._wake_category

    def setWakeCategory(self, var):
        self._wake_category = var

    def getAPUIdentifier(self):
        return self._apu_id

    def setAPUIdentifier(self, var):
        self._apu_id = var

    def __str__(self):
        val = "\n Aircraft of type '%s':" % (self.getICAOIdentifier())
        if self.getRegistration():
            val += "\n\t Registration: %s" % (self.getRegistration())
        val += "\n\t Name: %s" % (self.getName())
        val += "\n\t Manufacturer: %s" % (self.getManufacturer())
        val += "\n\t Wake category: %s" % (self.getWakeCategory())
        val += "\n\t Group: %s" % (self.getGroup())
        val += "\n\t MTOW: %i" % (self.getMTOW())
        # val += "\n\t Engine Name: %s" % (self._engine_icao)
        val += "\n\t Engine Count: %i" % (self.getEngineCount())
        val += "\n\t Default Engine: %s" % (
            "\n\t".join(str(self.getDefaultEngine()).split("\n"))
        )
        return val


class AircraftStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'Aircraft' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        self._aircraft_db = None
        if "aircraft_db" in db:
            if isinstance(db["aircraft_db"], AircraftDatabase):
                self._aircraft_db = db["aircraft_db"]
            elif isinstance(db["aircraft_db"], str) and os.path.isfile(
                db["aircraft_db"]
            ):
                self._aircraft_db = AircraftDatabase(db["aircraft_db"])

        if self._aircraft_db is None:
            self._aircraft_db = AircraftDatabase(db_path)

        # Engine-start-emission factors
        self._start_emission_factors_db = None
        if "engine_start_emission_factors_db" in db:
            if isinstance(
                db["engine_start_emission_factors_db"],
                EngineEmissionFactorsStartDatabase,
            ):
                self._start_emission_factors_db = db["engine_start_emission_factors_db"]
            elif isinstance(
                db["engine_start_emission_factors_db"], str
            ) and os.path.isfile(db["engine_start_emission_factors_db"]):
                self._start_emission_factors_db = EngineEmissionFactorsStartDatabase(
                    db["engine_start_emission_factors_db"]
                )

        if self._start_emission_factors_db is None:
            self._start_emission_factors_db = EngineEmissionFactorsStartDatabase(
                db_path
            )

        # instantiate all aircraft objects
        self.initAircraft()

    def getAPUStore(self):
        return APUStore(self._db_path)

    def getEmissionDynamicsStore(self):
        return EmissionDynamicsStore(self._db_path)

    def getEngineStartEmissionFactorsDatabase(self):
        return self._start_emission_factors_db

    def initAircraft(self):

        # unmatched_engines = []
        # ToDo: initiate only AC types in the study ?
        for key_, ac_dict in self.getAircraftDatabase().getEntries().items():
            # add aircraft to store
            ac = Aircraft(ac_dict)

            engine = (
                self.getEngineStore().getObject(ac_dict["engine"])
                or self.getEngineStore().getObject(ac_dict["engine_name"])
                or self.getHeliEngineStore().getObject(ac_dict["engine"])
                or self.getHeliEngineStore().getObject(ac_dict["engine_name"])
            )

            # If engine not found in the DB, the aircraft is ignored
            if not engine:
                logger.warning(
                    'Could not find engine with id "%s" for aircraft "%s"',
                    ac_dict["engine"],
                    ac.getICAOIdentifier(),
                )

                continue

            ac.setDefaultEngine(engine)

            if ac.getDefaultEngine() is not None:
                #   Main-engine-start-emission factors
                ac_group = fuzzy_match(
                    ac.getGroup(),
                    (
                        v["aircraft_group"]
                        for v in self.getEngineStartEmissionFactorsDatabase()
                        .getEntries()
                        .values()
                    ),
                )

                start_ei = Emission(
                    defaultValues={
                        "fuel_kg": 0.0,
                        "co_g": 0.0,
                        "co2_g": 0.0,
                        "hc_g": 0.0,
                        "nox_g": 0.0,
                        "sox_g": 0.0,
                        "pm10_g": 0.0,
                        "p1_g": 0.0,
                        "p2_g": 0.0,
                        "pm10_prefoa3_g": 0.0,
                        "pm10_nonvol_g": 0.0,
                        "pm10_sul_g": 0.0,
                        "pm10_organic_g": 0.0,
                    }
                )
                start_ei.setVerticalExtent({"z_min": 0, "z_max": 5})

                if ac_group is None:
                    ac.getDefaultEngine().setStartEmissions(
                        start_ei
                    )  # association of start ef by aircraft group!
                else:
                    for value in (
                        self.getEngineStartEmissionFactorsDatabase()
                        .getEntries()
                        .values()
                    ):
                        if value["aircraft_group"] == ac_group:
                            start_ei.add_value(
                                PollutantType.CO,
                                PollutantUnit.GRAM,
                                value["co"],
                            )
                            start_ei.add_value(
                                PollutantType.HC,
                                PollutantUnit.GRAM,
                                value["hc"],
                            )
                            start_ei.add_value(
                                PollutantType.NOx,
                                PollutantUnit.GRAM,
                                value["nox"],
                            )
                            start_ei.add_value(
                                PollutantType.SOx,
                                PollutantUnit.GRAM,
                                value["sox"],
                            )
                            start_ei.add_value(
                                PollutantType.PM10,
                                PollutantUnit.GRAM,
                                value["pm10"],
                            )
                            start_ei.add_value(
                                PollutantType.PM1,
                                PollutantUnit.GRAM,
                                value["p1"],
                            )
                            start_ei.add_value(
                                PollutantType.PM2,
                                PollutantUnit.GRAM,
                                value["p2"],
                            )

                    ac.getDefaultEngine().setStartEmissions(
                        start_ei
                    )  # association of start ef by aircraft group!

                if ac.getGroup():
                    apu_times_ = self.getAPUStore().get_apu_times(ac.getGroup())

                ac.setApuTimes(apu_times_)

                # emission factors
                ac.setApu(None)
                ac.setApuEmissions(None)

                apu_val_list = [
                    v.getName() for v in self.getAPUStore().getObjects().values()
                ]
                apu = fuzzy_match(ac._apu_id, apu_val_list)
                if apu:
                    apu_val_emissions = [
                        v._emissions for v in self.getAPUStore().getObjects().values()
                    ]
                    ac.setApu(apu)
                    ac.setApuEmissions(apu_val_emissions[apu_val_list.index(apu)])

            # TODO OPENGIS.ch: Why do we rename the group from the `default_aircraft` - "HELICOPTER LIGHT", "HELICOPTER HEAVY", etc, to "HELI SMALL" and "HELI LARGE" as in `default_emission_dynamics`?
            # Ideally I would recommend all these values to be added to `default_emission_dynamics` and remove the renaming.
            # If really needed, this should be a method of the `Aircraft` class.
            if (ac.getGroup() == "HELICOPTER") or (ac.getGroup() == "HELICOPTER LIGHT"):
                dynamic_group = "HELI SMALL"
            elif (
                (ac.getGroup() == "HELICOPTER HEAVY")
                or (ac.getGroup() == "HELICOPTER LARGE")
                or (ac.getGroup() == "HELICOPTER MEDIUM")
            ):
                dynamic_group = "HELI LARGE"
            else:
                dynamic_group = ac.getGroup()

            emission_dynamics_map = (
                self.getEmissionDynamicsStore().get_emissions_dynamics()
            )

            for flight_stage in FlightStage:
                ac.setEmissionDynamicsByMode(
                    flight_stage.value,
                    emission_dynamics_map[dynamic_group][flight_stage],
                )

            self.setObject(ac.getICAOIdentifier(), ac)

    def getAircraftDatabase(self):
        return self._aircraft_db

    def getEngineStore(self):
        return EngineStore(self._db_path)

    def getHeliEngineStore(self):
        return HeliEngineStore(self._db_path)


class AircraftDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to default_aircraft table in the spatialite database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="default_aircraft",
        table_columns_type_dict=None,
        primary_key="",
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY"),
                    ("icao", "TEXT"),
                    ("ac_group_code", "TEXT"),
                    ("ac_group", "TEXT"),
                    ("manufacturer", "TEXT"),
                    ("name", "TEXT"),
                    ("class", "TEXT"),
                    ("mtow", "DECIMAL"),
                    ("engine_count", "INTEGER"),
                    ("engine_name", "TEXT"),
                    ("engine", "TEXT"),
                    ("departure_profile", "TEXT"),
                    ("arrival_profile", "TEXT"),
                    ("bada_id", "TEXT"),
                    ("wake_category", "TEXT"),
                    ("apu_id", "TEXT"),
                ]
            )

        SQLSerializable.__init__(
            self,
            db_path_string,
            table_name_string,
            table_columns_type_dict,
            primary_key,
        )

        if self._db_path:
            self.deserialize()
