"""Fuel sulphur: the aircraft SOx emission index, by fuel.

All fuel sulphur leaves the engine as SO2 except the fraction eps that is
converted to sulphate. The CAEP14 calculation sheet (v14) uses FSC and eps
only for the sulphate vPM; SOx (as SO2, SO2/S = 64/32) is written here with
the same parameters, so the sulphur in the two adds up:

    SOx EI = 1000 x FSC x (1 - eps) x 64/32   [g per kg fuel]

Jet fuel (turbofans, turboprops and turboshaft helicopters burning Jet A/A-1,
and their engine tests): FSC 0.068 % and eps 2.4 %, the FOA3 values behind the
stored `pm10_sul` of the Jet Fuel rows of `default_aircraft_engine_ei`
(1000 x 0.00068 x 0.024 x 96/32 = 0.04896 g/kg), so SOx EI = 1.32736 g/kg.

AvGas (piston aircraft and piston helicopters): FSC 0.01 % (100 ppm, the upper
end of measured AvGas sulphur, CRC AV-30-22 2025) and eps 0 (the AvGas rows
carry no sulphate, `pm10_sul` 0), so SOx EI = 0.2 g/kg.

These values replace a missing SOx (`sox_ei` 0 or empty); a value in the
engine table is used as it is. APU and GSE SOx come from their own tables.
"""

JET_FUEL_SULPHUR_CONTENT = 0.00068  # mass fraction (680 ppm), FOA3
JET_SULPHUR_CONVERSION_EFFICIENCY = 0.024  # fraction converted to S(VI), FOA3
AVGAS_SULPHUR_CONTENT = 0.0001  # mass fraction (100 ppm)
AVGAS_SULPHUR_CONVERSION_EFFICIENCY = 0.0


def _sox(fsc: float, eps: float) -> float:
    return 1000.0 * fsc * (1.0 - eps) * 2.0


SOX_EI_JET_G_KG = _sox(JET_FUEL_SULPHUR_CONTENT, JET_SULPHUR_CONVERSION_EFFICIENCY)
SOX_EI_AVGAS_G_KG = _sox(AVGAS_SULPHUR_CONTENT, AVGAS_SULPHUR_CONVERSION_EFFICIENCY)


def is_avgas(fuel_type) -> bool:
    """True for the engine table's AvGas fuel type (any case, spacing)."""
    return str(fuel_type or "").replace(" ", "").lower().startswith("avgas")


def default_sox_ei_g_kg(fuel_type=None) -> float:
    """The fuel's SOx EI (g/kg): AvGas, else jet fuel."""
    return SOX_EI_AVGAS_G_KG if is_avgas(fuel_type) else SOX_EI_JET_G_KG


def sox_ei_g_kg(stored, fuel_type=None) -> float:
    """The stored SOx EI (g/kg), or the fuel's default when it is 0 or empty."""
    try:
        value = float(stored)
    except (TypeError, ValueError):
        return default_sox_ei_g_kg(fuel_type)
    return value if value > 0.0 else default_sox_ei_g_kg(fuel_type)


def helicopter_sox_ei_g_kg(engine_type) -> float:
    """Helicopters (FOCA gives no SOx): AvGas for PISTON engines, else jet fuel."""
    return (
        SOX_EI_AVGAS_G_KG
        if str(engine_type or "").strip().upper() == "PISTON"
        else SOX_EI_JET_G_KG
    )
