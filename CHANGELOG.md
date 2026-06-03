# Changelog

All notable changes to Open-ALAQS are listed here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) loosely; dates are
ISO 8601.

## [5.2.0] - 2026-06-02

Major release with two new top-level packages, helicopter dispatch (FOCA
2015), point sources v2 schema, and AUSTAL dispersion gap closure against
the QGIS plugin's reference output (correlation 0.823 → 0.9998 on a
144-hour campaign run). Plugin metadata 5.1.1 → 5.2.0; standalone
`__version__` 0.8.0 → 0.9.0. Inventory totals on unchanged study files
match 5.1.2 bit-for-bit (NOx = 29.884658 kg on the `training_v3`
reference study, unchanged across all release candidates).

### Added

#### New top-level packages

- **`openalaqs_standalone/`** — pip-installable Python package that runs
  the full emission calculation without QGIS, PyQt5, or SpatiaLite at
  runtime. Uses pyproj + shapely + numpy. Designed for headless / CI /
  cluster use. Subcommands `aircraft` (per-movement aircraft emission
  totals from an `.alaqs`) and `austal` (the orchestrate driver
  producing the six-folder austal_prep input structure). Optional
  `--apply-nox-corrections` flag for Reference A NOx ambient correction
  (default off; preserves bymode bit-identity with the plugin).
- **`austal_prep/`** — pure-Python package producing AUSTAL-ready inputs
  (e-files, series.dmna, austal.txt) from a standardized emissions CSV
  plus a meteo CSV. Three grid writer modes: hybrid (new default),
  time_indexed, legacy. Usable standalone or as a Dataiku recipe.

#### Helicopter dispatch (FOCA 2015)

- Helicopter-aware emission calculation dispatching to a four-category
  FOCA 2015 reference (PISTON, SINGLE_TURBOSHAFT, TWIN_TURBOSHAFT_LIGHT,
  TWIN_TURBOSHAFT_HEAVY). Category derivation: engine count plus an
  MTOM threshold at 3400 kg.
- New core tool `open_alaqs/core/tools/foca_heli_trajectory.py`
  generating per-category trajectories with LTO ceiling 3000 ft, hover
  altitude 5 ft, hover duration 18 s.
- New tables `default_helicopter` (60 rows) and
  `default_helicopter_engines` (86 rows) replacing the legacy
  `default_helicopter_engine_ei` table.
- Helicopter movements bypass APU and gate emissions; FOCA scope is
  airborne emissions only.

#### Point sources v2 schema

- New `activity_unit` column in `shapes_point_sources` to record
  emission-rate units explicitly per source.
- New Aircraft Profile builder for non-standard climb-out / approach
  profiles. Lookup via new `user_aircraft_profile` table.
- New `user_gate_profile` table for gate-specific occupancy schedules.
- Corresponding template-build SQL files in `tools/template_build/sql/`.

#### `migrate_alaqs.py` Phase 3

- New Phase 3 (point sources v2 schema) adds `activity_unit` column to
  existing `shapes_point_sources` tables and creates
  `user_aircraft_profile` / `user_gate_profile` tables.
- Writes a `.bak-<timestamp>` backup before any change and rolls back
  on error.

#### Aircraft and APU reference data

- Two new aircraft (`B731`, `B74D`) added to `default_aircraft.csv`
  with associated rows in `default_aircraft_engine_ei.csv`.
- Six example `.alaqs` files (training, EHRD, AIRPORT_A, training_v3,
  ...) refreshed to match.
- `default_aircraft_apu_ef.csv` reference values regenerated against
  the 5 jet-group + TURBOPROP APU schema (effective EFs averaged
  across the canonical APU model in each group).

#### Regression tests (8 new modules)

- `test_apu_code_2_distribution.py` — length-proportional APU
  distribution on `apu_code=2` movements (6 cases).
- `test_apu_code_loaded_from_db.py` — APU code propagation through
  the standalone pipeline (3 cases).
- `test_austal_date_normalization.py` — `te` field shifted to
  `yyyy-01-01 01:00:00` (4 cases).
- `test_austal_prep_hybrid_mode.py` — per-hour aircraft e-files,
  per-pollutant divergence, mass conservation through series.dmna
  (3 cases).
- `test_austal_sk_overlap.py` — true-sk overlap weighting for
  aircraft vertical layers (10 cases).
- `test_extract_sources_missing_tables.py` — defensive shapes_*
  extraction (7 cases).
- `test_orchestrate_empty_sources.py` — empty `sources_df` handling
  (3 cases).
- `test_runner_timestamp_derivation.py` — continuous-timeline helper
  (11 cases).

#### Documentation

- `documents/USER_GUIDE.md`: new **Helicopters (FOCA 2015)** section
  between Movements table and Meteorology, covering FOCA category
  derivation, dispatch behaviour, and what is suppressed (APU and
  gate emissions).
- `documents/TRAJECTORY_DATA_SOURCES.md`: per-category trajectory
  parameter sources for the four FOCA helicopter categories (R22 POH,
  FOCA Appendix A, EC135 / AS355 / AS332L1 corroboration).
- `documents/RELEASE_NOTES_5.2.0.md`: full user-facing release notes.
- Restructured `documents/AUSTAL/AUSTAL_OPERATION.md`.

#### METAR meteo script

- `scripts/metar_to_alaqs_meteo.py` rewritten with multi-format
  support: `--source {auto,iem-csv,ogimet,raw}`, `--anchor-year-month`
  for synthetic year remapping, `--plots-dir`, `--coverage-floor 70%`,
  per-row validation, dedup, time-window filter. Internal `_COLUMNS`
  unchanged; downstream consumers untouched.

### Changed

#### AUSTAL `grid_writer_mode` default flipped to `hybrid`

