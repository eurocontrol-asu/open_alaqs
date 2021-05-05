"""
This class provides all of the calculation methods required to perform emissions calculations for stationary sources.
"""
from __future__ import absolute_import
# from . import __init__
import os
import sys

import logging
logger = logging.getLogger("alaqs.%s" % (__name__))

import alaqsutils           # For logging and conversion of data types
import alaqsdblite          # Functions for working with ALAQS database

from interfaces.SourceModule import SourceWithTimeProfileModule
from interfaces.ParkingSources import ParkingSourcesStore
from interfaces.Emissions import Emission

class ParkingSourceWithTimeProfileModule(SourceWithTimeProfileModule):
    """
    Calculate parking emissions for a specific parking based on the parking name and time period

    The emission for any source for each time period is equal to the length of the parking in km multiplied by the
    average emission per vehicle per km multiplied by the number of vehicles for the time period

    multiplied by the activity factor for the specific hour. For example:
    E_{co} = Length_{km} \times EF_{co_km} \times  N_{vehicles}

    :param database_path: path to the alaqs output file being displayed/examined
    :param source_name: the name of the parking to be reviewed
    :return emission_profile: a dict containing the total emissions for each pollutant
    :rtype: dict
    """

    @staticmethod
    def getModuleName():
        return "ParkingSource"


    def __init__(self, values_dict = {}):
        SourceWithTimeProfileModule.__init__(self, values_dict)

        if not self.getDatabasePath() is None:
            self.setStore(ParkingSourcesStore(self.getDatabasePath()))

    def beginJob(self):
        SourceWithTimeProfileModule.beginJob(self)#super(ParkingSourceWithTimeProfileModule, self).beginJob()

    def process(self, startTimeSeries, endTimeSeries, source_names=[], **kwargs):
        result_ = []

        for source_id, source in list(self.getSources().items()):
            if source_names and not ("all" in source_names) and not source_id in source_names:
                # logger.error("Cannot process source with id '%s':" % source_id)
                continue

            activity_multiplier = self.getRelativeActivityPerHour(startTimeSeries, source.getUnitsPerYear(), source.getHourProfile(), source.getDailyProfile(), source.getMonthProfile())

            # Calculate the emissions for this time interval
            emissions = Emission(initValues={
                "fuel_kg": 0.,
                "co2_kg": 0.,
                "co_kg" : 0.,
                "hc_kg" : 0.,
                "nox_kg" : 0.,
                "sox_kg" : 0.,
                "pm10_kg" : 0.,
                "p1_kg" : 0.,
                "p2_kg": 0.,
                "pm10_prefoa3_kg" : 0.,
                "pm10_nonvol_kg" : 0.,
                "pm10_sul_kg" : 0.,
                "pm10_organic_kg" : 0.
            }, defaultValues={})

            #Factor 1./1000. to convert from g to kg
            emissions.addGeneric(source.getEmissionIndex(), activity_multiplier/1000., unit="gm_vh", new_unit="kg")
            emissions.setGeometryText(source.getGeometryText())

            # logger.debug("\t %s" % (emissions))

            result_.append((startTimeSeries.getTimeAsDateTime(), source, [emissions]))
        return result_

    def endJob(self):
        SourceWithTimeProfileModule.endJob(self)