import shutil
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Optional

import pandas as pd
import pytest


def get_data_path(subfolder: Optional[str] = "") -> Path:
    """
    Returns the path of the "data" dir for tests.
    If subfolder is given, the returned path includes the subfolder.
    """
    return Path(__file__).parent / "data" / subfolder


def get_copy_path(file_path: Path) -> Path:
    """
    Returns a path to a copied version of the file. The file should exist.
    """
    dst_path = get_tmp_path(file_path.name)
    shutil.copyfile(str(file_path), str(dst_path))
    return dst_path


def get_tmp_path(file_name: str) -> Path:
    # Get a unique non-existent path (up to milliseconds)
    return Path(gettempdir()) / (
        datetime.strptime(str(datetime.now()), "%Y-%m-%d %H:%M:%S.%f").strftime(
            "%Y%m%d_%H%M%S%f"
        )
        + "_"
        + file_name
    )


def get_vector_layer_path(relative_path: str, layer_name: Optional[str]) -> Path:
    """
    Returns the complete path to a (copied) layer source.
    The given relative_path should be relative to the data path.
    If layer_name is provided, a 'layername' param is added to the path,
    which is useful fo some layer sources like GeoPackage.
    """
    base_source_path = get_copy_path(get_data_path() / relative_path)
    return (
        Path(str(base_source_path) + f"|layername={layer_name}")
        if layer_name
        else base_source_path
    )


def compare_text_files(
    expected_file_path: str, obtained_file_path: str, rel_tol: float = 1e-7
):
    """
    Compare two CSV files, allowing for floating-point tolerance in numeric values.
    """
    df_expected = pd.read_csv(expected_file_path)
    df_obtained = pd.read_csv(obtained_file_path)

    pd.testing.assert_frame_equal(
        df_expected,
        df_obtained,
        check_exact=False,
        rtol=rel_tol,
    )


def aggregate_emissions(emissions_data: dict) -> dict:
    """Aggregate all emissions from the service result into total values by pollutant."""
    totals = {
        "fuel_kg": 0.0,
        "co_kg": 0.0,
        "co2_kg": 0.0,
        "hc_kg": 0.0,
        "nox_kg": 0.0,
        "sox_kg": 0.0,
        "pm10_kg": 0.0,
        "p1_kg": 0.0,
        "p2_kg": 0.0,
        "pm10_organic_kg": 0.0,
        "pm10_prefoa3_kg": 0.0,
        "pm10_nonvol_kg": 0.0,
        "pm10_sul_kg": 0.0,
    }
    for timestamp, period_emissions in emissions_data.items():
        for source, emissions_list in period_emissions:
            for emission in emissions_list:
                emission_kg = emission.transposeToKilograms()
                for key in totals.keys():
                    if emission_kg.hasKey(key):
                        totals[key] += emission_kg.getObject(key)
    return totals


def load_expected_totals_from_csv(csv_path: str) -> dict:
    """Load expected emission totals from a CSV file, summing all rows."""
    df = pd.read_csv(csv_path)
    pollutant_columns = [
        "co_kg",
        "co2_kg",
        "hc_kg",
        "nox_kg",
        "sox_kg",
        "pm10_kg",
        "p1_kg",
        "p2_kg",
        "pm10_organic_kg",
        "pm10_prefoa3_kg",
        "pm10_nonvol_kg",
        "pm10_sul_kg",
    ]
    return {
        col: df[col].sum() if col in df.columns else 0.0 for col in pollutant_columns
    }


def load_expected_from_csv_single_row(csv_path: str, row_index: int = 0) -> dict:
    """Load expected emission values from a specific row in a CSV file."""
    df = pd.read_csv(csv_path)
    pollutant_columns = [
        "co_kg",
        "co2_kg",
        "hc_kg",
        "nox_kg",
        "sox_kg",
        "pm10_kg",
        "p1_kg",
        "p2_kg",
        "pm10_organic_kg",
        "pm10_prefoa3_kg",
        "pm10_nonvol_kg",
        "pm10_sul_kg",
    ]
    return {
        col: df.iloc[row_index][col] if col in df.columns else 0.0
        for col in pollutant_columns
    }


def compare_emissions_with_expected(
    calculated, expected, rel_tol=1e-6, pollutants=None
):
    if pollutants is None:
        pollutants = ["co_kg", "co2_kg", "hc_kg", "nox_kg", "sox_kg", "pm10_kg"]
    for pollutant in pollutants:
        calc_val = calculated.get(pollutant, 0.0)
        exp_val = expected.get(pollutant, 0.0)
        assert calc_val == pytest.approx(
            exp_val, rel=rel_tol
        ), f"{pollutant} mismatch: calculated {calc_val}, expected {exp_val}"
