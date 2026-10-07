"""austal.txt declares `hm ?` when series.dmna carries a mixing height.

AUSTAL uses the hm column of series.dmna only when austal.txt has the line
`hm ?`, and only with the option NOSTANDARD. Without the line it silently
applies its own mixing height. Test with AUSTAL 3.3.0: four runs that
differ only in that line and in the hm column. Without the line, an
hourly hm column and a constant 914.4 m one gave identical concentrations
in every hour; with the line they differed in every hour.
"""

from pathlib import Path

import numpy as np
import pytest

from austal_prep.config import AustalStudyConfig, GridSpec
from austal_prep.writers.austal_txt import write_austal_config, writes_mixing_height

GRID = GridSpec(dd=250.0, nx=10, ny=10, x0=-1250.0, y0=-1250.0, sk=[0.0, 3.0, 6.0])


def _write(tmp_path: Path, **kw) -> list:
    study = AustalStudyConfig(title="t", grid=GRID, **kw)
    out = write_austal_config(
        tmp_path / "austal.txt",
        study,
        ["01"],
        ["nox"],
        {"xp": [], "yp": [], "hp": []},
        np.array([[True]]),
    )
    return out.read_text().splitlines()


def _hm_lines(lines):
    return [line for line in lines if line.split("\t")[0] == "hm"]


def test_hm_line_written_with_column_and_nostandard(tmp_path):
    lines = _write(tmp_path, os_options="NOSTANDARD;SCINOTAT;Kmax=1")
    assert [line.split("\t")[:2] for line in _hm_lines(lines)] == [["hm", "?"]]
    # in the meteorology block, before the grid
    assert lines.index(_hm_lines(lines)[0]) < next(
        i for i, line in enumerate(lines) if line.startswith("dd\t")
    )


def test_no_hm_line_without_column(tmp_path):
    lines = _write(
        tmp_path, os_options="NOSTANDARD;SCINOTAT", mixing_height_included=False
    )
    assert _hm_lines(lines) == []


def test_no_hm_line_without_nostandard(tmp_path):
    lines = _write(tmp_path, os_options="SCINOTAT")
    assert _hm_lines(lines) == []


@pytest.mark.parametrize(
    "included, os_options, expected",
    [
        (True, "NOSTANDARD;SCINOTAT;Kmax=1", True),
        (True, "nostandard", True),
        (True, "SCINOTAT", False),
        (False, "NOSTANDARD", False),
        (True, "", False),
    ],
)
def test_writes_mixing_height(included, os_options, expected):
    assert writes_mixing_height(included, os_options) is expected
