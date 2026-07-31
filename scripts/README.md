# `scripts/` — command-line utilities

Standalone utilities for Open-ALAQS users and maintainers. None of them are
invoked by the plugin at run time; they produce or transform the files that
the plugin reads.

## Inventory

| File | Purpose | When to run |
|---|---|---|
| `metar_to_alaqs_meteo.py` | Parse METAR observations into the `meteo.csv` format Open-ALAQS expects during *Create Output*. | Once per study, before inventory creation, to produce the hourly meteorology file. |
| `migrate_alaqs.py` | Upgrade a legacy `.alaqs` file to the current schema. | Whenever a user brings a `.alaqs` produced by an older plugin version and needs to open it with the current one. |
| `migrate_alaqs_gui.py` | Qt5 GUI wrapper around `migrate_alaqs.py`. Exposes every CLI flag plus a live log panel; useful for users uncomfortable with the command line. | Same situations as `migrate_alaqs.py`, when a GUI is preferred. Run with QGIS's bundled Python (e.g. `C:\PROGRA~1\QGIS34~1.13\bin\python.exe migrate_alaqs_gui.py`). |
| `import_engine_test_events.py` | Bulk-load engine run-up events from a CSV into the `engine_test_events` table. | After creating test-site area sources (`is_test_site='1'`) but before generating the emission inventory. |
| `austal_from_csv/` | [BETA] Standalone CLI that produces AUSTAL dispersion-model input files from pre-computed emissions and meteo CSVs (no `.alaqs` needed). See [`austal_from_csv/README.md`](austal_from_csv/README.md). | When you already have emissions/meteo CSVs and want AUSTAL inputs. |
| `emissions_austal/` | [BETA] Standalone CLI that runs the full emissions calculation against a `.alaqs` inventory and optionally generates AUSTAL inputs in one pass. See [`emissions_austal/README.md`](emissions_austal/README.md). | When you want to run the calculator headlessly from an OSGeo4W shell. |
| `update-strings.sh` | Run `pylupdate4` to refresh the `i18n/*.ts` Qt translation source files from `*.py` / `*.ui` changes. | Translation-maintenance workflow; only needed when the plugin UI strings change. |
| `compile-strings.sh` | Run `lrelease` to compile `i18n/*.ts` → `*.qm` binary translation files. | After the `.ts` files have been translated and you want the plugin to pick them up. |
| `run-env-linux.sh` | Shell environment setup for running QGIS 2 from a custom prefix. Legacy; predates QGIS 3 system-wide installs and is kept only for developers on unusual setups. | Rarely. |

## `metar_to_alaqs_meteo.py`

Converts a stream of METAR observations into `meteo.csv` with the columns
Open-ALAQS reads during *Create Output*.  See
[`README_metar_to_alaqs_meteo.md`](README_metar_to_alaqs_meteo.md) for the
full specification: expected meteo.csv schema, METAR parsing details,
supported pressure groups (`Q` in hPa, `A` in inHg × 100), mixing-height
option, and how to swap the in-house parser for the `python-metar` package
if desired.

Quick example:

```bash
python3 scripts/metar_to_alaqs_meteo.py \
    --station EHRD \
    --start 2025-12-01T06:00 \
    --end   2025-12-03T09:00 \
    --scenario "AIRPORT_A training" \
    --input  metar_rotterdam_dec_1_3.txt \
    --output AIRPORT_A_meteo.csv
```

Network access is not required — METAR fetching is deliberately left to the
caller (curl, wget, a Python poller, `python-metar`, etc.). This keeps the
parsing half usable on machines behind restrictive network policies.

## `migrate_alaqs.py`

Two-phase migration tool for upgrading legacy `.alaqs` files to the
current schema.

### Phase 1 — schema migration (always runs unless `--skip-schema`)

Diffs the source schema against the appropriate canonical template and
applies the diff inside a transaction.

The reference template is auto-selected by source filename:

- `*_out.alaqs` → `open_alaqs/core/templates/inventory.alaqs`
- everything else → `open_alaqs/core/templates/project.alaqs`

Pass `--reference PATH` to override the auto-selection.

