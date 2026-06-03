"""Integration tests for grid_writer_mode='hybrid' (the default).

Hybrid mode is what makes the standalone's AUSTAL inputs match the
QGIS plugin's behaviour for aircraft sources. Each aircraft sub-source
(one per pollutant) gets per-hour spatial dmnas; stationary sources
keep a single time-invariant dmna. The alternative ('time_indexed')
collapses all 8760 hours of aircraft activity into one shared spatial
template, which biases per-pollutant dispersion output. The bias has
been measured (correlation 0.82 vs the plugin, sum-ratio 0.94) and
hybrid is the fix.

These tests run the FULL pipeline (orchestrate + austal_prep) on the
canonical training_v3 fixture and check three invariants that, if
broken, would silently undo the fix:

  1. Aircraft gets per-hour e-files (regression to time_indexed
     would show 1 e-file per aircraft sub-source instead of n_hours).
  2. Per-pollutant aircraft e-files have DIFFERENT spatial patterns
     (regression to a shared aircraft pattern would show identical
     e-files across pollutants for the same hour).
  3. Mass conservation: total emitted mass derivable from
     (series.dmna rate x 3600s) equals the input emission for each
     aircraft pollutant.

Each test is fully independent: orchestrate + austal_prep run from
scratch per test, with a temporary output directory. The pipeline
takes ~15 s on training_v3, so the full file is ~45 s. That's the
cost of being independent and is well worth it for a default the
operator depends on.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ALAQS_FIXTURE = (
    REPO_ROOT / "openalaqs_standalone" / "validation" / "data" / "training_v3.alaqs"
)

# 51-hour window with 6 active aircraft hours (1, 2, 25, 26, 49, 50).
# Same window the R2 regression test pins.
START = "2025-12-01 06:00:00"
END = "2025-12-03 09:00:00"
N_HOURS_EXPECTED = 51


def _run_pipeline(out_root: Path) -> Path:
    """Run orchestrate + austal_prep end-to-end on training_v3 with
    hybrid mode (the default). Returns the austal_folder path.

    Uses subprocess to invoke the package's CLI rather than the
    Python API, because the CLI is what the operator runs and what
    we ultimately need to certify.
    """
    # Stage 1: orchestrate. CLI default for grid_writer_mode is
    # already 'hybrid'; not passing the flag is the assertion of
    # default behaviour.
    subprocess.run(
        [
            sys.executable,
            "-m",
            "openalaqs_standalone",
            "austal",
            str(ALAQS_FIXTURE),
            "--out",
            str(out_root),
            "--year",
            "2025",
            "--include-aircraft",
            "--aircraft-method",
            "bymode",
            "--source-dynamics",
            "none",
            "--use-isa-meteo",
            "--start",
            START,
            "--end",
            END,
            "--processes",
            "1",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
    )

    # Verify config.json embeds hybrid (the test's mode under test).
    cfg = json.loads((out_root / "config_folder" / "config.json").read_text())
    assert cfg["grid_writer_mode"] == "hybrid", (
        "orchestrate's default config.grid_writer_mode is not 'hybrid'. "
        "Either the orchestrate CLI default changed, or make_config no "
        "longer threads the mode into config.json."
    )

    # Stage 2: austal_prep reads config.json so it picks up hybrid.
    subprocess.run(
        [
            sys.executable,
            "-m",
            "austal_prep",
            "--sources",
            str(out_root / "sources_folder" / "sources.parquet"),
            "--emissions",
            str(out_root / "emissions_folder" / "emissions.parquet"),
            "--receptors",
            str(out_root / "receptors_folder" / "receptors.csv"),
            "--meteo",
            str(out_root / "meteo_folder" / "meteo.csv"),
            "--output-dir",
            str(out_root / "austal_folder"),
            "--config",
            str(out_root / "config_folder" / "config.json"),
            "--start",
            START,
            "--end",
            END,
            "--processes",
            "1",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
    )

    return out_root / "austal_folder"


def _parse_series_header(austal_folder: Path) -> dict:
    """Return a dict mapping column name -> index for the series.dmna
    form line. Column names look like '01.iq', '03.nox', '04.pm-1'.
    """
    text = (austal_folder / "series.dmna").read_text()
    form_line = next(L for L in text.splitlines() if L.startswith("form\t"))
    cols = form_line.removeprefix("form\t").split("\t")
    # strip quotes and the %... suffix
    out = {}
    for idx, c in enumerate(cols):
        c = c.strip('"')
        # column spec is "name%format" - keep everything before %
        name = c.split("%", 1)[0]
        out[name] = idx
    return out


def _read_series_column(austal_folder: Path, col_idx: int) -> list[str]:
    """Return all data-row values for one column in series.dmna."""
    text = (austal_folder / "series.dmna").read_text()
    lines = text.splitlines()
    # data starts after the '*' delimiter
    start = next(i for i, L in enumerate(lines) if L.strip() == "*") + 1
    vals = []
    for L in lines[start:]:
        if not L.strip() or L.strip().startswith("***"):
            continue
        cols = L.split("\t")
        if col_idx < len(cols):
            vals.append(cols[col_idx].strip())
    return vals


def _parse_efile_3d(path: Path) -> np.ndarray:
    """Parse one AUSTAL e<NNNN>.dmna file into a 3D numpy array
    indexed as arr[ix, iy, iz]. Reads hghb from the header to size
    the array.
    """
    text = path.read_text()
    lines = text.splitlines()
    # Find hghb (last one if header has multiple) and *
    nx = ny = nz = 0
    star_idx = 0
    for i, L in enumerate(lines):
        if L.startswith("hghb"):
            parts = L.split()
            if len(parts) >= 4:
                nx, ny, nz = int(parts[1]), int(parts[2]), int(parts[3])
        if L.strip() == "*":
            star_idx = i
            break
    if nx == 0:
        raise ValueError(f"{path}: no hghb header found")

    arr = np.zeros((nx, ny, nz), dtype=np.float64)
    i = star_idx + 1
    for k in range(nz):
        for j in range(ny - 1, -1, -1):
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines) or lines[i].strip().startswith("***"):
                break
            row = lines[i].split()
            for ii, v in enumerate(row[:nx]):
                arr[ii, j, k] = float(v)
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    return arr


def test_hybrid_aircraft_uses_per_hour_efiles(tmp_path: Path):
    """Aircraft sub-sources must each get one e-file per hour.

    A regression that routed aircraft through the time_indexed writer
    instead of write_grid_per_hour_aircraft would yield ONE e-file per
    aircraft sub-source (matching stationary), defeating the entire
    purpose of hybrid mode. This test catches that.
    """
    austal_folder = _run_pipeline(tmp_path)

    # Find which source dir indices are aircraft sub-sources by
    # reading the series.dmna form line: aircraft sub-sources have
    # column names like '01.co', '02.hc', '03.nox' where the index
    # in the form maps to a single pollutant. Stationary sources
    # have all-pollutant columns under the same iq.
    cols = _parse_series_header(austal_folder)
    # iq columns are '01.iq' ... '23.iq'. Source dir indices are 1-based.
    iq_cols = sorted(c for c in cols if c.endswith(".iq"))
    n_sources = len(iq_cols)
    assert n_sources >= 5, (
        f"expected at least 5 sources (5 aircraft sub-sources for "
        f"training_v3), got {n_sources}"
    )

    # Aircraft sub-source detection: look at the series iq values
    # across all rows for each source. Aircraft cycle 1..n_hours,
    # stationary stay at 1.
    aircraft_dirs: list[int] = []
    stationary_dirs: list[int] = []
    for s_idx in range(1, n_sources + 1):
        iq_col_name = f"{s_idx:02d}.iq"
        col_idx = cols[iq_col_name]
        vals = _read_series_column(austal_folder, col_idx)
        unique = sorted(set(int(v) for v in vals))
        if unique == [1]:
            stationary_dirs.append(s_idx)
        elif unique == list(range(1, N_HOURS_EXPECTED + 1)):
            aircraft_dirs.append(s_idx)
        else:
            pytest.fail(
                f"source {s_idx:02d} has unexpected iq values: {unique[:5]}... "
                f"(expected [1] or [1..{N_HOURS_EXPECTED}])"
            )

    # training_v3 emits 5 pollutants from aircraft (bymode: co, hc,
    # nox, pm10, pm25; no sox), so expect 5 aircraft sub-sources.
    assert len(aircraft_dirs) == 5, (
        f"expected exactly 5 aircraft sub-sources in training_v3 bymode "
        f"(co, hc, nox, pm10, pm25), found {len(aircraft_dirs)}: "
        f"dirs {aircraft_dirs}"
    )
    assert (
        len(stationary_dirs) >= 1
    ), f"expected at least 1 stationary source, found {len(stationary_dirs)}"

    # Each aircraft sub-source dir has exactly N_HOURS_EXPECTED e-files.
    for s_idx in aircraft_dirs:
        d = austal_folder / f"{s_idx:02d}"
        efiles = sorted(d.glob("e*.dmna"))
        assert len(efiles) == N_HOURS_EXPECTED, (
            f"aircraft sub-source dir {s_idx:02d}/ has {len(efiles)} e-files, "
            f"expected {N_HOURS_EXPECTED} (one per hour). This means hybrid "
            f"mode regressed to time_indexed for aircraft."
        )

    # Each stationary source dir has exactly 1 e-file.
    for s_idx in stationary_dirs:
        d = austal_folder / f"{s_idx:02d}"
        efiles = sorted(d.glob("e*.dmna"))
        assert len(efiles) == 1, (
            f"stationary source dir {s_idx:02d}/ has {len(efiles)} e-files, "
            f"expected 1 (time_indexed mode applies to stationary)"
        )


def test_hybrid_per_pollutant_spatial_patterns_differ(tmp_path: Path):
    """Aircraft sub-sources for different pollutants must have DIFFERENT
    spatial weight distributions at the same hour.

    The biased fallback (shared spatial pattern across pollutants) was
    the original time_indexed behaviour. Hybrid's whole reason to
    exist is to give each pollutant its own spatial distribution,
    because aircraft taxi mass is ~5% NOx but takeoff mass is ~85% NOx
    -- the spatial centroid is in completely different places.

    Picks an active hour from training_v3 (hour 1 has all 5 aircraft
    pollutants active) and asserts CO and NOx weight arrays are not
    elementwise-equal.
    """
    austal_folder = _run_pipeline(tmp_path)

    # Identify which dir is aircraft_co vs aircraft_nox by reading
    # the form line: 'NN.co' or 'NN.nox' (the dot-prefixed source
    # index uniquely identifies each per-pollutant column).
    cols = _parse_series_header(austal_folder)
    co_col = next((c for c in cols if c.endswith(".co")), None)
    nox_col = next((c for c in cols if c.endswith(".nox")), None)
    assert co_col and nox_col, (
        f"expected at least one .co and one .nox column in series.dmna; "
        f"found columns: {sorted(cols)[:20]}"
    )

    # Pull the source-dir prefix (first 'NN' of 'NN.co'). In hybrid
    # mode the FIRST .co / .nox column corresponds to the aircraft
    # sub-source (sub-sources are emitted before stationary in the
    # source ordering established by runner.py).
    co_dir = int(co_col.split(".")[0])
    nox_dir = int(nox_col.split(".")[0])

    # Hour 1 is the first aircraft-active hour in the training_v3
    # 51-hour window (verified manually). Read both e-files.
    co_arr = _parse_efile_3d(austal_folder / f"{co_dir:02d}" / "e0001.dmna")
    nox_arr = _parse_efile_3d(austal_folder / f"{nox_dir:02d}" / "e0001.dmna")

    # Sanity: both should be valid spatial distributions summing to 1.
    assert co_arr.sum() == pytest.approx(1.0, abs=1e-9), co_arr.sum()
    assert nox_arr.sum() == pytest.approx(1.0, abs=1e-9), nox_arr.sum()

    # The actual invariant: CO and NOx spatial patterns differ.
    # If they were elementwise equal we would be in shared-pattern
    # (biased) mode.
    assert not np.allclose(co_arr, nox_arr, atol=1e-6), (
        "aircraft_co and aircraft_nox have identical spatial patterns "
        "at hour 1 -- hybrid mode regressed to shared-pattern (biased) "
        "behaviour. Each pollutant should have its own spatial "
        "distribution computed from that pollutant's mass per cell."
    )

    # And the difference should be meaningful, not floating-point noise.
    # CO is taxi-dominant, NOx is climb-dominant -- their max-weight
    # cells are in different parts of the airport. Expect max|diff|
    # of at least 1e-3 (a tenth of a percent in normalised weights).
    max_abs_diff = float(np.abs(co_arr - nox_arr).max())
    assert max_abs_diff >= 1e-3, (
        f"aircraft_co vs aircraft_nox spatial diff is suspiciously small "
        f"(max |diff| = {max_abs_diff:.2e}). Expect at least 1e-3 from "
        f"the taxi-vs-climb mass split."
    )


def test_hybrid_mass_conservation(tmp_path: Path):
    """For each aircraft sub-source, the integrated emission derivable
    from series.dmna (rate g/s x 3600 s/hour x n_hours) must equal the
    total input emission of that pollutant from aircraft sources, to
    within tolerance.

    What this catches: a writer bug that drops, doubles, or
    misroutes mass between sub-sources. Per-cell weight conservation
    (each e-file sums to 1) does NOT catch a rate-allocation bug
    upstream in series.dmna -- this test does.

    Tolerance: series.dmna rates use AUSTAL's spec %10.3e format,
    giving ~4 significant figures (3 decimal places of mantissa).
    Accumulated rounding over n_hours times n_aircraft_sub_sources
    can reach 1e-4 relative on the integrated mass. Add a small
    absolute floor for very small pollutants. The 1e-30 g/s rate
    floor used to keep AUSTAL happy contributes a cumulative
    ~9.18e-25 kg over 51 hours -- negligible against the format
    rounding above.

    Any real routing bug (mass to wrong sub-source, duplicated
    cell, dropped hour) would produce error far larger than 1e-3
    relative.
    """
    austal_folder = _run_pipeline(tmp_path)

    # Total per-pollutant aircraft mass from the input emissions
    # parquet (ground truth -- this is what we expect to read back
    # out of series.dmna).
    em = pd.read_parquet(tmp_path / "emissions_folder" / "emissions.parquet")
    aircraft_mask = em["source_id"].str.startswith("aircraft:cell:")
    input_mass_kg = em[aircraft_mask].groupby("pollutant")["kg_in_hour"].sum().to_dict()

    cols = _parse_series_header(austal_folder)
    # AUSTAL splits pm10 into pm-1 + pm-2 and pm25 into pm25-1; map
    # the AUSTAL column names back to OpenALAQS pollutant names.
    # In hybrid mode, aircraft sub-sources are the FIRST occurrence
    # of each pollutant in the form line.
    austal_to_alaqs = {
        "co": "co",
        "hc": "hc",
        "nox": "nox",
        "sox": "sox",
        "pm-1": "pm10",
        "pm-2": "pm10",
        "pm25-1": "pm25",
    }
    # For each aircraft sub-source's pollutant column, sum rate*3600
    # over hours and accumulate by alaqs pollutant.
    integrated_kg: dict[str, float] = {}
    used_dirs: set[int] = set()
    for col_name, col_idx in cols.items():
        if "." not in col_name:
            continue
        prefix, suffix = col_name.split(".", 1)
        if suffix == "iq":
            continue
        if suffix not in austal_to_alaqs:
            continue
        # Skip if this is not the first occurrence of this AUSTAL
        # name -- only the FIRST (aircraft) gets summed here.
        # Track by AUSTAL name and skip subsequent dirs.
        # However, pm-1 and pm-2 both belong to the FIRST aircraft
        # pm10 dir, so they should be summed together for that dir.
        s_dir = int(prefix)
        # Check this is an aircraft sub-source by looking at iq cycling
        iq_col = f"{prefix}.iq"
        iq_vals = sorted(
            {int(v) for v in _read_series_column(austal_folder, cols[iq_col])}
        )
        if iq_vals != list(range(1, N_HOURS_EXPECTED + 1)):
            continue  # stationary, skip
        used_dirs.add(s_dir)
        # Sum rate * 3600 over all rows
        rate_vals = _read_series_column(austal_folder, col_idx)
        total_g = sum(float(v) for v in rate_vals) * 3600.0
        alaqs_p = austal_to_alaqs[suffix]
        integrated_kg.setdefault(alaqs_p, 0.0)
        integrated_kg[alaqs_p] += total_g / 1000.0

    # Now compare
    for alaqs_p, input_kg in input_mass_kg.items():
        if alaqs_p not in integrated_kg:
            # The pollutant didn't appear in series.dmna at all -- this
            # only happens if input_mass is also effectively zero.
            assert input_kg < 1e-9, (
                f"aircraft pollutant {alaqs_p!r} has input mass {input_kg:.6e} kg "
                f"but no AUSTAL sub-source. Mass routing is broken."
            )
            continue
        out_kg = integrated_kg[alaqs_p]
        assert out_kg == pytest.approx(input_kg, rel=1e-3, abs=1e-6), (
            f"aircraft {alaqs_p!r} mass conservation failed: "
            f"input {input_kg:.6f} kg vs series-integrated {out_kg:.6f} kg "
            f"(diff {out_kg - input_kg:+.6e} kg, rel {(out_kg - input_kg) / input_kg:+.2e}). "
            f"Tolerance is 1e-3 relative; anything larger indicates a "
            f"rate-routing bug between aircraft sub-sources, not just "
            f"%10.3e format rounding."
        )
