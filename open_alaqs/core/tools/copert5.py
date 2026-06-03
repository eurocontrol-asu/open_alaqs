import pandas as pd

from open_alaqs.core import alaqsdblite, alaqsutils
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools.copert5_utils import (
    VEHICLE_CATEGORIES,
    average_cold_only_emission_factors,
    average_emission_factors,
    average_evaporation,
    calculate_emissions,
    calculate_evaporation,
    ef_query,
)

logger = get_logger(__name__)


def catch_errors(f):
    """
    Decorator to catch all errors when executing the function.
    This decorator catches errors and writes them to the log.

    :param f: function to execute
    :return:
    """

    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            alaqsutils.print_error(f.__name__, Exception, e, log=logger)
            raise e

    return wrapper


@catch_errors
def roadway_emission_factors(input_data: dict, study_data: dict) -> dict:
    """
    This function creates a set of averaged emission factors for a roadway (or parking) based on:
    - The roadway fleet year (set using the study setup UI)
    - The roadway country (set using the study setup UI)
    - The roadway geometry

    This function contains the ALAQS roadway method adjusted to support COPERT 5.

    The function works by creating a dict that is fed repeatedly through different roadway vehicle types (passenger
    vehicles, light goods vehicles, heavy goods vehicles) and for different vehicle scenarios (pre-euro, EURO I,
    EURO II, ...). Each time the dict is passed through one of these functions, the emissions totals and vehicle totals
    are incremented based on the defined formulae for that vehicle class/scenario. At the end o the function, all
    emissions are averaged to provide an overall representative EF for the specific road.

    :param input_data: This is a dict of parameters that outline a description of the roadway. This should contain
        airport_temperature         In degrees C, comes from study setup UI
        roadway_method              Currently must be ALAQS
        roadway_fleet_year          A valid year for COPERT Fleet data
        roadway_country             A valid country for COPERT Fleet data
        parking_method              Currently must be ALAQS
    :return emission_factors:
    :rtype: dict
    """

    # Log the input data
    val = "\n\tRoadway emission factors input data:"
    for key, value in sorted(input_data.items()):
        val += f"\n\t\t{key} : {value}"
    logger.info(val)

    # Create a dataframe with the fleet
    fleet = pd.DataFrame(
        [
            {
                "vehicle_category": "pc",
                "fuel": "petrol",
                "euro_standard": input_data["pc_euro_standard"],
                "N": input_data["pc_p_percentage"],
            },
            {
                "vehicle_category": "pc",
                "fuel": "diesel",
                "euro_standard": input_data["pc_euro_standard"],
                "N": input_data["pc_d_percentage"],
            },
            {
                "vehicle_category": "lcv",
                "fuel": "petrol",
                "euro_standard": input_data["lcv_euro_standard"],
                "N": input_data["lcv_p_percentage"],
            },
            {
                "vehicle_category": "lcv",
                "fuel": "diesel",
                "euro_standard": input_data["lcv_euro_standard"],
                "N": input_data["lcv_d_percentage"],
            },
            {
                "vehicle_category": "hdt",
                "fuel": "petrol",
                "euro_standard": input_data["hdt_euro_standard"],
                "N": input_data["hdt_p_percentage"],
            },
            {
                "vehicle_category": "hdt",
                "fuel": "diesel",
                "euro_standard": input_data["hdt_euro_standard"],
                "N": input_data["hdt_d_percentage"],
            },
            {
                "vehicle_category": "motorcycle",
                "fuel": "petrol",
                "euro_standard": input_data["motorcycle_euro_standard"],
                "N": input_data["motorcycle_p_percentage"],
            },
            {
                "vehicle_category": "bus",
                "fuel": "diesel",
                "euro_standard": input_data["bus_euro_standard"],
                "N": input_data["bus_d_percentage"],
            },
        ]
    )
    fleet["M[km]"] = 1000

    # Get the speed
    speed = input_data["speed"]

    # Get the country
    country = study_data["roadway_country"]

    # Fetch the emission factors from the database
    efs = get_emission_factors(speed, country)

    # Calculate the emissions.
    # `airport_temperature` lives on the study setup (see openalaqsdialog.py
    # where it is read from spinBoxAirportTemperature into the study_data
    # dict), NOT on the per-feature parking/roadway form data. Reading it
    # from input_data raises KeyError('airport_temperature') and surfaces in
    # the UI as "Emissions could not be calculated: 'airport_temperature'".
    emissions = calculate_emissions(fleet, efs, study_data["airport_temperature"])

    # Calculate the average emission factors
    emission_factors = average_emission_factors(emissions)

    if input_data["parking"]:

        # Get the idle time [min] and travel distance [m -> km].
        # The UI field "distance" is labelled "Travel Distance [m]"
        # (see ui_parkings.ui); the COPERT 5 emission factors are in
        # g/km; previous code treated the value directly as km, which
        # made every stored *_gm_vh ~1000x too high.
        idle_time = input_data["idle_time"]
        distance = float(input_data["travel_distance"]) / 1000.0

        # Calculate the evaporation
        evaporation = calculate_evaporation(fleet, efs)

        # Calculate the average evaporation per vehicle
        mean_evaporation = average_evaporation(evaporation, idle_time)

        # Default: emit hot+cold at parking_speed × maneuvering_distance.
        # The cold contribution at this scale is ~0.00035 of its true
        # value because parking maneuvering is ~0.35 km vs the M=1000 km
        # used internally by calculate_emissions. To preserve byte-for-byte
        # backward compatibility with existing studies, this is the
        # default behavior.
        co_ef = emission_factors["eCO[g/km]"] * distance
        hc_ef = (
            emission_factors["eVOC[g/km]"] * distance + mean_evaporation["eVOC[g/vh]"]
        )
        nox_ef = emission_factors["eNOx[g/km]"] * distance
        sox_ef = emission_factors["eSO2[g/km]"] * distance
        pm10_ef = emission_factors["ePM2.5[g/km]"] * distance
        p1_ef = emission_factors["ePM0.1[g/km]"] * distance
        p2_ef = emission_factors["ePM2.5[g/km]"] * distance

        # Optional: re-apply cold-start at the post-parking trip scale.
        # Each parking event triggers exactly one cold start; the cold
        # portion of emissions occurs over the first L_trip km of the
        # trip until the engine reaches operating temperature (default
        # 12.4 km per COPERT 5 / EMEP-EEA Guidebook 2019). Scaling cold
        # by parking_distance instead of L_trip understates cold-start
        # NOx by a factor of ~35x for typical parking lots. Gated behind
        # a study-level flag so existing studies keep their current
        # totals; new studies opt in.
        if study_data.get("parking_include_cold_start", False):
            l_trip = study_data.get("parking_cold_trip_length_km", 12.4)
            cold_speed = study_data.get("parking_cold_speed_kmh", 30.0)

            # Subtract the small cold contribution already counted at
            # parking_speed × parking_distance, then add it back at
            # cold_speed × L_trip to avoid double-counting.
            cold_at_parking = average_cold_only_emission_factors(emissions)
            co_ef -= cold_at_parking["e_coldCO[g/km]"] * distance
            hc_ef -= cold_at_parking["e_coldVOC[g/km]"] * distance
            nox_ef -= cold_at_parking["e_coldNOx[g/km]"] * distance

            cold_efs = get_emission_factors(cold_speed, country)
            cold_emissions = calculate_emissions(
                fleet, cold_efs, study_data["airport_temperature"]
            )
            cold_at_trip = average_cold_only_emission_factors(cold_emissions)
            co_ef += cold_at_trip["e_coldCO[g/km]"] * l_trip
            hc_ef += cold_at_trip["e_coldVOC[g/km]"] * l_trip
            nox_ef += cold_at_trip["e_coldNOx[g/km]"] * l_trip

        # Calculate the average emissions per vehicle
        emission_factors_dict = {
            "co_ef": co_ef,
            "hc_ef": hc_ef,
            "nox_ef": nox_ef,
            "sox_ef": sox_ef,
            "pm10_ef": pm10_ef,
            "p1_ef": p1_ef,
            "p2_ef": p2_ef,
        }

        return emission_factors_dict

    # Return the result as dict
    emission_factors_dict = {
        "co_ef": emission_factors["eCO[g/km]"],
        "hc_ef": emission_factors["eVOC[g/km]"],
        "nox_ef": emission_factors["eNOx[g/km]"],
        "sox_ef": emission_factors["eSO2[g/km]"],
        "pm10_ef": emission_factors["ePM2.5[g/km]"],
        "p1_ef": emission_factors["ePM0.1[g/km]"],
        "p2_ef": emission_factors["ePM2.5[g/km]"],
    }

    return emission_factors_dict


def get_emission_factors(speed: float, country: str):
    # Build the SQL query to fetch the emission factors from the database
    sql = ef_query(speed, country)

    # Fetch the emission factors from the database
    ef_data = alaqsdblite.query_string_df(sql)

    # Get the categories
    vc = pd.DataFrame(
        {
            "category_short": VEHICLE_CATEGORIES.keys(),
            "category_long": VEHICLE_CATEGORIES.values(),
        }
    )

    # Change column names
    ef_data["fuel"] = ef_data["fuel"].str.lower()
    ef_data["vehicle_category"] = ef_data.merge(
        vc, how="left", left_on="vehicle_category", right_on="category_long"
    )["category_short"]

    return ef_data
