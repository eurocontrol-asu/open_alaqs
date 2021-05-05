from __future__ import absolute_import
from builtins import str
from builtins import object
from . import __init__ #setup the paths for direct calls of the module
import os, sys
sys.path.append("..") # Adds higher directory to python modules path.
import alaqsutils # For logging and conversion of data types
import alaqsdblite # Functions for working with ALAQS database

import logging
# logger = logging.getLogger("alaqs.%s" % (__name__))
logger = logging.getLogger("__alaqs__.%s" % (__name__))

from .UserTimeProfiles import UserHourProfileStore, UserDayProfileStore, UserMonthProfileStore
import pandas as pd
# from interfaces.Emissions import Emission

class SourceModule(object):
    """
    Abstract interface to calculate emissions for a specific source based on the source name
    """

    @staticmethod
    def getModuleName():
        return ""

    def __init__(self, values_dict = {}):
        self._database_path = values_dict["database_path"] if "database_path" in values_dict else None
        self._name = values_dict["name"] if "name" in values_dict else None
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
        DF = pd.DataFrame(list(self.getSources().items()), columns=['oid',"Sources"])
        if not DF.empty:
            self._dataframe = DF

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

    def process(self, startTimeSeries, endTimeSeries, source_name="", ambient_conditions=None, **kwargs):
        return NotImplemented

    def endJob(self):
        return NotImplemented


class SourceWithTimeProfileModule(SourceModule):
    """
    Abstract interface to calculate emissions for a specific source based on the source name and time period
    """
    def __init__(self, values_dict = {}):
        SourceModule.__init__(self, values_dict)

    def beginJob(self):
        SourceModule.beginJob(self)

        self._userHourProfileStore = UserHourProfileStore(self.getDatabasePath())
        self._userDayProfileStore = UserDayProfileStore(self.getDatabasePath())
        self._userMonthProfileStore = UserMonthProfileStore(self.getDatabasePath())

        #check if the database file exists
        if not os.path.isfile(self.getDatabasePath()):
            raise Exception("Did not find database at path '%s'." % (self.getDatabasePath()))

        self.loadSources()


    def getRelativeActivityPerHour(self, inventoryTimeSeries, annual_total_operating_hours, hour_profile_name, daily_profile_name, month_profile_name):

        hour_profile = self._userHourProfileStore.getObject(hour_profile_name)
        if hour_profile is None:
            logger.error("Could not retrieve the hourly time profile '%s'." % (hour_profile_name))
            raise Exception("Could not retrieve the hourly time profile '%s'." % (hour_profile_name))

        weekday_profile = self._userDayProfileStore.getObject(daily_profile_name)
        if weekday_profile is None:
            raise Exception("Could not retrieve the weekday time profile '%s'." % (daily_profile_name))

        month_profile = self._userMonthProfileStore.getObject(month_profile_name)
        if month_profile is None:
            raise Exception("Could not retrieve the month time profile '%s'." % (month_profile_name))

        hour_factor = float(hour_profile.getHours()[inventoryTimeSeries.getHour()])
        weekday_factor = float(weekday_profile.getDays()[inventoryTimeSeries.getDay()])
        month_factor = float(month_profile.getMonths()[inventoryTimeSeries.getMonth()])

        # debug output
        # for x in str(inventoryTimeSeries).split("\n"):
        #     # print "%s" % (str(x))
        #     logger.info("%s" % (str(x)))

        # Calculate the activity multiplier
        activity_multiplier = float(annual_total_operating_hours)/inventoryTimeSeries.getTotalHoursInYear() * hour_factor* weekday_factor*month_factor
        # logger.info("Activity multiplier is '%f' (hour factor = '%f',weekday factor = '%f', month factor = '%f'). Annual total operating hours: '%i'." % (activity_multiplier, hour_factor, weekday_factor, month_factor, annual_total_operating_hours))
        return activity_multiplier