"""Plugin AUSTAL writer: austal.txt declares `hm ?` when series.dmna has hm.

AUSTAL uses the hm column of series.dmna only with the line `hm ?` in
austal.txt, and only with the option NOSTANDARD; without the line it
silently applies its own mixing height (EHRD test, 6-7 October 2026).
"""

import datetime as dt
import shutil

import pytest
from qgis.testing import start_app

from open_alaqs.core.alaqsdblite import ProjectDatabase
from open_alaqs.core.EmissionCalculatorService import (
    EmissionCalculationConfig,
    EmissionCalculatorService,
)
from tests.utils import get_data_path

start_app()

GRID = {
    "x_cells": 100,
    "y_cells": 100,
    "z_cells": 1,
    "x_resolution": 100,
    "y_resolution": 100,
    "z_resolution": 100,
    "reference_latitude": 51.96,
    "reference_longitude": 4.44,
    "reference_altitude": 0.0,
}


@pytest.fixture(autouse=True)
def _reset():
    yield
    try:
        ProjectDatabase().path = None
    except Exception:
        pass
    try:
        from open_alaqs.core.tools.Singleton import Singleton

        Singleton.reset_all()
    except Exception:
        pass


def _austal_txt(tmp_path, options, mixing_height):
    db = tmp_path / "generic_out.alaqs"
    shutil.copy(get_data_path("generic") / "generic_out.alaqs", db)
    ProjectDatabase().path = str(db)
    out = tmp_path / "austal"
    cfg = EmissionCalculationConfig(
        db_path=str(db),
        start_dt_inclusive=dt.datetime(2020, 1, 1),
        end_dt_inclusive=dt.datetime(2020, 1, 1, 3),
        time_interval=dt.timedelta(hours=1),
        pollutant="NOx",
        method="bymode",
        grid_config=GRID,
    )
    cfg.dispersion_modules_config = {
        "AUSTAL": {
            "is_enabled": True,
            "output_path": str(out),
            "options_string": options,
            "mixing_height_enabled": mixing_height,
        }
    }
    res = EmissionCalculatorService().calculate_emissions(cfg)
    assert res.success, res.error_message
    return (out / "austal.txt").read_text().splitlines(), (out / "series.dmna").read_text()


@pytest.mark.parametrize(
    "options, mixing_height, expect_line",
    [
        ("NOSTANDARD;SCINOTAT;Kmax=1", True, True),
        ("NOSTANDARD;SCINOTAT;Kmax=1", False, False),
        ("SCINOTAT", True, False),
    ],
)
def test_hm_line(tmp_path, options, mixing_height, expect_line):
    lines, series = _austal_txt(tmp_path, options, mixing_height)
    hm = [l.split("\t")[:2] for l in lines if l.split("\t")[0] == "hm"]
    assert hm == ([["hm", "?"]] if expect_line else [])
    assert ('"hm%' in series) is mixing_height
