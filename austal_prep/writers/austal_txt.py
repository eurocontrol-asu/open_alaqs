"""
Writer for austal.txt — the AUSTAL configuration file.

Format reference: AUSTAL 3.2.0 technical documentation (§3.4.1
"Eingabedatei austal.txt"). Field semantics:

    ti          title (string)
    qs          quality level (0..4)
    z0, d0, ha  meteorology constants
    dd          mesh width (m)
    x0, y0      south-west corner of the calc grid relative to ref
    xp, yp, hp  receptor x/y/z lists (relative metres / m)
    nx, ny      number of meshes
    os          AUSTAL options string
    iq          source-file indices (one "?" per source — values come
                from series.dmna)
    hq          source heights (one entry per source)
    xq, yq      source SW-corner positions (one entry per source)
    <pollutant> per-source emission rate (one entry per source: "?" if
                emitted, "0" if not)

Pollutant naming: AUSTAL has its own short codes. PM10 → "pm-2",
PM2.5 → "pm-1", NOx → "nox", CO → "co", VOC → "voc". Non-PM ones map
1:1 from lowercase. PM mappings preserve the convention used by
upstream OpenALAQS (writeInputFile lines 939-941).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import numpy as np

from austal_prep.config import AustalStudyConfig
from austal_prep.writers._pollutants import (
    DEFAULT_PM10_FINE_FRACTION,
    austal_components,
)


def write_austal_config(
    out_path: Path,
    study: AustalStudyConfig,
    source_ids: List[str],
    pollutants: List[str],
    receptors: Dict[str, List[float]],  # {"xp": [...], "yp": [...], "hp": [...]}
    source_emits_pollutant: np.ndarray,  # (n_sources, n_pollutants) boolean
) -> Path:
    """Write austal.txt to out_path. Returns out_path on success.

    All position fields (xq, yq) reference the calculation grid's
    south-west corner — every source ends up at the same xq, yq
    because the actual position information lives in the per-source
    grid files (e.g. 01/e0001.dmna). This matches the AUSTAL
    "sourced from grid file" convention.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    grid = study.grid
    n_sources = len(source_ids)

    # Format the floats: integers with no decimal point look cleaner
    # in the AUSTAL file, so emit "11.2" but "0" not "0.0" where the
    # value is integer-valued. The reference uses both styles.
    def f(v: float) -> str:
        if v == int(v):
            return f"{int(v)}"
        return f"{v:g}"

    lines: List[str] = []
    add = lines.append

    add("----------------- general parameters")
    add(f'ti\t"{study.title}"\t\' title')
    add(f"qs\t{study.qs}\t' quality level")

    add("----------------- meteorology")
    add(f"z0\t{f(study.z0)}\t' roughness length (m)")
    add(f"d0\t{f(study.d0)}\t' displacement height (m)")
    add(f"ha\t{f(study.ha)}\t' anemometer height (m)")

    add("----------------- calculation grid")
    add(f"dd\t{f(grid.dd)}\t' mesh width")
    add(f"x0\t{f(grid.x0)}\t' left border (m)")
    add(f"y0\t{f(grid.y0)}\t' lower border (m)")

    if receptors["xp"]:
        add("xp\t" + "\t".join(f"{x:g}" for x in receptors["xp"]) + "\t' x-receptor")
        add("yp\t" + "\t".join(f"{y:g}" for y in receptors["yp"]) + "\t' y-receptor")
        add("hp\t" + "\t".join(f"{h:g}" for h in receptors["hp"]) + "\t' z-receptor")

    add(f"nx\t{grid.nx}\t' number of meshes")
    add(f"ny\t{grid.ny}\t' number of meshes")

    add("----------------- source definitions")
    if study.os_options:
        add(f'os\t"{study.os_options}"')

    # iq: one "?" per source. AUSTAL fills these from series.dmna.
    add("iq\t" + "\t".join(["?"] * n_sources) + "\t' file index (set in series.dmna)")
    add(
        "hq\t"
        + "\t".join([f(study.source_height)] * n_sources)
        + "\t' source height (ignored)"
    )
    # AUSTAL rejects sources whose declared (xq, yq) is coincident with
    # (x0, y0). Offset by source_offset_cells * dd to push the source
    # bbox strictly inside the calc grid (matches the reference layout).
    xq = grid.x0 + study.source_offset_cells * grid.dd
    yq = grid.y0 + study.source_offset_cells * grid.dd
    add(
        "xq\t"
        + "\t".join([f(xq)] * n_sources)
        + "\t' x-lower left (south-west) corner of the source"
    )
    add(
        "yq\t"
        + "\t".join([f(yq)] * n_sources)
        + "\t' y-lower left (south-west) corner of the source"
    )

    # Per-pollutant lines. AUSTAL parameter names for particulate
    # matter carry a component suffix (pm-1, pm-2, pm25-1) per the
    # AUSTAL 3.3 program description, Section 3.1. PM10 splits into
    # two components (fine + coarse) via pm10_fine_fraction; PM2.5
    # uses pm25-1 only; gaseous substances pass through unchanged.
    pm10_fine_fraction = getattr(
        study, "pm10_fine_fraction", DEFAULT_PM10_FINE_FRACTION
    )
    for p_idx, pollutant in enumerate(pollutants):
        per_source = [
            "?" if source_emits_pollutant[s_idx, p_idx] else "0"
            for s_idx in range(n_sources)
        ]
        for austal_name, _frac in austal_components(pollutant, pm10_fine_fraction):
            add(
                f"{austal_name}\t"
                + "\t".join(per_source)
                + f"\t' total {pollutant.upper()} (in g/s) (set in series.dmna)"
            )

    # write_text() gained the `newline` kwarg in Python 3.10; use
    # write_bytes() for compatibility with 3.9.
    out_path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return out_path
