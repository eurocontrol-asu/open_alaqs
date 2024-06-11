import os
from collections import OrderedDict

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)


class UserProfile:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._name = str(val["profile_name"]) if "profile_name" in val else ""

    def getName(self):
        return self._name


class UserHourProfile(UserProfile):
    def __init__(self, val=None):
        if val is None:
            val = {}
        UserProfile.__init__(self, val)

        self._hours = OrderedDict()
        for i_ in range(1, 25):
            self._hours[i_ - 1] = (
                float(val["h" + "%02d" % i_]) if "h" + "%02d" % i_ in val else 0.0
            )

    def getHours(self):
        return self._hours

    def setHours(self, val=None):
        if val is None:
            val = {}
        for key in val:
            self._hours[key] = float(val[key])

    def __str__(self):
        val = "\n UserProfile with name '%s'" % (self.getName())
        val += "\n\t Hours: %s" % (str(self.getHours()))

        return val


class UserDayProfile(UserProfile):
    def __init__(self, val=None):
        if val is None:
            val = {}
        UserProfile.__init__(self, val)

        self._days = OrderedDict()
        for i_ in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
            self._days[i_] = float(val[i_]) if i_ in val else 0.0

    def getDays(self):
        return self._days

    def setDays(self, val=None):
        if val is None:
            val = {}
        for key in val:
            self._days[key] = float(val[key])

    def __str__(self):
        val = "\n UserProfile with name '%s'" % (self.getName())
        val += "\n\t Days: %s" % (str(self.getDays()))
        return val


class UserMonthProfile(UserProfile):
    def __init__(self, val=None):
        if val is None:
            val = {}
        UserProfile.__init__(self, val)

        self._months = OrderedDict()
        for i_ in [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ]:
            self._months[i_] = float(val[i_]) if i_ in val else 0.0

    def getMonths(self):
        return self._months

    def setMonths(self, val=None):
        if val is None:
            val = {}
        for key in val:
            self._months[key] = float(val[key])

    def __str__(self):
        val = "\n UserProfile with name '%s'" % (self.getName())
        val += "\n\t Months: %s" % (str(self.getMonths()))
        return val


class UserHourProfileStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'UserHourProfile' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        self._user_hour_profile_db = None
        if "user_hour_profile_db" in db:
            if isinstance(db["user_hour_profile_db"], UserHourProfileDatabase):
                self._user_hour_profile_db = db["user_hour_profile_db"]
            elif isinstance(db["user_hour_profile_db"], str) and os.path.isfile(
                db["user_hour_profile_db"]
            ):
                self._user_hour_profile_db = UserHourProfileDatabase(
                    db["user_hour_profile_db"]
                )

        if self._user_hour_profile_db is None:
            self._user_hour_profile_db = UserHourProfileDatabase(db_path)

        # instantiate all UserHourProfile objects
        self.initUserHourProfiles()

    def initUserHourProfiles(self):
        for key, values_dict in list(
            self.getUserHourProfileDatabase().getEntries().items()
        ):
            # add engine to store
            self.setObject(
                (
                    values_dict["profile_name"]
                    if "profile_name" in values_dict
                    else "unknown"
                ),
                UserHourProfile(values_dict),
            )

    def getUserHourProfileDatabase(self):
        return self._user_hour_profile_db


class UserDayProfileStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'UserDayProfile' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        self._user_day_profile_db = None
        if "user_day_profile_db" in db:
            if isinstance(db["user_day_profile_db"], UserDayProfileDatabase):
                self._user_day_profile_db = db["user_day_profile_db"]
            elif isinstance(db["user_day_profile_db"], str) and os.path.isfile(
                db["user_day_profile_db"]
            ):
                self._user_day_profile_db = UserDayProfileDatabase(
                    db["user_day_profile_db"]
                )

        if self._user_day_profile_db is None:
            self._user_day_profile_db = UserDayProfileDatabase(db_path)

        # instantiate all UserDayProfile objects
        self.initUserDayProfiles()

    def initUserDayProfiles(self):
        for key, values_dict in list(
            self.getUserDayProfileDatabase().getEntries().items()
        ):
            # add engine to store
            self.setObject(
                (
                    values_dict["profile_name"]
                    if "profile_name" in values_dict
                    else "unknown"
                ),
                UserDayProfile(values_dict),
            )

    def getUserDayProfileDatabase(self):
        return self._user_day_profile_db


class UserMonthProfileStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'UserMonthProfile' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        self._user_month_profile_db = None
        if "user_month_profile_db" in db:
            if isinstance(db["user_month_profile_db"], UserMonthProfileDatabase):
                self._user_month_profile_db = db["user_month_profile_db"]
            elif isinstance(db["user_month_profile_db"], str) and os.path.isfile(
                db["user_month_profile_db"]
            ):
                self._user_month_profile_db = UserMonthProfileDatabase(
                    db["user_month_profile_db"]
                )

        if self._user_month_profile_db is None:
            self._user_month_profile_db = UserMonthProfileDatabase(db_path)

        # instantiate all UserMonthProfile objects
        self.initUserMonthProfiles()

    def initUserMonthProfiles(self):
        for key, values_dict in list(
            self.getUserMonthProfileDatabase().getEntries().items()
        ):
            # add engine to store
            self.setObject(
                (
                    values_dict["profile_name"]
                    if "profile_name" in values_dict
                    else "unknown"
                ),
                UserMonthProfile(values_dict),
            )

    def getUserMonthProfileDatabase(self):
        return self._user_month_profile_db


class UserHourProfileDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to user hour profiles in the spatialite database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="user_hour_profile",
        table_columns_type_dict=None,
        primary_key="oid",
        geometry_columns=None,
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                    ("profile_name", "TEXT"),
                    ("h01", "DECIMAL NULL"),
                    ("h02", "DECIMAL NULL"),
                    ("h03", "DECIMAL NULL"),
                    ("h04", "DECIMAL NULL"),
                    ("h05", "DECIMAL NULL"),
                    ("h06", "DECIMAL NULL"),
                    ("h07", "DECIMAL NULL"),
                    ("h08", "DECIMAL NULL"),
                    ("h09", "DECIMAL NULL"),
                    ("h10", "DECIMAL NULL"),
                    ("h11", "DECIMAL NULL"),
                    ("h12", "DECIMAL NULL"),
                    ("h13", "DECIMAL NULL"),
                    ("h14", "DECIMAL NULL"),
                    ("h15", "DECIMAL NULL"),
                    ("h16", "DECIMAL NULL"),
                    ("h17", "DECIMAL NULL"),
                    ("h18", "DECIMAL NULL"),
                    ("h19", "DECIMAL NULL"),
                    ("h20", "DECIMAL NULL"),
                    ("h21", "DECIMAL NULL"),
                    ("h22", "DECIMAL NULL"),
                    ("h23", "DECIMAL NULL"),
                    ("h24", "DECIMAL NULL"),
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

        if self._db_path:
            self.deserialize()


class UserDayProfileDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to user day profiles in the spatialite database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="user_day_profile",
        table_columns_type_dict=None,
        primary_key="oid",
        geometry_columns=None,
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                    ("profile_name", "TEXT"),
                    ("mon", "DECIMAL NULL"),
                    ("tue", "DECIMAL NULL"),
                    ("wed", "DECIMAL NULL"),
                    ("thu", "DECIMAL NULL"),
                    ("fri", "DECIMAL NULL"),
                    ("sat", "DECIMAL NULL"),
                    ("sun", "DECIMAL NULL"),
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

        if self._db_path:
            self.deserialize()


class UserMonthProfileDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to user month profiles in the spatialite database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="user_month_profile",
        table_columns_type_dict=None,
        primary_key="oid",
        geometry_columns=None,
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                    ("profile_name", "TEXT"),
                    ("jan", "DECIMAL NULL"),
                    ("feb", "DECIMAL NULL"),
                    ("mar", "DECIMAL NULL"),
                    ("apr", "DECIMAL NULL"),
                    ("may", "DECIMAL NULL"),
                    ("jun", "DECIMAL NULL"),
                    ("jul", "DECIMAL NULL"),
                    ("aug", "DECIMAL NULL"),
                    ("sep", "DECIMAL NULL"),
                    ("oct", "DECIMAL NULL"),
                    ("nov", "DECIMAL NULL"),
                    ("dec", "DECIMAL NULL"),
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

        if self._db_path:
            self.deserialize()


# if __name__ == "__main__":
#     # create a logger for this module
#     #logging.basicConfig(level=logging.DEBUG)
#
#     logger.setLevel(logging.DEBUG)
#     # create console handler and set level to debug
#     ch = logging.StreamHandler()
#     if loaded_color_logger:
#         ch= RainbowLoggingHandler(sys.stderr, color_funcName=('black', 'yellow', True))
#
#     ch.setLevel(logging.DEBUG)
#     # create formatter
#     formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
#     # add formatter to ch
#     ch.setFormatter(formatter)
#     # add ch to logger
#     logger.addHandler(ch)
#
#     path_to_database = os.path.join("..", "..", "example", "exeter_out.alaqs")
#
#     store = UserHourProfileStore(path_to_database)
#     for ts_id, ts in list(store.getObjects().items()):
#         logger.debug(ts)
#
#     store = UserDayProfileStore(path_to_database)
#     for ts_id, ts in list(store.getObjects().items()):
#         logger.debug(ts)
#
#     store = UserMonthProfileStore(path_to_database)
#     for ts_id, ts in list(store.getObjects().items()):
#         logger.debug(ts)
