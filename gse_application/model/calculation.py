# model/calculation.py

from typing import Dict, List

from .types import GSE, EmissionFactor, Movement


def calculate_emissions(
    movements: List[Movement],
    gse_list: List[GSE],
    emission_factors: List[EmissionFactor],
    pollutants: List[str] = None,
) -> List[Dict]:
    """
    Returns a list of dicts: one per (movement x pollutant), with calculated emissions.
    Formula:
        Emission [g] = power [kW] × load factor [%] × EF [g/kWh] × time [h] × deterioration factor × count
    """
    if pollutants is None:
        pollutants = [
            "CO_g_per_kWh",
            "HC_g_per_kWh",
            "NOx_g_per_kWh",
            "PM_g_per_kWh",
            "SOx_g_per_kWh",
        ]

    # Build index for fast lookup
    gse_by_type = {g.type: g for g in gse_list}
    ef_by_key = {}
    for ef in emission_factors:
        # Example key: (stage, category, power_range)
        ef_by_key[(ef.stage, ef.category, ef.power_range)] = ef

    results = []

    for mv in movements:
        gse = gse_by_type.get(mv.gse_type)
        if gse is None:
            continue  # Or log error

        # Try to find matching emission factor (basic: by stage and fuel)
        ef = None
        for cand in emission_factors:
            if cand.stage == gse.Stage and cand.category == gse.fuel:
                ef = cand
                break
        if ef is None:
            continue  # Or log error

        time_h = (
            mv.time / 60 if mv.time > 1 else mv.time
        )  # If in minutes, convert to hours if needed

        for pol in pollutants:
            ef_value = getattr(ef, pol, 0)
            emission = (
                gse.power
                * gse.load
                * ef_value
                * time_h
                * gse.deterioration_factor
                * mv.count
            )
            results.append(
                {
                    "gate_type": mv.gate_type,
                    "aircraft_group": mv.aircraft_group,
                    "gse_type": mv.gse_type,
                    "pollutant": pol.replace("_g_per_kWh", ""),
                    "emission_g": emission,
                }
            )
    return results
