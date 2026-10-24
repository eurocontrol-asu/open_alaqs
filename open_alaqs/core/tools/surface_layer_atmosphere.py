"""Ambient conditions at the height of a flight segment, from the hourly surface meteorology.

The emission calculation needs temperature, pressure and humidity where the engine is. The
study meteorology (`tbl_InvMeteo`) holds one row per hour at the airport: temperature, sea-level
pressure (QNH), relative humidity, wind speed, Obukhov length and mixing height. This module
carries that row up to a segment's height.

Three atmosphere models (method config key ``atmosphere_model``):

``standard_lapse`` (default)
    The station pressure at the airport (from QNH and the airport elevation, with the ISA
    relation that defines QNH) and the 2 m temperature, carried up with the ISA lapse rate
    (6.5 K/km) and the hydrostatic law; the humidity ratio of the ground air is kept.
    Against the De Bilt radiosondes of 2025 (450 soundings, driven by the hourly METAR rows
    of a nearby airport), within
    the emission ceiling: T(z) - T(surface) bias / RMS -1.3 / 2.9 K at 100 m, +0.3 / 1.4 K at
    300 m, +2.0 / 3.1 K at 900 m; the fuel-flow factor delta sqrt(theta) within 0.3 to 0.7 %
    RMS (the ground row held: 1.2 to 12.9 %). See documents/ATMOSPHERE_ALOFT.md.

``surface_layer``
    The boundary-layer temperature profile of AUSTAL 3.3 (function ``BlmTemp`` of ``TalBlm.c``;
    the AUSTAL manual does not give the formula), driven by the same hourly wind speed, Obukhov
    length and mixing height as the AUSTAL dispersion:

    * temperature: the 2 m temperature ta plus the Monin-Obukhov stability term
      ``(T* / kappa) (Theta(z, L) - Theta(2 m, L))``, ``T* = ta / (kappa g) u*^2 / L``, plus
      -9.766557 K/km (-g / cp) up to 200 m and -8.5 K/km above, up to the hour's mixing height;
      above it the temperature continues from its value there at -8.5 K/km;
    * friction velocity u*: AUSTAL's first estimate (``u2lInitialize``): the wind speed at the
      anemometer height divided by the simple Prandtl profile per unit u* (``StdUuPrandtl``),
      from z0, d0 and L. AUSTAL refines u* iteratively only when the first layer of its two-layer
      wind model lies below the anemometer (``u2lH1 < ha``); that refinement is not reproduced;
    * pressure: the station pressure at the airport, from QNH and the airport elevation with the
      ISA relation that defines QNH, integrated hydrostatically with the temperature profile;
    * humidity: the humidity ratio of the ground air is kept (water vapour is conserved); the
      relative humidity passed on is the one that gives that humidity ratio at the local T and p
      with the BFFM2 saturation formula (it can exceed 1 aloft; BFFM2 does not cap it).

    Three departures from AUSTAL's ``BlmTemp``, which AUSTAL evaluates only for plume rise and
    with a fixed ambient temperature (10 degC and 70 % at 2 m, manual section 3.4; changeable
    once per run with the NOSTANDARD option Ta=): T* uses the hour's ta instead of AUSTAL's fixed
    283.15 K; AUSTAL's limits of -30 and +40 degC on the profile are not applied (with hourly
    temperatures they would clip real values); and the stability term stops at the mixing height
    (``BlmTemp`` does not use the mixing height and extends it to any height). In stable hours
    that height is at most AUSTAL's own stable mixing height (``getHm``: 0.3 u*/f sqrt(f L/u*),
    800 m at most, f = 1.1e-4 1/s, AUSTAL's default), so a row whose MixingHeight is the ICAO
    3,000 ft value still gets a stable layer of realistic depth. Below 2 m the
    temperature is ta (AUSTAL measures from d0 with a floor of 6 z0, so the profile steps at
    2 m and returns to ta at d0 + 2 m; the step is a few tenths of a kelvin at most, 0.30 K
    with 3 m/s and L = 10 m; it does not reach flight segments, which are at 0 m on the
    ground roll and well above 3 m in the air).

    OpenALAQS bounds the surface heat flux implied by the row's wind and L (600 W/m2
    unstable, 100 W/m2 stable; ``bounded_stability``): above the bound, L is replaced by
    the one that gives the bounded flux, with a warning. A profile temperature outside
    180 to 340 K raises ValueError. ``blm_temperature(..., austal_exact=True)`` is the unmodified port, kept for the
    comparison with AUSTAL's code.

    Against the same soundings this profile is too cold: bias / RMS -1.5 / 2.8 K at 100 m,
    -1.2 / 1.7 K at 300 m, -2.7 / 3.5 K at 900 m within the emission ceiling; it is not more
    accurate than ``standard_lapse`` and depends on the stability inputs, so it is an option.

``ground_held``
    The hourly row as it is, at every height (the OpenALAQS 5.4.0 ambient conditions): the
    temperature, the sea-level pressure used as the ambient pressure, and the relative
    humidity. The 5.4.1 fuel-flow scaling still applies; no option restores 5.4.0 results.

Limitations of all aloft models: the humidity ratio is kept, so the relative humidity passed
to BFFM2 exceeds 1 in a layer that would be saturated (BFFM2 recovers the humidity ratio
exactly; no cap at saturation), and the lapse rate stays dry (or ISA) inside such a layer.
``surface_layer`` continues at -8.5 K/km above the mixing height to any height; emissions stop
at the mixing height unless the vertical limit is raised above it.

OpenALAQS counts emissions up to the hour's MixingHeight (the emission ceiling). Heights are above the airport (m); negative heights are taken as 0.
"""

