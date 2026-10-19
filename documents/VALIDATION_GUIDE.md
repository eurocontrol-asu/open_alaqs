# Open-ALAQS validation guide

A runbook for validating any new build of the Open-ALAQS plugin and the
companion `openalaqs_standalone` against two reference targets:

- **CAEP14** - the canonical, ICAO-defined reference fixture shipped in this
 package (`example/training/`). Tests bit-identity for the calculation
 primitives.
- **A real-airport campaign** - a multi-runway, multi-hundred-movement study
 the user maintains locally. Tests scale, multi-runway dispatch, and end-to-end
 AUSTAL prep. This guide refers to it as *the campaign study*; substitute the
 filename the user uses (e.g. `<study>.alaqs`).

The validation matrix:

| | CAEP14 reference | Campaign study |
| --- | ------------------------ | ------------------------ |
| **Plugin (QGIS)** | V1 | V3 |
| **Standalone (CLI)** | V2 | V4 |

Plus one cross-check:

- **V5** - Standalone vs Plugin on the same study (per-movement diff, both
 CAEP14 and campaign).

This document is self-contained. Hand it to a reviewer along with
the artifacts each validation produces, and the reviewer can perform the
comparison and assessment without further context.

---

## What the user brings

For each validation the user runs, the reviewer needs four things:

1. **Build identity** - `metadata.txt` version line for the plugin, git
 commit / archive checksum for the standalone, the exact CLI invocation
 used, and the QGIS version when applicable.
2. **Inputs used** - md5 of the `.alaqs` file under test, name of the
 campaign study, time window if any.
3. **Outputs produced** - per-movement CSV, per-source CSV, and (for AUSTAL
 runs) the `austal_folder` contents.
4. **Environment metadata** - OS, Python version, pandas/numpy/pyproj
 versions (relevant for floating-point reproducibility).

A copy-paste template is at the bottom of this file under *Submission
template*.

---

## V1 - Plugin vs CAEP14 reference

**Goal**: confirm the plugin's `bymode` calculation reproduces the
CAEP14 reference within 1e-6 relative tolerance per pollutant per
movement.

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
2. Project → Open → `example/training/training.alaqs`.
3. Open-ALAQS Toolbar → *Generate Emissions Inventory* with the settings of
 `documents/TEST_CASE_STUDY.md`: `training_movements.csv` for movements,
 `training_meteo.csv` for meteorology, `training_ads_b_data.csv` as ADS-B
 table, grid 100 x 100 x 20 cells of 250 x 250 x 50 m. Save as
 `training_out_REBUILT.alaqs` next to the original so the original is
 preserved. (Headless equivalent:
 `QT_QPA_PLATFORM=offscreen python3.12 tools/test_fixtures/rebuild_training_example_inventory.py --out training_out_REBUILT.alaqs`.)
4. Open-ALAQS Toolbar → *Calculate Emissions* on `training_out_REBUILT.alaqs`.
 Method: **bymode** (default). NOx ambient correction: **off** (default).
5. Export emissions to CSV via *Save to CSV*.

### Outputs to send

- `training_out_REBUILT.alaqs` (the regenerated inventory) - or the md5 if
 the file is too large.
- The exported per-movement CSV.
- The Open-ALAQS log lines from the *Calculate Emissions* run.

### What the reviewer does

- Compare the plugin results on `training_out_REBUILT.alaqs` with those on
 `example/training/training_out.alaqs` (the canonical inventory): they must
 be bit-identical per movement. The files themselves are not md5-identical
 (a rebuild differs in bytes), so do not md5-compare them.
- For each movement (13 total), read the plugin CSV and read
 `training_validation_reference.xlsx`. Diff per pollutant.
- Report per-movement deltas with three thresholds:
 - `|Δ/ref| ≤ 1e-6` → PASS (bit-identical at float64 precision)
 - `|Δ/ref| ≤ 1e-4` → PASS-WITH-DRIFT (acceptable; flag for investigation)
 - `|Δ/ref| > 1e-4` → FAIL (investigate root cause)
