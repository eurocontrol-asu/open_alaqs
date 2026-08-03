"""
This class provides all of the calculation methods required to perform
emissions calculations for area sources.
"""

from datetime import datetime

from open_alaqs.core.interfaces.AreaSources import AreaSourcesStore
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.SourceModule import SourceWithTimeProfileModule

_ZERO_EMISSION_VALUES = {
    "fuel_kg": 0.0,
    "co2_kg": 0.0,
    "co_kg": 0.0,
    "hc_kg": 0.0,
    "nox_kg": 0.0,
    "sox_kg": 0.0,
    "pm10_kg": 0.0,
    "p1_kg": 0.0,
    "p2_kg": 0.0,
    "pm10_nonvol_kg": 0.0,
    "pm10_sul_kg": 0.0,
    "pm10_organic_kg": 0.0,
}


class AreaSourceWithTimeProfileModule(SourceWithTimeProfileModule):
    # stationary loop-fusion eligible.
    time_invariant_geometry: bool = True

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

        if self.getDatabasePath() is not None:
            self.setStore(AreaSourcesStore(self.getDatabasePath()))

    def loadSources(self):
        """Populate ``_sources`` from ``AreaSourcesStore``, skipping any
        area sources flagged as engine-test sites (``is_test_site='1'``).

        The store is shared with ``EngineTestSourceModule``, which lists
        only test sites. Filtering here means the Results Analysis
        source-name dropdown for "AreaSource" excludes test sites, and
        each test-site source only appears once (under
        "EngineTestSource"). Prevents user confusion where the same
        source appears in both dropdowns and can be selected under the
        wrong module (which would silently produce zero because
        ``process()`` at line 84 skips test sites).
        """
        if self.getStore() is None:
            return
        for source_name, source in self.getStore().getObjects().items():
            if source.isTestSite():
                continue
            self.setSource(source_name, source)

    def beginJob(self):
        # super(AreaSourceWithTimeProfileModule, self).beginJob()
        SourceWithTimeProfileModule.beginJob(self)

    def process(
        self,
        start_dt: datetime,
        end_dt: datetime,
        source_names: list[str] = None,
        **kwargs
    ):
        if source_names is None:
            source_names = []

        result_ = []

        for source_id, source in self.getSources().items():
            if (
                source_names
                and ("all" not in source_names)
                and (source_id not in source_names)
            ):
                continue
            # Skip sources marked excluded from the study (instudy='0').
            # See Source.isInStudy() for the read-side contract.
            if not source.isInStudy():
                continue
            # Skip engine-test sites: their emissions come from per-event
            # records in ``engine_test_events`` and are computed by
            # ``EngineTestSourceModule``. Processing them here would apply
            # the *_kg_unit fixed rates on top of the event-based compute,
            # double-counting. Test-site sources are silently skipped
            # (log-worthy only if they somehow still carry non-zero
            # *_kg_unit rates, which is a data-entry inconsistency handled
            # by input validation, not here).
            if source.isTestSite():
                continue

            # try the precomputed per-hour activity cache
            # first; legacy fallback below.
            cached = self._try_get_per_hour_activity(source_id, start_dt)
            if cached is not None:
                period_h = (end_dt - start_dt).total_seconds() / 3600.0
                activity_multiplier = cached * period_h
            else:
                activity_multiplier = self.getEmissionsForTimePeriod(
                    start_dt,
                    end_dt,
                    source.getUnitsPerYear(),
                    source.getHourProfile(),
                    source.getDailyProfile(),
                    source.getMonthProfile(),
                )

            # Calculate the emissions for this time interval
            emissions = Emission(
                initValues=dict(_ZERO_EMISSION_VALUES), defaultValues={}
            )

            emissions.addGeneric(
                source.getEmissionIndex(), activity_multiplier, "_unit"
            )
            emissions.setGeometryText(source.getGeometryText())

            result_.append((start_dt, source, [emissions]))
        return result_

    def endJob(self):
        SourceWithTimeProfileModule.endJob(self)
