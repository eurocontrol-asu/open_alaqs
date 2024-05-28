import os
from collections import OrderedDict
from datetime import datetime

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)


class InventoryTime:
    def __init__(self, ts: datetime) -> None:
        self.ts = ts


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
                    datetime.fromisoformat(timeseries_dict["time"]),
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
