import csv
from pathlib import Path
from typing import Optional

import pandas as pd
from pyproj import CRS, Transformer

from open_alaqs.core.alaqs import get_runway_by_direction, get_runways
from open_alaqs.core.alaqsdblite import (
    ProjectDatabase,
    get_closest_runway_endpoint,
    get_max_profile_oid,
    get_runway_closest_endpoint,
    import_ads_b_data,
)
from open_alaqs.core.alaqslogging import get_logger
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

    Required columns and units:
      flight_id        (text identifier, groups rows into a flight)
      latitude         (degrees, WGS84)
      longitude        (degrees, WGS84)
      altitude         (feet)
      tas              (knots, true airspeed)

    At least one of these per row:
      power_setting    (engine power-setting fraction, 0-1, used by BFFM2
                        twin-quadratic-fit. The legacy column name `thrust`
                        is accepted as an alias for back-compat with old
                        files; values are still treated as a fraction --
                        files with raw-Newton values must be converted
                        before import.)
      fuel_flow        (kg/s, aircraft total)

    Optional columns (read if present, ignored otherwise):
      timestamp        (YYYY-MM-DD HH:MM:SS, matches movement.csv format
                        for human readability; not consumed by the plugin
                        -- flight time comes from the movement table's
                        runway_time/block_time matched by profile_id)

    Any other columns in the CSV are silently ignored. Real-world ADS-B
    exports typically include many fields the plugin does not need
    (aircraft_type, registration, squawk, icao24, callsign, weather, etc.);
    these all pass through validation unchanged. This is intentional --
    users should not need to hand-trim their files before import.

    The plugin handles ground taxi emissions via taxiway routes; ADS-B
    rows during ground taxi should NOT be included in this CSV (they
    would be imported as flight-trajectory points at zero altitude).
    """
    mandatory_fields = [
        "flight_id",
        "latitude",
        "longitude",
        "altitude",
        "tas",
    ]
    # power_setting is the new canonical name; thrust is the legacy alias.
    # Either one (or both) may be present. Validation accepts whichever
    # is found and applies range checking only to power_setting (legacy
    # `thrust` skips range validation to avoid breaking old files where
    # the value is a raw Newton number not a fraction; users are warned
    # via deprecation log when the legacy alias is detected).
    POWER_COL_CANONICAL = "power_setting"
    POWER_COL_LEGACY = "thrust"

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
        # Auto-detect separator (GitHub #52)
        from open_alaqs.core.tools.csv_interface import detect_separator

        sep = detect_separator(path)
        with open(path, "r") as file:
            reader = csv.reader(file, delimiter=sep)
            header = next(reader)
    except Exception as e:
        return False, f"Error reading the CSV file. Details: {e}"

    missing_fields = [field for field in mandatory_fields if field not in header]
    if missing_fields:
        return False, f"The following fields are missing in the CSV: {missing_fields}"

    # Confirm at least one power column is present
    power_col = None
    if POWER_COL_CANONICAL in header:
        power_col = POWER_COL_CANONICAL
    elif POWER_COL_LEGACY in header:
        power_col = POWER_COL_LEGACY
        logger.warning(
            "ADS-B CSV uses legacy column name 'thrust'. Rename to "
            "'power_setting' (engine power-setting fraction, 0-1) for "
            "future compatibility. Values are passed through unchanged."
        )

    if power_col is None and "fuel_flow" not in header:
        return (
            False,
            "The CSV must contain at least one of: 'power_setting' or 'fuel_flow'.",
        )

    # 2. Check not null values in mandatory fields
    try:
        df = pd.read_csv(path, sep=sep)
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

    # 3. At least one of power_setting / fuel_flow must be non-null per row
    optional_exclusive_fields = [c for c in (power_col, "fuel_flow") if c in df.columns]
    if not optional_exclusive_fields:
        return (
            False,
            "The CSV must contain at least one of: 'power_setting' or 'fuel_flow'.",
        )
    no_power_no_fuel_flow_count = (
        df[optional_exclusive_fields].isnull().all(axis=1).sum()
    )
    if no_power_no_fuel_flow_count > 0:
        return (
            False,
            f"Invalid data: rows with no '{power_col or 'power_setting'}' "
            f"nor 'fuel_flow' values: {no_power_no_fuel_flow_count}",
        )

    # 4. Range-check power_setting when present under the canonical name.
    # Acceptable range is [0, 1.5]: 0 = engine off, 1 = takeoff thrust,
    # values up to ~1.05 occur briefly during high-power takeoff segments.
    # Anything above 1.5 is almost certainly a unit error (raw Newtons or
    # similar) and is rejected to fail loud rather than silently producing
    # huge BFFM2 fuel flows.
    if power_col == POWER_COL_CANONICAL:
        ps = df[POWER_COL_CANONICAL].dropna()
        if not ps.empty:
            if (ps < 0).any() or (ps > 1.5).any():
                bad = ps[(ps < 0) | (ps > 1.5)]
                return (
                    False,
                    f"power_setting values out of range [0, 1.5]: "
                    f"{len(bad)} rows (sample: {list(bad.head(3))}). "
                    f"power_setting is the engine power-setting fraction "
                    f"used by BFFM2 (typically 0.07 idle .. 1.0 takeoff). "
                    f"Values above 1.5 suggest the column contains raw "
                    f"Newtons or another non-fractional unit; convert "
                    f"before import.",
                )

    return True, "The ADS-B data is valid!"


def import_adsb_file(
    adsb_path: str,
    inventory_path: str,
    movement_path: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Process a valid ADS-B CSV file, converts it to the ANP profiles format,
    and saves it into the Emissions Inventory database.

    Reference-point selection (per flight):
      Tier 1: if Movement CSV provides both runway and taxi_route for this
              flight_id, use the runway/taxi-route intersection (matches the
              calc-side reference used in GeoTransformation.runway_alignment).
      Tier 2: if only runway is provided, use that runway's closest endpoint
              to the ADS-B track's first/last point.
      Tier 3: if no Movement CSV row is found (or movement_path is None),
              use the globally closest runway endpoint.

    Tier 1 round-trips precisely against the calc-side UTM math; tiers 2 and
    3 are best-effort fallbacks and produce trajectories shifted by the
    (intersection - endpoint) offset.

    Args:
        adsb_path (str): Path of the ADS-B CSV file.
        inventory_path (str): Path of the Emissions Inventory database.
        movement_path (str, optional): Path of the Movement CSV file. If not
            provided, tier 3 is used for every flight.

    Returns:
        Tuple with a boolean import result and a string with a display message.
    """
    # 1. Pre-process ADS-B data
    try:
        # Auto-detect separator (GitHub #52)
        from open_alaqs.core.tools.csv_interface import detect_separator

        sep = detect_separator(adsb_path)
        adsb_data = pd.read_csv(adsb_path, sep=sep)
    except Exception as e:
        return False, f"Error reading the ADS-B CSV file. Details: {e}"

    # Optional: read Movement CSV for per-flight runway/taxi_route lookup.
    mdf_triples = None
    if movement_path:
        try:
            mdf = pd.read_csv(movement_path, sep=";")
            mdf_triples = mdf.groupby(["profile_id", "runway", "taxi_route"])
        except Exception as e:
            return False, f"Error reading the Movement CSV file. Details: {e}"

    # Resolve which column holds the engine power-setting fraction.
    # Canonical name is `power_setting`. Legacy `thrust` is accepted with
    # a warning and treated as a fraction (no unit conversion); legacy
    # files that stored raw Newtons in this column would have already
    # failed import-time validation if the column had been named
    # `power_setting`, so this back-compat path only catches files where
    # values were already fractional but the column was misnamed.
    if "power_setting" in adsb_data.columns:
        power_col = "power_setting"
    elif "thrust" in adsb_data.columns:
        power_col = "thrust"
    else:
        power_col = None

    # Process each unique flight
    id_column = "flight_id"
    anp_profiles = []
    max_profile_oid = get_max_profile_oid()

    for flight_id in adsb_data[id_column].unique():
        flight_data = adsb_data[adsb_data[id_column] == flight_id].copy()

        # 1.1. Determine arrival/departure
        is_arrival = (
            flight_data.at[flight_data.index[0], "altitude"]
            > flight_data.at[flight_data.index[-1], "altitude"]
        )

        # 1.2. Pick a reference point on the runway.
        # For closest-point fallback, get an extreme point from the ADS-B track.
        track_lat, track_lon = (
            flight_data[["latitude", "longitude"]].iloc[-1]
            if is_arrival
            else flight_data[["latitude", "longitude"]].iloc[0]
        )

        # Look up runway/taxi_route for this flight in Movement CSV (if present)
        _runway_direction = ""
        _taxi_route_id = ""
        if mdf_triples is not None:
            for triple, _ in mdf_triples:
                if flight_id == triple[0]:
                    _runway_direction = str(triple[1])
                    _taxi_route_id = triple[2]
                    break

        res, runway_obj = (
            get_runway_by_direction(_runway_direction)
            if _runway_direction
            else (False, None)
        )
        db_path = ProjectDatabase().path
        taxi_route_obj = (
            TaxiwayRoutesStore(db_path).getObject(_taxi_route_id)
            if _taxi_route_id
            else None
        )

        if runway_obj:
            runway_name = runway_obj.getName()
            if taxi_route_obj:
                # Tier 1: intersection of runway and taxi route (matches calc-side)
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
                # Tier 2: closest endpoint of the specified runway
                runway_lon, runway_lat = get_runway_closest_endpoint(
                    runway_name, track_lon, track_lat
                )
                logger.info(
                    "Using runway object for reference runway point calculation for importing ADS-B data."
                )
        else:
            # Tier 3: closest endpoint across all runways
            runway_name, runway_lon, runway_lat = get_closest_runway_endpoint(
                track_lon, track_lat
            )
            logger.info(
                "Since runway and taxi_route were not given or found, use closest runway endpoint calculation as reference runway point for importing ADS-B data."
            )

        runway_alt = 0

        # 1.3. Apply geographic_to_relative with the chosen reference
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

        # 1.4. Extract mode + build ANP-format rows
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

            # Determine mode based on arrival/departure and altitude.
            # For departures, z_m <= 0 marks ground-level (or sub-MSL)
            # points as TO; airborne points are CL. The previous check
            # used `z_m == 0` (literal equality), which silently failed
            # at airports below MSL — e.g. Rotterdam (EHRD) at z=-4.57 m
            # never matched, so every ground-roll point became CL.
            if is_arrival:
                mode = "AP"
            else:
                if z_m <= 0:
                    mode = "TO"
                else:
                    mode = "CL"

            # 2. Prepare data in ANP format for default_aircraft_profiles
            # (14-column schema):
            #   oid, profile_id, arrival_departure, stage, point,
            #   weight_kgs, x_m, y_m, z_m, tas_metres, power, fuel_flow_kgm,
            #   mode, course
            anp_row = [
                len(anp_profiles) + max_profile_oid + 1,  # oid
                flight_id,  # profile_id
                "A" if is_arrival else "D",  # arrival_departure
                1,  # stage (default)
                point_counter,  # point
                0.0,  # weight_kgs
                x_m,  # x_m
                y_m,  # y_m
                z_m,  # z_m
                tas_metres,  # tas_metres
                # power_setting fraction (0-1) for BFFM2 twin-quad fit
                (
                    row.get(power_col)
                    if power_col and pd.notna(row.get(power_col))
                    else None
                ),
                (
                    row.get("fuel_flow") if pd.notna(row.get("fuel_flow")) else None
                ),  # fuel_flow_kgm
                mode,  # mode
                "CUSTOM",  # course
            ]
            anp_profiles.append(anp_row)

    # 3. Import data to Inventory DB
    result_import = import_ads_b_data(anp_profiles, inventory_path)

    if result_import:
        return True, "ADS-B successfully imported!"
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
