"""
profiles_vec: vectorised activity-profile expansion for OpenALAQS.

Produces an entire 8760- or 8784-element multiplier array per call so
the emission inner loop can be replaced by one numpy multiplication
per (source, pollutant). The per-hour scalar code path in
core/interfaces/SourceModule.py
(`getRelativeActivityPerHour` / `_get_profile_mean`) is the reference
behaviour; the two paths produce element-wise equal results within
floating-point precision.

Normalisation invariant
-----------------------
For any profile triplet, the multipliers are rescaled so that
    mean(mults_over_year) == 1.0
which matches the existing per-hour code that divides h*d*m by their
calendar-weighted yearly mean. With this invariant, per-hour emission
is `(annual_total / n_hours) * mults[h]` and `sum_h(out) ==
annual_total` to float precision regardless of profile shape.

Leap-year handling
------------------
Year length is 8784 for leap years, 8760 otherwise — matching
SourceModule.getRelativeActivityPerHour (`_hours_in_year`). The
upstream standalone (`openalaqs_standalone/_profiles.py`) always uses
8760 and skips Feb 29; we deliberately differ so plugin scalar and
vectorised paths agree on leap and non-leap years alike.

KNOWN INCONSISTENCY at the AUSTAL boundary:
AUSTAL's annual-mean statistics divide by a hardcoded 8760 regardless
of leap year (TA Luft 2021, AUSTAL 3.3 doc). Feeding 8784 hourly rates
into a series.dmna therefore biases the reported annual mean ~0.27%
high. The de-facto AUSTAL convention is "8760 hours per year, always".
We keep 8784 in the inventory path to preserve emission totals
bit-for-bit and accept the small bias at the AUSTAL writer boundary.
A later refactor can skip Feb 29 or insert a length-aware divisor
adjustment. See the standalone and austal_prep, both of which use
8760 throughout.

This module is plugin-internal. It does not run SQL: profile data is
read from the already-populated `User{Hour,Day,Month}ProfileStore`
Singletons that EmissionCalculation initialises during construction.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

import numpy as np
import pandas as pd

# Must match SourceModule.month_abbreviations / weekday_abbreviations
# byte-for-byte (those dicts are the keys used by UserDayProfile and
# UserMonthProfile internally; see UserTimeProfiles.py).
_WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_MONTH_KEYS = (
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
)

__all__ = [
    "ProfileSet",
    "build_profile_set",
    "hours_in_year",
    "hourly_multipliers",
    "spread_annual",
    "hourly_timestamps",
]


@dataclass
class ProfileSet:
    """Activity profiles for a study, keyed by profile name.

    hourly:  name -> shape (24,)  array, one value per hour-of-day
    daily:   name -> shape  (7,)  array, Mon=0 .. Sun=6
    monthly: name -> shape (12,)  array, Jan=0 .. Dec=11
    """

    hourly: Dict[str, np.ndarray]
    daily: Dict[str, np.ndarray]
    monthly: Dict[str, np.ndarray]


def hours_in_year(year: int) -> int:
    """Return 8784 for leap years, 8760 otherwise. Matches the
    plugin's per-hour code (SourceModule._hours_in_year)."""
    return 8784 if calendar.isleap(year) else 8760


def build_profile_set(
    hour_store,
    day_store,
    month_store,
) -> ProfileSet:
    """Build a ProfileSet from the plugin's already-populated Singleton
    stores.

    Parameters
    ----------
    hour_store, day_store, month_store
        Instances of UserHourProfileStore, UserDayProfileStore,
        UserMonthProfileStore (see core/interfaces/UserTimeProfiles.py).
        These are populated lazily on first access via SQL; by the time
        EmissionCalculation reaches the vectorised path, the stores
        already hold every profile defined in the .alaqs file.

    No SQL is run here; we just repackage the OrderedDict contents as
    ndarrays so the vector math can index them with O(1) numpy gather.

    Profiles whose internal value is non-numeric are coerced via
    `float(...)`, matching `_ctf` in UserTimeProfiles which already
    sanitises during load.
    """
    hourly: Dict[str, np.ndarray] = {}
    daily: Dict[str, np.ndarray] = {}
    monthly: Dict[str, np.ndarray] = {}

    for name, prof in hour_store.getObjects().items():
        hd = prof.getHours()  # OrderedDict[int 0..23 -> float]
        hourly[name] = np.array([float(hd[i]) for i in range(24)], dtype=float)

    for name, prof in day_store.getObjects().items():
        dd = prof.getDays()  # OrderedDict["mon".."sun" -> float]
        daily[name] = np.array([float(dd[k]) for k in _WEEKDAY_KEYS], dtype=float)

    for name, prof in month_store.getObjects().items():
        md = prof.getMonths()  # OrderedDict["jan".."dec" -> float]
        monthly[name] = np.array([float(md[k]) for k in _MONTH_KEYS], dtype=float)

    return ProfileSet(hourly=hourly, daily=daily, monthly=monthly)


