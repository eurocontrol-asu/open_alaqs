"""
meem_v1.py: MEEM V1 nvPM emission index calculator
===================================================
Port of the "MEEM_V1" tab of the ICAO CAEP14 FBE Engines Emissions
Calculation Sheet v14 (MEEM V1, ICAO CAEP/13-MDG), with the constants of its
"Constants" tab and the atmosphere of its "USER INPUTS" tab. Cell references
in the comments below point to that workbook.

Two branches, chosen by the phase of flight (MEEM_V1!B16, from the
segment_constants table). OpenALAQS picks the phase from the segment altitude
above mean sea level, as the sheet's USER INPUTS!B36 does ("LTO" up to
3000 ft, "NON_LTO" above):

  LTO (TAKE OFF, CLIMB OUT, APPROACH, TAXI; segment at or below 3000 ft):
    The nvPM mass and number EIs are the certification values of the mode
    (EEDB nvPM at 100 %, 85 %, 30 % or 7 % thrust, MEEM_V1!B83 and an exact
    VLOOKUP in B101/B102). No interpolation, no altitude or ambient
    correction.

  Non-LTO (CLIMB TO CRUISE, CRUISE, DESCENT TO APPROACH; above 3000 ft):
    1. ISA+dT ambient T and P at the segment altitude (USER INPUTS!B44/B45).
    2. Mach from the true airspeed and the local speed of sound
       (USER INPUTS!B39), unless a Mach number is given.
    3. Engine inlet total conditions (B50/B51):
         TT = T (1 + 0.2 M^2), PT = P (1 + 0.2 M^2)^3.5
    4. Combustor inlet at the segment (B65/B66), with the phase's compressor
       efficiency eta and pressure coefficient Pi (Constants!A4:F10; for
       CLIMB TO CRUISE, Pi is linear in altitude between 0.85 at 3000 ft and
       1.15 at the cruise altitude):
         P3 = PT (1 + Pi (OPR - 1))
         T3 = TT (1 + ((P3 / PT)^((g-1)/g) - 1) / eta)
    5. Ground reference at ISA MSL with the same T3 (B76/B77):
         P3GR = P0 (1 + eta (T3 / T0 - 1))^(g/(g-1))
    6. Ground-reference thrust (B83): F = (P3GR / P0 - 1) / (OPR - 1)
    7. EIs at F (B101/B102): linear interpolation (FORECAST) between the two
       bracketing certification points sorted by thrust; the value at 100 %
       above 1 and the value at 7 % below 0.07.
    8. Fuel-composition factors (B107/B108, 1 for fossil fuel).
    9. Altitude correction (B119/B120), phi = 1.1:
         EI_mass = EI_mass_GR (P3 / P3GR)^1.35 phi^2.5
         EI_num  = EI_mass EI_num_GR / EI_mass_GR

The sheet has no value for an engine without a pressure ratio (its formulas
then return an error); OpenALAQS uses DEFAULT_OPR for such engines (see
Engine.getEmissionIndexByModeWithMEEM). The sheet's CLIMB TO CRUISE pressure
coefficient needs a cruise altitude (USER INPUTS!B20); OpenALAQS has none and
uses DEFAULT_CRUISE_ALTITUDE_FT, the sheet's stored value.

References:
  ICAO CAEP/13-MDG, MEEM V1.
  CAEP14 FBE Engines Emissions Calculation Sheet v14, tabs MEEM_V1,
  USER INPUTS and Constants.
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


# ── Constants (CAEP14 v14, "Constants" tab) ──────────────────────────────────

FT_TO_M: float = 0.3048000097536  # Constants!B17
MS_TO_KT: float = 1.94384  # Constants!B19
T0_K: float = 288.15  # Constants!B24 (MEEM_V1!B30)
P0_PA: float = 101_325.0  # Constants!B25 (MEEM_V1!B31)
G0: float = 9.80665  # Constants!B28
LAPSE_K_PER_M: float = -0.0065  # Constants!B29
GAMMA: float = 1.4  # Constants!B30 (MEEM_V1!B49)
R_AIR: float = 287.05287  # Constants!B31
TROPOPAUSE_M: float = 11_000.0  # Constants!D32
TROPOPAUSE_FT: float = TROPOPAUSE_M / FT_TO_M  # Constants!B32

LTO_CEILING_FT: float = 3000.0  # USER INPUTS!B36
LTO_CEILING_M: float = 914.4  # 3000 ft

PHI: float = 1.1  # enrichment factor, MEEM_V1!B118
MASS_EXPONENT: float = 1.35  # MEEM_V1!B119
PHI_EXPONENT: float = 2.5  # MEEM_V1!B119

DEFAULT_CRUISE_ALTITUDE_FT: float = 38_000.0  # USER INPUTS!B20 (stored value)
DEFAULT_OPR: float = 30.0

# Constants!A4:F10 "segment_constants":
#   phase: (eta_comp, Pi_alt, Pi_alt at 3000 ft, Pi_alt at cruise, section)
SEGMENT_CONSTANTS: dict[str, tuple] = {
    "TAKE OFF": (None, None, None, None, "LTO"),
    "CLIMB OUT": (None, None, None, None, "LTO"),
    "CLIMB TO CRUISE": (0.88, None, 0.85, 1.15, "Non LTO"),
    "CRUISE": (0.88, 0.95, None, None, "Non LTO"),
    "DESCENT TO APPROACH": (0.7, 0.12, None, None, "Non LTO"),
    "APPROACH": (None, None, None, None, "LTO"),
    "TAXI": (None, None, None, None, "LTO"),
}

# MEEM_V1!B83 thrust settings of the LTO phases.
LTO_PHASE_THRUST: dict[str, float] = {
    "TAXI": 0.07,
    "CLIMB OUT": 0.85,
    "LANDING": 0.3,
    "APPROACH": 0.3,
    "TAKE OFF": 1.0,
}

# Certification thrust of the four LTO modes (MEEM_V1!J5:J8).
MODE_THRUST: dict[str, float] = {"TO": 1.00, "CL": 0.85, "AP": 0.30, "TX": 0.07}

# Ground-reference thrust caps (MEEM_V1!B101).
_THRUST_MAX: float = 1.0
_THRUST_MIN: float = 0.07


# ── Atmosphere (USER INPUTS!B41:B46) ─────────────────────────────────────────


def isa_ambient(altitude_ft: float, delta_t: float = 0.0) -> tuple[float, float]:
    """Static temperature (K) and pressure (Pa) at a segment altitude (ft),
    ISA with a temperature deviation delta_t (K), as USER INPUTS!B44/B45."""
    h_ft = float(altitude_ft)
    t_trop = delta_t + T0_K + LAPSE_K_PER_M * TROPOPAUSE_M  # B41
    exponent = G0 / (-LAPSE_K_PER_M * R_AIR)
    if h_ft < TROPOPAUSE_FT:
        t_amb = T0_K + delta_t + h_ft * LAPSE_K_PER_M * FT_TO_M
    else:
        t_amb = T0_K + delta_t + TROPOPAUSE_FT * LAPSE_K_PER_M * FT_TO_M
    if h_ft <= TROPOPAUSE_FT:
        p_amb = P0_PA * ((t_amb - delta_t) / T0_K) ** exponent
    else:
        p_trop = P0_PA * ((t_trop - delta_t) / T0_K) ** exponent  # B43
        h_m = h_ft * FT_TO_M  # B40/D40
        p_amb = p_trop * math.exp(-G0 * (h_m - TROPOPAUSE_M) / (R_AIR * t_trop))
    return t_amb, p_amb


def speed_of_sound_kt(t_amb_k: float) -> float:
    """Local speed of sound in kt (USER INPUTS!D46)."""
    return math.sqrt(GAMMA * R_AIR * t_amb_k) * MS_TO_KT


def mach_from_tas(tas_kt: float, t_amb_k: float) -> float:
    """Flight Mach number from the true airspeed in kt (USER INPUTS!B39)."""
    return float(tas_kt) / speed_of_sound_kt(t_amb_k)


# ── Phase helpers ────────────────────────────────────────────────────────────


def section_of_flight(altitude_ft: float) -> str:
    """'LTO' at or below 3000 ft, else 'NON_LTO' (USER INPUTS!B36)."""
    return "NON_LTO" if float(altitude_ft) > LTO_CEILING_FT else "LTO"


def flight_section_of_phase(phase: str) -> str:
    """'LTO' or 'Non LTO' for a phase of flight (MEEM_V1!B16)."""
    try:
        return SEGMENT_CONSTANTS[phase][4]
    except KeyError:
        raise ValueError(f"Unknown MEEM V1 phase of flight: {phase!r}") from None


def pressure_coefficient(
    phase: str,
    altitude_ft: float,
    cruise_altitude_ft: float = DEFAULT_CRUISE_ALTITUDE_FT,
) -> float:
    """Pressure coefficient Pi_alt of a non-LTO phase (MEEM_V1!B26)."""
    _, pi_alt, pi_3000, pi_cruise, _ = SEGMENT_CONSTANTS[phase]
    if phase in ("DESCENT TO APPROACH", "CRUISE"):
        return pi_alt
    if phase == "CLIMB TO CRUISE":
        return pi_3000 + (float(altitude_ft) - LTO_CEILING_FT) * (
            pi_cruise - pi_3000
        ) / (float(cruise_altitude_ft) - LTO_CEILING_FT)
    raise ValueError(f"No pressure coefficient for phase {phase!r}")


# ── Interpolation (MEEM_V1!C88:D100, B101/B102) ──────────────────────────────


def _sorted_points(
    thrust_settings: Sequence[float], values: Sequence[float]
) -> tuple[list[float], list[float]]:
    """SORT(FILTER(points, thrust > 0)) by thrust, stable."""
    pairs = [
        (float(t), float(v))
        for t, v in zip(thrust_settings, values)
        if t is not None and float(t) > 0
    ]
    pairs.sort(key=lambda p: p[0])
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _lookup_exact(ts: list[float], ys: list[float], x: float) -> float:
    """VLOOKUP(x, points, 2, FALSE): first point with thrust == x."""
    for t, y in zip(ts, ys):
        if t == x:
            return y
    raise ValueError(f"No certification point at thrust {x}")


def interpolate_ei(
    thrust: float,
    thrust_settings: Sequence[float],
    values: Sequence[float],
) -> float:
    """EI at a ground-reference thrust, non-LTO branch of MEEM_V1!B101/B102:
    the value at 100 % above 1, the value at 7 % below 0.07, otherwise the
    straight line (FORECAST) through the last point at or below the thrust
    (MATCH type 1) and the next one."""
    ts, ys = _sorted_points(thrust_settings, values)
    x = float(thrust)
    if x > _THRUST_MAX:
        return _lookup_exact(ts, ys, 1.0)
    if x < _THRUST_MIN:
        return _lookup_exact(ts, ys, 0.07)
    idx = max(i for i, t in enumerate(ts) if t <= x)
    if idx + 1 >= len(ts):
        # x at the last point: the sheet's FORECAST would take a single
        # point here; the point's own value is the limit of the line.
        return ys[idx]
    x0, x1, y0, y1 = ts[idx], ts[idx + 1], ys[idx], ys[idx + 1]
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


# ── Main API ─────────────────────────────────────────────────────────────────


@dataclass
class MEEMResult:
    """nvPM emission indices and intermediate values of MEEM V1."""

    nvpm_mass_ei_mgkg: float  # mg/kg fuel at the segment (B119)
    nvpm_number_ei_nkg: float  # #/kg fuel at the segment (B120)
    gr_thrust: float  # ground-reference thrust setting F_GR/F00 (B83)
    flight_section: str  # "LTO" or "Non LTO" (B16)
    nvpm_mass_ei_gr_mgkg: float  # B101 (fossil)
    nvpm_number_ei_gr_nkg: float  # B102 (fossil)
    mach: Optional[float] = None  # B17
    T_amb: Optional[float] = None  # B47 (K)
    P_amb: Optional[float] = None  # B48 (Pa)
    T3_alt: Optional[float] = None  # B65 (K)
    P3_alt: Optional[float] = None  # B66 (Pa)
    P3_gr: Optional[float] = None  # B77 (Pa)


def calculate_nvpm_ei(
    phase: str,
    altitude_ft: float,
    thrust_settings: Sequence[float],
    ei_mass_mgkg: Sequence[float],
    ei_number_nkg: Sequence[float],
    opr: Optional[float] = None,
    mach: Optional[float] = None,
    tas_kt: Optional[float] = None,
    delta_t: float = 0.0,
    cruise_altitude_ft: float = DEFAULT_CRUISE_ALTITUDE_FT,
    k_saf_mass: float = 1.0,
    k_saf_number: float = 1.0,
    number_thrust_settings: Optional[Sequence[float]] = None,
) -> MEEMResult:
    """nvPM mass and number EIs at a segment, MEEM V1 as the CAEP14 v14 sheet.

    :param phase: sheet phase of flight (a key of SEGMENT_CONSTANTS, or
        "LANDING").
    :param altitude_ft: segment altitude above MSL (ft).
    :param thrust_settings: thrust settings F/F00 of the mass points (4 LTO
        points, plus the 5th point when the engine has one).
    :param ei_mass_mgkg: nvPM mass EI at each point (mg/kg).
    :param ei_number_nkg: nvPM number EI at each point (#/kg).
    :param opr: engine pressure ratio (non-LTO only).
    :param mach: flight Mach number; if None, computed from tas_kt.
    :param tas_kt: true airspeed (kt), used when mach is None.
    :param delta_t: ISA temperature deviation (K), USER INPUTS!B5.
    :param cruise_altitude_ft: cruise altitude (ft), USER INPUTS!B20.
    :param k_saf_mass: fuel-composition factor for mass (1 for fossil).
    :param k_saf_number: fuel-composition factor for number (1 for fossil).
    :param number_thrust_settings: thrust settings of the number points when
        they differ from the mass points (5-point engines); default: the same.
    """
    ts_num = (
        thrust_settings if number_thrust_settings is None else number_thrust_settings
    )
    phase = str(phase).upper()
    section = "LTO" if phase == "LANDING" else flight_section_of_phase(phase)

    if section == "LTO":
        thrust = LTO_PHASE_THRUST[phase]
        ts_m, ys_m = _sorted_points(thrust_settings, ei_mass_mgkg)
        ts_n, ys_n = _sorted_points(ts_num, ei_number_nkg)
        mass_gr = _lookup_exact(ts_m, ys_m, thrust)
        num_gr = _lookup_exact(ts_n, ys_n, thrust)
        return MEEMResult(
            nvpm_mass_ei_mgkg=mass_gr * k_saf_mass,
            nvpm_number_ei_nkg=num_gr * k_saf_number,
            gr_thrust=thrust,
            flight_section=section,
            nvpm_mass_ei_gr_mgkg=mass_gr,
            nvpm_number_ei_gr_nkg=num_gr,
        )

    if opr is None:
        raise ValueError("MEEM V1 non-LTO branch needs the engine pressure ratio")
    opr = float(opr)
    eta = SEGMENT_CONSTANTS[phase][0]  # B25
    pi_alt = pressure_coefficient(phase, altitude_ft, cruise_altitude_ft)  # B26

    t_amb, p_amb = isa_ambient(altitude_ft, delta_t)  # B47, B48
    if mach is None:
        if tas_kt is None:
            raise ValueError("MEEM V1 non-LTO branch needs a Mach number or a TAS")
        mach = mach_from_tas(tas_kt, t_amb)
    mach = float(mach)

    ram = 1.0 + ((GAMMA - 1.0) / 2.0) * mach**2
    tt_alt = t_amb * ram  # B50
    pt_alt = p_amb * ram ** (GAMMA / (GAMMA - 1.0))  # B51
    p3_alt = pt_alt * (1.0 + pi_alt * (opr - 1.0))  # B66
    t3_alt = tt_alt * (
        1.0 + (1.0 / eta) * ((p3_alt / pt_alt) ** ((GAMMA - 1.0) / GAMMA) - 1.0)
    )  # B65
    t3_gr = t3_alt  # B76
    p3_gr = P0_PA * (1.0 + eta * ((t3_gr / T0_K) - 1.0)) ** (
        GAMMA / (GAMMA - 1.0)
    )  # B77
    thrust = ((p3_gr / P0_PA) - 1.0) / (opr - 1.0)  # B83

    mass_gr = interpolate_ei(thrust, thrust_settings, ei_mass_mgkg)  # B101
    num_gr = interpolate_ei(thrust, ts_num, ei_number_nkg)  # B102
    mass_saf = mass_gr * k_saf_mass  # B109
    num_saf = num_gr * k_saf_number  # B110

    factor = (p3_alt / p3_gr) ** MASS_EXPONENT * PHI**PHI_EXPONENT
    mass_alt = mass_saf * factor  # B119
    if mass_saf != 0.0:
        num_alt = mass_alt * num_saf / mass_saf  # B120
    else:
        # B120 divides by zero here; the same correction factor is used.
        num_alt = num_saf * factor

    logger.debug(
        "MEEM V1 %s: alt=%.0f ft M=%.3f P3=%.0f Pa P3GR=%.0f Pa F_GR=%.4f "
        "EI_mass=%.4g mg/kg",
        phase,
        float(altitude_ft),
        mach,
        p3_alt,
        p3_gr,
        thrust,
        mass_alt,
    )
    return MEEMResult(
        nvpm_mass_ei_mgkg=mass_alt,
        nvpm_number_ei_nkg=num_alt,
        gr_thrust=thrust,
        flight_section=section,
        nvpm_mass_ei_gr_mgkg=mass_gr,
        nvpm_number_ei_gr_nkg=num_gr,
        mach=mach,
        T_amb=t_amb,
        P_amb=p_amb,
        T3_alt=t3_alt,
        P3_alt=p3_alt,
        P3_gr=p3_gr,
    )
