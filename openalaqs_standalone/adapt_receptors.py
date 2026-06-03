"""
adapt_receptors: convert receptor CSVs to the standard format
expected by austal_prep.

Supported input formats:

    QGIS Open-ALAQS receptor CSV (default).
        Columns: ID, latitude, longitude, EPSG
        The EPSG column carries the source CRS per row; all rows must
        agree. The standalone reads it directly, no source_epsg arg
        needed. Note: with always_xy=True, the 'longitude' column is
        treated as the x axis and 'latitude' as the y axis. For source
        CRSes other than 4326 (e.g. EPSG:28992 Dutch RD), the column
        names are conventional only; values are still (x, y) for the
        declared CRS.

    Dutch CIMLK receptor list (override).
        Columns: receptor_id, road_name, x_RD, y_RD, ...
        No EPSG column. Pass source_epsg=28992 explicitly and override
        name_col / x_col / y_col to receptor_id / x_RD / y_RD.

Standard receptors.csv expected by austal_prep:
    name    string
    x       float (in target UTM coordinate system, m)
    y       float
    z       float (height above ground, m, default 1.5)

Reprojection is done with pyproj. The target CRS is given by the
study config's utm_epsg (e.g. 32631 for UTM 31N), normally derived
from the airport longitude by the orchestrate layer.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

logger = logging.getLogger(__name__)


def adapt_receptors(
    in_csv: Path,
    out_csv: Path,
    source_epsg: int | None = None,
    target_epsg: int | None = None,
    name_col: str = "ID",
    x_col: str = "longitude",
    y_col: str = "latitude",
    epsg_col: str = "EPSG",
    z_default: float = 1.5,
    domain_bounds: tuple[float, float, float, float] | None = None,
) -> int:
    if target_epsg is None:
        raise ValueError(
            "adapt_receptors requires target_epsg. The orchestrate layer "
            "normally derives this from the airport longitude; if you are "
            "calling adapt_receptors directly, supply target_epsg yourself."
        )

    df = pd.read_csv(in_csv)

    if name_col not in df.columns:
        raise ValueError(f"Column {name_col!r} not in input. Found: {list(df.columns)}")
    if x_col not in df.columns or y_col not in df.columns:
        raise ValueError(
            f"Columns {x_col!r}/{y_col!r} not in input. Found: {list(df.columns)}"
        )

    # Resolve source EPSG. Explicit arg wins, otherwise read from the
    # per-row EPSG column (QGIS format), otherwise raise.
    if source_epsg is None:
        if epsg_col not in df.columns:
            raise ValueError(
                f"source_epsg not provided and no {epsg_col!r} column found "
                f"in input. Found columns: {list(df.columns)}. Either pass "
                f"source_epsg explicitly or add an {epsg_col!r} column."
            )
        nonnull = df[epsg_col].dropna()
        if nonnull.empty:
            raise ValueError(
                f"source_epsg not provided and {epsg_col!r} column is empty."
            )
        try:
            unique_epsg = sorted({int(v) for v in nonnull.unique()})
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"Cannot parse {epsg_col!r} column as integers. "
                f"Found values: {nonnull.unique().tolist()}"
            ) from e
        if len(unique_epsg) > 1:
            raise ValueError(
                f"Receptor CSV contains mixed values in {epsg_col!r} column: "
                f"{unique_epsg}. All rows must use the same CRS."
            )
        source_epsg = unique_epsg[0]

    if source_epsg == target_epsg:
        x_t = df[x_col].astype(float).values
        y_t = df[y_col].astype(float).values
    else:
        transformer = Transformer.from_crs(
            f"EPSG:{source_epsg}",
            f"EPSG:{target_epsg}",
            always_xy=True,
        )
        x_t, y_t = transformer.transform(
            df[x_col].astype(float).values,
            df[y_col].astype(float).values,
        )

    x_t = np.asarray(x_t, dtype=float)
    y_t = np.asarray(y_t, dtype=float)
    names = df[name_col].astype(str).values

    # Optional clip to AUSTAL domain. Bounds are in target_epsg, absolute
    # UTM. AUSTAL stops with "Outside computational area" when fed
    # receptors outside the grid; this filter prevents that by dropping
    # them up front and logging which ones were dropped.
    if domain_bounds is not None:
        x_min, x_max, y_min, y_max = domain_bounds
        mask = (x_t >= x_min) & (x_t <= x_max) & (y_t >= y_min) & (y_t <= y_max)
        n_dropped = int((~mask).sum())
        if n_dropped > 0:
            dropped = names[~mask].tolist()
            preview = (
                dropped
                if len(dropped) <= 20
                else dropped[:20] + [f"... and {len(dropped) - 20} more"]
            )
            logger.warning(
                "%d of %d receptor(s) outside AUSTAL domain "
                "[x in [%.1f, %.1f], y in [%.1f, %.1f]]; dropping: %s",
                n_dropped,
                len(mask),
                x_min,
                x_max,
                y_min,
                y_max,
                ", ".join(preview),
            )
        x_t = x_t[mask]
        y_t = y_t[mask]
        names = names[mask]

    out = pd.DataFrame(
        {
            "name": names,
            "x": x_t,
            "y": y_t,
            "z": z_default,
        }
    )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)
    return len(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("in_csv", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--source-epsg",
        type=int,
        default=None,
        help="Source CRS. If omitted, read from the EPSG "
        "column in the input CSV (QGIS format). "
        "Override for CSVs without that column "
        "(e.g. CIMLK in EPSG:28992).",
    )
    parser.add_argument(
        "--target-epsg",
        type=int,
        required=True,
        help="Target CRS (e.g. 32631 for UTM 31N). When "
        "called from orchestrate this is derived from "
        "the airport longitude.",
    )
    parser.add_argument("--name-col", default="ID")
    parser.add_argument("--x-col", default="longitude")
    parser.add_argument("--y-col", default="latitude")
    parser.add_argument(
        "--epsg-col",
        default="EPSG",
        help="Name of the per-row EPSG column (used only "
        "when --source-epsg is omitted).",
    )
    parser.add_argument("--z-default", type=float, default=1.5)
    parser.add_argument(
        "--domain-bounds",
        type=float,
        nargs=4,
        metavar=("XMIN", "XMAX", "YMIN", "YMAX"),
        default=None,
        help="Absolute UTM bounds (in target CRS) of the "
        "AUSTAL domain. Receptors outside are dropped "
        "with a warning. Normally set by orchestrate "
        "from the .alaqs airport reference and the "
        "grid configuration.",
    )
    args = parser.parse_args(argv)

    n = adapt_receptors(
        args.in_csv,
        args.out,
        source_epsg=args.source_epsg,
        target_epsg=args.target_epsg,
        name_col=args.name_col,
        x_col=args.x_col,
        y_col=args.y_col,
        epsg_col=args.epsg_col,
        z_default=args.z_default,
        domain_bounds=tuple(args.domain_bounds) if args.domain_bounds else None,
    )
    print(f"Wrote {n} receptors to {args.out}")


if __name__ == "__main__":
    main()
