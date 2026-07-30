"""Standalone extractor for engine-test event rows.

Reads the ``engine_test_events`` table, joins to ``shapes_area_sources``
on ``source_id`` for the parent geometry, and returns the join in a
shape ready for ``compute_engine_test.py``.

Filters:
  * ``shapes_area_sources.is_test_site='1'`` (matches the plugin's
    ``AreaSource.isTestSite()``).
  * ``shapes_area_sources.instudy='1'``.
  * ``engine_test_events.instudy='1'``.

Rows whose parent area source has been renamed / deleted (i.e. events
whose ``source_id`` no longer matches any area source) are dropped
silently. This is the same skip-with-warning contract the compute
module uses; the standalone log line reports the drop count so the
user can reconcile.

QGIS-free. Uses raw ``sqlite3`` and mirrors the pattern of
``extract_sources.py``.
"""

from __future__ import annotations

import sqlite3
from typing import Optional


def _wkb_to_wkt_via_shapely(wkb: Optional[bytes]) -> str:
    """Convert SpatiaLite-blob geometry to WKT via shapely. Best-effort:
    returns empty string on any failure (missing shapely, malformed
    blob, or None input). Matches the tolerance policy of
    extract_sources.py.
    """
    if wkb is None:
        return ""
    try:
        # spatialite blob prefix: 4 bytes header, then WKB.
        # shapely wkb reader tolerates trailing bytes on some versions
        # but not on others; strip the SpatiaLite prefix if present.
        raw = bytes(wkb)
        if len(raw) >= 43 and raw[0] == 0x00 and raw[38] == 0x7C:
            # Well-formed SpatiaLite blob. Extract WKB starting at
            # byte 39 (the geometry-type INT32 that starts standard WKB).
            body = raw[39:-1]  # drop trailing 0xFE marker
        else:
            body = raw
        from shapely import wkb as shp_wkb

        geom = shp_wkb.loads(body)
        return geom.wkt if geom is not None else ""
    except Exception:
        return ""


