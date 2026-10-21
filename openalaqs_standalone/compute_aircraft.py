"""
compute_aircraft: fixed-wing aircraft emission core.

This module is the standalone's port of the fixed-wing emission
pipeline in the CAEP14 validation reference
(`validation/tools/compute_caep14_reference.py`): `_compute_fixed_wing`
and its helpers `_build_icao_eedb`, `_segment_mach`,
`_segment_ei_bffm2`, `_add_em`, `_parse_dt`, `_bffm2_apply_segment`,
`_bffm2_traj_ff_amb`, `_twin_quadratic_ff_from_power`.

It computes per-movement emission totals for one fixed-wing movement,
for any of the three methods:

  bymode        EI from the EEDB table at the segment's LTO mode; pure
                fuel * EI_table / 1000.
  bffm2_anchor  fuel stays at the mode anchor (so CO2 matches bymode),
                but NOx/CO/HC EI is replaced by the BFFM2-ambient EI
                computed at the mode's anchor fuel flow.
  bffm2_traj    fuel AND NOx/CO/HC EI are resolved per segment, using
                either the trajectory's own fuel_flow_kgm (CUSTOM /
                ADS-B) or a twin-quadratic fit on the segment power
                setting (ANP), with BFFM2 ambient corrections.

SOx and PM10 use the EEDB-table EI (the plugin's BFFM2 implementation
has no BFFM2 path for them), except that above 3000 ft above the aerodrome
(ICAO LTO cycle) the nvPM part of PM10 is the MEEM V1 value (shared `open_alaqs.core.tools.meem_v1`,
as the plugin).

This module is the per-movement-totals core: the "(a)" output mode in
the strategy document. It computes one movement to a totals dict. The
later "(c)" layer (`distribute.py`) will reuse the same per-segment
results to spread emissions across (hour, grid-cell); this module is
written so that per-segment data is available to that layer rather
than discarded.

Differences from the reference, all deliberate:

  - Geometry primitives come from `openalaqs_standalone.geometry`
    (the WKB-sourced, full-precision port) instead of the reference's
    inline `_`-prefixed helpers.
  - Database accessors come from `openalaqs_standalone.movements`
    instead of the reference's inline DB readers.
  - The BFFM2 module is imported from the shared core at
    `open_alaqs.core.tools.bffm2`, byte-identical to the plugin's.
  - The twin-quadratic fit is reimplemented inline exactly as the
    reference does (`_twin_quadratic_ff_from_power`), so the two can
    be cross-checked; the shared
    `open_alaqs.core.tools.twin_quadratic_fit_method` is the canonical
    original.

The reference reads geometry via `ST_AsText` (6 decimal places); the
standalone uses full-precision WKB. The coordinate divergence is at
most ~5e-7 m, far below the validation tolerance, and cannot move any
pollutant off the documented 0.00 percent. See `geometry.py`.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from open_alaqs.core.tools import meem_v1 as _meem_v1
from open_alaqs.core.tools.bffm2 import calculate_emission_index as _bffm2_ei
from open_alaqs.core.tools.bffm2 import speed_of_sound_m_s as _speed_of_sound_m_s
from openalaqs_standalone import geometry as geo
from openalaqs_standalone import movements as mv
from openalaqs_standalone import nox_correction as _nox_corr
from openalaqs_standalone import runway_placement as rp

# ---------------------------------------------------------------------------
# Constants (must match the plugin and the CAEP14 reference)
# ---------------------------------------------------------------------------

# LTO vertical ceiling default: 3000 ft. The runtime value used in
# the segment loop is `max_height_m` (per-movement, from
# tbl_InvMeteo.MixingHeight; see compute_fixed_wing). This constant
# is retained as the documented LTO fallback for any code path that
# does not pass a per-movement value and for parity tests against
# `compute_caep14_reference.MAX_HEIGHT_M`.
MAX_HEIGHT_M = 914.4
# Tolerance on the vertical ceiling test, matching the plugin's
# apply_height_limits ULP fix.
EPS_VERTICAL_M = 1e-6
# Plausibility limit for a supplied (ADS-B / CUSTOM) fuel flow, as a multiple of the
# engine's ICAO take-off fuel flow. The ICAO value is a static, sea-level test-bed
# figure, not an in-flight maximum: at climb speed the fuel flow for a given net thrust
# is higher (ram drag), and climb points at high thrust can exceed it by a few percent.
# Only values above this multiple are treated as implausible input (wrong units, a
# total entered per engine, a wrong engine count) and replaced by the mode anchor. Same
# value as open_alaqs.core.MovementEmissionCalculator.ADSB_FF_CEILING_FACTOR.
# Above the take-off point the BFFM2 indices stay bounded: NOx is held at its
# take-off value, CO and HC at the mean of the climb-out and take-off values (as
# from the climb-out point upwards), so an accepted fuel flow above the take-off
# value needs no other guard.
ADSB_FF_CEILING_FACTOR = 1.5
# CO2 per kg of fuel burned (stoichiometric, ICAO).
CO2_PER_KG_FUEL = 3.16

# Brake-wear PM10 for arrivals, applied once on the first taxi-in
# segment for arriving aircraft above the MTOW threshold. Linear
# model: brake_wear_g = MTOW * slope - intercept. Per
# MovementEmissionCalculator
# _apply_single_engine_taxiing_emissions_for_arrival.
BRAKE_WEAR_MTOW_THRESHOLD_KG = 18632.0

# Plugin constant for stop-and-go events (idle taxi per stop), seconds.
# MovementEmissionCalculator.AVERAGE_DURATION_OF_STOP_AND_GOS_IN_S = 9.0.
# Each stop contributes this many extra idle-seconds of emissions at the
# LAST taxi segment, scaled by n_eng. Zero contribution when the movement
# has no stops (the canonical test study has all-zero number_of_stop_and_gos).
AVERAGE_DURATION_OF_STOP_AND_GOS_IN_S = 9.0
BRAKE_WEAR_SLOPE = 0.000476
BRAKE_WEAR_INTERCEPT = 8.74

# The seven pollutants the per-movement totals carry. pm25 mirrors pm10
# because aircraft engine PM is sub-micrometer (PM10 = PM1 = PM2.5 by
# convention in ICAO LTO); brake wear is also assigned identically to
# PM10, PM1, and PM2.5 by the QGIS plugin (see
# MovementEmissionCalculator.add_value loop over (PM10, PM1, PM2)).
# Producing the same numerical value for pm10 and pm25 is what the
# plugin does, so this is the reference behaviour we need to match.
POLLUTANTS = ("co", "co2", "hc", "nox", "sox", "pm10", "pm25")

# Pollutant -> EEDB emission-index column name.
EI_COLS = {
    "co": "co_ei",
    "hc": "hc_ei",
    "nox": "nox_ei",
    "sox": "sox_ei",
    "pm10": "pm10_ei",
}

# default_aircraft_engine_ei mode labels -> the bffm2 module's keys.
BFFM2_MODE_NAMES = {
    "TX": "Idle",
    "AP": "Approach",
    "CL": "Climbout",
    "TO": "Takeoff",
}

# CAEP14 default installation corrections. Same as the bffm2 module
# defaults but kept explicit here for traceability against
# SAE AIR-5715, exactly as the reference does.
BFFM2_INSTALLATION_CORRECTIONS = {
    "Takeoff": 1.010,
    "Climbout": 1.013,
    "Approach": 1.020,
    "Idle": 1.100,
}


# ---------------------------------------------------------------------------
# Small helpers (ported verbatim from the reference)
# ---------------------------------------------------------------------------


def _parse_dt(s: str) -> datetime:
    """Parse an `.alaqs` datetime string. Ported from the reference."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _add_em(em: dict, fuel_kg: float, ei: dict) -> None:
    """Add one segment's bymode emissions into the running totals dict.

    `em` is mutated in place. `ei` is an EEDB-row dict carrying the
    five `*_ei` columns. Ported verbatim from the reference's
    `_add_em`. PM2.5 is mirrored from PM10 because aircraft engine PM
    is sub-micrometer (matches the QGIS plugin convention of equal
    PM10/PM1/PM2.5 for aircraft engines).
    """
    for p, col in EI_COLS.items():
        em[p] += fuel_kg * ei[col] / 1000.0
    em["pm25"] += fuel_kg * ei["pm10_ei"] / 1000.0
    em["co2"] += fuel_kg * CO2_PER_KG_FUEL