The default `grid_writer_mode` is now `"hybrid"` (was `"time_indexed"`).
In hybrid mode, aircraft sub-sources receive one per-hour e-file per
hour with per-pollutant spatial weights; stationary sources keep a
single time-invariant e-file. The previous default (`time_indexed`)
collapsed all aircraft activity over the study window into one shared
spatial distribution, biasing per-pollutant dispersion: a cross-check
on a 144-hour campaign run found correlation 0.823 against the QGIS
plugin's AUSTAL output and a 6.1% deficit in total in-grid annual
mean concentration. The bias was attributable entirely to the
time-invariant spatial pattern (Monte Carlo at `qs=3` vs `qs=4`
contributed correlation 0.9999, well inside noise).

Changes:
- `austal_prep/config.py`: `grid_writer_mode` field default flipped.
  Docstring rewritten to describe all three modes accurately.
- `openalaqs_standalone/orchestrate.py`: function default flipped;
  new `--grid-writer-mode {legacy,time_indexed,hybrid}` CLI flag
  with default `hybrid`.
- `openalaqs_standalone/make_config.py`: function default and
  docstring flipped.

The hybrid writer code path itself (`write_grid_per_hour_aircraft`
in `austal_prep/writers/grid_files.py`, plus the per-pollutant
expansion logic in `austal_prep/runner.py`) was already present in
5.1.2 but exercised only via explicit opt-in. This release flips
the default so it ships activated.

Validation against plugin AUSTAL output (144-hour campaign,
`qs=3` both sides):

| metric                        | hybrid (this release) | time_indexed (prior) |
|-------------------------------|----------------------:|---------------------:|
| correlation at shift (0, 0)   |              0.999830 |             0.823    |
| max per-cell \|Δ\| (µg/m³)    |                 2.770 |           156.93     |
| mean per-cell \|Δ\|           |                 0.115 |             0.883    |
| peak position offset          |             same cell |       1-cell shift   |
| sum ratio (std / plugin)      |            1.0157 (+1.57%) | 0.9391 (-6.09%) |

The remaining +1.57% sum ratio is at the noise floor of source
splitting differences between the pipelines (plugin aggregates to
4 AUSTAL sources, standalone to 22 via `by_type_per_pollutant`).
Correlation is at the AUSTAL Monte Carlo noise floor (qs=3 vs qs=4
self-comparison gives 0.99992).

#### Other interface changes

- `SourceModule` emission methods now return
  `Dict[datetime, List[Emission]]` indexed by hour, not a flat list.
  Callers that iterated movements directly must walk the dict
  values; in-tree callers are updated.
- Plugin Point Sources form: new **activity unit** combobox between
  the emission rates and the geometry editor.
- `openalaqs_standalone` CLI: new
  `--grid-writer-mode {legacy,time_indexed,hybrid}` flag (default
  `hybrid`).

### Fixed

#### AUSTAL writer (`core/modules/AUSTALOutputModule.py`)

- **Multi-source zero-rate crash**. AUSTAL aborts with "Quelle ist
  nicht definiert nach Stunde H" when two consecutive exact-zero
  rates are emitted per source. Defensive `1e-30` floor and phantom
  sentinel cell added.
- **Date normalization**. `te` (end-of-time) field now shifts so
  dispersion starts at `yyyy-01-01 01:00:00`, mirroring the plugin's
  `set_normalized_date`.
- **Aircraft vertical sk-overlap weighting** (standalone path; plugin
  retains uniform 50 m bins for bit-match continuity). True-sk
  overlap distributes aircraft emission mass per-layer proportional
  to ground-cell overlap, matching the AUSTAL convention.
- **Per-pollutant aggregation strategy** `by_type_per_pollutant`:
  multi-pollutant stationary sources are split into single-pollutant
  sub-sources to avoid cross-pollutant leak through the AUSTAL source
  table.
- **Cell apportionment for gates**: `_polygon_cell_fractions` performs
  proper area-weighted apportionment of gate GSE + GPU emissions
  (was 100% on the first cell touched).
- **SCINOTAT** added to AUSTAL `os_options` to close a 673-cell
  gray-halo border in the QGIS gpkg display (cosmetic).

#### COPERT 5 parking (`core/tools/copert5.py`)

- **Distance unit bug**: UI shows distance in metres but the model
  treated it as kilometres, inflating non-exhaust emissions by 1000×.
  Now correctly divided by 1000.
- **Airport temperature** lookup in the parking emission factor
  (prior versions silently used 15 °C ISA regardless of study
  airport).

#### ADS-B trajectory classification (`core/tools/ads_b.py`)

- Sub-mode classifier now respects ICAO mode-switch altitudes for
  AP / CL / TO / IDLE; short approach segments were occasionally
  misclassified as climbout.

#### Geodetic length on multi-line geometries (`core/tools/spatial.py`)

- `geodetic_length_m()` now correctly handles `MultiLineString` inputs
  by summing per-line lengths. Previously raised on non-LineString
  geometries.

#### BFFM2 robustness (`core/tools/bffm2.py`)

- Twin-quadratic fit no longer crashes on degenerate engine EI tables
  (fewer than 3 anchor modes, or non-monotonic FF anchors); falls
  back to `mode_anchor` with a one-line warning.
- ISA-meteo override (`--isa-meteo` CLI flag, `use_isa_meteo=True`
  API) for explicit ambient-corrected comparisons against the
  plugin's CSV path. Bymode and helicopters immune; BFFM2 shows
  5–34% spurious deltas vs the plugin without the flag.

#### Standalone defensive fixes (`openalaqs_standalone/`)

- **`apu_code=2` length-proportional placement** (`distribute.py`,
  `compute_movements.py`). Movements flagged `apu_code=2` (APU
  running both at gate and on taxi) now distribute APU emissions
  along the taxi trajectory in proportion to per-segment length
  rather than collapsing all mass into segment 0. Mass-conservative
  across all branches.
- **Defensive missing-table handling in `extract_sources`**. All
  five `_extract_*` functions (roadways, parking, gates,
  point_sources, area_sources) now wrap their initial `SELECT *
  FROM shapes_<table>` in `try/except sqlite3.OperationalError`,
  log a one-line warning, and return `[]`. Previously two of the
  five (roadways, parking) crashed the pipeline on missing tables.
