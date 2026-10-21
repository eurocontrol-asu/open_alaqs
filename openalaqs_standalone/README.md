# openalaqs_standalone

A QGIS-free pipeline that turns an OpenALAQS `.alaqs` study file into
AUSTAL-ready inputs. It covers both source families:

- **Stationary sources** (road, parking, point, area): an ALAQS ->
  AUSTAL *adapter*. It reads pre-computed emission factors stored in
  the `.alaqs` file by a prior OpenALAQS plugin run and spreads them
  across the year using activity profiles. It does not run COPERT5 or
  compute those factors itself. See **Prerequisite** below.
- **Aircraft sources** (fixed-wing movements, helicopters, and the
  gate GSE/GPU emissions those movements drive): a real emission
  *calculator*. It walks each movement's trajectory or taxi route and
  integrates per-segment fuel, time and emission indices, with three
  selectable methods. This half is validated against the CAEP14
  reference and the pinned plugin outputs (see
  `validation/tools/CAEP14_VALIDATION.md`).

The package runs without QGIS, without PyQt, and without a native
SpatiaLite extension: it reads the `.alaqs` SQLite directly and parses
geometry BLOBs with shapely.

It ships as a top-level package in the Open-ALAQS repository, as a
sibling of the QGIS plugin at `open_alaqs/`. It can also be installed
on its own (`pip install -e .` from this directory) without needing the
plugin to be present. The AUSTAL writer helpers it depends on live in
the sibling `austal_prep/` package.

For a task-oriented walk-through of running the package from a terminal
(installation, CLI subcommands, method selection, NOx ambient correction,
`config.json` keys, validation harness), see [USAGE.md](USAGE.md). The
sections below cover architecture, conventions, and limitations.

## What it produces

Two output shapes, depending on which entry point is used.

**The `austal` command** builds the six-folder structure that the
`austal_prep` package consumes:

```
<output_root>/
├── sources_folder/
│   └── sources.parquet      schema: source_id, source_type, label,
│                            geometry_wkt, geometry_kind, height_m,
│                            extent_m2, length_m, in_study, extra_json
│                            (+ delta_z_m when aircraft sources are included)
├── emissions_folder/
│   ├── emissions.parquet    schema: timestamp, source_id, pollutant,
│   │                        kg_in_hour    (one row per source-pollutant-hour)
│   ├── <pollutant>_emissions.gpkg  plugin-style per-pollutant grid totals
│   │                        (inventory_gpkg.py)
│   └── runway_checks.csv    route and profile check report (only with
│                            --include-aircraft; see runway_checks.py)
├── receptors_folder/
│   └── receptors.csv        schema: name, x, y, z   (in target UTM)
├── meteo_folder/
│   └── meteo.csv            schema: timestamp, wind_direction_deg,
│                            wind_speed_ms, obukhov_length_m,
│                            mixing_height_m
├── config_folder/
│   └── config.json          AUSTAL study config
└── austal_folder/           empty; populated by the recipe
```

With `--include-aircraft`, the aircraft movement emissions are folded
into the same `sources.parquet` and `emissions.parquet`: each occupied
inventory grid cell becomes a synthetic `aircraft:cell:<ix>_<iy>_<iz>`
source, so one austal_prep run covers the whole study.

**The `aircraft` command** runs the aircraft core directly and writes:

- a per-movement totals CSV (one row per movement, one column per pollutant), and
- optionally, with `--austal-out`, the AUSTAL `emissions.parquet` +
  `sources.parquet` pair for the aircraft sources alone.

## Architecture

### Stationary modules

Per-source-type. Each reads one ALAQS table and produces its slice of
`emissions.parquet`; the EFs are already in the file.

```
_profiles.py           shared: load and apply hourly/daily/monthly
                       activity profiles; STATIONARY_POLLUTANTS
extract_sources.py     read source geometries from .alaqs
                       (all source types, single output)
compute_road.py        roadway segments -> hourly emissions
compute_parking.py     parking lots    -> hourly emissions
compute_point.py       stationary point sources -> hourly emissions
compute_area.py        area sources    -> hourly emissions
```

### Aircraft modules

A real per-movement emission calculator, validated against the
CAEP14 reference.