def _build_icao_eedb(engine_ei: dict) -> dict:
    """Build the nested icao_eedb dict that the bffm2 module expects.

    Format: {"NOx" / "CO" / "HC": {bffm2_mode: {ff_ref_kg_s: ei_g_kg}}}.
    The bffm2 module applies installation_corrections internally to the
    ff_ref keys, so the raw (un-corrected) EEDB fuel-flow values are
    passed here. Ported verbatim from the reference's `_build_icao_eedb`.
    """
    eedb: dict = {p: {} for p in ("NOx", "CO", "HC")}
    pol_map = {"NOx": "nox_ei", "CO": "co_ei", "HC": "hc_ei"}
    for ei_mode, bffm2_mode in BFFM2_MODE_NAMES.items():
        if ei_mode not in engine_ei:
            continue
        ff_ref = engine_ei[ei_mode]["ff"]
        for pol_name, ei_col in pol_map.items():
            eedb[pol_name][bffm2_mode] = {ff_ref: engine_ei[ei_mode][ei_col]}
    return eedb


def _segment_mach(tas_start: float, tas_end: float, T_K: float) -> float:
    """Per-segment flight Mach number TAS / a(T).

    Uses the segment's START-point TAS (as the plugin,
    MovementEmissionCalculator.calculate_emissions_per_segment) and the
    speed of sound a = sqrt(gamma R T) at the ambient temperature
    (`bffm2.speed_of_sound_m_s`). The `tas_end` argument is accepted for
    signature parity with the reference but is not used.
    """
    sos = _speed_of_sound_m_s(T_K)
    if sos <= 0:
        return 0.0
    return tas_start / sos


def _meem_v1_segment_ei(
    eng: dict,
    meem: dict,
    mode: str,
    alt_msl_m: float,
    tas_m_s: float,
    climbing: bool,
    delta_t: float = 0.0,
    airport_elevation_m: float = 0.0,
) -> dict:
    """The segment's EI with the MEEM V1 nvPM mass EI (shared
    `open_alaqs.core.tools.meem_v1`, the plugin's code) as the plugin's
    Engine.getEmissionIndexByModeWithMEEM applies it: at or below 3000 ft
    above the aerodrome (`alt_msl_m - airport_elevation_m`, ICAO LTO cycle)
    `eng` unchanged; above, pm10_ei moves by the MEEM mass EI minus the
    mode's pm10_nonvol, with the chain's ISA atmosphere at `alt_msl_m`
    (above MSL). `delta_t`: ISA deviation (K) from the movement's meteo
    (`meem_v1.delta_t_from_ground`); without meteo the ISA sea-level
    288.15 K is used, so 0.0065 K/m x elevation."""
    alt_ft = alt_msl_m / _meem_v1.FT_TO_M
    height_ft = (alt_msl_m - (airport_elevation_m or 0.0)) / _meem_v1.FT_TO_M
    if not meem or _meem_v1.section_of_flight(height_ft) == "LTO":
        return eng
    ts = [t for t in _meem_v1.MODE_THRUST.values()]
    mass = [meem["pm10_nonvol"][m] * 1000.0 for m in _meem_v1.MODE_THRUST]
    number = [meem["nvpm_number"][m] for m in _meem_v1.MODE_THRUST]
    ts_num = list(ts)
    if meem["m_f00"] and meem["m_f00"] > 0 and meem["m_max_mgkg"] is not None:
        ts.append(meem["m_f00"])
        mass.append(meem["m_max_mgkg"])
    if meem["n_f00"] and meem["n_f00"] > 0 and meem["n_max_nkg"] is not None:
        ts_num.append(meem["n_f00"])
        number.append(meem["n_max_nkg"])
    result = _meem_v1.calculate_nvpm_ei(
        phase="CLIMB TO CRUISE" if climbing else "DESCENT TO APPROACH",
        altitude_ft=alt_ft,
        thrust_settings=ts,
        ei_mass_mgkg=mass,
        ei_number_nkg=number,
        opr=meem["press_ratio"] or _meem_v1.DEFAULT_OPR,
        tas_kt=tas_m_s * _meem_v1.MS_TO_KT,
        number_thrust_settings=ts_num,
        delta_t=delta_t,
    )
    delta = result.nvpm_mass_ei_mgkg / 1000.0 - meem["pm10_nonvol"][mode]
    return dict(eng, pm10_ei=eng["pm10_ei"] + delta)


def _segment_ei_bffm2(
    pollutant: str,
    ff_amb_kg_s: float,
    icao_eedb: dict,
    meteo: dict,
    mach: float,
) -> float:
    """Per-segment BFFM2 ambient EI for one of NOx / CO / HC.

    Delegates to the shared `open_alaqs.core.tools.bffm2` module, the
    same code the plugin uses. Ported verbatim from the reference's
    `_segment_ei_bffm2`.
    """
    return _bffm2_ei(
        pollutant,
        ff_amb_kg_s,
        icao_eedb,
        ambient_conditions={
            "temperature_in_Kelvin": meteo["T_K"],
            "pressure_in_Pa": meteo["P_Pa"],
            "relative_humidity": meteo["RH"],
            "mach_number": mach,
        },
        installation_corrections=BFFM2_INSTALLATION_CORRECTIONS,
    )


