"""
parallel: a multiprocessing driver for movement emissions (Phase A4).

`compute_movements.compute_all_movements` computes every aircraft
movement in a serial loop. Each movement is an independent unit of
work -- load the movement, resolve its aircraft and engine, walk its
trajectory or taxi route, compute per-segment, gate and taxi
emissions -- so the loop is embarrassingly parallel. This module runs
that same loop across a process pool.

Why processes, not threads
--------------------------
The per-movement compute is CPU-bound Python: trajectory projection,
clipping, per-segment integration, BFFM2 corrections. The GIL means
threads would not speed that up. Processes do. The cost is that each
worker needs its own resources (an sqlite connection is not shareable
across processes) and that results must be pickled back to the
parent.

Design
------
  - The parent opens the .alaqs only to read the movement-oid index.
    It does not compute anything itself.
  - Each worker, at pool startup (via the pool `initializer`, run once
    per worker, not once per task), opens its OWN read-only sqlite
    connection to the same .alaqs file and builds its OWN per-study
    context (`build_context`). Building the context per worker is a
    handful of small queries; it is cheaper and simpler than pickling
    the context (which holds a shapely geometry) to every worker.
  - Movements are partitioned into batches. A batch, not a single
    movement, is the unit of work handed to a worker, so the
    per-task pickling overhead (the oid list out, the result dicts
    back) is amortised over many movements.
  - Each worker computes its batch with the exact same
    `compute_for_movement` call the serial driver uses, and returns
    {oid: result}. The parent merges the batch dicts.

Numerical parity
----------------
The parallel driver must produce results bit-identical to the serial
`compute_all_movements`: same `compute_for_movement`, same context
contents, same inputs. The only difference is which process runs a
given movement, and the compute is deterministic and movement-
independent, so the process boundary cannot change a number.
`test_parallel.py` asserts this equality directly. Because parity is
guaranteed, `compute_all_movements_parallel` is a drop-in replacement
for `compute_all_movements` whenever the movement count makes the
process-pool overhead worth paying.

This module imports only the standalone's own packages and the
standard library. No QGIS and no PyQt.
"""

from __future__ import annotations

import multiprocessing as _mp
import os
from typing import Optional

from openalaqs_standalone import compute_movements as _cm
from openalaqs_standalone import movements as _mv

# Default batch size: how many movement oids a worker processes per
# task. Small enough that work is spread evenly across workers even
# for modest studies, large enough that the per-task pickling cost is
# amortised. Tunable via the `batch_size` argument.
DEFAULT_BATCH_SIZE = 16

# Module-level worker state, populated once per worker by `_worker_init`
# and read by `_worker_compute_batch`. Each worker process has its own
# copy of these globals; they are never shared or pickled between
# processes. This is the standard multiprocessing pattern for
# per-worker resources that are expensive to build and not picklable
# (here, the sqlite connection).
_WORKER_CONN = None
_WORKER_CTX = None
_WORKER_METHOD = None
_WORKER_USE_ISA = None
_WORKER_APPLY_NOX = None


def _worker_init(
    alaqs_path: str,
    method: str,
    use_isa_meteo: bool,
    apply_nox_corrections: bool = False,
) -> None:
    """Pool initializer: set up this worker's per-process resources.

    Run once per worker process when the pool starts, not once per
    task. Opens this worker's own sqlite connection to the .alaqs file
    and builds its own per-study context, storing both in
    module-level globals for `_worker_compute_batch` to use. The
    method, meteo flag, and NOx-correction flag are stored too, so
    the per-task payload is only the oid list.
    """
    global _WORKER_CONN, _WORKER_CTX, _WORKER_METHOD, _WORKER_USE_ISA, _WORKER_APPLY_NOX
    _WORKER_CONN = _mv.connect(alaqs_path)
    _WORKER_CTX = _cm.build_context(_WORKER_CONN)
    _WORKER_METHOD = method
    _WORKER_USE_ISA = use_isa_meteo
    _WORKER_APPLY_NOX = apply_nox_corrections


def _worker_compute_batch(oids: list) -> dict:
    """Compute one batch of movement oids in a worker.

    Uses the connection, context, method, meteo flag and NOx-correction
    flag set up by `_worker_init`. Returns {oid: result} for the oids
    in this batch that produced a result; oids that could not be
    computed (None from `compute_for_movement`) are omitted, exactly as
    in the serial driver.
    """
    out: dict = {}
    for oid in oids:
        res = _cm.compute_for_movement(
            _WORKER_CONN,
            oid,
            _WORKER_CTX,
            method=_WORKER_METHOD,
            use_isa_meteo=_WORKER_USE_ISA,
            apply_nox_corrections=_WORKER_APPLY_NOX,
        )
        if res is not None:
            out[oid] = res
    return out


def _batched(items: list, batch_size: int) -> list:
    """Split a list into consecutive batches of at most `batch_size`."""
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def compute_all_movements_parallel(
    alaqs_path: str,
    method: str = "bymode",
    use_isa_meteo: bool = True,
    oids: Optional[list] = None,
    processes: Optional[int] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    apply_nox_corrections: bool = False,
) -> dict:
    """Compute every movement in the study, across a process pool.

    A drop-in parallel replacement for
    `compute_movements.compute_all_movements`: same inputs (except a
    file path instead of an open connection, because the workers open
    their own connections), same {oid: result} output, results
    bit-identical to the serial driver.

    Parameters
    ----------
    alaqs_path
        Path to the .alaqs study file. A path, not an open
        connection, because each worker opens its own connection;
        sqlite connections cannot cross a process boundary.
    method
        One of "bymode", "bffm2_anchor", "bffm2_traj".
    use_isa_meteo
        ISA vs loaded-meteo for the BFFM2 ambient correction.
    oids
        If given, only these movement oids are computed; otherwise all
        movements in `user_aircraft_movements`.
    processes
        Worker process count. Defaults to `os.cpu_count()`. A value of
        1 still goes through the pool machinery (one worker), which is
        useful for testing the parallel path without actual
        parallelism.
    batch_size
        How many oids each worker task processes at once. Defaults to
        DEFAULT_BATCH_SIZE. Larger batches mean less per-task pickling
        overhead but coarser load balancing.

    Returns
    -------
    A dict mapping oid -> per-movement result dict, identical to what
    `compute_all_movements` returns for the same inputs. Movements
    that could not be computed are omitted.

    If the study has no movements (or `oids` is an empty list), an
    empty dict is returned without starting a pool.
    """
    if method not in _cm.METHODS:
        raise ValueError(f"Unknown method: {method!r}; expected one of {_cm.METHODS}")
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")

    # Resolve the oid list. This is the one piece the parent reads
    # from the .alaqs; everything else happens in the workers.
    if oids is None:
        index_conn = _mv.connect(alaqs_path)
        try:
            oids = _mv.get_movement_oids(index_conn)
        finally:
            index_conn.close()

    if not oids:
        return {}

    if processes is None:
        processes = os.cpu_count() or 1
    # No point starting more workers than there are batches.
    batches = _batched(list(oids), batch_size)
    processes = max(1, min(processes, len(batches)))

    results: dict = {}
    with _mp.Pool(
        processes=processes,
        initializer=_worker_init,
        initargs=(alaqs_path, method, use_isa_meteo, apply_nox_corrections),
    ) as pool:
        for batch_result in pool.map(_worker_compute_batch, batches):
            results.update(batch_result)
    return results