What Phase 1 handles:

| Case | Default behaviour | Override |
|---|---|---|
| Table in REFERENCE but not in SOURCE | `CREATE TABLE` using REFERENCE's schema (empty table). | — |
| Table in SOURCE but not in REFERENCE | Reported as "extra"; left in place. | `--drop-extra-tables` to remove. |
| Column in REFERENCE but not in SOURCE | `ALTER TABLE ... ADD COLUMN` with REFERENCE's declared type, NULL default. | — |
| Column in SOURCE but not in REFERENCE | Reported as "extra"; left in place. | `--drop-extra-columns` to remove. |
| Type/affinity differences on common columns | Warned, never auto-rewritten (SQLite is dynamically typed). | — |
| Virtual tables (SpatialIndex, KNN2, ElementaryGeometries) | Filtered from both sides of the diff (they need the SpatiaLite extension to introspect; the runtime recreates them). | — |

Registered data-preserving transforms are run for special rename pairs.
The one currently registered is the legacy 1D axial
`default_aircraft_profiles` schema (`horizontal_metres`, `vertical_metres`)
→ 3D Cartesian (`x_m`, `y_m = 0`, `z_m`). Add new entries to the `RENAMES`
dict at the top of the script as the schema evolves.

### Phase 2 — reference-data refresh (opt-in via `--refresh-reference-data`)

Replaces the contents of selected reference tables with the rows from
the matching CSV in `--data-dir` (default: `open_alaqs/database/data/`).
DELETE + INSERT, not merge. Skipped by default.

The default `--refresh-tables` list contains 9 "safe" reference tables
(externally maintained, users rarely customize):

```
default_airports, default_vehicle_ef_copert5,
default_vehicle_fleet_euro_standards, default_aircraft_engine_mode,
default_stationary_category, default_stationary_substance,
default_stationary_ef, default_emission_dynamics, default_apu_times
```

Pass `--refresh-include-user-extensible` to also refresh the 7
user-extensible tables (`default_aircraft`, `default_aircraft_engine_ei`,
`default_aircraft_profiles`, `default_aircraft_apu_ef`,
`default_aircraft_start_ef`, `default_gate_profiles`,
`default_helicopter_engine_ei`). User customizations to those tables
WILL BE OVERWRITTEN.

Pass `--refresh-tables T1,T2,...` to override the list entirely.

A hardcoded guard refuses to refresh user-data tables (`user_*`,
`shapes_*`) regardless of `--refresh-tables`. The guard logs a warning
and silently strips forbidden names from the resolved list.

### Phase 3 — point-sources v2 hooks (auto, opt-out via `--skip-point-sources-v2`)

Two small post-migration steps tied to the point-sources v2 schema:

1. INSERT-OR-IGNOREs three named temporal profiles (`heating_season`,
   `cooling_season`, `business_hours`) into each of
   `user_month_profile`, `user_day_profile`, `user_hour_profile`.
   These three profiles are shipped in the canonical templates
   (`open_alaqs/core/templates/{project,inventory}.alaqs`) so new
   studies inherit them automatically. The Phase 3 INSERT-OR-IGNORE
   step backfills them into legacy studies migrated through Phase 1.
   The user's existing custom profiles (e.g. `parking`, `roadways`)
   are never modified. Idempotent on `profile_name`; running Phase 3
   on an already-migrated study is a no-op.

   The `user_*_profile` tables are in
   `USER_DATA_TABLES_FORBIDDEN_FROM_REFRESH` and therefore cannot be
   handled by Phase 2's CSV refresh path; Phase 3 is the only mechanism.

2. An optional deprecated-pin report (`--report-deprecated-pins`).
   Read-only on the source. Writes a CSV listing every in-study
   `shapes_point_sources` row whose EF fingerprint
   `(category, substance, NOx)` matches a `deprecated=1` row in
   `default_stationary_ef`. Each row includes a
   `recommended_replacement_description`, optional `ambiguous
   fingerprint` annotations when multiple legacy rows share the
   fingerprint, and two specific warnings for high-impact pre-v2
   data quality issues:
   - The legacy "Industrial natural gas" row whose NOx value of 2.24
     kg/10³ m³ is the AP-42 low-NOx-burner value, not the
     uncontrolled large-boiler value.
   - The legacy diesel row that used `1000_m3` units but matches the
     new `Stationary IC Engine` EFs that use hours.

   Output path defaults to `migration_<source-basename>.csv` in the
   source's directory; pass `--report-deprecated-pins PATH` for an
   explicit path.