from __future__ import annotations

import logging
import math
from array import array
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_SURFACE_LAYER = "surface_layer"
MODEL_STANDARD_LAPSE = "standard_lapse"
MODEL_GROUND_HELD = "ground_held"
ATMOSPHERE_MODELS = (MODEL_SURFACE_LAYER, MODEL_STANDARD_LAPSE, MODEL_GROUND_HELD)
DEFAULT_ATMOSPHERE_MODEL = MODEL_STANDARD_LAPSE

# Site parameters of the AUSTAL run (austal.txt z0, d0, ha), shared by the plugin's AUSTAL
# output module, the standalone pipeline, austal_prep and the surface_layer atmosphere:
# z0 = 0.1 m, the TA Luft (2021, Anhang 2) roughness length of airports (CORINE class 124);
# d0 = 6 z0 and ha = 10 m + d0, AUSTAL's own defaults, derived from z0 whenever they are left
# empty. ``site_parameters`` is the single source of truth; every other place calls it.
DEFAULT_ROUGHNESS_LENGTH_M = 0.1
DISPLACEMENT_HEIGHT_FACTOR = 6.0  # d0 = 6 z0
ANEMOMETER_HEIGHT_ABOVE_D0_M = 10.0  # ha = 10 m + d0

# AUSTAL 3.3 constants (TalBlm.h, TalBlm.c)
BLM_VKK = 0.40  # von Karman constant
BLM_GRAV = 9.8066  # m/s2
BLM_TZERO = 273.15
BLM_DRYAD = -0.009766557  # K/m, -g/cp
BLM_TMIN = -30.0  # degC, lower limit of AUSTAL's profile (austal_exact only)
BLM_TMAX = 40.0  # degC, upper limit of AUSTAL's profile (austal_exact only)
BLM_HT = 2.0  # m, height of the temperature measurement
BLM_HT2 = 200.0  # m, height above which BLM_GRAD2 applies
BLM_GRAD2 = -0.0085  # K/m
BLM_FCOR = 1.1e-4  # 1/s, AUSTAL's default Coriolis parameter (no latitude given)
BLM_FCORMIN = 6.1618e-5  # 1/s
BLM_DEFHM = 800.0  # m, AUSTAL's neutral mixing height (BLMDEFHM, at BLM_FCOR)
BLM_HMMIN = 20.0  # m
NEUTRAL_OBUKHOV_LENGTH_M = (
    99999.0  # AUSTAL / OpenALAQS value for neutral, also used when L is 0 or missing
)

