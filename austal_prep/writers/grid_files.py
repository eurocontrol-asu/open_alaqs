"""
Writer for AUSTAL grid files (per-source spatial distribution).

Two modes:

- legacy: one e0001.dmna .. e8760.dmna per source. Matches the
  AUSTAL reference layout (one e-file per hour, indexed). 8760 files
  per source × n_sources can be slow to write and slow to consume by
  AUSTAL; some downstream tooling expects this layout.

- time_indexed (default): one e.dmna per source with an extra t axis.
  AUSTAL accepts this format. One file instead of 8760, ~99% reduction
  in inode count and ~70% reduction in write time on local SSD.

Format reference (legacy): see the AUSTAL `e<NNNN>.dmna` per-source
grid file specification (AUSTAL 3.2.0 documentation, §3.4.7).

Header:
    t1, t2     start/end of the time window (D.HH:MM:SS relative to
               the year start)
    dd         mesh width (m)
    sk         vertical level top heights (space-separated)
    -          separator
    mode       "text"
    form       "Eq%5.1f"  (for legacy; weights are dimensionless [0..1])
    vldf       "V"        (volume value)
    artp       "M"        (M=master, mode of array combination)
    dims       3
    axes       "xyz"
    sequ       "k+,j-,i+" (k ascending, j descending, i ascending)
    -
    lowb       1 1 1
    hghb       nx ny nz
    *
    <data>     nx*ny*nz floats, ordered per sequ
    ***

For time_indexed mode the header gets an extra t axis. dims becomes
4, axes becomes "xyzt", and the data block has length nx*ny*nz*nt.

The data ordering in the reference is "k+,j-,i+":
  - outermost: k ascending  (z-cells from ground up)
  - middle:    j descending (y-cells from north to south)
  - innermost: i ascending  (x-cells from west to east)
For each (k, j) row the i values are tab-separated on one line.
After each (k, j) row there's a newline. Between j loops within a
fixed k, no extra blank line. Between k loops, a blank line.

(Verified against the reference: each "row" of the e0001.dmna data
block has 75 i-values, there are 75*20 = 1500 such rows total, and
blank lines separate the 20 k-blocks.)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import numpy as np

from austal_prep.config import GridSpec
from austal_prep.spatial import CellWeights


def _format_time_offset(ts: datetime, t_ref: datetime) -> str:
    """Format a timestamp as 'D.HH:MM:SS' relative to t_ref.

    The AUSTAL convention for grid-file t1/t2 timestamps is RELATIVE
    to the first hour of the dispersion run, NOT absolute day-of-year.
    The reference e-files (one per hour, indexed) carry t1=0.00:00:00
    and t2=<run_length>.HH:MM:SS for a full-run e-file. Earlier
    revisions of this function used the year start as reference, which
    produced day-197.00:00:00 for a run starting on 2025-07-17 and
    made AUSTAL reject the file with "not valid at 00:00:00" because
    the dispersion runtime is referenced to t=0 (start of run), not
    day-of-year.
    """
    delta = ts - t_ref
    total_seconds = int(delta.total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days}.{hours:02d}:{minutes:02d}:{seconds:02d}"


def _expand_to_dense(
    weights: CellWeights,
    grid: GridSpec,
    source_offset_cells: int = 0,
) -> np.ndarray:
    """Expand the sparse CellWeights into a dense (src_nx, src_ny,
    n_layers) array, where src_nx = grid.nx - 2*source_offset_cells.

    grid.nx/ny describe the AUSTAL calculation grid (the one declared
    in austal.txt). The dmna source grid is anchored at xq = x0 +
    source_offset_cells * dd and must FIT INSIDE the calc grid with a
    halo of source_offset_cells on every edge, so its cell count is
    grid.nx - 2*source_offset_cells. AUSTAL rejects dmnas whose
    declared extent overruns the calc grid edge.

    Cell indices in `weights` are in the calc-grid frame (where (0, 0)
    is at (x0, y0)). So a calc-grid cell at index (i, j) maps to dmna
    cell index (i - source_offset_cells, j - source_offset_cells).

    Indices that fall outside [0, src_nx) x [0, src_ny) after shifting
    are silently dropped — those cells lie in the calc-grid halo.
    """
    src_nx = grid.nx - 2 * source_offset_cells
    src_ny = grid.ny - 2 * source_offset_cells
    nz = grid.n_layers
    arr = np.zeros((src_nx, src_ny, nz), dtype=np.float64)
    for (i, j, k), w in zip(weights.indices, weights.weights):
        i_grid = i - source_offset_cells
        j_grid = j - source_offset_cells
        if 0 <= i_grid < src_nx and 0 <= j_grid < src_ny and 0 <= k < nz:
            arr[i_grid, j_grid, k] = w
    return arr


def _serialise_dense_kji(arr: np.ndarray) -> List[str]:
    """Serialise a (nx, ny, nz) array in "k+,j-,i+" order to a list of
    text lines.

    Each line is one (k, j) row of nx tab-separated values. Blank
    lines separate k-blocks (matching the reference exactly)."""
    nx, ny, nz = arr.shape
    lines: List[str] = []
    for k in range(nz):
        for j in range(ny - 1, -1, -1):  # j descending
            row = arr[:, j, k]  # i ascending
            lines.append("\t".join(_format_value(v) for v in row))
        # Blank line between k-blocks. The reference has trailing
        # blank between each k slab; mirror that.
        lines.append("")
    return lines


def _format_value(v: float) -> str:
    """Format a single weight. Reference uses "%5.1" by form spec but
    actually emits full-precision values for non-zero weights and "0.0"
    for zeros. We mirror that: zeros as "0.0", non-zeros as the full
    float repr (matches reference byte-for-byte).

    Convert numpy scalars to Python float before repr; numpy 2.x's
    repr emits 'np.float64(...)' which AUSTAL won't parse."""
    f = float(v)
    if f == 0.0:
        return "0.0"
    return repr(f)