To skip Phase 3 entirely, pass `--skip-point-sources-v2`.

### Safety

- A `.bak-<timestamp>.alaqs` copy is made in the same directory before
  any write. Pass `--no-backup` to skip (NOT recommended).
- Phase 1 runs in one transaction; Phase 2 in another. A failure in
  either phase rolls back THAT phase only. If Phase 2 fails after
  Phase 1 committed, the source has the new schema but the original
  data; restore from backup if you want to undo Phase 1 too.
- Pre-flight checks fail-fast: missing source file, missing reference
  template, missing CSVs for `--refresh-tables` → exit code 2 before
  any write.
- The tool is idempotent for Phase 1 (running on a migrated file
  produces an empty plan). Phase 2 is destructive by design (replace,
  not merge) — running it twice is a no-op only if the source's
  reference data already matches the CSV exactly.

### Usage

```bash
# Default: Phase 1 only (schema migration, auto-selected template):
python3 scripts/migrate_alaqs.py legacy.alaqs

# Dry-run (print plan, do not modify):
python3 scripts/migrate_alaqs.py legacy.alaqs --dry-run

# Schema + safe-default reference data refresh:
python3 scripts/migrate_alaqs.py legacy.alaqs \
    --refresh-reference-data

# Schema + full reference data refresh (overwrites user customizations):
python3 scripts/migrate_alaqs.py legacy.alaqs \
    --refresh-reference-data --refresh-include-user-extensible

# Data refresh only (skip schema):
python3 scripts/migrate_alaqs.py legacy.alaqs \
    --skip-schema --refresh-reference-data

# Custom refresh table set:
python3 scripts/migrate_alaqs.py legacy.alaqs \
    --refresh-reference-data \
    --refresh-tables "default_airports,default_vehicle_ef_copert5"

# Apply Phase 1 with extras pruned (matches the current template exactly):
python3 scripts/migrate_alaqs.py legacy.alaqs \
    --drop-extra-tables --drop-extra-columns

# Override the auto-selected reference template:
python3 scripts/migrate_alaqs.py legacy.alaqs \
    --reference open_alaqs/core/templates/inventory.alaqs

# Override the data CSV directory (e.g. for a frozen snapshot):
python3 scripts/migrate_alaqs.py legacy.alaqs \
    --refresh-reference-data --data-dir /path/to/frozen_csvs/

# v2: schema + data refresh + named-profile insert + deprecated-pin report
python3 scripts/migrate_alaqs.py legacy.alaqs \
    --refresh-reference-data --report-deprecated-pins

# v2: skip Phase 3 (keep study in v1 shape)
python3 scripts/migrate_alaqs.py legacy.alaqs \
    --refresh-reference-data --skip-point-sources-v2
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Migration applied or nothing to do. |
| 1 | Migration failed; original restored from backup if available. |
| 2 | Bad arguments / file not found. |

## `import_engine_test_events.py`

Bulk-loads engine-test event rows from a CSV into an ALAQS project's
`engine_test_events` table. Consumed after users have created their
test-site area sources (`is_test_site='1'` — see the "Engine test
sites" subsection of `documents/USER_GUIDE.md`) and want to populate
events without writing SQL by hand.

### CSV format

Wide format, one row per event. Header required. Column names match
the DB schema exactly:

- **Required:** `source_id`, `start_datetime`, `end_datetime`,
  `aircraft_type`
- **Optional:** `test_id`, `engine_uid`, `engine_count`, `t_TX_s`,
  `t_AP_s`, `t_CL_s`, `t_TO_s`, `instudy`

`thrust_mode` is intentionally NOT accepted from CSV: the DB column
still exists and defaults to `snap`, so users who need `meem` or
`bffm2` should `UPDATE` the row via SQL. This makes the choice
explicit rather than silently mis-typed in a spreadsheet cell.

Datetimes must be ISO 8601 (e.g. `2024-12-01T09:00:00`). `instudy`
must be `0` or `1` (defaults to `1`). Mode times (`t_*_s`) are
integer seconds, default 0. `engine_count` if given must be a
positive integer; if blank, falls back to the aircraft's default at
compute time.

### Modes

- **Dry run (default):** validates the CSV against the DB, prints
  a summary, no writes.
- `--apply` performs the INSERT.
- `--mode append` (default) — add rows to existing events.
- `--mode replace-for-source` — DELETE existing events for each
  `source_id` in the CSV, then insert. Re-import a corrected batch
  cleanly.
- `--mode replace-all` — DELETE all events first. Requires
  `--i-mean-it` as a safety flag against scripted mistakes.
- `--tolerate-warnings` — proceed even with warnings (unknown
  `source_id`, unknown `engine_uid`, running seconds exceed event
  window, etc.). Default is to fail on any warning.

### Validation

Row errors reject the row: `missing_required`,
`unparseable_datetime`, `end_before_start`, `invalid_mode_time`,
`invalid_engine_count`, `invalid_instudy`, `duplicate_row`.

Row warnings abort the whole import unless `--tolerate-warnings`:
`unknown_source_id`, `source_not_test_site`, `unknown_aircraft_type`,
`unknown_engine_uid`, `running_exceeds_window` (60 s tolerance).

All errors and warnings surface at once so the whole CSV can be
fixed in one pass rather than iteratively.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (dry-run passed, or apply completed). |
| 1 | Fatal error (CSV parse failure, DB error, invalid arguments). |
| 2 | Validation failed (row errors, or warnings without `--tolerate-warnings`). |

### Examples

Dry-run a batch:

```bash
python scripts/import_engine_test_events.py \
    /path/to/study.alaqs /path/to/logbook.csv
