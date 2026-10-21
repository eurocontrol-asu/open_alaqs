# tools/template_build/

Build-time tooling for the Open-ALAQS plugin's canonical SpatiaLite templates.

## What this directory does

The Open-ALAQS plugin ships two pre-built SpatiaLite databases that act as
schema templates for user studies:

- `open_alaqs/core/templates/project.alaqs` — empty project file (the
  `.alaqs` a user creates and edits in QGIS)
- `open_alaqs/core/templates/inventory.alaqs` — empty inventory output
  file (`*_out.alaqs` produced by Generate Emission Inventory)

These templates are built by `generate_templates.py` from three inputs:

- `spatialite_base.alaqs` — bare SpatiaLite scaffold (this directory)
- `sql/*.sql` — table-creation scripts (this directory)
- `open_alaqs/database/data/*.csv` — frozen reference-data CSVs (in the
  plugin tree, treated as source of truth)

## When this directory is used

**Never at user runtime.** The plugin uses the pre-built `.alaqs`
templates directly. This directory is only consulted when:

- A maintainer regenerates the templates after editing `database/data/*.csv`
  or `sql/*.sql`
- The test suite imports a few small helper functions
  (`get_engine`, `connect`, `apply_sql`, `apply_sqlserializable_registry`,
  `MATCH_PATTERNS`) from `generate_templates.py` for SQLite/SpatiaLite
  plumbing

The whole tree could be deleted without affecting the user-installed
plugin's runtime behaviour, because the built templates are checked in
to `open_alaqs/core/templates/`.

## Regenerating the templates

```bash
python3 -m tools.template_build.generate_templates
```

This builds `project.alaqs` and `inventory.alaqs` in
`open_alaqs/core/templates/` in three phases: tables owned by the
`SQLSerializable` interface classes, the 10 `sql/*.sql` tables, then the
reference data from `open_alaqs/database/data/*.csv`. The CSVs are read
with `float_precision="round_trip"`, so every stored REAL is the CSV text
value exactly (pandas' default parser is up to a few ulp off). It
overwrites the checked-in templates, so review the diff before committing.
The shipped templates are a rebuild of October 2026 (pandas 2.2.1, SQLite
3.45.1), made when the numeric columns of the shapes layers became `REAL`
(they were `DECIMAL`, which the QGIS SpatiaLite provider types from the
stored data instead of as Double). Compared table by table with the
templates shipped before, that rebuild changed:

- the declared type of 65 columns of 8 `shapes_*` tables, `DECIMAL` to
  `REAL` (`instudy` of `shapes_runways` and `shapes_taxiways` stays
  `DECIMAL`, a flag);
- the column order of `shapes_runways` (`touchdown_2` after `touchdown`;
  it was last in the earlier files, which had been migrated);
- the rowid order of the `shapes_buildings` and `shapes_receptor_points`
  rows of `geometry_columns`, `geometry_columns_auth`,
  `geometry_columns_statistics` and `geometry_columns_time` (same content);
- the timestamps and SQLite version of `spatialite_history` and the
  creation dates of `user_study_setup`;
- `project.alaqs` only: `default_vehicle_ef_copert5`, 26780 of 46435 rows
  (202590 cells) by up to 1e-12 relative (the earlier table was loaded
  with the default parser; the CSV holds 17-digit values such as
  0.17500000000000004, the earlier table 0.175), and 17 cells of
  `default_aircraft_engine_ei` by 1 ulp (the earlier table held, for
  example, 31.57 where the CSV has 31.569999999999997: 6BR010 and
  01P06BR014 TX `co_ei`, 4GE081 TO `nox_ei`, 07P27GE236 TO `pm10_nonvol`
  and `nvpm_ei`, ...). The shipped tables now equal the CSVs;
  `tests/test_database.py::test_template_data` accepts either. The
  training studies carry their own copies of these tables, so their
  results did not change.

A further rebuild differs from the shipped files only in the timestamps.

## What this directory is still useful for

- The test suite imports five helpers from `generate_templates.py`
  (`get_engine`, `connect`, `apply_sql`, `apply_sqlserializable_registry`,
  `MATCH_PATTERNS`) for SQLite/SpatiaLite plumbing.
- The 10 `sql/*.sql` files are still authoritative for their respective
  tables and could be used to bootstrap tooling that wants the schema
  in version-controlled text form.
- `spatialite_base.alaqs` is a clean SpatiaLite scaffold (no user
  tables) usable as a starting point for any future template
  regeneration work.

## Files

| File | Purpose |
|---|---|
| `generate_templates.py` | The build script |
| `spatialite_base.alaqs` | Bare SpatiaLite scaffold (input) |
| `sql/*.sql` | 10 CREATE TABLE scripts run against the scaffold (input) |
| `__init__.py` | Marks this directory as a Python package so test code can `from tools.template_build.generate_templates import ...` |