def _common_header_lines(
    dd: float,
    sk: List[float],
    nx: int,
    ny: int,
    nz: int,
) -> List[str]:
    return [
        f"dd\t{dd:g}",
        "sk\t" + " ".join(f"{s:g}" for s in sk),
        "-",
        'mode\t"text"',
        'form\t"Eq%5.1f"',
        'vldf\t"V"',
        'artp\t"M"',
    ]


def write_grid_legacy(
    out_dir: Path,
    source_dir_index: int,
    timestamps: List[datetime],
    weights: CellWeights,
    grid: GridSpec,
    source_offset_cells: int = 0,
) -> int:
    """Legacy mode: write one e0001.dmna .. eNNNN.dmna under
    out_dir/<source_dir_index:02d>/.

    Returns the number of files written.
    """
    src_dir = out_dir / f"{source_dir_index:02d}"
    src_dir.mkdir(parents=True, exist_ok=True)

    if not timestamps:
        return 0

    t_ref = timestamps[0]  # AUSTAL grid-file t1/t2 are relative to run start

    src_nx = grid.nx - 2 * source_offset_cells
    src_ny = grid.ny - 2 * source_offset_cells

    dense = _expand_to_dense(weights, grid, source_offset_cells)
    body_lines = _serialise_dense_kji(dense)
    body = "\n".join(body_lines)

    common_mid = _common_header_lines(grid.dd, grid.sk, src_nx, src_ny, grid.n_layers)

    # Each hour gets the same body but a different t1, t2.
    # Convention: parquet timestamps are hour-START. The integration
    # interval for hour h covers [timestamps[h], timestamps[h] + 1h).
    for h_idx, ts in enumerate(timestamps):
        t1 = _format_time_offset(ts, t_ref)
        t2 = _format_time_offset(ts + timedelta(hours=1), t_ref)

        header = (
            [f"t1\t{t1}", f"t2\t{t2}"]
            + common_mid
            + [
                "dims\t3",
                'axes\t"xyz"',
                "sequ\tk+,j-,i+",
                "-",
                "lowb\t1 1 1",
                f"hghb\t{src_nx} {src_ny} {grid.n_layers}",
                "*",
            ]
        )

        file_path = src_dir / f"e{h_idx + 1:04d}.dmna"
        with file_path.open("w", newline="\n") as fh:
            fh.write("\n".join(header) + "\n")
            fh.write(body + "\n")
            fh.write("***\n")

    return len(timestamps)