def _bffm2_apply_segment(
    em: dict,
    ff_amb_per_engine_kg_s: float,
    fuel_kg: float,
    eng: dict,
    icao_eedb: dict,
    meteo: dict,
    mach: float,
) -> None:
    """Add one segment's BFFM2 emissions into the running totals dict.

    PM10 and SOx use the EEDB-table EI; NOx/CO/HC use the BFFM2-ambient
    EI at the segment's ambient fuel flow. CO2 is stoichiometric. `em`
    is mutated in place. Ported verbatim from the reference's
    `_bffm2_apply_segment`.
    """
    em["pm10"] += fuel_kg * eng["pm10_ei"] / 1000.0
    # Aircraft engine PM is treated as all sub-micrometer (PM10 = PM1 =
    # PM2.5). Matches the QGIS plugin's behaviour, which assigns the
    # same value to PollutantType.PM10, .PM1, and .PM2 in
    # MovementEmissionCalculator.
    em["pm25"] += fuel_kg * eng["pm10_ei"] / 1000.0
    em["sox"] += fuel_kg * eng["sox_ei"] / 1000.0
    em["co2"] += fuel_kg * CO2_PER_KG_FUEL
    for pol_name, dest_key in (("NOx", "nox"), ("CO", "co"), ("HC", "hc")):
        ei = _segment_ei_bffm2(pol_name, ff_amb_per_engine_kg_s, icao_eedb, meteo, mach)
        em[dest_key] += fuel_kg * ei / 1000.0


def _twin_quadratic_ff_from_power(power: float, engine_ei: dict) -> float:
    """Replicate the plugin's twin_quadratic_fit_method exactly.

    A piecewise 3-point quadratic, NOT a 4-point least-squares fit:
      power <= 0.85: parabola through (0.07, 0.30, 0.85)
      power  > 0.85: parabola through (0.30, 0.85, 1.00)
    Values are normalised by the 100 percent (Takeoff) fuel flow, the
    quadratic is solved, then de-normalised. For power < 0.07 the
    result is clamped to the Idle fuel flow.

    Ported verbatim from the reference's `_twin_quadratic_ff_from_power`.
    The shared `open_alaqs.core.tools.twin_quadratic_fit_method` is the
    canonical original; this inline copy exists so the two can be
    cross-checked, exactly as in the reference.
    """
    # icao_eedb in plugin form: {power_pct: ff_kg_s}
    ff_by_p: dict = {}
    for mode_label, power_pct in (
        ("TX", 0.07),
        ("AP", 0.30),
        ("CL", 0.85),
        ("TO", 1.00),
    ):
        if mode_label in engine_ei:
            ff_by_p[power_pct] = engine_ei[mode_label]["ff"]
    if any(k not in ff_by_p for k in (0.07, 0.30, 0.85, 1.00)):
        return engine_ei.get("AP", engine_ei.get("TX", {"ff": 0.0}))["ff"]

    # Upper-tolerance clamp: small overshoots above 1.0 (typically 1-2%
    # from floating-point noise in profile interpolation, rounding in
    # default_emission_dynamics, or BFFM2 ambient power derivation under
    # non-ISA conditions) should be treated as 100% thrust, not
    # extrapolated through the upper-arm quadratic. Above 5%, raise.
    # Mirrors the plugin's twin_quadratic_fit_method.py _PS_UPPER_TOLERANCE.
    _PS_UPPER_TOLERANCE = 1.05
    if 1.0 < power <= _PS_UPPER_TOLERANCE:
        power = 1.0
    elif power > _PS_UPPER_TOLERANCE:
        raise ValueError(
            f"power_setting {power} exceeds upper tolerance "
            f"{_PS_UPPER_TOLERANCE} for twin-quadratic fit"
        )

    if power <= 0.85:
        x1, x2, x3 = 0.07, 0.30, 0.85
    else:
        x1, x2, x3 = 0.30, 0.85, 1.00

    max_rated_t = ff_by_p[1.0]
    y1 = ff_by_p[x1] / max_rated_t
    y2 = ff_by_p[x2] / max_rated_t
    y3 = ff_by_p[x3] / max_rated_t

    # Solve y = a x^2 + b x + c through three points.
    a = (y3 - y1) / ((x3 - x1) * (x1 - x2)) - (y3 - y2) / ((x3 - x2) * (x1 - x2))
    b = (y3 - y1) / (x3 - x1) - a * (x3 + x1)
    c = y3 - a * x3**2 - b * x3
    y = a * power**2 + b * power + c

    ff = y * max_rated_t
    if power < 0.07:
        ff = max(ff, ff_by_p[0.07])  # clamp at idle
    return max(0.0, ff)


def _bffm2_traj_ff_amb(
    conn,
    mov: dict,
    pt: tuple,
    eng: dict,
    engine_ei: dict,
    meteo: dict,
    mach: float,
    n_eng: int,
) -> float:
    """Per-engine ambient fuel flow for the bffm2_traj method.

    Mirrors MovementEmissionCalculator lines 1082-1124:
      - If the trajectory point carries `fuel_flow_kgm` (ADS-B /
        CUSTOM profiles): use fuel_flow_kgm / n_eng, with a fallback to
        the mode anchor when it exceeds ADSB_FF_CEILING_FACTOR x the TO
        anchor fuel flow (plausibility limit).
      - Otherwise (ANP profiles): twin-quadratic fit on the segment's
        `power` setting to get the EEDB reference fuel flow, then the
        SAE AIR-5715 / CAEP14 inverse ambient correction:
            ff_amb = ff_ref * delta / theta^3.8 / exp(0.2 * M^2)

    `power` and `fuel_flow_kgm` are re-read per point via
    `movements.get_trajectory_point_power_ff`, exactly as the reference
    re-reads them (the 7-column `get_trajectory` does not carry them).

    Ported verbatim from the reference's `_bffm2_traj_ff_amb`, with the
    inline SQL replaced by the `movements` accessor.
    """
    point_idx = pt[0]
    power, ff_kgm = mv.get_trajectory_point_power_ff(conn, mov["profile_id"], point_idx)

    # ADS-B / CUSTOM path: fuel_flow_kgm is an ambient (in-flight) FF
    # for ALL engines combined.
    ff_to_ceiling = engine_ei["TO"]["ff"] * ADSB_FF_CEILING_FACTOR
    if ff_kgm not in (None, 0):
        ff_per_engine = ff_kgm / n_eng
        if ff_per_engine > ff_to_ceiling:
            return eng["ff"]  # ceiling fallback to mode anchor
        return ff_per_engine

    # ANP path: twin-quadratic fit on power, then inverse ambient
    # correction.
    if power is None:
        return eng["ff"]  # fall back to mode anchor if power missing
    try:
        ff_ref = _twin_quadratic_ff_from_power(power, engine_ei)
    except ValueError:
        # Piston / propeller profiles (PA28, CNA206, PISTON-*, etc.)
        # carry `power` values well above the 1.05 turbofan tolerance
        # (e.g. 1.40 up to 6.25), because for those engines the column
        # is not a thrust fraction. The twin-quadratic fit is only
        # defined for turbofan/turbojet engines. Fall back to mode-
        # anchor FF in that case, mirroring the plugin's behaviour
        # (MovementEmissionCalculator wraps the BFFM2 EI lookup in
        # `try / except Exception` and falls back to the mode anchor on
        # any error from the BFFM2 path).
        return eng["ff"]
    theta = meteo["T_K"] / 288.15
    delta = meteo["P_Pa"] / 101325.0
    ff_amb = ff_ref * delta / (theta**3.8) / math.exp(0.2 * mach**2)
    return ff_amb