# Bound on the surface sensible heat flux implied by an hourly row (OpenALAQS, not AUSTAL).
# The row's wind speed and Obukhov length fix u* and T* = ta u*^2 / (kappa g L), hence the
# heat flux H = -rho cp u* T*. A meteo file can hold combinations that no real surface layer
# has (15 m/s with L = -50 m implies about 9 kW/m2), and the stability term then gives
# temperatures tens of kelvin away from the ground value. When |H| exceeds the bound, L is
# replaced by the Obukhov length that gives the bounded flux with the row's wind (u* follows),
# and a warning is logged once per row. The bounds are engineering limits chosen for OpenALAQS
# (daytime sensible heat flux over land rarely exceeds a few hundred W/m2; nocturnal fluxes are
# mostly a few tens of W/m2), not values from AUSTAL or VDI 3783.
HEAT_FLUX_MAX_UNSTABLE_W_M2 = 600.0
HEAT_FLUX_MAX_STABLE_W_M2 = 100.0
CP_AIR = 1005.0  # J/(kg K)
# Plausibility range of a profile temperature (K); outside it local_state raises ValueError.
T_VALID_MIN_K = 180.0
T_VALID_MAX_K = 340.0

# Hydrostatics and ISA
G0 = 9.80665
R_AIR = 287.053
ISA_T0 = 288.15
ISA_LAPSE = 0.0065
ISA_EXP = G0 / (R_AIR * ISA_LAPSE)  # 5.25588

# Profile grid (m above the airport): integration step and top. Above the top the temperature
# continues at BLM_GRAD2 (surface_layer) or the ISA lapse rate (standard_lapse).
_GRID_STEP_M = 5.0
_GRID_TOP_M = 3000.0


def normalise_model(model) -> str:
    """The atmosphere model name; None or empty gives the default. Unknown names raise ValueError."""
    if model is None or str(model).strip() == "":
        return DEFAULT_ATMOSPHERE_MODEL
    m = str(model).strip().lower()
    if m not in ATMOSPHERE_MODELS:
        raise ValueError(
            f"Unknown atmosphere_model '{model}'; expected one of {', '.join(ATMOSPHERE_MODELS)}"
        )
    return m


