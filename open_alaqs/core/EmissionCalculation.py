import bisect
from datetime import datetime, timedelta
from typing import Any, List, TypedDict

from qgis.PyQt import QtCore, QtWidgets

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.AmbientCondition import (
    AmbientCondition,
    AmbientConditionStore,
)
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.InventoryTimeSeries import InventoryTimeSeriesStore
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.modules.ModuleManager import (
    DispersionModuleRegistry,
    SourceModuleRegistry,
)
from open_alaqs.core.tools.Grid3D import Grid3D
from open_alaqs.core.tools.iterator import pairwise

logger = get_logger(__name__)


class GridConfig(TypedDict):
    x_cells: int
    y_cells: int
    z_cells: int
    x_resolution: int
    y_resolution: int
    z_resolution: int
    reference_latitude: float
    reference_longitude: float
    reference_altitude: float


class EmissionCalculation:
    # Class-level variable tracking the last DB file opened.  Singleton stores
    # are only flushed when this changes — not on every method switch.
    _last_db_path: str = ""

    def __init__(
        self,
        db_path: str,
        grid_config: GridConfig,
        start_dt: datetime,
        end_dt: datetime,
        time_interval: timedelta,
    ) -> None:
        assert db_path

        # Flush all Singleton stores only when the user opens a *different*
        # .alaqs database in the same QGIS Python session.  Resetting on
        # every calculation (e.g. switching bymode → BFFM2 on the same file)
        # is unnecessary: the stores are still valid for the same DB path.
        # Resetting unconditionally caused every BFFM2 run to fail silently
        # (store re-init errors swallowed by the try/except in
        # EmissionCalculatorService), leaving the output modules serving the
        # previous bymode results.
        if db_path != EmissionCalculation._last_db_path:
            from open_alaqs.core.tools.Singleton import Singleton

            Singleton.reset_all()
            EmissionCalculation._last_db_path = db_path

        self._database_path = db_path
        self._grid = Grid3D(self._database_path, grid_config)

        # Get the time series for this inventory
        self._start_dt = start_dt
        self._end_dt = end_dt
        self._time_interval = time_interval
        self._inventoryTimeSeriesStore = InventoryTimeSeriesStore(self._database_path)
        self._emissions = {}
        self._source_modules = {}
        self._dispersion_modules = {}
        self._ambient_conditions_store = AmbientConditionStore(self._database_path)
        # Pre-sort ambient conditions once so getAmbientCondition() can use
        # bisect instead of sorting + linear-scanning on every timestep.
        _all_ac = self._ambient_conditions_store.getAmbientConditions(scenario="")
        self._sorted_ac = sorted(_all_ac, key=lambda x: x.getDate())
        self._sorted_ac_times = [ac.getDate() for ac in self._sorted_ac]

    @staticmethod
    def ProgressBarWidget(dispersion_enabled=False):
        if dispersion_enabled:
            progressbar = QtWidgets.QProgressDialog(
                "Calculating emissions & writing input files for"
                " dispersion model ...",
                "Cancel",
                0,
                99,
            )
        else:
            progressbar = QtWidgets.QProgressDialog(
                "Calculating emissions ...", "Cancel", 0, 99
            )
        progressbar.setWindowTitle("Emissions Calculation")
        # self._progressbar.setValue(1)
        progressbar.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        progressbar.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progressbar.setAutoReset(True)
        progressbar.setAutoClose(True)
        progressbar.resize(350, 100)
        progressbar.show()
        return progressbar

    def getAmbientCondition(self, t_):
        # Use bisect on the pre-sorted timestamp list for O(log n) lookup
        # instead of sorting the full list and doing a linear min() search
        # on every one of the 8 760 timesteps in a year run.
        times = self._sorted_ac_times
        if not times:
            return AmbientCondition()
        idx = bisect.bisect_left(times, t_)
        if idx == 0:
            return self._sorted_ac[0]
        if idx >= len(times):
            return self._sorted_ac[-1]
        before = self._sorted_ac[idx - 1]
        after = self._sorted_ac[idx]
        return before if abs(t_ - times[idx - 1]) <= abs(times[idx] - t_) else after

    def add_source_module(
        self, module_name: str, module_config: dict[str, Any]
    ) -> None:
        EmissionSourceModule = SourceModuleRegistry().get_module(module_name)

        self._source_modules[module_name] = EmissionSourceModule(
            values_dict={
                "database_path": self._database_path,
                **module_config,
            }
        )

    def add_dispersion_modules(
        self, module_names: list[str], module_config: dict[str, Any]
    ):
        for module_name in module_names:
            DispersionSourceModule = DispersionModuleRegistry().get_module(module_name)

            self._dispersion_modules[module_name] = DispersionSourceModule(
                values_dict={
                    "database_path": self._database_path,
                    **module_config,
                }
            )

    def run(
        self, source_names: List, vertical_limit_m: float, show_progress: bool = True
    ):
        if source_names is None:
            source_names = []

        # ------------------------------------------------------------------
        # Leap-year sanity check.
        #
        # The per-hour profile-mean divisor in
        # SourceModule._get_profile_mean walks the full calendar year
        # (8784 hours in leap years, 8760 otherwise — see
        # SourceModule.py L206 and L259). If the user's [start_dt,
        # end_dt] interval does not cover a full calendar year worth
        # of hourly periods, the run will silently under- or
        # over-report annual totals by the missing fraction. Warn but
        # do not fail; some workflows deliberately run a partial year.
        # The vectorised path inherits this behaviour by construction
        # so the check applies regardless.
        #
        # Multi-year intervals are skipped — the per-year accounting
        # is correct in that case (the profile-mean cache invalidates
        # at the year boundary).
        # ------------------------------------------------------------------
        try:
            self._warn_if_partial_year()
        except Exception as e:  # never block run() on a sanity check
            logger.debug("Leap-year sanity check skipped: %s", e)

        default_emissions = {
            "fuel_kg": 0.0,
            "co_g": 0.0,
            "co2_g": 0.0,
            "hc_g": 0.0,
            "nox_g": 0.0,
            "sox_g": 0.0,
            "pm10_g": 0.0,
            "p1_g": 0.0,
            "p2_g": 0.0,
            "pm10_nonvol_g": 0.0,
            "pm10_sul_g": 0.0,
            "pm10_organic_g": 0.0,
            "nvpm_g": 0.0,
            "nvpm_number": 0.0,
        }

        # check if a dispersion module is enabled
        dispersion_enabled = len(self.getDispersionModules()) > 0

        # list the selected modules
        logger.debug("Selected source modules: %s", ", ".join(self.getModules().keys()))
        logger.debug(
            "Selected dispersion modules: %s",
            (
                ", ".join(self.getDispersionModules().keys())
                if dispersion_enabled
                else None
            ),
        )

        # execute beginJob(..) of SourceModules
        logger.debug("Execute beginJob(..) of source modules")
        for mod_name, mod_obj in self.getModules().items():
            mod_obj.beginJob()

        # ------------------------------------------------------------------
        # Vectorised activity-vector setup.
        #
        # Build a single shared ProfileSet from the
        # User{Hour,Day,Month}ProfileStore singletons (populated by the
        # SourceWithTimeProfileModule.beginJob calls above) and pre-
        # compute per-source hourly activity vectors for every stationary
        # module. Each stationary `process()` reads scalar per-hour
        # activity from the cache via `_try_get_per_hour_activity`
        # (O(1) ndarray index) instead of walking 8760 hours of profile
        # state per source.
        #
        # The cache is keyed by year (taken from the inventory start
        # datetime). Multi-year runs are not supported: the activity
        # vector spans a single calendar year.
        # ------------------------------------------------------------------
        from open_alaqs.core.interfaces.UserTimeProfiles import (
            UserDayProfileStore,
            UserHourProfileStore,
            UserMonthProfileStore,
        )
        from open_alaqs.core.tools.profiles_vec import build_profile_set
        from open_alaqs.core.tools.sources_df import build_sources_df

        db_path = self._database_path
        profile_set = build_profile_set(
            UserHourProfileStore(db_path),
            UserDayProfileStore(db_path),
            UserMonthProfileStore(db_path),
        )
        inventory_year = self._start_dt.year

        for mod_name, mod_obj in self.getModules().items():
            if not getattr(mod_obj, "time_invariant_geometry", False):
                continue
            if not hasattr(mod_obj, "precompute_activity_vectors"):
                # SourceModule subclasses without the vectorised mixin
                # (i.e. not derived from SourceWithTimeProfileModule)
                # cannot pre-compute; skip silently.
                continue
            mod_obj.precompute_activity_vectors(profile_set, inventory_year)
            logger.debug(
                "activity-vector cache populated for module %s "
                "(%d sources, year %d)",
                mod_name,
                len(getattr(mod_obj, "_activity_vec_cache", {})),
                inventory_year,
            )

        # Tabular view of all stationary sources for the AUSTAL writer.
        # Builds one pd.DataFrame per type from the already-populated
        # Singleton stores; no SQL. See core/tools/sources_df.py for
        # the full schema and the `<type>:<id>` source_id convention.
        self._sources_df = build_sources_df(self.getModules())
        for type_label, df in self._sources_df.items():
            logger.debug(
                "sources_df['%s']: %d rows, %d columns",
                type_label,
                len(df),
                len(df.columns),
            )

        # execute beginJob(..) of dispersion modules
        logger.debug("Execute beginJob(..) of dispersion modules")
        for (
            dispersion_mod_name,
            dispersion_mod_obj,
        ) in self.getDispersionModules().items():
            dispersion_mod_obj.beginJob()

        # execute process(..)
        logger.debug("Execute process(..)")
        try:
            # Only create progress bar if GUI mode is enabled
            progressbar = None
            total_count_ = 0
            if show_progress:
                progressbar = self.ProgressBarWidget(
                    dispersion_enabled=dispersion_enabled
                )
                total_count_ = len(list(self.getTimeSeries())) - 1

            count_ = 0

            # loop on complete period
            for start_dt, end_dt in pairwise(self.getTimeSeries()):
                if logger.isEnabledFor(10):  # logging.DEBUG == 10
                    logger.debug("start %s, end %s", start_dt, end_dt)

                # Update the progress bar only in GUI mode
                if progressbar is not None:
                    progressbar.setValue(int(100 * count_ / total_count_))
                    QtCore.QCoreApplication.instance().processEvents()
                    if progressbar.wasCanceled():
                        raise StopIteration("Operation canceled by user")
                count_ += 1

                # get the ambient condition
                # ToDo: only run on (start_, end_) with emission sources?
                try:
                    ambient_condition = self.getAmbientCondition(start_dt.timestamp())
                except Exception as error:
                    logger.warning(
                        "Couldn't load the ambient condition, so "
                        "default conditions are used:\n%s",
                        error,
                    )
                    ambient_condition = AmbientCondition()

                period_emissions = []

                # calculate emissions per source
                for mod_name, mod_obj in self.getModules().items():
                    if logger.isEnabledFor(10):
                        logger.debug(mod_name)

                    # process() returns a list of tuples for each specific
                    # time interval (start_, end_)
                    for timestamp_, source_, emission_ in mod_obj.process(
                        start_dt,
                        end_dt,
                        source_names=source_names,
                        ambient_conditions=ambient_condition,
                        vertical_limit_m=vertical_limit_m,
                    ):
                        if logger.isEnabledFor(10):
                            logger.debug("%s: %s", mod_name, timestamp_)

                        if emission_ is not None:
                            period_emissions.append((source_, emission_))
                        else:
                            period_emissions.append(
                                (
                                    source_,
                                    [Emission(default_emissions, default_emissions)],
                                )
                            )

                # calculate dispersion per model
                for (
                    dispersion_mod_name,
                    dispersion_mod_obj,
                ) in self.getDispersionModules().items():
                    if logger.isEnabledFor(10):
                        logger.debug("%s: %s", dispersion_mod_name, start_dt)
                    dispersion_mod_obj.process(
                        start_dt, end_dt, period_emissions, ambient_condition
                    )

                # add a generic (zero) emission if the list is empty
                if len(period_emissions) == 0:
                    period_emissions.append(
                        (Source(), [Emission(default_emissions, default_emissions)])
                    )

                # add the emissions to the dict
                self._emissions[start_dt] = period_emissions

        except StopIteration as e:
            logger.info("Iteration stopped. %s", e)

        # execute endJob(..)
        logger.debug("Execute endJob(..)")
        for mod_name, mod_obj in self.getModules().items():
            mod_obj.endJob()

        # execute endJob(..) of dispersion modules
        logger.debug("Execute endJob(..) of dispersion modules")
        for (
            dispersion_mod_name,
            dispersion_mod_obj,
        ) in self.getDispersionModules().items():
            dispersion_mod_obj.endJob()

    def getModules(self):
        return self._source_modules

    def _warn_if_partial_year(self) -> None:
        """Warn when [start_dt, end_dt] doesn't cover a full calendar
        year, since the per-hour profile-mean divisor uses the calendar
        year length. See run() for context.

        - Multi-year (year(end_dt) > year(start_dt)+1): skipped.
        - Spans exactly one calendar year: warn if period count
          differs from 8760 / 8784.
        - Spans into next year by ≤ 1 hour (e.g. start=Jan 1 00:00,
          end=Jan 1 00:00 next year inclusive): treated as full-year.

        Sub-hourly intervals are tolerated: the warning compares
        against `hours_in_year(year) * (3600 / time_interval_seconds)`.
        """
        import calendar

        start = self._start_dt
        end = self._end_dt
        ti_seconds = self._time_interval.total_seconds()
        if ti_seconds <= 0:
            return

        # Multi-year: skip. The profile cache invalidates per year
        # and the warning would mis-report.
        if end.year > start.year + 1:
            return
        if end.year == start.year + 1 and not (
            end.month == 1 and end.day == 1 and end.hour == 0
        ):
            return

        year = start.year
        hours_per_year = 8784 if calendar.isleap(year) else 8760
        expected_periods = int(hours_per_year * 3600 / ti_seconds)

        # Counting via len(list(getTimeSeries())) - 1 (pairwise pair count).
        n_periods = max(0, len(list(self.getTimeSeries())) - 1)

        if n_periods == expected_periods:
            return  # full year coverage

        delta = n_periods - expected_periods
        pct = abs(delta) * 100.0 / max(expected_periods, 1)
        sign = "extra" if delta > 0 else "missing"
        logger.warning(
            "Year %d has %d hours; the [start_dt=%s, end_dt=%s, interval=%ss] "
            "interval yields %d periods (%d %s, ~%.2f%%). Per-hour profile mean "
            "is computed against the full calendar year, so this run will "
            "%s annual totals by approximately that fraction. Set end_dt to "
            "%s-01-01 00:00:00 for a full leap-year-aware coverage.",
            year,
            hours_per_year,
            start.isoformat(),
            end.isoformat(),
            int(ti_seconds),
            n_periods,
            abs(delta),
            sign,
            pct,
            "over-report" if delta > 0 else "under-report",
            year + 1,
        )

    def getDispersionModules(self):
        return self._dispersion_modules

    def getEmissions(self):
        return self._emissions

    def sortEmissionsByTime(self):
        # sort emissions by index (which is a timestamp)
        self._emissions = dict(
            sorted(iter(self.getEmissions().items()), key=lambda x: x[0])
        )

    def getDatabasePath(self):
        return self._database_path

    def getTimeSeries(self):
        dt = self._start_dt
        while dt >= self._start_dt and dt <= self._end_dt:
            yield dt

            dt += self._time_interval

    def get3DGrid(self):
        return self._grid

