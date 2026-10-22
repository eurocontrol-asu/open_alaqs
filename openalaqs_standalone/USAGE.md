# openalaqs_standalone — terminal usage guide

A walk-through of the standalone, from a fresh checkout to a working AUSTAL
input set. Companion to the package [README](README.md), which covers the
internal architecture; this file is task-oriented.

## Contents

- [Install](#install)
- [Where the official test fixture lives](#where-the-official-test-fixture-lives)
- [The two subcommands at a glance](#the-two-subcommands-at-a-glance)
- [Recipe 1 — `aircraft`: per-movement emissions](#recipe-1--aircraft-per-movement-emissions)
- [Recipe 2 — `austal`: AUSTAL-ready folders](#recipe-2--austal-austal-ready-folders)
- [Selecting the emission method](#selecting-the-emission-method)
- [The NOx ambient correction](#the-nox-ambient-correction)
- [Reading `config.json`](#reading-configjson)
- [Validation harness (`validation/`)](#validation-harness-validation)
- [Parallel runs](#parallel-runs)
- [Restricting the time window](#restricting-the-time-window)
- [Troubleshooting](#troubleshooting)

## Install

The package is shipped as a top-level directory in the Open-ALAQS repository
and imports BFFM2, FOCA and runway-placement code from the plugin tree
(`open_alaqs/core/tools/`), so run it from the repository root with the root
on `PYTHONPATH`:

```bash
cd /path/to/openalaqs/
PYTHONPATH=. python -m openalaqs_standalone --help
```

Runtime dependencies are `numpy`, `pandas`, `pyarrow` (parquet), `shapely`,
and `pyproj`. The package never imports QGIS, PyQt, or `mod_spatialite`.

### Quick smoke test

From the repository root, the official training fixture should run end-to-end in
under a minute. Expected aircraft NOx total (13 movements, year 2025):

| `--method` value                | NOx (kg) |
| ------------------------------- | -------- |
| `bymode`                        |   31.841 |
| `bymode` + `--apply-nox-corrections` |   30.698 |
| `bffm2_anchor`                  |   30.056 |
| `bffm2_traj`                    |   18.721 |

(CO 22.414 / 22.414 / 21.949 / 23.338 kg; the same with `--aircraft-only`,
since the example has no gate, APU or start emissions.)

```bash
python -m openalaqs_standalone aircraft \
    example/training/training_out.alaqs \
    --out totals.csv --method bymode
```

If your numbers differ by more than rounding, something is wrong with
the install (most often a stale `.alaqs` schema that has not been
migrated; run `python scripts/migrate_alaqs.py example/training/training_out.alaqs`
first).

## Where the official test fixture lives

The canonical training study used by the User Guide and the validation
harness ships at the repository root under `example/training/`:

```
example/training/
├── training.alaqs                          project file (geometry, sources,
│                                           study setup)
├── training_out.alaqs                      inventory output (produced by
│                                           Generate Emission Inventory
│                                           in the QGIS plugin)
├── training_movements.csv                  aircraft movements
├── training_meteo.csv                      hourly meteorology
├── training_ads_b_data.csv                 ADS-B tracks, imported into
│                                           the inventory (movement 11
│                                           flies 1764584438_PHBBA)
└── training_validation_reference.xlsx      reference values for a
                                            self-check after running
```

Every example in this guide uses `example/training/training_out.alaqs` as
its input. From the repository root:

```bash
ALAQS=example/training/training_out.alaqs
```

## The two subcommands at a glance

```bash
python -m openalaqs_standalone <command> <study.alaqs> [options]
```

| Command   | Output                                                      | Use when                                                                |
| --------- | ----------------------------------------------------------- | ----------------------------------------------------------------------- |
| `aircraft`| one CSV of per-movement totals                              | you want a movement-by-movement emission table for analysis             |
| `austal`  | a six-folder structure ready for an external AUSTAL pipeline| you want AUSTAL-ready inputs (sources + emissions + meteo + receptors + config) |

The `austal` command can also fold the `aircraft` compute into the same
output structure with `--include-aircraft`, giving you one run that covers
both the stationary and the movement halves of the study.

## Recipe 1 — `aircraft`: per-movement emissions

Smallest possible call:

```bash
python -m openalaqs_standalone aircraft example/training/training_out.alaqs \
    --out movement_totals.csv
```

This writes `movement_totals.csv` with one row per movement, seven pollutant
columns (`co_kg`, `co2_kg`, `hc_kg`, `nox_kg`, `sox_kg`, `pm10_kg`,
`pm25_kg`), plus metadata (`oid`, `aircraft`, `departure_arrival`,
`profile_id`, `method`).

Add `--method` to pick the emission method (next section), `--processes N`
to parallelise (later section), or `--oids 4,12,73` to compute only a
subset of movements.

## Recipe 2 — `austal`: AUSTAL-ready folders

Stationary half only:

```bash
python -m openalaqs_standalone austal example/training/training_out.alaqs \
    --year 2025 \
    --out ./inputs/
```

Stationary + aircraft halves in one run:

```bash
python -m openalaqs_standalone austal example/training/training_out.alaqs \
    --year 2025 \
    --include-aircraft --aircraft-method bymode \
    --out ./inputs/
```

This produces:

```
inputs/
├── sources_folder/
│   └── sources.parquet            one row per source (id, type, geometry,
│                                  height, in_study, ...)
├── emissions_folder/
│   ├── emissions.parquet          one row per (source, pollutant, hour)
│   │                              carrying kg/hour
│   ├── co_emissions.gpkg, ...     one gpkg per pollutant, polygon features
│   │                              per inventory grid cell
│   └── runway_checks.csv          route and profile checks (with
│                                  --include-aircraft); never blocks the run
├── receptors_folder/
│   └── receptors.csv              receptors in target UTM
├── meteo_folder/
│   └── meteo.csv                  hourly meteorology
├── config_folder/
│   └── config.json                AUSTAL writer settings + grid + flags
└── austal_folder/                 (empty; filled by austal_prep)
```

The pair `sources.parquet` + `emissions.parquet` is the input contract that
the sibling `austal_prep` package consumes to produce
`austal.txt` + `series.dmna` + per-source grid files for an actual AUSTAL run.
That step is `python -m austal_prep` (see `python -m austal_prep --help` and the docstring of `austal_prep/__init__.py`).

## Selecting the emission method

Three methods are supported, all from the same trajectory and EI database:

| `--method` value | Fuel flow source                                                 | Ambient correction                              |
| ----------------- | ---------------------------------------------------------------- | ----------------------------------------------- |
| `bymode`          | EEDB mode-anchor fuel flow at the segment's mode                 | None by default; opt in with `--apply-nox-corrections` |
| `bffm2_anchor`    | EEDB mode-anchor fuel flow, BFFM2 EI on the log-log curve        | BFFM2 SAE AIR-5715 (built-in)                   |
| `bffm2_traj`      | Per-segment trajectory fuel flow via twin-quadratic fit          | BFFM2 SAE AIR-5715 (built-in)                   |

The BFFM2 ambient correction uses the study meteo in `tbl_InvMeteo` by
default (`--use-meteo`), as the plugin does; `--isa-meteo` (`austal`:
`--use-isa-meteo`) forces ISA and only reproduces older runs.

Set the method on the `aircraft` subcommand:

```bash
python -m openalaqs_standalone aircraft $ALAQS --out totals.csv \
    --method bffm2_traj
```

Set it on the `austal` subcommand (only takes effect with `--include-aircraft`):

```bash
python -m openalaqs_standalone austal $ALAQS --year 2025 --out ./inputs/ \
    --include-aircraft \
    --aircraft-method bffm2_traj
```

`bymode` is the default and matches the QGIS plugin's bymode path to
floating-point noise (3.9e-11 relative on `training_v3.alaqs`).

## The NOx ambient correction

The ICCAIA / CAEP14 v14 NOx ambient correction at takeoff (TO) and climb-out
(CL) segments. It reads ambient temperature, pressure and humidity from
`tbl_InvMeteo` per inventory period, plus airport elevation from
`user_study_setup`. The `tow_ratio` column from `user_aircraft_movements`
is used as a weight when set (defaults to 1.0).

**Default: off.** This preserves bit-identity with the plugin's default
bymode output. Opt in with `--apply-nox-corrections`:

```bash
python -m openalaqs_standalone aircraft $ALAQS --out totals.csv \
    --method bymode \
    --apply-nox-corrections
```

```bash
python -m openalaqs_standalone austal $ALAQS --year 2025 --out ./inputs/ \
    --include-aircraft --aircraft-method bymode \
    --apply-nox-corrections
```

The flag is **only effective with `--method bymode`** (or
`--aircraft-method bymode`). BFFM2 methods always include their own ambient
correction; the flag is ignored for them and for helicopter movements.

When you pass `--apply-nox-corrections` to the `austal` subcommand, the
value is recorded in `config.json` under the key `apply_nox_corrections`
(boolean) so downstream consumers can replicate the choice.

## Aircraft-only CSV output (`--aircraft-only`)

By default, the `aircraft` subcommand's per-movement CSV writes
`total_em_kg`, which is the trajectory plus gate (GSE + GPU) plus APU
plus engine-start contributions per movement (the "what flew this
hour, including everything that came with it" total). This is the
right quantity for inventory totals and for studies where the
trajectory + ground services are reported together.

For plugin-comparability (e.g. `VALIDATION_GUIDE.md` § V2 / V5),
add `--aircraft-only` to the `aircraft` subcommand:

```bash
python -m openalaqs_standalone aircraft $ALAQS --out totals.csv \
    --method bymode --aircraft-only
```

With the flag set, the standalone subtracts
`gate_em_kg + apu_em_kg + start_em_kg` from `total_em_kg` per movement
before writing the CSV. The resulting value per pollutant is directly
comparable to the plugin's `source_type = "Movement"` rows in its
per-source emissions CSV (which contain trajectory contributions only;
gate / APU / start emissions are emitted as separate source types on
the plugin side).

The flag affects only the per-movement CSV writer and the on-screen
study-totals summary (labeled `(kg, aircraft-only)` when the flag is
set, otherwise `(kg, total)`). It has no effect on the `austal`
subcommand's emissions.parquet output, which always uses the full
`total_em_kg`.

## Reading `config.json`

`config.json`, written into `config_folder/`, is the metadata file that any
downstream AUSTAL pipeline reads. The keys that affect computation:

```json
{
  "title": "Rotterdam",
  "qs": 3,
  "z0": 0.3,
  "d0": 1.2,
  "ha": 11.2,
  "os_options": "NOSTANDARD;NOTALUFT;SCINOTAT;Kmax=1",
  "mixing_height_included": true,
  "grid_writer_mode": "hybrid",
  "source_offset_cells": 2,
  "max_receptors": 20,
  "source_aggregation": "by_type_per_pollutant",
  "apply_nox_corrections": false,
  "grid": {
    "dd": 250.0,
    "nx": 104,
    "ny": 104,
    "x0": -13000.0,
    "y0": -13000.0,
    "sk": [0, 3, 6, 10, 16, 25, 40, 65, 100, 150, 200, 300, 400, 500,
           600, 700, 800, 1000, 1200, 1500],
    "reference_x": 599065.0372562435,
    "reference_y": 5757284.894734611,
    "utm_epsg": 32631
  },
  "selected_pollutants": ["co", "hc", "nox", "sox", "pm10", "pm25"],
  "start_dt": "2025-01-01T00:00:00",
  "end_dt": "2025-12-31T23:00:00"
}
```

| Key                    | Effect                                                              |
| ---------------------- | ------------------------------------------------------------------- |
| `qs`                   | AUSTAL quality level                                                |
| `z0`                   | roughness length (m)                                                |
| `d0`                   | displacement height (m); defaults to 4·z0                           |
| `ha`                   | anemometer reference height (m)                                     |
| `os_options`           | AUSTAL `os` line                                                    |
| `mixing_height_included`| feed mixing-height column to AUSTAL meteo                          |
| `grid_writer_mode`     | `hybrid` (default: one e-file per hour for aircraft sub-sources, one time-invariant e-file for stationary sources), `time_indexed` (one time-invariant e-file for all) or `legacy` (per-hour files for all) |
| `source_aggregation`   | `by_type_per_pollutant` (recommended) or `by_type` (legacy)          |
| `apply_nox_corrections`| record of the `--apply-nox-corrections` choice                      |
| `selected_pollutants`  | pollutants written                                                  |
| `grid.*`               | AUSTAL calc grid: cell size, count, origin, vertical layers, ref pt |
| `start_dt` / `end_dt`  | run window (from `--year` or `--start`/`--end`)                     |

The emission **method** (`bymode`, `bffm2_anchor`, `bffm2_traj`) is **not**
stored in `config.json`; it is a runtime CLI flag only. Pick it via
`--aircraft-method` each time you run.

Override defaults at the command line; `make_config.py` is also callable as
a Python function if you want to script the config generation:

```python
from openalaqs_standalone.make_config import make_config
from pathlib import Path

make_config(
    Path("example/training/training_out.alaqs"),
    Path("./inputs/config_folder/config.json"),
    title="EHRD training",
    year=2025,
    apply_nox_corrections=True,
)
```

## Validation harness (`validation/`)

`openalaqs_standalone/validation/` is the developer-facing CAEP14 reference
harness. It is kept up to date with the standalone's calculation paths
and is the canonical test for any change to the emission code. Three
subdirectories:

- `validation/data/` — bundled fixtures. Three derived variants of the
  training study (`training_v3.alaqs`, `training_v3_gatemovements.alaqs`,
  `training_v3_multisource.alaqs`) plus the plugin's own outputs on
  `training_v3.alaqs` for the four bit-identity targets (bymode,
  bymode-with-NOx-correction, bffm2_anchor, bffm2_traj) and the stationary
  sources in `validation/data/plugin_output/` (re-exported headlessly with
  `validation/tools/regenerate_plugin_csvs.py`), and
  `training_validation_reference.xlsx`, plugin beside the CAEP14 reference
  per movement (`validation/tools/regenerate_training_validation_xlsx.py`). The `training_v3*` files
  are evolved versions of `example/training/training.alaqs` carrying
  schema fixes and source variants that exercise the gate / multi-source
  code paths. `validation/data/source_csvs/` holds their text inputs:
  `training_movements.csv` is the movement table of `training_v3.alaqs`
  (and of `training_v3_multisource.alaqs`), 15 movements with the two AS50
  helicopters, in the plugin's import format; `training_v3_gatemovements.alaqs`
  differs from it in the gate and `gate_emissions_code` of movements 1, 2,
  3, 5 and 14. It is not the example's `training_movements.csv` (13
  movements, other runways and gates on some rows). `training_meteo.csv`
  and `training_ads_b_data.csv` are the example's files. No code reads
  this folder.
- `validation/tests/`: pytest modules, among them
  `test_plugin_csv_vs_reference.py` (plugin = reference = standalone on the
  15 movements), `test_bffm2_ambient_propagation_regression.py` (BFFM2 EI
  with pinned ambient inputs), `test_runway_placement.py` and
  `test_segment_mach.py`.
- `validation/tools/`: the CAEP14 reference computation itself
  (`compute_caep14_reference.py`), the headless plugin re-export
  (`regenerate_plugin_csvs.py`), the workbook builder
  (`regenerate_training_validation_xlsx.py`), the diff of a plugin
  per-movement CSV against the workbook's reference column
  (`compare_inventory_to_reference.py`), and the methodology doc
  (`CAEP14_VALIDATION.md`).

Run the validation tests:

```bash
PYTHONPATH=. pytest openalaqs_standalone/validation/tests/ -v
```

Run the CAEP14 reference against the pinned plugin output (add
`--use-meteo` for the BFFM2 methods), and check a plugin CSV against the
workbook:

```bash
PYTHONPATH=. python openalaqs_standalone/validation/tools/compute_caep14_reference.py \
    openalaqs_standalone/validation/data/training_v3.alaqs \
    --method bymode \
    --plugin-csv openalaqs_standalone/validation/data/plugin_output/training_movements_bymode.csv

PYTHONPATH=. python openalaqs_standalone/validation/tools/compare_inventory_to_reference.py \
    openalaqs_standalone/validation/data/plugin_output/training_movements_bymode.csv \
    --method=bymode openalaqs_standalone/validation/data/training_validation_reference.xlsx
```

The harness is the right place to extend whenever you add a new emission
path or a new validation target.

## Parallel runs

The aircraft compute parallelises across a process pool. The stationary
compute is already numpy-vectorised and is not parallelised.

```bash
# 4 worker processes; bit-identical to the serial driver
python -m openalaqs_standalone aircraft $ALAQS --out totals.csv --processes 4

python -m openalaqs_standalone austal $ALAQS --year 2025 --out ./inputs/ \
    --include-aircraft --processes 4
```

Worth it for studies with hundreds or thousands of movements; not worth it
for the training study.

## Restricting the time window

```bash
python -m openalaqs_standalone austal $ALAQS \
    --year 2025 --out ./inputs/ \
    --include-aircraft \
    --start 2025-12-01 --end 2025-12-02
```

The interval is half-open `[start, end)`. Stationary emissions are filtered
to the window per hour; movements are included if their direction-aware
start time (block_time for departures, runway_time for arrivals) is in
the window. Movements that straddle the boundary have their per-segment
emissions clipped. `meteo.csv` and `config.json`'s `start_dt` / `end_dt`
follow the window.

## Troubleshooting

**`ModuleNotFoundError: No module named 'open_alaqs.core.tools.bffm2'`** —
the standalone imports BFFM2 from the QGIS plugin tree. Run from the
repository root with `PYTHONPATH=.`.

**`shapely.errors.GEOSException` on a particular movement** — likely a
self-intersecting taxi route in the source `.alaqs`. Identify the offending
oid via `--oids` bisection; fix the geometry in the plugin or strip the
movement.

**`apply_nox_corrections` had no effect** — check that `--method` (or
`--aircraft-method`) is `bymode`. The flag is silently ignored for BFFM2
methods (which include their own ambient correction) and for helicopter
movements.

**Output `emissions.parquet` is empty**: usually means `instudy` is not `'1'` (for example `'0'`)
on every source, or a time window with no movements. Run with `--year`
only first to confirm the study has emissions, then narrow.
