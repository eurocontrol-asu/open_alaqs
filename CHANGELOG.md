# Changelog

All notable changes to Open-ALAQS are listed here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) loosely; dates are
ISO 8601.

## [5.0.0] - 2026-04-30

First stable release after the rebuild. The 5.0 line is not
backwards-compatible at the file-format level with the 4.x series — see the
**Migration** section below for how to bring an old `.alaqs` study forward.

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
