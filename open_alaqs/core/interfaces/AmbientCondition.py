import os
from collections import OrderedDict

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools import conversion
from open_alaqs.core.tools.csv_interface import read_csv_to_dict
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)


# Single source of truth for the meteorological CSV column schema. Used both
# by AmbientCondition.initAmbientCondition (load-time validation/parsing) and
# by openalaqsdialog.OpenAlaqsInventory.examine_met_file (file-picker
# validation in the Generate Emission Inventory dialog). Keeping the two
# call sites pinned to one constant prevents drift -- a previous version
# had `RelativeHumidity(%)` and `SeaLevelPressure(mb)` hardcoded in the GUI
# validator while the loader expected `(0-1)` and `(Pa)`, causing a
# headers-do-not-match popup on every CSV that satisfied the loader.
#
# Map: CSV column name (with units) -> internal field name passed to
# AmbientCondition.__init__ via ambientcondition_dict.
METEO_CSV_HEADERS = {
    "Scenario": "Scenario",
    "DateTime(YYYY-mm-dd hh:mm:ss)": "DateTime",
    "Temperature(K)": "Temperature",
    "Humidity(kg_water/kg_dry_air)": "Humidity",
    "RelativeHumidity(0-1)": "RelativeHumidity",
    "SeaLevelPressure(Pa)": "SeaLevelPressure",
    "WindSpeed(m/s)": "WindSpeed",
    "WindDirection(degrees)": "WindDirection",
    "ObukhovLength(m)": "ObukhovLength",
    "MixingHeight(m)": "MixingHeight",
}


class AmbientCondition:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._id = str(val["id"]) if "id" in val else None
        self._scenario = str(val["Scenario"]) if "Scenario" in val else "default"
        self._date = (
            conversion.convertTimeToSeconds(val["DateTime"])
            if "DateTime" in val
            else 0.0
        )
        # defaults are ISA conditions
        self._temperature_in_K = (
            conversion.convertToFloat(val["Temperature"], default=288.15)
            if "Temperature" in val
            else 288.15
        )
        self._relative_humidity = (
            conversion.convertToFloat(val["RelativeHumidity"], default=0.6)
            if "RelativeHumidity" in val
            else 0.6
        )
        self._humidity = (
            conversion.convertToFloat(val["Humidity"], default=0.00634)
            if "Humidity" in val
            else 0.00634
        )
        self._sealevel_pressure_Pa = (
            conversion.convertToFloat(val["SeaLevelPressure"], default=1013.25 * 100.0)
            if "SeaLevelPressure" in val
            else 1013.25 * 100.0
        )
        self._wind_speed_in_m_s = (
            conversion.convertToFloat(val["WindSpeed"], default=0.0)
            if "WindSpeed" in val
            else 0.0
        )
        self._wind_direction_degrees = (
            conversion.convertToFloat(val["WindDirection"], default=0.0)
            if "WindDirection" in val
            else 0.0
        )
        self._mixing_height_m = (
            conversion.convertToFloat(
                val["MixingHeight"], default=conversion.convertFeetToMeters(3000.0)
            )
            if "MixingHeight" in val
            else conversion.convertFeetToMeters(3000.0)
        )
        self._speed_of_sound_in_m_s = (
            conversion.convertToFloat(val["SpeedOfSound"], default=340.29)
            if "SpeedOfSound" in val
            else 340.29
        )
        self._obukhov_length = (
            conversion.convertToFloat(val["ObukhovLength"], default=99999.0)
            if "ObukhovLength" in val
            else 99999.0
        )

    def getId(self):
        return self._id

    def setId(self, var):
        self._id = var

    def getScenario(self):
        return self._scenario

    def setScenario(self, var):
        self._scenario = var

    def getDate(self):
        return self._date

    def setDate(self, var):
        self._date = var

    def getDateAsString(self):
        return conversion.convertSecondsToTimeString(self.getDate())

    def getTemperature(self):
        return self._temperature_in_K

    def setTemperature(self, var):
        self._temperature_in_K = var

    def getRelativeHumidity(self):
        return self._relative_humidity

    def setRelativeHumidity(self, var):
        self._relative_humidity = var

    def getHumidity(self):
        return self._humidity

    def setHumidity(self, var):
        self._humidity = var

    def getPressure(self):
        return self._sealevel_pressure_Pa

    def setPressure(self, var):
        self._sealevel_pressure_Pa = var

    def getWindSpeed(self):
        return self._wind_speed_in_m_s

    def setWindSpeed(self, var):
        self._wind_speed_in_m_s = var

    def getWindDirection(self):
        return self._wind_direction_degrees

    def setWindDirection(self, var):
        self._wind_direction_degrees = var

    def getMixingHeight(self):
        return self._mixing_height_m

    def setMixingHeight(self, var):
        self._mixing_height_m = var

    def getSpeedOfSound(self):
        return self._speed_of_sound_in_m_s

    def setSpeedOfSound(self, var):
        self._speed_of_sound_in_m_s = var

    def getObukhovLength(self):
        return self._obukhov_length

    def setObukhovLength(self, var):
        self._obukhov_length = var

    def __str__(self):
        val = "\n AmbientCondition with id '%s' for scenario '%s' at date '%s'" % (
            self.getId(),
            self.getScenario(),
            self.getDateAsString(),
        )
        val += "\n\t Temperature [K]: %f" % (self.getTemperature())
        val += "\n\t Humidity [kg water / kg dry air]: %f" % (self.getHumidity())
        val += "\n\t Relative humidity [%%]: %f" % (self.getRelativeHumidity())
        val += "\n\t Pressure (corresponding to sea level) [Pa]: %f" % (
            self.getPressure()
        )
        val += "\n\t Wind speed [m/s]: %f" % (self.getWindSpeed())
        val += "\n\t Wind direction [degree]: %f" % (self.getWindDirection())
        val += "\n\t Mixing height [m]: %f" % (self.getMixingHeight())
        val += "\n\t Speed of sound [m/s]: %f" % (self.getSpeedOfSound())
        val += "\n\t Obukhov Length [m]: %f" % (self.getObukhovLength())

        return val


class AmbientConditionStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'AmbientCondition' objects
    """

    def __init__(self, db_path="", init_csv_path=""):
        Store.__init__(self)

        self._db_path = None

        if os.path.isfile(db_path):
            self._db_path = db_path

        if self._db_path is not None:
            self._db = AmbientConditionDatabaseSQL(
                self._db_path, deserialize=not bool(init_csv_path)
            )

        # instantiate all AmbientCondition objects
        self.initAmbientCondition(init_csv_path)

    def initAmbientCondition(self, init_csv_path=""):

        # deserialize objects from csv file
        if init_csv_path:
            csv = read_csv_to_dict(init_csv_path)

            headers_ = METEO_CSV_HEADERS

            # check if all headers are found
            if not sorted(csv.keys()) == sorted(headers_.keys()):
                logger.error("Headers of meteo csv file do not match..")

                for key in list(headers_.keys()):
                    if not list(csv.keys()):
                        logger.error("Did not find header '%s' in csv file." % (key))

            head_ = "Scenario"
            if "Scenario" not in csv:
                logger.error(
                    "Did not find mandatory key '%s' in meteo csv file ... Cannot read the file"
                    % (head_)
                )
                raise Exception(
                    "Did not find mandatory key '%s' in meteo csv file ... Cannot read the file"
                    % (head_)
                )

            for i in range(0, len(csv[head_])):
                ambientcondition_dict = {"id": i, "SpeedOfSound": 340.29}

                for csv_head_ in list(csv.keys()):
                    if csv_head_ in headers_:
                        ambientcondition_dict[headers_[csv_head_]] = csv[csv_head_][i]

                # add value to SQL database interface
                self.getAmbientConditionDatabase().setEntry(
                    ambientcondition_dict.get("id", "unknown"), ambientcondition_dict
                )

        # deserialize objects from sql db
        for key, ambientcondition_dict in list(
            self.getAmbientConditionDatabase().getEntries().items()
        ):
            # add object to store
            self.setObject(
                ambientcondition_dict.get("id", "unknown"),
                AmbientCondition(ambientcondition_dict),
            )

    def getAmbientConditionDatabase(self):
        return self._db

    def getAmbientConditions(self, scenario=""):
        if scenario:
            return sorted(
                [
                    x
                    for x in list(self.getObjects().values())
                    if x.getScenario() == scenario
                ],
                key=lambda ac: ac.getDate(),
            )
        else:
            return sorted(list(self.getObjects().values()), key=lambda ac: ac.getDate())

    def getNearestByTime(self, timestamp_s):
        """Return the ``AmbientCondition`` whose ``DateTime`` is closest
        (nearest neighbour) to ``timestamp_s`` (a Unix timestamp).

        Returns an empty ``AmbientCondition()`` if the store has no
        entries. Callers that need to know whether the store was empty
        can check ``bool(self.getObjects())`` before calling; the
        returned empty instance has getters that return None (matching
        the pre-existing "no meteo loaded" contract used by
        ``EmissionCalculation.getAmbientCondition``).

        Mirrors the bisect semantics of
        ``EmissionCalculation.getAmbientCondition`` so per-time lookups
        that pass through the SourceModule layer produce the same
        AmbientCondition as those done inside EmissionCalculation.

        :param timestamp_s: Unix timestamp (seconds since epoch).
        :return: nearest ``AmbientCondition`` or empty instance.
        """
        import bisect

        # Sort once per call; the store's contents change rarely and the
        # cost is O(n log n) but n is typically small (one row per hour
        # for a year = 8760). If profiling shows this is hot, cache the
        # sorted list on the store as EmissionCalculation does.
        sorted_ac = self.getAmbientConditions(scenario="")
        if not sorted_ac:
            return AmbientCondition()

        times = [
            (ac.getDate().timestamp() if hasattr(ac.getDate(), "timestamp") else 0.0)
            for ac in sorted_ac
        ]

        idx = bisect.bisect_left(times, timestamp_s)
        if idx == 0:
            return sorted_ac[0]
        if idx >= len(times):
            return sorted_ac[-1]
        before = sorted_ac[idx - 1]
        after = sorted_ac[idx]
        return (
            before
            if abs(timestamp_s - times[idx - 1]) <= abs(times[idx] - timestamp_s)
            else after
        )

    def serialize(self):
        if not self.getAmbientConditionDatabase().serialize():
            logger.error(
                "Could not write ambient conditions to database at path '%s'!"
                % (self.getAmbientConditionDatabase().getDatabasePath())
            )


class AmbientConditionDatabaseSQL(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to ambient conditions table in the spatialite database
    """

    TABLE_NAME = "tbl_InvMeteo"

    def __init__(
        self,
        db_path_string,
        table_columns_type_dict=None,
        primary_key="",
        deserialize=True,
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("id", "INTEGER PRIMARY KEY NOT NULL"),
                    ("Scenario", "TEXT"),
                    ("DateTime", "DATETIME"),
                    ("Temperature", "DECIMAL"),
                    ("Humidity", "DECIMAL"),
                    ("RelativeHumidity", "DECIMAL"),
                    ("SeaLevelPressure", "DECIMAL"),
                    ("WindSpeed", "DECIMAL"),
                    ("WindDirection", "DECIMAL"),
                    ("ObukhovLength", "DECIMAL"),
                    ("MixingHeight", "DECIMAL"),
                    ("SpeedOfSound", "DECIMAL"),
                ]
            )

        SQLSerializable.__init__(
            self,
            db_path_string,
            self.TABLE_NAME,
            table_columns_type_dict,
            primary_key,
            None,
        )

        if deserialize and self._db_path:
            self.deserialize()


