import csv
from pathlib import Path

import pandas as pd
from pyproj import CRS, Transformer

from open_alaqs.core.alaqs import get_runways
from open_alaqs.core.alaqsdblite import (
    ProjectDatabase,
    get_closest_runway_endpoint,
    get_max_profile_oid,
    get_runway_closest_endpoint,
    import_ads_b_data,
)
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Runway import RunwayStore
from open_alaqs.core.interfaces.Taxiway import TaxiwayRoutesStore
from open_alaqs.core.tools import spatial

logger = get_logger(__name__)


def validate_adsb_file(path: str) -> tuple[bool, str]:
    """
    Checks whether an ADS-B CSV file is valid or not.

    Args:
        path (str): Path of the ADS-B CSV file.

    Returns:
        Tuple with a boolean validation result and a string with an explanatory message.
    """
    mandatory_fields = [
        "flight_id",
        "latitude",
        "longitude",
        "altitude",
        "tas",
    ]
    optional_exclusive_fields = ["thrust", "fuel_flow"]

    # 0. Check file
    if not Path(path).is_file():
        return False, "The given file path does not correspond to a file!"

    if not Path(path).exists():
        return False, "CSV file does not exist!"

    # 0.1 Check that there are runways in the study setup
    if not get_runways():
        return (
            False,
            "To import ADS-B data, at least one runway should exist in the study!",
        )

    # 1. Check mandatory fields in header
    header = ""
    try:
        with open(path, "r") as file:
            reader = csv.reader(file)
            header = next(reader)
    except Exception as e:
        return False, f"Error reading the CSV file. Details: {e}"

    missing_fields = [field for field in mandatory_fields if field not in header]
    if missing_fields:
        return False, f"The following fields are missing in the CSV: {missing_fields}"

    # 2. Check not null values in mandatory fields
    try:
        df = pd.read_csv(path)
    except Exception as e:
        return False, f"Error reading the CSV file. Details: {e}"

    missing_values = {
        field: df[field].isnull().sum()
        for field in mandatory_fields
        if df[field].isnull().any()
    }
    if missing_values:
        return False, "The following mandatory fields have NULL values: " + ", ".join(
            [f"'{k}' ({v})" for k, v in missing_values.items()]
        )

    # 3. Check thrust and fuel flow values
    no_thrust_no_fuel_flow_count = (
        df[optional_exclusive_fields].isnull().all(axis=1).sum()
    )
    if no_thrust_no_fuel_flow_count > 0:
        return (
            False,
            f"Invalid data: rows with no 'thrust' nor 'fuel flow' values: {no_thrust_no_fuel_flow_count}",
        )

    return True, "The ADS-B data are valid!"


