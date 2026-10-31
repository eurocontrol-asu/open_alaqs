# Open-ALAQS validation guide

This guide says what to run to validate a new build of the Open-ALAQS plugin
and of `openalaqs_standalone`, and how to judge the results. It is for
maintainers and for the reviewer who signs off a build. What the CAEP14
reference implements, and how to update it, is in
[CAEP14_VALIDATION.md](../../openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md).

Contents:

- [Validation targets](#validation-targets)
- [What the user brings](#what-the-user-brings)
- [V1 - Plugin vs reference workbook (training example)](#v1---plugin-vs-reference-workbook-training-example)
- [V2 - Standalone vs pinned plugin outputs](#v2---standalone-vs-pinned-plugin-outputs)
- [V3 - Plugin, new vs prior build (campaign study)](#v3---plugin-new-vs-prior-build-campaign-study)
- [V4 - Standalone on the campaign study](#v4---standalone-on-the-campaign-study)
- [V5 - Plugin vs standalone on the same study](#v5---plugin-vs-standalone-on-the-same-study)
- [Tolerances](#tolerances)
- [Failure triage](#failure-triage)
- [Data shipped with this package](#data-shipped-with-this-package)
- [Companion code](#companion-code)
- [Running the automated tests](#running-the-automated-tests)
- [Submission template](#submission-template)

## Validation targets

Two reference targets:

- **CAEP14**: the EUROCONTROL training study shipped in this package
 (`example/training/`; its 15-movement variant `training_v3.alaqs` in
 `openalaqs_standalone/validation/data/`), computed with the CAEP/ICAO
 method by the CAEP14 reference implementation. Tests that the
 calculation primitives agree to float64 noise.
- **A real-airport campaign**: a multi-runway, multi-hundred-movement study
 the user maintains locally. Tests scale, multi-runway dispatch, and end-to-end
 AUSTAL prep. This guide refers to it as *the campaign study*; substitute the
 filename the user uses (e.g. `<study>.alaqs`).

The validation matrix:

| | Training fixture (CAEP14) | Campaign study |
| --- | ------------------------ | ------------------------ |
| **Plugin (QGIS)** | V1 | V3 |
| **Standalone (CLI)** | V2 | V4 |

Plus one cross-check:

- **V5**: Standalone vs Plugin on the same study (per-movement diff, both
 CAEP14 and campaign).

This document is self-contained. Hand it to a reviewer along with
the artifacts each validation produces, and the reviewer can perform the
comparison and assessment without further context.

## What the user brings

For each validation the user runs, the reviewer needs four things:

1. **Build identity**: `metadata.txt` version line for the plugin, git
 commit / archive checksum for the standalone, the exact CLI invocation
 used, and the QGIS version when applicable.
2. **Inputs used**: md5 of the `.alaqs` file under test, name of the
 campaign study, time window if any.
3. **Outputs produced**: per-movement CSV, per-source CSV, and (for AUSTAL
 runs) the `austal_folder` contents.
4. **Environment metadata**: OS, Python version, pandas/numpy/pyproj
 versions (relevant for floating-point reproducibility).

A copy-paste template is at the end of this file under
[Submission template](#submission-template).

## V1 - Plugin vs reference workbook (training example)

**Goal**: confirm the plugin's `bymode` calculation reproduces the
CAEP14 reference within the PASS band of [Tolerances](#tolerances) per
pollutant per movement.

### Inputs (all shipped in this package)

```
example/training/training.alaqs project file
example/training/training_out.alaqs canonical CAEP14 inventory
example/training/training_movements.csv 13 movements
example/training/training_meteo.csv 75 hourly meteo rows
example/training/training_ads_b_data.csv ADS-B tracks, imported into the inventory (movement 11)
example/training/training_validation_reference.xlsx reference NOx, CO, HC, PM, SO2
 per movement (the plugin's results beside the CAEP14 reference implementation)
```

### Procedure (QGIS)

1. Open QGIS 3.40 with the Open-ALAQS plugin installed from the package.
2. Open `example/training/training.alaqs` with the plugin's toolbar button
 *Load an Open ALAQS project* (QGIS Project > Open does not open an `.alaqs`).
3. Open-ALAQS Toolbar > *Calculate Emissions Inventory* (window *Generate
 Emission Inventory*) with the settings of
 [TUTORIAL_ROTTERDAM.md](../user/TUTORIAL_ROTTERDAM.md): `training_movements.csv` for movements,
 `training_meteo.csv` for meteorology, `training_ads_b_data.csv` as ADS-B
 table, grid 100 x 100 x 20 cells of 250 x 250 x 50 m. Save as
 `training_out_REBUILT.alaqs` next to the original so the original is
 preserved. (Headless equivalent:
 `QT_QPA_PLATFORM=offscreen python3.12 tools/test_fixtures/rebuild_training_example_inventory.py --out example/training/training_out_REBUILT.alaqs`.)
4. Open-ALAQS Toolbar > *Visualize Emission Calculation* on `training_out_REBUILT.alaqs`.
 Method: **bymode** (default). NOx ambient correction: **off** (default).
 Emission Source Type: **MovementSource**. In the **Output Formats** tab,
 set the Emissions table *Output view type* to **by source** (the default,
 *by aggregation*, gives one total row; *by source* gives the rows of each
 movement, which the reviewer sums by `source_name`).
5. Click *View Emissions Table* and export it with *Export CSV*.

The same export steps (method, NOx correction, *by source*, *Export CSV*)
apply to every plugin CSV this guide asks for.

### Outputs to send

- `training_out_REBUILT.alaqs` (the regenerated inventory), or the md5 if
 the file is too large.
- The exported per-movement CSV.
- The Open-ALAQS log lines from the *Visualize Emission Calculation* run.

### What the reviewer does

- Compare the plugin results on `training_out_REBUILT.alaqs` with those on
 `example/training/training_out.alaqs` (the canonical inventory): they must
 be bit-identical per movement. The files themselves are not md5-identical
 (a rebuild differs in bytes), so do not md5-compare them.
- For each movement (13 total), read the plugin CSV and read
 `training_validation_reference.xlsx`. Diff per pollutant and report the
 per-movement deltas in the three [tolerance bands](#tolerance-bands).
 For a quick installation check,
 `compare_inventory_to_reference.py <csv> --method=bymode` does this diff
 against the workbook's reference column with a coarser threshold (see
 [Tolerances](#tolerances)).
- Surface any non-PASS rows in a table, propose root-cause hypotheses
 (EF table change, profile table change, ambient-correction toggle,
 meteo expansion); see [Failure triage](#failure-triage).

## V2 - Standalone vs pinned plugin outputs

**Goal**: confirm the standalone reproduces the pinned plugin CSVs of the
CAEP14 fixture (`training_v3.alaqs`) within the PASS band (matching method,
matching ambient settings). The current build agrees to float64 noise,
except `bymode` with the NOx correction ([Current agreement](#current-agreement)). V2 compares the standalone with these plugin
outputs, not with the reference implementation itself; the reference is
checked against the same CSVs by `compute_caep14_reference.py`
([CAEP14_VALIDATION.md](../../openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md#running-the-reference)).

### Inputs

The four pinned plugin per-movement CSVs shipped at:

```
openalaqs_standalone/validation/data/plugin_output/training_movements_bymode.csv
openalaqs_standalone/validation/data/plugin_output/training_movements_bymode_nox_corr.csv
openalaqs_standalone/validation/data/plugin_output/training_movements_bffm2_anchor.csv
openalaqs_standalone/validation/data/plugin_output/training_movements_bffm2_traj.csv
```

These are pinned plugin outputs used as the comparison target for the
standalone. They were generated from the 15-movement training_v3.alaqs
fixture (13 fixed-wing + 2 helicopter). Each contains only
`source_type = "Movement"` rows: aircraft trajectory contributions
only, with the plugin's separate gate / APU / engine-start source
types excluded.

The matching standalone fixture is:

```
openalaqs_standalone/validation/data/training_v3.alaqs
```

### Comparing like with like: `--aircraft-only`

The standalone's per-movement CSV holds the movement total by default
(gate, APU and engine start folded in); the pinned plugin CSVs hold the
trajectory only. Pass `--aircraft-only` to the `aircraft` subcommand to
make the two comparable (see
[USAGE.md](../../openalaqs_standalone/USAGE.md#aircraft-only-output)).
`training_v3.alaqs` has no gate, APU or engine-start emissions, so on this
fixture the flag changes nothing and V2 passes as written; keep it so the
procedure also holds on other studies.

### Procedure (terminal)

From the repository root, with `PYTHONPATH=.`:

```bash
# 1. bymode (default), ambient correction off
python -m openalaqs_standalone aircraft \
 openalaqs_standalone/validation/data/training_v3.alaqs \
 --out v2_bymode.csv --method bymode \
 --aircraft-only

# 2. bymode + NOx ambient correction on
python -m openalaqs_standalone aircraft \
 openalaqs_standalone/validation/data/training_v3.alaqs \
 --out v2_bymode_nox_corr.csv --method bymode \
 --apply-nox-corrections --aircraft-only

# 3. BFFM2 anchor
python -m openalaqs_standalone aircraft \
 openalaqs_standalone/validation/data/training_v3.alaqs \
 --out v2_bffm2_anchor.csv --method bffm2_anchor \
 --aircraft-only

# 4. BFFM2 trajectory
python -m openalaqs_standalone aircraft \
 openalaqs_standalone/validation/data/training_v3.alaqs \
 --out v2_bffm2_traj.csv --method bffm2_traj \
 --aircraft-only
```

**Meteo**: the pinned plugin CSVs were made with the study meteo
(`tbl_InvMeteo`), which the plugin applies to the BFFM2 ambient correction
and to the NOx correction. The standalone uses it by default
(`--use-meteo`); do not pass `--isa-meteo`, which puts the BFFM2 methods
and the NOx-corrected run off the pinned files (see
[Effect of the meteo setting](#effect-of-the-meteo-setting)).

Expected per-movement aircraft-only totals (sum across 15 movements
in training_v3.alaqs: 13 fixed-wing + 2 helicopter, kg):

| Method                              | NOx    | CO     | HC    |
| ----------------------------------- | -----: | -----: | ----: |
| bymode                              | 29.197 | 21.812 | 1.456 |
| bymode + `--apply-nox-corrections`  | 27.963 | 21.812 | 1.456 |
| bffm2_anchor                        | 27.990 | 20.908 | 1.407 |
| bffm2_traj                          | 15.311 | 21.546 | 1.409 |

(Measured with the standalone of this version, default meteo and
`--aircraft-only`, on `training_v3.alaqs`; equal to the sums of the pinned
plugin CSVs. Any drift here for the shipped standalone indicates a
regression. For a NEW build of the standalone, drift is expected and is
the V2 result.)

If you are running the 13-movement example inventory
`example/training/training_out.alaqs` (no helicopters) as a smoke test,
the totals must match the
[quick smoke test](../../openalaqs_standalone/USAGE.md#quick-smoke-test)
of USAGE.md, with or without `--aircraft-only`.

### Outputs to send

- The four `v2_*.csv` files produced by the standalone (with
  `--aircraft-only`).
- The standalone version string (`__version__`, the last line of
  `openalaqs_standalone/__init__.py`, or git commit / archive md5).

### What the reviewer does

- For each `v2_*.csv`, per-movement diff against the matching pinned file at
  `openalaqs_standalone/validation/data/plugin_output/training_movements_*.csv`.
  The rows are keyed differently: the standalone CSV has one row per
  movement with an `oid` column; the plugin CSV identifies the movement by
  the `source_name` string (`id 1: A20N A 24 → G4  2025-12-01 06:05`), so
  take the number after `id ` as the oid and sum the plugin rows of each
  movement (as
  `openalaqs_standalone/validation/tests/test_plugin_csv_vs_reference.py`
  does).
  Expected: PASS everywhere; the measured agreement of this version is in
  [Current agreement](#current-agreement).
- Cross-method sanity (no aircraft should produce zero CO, CO2, HC, NOx,
  SOx or PM10; SOx is fuel × 0.758 g/kg for every movement of this
  fixture (jet fuel), helicopters included; all 15 movements should appear
  in each output).
- Compare the aggregate NOx totals against the expected table above.

## V3 - Plugin, new vs prior build (campaign study)

**Goal**: confirm the plugin produces stable per-movement outputs on the
multi-runway, multi-hundred-movement campaign study the user
maintains. There is no independent reference; the new build is compared
with the prior validated build, and every row is expected in the PASS band
unless a change between the builds explains it.

### Inputs

- `<campaign_study>.alaqs`: the user's local file, with multi-runway
 layout, hundreds to thousands of movements, real meteo, real receptors.
- The previous validated build's per-movement CSV (call it `prior_v3.csv`).
- The same user's QGIS project and any per-study tweaks
 (e.g. `tow_ratio` overrides in `user_aircraft_movements`).

### Procedure (QGIS)

1. Open QGIS 3.40 with the **new** plugin installed.
2. Open `<campaign_study>.alaqs` with the plugin's toolbar button *Load an
 Open ALAQS project*.
3. Open-ALAQS Toolbar > *Visualize Emission Calculation* on the study's
 inventory (`*_out.alaqs`). Run for the inventory year
 declared in `user_study_setup`. Method as previously validated
 (typically `bymode`).
4. Export the per-movement table to CSV as in V1 step 4 and 5.

### Outputs to send

- The per-movement CSV from the new build (call it `new_v3.csv`).
- The corresponding `prior_v3.csv` (user already has this).
- The `metadata.txt` version line for the new build.
- Movement count, total NOx (kg), total CO (kg), total HC (kg) for both
 runs: a useful sanity check before per-movement comparison.

### What the reviewer does

- Row-align `new_v3.csv` and `prior_v3.csv` by movement oid + direction.
- Per-movement absolute and relative deltas per pollutant.
- Summary table: count of rows in each [tolerance band](#tolerance-bands).
- If failures exist, group by `aircraft_icao`, `engine_name`,
 `profile_id`, and `runway` to find the dominant pattern.
- Likely-cause hypotheses, drawing on knowledge of which files changed
 between the prior and new builds.

## V4 - Standalone on the campaign study

**Goal**: confirm the standalone produces the same per-movement results as
the plugin (V3) on the campaign study, and is unchanged from its own
prior-build output for the same input.

### Inputs

- `<campaign_study>.alaqs` (same file as V3).
- The standalone build under test.
- The plugin CSV from V3 (so V5 can also be run from these artifacts).

### Procedure (terminal)

```bash
# aircraft compute only (movement-by-movement totals)
python -m openalaqs_standalone aircraft \
 <campaign_study>.alaqs \
 --out v4_aircraft.csv \
 --method bymode \
 --aircraft-only \
 --processes 8

# full austal pipeline (six folders including aircraft cell sources)
python -m openalaqs_standalone austal \
 <campaign_study>.alaqs \
 --year <year_from_user_study_setup> \
 --include-aircraft --aircraft-method bymode \
 --processes 8 \
 --out ./v4_austal/
```

`--aircraft-only` because `v4_aircraft.csv` is compared with the plugin's
Movement rows in V5 (see V2). The flag does not change the `austal` run.

### Outputs to send

- `v4_aircraft.csv`: per-movement aircraft-trajectory totals.
- `v4_austal/emissions_folder/emissions.parquet`: hourly per-source rates.
- `v4_austal/config_folder/config.json`: write settings, grid, time window.
- `v4_austal/sources_folder/sources.parquet`: source geometry + metadata.
- Standalone version, CLI invocation, walltime, peak memory if known.

### What the reviewer does

- Compare `v4_aircraft.csv` against V3's plugin CSV per-movement (per V5
 below).
- Cross-check `emissions.parquet` aggregates by source type (the
 `source_type` of `sources.parquet`: `aircraft`, `road`, `parking`,
 `point`, `area`, `engine_test`, `gate`; gate emissions are folded into
 the aircraft totals) against per-type totals from V3's plugin run when
 reported.
- Verify `config.json` has the expected keys
 (`apply_nox_corrections`, `grid.utm_epsg`, `grid.nx`/`ny`,
 `start_dt`/`end_dt`, `selected_pollutants`); the keys are listed in
 [USAGE.md](../../openalaqs_standalone/USAGE.md#reading-configjson).

## V5 - Plugin vs standalone on the same study

**Goal**: every per-movement row in the plugin's CSV matches the
standalone's `aircraft` CSV within the PASS band, on the same study (both
CAEP14 and the campaign). On the CAEP14 fixture the current build agrees to
float64 noise, except `bymode` with the NOx correction.

### Inputs

- For CAEP14: the V1 plugin CSV and a standalone run on the same inventory
 (`aircraft training_out_REBUILT.alaqs --aircraft-only`), or the pinned
 plugin CSVs and the V2 outputs on `training_v3.alaqs`.
- For campaign: V3 plugin CSV + V4 standalone `aircraft` CSV (run with
 `--aircraft-only`, see V4).

### What the reviewer does

- Build the row-aligned diff table keyed by `(oid, departure_arrival)`
 (plugin side: the oid is the number after `id ` in `source_name`; sum the
 plugin rows of each movement).
- Report the [tolerance bands](#tolerance-bands) per pollutant.
- For CAEP14: expect 100 % PASS. Any row outside is a regression.
- For campaign: report the band distribution. Investigate any
 PASS-WITH-DRIFT rows that did not exist in the prior build's V5 result.

## Tolerances

This section is the one place for the tolerance bands and for the measured
agreement between the plugin, the standalone and the CAEP14 reference.

### Vocabulary

This guide uses three terms, from strictest to loosest:

- **Bit-identical**: the same IEEE 754 binary64 value; in a CSV, the same
  value to all digits the CSV keeps (15 to 17 significant digits with
  `repr` or `%.17g`). Used only for the same code on the same input (V1,
  rebuilt against shipped inventory).
- **Float64 noise**: a relative difference of about 1e-10 or less, from a
  different order of summation or of operations. Two implementations that
  agree to this level compute the same thing.
- **PASS band**: a relative difference of at most 1e-6 (below).

### Relative tolerance

`|Δ / max(|ref|, ε)|` with `ε = 1e-30` (so zero-reference values don't
explode). Compute per (movement, pollutant) cell, not aggregated.

### Tolerance bands

- **PASS** (`≤ 1e-6`): the same calculation; differences come from
 floating-point order or a formula written in a slightly different but
 equivalent form (for example the NOx correction with the pressure in hPa).
- **PASS-WITH-DRIFT** (`≤ 1e-4`): subtle drift, likely from one of:
 reordered summation, slightly different interpolation order, or
 reference-data refresh. Investigate; usually safe.
- **FAIL** (`> 1e-4`): a real difference. Pollutant or movement is
 responding to a different code path.

The checks shipped with the code use their own, coarser thresholds:
`test_plugin_csv_vs_reference.py` fails above 2e-4 relative (plugin
against reference and standalone, 15 movements, the three methods and
`bymode` with the NOx correction), and
`compare_inventory_to_reference.py` flags a movement above 0.5 % (exit
code 0 when all movements pass).

### Current agreement

Measured on this version, largest relative difference per movement and
pollutant:

| Comparison | Fixture | Agreement |
| --- | --- | --- |
| Standalone vs pinned plugin CSVs, three methods (V2) | `training_v3.alaqs`, 15 movements | 3.9e-11 |
| Standalone vs pinned plugin CSVs, `bymode` with NOx correction | `training_v3.alaqs` | 2.9e-7 |
| Reference vs plugin, three methods | `training_v3.alaqs` | 3.4e-13 (0.00 % on 15 of 15 movements) |
| Reference vs plugin, `bymode` with NOx correction | `training_v3.alaqs` | 3.1e-6 |
| Reference vs plugin, `bymode` and `bffm2_anchor` on every movement, `bffm2_traj` on the ANP movements | `example/training/training_out.alaqs`, 13 movements | 3e-13 |
| Reference vs plugin, `bffm2_traj` on movement 11 (CUSTOM) | `training_out.alaqs` | 2.6e-13 |
| Reference vs plugin, `bymode` with NOx correction | `training_out.alaqs` | 1e-6 to 3e-6 on the six departures (largest on movements 10 and 11) |
| Reference vs standalone, helicopters at mixing heights 914.4, 600, 300 and 100 m, with and without a helipad gate | `training_v3.alaqs` | 1e-10 |
| Reference vs standalone net of the gate emissions (APU, GSE, engine start, which the reference does not model); measured before the 5.4.1 fuel-flow scaling | operational study, 159 movements, 33 engines | 7e-10 (`bymode`), 6.5e-10 (`bffm2_anchor`), 4e-8 on the CUSTOM movements of `bffm2_traj`; one ANP departure of `bffm2_traj` 6e-4 on NOx (0.02 % of its take-off fuel, in an hour with a 400 m mixing height; cause not isolated) |

The rows on `training_out.alaqs` and on the operational study are not part
of the test suite.

### Effect of the meteo setting

The pinned plugin CSVs are made with the study meteo. Run at ISA instead
(the standalone's `--isa-meteo`, or the reference without `--use-meteo`),
the largest per-movement NOx difference from the pinned files is 8 % for
`bymode` with the NOx correction, 22 % for `bffm2_anchor` and 34 % for
`bffm2_traj`. `bymode` without the correction and the helicopters are
unaffected.

## Failure triage

### Per-pollutant aggregate sanity check

For each pollutant, sum across all movements in both files; compute the
ratio of totals. If the per-row diff is dominated by a small number of
movements (e.g. 5 of 1561), the aggregate ratio will be close to 1.0
while the per-row max-delta will be large. Both are useful diagnostics
and the reviewer should report both.

### Failure triage rules

1. **One pollutant, all movements affected**: likely an EF table
 refresh (default_aircraft_engine_ei, default_stationary_ef).
2. **All pollutants, one engine family**: engine row replaced or its
 EI numbers updated.
3. **All pollutants, one profile**: default_aircraft_profiles row
 updated.
4. **All pollutants, BFFM2 only**: BFFM2 fuel-flow code path
 regression (`twin_quadratic_fit_method.py`, `bffm2.py`).
5. **NOx only, takeoff/climb-out segments only**:
 `--apply-nox-corrections` flag flipped between runs, or
 `nox_correction_ambient.py` changed.
6. **One aircraft type, all movements**: `default_aircraft.csv` row
 for that ICAO changed (different engine_name or profile_id).

Failures seen in earlier builds, with their symptoms and the code to
check, are listed in
[REGRESSION_PATTERNS.md](../developer/REGRESSION_PATTERNS.md).

## Data shipped with this package

| Path | Purpose |
| --------------------------------------------------------------------- | ---------------------------------------- |
| `example/training/training.alaqs` | CAEP14 study project file |
| `example/training/training_out.alaqs` | CAEP14 canonical inventory |
| `example/training/training_movements.csv` | 13-movement CAEP14 set |
| `example/training/training_meteo.csv` | 75 hourly meteo rows |
| `example/training/training_ads_b_data.csv` | ADS-B tracks imported into the inventory, flown by movement 11 ([details](../../openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md#movement-11-phbba-custom-track)) |
| `example/training/training_validation_reference.xlsx` | Per-movement reference totals (plugin beside the CAEP14 reference) |
| `openalaqs_standalone/validation/data/training_v3*.alaqs` | Derived multi-source CAEP14 variants |
| `openalaqs_standalone/validation/data/plugin_output/training_movements_bymode.csv` | Pinned plugin output, `bymode` |
| `openalaqs_standalone/validation/data/plugin_output/training_movements_bymode_nox_corr.csv` | Pinned plugin output, `bymode`+corr |
| `openalaqs_standalone/validation/data/plugin_output/training_movements_bffm2_anchor.csv` | Pinned plugin output, `bffm2_anchor` |
| `openalaqs_standalone/validation/data/plugin_output/training_movements_bffm2_traj.csv` | Pinned plugin output, `bffm2_traj` |
| `openalaqs_standalone/validation/data/plugin_output/training_sources_bymode.csv` | Pinned plugin output, stationary sources, `bymode` |
| `openalaqs_standalone/validation/data/training_validation_reference.xlsx` | Plugin beside the CAEP14 reference on `training_v3.alaqs` (15 movements, helicopters included) |

The pinned plugin outputs are made by the plugin of this version, run
headlessly (`regenerate_plugin_csvs.py`), with the study meteo. How they
and the workbooks are regenerated is in
[CAEP14_VALIDATION.md](../../openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md#updating-the-reference-and-the-pinned-outputs).

The campaign study is the user's local artifact and is not shipped.

## Companion code

The validation tools of `openalaqs_standalone/validation/tools/` (the
reference, the headless plugin re-export, the workbook builder, the
workbook diff) are listed in
[CAEP14_VALIDATION.md](../../openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md#files).
Other code used by these validations:

| Code path | Use |
| ---------------------------------------------------------------------------------- | -------------------------------------------- |
| `tools/test_fixtures/rebuild_training_example_inventory.py` | Rebuild `example/training/training_out.alaqs` from the example inputs |
| `openalaqs_standalone/validation/tests/test_plugin_csv_vs_reference.py` | Plugin = reference = standalone, 15 movements, 2e-4 |
| `openalaqs_standalone/validation/tests/test_bffm2_ambient_propagation_regression.py` | BFFM2 EI regression pytest |
| `scripts/migrate_alaqs.py` | Upgrade a legacy `.alaqs` to current schema |
| `scripts/migrate_alaqs_gui.py` | Qt5 GUI wrapper around the migration tool |

## Running the automated tests

Run the two suites separately, from the repository root:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest --run-slow tests
python -m pytest openalaqs_standalone/validation/tests
```

Together on one command line, pytest takes `openalaqs_standalone/pyproject.toml` as its configuration, the repository's `conftest.py` is not loaded, and `--run-slow` is not recognised. Slow tests (`@pytest.mark.slow`, among them `tests/test_emission_calculation.py`) run only with `--run-slow`. Calculations run directly on the bundled `.alaqs` fixtures can write cache tables into them (`test_bundled_fixture_hygiene` then fails): run ad hoc calculations on copies, keep the test checkout clean, and give pytest a `--basetemp` with a few GB of space (the plugin suite used 3.5 GB).

## Submission template

Copy this template into your validation submission and fill in the
values for the validations you ran.

```
=== Build identity ===
Plugin metadata.txt version: ____
Standalone version/commit: ____
QGIS version: ____
Python version: ____
pandas / numpy / pyproj: ____
OS: ____

=== Validations performed ===
[ ] V1 Plugin vs reference workbook (training example)
[ ] V2 Standalone vs pinned plugin outputs (all 4 method variants)
[ ] V3 Plugin, new vs prior build (campaign study)
[ ] V4 Standalone on the campaign study
[ ] V5 Plugin vs standalone on the same study (CAEP14 + campaign)

=== Inputs ===
Campaign study filename: ____
Campaign study .alaqs md5: ____
Inventory year used: ____
Method: bymode | bffm2_anchor | bffm2_traj
NOx ambient correction: off | on
Time window (if any): ____

=== V1 deliverables ===
 Per-movement results, rebuilt vs shipped inventory: identical | differ
 V1 per-movement CSV: attached
 Plugin log excerpt: attached

=== V2 deliverables ===
 v2_bymode.csv: attached
 v2_bymode_nox_corr.csv: attached
 v2_bffm2_anchor.csv: attached
 v2_bffm2_traj.csv: attached

=== V3 deliverables ===
 new_v3.csv: attached
 prior_v3.csv: attached (or md5)
 Movement count (new / prior): ____ / ____
 Total NOx (kg) (new / prior): ____ / ____

=== V4 deliverables ===
 v4_aircraft.csv: attached
 v4_austal/config_folder/config.json: attached
 emissions.parquet aggregates per source type:
 aircraft (gate folded in): ____ kg NOx
 road: ____ kg NOx
 parking: ____ kg NOx
 point: ____ kg NOx
 area: ____ kg NOx
 engine_test: ____ kg NOx

=== Request to the reviewer ===
Please:
 1. Check per-movement results on the rebuilt vs the shipped inventory (V1).
 2. Per-movement diff with 1e-6 / 1e-4 tolerance bands for V1, V2, V3, V4.
 3. V5 cross-check (plugin vs standalone on the same study).
 4. Failure triage on any FAIL rows using the rules in
 VALIDATION_GUIDE.md "Failure triage rules".
 5. Sign-off statement: PASS / PASS-WITH-DRIFT / FAIL per validation.
```

See also:

- [CAEP14_VALIDATION.md](../../openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md): what the CAEP14 reference implements and how to update it
- [REGRESSION_PATTERNS.md](../developer/REGRESSION_PATTERNS.md): known regression patterns
- [openalaqs_standalone USAGE.md](../../openalaqs_standalone/USAGE.md): the standalone's commands and options
- [AIRCRAFT_EMISSIONS.md](../methods/AIRCRAFT_EMISSIONS.md): the aircraft emission methods being validated