def hourly_multipliers(
    profiles: ProfileSet,
    hour_profile_name: Optional[str],
    day_profile_name: Optional[str],
    month_profile_name: Optional[str],
    year: int,
) -> np.ndarray:
    """Build a length-`hours_in_year(year)` array of mean-1 multipliers.

    Profile names that are missing, None, or not present in `profiles`
    fall back to all-1.0. This mirrors the legacy code's behaviour of
    resolving unknown names to the 'default' profile (uniform 1.0).

    The result is mean-normalised: `out.mean() == 1.0` to float
    precision, which is the invariant SourceModule._get_profile_mean
    enforces in the scalar path. Combined with `spread_annual`, the
    annual sum of per-hour emissions equals `annual_total` regardless
    of profile shape.

    Implementation note: builds the full 8760/8784 hour calendar via a
    single `pd.date_range`, extracts hour-of-day / weekday / month-1 as
    int ndarrays, and indexes the three profile arrays with them. The
    arithmetic order (hour * day * month) is identical to the per-hour
    scalar code path, so element-wise equality holds.
    """
    n_hours = hours_in_year(year)

    hp = profiles.hourly.get(hour_profile_name) if hour_profile_name else None
    dp = profiles.daily.get(day_profile_name) if day_profile_name else None
    mp = profiles.monthly.get(month_profile_name) if month_profile_name else None

    if hp is None:
        hp = np.ones(24, dtype=float)
    if dp is None:
        dp = np.ones(7, dtype=float)
    if mp is None:
        mp = np.ones(12, dtype=float)

    idx = pd.date_range(
        start=datetime(year, 1, 1, 0, 0, 0),
        periods=n_hours,
        freq="h",
    )

    mults = (
        hp[idx.hour.to_numpy()]
        * dp[idx.weekday.to_numpy()]
        * mp[idx.month.to_numpy() - 1]
    )

    total = float(mults.sum())
    if total <= 0.0:
        # All-zero or pathological profile; fall back to uniform so
        # downstream multiplications stay finite. Emission stays 0
        # because the EF*activity factor is the dominant term and the
        # caller will already have skipped this source if its annual
        # total is zero.
        return np.ones(n_hours, dtype=float)

    return mults * (n_hours / total)


def spread_annual(
    annual_emission: float,
    multipliers: np.ndarray,
) -> np.ndarray:
    """Spread an annual emission across the full year.

    Parameters
    ----------
    annual_emission
        Annual total in any unit (kg, g, vehicles, ...). The output
        carries the same unit per hour.
    multipliers
        Array of length 8760 or 8784, mean-normalised to 1.0 by
        `hourly_multipliers`.

    Returns
    -------
    ndarray of length matching `multipliers`, with
        sum(out) == annual_emission   (to float precision)
        out[h]   = (annual_emission / n_hours) * multipliers[h]
    """
    n_hours = multipliers.shape[0]
    if n_hours not in (8760, 8784):
        raise ValueError(
            f"multipliers length {n_hours} is neither 8760 nor 8784; "
            "did you pass an unnormalised profile triplet?"
        )
    return (annual_emission / n_hours) * multipliers


def hourly_timestamps(year: int) -> pd.DatetimeIndex:
    """Return a DatetimeIndex of length `hours_in_year(year)` covering
    every hour of `year` at hourly resolution.

    Used by output modules that need timestamps in lockstep with the
    multiplier arrays produced by `hourly_multipliers`.
    """
    return pd.date_range(
        start=datetime(year, 1, 1, 0, 0, 0),
        periods=hours_in_year(year),
        freq="h",
    )

