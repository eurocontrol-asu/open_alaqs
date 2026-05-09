import calendar
import os
import sys
from datetime import datetime

import pandas as pd

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.interfaces.UserTimeProfiles import (
    UserDayProfileStore,
    UserHourProfileStore,
    UserMonthProfileStore,
)

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

    # ------------------------------------------------------------------
    # Loop-ordering discriminator.
    #
    # Mirrors `Source.time_invariant_geometry` at the module level. When
    # True, EmissionCalculation.run() pre-computes the per-source hourly
    # activity vector once via `precompute_activity_vectors` before
    # entering the time-major loop, and the module's `process()` reads
    # from that cache instead of calling `getRelativeActivityPerHour` /
    # `getEmissionsForTimePeriod` 8760 times per source.
    #
    # Stationary modules (Roadway, Parking, Point, Area) override to
    # True. MovementSourceModule (aircraft + gates + taxiways) keeps
    # the base False and stays on the time-major path.
    # ------------------------------------------------------------------
    time_invariant_geometry: bool = False

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

    def getSources(self) -> dict[str, Source]:
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

        # Cache hours_in_year once; also pre-resolve profile objects on first
        # use so getRelativeActivityPerHour() does attribute reads rather than
        # store lookups on each of the 8 760 calls per source per year.
        self._hours_in_year: int = 0  # set on first getRelativeActivityPerHour call
        self._hours_in_year_year: int = -1  # tracks which year the cache is valid for
        self._profile_cache: dict = {}  # (hour_name, day_name, month_name) -> (h,d,m)
        # Cache for the calendar-weighted mean of the hour x weekday x month
        # profile product over the inventory year. See _get_profile_mean for
        # rationale.
        self._profile_mean_cache: dict = (
            {}
        )  # (hour_name, day_name, month_name, year) -> mean

    def _get_profiles(self, hour_name, day_name, month_name):
        """Return (hour_profile, day_profile, month_profile), caching by name triple."""
        key = (hour_name, day_name, month_name)
        if key not in self._profile_cache:
            h = self._userHourProfileStore.getObject(hour_name)
            if h is None:
                raise Exception(
                    "Could not retrieve the hourly time profile '%s'." % hour_name
                )
            d = self._userDayProfileStore.getObject(day_name)
            if d is None:
                raise Exception(
                    "Could not retrieve the weekday time profile '%s'." % day_name
                )
            m = self._userMonthProfileStore.getObject(month_name)
            if m is None:
                raise Exception(
                    "Could not retrieve the month time profile '%s'." % month_name
                )
            self._profile_cache[key] = (h, d, m)
        return self._profile_cache[key]

    def _get_profile_mean(self, hour_name, day_name, month_name, year):
        """Return the calendar-weighted mean of hour_factor * weekday_factor *
        month_factor over every hour of `year`.

        ALAQS profiles are separable relative weights: total annual activity
        comes from `unit_year` (or `ops_year`) and the EF, while the three
        profiles encode only how that activity is distributed across hours,
        weekdays, and months. For this separability to be physically meaningful,
        the calendar-weighted mean of (hour x weekday x month) over the year
        must be 1.0; otherwise the profile silently rescales the source's
        annual emission. Profiles whose mean is not 1.0 (e.g. a winter-heavy
        heating profile averaging 0.95) leak shape into mass.

        getRelativeActivityPerHour() now divides its return value by this mean
        so annual emission equals EF * unit_year for any profile triplet,
        within float precision.

        Cost: one 8760-hour loop per unique (hour, day, month, year) tuple,
        amortised across all sources sharing the triplet.
        """
        key = (hour_name, day_name, month_name, year)
        if key not in self._profile_mean_cache:
            hour_profile, weekday_profile, month_profile = self._get_profiles(
                hour_name, day_name, month_name
            )
            hours_in_year = 8784 if calendar.isleap(year) else 8760

            total = 0.0
            dt = datetime(year, 1, 1, 0, 0, 0)
            one_hour = pd.Timedelta(hours=1)
            for _ in range(hours_in_year):
                h = float(hour_profile.getHours()[dt.hour])
                d = float(
                    weekday_profile.getDays()[weekday_abbreviations[dt.weekday()]]
                )
                m = float(month_profile.getMonths()[month_abbreviations[dt.month]])
                total += h * d * m
                dt = dt + one_hour
            mean = total / hours_in_year
            # Guard against the all-zero profile case. Multiplier is already 0
            # so emissions remain 0 regardless; returning 1.0 avoids a divide
            # by zero in getRelativeActivityPerHour.
            self._profile_mean_cache[key] = mean if mean != 0.0 else 1.0
        return self._profile_mean_cache[key]

    def getEmissionsForTimePeriod(
        self,
        start_dt: datetime,
        end_dt: datetime,
        annual_total_operating_hours,
        hour_profile_name,
        daily_profile_name,
        month_profile_name,
    ):
        time_period = end_dt - start_dt
        emit_per_hour = self.getRelativeActivityPerHour(
            start_dt,
            annual_total_operating_hours,
            hour_profile_name,
            daily_profile_name,
            month_profile_name,
        )
        emit_per_second = emit_per_hour / 60 / 60

        return emit_per_second * time_period.total_seconds()

    def getRelativeActivityPerHour(
        self,
        inventory_dt: datetime,
        annual_total_operating_hours,
        hour_profile_name,
        daily_profile_name,
        month_profile_name,
    ):
        # Refresh hours_in_year if the calendar year changes (handles multi-year
        # runs and the leap-year boundary correctly).
        year = inventory_dt.year
        if year != self._hours_in_year_year:
            self._hours_in_year = 8784 if calendar.isleap(year) else 8760
            self._hours_in_year_year = year

        hour_profile, weekday_profile, month_profile = self._get_profiles(
            hour_profile_name, daily_profile_name, month_profile_name
        )

        operating_factor = float(annual_total_operating_hours) / self._hours_in_year
        hour_factor = float(hour_profile.getHours()[inventory_dt.hour])
        weekday_factor = float(
            weekday_profile.getDays()[weekday_abbreviations[inventory_dt.weekday()]]
        )
        month_factor = float(
            month_profile.getMonths()[month_abbreviations[inventory_dt.month]]
        )

        # Normalise by the calendar-weighted profile mean so annual emission
        # equals EF * unit_year regardless of whether the user-supplied
        # profile triplet averages to 1.0. See _get_profile_mean docstring.
        profile_mean = self._get_profile_mean(
            hour_profile_name, daily_profile_name, month_profile_name, year
        )

        return (
            operating_factor
            * hour_factor
            * weekday_factor
            * month_factor
            / profile_mean
        )

    # ------------------------------------------------------------------
    # Vectorised fast-path cache.
    #
    # `EmissionCalculation.run()` calls `precompute_activity_vectors` on
    # each stationary module before entering the time-major loop. This
    # populates a per-source ndarray of length 8760/8784, computed once
    # via `Source.getHourlyActivityVector`. The module's `process()`
    # then reads scalar per-hour activity from the cache via
    # `_try_get_per_hour_activity` (O(1) ndarray index) instead of
    # walking 8760 hours through `_get_profile_mean` and per-hour
    # profile lookups.
    #
    # The cache is keyed by source_id and validated by year, so
    # multi-year runs and database swaps invalidate it implicitly. When
    # the cache is absent or stale, `_try_get_per_hour_activity`
    # returns None and the scalar fallback path runs unchanged.
    # ------------------------------------------------------------------
    def precompute_activity_vectors(self, profile_set, year: int) -> None:
        """Build the per-source hourly activity vector cache.

        Parameters
        ----------
        profile_set
            A `core.tools.profiles_vec.ProfileSet` built from the
            already-populated User{Hour,Day,Month}ProfileStore
            singletons (typically constructed once in
            EmissionCalculation.run() and shared across all stationary
            modules).
        year
            Calendar year of the inventory; used for leap-year length
            and as the cache validity key.

        Sources flagged `instudy='0'` are skipped — they are excluded
        from emission output by the per-source filter in `process()`,
        so caching their vectors would just waste memory.
        """
        from datetime import datetime

        self._activity_vec_cache: dict = {}
        self._activity_vec_year: int = year
        # Anchor for index arithmetic. Plain datetime (no tz) matches
        # the start_dt the time-major loop passes in.
        self._activity_vec_t0 = datetime(year, 1, 1, 0, 0, 0)

        for source_id, source in self.getSources().items():
            if not source.isInStudy():
                continue
            self._activity_vec_cache[source_id] = source.getHourlyActivityVector(
                profile_set, year
            )

    def _try_get_per_hour_activity(self, source_id: str, inventory_dt: datetime):
        """Return cached per-hour activity for `source_id` at
        `inventory_dt`, or None when the cache is absent / stale /
        out of range.

        On a cache hit, the returned scalar is element-wise equal
        (within float precision) to
            getRelativeActivityPerHour(
                inventory_dt, units_per_year, hour, day, month
            )
        for the same source — by construction in
        `Source.getHourlyActivityVector` and `profiles_vec`.
        """
        cache = getattr(self, "_activity_vec_cache", None)
        if cache is None:
            return None
        if source_id not in cache:
            return None
        if inventory_dt.year != self._activity_vec_year:
            return None
        h_idx = int(
            (inventory_dt - self._activity_vec_t0).total_seconds() // 3600
        )
        arr = cache[source_id]
        if h_idx < 0 or h_idx >= arr.shape[0]:
            return None
        return float(arr[h_idx])
