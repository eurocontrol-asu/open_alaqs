# Known regression patterns

For maintainers: the failure modes seen in earlier builds, with their symptom,
root cause and the code to check. Read this when a validation of
[VALIDATION_GUIDE.md](../validation/VALIDATION_GUIDE.md) fails; these patterns
cover most of the failures observed so far.

Contents:

- [1. AUSTAL writer aborts mid-run with "Grid source NN not available"](#1-austal-writer-aborts-mid-run-with-grid-source-nn-not-available)
- [2. Aircraft has no attribute getStartEmissions](#2-aircraft-has-no-attribute-getstartemissions)
- [3. default_aircraft.csv containing duplicate helicopter rows](#3-default_aircraftcsv-containing-duplicate-helicopter-rows)
- [4. APU silent-zero emissions](#4-apu-silent-zero-emissions)
- [5. Standalone fails on an old inventory](#5-standalone-fails-on-an-old-inventory)
- [6. Other easy-to-regress fixes](#6-other-easy-to-regress-fixes)
- [7. recipe_config.json parameter coverage](#7-recipe_configjson-parameter-coverage)

## 1. AUSTAL writer aborts mid-run with "Grid source NN not available"

**Symptom**: `austal.exe` aborts with
```
*** Grid source "02" not available! (TalSrc.SrcCrtPtl.14)
```
typically at the second hour of the run.

**Root cause**: per-source rate transitions to exactly `0.000e+00` mid-run.
AUSTAL refuses to instantiate the next-hour grid source for that slot.

**Where to look**: `core/modules/AUSTALOutputModule.py`, which must:
- Floor every per-source rate at `1.0e-30` instead of `0.0` in the
 `series.dmna` writer.
- Back-fill zero-mass hours with phantom single-cell Eq weight = 1.0 and
 reset `self._start_time` / `self._end_time` from `_first_start_time +
 timedelta(hours=time_id ± 1)` per back-filled e-file (otherwise AUSTAL
 rejects `*** File "...e0001.dmna" [...] not valid at 00:00:00!`).
- Re-encode `WindDirection == 0` with `WindSpeed > 0` to the AUSTAL
 "missing" sentinel `999` to suppress the "Datenzeilen mit Windrichtung
 gleich 0 und Windgeschwindigkeit groesser 0" warning.

If a build aborts this way, check that all three are present in
`AUSTALOutputModule.py`.

## 2. Aircraft has no attribute getStartEmissions

**Symptom**: plugin emission calculation crashes with
```
AttributeError: 'Aircraft' object has no attribute 'getStartEmissions'.
Did you mean: 'getApuEmissions'?
```
in `TaxiingEmissionCalculator.__init__` (`MovementEmissionCalculator.py`), where it reads `self._aircraft.getStartEmissions()`.

**Root cause**: `MovementEmissionCalculator.py` calls
`self._aircraft.getStartEmissions()` (aircraft-keyed start emissions,
correct), but the `Aircraft` interface class is missing the
`getStartEmissions()` method. Start emissions belong on `Aircraft`, not
`Engine`, because an Engine instance can be shared across aircraft in
different groups.

**Where to look**: `core/interfaces/Aircraft.py` must expose
`def getStartEmissions(self)`. The call in `MovementEmissionCalculator.py`
and the method on `Aircraft` are paired: do not change one without the
other.

## 3. default_aircraft.csv containing duplicate helicopter rows

**Symptom**: the plugin's helicopter feature emits zero (or duplicate)
emissions; `default_aircraft.csv` has more rows than the expected 1919.

**Root cause**: helicopters live in `default_helicopter.csv` (60 rows,
with variants per type), not in `default_aircraft.csv`. A
`default_aircraft.csv` taken from an older source still carries the 61
helicopter rows (1980 rows in all), leaving duplicates across the two
tables; it also lacks the APU backfills (pattern 4).

**Where to look**: the row count and the helicopter types of
`default_aircraft.csv`; ship the file of this repository unchanged.

## 4. APU silent-zero emissions

**Symptom**: aircraft of certain ICAO types produce zero APU emissions
even when `apu_code = 1` (APU active) in the movement record.

**Root cause**: `default_aircraft.apu_id IS NULL` for that ICAO. The
APU-emission lookup `JOIN default_aircraft_apu_ef ON apu_id` returns zero
rows; no error is raised; emissions silently drop to zero.

**Important**: NULL `apu_id` has two meanings:
 (a) "the aircraft has no APU at all" - correct as zero (most Cessna
 Citation light jets, most King Air turboprops, PC-24, ATR family).
 (b) "we don't know the APU model" - INCORRECT as zero.

The `apu_id` values come from per-ICAO research (`CHANGELOG.md` [5.2.0]
lists the ICAOs that received one). Do not backfill a group default
("most-common APU per `ac_group`"): it conflates the two meanings.

**Current state**:
- Tier 1 (bulk per-ac_group rule): 6 ICAOs correctly NULL; 2 (CRJ9,
 LJ45) have a standard APU but the model is missing from
 `default_aircraft_apu_ef`. Both stay NULL pending an EF table
 extension.
- Tier 2 (91 ICAOs reviewed): 7 backfilled (H25B,
 H25C, HA4T, BCS1, BCS3, B731, B74D). 23 future-EF (have APU, model
 not in EF table). 61 correctly NULL.

The shipped `default_aircraft.csv` has 162 of 1919 rows (8.4%) with
populated `apu_id` and 1757 (91.6%) NULL. The NULL count should reduce
further as the future-EF list is closed out.

## 5. Standalone fails on an old inventory

**Symptom**: `python -m openalaqs_standalone aircraft training_out.alaqs`
fails with
```
OperationalError: no such table: default_helicopter
```

**Root cause**: `openalaqs_standalone/movements.py` queries
`default_helicopter` to decide whether each movement is fixed-wing or
helicopter. Inventories made by plugin versions before 5.2.0 (the FOCA 2015
helicopter release) have no `default_helicopter` table.

**Where to look**: `movements.get_helicopter()` and
`movements.get_helicopter_engine_type()` check `_table_exists(conn, ...)`
first and return `None` when the helicopter tables are absent, so every
aircraft of such a study is treated as fixed-wing (which is correct). Any
new query of the standalone on a table added by a later plugin version
needs the same guard.

## 6. Other easy-to-regress fixes

If a build loses one of these, the symptom in the last column shows up:

| Fix | File | Symptom if reverted |
| -------------------------------------------- | --------------------------------------------- | ---------------------------------------------------------- |
| COPERT 5 parking distance `m → km` | `core/tools/copert5.py` | All parking COPERT 5 emissions ~1000x too high |
| ADS-B `z_m <= 0` for mode classification | `core/tools/ads_b.py` | Sub-MSL airports (e.g. EHRD at -15 ft, -5 m) misclassify TO as CL (ground points are snapped to height 0 by `_snap_ground_heights` before the `z_m <= 0` test) |
| BFFM2 1.05 power-setting tolerance clamp | `core/tools/twin_quadratic_fit_method.py` | Small floating-point overshoots abort the whole movement |
| BFFM2 `ValueError` fallback to mode-anchor EI| `core/MovementEmissionCalculator.py` | BFFM2 failures abort the study instead of degrading |
| Geodetic length for `MultiLineString` | `core/tools/spatial.py` | Mass silently dropped for clipped polylines re-entering the same cell |
| Empty `tbl_InvMeteo` warning | `core/EmissionCalculation.py` | BFFM2 silently uses ISA when meteo table is empty |

## 7. recipe_config.json parameter coverage

The Dataiku recipe parses `recipe_config.json` via its `_resolve_config(...)`
(in the recipe file `openalaqs_standalone_recipe.txt` of the Dataiku update
package, not in this repository).
A parameter that exists in the CLI but is not in `_resolve_config` will be
silently ignored when set via the JSON (for example `apply_nox_corrections`
accepted by the CLI but not read from the JSON). The recipe must
handle all 26 keys documented in
`example/training/recipe_config.example.json` (besides the `_`-prefixed
comment entries; the recipe is not in this repository, so this cannot be
checked here); a new CLI flag requires a matching entry in `_resolve_config`'s return dict
and a matching kwarg in the `orchestrate()` call site.

See also:

- [VALIDATION_GUIDE.md](../validation/VALIDATION_GUIDE.md): validations V1 to V5, tolerances and failure triage
- [CAEP14_VALIDATION.md](../../openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md): the CAEP14 reference implementation
- [DEPRECATIONS.md](DEPRECATIONS.md): deprecated data and code paths