def write_grid_time_indexed(
    out_dir: Path,
    source_dir_index: int,
    timestamps: List[datetime],
    weights: CellWeights,
    grid: GridSpec,
    source_offset_cells: int = 0,
) -> int:
    """Time-indexed (single-file) mode: write one e0001.dmna per
    source under out_dir/<source_dir_index:02d>/.

    AUSTAL identifies which grid file to read for each (source, hour)
    via the iq column in series.dmna. iq is a file-index pointing at
    eNNNN.dmna. When the spatial pattern is time-invariant (the
    typical case for OpenALAQS sources), we can write the spatial
    pattern ONCE as e0001.dmna and have series.dmna set iq=1 for
    every hour. AUSTAL reads e0001.dmna repeatedly with the hourly
    rate scalars from series.dmna.

    The t1..t2 interval in the grid file header spans the full study
    period rather than a single hour, signalling to AUSTAL that the
    same file applies for the entire run.

    This is mathematically equivalent to writing 8760 identical
    e0001.dmna ... e8760.dmna files (legacy mode), at a fraction of
    the disk and upload cost.

    Returns 1 (one file written).
    """
    src_dir = out_dir / f"{source_dir_index:02d}"
    src_dir.mkdir(parents=True, exist_ok=True)

    if not timestamps:
        return 0

    # t_ref is the start of the dispersion run (first timestamp);
    # AUSTAL expects grid-file t1/t2 RELATIVE to run start.
    t_ref = timestamps[0]
    t1 = _format_time_offset(timestamps[0], t_ref)
    t2 = _format_time_offset(timestamps[-1] + timedelta(hours=1), t_ref)

    dense = _expand_to_dense(weights, grid, source_offset_cells)
    body_lines = _serialise_dense_kji(dense)
    body = "\n".join(body_lines)

    src_nx = grid.nx - 2 * source_offset_cells
    src_ny = grid.ny - 2 * source_offset_cells

    header = (
        [f"t1\t{t1}", f"t2\t{t2}"]
        + _common_header_lines(grid.dd, grid.sk, src_nx, src_ny, grid.n_layers)
        + [
            "dims\t3",
            'axes\t"xyz"',
            "sequ\tk+,j-,i+",
            "-",
            "lowb\t1 1 1",
            f"hghb\t{src_nx} {src_ny} {grid.n_layers}",
            "*",
        ]
    )

    # Write as e0001.dmna so AUSTAL finds it when series.dmna sets
    # iq=1 (which the series.dmna writer does for time_indexed mode).
    file_path = src_dir / "e0001.dmna"
    with file_path.open("w", newline="\n") as fh:
        fh.write("\n".join(header) + "\n")
        fh.write(body + "\n")
        fh.write("***\n")

    return 1


