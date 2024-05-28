import os
import sys
from datetime import datetime

import pandas as pd

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.UserTimeProfiles import (
    UserDayProfileStore,
    UserHourProfileStore,
    UserMonthProfileStore,
)
from open_alaqs.core.utils.utils import get_hours_in_year

sys.path.append("..")  # Adds higher directory to python modules path.

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
    0: "mon",
    1: "tue",
    2: "wed",
    3: "thu",
    4: "fri",
    5: "sat",
    6: "sun",
}


class SourceModule:
    """
    Abstract interface to calculate emissions for a specific source based on the
    source name
    """

    @staticmethod
    def getModuleName():
        return ""

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}

        self._database_path = values_dict.get("database_path")
        self._name = values_dict.get("name")
        self._sources = {}
        self._store = None
        self._dataframe = pd.DataFrame(columns=["oid", "Sources"])

    def getStore(self):
        return self._store

    def setStore(self, val):
        self._store = val

    def getSources(self):
        return self._sources

    def setSource(self, key, value):
        self._sources[key] = value

    def resetSources(self):
        self._sources = {}

    def getSourceNames(self):
        return [str(source_.getName()) for x_, source_ in self._sources.items()]

    def setDatabasePath(self, val):
        self._database_path = val

    def getDatabasePath(self):
        return self._database_path

    def convertSourcesToDataFrame(self):
        df = pd.DataFrame(list(self.getSources().items()), columns=["oid", "Sources"])
        if not df.empty:
            self._dataframe = df

    def getDataframe(self):
        return self._dataframe

    def beginJob(self):
        self.loadSources()
        self.convertSourcesToDataFrame()

    def loadSources(self):
        if self.getStore() is not None:
            for source_name, source in self.getStore().getObjects().items():
                self.setSource(source_name, source)

    def process(
        self, start_time, end_time, source_names=None, ambient_conditions=None, **kwargs
    ):
        return NotImplemented

    def endJob(self):
        return NotImplemented


class SourceWithTimeProfileModule(SourceModule):
    """
    Abstract interface to calculate emissions for a specific source based on the
    source name and time period
    """

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        SourceModule.__init__(self, values_dict)

        self._userHourProfileStore = None
        self._userDayProfileStore = None
        self._userMonthProfileStore = None

    def beginJob(self):
        SourceModule.beginJob(self)

        db_path = self.getDatabasePath()

        self._userHourProfileStore = UserHourProfileStore(db_path)
        self._userDayProfileStore = UserDayProfileStore(db_path)
        self._userMonthProfileStore = UserMonthProfileStore(db_path)

        # check if the database file exists
        if not os.path.isfile(self.getDatabasePath()):
            raise Exception("Did not find database at path '%s'." % db_path)

        self.loadSources()

    def getRelativeActivityPerHour(
        self,
        inventory_dt: datetime,
        annual_total_operating_hours,
        hour_profile_name,
        daily_profile_name,
        month_profile_name,
    ):

        hour_profile = self._userHourProfileStore.getObject(hour_profile_name)
        if hour_profile is None:
            logger.error(
                "Could not retrieve the hourly time profile '%s'." % (hour_profile_name)
            )
            raise Exception(
                "Could not retrieve the hourly time profile '%s'." % (hour_profile_name)
            )

        weekday_profile = self._userDayProfileStore.getObject(daily_profile_name)
        if weekday_profile is None:
            raise Exception(
                "Could not retrieve the weekday time profile '%s'."
                % (daily_profile_name)
            )

        month_profile = self._userMonthProfileStore.getObject(month_profile_name)
        if month_profile is None:
            raise Exception(
                "Could not retrieve the month time profile '%s'." % (month_profile_name)
            )

        hours_in_year = get_hours_in_year(inventory_dt.year)
        operating_factor = float(annual_total_operating_hours) / hours_in_year
        hour_factor = float(hour_profile.getHours()[inventory_dt.hour])
        weekday_factor = float(
            weekday_profile.getDays()[weekday_abbreviations[inventory_dt.weekday()]]
        )
        month_factor = float(
            month_profile.getMonths()[month_abbreviations[inventory_dt.month]]
        )

        # Calculate the activity multiplier
        return operating_factor * hour_factor * weekday_factor * month_factor
