"""
This class provides all of the calculation methods required to perform emissions
 calculations for roadways.
"""
import logging

from open_alaqs.alaqs_core.interfaces.Emissions import Emission
from open_alaqs.alaqs_core.interfaces.RoadwaySources import RoadwaySourcesStore
from open_alaqs.alaqs_core.interfaces.SourceModule import \
    SourceWithTimeProfileModule

logger = logging.getLogger("alaqs.%s" % __name__)


class RoadwaySourceWithTimeProfileModule(SourceWithTimeProfileModule):
    """
    Calculate roadway emissions for a specific roadway based on the roadway name
     and time period

    The emission for any source for each time period is equal to the length of
     the roadway in km multiplied by the
    average emission per vehicle per km multiplied by the number of vehicles for
     the time period

    multiplied by the activity factor for the specific hour. For example:
    \f$E_{co} = Length_{km} \times EF_{co_km} \times  N_{vehicles}\f$

    :param database_path: path to the alaqs output file being displayed/examined
    :param source_name: the name of the roadway to be reviewed
    :return emission_profile: a dict containing the total emissions for each
     pollutant
    :rtype: dict
    """

    @staticmethod
    def getModuleName():
        return "RoadwaySource"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        SourceWithTimeProfileModule.__init__(self, values_dict)

        if not self.getDatabasePath() is None:
            self.setStore(RoadwaySourcesStore(self.getDatabasePath()))

    def beginJob(self):
        SourceWithTimeProfileModule.beginJob(
            self)  # super(RoadwaySourceWithTimeProfileModule, self).beginJob()

    def process(self, startTimeSeries, endTimeSeries, source_names=None,
                **kwargs):
        if source_names is None:
            source_names = []
        result_ = []

        for source_id, source in list(self.getSources().items()):
            if source_names and not (
                    "all" in source_names) and not source_id in source_names:
                # logger.error("Cannot process source with id '%s':" % source_id)
                continue

            activity_multiplier = self.getRelativeActivityPerHour(
                startTimeSeries, source.getUnitsPerYear(),
                source.getHourProfile(), source.getDailyProfile(),
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

            # FIXME:
            # Factor 1./1000. to convert from g to kg
            emissions.addGeneric(source.getEmissionIndex(), source.getLength(
                unitInKM=True) * activity_multiplier / 1000., unit="gm_km",
                                 new_unit="kg")

            emissions.setGeometryText(source.getGeometryText())

            result_.append(
                (startTimeSeries.getTimeAsDateTime(), source, [emissions]))

        return result_

    def endJob(self):
        SourceWithTimeProfileModule.endJob(self)