- Surface any non-PASS rows in a table, propose root-cause hypotheses
 (EF table change, profile table change, ambient-correction toggle,
 meteo expansion).

---

## V2 - Standalone vs CAEP14 reference

**Goal**: confirm the standalone reproduces V1's plugin output bit-identically
(matching method, matching ambient settings).

### Inputs

The four pinned plugin per-movement CSVs shipped at:

```
openalaqs_standalone/validation/data/plugin_output/training_movements_bymode.csv
openalaqs_standalone/validation/data/plugin_output/training_movements_bymode_nox_corr.csv
openalaqs_standalone/validation/data/plugin_output/training_movements_bffm2_anchor.csv
openalaqs_standalone/validation/data/plugin_output/training_movements_bffm2_traj.csv
```

These are pinned plugin outputs used as the bit-identity target for the
standalone. They were generated from the 15-movement training_v3.alaqs
fixture (13 fixed-wing + 2 helicopter). Each contains only
`source_type = "Movement"` rows — aircraft trajectory contributions
only, with the plugin's separate gate / APU / engine-start source
types excluded.

The matching standalone fixture is:

```
openalaqs_standalone/validation/data/training_v3.alaqs
```

### Apples-to-apples comparison: `--aircraft-only`

The standalone CLI's default per-movement CSV writes `total_em_kg`,
which folds gate (GSE+GPU), APU, and engine-start emissions into each
movement total. The pinned plugin CSVs contain only the aircraft
trajectory contribution. A direct CSV diff is therefore not
apples-to-apples and will appear to fail on any movement with a
non-zero APU or start contribution.

Pass `--aircraft-only` to the `aircraft` subcommand. With that flag
set, the standalone subtracts `gate_em_kg + apu_em_kg + start_em_kg`
from `total_em_kg` per movement before writing the CSV, producing a
value directly comparable to the plugin's Movement-source rows.

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
and the NOx-corrected run off the pinned files (largest per-movement NOx
delta 8 % with the NOx correction, 22 % `bffm2_anchor`, 34 % `bffm2_traj`;
bymode without correction and the helicopters are unaffected).

Expected per-movement aircraft-only totals (sum across 15 movements
in training_v3.alaqs: 13 fixed-wing + 2 helicopter, kg):

| Method                              | NOx    | CO     | HC    |
| ----------------------------------- | -----: | -----: | ----: |
| bymode                              | 29.197 | 21.812 | 1.456 |
| bymode + `--apply-nox-corrections`  | 27.963 | 21.812 | 1.456 |
| bffm2_anchor                        | 27.745 | 21.532 | 1.468 |
| bffm2_traj                          | 15.274 | 22.488 | 1.469 |

(Measured with the standalone of this version, default meteo and
`--aircraft-only`, on `training_v3.alaqs`; equal to the sums of the pinned
plugin CSVs. Any drift here for the shipped standalone indicates a
regression. For a NEW build of the standalone, drift is expected and is
the V2 result.)

If you are running the 13-movement example inventory
`example/training/training_out.alaqs` (no helicopters) as a smoke test,
the totals must match `USAGE.md` § "Quick smoke test" (31.804 / 30.661 /
30.024 / 17.419 kg NOx for the four methods, with or without
`--aircraft-only`).

### Outputs to send

- The four `v2_*.csv` files produced by the standalone (with
  `--aircraft-only`).
- The standalone version string (top of
  `openalaqs_standalone/__init__.py`, or git commit / archive md5).

### What the reviewer does

- For each `v2_*.csv`, per-row diff against the matching pinned file at
  `openalaqs_standalone/validation/data/plugin_output/training_movements_*.csv`.
  Tolerance bands per V1. Expected: PASS at 1e-6 everywhere except
  `bffm2_traj` movement 11 (CUSTOM, PHBBA), PASS-WITH-DRIFT at 8e-5 on
  every pollutant.
