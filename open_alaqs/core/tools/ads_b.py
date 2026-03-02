import csv
from pathlib import Path

import pandas as pd
from pyproj import CRS, Transformer

from open_alaqs.core.alaqs import get_runways, import_ads_b_data
from open_alaqs.core.alaqsdblite import get_closest_runway_point, get_max_profile_oid


def validate_adsb_file(path: str) -> tuple[bool, str]:
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

    return True, "The ADS-B data is valid!"


def import_adsb_file(csv_path: str, inventory_path: str) -> tuple[bool, str]:
    # 1. Pre-process data
    try:
        adsb_data = pd.read_csv(csv_path)
    except Exception as e:
        return False, f"Error reading the CSV file. Details: {e}"

    # Process each unique flight
    id_column = "flight_id"
    anp_profiles = []
    max_profile_oid = get_max_profile_oid()

    for flight_id in adsb_data[id_column].unique():
        flight_data = adsb_data[adsb_data[id_column] == flight_id].copy()

        # 1.1. Determine arrival/departure
        is_arrival = (
            flight_data["altitude"][0]
            > flight_data.at[flight_data.index[-1], "altitude"]
        )

        # 1.2. Convert from geographic coordinates to planar (relative) ones
        track_lat, track_lon = (
            flight_data[["latitude", "longitude"]].iloc[-1]
            if is_arrival
            else flight_data[["latitude", "longitude"]].iloc[0]
        )

        runway_name, runway_lat, runway_lon = get_closest_runway_point(
            track_lat, track_lon
        )
        runway_alt = 0

        # Apply geographic_to_relative_df_proj with the appropriate runway reference
        flight_data_x_y_z = _geographic_to_relative_df(
            flight_data,
            runway_lon,
            runway_lat,
            runway_alt,
        )

        print(
            f"Profile {flight_id} ({runway_name}) - Total points: {len(flight_data_x_y_z)}, "
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
            anp_row = {
                "oid": len(anp_profiles) + max_profile_oid + 1,
                "profile_id": flight_id,
                "arrival_departure": "A" if is_arrival else "D",
                "stage": 1,  # Default stage
                "point": point_counter,
                "weight_kgs": 0.0,  # Default, can be populated if available
                "x_m": x_m,
                "y_m": y_m,
                "z_m": z_m,
                "tas_metres": tas_metres,
                "power": row.get("thrust", ""),
                "fuel_flow_kgm": row.get("fuel_flow", ""),
                "mode": mode,
                "course": "CUSTOM",
            }
            anp_profiles.append(anp_row)

    # 3. Import data to Inventory DB
    result_import = import_ads_b_data(anp_profiles, inventory_path)

    if result_import:
        return True, "ADS-B successfully imported!"
    else:
        return False, "ADS-B could not be imported into the database!"


def _geographic_to_relative_df(df, start_lon, start_lat, start_alt):
    """
    Convert geographic coordinates to relative Cartesian coordinates
    using a projected CRS in meters (Option B).

    Args:
        df: DataFrame with columns ['longitude', 'latitude', 'altitude']
        start_lon: reference longitude (deg)
        start_lat: reference latitude (deg)
        start_alt: reference altitude (m)

    Returns:
        DataFrame with columns ['x_m', 'y_m', 'z_m']
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
    result_df["z_m"] = result_df["altitude"] * 0.3048 - start_alt

    return result_df