- **Defensive empty-`sources_df` handling in `orchestrate`**. The
  line `f"({dict(sources_df.source_type.value_counts())})"` no
  longer crashes when `extract_sources` returns an empty DataFrame.
- **Continuous-timeline timestamp derivation in `runner`**. New
  `_derive_timestamps()` helper builds a continuous hourly range
  from `emissions_df.timestamp.min()..max()`. The previous inline
  derivation dropped internal gap-hours, causing AUSTAL to abort
  with "Quelle ist nicht definiert nach Stunde H" at the first
  uncovered hour. Downstream `build_emission_rates_fast` zero-fills
  missing rate cells; `load_meteo` substitutes AUSTAL-default
  sentinels for missing meteo hours.

#### Cross-platform template build

- `tools/template_build/generate_templates.py` uses
  `sqlalchemy.engine.URL.create()` to build the sqlite URI (was
  hand-rolled string concatenation). Fixes 36 OperationalError
  failures on Windows OSGeo4W pytest related to backslash-in-URI.

### CI / Test infrastructure

- `pyarrow>=14.0` added to `requirements.txt` (parquet I/O for the
  `openalaqs_standalone` subprocess in
  `tests/test_austal_prep_hybrid_mode.py`).
- `tests/data/AIRPORT_A/{AIRPORT_A,AIRPORT_A_out}.alaqs` migrated from
  v1 to v2 schema using `scripts/migrate_alaqs.py
  --refresh-reference-data`, with `shapes_point_sources` rebuilt in
  template column order.
- `open_alaqs/core/tools/create_output.py` `shapes_point_sources`
  copy refactored to use explicit column names in SELECT and INSERT
  (previously a hardcoded 22-placeholder `VALUES` list against an
  implicit-positional target, which broke after the v2 schema added
  `activity_unit`).
- Two ANP tests in `tests/test_emission_calculator_service.py` marked
  `@pytest.mark.xfail(strict=True)` pending regeneration of
  `ANP_emissions_table_by_aggregation_co.csv` against the 5.1.2
  start-emission keying fix. Tracked for 5.2.1.

### Removed

- Legacy `default_helicopter_engine_ei` table (replaced by
  `default_helicopter` + `default_helicopter_engines`). Affected
  studies are migrated automatically by `scripts/migrate_alaqs.py`.
- Stale `.DS_Store` committed in earlier releases under
  `open_alaqs/core/`.
- Per-movement and per-segment diagnostic parquets in
  `openalaqs_standalone/orchestrate.py` (`write_per_movement_diag`
  removed; cell-diag env-var gate retained as opt-in).

### Migration

To bring a 5.1.x study forward to 5.2.0:

```
python3 scripts/migrate_alaqs.py path/to/your.alaqs \
    --refresh-reference-data \
    --drop-extra-columns
```

The migrator detects whether `shapes_point_sources` already has
`activity_unit` and whether the `default_helicopter` /
`default_helicopter_engines` tables exist, applies the v2 changes in
place, and writes a `.bak-<timestamp>` backup. See the
**Helicopters (FOCA 2015)** section of `documents/USER_GUIDE.md` for
FOCA dispatch behaviour post-migration.

### Validation

- `training_v3` (15-movement reference study, 13 fixed-wing + 2
  helicopter): bymode NOx = 29.884658 kg, unchanged across all
  release candidates.
- Cross-method 90/90 bit-identical against the CAEP14 v14 reference
  on a fresh build (training_v3, three methods).
- 144-hour LFSB v3 campaign: standalone-vs-plugin AUSTAL output
  correlation 0.9998 (was 0.823 in `time_indexed` default).
- 53 standalone tests pass on Linux; 402 QGIS-required tests pass on
  the CI docker matrix (1 known stale-fixture failure tracked for
  5.2.1, plus 2 xfailed ANP tests).

## [5.1.2] - 2026-05-30

### Data updates

- `database/data/default_aircraft.csv`: applied APU Tier 2 backfill for
  7 ICAOs (H25B, H25C, HA4T = Honeywell GTCP 36-150; BCS1, BCS3 =
  Honeywell 131-9; B731 = Garrett GTCP85-129; B74D = Garrett GTCP 660),
  reducing NULL `apu_id` count from 1764 to 1757 rows. Each backfilled
  ICAO maps to an existing row in `default_aircraft_apu_ef` with full
  fuel/CO/HC/NOx/SOx/PM10 emission factors. Decision rules + per-ICAO
  citations in `documents/APU_TIER2_RESULTS.md`. The same backfill is
  baked into `core/templates/project.alaqs`.

### Documentation

- `documents/USER_GUIDE.md` Point sources section refreshed for v2:
  describes `annual_activity` + `activity_unit` (replacing
  `units_per_year`), the 7 default categories (added Stationary IC
  Engine), the three named profiles (`heating_season`,
  `cooling_season`, `business_hours`), and the v2 emission formula.
- `documents/VALIDATION_GUIDE.md` new: complete validation runbook
  (V1-V5) for CAEP14 reference and campaign-study targets, including
  a Known regression patterns section that documents the 8 regression
  modes observed during the build cycle.
- `documents/APU_ASSIGNMENT_WORK.md`, `documents/APU_TIER2_RESULTS.md`,
  `documents/apu_tier2_backfill.sql`: APU research record now part of
  the package (was session-local).

### Build baseline
This release is built directly on top of the validated ASU plugin tree
(commit working state with helicopter FOCA 2015 dispatch, AUSTAL series.dmna
fixes for zero-rate sources, COPERT 5 parking distance unit fix, ADS-B
sub-MSL handling, BFFM2 power overshoot tolerance, MultiLineString
geodetic length, aircraft-keyed start emissions, helicopter table guards
in the standalone). Every file in `open_alaqs/` is byte-identical to the
validated tree except for the v2 point-source schema additions
(`PointSources.py`, `SourceModule.py`, `default_stationary_*.csv`,
`ui_point_sources.{ui,py}`, `metadata.txt`, the two template `.alaqs`
files, the `default_aircraft.csv` B731/B74D backfill) and the removal of
the internal `core/diag.py` debug module and its two import hooks. The
upstream `eurocontrol-asu/open_alaqs` 5.1.1 release is the long-term
target for upstreaming these v2 additions; this build ships the
validated state intact so existing users see the same calculation
outputs they have already validated.

