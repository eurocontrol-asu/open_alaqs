"""
This class provides all of the calculation methods required to perform
emissions calculations for area sources.
"""

from open_alaqs.alaqs_core.interfaces.AreaSources import AreaSourcesStore
from open_alaqs.alaqs_core.interfaces.Emissions import Emission
from open_alaqs.alaqs_core.interfaces.SourceModule import \
    SourceWithTimeProfileModule


class AreaSourceWithTimeProfileModule(SourceWithTimeProfileModule):
    """
    This class provides all of the calculation methods required to perform
    emissions calculations for area sources.
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
        # super(AreaSourceWithTimeProfileModule, self).beginJob()
        SourceWithTimeProfileModule.beginJob(self)

    def process(self, start_time, end_time, source_names=None,
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
                start_time,
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
                "pm10_nonvol_kg": 0.,
                "pm10_sul_kg": 0.,
                "pm10_organic_kg": 0.
            }, defaultValues={})

            emissions.addGeneric(
                source.getEmissionIndex(), activity_multiplier, "_unit")
            emissions.setGeometryText(source.getGeometryText())

            result_.append((
                start_time.getTimeAsDateTime(), source, [emissions]))
        return result_

    def endJob(self):
        SourceWithTimeProfileModule.endJob(self)
