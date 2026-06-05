"""
An implementation of the Tier 3 method
From EMEP/EEA air pollutant emission inventory guidebook 2019 – Update Oct. 2020
"""

import numpy as np
import pandas as pd

FUELS = ["petrol", "diesel"]
EURO_STANDARDS = [
    "Conventional",
    "Euro 1",
    "Euro 2",
    "Euro 3",
    "Euro 4",
    "Euro 5",
    "Euro 6 a/b/c",
    "Euro 6 d",
    "Euro 6 d-temp",
    "Euro I",
    "Euro II",
    "Euro III",
    "Euro IV",
    "Euro V",
    "Euro VI A/B/C",
    "Euro VI D/E",
]
# PM10 is intentionally excluded from this list. Per EMEP/EEA Guidebook 2023
# Update 2025, chapter 1.A.3.b.i-iv "Road transport" §1.1 (p.4) and the table
# notes throughout (PM2.5=PM10=TSP), road transport exhaust PM at PM10, PM2.5,
# and TSP are numerically equal: the coarse exhaust fraction (>2.5 µm) is
# treated as negligible. Code paths that need a pm10_ef value use the PM2.5
# emission factor by design (see copert5.py).
#
# The legacy COPERT 5.4.52 dataset shipped in `default_vehicle_ef_copert5.csv`
# contained separate PM10 rows that diverged from PM2.5 due to data-import
# artifacts. As of 2026-06-05: the 639 row pairs where PM10 < PM2.5 (2505
# violating cells) have been fixed via PM10[speed] = max(PM10[speed],
# PM2.5[speed]); see tools/data_integrity_fixes/fix_pm10_at_least_pm25.py
# and documents/DATASET_PROVENANCE.md. The EU28-only PM10 vs EU27 labelling
# mismatch remains open (deferred). Even with PM10 ≥ PM2.5 enforced,
# activating PM10 here would still not produce methodologically distinct
# output since the Guidebook explicitly states they are equal for road
# exhaust; future EF refreshes will use a single "PM Exhaust" label.
POLLUTANTS = ["CH4", "CO", "CO2", "NH3", "NOx", "PM0.1", "PM2.5", "SO2", "VOC"]

VEHICLE_CATEGORIES = {
    "bus": "Buses",
    "motorcycle": "Motorcycles",
    "lcv": "Light Commercial Vehicles",
    "pc": "Passenger Cars",
    "hdt": "Heavy Duty Trucks",
}


def normalize_speed(v: float) -> int:
    """
    Get the closest decimal speed between 10 and 130 km/h.

    :param v: the speed [km/h]
    :return: the decimal speed [km/h]
    """

    # Get the available decimal speeds (min: 10, max: 130)
    vs = np.arange(10, 131, 10)

    # Return the closest decimal speed
    return vs[np.argmin(np.abs(vs - v))]


def ef_query(speed: float, country: str = "EU27"):
    """
    Build the SQL query to get the relevant emission factors.

    :param speed: the average speed of the vehicles [km/h]
    :param country: one of the available EU countries (defaults to 'EU27')
    :return:
    """

    # Get the closest decimal speed
    normalized_speed = normalize_speed(speed)

    # Build the query
    return (
        f"SELECT vehicle_category, fuel, euro_standard, pollutant, `hot-cold-evaporation`, evaporation_split,"
        f" `{normalized_speed}` AS `e[g/km]` FROM default_vehicle_ef_copert5 WHERE country = '{country}'"
    )