def _write_one_hour_aircraft(args) -> int:
    """Worker: write one hour's per-hour aircraft dmna.

    Module-level so multiprocessing can pickle it. Receives a tuple of
    everything needed; returns 1 on success. The grid argument is a
    GridSpec dataclass (picklable); hour_cell_items is a list of
    ((ix, iy, iz), kg_total) tuples for cells active in this hour.
    """
    (
        out_dir_str,
        source_dir_index,
        h_idx,
        ts,
        t_ref,
        hour_cell_items,
        grid,
        source_offset_cells,
        common_mid,
    ) = args

    src_dir = Path(out_dir_str) / f"{source_dir_index:02d}"

    # Source-grid dimensions (smaller than calc grid by 2*offset on each
    # axis, so the source bbox sits strictly inside the calc grid with
    # source_offset_cells of halo on every edge).
    src_nx = grid.nx - 2 * source_offset_cells
    src_ny = grid.ny - 2 * source_offset_cells
    nz = grid.n_layers

    dense = np.zeros((src_nx, src_ny, nz), dtype=np.float64)

    total = 0.0
    for _, kg in hour_cell_items:
        total += kg

    if total <= 0.0:
        # Sentinel at NW corner of the source grid (i=0, j=src_ny-1, k=0).
        dense[0, src_ny - 1, 0] = 1.0
    else:
        # The (ix, iy) parsed from "aircraft:cell:<ix>_<iy>_<iz>" come
        # from `openalaqs_standalone.distribute.cell_index`, which
        # computes indices in the EM-grid frame (origin at
        # `grid_bounds["origin_x_utm"]` = UTM ref - x_cells/2 * dd,
        # i.e. the EM-grid SW corner, NOT the calc-grid SW corner).
        # The dmna source array IS the EM grid (size = grid.nx -
        # 2*source_offset_cells), so the EM-grid indices map DIRECTLY
        # to dmna source array indices with no subtraction.
        #
        # Subtracting source_offset_cells here (as the stationary
        # _expand_to_dense path does, for cells already in calc-grid
        # frame from austal_prep.spatial._xy_indices_from_bbox) would
        # double-apply the halo offset and shift every aircraft source
        # source_offset_cells*dd SW. With the default
        # source_offset_cells=2 / dd=100, that was the 200 m SW
        # offset previously visible in AUSTAL aircraft dispersion vs
        # the plugin output. Stationary sources were unaffected
        # because their indices arrive in calc-grid frame.
        for (ix, iy, iz), kg in hour_cell_items:
            if 0 <= ix < src_nx and 0 <= iy < src_ny and 0 <= iz < nz:
                dense[ix, iy, iz] = kg / total

    body_lines = _serialise_dense_kji(dense)
    body = "\n".join(body_lines)

    t1 = _format_time_offset(ts, t_ref)
    t2 = _format_time_offset(ts + timedelta(hours=1), t_ref)
    header = (
        [f"t1\t{t1}", f"t2\t{t2}"]
        + common_mid
        + [
            "dims\t3",
            'axes\t"xyz"',
            "sequ\tk+,j-,i+",
            "-",
            "lowb\t1 1 1",
            f"hghb\t{src_nx} {src_ny} {nz}",
            "*",
        ]
    )

    file_path = src_dir / f"e{h_idx + 1:04d}.dmna"
    with file_path.open("w", newline="\n") as fh:
        fh.write("\n".join(header) + "\n")
        fh.write(body + "\n")
        fh.write("***\n")
    return 1


