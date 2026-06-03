#!/usr/bin/env python3
"""
Migrate a legacy .alaqs file to the schema expected by the current Open-ALAQS plugin.

Strategy
========
This is a comparative migration tool. It runs in two phases against
the canonical templates that ship with the plugin:

  Phase 1 — schema migration (always runs unless --skip-schema)
      Diffs the source schema against the appropriate template
      (core/templates/project.alaqs for project files,
      core/templates/inventory.alaqs for *_out.alaqs files), produces
      an edit plan, and applies it inside a transaction.

  Phase 2 — reference-data refresh (opt-in via --refresh-reference-data)
      For each table listed in --refresh-tables, replaces the source
      DB's contents with the rows from the corresponding CSV in
      open_alaqs/database/data/. DELETE + INSERT, not merge:
      customizations to refreshed tables WILL BE LOST. Tables holding
      user data (`user_*`, `shapes_*`) are hardcoded as never-refreshable.

Reference template selection (Phase 1)
--------------------------------------
By default the reference is auto-selected by source filename:
  - `*_out.alaqs`                  -> core/templates/inventory.alaqs
  - everything else (project)      -> core/templates/project.alaqs

Pass --reference PATH to override.

Differences handled in Phase 1
------------------------------
  1. Tables present in REFERENCE but missing in SOURCE
     -> CREATE TABLE using REFERENCE's schema.
  2. Tables present in SOURCE but absent from REFERENCE
     -> Reported as "extra"; not dropped by default. Pass --drop-extra-tables
        to remove. SpatiaLite virtual tables (SpatialIndex, KNN2,
        ElementaryGeometries) are silently filtered from both sides
        of the diff — they need the SpatiaLite extension to introspect.
  3. Columns present in REFERENCE but missing from SOURCE
     -> ALTER TABLE ... ADD COLUMN. Column-rename pairs use the RENAMES
        dict (e.g. (horizontal_metres, vertical_metres) -> (x_m, y_m=0, z_m)).
  4. Columns present in SOURCE but absent from REFERENCE
     -> Reported as "extra"; left in place by default. Pass --drop-extra-columns.
  5. Type/affinity differences
     -> Reported but not corrected (SQLite is dynamically typed).

Usage
=====

    python migrate_alaqs.py SOURCE.alaqs [options]

Common options:
    --reference PATH               Override the auto-selected reference template.
    --dry-run                      Print the edit plan(s), do not modify SOURCE.
    --no-backup                    Skip the .bak-<timestamp> copy (DANGEROUS).
    --drop-extra-tables            Remove tables in SOURCE but not in REFERENCE.
    --drop-extra-columns           Remove columns in SOURCE but not in REFERENCE.
    --skip-schema                  Skip Phase 1 (data refresh only).

Phase 2 options:
    --refresh-reference-data       Enable Phase 2.
    --data-dir PATH                Directory containing default_*.csv
                                   (default: open_alaqs/database/data/).
    --refresh-tables T1,T2,...     Comma-separated list of tables to refresh.
                                   Default: 9 "safe" reference tables.
    --refresh-include-user-extensible
                                   Add the 7 user-extensible reference
                                   tables to the refresh list (LOSES
                                   user customizations to those tables).

Exit codes:
    0 — migration applied or nothing to do
    1 — migration failed; original restored from backup if available
    2 — bad arguments / file not found
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import shutil
import sqlite3
import sys
from collections import OrderedDict
from pathlib import Path

# ---------------------------------------------------------------------------
# Special data-preserving column transformations.
#
# Each entry: { table: { (legacy_cols_tuple) : (new_cols_tuple, mapping_sql) } }
#
# mapping_sql is a fragment used inside an INSERT ... SELECT to derive the
# new columns from the old. Use placeholder `{src}` to refer to the source
# table.
# ---------------------------------------------------------------------------

RENAMES = {
    "default_aircraft_profiles": [
        # Legacy 1D axial profile -> rebuilt 3D Cartesian
        {
            "legacy_cols": ("horizontal_metres", "vertical_metres"),
            "new_cols": ("x_m", "y_m", "z_m"),
            # Map: x_m = horizontal_metres, y_m = 0 (always 0 in legacy 1D),
            #      z_m = vertical_metres
            "select_expr": (
                "horizontal_metres AS x_m, "
                "0                 AS y_m, "
                "vertical_metres   AS z_m"
            ),
            # Drop these legacy columns after the conversion
            "drop_after": (
                "weight_lbs",
                "horizontal_feet",
                "horizontal_metres",
                "vertical_feet",
                "vertical_metres",
                "tas_knots",
            ),
        },
    ],
}

# ---------------------------------------------------------------------------
# Reference templates and reference-data location.
# Both default to the plugin's tree layout:
#   open_alaqs/core/templates/{project,inventory}.alaqs
#   open_alaqs/database/data/default_*.csv
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PROJECT = REPO_ROOT / "open_alaqs" / "core" / "templates" / "project.alaqs"
TEMPLATE_INVENTORY = REPO_ROOT / "open_alaqs" / "core" / "templates" / "inventory.alaqs"
DEFAULT_DATA_DIR = REPO_ROOT / "open_alaqs" / "database" / "data"

# Backward-compat alias kept for any external caller that imports it.
DEFAULT_REFERENCE = TEMPLATE_PROJECT


# ---------------------------------------------------------------------------
# Phase 2 (reference-data refresh) configuration
# ---------------------------------------------------------------------------

# "Safe" reference-data tables: pure-reference data, externally maintained,
# users rarely customize. Default selection when --refresh-reference-data
# is passed without --refresh-tables.
DEFAULT_REFRESH_TABLES = (
    "default_airports",
    "default_vehicle_ef_copert5",
    "default_vehicle_fleet_euro_standards",
    "default_aircraft_engine_mode",
    "default_stationary_category",
    "default_stationary_substance",
    "default_stationary_ef",
    "default_emission_dynamics",
    "default_apu_times",
)

# User-extensible reference tables. Users may have added custom rows.
# Refreshing these tables OVERWRITES customizations -- enabled only by
# --refresh-include-user-extensible.
USER_EXTENSIBLE_REFRESH_TABLES = (
    "default_aircraft",
    "default_aircraft_engine_ei",
    "default_aircraft_profiles",
    "default_aircraft_apu_ef",
    "default_aircraft_start_ef",
    "default_gate_profiles",
    "default_helicopter_engine_ei",
)

# Tables that hold user project data. Refreshing any of these would
# destroy the user's work. The guard is unconditional -- it overrides
# --refresh-tables even if the user explicitly names one of these.
USER_DATA_TABLES_FORBIDDEN_FROM_REFRESH = frozenset(
    {
        "user_aircraft_movements",
        "user_study_setup",
        "user_day_profile",
        "user_hour_profile",
        "user_month_profile",
        "user_taxiroute_taxiways",
        # Spatial layers users edit in QGIS:
        "shapes_runways",
        "shapes_taxiways",
        "shapes_gates",
        "shapes_tracks",
        "shapes_parking",
        "shapes_roadways",
        "shapes_buildings",
        "shapes_point_sources",
        "shapes_area_sources",
        "shapes_receptor_points",
    }
)


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------


def get_tables(conn: sqlite3.Connection) -> set[str]:
    """Return user table names, excluding virtual tables.

    Virtual tables (SpatialIndex, KNN2, ElementaryGeometries, R*Tree
    indices, FTS, ...) need the corresponding SQLite extension to load;
    PRAGMA table_info on them fails with "no such module: VirtualXXX"
    in a plain sqlite3 connection. We do not migrate them structurally
    (the runtime SpatiaLite recreates them automatically), so filter
    them out at the schema layer.
    """
    return {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' "
            "AND (sql IS NULL OR sql NOT LIKE 'CREATE VIRTUAL%')"
        )
    }


def get_columns(conn: sqlite3.Connection, table: str) -> "OrderedDict[str, str]":
    """Return an OrderedDict mapping column_name -> declared_type, in DB order."""
    out = OrderedDict()
    for r in conn.execute(f"PRAGMA table_info('{table}')"):
        out[r[1]] = r[2]
    return out


def get_create_sql(conn: sqlite3.Connection, table: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Edit-plan generation
# ---------------------------------------------------------------------------


class EditPlan:
    def __init__(self) -> None:
        self.create_tables: list[tuple[str, str]] = []  # (name, create_sql)
        self.drop_tables: list[str] = []
        self.add_columns: list[tuple[str, str, str]] = []  # (table, col, type)
        self.drop_columns: list[tuple[str, list[str]]] = []  # (table, cols)
        self.transformations: list[tuple[str, dict]] = []  # (table, rename_entry)
        self.warnings: list[str] = []
        self.extras: list[str] = []

    def is_empty(self) -> bool:
        return not (
            self.create_tables
            or self.drop_tables
            or self.add_columns
            or self.drop_columns
            or self.transformations
        )

    def print_summary(self) -> None:
        print("Edit plan")
        print("=========")
        if self.is_empty() and not self.extras and not self.warnings:
            print("  (no changes needed)")
            return
        for name, _sql in self.create_tables:
            print(f"  + CREATE TABLE {name}")
        for name in self.drop_tables:
            print(f"  - DROP TABLE {name}")
        for tbl, col, typ in self.add_columns:
            print(f"  + ADD COLUMN {tbl}.{col} {typ}")
        for tbl, cols in self.drop_columns:
            print(f"  - DROP COLUMNS {tbl}: {sorted(cols)}")
        for tbl, entry in self.transformations:
            print(f"  ~ TRANSFORM {tbl}: {entry['legacy_cols']} -> {entry['new_cols']}")
        for w in self.warnings:
            print(f"  ! WARNING: {w}")
        for e in self.extras:
            print(f"  i {e}")


def diff_schemas(
    src: sqlite3.Connection,
    ref: sqlite3.Connection,
    drop_extra_tables: bool,
    drop_extra_columns: bool,
) -> EditPlan:
    plan = EditPlan()
    src_tables = get_tables(src)
    ref_tables = get_tables(ref)

    # 1. Tables only in REF
    for t in sorted(ref_tables - src_tables):
        sql = get_create_sql(ref, t)
        if sql:
            plan.create_tables.append((t, sql))

    # 2. Tables only in SRC
    for t in sorted(src_tables - ref_tables):
        if drop_extra_tables:
            plan.drop_tables.append(t)
        else:
            plan.extras.append(
                f"table '{t}' exists in source but not in reference; "
                f"left in place (use --drop-extra-tables to remove)"
            )

    # 3 & 4. Per-table column diffs (only for tables present in both)
    for t in sorted(src_tables & ref_tables):
        src_cols = get_columns(src, t)
        ref_cols = get_columns(ref, t)
        only_src = set(src_cols) - set(ref_cols)
        only_ref = set(ref_cols) - set(src_cols)

        # Special transformations first — they consume some legacy/new columns
        consumed_legacy: set[str] = set()
        consumed_new: set[str] = set()
        if t in RENAMES:
            for entry in RENAMES[t]:
                legacy = set(entry["legacy_cols"])
                new = set(entry["new_cols"])
                if legacy.issubset(only_src) and new.issubset(only_ref):
                    plan.transformations.append((t, entry))
                    consumed_legacy |= legacy | set(entry["drop_after"])
                    consumed_new |= new

        # 3. Add missing reference columns (excluding ones consumed by transform)
        remaining_only_ref = only_ref - consumed_new
        for col in remaining_only_ref:
            plan.add_columns.append((t, col, ref_cols[col]))

        # 4. Drop extra source columns (excluding ones to be dropped by transform)
        remaining_only_src = only_src - consumed_legacy
        if remaining_only_src:
            if drop_extra_columns:
                plan.drop_columns.append((t, sorted(remaining_only_src)))
            else:
                plan.extras.append(
                    f"table '{t}' has extra columns {sorted(remaining_only_src)}; "
                    f"left in place (use --drop-extra-columns to remove)"
                )

        # 5. Type differences (warning only)
        for col in src_cols.keys() & ref_cols.keys():
            sa = src_cols[col].strip().upper().replace(" ", "")
            ra = ref_cols[col].strip().upper().replace(" ", "")
            if sa != ra and sa and ra:
                plan.warnings.append(
                    f"{t}.{col}: source type '{src_cols[col]}' differs from "
                    f"reference '{ref_cols[col]}' (left unchanged)"
                )

    return plan


# ---------------------------------------------------------------------------
# Applying edits
# ---------------------------------------------------------------------------


def apply_create_table(conn: sqlite3.Connection, _name: str, create_sql: str) -> None:
    conn.execute(create_sql)


def apply_drop_table(conn: sqlite3.Connection, name: str) -> None:
    conn.execute(f"DROP TABLE {name!r}")


def apply_add_column(conn: sqlite3.Connection, table: str, col: str, typ: str) -> None:
    # Quote column name to be safe against keywords
    conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {typ}')


def apply_drop_columns(
    conn: sqlite3.Connection,
    table: str,
    cols_to_drop: list[str],
    ref: sqlite3.Connection,
) -> None:
    """SQLite < 3.35 has no DROP COLUMN; use the create-copy-rename pattern."""
    keep_cols = OrderedDict(
        (c, t) for c, t in get_columns(conn, table).items() if c not in cols_to_drop
    )
    cols_csv = ", ".join(f'"{c}"' for c in keep_cols)
    new_def = ", ".join(f'"{c}" {t}' for c, t in keep_cols.items())
    conn.execute(f"DROP TABLE IF EXISTS {table}__migtmp")
    conn.execute(f'CREATE TABLE "{table}__migtmp" ({new_def})')
    conn.execute(
        f'INSERT INTO "{table}__migtmp" ({cols_csv}) '
        f'SELECT {cols_csv} FROM "{table}"'
    )
    conn.execute(f'DROP TABLE "{table}"')
    conn.execute(f'ALTER TABLE "{table}__migtmp" RENAME TO "{table}"')


def apply_transformation(
    conn: sqlite3.Connection,
    table: str,
    entry: dict,
    ref: sqlite3.Connection,
) -> None:
    """Run a data-preserving rename via the create-copy-rename pattern."""
    src_cols = get_columns(conn, table)
    drop_set = set(entry["drop_after"])
    new_cols_set = set(entry["new_cols"])

    # Final column list = (src cols not in drop_after) ∪ (entry["new_cols"])
    keep_src = [c for c in src_cols if c not in drop_set and c not in new_cols_set]

    # Get reference types for the new columns
    ref_cols = get_columns(ref, table)
    new_col_defs = [(c, ref_cols.get(c, "DECIMAL")) for c in entry["new_cols"]]

    final_defs = [(c, src_cols[c]) for c in keep_src] + new_col_defs
    final_csv = ", ".join(f'"{c}" {t}' for c, t in final_defs)

    keep_csv = ", ".join(f'"{c}"' for c in keep_src)
    new_csv = ", ".join(f'"{c}"' for c in entry["new_cols"])

    conn.execute(f"DROP TABLE IF EXISTS {table}__migtmp")
    conn.execute(f'CREATE TABLE "{table}__migtmp" ({final_defs and final_csv})')

    select_parts = []
    if keep_src:
        select_parts.append(keep_csv)
    select_parts.append(entry["select_expr"])
    select_clause = ", ".join(select_parts)

    target_csv = (keep_csv + ", " + new_csv) if keep_src else new_csv
    conn.execute(
        f'INSERT INTO "{table}__migtmp" ({target_csv}) '
        f'SELECT {select_clause} FROM "{table}"'
    )
    conn.execute(f'DROP TABLE "{table}"')
    conn.execute(f'ALTER TABLE "{table}__migtmp" RENAME TO "{table}"')


def apply_plan(
    conn: sqlite3.Connection, ref: sqlite3.Connection, plan: EditPlan
) -> None:
    # SpatiaLite views (e.g. geom_cols_ref_sys, vector_layers, ...) and triggers
    # (e.g. ggi_shapes_roadways_geometry, geometry_columns_*_insert, ...) reference
    # the geometry_columns / virts_geometry_columns / views_geometry_columns
    # metadata tables.  When apply_drop_columns or apply_drop_table touches one of
    # those metadata tables it uses the standard "create-temp / copy / drop original
    # / rename" workaround (SQLite < 3.35 has no native DROP COLUMN), and SQLite's
    # schema-consistency check fires on the RENAME step because the dependent views
    # and triggers reference an about-to-disappear table.  The whole transaction
    # then rolls back and the migration silently restores the backup, leaving the
    # user's file unchanged.  We avoid this by snapshotting and dropping any view
    # or trigger that references one of those three metadata tables before applying
    # the plan, then recreating them from the captured DDL at the end.  If anything
    # in the body raises, the BEGIN/COMMIT in main() rolls back and the views and
    # triggers come back along with the rest of the schema, so this is safe.
    spatialite_objects = _capture_spatialite_metadata_dependents(conn)
    for kind, name, _sql in spatialite_objects:
        conn.execute(f'DROP {kind} IF EXISTS "{name}"')

    # Order: create new tables, then per-table column adds/transforms, then column drops, then table drops
    for name, sql in plan.create_tables:
        apply_create_table(conn, name, sql)
    for tbl, col, typ in plan.add_columns:
        apply_add_column(conn, tbl, col, typ)
    for tbl, entry in plan.transformations:
        apply_transformation(conn, tbl, entry, ref)
    for tbl, cols in plan.drop_columns:
        apply_drop_columns(conn, tbl, cols, ref)
    for name in plan.drop_tables:
        apply_drop_table(conn, name)

    # Recreate captured views and triggers.  Skip any whose host table no longer
    # exists (e.g. shapes_aircraft_tracks was dropped by --drop-extra-tables, so
    # ggi_shapes_aircraft_tracks_geometry has nothing to attach to).
    existing_tables = get_tables(conn)
    for kind, name, sql in spatialite_objects:
        if kind == "TRIGGER":
            host = _get_trigger_host_from_ddl(sql)
            if host and host not in existing_tables:
                continue
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as exc:
            # Best-effort: log and continue.  The QGIS plugin doesn't depend on
            # these SpatiaLite-internal validation triggers existing — only on
            # the metadata tables themselves having the expected shape — so
            # losing one (e.g. because the table layout changed) is recoverable.
            print(
                f"WARNING: could not recreate {kind.lower()} '{name}': {exc}",
                file=sys.stderr,
            )

    # Clean up stale rows in SpatiaLite metadata tables that point at tables we
    # just dropped (e.g. a row for shapes_aircraft_tracks remains in
    # geometry_columns after --drop-extra-tables removed the table itself).
    # Leaving stale rows confuses QGIS's spatialite provider which scans these
    # tables to discover layers.
    _clean_stale_spatialite_metadata_rows(conn, existing_tables)


def _clean_stale_spatialite_metadata_rows(
    conn: sqlite3.Connection, existing_tables: set[str]
) -> None:
    """Delete rows from SpatiaLite metadata tables that reference tables which
    no longer exist after migration.  Operates on whichever of the standard
    ``f_table_name``-keyed metadata tables are present in the source.
    """
    metadata_with_table_ref = [
        ("geometry_columns", "f_table_name"),
        ("geometry_columns_auth", "f_table_name"),
        ("geometry_columns_field_infos", "f_table_name"),
        ("geometry_columns_statistics", "f_table_name"),
        ("geometry_columns_time", "f_table_name"),
        ("views_geometry_columns", "f_table_name"),
    ]
    db_tables = get_tables(conn)
    for meta_tbl, fk_col in metadata_with_table_ref:
        if meta_tbl not in db_tables:
            continue
        rows = conn.execute(f'SELECT DISTINCT "{fk_col}" FROM "{meta_tbl}"').fetchall()
        for (ref_name,) in rows:
            if ref_name and ref_name not in existing_tables:
                conn.execute(
                    f'DELETE FROM "{meta_tbl}" WHERE "{fk_col}" = ?', (ref_name,)
                )


# Tables whose columns the SpatiaLite metadata views and triggers depend on.
# Any view or trigger whose body references one of these tables is dropped
# before plan apply and recreated afterwards (see apply_plan).
_SPATIALITE_METADATA_TABLES = (
    "geometry_columns",
    "virts_geometry_columns",
    "views_geometry_columns",
)


def _capture_spatialite_metadata_dependents(
    conn: sqlite3.Connection,
) -> list[tuple[str, str, str]]:
    """Return [(kind, name, create_sql)] for every view or trigger in the source
    DB whose definition references one of the SpatiaLite metadata tables that
    the plan-apply step may rebuild via the create-copy-rename pattern.

    `kind` is the SQL keyword used for DROP/CREATE: ``"VIEW"`` or ``"TRIGGER"``.
    """
    captured: list[tuple[str, str, str]] = []
    rows = conn.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE type IN ('view', 'trigger') AND sql IS NOT NULL"
    ).fetchall()
    for type_, name, sql in rows:
        if any(tbl in sql for tbl in _SPATIALITE_METADATA_TABLES):
            captured.append((type_.upper(), name, sql))
    return captured


def _get_trigger_host_from_ddl(sql: str) -> str | None:
    """Best-effort extract the host-table name from a CREATE TRIGGER statement.

    Looks for ``ON "<name>"`` or ``ON <name>`` after the trigger event keyword.
    Returns None if the pattern is unrecognised.
    """
    # Normalise whitespace then search for the ON clause.
    import re

    m = re.search(
        r'\s+ON\s+(?:"([^"]+)"|\'([^\']+)\'|([A-Za-z_][A-Za-z0-9_]*))',
        sql,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    return m.group(1) or m.group(2) or m.group(3)


# ---------------------------------------------------------------------------
# Phase 3 — point-sources v2 hooks
# ---------------------------------------------------------------------------
# Two small post-migration steps tied to the point-sources v2 schema
# additions:
#
#   1. The three v2 temporal profiles (`heating_season`,
#      `cooling_season`, `business_hours`) live in the canonical
#      template files (built into `core/templates/project.alaqs` and
#      `inventory.alaqs`). New studies inherit them automatically.
#      Existing studies, migrated through Phase 1, need an explicit
#      INSERT OR IGNORE step because `user_*_profile` tables are in
#      `USER_DATA_TABLES_FORBIDDEN_FROM_REFRESH` (Phase 2 cannot
#      touch them) — the user's existing custom profiles must be
#      preserved, but the three v2 system profiles can be appended
#      idempotently.
#
#   2. A migration report identifying in-study shapes_point_sources
#      rows whose EF fingerprint matches a `deprecated=1` row in
#      `default_stationary_ef`. Read-only. Output is a CSV next to
#      the source file (or `--report-deprecated-pins=PATH`).

# Three v2 profiles. Use h01..h24 (1-indexed) per the schema.
POINT_SOURCES_V2_PROFILES = {
    "user_month_profile": {
        "cols": [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ],
        "rows": {
            "heating_season": [
                2.00,
                1.80,
                1.40,
                0.70,
                0.30,
                0.10,
                0.05,
                0.05,
                0.30,
                0.80,
                1.50,
                1.90,
            ],
            "cooling_season": [
                0.20,
                0.20,
                0.30,
                0.50,
                0.90,
                1.40,
                1.80,
                1.80,
                1.20,
                0.60,
                0.30,
                0.20,
            ],
            "business_hours": [
                1.00,
                1.00,
                1.00,
                1.00,
                1.00,
                1.00,
                1.00,
                1.00,
                1.00,
                1.00,
                1.00,
                1.00,
            ],
        },
    },
    "user_day_profile": {
        "cols": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "rows": {
            "heating_season": [1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00],
            "cooling_season": [1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00],
            "business_hours": [1.20, 1.20, 1.20, 1.20, 1.20, 0.40, 0.40],
        },
    },
    "user_hour_profile": {
        "cols": [f"h{i:02d}" for i in range(1, 25)],
        "rows": {
            "heating_season": [1.0] * 24,
            "cooling_season": [
                0.4,
                0.3,
                0.3,
                0.3,
                0.3,
                0.4,
                0.6,
                0.8,
                1.0,
                1.2,
                1.4,
                1.6,
                1.8,
                2.0,
                2.0,
                2.0,
                1.8,
                1.5,
                1.2,
                1.0,
                0.8,
                0.6,
                0.5,
                0.4,
            ],
            "business_hours": [
                0.2,
                0.2,
                0.2,
                0.2,
                0.2,
                0.2,
                0.5,
                1.5,
                1.5,
                1.5,
                1.5,
                1.5,
                1.5,
                1.5,
                1.5,
                1.5,
                1.5,
                1.5,
                1.5,
                1.0,
                0.5,
                0.3,
                0.2,
                0.2,
            ],
        },
    },
}


def insert_point_sources_v2_profiles(conn: sqlite3.Connection) -> dict:
    """Insert the three v2 temporal profiles into each `user_*_profile`
    table where they are not already present. Idempotent on
    profile_name. Returns {table: [inserted_profile_names]}.

    Safe to call on any .alaqs file: tables that do not exist are
    silently skipped (logged), and existing profile rows are never
    overwritten.
    """
    summary: dict = {}
    tables_present = get_tables(conn)
    for table, spec in POINT_SOURCES_V2_PROFILES.items():
        if table not in tables_present:
            summary[table] = []
            continue
        inserted = []
        for name, values in spec["rows"].items():
            present = conn.execute(
                f"SELECT 1 FROM {table} WHERE profile_name = ?", (name,)
            ).fetchone()
            if present:
                continue
            placeholders = ", ".join(["?"] * (1 + len(spec["cols"])))
            conn.execute(
                f"INSERT INTO {table} (profile_name, {', '.join(spec['cols'])}) "
                f"VALUES ({placeholders})",
                [name] + values,
            )
            inserted.append(name)
        summary[table] = inserted
    return summary


# ---------------------------------------------------------------------------
# Phase 3 — deprecated-pin report
# ---------------------------------------------------------------------------
# Helper substitution rules for the recommended_replacement column.
# Keys are case-insensitive substrings tested against the legacy EF
# description. Add entries here when expanding the v2 ruleset.
_DEPRECATED_PIN_REPLACEMENTS = {
    "natural gas : utility": "Natural Gas, Large Wall-Fired >100 MMBtu/hr, Uncontrolled Pre-NSPS",
    "natural gas : industrial": "Natural Gas, Large Wall-Fired >100 MMBtu/hr, Low-NOx burners",
    "natural gas : commercial": "Natural Gas, Small Boilers <100 MMBtu/hr, Uncontrolled",
    "natural gas : domestic": "Natural Gas, Residential <0.3 MMBtu/hr",
    "diesel": "Diesel >600 hp, Open-Chamber, Uncontrolled (verify size class and chamber type)",
}


def _suggest_replacement(category_int: int, description: str) -> str | None:
    desc_l = (description or "").lower()
    for needle, replacement in _DEPRECATED_PIN_REPLACEMENTS.items():
        if needle in desc_l:
            return replacement
    return None


def report_deprecated_pins(
    conn: sqlite3.Connection,
    report_path: Path,
) -> int:
    """Write a CSV listing every in-study `shapes_point_sources` row
    whose EF fingerprint matches a `deprecated=1` row in
    `default_stationary_ef`.

    Fingerprint = (`category_name` -> int via `default_stationary_category`,
    `substance_name` -> int via `default_stationary_substance`,
    `nox_kg_k` rounded to 4 decimal places). HC and other pollutant
    columns are NOT part of the fingerprint because operators
    routinely override them on individual sources after picking an EF
    preset.

    Returns the number of CSV rows written (excluding header).

    Notes:
      - Read-only on the DB.
      - Requires v2 schema (the `deprecated` column on
        `default_stationary_ef`). Returns 0 if the column is missing.
      - Multiple legacy rows may share a fingerprint (e.g. Natural Gas
        Commercial and Domestic both have NOx=1.6); the canonical
        match is the lowest oid and the report's `notes` column
        surfaces siblings.
    """
    import csv as _csv
    from collections import defaultdict as _defaultdict

    # Guard: v2 column must exist on default_stationary_ef
    if not _has_column(conn, "default_stationary_ef", "deprecated"):
        print("  (deprecated column not present; Phase 1 hasn't run yet)")
        with report_path.open("w", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(
                [
                    "source_id",
                    "shapes_point_sources_oid",
                    "shapes_category",
                    "shapes_substance",
                    "current_nox_kg_k",
                    "legacy_ef_oid",
                    "legacy_ef_description",
                    "recommended_replacement_description",
                    "notes",
                ]
            )
        return 0

    legacy_index = _defaultdict(list)
    for oid, cat, sub, nox, desc in conn.execute(
        "SELECT oid, category, SUBSTANCE, nox_kg_k, description "
        "FROM default_stationary_ef WHERE deprecated = 1"
    ):
        try:
            key = (int(cat), int(sub), round(float(nox), 4))
        except (TypeError, ValueError):
            continue
        legacy_index[key].append((oid, cat, desc))

    cat_code = {
        name: int(code)
        for code, name in conn.execute(
            "SELECT category, category_name FROM default_stationary_category"
        )
    }
    sub_code = {
        name: int(code)
        for code, name in conn.execute(
            "SELECT substance, substance_name FROM default_stationary_substance"
        )
    }

    n = 0
    with report_path.open("w", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(
            [
                "source_id",
                "shapes_point_sources_oid",
                "shapes_category",
                "shapes_substance",
                "current_nox_kg_k",
                "legacy_ef_oid",
                "legacy_ef_description",
                "recommended_replacement_description",
                "notes",
            ]
        )
        for sps_oid, source_id, cat_name, sub_name, current_nox in conn.execute(
            "SELECT oid, source_id, category, substance, nox_kg_k "
            "FROM shapes_point_sources WHERE instudy = '1'"
        ):
            cat_int = cat_code.get((cat_name or "").strip())
            sub_int = sub_code.get((sub_name or "").strip())
            if cat_int is None or sub_int is None or current_nox is None:
                continue
            try:
                key = (cat_int, sub_int, round(float(current_nox), 4))
            except (TypeError, ValueError):
                continue
            matches = legacy_index.get(key)
            if not matches:
                continue
            legacy_ef_oid, legacy_cat, legacy_desc = matches[0]
            recommended = _suggest_replacement(legacy_cat, legacy_desc)
            notes = []
            if len(matches) > 1:
                sib = ", ".join(f"oid={m[0]}:{m[2][:40]}" for m in matches[1:])
                notes.append(f"ambiguous fingerprint; also matches {sib}")
            if recommended is None:
                notes.append("no automatic recommendation; review manually")
            desc_l = (legacy_desc or "").lower()
            if (
                "industrial" in desc_l
                and "natural gas" in desc_l
                and abs(float(current_nox) - 2.24) < 1e-3
            ):
                notes.append(
                    "WARNING: legacy 'Industrial' label carries 2.24 kg/10^3 m^3, "
                    "which is AP-42 LOW-NOX BURNER value, not uncontrolled large boiler"
                )
            if "diesel" in desc_l and legacy_cat == 2:
                notes.append(
                    "WARNING: legacy 'Diesel' row used 1000_m3 units; new IC Engine "
                    "row uses operating HOURS. Re-verify activity quantity unit."
                )
            w.writerow(
                [
                    source_id,
                    sps_oid,
                    cat_name,
                    sub_name,
                    current_nox,
                    legacy_ef_oid,
                    legacy_desc,
                    recommended or "",
                    " | ".join(notes),
                ]
            )
            n += 1
    return n


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """True iff `column` is present on `table`."""
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def make_backup(db_path: Path) -> Path:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = db_path.with_suffix(f".bak-{ts}{db_path.suffix}")
    shutil.copy2(db_path, bak)
    return bak


def verify_after(
    conn: sqlite3.Connection, plan: EditPlan, ref: sqlite3.Connection
) -> None:
    """Sanity-check the migrated DB against the reference."""
    for t in (n for n, _ in plan.create_tables):
        rows = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        # Newly-created tables should be empty (no data was copied)
        if rows != 0:
            raise RuntimeError(
                f"Created table '{t}' is unexpectedly non-empty ({rows} rows)"
            )
    for tbl, _entry in plan.transformations:
        # Cross-check column set
        present = set(get_columns(conn, tbl))
        ref_cols = set(get_columns(ref, tbl))
        for c in ref_cols:
            if c not in present:
                raise RuntimeError(
                    f"After transformation, '{tbl}' is still missing column '{c}'"
                )


# ---------------------------------------------------------------------------
# Reference template auto-selection
# ---------------------------------------------------------------------------


def select_template_for(source_path: Path) -> Path:
    """Pick the canonical template that matches `source_path` by name.
    Files ending in `_out.alaqs` migrate to inventory.alaqs; everything
    else to project.alaqs."""
    if source_path.name.lower().endswith("_out.alaqs"):
        return TEMPLATE_INVENTORY
    return TEMPLATE_PROJECT


# ---------------------------------------------------------------------------
# Phase 2 — reference-data refresh
# ---------------------------------------------------------------------------


def _resolve_refresh_tables(requested: list) -> list:
    """Strip user-data tables from the requested refresh list with a
    loud warning. Returns the sanitized list."""
    out = []
    for t in requested:
        if t in USER_DATA_TABLES_FORBIDDEN_FROM_REFRESH:
            print(
                f"  ! REFUSING to refresh user-data table '{t}'. "
                f"This table holds user project data and is hardcoded as "
                f"never-refreshable. Drop it from --refresh-tables.",
                file=sys.stderr,
            )
            continue
        out.append(t)
    return out


def refresh_one_table(
    conn: sqlite3.Connection,
    table: str,
    csv_path: Path,
) -> tuple:
    """Replace `table`'s contents with the rows from `csv_path`.
    Returns (rows_before, rows_after)."""
    rows_before = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)

    db_cols = list(get_columns(conn, table).keys())
    db_col_types = get_columns(conn, table)
    db_col_set = set(db_cols)
    common_cols = [c for c in header if c in db_col_set]
    common_indices = [header.index(c) for c in common_cols]

    if not common_cols:
        raise RuntimeError(
            f"refresh of '{table}': no overlap between CSV columns "
            f"({header}) and DB columns ({db_cols})"
        )

    quoted_cols = ", ".join(f'"{c}"' for c in common_cols)
    placeholders = ", ".join(["?"] * len(common_cols))
    insert_sql = f'INSERT INTO "{table}" ({quoted_cols}) VALUES ({placeholders})'

    # Per-column coercion. csv.reader yields strings only; SQLite NUMERIC
    # affinity rescues columns declared INT/NUM/REAL/FLOAT, but columns
    # with no declared type (BLOB affinity) keep whatever Python type we
    # bind, so we must coerce numeric strings ourselves. Declared-TEXT
    # columns are left alone so values like aircraft codes ("737") are
    # not silently turned into integers.
    def _build_coercer(col_type):
        t = (col_type or "").upper()
        if "TEXT" in t or "CHAR" in t or "CLOB" in t:
            # Pure string column: never numericize.
            return lambda v: None if v == "" else v

        # BLOB / numeric / no-affinity: best-effort int -> float -> str.
        def _num(v):
            if v == "":
                return None
            try:
                return int(v)
            except ValueError:
                pass
            try:
                return float(v)
            except ValueError:
                pass
            return v

        return _num

    coercers = [_build_coercer(db_col_types[c]) for c in common_cols]

    conn.execute(f'DELETE FROM "{table}"')
    for row in rows:
        if len(row) < max(common_indices) + 1:
            continue
        values = tuple(coercers[i](row[idx]) for i, idx in enumerate(common_indices))
        conn.execute(insert_sql, values)

    rows_after = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    return rows_before, rows_after


def refresh_reference_data(
    conn: sqlite3.Connection,
    refresh_list: list,
    data_dir: Path,
) -> int:
    """Run Phase 2. Returns the number of tables successfully refreshed."""
    count = 0
    for table in refresh_list:
        if table not in get_tables(conn):
            print(
                f"  ! '{table}': table not in source DB after Phase 1; "
                f"skipping refresh",
                file=sys.stderr,
            )
            continue

        csv_path = data_dir / f"{table}.csv"
        if not csv_path.is_file():
            print(
                f"  ! '{table}': CSV not found at {csv_path}; skipping refresh",
                file=sys.stderr,
            )
            continue

        try:
            before, after = refresh_one_table(conn, table, csv_path)
        except Exception as exc:
            print(f"  ! '{table}': refresh failed: {exc}", file=sys.stderr)
            raise  # let the outer transaction roll back

        if before == after:
            print(f"  {table:<42} {before:>6} rows -> {after:>6} rows (unchanged)")
        else:
            delta = after - before
            sign = "+" if delta > 0 else ""
            print(
                f"  {table:<42} {before:>6} rows -> {after:>6} rows " f"({sign}{delta})"
            )
        count += 1
    return count


def main(argv: list[str]) -> int:  # noqa: C901
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("alaqs_path", type=Path, help="Path to .alaqs to migrate")
    parser.add_argument(
        "--reference",
        type=Path,
        default=None,
        help="Reference .alaqs (default: auto-select by suffix — "
        "core/templates/inventory.alaqs for *_out.alaqs, "
        "core/templates/project.alaqs otherwise)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print plan only; do not modify SOURCE"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the .bak-<timestamp> copy (DANGEROUS)",
    )
    parser.add_argument(
        "--drop-extra-tables",
        action="store_true",
        help="Remove tables in SOURCE not present in REFERENCE",
    )
    parser.add_argument(
        "--drop-extra-columns",
        action="store_true",
        help="Remove columns in SOURCE not present in REFERENCE",
    )
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Skip Phase 1 (schema migration). Useful for " "data-only refresh runs.",
    )
    parser.add_argument(
        "--refresh-reference-data",
        action="store_true",
        help="Enable Phase 2: replace contents of the tables in "
        "--refresh-tables with rows from CSVs in --data-dir.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Directory containing default_*.csv reference data "
        f"(default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--refresh-tables",
        type=str,
        default=None,
        help="Comma-separated list of tables to refresh in Phase 2. "
        f"Default: the {len(DEFAULT_REFRESH_TABLES)} 'safe' "
        f"reference tables ({', '.join(DEFAULT_REFRESH_TABLES)}).",
    )
    parser.add_argument(
        "--refresh-include-user-extensible",
        action="store_true",
        help="Add the 7 user-extensible reference tables "
        "(default_aircraft, default_aircraft_engine_ei, ...) "
        "to the refresh list. WILL OVERWRITE user customizations.",
    )
    parser.add_argument(
        "--skip-point-sources-v2",
        action="store_true",
        help="Skip Phase 3: the point-sources v2 hook that "
        "INSERT-OR-IGNOREs the three named temporal profiles "
        "(heating_season, cooling_season, business_hours) into "
        "user_*_profile. Default: enabled. Skip only if you know your "
        "study predates the v2 schema and you want to keep it in v1 "
        "shape.",
    )
    parser.add_argument(
        "--report-deprecated-pins",
        nargs="?",
        const="AUTO",
        default=None,
        metavar="PATH",
        help="Emit a CSV listing in-study shapes_point_sources rows "
        "whose EF fingerprint matches a deprecated default_stationary_ef "
        "row. Requires the v2 schema (run with Phase 1 first if the "
        "study is pre-v2). Pass a path explicitly, or omit the value to "
        "write to migration_<source-basename>.csv in the source's "
        "directory.",
    )
    args = parser.parse_args(argv)

    # File existence checks
    if not args.alaqs_path.exists() or not args.alaqs_path.is_file():
        print(f"ERROR: source file not found: {args.alaqs_path}", file=sys.stderr)
        return 2

    # Auto-select the reference template if not provided.
    if args.reference is None:
        args.reference = select_template_for(args.alaqs_path)
        print(
            f"Auto-selected reference: {args.reference.name} "
            f"(based on source filename '{args.alaqs_path.name}')"
        )

    if not args.reference.exists() or not args.reference.is_file():
        print(f"ERROR: reference file not found: {args.reference}", file=sys.stderr)
        return 2

    # Resolve Phase 2 settings
    refresh_list: list = []
    if args.refresh_reference_data:
        if args.refresh_tables:
            requested = [t.strip() for t in args.refresh_tables.split(",") if t.strip()]
        else:
            requested = list(DEFAULT_REFRESH_TABLES)
            if args.refresh_include_user_extensible:
                requested.extend(USER_EXTENSIBLE_REFRESH_TABLES)
        refresh_list = _resolve_refresh_tables(requested)

        if not args.data_dir.is_dir():
            print(
                f"ERROR: --data-dir not found or not a directory: {args.data_dir}",
                file=sys.stderr,
            )
            return 2

        # Pre-check that all needed CSVs exist
        missing = [
            t for t in refresh_list if not (args.data_dir / f"{t}.csv").is_file()
        ]
        if missing:
            print(
                f"ERROR: --refresh-tables references CSVs missing from "
                f"{args.data_dir}: {missing}",
                file=sys.stderr,
            )
            return 2

    if args.skip_schema and not args.refresh_reference_data:
        print(
            "ERROR: --skip-schema with no --refresh-reference-data has nothing "
            "to do.",
            file=sys.stderr,
        )
        return 2

    # Open connections
    src = sqlite3.connect(args.alaqs_path)
    ref = sqlite3.connect(args.reference)

    # ----- Phase 1: schema diff + plan -----
    plan: EditPlan | None = None
    if not args.skip_schema:
        try:
            plan = diff_schemas(
                src,
                ref,
                drop_extra_tables=args.drop_extra_tables,
                drop_extra_columns=args.drop_extra_columns,
            )
            print("=== Phase 1: schema migration ===")
            plan.print_summary()
        except Exception as exc:
            print(f"ERROR: schema diff failed: {exc}", file=sys.stderr)
            ref.close()
            src.close()
            return 1

        if args.dry_run and not args.refresh_reference_data:
            print("\n--dry-run: no changes applied.")
            ref.close()
            src.close()
            return 0
    else:
        print("=== Phase 1: SKIPPED (--skip-schema) ===")

    # If Phase 2 isn't enabled and Phase 1 has nothing to do, we're done.
    if not args.refresh_reference_data and plan is not None and plan.is_empty():
        ref.close()
        src.close()
        print("\nNothing to do.")
        return 0

    # ----- Backup before any write -----
    bak_path: Path | None = None
    if not args.dry_run and not args.no_backup:
        bak_path = make_backup(args.alaqs_path)
        print(f"\nBackup written: {bak_path}")
    elif args.no_backup and not args.dry_run:
        print("\nWARNING: --no-backup specified; original will be modified in place.")

    if args.dry_run:
        # Phase 2 in dry-run mode: just show what we'd do.
        if args.refresh_reference_data:
            print("\n=== Phase 2: reference data refresh (dry-run) ===")
            print(f"  data_dir: {args.data_dir}")
            print(f"  tables to refresh ({len(refresh_list)}): {refresh_list}")
        if not args.skip_point_sources_v2:
            print("\n=== Phase 3: point-sources v2 profiles (dry-run) ===")
            print(
                "  Would INSERT-OR-IGNORE: heating_season, cooling_season, "
                "business_hours into user_month/day/hour_profile."
            )
        if args.report_deprecated_pins is not None:
            print("\n=== Phase 3 report (dry-run) ===")
            if args.report_deprecated_pins == "AUTO":
                report_path = (
                    args.alaqs_path.parent / f"migration_{args.alaqs_path.stem}.csv"
                )
            else:
                report_path = Path(args.report_deprecated_pins)
            print(f"  Would write deprecated-pin report to: {report_path}")
        print("\n--dry-run: no changes applied.")
        ref.close()
        src.close()
        return 0

    # ----- Apply Phase 1 -----
    try:
        if plan is not None and not plan.is_empty():
            src.execute("BEGIN")
            apply_plan(src, ref, plan)
            verify_after(src, plan, ref)
            src.execute("COMMIT")
            print("\nPhase 1 applied.")

        # ----- Phase 2 -----
        if args.refresh_reference_data:
            if not refresh_list:
                print("\n=== Phase 2: SKIPPED (refresh list empty after guard) ===")
            else:
                print("\n=== Phase 2: reference data refresh ===")
                src.execute("BEGIN")
                n = refresh_reference_data(src, refresh_list, args.data_dir)
                src.execute("COMMIT")
                print(f"\nPhase 2 applied: {n} table(s) refreshed.")

        # ----- Phase 3: point-sources v2 hooks -----
        # Always runs unless explicitly skipped. The
        # INSERT-OR-IGNORE semantics make it safe to run on any
        # study (pre-v2 or already v2).
        if not args.skip_point_sources_v2:
            print("\n=== Phase 3: point-sources v2 profiles ===")
            src.execute("BEGIN")
            summary = insert_point_sources_v2_profiles(src)
            src.execute("COMMIT")
            for table, inserted in summary.items():
                if inserted:
                    print(f"  {table}: inserted {inserted}")
                else:
                    print(f"  {table}: already present (or table absent)")
        else:
            print("\n=== Phase 3: SKIPPED (--skip-point-sources-v2) ===")

        # ----- Optional: deprecated-pin report -----
        # Runs after Phase 1+2+3 so the DB is in v2 shape before the
        # fingerprint match. Read-only on the source.
        if args.report_deprecated_pins is not None:
            print("\n=== Phase 3 report: deprecated-pin scan ===")
            if args.report_deprecated_pins == "AUTO":
                report_path = (
                    args.alaqs_path.parent / f"migration_{args.alaqs_path.stem}.csv"
                )
            else:
                report_path = Path(args.report_deprecated_pins)
            n_pins = report_deprecated_pins(src, report_path)
            print(f"  Wrote {n_pins} in-study sources to {report_path}")

        # VACUUM outside any transaction
        try:
            src.execute("VACUUM")
        except Exception as exc:
            print(f"VACUUM warning (non-fatal): {exc}")

        print("\nMigration applied successfully.")
        return 0
    except Exception as exc:
        try:
            src.execute("ROLLBACK")
        except Exception:
            pass
        print(f"\nERROR: migration failed: {exc}", file=sys.stderr)
        if bak_path is not None:
            try:
                src.close()
                shutil.copy2(bak_path, args.alaqs_path)
                print(f"Restored original from backup: {bak_path}", file=sys.stderr)
            except Exception as restore_exc:
                print(
                    f"FATAL: could not restore from backup ({restore_exc}). "
                    f"Backup is at {bak_path}",
                    file=sys.stderr,
                )
        return 1
    finally:
        try:
            ref.close()
        except Exception:
            pass
        try:
            src.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
