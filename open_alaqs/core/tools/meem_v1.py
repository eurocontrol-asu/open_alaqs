"""
meem_v1.py — MEEM V1 nvPM emission index calculator
=====================================================
Implements the Main Engine Emission Model version 1 (MEEM V1) as specified
in ICAO CAEP/13-MDG and validated against CAEP14 FBE Calculation Sheet v12.

MEEM V1 is the standard method for computing non-volatile PM (nvPM) emission
indices. It has two distinct roles:

  LTO phase (altitude < ~914 m, Mach < ~0.3):
    Log-log interpolation of nvPM mass EI and linear interpolation of nvPM
    number EI between the four (or five) EEDB certification points. No altitude
    correction is applied within the LTO domain.

  Non-LTO phase (cruise, climb, descent):
    Full altitude correction chain:
      1. ISA atmosphere at segment altitude.
      2. Total conditions at engine inlet (PT,alt, TT,alt) via Mach number.
      3. Combustor inlet conditions at altitude (P3,alt, T3,alt) via OPR and ηcomp.
      4. Combustor inlet at ground reference (P3,GR, T3,GR) at ISA MSL.
      5. Equivalent GR thrust setting via the pressure ratio Πalt = P3,alt / P3,GR.
      6. Interpolate nvPM EI at the GR-equivalent thrust from the EEDB points.
      7. Apply DLR enrichment factor φ = (T3,alt / T3,GR)^n for mass;
         same correction for number with a separate exponent.

For OpenALAQS LTO operations only steps 1–6 are relevant and the altitude
correction is negligible below ~914 m. Step 7 is provided for completeness
and for future non-LTO extension.

References:
  ICAO CAEP/13-MDG, MEEM V1 specification (2019).
  CAEP14 FBE Engines Emissions Calculation Sheet v12, "MEEM_V1" tab.
  ICAO Doc 9889, Air Quality Manual, 3rd edition (2011) / updates.
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ── Physical / ISA constants ──────────────────────────────────────────────────


@dataclass(frozen=True)
class _ISA:
    T0: float = 288.15  # Sea-level temperature (K)
    P0: float = 101_325.0  # Sea-level pressure (Pa)
    lapse: float = -0.0065  # Temperature lapse rate (K/m), troposphere
    tropo_m: float = 11_000.0  # Tropopause altitude (m)
    gamma: float = 1.4  # Ratio of specific heats for dry air
    R: float = 287.05287  # Gas constant for air (J/kg·K)
    g: float = 9.80665  # Gravitational acceleration (m/s²)


ISA = _ISA()

# Exponent for ISA pressure model: g / (R × |lapse|)
_ISA_PRESSURE_EXPONENT = ISA.g / (ISA.R * abs(ISA.lapse))  # ≈ 5.2561

# ── Mode-to-thrust-setting mapping (ICAO LTO cycle) ──────────────────────────

MODE_THRUST: dict[str, float] = {"TO": 1.00, "CL": 0.85, "AP": 0.30, "TX": 0.07}

# Phase-specific compressor efficiency (ηcomp) from CAEP14 Constants tab.
# LTO modes use the climb-out value (conservative; true LTO efficiency is not
# explicitly given in the CAEP14 sheet for ground-level operations).
PHASE_ETA_COMP: dict[str, float] = {
    "TAKE OFF": 0.88,
    "CLIMB OUT": 0.88,
    "CLIMB TO CRUISE": 0.88,
    "CRUISE": 0.88,
    "DESCENT": 0.70,
    "APPROACH": 0.88,
    "TAXI": 0.88,
}

# DLR enrichment model exponents (CAEP14 MEEM_V1 sheet, section 7).
# Typical values from the literature; both exponents are ~1 for standard engines.
_N_MASS: float = 1.0  # enrichment exponent for nvPM mass EI
_N_NUMBER: float = 1.0  # enrichment exponent for nvPM number EI

# Small epsilon guard for log operations
_EPSILON = 1e-15


# ── ISA atmosphere model ──────────────────────────────────────────────────────


def isa_conditions(altitude_m: float) -> tuple[float, float]:
    """
    Compute ISA temperature (K) and pressure (Pa) at a given altitude.

    Valid up to the tropopause (11 000 m / 36 089 ft). Above the tropopause
    the temperature is held constant and pressure follows the isothermal law.

    :param altitude_m: Geometric altitude above MSL (m).
    :return: (T_K, P_Pa)
    """
    h = max(0.0, float(altitude_m))

    if h <= ISA.tropo_m:
        T = ISA.T0 + ISA.lapse * h
        P = ISA.P0 * (T / ISA.T0) ** _ISA_PRESSURE_EXPONENT
    else:
        # Stratosphere: isothermal above 11 km
        T_tropo = ISA.T0 + ISA.lapse * ISA.tropo_m
        P_tropo = ISA.P0 * (T_tropo / ISA.T0) ** _ISA_PRESSURE_EXPONENT
        T = T_tropo
        P = P_tropo * math.exp(-ISA.g * (h - ISA.tropo_m) / (ISA.R * T_tropo))

    return T, P


def total_conditions(
    T_static: float, P_static: float, mach: float
) -> tuple[float, float]:
    """
    Compute total (stagnation) temperature TT and pressure PT at the engine
    inlet from static conditions and Mach number.

    :param T_static: Static temperature (K).
    :param P_static: Static pressure (Pa).
    :param mach:     Flight Mach number (dimensionless, ≥ 0).
    :return: (TT_K, PT_Pa)
    """
    M = max(0.0, float(mach))
    factor = 1.0 + (ISA.gamma - 1.0) / 2.0 * M**2
    TT = T_static * factor
    PT = P_static * factor ** (ISA.gamma / (ISA.gamma - 1.0))
    return TT, PT


def combustor_inlet_conditions(
    TT: float, PT: float, opr: float, eta_comp: float
) -> tuple[float, float]:
    """
    Estimate combustor inlet total temperature T3 and pressure P3 from engine
    inlet total conditions, overall pressure ratio (OPR), and isentropic
    compressor efficiency.

    The isentropic relation with efficiency η is:
        T3 = TT × OPR^((γ-1)/(γ×η))
        P3 = PT × OPR

    :param TT:       Engine inlet total temperature (K).
    :param PT:       Engine inlet total pressure (Pa).
    :param opr:      Overall pressure ratio (dimensionless, > 1).
    :param eta_comp: Isentropic compressor efficiency (0 < η ≤ 1).
    :return: (T3_K, P3_Pa)
    """
    exponent = (ISA.gamma - 1.0) / (ISA.gamma * max(eta_comp, 1e-6))
    T3 = TT * opr**exponent
    P3 = PT * opr
    return T3, P3


# ── Interpolation ─────────────────────────────────────────────────────────────


def _sort_eedb_points(
    thrust_settings: list[float], ei_values: list[float]
) -> tuple[list[float], list[float]]:
    """Return (thrust_settings, ei_values) sorted by ascending thrust setting."""
    paired = sorted(zip(thrust_settings, ei_values), key=lambda x: x[0])
    ts, ei = zip(*paired)
    return list(ts), list(ei)


def interpolate_nvpm_mass_ei(
    power_setting: float,
    thrust_settings: list[float],
    ei_mass_mgkg: list[float],
) -> float:
    """
    Interpolate nvPM mass emission index at an arbitrary thrust setting using
    log-log interpolation through the EEDB certification points.

    Per MEEM V1 specification, nvPM mass EI is interpolated on log-log axes
    (both x = thrust setting and y = EI are log-transformed). Extrapolation
    below the minimum or above the maximum thrust clamps to the nearest endpoint.

    :param power_setting:    Thrust setting F/F00 (0–1).
    :param thrust_settings:  List of EEDB thrust settings (F/F00), typically
                             [0.07, 0.30, 0.85, 1.00] for 4-point engines.
                             5-point engines include an additional peak point.
    :param ei_mass_mgkg:     nvPM mass EI at each EEDB point (mg/kg fuel).
    :return:                 Interpolated nvPM mass EI (mg/kg fuel). Returns 0
                             if all EEDB values are zero or negative.
    """
    ts, ei = _sort_eedb_points(thrust_settings, ei_mass_mgkg)

    # Guard: all zero / negative EEDB values — no nvPM data available
    valid = [v for v in ei if v and v > 0]
    if not valid:
        return 0.0

    # Replace non-positive values with epsilon to allow log transform
    ei_safe = [max(v, _EPSILON) for v in ei]
    ts_safe = [max(t, _EPSILON) for t in ts]

    log_ts = [math.log10(t) for t in ts_safe]
    log_ei = [math.log10(e) for e in ei_safe]

    x = max(math.log10(max(power_setting, _EPSILON)), log_ts[0])
    x = min(x, log_ts[-1])

    # Piecewise linear interpolation in log-log space
    for i in range(len(log_ts) - 1):
        if log_ts[i] <= x <= log_ts[i + 1]:
            if log_ts[i + 1] == log_ts[i]:
                y = log_ei[i]
            else:
                slope = (log_ei[i + 1] - log_ei[i]) / (log_ts[i + 1] - log_ts[i])
                y = log_ei[i] + slope * (x - log_ts[i])
            return 10.0**y

    # Should not reach here after clamping, but return endpoint as safety
    return 10.0 ** log_ei[-1]


def interpolate_nvpm_number_ei(
    power_setting: float,
    thrust_settings: list[float],
    ei_number_nkg: list[float],
) -> float:
    """
    Interpolate nvPM number emission index at an arbitrary thrust setting using
    piecewise linear interpolation in linear space.

    Per MEEM V1 specification, nvPM number EI is interpolated linearly (not
    log-log), since the number EI does not exhibit the same monotonic log-log
    behaviour as the mass EI.

    :param power_setting:   Thrust setting F/F00 (0–1).
    :param thrust_settings: List of EEDB thrust settings (F/F00).
    :param ei_number_nkg:   nvPM number EI at each EEDB point (#/kg fuel).
    :return:                Interpolated nvPM number EI (#/kg fuel).
    """
    ts, ei = _sort_eedb_points(thrust_settings, ei_number_nkg)

    if not any(v and v > 0 for v in ei):
        return 0.0

    x = max(min(power_setting, ts[-1]), ts[0])

    for i in range(len(ts) - 1):
        if ts[i] <= x <= ts[i + 1]:
            if ts[i + 1] == ts[i]:
                return ei[i]
            frac = (x - ts[i]) / (ts[i + 1] - ts[i])
            return ei[i] + frac * (ei[i + 1] - ei[i])

    return ei[-1]


# ── Altitude correction ───────────────────────────────────────────────────────


def _altitude_correction_factor(
    T3_alt: float, T3_gr: float, exponent: float = _N_MASS
) -> float:
    """
    Compute the DLR enrichment correction factor φ^n for translating the
    ground-reference nvPM EI to altitude conditions.

    φ = T3_alt / T3_GR  (combustor inlet temperature ratio)

    For LTO altitudes (<914 m) φ ≈ 1 and the correction is negligible.

    :param T3_alt:  Combustor inlet temperature at altitude (K).
    :param T3_gr:   Combustor inlet temperature at ground reference (K).
    :param exponent: DLR model exponent (1.0 for mass, 1.0 for number by default).
    :return: Correction factor φ^n (dimensionless, 1.0 for LTO).
    """
    if T3_gr <= 0:
        return 1.0
    phi = T3_alt / T3_gr
    return phi**exponent


def equivalent_gr_thrust(
    thrust_alt: float,
    P3_alt: float,
    P3_gr: float,
) -> float:
    """
    Map the thrust setting at altitude to its ground-reference equivalent using
    the combustor pressure ratio.

    From MEEM V1 section 4:
        F_GR/F00 = (F_alt/F00) × (P3_GR / P3_alt)

    For LTO phases (altitude < 914 m) this ratio ≈ 1.0.

    :param thrust_alt: Thrust setting at altitude (F/F00).
    :param P3_alt:     Combustor inlet pressure at altitude (Pa).
    :param P3_gr:      Combustor inlet pressure at ground reference (Pa).
    :return:           Equivalent GR thrust setting F_GR/F00 (clamped to [0, 1]).
    """
    if P3_alt <= 0:
        return thrust_alt
    ratio = P3_gr / P3_alt
    return max(0.0, min(1.0, thrust_alt * ratio))


# ── Main API ──────────────────────────────────────────────────────────────────


@dataclass
class MEEMResult:
    """nvPM emission indices returned by MEEM V1."""

    nvpm_mass_ei_mgkg: float  # mg/kg fuel
    nvpm_number_ei_nkg: float  # #/kg fuel
    gr_thrust: float  # ground-reference thrust setting used for interp
    T3_alt: float  # combustor inlet T at altitude (K) — NaN for LTO
    T3_gr: float  # combustor inlet T at GR (K)
    phi: float  # enrichment factor applied (1.0 for LTO)


def calculate_nvpm_ei(
    power_setting: float,
    thrust_settings: list[float],
    ei_mass_mgkg: list[float],
    ei_number_nkg: list[float],
    altitude_m: float = 0.0,
    mach: float = 0.0,
    opr: float = 30.0,
    phase: str = "CLIMB OUT",
    apply_altitude_correction: bool = False,
    T_ambient_K: Optional[float] = None,
    P_ambient_Pa: Optional[float] = None,
) -> MEEMResult:
    """
    Compute nvPM mass and number emission indices at the given segment
    conditions using the MEEM V1 method (ICAO CAEP/13-MDG).

    For LTO segments (altitude_m ≤ 914 m), the altitude correction is
    disabled regardless of the apply_altitude_correction flag — the ISA
    correction at low altitude is < 1% and contributes measurement noise.

    For non-LTO segments (altitude_m > 914 m), the full altitude correction
    chain is applied when apply_altitude_correction=True.

    :param power_setting:             Thrust setting F/F00 for this segment (0–1).
    :param thrust_settings:           EEDB thrust settings (F/F00 list, 4 or 5 pts).
    :param ei_mass_mgkg:              EEDB nvPM mass EI at each point (mg/kg).
    :param ei_number_nkg:             EEDB nvPM number EI at each point (#/kg).
    :param altitude_m:                Segment altitude above MSL (m). Used as the
                                      primary atmospheric input when T_ambient_K and
                                      P_ambient_Pa are not supplied (ISA model).
    :param mach:                      Flight Mach number (dimensionless, ≥ 0).
    :param opr:                       Engine overall pressure ratio (dimensionless).
    :param phase:                     Flight phase name (used to select ηcomp from
                                      CAEP14 Constants). One of the keys in
                                      PHASE_ETA_COMP, or a custom name (uses 0.88).
    :param apply_altitude_correction: If True, apply the P3/T3 altitude correction
                                      for non-LTO segments. Ignored for LTO.
    :param T_ambient_K:               Optional actual ambient static temperature (K).
                                      If provided together with P_ambient_Pa, overrides
                                      the ISA atmosphere and allows non-ISA corrections
                                      (e.g. from tbl_InvMeteo). If only one of the
                                      two is provided, both fall back to ISA.
    :param P_ambient_Pa:              Optional actual ambient static pressure (Pa).
                                      See T_ambient_K note above.
    :return: MEEMResult dataclass.

    Example (LTO idle — just interpolation, no altitude correction)::

        result = calculate_nvpm_ei(
            power_setting=0.07,
            thrust_settings=[0.07, 0.30, 0.85, 1.00],
            ei_mass_mgkg=[4.78, 2.83, 43.80, 66.37],
            ei_number_nkg=[241e12, 143e12, 276e12, 418e12],
        )
        # result.nvpm_mass_ei_mgkg ≈ 4.78  (at idle, no interpolation needed)
        # result.nvpm_number_ei_nkg ≈ 241e12

    Example (non-LTO CLIMB segment with altitude correction, ISA)::

        result = calculate_nvpm_ei(
            power_setting=0.85,
            thrust_settings=[0.07, 0.30, 0.85, 1.00],
            ei_mass_mgkg=[4.78, 2.83, 43.80, 66.37],
            ei_number_nkg=[241e12, 143e12, 276e12, 418e12],
            altitude_m=9144,      # 30 000 ft
            mach=0.78,
            opr=25.6,
            phase="CLIMB TO CRUISE",
            apply_altitude_correction=True,
        )

    Example (non-LTO segment with measured non-ISA ambient)::

        result = calculate_nvpm_ei(
            power_setting=0.85,
            thrust_settings=[0.07, 0.30, 0.85, 1.00],
            ei_mass_mgkg=[4.78, 2.83, 43.80, 66.37],
            ei_number_nkg=[241e12, 143e12, 276e12, 418e12],
            altitude_m=9144,
            mach=0.78,
            opr=25.6,
            phase="CLIMB TO CRUISE",
            apply_altitude_correction=True,
            T_ambient_K=220.0,    # non-ISA (warm-tropopause day)
            P_ambient_Pa=30000.0,
        )
    """
    altitude_m = max(0.0, float(altitude_m))
    mach = max(0.0, float(mach))
    opr = max(1.0, float(opr))
    ps = max(0.0, min(1.0, float(power_setting)))

    is_lto = altitude_m <= 914.4  # LTO ceiling: 3000 ft = 914.4 m

    # ── Ground reference conditions (ISA MSL) ────────────────────────────────
    T_gr, P_gr = ISA.T0, ISA.P0
    TT_gr, PT_gr = total_conditions(T_gr, P_gr, mach=0.0)  # GR is ground run: M≈0
    eta_gr = PHASE_ETA_COMP.get("CLIMB OUT", 0.88)  # GR uses climb-out ηcomp
    T3_gr, P3_gr = combustor_inlet_conditions(TT_gr, PT_gr, opr, eta_gr)

    # ── Segment conditions ───────────────────────────────────────────────────
    # If caller supplies both ambient T and P, use them directly (non-ISA);
    # otherwise fall back to ISA at altitude_m. Partial overrides are ignored
    # to avoid mixing ISA pressure with non-ISA temperature (or vice versa).
    if T_ambient_K is not None and P_ambient_Pa is not None:
        T_alt = float(T_ambient_K)
        P_alt = float(P_ambient_Pa)
    else:
        T_alt, P_alt = isa_conditions(altitude_m)
    TT_alt, PT_alt = total_conditions(T_alt, P_alt, mach)
    eta_alt = PHASE_ETA_COMP.get(phase.upper(), 0.88)
    T3_alt, P3_alt = combustor_inlet_conditions(TT_alt, PT_alt, opr, eta_alt)

    # ── Thrust setting for interpolation ────────────────────────────────────
    if is_lto or not apply_altitude_correction:
        gr_thrust = ps
        phi_mass = 1.0
        phi_number = 1.0
    else:
        gr_thrust = equivalent_gr_thrust(ps, P3_alt, P3_gr)
        phi_mass = _altitude_correction_factor(T3_alt, T3_gr, _N_MASS)
        phi_number = _altitude_correction_factor(T3_alt, T3_gr, _N_NUMBER)
        logger.debug(
            "MEEM_V1: alt=%.0f m  Mach=%.3f  ps=%.3f → F_GR=%.3f  "
            "T3_alt=%.1f K  T3_GR=%.1f K  φ=%.4f",
            altitude_m,
            mach,
            ps,
            gr_thrust,
            T3_alt,
            T3_gr,
            phi_mass,
        )

    # ── Interpolate at GR thrust ──────────────────────────────────────────
    ei_mass_gr = interpolate_nvpm_mass_ei(gr_thrust, thrust_settings, ei_mass_mgkg)
    ei_number_gr = interpolate_nvpm_number_ei(gr_thrust, thrust_settings, ei_number_nkg)

    # ── Apply altitude correction ────────────────────────────────────────
    ei_mass_alt = ei_mass_gr * phi_mass
    ei_number_alt = ei_number_gr * phi_number

    return MEEMResult(
        nvpm_mass_ei_mgkg=ei_mass_alt,
        nvpm_number_ei_nkg=ei_number_alt,
        gr_thrust=gr_thrust,
        T3_alt=T3_alt,
        T3_gr=T3_gr,
        phi=phi_mass,
    )


def build_eedb_points_from_engine_row(engine_row: dict) -> dict:
    """
    Convenience function: extract MEEM V1 EEDB point lists from an engine row
    as stored in default_aircraft_engine_ei (one row per mode).

    Expects a dict with keys matching those produced by the reshape script:
        nvpm_ei (g/kg) — non-volatile PM mass EI
        nvpm_number_ei (#/kg)
        nvpm_ei_max (optional, for 5-point engines)
        nvpm_number_ei_max (optional)
        meem_nvpm_m_i_mode ('4PT' or '5PT')
        meem_nvpm_m_i_f00_avg (5th point thrust fraction, if 5PT)

    Alternatively, pass a list of four dicts (one per mode TO/CL/AP/TX).

    :param engine_row: dict with at minimum:
        {mode: {'thrust': float, 'nvpm_ei': float, 'nvpm_number_ei': float}, ...}
        where mode ∈ {'TO', 'CL', 'AP', 'TX'}.
    :return: dict with keys 'thrust_settings', 'ei_mass_mgkg', 'ei_number_nkg'.

    Note: nvpm_ei in the database is stored in g/kg; MEEM V1 uses mg/kg.
    This function converts automatically (× 1000).
    """
    ts, mass, number = [], [], []
    for mode, thrust in MODE_THRUST.items():
        row = engine_row.get(mode)
        if row is None:
            continue
        nvpm_m = row.get("nvpm_ei")  # g/kg in ALAQS DB
        nvpm_n = row.get("nvpm_number_ei")  # #/kg
        if nvpm_m is not None:
            ts.append(thrust)
            mass.append(float(nvpm_m) * 1000.0)  # g/kg → mg/kg
            number.append(float(nvpm_n) if nvpm_n else 0.0)

    return {"thrust_settings": ts, "ei_mass_mgkg": mass, "ei_number_nkg": number}
