"""Core logic for importing engine-test events from a CSV into an
ALAQS project's ``engine_test_events`` table.

This module is dependency-free (stdlib only) and is imported by:
  * ``scripts/import_engine_test_events.py`` (CLI wrapper for
    command-line users, tested by ``tests/test_import_engine_test_events.py``).
  * ``open_alaqs.openalaqsdialog.OpenAlaqsImportEngineTestEvents`` (the
    QGIS-plugin dialog for in-QGIS users).

Both entry points share this validation and apply logic verbatim so
the CLI and the UI never diverge.

CSV format
----------

Header row required. Column order is flexible; the importer maps by
header name. UTF-8 encoding, comma-delimited (RFC 4180). Empty cells
take the column default (not the literal string ``""``).

Columns (all names match the DB schema exactly):

  Required:
    source_id         Test-site area source identifier
    start_datetime    ISO 8601 (e.g. 2024-12-01T09:00:00)
    end_datetime      ISO 8601, strictly after start_datetime
    aircraft_type     ICAO code (e.g. C56X, B738)

  Optional:
    test_id           Free-form user reference
    engine_uid        Engine EI table key. Falls back to aircraft
                      default at compute time if empty
    engine_count      Positive integer. Falls back to aircraft default
                      at compute time if empty
    t_TX_s            Seconds in taxi/ground-idle. Default 0
    t_AP_s            Seconds in approach. Default 0
    t_CL_s            Seconds in climb-out. Default 0
    t_TO_s            Seconds in take-off. Default 0
    instudy           '0' or '1'. Default '1'

Not accepted from CSV:
    thrust_mode       DB column exists with default 'snap'. Users who
                      need 'meem' or 'bffm2' UPDATE via SQL. Not in
                      the CSV because misuse would be silent.

Modes
-----

The caller (CLI or dialog) picks the insert mode:

  append              Add rows to existing engine_test_events
  replace-for-source  DELETE existing events for each source_id in the
                      CSV, then insert. Useful for re-importing a
                      corrected batch for one test site.
  replace-all         DELETE every row in engine_test_events, then
                      insert. Caller must confirm this destructive
                      choice (CLI requires --i-mean-it; dialog shows a
                      confirmation modal).

Warnings vs errors
------------------

Row errors reject a row:
  * missing_required
  * unparseable_datetime
  * end_before_start
  * invalid_mode_time
  * invalid_engine_count
  * invalid_instudy
  * duplicate_row  (same source_id + start_datetime + aircraft_type)

Row warnings do NOT reject a row on their own; the caller decides
whether to abort:
  * unknown_source_id
  * source_not_test_site
  * unknown_aircraft_type
  * unknown_engine_uid
  * running_exceeds_window  (60 s tolerance, matching Phase 2's
    EngineTestEvent.getConsistencyWarnings tolerance)

Whole-CSV errors abort before any validation:
  * Missing required column in header (returned as ``header_error``
    from ``read_csv``).
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

# ── Column contract ────────────────────────────────────────────────────

REQUIRED_COLUMNS = (
    "source_id",
    "start_datetime",
    "end_datetime",
    "aircraft_type",
)

OPTIONAL_COLUMNS = (
    "test_id",
    "engine_uid",
    "engine_count",
    "t_TX_s",
    "t_AP_s",
    "t_CL_s",
    "t_TO_s",
    "instudy",
)

ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

MODE_TIME_COLUMNS = ("t_TX_s", "t_AP_s", "t_CL_s", "t_TO_s")

# Running-seconds tolerance for the running_exceeds_window warning.
# Matches Phase 2's EngineTestEvent.getConsistencyWarnings tolerance.
_RUNNING_EXCEEDS_WINDOW_TOLERANCE_S = 60


# ── Result types ───────────────────────────────────────────────────────


@dataclass
class RowIssue:
    """One error or warning against one CSV row."""

    row_number: int  # 1-indexed, matching how spreadsheet software labels rows
    code: str
    message: str


@dataclass
class ValidatedRow:
    """A row that passed all validation and is ready to insert."""

    row_number: int
    source_id: str
    test_id: Optional[str]
    start_datetime: str
    end_datetime: str
    aircraft_type: str
    engine_uid: Optional[str]
    engine_count: Optional[int]
    t_TX_s: int
    t_AP_s: int
    t_CL_s: int
    t_TO_s: int
    instudy: str

    def to_insert_tuple(self) -> tuple:
        return (
            self.source_id,
            self.test_id,
            self.start_datetime,
            self.end_datetime,
            self.aircraft_type,
            self.engine_uid,
            self.engine_count,
            self.t_TX_s,
            self.t_AP_s,
            self.t_CL_s,
            self.t_TO_s,
            self.instudy,
        )


@dataclass
class ValidationResult:
    valid_rows: list[ValidatedRow] = field(default_factory=list)
    errors: list[RowIssue] = field(default_factory=list)
    warnings: list[RowIssue] = field(default_factory=list)
    header_error: Optional[str] = None


# ── Parsing helpers ────────────────────────────────────────────────────


def _parse_iso_datetime(s: str) -> Optional[datetime]:
    """Parse ISO 8601. Return None on failure so the caller emits a
    single clear error rather than a raw ValueError."""
    if s is None:
        return None
    s = s.strip()
    if s == "":
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _parse_optional_int(s: Optional[str]) -> tuple[bool, Optional[int]]:
    """Return (ok, value). Empty string / None → (True, None). A digit
    string that's non-negative → (True, int). Anything else → (False, None).
    """
    if s is None:
        return True, None
    s = s.strip()
    if s == "":
        return True, None
    try:
        v = int(s)
        return True, v
    except ValueError:
        return False, None


def _parse_mode_seconds(s: Optional[str]) -> tuple[bool, int, Optional[str]]:
    """Parse a t_MODE_s column. Empty → (True, 0, None). Non-negative int
    → (True, v, None). Negative → (False, 0, 'negative_running').
    Malformed → (False, 0, 'not_an_integer')."""
    if s is None:
        return True, 0, None
    s = s.strip()
    if s == "":
        return True, 0, None
    try:
        v = int(s)
    except ValueError:
        return False, 0, "not_an_integer"
    if v < 0:
        return False, 0, "negative_running"
    return True, v, None


# ── CSV → ValidationResult (no DB access) ──────────────────────────────


def validate_csv_rows(
    csv_rows: Iterable[dict[str, str]],
) -> ValidationResult:
    """Validate the CSV without touching the DB. DB cross-checks happen
    downstream in ``validate_against_db``.
    """
    result = ValidationResult()
    seen_dupe_keys: dict[tuple, int] = {}

    for i, row in enumerate(csv_rows, start=2):  # header is line 1
        errs: list[RowIssue] = []

        # Required-value checks
        for col in REQUIRED_COLUMNS:
            val = (row.get(col) or "").strip()
            if val == "":
                errs.append(RowIssue(i, "missing_required", f"column {col!r} is empty"))

        # If any required is missing, skip the rest; row is unusable.
        if errs:
            result.errors.extend(errs)
            continue

        source_id = row["source_id"].strip()
        aircraft_type = row["aircraft_type"].strip()

        # Datetimes
        start_str = row["start_datetime"].strip()
        end_str = row["end_datetime"].strip()
        start_dt = _parse_iso_datetime(start_str)
        end_dt = _parse_iso_datetime(end_str)
        if start_dt is None:
            errs.append(
                RowIssue(
                    i,
                    "unparseable_datetime",
                    f"start_datetime {start_str!r} is not ISO 8601",
                )
            )
        if end_dt is None:
            errs.append(
                RowIssue(
                    i,
                    "unparseable_datetime",
                    f"end_datetime {end_str!r} is not ISO 8601",
                )
            )
        if start_dt is not None and end_dt is not None and end_dt <= start_dt:
            errs.append(
                RowIssue(
                    i,
                    "end_before_start",
                    "end_datetime must be strictly after start_datetime",
                )
            )

        # Duplicate detection: same (source_id, start_datetime, aircraft_type)
        dupe_key = (source_id, start_str, aircraft_type)
        if dupe_key in seen_dupe_keys:
            errs.append(
                RowIssue(
                    i,
                    "duplicate_row",
                    f"same (source_id, start_datetime, aircraft_type) as row "
                    f"{seen_dupe_keys[dupe_key]}",
                )
            )

        # Optional-column parsing
        test_id = (row.get("test_id") or "").strip() or None
        engine_uid = (row.get("engine_uid") or "").strip() or None

        ok_count, engine_count = _parse_optional_int(row.get("engine_count"))
        if not ok_count:
            errs.append(
                RowIssue(
                    i,
                    "invalid_engine_count",
                    f"engine_count {row.get('engine_count')!r} is not an integer",
                )
            )
        elif engine_count is not None and engine_count <= 0:
            errs.append(
                RowIssue(
                    i,
                    "invalid_engine_count",
                    f"engine_count must be a positive integer, got {engine_count}",
                )
            )

        mode_times: dict[str, int] = {}
        for col in MODE_TIME_COLUMNS:
            ok_mt, v_mt, mt_err = _parse_mode_seconds(row.get(col))
            if not ok_mt:
                errs.append(
                    RowIssue(
                        i,
                        "invalid_mode_time",
                        f"{col}={row.get(col)!r}: {mt_err}",
                    )
                )
            mode_times[col] = v_mt

        instudy = (row.get("instudy") or "1").strip()
        if instudy == "":
            instudy = "1"
        if instudy not in ("0", "1"):
            errs.append(
                RowIssue(
                    i,
                    "invalid_instudy",
                    f"instudy {row.get('instudy')!r} must be '0' or '1'",
                )
            )

        if errs:
            result.errors.extend(errs)
            continue

        # Record dupe key only for successfully-validated (so-far) rows.
        seen_dupe_keys[dupe_key] = i

        # Running-seconds vs window warning (D from Phase 2).
        running = sum(mode_times.values())
        if engine_count is not None and engine_count > 0:
            running_total = running * engine_count
        else:
            running_total = running
        window_s = (end_dt - start_dt).total_seconds()
        if running_total > window_s + _RUNNING_EXCEEDS_WINDOW_TOLERANCE_S:
            result.warnings.append(
                RowIssue(
                    i,
                    "running_exceeds_window",
                    f"sum of mode times ({running_total}s across "
                    f"{engine_count or 1} engine(s)) exceeds the "
                    f"event window ({int(window_s)}s) by more than "
                    f"{_RUNNING_EXCEEDS_WINDOW_TOLERANCE_S}s tolerance",
                )
            )

        result.valid_rows.append(
            ValidatedRow(
                row_number=i,
                source_id=source_id,
                test_id=test_id,
                start_datetime=start_str,
                end_datetime=end_str,
                aircraft_type=aircraft_type,
                engine_uid=engine_uid,
                engine_count=engine_count,
                t_TX_s=mode_times["t_TX_s"],
                t_AP_s=mode_times["t_AP_s"],
                t_CL_s=mode_times["t_CL_s"],
                t_TO_s=mode_times["t_TO_s"],
                instudy=instudy,
            )
        )

    return result


def read_csv(csv_path: Path) -> tuple[list[dict[str, str]], Optional[str]]:
    """Read the CSV. Return (rows, header_error). If the header is
    missing a required column, ``header_error`` is set and ``rows`` is
    empty.
    """
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            return [], (
                "CSV header missing required column(s): "
                + ", ".join(missing)
                + f"\n  header seen: {fieldnames}"
                + f"\n  columns expected: {list(ALL_COLUMNS)}"
            )
        rows = list(reader)
    return rows, None


# ── DB cross-checks ────────────────────────────────────────────────────


def _fetch_lookup_sets(conn: sqlite3.Connection) -> dict[str, set]:
    """Read reference tables into sets for O(1) membership checks.
    Missing tables return empty sets and yield no warnings on the
    respective lookups (informative when the DB is un-migrated or
    bare — the caller can still validate structural aspects of the
    CSV even without reference data)."""
    cur = conn.cursor()
    sets: dict[str, set] = {
        "shapes_area_sources": set(),
        "test_site_source_ids": set(),
        "default_aircraft": set(),
        "default_aircraft_engine_ei": set(),
    }

    try:
        for sid, is_test_site in cur.execute(
            "SELECT source_id, is_test_site FROM shapes_area_sources"
        ):
            if sid is None:
                continue
            sets["shapes_area_sources"].add(str(sid))
            if str(is_test_site or "0").strip() == "1":
                sets["test_site_source_ids"].add(str(sid))
    except sqlite3.OperationalError:
        pass  # table absent or is_test_site column absent

    try:
        for (icao,) in cur.execute("SELECT icao FROM default_aircraft"):
            if icao is not None:
                sets["default_aircraft"].add(str(icao))
    except sqlite3.OperationalError:
        pass

    try:
        for (uid,) in cur.execute(
            "SELECT engine_full_name FROM default_aircraft_engine_ei"
        ):
            if uid is not None:
                sets["default_aircraft_engine_ei"].add(str(uid))
    except sqlite3.OperationalError:
        # Try alternate column name
        try:
            for (uid,) in cur.execute(
                "SELECT engine_uid FROM default_aircraft_engine_ei"
            ):
                if uid is not None:
                    sets["default_aircraft_engine_ei"].add(str(uid))
        except sqlite3.OperationalError:
            pass

    return sets


def validate_against_db(
    valid_rows: list[ValidatedRow],
    conn: sqlite3.Connection,
) -> list[RowIssue]:
    """Cross-check each already-CSV-valid row against reference tables
    in the DB. Emits warnings (not errors) so the caller decides whether
    to abort."""
    lookups = _fetch_lookup_sets(conn)
    warnings: list[RowIssue] = []

    for r in valid_rows:
        if r.source_id not in lookups["shapes_area_sources"]:
            warnings.append(
                RowIssue(
                    r.row_number,
                    "unknown_source_id",
                    f"source_id {r.source_id!r} not found in shapes_area_sources",
                )
            )
        elif r.source_id not in lookups["test_site_source_ids"]:
            warnings.append(
                RowIssue(
                    r.row_number,
                    "source_not_test_site",
                    f"source_id {r.source_id!r} exists but is_test_site='0'; "
                    "compute would ignore its events",
                )
            )

        if (
            lookups["default_aircraft"]
            and r.aircraft_type not in lookups["default_aircraft"]
        ):
            warnings.append(
                RowIssue(
                    r.row_number,
                    "unknown_aircraft_type",
                    f"aircraft_type {r.aircraft_type!r} not in default_aircraft",
                )
            )

        if (
            r.engine_uid is not None
            and lookups["default_aircraft_engine_ei"]
            and r.engine_uid not in lookups["default_aircraft_engine_ei"]
        ):
            warnings.append(
                RowIssue(
                    r.row_number,
                    "unknown_engine_uid",
                    f"engine_uid {r.engine_uid!r} not in default_aircraft_engine_ei",
                )
            )

    return warnings


# ── Insert ─────────────────────────────────────────────────────────────


_INSERT_SQL = (
    "INSERT INTO engine_test_events ("
    "source_id, test_id, start_datetime, end_datetime, aircraft_type, "
    "engine_uid, engine_count, t_TX_s, t_AP_s, t_CL_s, t_TO_s, instudy"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def apply_insert(
    conn: sqlite3.Connection,
    rows: list[ValidatedRow],
    mode: str,
) -> dict:
    """Insert rows into engine_test_events under one of the three modes.
    All-or-nothing: uses a single transaction; on any SQLite error the
    caller sees the exception and the DB is rolled back."""
    cur = conn.cursor()

    if mode == "replace-all":
        cur.execute("DELETE FROM engine_test_events")
    elif mode == "replace-for-source":
        source_ids = sorted({r.source_id for r in rows})
        # Chunk the IN() to keep parameter count sane on ancient sqlite
        # builds; 500 is well under any known SQLITE_MAX_VARIABLE_NUMBER.
        for i in range(0, len(source_ids), 500):
            chunk = source_ids[i : i + 500]
            placeholders = ",".join("?" * len(chunk))
            cur.execute(
                f"DELETE FROM engine_test_events WHERE source_id IN ({placeholders})",
                chunk,
            )

    per_source: dict[str, int] = {}
    for r in rows:
        cur.execute(_INSERT_SQL, r.to_insert_tuple())
        per_source[r.source_id] = per_source.get(r.source_id, 0) + 1

    conn.commit()
    return per_source


# ── Reporting ──────────────────────────────────────────────────────────


def format_summary(
    result: ValidationResult,
    db_warnings: list[RowIssue],
    csv_row_count: int,
) -> str:
    """Format a validation summary as plain text. Used by both the CLI
    (printed to stdout) and the dialog (shown in a read-only text
    area).
    """
    lines = []
    total_warnings = len(result.warnings) + len(db_warnings)
    lines.append("Import summary")
    lines.append(f"  CSV rows read:          {csv_row_count}")
    lines.append(f"  Rows valid:             {len(result.valid_rows)}")
    lines.append(f"  Rows rejected:          {len(result.errors)}")
    lines.append(f"  Warnings:               {total_warnings}")

    if result.errors:
        lines.append("")
        lines.append("Errors:")
        for e in result.errors:
            lines.append(f"  Row {e.row_number}: [{e.code}] {e.message}")

    all_warnings = result.warnings + db_warnings
    all_warnings.sort(key=lambda x: (x.row_number, x.code))
    if all_warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in all_warnings:
            lines.append(f"  Row {w.row_number}: [{w.code}] {w.message}")

    return "\n".join(lines)


def format_apply_summary(per_source: dict[str, int], mode: str) -> str:
    lines = ["", f"Applied ({mode}):"]
    total = sum(per_source.values())
    for sid in sorted(per_source):
        lines.append(f"  {sid}: {per_source[sid]} event(s)")
    lines.append(f"  total: {total} event(s) inserted")
    return "\n".join(lines)


__all__ = [
    "REQUIRED_COLUMNS",
    "OPTIONAL_COLUMNS",
    "ALL_COLUMNS",
    "MODE_TIME_COLUMNS",
    "RowIssue",
    "ValidatedRow",
    "ValidationResult",
    "read_csv",
    "validate_csv_rows",
    "validate_against_db",
    "apply_insert",
    "format_summary",
    "format_apply_summary",
]
