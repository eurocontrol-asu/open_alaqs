# tools/test_fixtures/

Maintainer scripts that update test fixture files when source data
or calculator output drifts. None of these are pytest tests; pytest
does not collect or run them. They are invoked by hand when needed.

## When to use each script

| Script | When to run |
|---|---|
| `regenerate_default_aircraft_profiles.py` | After `open_alaqs/database/data/default_aircraft_profiles.csv` is updated and the `default_aircraft_profiles` tables in the 10 `.alaqs` files listed in the script (example, ANP and AIRPORT_A fixtures, `core/templates/project.alaqs`, and the three `openalaqs_standalone/validation/data/training_v3*.alaqs`) need to follow. Brings them back into alignment with the canonical CSV, keeping study-specific rows (CUSTOM, HELIPROF). |
| `regenerate_default_aircraft.py` | After the default profile columns of `open_alaqs/database/data/default_aircraft.csv` change. Updates `departure_profile` and `arrival_profile` in the fixtures whose `default_aircraft` is a copy of the CSV; skips the others. |
| `regenerate_emission_calculation_references.py` | After a calculator change that shifts numeric output. Regenerates 16 reference outputs (`.gpkg` vector layers + `.csv` tables) used by `tests/test_emission_calculation.py`. The test compares its current output to these references, cell by cell; it is a slow test (`pytest --run-slow`). An unknown `source_type` makes the script stop. |
| `regenerate_emission_vector_layers.py` | When only the 14 vector-layer `.gpkg` references of `tests/test_emission_calculation.py` (AIRPORT_A and ANP) need refreshing; `--start`/`--end` select a subset. Run as `python3 -m tools.test_fixtures.regenerate_emission_vector_layers`. |
| `rebuild_training_example_inventory.py` | After `example/training/training.alaqs` or the example's CSVs (movements, meteo, ADS-B) change. Rebuilds `training_out.alaqs` through the plugin's inventory creation and ADS-B import, with the settings of `documents/TEST_CASE_STUDY.md`; then rebuild the example workbook (`openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md`, step 3). |
| `regenerate_anp_reference_csv.py` | When the ANP test fixture's `ANP_emissions_table_by_aggregation_co.csv` has drifted from the current calculator output. Snapshots the current output into the canonical 14-column CSV format. |

## Why they live outside `tests/`

Keeping them under `tests/` confused pytest's collection (the scripts
are not tests, they are tools for refreshing tests' input data). Moving
them to `tools/test_fixtures/` makes the role explicit: build/maintenance
tooling, not part of the test suite itself.

## Usage

The scripts that drive the plugin assume `QT_QPA_PLATFORM=offscreen`
for headless QGIS. Run from the repo root:

```bash
QT_QPA_PLATFORM=offscreen python3 tools/test_fixtures/regenerate_default_aircraft_profiles.py
python3 tools/test_fixtures/regenerate_default_aircraft.py
QT_QPA_PLATFORM=offscreen python3 tools/test_fixtures/regenerate_emission_calculation_references.py
QT_QPA_PLATFORM=offscreen python3 -m tools.test_fixtures.regenerate_emission_vector_layers
QT_QPA_PLATFORM=offscreen python3 tools/test_fixtures/rebuild_training_example_inventory.py
QT_QPA_PLATFORM=offscreen python3 tools/test_fixtures/regenerate_anp_reference_csv.py
```

After running, re-run the affected tests (`pytest --run-slow
tests/test_emission_calculation.py` for the emission-calculation
references).
