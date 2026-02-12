import csv
from pathlib import Path

import pandas as pd


def validate_adsb_file(path: str) -> tuple[bool, str]:
    mandatory_fields = ["flight_id", "latitude", "longitude", "altitude", "tas"]
    optional_exclusive_fields = ["thrust", "fuel_flow"]

    # 0. Check file
    if not Path(path).is_file():
        return False, "The given file path does not correspond to a file!"

    if not Path(path).exists():
        return False, "CSV file does not exist!"

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
    pass