def import_adsb_file(csv_path: str, inventory_path: str) -> tuple[bool, str]:
    """
    Process a valid ADS-B CSV file, converts it to the ANP profiles format,
    and saves it into the Emissions Inventory database.

    Args:
        csv_path (str): Path of the ADS-B CSV file.
        inventory_path (str): Path of the Emissions Inventory database.

    Returns:
        Tuple with a boolean import result and a string with a display message.
    """
    # 1. Pre-process data
    try:
        adsb_data = pd.read_csv(csv_path)
    except Exception as e:
        return False, f"Error reading the CSV file. Details: {e}"

    # Process each unique flight
    id_column = "flight_id"
    anp_profiles = []
    max_profile_oid = get_max_profile_oid()
    flight_count = 0  # For logging purposes

    for flight_id in adsb_data[id_column].unique():
        flight_data = adsb_data[adsb_data[id_column] == flight_id].copy()

        # 1.1. Determine arrival/departure
        is_arrival = (
            flight_data.at[flight_data.index[0], "altitude"]
            > flight_data.at[flight_data.index[-1], "altitude"]
        )

        # 1.2. Convert from geographic coordinates to planar (relative) ones
        # 1.2.1 Pick a reference point on the runway

        _runway_id = (
            flight_data.at[flight_data.index[0], "runway"]
            if "runway" in flight_data.columns
            else ""
        )
        _taxi_route_id = (
            flight_data.at[flight_data.index[0], "taxi_route"]
            if "taxi_route" in flight_data.columns
            else ""
        )
        db_path = ProjectDatabase().path
        runway_obj = RunwayStore(db_path).getObject(_runway_id) if _runway_id else None
        taxi_route_obj = (
            TaxiwayRoutesStore(db_path).getObject(_taxi_route_id)
            if _taxi_route_id
            else None
        )

        # 1.2.1.1 Get the reference point depending on the provided information
        # For closest point analysis, get a point from the ADS-B track
        track_lat, track_lon = (
            flight_data[["latitude", "longitude"]].iloc[-1]
            if is_arrival
            else flight_data[["latitude", "longitude"]].iloc[0]
        )

        if runway_obj:
            runway_name = runway_obj.getName()
            if taxi_route_obj:
                intersection = spatial.get_intersection_point_runway_and_taxi_route(
                    runway_obj, taxi_route_obj
                )
                if intersection.isEmpty():
                    logger.warning(
                        f"Ignoring ADS-B trajectory, since runway ({runway_name}) and taxi route ({taxi_route_obj.getName()}) do not intersect!"
                    )
                    continue
                else:
                    tr = spatial.create_coordinate_transform(3857, 4326)
                    intersection_wgs84 = tr.transform(intersection)
                    runway_lon, runway_lat = (
                        intersection_wgs84.x(),
                        intersection_wgs84.y(),
                    )
                    logger.info(
                        "Using runway and taxi_route intersection as reference runway point for importing ADS-B data."
                    )
            else:
                runway_lon, runway_lat = get_runway_closest_endpoint(
                    runway_name, track_lon, track_lat
                )
                logger.info(
                    "Using runway column for reference runway point calculation for importing ADS-B data."
                )
        else:
            # No runway nor taxi route given, so get the closest runway's endpoint
            runway_name, runway_lon, runway_lat = get_closest_runway_endpoint(
                track_lon, track_lat
            )
            logger.info(
                "Using closest runway endpoint calculation as reference runway point for importing ADS-B data."
            )

        runway_alt = 0

        # 1.2.1.2 Apply geographic_to_relative_df_proj with the appropriate runway reference
        flight_data_x_y_z = _geographic_to_relative_df(
            flight_data,
            runway_lon,
            runway_lat,
            runway_alt,
        )

        logger.info(
            f"ADS-B coordinate conversion: Profile {flight_id} ({runway_name}) - Total points: {len(flight_data_x_y_z)}, "
            f"X: [{flight_data_x_y_z['x_m'].min():.1f}, {flight_data_x_y_z['x_m'].max():.1f}] m, "
            f"Y: [{flight_data_x_y_z['y_m'].min():.1f}, {flight_data_x_y_z['y_m'].max():.1f}] m, "
            f"Z: [{flight_data_x_y_z['z_m'].min():.1f}, {flight_data_x_y_z['z_m'].max():.1f}] m"
        )

        # 1.3. Extract mode
        # Process each point in the trajectory (in order from dataframe)
        # Reset point counter for each new profile_id
        for point_counter, (idx, row) in enumerate(
            flight_data_x_y_z.iterrows(), start=1
        ):
            # Use existing normalized coordinates from dataframe
            x_m = row.get("x_m", 0.0)
            y_m = row.get("y_m", 0.0)
            z_m = row.get("z_m", 0.0)

            # Convert TAS from knots to m/s if tas_kt exists, otherwise use tas_metres if available
            if "tas" in row and pd.notna(row["tas"]):
                tas_metres = row["tas"] * 0.514444
            else:
                tas_metres = None

            # Determine mode based on arrival/departure and altitude
            if is_arrival:
                # Approaching: set mode to AP
                mode = "AP"
            else:
                # Departing: check altitude
                z_m = row.get("z_m", 0.0)
                if z_m == 0:
                    mode = "TO"  # Take-off
                else:
                    mode = "CL"  # Climb

            # 2. Prepare data in ANP format
            anp_row = [
                len(anp_profiles) + max_profile_oid + 1,  # "oid"
                flight_id,  # "profile_id"
                "A" if is_arrival else "D",  # "arrival_departure"
                1,  # Default stage  # "stage"
                point_counter,  # "point"
                0.0,  # Default, can be populated if available  "weight_kgs"
                x_m,
                y_m,
                z_m,
                tas_metres,  # "tas_metres"
                row.get("thrust", ""),  # "power"
                row.get("fuel_flow", ""),  # "fuel_flow_kgm"
                mode,  # "mode"
                "CUSTOM",  # "course"
            ]
            anp_profiles.append(anp_row)

        flight_count += 1

    # 3. Import data to Inventory DB
    result_import = import_ads_b_data(anp_profiles, inventory_path)

    if result_import:
        return True, f"ADS-B successfully imported! ({flight_count} profile(s))"
    else:
        return False, "ADS-B could not be imported into the database!"


def _geographic_to_relative_df(
    df: pd.DataFrame, start_lon: float, start_lat: float, start_alt: float
) -> pd.DataFrame:
    """
    Convert geographic coordinates to relative Cartesian coordinates
    using a projected CRS in meters.

    Args:
        df: DataFrame with columns ['longitude', 'latitude', 'altitude']
        start_lon: reference longitude (deg)
        start_lat: reference latitude (deg)
        start_alt: reference altitude (m)

    Returns:
        Copied input DataFrame with extra columns ['x_m', 'y_m', 'z_m']
    """
    result_df = df.copy()

    # WGS84 geographic CRS
    crs_geo = CRS.from_epsg(4326)

    # Choose UTM zone based on reference point
    utm_zone = int((start_lon + 180) // 6) + 1
    hemisphere = "north" if start_lat >= 0 else "south"
    crs_proj = CRS.from_dict(
        {
            "proj": "utm",
            "zone": utm_zone,
            "south": hemisphere == "south",
            "ellps": "WGS84",
            "units": "m",
        }
    )

    transformer = Transformer.from_crs(crs_geo, crs_proj, always_xy=True)

    # Project reference point
    x0, y0 = transformer.transform(start_lon, start_lat)

    # Project all points
    x, y = transformer.transform(
        result_df["longitude"].values, result_df["latitude"].values
    )

    # Relative coordinates
    result_df["x_m"] = x - x0
    result_df["y_m"] = y - y0
    result_df["z_m"] = round(result_df["altitude"] * 0.3048 - start_alt, 3)

    return result_df
