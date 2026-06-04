"""Regression: every numeric field in the form line of series.dmna and
the per-source grid files must end with a valid AUSTAL type letter
(t, f, d, or e).

Without the trailing type letter, AUSTAL concatenates the format tokens
internally and the resulting parser fails with

    *** Invalid format string!
        (IBJdmn.DmnAnaForm.11)
    *** te%20ltra%5.0ua%5.1lm%7.1hm%7.101.iq%3.0...
    ***               |     ^

because after `%5.0` it reads `u` (from the next field's label) where
it expects a type letter.

The plugin's AUSTAL writer (open_alaqs/core/modules/AUSTALOutputModule.py:2016
and the grid-file form at lines 1457, 1476) emits the tokens with the
'f' suffix; this test pins the standalone writer to the same
behaviour.
"""

import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from austal_prep.config import GridSpec
from austal_prep.spatial import CellWeights
from austal_prep.writers.grid_files import write_grid_legacy
from austal_prep.writers.series_dmna import write_series

# AUSTAL accepts these type letters at the end of a numeric format
# token. 't' is for text (timestamp); 'f' is float; 'd' is integer;
# 'e' is exponential. Anything else (or none at all) is rejected by
# IBJdmn.DmnAnaForm.
_VALID_TYPE_LETTERS = set("tfde")


def _form_tokens(form_line: str):
    """Yield (raw_token, trailing_type_letter) for every quoted token
    on the form line.

    A well-formed AUSTAL form token is `"<label>%<width>(.<prec>)?<modifier>?<type>"`
    where <type> is the trailing letter (the only thing we care about).
    """
    for match in re.finditer(r'"[^"]+"', form_line):
        token = match.group(0)
        inner = token.strip('"')
        last = inner[-1]
        assert last.isalpha(), (
            f"form token {token!r} does not end in a letter; "
            f"AUSTAL cannot determine its type"
        )
        yield token, last


def _build_series_inputs(n_hours: int = 24, n_sources: int = 2):
    """Minimal series.dmna inputs: n_hours, n_sources, single
    pollutant. All sources emit the single pollutant."""
    start = datetime(2025, 1, 1, 1)
    timestamps = [start + timedelta(hours=h) for h in range(n_hours)]
    meteo = {
        t: dict(
            wind_direction_deg=180,
            wind_speed_ms=3.0,
            obukhov_length_m=99999.0,
            mixing_height_m=600.0,
        )
        for t in timestamps
    }
    rates = np.full((n_hours, n_sources, 1), 0.5)
    source_ids = [f"src_{i:02d}" for i in range(n_sources)]
    pollutants = ["nox"]
    emits = np.ones((n_sources, 1), dtype=bool)
    return timestamps, meteo, rates, source_ids, pollutants, emits


def test_series_form_line_every_token_has_type_letter():
    """series.dmna form line: every quoted token must end with a valid
    AUSTAL type letter."""
    ts, meteo, rates, src_ids, polls, emits = _build_series_inputs()
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "series.dmna"
        write_series(
            out,
            timestamps=ts,
            meteo=meteo,
            emission_rates=rates,
            source_ids=src_ids,
            pollutants=polls,
            source_emits_pollutant=emits,
            mixing_height_included=True,
        )
        text = out.read_text()

    form_line = next(ln for ln in text.splitlines() if ln.startswith("form\t"))
    tokens = list(_form_tokens(form_line))
    assert tokens, "no form tokens parsed"

    bad = [t for t, letter in tokens if letter not in _VALID_TYPE_LETTERS]
    assert not bad, (
        f"series.dmna form line has tokens without a valid AUSTAL "
        f"type letter (one of {sorted(_VALID_TYPE_LETTERS)}): {bad}"
    )


def test_series_form_line_specific_types():
    """Pin the exact type letter per field so a future change of
    writer output format doesn't silently break AUSTAL parsing."""
    ts, meteo, rates, src_ids, polls, emits = _build_series_inputs(
        n_hours=8, n_sources=1
    )
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "series.dmna"
        write_series(
            out,
            timestamps=ts,
            meteo=meteo,
            emission_rates=rates,
            source_ids=src_ids,
            pollutants=polls,
            source_emits_pollutant=emits,
            mixing_height_included=True,
        )
        text = out.read_text()

    form_line = next(ln for ln in text.splitlines() if ln.startswith("form\t"))

    # Required tokens (regardless of additional source/pollutant columns)
    required = [
        '"te%20lt"',  # timestamp, text type
        '"ra%5.0f"',  # wind direction, float
        '"ua%5.1f"',  # wind speed, float
        '"lm%7.1f"',  # Obukhov length, float
        '"hm%7.1f"',  # mixing height, float
        '"01.iq%3.0f"',  # per-source grid file index, float
    ]
    for tok in required:
        assert tok in form_line, (
            f"required form token {tok!r} not in series.dmna form line: "
            f"{form_line!r}"
        )


def test_grid_file_form_line_has_type_letter():
    """e0001.dmna (legacy grid file) form line must end with a valid
    AUSTAL type letter."""
    grid = GridSpec(
        dd=250.0,
        nx=10,
        ny=10,
        x0=-1250.0,
        y0=-1250.0,
        sk=[0.0, 3.0, 6.0, 10.0],
    )
    n_hours = 3
    timestamps = [datetime(2025, 1, 1, 1) + timedelta(hours=h) for h in range(n_hours)]
    # One occupied cell, time-invariant weights summing to 1.0.
    weights = CellWeights(
        indices=np.array([[5, 5, 0]], dtype=np.int32),
        weights=np.array([1.0], dtype=np.float64),
        bbox_metres=(0.0, 0.0, grid.dd, grid.dd),
    )

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        n_written = write_grid_legacy(
            out_dir=out_dir,
            source_dir_index=1,
            timestamps=timestamps,
            weights=weights,
            grid=grid,
        )
        assert n_written == n_hours
        e_files = sorted((out_dir / "01").glob("e*.dmna"))
        assert e_files, "no e*.dmna files written"
        text = e_files[0].read_text()

    form_line = next(ln for ln in text.splitlines() if ln.startswith("form\t"))
    tokens = list(_form_tokens(form_line))
    assert tokens, "no form tokens parsed in grid file"

    bad = [t for t, letter in tokens if letter not in _VALID_TYPE_LETTERS]
    assert not bad, (
        f"grid file form line has tokens without a valid AUSTAL "
        f"type letter (one of {sorted(_VALID_TYPE_LETTERS)}): {bad}"
    )

    # Pin the exact expected token. Weights are floats in [0, 1].
    assert (
        '"Eq%5.1f"' in form_line
    ), f"grid file form token 'Eq%5.1f' not in: {form_line!r}"