def _is_empty(value) -> bool:
    """True for a site parameter that was left empty: None, "" (whitespace counts) or the
    text NULL / None of a configuration file. A NaN is not empty: it is invalid and raises.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == "" or value.strip().upper() in ("NULL", "NONE")
    return False


def site_parameters(z0=None, d0=None, ha=None):
    """(z0, d0, ha) in m: the given values, with the defaults for those left empty (None, "",
    NULL): z0 = DEFAULT_ROUGHNESS_LENGTH_M (0.1 m, TA Luft airports), d0 = 6 z0 and ha = 10 m
    + d0, so that site_parameters() is (0.1, 0.6, 10.6) and site_parameters(0.25) is
    (0.25, 1.5, 11.5). A derived value is rounded to 10 decimals so that 6 * 0.1 is 0.6.

    Raises ValueError unless z0 > 0, d0 >= 0 and ha > d0 (the anemometer above the
    displacement height), all finite.
    """
    z0 = DEFAULT_ROUGHNESS_LENGTH_M if _is_empty(z0) else float(z0)
    d0 = round(DISPLACEMENT_HEIGHT_FACTOR * z0, 10) if _is_empty(d0) else float(d0)
    ha = round(ANEMOMETER_HEIGHT_ABOVE_D0_M + d0, 10) if _is_empty(ha) else float(ha)
    if (
        not all(math.isfinite(v) for v in (z0, d0, ha))
        or z0 <= 0.0
        or d0 < 0.0
        or ha <= d0
    ):
        raise ValueError(
            "Atmosphere site parameters need z0 > 0, d0 >= 0 and ha > d0 "
            f"(got z0={z0}, d0={d0}, ha={ha} m)"
        )
    return z0, d0, ha


def site_parameters_from_settings(z0=None, d0=None, ha=None):
    """``site_parameters`` for settings that cannot be empty, such as the plugin's spin boxes
    (AUSTAL output module: Roughness Length, Displacement Height, Anemometer Height) and
    a configuration file read into numbers: a value of 0 means "derive" (z0 0 gives the
    default roughness length, d0 0 gives 6 z0, ha 0 gives 10 m + d0). A displacement height
    of exactly 0 m therefore cannot be set through these settings; AUSTAL's floor on the
    profile height is 6 z0 in any case.
    """

    def _or_none(value):
        if _is_empty(value):
            return None
        try:
            return None if float(value) == 0.0 else value
        except (TypeError, ValueError):
            return value

    return site_parameters(_or_none(z0), _or_none(d0), _or_none(ha))


def station_pressure_from_qnh(qnh_pa: float, elevation_m: float) -> float:
    """Pressure at the airport elevation from QNH, with the ISA relation that defines QNH."""
    return (
        float(qnh_pa)
        * (1.0 - ISA_LAPSE * float(elevation_m or 0.0) / ISA_T0) ** ISA_EXP
    )


def _obukhov(lm) -> float:
    try:
        lm = float(lm)
    except (TypeError, ValueError):
        return NEUTRAL_OBUKHOV_LENGTH_M
    if lm == 0.0 or math.isnan(lm):
        return NEUTRAL_OBUKHOV_LENGTH_M
    return lm


def _prandtl_u_per_ustar(h: float, z0: float, d0: float, lmo: float) -> float:
    """AUSTAL StdUuPrandtl(h, z0, d0, ust=1, lmo, simple=1): wind speed per unit u*."""
    hh = d0 + 6.0 * z0
    z = hh - d0 if h < hh else h - d0
    if lmo >= 0.0:
        zm = z / lmo
        zm0 = z0 / lmo
        psi = math.log(zm / zm0) + 5.0 * (zm - zm0) if zm > zm0 else 0.0
        u = psi / BLM_VKK
    else:
        zm = z / lmo
        zm0 = z0 / lmo
        psi = (1.0 - 15.0 * zm) ** 0.25
        psi0 = (1.0 - 15.0 * zm0) ** 0.25
        u1 = (psi0 + 1) * (psi0 + 1) * (psi0 * psi0 + 1) * zm / zm0
        u1 = math.log(u1 / ((psi + 1) * (psi + 1) * (psi * psi + 1)))
        u = (2.0 * (math.atan(psi) - math.atan(psi0)) + u1) / BLM_VKK
    if h < hh:
        u *= h / hh
    return u


def friction_velocity(ua: float, ha: float, z0: float, d0: float, lm) -> float:
    """u* (m/s) from the wind speed ua at the anemometer height ha, as AUSTAL's first estimate."""
    ua = float(ua or 0.0)
    if ua <= 0.0:
        return 0.0
    u = _prandtl_u_per_ustar(ha, z0, d0, _obukhov(lm))
    return ua / u if u > 0.0 else 0.0


def implied_heat_flux(ust: float, lm, ta_k: float, p_pa: float) -> float:
    """Surface sensible heat flux (W/m2, positive upwards) implied by u* and L:
    H = -rho cp ta u*^3 / (kappa g L)."""
    lm = _obukhov(lm)
    rho = p_pa / (R_AIR * ta_k)
    return -rho * CP_AIR * ta_k * ust**3 / (BLM_VKK * BLM_GRAV * lm)


def bounded_stability(ua, ha, z0, d0, lm, ta_k, p_pa):
    """(u*, L, H, bounded) for the hour: L and u* as given by the row, or, when the implied
    heat flux exceeds HEAT_FLUX_MAX_UNSTABLE_W_M2 (L < 0) or HEAT_FLUX_MAX_STABLE_W_M2 (L > 0),
    the Obukhov length that gives the bounded flux with the row's wind, and its u*."""
    lm = _obukhov(lm)
    ust = friction_velocity(ua, ha, z0, d0, lm)
    if ust <= 0.0 or lm == NEUTRAL_OBUKHOV_LENGTH_M:
        return ust, lm, 0.0, False
    h_flux = implied_heat_flux(ust, lm, ta_k, p_pa)
    cap = HEAT_FLUX_MAX_UNSTABLE_W_M2 if lm < 0.0 else HEAT_FLUX_MAX_STABLE_W_M2
    if abs(h_flux) <= cap:
        return ust, lm, h_flux, False
    rho = p_pa / (R_AIR * ta_k)
    h_target = math.copysign(cap, h_flux)
    for _ in range(200):
        lm_new = -rho * CP_AIR * ta_k * ust**3 / (BLM_VKK * BLM_GRAV * h_target)
        ust_new = friction_velocity(ua, ha, z0, d0, lm_new)
        done = abs(lm_new - lm) <= 1e-9 * abs(lm_new) and abs(ust_new - ust) <= 1e-12
        lm, ust = lm_new, ust_new
        if done:
            break
    return ust, lm, implied_heat_flux(ust, lm, ta_k, p_pa), True