```
geometry.py            QGIS-free spatial primitives; SpatiaLite WKB
                       blob reader
movements.py           .alaqs database accessors for the aircraft
                       pipeline (movements, runway, taxi routes,
                       engines, gates, gate profiles)
compute_aircraft.py    fixed-wing per-movement emissions, three
                       methods (bymode, bffm2_anchor, bffm2_traj),
                       with per-segment records retained
nox_correction.py      Reference A NOx ambient correction (humidity
                       and temperature). Off by default; opt-in via
                       `--apply-nox-corrections` on the `aircraft`
                       and `austal` commands so the default behaviour
                       remains bit-identical to the plugin's bymode
                       path.
compute_helicopter.py  FOCA helicopter per-movement emissions
compute_gate_movements.py  per-movement gate (GSE + GPU) emissions,
                       driven by the movements and default_gate_profiles;
                       folded into each movement's total
compute_apu_movements.py   per-movement APU emissions, folded into each
                       movement's total
compute_start_movements.py per-movement engine-start emissions (departures),
                       folded into each movement's total
source_dynamics.py     smooth-and-shift (--source-dynamics default/sas)
                       spatial apportionment
compute_engine_test.py per-event engine-test-run emissions from the
                       `engine_test_events` table. QGIS-free twin of
                       `EngineTestSourceModule`; same math bit-for-bit.
                       Three thrust modes: `snap` (default), `meem`
                       (numerically identical to snap for engine-test
                       events at anchor thrust), `bffm2` (gas-phase
                       ambient correction, PM10/SOx passthrough).
                       BFFM2 requires an optional `conn` kwarg for
                       `tbl_InvMeteo` lookups; snap-only workflows use
                       the same signature as before.
extract_engine_test_events.py  read engine_test_events joined against
                       shapes_area_sources (test-site filter);
                       produces the event-dict input that
                       compute_engine_test.py consumes.
compute_movements.py   dispatch + study-level driver
parallel.py            multiprocessing driver for the movement
                       compute; results bit-identical to the serial
                       driver
```

### Distribution and output

```
distribute.py          per-(time bucket, grid cell) emission
                       distribution: hourly or sub-hour in time, per
                       grid cell in space
austal_aircraft.py     gridded aircraft emissions -> the
                       emissions.parquet + sources.parquet pair
                       austal_prep consumes
inventory_gpkg.py      emissions.parquet + sources.parquet -> plugin-style
                       per-pollutant GeoPackages (<pollutant>_emissions.gpkg)
```

### Utilities and entry points

```
adapt_meteo.py         .alaqs (or external CSV) -> meteo.csv
adapt_receptors.py     external receptor CSV -> standard receptors.csv
make_config.py         scaffold a config.json from .alaqs metadata
orchestrate.py         builds the six-folder austal_prep structure;
                       the `austal` subcommand; callable as a Python
                       function for embedding in other pipelines
cli.py / __main__.py   `python -m openalaqs_standalone <command>`:
                       dispatches to `aircraft` or `austal`
runway_placement.py    placement of flight profiles on the runway (rules shared
                       with the plugin: open_alaqs/core/tools/runway_placement.py)
runway_checks.py       route and profile check report; also
                       `python -m openalaqs_standalone.runway_checks study.alaqs out.csv`
```

### Source coverage

| Source type | ALAQS table | Status |
| --- | --- | --- |
| Roadway | `shapes_roadways` | implemented (adapter) |
| Parking | `shapes_parking` | implemented (adapter) |
| Point | `shapes_point_sources` | implemented (adapter) |
| Area | `shapes_area_sources` | implemented (adapter) |
| Gate | `shapes_gates` + `default_gate_profiles` | implemented (movement-driven calculator) |
| Aircraft movement | `user_aircraft_movements` | implemented (calculator, 3 methods) |
| Helicopter movement | `user_aircraft_movements` | implemented (FOCA calculator) |
| Engine test site | `engine_test_events` + `shapes_area_sources` (`is_test_site='1'`) | implemented (calculator, 3 thrust modes) |

## Quick start

### Stationary sources, the six-folder structure