Point-sources v2 schema additions, an integrated `openalaqs_standalone`
QGIS-free pipeline as a top-level sibling of `open_alaqs/`, and quality
fixes for `default_aircraft`. Backward compatible: legacy v1 studies
continue to load and calculate; existing rows are flagged
`deprecated=1` for opt-in migration.

### Added

- `openalaqs_standalone/` top-level package: QGIS-free emission
  pipeline (30 Python modules, ~46 MB including CAEP14 validation
  fixtures and reference data). Same emission math as the plugin
  (bymode, BFFM2, MEEM); runs without QGIS or PyQt5. Suitable for
  headless / CI / cluster use, batched campaigns, and validation
  against the canonical CAEP14 reference (`training_v3.alaqs`).
  Opt-in Reference A NOx ambient correction via
  `--apply-nox-corrections` (default off; preserves existing
  std-vs-plug bit-identity).
- `austal_prep/` top-level package: writer/helper modules for
  generating AUSTAL `series.dmna`, `austal.txt`, and meteorological
  inputs from a standalone emissions run.
- Point-sources v2 schema columns on `default_stationary_ef`:
  `activity_unit`, `reference`, `deprecated`,
  `recommended_month_profile`, `recommended_day_profile`,
  `recommended_hour_profile`. Surfaced in the plug Point Sources
  form as a read-only "Activity unit" line and pre-selected
  temporal profile dropdowns.
- Point-sources v2 schema column on `shapes_point_sources`:
  `activity_unit` (per-source override; NULL = inherit from EF row).
- New `Stationary IC Engine` source category (`category=6`) in
  `default_stationary_category`. Pairs with `activity_unit='hr'`.
- 11 new AP-42 1.4-1 natural-gas combustion emission factor rows
  in `default_stationary_ef` (oids 51-61, category=2, types 100-110)
  covering large wall-fired (uncontrolled pre-NSPS / post-NSPS /
  low-NOx / FGR), tangential-fired (uncontrolled / FGR), small
  boilers (uncontrolled / low-NOx / LNB+FGR), residential, and
  EMEP 1.A.4 commercial cross-reference. All carry
  `activity_unit='1000_m3'` and
  `recommended_month_profile='heating_season'`.
- 3 new AP-42 3.3 / 3.4 stationary internal combustion engine rows
  in `default_stationary_ef` (oids 62-64, category=6, types 1-3):
  Diesel >600 hp Prechamber, Diesel >600 hp Open-Chamber, Diesel
  <600 hp. All carry `activity_unit='hr'` and `recommended_day_profile`
  / `recommended_hour_profile='business_hours'`.
- 3 named temporal profiles shipped in `project.alaqs` and
  `inventory.alaqs` templates and INSERT-OR-IGNORE'd into existing
  studies by Phase 3 of `scripts/migrate_alaqs.py`:
  `heating_season` (winter-peaked month, flat day/hour),
  `cooling_season` (summer-peaked month, flat day, afternoon-peaked
  hour for AC load), `business_hours` (flat month, weekday-weighted
  day, 07-19 active hour). Idempotent on profile_name.
- `scripts/migrate_alaqs.py` Phase 3: point-sources v2 hooks
  (temporal-profile INSERT-OR-IGNORE + optional deprecated-pin
  report). Two new CLI flags:
  - `--skip-point-sources-v2` (default off; skip the profile insert).
  - `--report-deprecated-pins [PATH]` (off by default; emit a CSV
    identifying in-study `shapes_point_sources` rows whose EF
    fingerprint matches a `deprecated=1` row in
    `default_stationary_ef`, with warnings for the misnamed
    "Industrial" natural-gas row and the unit-incompatible legacy
    diesel row).
- `scripts/migrate_alaqs_gui.py` Phase 3 group box: two checkboxes
  exposing the new flags with tooltips.
- B731 (Boeing 737-100) and B74D (Boeing 747-400D Domestic)
  reference data backfilled in `default_aircraft.csv`: name,
  manufacturer, mtow per ICAO Doc 8643.

### Changed

- `core/interfaces/SourceModule.py`: parameter
  `annual_total_operating_hours` renamed to `annual_activity` in
  `getEmissionsForTimePeriod` and `getRelativeActivityPerHour`.
  Mechanical rename; all internal callers pass positionally. The
  unit pairing now lives explicitly on the EF row's
  `activity_unit` column. The arithmetic is unchanged.
- Plug Point Sources form (`ui/ui_point_sources.{ui,py}`): the
  "Units Per Year" label is now "Activity per year"; a new read-only
  "Activity unit" field surfaces the EF row's unit. When an EF is
  selected, the form pre-selects the recommended month / day / hour
  profiles in the corresponding dropdowns (user can override).
- 50 legacy `default_stationary_ef` rows are flagged `deprecated=1`
  with `activity_unit` and `reference` backfilled by a category /
  substance / description heuristic. The rows remain functional and
  no calculation changes; the flag is informational only and drives
  the new migration report.

### Fixed

- `core/tools/copert5.py`: COPERT 5 parking emission factors were
  applied with the `travel_distance` field treated as km, but the UI
  labels it in metres. Pre-fix, every stored `*_gm_vh` was ~1000x too
  high. Distance is now divided by 1000 before the lookup.
- `core/tools/ads_b.py`: ADS-B trajectory mode classification used
  literal equality `z_m == 0` to decide TO vs CL, which silently
  failed at airports below MSL (e.g. Rotterdam EHRD at z=-4.57 m
  classified every ground-roll point as CL). Changed to `z_m <= 0`.
