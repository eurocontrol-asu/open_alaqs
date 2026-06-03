"""
_profiles: helpers shared by the compute_* modules.

Loads ALAQS activity profiles (hourly, weekly, monthly multipliers) and
spreads an annual emission across all hours of the year using the
profile triplet for a given source.

Year length is 8784 for leap years, 8760 otherwise. This matches the
QGIS Open-ALAQS plugin (SourceModule._hours_in_year). Feb 29 is
included in leap years rather than skipped.

The ALAQS profile model:
    Each profile table has a 'name' column and N value columns (24 for
    hourly, 7 for daily, 12 for monthly). A source picks one profile
    name per axis. The value for hour h of the year is:
        v(h) = hour_profile[hour_of_day] * day_profile[weekday] * month_profile[month]
    The annual emission is split across the year proportionally to v(h),
    so that sum_h(emission_per_hour) == annual_emission.

If a profile is missing or all-1.0, the contribution is uniform and the
multiplier is 1.0 for every hour.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

import numpy as np
import pandas as pd

# The full set of pollutants every stationary compute (road, parking,
# point, area) supports. Each of those modules maps these labels to a
# column in its source table, so this is exactly the set that can be
# requested without a compute hitting a missing column. It is the
# default pollutant list for the stationary computes and for
# `orchestrate`: "all pollutants" means this set.
#
# Note this differs from the aircraft core's POLLUTANTS
# ("co", "co2", "hc", "nox", "sox", "pm10"): the stationary source
# tables carry pm25 (the p1/p2 fraction columns) but no co2, while
# the aircraft core carries co2 but no pm25. The two source families
# genuinely have different pollutant universes; nothing here forces
# them to agree.
STATIONARY_POLLUTANTS = ("co", "hc", "nox", "sox", "pm10", "pm25")


def hours_in_year(year: int) -> int:
    """Return 8784 for leap years, 8760 otherwise.

    Matches the QGIS Open-ALAQS plugin's SourceModule._hours_in_year so
    plugin (scalar) and standalone (vectorised) paths produce identical
    annual emission totals on both leap and non-leap years.
    """
    return 8784 if calendar.isleap(year) else 8760


@dataclass
class ProfileSet:
    """Activity profiles loaded from an .alaqs database, keyed by name."""

    hourly: Dict[str, np.ndarray]  # name -> shape (24,) array
    daily: Dict[str, np.ndarray]  # name -> shape (7,)  array
    monthly: Dict[str, np.ndarray]  # name -> shape (12,) array


def load_profiles(conn: sqlite3.Connection) -> ProfileSet:
    """Read all three profile tables from the .alaqs file.

    Schema:
        user_hour_profile:  pk, name, h00..h23
        user_day_profile:   pk, name, mon..sun
        user_month_profile: pk, name, jan..dec
    """
    hourly: Dict[str, np.ndarray] = {}
    daily: Dict[str, np.ndarray] = {}
    monthly: Dict[str, np.ndarray] = {}

    cur = conn.cursor()

    for row in cur.execute("SELECT * FROM user_hour_profile"):
        name = row[1]
        values = np.asarray(row[2:26], dtype=float)
        hourly[name] = values

    for row in cur.execute("SELECT * FROM user_day_profile"):
        name = row[1]
        values = np.asarray(row[2:9], dtype=float)
        daily[name] = values

    for row in cur.execute("SELECT * FROM user_month_profile"):
        name = row[1]
        values = np.asarray(row[2:14], dtype=float)
        monthly[name] = values

    return ProfileSet(hourly=hourly, daily=daily, monthly=monthly)


def hourly_multipliers(
    profiles: ProfileSet,
    hour_name: Optional[str],
    day_name: Optional[str],
    month_name: Optional[str],
    year: int,
) -> np.ndarray:
    """Build a length-`hours_in_year(year)` array of multipliers for the
    given profile triplet.

    Each entry is hourly[hour_of_day] * daily[weekday] * monthly[month].
    The multiplier is normalised so that mean(mults) == 1.0, i.e. for
    any hour h the per-hour emission can be computed as
    `(annual_total / n_hours) * mults[h]` without further normalisation.
    """
    hp = profiles.hourly.get(hour_name or "", np.ones(24))
    dp = profiles.daily.get(day_name or "", np.ones(7))
    mp = profiles.monthly.get(month_name or "", np.ones(12))

    n_hours = hours_in_year(year)
    mults = np.empty(n_hours, dtype=float)
    t = datetime(year, 1, 1, 0, 0, 0)
    for h_idx in range(n_hours):
        mults[h_idx] = hp[t.hour] * dp[t.weekday()] * mp[t.month - 1]
        t += timedelta(hours=1)

    # Normalise so the mean over the year is 1.0
    total = float(mults.sum())
    if total <= 0.0:
        return np.ones(n_hours, dtype=float)
    return mults * (n_hours / total)


def hourly_timestamps(year: int) -> pd.DatetimeIndex:
    """Hourly timestamps covering the full calendar year.

    Length is 8784 for leap years, 8760 otherwise. Feb 29 is included
    in leap years.
    """
    return pd.date_range(
        start=datetime(year, 1, 1, 0, 0, 0),
        periods=hours_in_year(year),
        freq="h",
    )


def window_mask(
    timestamps: pd.DatetimeIndex,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> np.ndarray:
    """Return a boolean mask over `timestamps` selecting the half-open
    window `[start, end)`.

    `start` and `end` may be naive datetimes; they are compared
    directly against the (also naive) timestamps. If both are None the
    mask is all-True (full year).

    The half-open convention means an hour at exactly `end` is
    excluded, so a window of `[2025-01-01, 2025-01-08)` selects
    exactly 168 hours. This makes window concatenation unambiguous
    (back-to-back windows don't double-count the boundary hour).

    A movement filter (compute_movements / parallel) uses a parallel
    rule: a movement is included iff its start timestamp is in the
    same half-open window.
    """
    if start is None and end is None:
        return np.ones(len(timestamps), dtype=bool)
    ts = timestamps
    mask = np.ones(len(ts), dtype=bool)
    if start is not None:
        mask &= ts >= pd.Timestamp(start)
    if end is not None:
        mask &= ts < pd.Timestamp(end)
    return mask


def spread_annual(
    annual_emission_kg: float,
    multipliers: np.ndarray,
) -> np.ndarray:
    """Spread an annual emission (kg) across the year's hourly grid.

    Returns an array of kg-per-hour values where:
        sum(out) ~= annual_emission_kg  (within float precision)
        out[h] = (annual / n_hours) * multipliers[h]
    n_hours is inferred from `multipliers.shape[0]`. Caller is
    responsible for using a multipliers array built for the right year
    (length 8760 or 8784).
    """
    n_hours = multipliers.shape[0]
    if n_hours not in (8760, 8784):
        raise ValueError(
            f"multipliers length {n_hours} not in (8760, 8784); "
            f"expected the output of hourly_multipliers(...)"
        )
    per_hour = annual_emission_kg / n_hours
    return per_hour * multipliers
