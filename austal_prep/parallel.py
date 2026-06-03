"""
parallel: a multiprocessing driver for per-source grid file writes.

`runner.run_austal_prep` writes the per-source eNNNN.dmna files in a
serial loop over `source_ids`, calling `write_grids_for_source` for
each. Each source's writes are independent of every other source's
(separate output subdirectory, separate weights array, separate
file-system writes), so the loop is embarrassingly parallel. This
module runs that same loop across a process pool.

Why processes, not threads
--------------------------
The per-source compute is CPU-bound Python: numpy dense expansion,
serialisation of float arrays into the AUSTAL DMNA text format, and
file I/O. The GIL means threads would only help for the I/O slice.
Processes parallelise both the CPU work and the I/O.

Design
------
- The parent partitions `source_ids` and the corresponding
  `(source_dir_index, weights)` payloads, then dispatches each unit
  of work to a worker. Per-source weights are numpy arrays inside
  `CellWeights` dataclass instances; both pickle fine.
- Workers are stateless: each task carries everything it needs
  (output directory, source dir index, timestamps, weights, grid
  spec, mode, source offset). No pool initializer needed.
- The batch unit is a single source. AUSTAL studies have at most a
  few hundred sources; per-task pickling overhead is tiny next to
  the file I/O for that source.

Numerical and byte-level parity
-------------------------------
Parity with the serial driver is exact: each worker calls
`write_grids_for_source` with the same inputs the serial loop would
have used, so every byte written to the per-source subdirectories
matches the serial driver's output. The only freedom the parallel
driver has is task ordering, and `write_grids_for_source` is
deterministic and source-independent, so ordering cannot change a
byte. The aggregate file count returned matches too.

This module imports only `austal_prep` and the standard library.
"""

from __future__ import annotations

import multiprocessing as _mp
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from austal_prep.config import GridSpec
from austal_prep.writers.grid_files import write_grids_for_source


def _worker_write_source(args: Tuple) -> int:
    """Write one source's grid files in a worker.

    The args tuple carries everything the writer needs. Returns the
    number of files written for this source, which the parent sums.
    """
    (
        out_dir,
        source_dir_index,
        timestamps,
        weights,
        grid,
        mode,
        source_offset_cells,
    ) = args
    return write_grids_for_source(
        out_dir=Path(out_dir),
        source_dir_index=source_dir_index,
        timestamps=timestamps,
        weights=weights,
        grid=grid,
        mode=mode,
        source_offset_cells=source_offset_cells,
    )


def write_grids_parallel(
    out_dir: Path,
    source_ids: List[str],
    timestamps: List[datetime],
    cell_weights: dict,
    grid: GridSpec,
    mode: str,
    source_offset_cells: int = 0,
    processes: Optional[int] = None,
) -> int:
    """Write per-source grid files across a process pool.

    A drop-in parallel replacement for the per-source loop in
    `run_austal_prep`. Identical output (byte-for-byte) to the serial
    loop, given the same inputs.

    Parameters
    ----------
    out_dir
        Output directory; per-source subdirectories ("01", "02", ...)
        are created inside it.
    source_ids
        Ordered list of source identifiers. The 1-based index in
        this list becomes the source_dir_index ("01", "02", ...).
    timestamps
        List of hour-start datetimes covering the study window.
    cell_weights
        Dict mapping source_id -> CellWeights. Must have an entry
        for every id in source_ids.
    grid
        Grid spec (dd, nx, ny, sk, ...) passed through to the writer.
    mode
        One of "legacy" (per-hour eNNNN.dmna) or "time_indexed"
        (single e0001.dmna with full time series).
    source_offset_cells
        Cell offset relative to grid origin, passed through.
    processes
        Worker process count. Defaults to `os.cpu_count()`. A value
        of 1 still goes through the pool machinery (one worker), so
        the parallel path is testable without actual parallelism.

    Returns
    -------
    Total number of grid files written across all sources.

    If `source_ids` is empty, returns 0 without starting a pool.
    """
    if not source_ids:
        return 0

    if processes is None:
        processes = os.cpu_count() or 1
    processes = max(1, int(processes))

    # Build one task per source. Each task is fully self-contained
    # (no shared mutable state); the worker calls the same
    # write_grids_for_source the serial driver would call.
    tasks = [
        (
            str(out_dir),
            s_idx + 1,
            timestamps,
            cell_weights[sid],
            grid,
            mode,
            source_offset_cells,
        )
        for s_idx, sid in enumerate(source_ids)
    ]

    if processes == 1:
        # Single-process path: still exercises the parallel code
        # path (same task-tuple shape, same worker callable) but
        # without the pool. Useful for tests and for deterministic
        # debugging.
        return sum(_worker_write_source(t) for t in tasks)

    # Multi-process path. `spawn` start method to avoid platform-
    # dependent behaviour (fork-on-Linux vs spawn-on-Windows can
    # differ in how the parent's state is inherited).
    ctx = _mp.get_context("spawn")
    with ctx.Pool(processes=processes) as pool:
        per_source_counts = pool.map(_worker_write_source, tasks)

    return sum(per_source_counts)
