"""ICCAIA / CAEP14 v14 NOx correction for ambient conditions.

Mirrors the plugin's `core/tools/nox_correction_ambient.py`. The
correction is the simple-method correction for take-off and climb-out
NOx emissions, taking into account: weight ratio (tow_ratio), ambient
temperature deviation from ISA, and ambient humidity.

Formula (ICCAIA simple correction, equivalent to ICAO Annex 16 Vol II
Appendix 3 / CAEP14 v14):

    EI_NOx_corrected = EI_NOx_ref
        * (1 + 1.55 * (tow_ratio - 1) + 0.012 * (T - T_isa))
        * exp(19.0 * (0.00634 - h))

where:
    T       ambient temperature (K)
    T_isa   ISA temperature at the airport elevation (K)
    h       ambient humidity ratio (kg water / kg dry air)
    tow_ratio  takeoff weight ratio (defaults to 1.0; correction term
               vanishes when ratio = 1)
    P_sat   saturation vapour pressure (Pa), Magnus formula
    P_a     ambient pressure (Pa)

The correction applies only at modes TO and CL (per ICCAIA guidance).
Approach and idle modes are not corrected because the simple-method
correction is not valid there.

The correction is gated behind a `apply_nox_corrections` flag (default
False). When the BFFM2 method is in use, the correction is suppressed
because BFFM2 already incorporates ambient corrections through its own
EI calculation; double-correcting would be wrong.
"""

from __future__ import annotations

import math
from typing import Optional

# ICCAIA reference humidity ratio (kg water / kg dry air). At this
# humidity the exp term equals 1.0 (no correction).
_H_REF_KG_PER_KG = 0.00634

# Modes that receive the simple-method correction. Approach (AP) and
# idle/taxi (TX) are not corrected.
_CORRECTED_MODES = frozenset({"TO", "CL"})


def _isa_temperature_k(elevation_m: float) -> float:
    """ISA standard temperature (K) at airport elevation.

    Lapse rate -6.5 K/km from sea-level ISA (15 degC = 288.15 K).
    Same constant as the plugin (nox_correction_ambient.py:58).
    """
    return 288.15 + (elevation_m / 1000.0) * (-6.5)


def _humidity_ratio(
    temperature_k: float, pressure_pa: float, relative_humidity: float
) -> float:
    """Ambient humidity ratio h (kg water / kg dry air).

    Magnus saturation vapour pressure (hPa, equivalent to mbar), with
    the pressure expression in psia per the plugin. Same formula as
    nox_correction_ambient.py:65-71.
    """
    t_c = temperature_k - 273.15
    # P_sat in hPa (= mbar)
    p_sat_hpa = 6.1078 * 10.0 ** ((7.5 * t_c) / (237.3 + t_c))
    # P_psia from Pa: Pa * 1e-3 (kPa) * 0.14504 (kPa -> psia)
    p_psia = pressure_pa * 1e-3 * 0.14504
    # Humidity ratio per plugin formula. The constant 68.9473 is the
    # psia->hPa conversion that aligns the units of (P_psia - RH*P_sat)
    # to hPa-equivalents. Kept verbatim from the plugin for bit match.
    denom = (p_psia * 68.9473) - (relative_humidity * p_sat_hpa)
    if denom <= 0.0:
        return 0.0
    return (0.62197058 * relative_humidity * p_sat_hpa) / denom


def correction_factor(
    mode: str,
    temperature_k: float,
    pressure_pa: float,
    relative_humidity: float,
    airport_elevation_m: float,
    tow_ratio: Optional[float] = None,
) -> float:
    """Return the multiplicative NOx correction factor for one segment.

    Returns 1.0 (no correction) when `mode` is not in {"TO", "CL"}, so
    callers can multiply the segment's NOx unconditionally without
    branching on mode.

    Parameters
    ----------
    mode
        Segment LTO mode label: "TO", "CL", "AP", "TX", "ID".
    temperature_k, pressure_pa, relative_humidity
        Ambient conditions from the per-period meteo row. RH is the
        fractional humidity (0 - 1), not a percentage.
    airport_elevation_m
        Airport reference elevation (metres), from
        user_study_setup.airport_elevation.
    tow_ratio
        Takeoff weight ratio. When None or unset (the typical case),
        defaults to 1.0 so the weight term contributes 0.

    Notes
    -----
    For mode in {"TO", "CL"} the returned factor is

        (1 + 1.55 * (tow_ratio - 1) + 0.012 * (T - T_isa))
            * exp(19.0 * (0.00634 - h))

    matching the plugin's nox_correction_for_ambient_conditions.
    """
    if mode not in _CORRECTED_MODES:
        return 1.0
    if tow_ratio is None or tow_ratio <= 0.0:
        tow_ratio = 1.0
    t_isa = _isa_temperature_k(airport_elevation_m)
    h = _humidity_ratio(temperature_k, pressure_pa, relative_humidity)
    weight_term = 1.55 * (tow_ratio - 1.0)
    temp_term = 0.012 * (temperature_k - t_isa)
    humidity_factor = math.exp(19.0 * (_H_REF_KG_PER_KG - h))
    return (1.0 + weight_term + temp_term) * humidity_factor
