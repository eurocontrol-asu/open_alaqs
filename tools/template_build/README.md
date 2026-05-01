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
  (`get_engine`, `connect`, `apply_sql`, `MATCH_PATTERNS`) from
  `generate_templates.py` for SQLite/SpatiaLite plumbing

The whole tree could be deleted without affecting the user-installed
plugin's runtime behaviour, because the built templates are checked in
to `open_alaqs/core/templates/`.

## Regenerating the templates

The full regeneration path is currently **incomplete**: only
10 of the 16 user-data tables have matching `sql/*.sql` files, and the
remaining 6 (`default_aircraft`, `default_aircraft_engine_ei`,
`default_aircraft_profiles`, `default_aircraft_apu_ef`,
`default_aircraft_start_ef`, `default_helicopter_engine_ei`) used to be
seeded from the now-removed `database/src/new_blank_study.alaqs`
during the legacy build pipeline. That dependency was dropped without
replacing the seeding mechanism, so running

```bash
python3 -m tools.template_build.generate_templates
```

will currently fail at the CSV-import step with `no such table:
default_aircraft`. Treat the templates as **frozen build artefacts**:
they are checked in to `open_alaqs/core/templates/` and re-shipped
unchanged. To update them, edit the SpatiaLite databases directly with
your tool of choice, or restore the full create-from-interfaces flow
(see git history of `open_alaqs/database/generate_templates.py` before
the move to this directory).

## What this directory is still useful for

- The test suite imports four helper functions from
  `generate_templates.py` (`get_engine`, `connect`, `apply_sql`,
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