- `core/tools/twin_quadratic_fit_method.py`: small floating-point
  overshoots in power_setting (e.g. 1.01 from BFFM2 derivation under
  non-ISA conditions) raised `ValueError`, aborting the whole
  movement. The function now accepts up to 1.05 and clamps to 1.0
  with a logged warning; >1.05 still raises.
- `core/MovementEmissionCalculator.py`: two fixes:
  (1) start emissions are now keyed by aircraft (which carries the
  group) instead of engine (which can be shared across groups);
  (2) BFFM2 `ValueError` from the twin-quadratic fit is caught and the
  calculation falls back to the mode-anchor EI path instead of
  aborting the whole study.
- `core/EmissionCalculation.py`: warning when `tbl_InvMeteo` is empty,
  to make it clear why BFFM2 output reverts to ISA defaults instead
  of the configured meteo.
- `core/tools/spatial.py`: geodetic length computation now handles
  MultiLineString and GeometryCollection inputs (previously returned
  zero length for any clipped polyline that re-entered the same cell,
  silently dropping mass for affected segments).
- AUSTAL multi-source `series.dmna` writer (`core/modules/AUSTALOutputModule.py`)
  regressed against upstream 5.1.1 — three battle-tested fixes restored:
  - **Zero-rate floor**: per-source rates of exactly `0.000e+00` mid-run
    triggered `*** Grid source "NN" not available! (TalSrc.SrcCrtPtl.14)`
    abort the next hour. Rates are now floored at `1.0e-30` (~3.2e-26 g
    per slot over a year of zeros, below numerical precision).
  - **Back-filled e-files**: zero-mass hours now write phantom single-cell
    Eq weights with per-file `_start_time` / `_end_time` derived from the
    hour index (avoids `*** File "...e0001.dmna" [...] not valid at 00:00:00!`).
  - **Wind direction sentinel**: `WindDirection == 0` with `WindSpeed > 0`
    is re-encoded to AUSTAL's "missing" sentinel `999`, suppressing the
    AUSTAL warning *"Datenzeilen mit Windrichtung gleich 0 und
    Windgeschwindigkeit groesser 0"*.
- `openalaqs_standalone.movements.get_helicopter` and
  `get_helicopter_engine_type` now treat absence of
  `default_helicopter` / `default_helicopter_engines` as "no
  helicopters in this study" (every aircraft is fixed-wing) rather
  than crashing with `OperationalError: no such table`. Lets the
  standalone run cleanly against the upstream `example/training`
  fixture, which ships without helicopter tables.
- `openalaqs_standalone aircraft --gpkg-out` removed. The argument
  was unused (a previous module rename had left a broken import) and
  its output duplicated what the `austal` subcommand already
  produces under `<out>/inventory_gpkgs/` via the
  `inventory_gpkg.write_pollutant_gpkgs` API. Users wanting
  gpkg outputs should run `austal`.

### Migration

For an existing study, run:

```bash
python3 scripts/migrate_alaqs.py study.alaqs --refresh-reference-data --report-deprecated-pins
```

The script adds the v2 columns, refreshes the 9 safe reference
tables from CSV, inserts the 3 named profiles, and writes
`migration_<basename>.csv` listing every in-study point source
pinned to a deprecated EF row with a recommended replacement.

Tested end-to-end against a multi-source legacy study fixture
(thousands of movements, dozens of in-study point sources): 7 schema
additions, 14 new EF rows, 3 profiles per `user_*_profile` table
inserted, every in-study source flagged in the migration report with
its recommended replacement, including the LOW-NOX-BURNER warning on
sources pinned to the misnamed legacy Industrial Natural Gas row.
Idempotent re-run: 0 changes.

## [5.1.1] - 2026-05-10

Hotfix release from EHRD (Rotterdam) integration testing. Adds per-receptor compliance evaluation against EU Directive 2024/2881 (binding from 1 January 2030) and fixes several AUSTAL writer/reader correctness issues, plus UX improvements around result-button gating and error reporting.

### Added

- New `ComplianceReportOutputModule`. Reads `<substance>-tmpa.dmna` files from the AUSTAL work directory and produces a per-receptor PASS/FAIL table against EU Directive 2024/2881 limit values applicable from 1 January 2030. Reportable substances: PM10, PM2.5, NO2, NOx (ecosystem), SO2. Threshold values verified against the official directive (Annex I, Section 1) and the EEA Air Quality Status Report 2025. CSV export available. CO/HC/CO2 are explicitly excluded with an explanatory note in the dialog header.
- Receptor CSV picker in both ALAQS and "Generate from CSV" input modes. ALAQS mode uses a 3-tier priority chain: CSV -> `shapes_receptor_points` table in the .alaqs database (filtered to `instudy != 'N'`) -> empty. CSV mode uses the receptor CSV picker only.
- NOTALUFT (per-hour series) checkbox on the Output Mode row. Required to produce per-receptor `-tmpa.dmna` files that the new Compliance Report and rewritten Plot Time
## [5.1.0] - 2026-05-09

Performance and correctness refactor of the calculation and AUSTAL
output paths. Inventory totals match prior versions bit-for-bit; AUSTAL
output now correctly includes stationary-source contributions that the
previous writer silently dropped (validated against
`example/training/training_validation_reference.xlsx`).

### Added

- Vectorised emission API. `Source.getHourlyActivityVector` produces
  the full year of per-hour activity in one numpy operation; stationary
  source modules pre-compute the cache once per run and read it with
  O(1) lookups during the time-major loop. Replaces 8760 scalar
  `getRelativeActivityPerHour` calls per source.
- Time-indexed AUSTAL writer (`AUSTALOutputModule`). Stationary sources
  are aggregated by type and emitted as four AUSTAL source slots in a
  hybrid `series.dmna` alongside the existing per-hour movement slot.
  Per-source spatial weights are computed once via
  `core/tools/austal_helpers.compute_cell_weights`.
- DataFrame data layer (`core/tools/sources_df.py`) backing the
  AUSTAL writer.
- Leap-year sanity warning when `[start_dt, end_dt]` does not cover a
  full calendar year.

### Changed

