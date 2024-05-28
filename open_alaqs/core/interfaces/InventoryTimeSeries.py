import os
from collections import OrderedDict
from datetime import datetime

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)

# Set the names of the month and days of the week to prevent locale issue
month_abbreviations = {
    1: "jan",
    2: "feb",
    3: "mar",
    4: "apr",
    5: "may",
    6: "jun",
    7: "jul",
    8: "aug",
    9: "sep",
    10: "oct",
    11: "nov",
    12: "dec",
}
weekday_abbreviations = {
    1: "mon",
    2: "tue",
    3: "wed",
    4: "thu",
    5: "fri",
    6: "sat",
    7: "sun",
}


class InventoryTime:
    def __init__(self, ts_id: int, ts: datetime, mix_height: float) -> None:
        self.ts_id = ts_id
        self.ts = ts
        self.mix_height = mix_height

    def getTime(self) -> float:
        """Returns the time as UNIX timestamp in seconds."""
        return self.ts.timestamp()

    def getTimeAsDateTime(self) -> str:
        return self.ts

    def getMonth(self) -> str:
        return month_abbreviations[self.ts.month]

    def getDay(self) -> str:
        return weekday_abbreviations[self.ts.weekday() + 1]

    def getHour(self) -> int:
        return self.ts.hour

    def getMixingHeight(self) -> float:
        return self.mix_height

    # TODO what happens if the time period includes both? This is unresolved in original ALAQS and here
    def getTotalHoursInYear(self) -> int:
        td = datetime(self.ts.year + 1, 1, 1, 0, 0, 0) - datetime(
            self.ts.year, 1, 1, 0, 0, 0
        )
        return td.total_seconds() / 60 / 60

    def __str__(self) -> str:
        return f"{self.__class__.__name__} #{self.ts_id}: {self.ts.isoformat()}, {self.mix_height}"


class InventoryTimeSeriesStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'InventoryTimeSeries' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        # Engine Modes
        self._inventory_timeseries_db = None
        inventory_timeseries_db_ = db.get("inventory_timeseries_db")
        if isinstance(inventory_timeseries_db_, InventoryTimeSeriesDatabase):
            self._inventory_timeseries_db = inventory_timeseries_db_
        elif isinstance(inventory_timeseries_db_, str) and os.path.isfile(
            inventory_timeseries_db_
        ):
            self._inventory_timeseries_db = InventoryTimeSeriesDatabase(
                inventory_timeseries_db_
            )
        else:
            self._inventory_timeseries_db = InventoryTimeSeriesDatabase(db_path)

        # instantiate all InventoryTime objects
        self.initInventoryTimes()

    def initInventoryTimes(self):
        entries = self.getInventoryTimeSeriesDatabase().getEntries()
        for timeseries_dict in entries.values():
            self.setObject(
                timeseries_dict.get("time_id", -1),
                InventoryTime(
                    timeseries_dict["time_id"],
                    datetime.fromisoformat(timeseries_dict["time"]),
                    timeseries_dict["mix_height"],
                ),
            )

    def getInventoryTimeSeriesDatabase(self):
        return self._inventory_timeseries_db

    def getTimeSeries(self):
        for index_, ts_ in sorted(self.getObjects().items()):
            yield ts_


class InventoryTimeSeriesDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to runway shape file in the spatialite database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="tbl_InvTime",
        table_columns_type_dict=None,
        primary_key="time_id",
        geometry_columns=None,
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("time_id", "INTEGER PRIMARY KEY NOT NULL"),
                    ("time", "DATETIME"),
                    ("mix_height", "DECIMAL"),
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