- Cross-method sanity (no aircraft should produce zero CO, CO2, HC, NOx or
  PM10; SOx is 0 for every movement of this fixture, plugin and reference
  alike; all 15 movements should appear in each output).
- Compare the aggregate NOx totals against the expected table above.

---

## V3 - Plugin vs Campaign study (real-airport scale)

**Goal**: confirm the plugin produces stable per-movement outputs on the
multi-runway, multi-hundred-movement campaign study the user
maintains. Bit-identity is NOT expected against any reference; what is
expected is bit-identity against the prior validated build.

### Inputs

- `<campaign_study>.alaqs` - the user's local file, with multi-runway
 layout, hundreds to thousands of movements, real meteo, real receptors.
- The previous validated build's per-movement CSV (call it `prior_v3.csv`).
- The same user's QGIS project and any per-study tweaks
 (e.g. `tow_ratio` overrides in `user_aircraft_movements`).

### Procedure (QGIS)

1. Open QGIS 3.40 with the **new** plugin installed.
2. Project → Open → `<campaign_study>.alaqs`.
3. Open-ALAQS Toolbar → *Calculate Emissions*. Run for the inventory year
 declared in `user_study_setup`. Method as previously validated
 (typically `bymode`).
4. Save to CSV.

### Outputs to send

- The per-movement CSV from the new build (call it `new_v3.csv`).
- The corresponding `prior_v3.csv` (user already has this).
- The `metadata.txt` version line for the new build.
- Movement count, total NOx (kg), total CO (kg), total HC (kg) for both
 runs - useful sanity check before per-movement comparison.

### What the reviewer does

- Row-align `new_v3.csv` and `prior_v3.csv` by movement oid + direction.
- Per-movement absolute and relative deltas per pollutant.
- Summary table: count of rows in each tolerance band (1e-6 / 1e-4 / >1e-4).
- If failures exist, group by `aircraft_icao`, `engine_name`,
 `profile_id`, and `runway` to find the dominant pattern.
- Likely-cause hypotheses, drawing on knowledge of which files changed
 between the prior and new builds.

---

## V4 - Standalone vs Campaign study

**Goal**: confirm the standalone produces the same per-movement results as
the plugin (V3) on the campaign study, with the standalone bit-identical
to its own prior-build output for the same input.

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
 --processes 8

# full austal pipeline (six folders including aircraft cell sources)
python -m openalaqs_standalone austal \
 <campaign_study>.alaqs \
 --year <year_from_user_study_setup> \
 --include-aircraft --aircraft-method bymode \
 --processes 8 \
 --out ./v4_austal/