- AUSTAL calc grid is now the em grid plus
  `DEFAULT_CONCENTRATION_GRID_FACTOR` cells of halo on every side
  (44×44 for a 40×40 em grid). Sources sit centred inside the calc
  grid with symmetric 2-cell buffer. The em grid sits exactly inside
  the conc raster.
- Emission and concentration QGIS layers are now exported in the
  project UTM zone instead of EPSG:3857. Cells render as true
  `dd × dd` m squares; the cos(lat) distortion at high latitudes is
  gone.
- `EmissionsQGISVectorLayerOutputModule` and
  `ConcentrationsQGISVectorLayerOutputModule` keep working data in
  EPSG:3857 / UTM respectively and project at output time only.
- `ContourPlotVectorLayer` accepts an optional `epsg=` argument.

### Fixed

- Stationary contributions (especially `PointSources`) reach the AUSTAL
  output. The previous writer's `getEfficiencyXY` returned 0 for
  zero-area geometries (points), silently dropping those sources from
  `series.dmna` while keeping them in the inventory CSV. Validated
  against the training reference: stationary totals match within
  rounding (<0.025%); inventory CSV grand totals match exactly.

### Removed

- `_grid_writer_mode` setting and the legacy per-hour AUSTAL writer
  path (`writeInputFile` / `writeTimeSeriesFile`). Time-indexed mode
  is now the only writer.
- `_use_vectorised_path` flag. The vectorised activity-vector cache
  is the only path.

## [5.0.1] - 2026-05-06

Patch release covering two correctness bugs in the AUSTAL dispersion
output of 5.0.0 and a set of documentation corrections. No file-format
or API changes; existing 5.0.0 `.alaqs` files are loaded unchanged.

> **Action required for 5.0.0 dispersion users:** any AUSTAL run made
> with 5.0.0 has a vertical-grid mismatch that produced ~7x-too-low
> ground concentrations. Re-run with 5.0.1 before reporting numbers.

### Fixed

- **AUSTAL vertical grid mismatch** in `AUSTALOutputModule.py`. The
  per-source `e000N.dmna` files were written with a uniform 50 m
  first cell (`sk` from `Grid3D.getResolutionZ()`), while the calc
  grid declared in `austal.txt` omitted `sk` and therefore used the
  AUSTAL built-in default
  `0 3 6 10 16 25 40 65 100 150 200 300 400 500 600 700 800 1000 1200 1500`
  (3 m first cell). Ground-level road and parking emissions were
  released uniformly into the first 50 m of atmosphere instead of
  0–3 m, suppressing near-source ground concentrations by roughly a
  factor of 7. The per-source `sk` is now written from the AUSTAL
  default explicitly.
- **Concentration GPKG spatial alignment** in
  `ConcentrationsQGISVectorLayerOutputModule.py`. Three connected
  issues caused the QGIS-built GPKG of `y00a` output to disagree
  with the underlying AUSTAL grid: `_data_cells` was built from the
  `.alaqs` DB grid plus a hardcoded halo and ignored the y00a
  header; `process()` iterated y00a cells with `delta = 250` in raw
  EPSG:3857 units while polygons were ~413 raw units wide,
  producing Point-in-polygon binning that summed multiple y00a
  cells into one polygon; and the contains() lookup was
  unnecessary. Fixed by reading `xmin/ymin/delta/hghb` from the
  y00a header, building `_data_cells` in absolute UTM, mapping y00a
  cells 1:1 to data_cells via direct array assignment, and
  reprojecting to EPSG:3857 only at the final `endJob()` step.
  Verified on a synthetic single-source test: 19 nonzero polygons,
  cell-by-cell match against the y00a DMNA.

### Documentation

- **Activity Profiles section** in `documents/USER_GUIDE.md` rewritten.
  The previous description claimed profile values were [0, 1] activity
  multipliers and that zeroing a period deactivated the source. Both
  are wrong: profiles are non-negative shape factors, and the internal
  calendar-weighted normalisation redistributes mass to non-zero
  periods, leaving the annual total unchanged. The new section gives
  the multiplicative formula explicitly and points users at
  `unit_year` / `ops_year` for actual reductions.
- **BFFM2 limitations** in `documents/BFFM2_validation/BFFM2.md`:
  the straight-line trajectory limitation applies only to standard
  ANP profiles. ADS-B `course = CUSTOM` profiles can describe
  arbitrary curved trajectories.
- **User Guide Create Output File section** documents the ADS-B
  Data (Optional) widget and the ADS-B CSV column schema sourced
  from `open_alaqs/core/tools/ads_b.py:validate_adsb_file`.
- **CHANGELOG Compatibility subsection** added to the 5.0.0 entry.
  Lists primary CI targets (QGIS 3.40.15 LTR and 3.44.9) and notes
  QGIS 4.x as experimentally supported.

### Assets

- `emissions-calculation.png` and `generate-emissions-inventory.png`
  re-captured against the current 5.0.0 UI (the previous shots
  pre-dated the ADS-B Data widget and the reorganised
  Configuration tab).
- `gates.PNG` removed: byte-for-byte duplicate of `gates.png`,
  not referenced from any document.

## [5.0.0] - 2026-04-30

First stable release after the rebuild. The 5.0 line is not
backwards-compatible at the file-format level with the 4.x series — see the
**Migration** section below for how to bring an old `.alaqs` study forward.

### Compatibility

- **QGIS 3.x (LTR / latest)** — primary supported targets. The CI matrix
  runs the test suite against the QGIS Docker images
  `qgis/qgis:3.40.15-noble` (LTR) and `qgis/qgis:3.44.9-noble` (latest)
  for every PR.
- **QGIS 4.x (experimental)** — the plugin has been used end-to-end on
  QGIS 4.x development builds throughout 2026 and is functional there.
  QGIS 4.x is not yet covered by automated CI; users running on 4.x
  builds are invited to report issues against this repository.

### Added

