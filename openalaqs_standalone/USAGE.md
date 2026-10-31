# openalaqs_standalone usage

How to run `openalaqs_standalone` from a terminal, from a fresh checkout to a
working AUSTAL input set: install, commands, options, `config.json`, time
window, parallel runs and output folders. It is for users; the architecture,
conventions and limitations are in the package [README](README.md).

Contents:

- [Install](#install)
- [Where the official test fixture lives](#where-the-official-test-fixture-lives)
- [The two subcommands at a glance](#the-two-subcommands-at-a-glance)
- [Per-movement emissions: aircraft](#per-movement-emissions-aircraft)
- [AUSTAL-ready folders: austal](#austal-ready-folders-austal)
- [Selecting the emission method](#selecting-the-emission-method)
- [The NOx ambient correction](#the-nox-ambient-correction)
- [Aircraft-only output](#aircraft-only-output)
- [Reading config.json](#reading-configjson)
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
| `bffm2_anchor`                  |   30.141 |
| `bffm2_traj`                    |   16.615 |

(CO 22.414 / 22.414 / 21.313 / 22.943 kg; the same with `--aircraft-only`,
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
│                                           the inventory (movement 11)
└── training_validation_reference.xlsx      reference values for a
                                            self-check after running
```

Movement 11 flies one of the ADS-B tracks
([details](validation/tools/CAEP14_VALIDATION.md#movement-11-phbba-custom-track)).

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

## Per-movement emissions: aircraft

Smallest possible call:

```bash
python -m openalaqs_standalone aircraft example/training/training_out.alaqs \
    --out movement_totals.csv
```

This writes `movement_totals.csv` with one row per movement, seven pollutant
columns (`co_kg`, `co2_kg`, `hc_kg`, `nox_kg`, `sox_kg`, `pm10_kg`,
`pm25_kg`), plus metadata (`oid`, `aircraft`, `departure_arrival`,
`profile_id`, `method`).

Add `--method` to pick the emission method
([Selecting the emission method](#selecting-the-emission-method)),
`--processes N` to parallelise ([Parallel runs](#parallel-runs)), or
`--oids 4,12,73` to compute only a subset of movements. `--austal-out DIR`
also writes the AUSTAL `emissions.parquet` + `sources.parquet` pair for the
aircraft sources alone:

```bash
python -m openalaqs_standalone aircraft example/training/training_out.alaqs \
    --out movement_totals.csv \
    --austal-out ./austal_aircraft/
```

## AUSTAL-ready folders: austal

The stationary half reads the emission factors the plugin wrote into the
`.alaqs` file; it does not compute them (see
[README](README.md#prerequisite-the-stationary-efs-must-already-be-in-the-alaqs-file)).

Stationary half only:

```bash
python -m openalaqs_standalone austal example/training/training_out.alaqs \
    --year 2025 \
    --out ./inputs/
```

With the meteo year shifted and the receptors written in UTM zone 31N
(EPSG:32631), for a Rotterdam road and parking study:

```bash
python -m openalaqs_standalone austal \
    EHRD_roadways_2025_final_with_parking.alaqs \
    --year 2025 \
    --meteo-year-shift 2025 \
    --receptor-target-epsg 32631 \
    --title "EHRD road and parking" \
    --out ./inputs/
```

Stationary + aircraft halves in one run:

```bash
python -m openalaqs_standalone austal example/training/training_out.alaqs \
    --year 2025 \
    --include-aircraft --aircraft-method bymode \
    --out ./inputs/
```

This computes the aircraft movement emissions (including the
movement-driven gate emissions) and folds them into the same
`sources.parquet` and `emissions.parquet` as the stationary sources.

The AUSTAL grid is read from the study's `grid_3d_definition`. Receptors
outside that grid are dropped (with their IDs in the log);
`--grid-size`/`--grid-step` override only this clipping square, not the
AUSTAL grid.

`--pollutants` defaults to the full stationary set
(`co,hc,nox,sox,pm10,pm25`); pass an explicit comma-separated list to
narrow it. `co2` is also accepted; it comes from the aircraft only (see
[README](README.md#pollutants)).

### Output folders

```
inputs/
├── sources_folder/
│   └── sources.parquet          one row per source; schema: source_id,
│                                source_type, label, geometry_wkt,
│                                geometry_kind, height_m, extent_m2,
│                                length_m, in_study, extra_json
│                                (+ delta_z_m when aircraft sources are included)
├── emissions_folder/
│   ├── emissions.parquet        one row per (source, pollutant, hour);
│   │                            schema: timestamp, source_id, pollutant,
│   │                            kg_in_hour
│   ├── co_emissions.gpkg, ...   one GeoPackage per pollutant, polygon
│   │                            features per inventory grid cell
│   └── runway_checks.csv        route and profile checks (only with
│                                --include-aircraft); never blocks the run
├── receptors_folder/
│   └── receptors.csv            schema: name, x, y, z (in target UTM)
├── meteo_folder/
│   └── meteo.csv                hourly meteorology; schema: timestamp,
│                                wind_direction_deg, wind_speed_ms,
│                                obukhov_length_m, mixing_height_m
├── config_folder/
│   └── config.json              AUSTAL writer settings + grid + flags
└── austal_folder/               (empty; filled by austal_prep)
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
`--use-isa-meteo`) forces ISA, for comparison with runs made at ISA.

### Atmosphere aloft

The hourly meteo row is carried to each flight segment's height with
`--atmosphere-model` (both subcommands):

| Value | Ambient at the segment's height |
| --- | --- |
| `standard_lapse` (default) | 2 m temperature and station pressure (from QNH and the airport elevation) carried up with the ISA lapse rate and the hydrostatic law; humidity ratio kept |
| `surface_layer` | AUSTAL 3.3 boundary-layer temperature profile from the hour's temperature, wind, Obukhov length and mixing height; pressure and humidity as above. Implied heat flux bounded at 600 / 100 W/m2 (unstable / stable), with a warning. 1 to 3 K too cold against the De Bilt radiosondes of 2025 |
| `ground_held` | the hourly row at every height, the ambient conditions of 5.4.0 (the fuel-flow scaling is not switched back, so 5.4.0 BFFM2 results are not reproduced) |

Site parameters: `--z0`, `--d0`, `--ha` (m), the AUSTAL site parameters. Both
subcommands share one default with the plugin's AUSTAL module and `austal_prep`
(`open_alaqs/core/tools/surface_layer_atmosphere.site_parameters`): z0 0.1 m
(the TA Luft value for airports), d0 6 z0 (0.6 m), ha 10 m + d0 (10.6 m); d0
and ha are derived from z0 when not given. `aircraft` uses them for
`surface_layer` only; `austal` writes them to the AUSTAL config and uses them
for the emissions alike. How to choose them: [Site parameters](../documents/user/DISPERSION_AUSTAL.md#site-parameters). With
`--isa-meteo` (or no meteo row) the ambient stays ISA at every height whatever
the model. A meteo row whose temperature or pressure is not a positive number
stops the run with a message naming its date.

Engine tests in the `austal` subcommand use the ICAO mode values, so the
method and atmosphere options do not reach them (see
[README](README.md#limitations)).

```bash
python -m openalaqs_standalone aircraft $ALAQS --out totals.csv \
    --method bffm2_traj --atmosphere-model ground_held   # the 5.4.0 ambient conditions
```

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
floating-point noise (see
[Tolerances](../documents/validation/VALIDATION_GUIDE.md#tolerances)).

## The NOx ambient correction

The ICCAIA / CAEP/14 NOx ambient correction at takeoff (TO) and climb-out
(CL) segments. It reads ambient temperature, pressure and humidity from
`tbl_InvMeteo` per inventory period, plus airport elevation from
`user_study_setup`. The `tow_ratio` column from `user_aircraft_movements`
is used as a weight when set (defaults to 1.0; 0, negative or NaN is
taken as 1.0, as in the plugin).

**Default: off**, as in the plugin, so the default bymode output matches
the plugin's. Opt in with `--apply-nox-corrections`:

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

## Aircraft-only output

By default, the pollutant columns (`co_kg` ... `pm25_kg`) of the
`aircraft` subcommand's per-movement CSV hold the movement total: the
trajectory plus gate (GSE + GPU) plus APU plus engine-start contributions
per movement (the "what flew this
hour, including everything that came with it" total). This is the
right quantity for inventory totals and for studies where the
trajectory + ground services are reported together.

For comparison with the plugin (validations V2 and V5 of
[VALIDATION_GUIDE.md](../documents/validation/VALIDATION_GUIDE.md)),
add `--aircraft-only` to the `aircraft` subcommand:

```bash
python -m openalaqs_standalone aircraft $ALAQS --out totals.csv \
    --method bymode --aircraft-only
```

With the flag set, the standalone subtracts the gate, APU and
engine-start contributions from each pollutant column per movement
before writing the CSV. The resulting value per pollutant is directly
comparable to the plugin's `source_type = "Movement"` rows in its
per-source emissions CSV (which contain trajectory contributions only;
gate / APU / start emissions are emitted as separate source types on
the plugin side).

The flag affects only the per-movement CSV writer and the on-screen
study-totals summary (labeled `(kg, aircraft-only)` when the flag is
set, otherwise `(kg, total)`). It has no effect on the `austal`
subcommand's emissions.parquet output, which always uses the full
movement total.

## Reading config.json

`config.json`, written into `config_folder/`, is the metadata file that any
downstream AUSTAL pipeline reads. The `aircraft` and `austal` subcommands write it
and do not read it; `python -m austal_prep --config config.json` reads the keys
marked in the table. An example:

```json
{
  "title": "Rotterdam",
  "qs": 3,
  "z0": 0.1,
  "d0": 0.6,
  "ha": 10.6,
  "os_options": "NOSTANDARD;NOTALUFT;SCINOTAT;Kmax=1",
  "mixing_height_included": true,
  "grid_writer_mode": "hybrid",
  "source_offset_cells": 2,
  "max_receptors": 20,
  "source_aggregation": "by_type_per_pollutant",
  "apply_nox_corrections": false,
  "atmosphere_model": "standard_lapse",
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
| `qs`                   | AUSTAL quality level (read by `austal_prep`)                        |
| `z0`                   | roughness length (m); default 0.1 (TA Luft, airports)               |
| `d0`                   | displacement height (m); null or absent = 6 z0                      |
| `ha`                   | anemometer height (m) for the roughness z0; null or absent = 10 m + d0 |
| `os_options`           | AUSTAL `os` line (read by `austal_prep`)                            |
| `mixing_height_included`| feed mixing-height column to AUSTAL meteo (read by `austal_prep`)  |
| `grid_writer_mode`     | `hybrid` (default: one e-file per hour for aircraft sub-sources, one time-invariant e-file for stationary sources), `time_indexed` (one time-invariant e-file for all) or `legacy` (per-hour files for all) |
| `source_offset_cells`  | offset of the source origin from the grid origin, in cells (2; read by `austal_prep`) |
| `max_receptors`        | cap on the number of receptor points (20; null: no cap; read by `austal_prep`) |
| `source_aggregation`   | `by_type_per_pollutant` (recommended), `by_type` (legacy) or `none` (one AUSTAL source per input source); read by `austal_prep` |
| `apply_nox_corrections`| record of the `--apply-nox-corrections` choice; not read by any command (the emissions in `emissions.parquet` already include it) |
| `atmosphere_model`     | record of the `--atmosphere-model` choice (`standard_lapse` by default); not read by any command (as above) |
| `selected_pollutants`  | pollutants of the run; not read by `austal_prep`, which takes `--pollutants` (default: all in `emissions.parquet`) |
| `grid.*`               | AUSTAL calc grid: cell size, count, origin, vertical layers, ref pt (read by `austal_prep`) |
| `start_dt` / `end_dt`  | run window (from `--year` or `--start`/`--end`); not read by `austal_prep`, which takes `--start` / `--end` |

`python -m austal_prep` reads `title`, `qs`, `z0`, `d0`, `ha`, `os_options`,
`pm10_fine_fraction`, `mixing_height_included`, `grid_writer_mode`
(`time_indexed` when absent), `source_height`, `source_offset_cells`,
`max_receptors`, `source_aggregation`, `processes` and `grid.*`. It ignores
the other keys: it writes AUSTAL inputs from emissions already computed.

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

## Parallel runs

`--processes N` (N > 1) runs the aircraft movement compute across a process
pool; the results are bit-identical to the serial driver. On the `austal`
subcommand it takes effect only with `--include-aircraft`. The stationary
compute is already numpy-vectorised and is not parallelised.

```bash
# 4 worker processes
python -m openalaqs_standalone aircraft $ALAQS --out totals.csv --processes 4

python -m openalaqs_standalone austal $ALAQS --year 2025 --out ./inputs/ \
    --include-aircraft --processes 4
```

Worth it for studies with hundreds or thousands of movements; not worth it
for the training study.

## Restricting the time window

The `austal` subcommand accepts `--start` and `--end` (ISO format) to
restrict the run to a window inside the inventory year:

```bash
python -m openalaqs_standalone austal $ALAQS \
    --year 2025 --out ./inputs/ \
    --include-aircraft \
    --start 2025-12-01 --end 2025-12-02
```

The window is half-open `[start, end)`. Behaviour:

- **Stationary sources**: hourly emissions are filtered to the
  window. The per-hour mass for kept hours is unchanged, so
  conservation against the same-hours slice of the full-year output
  holds exactly.
- **Aircraft sources**: a movement is included if its start time is
  in the window, using `block_time` for departures and `runway_time`
  for arrivals (the direction-aware rule); for movements that
  straddle the window boundary, the per-segment emissions are also
  clipped to the window so the run only contains emissions that
  physically occur in `[start, end)`. This is the
  dispersion-correct interpretation.
- **Meteo and config**: `meteo.csv` is trimmed to the window;
  `config.json`'s `start_dt` / `end_dt` reflect the window bounds.

The CLI rejects windows outside the inventory year (`start` must be
in `[year-01-01, year+1-01-01)`) and `start >= end`.

## Troubleshooting

**`ModuleNotFoundError: No module named 'open_alaqs.core.tools.bffm2'`**:
the standalone imports BFFM2 from the QGIS plugin tree. Run from the
repository root with `PYTHONPATH=.`.

**`shapely.errors.GEOSException` on a particular movement**: likely a
self-intersecting taxi route in the source `.alaqs`. Identify the offending
oid via `--oids` bisection; fix the geometry in the plugin or strip the
movement.

**`apply_nox_corrections` had no effect**: check that `--method` (or
`--aircraft-method`) is `bymode`. The flag is silently ignored for BFFM2
methods (which include their own ambient correction) and for helicopter
movements.

**Output `emissions.parquet` is empty**: usually means `instudy` is not `'1'` (for example `'0'`)
on every source, or a time window with no movements. Run with `--year`
only first to confirm the study has emissions, then narrow.

See also:

- [README](README.md): architecture, conventions and limitations of the package
- [WITHOUT_QGIS.md](../documents/user/WITHOUT_QGIS.md): which tool to run without the QGIS GUI
- [DISPERSION_AUSTAL.md](../documents/user/DISPERSION_AUSTAL.md): running AUSTAL and reading its results
- [TROUBLESHOOTING.md](../documents/user/TROUBLESHOOTING.md): problems with the plugin
