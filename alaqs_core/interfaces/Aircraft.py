import difflib
import logging
import os
from collections import OrderedDict

from open_alaqs.alaqs_core.interfaces.APU import APUStore
from open_alaqs.alaqs_core.interfaces.EmissionDynamics import \
    EmissionDynamicsStore
from open_alaqs.alaqs_core.interfaces.Emissions import Emission
from open_alaqs.alaqs_core.interfaces.EngineDatabases import \
    EngineEmissionFactorsStartDatabase
from open_alaqs.alaqs_core.interfaces.EngineStore import EngineStore, \
    HeliEngineStore
from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.interfaces.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.Store import Store

logger = logging.getLogger("__alaqs__.%s" % __name__)


class Aircraft:
    def __init__(self, val=None):
        if val is None:
            val = {}

        self._icao = str(val["icao"]) if "icao" in val else "unknown"
        self._ac_group_code=str(val["ac_group_code"]) if "ac_group_code" in val else ""
        self._ac_group=str(val["ac_group"]) if "ac_group" in val else ""
        self._manufacturer=str(val["manufacturer"]) if "manufacturer" in val else ""
        self._name=str(val["name"]) if "name" in val else ""
        self._class=str(val["class"]) if "class" in val else ""
        self._mtow =int(val["mtow"]) if "mtow" in val and val["mtow"] else 0
        self._engine_count =int(val["engine_count"]) if "engine_count" in val and val["engine_count"] else 0
        self._departure_profile_name=str(val["departure_profile"]) if "departure_profile" in val else ""
        self._arrival_profile_name=str(val["arrival_profile"]) if "arrival_profile" in val else ""
        self._bada_id=str(val["bada_id"]) if "bada_id" in val else ""
        self._wake_category=str(val["wake_category"]) if "wake_category" in val else ""
        self._apu_id =str(val["apu_id"]) if "apu_id" in val else ""
        self._registration = str(val["aircraft_registration"]) if "aircraft_registration" in val else ""

        self._engine = None
        self._defaultengine = None
        self._apu = None
        self._dynamics = {"TX": None, "AP": None, "CL": None, "TO": None}

    def setRegistration(self, val):
        self._registration = val
    def getRegistration(self):
        return self._registration
    def getDefaultEngine(self):
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
        self._dynamics.update({mode:var})

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
    def getGroup(self):
        return self._ac_group
    def setGroup(self, var):
        self._ac_group = var
    def getClass(self):
        return self._class
    def setClass(self, var):
        self._class = var
    def getName(self):
        return self._name
    def setName(self, var):
        self._name = var
    def getMTOW(self):
        return self._mtow
    def setMTOW(self, var):
        self._mtow = var

    def getEngineCount(self):
        return self._engine_count
    def setEngineCount(self, var):
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
        #val += "\n\t Engine Name: %s" % (self._engine_icao)
        val += "\n\t Engine Count: %i" % (self.getEngineCount())
        val += "\n\t Default Engine: %s" % ("\n\t".join(str(self.getDefaultEngine()).split("\n")))
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
            elif isinstance(db["aircraft_db"], str) and os.path.isfile(db["aircraft_db"]):
                self._aircraft_db = AircraftDatabase(db["aircraft_db"])

        if self._aircraft_db is None:
            self._aircraft_db = AircraftDatabase(db_path)

        #Engine-start-emission factors
        self._start_emission_factors_db = None
        if  "engine_start_emission_factors_db" in db:
            if isinstance(db["engine_start_emission_factors_db"], EngineEmissionFactorsStartDatabase):
                self._start_emission_factors_db = db["engine_start_emission_factors_db"]
            elif isinstance(db["engine_start_emission_factors_db"], str) and os.path.isfile(db["engine_start_emission_factors_db"]):
                self._start_emission_factors_db = EngineEmissionFactorsStartDatabase(db["engine_start_emission_factors_db"])

        if self._start_emission_factors_db is None:
            self._start_emission_factors_db = EngineEmissionFactorsStartDatabase(db_path)

        #instantiate all aircraft objects
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

            try:
                #add aircraft to store
                ac = Aircraft(ac_dict)
                # if ac.getGroup() == "HELICOPTER":
                #
                #     if "engine_name" in ac_dict.keys() and \
                #             self.getHelicopterEngineStore().getHeliEngineEmissionIndices().has_key(ac_dict["engine_name"]):
                #
                #         heli_eng = Engine(ac_dict["engine_name"])
                #         heli_eng.setName(ac_dict["engine_name"])
                #         heli_eng_ei = self.getHelicopterEngineStore().getHeliEngineEmissionIndices().get(ac_dict["engine_name"])
                #         heli_eng.setEmissionIndex(heli_eng_ei.getObjects())
                #         # start_ei = Emission(defaultValues={"fuel_kg" : 0.,
                #         #     "co_g" : 0.,
                #         #     "co2_g" : 0.,
                #         #     "hc_g" : 0.,
                #         #     "nox_g" : 0.,
                #         #     "sox_g" : 0.,
                #         #     "pm10_g" : 0.,
                #         #     "p1_g" : 0.,
                #         #     "p2_g": 0.,
                #         #     "pm10_prefoa3_g" : 0.,
                #         #     "pm10_nonvol_g" : 0.,
                #         #     "pm10_sul_g" : 0.,
                #         #     "pm10_organic_g" : 0.
                #         # })
                #         # start_ei.setVerticalExtent({'z_min': 0, 'z_max': 5})
                #         ac.setDefaultEngine(heli_eng)
                #         # ac.getDefaultEngine().setStartEmissions(start_ei)
                #         # emission factors
                #         ac.setApu(None)
                #         ac.setApuEmissions(None)
                #     else:
                #         logger.warning("Could not find engine with id '%s' for HELICOPTER %s"%(ac_dict["engine"],
                #                                                                                ac.getICAOIdentifier()))
                #         continue

                #default engine assignment
                if "engine" in ac_dict and self.getEngineStore().hasKey(ac_dict["engine"]):
                    ac.setDefaultEngine(self.getEngineStore().getObject(ac_dict["engine"]))

                elif "engine" in ac_dict and not self.getEngineStore().hasKey(ac_dict["engine"]):
                    if self.getEngineStore().hasKey(ac_dict["engine_name"]):
                        logger.info("Engine sub %s for %s"%(ac_dict["engine_name"], ac_dict["engine"]))
                        ac.setDefaultEngine(self.getEngineStore().getObject(ac_dict["engine_name"]))

                # try HELICOPTER DB
                elif "engine_name" in ac_dict and self.getHeliEngineStore().hasKey(ac_dict["engine_name"]):
                    ac.setDefaultEngine(self.getHeliEngineStore().getObject(ac_dict["engine_name"]))

                else:
                    # If engine not found in the DB, the aircraft is ignored
                    # if not ac_dict["engine"] in unmatched_engines:
                    #     unmatched_engines.append(ac_dict["engine"])
                    logger.warning("Could not find engine with id '%s' for AC %s"%(ac_dict["engine"], ac.getICAOIdentifier()))
                    continue
                    # return

                if not ac.getDefaultEngine() is None:
                    #   Main-engine-start-emission factors
                    matched = difflib.get_close_matches(ac.getGroup(), [values["aircraft_group"]
                                for key, values in list(self.getEngineStartEmissionFactorsDatabase().getEntries().items())])
                    ac_group = matched[0] if matched else None

                    start_ei = Emission(defaultValues={"fuel_kg" : 0.,
                        "co_g" : 0.,
                        "co2_g" : 0.,
                        "hc_g" : 0.,
                        "nox_g" : 0.,
                        "sox_g" : 0.,
                        "pm10_g" : 0.,
                        "p1_g" : 0.,
                        "p2_g": 0.,
                        "pm10_prefoa3_g" : 0.,
                        "pm10_nonvol_g" : 0.,
                        "pm10_sul_g" : 0.,
                        "pm10_organic_g" : 0.
                    })
                    start_ei.setVerticalExtent({'z_min': 0, 'z_max': 5})

                    if ac_group is None:
                        ac.getDefaultEngine().setStartEmissions(start_ei) # association of start ef by aircraft group!
                    else:
                        for key, value in list(self.getEngineStartEmissionFactorsDatabase().getEntries().items()):
                            if value["aircraft_group"] == ac_group:
                                start_ei.addCO(value["co"])
                                start_ei.addHC(value["hc"])
                                start_ei.addNOx(value["nox"])
                                start_ei.addSOx(value["sox"])
                                start_ei.addPM10(value["pm10"])
                                start_ei.addPM1(value["p1"])
                                start_ei.addPM2(value["p2"])
                        ac.getDefaultEngine().setStartEmissions(start_ei) #association of start ef by aircraft group!

                    apu_group = None
                    # APU infos:

                    # times
                    apu_times = {
                        "REMOTE":{"arr":0, "dep":0},
                         "PIER":{"arr":0, "dep":0},
                         "CARGO":{"arr":0, "dep":0}
                                 }
                    try:
                        if ac.getGroup():
                            apu_times_ = self.getAPUStore().get_apu_times(ac.getGroup())
                    except Exception as exc_:
                        logger.error("Problem with assigning APU times %s"%exc_)
                    ac.setApuTimes(apu_times_)

                    # emission factors
                    ac.setApu(None)
                    ac.setApuEmissions(None)
                    try:
                        if "apu_id" in ac_dict:
                            apu_val_list = [values_.getName() for key_, values_ in list(self.getAPUStore().getObjects().items())]
                            apu_val_emissions = [values_._emissions for key_, values_ in list(self.getAPUStore().getObjects().items())]
                            matched = difflib.get_close_matches(ac._apu_id, apu_val_list)
                            if matched:
                                ac.setApu(matched[0])
                                ac.setApuEmissions(apu_val_emissions[apu_val_list.index(matched[0])])
                    except Exception as exc_:
                        logger.error("Problem with assigning APU id %s" % exc_)

                # emission factors
                # matched = difflib.get_close_matches(ac.getGroup(), [values.getAircraftGroup()
                #                                         for key, values in self.getAPUStore().getObjects().items()])
                #
                # if matched:
                #     apu_group = matched[0]
                #     for key, apu in self.getAPUStore().getObjects().items():
                #         if apu.getAircraftGroup() == apu_group:
                #             ac.setApu(apu)
                # else:
                #     # logger.warning("Did not find apu emission factors for aircraft '%s' (%s). Update the table 'default_apu_ef'." % (ac.getICAOIdentifier(), ac.getGroup()))
                #     pass

                sas_group = None
                group_ = None

                if (ac.getGroup() == 'HELICOPTER') or (ac.getGroup() == 'HELICOPTER LIGHT'):
                    group_ = "HELI SMALL"
                elif (ac.getGroup() == 'HELICOPTER HEAVY') or (ac.getGroup() == 'HELICOPTER LARGE') \
                        or (ac.getGroup() == 'HELICOPTER MEDIUM'):
                    group_ = "HELI LARGE"
                else:
                    group_ = ac.getGroup()

                # Smooth and Shift factors
                matched = difflib.get_close_matches(group_, [values.getDynamicsGroup() for key, values in
                                                        list(self.getEmissionDynamicsStore().getObjects().items())])
                if matched:
                    sas_group = matched[0]
                    for key, sas in list(self.getEmissionDynamicsStore().getObjects().items()):
                        if group_ in sas.getDynamicsGroup():
                            if "TX" in sas.getDynamicsGroup():
                                ac.setEmissionDynamicsByMode("TX", sas)
                            elif "CL" in sas.getDynamicsGroup():
                                ac.setEmissionDynamicsByMode("CL", sas)
                            if "TO" in sas.getDynamicsGroup():
                                ac.setEmissionDynamicsByMode("TO", sas)
                            elif "AP" in sas.getDynamicsGroup():
                                ac.setEmissionDynamicsByMode("AP", sas)

                self.setObject(ac.getICAOIdentifier(), ac)

            except Exception as exc_:
                print(exc_)
                continue


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

    def __init__(self,
                 db_path_string,
                 table_name_string="default_aircraft",
                 table_columns_type_dict=None,
                 primary_key=""
                 ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
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
                ("apu_id", "TEXT")
            ])

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key)

        if self._db_path:
            self.deserialize()

