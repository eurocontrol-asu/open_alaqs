import shutil
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Optional


def get_data_path(subfolder: Optional[str] = "") -> Path:
    """
    Returns the path of the "data" dir for tests.
    If subfolder is given, the returned path includes the subfolder.
    """
    return Path.cwd() / "tests" / "data" / subfolder


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
