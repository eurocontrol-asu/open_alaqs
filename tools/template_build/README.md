# Template build

For maintainers: the build-time tooling that produces the Open-ALAQS
plugin's canonical SpatiaLite templates, and when to run it.

## What this directory does

The Open-ALAQS plugin ships two pre-built SpatiaLite databases that act as
schema templates for user studies:

- `open_alaqs/core/templates/project.alaqs`: empty project file (the
  `.alaqs` a user creates and edits in QGIS)
- `open_alaqs/core/templates/inventory.alaqs`: empty inventory output
  file (`*_out.alaqs` produced by Generate Emission Inventory)

These templates are built by `generate_templates.py` from three inputs:

- `spatialite_base.alaqs`: bare SpatiaLite scaffold (this directory)
- `sql/*.sql`: table-creation scripts (this directory)
- `open_alaqs/database/data/*.csv`: frozen reference-data CSVs (in the
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
The shipped templates were built this way (pandas 2.2.1, SQLite 3.45.1).
The numeric columns of the 8 `shapes_*` tables are declared `REAL` (65
columns; `DECIMAL` would let the QGIS SpatiaLite provider type them from the
stored data instead of as Double); `instudy` of `shapes_runways` and
`shapes_taxiways` stays `DECIMAL`, a flag. The reference tables equal the
CSVs exactly; `tests/test_database.py::test_template_data` compares them
with `pandas.testing.assert_frame_equal` at its default relative tolerance.

A rebuild differs from the shipped files only in the timestamps (of
`spatialite_history` and the creation dates of `user_study_setup`).

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

See also:

- [REFERENCE_DATA.md](../../documents/methods/REFERENCE_DATA.md): the reference tables and their sources
- [migrate_alaqs.py](../../scripts/README.md#migrate_alaqspy): bringing existing studies to the template schema
- [tools/test_fixtures](../test_fixtures/README.md): refreshing test fixtures
