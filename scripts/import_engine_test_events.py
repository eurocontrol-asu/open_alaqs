"""Import engine-test events from a CSV into an ALAQS project (CLI).

Consumed by users after they have created their test-site area sources
(``shapes_area_sources.is_test_site='1'``) and want to bulk-load event
rows into ``engine_test_events``.

The importer's core logic lives in
``open_alaqs.core.tools.engine_test_import`` so it can be shared with the
QGIS-plugin dialog (``open_alaqs.openalaqsdialog.OpenAlaqsImportEngineTestEvents``).
This file is only the CLI wrapper: argument parsing, stdout printing,
exit-code mapping. See the core module for CSV-format documentation,
validation semantics, and the full list of error / warning codes.

Modes
-----

Default is dry-run: validate the CSV against the DB, print a summary,
change nothing. Pass ``--apply`` to actually INSERT.

``--mode`` controls what the INSERT does:

  append              Add rows to existing engine_test_events (default)
  replace-for-source  DELETE existing events for each source_id in the
                      CSV, then insert.
  replace-all         DELETE every row in engine_test_events, then
                      insert. Requires ``--i-mean-it`` as a safety
                      flag.

Warnings do NOT reject rows on their own; they abort the whole import
unless ``--tolerate-warnings`` is passed.

Exit codes:
  0  Success (dry-run passed, or apply completed)
  1  Fatal error (CSV parse fail, DB error, invalid arguments)
  2  Validation failed (row errors, or warnings without
     --tolerate-warnings)

Example
-------

  # Dry-run a batch
  python scripts/import_engine_test_events.py \\
      /path/to/study.alaqs /path/to/logbook.csv

  # Apply after review
  python scripts/import_engine_test_events.py \\
      /path/to/study.alaqs /path/to/logbook.csv --apply

  # Re-import a corrected batch for source N1
  python scripts/import_engine_test_events.py \\
      /path/to/study.alaqs /path/to/N1_fix.csv \\
      --apply --mode replace-for-source
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# Add the repo root to sys.path so ``open_alaqs.core.tools`` imports
# work when this script is run directly (``python scripts/import_...``).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Re-export for backward compatibility with any external code that
# imported these names from the CLI module (e.g. the CLI's own test
# file). The core module is the source of truth; these names are only
# aliases.
from open_alaqs.core.tools.engine_test_import import (  # noqa: E402; noqa: E402, F401
    ALL_COLUMNS,
    MODE_TIME_COLUMNS,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    RowIssue,
    ValidatedRow,
    ValidationResult,
    apply_insert,
    format_apply_summary,
    format_summary,
    read_csv,
    validate_against_db,
    validate_csv_rows,
)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Import engine-test events from a CSV into an ALAQS project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("alaqs_path", type=Path, help="Path to the .alaqs project file")
    p.add_argument("csv_path", type=Path, help="Path to the input CSV file")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually INSERT rows. Default is dry-run (validate only, no writes).",
    )
    p.add_argument(
        "--mode",
        choices=("append", "replace-for-source", "replace-all"),
        default="append",
        help="Insert mode (default: append)",
    )
    p.add_argument(
        "--i-mean-it",
        action="store_true",
        help="Required with --mode replace-all. Confirms you accept "
        "that ALL existing engine_test_events rows will be deleted first.",
    )
    p.add_argument(
        "--tolerate-warnings",
        action="store_true",
        help="Proceed even if the CSV has warnings (unknown source_id, "
        "unknown engine_uid, running exceeds window). Default is to "
        "fail on any warning.",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # Precondition: --i-mean-it required for replace-all.
    if args.mode == "replace-all" and args.apply and not args.i_mean_it:
        print(
            "ERROR: --mode replace-all with --apply requires --i-mean-it. "
            "Aborting to protect existing data.",
            file=sys.stderr,
        )
        return 1

    if not args.alaqs_path.exists():
        print(f"ERROR: alaqs file not found: {args.alaqs_path}", file=sys.stderr)
        return 1
    if not args.csv_path.exists():
        print(f"ERROR: CSV file not found: {args.csv_path}", file=sys.stderr)
        return 1

    # Read CSV
    try:
        rows, header_error = read_csv(args.csv_path)
    except Exception as e:
        print(f"ERROR: could not read CSV: {e}", file=sys.stderr)
        return 1
    if header_error is not None:
        print(f"ERROR: {header_error}", file=sys.stderr)
        return 1

    # CSV validation
    result = validate_csv_rows(rows)

    # DB cross-checks
    try:
        conn = sqlite3.connect(args.alaqs_path)
    except sqlite3.Error as e:
        print(f"ERROR: could not open alaqs file: {e}", file=sys.stderr)
        return 1

    try:
        db_warnings = validate_against_db(result.valid_rows, conn)
    finally:
        # Close before any apply; apply reopens with the right
        # transaction semantics.
        pass

    print(format_summary(result, db_warnings, csv_row_count=len(rows)))

    total_warnings = len(result.warnings) + len(db_warnings)

    # Refusal criteria
    if result.errors:
        print("\nFail: rows contain errors. Fix the CSV and re-run.", file=sys.stderr)
        conn.close()
        return 2
    if total_warnings and not args.tolerate_warnings:
        print(
            "\nFail: --tolerate-warnings not set. "
            "Fix the warnings above or re-run with --tolerate-warnings.",
            file=sys.stderr,
        )
        conn.close()
        return 2

    # Dry-run terminates here.
    if not args.apply:
        print("\nDry-run OK. Re-run with --apply to insert.")
        conn.close()
        return 0

    # Apply
    try:
        per_source = apply_insert(conn, result.valid_rows, args.mode)
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        print(f"ERROR: DB write failed, rolled back: {e}", file=sys.stderr)
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(format_apply_summary(per_source, args.mode))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