def _theta(z: float, lm: float) -> float:
    """AUSTAL getTheta (TalBlm.c)."""
    zeta = z / lm
    if lm > 0.0:
        if zeta < 0.5:
            return math.log(zeta) + 5.0 * zeta - 7.0 * math.log(2.0) + 4.0
        if zeta < 10.0:
            return 8.0 * math.log(zeta) + 4.25 / zeta - 0.5 / (zeta * zeta)
        return 0.7585 * zeta + 8.0 * math.log(10.0) - 7.165
    y = math.sqrt(1.0 - 15.0 * zeta)
    return math.log(abs(zeta)) - 2.0 * math.log(1.0 + y)


def blm_temperature(
    h: float,
    z0: float,
    d0: float,
    ust: float,
    lm,
    ta_k: float,
    austal_exact: bool = False,
) -> float:
    """Temperature (K) at h m above ground, AUSTAL BlmTemp (TalBlm.c, boundary layer version 0).

    austal_exact=True: AUSTAL's code unchanged (T* with 283.15 K, profile limited to -30 to
    +40 degC). False (used by OpenALAQS): T* with ta_k and no limits.
    """
    lm = _obukhov(lm)
    z = 6.0 * z0 if h < d0 + 6.0 * z0 else h - d0
    za = BLM_HT
    t_ref = (BLM_TZERO + 10.0) if austal_exact else ta_k
    tst = (t_ref / (BLM_VKK * BLM_GRAV)) * ust * ust / lm
    t = ta_k + (tst / BLM_VKK) * (_theta(z, lm) - _theta(za, lm))
    g1, g2 = BLM_DRYAD, BLM_GRAD2
    if za < BLM_HT2:
        if z < BLM_HT2:
            t += g1 * (z - za)
        else:
            t += g2 * (z - za) + (g1 - g2) * (BLM_HT2 - za)
    else:
        if z < BLM_HT2:
            t += g1 * (z - za) + (g2 - g1) * (BLM_HT2 - za)
        else:
            t += g2 * (z - za)
    if not austal_exact:
        return t
    tbase = BLM_TZERO if ta_k > BLM_TZERO - BLM_TMAX else 0.0
    if t > tbase + BLM_TMAX:
        t = tbase + BLM_TMAX
    elif t < tbase + BLM_TMIN:
        t = tbase + BLM_TMIN
    return t


def austal_stable_mixing_height(
    ust: float, lm, fcor: float = BLM_FCOR
) -> Optional[float]:
    """AUSTAL getHm (TalBlm.c, VDI 3783 Part 8) for L > 0: the mixing height of a stable or
    neutral hour, 0.3 u*/f times sqrt(f L / u*) when that is below 1, at most 800 m and at least
    20 m. None for unstable hours (L < 0) or without wind."""
    lm = _obukhov(lm)
    if lm <= 0.0 or ust <= 0.0:
        return None
    fc = max(BLM_FCORMIN, abs(fcor))
    hm_neutral = BLM_DEFHM * BLM_FCOR / fc
    hm = 0.3 * ust / fc
    a = math.sqrt(fc * lm / ust)
    if a < 1.0:
        hm *= a
    if hm > hm_neutral:
        hm = hm_neutral
    return max(hm, BLM_HMMIN)


def _p_sat_mbar(t_k: float) -> float:
    """Saturation vapour pressure (mbar), as bffm2.calculate_emission_index."""
    t_c = t_k - 273.15
    return 6.107 * 10 ** ((7.5 * t_c) / (237.3 + t_c))