# if __name__ == "__main__":
#     # from PyQt4 import QtGui
#     # #from python_qt_binding import QtGui, QtCore  # new imports
#     # app = QtGui.QApplication(sys.argv)
#
#     # create a logger for this module
#     # create console handler and set level to debug
#     # logging.basicConfig(level=logging.DEBUG)
#     # logger.setLevel(logging.DEBUG)
#
#     # path_to_database = os.path.join("..", "..", "example", "test_movs.alaqs")
#     path_to_database = os.path.join("..", "..", "example", "CAEPport", "old", "02042020_out.alaqs")
#
#     if not os.path.isfile(path_to_database):
#         # fix_print_with_import
#         print("Database %s not found"%path_to_database)
#
#     Aircraft_store = AircraftStore(path_to_database)
#     engine_store = list(Aircraft_store.getEngineStore().getObjects().keys())
#     h_engine_store = list(Aircraft_store.getHeliEngineStore().getObjects().keys())
#
#     # from Movement import MovementStore
#     # movement_store = MovementStore(path_to_database)
#
#     testAC = ['L410', 'AT45', 'AT72', 'B763']
#     # testEN = ['T034', 'T794', '1CM007', '1CM007', '6AL006', '6GE093']
#
#     for i, ac_key in enumerate(testAC):
#         # if ac_key not in AircraftStore(path_to_database).getObjects().keys():
#         if not Aircraft_store.hasKey(ac_key):
#             # fix_print_with_import
#             print("Could not find aircraft associated to type '%s'" % (ac_key))
#         else:
#             acs = Aircraft_store.getObject(ac_key)
#             print(acs)
#         # break
#
#     #         # break
#     #         ac_new = None
#     #         matched = difflib.get_close_matches(testEN[i], store.getEngineStore().getObjects().keys())
#     #         if matched:
#     #             # ac_new = matched[0]
#     #             print "Matched aircraft type '%s' to %s'." % (testEN[i], matched)
#     #             # ac_new = matched[0]
#     #             # if not ac_new.lower() == ac_key.lower():
#     #             #     print "Matched aircraft type '%s' to %s'." % (ac_key, ac_new)
#     #         else:
#     #             print "Skipping movement for aircraft associated to type '%s'." % (ac_key)
#     #             continue
#
#
#     # for id, ac_ in Aircraft_store.getObjects().items():
#     #     print id, ac_.getName(), ac_.getGroup()
#     #     print ac_.getApu(), ac_.getApuTimes(), ac_.getApuEmissions()
#     #     print "--------"
#         # #logger.debug(id, val)