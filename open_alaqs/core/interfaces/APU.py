from collections import OrderedDict

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)
# defaultEI={
#             "fuel_kg_sec" : 0.,
#             "co_g_kg" : 0.,
#             "co2_g_kg" : 3.16*1000.,
#             "hc_g_kg" : 0.,
#             "nox_g_kg" : 0.,
#             "sox_g_kg" : 0.,
#             "pm10_g_kg" : 0.,
#             "p1_g_kg" : 0.,
#             "p2_g_kg": 0.,
#             "smoke_number" : 0.,
#             "smoke_number_maximum" : 0.,
#             "fuel_type"  : "",
#             "pm10_prefoa3_g_kg" : 0.,
#             "pm10_nonvol_g_kg" : 0.,
#             "pm10_sul_g_kg" : 0.,
#             "pm10_organic_g_kg" : 0.
# }


class APU:
    def __init__(self, val=None):
        if val is None:
            val = {}

        self._apu_id = str(val["apu_id"]) if "apu_id" in val else ""
        self._emissions = {}

        # [Number of Operations TimeMode [sec] * Emission IndexMode [kg/h] * 1000.0/3600.0] (in g/s)
        self._emissions["fuel_kg_sec"] = (
            val["fuel_kg_h"] * 1.0 / 3600 if "fuel_kg_h" in val else 0.0
        )
        self._emissions["co_g_s"] = (
            val["co_kg_h"] * 1 / 3.6 if "co_kg_h" in val else 0.0
        )
        self._emissions["hc_g_s"] = (
            val["hc_kg_h"] * 1 / 3.6 if "hc_kg_h" in val else 0.0
        )
        self._emissions["nox_g_s"] = (
            val["nox_kg_h"] * 1 / 3.6 if "nox_kg_h" in val else 0.0
        )
        self._emissions["sox_g_s"] = (
            val["sox_kg_h"] * 1 / 3.6 if "sox_kg_h" in val else 0.0
        )
        self._emissions["pm10_g_s"] = (
            val["pm10_kg_h"] * 1 / 3.6 if "pm10_kg_h" in val else 0.0
        )
        self._emissions["co2_g_s"] = (
            val["fuel_kg_h"] * 3.16 * 1000.0 / 3600 if "fuel_kg_h" in val else 0.0
        )

        # self._emissions["NL"] = {
        #     "fuel_kg_sec" : val["FF_NL_in_kg_s"] if "FF_NL_in_kg_s" in val else 0.,
        #     "co_g_s" : val["CO_NL_in_g_s"] if "CO_NL_in_g_s" in val else 0.,
        #     "hc_g_s" : val["HC_NL_in_g_s"] if "HC_NL_in_g_s" in val else 0.,
        #     "nox_g_s" : val["NOx_NL_in_g_s"] if "NOx_NL_in_g_s" in val else 0.,
        # }
        # self._emissions["NL"]["co2_g_s"] = self._emissions["NL"]["fuel_kg_sec"]*3.16*1000.
        #
        # self._emissions["NR"] = {
        #     "fuel_kg_sec" : val["FF_NR_in_kg_s"] if "FF_NR_in_kg_s" in val else 0.,
        #     "co_g_s" : val["CO_NR_in_g_s"] if "CO_NR_in_g_s" in val else 0.,
        #     "co2_g_s" : 3.16,
        #     "hc_g_s" : val["HC_NR_in_g_s"] if "HC_NR_in_g_s" in val else 0.,
        #     "nox_g_s" : val["NOx_NR_in_g_s"] if "NOx_NR_in_g_s" in val else 0.,
        # }
        # self._emissions["NR"]["co2_g_s"] = self._emissions["NR"]["fuel_kg_sec"]*3.16*1000.
        #
        # self._emissions["HL"] = {
        #     "fuel_kg_sec" : val["FF_HL_in_kg_s"] if "FF_HL_in_kg_s" in val else 0.,
        #     "co_g_s" : val["CO_HL_in_g_s"] if "CO_HL_in_g_s" in val else 0.,
        #     "co2_g_s" : 3.16,
        #     "hc_g_s" : val["HC_HL_in_g_s"] if "HC_HL_in_g_s" in val else 0.,
        #     "nox_g_s" : val["NOx_HL_in_g_s"] if "NOx_HL_in_g_s" in val else 0.,
        # }
        # self._emissions["HL"]["co2_g_s"] = self._emissions["HL"]["fuel_kg_sec"]*3.16*1000.

    def getName(self):
        return self._apu_id

    def getModes(self):
        return list(self._emissions.keys())

    def getEmissions(self, mode):
        if mode in self._emissions:
            return self._emissions[mode]
        return {}

    def setEmission(self, mode, ei):
        self._emissions[mode] = ei

    def __str__(self):
        val = "\n APU id '%s'" % (self.getName())
        for mode in self.getModes():
            val += "\n\t EI for '%s':" % (mode)
            val += "\n\t\t %f" % (self.getEmissions(mode))
        return val

    # def __str__(self):
    #     val = "\n APU id '%s'" % (self.get_APU_id())
    #     for mode in self.getModes():
    #         val += "\n\t Emissions in mode '%s':" % (mode)
    #         for key, value in self.getEmissions(mode).items():
    #             val += "\n\t\t %s: %f" % (key, value)
    #     return val


class APUStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'APU' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path
        self._db = APUDatabase(db_path, deserialize=True)
        self._apu_times = APUtimes(db_path, deserialize=True)
        self._times = {"REMOTE": {}, "PIER": {}, "CARGO": {}}

        # instantiate all objects
        self.initAPUs()

    def initAPUs(self):
        for key, apu_dict in list(self.getAPUDatabase().getEntries().items()):
            # add apu to store
            self.setObject(
                apu_dict["oid"] if "oid" in apu_dict else "unknown", APU(apu_dict)
            )

        try:
            for key, apu_t_dict in list(self._apu_times.getEntries().items()):
                if apu_t_dict["stand_type"] == "REMOTE":
                    self._times["REMOTE"].update(
                        {
                            apu_t_dict["ac_category"]: {
                                "arr_s": apu_t_dict["time_arr_min"] * 60.0,
                                "dep_s": apu_t_dict["time_dep_min"] * 60.0,
                            }
                        }
                    )
                elif apu_t_dict["stand_type"] == "PIER":
                    self._times["PIER"].update(
                        {
                            apu_t_dict["ac_category"]: {
                                "arr_s": apu_t_dict["time_arr_min"] * 60.0,
                                "dep_s": apu_t_dict["time_dep_min"] * 60.0,
                            }
                        }
                    )
                elif apu_t_dict["stand_type"] == "CARGO":
                    self._times["CARGO"].update(
                        {
                            apu_t_dict["ac_category"]: {
                                "arr_s": apu_t_dict["time_arr_min"] * 60.0,
                                "dep_s": apu_t_dict["time_dep_min"] * 60.0,
                            }
                        }
                    )
        except Exception as exc_:
            logger.error("initAPUs: %s" % exc_)

            # self._times["time_arr_min"] = apu_t_dict["time_arr_min"] if "time_arr_min" in apu_t_dict else None
            # self._times["time_dep_min"] = apu_t_dict["time_dep_min"] if "time_dep_min" in apu_t_dict else None

    def getAPUDatabase(self):
        return self._db

    def get_apu_times(self, ac_category):
        apu_dic = {}
        apu_dic[ac_category] = {}
        for stand_category in self._times:
            if ac_category in self._times[stand_category]:
                apu_dic[ac_category].update(
                    {stand_category: self._times[stand_category][ac_category]}
                )
        if apu_dic[ac_category]:
            return apu_dic
        else:
            return None


class APUDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to apu emissions as stored in the database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="default_aircraft_apu_ef",
        table_columns_type_dict=None,
        primary_key="",
        geometry_columns=None,
        deserialize=True,
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                    ("apu_id", "TEXT"),
                    ("fuel_kg_h", "DECIMAL"),
                    ("co_kg_h", "DECIMAL"),
                    ("hc_kg_h", "DECIMAL"),
                    ("nox_kg_h", "DECIMAL"),
                    ("sox_kg_h", "DECIMAL"),
                    ("pm10_kg_h", "DECIMAL"),
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

        if self._db_path and deserialize:
            self.deserialize()


class APUtimes(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to apu emissions as stored in the database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="default_apu_times",
        table_columns_type_dict=None,
        primary_key="",
        geometry_columns=None,
        deserialize=True,
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                    ("ac_category", "TEXT"),
                    ("stand_type", "TEXT"),
                    ("time_arr_min", "DECIMAL"),
                    ("time_dep_min", "DECIMAL"),
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

        if self._db_path and deserialize:
            self.deserialize()
