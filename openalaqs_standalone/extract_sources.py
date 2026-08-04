"""
extract_sources: read source geometries and metadata from an .alaqs
SpatiaLite database and write sources.parquet.

The .alaqs schema stores each source type in its own table:
    shapes_roadways      LINESTRING + COPERT5 fleet/EFs
    shapes_parking       POLYGON + per-vehicle EFs + movement counts
    shapes_gates         POLYGON + idle-time-based EFs
    shapes_point_sources POINT + emission rates
    shapes_area_sources  POLYGON + emission rates
    shapes_buildings     not a source (used for dispersion)

This module flattens all source types into a unified sources.parquet:
    source_id      string  ("road:OostSidelinge_001", "parking:ES.1", ...)
    source_type    string  (road | parking | gate | point | area)
    label          string
    geometry_wkt   string  (in source CRS)
    geometry_kind  string  (line | polygon | point)
    height_m       float64
    extent_m2      float64  (polygon area, line length, or 0 for points)
    length_m       float64  (linestring length, 0 for non-line)
    in_study       bool
    extra_json     string   (per-type metadata, e.g. fleet composition)

Geometries are stored as WKT in EPSG:3857 (Web Mercator), the OpenALAQS
internal projection. Reprojection to AUSTAL grid coordinates happens
later in austal_prep.io.loaders.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

# OpenALAQS uses EPSG:3857 internally for SpatiaLite geometries
ALAQS_INTERNAL_EPSG = 3857


def _wkb_to_wkt_via_shapely(wkb_bytes: bytes) -> tuple[str, str, float, float]:
    """Decode SpatiaLite blob (or raw WKB) and return (wkt, kind, length_m, area_m2).

    SpatiaLite blob format:
        byte 0:        0x00 (start marker)
        byte 1:        endian (0x01 LE, 0x00 BE)
        bytes 2-5:     SRID (int32 in given endian)
        bytes 6-37:    minimum bounding rectangle (4 doubles, 32 bytes)
        byte 38:       0x7C (MBR/WKB separator)
        bytes 39..-2:  WKB body WITHOUT its leading endian byte
                       (the blob's byte 1 is reused as the WKB endian)
        byte -1:       0xFE (end marker)

    Standard WKB starts with a byte order byte directly. We detect
    SpatiaLite blobs by the leading 0x00 + endian + 0x7C-at-offset-38
    pattern.
    """
    from shapely.wkb import loads as wkb_loads

    if not wkb_bytes:
        return ("", "unknown", 0.0, 0.0)

    geom = None
    if (
        len(wkb_bytes) >= 40
        and wkb_bytes[0] == 0x00
        and wkb_bytes[1] in (0x00, 0x01)
        and wkb_bytes[38] == 0x7C
    ):
        endian = wkb_bytes[1]
        wkb = bytes([endian]) + wkb_bytes[39:-1]
        try:
            geom = wkb_loads(wkb)
        except Exception:
            geom = None

    if geom is None:
        try:
            geom = wkb_loads(wkb_bytes)
        except Exception:
            return ("", "unknown", 0.0, 0.0)

    wkt = geom.wkt
    geom_type = geom.geom_type.lower()
    if "linestring" in geom_type:
        kind = "line"
        length_m = float(geom.length)
        area_m2 = 0.0
    elif "polygon" in geom_type:
        kind = "polygon"
        length_m = 0.0
        area_m2 = float(geom.area)
    elif "point" in geom_type:
        kind = "point"
        length_m = 0.0
        area_m2 = 0.0
    else:
        kind = geom_type
        length_m = 0.0
        area_m2 = 0.0
    return wkt, kind, length_m, area_m2


def _extract_roadways(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM shapes_roadways")
    except sqlite3.OperationalError as e:
        # Some .alaqs studies legitimately have no roadway sources and
        # may not have the table at all (older schema, export-only
        # files, studies set up for aircraft-only). Skip gracefully and
        # let the rest of the pipeline run.
        print(
            f"  [extract_sources] shapes_roadways not present: {e} — skipping roadways"
        )
        return []
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        rec = dict(zip(cols, raw))
        wkt, kind, length_m, area_m2 = _wkb_to_wkt_via_shapely(rec.get("geometry"))
        # length_m is in EPSG:3857, which is geographic-style; for
        # accurate length we'd need to reproject to a metric CRS. The
        # `distance` column in shapes_roadways already stores the
        # planimetric length, so prefer it.
        length_m_db = float(rec.get("distance") or length_m or 0.0)
        rows.append(
            {
                "source_id": f"road:{rec['roadway_id']}",
                "source_type": "road",
                "label": str(rec.get("roadway_id", "")),
                "geometry_wkt": wkt,
                "geometry_kind": kind,
                "height_m": float(rec.get("height") or 0.0),
                "extent_m2": 0.0,
                "length_m": length_m_db,
                "in_study": str(rec.get("instudy", "1")) in ("1", "True", "true"),
                "extra_json": json.dumps(
                    {
                        "vehicle_year": rec.get("vehicle_year"),
                        "speed_kmh": rec.get("speed"),
                        "pc_p_pct": rec.get("pc_p_percentage"),
                        "pc_d_pct": rec.get("pc_d_percentage"),
                        "lcv_p_pct": rec.get("lcv_p_percentage"),
                        "lcv_d_pct": rec.get("lcv_d_percentage"),
                        "hdt_p_pct": rec.get("hdt_p_percentage"),
                        "hdt_d_pct": rec.get("hdt_d_percentage"),
                        "motorcycle_p_pct": rec.get("motorcycle_p_percentage"),
                        "bus_d_pct": rec.get("bus_d_percentage"),
                        "hour_profile": rec.get("hour_profile"),
                        "daily_profile": rec.get("daily_profile"),
                        "month_profile": rec.get("month_profile"),
                        "method": rec.get("method"),
                        "co_gm_km": rec.get("co_gm_km"),
                        "hc_gm_km": rec.get("hc_gm_km"),
                        "nox_gm_km": rec.get("nox_gm_km"),
                        "sox_gm_km": rec.get("sox_gm_km"),
                        "pm10_gm_km": rec.get("pm10_gm_km"),
                        "p1_gm_km": rec.get("p1_gm_km"),
                        "p2_gm_km": rec.get("p2_gm_km"),
                        "scenario": rec.get("scenario"),
                    },
                    default=str,
                ),
            }
        )
    return rows


def _extract_parking(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM shapes_parking")
    except sqlite3.OperationalError as e:
        print(f"  [extract_sources] shapes_parking not present: {e} — skipping parking")
        return []
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        rec = dict(zip(cols, raw))
        wkt, kind, length_m, area_m2 = _wkb_to_wkt_via_shapely(rec.get("geometry"))
        rows.append(
            {
                "source_id": f"parking:{rec['parking_id']}",
                "source_type": "parking",
                "label": str(rec.get("parking_id", "")),
                "geometry_wkt": wkt,
                "geometry_kind": kind,
                "height_m": float(rec.get("height") or 0.0),
                "extent_m2": area_m2,
                "length_m": 0.0,
                "in_study": str(rec.get("instudy", "1")) in ("1", "True", "true"),
                "extra_json": json.dumps(
                    {
                        "vehicle_year": rec.get("vehicle_year"),
                        "movements_per_year": rec.get("vehicle_year"),
                        "speed_kmh": rec.get("speed"),
                        "distance_km": rec.get("distance"),
                        "idle_time_min": rec.get("idle_time"),
                        "pc_p_pct": rec.get("pc_p_percentage"),
                        "pc_d_pct": rec.get("pc_d_percentage"),
                        "lcv_p_pct": rec.get("lcv_p_percentage"),
                        "lcv_d_pct": rec.get("lcv_d_percentage"),
                        "hdt_p_pct": rec.get("hdt_p_percentage"),
                        "hdt_d_pct": rec.get("hdt_d_percentage"),
                        "motorcycle_p_pct": rec.get("motorcycle_p_percentage"),
                        "bus_d_pct": rec.get("bus_d_percentage"),
                        "hour_profile": rec.get("hour_profile"),
                        "daily_profile": rec.get("daily_profile"),
                        "month_profile": rec.get("month_profile"),
                        "method": rec.get("method"),
                        "co_gm_vh": rec.get("co_gm_vh"),
                        "hc_gm_vh": rec.get("hc_gm_vh"),
                        "nox_gm_vh": rec.get("nox_gm_vh"),
                        "sox_gm_vh": rec.get("sox_gm_vh"),
                        "pm10_gm_vh": rec.get("pm10_gm_vh"),
                        "p1_gm_vh": rec.get("p1_gm_vh"),
                        "p2_gm_vh": rec.get("p2_gm_vh"),
                    },
                    default=str,
                ),
            }
        )
    return rows


def _extract_gates(conn: sqlite3.Connection) -> list[dict]:
    """shapes_gates has no EF columns; gate emissions are derived from
    the aircraft movements via default_gate_profiles (see
    compute_gate_movements). We still expose the gate geometry and
    metadata in sources.parquet so downstream tools can reason about
    gate placement; the emissions for those gates come from the
    movement path.
    """
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM shapes_gates")
    except sqlite3.OperationalError as e:
        print(f"  [extract_sources] shapes_gates not present: {e} — skipping gates")
        return []
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        rec = dict(zip(cols, raw))
        wkt, kind, length_m, area_m2 = _wkb_to_wkt_via_shapely(rec.get("geometry"))
        rows.append(
            {
                "source_id": f"gate:{rec['gate_id']}",
                "source_type": "gate",
                "label": str(rec.get("gate_id", "")),
                "geometry_wkt": wkt,
                "geometry_kind": kind,
                "height_m": float(rec.get("gate_height") or 0.0),
                "extent_m2": area_m2,
                "length_m": 0.0,
                "in_study": str(rec.get("instudy", "1")) in ("1", "True", "true"),
                "extra_json": json.dumps(
                    {
                        "gate_type": rec.get("gate_type"),
                    },
                    default=str,
                ),
            }
        )
    return rows


def _extract_point_sources(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM shapes_point_sources")
    except sqlite3.OperationalError as e:
        print(
            f"  [extract_sources] shapes_point_sources not present: {e} — skipping point sources"
        )
        return []
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        rec = dict(zip(cols, raw))
        wkt, kind, length_m, area_m2 = _wkb_to_wkt_via_shapely(rec.get("geometry"))
        raw_id = rec.get("source_id") or rec.get("oid")
        rows.append(
            {
                "source_id": f"point:{raw_id}",
                "source_type": "point",
                "label": str(raw_id),
                "geometry_wkt": wkt,
                "geometry_kind": kind,
                "height_m": float(rec.get("height") or 0.0),
                "extent_m2": 0.0,
                "length_m": 0.0,
                "in_study": str(rec.get("instudy", "1")) in ("1", "True", "true"),
                "extra_json": json.dumps(
                    {
                        "category": rec.get("category"),
                        "point_type": rec.get("point_type"),
                        "substance": rec.get("substance"),
                        "temperature": rec.get("temperature"),
                        "diameter": rec.get("diameter"),
                        "velocity": rec.get("velocity"),
                        "ops_year": rec.get("ops_year"),
                        "hour_profile": rec.get("hour_profile"),
                        "daily_profile": rec.get("daily_profile"),
                        "month_profile": rec.get("month_profile"),
                        "co_kg_k": rec.get("co_kg_k"),
                        "hc_kg_k": rec.get("hc_kg_k"),
                        "nox_kg_k": rec.get("nox_kg_k"),
                        "sox_kg_k": rec.get("sox_kg_k"),
                        "pm10_kg_k": rec.get("pm10_kg_k"),
                        "p1_kg_k": rec.get("p1_kg_k"),
                        "p2_kg_k": rec.get("p2_kg_k"),
                    },
                    default=str,
                ),
            }
        )
    return rows


def _extract_area_sources(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM shapes_area_sources")
    except sqlite3.OperationalError as e:
        print(
            f"  [extract_sources] shapes_area_sources not present: {e} — skipping area sources"
        )
        return []
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        rec = dict(zip(cols, raw))

        # Engine-test sites (is_test_site='1') get emitted with
        # source_id "engine_test:<oid>" and source_type "engine_test"
        # instead of "area:<oid>" / "area". This lets `orchestrate.py`
        # dispatch to `compute_engine_test_emissions` for them and keeps
        # their emissions out of the regular area-source compute (which
        # would produce zero anyway since test sites carry no *_kg_unit
        # rates). Downstream `austal_prep` doesn't dispatch on
        # source_type — it uses geometry_kind (polygon) — so the AUSTAL
        # writer treats these the same as regular area sources. The
        # source_id prefix guarantees uniqueness against area sources
        # with the same numeric oid. Pre-v1b projects lacking the
        # column entirely still work: rec.get returns None, str(None) =
        # "None", .strip() = "None", not "1", so those rows fall
        # through to the area path unchanged.
        is_test_site = str(rec.get("is_test_site") or "0").strip()
        source_type = "engine_test" if is_test_site == "1" else "area"
        source_prefix = "engine_test" if is_test_site == "1" else "area"

        wkt, kind, length_m, area_m2 = _wkb_to_wkt_via_shapely(rec.get("geometry"))
        raw_id = rec.get("source_id") or rec.get("oid")
        rows.append(
            {
                "source_id": f"{source_prefix}:{raw_id}",
                "source_type": source_type,
                "label": str(raw_id),
                "geometry_wkt": wkt,
                "geometry_kind": kind,
                "height_m": float(rec.get("height") or 0.0),
                "extent_m2": area_m2,
                "length_m": 0.0,
                "in_study": str(rec.get("instudy", "1")) in ("1", "True", "true"),
                "extra_json": json.dumps(
                    {
                        "unit_year": rec.get("unit_year"),
                        "heat_flux": rec.get("heat_flux"),
                        "hourly_profile": rec.get("hourly_profile"),
                        "daily_profile": rec.get("daily_profile"),
                        "monthly_profile": rec.get("monthly_profile"),
                        "co_kg_unit": rec.get("co_kg_unit"),
                        "hc_kg_unit": rec.get("hc_kg_unit"),
                        "nox_kg_unit": rec.get("nox_kg_unit"),
                        "sox_kg_unit": rec.get("sox_kg_unit"),
                        "pm10_kg_unit": rec.get("pm10_kg_unit"),
                        "p1_kg_unit": rec.get("p1_kg_unit"),
                        "p2_kg_unit": rec.get("p2_kg_unit"),
                        "is_test_site": is_test_site,
                    },
                    default=str,
                ),
            }
        )
    return rows


def extract_sources(alaqs_path: Path, out_path: Optional[Path] = None) -> pd.DataFrame:
    """Read all source types from an .alaqs file and produce a DataFrame.

    If `out_path` is given, write the DataFrame to a parquet file.

    Source types extracted:
        road         from shapes_roadways
        parking      from shapes_parking
        gate         from shapes_gates           (no EFs; movement-driven)
        point        from shapes_point_sources
        area         from shapes_area_sources    (is_test_site='0')
        engine_test  from shapes_area_sources    (is_test_site='1')

    Aircraft tracks (shapes_aircraft_tracks, shapes_tracks,
    cache_runway_trajectories) are not extracted: they are intermediate
    structures used by movement processing, not first-class sources in
    the dispersion model.
    """
    conn = sqlite3.connect(str(alaqs_path))
    try:
        rows = []
        rows.extend(_extract_roadways(conn))
        rows.extend(_extract_parking(conn))
        rows.extend(_extract_gates(conn))
        rows.extend(_extract_point_sources(conn))
        rows.extend(_extract_area_sources(conn))
    finally:
        conn.close()

    df = pd.DataFrame(rows)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, index=False)
    return df


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alaqs_file", type=Path)
    parser.add_argument(
        "--out", type=Path, required=True, help="Output sources.parquet path"
    )
    args = parser.parse_args(argv)

    df = extract_sources(args.alaqs_file, args.out)
    print(f"Wrote {len(df)} sources to {args.out}")
    by_type = df["source_type"].value_counts()
    for t, n in by_type.items():
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()