```bash
python -m openalaqs_standalone austal \
    EHRD_roadways_2025_final_with_parking.alaqs \
    --year 2025 \
    --meteo-year-shift 2025 \
    --receptor-target-epsg 32631 \
    --title "EHRD road and parking" \
    --out ./inputs/
```

The AUSTAL grid is read from the study's `grid_3d_definition`. Receptors
outside that grid are dropped (with their IDs in the log);
`--grid-size`/`--grid-step` override only this clipping square, not the
AUSTAL grid.

`--pollutants` defaults to the full stationary set
(`co,hc,nox,sox,pm10,pm25`); pass an explicit comma-separated list to
narrow it. `co2` is also accepted; it comes from the aircraft only (see
[Pollutants](#pollutants)).

### The whole study, stationary + aircraft, in one run

```bash
python -m openalaqs_standalone austal study.alaqs \
    --year 2025 --out ./inputs/ \
    --include-aircraft --aircraft-method bymode
```

This computes the aircraft movement emissions (including the
movement-driven gate emissions) and folds them into the same
`sources.parquet` and `emissions.parquet` as the stationary sources.

### A shorter time window

The `austal` command also accepts `--start` and `--end` (ISO format)
to restrict the run to a window inside the inventory year:

```bash
python -m openalaqs_standalone austal study.alaqs \
    --year 2025 --out ./inputs/ \
    --include-aircraft \
    --start 2025-01-01 --end 2025-01-08
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

### Parallel aircraft compute via `austal`

When `--include-aircraft` is set, `--processes N` (N > 1) runs the
aircraft movement compute across a process pool, producing
bit-identical results to the serial driver:

```bash
python -m openalaqs_standalone austal study.alaqs \
    --year 2025 --out ./inputs/ \
    --include-aircraft --processes 4
```

The stationary computes are already numpy-vectorised and are not
parallelised; `--processes` affects only the aircraft pipeline.
Worth using for studies with many movements; not worth using on
small movement counts.

### The aircraft core directly

```bash
# per-movement totals CSV
python -m openalaqs_standalone aircraft study.alaqs \
    --out movement_totals.csv --method bymode

# also write the AUSTAL pair, across four worker processes
python -m openalaqs_standalone aircraft study.alaqs \
    --out movement_totals.csv \
    --austal-out ./austal_aircraft/ \
    --processes 4
```

`--processes N` (N > 1) runs the multiprocessing driver, which
produces results identical to the serial driver.

## Individual modules

Each compute module also has its own CLI entry point, useful for
isolating one source type:

```bash
python -m openalaqs_standalone.extract_sources study.alaqs --out sources.parquet
python -m openalaqs_standalone.compute_road study.alaqs --year 2025 --out road.parquet
python -m openalaqs_standalone.adapt_meteo study.alaqs --year-shift-to 2025 --out meteo.csv
python -m openalaqs_standalone.adapt_receptors cimlk.csv \
    --source-epsg 28992 --target-epsg 32631 --out receptors.csv
python -m openalaqs_standalone.make_config study.alaqs --year 2025 --out config.json
```

## Prerequisite: the stationary EFs must already be in the .alaqs file

**The stationary half of this pipeline does not run COPERT5 or compute
emission factors.** It reads the pre-computed `nox_gm_km`,
`pm10_gm_km`, `p1_gm_km` (etc.) values already stored in the
`shapes_roadways` and `shapes_parking` tables, then multiplies by
distance, vehicle counts, and the temporal profile to produce hourly
emissions.

So the `.alaqs` file fed to the stationary computes must have been
produced by an upstream OpenALAQS plugin run that:

- applied COPERT5 with the correct fleet composition and Euro standards,
- applied any study-specific adjustments (cold-start at trip scale,
  non-exhaust EMEP/EEA Tier 2 factors, parking scaling, etc.),
- wrote the resulting g/km and g/vh values back into the source tables.

The standalone stationary computes are faithful to whatever EFs are in
the file: PR2 fixes propagate if present; older unpatched EFs produce
correspondingly older emissions.

The **aircraft** half is different: it is a real calculator and needs
no pre-computed EFs. It reads the engine emission-index tables, the
aircraft profiles, the gate profiles and the meteo directly and
integrates the emissions itself.

### Workflow for the stationary inputs

1. Build the inventory in QGIS using the OpenALAQS plugin (5.0.0 or
   later, which includes the PR2 fixes such as parking cold start at
   trip scale).
2. The plugin's "Calculate Emissions" step writes EFs into
   `shapes_roadways` and `shapes_parking`.
3. Save the resulting `.alaqs` file.
4. Run the `austal` command against that file.

### Why the stationary half is structured this way

The plugin's emission-calculation modules (`RoadwaySourceModule.py`,
`ParkingSourceModule.py`) have QGIS dependencies mixed with the COPERT5
logic, so importing them outside QGIS is not straightforward. The
stationary computes read the EFs the plugin already wrote rather than
recomputing them. The long-term fix is to extract the pure-Python
calculation logic into a shared `core/tools/` and have both the plugin
and the standalone import it; until then, the workflow above is the
bridge. The aircraft half already follows that better pattern: it
shares the QGIS-free `open_alaqs.core.tools.*` algorithm modules with
the validation reference.

### Verifying your .alaqs has the right stationary EFs

The PR2-applied EHRD baseline for parking is:

- NOx 31.26 kg/yr
- PM10 3.27 kg/yr
- PM2.5 1.79 kg/yr (PM10/PM2.5 ratio 1.83)

If `compute_parking` against an `.alaqs` file gives NOx around 20.25
kg/yr instead of 31.26, the cold-start fix was not applied upstream;
rebuild the inventory with the PR2 patches.

## Conventions

### Source ID prefixes

Every source ID carries a type prefix, used by the by-type
aggregation and to keep namespaces distinct in a combined
`sources.parquet`:

- `road:<roadway_id>`
- `parking:<parking_id>`
- `point:<point_id>`
- `area:<area_id>`
- `gate:<gate_id>` (the gate geometry; gate emissions are folded into
  the aircraft movement totals)
- `aircraft:cell:<ix>_<iy>_<iz>` (a synthetic per-grid-cell source for
  the gridded aircraft emissions, one per occupied 3D cell)

### Pollutants

The stationary computes support `co, hc, nox, sox, pm10, pm25` (the
constant `STATIONARY_POLLUTANTS` in `_profiles.py`), which is the
default pollutant list for the stationary computes and for the
`austal` command.

The aircraft core supports `co, co2, hc, nox, sox, pm10, pm25`. The
stationary source tables carry no co2. When `--include-aircraft` is
used, the aircraft emissions are filtered to the requested pollutant
list so the combined `emissions.parquet` is coherent. `--pollutants`
of the `austal` command accepts co2: the stationary sources contribute
0 for it (they are not asked for co2, and one info line says so), and
with `--include-aircraft` the aircraft co2 is written to
`emissions.parquet` and `co2_emissions.gpkg`.

`austal_prep` writes co2 to `austal.txt` and `series.dmna` as the
substance `co2` (source strength in g/s), the same name the plugin
writes. `co2` (like `co`, `hc` and `sox`) is not one of the substances
of the standard AUSTAL 3.3 settings; it is defined in the
`austal.settings` shipped with OpenALAQS (`documents/AUSTAL/`, section
`[CO2]`, concentration in mg/m3). Replace the `austal.settings` of the
AUSTAL installation with that copy before running AUSTAL on these
inputs (see `documents/AUSTAL/AUSTAL.md`).

`austal_prep` writes pm10 as two AUSTAL components, `pm-1` (the fine
fraction, `pm10_fine_fraction`) and `pm-2` (the rest), which AUSTAL sums
into substance `pm`; pm25 is written as `pm25-1` (substance `pm25`).

### Emission factor columns (stationary)

The OpenALAQS schema is inconsistent between source types about which
column holds PM2.5 versus total PM10:

| Source | Total PM10 column | PM2.5 column |
| --- | --- | --- |
| Road | `pm10_gm_km` | `p1_gm_km` |
| Parking | `pm10_gm_vh` | `p2_gm_vh` |
| Point | `pm10_kg_k` | `p2_kg_k` (assumed; matches parking) |
| Area | `pm10_kg_unit` | `p2_kg_unit` (assumed; matches parking) |

The pollutant-column dict in each compute module encodes this. For
point and area sources the `p2_*` = PM2.5 assumption is empirically
unverified, because the EHRD study has no point or area sources to
test against. If a study uses these types and the PM10/PM2.5 ratio
looks wrong, verify the upstream conventions.

### Activity profiles (stationary)

`_profiles.py` builds an hourly multiplier array from a
(hour_profile, daily_profile, month_profile) triplet, normalised so
the mean over the year is 1.0; the per-hour emission is then
`(annual_kg / hours_in_year) * mult[h]`. Missing or unknown profiles
fall back to all-1.0. The hour count is leap-year-aware.

### Coordinate systems

- ALAQS internal: EPSG:3857 (Web Mercator). Geometries in the `.alaqs`
  database are stored in this CRS, and that is what `extract_sources`
  and the aircraft grid polygons output in their WKT.
- AUSTAL local: a metric UTM zone, configured per study via `utm_epsg`
  in `config.json`. Reprojection from 3857 to the AUSTAL frame happens
  in `austal_prep`.
- CIMLK receptors: EPSG:28992 (Dutch Rijksdriehoek). Reprojection to
  UTM happens in `adapt_receptors`.

## Limitations

The phase plan for the aircraft pipeline (A0 per-movement core, A2
gate emissions, A3 time-and-grid distribution, A4 parallel driver, A5
AUSTAL and GeoPackage output) is complete, and the `austal` command
joins the stationary and aircraft halves into one run.

What is not yet built:

- **MESO-NH export.** An exporter to the MESO-NH ASCII emission
  formats (a ground-emissions case and an altitude-emissions case) is
  scoped but not implemented: a few
  conversion conventions still need to be confirmed (the molec/cm2/s
  conversion basis for the ground case, the multi-species column
  order, the altitude datum/sign convention).
- **Point and area PM column convention** is assumed, not verified
  (see "Emission factor columns" above): no test study exercises
  those source types.
- **Shared-import refactor of the stationary half.** The stationary
  computes still read pre-computed EFs rather than calling shared
  COPERT5 logic; see "Why the stationary half is structured this
  way".

## Testing

```bash
PYTHONPATH=. pytest openalaqs_standalone/validation/tests/ -q
```

A few more standalone tests live in the plugin suite under `tests/`.
Together they cover, among other things:

- source extraction: engine-test sites emitted as their own source type
  (`test_phase1b_extract_sources_standalone.py`) and missing `shapes_*`
  tables skipped (`tests/test_extract_sources_missing_tables.py`)
- the plugin-output gate: the CAEP14 reference and the standalone
  reproduce the pinned plugin CSVs (`validation/data/plugin_output/`)
  for all 15 movements and the three methods, within 2e-4 relative
  (movement 11, the ADS-B track, differs by 1.3e-5 on `bffm2_traj`)
  (`test_plugin_csv_vs_reference.py`)
- the CAEP14 reference itself (`test_caep14_sheet_reference_case.py`,
  `test_caep14_reference_lookups.py`, `test_helicopter_caep14_reference.py`)
- engine-start emissions and `gate_emissions_code` (`test_start_gate_code.py`;
  plugin parity in `tests/test_zz_gate_code_start_parity.py`)
- engine-test event extraction and emissions, all three thrust modes
  (`test_phase3_engine_test_standalone.py`)
- runway placement of flight profiles and the segment Mach number
  (`test_runway_placement.py`, `test_segment_mach.py`)
- the grid distribution: taxi split by segment time, helicopter helipad
  cell, vertical layer fractions below ground
  (`test_taxi_split_by_segment_time.py`,
  `test_helicopter_helipad_standalone.py`,
  `test_iz_layer_fractions_below_ground.py`)
- the per-pollutant GeoPackages (`inventory_gpkg`): area, engine-test
  and point sources are gridded along with the others, and the
  GeoPackage total equals the `emissions.parquet` mass
  (`test_inventory_gpkg_all_source_kinds.py`)
- an `austal --include-aircraft` run on `training_v3.alaqs` through
  `austal_prep`: per-hour e-files for the aircraft sources, per-pollutant
  spatial weights, mass conservation (`tests/test_austal_prep_hybrid_mode.py`)

Tests that need `mod_spatialite` (the CAEP14 reference) or a fixture
that is not present are skipped with a message.
