from __future__ import absolute_import
from builtins import str
import os
import sys
import logging

import pandas as pd

from open_alaqs.alaqs_core.interfaces.UserTimeProfiles import \
    UserHourProfileStore, UserDayProfileStore, UserMonthProfileStore

sys.path.append("..")  # Adds higher directory to python modules path.

logger = logging.getLogger("__alaqs__.%s" % __name__)


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
        self._dataframe = pd.DataFrame()

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

    def Sources2DataFrame(self):
        df = pd.DataFrame(list(self.getSources().items()),
                          columns=['oid', "Sources"])
        if not df.empty:
            self._dataframe = df

    def LoadMovementsDataFrame(self):
        df_ = self._dataframe
        return df_

    def beginJob(self):
        self.loadSources()
        self.Sources2DataFrame()

    def loadSources(self):
        if not self.getStore() is None:
            for source_name, source in self.getStore().getObjects().items():
                self.setSource(source_name, source)

    def process(self, startTimeSeries, endTimeSeries, source_names=None,
                ambient_conditions=None, **kwargs):
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

    def getRelativeActivityPerHour(self, inventoryTimeSeries,
                                   annual_total_operating_hours,
                                   hour_profile_name, daily_profile_name,
                                   month_profile_name):

        hour_profile = self._userHourProfileStore.getObject(hour_profile_name)
        if hour_profile is None:
            logger.error("Could not retrieve the hourly time profile '%s'." % (
                hour_profile_name))
            raise Exception(
                "Could not retrieve the hourly time profile '%s'." % (
                    hour_profile_name))

        weekday_profile = self._userDayProfileStore.getObject(
            daily_profile_name)
        if weekday_profile is None:
            raise Exception(
                "Could not retrieve the weekday time profile '%s'." % (
                    daily_profile_name))

        month_profile = self._userMonthProfileStore.getObject(
            month_profile_name)
        if month_profile is None:
            raise Exception(
                "Could not retrieve the month time profile '%s'." % (
                    month_profile_name))

        hours_in_year = inventoryTimeSeries.getTotalHoursInYear()
        operating_factor = float(annual_total_operating_hours) / hours_in_year
        hour_factor = float(
            hour_profile.getHours()[inventoryTimeSeries.getHour()])
        weekday_factor = float(
            weekday_profile.getDays()[inventoryTimeSeries.getDay()])
        month_factor = float(
            month_profile.getMonths()[inventoryTimeSeries.getMonth()])

        # debug output
        # for x in str(inventoryTimeSeries).split("\n"):
        #     # print "%s" % (str(x))
        #     logger.info("%s" % (str(x)))

        # Calculate the activity multiplier
        multiplier = \
            operating_factor * hour_factor * weekday_factor * month_factor

        return multiplier
