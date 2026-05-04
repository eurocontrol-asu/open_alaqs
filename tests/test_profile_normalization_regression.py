"""Regression test for the profile normalisation fix in SourceModule.

Bug:
  SourceWithTimeProfileModule.getRelativeActivityPerHour returned the raw
  product

      operating_factor * hour_factor * weekday_factor * month_factor

  without normalisation. ALAQS data model treats the three profiles
  (hour, weekday, month) as separable relative weights: total annual
  activity comes from unit_year (or ops_year), and the profiles encode
  only how that activity is distributed across hours / weekdays /
  months. For this to be physically meaningful, the calendar-weighted
  mean of the product (hour x weekday x month) must be 1.0; otherwise
  profile shape silently leaks into mass.

  Profiles authored at "convenient" levels (e.g. low overnight, high
  morning, moderate afternoon for a heating source) often have a
  calendar-weighted mean below 1.0, which silently down-scales the
  annual emission. Symptom: an area source with `unit_year=1000`,
  EF=10 kg/unit was expected to emit 10,000 kg/year but actually
  emitted ~9,500 kg/year because the heating-style hour profile
  averaged 0.95.

Fix:
  Divide getRelativeActivityPerHour's return value by the
  calendar-weighted mean of the profile product over the inventory
  year. The mean is cached per (hour_name, day_name, month_name, year)
  tuple to keep the 8760-hour loop one-shot per unique profile triplet.

This test exercises only the helper logic on stub profile objects, so
it can run without a full QGIS or spatialite environment.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime
from types import SimpleNamespace

import pytest


# SourceModule.py imports UserTimeProfiles -> SQLSerializable -> sql_interface
# which loads `qgis.utils.spatialite_connect` at module load. The tests in
# this file exercise pure-Python paths (only the new _get_profile_mean
# helper and the modified return in getRelativeActivityPerHour, both
# fed from in-memory stub profile objects) and never touch SQL, so we
# stub the qgis namespace to allow standalone execution outside the
# QGIS Python.
def _ensure_qgis_stubs():
    if "qgis" not in sys.modules:
        sys.modules["qgis"] = types.ModuleType("qgis")

    qgis_utils = sys.modules.get("qgis.utils") or types.ModuleType("qgis.utils")

    def _spatialite_connect(db_name, *args, **kwargs):
        """Plain sqlite3 connect. Adequate stub even though this test never
        opens a connection."""
        import sqlite3

        return sqlite3.connect(db_name)

    qgis_utils.spatialite_connect = _spatialite_connect
    sys.modules["qgis.utils"] = qgis_utils
    sys.modules["qgis"].utils = qgis_utils

    if "qgis.core" not in sys.modules:
        qgis_core = types.ModuleType("qgis.core")

        class _QgsStub:
            """Stand-in for qgis.core.Qgis / QgsMessageLog. Calls become
            no-ops, attribute access returns more stubs."""

            Info = Warning = Critical = 0

            def __getattr__(self, name):
                return _QgsStub()

            def __call__(self, *args, **kwargs):
                return None

        qgis_core.Qgis = _QgsStub()
        qgis_core.QgsMessageLog = _QgsStub()
        sys.modules["qgis.core"] = qgis_core
        sys.modules["qgis"].core = qgis_core


_ensure_qgis_stubs()


from open_alaqs.core.interfaces.SourceModule import (  # noqa: E402
    SourceWithTimeProfileModule,
)


# Stub profile objects with the same .getHours / .getDays / .getMonths
# interface as UserHourProfile / UserDayProfile / UserMonthProfile.
def _stub_hour(values):
    """values: list of 24 floats indexed by hour-of-day 0..23."""
    return SimpleNamespace(getHours=lambda v=list(values): v)


def _stub_day(monday_to_sunday):
    """monday_to_sunday: list of 7 floats, indexed by abbreviation
    (mon..sun) downstream."""
    abbr_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    d = dict(zip(abbr_keys, monday_to_sunday))
    return SimpleNamespace(getDays=lambda v=d: v)


def _stub_month(jan_to_dec):
    """jan_to_dec: list of 12 floats, indexed by abbreviation downstream."""
    abbr_keys = [
        "jan",
        "feb",
        "mar",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
    ]
    m = dict(zip(abbr_keys, jan_to_dec))
    return SimpleNamespace(getMonths=lambda v=m: v)


def _make_module(hour_profiles, day_profiles, month_profiles):
    """Build a SourceWithTimeProfileModule populated with stub profile
    stores so we can call getRelativeActivityPerHour and
    _get_profile_mean without a database.

    hour_profiles: dict of name -> stub hour profile
    day_profiles:  dict of name -> stub day profile
    month_profiles: dict of name -> stub month profile
    """
    mod = SourceWithTimeProfileModule.__new__(SourceWithTimeProfileModule)

    # Bypass beginJob() (which expects a database). Initialise the bits
    # getRelativeActivityPerHour and _get_profile_mean actually touch.
    mod._userHourProfileStore = SimpleNamespace(
        getObject=lambda name: hour_profiles.get(name)
    )
    mod._userDayProfileStore = SimpleNamespace(
        getObject=lambda name: day_profiles.get(name)
    )
    mod._userMonthProfileStore = SimpleNamespace(
        getObject=lambda name: month_profiles.get(name)
    )
    mod._hours_in_year = 0
    mod._hours_in_year_year = -1
    mod._profile_cache = {}
    mod._profile_mean_cache = {}
    return mod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDefaultProfileBehaviorUnchanged:
    """All-1.0 profiles must produce mean=1.0 exactly, so the multiplier
    is unchanged from the legacy behavior. This is the common case in
    the existing OpenALAQS template profiles and the EHRD road/parking
    inventory; the fix must not change their totals."""

    def setup_method(self, method):
        self.mod = _make_module(
            hour_profiles={"default": _stub_hour([1.0] * 24)},
            day_profiles={"default": _stub_day([1.0] * 7)},
            month_profiles={"default": _stub_month([1.0] * 12)},
        )

    def test_default_mean_is_one(self):
        mean = self.mod._get_profile_mean("default", "default", "default", 2025)
        assert mean == pytest.approx(1.0, abs=1e-12)

    def test_default_multiplier_unchanged(self):
        # Inventory dt arbitrary; mean=1.0 means division is a no-op.
        result = self.mod.getRelativeActivityPerHour(
            datetime(2025, 6, 15, 12),
            8760,  # operating_hours == hours_in_year => operating_factor = 1
            "default",
            "default",
            "default",
        )
        assert result == pytest.approx(1.0, abs=1e-12)


class TestProfileNormalisesAnnualTotal:
    """A heating-style profile with hour-mean below 1.0 should still
    produce an annual sum equal to operating_factor * hours_in_year
    after the fix. Before the fix, it would be ~5% too low."""

    def setup_method(self, method):
        # Hour profile loosely modelled on a building-heating shape:
        # low overnight, peak in morning and evening, moderate midday.
        # Calendar-weighted mean works out to ~0.95.
        hour_values = [
            0.30,  # 00
            0.20,  # 01
            0.20,  # 02
            0.20,  # 03
            0.30,  # 04
            0.50,  # 05
            1.20,  # 06
            1.80,  # 07
            1.80,  # 08
            1.50,  # 09
            1.20,  # 10
            1.10,  # 11
            1.00,  # 12
            1.00,  # 13
            1.00,  # 14
            1.00,  # 15
            1.20,  # 16
            1.50,  # 17
            1.80,  # 18
            1.50,  # 19
            1.00,  # 20
            0.80,  # 21
            0.60,  # 22
            0.40,  # 23
        ]
        self.mod = _make_module(
            hour_profiles={"heating": _stub_hour(hour_values)},
            day_profiles={"default": _stub_day([1.0] * 7)},
            month_profiles={"default": _stub_month([1.0] * 12)},
        )

    def test_profile_mean_below_one(self):
        """Confirm the test fixture actually reproduces the bug condition."""
        mean = self.mod._get_profile_mean("heating", "default", "default", 2025)
        # Hour-only mean = sum/24, with daily/monthly = 1 the calendar-weighted
        # mean should equal that.
        expected = (
            sum(
                [
                    0.30,
                    0.20,
                    0.20,
                    0.20,
                    0.30,
                    0.50,
                    1.20,
                    1.80,
                    1.80,
                    1.50,
                    1.20,
                    1.10,
                    1.00,
                    1.00,
                    1.00,
                    1.00,
                    1.20,
                    1.50,
                    1.80,
                    1.50,
                    1.00,
                    0.80,
                    0.60,
                    0.40,
                ]
            )
            / 24
        )
        assert mean == pytest.approx(expected, abs=1e-9)
        assert mean < 1.0  # confirms bug condition

    def test_annual_sum_equals_ef_times_unit_year(self):
        """Walk all 8760 hours of 2025; the sum of getRelativeActivityPerHour
        should equal annual_total_operating_hours regardless of profile shape.

        This is the core property the fix establishes: profile shape no
        longer leaks into mass.
        """
        total = 0.0
        dt = datetime(2025, 1, 1, 0, 0)
        one_hour_seconds = 3600
        for _ in range(8760):
            total += self.mod.getRelativeActivityPerHour(
                dt, 8760, "heating", "default", "default"
            )
            # Increment by one hour
            ts = dt.timestamp() + one_hour_seconds
            dt = datetime.fromtimestamp(ts)
        # Within float precision the annual sum should equal hours_in_year
        # exactly (operating_factor=1 by construction).
        assert total == pytest.approx(8760.0, rel=1e-9)

    def test_temporal_shape_preserved(self):
        """Normalisation only rescales magnitude. The relative shape (peak vs
        trough) must be preserved."""
        # Pick a peak hour (07:00 = 1.80) and a trough hour (02:00 = 0.20)
        peak = self.mod.getRelativeActivityPerHour(
            datetime(2025, 6, 15, 7), 8760, "heating", "default", "default"
        )
        trough = self.mod.getRelativeActivityPerHour(
            datetime(2025, 6, 15, 2), 8760, "heating", "default", "default"
        )
        # Original profile ratio is 1.80 / 0.20 = 9
        assert peak / trough == pytest.approx(9.0, rel=1e-12)


class TestProfileMeanCache:
    """The cache amortises the 8760-hour loop across all sources sharing
    the same (hour, day, month, year) tuple."""

    def setup_method(self, method):
        self.mod = _make_module(
            hour_profiles={"default": _stub_hour([1.0] * 24)},
            day_profiles={"default": _stub_day([1.0] * 7)},
            month_profiles={"default": _stub_month([1.0] * 12)},
        )

    def test_cache_hit_avoids_recomputation(self):
        # First call populates cache.
        self.mod._get_profile_mean("default", "default", "default", 2025)
        assert ("default", "default", "default", 2025) in self.mod._profile_mean_cache

        # Mutate the underlying profile to a different mean. If the cache is
        # working, the second call should still return 1.0 (the cached value).
        self.mod._userHourProfileStore = SimpleNamespace(
            getObject=lambda name: _stub_hour([2.0] * 24)
        )
        # Have to clear _profile_cache too (otherwise both old caches lie).
        # Actually, deliberately do NOT clear _profile_cache - the test is
        # whether the mean cache short-circuits the computation; if it does,
        # we never reach the underlying profile store.
        result = self.mod._get_profile_mean("default", "default", "default", 2025)
        assert result == pytest.approx(1.0, abs=1e-12)

    def test_different_year_different_cache_key(self):
        """2024 (leap year, 8784 hours) and 2025 (non-leap, 8760 hours)
        produce nominally the same mean for all-1.0 profiles, but use
        different cache entries."""
        m_2025 = self.mod._get_profile_mean("default", "default", "default", 2025)
        m_2024 = self.mod._get_profile_mean("default", "default", "default", 2024)
        assert m_2025 == pytest.approx(1.0, abs=1e-12)
        assert m_2024 == pytest.approx(1.0, abs=1e-12)
        assert ("default", "default", "default", 2024) in self.mod._profile_mean_cache
        assert ("default", "default", "default", 2025) in self.mod._profile_mean_cache


class TestEdgeCases:
    def test_all_zero_profile_returns_zero_emission_safely(self):
        """If a user authors an all-zero profile (e.g. 'never operates'),
        the emission must be 0, not raise ZeroDivisionError."""
        mod = _make_module(
            hour_profiles={"zero": _stub_hour([0.0] * 24)},
            day_profiles={"default": _stub_day([1.0] * 7)},
            month_profiles={"default": _stub_month([1.0] * 12)},
        )
        # Helper guards against div-by-zero by returning 1.0 when mean is 0;
        # the multiplier is 0 anyway so emission ends up at 0.
        mean = mod._get_profile_mean("zero", "default", "default", 2025)
        assert mean == 1.0  # safety guard
        result = mod.getRelativeActivityPerHour(
            datetime(2025, 6, 15, 12), 8760, "zero", "default", "default"
        )
        assert result == 0.0

    def test_missing_profile_falls_through_to_existing_error_path(self):
        """A missing profile should raise the existing 'Could not retrieve...'
        exception, not silently fall into the normalisation path."""
        mod = _make_module(
            hour_profiles={"default": _stub_hour([1.0] * 24)},
            day_profiles={"default": _stub_day([1.0] * 7)},
            month_profiles={"default": _stub_month([1.0] * 12)},
        )
        with pytest.raises(Exception, match="Could not retrieve"):
            mod._get_profile_mean("nonexistent", "default", "default", 2025)