# ---------------------------------------------------------------------------
# Fixed-wing per-movement compute
# ---------------------------------------------------------------------------


def compute_fixed_wing(  # noqa: C901 — orchestrates the full per-movement aircraft emission pipeline
    conn,
    mov: dict,
    ctx: dict,
    method: str = "bymode",
    use_isa_meteo: bool = True,
    apply_nox_corrections: bool = False,
) -> Optional[dict]:
    """Compute per-movement emissions for one fixed-wing movement.

    Parameters
    ----------
    conn
        An open `.alaqs` connection (from `movements.connect`).
    mov
        The movement dict from `movements.get_movement`.
    ctx
        Shared per-study context. Must carry:
          ctx["runways"]       dict from movements.get_runways, keyed by direction
          ctx["grid_bounds"]   the dict from `geometry.grid_bounds_3857`
        and may carry:
          ctx["intersection_cache"]  a dict, populated lazily here, of
                                     route_name -> intersection point
          ctx["airport_elevation_m"] used by the NOx ambient correction
                                     when apply_nox_corrections=True.
    method
        One of "bymode", "bffm2_anchor", "bffm2_traj".
    use_isa_meteo
        When True (default), BFFM2 ambient corrections use ISA
        conditions, matching the plugin's emission-CSV output. When
        False, the loaded `tbl_InvMeteo` row is used. No effect when
        method == "bymode".
    apply_nox_corrections
        When True AND method == "bymode", apply the ICCAIA / CAEP14 v14
        simple-method NOx correction at takeoff and climb-out segments.
        Reads ambient T, P, RH from `tbl_InvMeteo` per-period (same row
        BFFM2 uses), and tow_ratio from the movement (defaults to 1.0
        when unset, which drops the weight term). Defaults to False to
        preserve historical bymode behaviour. Suppressed when method !=
        "bymode" (BFFM2 already incorporates ambient corrections; double-
        correcting would be wrong). Mirrors the plugin's
        `_apply_nox_corrections` (MovementEmissionCalculator.py:1049-
        1053), which is gated by the same condition.

    Returns
    -------
    A per-movement result dict (see the return statement for the full
    shape), or None if the movement cannot be computed (missing engine
    EI, zero engine count, missing trajectory).

    Ported from the reference's `_compute_fixed_wing`, with geometry
    and DB calls rewired to the `geometry` and `movements` modules. The
    per-segment fuel-by-mode breakdown and the segment counters are
    kept in the result so the later (c) distribution layer can reuse
    them.
    """
    if method not in ("bymode", "bffm2_anchor", "bffm2_traj"):
        raise ValueError(f"Unknown method: {method!r}")

    engine_ei = mv.get_engine_ei(conn, mov["engine_name"])
    if "TX" not in engine_ei:
        return None
    n_eng = mv.get_engine_count(conn, mov["aircraft"])
    if n_eng <= 0:
        return None
    meem = mv.get_engine_meem(conn, mov["engine_name"])

    # Decide whether to load the meteo row. BFFM2 always needs it; bymode
    # also needs it when the NOx ambient correction is requested, and for
    # the MEEM V1 temperature deviation above 3000 ft above the aerodrome
    # (the plugin always has the period's meteo).
    needs_meteo = (method != "bymode") or apply_nox_corrections or bool(meem)

    # BFFM2 setup: build the icao_eedb dict once per movement, fetch
    # the meteo row. Skipped entirely for bymode unless the NOx ambient
    # correction is requested (in which case bymode also needs meteo).
    icao_eedb = _build_icao_eedb(engine_ei) if method != "bymode" else None
    meteo = (
        mv.get_meteo_at(conn, mov["runway_time"], use_isa=use_isa_meteo)
        if needs_meteo
        else None
    )
    # Per-movement vertical ceiling used by apply_height_limits. Reads
    # tbl_InvMeteo.MixingHeight for the period containing runway_time;
    # falls back to user_study_setup.vertical_limit (or 914.4 m) when
    # missing. Mirrors MovementSourceModule.process() lines 254-260,
    # which sets calculation_limit["max_height"] from
    # ambient_conditions.getMixingHeight() (which reads tbl_InvMeteo)
    # and only falls back to vertical_limit_m on AttributeError.
    max_height_m = mv.get_mixing_height_at(conn, mov["runway_time"])

    # ---- TX (taxi) ----
    # Total taxi time is the absolute gap between runway_time and block_time.
    # The plugin splits this into a "natural" portion (sum of segment
    # length/speed, distributed along the route by length) and a "queuing"
    # portion (the excess, placed entirely at the LAST taxi segment).
    # Stop-and-go is an additional emission at the last segment.
    # See MovementEmissionCalculator.py lines 327, 383-403 for the
    # plugin source. The standalone must match for the spatial pattern
    # to align: distributing total time by length over-feeds the
    # mid-route segments and starves the gate-side segment of the
    # the bulk of typical taxi time that is queuing.
    taxi_time_s = abs(
        (_parse_dt(mov["runway_time"]) - _parse_dt(mov["block_time"])).total_seconds()
    )
    # Natural time: cached per-route via ctx (see compute_movements
    # for the cache build). Falls back to taxi_time_s when missing so
    # behaviour degrades gracefully — the old all-in-tx_em layout —
    # rather than zero-ing out taxi emissions.
    natural_taxi_time_s = taxi_time_s
    route_time_s = taxi_time_s  # the route's own time at its segment speeds (uncapped); total when unknown
    nat_cache = ctx.get("natural_taxi_times")
    if nat_cache is not None:
        cached = nat_cache.get(mov["taxi_route"])
        if cached is not None:
            natural_taxi_time_s = min(cached, taxi_time_s)
            route_time_s = cached
    queuing_time_s = max(0.0, taxi_time_s - natural_taxi_time_s)
    # Stop-and-go: AVERAGE_DURATION = 9 s per stop (plugin constant).
    stop_and_go_time_s = AVERAGE_DURATION_OF_STOP_AND_GOS_IN_S * float(
        mov.get("number_of_stop_and_gos") or 0
    )

    tx = engine_ei["TX"]
    # For BFFM2 (both anchor and traj sub-methods) the plugin's
    # TaxiingEmissionCalculator routes through
    # `getEmissionIndexByEngineState(power_setting=engine_thrust_level_taxiing,
    # method=BFFM2)` with `fuel_flow=None`, which falls into the
    # twin-quadratic / power-setting branch in `Engine.getEmissionIndexByEngineState`
    # and applies the SAE AIR-5715 inverse ambient correction:
    #     ff_amb = ff_ref * delta / theta^3.8 / exp(0.2 * M^2)   (M=0 at taxi)
    # The standalone must match: the reference EEDB idle FF (`tx["ff"]`)
    # is corrected to ambient before the segment fuel is computed.
    # For bymode the plugin uses the table EI directly, no FF correction.
    if method != "bymode":
        theta = meteo["T_K"] / 288.15
        delta = meteo["P_Pa"] / 101325.0
        tx_ff_amb = tx["ff"] * delta / (theta**3.8)  # mach=0 at taxi
    else:
        tx_ff_amb = tx["ff"]

    # Compute three separate emission bundles: natural (along the route by
    # length), queue (at the last segment), and stop-and-go (also at the
    # last segment). Each shares the same idle FF and EI; only the time
    # multiplier differs. Plugin scaling: natural × n_eng × taxi_fuel_ratio,
    # queue × n_eng (no fuel ratio), stop × n_eng (no fuel ratio).
    nat_fuel = natural_taxi_time_s * tx_ff_amb * n_eng * mov["taxi_fuel_ratio"]
    queue_fuel = queuing_time_s * tx_ff_amb * n_eng
    stop_fuel = stop_and_go_time_s * tx_ff_amb * n_eng

    def _build_em(fuel_kg):
        em_local = {p: 0.0 for p in POLLUTANTS}
        if fuel_kg <= 0.0:
            return em_local
        if method == "bymode":
            _add_em(em_local, fuel_kg, tx)
        else:
            _bffm2_apply_segment(
                em_local, tx_ff_amb, fuel_kg, tx, icao_eedb, meteo, mach=0.0
            )
        return em_local

    tx_em = _build_em(nat_fuel)
    queue_em = _build_em(queue_fuel)
    stop_em = _build_em(stop_fuel)

    # Brake-wear PM10/PM2.5: arrivals only, MTOW above the threshold.
    # The plugin (MovementEmissionCalculator
    # _apply_single_engine_taxiing_emissions_for_arrival) gates this on
    # `index_segment == 0` and so places the entire brake-wear mass on
    # the FIRST segment of the arrival taxi-route, not length-distributed
    # along it. We mirror that by carrying brake-wear in its own
    # `brake_wear_em` dict (separate from tx_em) and letting distribute.py
    # place it at idx == 0 of the arrival route (parallel to apu_em /
    # start_em placement). Folding it into tx_em would length-distribute
    # the mass and was the earlier-version bug that drove the PM10
    # per-cell redistribution observed in the round-6 plugin diff.
    brake_wear_kg = 0.0
    brake_wear_em = {p: 0.0 for p in POLLUTANTS}
    if mov["departure_arrival"] == "A":
        mtow = mv.get_mtow_kg(conn, mov["aircraft"])
        if mtow is not None and mtow > BRAKE_WEAR_MTOW_THRESHOLD_KG:
            brake_wear_kg = (
                mtow * BRAKE_WEAR_SLOPE - BRAKE_WEAR_INTERCEPT
            ) / 1000.0  # g -> kg
            # Plugin assigns the same brake-wear value to PM10, PM1, and
            # PM2 (see MovementEmissionCalculator add_value loop). The
            # standalone tracks PM10 and PM2.5; both get the same value.
            brake_wear_em["pm10"] = brake_wear_kg
            brake_wear_em["pm25"] = brake_wear_kg

    # Running movement-total emission. queue_em, stop_em, and brake_wear_em
    # all fold into the total just as tx_em does; the segment-level
    # placement happens in distribute.py Path B (tx_em length-distributed,
    # queue/stop at last segment, brake_wear at idx == 0 of arrival route).
    em = {p: tx_em[p] + queue_em[p] + stop_em[p] + brake_wear_em[p] for p in POLLUTANTS}
    # Compatibility: a few downstream readers refer to tx_fuel as the
    # idle-mode fuel burn for the whole movement. Keep that semantic so
    # the legacy return key tx_fuel_kg is the same.
    tx_fuel = nat_fuel + queue_fuel + stop_fuel

    # ---- Spatial setup ----
    # Multi-runway: pick the runway this movement uses, keyed by the
    # designator integer parsed from mov["runway"]. For a single-
    # runway study ctx["runways"] still has every designator from the
    # one runway as a key, so this lookup works for both cases.
    runway = ctx["runways"][mov["runway_direction"]]
    is_dep = mov["departure_arrival"] == "D"

    # ---- Trajectory ----
    # Load profile first so we know the rollout length for arrival origin shift.
    traj = mv.get_trajectory(conn, mov["profile_id"])
    if not traj:
        return None
    is_custom = traj[0][6] == "CUSTOM"

    # Trajectory origin and walk azimuth.
    #
    #   DEPARTURE: origin = active threshold (brake-release point).
    #              Walk azimuth = motion direction (from active toward opp).
    #              All profile x are non-negative.
    #
    #   ARRIVAL:   origin = taxi-route runway-exit point. The ANP profile's
    #              local origin (x=0, y=0) is placed at the exit. Profile
    #              points with x>0 (rollout) are walked in the motion
    #              direction; points with x<0 (descent) are walked in the
    #              approach direction. project_anp handles the signed-x
    #              dispatch internally.
    #              Walk azimuth = motion direction = (approach_azimuth + 180).
    #
    #              Fallback: if the taxi route does not intersect the
    #              runway centreline (exit_3857 is None), the active
    #              threshold is used as the origin instead. This matches
    #              the plugin's observed behaviour against the canonical test study (the 50
    #              of 922 arrivals with no recoverable exit) and at
    #              training_v3 (all 8 arrivals have a recoverable exit).
    #
    # NOTE on the earlier rollout-shift logic. A previous revision walked
    # the exit point back along the approach direction by `rollout_length`
    # so that the profile's last point (x = +rollout) would land on the
    # exit. That shift was the cause of the systematic -3.5 to -5%
    # arrival deficit at training_v3 across all three methods and of
    # the ~1300 m mis-placement on arrivals at the canonical test study. Per-movement
    # diagnostics (diagnose_rollout_shift.py) show the plugin uses the
    # exit point directly with no shift, matching the CAEP14 reference;
    # the standalone alone applied the shift. The shift has been removed
    # unconditionally.
    #
    # NOTE on the departure anchor. An earlier revision anchored departure
    # trajectories at the runway's active threshold (= brake-release point
    # for ANP profiles). The CAEP14 Python reference and the plugin both
    # anchor departures at the taxi-runway intersection instead. For ANP
    # profiles on training_v3 the two choices produce identical results
    # because no grid clipping is involved (the takeoff roll lies well
    # inside the inventory grid). For CUSTOM (imported / ADS-B) profiles
    # such as mov 11 PHBBA, the imported (x_m, y_m) coordinates were
    # generated relative to a specific taxi-runway intersection, so the
    # anchor choice matters: anchoring at the threshold shifts the entire
    # trajectory by the threshold-to-intersection distance (132 m / 81 m
    # on-ground at EHRD G2), producing a -0.87% offset from the reference.
    # The standalone now uses the same anchor for arrivals and departures
    # (taxi-runway intersection from _intersection_cached) to match.
    exit_3857 = _intersection_cached(ctx, conn, mov["taxi_route"], runway)
    arrival_touchdown_m = None
    arrival_touchdown_source = None
    arrival_exit = None
    rollout_cut_m = 0.0
    departure_lineup_m = None
    stretch = None  # runway taxiing between an ANP arrival's rollout end and its exit

    if is_dep:
        # Departure: anchor at taxi-runway intersection (matches plugin
        # and reference). Fallback to active threshold (= brake-release
        # point) when the taxi route does not intersect the runway.
        if exit_3857 is None:
            intersection_3857 = geo.runway_backup_3857(
                runway, mov["runway_direction"], is_dep
            )
        else:
            intersection_3857 = exit_3857
        if not is_custom and exit_3857 is not None:
            # ANP: brake release at the line-up point, where the route last meets the runway in route order
            # (the centroid of the whole overlap falls mid-runway for a route that backtracks or crosses
            # twice). CUSTOM keeps the importer's point so its offsets round-trip.
            lineup_m = rp.lineup_distance(
                _route_crossings_cached(ctx, conn, mov, runway)
            )
            if lineup_m is not None:
                intersection_3857 = rp.point_at(
                    rp.runway_frame(runway, mov["runway_direction"]), lineup_m
                )
                departure_lineup_m = lineup_m
        az_deg = geo.runway_azimuth_deg(runway, mov["runway_direction"], is_dep)
    else:
        # Arrival: anchor at taxi-runway intersection (post rollout-shift
        # fix). Fallback to active threshold (= touchdown point) when the
        # taxi route does not intersect the runway.
        active_threshold_3857 = geo.runway_threshold_3857(
            runway, mov["runway_direction"]
        )
        # Approach direction azimuth, as returned by runway_azimuth_deg for
        # arrivals (bearing from opp toward active). Motion direction is the
        # reverse.
        approach_az_deg = geo.runway_azimuth_deg(
            runway, mov["runway_direction"], is_dep=False
        )
        az_deg = (approach_az_deg + 180.0) % 360.0  # motion direction

        if is_custom:
            # ADS-B / CUSTOM: offsets were taken from this point by the importer; keep it so positions round-trip.
            intersection_3857 = (
                active_threshold_3857 if exit_3857 is None else exit_3857
            )
        else:
            # ANP: Doc 29 approach profiles have x = 0 at the touchdown and cross the landing threshold at the
            # threshold crossing height. Touchdown = landing threshold + the runway's Touchdown Offset for this
            # direction if set, else the profile's own 50 ft crossing distance. The taxi route no longer moves
            # the profile (it is only where taxiing starts).
            key = (mov["profile_id"], mov["runway_direction"], id(runway))
            cache = ctx.setdefault("touchdown_cache", {})
            if key not in cache:
                frame = rp.runway_frame(runway, mov["runway_direction"])
                d_td, td_src = rp.arrival_touchdown_distance(
                    runway, mov["runway_direction"], traj
                )
                cache[key] = (rp.point_at(frame, d_td), d_td, td_src)
            intersection_3857, arrival_touchdown_m, arrival_touchdown_source = cache[
                key
            ]
            # The aircraft leaves the runway at the route's exit: the rollout ends there when the exit comes
            # first (the rest is not flown; taxiing starts at the exit).
            ex = _arrival_exit(ctx, conn, mov, runway, traj, arrival_touchdown_m)
            if ex is not None:
                arrival_exit = ex
                if ex["x_m"] < traj[-1][1]:
                    rollout_cut_m = traj[-1][1] - ex["x_m"]
                    traj = rp.truncate_after(traj, ex["x_m"])
                elif ex["x_m"] - traj[-1][1] > rp.STRETCH_MIN_M:
                    # Exit past the rollout end: the aircraft rolls on along the runway to the exit. That
                    # stretch is taxiing; it takes its share of the movement's taxi time (queuing shrinks
                    # first), so the total taxi time stays as measured.
                    frame = rp.runway_frame(runway, mov["runway_direction"])
                    s0 = arrival_touchdown_m + traj[-1][1]
                    length = ex["s_m"] - s0
                    stretch = dict(
                        length_m=length,
                        time_unscaled_s=rp.stretch_time_s(length, traj[-1][4]),
                        p1_3857=rp.point_at(frame, s0),
                        p2_3857=rp.point_at(frame, ex["s_m"]),
                    )

    # Arrival runway time = touchdown (A-CDM ALDT: "the time that an aircraft lands on a runway"): the time
    # from block to runway time then contains the landing roll, which the profile already counts. The taxi
    # time is the rest (not below 0). ANP and CUSTOM profiles alike.
    rollout_time_s = 0.0
    block_to_runway_s = taxi_time_s
    if not is_dep and ctx.get("arrival_runway_time_is_touchdown", True):
        rollout_time_s = rp.rollout_duration_s(traj)
    stretch_em = {p: 0.0 for p in POLLUTANTS}
    if stretch is not None or rollout_time_s > 0.0:
        # Re-split the taxi time: route, runway stretch, queue (runway_placement.split_taxi_time).
        block_to_runway_s = taxi_time_s
        taxi_time_s = max(0.0, taxi_time_s - rollout_time_s)
        nat, t_st, que = rp.split_taxi_time(
            taxi_time_s, route_time_s, stretch["time_unscaled_s"] if stretch else 0.0
        )
        natural_taxi_time_s, queuing_time_s = nat, que
        nat_fuel = natural_taxi_time_s * tx_ff_amb * n_eng * mov["taxi_fuel_ratio"]
        queue_fuel = queuing_time_s * tx_ff_amb * n_eng
        tx_em, queue_em = _build_em(nat_fuel), _build_em(queue_fuel)
        st_fuel_in = 0.0
        if stretch is not None:
            stretch["time_s"] = t_st
            # All engines (the aircraft is still on the runway; no taxi fuel ratio, as in the plugin); only
            # the part inside the grid counts, as for profile segments.
            st_fuel = t_st * tx_ff_amb * n_eng
            clipped = geo.clip_segment_2d(
                stretch["p1_3857"], stretch["p2_3857"], ctx["grid_bounds"]
            )
            if clipped is not None:
                full = geo.ground_distance_m(stretch["p1_3857"], stretch["p2_3857"])
                f_in = geo.ground_distance_m(*clipped) / full if full > 0 else 0.0
                st_fuel_in = st_fuel * f_in
                stretch_em = _build_em(st_fuel_in)
            stretch["fuel_kg"] = st_fuel_in
        tx_fuel = nat_fuel + queue_fuel + stop_fuel + st_fuel_in
        em = {
            p: tx_em[p] + queue_em[p] + stop_em[p] + brake_wear_em[p]
            for p in POLLUTANTS
        }

    fuel_by_mode = {"TO": 0.0, "CL": 0.0, "AP": 0.0}
    segs_inc = segs_skip_v = segs_skip_g = segs_part = 0
    # Per-segment records, retained so the Phase A3 spatial
    # distribution layer can apportion each segment's emission across
    # the grid cells its clipped geometry crosses, without recomputing
    # the projection and clipping. Each record is a dict; see the
    # `segments` key in the return value for the field list.
    segments: list[dict] = []

    def _proj(x, y):
        if is_custom:
            return geo.project_custom(
                intersection_3857, ctx["grid_bounds"]["utm_epsg"], x, y
            )
        return geo.project_anp(intersection_3857, az_deg, x, y)

    for i in range(len(traj) - 1):
        # Profile row layout from get_trajectory:
        #   (point, x_m, y_m, z_m, tas_metres, mode, course)
        pt1 = traj[i]
        pt2 = traj[i + 1]
        _, x1, y1, z1, tas1, mode1, _ = pt1
        _, x2, y2, z2, tas2, mode2, _ = pt2
        # Start-point altitude before the clip, for MEEM V1 (the plugin uses
        # the unclipped start point).
        z1_start = z1

        # Vertical clip: match the plugin's apply_height_limits
        # (MovementEmissionCalculator.py lines 1042-1078). Three cases:
        #   both endpoints above ceiling -> skip the segment entirely;
        #   start above, end below       -> start moved to the crossing;
        #   start below, end above       -> end moved to the crossing
        #   (see the crossing-segment block below).
        # The ceiling is max_height_m, the per-movement MixingHeight
        # from tbl_InvMeteo (with vertical_limit fallback). Both the
        # standalone and the plugin read MixingHeight; see the
        # max_height_m fetch above. The added per-segment boundary
        # clipping (the > and < branches below) was missing from the
        # standalone before this patch -- only the "both above" skip
        # was present, so partial-crossing segments were not clamped
        # and their above-ceiling endpoint contributed mass at the wrong
        # iz layer.
        if z1 >= max_height_m - EPS_VERTICAL_M and z2 >= max_height_m - EPS_VERTICAL_M:
            segs_skip_v += 1
            continue
        # Crossing segments: the endpoint above the ceiling is moved along the
        # segment to the crossing (altitude linear along the segment), so only
        # the part below the ceiling counts. Mirrors the plugin's
        # apply_height_limits, which interpolates in EPSG:3857.
        _cross = None
        if z1 > max_height_m > z2:
            _cross = ("start", (max_height_m - z2) / (z1 - z2))
            z1 = max_height_m
        elif z1 < max_height_m < z2:
            _cross = ("end", (max_height_m - z1) / (z2 - z1))
            z2 = max_height_m
        if mode1 not in engine_ei or tas1 + tas2 <= 0:
            continue

        p1 = _proj(x1, y1)
        p2 = _proj(x2, y2)
        if _cross is not None:
            _f = _cross[1]
            if _cross[0] == "start":
                p1 = (p2[0] + _f * (p1[0] - p2[0]), p2[1] + _f * (p1[1] - p2[1]))
            else:
                p2 = (p1[0] + _f * (p2[0] - p1[0]), p1[1] + _f * (p2[1] - p1[1]))
        clipped = geo.clip_segment_2d(p1, p2, ctx["grid_bounds"])
        if clipped is None:
            segs_skip_g += 1
            continue
        if clipped != (p1, p2):
            segs_part += 1
            p1, p2 = clipped

        ground_m = geo.ground_distance_m(p1, p2)
        if ground_m <= 0.0:
            continue
        seg_time = ground_m / ((tas1 + tas2) / 2.0)
        eng = engine_ei[mode1]

        # Per-segment Mach (BFFM2 only; bymode ignores it). The plugin
        # uses the start point's TAS, not the average.
        mach = _segment_mach(tas1, tas2, meteo["T_K"]) if method != "bymode" else 0.0

        if method in ("bymode", "bffm2_anchor"):
            seg_ff_amb = eng["ff"]
        else:  # bffm2_traj
            seg_ff_amb = _bffm2_traj_ff_amb(
                conn,
                mov,
                pt1,
                eng,
                engine_ei,
                meteo,
                mach,
                n_eng,
            )

        seg_fuel = seg_time * seg_ff_amb * n_eng
        # MEEM V1 nvPM above 3000 ft above the aerodrome (pm10 only; fuel
        # unchanged), ISA + delta_t at the segment altitude above MSL, with
        # delta_t from the movement's meteo temperature.
        eng = _meem_v1_segment_ei(
            eng,
            meem,
            mode1,
            z1_start + ctx.get("airport_elevation_m", 0.0),
            tas1,
            is_dep,
            delta_t=_meem_v1.delta_t_from_ground(
                meteo["T_K"] if meteo else None, ctx.get("airport_elevation_m", 0.0)
            ),
            airport_elevation_m=ctx.get("airport_elevation_m", 0.0),
        )
        # Plugin guard ("Bug #22" in MovementEmissionCalculator): under
        # BFFM2, a segment whose start point has neither power nor fuel
        # flow uses the Bymode emission indices (mode anchor). Piston and
        # propeller ANP profiles often carry no power.
        bymode_fallback = False
        if method != "bymode":
            _pw, _ffk = mv.get_trajectory_point_power_ff(
                conn, mov["profile_id"], pt1[0]
            )
            bymode_fallback = _pw is None and _ffk is None
        # Compute this segment's emission into its own dict so the
        # per-segment record can carry it, then fold it into the
        # running movement total. The arithmetic is identical to
        # adding straight into `em`; it is just done in two steps so
        # the segment contribution is observable.
        seg_em = {p: 0.0 for p in POLLUTANTS}
        if method == "bymode":
            _add_em(seg_em, seg_fuel, eng)
            # ICCAIA / CAEP14 v14 NOx ambient correction. Mirrors the
            # plugin's MovementEmissionCalculator._apply_nox_corrections,
            # which is gated by the same `apply_nox_corrections` flag
            # (and the same method != BFFM2 condition; bymode here, by
            # construction). Applies to modes TO and CL only; AP and TX
            # segments pass through unchanged (correction_factor returns
            # 1.0). Multiplies seg_em["nox"] in place.
            if apply_nox_corrections:
                factor = _nox_corr.correction_factor(
                    mode1,
                    temperature_k=meteo["T_K"],
                    pressure_pa=meteo["P_Pa"],
                    relative_humidity=meteo["RH"],
                    airport_elevation_m=ctx.get("airport_elevation_m", 0.0),
                    tow_ratio=mov.get("tow_ratio"),
                )
                if factor != 1.0:
                    seg_em["nox"] *= factor
        elif bymode_fallback:
            _add_em(seg_em, seg_fuel, eng)
        else:
            _bffm2_apply_segment(
                seg_em, seg_ff_amb, seg_fuel, eng, icao_eedb, meteo, mach
            )
        for p in POLLUTANTS:
            em[p] += seg_em[p]
        fuel_by_mode[mode1] = fuel_by_mode.get(mode1, 0.0) + seg_fuel
        segs_inc += 1
        # Retain the per-segment record for the Phase A3 spatial
        # distribution layer. p1, p2 are the clipped EPSG:3857
        # endpoints; z1, z2 are the trajectory altitudes (metres) at
        # the segment's start and end, kept so the in-flight / altitude
        # emission case can be separated from the ground case.
        segments.append(
            {
                "mode": mode1,
                "p1_3857": p1,
                "p2_3857": p2,
                "z1_m": z1,
                "z2_m": z2,
                "ground_m": ground_m,
                "fuel_kg": seg_fuel,
                "em_kg": seg_em,
            }
        )

    if stretch is not None and stretch["fuel_kg"] > 0.0:
        # Runway taxiing segment (mode TX, on the ground). Its emission is part of the taxi emission, so it
        # is added to the total here, like the taxi parts above; it is placed on the runway by distribute.py
        # like any other segment.
        p1, p2 = geo.clip_segment_2d(
            stretch["p1_3857"], stretch["p2_3857"], ctx["grid_bounds"]
        )
        for p in POLLUTANTS:
            em[p] += stretch_em[p]
        segments.append(
            {
                "mode": "TX",
                "p1_3857": p1,
                "p2_3857": p2,
                "z1_m": 0.0,
                "z2_m": 0.0,
                "ground_m": geo.ground_distance_m(p1, p2),
                "fuel_kg": stretch["fuel_kg"],
                "em_kg": stretch_em,
            }
        )

    return {
        "oid": mov["oid"],
        "aircraft": mov["aircraft"],
        "departure_arrival": mov["departure_arrival"],
        "profile_id": mov["profile_id"],
        "n_engines": n_eng,
        "method": method,
        "taxi_time_s": taxi_time_s,
        "arrival_touchdown_m": arrival_touchdown_m,
        "arrival_touchdown_source": arrival_touchdown_source,
        "arrival_exit": arrival_exit,
        "rollout_cut_m": rollout_cut_m,
        "runway_stretch_m": stretch["length_m"] if stretch else 0.0,
        "runway_stretch_time_s": stretch["time_s"] if stretch else 0.0,
        "rollout_time_s": rollout_time_s,
        "departure_lineup_m": departure_lineup_m,
        "block_to_runway_time_s": block_to_runway_s,
        "natural_taxi_time_s": natural_taxi_time_s,
        "queuing_time_s": queuing_time_s,
        "stop_and_go_time_s": stop_and_go_time_s,
        "tx_fuel_kg": tx_fuel,
        "brake_wear_pm10_kg": brake_wear_kg,
        "traj_fuel_by_mode_kg": fuel_by_mode,
        "segments_included": segs_inc,
        "segments_skipped_vertical": segs_skip_v,
        "segments_skipped_grid": segs_skip_g,
        "segments_partially_clipped": segs_part,
        # Per-segment records for the Phase A3 spatial distribution
        # layer: one dict per included segment, carrying the clipped
        # EPSG:3857 endpoints, the trajectory altitudes, the ground
        # length, the fuel burn, and the per-pollutant emission. The
        # sum of `em_kg` over this list plus `tx_em_kg` plus
        # `queue_em_kg` plus `stop_em_kg` equals `total_em_kg`. Empty
        # for movements with no included segments.
        "segments": segments,
        # Taxi emissions are split four ways so the spatial layer can
        # match the plugin's per-segment placement:
        #   tx_em_kg       -- natural-time portion, distributed along the
        #                     route by segment length. Engine-only (NO
        #                     brake-wear; that lives in brake_wear_em_kg).
        #   queue_em_kg    -- queuing-time portion (excess of total taxi
        #                     time over natural taxi time), placed entirely
        #                     at the LAST segment in the taxi route.
        #   stop_em_kg     -- AVERAGE_DURATION_OF_STOP_AND_GOS_IN_S *
        #                     number_of_stop_and_gos seconds of extra
        #                     idle, also at the LAST segment.
        #   brake_wear_em_kg -- arrivals only, MTOW > 18632 kg, placed
        #                     at the FIRST segment (idx == 0) of the
        #                     arrival taxi route. Only pm10 and pm25 are
        #                     non-zero (matches the plugin's add_value
        #                     loop over PM10/PM1/PM2; standalone has no
        #                     PM1, so pm10 and pm25 mirror).
        "tx_em_kg": tx_em,
        "queue_em_kg": queue_em,
        "stop_em_kg": stop_em,
        "brake_wear_em_kg": brake_wear_em,
        "total_em_kg": em,
    }