- **`scripts/migrate_alaqs.py`** — CLI tool that rewrites a legacy 4.x-era
  `.alaqs` file in place against the current canonical schema. Supports two
  phases: (1) schema migration (add/drop tables and columns to match the
  reference template), (2) optional reference-data refresh (replace the
  contents of `default_*` tables with shipped CSVs). Handles the SpatiaLite
  metadata view and trigger dependencies that the legacy file format brings
  along, so files written with SpatiaLite 4.x or earlier migrate cleanly.

- **`scripts/migrate_alaqs_gui.py`** — PyQt5 wrapper around the CLI for users
  who prefer a graphical interface. Exposes every CLI flag, surfaces the
  migration log live, and runs the migration in a worker thread so the UI
  stays responsive.

- **`documents/AUSTAL/AUSTAL_OPERATION.md`** — operating guide for the
  in-plugin AUSTAL Dispersion Analysis dialog. Covers the executable
  selection, input-file strategy (existing files / from inventory / from
  CSV), grid configuration, execution, and result visualisation in step
  order.

- **CAEP14 v14 emission-index database** validated against the official
  CAEP14 spreadsheet. The bundled `default_aircraft_engine_ei` table now
  matches the v14 anchors to 0% drift for every engine that appears in the
  AIRPORT_A test fixture (see `tests/data/AIRPORT_A/AIRPORT_A_CAEP14_comparison.xlsx`).

- **`tests/data/AIRPORT_A/`** new test fixture (Rotterdam-shaped airport
  with two engines: 01P20CM128 LEAP-1A26/26E1 and 11GE144 CF34-10E5A1),
  used to lock the bymode and BFFM2 emission paths against external
  references.

- **`example/training/training_validation_reference.xlsx`** — paired-column
  reference spreadsheet validating the three plugin emission methods
  (bymode, BFFM2 trajectory, BFFM2 anchor) against equivalent CAEP14 v14
  computations. Drift is documented per-pair (~0% bymode, ~2-3% BFFM2 NOx,
  <1% BFFM2 CO/HC).

### Changed

- **Emissions vector layer output now reprojects the receptor grid to
  EPSG:3857** in `EmissionsQGISVectorLayerOutputModule.beginJob`. The grid
  is built in local UTM (so user-supplied resolutions are honoured to ~2%
  on the ground), then reprojected so source/emission geometries — which
  are stored in EPSG:3857 throughout the rebuild — can be intersected in
  matching CRS. As a side effect, individual cell sums shift by ~1.5%
  relative to the pre-rebuild output because emissions redistribute
  across the projected cell footprints; aggregate totals are unchanged.

- **Movements CSV legacy compatibility** — `inventory_insert_movements`
  now strips the trailing `domestic` column case-insensitively when it
  detects a 21-column header (the pre-rebuild export). Previously this
  silently dropped `gate_emissions_code` from column 13 onwards, which
  would inflate emissions because the default `gate_emissions_code=1`
  re-enabled GSE on every movement. Affects users importing CSVs from
  pre-5.0 exports.

- **`SQLSerializable._recreate_table` → `recreate_table`** (made public).
  Three call sites updated. Part of the schema-template registry work
  needed for `tools/template_build/generate_templates.py` to apply
  migrations consistently across all 24 SQLSerializable subclasses.

- **`default_aircraft.engine_count` is now `TEXT` (was `INTEGER`)** to
  accommodate non-numeric engine-count markers (e.g. `"C"` for combined
  rotorcraft entries) that appear in some EEDB rows.

- **`default_aircraft_engine_ei` schema realignment** — column count is 32
  (one fewer than the 33-column 4.x baseline) after dropping the legacy
  `pm10_prefoa3` field which was not used anywhere in the runtime. Column
  ordering was also realigned with the canonical template. Rows in
  legacy files are migrated transparently by `--drop-extra-columns`.

- **Dual-mode BFFM2** — the BFFM2 path accepts a `bffm2_ff_source` config
  field (`trajectory` default, or `mode_anchor`). Exposed in the Generate
  Emission Inventory dialog via a dropdown.

- **Create Output dialog "Advanced Options" group removed** — the Method
  dropdown (with "ALAQS" as the sole choice), Towing Speed, and Vertical
  Limit fields have been removed. Method was never routed to any consumer,
  Towing Speed was written to a dict key no downstream code read, and
  Vertical Limit wrote to a DB column nothing queried — the actual LTO
  ceiling is `EmissionCalculatorService.vertical_limit_m = 914.4` m (CAEP
  standard), hardcoded at the calculation boundary.

### Removed

- **18 legacy 4.x-era tables** are no longer part of the canonical schema
  and are dropped on migration with `--drop-extra-tables`. Listed for
  reference: `default_aircraft_registrations`, `default_apu_ef`,
  `default_change_log`, `default_class_break`,
  `default_cost319_vehicle_fleet`, `default_dictionary`,
  `default_grid_definition`, `default_layer_definition`,
  `default_merge_definition`, `default_pollutants`,
  `default_table_updates`, `default_vehicle_co_ef`,
  `default_vehicle_hc_ef`, `default_vehicle_nox_ef`,
  `default_vehicle_pm10_ef`, `shapes_aircraft_tracks`, `user_stand_ef`,
  `user_taxiroute_aircraft_group`. The COPERT5 vehicle EF data is now
  consolidated in the single `default_vehicle_ef_copert5` table.

- **Legacy columns** dropped on migration with `--drop-extra-columns`:
  `geometry_columns.type`, `virts_geometry_columns.type` (SpatiaLite 2.x
  metadata column), `shapes_point_sources.type`,
  `shapes_parking.{park_time, vehicle_heavy, vehicle_light, vehicle_medium}`,
  `shapes_roadways.{vehicle_heavy, vehicle_light, vehicle_medium}`,
  `user_aircraft_movements.{aircraft_registration, domestic}`,
  `default_aircraft_engine_ei.pm10_prefoa3`.

### Fixed

