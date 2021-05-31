from __future__ import absolute_import

import logging

from open_alaqs.alaqs_core.interfaces.SourceModule import \
    SourceWithTimeProfileModule
from open_alaqs.alaqs_core.interfaces.AreaSources import AreaSourcesStore
from open_alaqs.alaqs_core.interfaces.Emissions import Emission

logger = logging.getLogger("alaqs.%s" % __name__)


class AreaSourceWithTimeProfileModule(SourceWithTimeProfileModule):
    """
    This class provides all of the calculation methods required to perform
    emissions calculations for area sources.

    todo: Check if these comments can be removed, as they do not belong to the
     init function of this module
    Calculate area emissions for a specific source based on the source name and
     time period.

    The emission for any source for each time period is equal to the total
    emission for the entire time period multiplied by the activity factor for
    the specific hour. For example:
    \f$E_{co} =
    CO_{total} \times  AF_{hour} \times AF_{week} \times AF_{month}\f$

    :param database_path: path to the alaqs output file being displayed/examined
    :param source_name: the name of the source to be reviewed
    :return emission_profile: a dict containing the total emissions for each
     pollutant
    :rtype: dict
    """

    @staticmethod
    def getModuleName():
        return "AreaSource"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        SourceWithTimeProfileModule.__init__(self, values_dict)

        if not self.getDatabasePath() is None:
            self.setStore(AreaSourcesStore(self.getDatabasePath()))

    def beginJob(self):
        SourceWithTimeProfileModule.beginJob(
            self)  # super(AreaSourceWithTimeProfileModule, self).beginJob()

    def process(self, startTimeSeries, endTimeSeries, source_names=None,
                **kwargs):
        if source_names is None:
            source_names = []

        result_ = []

        for source_id, source in list(self.getSources().items()):
            if source_names and \
                    ("all" not in source_names) and \
                    (source_id not in source_names):
                continue

            activity_multiplier = self.getRelativeActivityPerHour(
                startTimeSeries,
                source.getUnitsPerYear(),
                source.getHourProfile(),
                source.getDailyProfile(),
                source.getMonthProfile())

            # Calculate the emissions for this time interval
            emissions = Emission(initValues={
                "fuel_kg": 0.,
                "co2_kg": 0.,
                "co_kg": 0.,
                "hc_kg": 0.,
                "nox_kg": 0.,
                "sox_kg": 0.,
                "pm10_kg": 0.,
                "p1_kg": 0.,
                "p2_kg": 0.,
                "pm10_prefoa3_kg": 0.,
                "pm10_nonvol_kg": 0.,
                "pm10_sul_kg": 0.,
                "pm10_organic_kg": 0.
            }, defaultValues={})

            emissions.addGeneric(
                source.getEmissionIndex(), activity_multiplier, "_unit")
            emissions.setGeometryText(source.getGeometryText())

            result_.append((
                startTimeSeries.getTimeAsDateTime(), source, [emissions]))
        return result_

    def endJob(self):
        SourceWithTimeProfileModule.endJob(self)