def _route_crossings_cached(ctx: dict, conn, mov: dict, runway: dict) -> list:
    """The movement's taxi route crossings with its runway, in route order (runway_placement.route_crossings)."""
    cache = ctx.setdefault("crossings_cache", {})
    key = (mov["taxi_route"], mov["runway_direction"], id(runway))
    if key not in cache:
        parts = (
            rp.route_parts_from_study(conn, mov["taxi_route"])
            if mov.get("taxi_route")
            else None
        )
        frame = rp.runway_frame(runway, mov["runway_direction"])
        cache[key] = (
            rp.route_crossings(frame, runway["geom_3857"], parts) if parts else []
        )
    return cache[key]


def _arrival_exit(ctx: dict, conn, mov: dict, runway: dict, traj, touchdown_m: float):
    """Runway exit of an ANP arrival (runway_placement.select_exit over the route's crossings), or None."""
    return rp.select_exit(
        _route_crossings_cached(ctx, conn, mov, runway), touchdown_m, traj
    )


def _intersection_cached(
    ctx: dict, conn, route_name: str, runway: dict
) -> Optional[tuple]:
    """Lazily resolve and cache a route's runway/taxi intersection.

    The intersection point depends on the taxi route AND the runway.
    Multi-runway support: the cache key is (route_name, id(runway))
    so two movements on the same taxi route but different runways
    do not share an intersection.  For single-runway studies this is
    a no-op change.

    The intersection geometry uses ALL segments of the taxi route as a
    MultiLineString.  This matches the plugin's
    `get_intersection_point_runway_and_taxi_route` which unionises the
    QgsGeometry of every taxi-route segment before intersecting with
    the buffered runway centreline.  The previous standalone path used
    `get_taxi_route_linestring` which applies `linemerge(...)` and then
    keeps only the first chain when the segments form multiple
    disjoint groups.  For 7 arrival routes (F2, F3, F4, F4A,
    F5A, F9, AC) the first chain is a gate-end stub and the
    runway-crossing segment sits in a different chain — making
    standalone fall back to the active threshold while the plugin
    successfully finds the exit and applies Option A.  Aligning the
    geometry here removes that 39-movement divergence.
    """
    cache = ctx.setdefault("intersection_cache", {})
    key = (route_name, id(runway))
    if key not in cache:
        # Load every segment of the route, in sequence order.
        row = conn.execute(
            "SELECT sequence FROM user_taxiroute_taxiways WHERE route_name=?",
            (route_name,),
        ).fetchone()
        if not row:
            cache[key] = None
        else:
            from shapely.geometry import MultiLineString

            from openalaqs_standalone.geometry import spatialite_blob_to_shapely

            parts = []
            for name in row[0].split(","):
                sub = conn.execute(
                    "SELECT geometry FROM shapes_taxiways WHERE taxiway_id=?",
                    (name.strip(),),
                ).fetchone()
                if sub and sub[0]:
                    g = spatialite_blob_to_shapely(sub[0])
                    if g is not None:
                        parts.append(g)
            if not parts:
                cache[key] = None
            else:
                taxi_geom = parts[0] if len(parts) == 1 else MultiLineString(parts)
                cache[key] = geo.runway_taxi_intersection_3857(
                    runway["geom_3857"], taxi_geom
                )
    return cache[key]