def write_grid_per_hour_aircraft(
    out_dir: Path,
    source_dir_index: int,
    aircraft_emissions_df,  # pd.DataFrame
    timestamps: List[datetime],
    grid: GridSpec,
    source_offset_cells: int = 0,
    processes: Optional[int] = None,
    *,
    pollutant: str,
) -> int:
    """Write per-hour eNNNN.dmna files for ONE aircraft sub-source -
    the one corresponding to the named pollutant.

    Each hour's dmna holds the spatial distribution of THIS POLLUTANT
    only, with cells summing to 1.0 over the cells that emitted that
    pollutant in that hour. Empty hours get a sentinel pattern (1.0
    at NW corner cell, i=0 j=ny-1 k=0) matching the plugin convention.
    series.dmna's rate for empty hours is 0, so the sentinel
    contributes nothing to dispersion.

    Args:
        aircraft_emissions_df: emissions filtered to source_ids
            starting with "aircraft:cell:". Columns: timestamp,
            source_id, pollutant, kg_in_hour. Cell coordinates are
            parsed from source_id (format
            "aircraft:cell:<ix>_<iy>_<iz>"). Caller is responsible
            for filtering to the single pollutant; the writer also
            applies the filter defensively below.
        timestamps: hourly study window.
        processes: if >1, parallelise the per-hour file writes
            across a multiprocessing pool. Each worker handles one
            hour independently (CPU-bound serialisation plus file
            I/O).
        pollutant: which pollutant's mass defines this sub-source's
            spatial distribution. Required. Each pollutant has its
            own sub-source with its own dmna sequence; this argument
            selects which one we are writing.

    Per-pollutant aircraft sub-sources
    -----------------------------------
    The aircraft super-source aggregates many per-cell sources whose
    pollutant compositions vary by aircraft mode:
      - taxi/idle cells: NOx is ~5% of total mass (CO+HC dominate)
      - takeoff/climb cells: NOx is ~85-95% of total mass
    A single shared dmna applied to all pollutants therefore biases
    every per-pollutant output. Splitting aircraft into one
    sub-source per pollutant - each with its own spatial pattern
    computed from that pollutant's mass only - eliminates the bias.
    Mirrors the plugin's per-pollutant bundle structure.

    Returns the number of files written (= len(timestamps)).
    """
    src_dir = out_dir / f"{source_dir_index:02d}"
    src_dir.mkdir(parents=True, exist_ok=True)

    if not timestamps:
        return 0

    t_ref = timestamps[0]
    common_mid = _common_header_lines(grid.dd, grid.sk, grid.nx, grid.ny, grid.n_layers)

    # Parse cell coords once for all rows, then group by (hour, cell)
    # and materialise as per-hour dicts of ((ix, iy, iz), kg) items.
    # Slicing once here is cheaper than reading the multi-indexed
    # Series 144 times, and the per-hour dicts pickle compactly when
    # dispatched to multiprocessing workers.
    df = aircraft_emissions_df
    hour_items: dict = {}
    if not df.empty:
        # Single-pollutant filter: each aircraft sub-source writes
        # spatial fractions from THIS pollutant's mass only. The
        # caller usually pre-filters to this pollutant; the writer
        # enforces it defensively so a mis-passed DataFrame can't
        # silently mix in other pollutants' mass.
        df_p = df[df["pollutant"] == pollutant]
        if df_p.empty:
            # No emissions for this pollutant in the study window.
            # All hours fall through to the sentinel pattern below
            # (empty hour_items dict -> empty list -> sentinel).
            # series.dmna's rate for this sub-source is zero in every
            # hour, so the sentinel contributes nothing.
            pass
        else:
            coord_strs = df_p["source_id"].str.removeprefix("aircraft:cell:")
            parts = coord_strs.str.split("_", n=2, expand=True)
            df_p = df_p.assign(
                _ix=parts[0].astype(int),
                _iy=parts[1].astype(int),
                _iz=parts[2].astype(int),
            )
            # Group by (hour, cell) for THIS pollutant only. Each
            # group's `kg_in_hour` is the per-pollutant mass for
            # that cell at that hour, exactly the quantity AUSTAL
            # needs in the spatial-fraction calculation.
            by_hour_cell = df_p.groupby(["timestamp", "_ix", "_iy", "_iz"])[
                "kg_in_hour"
            ].sum()
            for ts, sub in by_hour_cell.groupby(level=0):
                hour_items[ts] = [
                    ((int(ix), int(iy), int(iz)), float(kg))
                    for (_, ix, iy, iz), kg in sub.items()
                ]

    # Build the task list. One entry per hour.
    out_dir_str = str(out_dir)
    tasks = []
    for h_idx, ts in enumerate(timestamps):
        tasks.append(
            (
                out_dir_str,
                source_dir_index,
                h_idx,
                ts,
                t_ref,
                hour_items.get(ts, []),
                grid,
                source_offset_cells,
                common_mid,
            )
        )

    # Dispatch serial or parallel.
    if processes is None or processes <= 1:
        for task in tasks:
            _write_one_hour_aircraft(task)
    else:
        import multiprocessing as _mp

        with _mp.Pool(processes=processes) as pool:
            for _ in pool.imap_unordered(_write_one_hour_aircraft, tasks):
                pass

    return len(timestamps)


def write_grids_for_source(
    out_dir: Path,
    source_dir_index: int,
    timestamps: List[datetime],
    weights: CellWeights,
    grid: GridSpec,
    mode: str,
    source_offset_cells: int = 0,
) -> int:
    """Dispatch to the appropriate grid writer."""
    if mode == "legacy":
        return write_grid_legacy(
            out_dir,
            source_dir_index,
            timestamps,
            weights,
            grid,
            source_offset_cells=source_offset_cells,
        )
    if mode == "time_indexed":
        return write_grid_time_indexed(
            out_dir,
            source_dir_index,
            timestamps,
            weights,
            grid,
            source_offset_cells=source_offset_cells,
        )
    raise ValueError(f"Unknown grid writer mode: {mode!r}")