```

Apply after review:

```bash
python scripts/import_engine_test_events.py \
    /path/to/study.alaqs /path/to/logbook.csv --apply
```

Re-import a corrected batch for one source:

```bash
python scripts/import_engine_test_events.py \
    /path/to/study.alaqs /path/to/N1_fix.csv \
    --apply --mode replace-for-source
```

## `migrate_alaqs_gui.py`

A graphical front-end for `migrate_alaqs.py` for users who prefer not to use
the command line. Every CLI flag is exposed as a checkbox or text field, with
tooltips explaining each option. A live log panel streams the script's stdout
and stderr while the migration runs.

Place it in the same directory as `migrate_alaqs.py` (i.e. `scripts/`); the
auto-template-selection looks at sibling paths (`open_alaqs/core/templates/*.alaqs`
and `open_alaqs/database/data/`) so the GUI must be next to the migration script
for those defaults to resolve.

Run with QGIS's bundled Python on Windows:

```cmd
C:\PROGRA~1\QGIS34~1.13\bin\python.exe scripts\migrate_alaqs_gui.py
```

Or with any system Python that has PyQt5 installed:

```bash
python3 scripts/migrate_alaqs_gui.py
```

The GUI offers the same dry-run / apply distinction as the CLI: dry-run
prints the edit plan without modifying the source file. Destructive options
(`--no-backup`, `--drop-extra-tables`, `--drop-extra-columns`,
`--refresh-include-user-extensible`) are gathered in a red-bordered group
and trigger a warning dialog before apply.

The Phase 3 group box exposes two checkboxes:

- *Skip Phase 3* — equivalent to `--skip-point-sources-v2`.
- *Emit deprecated-pin report* — equivalent to `--report-deprecated-pins`. The report path is auto-generated next to the source file.

## Translation helpers

`update-strings.sh` and `compile-strings.sh` are thin wrappers around Qt's
`pylupdate4` and `lrelease` respectively. They operate on the `i18n/`
directory at the plugin root. Modern Qt 5 / PyQt5 setups may require
`pylupdate5` / `lrelease-qt5` binaries; edit the scripts in place if your
distro uses different names. These are infrequently needed — only when the
plugin UI strings are edited.
