"""
FOCA 2015 helicopter LTO emissions methodology (reference layer).

Pure formulas, tabulated values, operational profiles, category-classification
logic, and airframe MTOM fallback data from:

    Rindlisbacher T., Chabbey L., "Guidance on the Determination of
    Helicopter Emissions", Swiss Federal Office of Civil Aviation,
    Edition 2, December 2015. Ref: COO.2207.111.2.2015750.

No I/O, no QGIS, no database. Orchestration over these primitives
(compute_mode_emissions, compute_lto) lives in foca_heli_utils.

Known FOCA 2015 PDF inconsistencies (resolved here):
  1. Piston fuel-flow leading coefficient: body text says 19e-12,
     Appendix E plot renders 1.9e-12. We use 1.9e-12 (verified at SHP=300).
  2. Appendix C twin-heavy power settings: MODEL column shows legacy
     2009-era values (7%/75%/35%); Table 4 (2015 update) prescribes
     6%/66%/32%. We use Table 4.
  3. Appendix C PM column is 3-4x below section 3.2's PM formula prediction.
     The formula matches Appendix B and Appendix F plot exactly. We use
     the formula.

SHP parameter convention:
    max_shp   maximum shaft horse power of the engine. Used only to
              select the turboshaft fuel-flow polynomial (breakpoints
              at 600 SHP and 1000 SHP).
    mode_shp  shaft horse power at the operating power setting
              (max_shp * power_fraction). Plugged into every fuel-flow
              and EI formula.

1 SHP = 0.7457 kW. FOCA fits are in HP.
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Category enum and operational profiles
# ---------------------------------------------------------------------------


class HelicopterCategory(str, Enum):
    """FOCA 2015 helicopter categories. Drives profile, formula, and CO2 factor selection."""

    PISTON = "PISTON"
    SINGLE_TURBOSHAFT = "SINGLE_TURBOSHAFT"
    TWIN_TURBOSHAFT_LIGHT = "TWIN_TURBOSHAFT_LIGHT"
    TWIN_TURBOSHAFT_HEAVY = "TWIN_TURBOSHAFT_HEAVY"


@dataclass(frozen=True)
class OperationalProfile:
    """Times in mode (minutes per full LTO) and power fractions for one
    helicopter category. Source: FOCA 2015 Tables 1 to 4.

    Power fractions are dimensionless (0..1) of max SHP per engine.
    """

    gi_time_min: float
    to_time_min: float
    ap_time_min: float
    gi_power: float
    to_power: float
    ap_power: float
    mean_power: float


PROFILES: dict[HelicopterCategory, OperationalProfile] = {
    HelicopterCategory.PISTON: OperationalProfile(
        gi_time_min=5.0,
        to_time_min=4.0,
        ap_time_min=5.5,
        gi_power=0.20,
        to_power=0.95,
        ap_power=0.60,
        mean_power=0.90,
    ),
    HelicopterCategory.SINGLE_TURBOSHAFT: OperationalProfile(
        gi_time_min=5.0,
        to_time_min=3.0,
        ap_time_min=5.5,
        gi_power=0.13,
        to_power=0.87,
        ap_power=0.46,
        mean_power=0.80,
    ),
    HelicopterCategory.TWIN_TURBOSHAFT_LIGHT: OperationalProfile(
        gi_time_min=5.0,
        to_time_min=3.0,
        ap_time_min=5.5,
        gi_power=0.07,
        to_power=0.78,
        ap_power=0.38,
        mean_power=0.65,
    ),
    HelicopterCategory.TWIN_TURBOSHAFT_HEAVY: OperationalProfile(
        gi_time_min=5.0,
        to_time_min=3.0,
        ap_time_min=5.5,
        gi_power=0.06,
        to_power=0.66,
        ap_power=0.32,
        mean_power=0.62,
    ),
}


# GI split between departure and arrival halves (FOCA 2015 Appendix A).
GI_DEPARTURE_FRACTION = 0.8
GI_ARRIVAL_FRACTION = 0.2

# Twin-turboshaft classification threshold (FOCA 2015 section 2.4).
TWIN_MTOM_THRESHOLD_KG = 3400.0

# CO2 emission factors (kg CO2 per kg fuel).
CO2_FACTOR_AVGAS = 3.10  # piston (AvGas)
CO2_FACTOR_JET = 3.16  # turboshaft (Jet-A)


# ---------------------------------------------------------------------------
# Piston engines (FOCA 2015 section 3.1)
# ---------------------------------------------------------------------------


def piston_fuel_flow_kg_s(mode_shp: float) -> float:
    """Piston fuel flow (kg/s). FOCA 2015 section 3.1, Appendix E polynomial:

    FF = 1.9e-12*S^4 - 1.0e-9*S^3 + 2.6e-7*S^2 + 4.0e-5*S + 0.006
    """
    s = float(mode_shp)
    return 1.9e-12 * s**4 - 1.0e-9 * s**3 + 2.6e-7 * s**2 + 4.0e-5 * s + 0.006


# Piston EIs are tabulated per power setting (FOCA Tables 5, 6, 7).
_PISTON_NOX_BY_POWER = {
    0.20: 1.0,  # GI
    0.95: 1.0,  # TO
    0.60: 4.0,  # AP
    0.90: 2.0,  # mean / cruise
}

_PISTON_PM_BY_POWER = {
    0.20: 0.05,
    0.95: 0.10,
    0.60: 0.04,
    0.90: 0.07,
}

_PISTON_MEAN_PARTICLE_SIZE_NM = {
    0.20: 18.9,
    0.60: 29.2,
    0.95: 40.3,
    0.90: 39.3,
}


def piston_ei_nox_g_kg(power_fraction: float) -> float:
    """Piston EI NOx (g/kg). FOCA 2015 Table 5. Power must be tabulated."""
    return _lookup_or_raise(_PISTON_NOX_BY_POWER, power_fraction, "piston NOx")


def piston_ei_hc_g_kg(mode_shp: float) -> float:
    """Piston EI HC (g/kg). FOCA 2015 section 3.1: 80 * SHP^-0.35."""
    return 80.0 * (float(mode_shp) ** -0.35)


def piston_ei_co_g_kg(mode_shp: float) -> float:
    """Piston EI CO (g/kg). FOCA 2015 section 3.1: constant 1000 across power settings."""
    _ = mode_shp  # signature symmetry with turboshaft equivalent
    return 1000.0


def piston_ei_pm_g_kg(power_fraction: float) -> float:
    """Piston EI PM non-volatile mass (g/kg). FOCA 2015 Table 6."""
    return _lookup_or_raise(_PISTON_PM_BY_POWER, power_fraction, "piston PM")


def piston_mean_particle_size_nm(power_fraction: float) -> float:
    """Piston mean nvPM particle size (nm). FOCA 2015 Table 7."""
    return _lookup_or_raise(
        _PISTON_MEAN_PARTICLE_SIZE_NM,
        power_fraction,
        "piston particle size",
    )


# ---------------------------------------------------------------------------
# Turboshaft engines (FOCA 2015 section 3.2)
# ---------------------------------------------------------------------------


def turboshaft_fuel_flow_kg_s(max_shp: float, mode_shp: float) -> float:
    """Turboshaft fuel flow (kg/s).

    Polynomial selected by MAX SHP, then evaluated at MODE SHP.
    Breakpoints (FOCA 2015 section 3.2): <=600, 601..1000, >1000.
    """
    if max_shp > 1000.0:
        return _turboshaft_ff_above_1000(mode_shp)
    if max_shp > 600.0:
        return _turboshaft_ff_600_to_1000(mode_shp)
    return _turboshaft_ff_up_to_600(mode_shp)


def _turboshaft_ff_above_1000(s: float) -> float:
    s = float(s)
    return (
        4.0539e-18 * s**5
        - 3.16298e-14 * s**4
        + 9.2087e-11 * s**3
        - 1.2156e-7 * s**2
        + 1.1476e-4 * s
        + 0.01256
    )


def _turboshaft_ff_600_to_1000(s: float) -> float:
    s = float(s)
    return (
        3.3158e-16 * s**5
        - 1.0175e-12 * s**4
        + 1.1627e-9 * s**3
        - 5.9528e-7 * s**2
        + 1.8168e-4 * s
        + 0.0062945
    )


def _turboshaft_ff_up_to_600(s: float) -> float:
    s = float(s)
    return (
        2.197e-15 * s**5
        - 4.4441e-12 * s**4
        + 3.4208e-9 * s**3
        - 1.2138e-6 * s**2
        + 2.414e-4 * s
        + 0.004583
    )


def turboshaft_ei_nox_g_kg(mode_shp: float) -> float:
    """Turboshaft EI NOx (g/kg). FOCA 2015 section 3.2: 0.2113 * SHP^0.5677."""
    return 0.2113 * (float(mode_shp) ** 0.5677)


def turboshaft_ei_hc_g_kg(mode_shp: float) -> float:
    """Turboshaft EI HC (g/kg). FOCA 2015 section 3.2: 3819 * SHP^-1.0801."""
    return 3819.0 * (float(mode_shp) ** -1.0801)


def turboshaft_ei_co_g_kg(mode_shp: float) -> float:
    """Turboshaft EI CO (g/kg). FOCA 2015 section 3.2: 5660 * SHP^-1.11."""
    return 5660.0 * (float(mode_shp) ** -1.11)


def turboshaft_ei_pm_nvol_g_kg(mode_shp: float) -> float:
    """Turboshaft EI PM non-volatile mass (g/kg). FOCA 2015 section 3.2:

    EI_PM = -4.8e-8 * SHP^2 + 2.3664e-4 * SHP + 0.1056
    """
    s = float(mode_shp)
    return -4.8e-8 * s**2 + 2.3664e-4 * s + 0.1056


# Turboshaft particle size lookup (FOCA 2015 Table 8), keyed by category
# and power setting.
_TURBOSHAFT_PARTICLE_SIZE_NM = {
    HelicopterCategory.SINGLE_TURBOSHAFT: {
        0.13: 19.1,
        0.46: 24.2,
        0.87: 38.5,
        0.80: 36.5,
    },
    HelicopterCategory.TWIN_TURBOSHAFT_LIGHT: {
        0.07: 20.0,
        0.38: 21.8,
        0.78: 35.8,
        0.65: 31.1,
    },
    HelicopterCategory.TWIN_TURBOSHAFT_HEAVY: {
        0.06: 20.2,
        0.32: 20.4,
        0.66: 31.5,
        0.62: 30.0,
    },
}


def turboshaft_mean_particle_size_nm(
    category: HelicopterCategory,
    power_fraction: float,
) -> float:
    """Turboshaft mean nvPM particle size (nm). FOCA 2015 Table 8."""
    if category not in _TURBOSHAFT_PARTICLE_SIZE_NM:
        raise ValueError(f"Unknown turboshaft category: {category!r}")
    return _lookup_or_raise(
        _TURBOSHAFT_PARTICLE_SIZE_NM[category],
        power_fraction,
        f"{category.value} particle size",
    )


# ---------------------------------------------------------------------------
# PM number (both engine types)
# ---------------------------------------------------------------------------

_PM_LOGNORMAL_FACTOR = math.exp(4.5 * 1.8**2)


def pm_number_per_kg(ei_pm_g_kg: float, mean_particle_size_nm: float) -> float:
    """PM number per kg fuel. FOCA 2015 sections 3.1 and 3.2:

    PM# = EI_PM / ((pi/6) * D^3 * exp(4.5 * 1.8^2))
    """
    d = float(mean_particle_size_nm)
    if d <= 0:
        return 0.0
    volume_term = (math.pi / 6.0) * (d**3) * _PM_LOGNORMAL_FACTOR
    return float(ei_pm_g_kg) / volume_term


# ---------------------------------------------------------------------------
# Category derivation from engine + airframe attributes
# ---------------------------------------------------------------------------


def derive_category(
    engine_type: str,
    number_of_engines: int,
    mtom_kg: Optional[float],
) -> HelicopterCategory:
    """Resolve a HelicopterCategory from engine_type + n_engines + MTOM.

    Used at data-definition time when category is not explicit. Twin
    turboshaft requires MTOM (FOCA 2015 section 2.4 threshold: 3400 kg).

    Raises ValueError if engine_type is unrecognized, if n_engines is
    invalid, or if MTOM is missing for a twin turboshaft row.
    """
    et = (engine_type or "").upper()
    if et == "PISTON":
        return HelicopterCategory.PISTON
    if et != "TURBOSHAFT":
        raise ValueError(f"Unknown engine_type: {engine_type!r}")

    if number_of_engines == 1:
        return HelicopterCategory.SINGLE_TURBOSHAFT
    if number_of_engines >= 2:
        if mtom_kg is None:
            raise ValueError(
                "Cannot classify twin turboshaft helicopter without MTOM "
                f"(threshold {TWIN_MTOM_THRESHOLD_KG} kg).",
            )
        if mtom_kg <= TWIN_MTOM_THRESHOLD_KG:
            return HelicopterCategory.TWIN_TURBOSHAFT_LIGHT
        return HelicopterCategory.TWIN_TURBOSHAFT_HEAVY

    raise ValueError(f"Invalid number_of_engines: {number_of_engines!r}")


# ---------------------------------------------------------------------------
# Airframe MTOM fallback lookup
# ---------------------------------------------------------------------------
#
# Engine-name -> (mtom_kg, representative_airframe, source) mapping used to
# classify twin-turboshaft helicopters when default_aircraft.mtow is missing.
# Primary MTOM source at runtime is default_aircraft.mtow; this dict is a
# last-resort fallback covering 36 twin-turboshaft engine variants plus two
# single-turboshaft and two piston entries for completeness.
#
# Keys are uppercase, whitespace-collapsed, matching the engine_name spellings
# in the FOCA 2015 helicopter engine catalog (default_helicopter_engines).
# Citations on each entry are verified against authoritative sources
# (manufacturer data sheets, EASA TCDS, SKYbrary, Wikipedia airframe specs).


@dataclass(frozen=True)
class _AirframeMTOMEntry:
    mtom_kg: float
    representative_airframe: str
    source: str


def _normalize_engine_name(name: str) -> str:
    """Uppercase + collapse internal whitespace. Used for case/space-insensitive lookup."""
    return " ".join((name or "").upper().split())


def _e(mtom_kg: float, airframe: str, source: str) -> _AirframeMTOMEntry:
    """Shorthand constructor for the table below."""
    return _AirframeMTOMEntry(mtom_kg, airframe, source)


_AIRFRAME_MTOM_FALLBACK: dict[str, _AirframeMTOMEntry] = {
    # --- Turbomeca/Safran Arriel 1 series (twin variants) ---
    _normalize_engine_name("ARRIEL 1A1"): _e(
        3400.0,
        "SA365C1 Dauphin 2",
        "Wikipedia AS365 Dauphin: SA365C with Arriel 1A1, 3400 kg MTOW; "
        "EASA TCDS E.073 confirms Arriel 1A1 for twin-engine use",
    ),
    _normalize_engine_name("ARRIEL 1A2"): _e(
        3400.0,
        "SA365C2 Dauphin 2",
        "Wikipedia AS365 Dauphin: SA365C2 with Arriel 1A2; same airframe "
        "family as SA365C1 (3400 kg)",
    ),
    _normalize_engine_name("ARRIEL 1C"): _e(
        3850.0,
        "SA365N Dauphin 2",
        "Wikipedia AS365 Dauphin: SA365N (initial) with 660 shp Arriel 1C, "
        "MTOW 3850 kg (later raised to 4000 kg)",
    ),
    _normalize_engine_name("ARRIEL 1C1"): _e(
        4100.0,
        "AS365N1 Dauphin 2",
        "Wikipedia AS365 Dauphin: AS365N1 with 705 shp Arriel 1C1, MTOW 4100 kg",
    ),
    _normalize_engine_name("ARRIEL 1D1"): _e(
        2600.0,
        "AS355N Twin Squirrel",
        "Arriel 1D1 at 712 SHP in twin config goes on AS355N Ecureuil 2 / "
        "Twin Squirrel (airframe CSV: AS-355 = 2600 kg). Note: also used as "
        "single on AS350B2 at 732 SHP (different row in CSV)",
    ),
    _normalize_engine_name("ARRIEL 1E2"): _e(
        3585.0,
        "MBB-BK 117 C1 / EC145",
        "FAA AD 2009-12-51 and StandardAero: Arriel 1E2 on Eurocopter "
        "Deutschland MBB-BK117-C1. BK117-C1/C2 MTOW 3350-3585 kg",
    ),
    _normalize_engine_name("ARRIEL1K1"): _e(
        2720.0,
        "Agusta A109K2",
        "TAR 15/21B/3 Aviation.govt.nz: Arriel 1K1 is used on Agusta A109K2; "
        "A109K2 MTOW 2720 kg. Note: no space in CSV spelling.",
    ),
    # --- Turbomeca/Safran Arriel 2 series ---
    _normalize_engine_name("ARRIEL 2C"): _e(
        4300.0,
        "AS365 N3 Dauphin 2",
        "Wikipedia AS365 Dauphin: AS365 N3 with 851 shp Arriel 2C, MTOW 4300 kg",
    ),
    _normalize_engine_name("ARRIEL 2C1"): _e(
        4800.0,
        "EC155 B",
        "Globalmilitary.net EC155 B: Arriel 2C1, MTOW 4800 kg "
        "(Dauphin N3 family derivative)",
    ),
    _normalize_engine_name("ARRIEL 2C2"): _e(
        4950.0,
        "EC155 B1 / HH-65C",
        "Wikipedia EC155: B1 with Arriel 2C2, MTOW 4950 kg. Also HH-65C "
        "(Arriel 2C2-CG) at 4300 kg; we use the civilian EC155 B1 value",
    ),
    _normalize_engine_name("ARRIEL 2S1"): _e(
        5307.0,
        "Sikorsky S-76C+",
        "Wikipedia S-76: S-76C+ with Arriel 2S1 + FADEC, MTOW 5307 kg",
    ),
    # --- Turbomeca/Safran Arrius series ---
    _normalize_engine_name("ARRIUS 1A"): _e(
        2540.0,
        "AS355 F Ecureuil 2 / EC135 early prototype",
        "EASA TCDS E.080: Arrius 1/1A1 for twin-engines helicopters. "
        "Arrius 1A was used on early EC355 (AS355 F2) derivatives; "
        "AS355 MTOW ~2540 kg",
    ),
    _normalize_engine_name("ARRIUS 2B1"): _e(
        2720.0,
        "EC135 T1",
        "Wikipedia EC135: T1 with 435 kW (583 shp) Arrius 2B1, initial MTOW "
        "2630 kg, later 2720 kg",
    ),
    _normalize_engine_name("ARRIUS 2B2"): _e(
        2910.0,
        "EC135 T2 / T2+",
        "Wikipedia/Skybrary EC135: T2 and T2+ with Arrius 2B2, MTOW 2910-2950 kg",
    ),
    _normalize_engine_name("ARRIUS 2K"): _e(
        2850.0,
        "Agusta A109 Power / AW109 Power",
        "Safran: Arrius 2K2 drives the AW109 Power. AW109 Power MTOW 2850 kg",
    ),
    # --- Pratt & Whitney PW200 series ---
    _normalize_engine_name("PW206A"): _e(
        2850.0,
        "Agusta A109 Power (early)",
        "P&W PW200 page: PW206A for Agusta A109. A109 Power MTOW 2850 kg",
    ),
    _normalize_engine_name("PW206C"): _e(
        2850.0,
        "Agusta A109 E Power",
        "P&W PW200 page: PW206C for Leonardo A109E Power. Confirmed by FOCA "
        "2015 Appendix B validation (A109E, PW206C, 2850 kg MTOW)",
    ),
    _normalize_engine_name("PW207C"): _e(
        3175.0,
        "Leonardo A109 Grand / AW109 Nexus",
        "P&W PW200 page: PW207C for Leonardo A109 Grand and AW109 Nexus. "
        "A109 Grand MTOW 3175 kg",
    ),
    # --- Pratt & Whitney PT6 series ---
    _normalize_engine_name("PT6B-36A"): _e(
        5307.0,
        "Sikorsky S-76B",
        "Wikipedia S-76: S-76B with PT6B-36A or PT6B-36B, MTOW 5307 kg",
    ),
    _normalize_engine_name("PT6C-67C"): _e(
        6400.0,
        "AgustaWestland AW139",
        "Wikipedia/SKYbrary AW139: two PT6C-67C, MTOW 6400 kg (original) "
        "or 6800/7000 kg (uprated). We use 6400 kg as the baseline",
    ),
    _normalize_engine_name("PT6T-3"): _e(
        5080.0,
        "Bell 212 Twin Huey",
        "Wikipedia/SKYbrary Bell 212: PT6T-3 Twin-Pac (two power sections, "
        "combined 1800 shp), MTOW 5080 kg. Note: the heli CSV lists PT6T-3 "
        "with n_engines=2 treating each power section as one engine",
    ),
    # --- Allison/Rolls-Royce DDA 250 series (twin variants on Bo 105 family) ---
    _normalize_engine_name("DDA250-C20"): _e(
        2300.0,
        "MBB Bo 105 C (initial)",
        "Wikipedia Bo 105: Bo 105C with Allison 250-C20, MTOW ~2300 kg "
        "(later raised to 2400 kg)",
    ),
    _normalize_engine_name("DDA250-C20B"): _e(
        2500.0,
        "MBB Bo 105 CB / CBS",
        "Wikipedia/SKYbrary Bo 105: Bo 105CB/CBS with 420 shp Allison "
        "250-C20B, MTOW 2500 kg",
    ),
    _normalize_engine_name("DDA250-C20F"): _e(
        2500.0,
        "MBB Bo 105 CBS",
        "Bo 105 variant; DDA250-C20F is a minor subvariant on Bo 105 family. "
        "MTOW 2500 kg",
    ),
    _normalize_engine_name("DDA250-C20R"): _e(
        2500.0,
        "MBB Bo 105 LS A1 (Canada)",
        "Bo 105 variant with C20R variant of Allison 250. MTOW 2500 kg "
        "(LS A1); later LS A3 Superlifter was 2850 kg",
    ),
    _normalize_engine_name("DDA250-C20R/1"): _e(
        2600.0,
        "MBB Bo 105 LS A3",
        "Wikipedia Bo 105: LS A3 (1986) with DDA250-C20R variants, MTOW 2600 kg",
    ),
    _normalize_engine_name("DDA250-C30S"): _e(
        5307.0,
        "Sikorsky S-76A (original)",
        "Wikipedia S-76: Original S-76A used Allison 250-C30 engines; "
        "DDA250-C30S is the 650-shp twin subvariant. S-76 MTOW 5307 kg",
    ),
    _normalize_engine_name("DDA250-C40B"): _e(
        2835.0,
        "MD Explorer 900 (early)",
        "DDA 250-C40B at 715 SHP used in MD Explorer 900 early variants "
        "before switchover to PW207E. MD 900 MTOW 2835 kg",
    ),
    # --- Honeywell/Lycoming LTS101 series ---
    _normalize_engine_name("LTS101-750B.1"): _e(
        4000.0,
        "Aerospatiale HH-65A Dolphin",
        "Wikipedia HH-65 Dolphin: 734 shp LTS101-750B-2 twin; original "
        "HH-65A MTOW 4000 kg (8900 lb)",
    ),
    _normalize_engine_name("LTS101-750C.1"): _e(
        3350.0,
        "MBB-BK 117 A3/A4",
        "BK-117 B2 with LTS101-750B.1: 3350 kg MTOW (generalequipment.info "
        "BK-117 specifications)",
    ),
    # --- Turbomeca MAKILA series ---
    _normalize_engine_name("MAKILA 1A1"): _e(
        8600.0,
        "Eurocopter AS332L1 Super Puma",
        "Eurocopter Technical Data Brochure 2006: AS332L1 Super Puma with "
        "Makila 1A1 engines, MTOW 8600 kg",
    ),
    # --- General Electric T700 / CT7 series ---
    _normalize_engine_name("T700-GE-700"): _e(
        9185.0,
        "Sikorsky UH-60A Black Hawk",
        "Wikipedia UH-60A: T700-GE-700, 1622 shp each, MTOW 20,250 lb = 9185 kg",
    ),
    _normalize_engine_name("GE CT7-8A"): _e(
        12000.0,
        "Sikorsky S-92",
        "SKYbrary/Wikipedia S-92: two CT7-8A at 2520 shp each, MTOW 12000 kg "
        "(some brochures cite 12,835 kg / 28,300 lb)",
    ),
    # --- Klimov TV series (Soviet) ---
    _normalize_engine_name("TV2-117"): _e(
        12000.0,
        "Mil Mi-8 (original)",
        "National Interest/Mi-8 specs: TV2-117 original engine, Mi-8 MTOW 12000 kg",
    ),
    _normalize_engine_name("TV3-117VMA"): _e(
        13000.0,
        "Mil Mi-17 / Mi-171",
        "SKYbrary/Wikipedia Mi-17: TV3-117VM turboshafts, MTOW 13000 kg",
    ),
    # --- General Electric T64 series ---
    _normalize_engine_name("T 64-GE-7"): _e(
        19050.0,
        "Sikorsky HH-53B / CH-53 Sea Stallion",
        "PaveCave/Wikipedia: T64-GE-7 at 3925 shp was upgrade engine for "
        "HH-53B (twin). CH-53A/D MTOW 19,050-21,000 kg. Note: heli CSV also "
        "shows this engine with n=3 (CH-53D variants); both classify as HEAVY",
    ),
    # --- Single-turboshaft entries (no classification impact; reference only) ---
    _normalize_engine_name("ARRIEL 1B"): _e(
        2100.0,
        "AS350B Squirrel",
        "Wikipedia AS350: AS350B with Arriel 1B, MTOW 2100 kg",
    ),
    _normalize_engine_name("ARRIEL 1D"): _e(
        2100.0,
        "AS350B1 Squirrel",
        "Wikipedia AS350: AS350B1 with Arriel 1D, MTOW 2100 kg",
    ),
    # --- Piston entries (no classification impact; reference only) ---
    _normalize_engine_name("HIO-360"): _e(
        620.0,
        "Robinson R22 / Enstrom F-28",
        "FAA Part 141 training manuals: R22 with HIO-360 (190 hp), MTOW 620 kg",
    ),
    _normalize_engine_name("HIO-540"): _e(
        1089.0,
        "Robinson R44 Astro",
        "Wikipedia R44: HIO-540 (245 hp), MTOW 1089 kg (2400 lb)",
    ),
}


def lookup_mtom_kg(engine_name: str) -> Optional[float]:
    """Return the built-in fallback MTOM (kg) for the given engine name.

    Lookup is case-insensitive and whitespace-collapsed. Returns None if
    the engine is not in the fallback table. Use only when the primary
    source (default_aircraft.mtow) is missing.
    """
    if not engine_name:
        return None
    entry = _AIRFRAME_MTOM_FALLBACK.get(_normalize_engine_name(engine_name))
    return entry.mtom_kg if entry else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _lookup_or_raise(table: dict, key: float, label: str) -> float:
    """Look up a power setting in an EI table, with float tolerance."""
    for k, v in table.items():
        if abs(k - key) < 1e-6:
            return v
    raise KeyError(
        f"No {label} value tabulated for power fraction {key!r}. "
        f"Available: {sorted(table.keys())}",
    )
