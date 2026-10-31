# CAEP14 reference validation

This page describes the CAEP14 reference implementation of the
OpenALAQS aircraft emission calculations in this directory: what it
implements, how it is run, and how it and the pinned plugin outputs are
updated. It is for maintainers. What to run to validate a build, and how to
judge the result, is in
[VALIDATION_GUIDE.md](../../../documents/validation/VALIDATION_GUIDE.md);
the measured agreement is in its
[Tolerances](../../../documents/validation/VALIDATION_GUIDE.md#tolerances)
section.

The reference covers the three calculation methods (`bymode`,
`bffm2_anchor`, `bffm2_traj`), fixed-wing aircraft and helicopters. The
training study is the canonical fixture: its inventory
`validation/data/training_v3.alaqs` (15 movements, two helicopters
included) for the pinned outputs, and `example/training/training_out.alaqs`
(13 movements) for the user-facing workbook; the scripts work against any
OpenALAQS inventory (`_out.alaqs`) database.

Contents:

- [Files](#files)
- [Running the reference](#running-the-reference)
- [Updating the reference and the pinned outputs](#updating-the-reference-and-the-pinned-outputs)
- [Methods covered by the reference](#methods-covered-by-the-reference)
- [Ambient conditions: ISA vs tbl_InvMeteo](#ambient-conditions-isa-vs-tbl_invmeteo)
- [Movement 11 (PHBBA, CUSTOM track)](#movement-11-phbba-custom-track)
- [Reference vs plugin: data flow](#reference-vs-plugin-data-flow)
- [What the CAEP/14 reference cases cover](#what-the-caep14-reference-cases-cover)
- [Use on other studies](#use-on-other-studies)

## Files

| File | Purpose |
| --- | --- |
| `compute_caep14_reference.py` | The reference implementation.  Produces per-movement CO, CO₂, HC, NOₓ, SOₓ, PM₁₀ totals for one method and either prints a table or compares against a plugin CSV. Flags: `--method` (`bymode`, `bffm2_anchor`, `bffm2_traj`; default `bymode`), `--use-meteo` (study meteo instead of ISA), `--plugin-csv`, `--oid` (one movement), `--apply-nox-corrections` (bymode: ICCAIA NOx correction on take-off and climb-out), `--atmosphere-model` (`surface_layer`, `standard_lapse`, `ground_held`; default `standard_lapse`), `--z0`, `--d0`, `--ha` (site parameters in m for `surface_layer`; empty gives 0.1, 6 z0, 10 m + d0), `--verbose-diag`. |
| `regenerate_plugin_csvs.py` | Runs the plugin's calculation service headlessly (QGIS bindings, no GUI) on the fixture, all source types, for the three methods and for bymode with the NOx correction, and writes the pinned CSVs (`training_movements_*.csv`, `training_sources_bymode.csv`). |
| `regenerate_training_validation_xlsx.py` | Reads the pinned plugin CSVs and runs the reference for the three methods and the NOx-correction run, then writes `data/training_validation_reference.xlsx`: plugin beside reference per movement, hourly plugin emissions of movements and stationary sources, the helicopter parameters. |
| `compare_inventory_to_reference.py` | Diffs an exported per-movement CSV (QGIS Table View, or the pinned files) against the reference column of the workbook for one method; the installation check of V1 in `documents/validation/VALIDATION_GUIDE.md`. Usage: `compare_inventory_to_reference.py <csv> --method=bymode [<workbook.xlsx>]` (default workbook `example/training/training_validation_reference.xlsx`). The method is accepted only in the `--method=bymode` form; `--method bymode` (with a space) is read as a file path. |
| `../tests/test_bffm2_ambient_propagation_regression.py` | Pure-Python pytest module that pins the BFFM2 ambient-correction behaviour (ISA, cold-dry, warm-humid, per-segment Mach) so a future change in `core/tools/bffm2.py` will surface immediately. |

The reference is dependency-light: it requires `numpy`, `shapely`,
`pyproj` and `openpyxl` (the last only for the xlsx-regen script).  It
does not import QGIS and runs in any standard Python 3.12 environment.

## Running the reference

From the repository root, against the pinned plugin CSVs:

```bash
PYTHONPATH=. python3 openalaqs_standalone/validation/tools/compute_caep14_reference.py \
    openalaqs_standalone/validation/data/training_v3.alaqs --method=bymode \
    --plugin-csv=openalaqs_standalone/validation/data/plugin_output/training_movements_bymode.csv

PYTHONPATH=. python3 openalaqs_standalone/validation/tools/compute_caep14_reference.py \
    openalaqs_standalone/validation/data/training_v3.alaqs --method=bffm2_anchor --use-meteo \
    --plugin-csv=openalaqs_standalone/validation/data/plugin_output/training_movements_bffm2_anchor.csv

PYTHONPATH=. python3 openalaqs_standalone/validation/tools/compute_caep14_reference.py \
    openalaqs_standalone/validation/data/training_v3.alaqs --method=bffm2_traj --use-meteo \
    --plugin-csv=openalaqs_standalone/validation/data/plugin_output/training_movements_bffm2_traj.csv
```

`--use-meteo` because the plugin applies `tbl_InvMeteo` (see
[Ambient conditions](#ambient-conditions-isa-vs-tbl_invmeteo)); `bymode`
without the NOx correction has no ambient correction.

Each invocation prints a per-movement table with CO, CO₂, NOₓ and
PM₁₀ from both reference (`_ref`) and plugin (`_plg`) plus a Δ%
column. For this version every movement of `training_v3.alaqs`, movement 11
(PHBBA, CUSTOM) included, shows 0.00 % for all three methods; the measured
differences are in
[Tolerances](../../../documents/validation/VALIDATION_GUIDE.md#current-agreement).
`tests/test_plugin_csv_vs_reference.py` pins this (plugin against reference
and standalone, 15 movements, the three methods and `bymode` with the NOx
correction). Any plugin-vs-reference delta
larger than these is a regression and should be investigated before
release.

## Updating the reference and the pinned outputs

The files in `data/plugin_output/` are written by
`tools/regenerate_plugin_csvs.py`, which runs the plugin's
`EmissionCalculatorService` (the code path of the QGIS dialog) without a
display: the three methods, `bymode` with the ICCAIA NOx correction
(`training_movements_bymode_nox_corr.csv`) and the stationary-source rows
(`training_sources_bymode.csv`), all with the study meteo. The workbook
`data/training_validation_reference.xlsx` is rebuilt from them.

### Re-export the pinned plugin CSVs

Headless (the pinned files were made this way, with the QGIS Python
bindings and no display):

```bash
QT_QPA_PLATFORM=offscreen python3.12 \
    openalaqs_standalone/validation/tools/regenerate_plugin_csvs.py
```

Or in QGIS: run *Visualize Emission Calculation* on
`openalaqs_standalone/validation/data/training_v3.alaqs` with each of the
three calculation methods and once with `bymode` and *Apply NOx
Corrections* on, and export the per-movement emissions to CSV as in V1 of
[VALIDATION_GUIDE.md](../../../documents/validation/VALIDATION_GUIDE.md#v1---plugin-vs-reference-workbook-training-example).
Save them as `training_movements_bymode.csv`,
`training_movements_bffm2_anchor.csv`, `training_movements_bffm2_traj.csv`
and `training_movements_bymode_nox_corr.csv` (the file names the regen
script expects by default). Only `source_name` and the `*_kg` columns are
read; rows of one movement are summed.

On `training_v3.alaqs` the plugin runs with the inventory grid of the file,
50 × 50 × 20 cells of 250 × 250 × 50 m, mixing height 914.4 m
(3000 ft), apply-NOₓ-corrections off (on for the `_nox_corr` file), and the
bffm2_ff_source set to `trajectory` (the CAEP/14 default).

### Regenerate the validation workbooks

```bash
PYTHONPATH=. python3 openalaqs_standalone/validation/tools/regenerate_training_validation_xlsx.py
```

Reads the pinned plugin CSVs, runs the reference with the study meteo, and
writes `data/training_validation_reference.xlsx` (sheets README, Summary,
Movement, NOx_correction, Movement_Hourly, the four stationary-source
sheets, Helicopter). The user-facing copy
`example/training/training_validation_reference.xlsx` is made the same way
from `example/training/training_out.alaqs` (13 movements, no helicopters).
That inventory is itself rebuilt from `training.alaqs` and the example's
CSVs (movements, meteo, ADS-B) with the settings of
`documents/user/TUTORIAL_ROTTERDAM.md`:

```bash
QT_QPA_PLATFORM=offscreen python3.12 tools/test_fixtures/rebuild_training_example_inventory.py
QT_QPA_PLATFORM=offscreen python3.12 openalaqs_standalone/validation/tools/regenerate_plugin_csvs.py \
    --fixture example/training/training_out.alaqs --out-dir /tmp/ex
PYTHONPATH=. python3 openalaqs_standalone/validation/tools/regenerate_training_validation_xlsx.py \
    --fixture example/training/training_out.alaqs --plugin-dir /tmp/ex \
    --out example/training/training_validation_reference.xlsx
```

The agreement of plugin and reference on that inventory is listed in
[Tolerances](../../../documents/validation/VALIDATION_GUIDE.md#current-agreement);
this check is not part of the test suite.

### Run the regression test

```bash
PYTHONPATH=. pytest openalaqs_standalone/validation/tests/test_bffm2_ambient_propagation_regression.py -v
```

Five tests must pass. These pin the BFFM2 module's ambient-condition
plumbing against ISA / cold-dry / warm-humid / per-segment-Mach inputs
and against the exact dict shape that `Engine.getEmissionIndexByFuelFlow`
builds from `method["config"]["ambient_conditions"]`.

### When a plugin change shifts the reference

If a future plugin change is intentional and shifts the reference
output (e.g. a new CAEP edition, a different installation correction
default, a fix in `twin_quadratic_fit_method.py`), the workflow is:

1. Make the same change in `compute_caep14_reference.py` (and add a
   short comment pointing at the plugin commit hash that motivated it).
2. When the plugin result itself changes, re-export the pinned plugin
   CSVs first ([Re-export the pinned plugin CSVs](#re-export-the-pinned-plugin-csvs)).
   Then re-run the three invocations of
   [Running the reference](#running-the-reference) and confirm that 15 of
   15 movements still match to 0.00 %; `tests/test_plugin_csv_vs_reference.py`
   checks this.
3. [Regenerate the validation workbooks](#regenerate-the-validation-workbooks).
4. Update the pinned values in
   `tests/test_bffm2_ambient_propagation_regression.py` if BFFM2
   itself was the change; otherwise the test should keep passing
   unchanged.
5. Add a one-line entry to `CHANGELOG.md` recording the validation
   result.

## Methods covered by the reference

### `bymode`

CAEP14 LTO-mode look-up: per-segment fuel flow is the EEDB anchor for
the segment's mode label (TX/AP/CL/TO) and the EI is taken directly
from the engine's EEDB row.  Identical to the plugin's `bymode` path
once both apply identical grid-clipping, vertical clipping at
914.4 m + 1 µm tolerance, and identical brake-wear PM₁₀ for arrivals
above 18 632 kg MTOW.

### `bffm2_anchor`

Fuel flow stays at the mode anchor as in `bymode`; the EI for NOₓ /
CO / HC is replaced by the BFFM2-ambient EI computed at the anchor
fuel flow with the segment's ambient conditions.  Per-segment Mach
is the flight Mach, start-point TAS over the speed of sound at the ambient
temperature.  PM₁₀ and SOₓ stay at the table EI.

The speed of sound is a = √(γ R T) with γ = 1.4 and R = 287.05287 J/(kg K)
(ICAO Doc 7488), as in the CAEP/14 BFFM2 formulation. The plugin and the
standalone share `open_alaqs/core/tools/bffm2.py::speed_of_sound_m_s`; the
reference writes the formula out. `test_segment_mach.py` reproduces the
two Mach values of the CAEP/14 reference cases to 10⁻⁹ (with their rounded
1.94384 kt per m/s).

### `bffm2_traj`

Per-segment fuel flow is resolved either from `fuel_flow_kgm` (CUSTOM
/ ADS-B profiles, divided by `engine_count`; above
`ADSB_FF_CEILING_FACTOR` = 1.5 × the TO anchor fuel flow the segment
falls back to the anchor fuel flow of its mode, as in the plugin) or from the segment's `power` setting via the
piecewise three-point quadratic fit from
`core/tools/twin_quadratic_fit_method.py`, then scaled to ambient fuel
flow with the corrected-parameter scaling of gas-turbine performance (the
corrected fuel flow, fuel flow / (δ √θ), is a function of the corrected
thrust, thrust / δ, and Mach):

```
Wf_amb = Wf_ref * δ * sqrt(θ)
```

δ and θ (and the Mach number and the BFFM2 ambient corrections) are those at
the segment's start height, from the period's meteo row with the atmosphere
model of the plugin (`--atmosphere-model`, default `standard_lapse`: the
row's 2 m temperature and station pressure, from QNH, carried up with the ISA
lapse rate; `surface_layer`: AUSTAL's boundary-layer temperature profile;
`ground_held`: the hourly row at every height, the ambient conditions of
5.4.0, not its fuel-flow scaling). The reference, the standalone and the
plugin share `open_alaqs/core/tools/surface_layer_atmosphere.py`; the
`surface_layer` formulas are checked against AUSTAL's C code in
`tests/test_surface_layer_atmosphere.py`. The pinned outputs use the default
`standard_lapse`. The shared site defaults are z0 0.1 m, d0 0.6 m,
ha 10.6 m, used by `surface_layer` only.

BFFM2 (SAE AIR5715) converts a known fuel flow to reference conditions for
the emission-index lookup; it is not a fuel-flow model, and its inverse,
`Wf_ref * δ / θ^3.8 / exp(0.2 M^2)`, is not used to scale the fuel flow to
ambient (it lowers the fuel flow with rising temperature, −12 % at 25 °C,
where the corrected-parameter scaling gives +1.7 %). The CAEP/14 reference
cases take the fuel flow as an input and do not test this step.

EI for NOₓ / CO / HC is then the BFFM2-ambient EI at that ambient
fuel flow.  PM₁₀ and SOₓ remain at the table EI.

Only a positive `fuel_flow_kgm` is a fuel flow; zero or negative is taken
as missing. A power between 1.0 and 1.05 is taken as 1.0. A segment without
a positive fuel flow whose power is missing, above 1.05 or below 0 (piston
and propeller profiles, whose `power` column is not a thrust fraction) takes
the bymode index of its mode (EEDB fuel flow, unscaled), as in the plugin.

The reference's `_twin_quadratic_ff_from_power` reimplements the
plugin's piecewise three-point quadratic (parabola through 0.07 / 0.30
/ 0.85 below 85 % thrust, through 0.30 / 0.85 / 1.00 above) bit-for-bit.
A least-squares fit through the four points instead gives NOₓ deltas of
about 0.7 % on E190 arrivals.

### Taxi (BFFM2 methods)

With `bffm2_anchor` and `bffm2_traj` the taxi reference fuel flow is the
twin-quadratic fit at the movement's `engine_thrust_level_for_taxiing`
(0.07 when it is not given, so the EEDB idle fuel flow; 0 is floored at
idle), scaled to ambient, `ff_ref · δ · √θ` (Mach 0), and that ambient
fuel flow is used for both the taxi fuel mass and the BFFM2 EI lookup: in
the plugin (`TaxiingEmissionCalculator` calls
`Engine.getEmissionIndexByEngineState(power_setting, method=BFFM2)` without
a `fuel_flow` argument, which takes the power-setting branch), in the
standalone (`compute_aircraft.compute_fixed_wing`) and in the reference
(`compute_caep14_reference._compute_fixed_wing`). A thrust the fit rejects
(above 1.05 or below 0, e.g. 7 typed for 7 %) gives the bymode TX index
(EEDB TX fuel flow, unscaled, and TX indices), with an error in the log.

### Vertical limit

The vertical clip uses the mixing height of the movement's period, from the
meteo row nearest to the period start; the reference (`_mixing_height_at`),
the standalone (`movements.get_mixing_height_at()`) and the plugin use the
same row and the same 914.4 m when there is no mixing height
([LTO ceiling](../../../documents/methods/AIRCRAFT_EMISSIONS.md#lto-ceiling-and-segment-clipping)). A segment with one endpoint below and one above the
limit is cut where it meets the limit (altitude linear along the segment),
so only the part below the limit counts. On the training fixture at 914.4 m
every crossing segment lies outside the 50 × 50 grid. Tests:
`tests/test_height_limit_crossing_segment.py` (plugin) and
`validation/tests/test_crossing_segment_standalone.py` (standalone =
reference, also at a 300 m limit; analytic crossing distance).

### NOx ambient correction (`bymode`)

The ICCAIA NOx ambient correction (*Apply NOx Corrections*) applies to the
take-off and climb-out segments only, the modes the simple method is
defined for: in the plugin (`NOX_CORRECTION_MODES` in
`MovementEmissionCalculator`), the standalone and the reference
(`--apply-nox-corrections`, `_nox_ambient_factor`, written out from
Doc 9889 with the pressure in hPa). It reads the study's airport elevation
as the airport altitude (−5 m on the fixture). Plugin = reference =
standalone on 15 of 15 movements (`test_plugin_csv_vs_reference.py`).

### MEEM V1 above 3000 ft

Above 3000 ft above the aerodrome the reference's `_meem_v1_mass_mgkg` runs
the MEEM V1 ISA + ΔT atmosphere, with ΔT as
defined in
[MEEM V1](../../../documents/methods/AIRCRAFT_EMISSIONS.md#meem-v1-nvpm-above-3000-ft)
(`_meem_delta_t`); the plugin (`Engine.getEmissionIndexByModeWithMEEM`,
`delta_t`) and the standalone (`compute_aircraft._meem_v1_segment_ei`) do
the same with `meem_v1.delta_t_from_ground`. That is the `ground_held`
case; with `standard_lapse` or `surface_layer` all three pass the segment's
local T and p instead (the reference through its `ambient` argument). For `bymode` the reference and
the standalone read the meteo row when the engine has MEEM inputs.
`validation/tests/test_meem_v1_reference.py` checks both against two
MEEM V1 reference cases (11GE144, ΔT −5.1825 K and +12 K).
`training_v3` has no segment above 3000 ft (mixing height 914.4 m); the
example inventory `training_out.alaqs` has (1500 m mixing height on
2 December). The engine table carries `press_ratio` and the 5th nvPM point
from ICAO EEDB v31 (ACT_PRF for engines not in
it), and `nvpm_number_ei` in #/kg; the reference reads `press_ratio` and the
5th mass point.

### Helicopters (oid 14, 15)

FOCA 2015 Appendix A is used identically for all three methods (FOCA
does not go through BFFM2).  The reference re-uses the plugin's own
`core/tools/foca_heli.py` / `foca_heli_utils.py` modules to guarantee
that any future change to the FOCA implementation is picked up by the
validation without separate maintenance. The active mode (TO
or AP) is scaled by the share of its time below the period's mixing height
and inside the grid on the FOCA flight path (origin at the gate centroid,
else the runway threshold; departure outbound along the runway, arrival
back along the approach). The reference builds that path and the cut on
its own from the parameters in `core/tools/foca_heli_trajectory.py`
(`_heli_flight_path_local`, `_heli_active_fraction`);
`tests/test_helicopter_caep14_reference.py` checks it against the
standalone at 914.4, 600, 300 and 100 m, with and without a helipad gate.
The arrival (movement 15) starts its approach outside the 50 × 50 grid, so
the cut matters there. The reference equals the plugin on the fixture at
914.4 m without gates and at 300 m with gate G4 as helipad (0.00 % on 15 of
15 for `bymode`), and the standalone at 914.4, 600, 300 and 100 m with and
without a gate (see
[Tolerances](../../../documents/validation/VALIDATION_GUIDE.md#current-agreement)).

## Ambient conditions: ISA vs `tbl_InvMeteo`

The reference defaults to ISA conditions (T = 288.15 K, P = 101 325 Pa,
RH = 0.6) for the BFFM2 ambient correction. The plugin applies the study
meteo, so pass `--use-meteo` to read the meteo row at each movement's
`runway_time` from `tbl_InvMeteo` (the pinned exports need it):

```bash
PYTHONPATH=. python3 openalaqs_standalone/validation/tools/compute_caep14_reference.py \
    openalaqs_standalone/validation/data/training_v3.alaqs \
    --method=bffm2_anchor \
    --use-meteo
```

Run at ISA, the BFFM2 methods and the NOx-corrected run move off the pinned
files; the size of the difference is in
[Effect of the meteo setting](../../../documents/validation/VALIDATION_GUIDE.md#effect-of-the-meteo-setting).

Two fallback paths in the plugin make BFFM2 revert to ISA; both log a
`WARNING`:

1. `EmissionCalculation.__init__` when `tbl_InvMeteo` is empty:
   `_sorted_ac_times = []` makes `getAmbientCondition()` return
   `AmbientCondition()` (ISA defaults) for every time slice.
2. `Engine.getEmissionIndexByFuelFlow` when the ambient extraction
   raises an exception: the surrounding `except Exception` substitutes
   ISA.

If a future plugin run produces output that disagrees with the
`--use-meteo` reference but agrees with the default reference, search
the QGIS log for these warnings to identify whether the meteo store is
empty, the extraction failed for a specific row, or the data is
otherwise unavailable.

## Movement 11 (PHBBA, CUSTOM track)

Movement 11 (A20N CUSTOM departure on runway 24, gate G2) flies the ADS-B
track `1764584438_PHBBA` from `data/source_csvs/training_ads_b_data.csv`.
The fixture's PHBBA and PHRTM rows are imported with the current importer
(tier 1: reference point from the movement's runway and taxi route):
heights above the airport elevation (−5 m) and the take-off roll at
height 0 with mode TO. The track stays below the 914.4 m cut. PHRTM is not
used by any movement.

The `fuel_flow` column of the track is 2 × the ICAO fuel flow of 01P20CM128
(the A20N engine of movement 11) interpolated linearly on its four (thrust,
fuel flow) points at the row's `power_setting`, rounded to 4 decimals:
0.65 to 1.57 kg/s for PHBBA (PHRTM gets the same curve, with its power
below idle raised to 0.07). The tracks are an example, not measured fuel
flows. Only `bffm2_traj` uses the supplied fuel flow; the values stay below
1.5 × the take-off fuel flow per engine (0.78 against 1.29 kg/s), so no
point falls back to the mode anchor.

## Reference vs plugin: data flow

```
   training_v3.alaqs / <study>_out.alaqs (sqlite inventory)
          │
          │  read engine EI, trajectories, taxi route, meteo
          ▼
   compute_caep14_reference.py
          │
          ├── grid clip in EPSG:3857 (grid_3d_definition; 50×50 cells of 250 m on training_v3)
          ├── vertical clip at 914.4 m ±1 µm
          ├── runway alignment via pyproj.Geod
          ├── ANP arrivals: landing threshold + Touchdown Offset, rollout cut at the route exit
          ├── ANP departures: brake release at the line-up point
          ├── CUSTOM tracks: runway/taxi intersection via Shapely buffer(1 m)
          ├── per-segment fuel/time/EI per method
          ├── brake-wear PM10 for arrivals > 18 632 kg MTOW
          ├── FOCA Appendix A for helicopters
          └── BFFM2 EI via core/tools/bffm2.py (NOx/CO/HC)
          │
          ▼
   per-movement totals  vs  plugin CSV totals  → Δ%
```

Every spatial primitive in the reference is verified against the
plugin's own implementation to sub-millimetre precision (runway
alignment to 0.08 m, intersection point to 0.0000 m, grid bounds to
0.0004 m at x_max).  See the file-level docstrings in
`compute_caep14_reference.py` for line-by-line traceability to the
plugin sources it mirrors.

## What the CAEP/14 reference cases cover

The CAEP/14 BFFM2 reference cases take the engine fuel flow as an input and
give the BFFM2 reference fuel flow and the ambient emission indices; their
results are reproduced in the tests. Note on
independence: the reference implementation writes out the geometry, the
fuel-flow step, the taxi, the NOx correction and the helicopter cut on its
own, but imports the plugin's BFFM2 index function
(`open_alaqs.core.tools.bffm2.calculate_emission_index`) and the FOCA
helicopter tables (`foca_heli`, `foca_heli_utils`). Those two parts are what
the CAEP/14 reference cases and the FOCA Appendix A values check, not the
plugin-vs-reference comparison.
It has no view on how a fuel flow is derived from a thrust: that step is
validated against the reference implementation, as the rest of the method;
the index step is pinned to the CAEP/14 reference cases.

- `tests/test_caep14_bffm2_reference_case.py`: BFFM2 index step against
  two CAEP/14 reference cases for engine 01P20CM127 (LEAP-1A24) at
  fuel flow 1.1749 kg/s. The worked case, climb to cruise at 22 500 ft
  (non-LTO, lean burn: v2 indices, exponent 0.3): reference fuel flow
  1.657227 kg/s, EI NOx 60.20166, CO 0.459531, HC 0.0282788 g/kg. The LTO
  path (standard indices, exponent 0.5), the same engine and fuel flow
  at altitude 1 000 ft, CLIMB OUT, 180 kt:
  reference fuel flow 1.204590 kg/s, EI NOx 17.65248, CO 0.329654,
  HC 0.0202864 g/kg. The code matches CO and HC to 1e-14 and NOx to 2e-6
  from RH (the humidity ratio formula), exactly with the reference cases'
  humidity ratio.

## Use on other studies

The reference matches engines on `engine_name` exactly (or
`engine_full_name` for rows without an `engine_name`), the key of the
plugin and the standalone, and treats a movement as a helicopter when its
aircraft type is listed in `default_helicopter`, as the plugin and the
standalone do (a study may give its helicopters a profile, `HELIPROF-*`).
On an operational study of 159 movements and 33 engines (jets, turboprops,
pistons, EC35 helicopters, 77 CUSTOM profiles; study meteo) it equals the
standalone net of the gate emissions (APU, GSE, engine start, which the
reference does not model) to floating-point noise, with one ANP departure
of `bffm2_traj` as the exception; the figures are in
[Tolerances](../../../documents/validation/VALIDATION_GUIDE.md#current-agreement).
This check is not part of the test suite.

See also:

- [VALIDATION_GUIDE.md](../../../documents/validation/VALIDATION_GUIDE.md): what to run to validate a build, and the tolerances
- [AIRCRAFT_EMISSIONS.md](../../../documents/methods/AIRCRAFT_EMISSIONS.md): the aircraft emission methods
- [HELICOPTERS.md](../../../documents/methods/HELICOPTERS.md): the FOCA 2015 helicopter method
- [openalaqs_standalone README](../../README.md#testing): the standalone's tests
