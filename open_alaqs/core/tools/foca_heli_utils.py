"""
FOCA 2015 helicopter LTO emissions methodology (orchestration layer).

Wraps the reference primitives in foca_heli to produce per-mode emissions
and full-LTO totals from a small input set:

    compute_mode_emissions(category, max_shp, power_fraction) -> ModeEmissions
    compute_lto(category, max_shp, n_engines)                 -> LtoResult
    gi_time_for_movement(category, is_departure)              -> minutes

The output dataclasses are pure data (no plugin Emission types here).
Adaptation to open_alaqs's EmissionIndex / Emission objects happens at
the calculator layer in Phase 4.

Full LTO formula (FOCA 2015 section 4.1):
    LTO_Fuel      = 60 * (GI_t * GI_FF + TO_t * TO_FF + AP_t * AP_FF) * n
    LTO_Pollutant = 60 * (GI_t * GI_FF * GI_EI + ... ) * n

Times in minutes (the *60 converts to seconds), fuel flow in kg/s, EI in g/kg,
n is the engine count. The full GI time is treated as a single emission mode;
the 80/20 split between departure and arrival halves is applied to the
time charged to each movement (gi_time_for_movement), not to the EIs.
"""

from dataclasses import dataclass, field

from open_alaqs.core.tools.foca_heli import (
    CO2_FACTOR_AVGAS,
    CO2_FACTOR_JET,
    GI_ARRIVAL_FRACTION,
    GI_DEPARTURE_FRACTION,
    PROFILES,
    HelicopterCategory,
    piston_ei_co_g_kg,
    piston_ei_hc_g_kg,
    piston_ei_nox_g_kg,
    piston_ei_pm_g_kg,
    piston_fuel_flow_kg_s,
    piston_mean_particle_size_nm,
    pm_number_per_kg,
    turboshaft_ei_co_g_kg,
    turboshaft_ei_hc_g_kg,
    turboshaft_ei_nox_g_kg,
    turboshaft_ei_pm_nvol_g_kg,
    turboshaft_fuel_flow_kg_s,
    turboshaft_mean_particle_size_nm,
)

# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModeEmissions:
    """Per-mode emission factors and fuel flow. Per single engine."""

    fuel_flow_kg_s: float
    ei_nox_g_kg: float
    ei_hc_g_kg: float
    ei_co_g_kg: float
    ei_pm_g_kg: float
    pm_number_per_kg: float
    co2_g_kg: float


@dataclass(frozen=True)
class ModeResult:
    """Totals for one mode (GI, TO, or AP) of a full LTO.

    Values are summed across n_engines. Units in field names.
    """

    mode: str  # "GI" | "TO" | "AP"
    power_fraction: float
    time_s: float
    fuel_flow_kg_s_per_engine: float
    fuel_kg: float
    nox_g: float
    hc_g: float
    co_g: float
    pm_g: float
    co2_g: float


