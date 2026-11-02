# openalaqs_standalone

The architecture, modules, conventions, limitations and tests of
`openalaqs_standalone`, for developers. To run it, see
[USAGE.md](USAGE.md) (install, commands, options, output folders).

`openalaqs_standalone` is a QGIS-free pipeline that turns an OpenALAQS
`.alaqs` study file into AUSTAL-ready inputs. It covers both source families:

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
  [CAEP14_VALIDATION.md](validation/tools/CAEP14_VALIDATION.md)).

The package runs without QGIS, without PyQt, and without a native
SpatiaLite extension: it reads the `.alaqs` SQLite directly and parses
geometry BLOBs with shapely.

It ships as a top-level package in the Open-ALAQS repository, as a
sibling of the QGIS plugin at `open_alaqs/`. It imports QGIS-free
modules of the plugin tree (`open_alaqs.core.tools`: BFFM2, MEEM, FOCA,
fuel sulphur, UTM and runway placement; `open_alaqs.core.interfaces.Emissions`), and its `pyproject.toml` packages
`openalaqs_standalone` only, so it is not usable without the plugin tree:
run it from the repository root with the root on `PYTHONPATH` (see
[USAGE.md](USAGE.md#install)). The AUSTAL writer helpers it depends on
live in the sibling `austal_prep/` package.

Contents:

- [What it produces](#what-it-produces)
- [Architecture](#architecture)
- [Prerequisite: the stationary EFs must already be in the .alaqs file](#prerequisite-the-stationary-efs-must-already-be-in-the-alaqs-file)
- [Conventions](#conventions)
- [Limitations](#limitations)
- [Testing](#testing)

## What it produces

Two output shapes, depending on which entry point is used.

**The `austal` command** builds the six-folder structure that the
`austal_prep` package consumes (sources, emissions, receptors, meteo,
config and an empty AUSTAL folder; the folder tree and file schemas are in
[USAGE.md](USAGE.md#output-folders)). With `--include-aircraft`, the
aircraft movement emissions are folded into the same `sources.parquet` and
`emissions.parquet`: each occupied inventory grid cell becomes a synthetic
`aircraft:cell:<ix>_<iy>_<iz>` source, so one austal_prep run covers the
whole study.

**The `aircraft` command** runs the aircraft core directly and writes a
per-movement totals CSV (one row per movement, one column per pollutant)
and, with `--austal-out`, the AUSTAL `emissions.parquet` +
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
nox_correction.py      ICCAIA NOx ambient correction (take-off weight
                       ratio, temperature and humidity); off by default (see
                       USAGE.md, "The NOx ambient correction")
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

### Running one module

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
the file: fixes the plugin applied when it wrote the EFs (such as the
parking cold start at trip scale) carry through; EFs written by an older
plugin give correspondingly older emissions.

The **aircraft** half is different: it is a real calculator and needs
no pre-computed EFs. It reads the engine emission-index tables, the
aircraft profiles, the gate profiles and the meteo directly and
integrates the emissions itself.

### Workflow for the stationary inputs

1. Build the inventory in QGIS using the OpenALAQS plugin (5.0.0 or
   later, which applies the parking cold start at trip scale).
2. The plugin's `Recalculate` button of the parking and roadway forms
   writes the EFs into `shapes_roadways` and `shapes_parking`.
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

For an EHRD study that is not shipped with the repository, the parking
baseline with the trip-scale cold start is (computed with 5.2.0):

- NOx 31.26 kg/yr
- PM10 3.27 kg/yr
- PM2.5 1.79 kg/yr (PM10/PM2.5 ratio 1.83)

and an inventory without the trip-scale cold start gives NOx around
20.25 kg/yr instead of 31.26. These figures do not apply to the bundled training
study: its single `ParkingLot` (20 000 vehicles per year, NOx 95.82
g/vehicle) gives NOx 1916.33 kg and PM10 15.99 kg for 2025
(`python -m openalaqs_standalone.compute_parking
example/training/training_out.alaqs --year 2025 --out parking.parquet`
from the repository root).

## Conventions

### Source ID prefixes

Every source ID carries a type prefix, used by the by-type
aggregation and to keep namespaces distinct in a combined
`sources.parquet`:

- `road:<roadway_id>`
- `parking:<parking_id>`
- `point:<point_id>`
- `area:<area_id>`
- `engine_test:<oid>` (an area source flagged `is_test_site = '1'`;
  its `source_type` is `engine_test`)
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
inputs (see [AUSTAL.md](../documents/AUSTAL/AUSTAL.md#configuration-files)).

`austal_prep` writes pm10 as two AUSTAL components, `pm-1` (the fine
fraction, `pm10_fine_fraction`) and `pm-2` (the rest), which AUSTAL sums
into substance `pm`; pm25 is written as `pm25-1` (substance `pm25`).

### Emission factor columns (stationary)

The column that holds PM2.5 differs between the schema of each source
type:

| Source | Total PM10 column | PM2.5 column |
| --- | --- | --- |
| Road | `pm10_gm_km` | `p2_gm_km` (`p1_gm_km` is PM0.1) |
| Parking | `pm10_gm_vh` | `p2_gm_vh` |
| Point | `pm10_kg_k` | `p2_kg_k` (assumed; matches parking) |
| Area | `pm10_kg_unit` | `p2_kg_unit` (assumed; matches parking) |

The pollutant-column dict in each compute module encodes this. For
point and area sources the `p2_*` = PM2.5 assumption is empirically
unverified: the training study has one point source (`Power`, PM10
60.04 kg/unit but P1 and P2 0) and one area source (`Terminal`, no PM),
so no bundled study has a PM2.5 factor for these types to test against. If a study uses these types and the PM10/PM2.5 ratio
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

The aircraft pipeline (per-movement core, gate emissions, time-and-grid
distribution, parallel driver, AUSTAL and GeoPackage output) is complete,
and the `austal` command joins the stationary and aircraft halves into one
run.

What is not yet built:

- **MESO-NH export.** An exporter to the MESO-NH ASCII emission
  formats (a ground-emissions case and an altitude-emissions case) is
  scoped but not implemented: a few
  conversion conventions still need to be confirmed (the molec/cm2/s
  conversion basis for the ground case, the multi-species column
  order, the altitude datum/sign convention).
- **Point and area PM column convention** is assumed, not verified
  (see "Emission factor columns" above): no bundled study has a
  non-zero PM2.5 factor for those source types.
- **Hourly periods only.** The standalone works in hourly periods that start
  on the hour; a movement takes the meteo row nearest to the start of its
  hour. The plugin uses the study's time interval, so the two agree for
  studies with hourly periods only.
- **Tracks are not followed.** The plugin lays a movement with a `track_id`
  along its track (`shapes_tracks`): the trajectory points follow the track,
  which changes the segment lengths and so the emissions (on the training
  study, an A20N departure along a turning track gets 4.32 kg NOx instead of
  4.18 kg with `bymode`). The standalone ignores `track_id` and `shapes_tracks`
  and always uses the profile along the runway axis, so results differ for
  movements with a track. ADS-B (CUSTOM) profiles are not tracks and are
  followed by both.
- **Engine tests in the `austal` pipeline** are computed with the ICAO
  mode values ("snap"): `compute_engine_test_emissions` passes no database
  connection, so BFFM2 events fall back to snap there.
- **Shared-import refactor of the stationary half.** The stationary
  computes still read pre-computed EFs rather than calling shared
  COPERT5 logic; see "Why the stationary half is structured this
  way".

## Testing

```bash
PYTHONPATH=. pytest openalaqs_standalone/validation/tests/ -q
```

A few more standalone tests live in the plugin suite under `tests/`; run
the two suites separately (see
[VALIDATION_GUIDE.md](../documents/validation/VALIDATION_GUIDE.md#running-the-automated-tests)).
Together they cover, among other things:

- source extraction: engine-test sites emitted as their own source type
  (`test_phase1b_extract_sources_standalone.py`) and missing `shapes_*`
  tables skipped (`tests/test_extract_sources_missing_tables.py`)
- the plugin-output gate: the CAEP14 reference and the standalone
  reproduce the pinned plugin CSVs (`validation/data/plugin_output/`)
  for all 15 movements and the three methods, within 2e-4 relative
  (`test_plugin_csv_vs_reference.py`; the measured agreement is in
  [Tolerances](../documents/validation/VALIDATION_GUIDE.md#tolerances))
- the CAEP14 reference itself (`test_caep14_bffm2_reference_case.py`,
  `test_caep14_reference_lookups.py`, `test_helicopter_caep14_reference.py`)
- engine-start emissions and `gate_emissions_code` (`test_start_gate_code.py`;
  plugin parity in `tests/test_zz_gate_code_start_parity.py`)
- engine-test event extraction and emissions, all three thrust modes
  (`test_phase3_engine_test_standalone.py`)
- single-engine taxi (`taxi_engine_count`, main engine start/off times,
  `taxi_fuel_ratio`) and its split over the route segments
  (`test_single_engine_taxi_split.py`; plugin parity of the movement totals
  and of each taxi segment in `tests/test_zz_single_engine_taxi_parity.py`)
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

### Validation harness

`openalaqs_standalone/validation/` is the CAEP14 reference harness. It is
kept up to date with the standalone's calculation paths and is the
canonical test for any change to the emission code; extend it whenever you
add a new emission path or a new validation target. Three subdirectories:

- `validation/data/`: bundled fixtures. Three derived variants of the
  training study (`training_v3.alaqs`, `training_v3_gatemovements.alaqs`,
  `training_v3_multisource.alaqs`) plus the plugin's own outputs on
  `training_v3.alaqs` for the four comparison targets (bymode,
  bymode-with-NOx-correction, bffm2_anchor, bffm2_traj) and the stationary
  sources in `validation/data/plugin_output/`, and
  `training_validation_reference.xlsx`, plugin beside the CAEP14 reference
  per movement. The `training_v3*` files
  are evolved versions of `example/training/training.alaqs` carrying
  schema fixes and source variants that exercise the gate / multi-source
  code paths. `validation/data/source_csvs/` holds their text inputs:
  `training_movements.csv` is the movement table of `training_v3.alaqs`
  (and of `training_v3_multisource.alaqs`), 15 movements with the two AS50
  helicopters, in the plugin's import format; `training_v3_gatemovements.alaqs`
  differs from it in the gate and `gate_emissions_code` of movements 1, 2,
  3, 5 and 14. It is not the example's `training_movements.csv` (13
  movements, other runways and gates on some rows). `training_meteo.csv`
  and `training_ads_b_data.csv` are the example's files. The only code
  that reads this folder is the test
  `validation/tests/test_source_csvs_match_fixture.py`, which checks that
  `training_movements.csv` equals the movement table of `training_v3.alaqs`.
- `validation/tests/`: pytest modules, among them
  `test_plugin_csv_vs_reference.py` (plugin = reference = standalone on the
  15 movements), `test_bffm2_ambient_propagation_regression.py` (BFFM2 EI
  with pinned ambient inputs), `test_runway_placement.py` and
  `test_segment_mach.py`.
- `validation/tools/`: the CAEP14 reference and its helper scripts,
  described in [CAEP14_VALIDATION.md](validation/tools/CAEP14_VALIDATION.md#files)
  (how to run the reference, regenerate the pinned outputs and the
  workbooks).

See also:

- [USAGE.md](USAGE.md): install, commands and options
- [CAEP14_VALIDATION.md](validation/tools/CAEP14_VALIDATION.md): the CAEP14 reference implementation
- [VALIDATION_GUIDE.md](../documents/validation/VALIDATION_GUIDE.md): validating a build
- [WITHOUT_QGIS.md](../documents/user/WITHOUT_QGIS.md): which tool to run without the QGIS GUI
