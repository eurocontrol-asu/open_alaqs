import shutil
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Optional

import pandas as pd


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
