"""The plugin re-export writes plain numbers, whatever numeric type the plugin returns.

Under NumPy 2 the plugin can hand back np.float64 values; their repr is
'np.float64(...)', which the readers of the pinned CSVs cannot parse. The
writer converts to float first. QGIS-free: only the CSV writer is exercised.
"""

import csv
import importlib.util
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _tool():
    spec = importlib.util.spec_from_file_location(
        "regenerate_plugin_csvs", TOOLS / "regenerate_plugin_csvs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rows_with_numpy_floats_parse_back(tmp_path):
    tool = _tool()
    kg = {c: np.float64(1.5) for c in tool.COLUMNS}
    kg["nox_kg"] = np.float64(0.123456789012345)
    path = tmp_path / "out.csv"
    tool._write(path, [("2025-12-01T06:00:00", "Movement", "id 1: X", kg)])
    text = path.read_text()
    assert "np.float64" not in text
    row = next(csv.DictReader(open(path)))
    assert float(row["nox_kg"]) == 0.123456789012345
    assert float(row["co2_kg"]) == 1.5
