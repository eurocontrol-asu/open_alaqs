"""
Writer for series.dmna — the AUSTAL meteorological time series file.

Format reference: AUSTAL 3.2.0 technical documentation (§3.4.3
"Zeitreihen series.dmna").

Header:
    form    column format specifiers; one per output column
    mode    "text"
    sequ    "i"           single-axis sequence
    dims    1
    lowb    1
    hghb    n_hours
    *

Each data row:
    timestamp_str  ra ua lm [hm] iq_per_source [er_per_source_pollutant]

Where:
    ra  wind direction (deg)         %5.0f
    ua  wind speed (m/s)              %5.1f
    lm  Obukhov length (m)            %7.1f
    hm  mixing height (m)             %7.1f   (only if included)
    iq  source-specific time index    %3.0f   one per source
    er  emission rate (g/s)           %10.3e  one per source × pollutant

Timestamp format mirrors the reference: "YYYY-MM-DD.HH:MM:SS". The
reference labels hour 1 as "2025-01-01.01:00:00" (the time at the END
of the integration interval, by AUSTAL convention).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import numpy as np

from austal_prep.writers._pollutants import (
    DEFAULT_PM10_FINE_FRACTION,
    austal_components,
)


def _timestamp_string(ts: datetime) -> str:
    """AUSTAL-formatted timestamp string. AUSTAL uses hour-END
    timestamps (a row labelled "2025-01-01.01:00:00" represents the
    integration interval 00:00 to 01:00). Our parquet inputs use
    hour-START, so add one hour at format time."""
    return (ts + timedelta(hours=1)).strftime("%Y-%m-%d.%H:%M:%S")


def write_series(
    out_path: Path,
    timestamps: List[datetime],
    meteo: Dict[datetime, dict],
    emission_rates: np.ndarray,  # (n_hours, n_sources, n_pollutants) g/s
    source_ids: List[str],
    pollutants: List[str],
    source_emits_pollutant: np.ndarray,  # (n_sources, n_pollutants) boolean
    mixing_height_included: bool = True,
    grid_writer_mode: str = "time_indexed",
    pm10_fine_fraction: float = DEFAULT_PM10_FINE_FRACTION,
    per_source_legacy: List[bool] = None,
    normalize_to_year_start: bool = True,
) -> Path:
    """Write series.dmna. Returns out_path on success.

    The (source_id, pollutant) columns appear only for combinations
    where source_emits_pollutant is True. This avoids emitting a long
    row of zeros for pollutants a source doesn't generate.

    The 'iq' column tells AUSTAL which eNNNN.dmna file to read for
    each (source, hour). Behavior depends on grid_writer_mode:
      - "time_indexed": iq=1 for every hour, since only e0001.dmna
        exists per source. The single grid file's spatial pattern is
        time-invariant; the hourly modulation comes from the emission
        rate columns. This is the efficient default.
      - "legacy": iq=h_idx+1 (1, 2, ... n_hours), pointing at
        e0001.dmna ... eNNNN.dmna respectively. Used when each hour
        has a genuinely different spatial pattern (e.g. movement
        sources, future work).
      - "hybrid": per-source iq scheme. Caller passes per_source_legacy
        (a list of bool, one per source). True entries get legacy-style
        iq=h+1; False entries get time_indexed-style iq=1.

    per_source_legacy: optional list (length = len(source_ids)). When
        provided, overrides grid_writer_mode for iq generation per
        source. Required for "hybrid" mode.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_h = len(timestamps)

    # AUSTAL requires the dispersion run to start at yyyy-01-01.01:00:00
    # in te-convention (= yyyy-01-01.00:00:00 in interval-start time).
    # When the real emission window is anywhere other than the first
    # 51 hours of the year (e.g. a December window), AUSTAL's internal
    # time bookkeeping reconciles the series.dmna te values against the
    # e-file t1/t2 (which are absolute year-relative offsets), and the
    # mismatch surfaces as
    #   *** Request for t2=X, current grid source not valid after Y!
    #     (TalSrc.GetGridSource.4)
    #   *** Grid source "01" not available!
    #     (TalSrc.SrcCrtPtl.14)
    # at AUSTAL startup. The plugin sidesteps this with its
    # set_normalized_date() (AUSTALOutputModule.py:737); we apply the
    # same shift here. Meteo and emission rates are keyed by real ts
    # and untouched; only the label written into series.dmna shifts.
    if normalize_to_year_start and timestamps:
        year_start = datetime(timestamps[0].year, 1, 1, 0, 0, 0)
        t_delta = timestamps[0] - year_start
    else:
        t_delta = timedelta(0)

    # Resolve per-source iq scheme. If caller didn't pass per_source_legacy,
    # derive it from grid_writer_mode (uniform across sources). For
    # "hybrid", per_source_legacy must be passed explicitly by the caller.
    if per_source_legacy is None:
        if grid_writer_mode == "hybrid":
            raise ValueError(
                "grid_writer_mode='hybrid' requires per_source_legacy to "
                "be passed explicitly (one bool per source)."
            )
        legacy_iq = grid_writer_mode == "legacy"
        per_source_legacy = [legacy_iq] * len(source_ids)
    elif len(per_source_legacy) != len(source_ids):
        raise ValueError(
            f"per_source_legacy length {len(per_source_legacy)} does not "
            f"match number of sources {len(source_ids)}."
        )

    # Active (source, pollutant) pairs: only those that emit anything
    active_pairs = [
        (s_idx, p_idx)
        for s_idx in range(len(source_ids))
        for p_idx in range(len(pollutants))
        if source_emits_pollutant[s_idx, p_idx]
    ]

    # Build column list
    # Header: form line
    form_parts = ['"te%20lt"', '"ra%5.0"', '"ua%5.1"', '"lm%7.1"']
    if mixing_height_included:
        form_parts.append('"hm%7.1"')

    # Per-source iq columns: number them 01, 02, ... matching the
    # per-source grid directory naming convention. (See grid_files.py)
    iq_indices = [f"{i + 1:02d}" for i in range(len(source_ids))]
    for iq in iq_indices:
        form_parts.append(f'"{iq}.iq%3.0"')

    # Per-active-pair emission columns. PM10 expands into two
    # columns (pm-1 and pm-2); PM2.5 into one (pm25-1); other
    # pollutants are 1:1. Order is source-major then component-major
    # within each source so columns line up between the form line
    # and every data row.
    for s_idx, p_idx in active_pairs:
        iq = iq_indices[s_idx]
        for austal_p, _frac in austal_components(pollutants[p_idx], pm10_fine_fraction):
            form_parts.append(f'"{iq}.{austal_p}%10.3e"')

    lines: List[str] = []
    add = lines.append
    add("form\t" + "\t".join(form_parts))
    add('mode\t"text"')
    add('sequ\t"i"')
    add("dims\t1")
    add("lowb\t1")
    add(f"hghb\t{n_h}")
    # AUSTAL's DMNA reader has a default 4000-byte line buffer (per
    # AUSTAL 3.3 docs Annex B). With many sources × pollutants the
    # form line alone exceeds that. Set buff to 1 MB which covers any
    # reasonable source count (~10000 sources) without overhead in
    # AUSTAL's allocator.
    add("buff\t1000000")
    add("*")

    # Body rows. For each timestamp h, the format is:
    #  ts  ra  ua  lm  [hm]  iq01 iq02 ... iqNN  er01 er02 ... erMM
    # The ts column is shifted by -t_delta so AUSTAL sees a run that
    # starts at yyyy-01-01.01:00:00; meteo/rates lookups stay keyed
    # by the real ts.
    for h_idx, ts in enumerate(timestamps):
        meteo_row = meteo[ts]
        cols: List[str] = []
        cols.append(_timestamp_string(ts - t_delta))
        cols.append(f"{meteo_row['wind_direction_deg']:5.0f}")
        cols.append(f"{meteo_row['wind_speed_ms']:5.1f}")
        cols.append(f"{meteo_row['obukhov_length_m']:7.1f}")
        if mixing_height_included:
            cols.append(f"{meteo_row['mixing_height_m']:7.1f}")
        # Per-source iq column: which eNNNN.dmna file to read for
        # this hour. In time_indexed mode there's only e0001.dmna per
        # source, so iq=1 always. In legacy mode iq numbers hours
        # 1..n_hours and points at e0001..eNNNN.dmna. In hybrid mode,
        # per_source_legacy specifies which sources use which scheme.
        for s_idx in range(len(source_ids)):
            iq_value = h_idx + 1 if per_source_legacy[s_idx] else 1
            cols.append(f"{iq_value:3d}")
        # Per-active-pair emission rates.
        # AUSTAL 3.3.0 aborts multi-source runs with
        #   *** Grid source "NN" not available!  (TalSrc.SrcCrtPtl.14)
        # at the hour after any source rate transitions to exactly
        # 0.000e+00 mid-run. Substitute a 1e-30 floor to keep the rate
        # strictly positive. Total fictitious mass over a year of zeros
        # is ~3.2e-26 g per source-pollutant pair, well below numerical
        # precision. Matches the plugin's _ti_write_series fix in
        # AUSTALOutputModule.py.
        for s_idx, p_idx in active_pairs:
            val = float(emission_rates[h_idx, s_idx, p_idx])
            if val == 0.0:
                val = 1.0e-30
            for _austal_p, frac in austal_components(
                pollutants[p_idx], pm10_fine_fraction
            ):
                cols.append(f"{val * frac:10.3e}")
        add("\t".join(cols))

    add("")  # trailing newline before terminator (matches reference)
    add("***")

    # AUSTAL (Windows binary, AUSTAL_3.3.0-WI-x) is sensitive to the
    # line-ending convention in series.dmna. The plugin's writer goes
    # through Python's text mode open() on Windows, which produces
    # CRLF; AUSTAL accepts that file. The same data written with LF
    # endings triggers a spurious
    #   *** Request for t2=X+1h, current grid source not valid after X!
    #     (TalSrc.GetGridSource.4)
    # at the run end (AUSTAL apparently adds an extra closure-hour
    # iteration when the series.dmna boundary isn't recognized as
    # cleanly terminated). Plugin e-files are LF and AUSTAL parses
    # them fine; only series.dmna needs CRLF.
    out_path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return out_path
