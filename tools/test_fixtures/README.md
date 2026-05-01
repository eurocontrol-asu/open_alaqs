# tools/test_fixtures/

Maintainer scripts that update test fixture files when source data
or calculator output drifts. None of these are pytest tests; pytest
does not collect or run them. They are invoked by hand when needed.

## When to use each script

| Script | When to run |
|---|---|
| `regenerate_default_aircraft_profiles.py` | After `open_alaqs/database/data/default_aircraft_profiles.csv` is updated and the `default_aircraft_profiles` tables in the 6 committed `.alaqs` fixtures need to follow. Brings them back into alignment with the canonical CSV. |
| `regenerate_emission_calculation_references.py` | After a calculator change that shifts numeric output. Regenerates 16 reference outputs (`.gpkg` vector layers + `.csv` tables) used by `tests/test_emission_calculation.py`. The test compares its current output to these references; when the references are stale the test xfails. |
| `regenerate_anp_reference_csv.py` | When the ANP test fixture's `ANP_emissions_table_by_aggregation_co.csv` has drifted from the current calculator output. Snapshots the current output into the canonical 14-column CSV format. |

## Why they live outside `tests/`

Keeping them under `tests/` confused pytest's collection (the scripts
are not tests, they are tools for refreshing tests' input data). Moving
them to `tools/test_fixtures/` makes the role explicit: build/maintenance
tooling, not part of the test suite itself.

## Usage

All three scripts assume `QT_QPA_PLATFORM=offscreen` for headless QGIS.
Run from the repo root:

```bash
QT_QPA_PLATFORM=offscreen python3 tools/test_fixtures/regenerate_default_aircraft_profiles.py
QT_QPA_PLATFORM=offscreen python3 tools/test_fixtures/regenerate_emission_calculation_references.py
QT_QPA_PLATFORM=offscreen python3 tools/test_fixtures/regenerate_anp_reference_csv.py
```

After running, re-run the affected pytest tests to confirm the xfail
mark can be removed.