def cold_mileage_fractions(
    trip_length: float = 12.4, temperature: float = 15
) -> pd.DataFrame:
    """
    Determine the cold mileage fractions (incl. reduction factors) for each technology.

    :param trip_length: the average trip length [km]
    :param temperature: the ambient temperature [degrees Celsius]
    :return: the cold mileage fraction, beta, and the reduction factors for each pollutant [-]
    """

    # Calculate the default cold mileage fraction
    # Table 3-39: Cold mileage percentage β
    default_beta = (
        0.6474
        - 0.02545 * trip_length
        - (0.00974 - 0.000385 * trip_length) * temperature
    )
    # Method for diesel heavy-duty vehicles and buses
    # Per EMEP/EEA Guidebook 2023 Update 2025, chapter 1.A.3.b.i-iv §3.4 p.77:
    #   beta = 8.25 / ltrip; if beta > 1 then beta = 1
    # i.e. cold-mileage fraction is the warm-up distance (8.25 km) over the
    # trip length, capped at 1.0 for trips shorter than 8.25 km.
    beta_hdt_diesel = min(8.25 / trip_length, 1)

    # Calculate the cold mileage reduction factor
    # Table 3-43: β-reduction factors (bci,k) for Euro 6 petrol vehicles
    bc6pco = 0.1902 - 0.006 * trip_length
    bc6pnox = 0.1573 - 0.005 * trip_length
    bc6pvoc = 0.2072 - 0.0066 * trip_length
    # Table 3-46: β-reduction factors (bci,k) for Euro 6 diesel vehicles
    bc6dco = 0.2022 - 0.0064 * trip_length
    bc6dnox = 0.1719 - 0.0055 * trip_length
    bc6dvoc = 0.2398 - 0.0076 * trip_length

    # Map the fractions to each technology
    # The comments indicate the source of the β-reduction factors
    # Table 3-41: β-reduction factors (bci,k) for Euro 1 to Euro 5 petrol vehicles (relative to Euro 1)
    fractions = pd.DataFrame(
        columns=[
            "vehicle_category",
            "fuel",
            "euro_standard",
            "beta",
            "bcCO",
            "bcNOx",
            "bcVOC",
        ],
        data=[
            ["pc", "petrol", "Conventional", default_beta, 1, 1, 1],  # Equation 10
            ["pc", "petrol", "Euro 1", default_beta, 1, 1, 1],  # Equation 10
            ["pc", "petrol", "Euro 2", default_beta, 0.72, 0.72, 0.56],  # Table 3-41
            ["pc", "petrol", "Euro 3", default_beta, 0.62, 0.32, 0.32],  # Table 3-41
            ["pc", "petrol", "Euro 4", default_beta, 0.18, 0.18, 0.18],  # Table 3-41
            ["pc", "petrol", "Euro 5", default_beta, 0.18, 0.18, 0.18],  # Table 3-41
            [
                "pc",
                "petrol",
                "Euro 6",
                default_beta,
                bc6pco,
                bc6pnox,
                bc6pvoc,
            ],  # Table 3-43
            ["pc", "diesel", "Conventional", default_beta, 1, 1, 1],  # Equation 10
            ["pc", "diesel", "Euro 1", default_beta, 1, 1, 1],  # Equation 10
            ["pc", "diesel", "Euro 2", default_beta, 1, 1, 1],  # Equation 10
            ["pc", "diesel", "Euro 3", default_beta, 1, 1, 1],  # Equation 10
            ["pc", "diesel", "Euro 4", default_beta, 1, 1, 1],  # Equation 10
            ["pc", "diesel", "Euro 5", default_beta, 1, 1, 1],  # Equation 10
            [
                "pc",
                "diesel",
                "Euro 6",
                default_beta,
                bc6dco,
                bc6dnox,
                bc6dvoc,
            ],  # Table 3-46
            ["lcv", "petrol", "Conventional", default_beta, 1, 1, 1],  # Equation 10
            ["lcv", "petrol", "Euro 1", default_beta, 1, 1, 1],  # Equation 10
            ["lcv", "petrol", "Euro 2", default_beta, 0.72, 0.72, 0.56],  # Table 3-41
            ["lcv", "petrol", "Euro 3", default_beta, 0.62, 0.32, 0.32],  # Table 3-41
            ["lcv", "petrol", "Euro 4", default_beta, 0.18, 0.18, 0.18],  # Table 3-41
            ["lcv", "petrol", "Euro 5", default_beta, 0.18, 0.18, 0.18],  # Table 3-41
            [
                "lcv",
                "petrol",
                "Euro 6",
                default_beta,
                bc6pco,
                bc6pnox,
                bc6pvoc,
            ],  # Table 3-43
            ["lcv", "diesel", "Conventional", default_beta, 1, 1, 1],  # Equation 10
            ["lcv", "diesel", "Euro 1", default_beta, 1, 1, 1],  # Equation 10
            ["lcv", "diesel", "Euro 2", default_beta, 1, 1, 1],  # Equation 10
            ["lcv", "diesel", "Euro 3", default_beta, 1, 1, 1],  # Equation 10
            ["lcv", "diesel", "Euro 4", default_beta, 1, 1, 1],  # Equation 10
            ["lcv", "diesel", "Euro 5", default_beta, 1, 1, 1],  # Equation 10
            ["lcv", "diesel", "Euro 6", default_beta, 1, 1, 1],  # Equation 10
            ["hdt", "petrol", "Conventional", 0, 1, 1, 1],  # Only hot emissions
            [
                "hdt",
                "diesel",
                "Conventional",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "hdt",
                "diesel",
                "Euro I",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "hdt",
                "diesel",
                "Euro II",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "hdt",
                "diesel",
                "Euro III",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "hdt",
                "diesel",
                "Euro IV",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "hdt",
                "diesel",
                "Euro V",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "hdt",
                "diesel",
                "Euro VI",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "bus",
                "diesel",
                "Conventional",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "bus",
                "diesel",
                "Euro I",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "bus",
                "diesel",
                "Euro II",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "bus",
                "diesel",
                "Euro III",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "bus",
                "diesel",
                "Euro IV",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "bus",
                "diesel",
                "Euro V",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            [
                "bus",
                "diesel",
                "Euro VI",
                beta_hdt_diesel,
                1,
                1,
                1,
            ],  # Method for diesel heavy-duty vehicles and buses
            ["motorcycle", "petrol", "Conventional", 0, 1, 1, 1],  # Only hot emissions
            ["motorcycle", "petrol", "Euro 1", 0, 1, 1, 1],  # Only hot emissions
            ["motorcycle", "petrol", "Euro 2", 0, 1, 1, 1],  # Only hot emissions
            ["motorcycle", "petrol", "Euro 3", 0, 1, 1, 1],  # Only hot emissions
            ["motorcycle", "petrol", "Euro 4", 0, 1, 1, 1],  # Only hot emissions
            ["motorcycle", "petrol", "Euro 5", 0, 1, 1, 1],  # Only hot emissions
        ],
    )

    # Add Euro 6 variations
    fractions = fractions.merge(
        pd.DataFrame(
            [
                {"euro_standard": "Euro 6", "alternative": "Euro 6 a/b/c"},
                {"euro_standard": "Euro 6", "alternative": "Euro 6 d-temp"},
                {"euro_standard": "Euro 6", "alternative": "Euro 6 d"},
                {"euro_standard": "Euro VI", "alternative": "Euro VI A/B/C"},
                {"euro_standard": "Euro VI", "alternative": "Euro VI D/E"},
            ]
        ),
        how="outer",
        on="euro_standard",
    ).sort_values(["fuel", "vehicle_category"])
    fractions.loc[~fractions["alternative"].isna(), "euro_standard"] = fractions.loc[
        ~fractions["alternative"].isna(), "alternative"
    ]

    return fractions.set_index(["vehicle_category", "fuel", "euro_standard"]).drop(
        columns={"alternative"}
    )


def calculate_emissions(
    fleet: pd.DataFrame, efs: pd.DataFrame, airport_temperature: int | None
) -> pd.DataFrame:
    """
    Calculate the emissions for each technology (a combination of vehicle category, fuel type and euro standard).

    :param fleet: The fleet mix with columns vehicle_category, fuel, euro_standard
    :param efs: The emission factors
    :param airport_temperature: In degrees C, comes from study setup UI
    """

    # Input data validation
    if not fleet["vehicle_category"].isin(VEHICLE_CATEGORIES.keys()).all():
        raise ValueError(
            f"vehicle_category should be one of the values in {VEHICLE_CATEGORIES.keys()}"
        )
    if not fleet["fuel"].isin(FUELS).all():
        raise ValueError(f"fuel should be one of the values in {FUELS}")
    if not fleet["euro_standard"].isin(EURO_STANDARDS).all():
        raise ValueError(
            f"euro_standard should be one of the values in {EURO_STANDARDS}"
        )
    if "N" not in fleet:
        raise ValueError(
            "number of vehicles, N, for each technology should be provided"
        )
    if "M[km]" not in fleet:
        raise ValueError(
            "mileage per vehicle [km], M, for each technology should be provided"
        )

    # Set the technology as index
    fleet = fleet.set_index(["vehicle_category", "fuel", "euro_standard"])

    # Determine hot emission factors
    efs_hot = efs[efs["hot-cold-evaporation"] == "Hot"].pivot(
        index=["vehicle_category", "fuel", "euro_standard"],
        columns="pollutant",
        values="e[g/km]",
    )
    efs_hot = efs_hot[POLLUTANTS]
    efs_hot.columns = [f"e_hot{c}[g/km]" for c in efs_hot.columns]
    fleet = fleet.merge(efs_hot, how="left", left_index=True, right_index=True)

    # Add emissions (g) during stabilised (hot) engine operation
    for p in POLLUTANTS:
        fleet[f"E_hot{p}[g]"] = fleet["N"] * fleet["M[km]"] * fleet[f"e_hot{p}[g/km]"]

    # Determine cold emission factors
    efs_cold = efs[efs["hot-cold-evaporation"] == "Cold"].pivot(
        index=["vehicle_category", "fuel", "euro_standard"],
        columns="pollutant",
        values="e[g/km]",
    )
    efs_cold = efs_cold[POLLUTANTS]
    efs_cold.columns = [f"e_cold{c}[g/km]" for c in efs_cold.columns]
    fleet = fleet.merge(efs_cold, how="left", left_index=True, right_index=True)

    # Determine fraction of cold mileage, beta, and beta reduction factor, bk
    if airport_temperature is not None:
        beta = cold_mileage_fractions(temperature=airport_temperature)
    else:
        beta = cold_mileage_fractions()
    fleet = fleet.merge(beta, how="left", left_index=True, right_index=True)

    # Add emissions (g) during transient thermal engine operation (cold start) if bc is known else assume 0
    for p in POLLUTANTS:
        if f"bc{p}" in fleet:
            fleet[f"E_cold{p}[g]"] = fleet[
                ["beta", f"bc{p}", "N", "M[km]", f"e_cold{p}[g/km]"]
            ].product(axis=1)
        else:
            fleet[f"E_cold{p}[g]"] = 0

    # Calculate the total emissions (g)
    for p in POLLUTANTS:
        fleet[f"E{p}[g]"] = fleet[f"E_hot{p}[g]"] + fleet[f"E_cold{p}[g]"]

    return fleet


def calculate_evaporation(fleet: pd.DataFrame, efs: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the evaporation emissions for each technology (a combination of vehicle category, fuel type and euro
     standard).

    :param fleet: The fleet mix with columns vehicle_category, fuel, euro_standard
    :param efs: The emission factors
    """

    # Input data validation
    if not fleet["vehicle_category"].isin(VEHICLE_CATEGORIES.keys()).all():
        raise ValueError(
            f"vehicle_category should be one of the values in {VEHICLE_CATEGORIES.keys()}"
        )
    if not fleet["fuel"].isin(FUELS).all():
        raise ValueError(f"fuel should be one of the values in {FUELS}")
    if not fleet["euro_standard"].isin(EURO_STANDARDS).all():
        raise ValueError(
            f"euro_standard should be one of the values in {EURO_STANDARDS}"
        )
    if "N" not in fleet:
        raise ValueError(
            "number of vehicles, N, for each technology should be provided"
        )
    if "M[km]" not in fleet:
        raise ValueError(
            "mileage per vehicle [km], M, for each technology should be provided"
        )

    # Set the technology as index
    fleet = fleet.set_index(["vehicle_category", "fuel", "euro_standard"])

    # Determine evaporation emission factors (VOC only).
    #
    # Per EMEP/EEA Guidebook 2023 Update 2025, chapter 1.A.3.b.v "Gasoline
    # evaporation" §4.7 "Gridding" (p.28-29), the three evaporation modes have
    # distinct spatial allocations:
    #
    #   - Diurnal: "occur at any time, their spatial allocation to urban /
    #     rural / highway conditions depends on the time spent by the vehicles
    #     on the different road classes". Parked vehicles dominate.
    #
    #   - Hot soak: "the majority of these emissions occur in the area of
    #     residence of the car owner, as they are associated with short trips".
    #     One event per parking (engine turn-off).
    #
    #   - Running losses: "are proportional to the mileage driven by the
    #     vehicles. Therefore, their allocation to urban areas, rural areas and
    #     highways has to follow the mileage split assumed for the calculation
    #     of exhaust emissions."
    #
    # Parking sources therefore include only Diurnal + Hot soak. Running losses
    # belong on driving (road / movement) sources, but OpenALAQS does not
    # currently expose an evaporation contribution on roadway sources; see
    # "Known limitations and future work" item 2 in
    # documents/AUXILIARY_MATERIAL.md.
    #
    # Known limitation: Hot soak is a per-parking-event quantum, but the
    # downstream scaling in average_evaporation treats all components as
    # time-proportional via idle_time / (24*60). This understates Hot soak
    # for short parkings and overstates it for long ones; correction
    # deferred to a future PR (see AUXILIARY_MATERIAL.md).
    efs_evap = efs[efs["hot-cold-evaporation"] == "Evaporation"].pivot(
        index=["vehicle_category", "fuel", "euro_standard"],
        columns="evaporation_split",
        values="e[g/km]",
    )
    # Parking sums only Diurnal + Hot soak (Guidebook §4.7); Running losses
    # excluded. Defensive subset: include whichever of the two columns are
    # present in the EF data.
    parking_evap_modes = [c for c in ("Diurnal", "Hot soak") if c in efs_evap.columns]
    efs_evap["eVOC[g/day]"] = efs_evap[parking_evap_modes].sum(axis=1)
    fleet = fleet.merge(
        efs_evap[["eVOC[g/day]"]], how="left", left_index=True, right_index=True
    )

    # Calculate the total evaporation emissions (g/day)
    fleet["EVOC[g/day]"] = fleet["N"] * fleet["eVOC[g/day]"]

    return fleet


def average_emission_factors(e: pd.DataFrame) -> pd.Series:
    # Determine the total emissions
    total_emissions = e[[f"E{p}[g]" for p in POLLUTANTS]].sum()

    # Determine the total mileage
    total_mileage = e[["N", "M[km]"]].product(axis=1).sum()

    # Calculate the average emission factors
    emission_factors = pd.Series(
        {f"e{p}[g/km]": total_emissions[f"E{p}[g]"] / total_mileage for p in POLLUTANTS}
    )

    return emission_factors


def average_cold_only_emission_factors(e: pd.DataFrame) -> pd.Series:
    """Return only the cold-start contribution from a calculate_emissions
    DataFrame, fleet-averaged in the same units as average_emission_factors.

    Used by the parking calculator to apply cold-start at trip scale rather
    than at parking-maneuvering scale. The default parking branch in
    roadway_emission_factors() multiplies the combined hot+cold EF by the
    parking maneuvering distance (~0.35 km), which scales cold-start by
    0.35/1000 ~= 0.00035 (effectively zero). Extracting cold-only here lets
    the caller apply it at the post-parking trip length L_trip (default
    12.4 km, COPERT 5).

    For pollutants without a cold contribution (no bc{p} column in the
    input), E_cold{p} is zero and the returned EF is zero.
    """
    cold_cols = [f"E_cold{p}[g]" for p in POLLUTANTS if f"E_cold{p}[g]" in e.columns]
    total_cold = e[cold_cols].sum() if cold_cols else None
    total_mileage = e[["N", "M[km]"]].product(axis=1).sum()

    out = {}
    for p in POLLUTANTS:
        col = f"E_cold{p}[g]"
        if total_cold is not None and col in total_cold:
            out[f"e_cold{p}[g/km]"] = total_cold[col] / total_mileage
        else:
            out[f"e_cold{p}[g/km]"] = 0.0
    return pd.Series(out)


def average_evaporation(e: pd.DataFrame, t_min: float) -> pd.Series:
    # Determine the total emissions for t_min
    total_evaporation = e["EVOC[g/day]"].sum() / (24 * 60) * t_min

    # Determine the total number of vehicles
    total_vehicles = e["N"].sum()

    # Calculate the average evaporation
    emission_factors = pd.Series({"eVOC[g/vh]": total_evaporation / total_vehicles})

    return emission_factors