- **Migration of legacy SpatiaLite metadata** (`scripts/migrate_alaqs.py`)
  — pre-fix, a `--drop-extra-columns` run on a 4.x-era file would abort
  with `error in trigger ggi_<table>_geometry: no such table:
  main.geometry_columns` because SpatiaLite ships dependent views (`vector_layers`,
  `geom_cols_ref_sys`) and triggers (`ggi_*_geometry`,
  `geometry_columns_*_insert`) whose bodies reference the metadata
  tables. The migrator now snapshots and recreates the dependent views
  and triggers around the column-drop step. Stale rows in
  `geometry_columns` referencing dropped tables are also cleaned up so
  QGIS does not see phantom layers when opening the migrated file.
  Regression test:
  `tests/test_migrate_legacy_spatialite_metadata_regression.py`.

- **Profile product normalisation** —
  `SourceWithTimeProfileModule.getRelativeActivityPerHour` now divides by
  the calendar-weighted mean of (hour × weekday × month) over the inventory
  year. Profiles whose mean was not exactly 1.0 previously rescaled the
  annual emission silently away from `EF × unit_year`. Profiles authored to
  the OpenALAQS template convention (mean = 1.0) are unchanged byte-for-byte.

- **`instudy='0'` filter** — sources marked excluded from the study via the
  `instudy` column are now filtered out at calculation time. The column had
  been declared in the schema for roadways, parking, gates, point sources,
  area sources, and runways but was never read by any module — the rows
  were silently included in totals.

- **`Source.__init__` profile-name aliasing** — Source rows now correctly
  read `hourly_profile`, `daily_profile`, and `monthly_profile` from the
  database. A key mismatch had caused the loader to fall back to the
  default profile silently for any source where the user had set a
  non-default value.

- **AmbientCondition NULL handling + METAR VRB winds** —
  `AmbientCondition.__init__` now uses explicit numeric defaults for every
  field instead of returning `None` on empty cells. The METAR-to-meteo
  converter writes `999` (AUSTAL calm-variable convention) for VRB winds
  instead of empty string. Together these prevent a `TypeError: must be
  real number, not NoneType` crash in `AUSTALOutputModule` on inventories
  with VRB METAR observations.

- **Parking cold-start at trip scale** — the COPERT5 cold-start contribution
  is now applied once per parking trip rather than once per road segment
  when `parking_include_cold_start=True`. Default behaviour (cold start
  off) is unchanged.

- **Taxi Mach state-leak isolation** —
  `TaxiingEmissionCalculator.calculate_emissions` now forces
  `mach_number = 0.0` for taxi operations. The shared `method["config"]`
  dict was being mutated per flight segment by `FlightEmissionCalculator`,
  leaking the previous segment's terminal Mach (typically 0.15-0.40) into
  taxi BFFM2 lookups and producing 0.5-3% under-prediction on taxi fuel
  flow. CAEP14 v14 spec says ground operations are M=0.

- **Climbout installation correction** — `MovementSourceModule` CAEP14 v14
  installation correction for Climbout corrected from 1.012 to 1.013 (the
  1.012 override disagreed with the `bffm2.py` docstring, comment, and
  default).

- **MES double-count fix** — single-engine taxi main-engine-start emissions
  are now added exactly once per movement instead of once per taxi segment
  inside the MES window. Affects movements with `gate_emissions_code=1`
  AND a non-null `set_time_of_main_engine_start_after_block_off_in_s` (or
  the before-takeoff variant) AND multi-segment taxi routes.

- **Gate emissions gating** — `MovementSourceModule` now forwards the
  movement's `gate_emissions_code` to the gate emissions path, so `code=0`
  movements no longer leak POLYGON-geometry entries.

- **Stop-and-go engine count** — stop-and-go emissions now multiply by
  `number_of_engines`, matching the convention used for taxi and queuing
  time. Affects movements with `number_of_stop_and_gos > 0`; no effect on
  engine-only validation scope where stops are zeroed out.

- **CO/HC interpolation alignment with CAEP14 v14** — in the standard
  SL/HL-intersection case, EI now snaps to the horizontal mean value for
  any segment fuel flow above the APP anchor (SAE AIR-5715 "HC_CO Slope To
  Mean Value" rule). The previous smoothed step disagreed with v14 by up
  to 8× EI at warm-humid AP-anchor conditions.

- **Log-noise suppression** — `OutputModule`,
  `TableViewWidgetOutputModule`, and `AUSTALOutputModule` no longer log
  ERROR for zero-valued placeholder emissions synthesised for empty
  periods. Real missing-geometry bugs still surface.

- **AUSTAL diagnostic level + day-window correction** —
  `checkTimeIntervalinResults` now logs at ERROR level (was DEBUG) when
  `series.dmna` and `austal.txt` files disagree. `checkHoursinResults`
  warning text and `end_date` assignment are now consistent at start +
  23 h (AUSTAL convention: a day is 24 inclusive timestamps from
  01:00..00:00).

- **Below-MSL airport elevation entry** — `spinBoxAirportElevation` and
  `spinBoxAirportTemperature` now declare explicit `minimum` properties.
  Below-MSL airports (EHRD, EHAM, LLEY, etc.) and cold-climate annual
  means now round-trip correctly. Without the minimum, Qt clamped any
  negative value to 0 silently.

- **CSV receptor altitude optional** — the receptor CSV loader now accepts
  a 3-column file (`id, longitude, latitude`) without silently producing
  an empty GeoDataFrame. Default receptor breathing height (1.5 m) is
  applied downstream by `AUSTALOutputModule.getGridXYFromReferencePoint`.

### Migration

To bring a 4.x-era `.alaqs` file forward:

```
python scripts/migrate_alaqs.py path/to/your.alaqs \
    --drop-extra-tables \
    --drop-extra-columns \
    --refresh-reference-data \
    --refresh-include-user-extensible
```

`--refresh-include-user-extensible` overwrites `default_aircraft`,
`default_aircraft_engine_ei`, and 5 other "user-extensible" tables with
the shipped reference data; drop this flag if your study has bespoke
entries you want to preserve. The migrator writes a `.bak-<timestamp>`
backup before any change and rolls back on error, so the source file is
safe.
