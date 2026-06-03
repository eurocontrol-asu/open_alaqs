"""
Load sources.parquet and reproject geometries from EPSG:3857 to the
calculation grid CRS (UTM metres).

The sources.parquet schema (produced by `openalaqs_standalone`,
`extract_sources.py`) is:

    source_id     string  prefixed: "road:...", "parking:...", etc.
    source_type   string  road | parking | movement | gate | stationary
    label         string  human-readable name
    geometry_wkt  string  WKT in EPSG:3857
    geometry_kind string  point | line | polygon
    height_m      float   release height above ground
    extent_m2     float   area for polygons; not used here
    length_m      float   line length; not used here
    in_study      bool    skip rows where False
    extra_json    string  source-type-specific attributes (passthrough)

The output is a dict keyed by source_id. Geometry is reprojected to
the grid's UTM EPSG. Sources with in_study=False are dropped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from shapely import wkt as shapely_wkt
from shapely.ops import transform as shapely_transform


def _build_transformer(src_epsg: int, dst_epsg: int):
    """Lazy import of pyproj so the module loads without it for code
    paths that don't need reprojection (e.g. unit tests with synthetic
    grid-CRS WKT)."""
    from pyproj import Transformer

    return Transformer.from_crs(src_epsg, dst_epsg, always_xy=True).transform


def load_sources(
    sources_parquet: Path,
    target_utm_epsg: Optional[int] = None,
    source_epsg: int = 3857,
    reference_x: float = 0.0,
    reference_y: float = 0.0,
) -> Dict[str, dict]:
    """Read sources.parquet and return {source_id: source_dict}.

    target_utm_epsg: if provided, geometries are reprojected from
        source_epsg (default 3857) into the target EPSG. WKTs are
        replaced in-place.

    reference_x, reference_y: after reprojection, all coordinates are
        translated by (-reference_x, -reference_y) so they share the
        same origin as the grid. This must match the GridSpec's
        reference_x/y. Defaults to (0, 0) for tests using synthetic
        WKT already in grid coordinates.

    If target_utm_epsg is None, geometries are returned unchanged
    (apart from the reference translation).
    """
    df = pd.read_parquet(sources_parquet)
    required = {
        "source_id",
        "source_type",
        "geometry_wkt",
        "geometry_kind",
        "height_m",
        "in_study",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"sources.parquet missing required columns: {sorted(missing)}")

    # Drop in_study=False rows
    df = df[df["in_study"].astype(bool)].copy()

    transformer = None
    if target_utm_epsg is not None and target_utm_epsg != source_epsg:
        transformer = _build_transformer(source_epsg, target_utm_epsg)

    needs_translate = reference_x != 0.0 or reference_y != 0.0

    out: Dict[str, dict] = {}
    for row in df.itertuples(index=False):
        wkt = row.geometry_wkt
        if transformer is not None or needs_translate:
            geom = shapely_wkt.loads(wkt)
            if transformer is not None:
                geom = shapely_transform(transformer, geom)
            if needs_translate:
                geom = shapely_transform(
                    lambda x, y, z=None: (
                        (x - reference_x, y - reference_y)
                        if z is None
                        else (x - reference_x, y - reference_y, z)
                    ),
                    geom,
                )
            wkt = geom.wkt
        # NaN-safe float coercion. When sources.parquet is the result
        # of concatenating tables with different columns (aircraft
        # path adds delta_z_m, stationary path does not), the missing
        # entries become NaN. The `x or default` idiom does NOT catch
        # NaN — float('nan') is truthy in Python, so `NaN or 0.0`
        # returns NaN. A NaN height_m or delta_z_m then cascades into
        # compute_cell_weights, producing NaN weights at every (i,j,k)
        # cell, and AUSTAL aborts with "k=20 not in range 1..19!"
        # when casting NaN to a layer index. pd.notna handles both
        # None and NaN.
        _h = getattr(row, "height_m", None)
        height_m = float(_h) if pd.notna(_h) else 0.0
        _dz = getattr(row, "delta_z_m", None)
        delta_z_m = float(_dz) if pd.notna(_dz) else 0.0
        out[row.source_id] = {
            "source_type": row.source_type,
            "label": getattr(row, "label", row.source_id),
            "wkt": wkt,
            "geometry_kind": row.geometry_kind,
            "height_m": height_m,
            # delta_z_m: vertical extent above height_m (m). Optional
            # column. Populated by the aircraft synthetic-source path
            # (austal_aircraft) to encode per-z-layer release; absent
            # (NaN after concat) for stationary sources whose vertical
            # extent is zero.
            "delta_z_m": delta_z_m,
        }
    return out


def load_emissions(
    emissions_parquet: Path,
    source_ids: Optional[set] = None,
    pollutants: Optional[set] = None,
) -> pd.DataFrame:
    """Read emissions.parquet, optionally filtering to a set of
    source_ids and pollutants. Returns the long-form DataFrame.

    Columns: timestamp, source_id, pollutant, kg_in_hour.
    """
    df = pd.read_parquet(emissions_parquet)
    required = {"timestamp", "source_id", "pollutant", "kg_in_hour"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"emissions.parquet missing required columns: {sorted(missing)}"
        )
    if source_ids is not None:
        df = df[df["source_id"].isin(source_ids)]
    if pollutants is not None:
        df = df[df["pollutant"].isin(pollutants)]
    return df
