"""Receptor heights in adapt_receptors.

Until 5.4.2 every receptor was written at z_default (1.5 m) whatever height
the receptor CSV carried; austal_prep writes the z column as each receptor's
hp in austal.txt, so the AUSTAL receptor heights were all 1.5 m.
"""

from __future__ import annotations

import logging

import pandas as pd
import pytest

from openalaqs_standalone import orchestrate as _orchestrate
from openalaqs_standalone.adapt_receptors import adapt_receptors

# Two Rotterdam receptors (WGS84), written in UTM 31N.
ROWS = [
    ("NL01491", 51.93858, 4.43070),
    ("NL01493", 51.92711, 4.46136),
    ("NL01494", 51.91000, 4.48000),
]


def _csv(tmp_path, extra=None, name="r.csv"):
    df = pd.DataFrame(ROWS, columns=["ID", "latitude", "longitude"])
    df["EPSG"] = 4326
    for col, values in (extra or {}).items():
        df[col] = values
    path = tmp_path / name
    df.to_csv(path, index=False)
    return path


def _run(tmp_path, src, **kw):
    out = tmp_path / "out.csv"
    n = adapt_receptors(src, out, target_epsg=32631, **kw)
    df = pd.read_csv(out)
    assert len(df) == n
    return df


def test_no_height_column_uses_default(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        df = _run(tmp_path, _csv(tmp_path))
    assert df["z"].tolist() == [1.5, 1.5, 1.5]
    assert "no height column" in caplog.text


def test_no_height_column_other_default(tmp_path):
    df = _run(tmp_path, _csv(tmp_path), z_default=3.0)
    assert df["z"].tolist() == [3.0, 3.0, 3.0]


@pytest.mark.parametrize("col", ["z", "height", "altitude", "hp", "Height"])
def test_height_column_is_read(tmp_path, col):
    df = _run(tmp_path, _csv(tmp_path, {col: [3.5, 2.0, 4.0]}))
    assert df["z"].tolist() == [3.5, 2.0, 4.0]


def test_empty_height_takes_default_with_warning(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        df = _run(tmp_path, _csv(tmp_path, {"z": [3.5, None, 2.0]}))
    assert df["z"].tolist() == [3.5, 1.5, 2.0]
    assert "1 receptor(s) without a height" in caplog.text


def test_named_height_column(tmp_path):
    src = _csv(tmp_path, {"z": [9.0, 9.0, 9.0], "inlet_m": [2.5, 3.0, 4.0]})
    df = _run(tmp_path, src, z_col="inlet_m")
    assert df["z"].tolist() == [2.5, 3.0, 4.0]


def test_named_height_column_missing(tmp_path):
    with pytest.raises(ValueError, match="Height column 'inlet_m'"):
        _run(tmp_path, _csv(tmp_path), z_col="inlet_m")


def test_height_of_zero_stops(tmp_path):
    with pytest.raises(ValueError, match="must be > 0 m"):
        _run(tmp_path, _csv(tmp_path, {"height": [0.0, 2.0, 3.0]}))


def test_clipped_receptor_drops_its_height(tmp_path):
    full = _run(tmp_path, _csv(tmp_path, {"z": [3.5, 2.0, 4.0]}))
    # Bounds around the first two receptors only.
    xs, ys = full["x"][:2], full["y"][:2]
    bounds = (xs.min() - 10, xs.max() + 10, ys.min() - 10, ys.max() + 10)
    df = _run(tmp_path, _csv(tmp_path, {"z": [3.5, 2.0, 4.0]}), domain_bounds=bounds)
    assert df["name"].tolist() == ["NL01491", "NL01493"]
    assert df["z"].tolist() == [3.5, 2.0]


def test_orchestrate_passes_height_options():
    import inspect

    params = inspect.signature(_orchestrate.orchestrate).parameters
    assert params["receptor_z_col"].default is None
    assert params["receptor_z_default"].default == 1.5
    src = inspect.getsource(_orchestrate)
    for text in (
        "--receptor-z-col",
        "--receptor-z-default",
        "z_col=receptor_z_col",
        "z_default=receptor_z_default",
    ):
        assert text in src