```

### Outputs to send

- `v4_aircraft.csv` - per-movement totals.
- `v4_austal/emissions_folder/emissions.parquet` - hourly per-source rates.
- `v4_austal/config_folder/config.json` - write settings, grid, time window.
- `v4_austal/sources_folder/sources.parquet` - source geometry + metadata.
- Standalone version, CLI invocation, walltime, peak memory if known.

### What the reviewer does

- Compare `v4_aircraft.csv` against V3's plugin CSV per-movement (per V5
 below).
- Cross-check `emissions.parquet` aggregates by source-type
 (aircraft / stationary / road / parking / point / area / gate) against
 per-type totals from V3's plugin run when reported.
- Verify `config.json` has the expected keys
 (`apply_nox_corrections`, `grid.utm_epsg`, `grid.nx`/`ny`,
 `start_dt`/`end_dt`, `selected_pollutants`).

---

## V5 - Plugin vs. Standalone bit-identity on the same study

**Goal**: every per-movement row in the plugin's CSV matches the
standalone's `aircraft` CSV to within float64 noise, on the same study
(both CAEP14 and the campaign).

### Inputs

- For CAEP14: the V1 plugin CSV and a standalone run on the same inventory
 (`aircraft training_out_REBUILT.alaqs --aircraft-only`), or the pinned
 plugin CSVs and the V2 outputs on `training_v3.alaqs`.
- For campaign: V3 plugin CSV + V4 standalone `aircraft` CSV.

### What the reviewer does

- Build the row-aligned diff table keyed by `(oid, departure_arrival)`.
- Tolerance bands: 1e-6 / 1e-4 / >1e-4 relative per pollutant.
- For CAEP14: expect 100 % PASS at 1e-6, except `bffm2_traj` movement 11
 (CUSTOM): PASS-WITH-DRIFT, 4.4e-5 on the example and 8e-5 on
 `training_v3.alaqs`. Any other row outside is a regression.
- For campaign: report the band distribution. Investigate any 1e-4-band
 rows that did not exist in the prior build's V5 result.

---

## Comparison methodology (what the reviewer does internally)

### Bit-identity definition

A floating-point value `a` is bit-identical to `b` when both have the same
sign, exponent, and mantissa under IEEE 754 binary64. For CSV-mediated
comparisons this collapses to **agreement to all significant digits the CSV
preserves** - typically 15-17 decimal digits if the writer used `repr` or
`%.17g`. Any difference at this level is a calculation drift, not a
formatting drift.

### Relative tolerance

`|Δ / max(|ref|, ε)|` with `ε = 1e-30` (so zero-reference values don't
explode). Compute per (movement, pollutant) cell, not aggregated.

### Tolerance bands

- **PASS** (`≤ 1e-6`): bit-identical at float64 precision after round-trip
 through CSV. Two implementations are computing the same thing.
- **PASS-WITH-DRIFT** (`≤ 1e-4`): subtle drift, likely from one of:
 reordered summation, slightly different interpolation order, or
 reference-data refresh. Investigate; usually safe.
- **FAIL** (`> 1e-4`): a real difference. Pollutant or movement is
 responding to a different code path.

### Per-pollutant aggregate sanity check

For each pollutant, sum across all movements in both files; compute the
ratio of totals. If the per-row diff is dominated by a small number of
movements (e.g. 5 of 1561), the aggregate ratio will be close to 1.0
while the per-row max-delta will be large. Both are useful diagnostics
and the reviewer should report both.

### Failure triage rules

1. **One pollutant, all movements affected** → likely an EF table
 refresh (default_aircraft_engine_ei, default_stationary_ef).
2. **All pollutants, one engine family** → engine row replaced or its
 EI numbers updated.
3. **All pollutants, one profile** → default_aircraft_profiles row
 updated.
4. **All pollutants, BFFM2 only** → BFFM2 fuel-flow code path
 regression (`twin_quadratic_fit_method.py`, `bffm2.py`).
5. **NOx only, takeoff/climb-out segments only** →
 `--apply-nox-corrections` flag flipped between runs, or
 `nox_correction_ambient.py` changed.
6. **One aircraft type, all movements** → `default_aircraft.csv` row
 for that ICAO changed (different engine_name or profile_id).

---

## Data shipped with this package

| Path | Purpose |
| --------------------------------------------------------------------- | ---------------------------------------- |
| `example/training/training.alaqs` | CAEP14 study project file |
| `example/training/training_out.alaqs` | CAEP14 canonical inventory |
| `example/training/training_movements.csv` | 13-movement CAEP14 set |
| `example/training/training_meteo.csv` | 75 hourly meteo rows |
| `example/training/training_ads_b_data.csv` | ADS-B tracks imported into the inventory; movement 11 flies `1764584438_PHBBA` (all methods) |
| `example/training/training_validation_reference.xlsx` | Per-movement reference totals (plugin beside the CAEP14 reference) |
| `openalaqs_standalone/validation/data/training_v3*.alaqs` | Derived multi-source CAEP14 variants |
| `openalaqs_standalone/validation/data/plugin_output/training_movements_bymode.csv` | Pinned plugin output, `bymode` |
| `openalaqs_standalone/validation/data/plugin_output/training_movements_bymode_nox_corr.csv` | Pinned plugin output, `bymode`+corr |
| `openalaqs_standalone/validation/data/plugin_output/training_movements_bffm2_anchor.csv` | Pinned plugin output, `bffm2_anchor` |
| `openalaqs_standalone/validation/data/plugin_output/training_movements_bffm2_traj.csv` | Pinned plugin output, `bffm2_traj` |
| `openalaqs_standalone/validation/data/plugin_output/training_sources_bymode.csv` | Pinned plugin output, stationary sources, `bymode` |
| `openalaqs_standalone/validation/data/training_validation_reference.xlsx` | Plugin beside the CAEP14 reference on `training_v3.alaqs` (15 movements, helicopters included) |

The pinned plugin outputs are made by the plugin of this version, run
headlessly (`regenerate_plugin_csvs.py`), with the study meteo.

The campaign study is the user's local artifact and is not shipped.

---

## Companion code references

| Code path | Use |
| ---------------------------------------------------------------------------------- | -------------------------------------------- |
| `openalaqs_standalone/validation/tools/compute_caep14_reference.py` | Compute the CAEP14 reference from scratch |
| `openalaqs_standalone/validation/tools/compare_inventory_to_reference.py` | Per-movement diff of a plugin CSV against the workbook reference column (0.5 % threshold, exit 0 when all pass) |
| `openalaqs_standalone/validation/tools/regenerate_plugin_csvs.py` | Re-export the pinned plugin CSVs headlessly (QGIS bindings, no GUI) |
| `openalaqs_standalone/validation/tools/regenerate_training_validation_xlsx.py` | Rebuild the validation workbooks |
| `tools/test_fixtures/rebuild_training_example_inventory.py` | Rebuild `example/training/training_out.alaqs` from the example inputs |
| `openalaqs_standalone/validation/tests/test_plugin_csv_vs_reference.py` | Plugin = reference = standalone, 15 movements, 2e-4 |
| `openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md` | Methodology + earlier validation history |
| `openalaqs_standalone/validation/tests/test_bffm2_ambient_propagation_regression.py` | BFFM2 EI regression pytest |
| `scripts/migrate_alaqs.py` | Upgrade a legacy `.alaqs` to current schema |
| `scripts/migrate_alaqs_gui.py` | Qt5 GUI wrapper around the migration tool |

---


---

## Known regression patterns (what to look for first)

The following issues have surfaced before in this codebase. If a validation
fails, check these first; they cover most observed failure modes.

### 1. AUSTAL writer aborts mid-run with "Grid source NN not available"

**Symptom**: `austal.exe` aborts with
```
*** Grid source "02" not available! (TalSrc.SrcCrtPtl.14)
```
typically at the second hour of the run.

**Root cause**: per-source rate transitions to exactly `0.000e+00` mid-run.
AUSTAL refuses to instantiate the next-hour grid source for that slot.

**Fix in `core/modules/AUSTALOutputModule.py`**:
- Floor every per-source rate at `1.0e-30` instead of `0.0` in the
 `series.dmna` writer.
- Back-fill zero-mass hours with phantom single-cell Eq weight = 1.0 and
 reset `self._start_time` / `self._end_time` from `_first_start_time +
 timedelta(hours=time_id ± 1)` per back-filled e-file (otherwise AUSTAL
 rejects `*** File "...e0001.dmna" [...] not valid at 00:00:00!`).
- Re-encode `WindDirection == 0` with `WindSpeed > 0` to the AUSTAL
 "missing" sentinel `999` to suppress the "Datenzeilen mit Windrichtung
 gleich 0 und Windgeschwindigkeit groesser 0" warning.

All three live in the patched plugin. If a new build of the plugin
reintroduces the abort, check that these three patches are still present
in `AUSTALOutputModule.py`.

### 2. `Aircraft has no attribute 'getStartEmissions'` AttributeError

**Symptom**: plugin emission calculation crashes with
```
AttributeError: 'Aircraft' object has no attribute 'getStartEmissions'.
Did you mean: 'getApuEmissions'?
```
at `MovementEmissionCalculator.__init__` line ~237.

**Root cause**: `MovementEmissionCalculator.py` calls
`self._aircraft.getStartEmissions()` (aircraft-keyed start emissions,
correct), but the `Aircraft` interface class is missing the
`getStartEmissions()` method. The method was moved from `Engine` to
`Aircraft` in the validated tree (because the Engine instance can be
shared across aircraft in different groups, so the per-aircraft value
belongs on `Aircraft`).

**Fix**: ensure `core/interfaces/Aircraft.py` exposes
`def getStartEmissions(self)` (it does in the validated tree). Do NOT
revert `MovementEmissionCalculator.py` to `self._engine.getStartEmissions()`
without also reverting the Aircraft.py change - they are paired.

**Lesson**: when porting fixes from one tree to another, the
`MovementEmissionCalculator.py` aircraft-keyed call has a dependency on
the matching `Aircraft.getStartEmissions()` method addition. Porting one
without the other breaks the plugin.

### 3. `default_aircraft.csv` containing duplicate helicopter rows

**Symptom**: the plugin's helicopter feature emits zero (or duplicate)
emissions; `default_aircraft.csv` has more rows than the expected 1919
(post-refactor count: the 60 helicopters were extracted to their own
table).

**Root cause**: 60 helicopter rows were moved out of
`default_aircraft.csv` and into `default_helicopter.csv` as part of
the FOCA 2015 helicopter dispatch refactor introduced in the 5.2.0
release. A rebuild that uses an upstream `default_aircraft.csv` from
before that refactor (instead of the current canonical version)
reintroduces the helicopter rows, leaving duplicates across the two
tables.

**Fix**: ship `default_aircraft.csv` from the canonical tree verbatim.
The 5.2.0 release applied Tier 1 (per-ac_group rule) and Tier 2
(per-ICAO research) APU backfills — see the `[5.2.0]` section of
`CHANGELOG.md` for the list of ICAOs whose `apu_id` was populated.
Don't overlay an upstream version that pre-dates the backfill.

**Lesson**: overlays must take their baseline from the tree they are
overlaid on top of, not from a different tree.

### 4. APU silent-zero emissions

**Symptom**: aircraft of certain ICAO types produce zero APU emissions
even when `apu_code = 1` (APU active) in the movement record.

**Root cause**: `default_aircraft.apu_id IS NULL` for that ICAO. The
APU-emission lookup `JOIN default_aircraft_apu_ef ON apu_id` returns zero
rows; no error is raised; emissions silently drop to zero.

**Important**: NULL `apu_id` has two meanings:
 (a) "the aircraft has no APU at all" - correct as zero (most Cessna
 Citation light jets, most King Air turboprops, PC-24, ATR family).
 (b) "we don't know the APU model" - INCORRECT as zero.

The fix is per-ICAO research, applied to `default_aircraft.csv` in
the 5.2.0 release. See `CHANGELOG.md` [5.2.0] for the list of ICAOs
that received populated `apu_id` values. A group-default backfill
(assigning a "most-common APU per `ac_group`") is WITHDRAWN as it
conflates the two meanings.

**Status in this release**:
- Tier 1 (bulk per-ac_group rule): 6 ICAOs correctly NULL; 2 (CRJ9,
 LJ45) have a standard APU but the model is missing from
 `default_aircraft_apu_ef`. Both stay NULL pending an EF table
 extension.
- Tier 2 (91 ICAOs reviewed): 7 backfilled in this release (H25B,
 H25C, HA4T, BCS1, BCS3, B731, B74D). 23 future-EF (have APU, model
 not in EF table). 61 correctly NULL.

The shipped `default_aircraft.csv` has 162 of 1919 rows (8.4%) with
populated `apu_id` and 1757 (91.6%) NULL. The NULL count should reduce
further as the future-EF list is closed out.

### 5. Standalone fails on the official training fixture

**Symptom**: `python -m openalaqs_standalone aircraft training_out.alaqs`
fails with
```
OperationalError: no such table: default_helicopter
```

**Root cause**: `openalaqs_standalone/movements.py` queries
`default_helicopter` unconditionally to decide whether each movement is
fixed-wing or helicopter. Inventories made by plugin versions before the
FOCA 2015 helicopter implementation (such as the
`example/training/training_out.alaqs` shipped before 5.3.x) have no
`default_helicopter` table.

**Fix**: `movements.get_helicopter()` and `movements.get_helicopter_engine_type()`
now check `_table_exists(conn, ...)` first and return `None` when the
helicopter tables are absent - that is, every aircraft in those studies
is treated as fixed-wing (which is correct).

**Lesson**: studies created by older plugin versions have a different
schema. The standalone must gracefully degrade when tables added by
newer plugin versions are absent.

### 6. Other validated-but-easy-to-regress fixes

The following are battle-tested in the validated plugin tree. If a new
build doesn't include them, sub-class symptoms will show up:

| Fix | File | Symptom if reverted |
| -------------------------------------------- | --------------------------------------------- | ---------------------------------------------------------- |
| COPERT 5 parking distance `m → km` | `core/tools/copert5.py` | All parking COPERT 5 emissions ~1000x too high |
| ADS-B `z_m <= 0` for mode classification | `core/tools/ads_b.py` | Sub-MSL airports (e.g. EHRD at -15 ft, -5 m) misclassify TO as CL (ground points are snapped to height 0 by `_snap_ground_heights` before the `z_m <= 0` test) |
| BFFM2 1.05 power-setting tolerance clamp | `core/tools/twin_quadratic_fit_method.py` | Small floating-point overshoots abort the whole movement |
| BFFM2 `ValueError` fallback to mode-anchor EI| `core/MovementEmissionCalculator.py` | BFFM2 failures abort the study instead of degrading |
| Geodetic length for `MultiLineString` | `core/tools/spatial.py` | Mass silently dropped for clipped polylines re-entering the same cell |
| Empty `tbl_InvMeteo` warning | `core/EmissionCalculation.py` | BFFM2 silently uses ISA when meteo table is empty |

### 7. recipe_config.json parameter coverage

The Dataiku recipe parses `recipe_config.json` via `_resolve_config(...)`.
A parameter that exists in the CLI but is not in `_resolve_config` will be
silently ignored when set via the JSON. This happened with
`apply_nox_corrections` (CLI accepted it, JSON did not). The current
recipe handles all 22 keys documented in
`example/training/recipe_config.example.json`; adding a new CLI flag in
the future requires a matching entry in `_resolve_config`'s return dict
and a matching kwarg in the `orchestrate()` call site.

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
[ ] V1 Plugin vs CAEP14 reference
[ ] V2 Standalone vs CAEP14 reference (all 4 method variants)
[ ] V3 Plugin vs Campaign study (new build vs prior build)
[ ] V4 Standalone vs Campaign study
[ ] V5 Plugin vs. Standalone bit-identity (CAEP14 + campaign)

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
 aircraft: ____ kg NOx
 stationary: ____ kg NOx
 road: ____ kg NOx
 parking: ____ kg NOx
 point: ____ kg NOx
 area: ____ kg NOx
 gate: ____ kg NOx

=== Request to the reviewer ===
Please:
 1. Check per-movement results on the rebuilt vs the shipped inventory (V1).
 2. Per-movement diff with 1e-6 / 1e-4 tolerance bands for V1, V2, V3, V4.
 3. V5 cross-check (plugin vs. standalone bit-identity).
 4. Failure triage on any FAIL rows using the rules in
 VALIDATION_GUIDE.md "Failure triage rules".
 5. Sign-off statement: PASS / PASS-WITH-DRIFT / FAIL per validation.
```