def _p_mbar(p_pa: float) -> float:
    """Pressure in mbar the way bffm2 converts it (Pa -> psia -> mbar)."""
    return p_pa * 0.14504 * 1e-3 * 68.9473


def humidity_ratio(t_k: float, p_pa: float, rh: float) -> float:
    """Humidity ratio (kg water / kg dry air) as bffm2.calculate_emission_index computes it."""
    p_sat = _p_sat_mbar(t_k)
    return (0.62197058 * rh * p_sat) / (_p_mbar(p_pa) - rh * p_sat)


def relative_humidity_for_ratio(t_k: float, p_pa: float, omega: float) -> float:
    """Relative humidity that gives the humidity ratio omega at (t_k, p_pa) in humidity_ratio."""
    return omega * _p_mbar(p_pa) / (_p_sat_mbar(t_k) * (0.62197058 + omega))


_N_GRID = int(round(_GRID_TOP_M / _GRID_STEP_M))
_GRID_H = array("d", (i * _GRID_STEP_M for i in range(_N_GRID + 1)))


class _Profile:
    """T(h) and p(h) of one hourly row for one model, on a 5 m grid from the airport to 3,000 m."""

    def __init__(self, model, t2m_k, p_ground_pa, ust, lm, z0, d0, hm=None):
        self.model = model
        self.t2m = t2m_k
        self.p0 = p_ground_pa
        self.ust, self.lm, self.z0, self.d0 = ust, lm, z0, d0
        # mixing height (m above ground): the stability term applies up to it
        self.hm = _clean_mixing_height(hm)
        self.t_hm = (
            blm_temperature(self.hm, z0, d0, ust, lm, t2m_k)
            if self.hm is not None
            else None
        )
        self.t = array("d", (self._t_exact(x) for x in _GRID_H))
        bad = [x for x in self.t if not (T_VALID_MIN_K <= x <= T_VALID_MAX_K)]
        if bad:
            raise ValueError(
                f"Atmosphere model {model}: temperature {bad[0]:.1f} K outside "
                f"{T_VALID_MIN_K:.0f} to {T_VALID_MAX_K:.0f} K (row: T {t2m_k} K, u* {ust:.3f} m/s, "
                f"L {lm} m, mixing height {hm} m)"
            )
        # ln p by the trapezoidal rule of dln p / dh = -g / (R T)
        lnp = array("d", [math.log(p_ground_pa)])
        k = G0 / R_AIR
        t = self.t
        for i in range(1, _N_GRID + 1):
            lnp.append(lnp[-1] - k * 0.5 * (1.0 / t[i - 1] + 1.0 / t[i]) * _GRID_STEP_M)
        self.lnp = lnp
        self.top_gradient = BLM_GRAD2 if model == MODEL_SURFACE_LAYER else -ISA_LAPSE

    def _t_exact(self, h):
        if self.model == MODEL_STANDARD_LAPSE:
            return self.t2m - ISA_LAPSE * h
        if h <= BLM_HT:
            return self.t2m
        if self.hm is not None and h > self.hm:
            return self.t_hm + BLM_GRAD2 * (h - self.hm)
        return blm_temperature(h, self.z0, self.d0, self.ust, self.lm, self.t2m)

    def at(self, h):
        """(T in K, p in Pa) at h m above the airport."""
        h = max(0.0, float(h or 0.0))
        if h >= _GRID_TOP_M:
            t_top, lnp_top = self.t[-1], self.lnp[-1]
            dh = h - _GRID_TOP_M
            g = self.top_gradient
            t = t_top + g * dh
            if t <= 1.0:
                t = 1.0
            p = math.exp(lnp_top) * (t / t_top) ** (-G0 / (R_AIR * g))
            return t, p
        i = min(int(h // _GRID_STEP_M), _N_GRID - 1)
        f = (h - _GRID_H[i]) / _GRID_STEP_M
        t = self._t_exact(h)
        lnp = self.lnp[i] + f * (self.lnp[i + 1] - self.lnp[i])
        return t, math.exp(lnp)


def _clean_mixing_height(hm):
    """The mixing height in m, or None when it is missing, not finite or at most 2 m
    (0, -999 and NaN are common 'missing' codes)."""
    if hm is None or hm == "":
        return None
    try:
        hm = float(hm)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(hm) or hm <= BLM_HT:
        return None
    return hm


@lru_cache(maxsize=512)
def _profile(model, t2m_k, qnh_pa, ua, lm, elevation_m, z0, d0, ha, hm):
    p_ground = station_pressure_from_qnh(qnh_pa, elevation_m)
    hm = _clean_mixing_height(hm)
    lm = _obukhov(lm)
    ust = 0.0
    if model == MODEL_SURFACE_LAYER:
        ust, lm_eff, h_flux, bounded = bounded_stability(
            ua, ha, z0, d0, lm, t2m_k, p_ground
        )
        if bounded:
            logger.warning(
                "Atmosphere aloft: the meteo row (T %.2f K, wind %.2f m/s, L %.1f m) implies a "
                "surface heat flux of %.0f W/m2; L set to %.1f m (heat flux %.0f W/m2, u* %.3f m/s).",
                t2m_k,
                ua,
                lm,
                implied_heat_flux(
                    friction_velocity(ua, ha, z0, d0, lm), lm, t2m_k, p_ground
                ),
                lm_eff,
                h_flux,
                ust,
            )
        lm_row, lm = lm, lm_eff
        # Height up to which the stability term applies: the hour's mixing height, and in
        # stable hours at most AUSTAL's own stable mixing height. The latter covers rows whose
        # MixingHeight is the ICAO 3,000 ft value rather than a measured one.
        hm_stable = austal_stable_mixing_height(ust, lm)
        if hm_stable is not None:
            hm = hm_stable if hm is None else min(hm, hm_stable)
    else:
        lm_row = lm
    try:
        return _Profile(model, t2m_k, p_ground, ust, lm, z0, d0, hm)
    except ValueError as exc:
        if lm_row != lm:
            raise ValueError(
                f"{exc}; the row's own L is {lm_row} m (replaced by the heat-flux bound)"
            ) from None
        raise


def local_state(
    model,
    temperature_k: float,
    sea_level_pressure_pa: float,
    relative_humidity: float,
    height_m: float,
    wind_speed_m_s=None,
    obukhov_length_m=None,
    airport_elevation_m: float = 0.0,
    z0=None,
    d0=None,
    ha=None,
    mixing_height_m=None,
):
    """(temperature K, pressure Pa, relative humidity) at height_m above the airport.

    The inputs are the hourly row of tbl_InvMeteo (temperature, sea-level pressure, relative
    humidity, wind speed, Obukhov length, mixing height) and the airport elevation. For
    ``ground_held`` the row is returned unchanged at every height. Without a mixing height
    (None, NaN or at most 2 m) the stability term of an unstable hour applies at every height;
    stable and neutral hours stop at AUSTAL's stable mixing height (getHm) in any case.
    Raises ValueError for invalid site parameters, a temperature or sea-level pressure that is
    not a positive number, or a profile temperature outside 180 to 340 K. The callers add the
    meteo row's date to the message.
    """
    model = normalise_model(model)
    t2m = float(temperature_k)
    qnh = float(sea_level_pressure_pa)
    rh = float(relative_humidity)
    if model == MODEL_GROUND_HELD:
        return t2m, qnh, rh
    if not (math.isfinite(t2m) and t2m > 0.0):
        raise ValueError(f"temperature {t2m} K is not a positive number")
    if not (math.isfinite(qnh) and qnh > 0.0):
        raise ValueError(f"sea-level pressure {qnh} Pa is not a positive number")
    z0_, d0_, ha_ = site_parameters(z0, d0, ha)
    prof = _profile(
        model,
        t2m,
        qnh,
        float(wind_speed_m_s or 0.0),
        _obukhov(obukhov_length_m),
        float(airport_elevation_m or 0.0),
        z0_,
        d0_,
        ha_,
        _clean_mixing_height(mixing_height_m),
    )
    h = max(0.0, float(height_m or 0.0))
    t, p = prof.at(h)
    omega = humidity_ratio(t2m, prof.p0, rh)
    rh_local = rh if h == 0.0 else relative_humidity_for_ratio(t, p, omega)
    return t, p, rh_local
