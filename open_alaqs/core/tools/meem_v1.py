"""
meem_v1.py: MEEM V1 nvPM emission index calculator
===================================================
Implementation of MEEM V1 (ICAO CAEP/13-MDG method), with its ISA constants
and the ISA + delta T atmosphere of the method.

Two branches, chosen by the phase of flight (from the segment_constants
table). OpenALAQS picks the section with the method's rule ("LTO" up to
3000 ft, "NON_LTO" above), applied to the
segment height above the aerodrome as in the ICAO LTO cycle
(section_of_flight takes that height); the non-LTO chain itself works at the
segment altitude above mean sea level (height plus airport elevation):

  LTO (TAKE OFF, CLIMB OUT, APPROACH, TAXI; segment at or below 3000 ft):
    The nvPM mass and number EIs are the certification values of the mode
    (EEDB nvPM at 100 %, 85 %, 30 % or 7 % thrust, by an exact lookup of the
    mode's thrust setting). No interpolation, no altitude or ambient
    correction.

  Non-LTO (CLIMB TO CRUISE, CRUISE, DESCENT TO APPROACH; above 3000 ft):
    1. ISA+dT ambient T and P at the segment altitude.
       OpenALAQS 5.4.1: calculate_nvpm_ei(..., ambient=(T, P)) replaces them
       with the local T and P of the atmosphere model (standard_lapse or
       surface_layer); dT is then not used. The method's ISA+dT is used for
       ground_held.
    2. Mach from the true airspeed and the local speed of sound, unless a
       Mach number is given.
    3. Engine inlet total conditions:
         TT = T (1 + 0.2 M^2), PT = P (1 + 0.2 M^2)^3.5
    4. Combustor inlet at the segment, with the phase's compressor
       efficiency eta and pressure coefficient Pi (segment_constants; for
       CLIMB TO CRUISE, Pi is linear in altitude between 0.85 at 3000 ft and
       1.15 at the cruise altitude):
         P3 = PT (1 + Pi (OPR - 1))
         T3 = TT (1 + ((P3 / PT)^((g-1)/g) - 1) / eta)
    5. Ground reference at ISA MSL with the same T3:
         P3GR = P0 (1 + eta (T3 / T0 - 1))^(g/(g-1))
    6. Ground-reference thrust: F = (P3GR / P0 - 1) / (OPR - 1)
    7. EIs at F: linear interpolation (FORECAST) between the two
       bracketing certification points sorted by thrust; the value at 100 %
       above 1 and the value at 7 % below 0.07.
    8. Fuel-composition factors (1 for fossil fuel).
    9. Altitude correction, phi = 1.1:
         EI_mass = EI_mass_GR (P3 / P3GR)^1.35 phi^2.5
         EI_num  = EI_mass EI_num_GR / EI_mass_GR

The method has no value for an engine without a pressure ratio;
OpenALAQS uses DEFAULT_OPR for such engines (see
Engine.getEmissionIndexByModeWithMEEM). The CLIMB TO CRUISE pressure
coefficient needs a cruise altitude; OpenALAQS has no
cruise altitude (no aircraft, engine or profile column holds one) and uses
DEFAULT_CRUISE_ALTITUDE_FT (38000 ft).

The temperature deviation delta_t ("delta T at 0 ft MSL") is
taken from the meteo of the movement's period: the ground temperature minus
the ISA temperature at the airport elevation (delta_t_from_ground), constant
aloft, so that the ISA+dT temperature at the airport elevation equals the
meteo temperature. Without meteo the ground temperature is the ISA sea-level
288.15 K (AmbientCondition default, standalone ISA meteo), so delta_t is
0.0065 K/m x the airport elevation (10.76 K at 1655 m), not 0; it is 0 only
for an airport at sea level or when no temperature is given.

References:
  ICAO CAEP/13-MDG, MEEM V1.
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ── Constants (ISA and unit conversions) ─────────────────────────────────────

FT_TO_M: float = 0.3048000097536  # ft to m
MS_TO_KT: float = 1.94384  # m/s to kt
T0_K: float = 288.15  # ISA sea-level temperature
P0_PA: float = 101_325.0  # ISA sea-level pressure
G0: float = 9.80665  # standard gravity
LAPSE_K_PER_M: float = -0.0065  # ISA lapse rate
GAMMA: float = 1.4  # ratio of specific heats
R_AIR: float = 287.05287  # specific gas constant of air
TROPOPAUSE_M: float = 11_000.0  # ISA tropopause
TROPOPAUSE_FT: float = TROPOPAUSE_M / FT_TO_M

LTO_CEILING_FT: float = 3000.0  # ICAO LTO cycle ceiling
LTO_CEILING_M: float = 914.4  # 3000 ft

PHI: float = 1.1  # enrichment factor
MASS_EXPONENT: float = 1.35  # altitude correction exponent
PHI_EXPONENT: float = 2.5  # enrichment factor exponent

DEFAULT_CRUISE_ALTITUDE_FT: float = 38_000.0
DEFAULT_OPR: float = 30.0

# segment_constants of MEEM V1:
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

# Thrust settings of the LTO phases.
LTO_PHASE_THRUST: dict[str, float] = {
    "TAXI": 0.07,
    "CLIMB OUT": 0.85,
    "LANDING": 0.3,
    "APPROACH": 0.3,
    "TAKE OFF": 1.0,
}

# Certification thrust of the four LTO modes.
MODE_THRUST: dict[str, float] = {"TO": 1.00, "CL": 0.85, "AP": 0.30, "TX": 0.07}

# Ground-reference thrust caps.
_THRUST_MAX: float = 1.0
_THRUST_MIN: float = 0.07


# ── Atmosphere (ISA + delta T) ───────────────────────────────────────────────


def delta_t_from_ground(
    t_ground_k: Optional[float], airport_elevation_m: Optional[float]
) -> float:
    """ISA temperature deviation (K) from the ground ambient temperature (K)
    at the airport: T_ground - (T0 + L h), L = -0.0065 K/m, h the airport
    elevation above MSL (m). 0 when no temperature is given (None). Without
    meteo the plugin and the standalone pass the ISA sea-level 288.15 K, which
    gives 0.0065 K/m x h (delta_t_from_ground(288.15, 1655) = 10.76 K), not 0."""
    if t_ground_k is None:
        return 0.0
    h = float(airport_elevation_m or 0.0)
    return float(t_ground_k) - (T0_K + LAPSE_K_PER_M * h)


def isa_ambient(altitude_ft: float, delta_t: float = 0.0) -> tuple[float, float]:
    """Static temperature (K) and pressure (Pa) at a segment altitude (ft),
    ISA with a temperature deviation delta_t (K)."""
    h_ft = float(altitude_ft)
    t_trop = delta_t + T0_K + LAPSE_K_PER_M * TROPOPAUSE_M
    exponent = G0 / (-LAPSE_K_PER_M * R_AIR)
    if h_ft < TROPOPAUSE_FT:
        t_amb = T0_K + delta_t + h_ft * LAPSE_K_PER_M * FT_TO_M
    else:
        t_amb = T0_K + delta_t + TROPOPAUSE_FT * LAPSE_K_PER_M * FT_TO_M
    if h_ft <= TROPOPAUSE_FT:
        p_amb = P0_PA * ((t_amb - delta_t) / T0_K) ** exponent
    else:
        p_trop = P0_PA * ((t_trop - delta_t) / T0_K) ** exponent
        h_m = h_ft * FT_TO_M
        p_amb = p_trop * math.exp(-G0 * (h_m - TROPOPAUSE_M) / (R_AIR * t_trop))
    return t_amb, p_amb


def speed_of_sound_kt(t_amb_k: float) -> float:
    """Local speed of sound in kt."""
    return math.sqrt(GAMMA * R_AIR * t_amb_k) * MS_TO_KT


def mach_from_tas(tas_kt: float, t_amb_k: float) -> float:
    """Flight Mach number from the true airspeed in kt."""
    return float(tas_kt) / speed_of_sound_kt(t_amb_k)


# ── Phase helpers ────────────────────────────────────────────────────────────


def section_of_flight(altitude_ft: float) -> str:
    """'LTO' at or below 3000 ft, else 'NON_LTO'.
    ``altitude_ft`` is the segment height above the aerodrome (ICAO LTO
    cycle), not the altitude above MSL."""
    return "NON_LTO" if float(altitude_ft) > LTO_CEILING_FT else "LTO"


def flight_section_of_phase(phase: str) -> str:
    """'LTO' or 'Non LTO' for a phase of flight."""
    try:
        return SEGMENT_CONSTANTS[phase][4]
    except KeyError:
        raise ValueError(f"Unknown MEEM V1 phase of flight: {phase!r}") from None


def pressure_coefficient(
    phase: str,
    altitude_ft: float,
    cruise_altitude_ft: float = DEFAULT_CRUISE_ALTITUDE_FT,
) -> float:
    """Pressure coefficient Pi_alt of a non-LTO phase."""
    _, pi_alt, pi_3000, pi_cruise, _ = SEGMENT_CONSTANTS[phase]
    if phase in ("DESCENT TO APPROACH", "CRUISE"):
        return pi_alt
    if phase == "CLIMB TO CRUISE":
        return pi_3000 + (float(altitude_ft) - LTO_CEILING_FT) * (
            pi_cruise - pi_3000
        ) / (float(cruise_altitude_ft) - LTO_CEILING_FT)
    raise ValueError(f"No pressure coefficient for phase {phase!r}")


# ── Interpolation ────────────────────────────────────────────────────────────


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
    """EI at a ground-reference thrust, non-LTO branch of MEEM V1:
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
        # x at the last point: a FORECAST would take a single
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

    nvpm_mass_ei_mgkg: float  # mg/kg fuel at the segment
    nvpm_number_ei_nkg: float  # #/kg fuel at the segment
    gr_thrust: float  # ground-reference thrust setting F_GR/F00
    flight_section: str  # "LTO" or "Non LTO"
    nvpm_mass_ei_gr_mgkg: float  # ground reference (fossil)
    nvpm_number_ei_gr_nkg: float  # ground reference (fossil)
    mach: Optional[float] = None
    T_amb: Optional[float] = None  # K
    P_amb: Optional[float] = None  # Pa
    T3_alt: Optional[float] = None  # K
    P3_alt: Optional[float] = None  # Pa
    P3_gr: Optional[float] = None  # Pa


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
    ambient: Optional[Tuple[float, float]] = None,
) -> MEEMResult:
    """nvPM mass and number EIs at a segment, MEEM V1 (ICAO CAEP/13-MDG method).

    :param phase: MEEM V1 phase of flight (a key of SEGMENT_CONSTANTS, or
        "LANDING").
    :param altitude_ft: segment altitude above MSL (ft).
    :param thrust_settings: thrust settings F/F00 of the mass points (4 LTO
        points, plus the 5th point when the engine has one).
    :param ei_mass_mgkg: nvPM mass EI at each point (mg/kg).
    :param ei_number_nkg: nvPM number EI at each point (#/kg).
    :param opr: engine pressure ratio (non-LTO only).
    :param mach: flight Mach number; if None, computed from tas_kt.
    :param tas_kt: true airspeed (kt), used when mach is None.
    :param delta_t: ISA temperature deviation (K) at 0 ft MSL.
    :param cruise_altitude_ft: cruise altitude (ft).
    :param k_saf_mass: fuel-composition factor for mass (1 for fossil).
    :param k_saf_number: fuel-composition factor for number (1 for fossil).
    :param number_thrust_settings: thrust settings of the number points when
        they differ from the mass points (5-point engines); default: the same.
    :param ambient: (T in K, p in Pa) at the segment from the emission
        calculation's atmosphere model (OpenALAQS 5.4.1, atmosphere_model);
        replaces the ISA + delta_t atmosphere. None: the ISA + delta_t
        atmosphere.
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
    eta = SEGMENT_CONSTANTS[phase][0]
    pi_alt = pressure_coefficient(phase, altitude_ft, cruise_altitude_ft)

    if ambient is not None:
        t_amb, p_amb = float(ambient[0]), float(ambient[1])
    else:
        t_amb, p_amb = isa_ambient(altitude_ft, delta_t)
    if mach is None:
        if tas_kt is None:
            raise ValueError("MEEM V1 non-LTO branch needs a Mach number or a TAS")
        mach = mach_from_tas(tas_kt, t_amb)
    mach = float(mach)

    ram = 1.0 + ((GAMMA - 1.0) / 2.0) * mach**2
    tt_alt = t_amb * ram
    pt_alt = p_amb * ram ** (GAMMA / (GAMMA - 1.0))
    p3_alt = pt_alt * (1.0 + pi_alt * (opr - 1.0))
    t3_alt = tt_alt * (
        1.0 + (1.0 / eta) * ((p3_alt / pt_alt) ** ((GAMMA - 1.0) / GAMMA) - 1.0)
    )
    t3_gr = t3_alt
    p3_gr = P0_PA * (1.0 + eta * ((t3_gr / T0_K) - 1.0)) ** (GAMMA / (GAMMA - 1.0))
    thrust = ((p3_gr / P0_PA) - 1.0) / (opr - 1.0)

    mass_gr = interpolate_ei(thrust, thrust_settings, ei_mass_mgkg)
    num_gr = interpolate_ei(thrust, ts_num, ei_number_nkg)
    mass_saf = mass_gr * k_saf_mass
    num_saf = num_gr * k_saf_number

    factor = (p3_alt / p3_gr) ** MASS_EXPONENT * PHI**PHI_EXPONENT
    mass_alt = mass_saf * factor
    if mass_saf != 0.0:
        num_alt = mass_alt * num_saf / mass_saf
    else:
        # The mass ratio divides by zero here; the same correction factor is used.
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