@dataclass(frozen=True)
class LtoResult:
    """Full-LTO totals plus per-mode breakdown."""

    fuel_kg: float
    nox_g: float
    hc_g: float
    co_g: float
    pm_g: float
    co2_g: float
    modes: list[ModeResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def compute_mode_emissions(
    category: HelicopterCategory,
    max_shp_per_engine: float,
    power_fraction: float,
) -> ModeEmissions:
    """Per-mode emission factors for a helicopter at a given power setting.

    Dispatches piston vs turboshaft based on category. Returns per-engine
    values; the caller scales by n_engines and mode time to get totals.
    """
    if max_shp_per_engine <= 0:
        raise ValueError(
            f"max_shp_per_engine must be positive, got {max_shp_per_engine!r}",
        )
    mode_shp = max_shp_per_engine * power_fraction

    if category == HelicopterCategory.PISTON:
        ff = piston_fuel_flow_kg_s(mode_shp)
        ei_nox = piston_ei_nox_g_kg(power_fraction)
        ei_hc = piston_ei_hc_g_kg(mode_shp)
        ei_co = piston_ei_co_g_kg(mode_shp)
        ei_pm = piston_ei_pm_g_kg(power_fraction)
        d_nm = piston_mean_particle_size_nm(power_fraction)
        co2 = CO2_FACTOR_AVGAS * 1000.0
    else:
        ff = turboshaft_fuel_flow_kg_s(max_shp_per_engine, mode_shp)
        ei_nox = turboshaft_ei_nox_g_kg(mode_shp)
        ei_hc = turboshaft_ei_hc_g_kg(mode_shp)
        ei_co = turboshaft_ei_co_g_kg(mode_shp)
        ei_pm = turboshaft_ei_pm_nvol_g_kg(mode_shp)
        d_nm = turboshaft_mean_particle_size_nm(category, power_fraction)
        co2 = CO2_FACTOR_JET * 1000.0

    return ModeEmissions(
        fuel_flow_kg_s=ff,
        ei_nox_g_kg=ei_nox,
        ei_hc_g_kg=ei_hc,
        ei_co_g_kg=ei_co,
        ei_pm_g_kg=ei_pm,
        pm_number_per_kg=pm_number_per_kg(ei_pm, d_nm),
        co2_g_kg=co2,
    )


def compute_lto(
    category: HelicopterCategory,
    max_shp_per_engine: float,
    number_of_engines: int,
) -> LtoResult:
    """Full-LTO totals for a helicopter.

    A full LTO = one departure + one arrival, with GI covering both halves
    (5 minutes total in the 2015 edition). Per-mode totals are scaled by
    n_engines.
    """
    if number_of_engines < 1:
        raise ValueError(
            f"number_of_engines must be >= 1, got {number_of_engines!r}",
        )
    profile = PROFILES[category]
    gi = _mode_result(
        "GI",
        profile.gi_power,
        profile.gi_time_min,
        compute_mode_emissions(category, max_shp_per_engine, profile.gi_power),
        number_of_engines,
    )
    to = _mode_result(
        "TO",
        profile.to_power,
        profile.to_time_min,
        compute_mode_emissions(category, max_shp_per_engine, profile.to_power),
        number_of_engines,
    )
    ap = _mode_result(
        "AP",
        profile.ap_power,
        profile.ap_time_min,
        compute_mode_emissions(category, max_shp_per_engine, profile.ap_power),
        number_of_engines,
    )
    return LtoResult(
        fuel_kg=gi.fuel_kg + to.fuel_kg + ap.fuel_kg,
        nox_g=gi.nox_g + to.nox_g + ap.nox_g,
        hc_g=gi.hc_g + to.hc_g + ap.hc_g,
        co_g=gi.co_g + to.co_g + ap.co_g,
        pm_g=gi.pm_g + to.pm_g + ap.pm_g,
        co2_g=gi.co2_g + to.co2_g + ap.co2_g,
        modes=[gi, to, ap],
    )


def gi_time_for_movement(
    category: HelicopterCategory,
    is_departure: bool,
) -> float:
    """Return the GI time (minutes) charged to one half-LTO movement.

    Departure carries 80% of the GI time, arrival the remaining 20%
    (FOCA 2015 Appendix A). Sum across a paired dep+arr movement
    recovers the full 5 minute GI.
    """
    profile = PROFILES[category]
    fraction = GI_DEPARTURE_FRACTION if is_departure else GI_ARRIVAL_FRACTION
    return profile.gi_time_min * fraction


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mode_result(
    name: str,
    power_fraction: float,
    time_min: float,
    em: ModeEmissions,
    n_engines: int,
) -> ModeResult:
    time_s = time_min * 60.0
    fuel_total = em.fuel_flow_kg_s * time_s * n_engines
    return ModeResult(
        mode=name,
        power_fraction=power_fraction,
        time_s=time_s,
        fuel_flow_kg_s_per_engine=em.fuel_flow_kg_s,
        fuel_kg=fuel_total,
        nox_g=fuel_total * em.ei_nox_g_kg,
        hc_g=fuel_total * em.ei_hc_g_kg,
        co_g=fuel_total * em.ei_co_g_kg,
        pm_g=fuel_total * em.ei_pm_g_kg,
        co2_g=fuel_total * em.co2_g_kg,
    )