def extract_engine_test_events(conn: sqlite3.Connection) -> list[dict]:
    """Read engine_test_events joined to shapes_area_sources.

    Returns a list of dicts, one per event, with the following keys
    consumed by ``compute_engine_test.py``:

      * ``event_id``, ``source_id``, ``test_id``
      * ``start_datetime``, ``end_datetime`` (ISO 8601 strings)
      * ``aircraft_type``, ``engine_uid``, ``engine_count``
      * ``t_TX_s``, ``t_AP_s``, ``t_CL_s``, ``t_TO_s``
      * ``thrust_mode``, ``instudy`` (event's own; caller has already
        checked the parent source's instudy)
      * ``source_geometry_wkt`` (parent area source WKT; may be empty
        if the geometry blob could not be parsed)
      * ``source_height_m`` (parent area source height)

    Silent skip cases (logged only in aggregate):
      * Event whose ``source_id`` matches no test-site area source
        (parent renamed / deleted / flag flipped).
      * Event or parent with ``instudy='0'``.

    Returns ``[]`` if either table is absent (pre-v1b projects or
    fresh templates without engine_test_events).
    """
    cur = conn.cursor()

    # Both tables must exist. If the schema hasn't been migrated yet,
    # return an empty list rather than raise.
    try:
        cur.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='engine_test_events'"
        )
        if cur.fetchone()[0] == 0:
            print(
                "  [extract_engine_test_events] engine_test_events table absent; "
                "returning empty list"
            )
            return []
        cur.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='shapes_area_sources'"
        )
        if cur.fetchone()[0] == 0:
            print(
                "  [extract_engine_test_events] shapes_area_sources absent; "
                "returning empty list"
            )
            return []
    except sqlite3.OperationalError as e:
        print(f"  [extract_engine_test_events] schema probe failed: {e}")
        return []

    # Detect is_test_site column on shapes_area_sources. Pre-v1b projects
    # (that got the engine_test_events table via manual SQL somehow but
    # not the shapes_area_sources column) would fail without this check.
    src_cols = [r[1] for r in cur.execute("PRAGMA table_info(shapes_area_sources)")]
    if "is_test_site" not in src_cols:
        print(
            "  [extract_engine_test_events] shapes_area_sources lacks is_test_site "
            "column; skipping. Run scripts/migrate_alaqs.py to add it."
        )
        return []

    # Query: LEFT JOIN so we can count orphaned events, then filter.
    cur.execute(
        """
        SELECT e.event_id, e.source_id, e.test_id,
               e.start_datetime, e.end_datetime,
               e.aircraft_type, e.engine_uid, e.engine_count,
               e.t_TX_s, e.t_AP_s, e.t_CL_s, e.t_TO_s,
               e.thrust_mode, e.instudy,
               s.height, s.geometry, s.is_test_site, s.instudy AS source_instudy
        FROM engine_test_events AS e
        LEFT JOIN shapes_area_sources AS s
          ON e.source_id = s.source_id
        """
    )
    cols = [d[0] for d in cur.description]

    events: list[dict] = []
    n_orphan = 0
    n_source_not_test_site = 0
    n_source_out_of_study = 0
    n_event_out_of_study = 0

    for raw in cur.fetchall():
        rec = dict(zip(cols, raw))

        if (
            rec.get("height") is None
            and rec.get("geometry") is None
            and rec.get("is_test_site") is None
        ):
            # LEFT JOIN produced no match: orphaned event.
            n_orphan += 1
            continue

        if str(rec.get("is_test_site") or "0").strip() != "1":
            n_source_not_test_site += 1
            continue

        if str(rec.get("source_instudy") or "1").strip() != "1":
            n_source_out_of_study += 1
            continue

        if str(rec.get("instudy") or "1").strip() != "1":
            n_event_out_of_study += 1
            continue

        events.append(
            {
                "event_id": rec.get("event_id"),
                "source_id": rec.get("source_id"),
                "test_id": rec.get("test_id"),
                "start_datetime": rec.get("start_datetime"),
                "end_datetime": rec.get("end_datetime"),
                "aircraft_type": rec.get("aircraft_type"),
                "engine_uid": rec.get("engine_uid"),
                "engine_count": rec.get("engine_count"),
                "t_TX_s": rec.get("t_TX_s"),
                "t_AP_s": rec.get("t_AP_s"),
                "t_CL_s": rec.get("t_CL_s"),
                "t_TO_s": rec.get("t_TO_s"),
                "thrust_mode": rec.get("thrust_mode") or "snap",
                "instudy": rec.get("instudy") or "1",
                "source_geometry_wkt": _wkb_to_wkt_via_shapely(rec.get("geometry")),
                "source_height_m": float(rec.get("height") or 0.0),
            }
        )

    if n_orphan:
        print(
            f"  [extract_engine_test_events] {n_orphan} event(s) skipped: "
            "source_id not found in shapes_area_sources"
        )
    if n_source_not_test_site:
        print(
            f"  [extract_engine_test_events] {n_source_not_test_site} event(s) "
            "skipped: parent source not flagged is_test_site='1'"
        )
    if n_source_out_of_study:
        print(
            f"  [extract_engine_test_events] {n_source_out_of_study} event(s) "
            "skipped: parent source out of study"
        )
    if n_event_out_of_study:
        print(
            f"  [extract_engine_test_events] {n_event_out_of_study} event(s) "
            "skipped: event out of study"
        )

    print(f"  [extract_engine_test_events] {len(events)} engine-test event(s) kept")
    return events


def extract_engine_test_events_from_path(alaqs_path: str) -> list[dict]:
    """Convenience: open ``alaqs_path``, call ``extract_engine_test_events``,
    close. Mirrors the extract_sources helper of the same shape.
    """
    conn = sqlite3.connect(alaqs_path)
    try:
        return extract_engine_test_events(conn)
    finally:
        conn.close()


__all__ = [
    "extract_engine_test_events",
    "extract_engine_test_events_from_path",
]
