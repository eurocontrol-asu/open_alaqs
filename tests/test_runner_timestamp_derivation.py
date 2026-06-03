"""Regression for R2: austal_prep.runner._derive_timestamps closes the
internal-gap abort bug while preserving plugin parity on training_v3.

Before this fix, runner.py:118 read:

    timestamps = sorted(emissions_df["timestamp"].drop_duplicates())

When the emissions data had INTERNAL GAPS (an hour with no emission
rows between hours that do), the gap hour was silently dropped from
the timestamp list. AUSTAL then ran fewer hours than the wall-clock
span and aborted at the first uncovered hour with
`Quelle ist nicht definiert nach Stunde H`.

The fix derives the timeline from emissions_df.min()..max() with a
CONTINUOUS hourly cadence (no gap drops). This matches the plugin's
AUSTAL behaviour: both std and plugin size the simulation from the
inventory's actual emission rows, so bit-parity on training_v3
(dense 51-hour data inside a 52-hour configured window) is preserved.

What this test pins:
  1. Dense input -> output bit-identical to pre-fix
     (training_v3 baseline preserved).
  2. Sparse input with internal gaps -> output is a CONTINUOUS hourly
     range from min to max (gaps filled). This is the bug fix.
  3. Helper output is hourly cadence, sorted ascending.

What this test does NOT do:
  - Test extension beyond emissions max to a user-supplied end_dt.
    That mode is deliberately not implemented because it would
    diverge from plugin behaviour. start_dt/end_dt are retained in
    the helper's signature for compatibility but are ignored.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from austal_prep.runner import _derive_timestamps

# ---------------------------------------------------------------------------
# Dense input: pre-fix and post-fix produce identical output (plugin parity)
# ---------------------------------------------------------------------------


def test_dense_continuous_input_passes_through_unchanged():
    """When data already covers every hour in its min..max range,
    the helper's output is bit-identical to what the pre-fix code
    path (sorted unique timestamps) would have produced.
    """
    hourly = pd.date_range("2025-02-01", periods=10, freq="h")
    df = pd.DataFrame({"timestamp": hourly})
    ts = _derive_timestamps(df, None, None)
    # Same as sorted(unique(timestamps))
    assert ts == list(hourly)


def test_dense_input_with_window_arguments_ignored():
    """start_dt/end_dt arguments are accepted but ignored. Output is
    still data-derived. This is the plugin-parity contract.
    """
    hourly = pd.date_range("2025-02-01", periods=10, freq="h")
    df = pd.DataFrame({"timestamp": hourly})
    # Even with a 100-hour window, the timeline stays at 10 hours
    ts = _derive_timestamps(
        df,
        datetime(2025, 1, 25, 0),
        datetime(2025, 2, 5, 0),
    )
    assert len(ts) == 10
    assert ts[0] == pd.Timestamp("2025-02-01 00:00:00")
    assert ts[-1] == pd.Timestamp("2025-02-01 09:00:00")


def test_training_v3_dense_51_hours_unchanged():
    """Plugin parity check: training_v3-like 51 hours of dense data
    produces a 51-hour timeline, NOT a 52-hour one.
    """
    hourly = pd.date_range("2025-12-01 06:00", "2025-12-03 08:00", freq="h")
    assert len(hourly) == 51
    df = pd.DataFrame({"timestamp": hourly})
    # Simulating the runner.py call shape: window extends one hour
    # past the data's last hour (configured end_dt = 09:00 day 3).
    ts = _derive_timestamps(
        df,
        datetime(2025, 12, 1, 6),
        datetime(2025, 12, 3, 9),
    )
    # Helper IGNORES the window; output is 51 hours (data extent),
    # NOT 52 hours (window extent).
    assert len(ts) == 51
    assert ts[0] == pd.Timestamp("2025-12-01 06:00:00")
    assert ts[-1] == pd.Timestamp("2025-12-03 08:00:00")


# ---------------------------------------------------------------------------
# Sparse input with internal gaps: the bug fix
# ---------------------------------------------------------------------------


def test_internal_gap_is_filled():
    """The main bug: emissions at hours 5 and 7 but NOT at hour 6.
    Pre-fix gave [5, 7]; AUSTAL aborts. Post-fix gives [5, 6, 7]
    with hour 6 zero-filled downstream.
    """
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01 05:00:00",
                    "2025-01-01 07:00:00",
                ]
            ),
        }
    )
    ts = _derive_timestamps(df, None, None)
    assert len(ts) == 3
    assert ts == [
        pd.Timestamp("2025-01-01 05:00:00"),
        pd.Timestamp("2025-01-01 06:00:00"),
        pd.Timestamp("2025-01-01 07:00:00"),
    ]


def test_multi_hour_gap_is_filled():
    """Larger gap: emissions at hours 5 and 12 only, with hours 6-11
    missing. Post-fix gives all 8 hours [5, 6, ..., 12].
    """
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01 05:00:00",
                    "2025-01-01 12:00:00",
                ]
            ),
        }
    )
    ts = _derive_timestamps(df, None, None)
    assert len(ts) == 8
    assert ts[0] == pd.Timestamp("2025-01-01 05:00:00")
    assert ts[-1] == pd.Timestamp("2025-01-01 12:00:00")
    # All consecutive
    deltas = {(ts[i + 1] - ts[i]).total_seconds() for i in range(len(ts) - 1)}
    assert deltas == {3600.0}


def test_multiple_internal_gaps_all_filled():
    """Multiple non-adjacent gaps all get filled."""
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01 03:00:00",  # hour 3
                    "2025-01-01 05:00:00",  # hour 5 (gap at 4)
                    "2025-01-01 09:00:00",  # hour 9 (gap at 6, 7, 8)
                    "2025-01-01 10:00:00",  # hour 10
                ]
            ),
        }
    )
    ts = _derive_timestamps(df, None, None)
    # Range 3..10 = 8 hours
    assert len(ts) == 8
    assert ts[0] == pd.Timestamp("2025-01-01 03:00:00")
    assert ts[-1] == pd.Timestamp("2025-01-01 10:00:00")


# ---------------------------------------------------------------------------
# Boundary cases
# ---------------------------------------------------------------------------


def test_single_hour_emission_produces_single_timestamp():
    """One emission hour -> one timestamp."""
    df = pd.DataFrame({"timestamp": pd.to_datetime(["2025-01-01 12:00:00"])})
    ts = _derive_timestamps(df, None, None)
    assert len(ts) == 1
    assert ts[0] == pd.Timestamp("2025-01-01 12:00:00")


def test_empty_emissions_df_raises():
    """No data: helper has nothing to anchor on. Raises."""
    df = pd.DataFrame({"timestamp": pd.to_datetime([])})
    with pytest.raises(ValueError, match="empty emissions_df"):
        _derive_timestamps(df, None, None)


def test_duplicate_timestamps_handled():
    """Duplicate timestamps (multiple sources at the same hour) shouldn't
    double-count -- the helper takes min/max and fills hourly.
    """
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01 05:00:00",
                    "2025-01-01 05:00:00",  # dup
                    "2025-01-01 05:00:00",  # dup
                    "2025-01-01 08:00:00",
                ]
            ),
        }
    )
    ts = _derive_timestamps(df, None, None)
    # Range 5..8 = 4 hours
    assert len(ts) == 4


# ---------------------------------------------------------------------------
# Cross-test: helper output meets AUSTAL's expectations
# ---------------------------------------------------------------------------


def test_output_is_hourly_cadence():
    """AUSTAL series.dmna expects hourly cadence; verify on a long range."""
    hourly = pd.date_range("2025-01-01", "2025-12-31 23:00", freq="h")
    df = pd.DataFrame({"timestamp": hourly})
    ts = _derive_timestamps(df, None, None)
    # Full year hourly: 365 * 24 = 8760
    assert len(ts) == 8760
    # No gaps in first 100 hours
    deltas = {(ts[i + 1] - ts[i]).total_seconds() for i in range(0, 100)}
    assert deltas == {3600.0}


def test_output_is_sorted_ascending():
    """The list must be sorted (downstream code may assume monotonic)."""
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01 23:00:00",  # late
                    "2025-01-01 05:00:00",  # early
                ]
            ),
        }
    )
    ts = _derive_timestamps(df, None, None)
    assert ts == sorted(ts)
    assert ts[0] < ts[-1]