# if __name__ == "__main__":
#     # import __init__
#     # import alaqslogging
#
#     for i in range(1,3):
#
#         # fix_print_with_import
#         print("-------------")
#         path_to_database = os.path.join("..", "..", "example/ATM4E/", "ATM4E_out_D%s.alaqs"%str(i).zfill(2))
#         # fix_print_with_import
#         print(path_to_database)
#
#         # path_to_csv = os.path.join("..", "..", "example/ATM4E/", "meteo.csv")
#         store = AmbientConditionStore(path_to_database, init_csv_path="")
#
#         for ac_name, ac in list(store.getObjects().items()):
#             if ac_name == 1:
#                 # fix_print_with_import
#                 print(ac)
#
#         # sys.modules[__name__].__dict__.clear()
#         # get_ipython().magic('reset -sf')
#         # get_ipython().magic('%reset_selective -f path_to_database')
#         # get_ipython().magic('%reset_selective -f store')
#         # get_ipython().magic('%reset_selective -f AmbientConditionDatabaseSQL')
#         get_ipython().magic('%reset_selective -f AmbientConditionStore')
#         from interfaces.AmbientCondition import AmbientConditionStore
#
#
#         # path_to_database = os.path.join("..", "..", "example/ATM4E/", "ATM4E_out_D02.alaqs")
#     # # path_to_csv = os.path.join("..", "..", "example/ATM4E/", "meteo.csv")
#     # store = AmbientConditionStore(path_to_database, init_csv_path="")
#     #
#
#     #
#     # for ac in store.getAmbientConditions(scenario="default"):
#     #     print ac
