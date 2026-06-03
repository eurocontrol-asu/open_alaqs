"""Regression: series.dmna timestamps must be shifted so AUSTAL sees
the dispersion starting at yyyy-01-01.01:00:00 in te-convention,
regardless of when the actual emission window falls in the year.

Without this shift, AUSTAL fails at startup with
    *** Request for t2=X, current grid source not valid after Y!
      (TalSrc.GetGridSource.4)
    *** Grid source "01" not available!
      (TalSrc.SrcCrtPtl.14)
because AUSTAL's time bookkeeping reconciles series.dmna te values
against the e-file t1/t2 (which are year-relative offsets like 0.00:00:00
.. 2.03:00:00 for a 51-hour window) and a December series.dmna doesn't
line up with a 51-hour-from-year-start e-file.

The plugin handles this via set_normalized_date() at
open_alaqs/core/modules/AUSTALOutputModule.py:737. This test ensures
austal_prep's write_series applies the same shift by default.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from austal_prep.writers.series_dmna import write_series


def _build_inputs(start_dt: datetime, n_hours: int = 51):
    timestamps = [start_dt + timedelta(hours=h) for h in range(n_hours)]
    meteo = {
        t: dict(
            wind_direction_deg=180,
            wind_speed_ms=3.0,
            obukhov_length_m=99999.0,
            mixing_height_m=600.0,
        )
        for t in timestamps
    }
    rates = np.full((n_hours, 1, 1), 0.5)  # 0.5 g/s for a single (src, poll)
    return timestamps, meteo, rates


def _data_rows(series_dmna_text: str):
    lines = series_dmna_text.splitlines()
    # Body starts after the '*' marker line.
    idx = next(i for i, ln in enumerate(lines) if ln.strip() == "*") + 1
    return [ln for ln in lines[idx:] if ln and not ln.startswith("*")]


def test_default_normalizes_december_window_to_january():
    """December emission window must produce January timestamps in
    series.dmna (yyyy-01-01.01:00:00 ... yyyy-01-03.03:00:00 for 51h)."""
    ts, meteo, rates = _build_inputs(datetime(2025, 12, 1, 6))
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "series.dmna"
        write_series(
            out,
            ts,
            meteo,
            rates,
            ["s1"],
            ["nox"],
            np.array([[True]]),
            grid_writer_mode="time_indexed",
        )
        rows = _data_rows(out.read_text())
    assert len(rows) == 51
    assert rows[0].startswith("2025-01-01.01:00:00")
    assert rows[-1].startswith("2025-01-03.03:00:00")


def test_normalize_off_preserves_real_dates():
    """Escape hatch: when normalize_to_year_start=False, real dates
    are preserved. Useful for downstream non-AUSTAL consumers and for
    debugging."""
    ts, meteo, rates = _build_inputs(datetime(2025, 12, 1, 6))
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "series.dmna"
        write_series(
            out,
            ts,
            meteo,
            rates,
            ["s1"],
            ["nox"],
            np.array([[True]]),
            grid_writer_mode="time_indexed",
            normalize_to_year_start=False,
        )
        rows = _data_rows(out.read_text())
    assert rows[0].startswith("2025-12-01.07:00:00")
    assert rows[-1].startswith("2025-12-03.09:00:00")


def test_january_window_is_unchanged():
    """Already year-aligned windows must produce the same output
    whether the flag is on or off (t_delta=0)."""
    ts, meteo, rates = _build_inputs(datetime(2025, 1, 1, 0))
    with tempfile.TemporaryDirectory() as td:
        on = Path(td) / "on.dmna"
        off = Path(td) / "off.dmna"
        write_series(
            on,
            ts,
            meteo,
            rates,
            ["s1"],
            ["nox"],
            np.array([[True]]),
            grid_writer_mode="time_indexed",
        )
        write_series(
            off,
            ts,
            meteo,
            rates,
            ["s1"],
            ["nox"],
            np.array([[True]]),
            grid_writer_mode="time_indexed",
            normalize_to_year_start=False,
        )
        assert on.read_text() == off.read_text()


def test_emission_rates_keyed_by_real_ts_not_shifted_ts():
    """meteo and emission_rates lookups must remain keyed by the real
    timestamp. The shift is label-only on the te column. Pass a meteo
    dict with REAL keys and verify wind speed/direction round-trip
    correctly into the (normalized) row whose te corresponds to that
    real hour by index position."""
    ts, _, rates = _build_inputs(datetime(2025, 12, 1, 6), n_hours=3)
    meteo = {
        ts[0]: dict(
            wind_direction_deg=100,
            wind_speed_ms=1.0,
            obukhov_length_m=99999.0,
            mixing_height_m=500.0,
        ),
        ts[1]: dict(
            wind_direction_deg=200,
            wind_speed_ms=2.0,
            obukhov_length_m=99999.0,
            mixing_height_m=600.0,
        ),
        ts[2]: dict(
            wind_direction_deg=300,
            wind_speed_ms=3.0,
            obukhov_length_m=99999.0,
            mixing_height_m=700.0,
        ),
    }
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "series.dmna"
        write_series(
            out,
            ts,
            meteo,
            rates,
            ["s1"],
            ["nox"],
            np.array([[True]]),
            grid_writer_mode="time_indexed",
        )
        rows = _data_rows(out.read_text())
    # Row 0: normalized to 2025-01-01.01:00, real ts is 2025-12-01 06:00
    # so wind direction must be 100 (meteo[ts[0]]).
    assert rows[0].startswith("2025-01-01.01:00:00")
    assert "  100" in rows[0]
    assert "  1.0" in rows[0]
    # Row 2: normalized to 2025-01-01.03:00, real ts is 2025-12-01 08:00
    # so wind direction must be 300 (meteo[ts[2]]).
    assert rows[2].startswith("2025-01-01.03:00:00")
    assert "  300" in rows[2]
    assert "  3.0" in rows[2]
