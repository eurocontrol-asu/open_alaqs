# CAEP14 Reference Validation for OpenALAQS

This directory contains a self-contained CAEP14 v14 reference implementation
of OpenALAQS emission calculations.  The reference is used to validate
plugin output across all three calculation methods (`bymode`,
`bffm2_anchor`, `bffm2_traj`) and across fixed-wing and helicopter
aircraft.  The training dataset (`example/training/training.alaqs`) is
the canonical fixture, but the scripts work against any OpenALAQS
study database.

The reference was first developed and pinned against OpenALAQS 5.2.0 in
May 2026. The pinned plugin outputs in `data/plugin_output/` were
re-exported in October 2026 from the plugin of this version, headlessly
(`tools/regenerate_plugin_csvs.py`): all 15 movements of
`training_v3.alaqs`, the two helicopters included, agree between the
plugin, the reference and the standalone for the three methods to
floating-point noise, except the CUSTOM departure (movement 11, PHBBA) at
1e-4. The plugin applies the study meteo (`tbl_InvMeteo`) to the BFFM2
ambient corrections, so the comparison is run with `--use-meteo`; the
5.2.0 exports were made at ISA. See "October 2026" at the end.

---

## Files

| File | Purpose |
| --- | --- |
| `compute_caep14_reference.py` | The reference implementation.  Produces per-movement CO, CO₂, HC, NOₓ, SOₓ, PM₁₀ totals for one method and either prints a table or compares against a plugin CSV. |
| `regenerate_plugin_csvs.py` | Runs the plugin's calculation service headlessly (QGIS bindings, no GUI) on the fixture, all source types, for the three methods and for bymode with the NOx correction, and writes the pinned CSVs (`training_movements_*.csv`, `training_sources_bymode.csv`). |
| `regenerate_training_validation_xlsx.py` | Reads the pinned plugin CSVs and runs the reference for the three methods and the NOx-correction run, then writes `data/training_validation_reference.xlsx`: plugin beside reference per movement, hourly plugin emissions of movements and stationary sources, the helicopter parameters. |
| `compare_inventory_to_reference.py` | Diffs an exported per-movement CSV (QGIS Table View, or the pinned files) against the reference column of the workbook for one method; the installation check of `documents/VALIDATION_GUIDE.md`. |
| `../tests/test_bffm2_ambient_propagation_regression.py` | Pure-Python pytest module that pins the BFFM2 ambient-correction behaviour (ISA, cold-dry, warm-humid, per-segment Mach) so a future change in `core/tools/bffm2.py` will surface immediately. |

The reference is dependency-light: it requires `numpy`, `shapely`,
`pyproj` and `openpyxl` (the last only for the xlsx-regen script).  It
does not import QGIS and runs in any standard Python 3.12 environment.

---

## Workflow for validating a new plugin build

### 1. Run the plugin against the training fixture

Headless (the pinned files were made this way, with the QGIS Python
bindings and no display):

```bash
QT_QPA_PLATFORM=offscreen python3.12 \
    openalaqs_standalone/validation/tools/regenerate_plugin_csvs.py
```

Or in QGIS: open `example/training/training.alaqs`, run an inventory with
each of the three calculation methods, and export the per-movement
emissions to CSV via the standard Output Module.  Save them as
`training_movements_bymode.csv`, `training_movements_bffm2_anchor.csv`
and `training_movements_bffm2_traj.csv` (the file names the regen
script expects by default). Only `source_name` and the `*_kg` columns
are read; rows of one movement are summed.

For each method the plugin must run with the inventory grid set to
50 × 50 × 20 cells of 250 × 250 × 50 m, mixing height 914.4 m
(3000 ft), apply-NOₓ-corrections off, and the bffm2_ff_source set to
`trajectory` (the CAEP14 v14 default).

### 2. Run the reference for each method

```bash
cd tools/
python3 compute_caep14_reference.py /path/to/training.alaqs \
    --method=bymode \
    --plugin-csv=/path/to/training_movements_bymode.csv

python3 compute_caep14_reference.py /path/to/training.alaqs \
    --method=bffm2_anchor --use-meteo \
    --plugin-csv=/path/to/training_movements_bffm2_anchor.csv

python3 compute_caep14_reference.py /path/to/training.alaqs \
    --method=bffm2_traj --use-meteo \
    --plugin-csv=/path/to/training_movements_bffm2_traj.csv
```

(`--use-meteo` because the plugin applies `tbl_InvMeteo`; at ISA the
BFFM2 methods differ from the plugin by 5 to 25 % on the fixture's cold
and warm days. `bymode` has no ambient correction.)

Each invocation prints a per-movement table with CO, CO₂, NOₓ and
PM₁₀ from both reference (`_ref`) and plugin (`_plg`) plus a Δ%
column.  The expected outcome for this version against `training_v3.alaqs`
(October 2026 export):

| method | 14 of 15 movements | movement 11 (PHBBA, CUSTOM) |
| --- | --- | --- |
| `bymode` | 0.00 % on all pollutants | 0.00 % |
| `bffm2_anchor` (`--use-meteo`) | 0.00 % | 0.00 % |
| `bffm2_traj` (`--use-meteo`) | 0.00 % | +0.01 % |

`tests/test_plugin_csv_vs_reference.py` pins this (2e-4 relative, plugin
against reference and standalone, 15 movements, three methods). For
OpenALAQS 5.2.0 the 5.2.0 exports gave 0.00 % on 14 movements at ISA and
+0.07 / +0.87 % (bymode, anchor) or +0.26 % (trajectory) on movement 11.

Any plugin-vs-reference delta larger than these is a regression and
should be investigated before release.

### 3. Regenerate the validation workbook

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
`documents/TEST_CASE_STUDY.md`:

```bash
QT_QPA_PLATFORM=offscreen python3.12 tools/test_fixtures/rebuild_training_example_inventory.py
QT_QPA_PLATFORM=offscreen python3.12 openalaqs_standalone/validation/tools/regenerate_plugin_csvs.py \
    --fixture example/training/training_out.alaqs --out-dir /tmp/ex
PYTHONPATH=. python3 openalaqs_standalone/validation/tools/regenerate_training_validation_xlsx.py \
    --fixture example/training/training_out.alaqs --plugin-dir /tmp/ex \
    --out example/training/training_validation_reference.xlsx
```

On that inventory the plugin and the reference agree to 3e-10 on the ANP
movements and 4e-5 on movement 11 (CUSTOM), every method. (With the
200 m-tall grid the example carried before October 2026, 40 x 40 x 20
cells of 10 m, the ANP movements agreed to 4e-6 only; the gap went with
the grid.) `compare_inventory_to_reference.py <csv> --method=...`
then checks any exported per-movement CSV against the workbook's reference
column (0.5 % tolerance, exit code 0 when all movements pass).

### 4. Run the regression test

```bash
pytest tests/test_bffm2_ambient_propagation_regression.py -v
```

Five tests must pass.  These pin the BFFM2 module's ambient-condition
plumbing against ISA / cold-dry / warm-humid / per-segment-Mach inputs
and against the exact dict shape that `Engine.getEmissionIndexByFuelFlow`
builds from `method["config"]["ambient_conditions"]`.

---

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
is computed from start-point TAS and ambient temperature.  PM₁₀ and
SOₓ stay at the table EI.

### `bffm2_traj`

Per-segment fuel flow is resolved either from `fuel_flow_kgm` (CUSTOM
/ ADS-B profiles, divided by `engine_count` and clamped to the TO
anchor as a ceiling) or from the segment's `power` setting via the
piecewise three-point quadratic fit from
`core/tools/twin_quadratic_fit_method.py`, then converted to ambient
fuel flow via the inverse SAE AIR-5715 / CAEP14 correction:

```
Wf_amb = Wf_ref * δ / θ^3.8 / exp(0.2 * M^2)
```

EI for NOₓ / CO / HC is then the BFFM2-ambient EI at that ambient
fuel flow.  PM₁₀ and SOₓ remain at the table EI.

The reference's `_twin_quadratic_ff_from_power` reimplements the
plugin's piecewise three-point quadratic (parabola through 0.07 / 0.30
/ 0.85 below 85 % thrust, through 0.30 / 0.85 / 1.00 above) bit-for-bit;
a previous four-point `np.polyfit(deg=2)` formulation produced
~0.7 % NOₓ deltas on E190 arrivals that disappeared once the piecewise
form was adopted.

### Helicopters (oid 14, 15)

FOCA 2015 Appendix A is used identically for all three methods (FOCA
does not go through BFFM2).  The reference re-uses the plugin's own
`core/tools/foca_heli.py` / `foca_heli_utils.py` modules to guarantee
that any future change to the FOCA implementation is picked up by the
validation without separate maintenance. Since 5.3.2 the active mode (TO
or AP) is scaled by the share of its time below the period's mixing height
and inside the grid on the FOCA flight path (origin at the gate centroid,
else the runway threshold; departure outbound along the runway, arrival
back along the approach). The reference builds that path and the cut on
its own from the parameters in `core/tools/foca_heli_trajectory.py`
(`_heli_flight_path_local`, `_heli_active_fraction`);
`tests/test_helicopter_caep14_reference.py` checks it against the
standalone at 914.4, 600, 300 and 100 m, with and without a helipad gate.

---

## Ambient conditions: ISA vs `tbl_InvMeteo`

The reference defaults to ISA conditions (T = 288.15 K, P = 101 325 Pa,
RH = 0.6) for the BFFM2 ambient correction, which is what the 5.2.0
plugin's emission CSV output used. The plugin of 5.3.4 and later applies
the study meteo, so pass `--use-meteo` to read the meteo row at each
movement's `runway_time` from `tbl_InvMeteo` (the October 2026 exports
need it):

```bash
python3 compute_caep14_reference.py /path/to/training.alaqs \
    --method=bffm2_anchor \
    --use-meteo
```

Two silent-fallback paths in the plugin caused BFFM2 to revert to ISA
in earlier builds, both of which now log a `WARNING`:

1. `EmissionCalculation.__init__` when `tbl_InvMeteo` is empty —
   `_sorted_ac_times = []` makes `getAmbientCondition()` return
   `AmbientCondition()` (ISA defaults) for every time slice without
   any visible signal.
2. `Engine.getEmissionIndexByFuelFlow` when the ambient extraction
   raised an exception — the surrounding `except Exception` swallowed
   the cause and substituted ISA.

If a future plugin run produces output that disagrees with the
`--use-meteo` reference but agrees with the default reference, search
the QGIS log for these warnings to identify whether the meteo store is
empty, the extraction failed for a specific row, or the data is
otherwise unavailable.

---

## Mov 11 PHBBA track (re-imported October 2026)

Movement 11 (A20N CUSTOM departure on runway 24, gate G2) flies the ADS-B
track `1764584438_PHBBA` from `data/source_csvs/training_ads_b_data.csv`.
The fixture's PHBBA and PHRTM rows were re-imported in October 2026 with
the current importer (tier 1: reference point from the movement's runway
and taxi route): heights above the airport elevation (−5 m) and the
take-off roll at height 0 with mode TO. The horizontal positions equal
the earlier import to 1e-9 m, so the offset reported here before (81 m
on the ground) no longer exists. The emission totals of movement 11 do
not change with the re-import (the track stays below the 914.4 m cut);
the remaining plugin/reference gap on movement 11 (8e-5 on `bffm2_traj`)
is not explained yet.

---

## Reference vs plugin: data flow

```
   training.alaqs (sqlite)
          │
          │  read engine EI, trajectories, taxi route, meteo
          ▼
   compute_caep14_reference.py
          │
          ├── grid clip in EPSG:3857 (50×50 cells, 250 m)
          ├── vertical clip at 914.4 m ±1 µm
          ├── runway alignment via pyproj.Geod
          ├── runway/taxi intersection via Shapely buffer(1 m).intersection
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

---

## Updating the reference for a new plugin release

If a future plugin change is intentional and shifts the reference
output (e.g. a new CAEP edition, a different installation correction
default, a fix in `twin_quadratic_fit_method.py`), the workflow is:

1. Make the same change in `compute_caep14_reference.py` (and add a
   short comment pointing at the plugin commit hash that motivated it).
2. Re-run the three validation invocations from step 2 above and
   confirm that 14 of 15 movements still match to 0.00 %.
3. Regenerate the workbook via step 3 above.
4. Update the pinned values in
   `tests/test_bffm2_ambient_propagation_regression.py` if BFFM2
   itself was the change; otherwise the test should keep passing
   unchanged.
5. Add a one-line entry to `CHANGELOG.md` recording the validation
   result.

---

## May 2026 patch round

Two implementation gaps surfaced during a focused validation against the
EHRD CAEP14 training fixture (50×50 grid, 15 movements over 3 days, real
meteo per period).  Both have been fixed in the standalone and the
`compute_caep14_reference.py` reference; the plugin already had the
correct behaviour.

### Mixing height per period

Previously the standalone hard-coded `MAX_HEIGHT_M = 914.4` for the
vertical-clip pass.  The plugin's `MovementSourceModule.process()` reads
`tbl_InvMeteo.MixingHeight` per inventory period and passes it as
`max_height` into `apply_height_limits`.  Effect on the EHRD fixture:
on Day 2 (mix = 1500 m) one above-LTO fragment of movement 8 (E190
departure, JET-REGIONAL-D-1) was being dropped that should have been
kept (+6.73 kg CO₂); on Day 3 (mix = 600 m) one pt6 → pt7 segment of
movement 10 (A20N arrival, JET-SMALL-A-1) was being kept that should
have been dropped (−63.76 kg CO₂).  The fix adds
`movements.get_mixing_height_at()` with the fallback chain
`tbl_InvMeteo.MixingHeight → user_study_setup.vertical_limit → 914.4
m`, and `compute_aircraft.compute_fixed_wing` now reads it once per
movement and passes the result through the clip.

### Segments crossing the vertical limit

A segment with one endpoint below and one above the limit used to be
counted whole: only the altitude of the upper endpoint was capped, so
its full horizontal length entered distance, time and emissions. The
plugin (`apply_height_limits`), the standalone and this reference now
move the upper endpoint along the segment to where it meets the limit
(altitude linear along the segment), so only the part below the limit
counts. On the training fixture at 914.4 m every crossing segment lies
outside the 50 × 50 grid, so the pinned plugin outputs are unchanged.
Tests: `tests/test_height_limit_crossing_segment.py` (plugin) and
`validation/tests/test_crossing_segment_standalone.py` (standalone =
reference, also at a 300 m limit; analytic crossing distance).

### BFFM2 taxi ambient FF

The plugin's `TaxiingEmissionCalculator` calls
`Engine.getEmissionIndexByEngineState(power_setting, method=BFFM2)`
**without** an explicit `fuel_flow` argument, which routes through the
power-setting branch in `Engine.getEmissionIndexByEngineState` and
applies the SAE AIR-5715 inverse correction
`ff_amb = ff_ref · δ / θ^3.8 / exp(0.2 · M²)` (with `M = 0` at taxi)
before the segment fuel is computed.  The standalone and the reference
were both passing `tx["ff"]` (the EEDB reference idle fuel flow)
unchanged into `_bffm2_apply_segment`.  On Day 1 of the EHRD fixture
(T = 280.5 K, P = 97 600 Pa) the correction factor is 1.0659, so plugin
taxi fuel was systematically 6.6 % higher than standalone taxi fuel —
which propagated to a ~1.9 % delta on per-movement CO₂ in `bffm2_anchor`
and the BFFM2 EI lookup on `bffm2_traj`.  The fix computes
`tx_ff_amb = tx["ff"] · δ / θ^3.8` (mach 0) and uses it for both the
segment fuel mass and the BFFM2 EI lookup, in both the standalone
(`compute_aircraft.compute_fixed_wing`) and the reference
(`compute_caep14_reference._compute_fixed_wing`).

After both fixes the standalone matches the plugin CSVs to within
floating-point noise on all 14 fixed-wing + 2 helicopter movements
across `bymode`, `bffm2_anchor`, and `bffm2_traj`.

## October 2026: index step, re-export, helicopters

### What the CAEP validation covers

The CAEP validation (EUROCONTROL's CAEP/14 engine-emissions calculation;
its results are reproduced in the tests, the workbook itself is not part of
the repository) takes the engine fuel flow as an input and computes the
BFFM2 reference fuel flow and the ambient emission indices. Note on
independence: the reference implementation writes out the geometry, the
fuel-flow step, the taxi, the NOx correction and the helicopter cut on its
own, but imports the plugin's BFFM2 index function
(`open_alaqs.core.tools.bffm2.calculate_emission_index`) and the FOCA
helicopter tables (`foca_heli`, `foca_heli_utils`). Those two parts are what
the CAEP validation cases and the FOCA Appendix A values check, not the
plugin-vs-reference comparison.
It has no view on how a fuel flow is derived from a thrust: that step is
validated against the reference implementation, as the rest of the method;
the index step is pinned to the CAEP validation.

- `tests/test_caep14_sheet_reference_case.py`: BFFM2 index step against
  two cases of the CAEP validation for engine 01P20CM127 (LEAP-1A24) at
  fuel flow 1.1749 kg/s. The worked case, climb to cruise at 22 500 ft
  (non-LTO, lean burn: v2 indices, exponent 0.3): reference fuel flow
  1.657227 kg/s, EI NOx 60.20166, CO 0.459531, HC 0.0282788 g/kg. The LTO
  path (standard indices, exponent 0.5), the same workbook recalculated
  in LibreOffice 24.2 headless with altitude 1 000 ft, CLIMB OUT, 180 kt:
  reference fuel flow 1.204590 kg/s, EI NOx 17.65248, CO 0.329654,
  HC 0.0202864 g/kg. The code matches CO and HC to 1e-14 and NOx to 2e-6
  from RH (the humidity ratio formula), exactly with the CAEP validation's
  humidity ratio.

### Re-export of the pinned plugin outputs

The 5.2.0 exports in `data/plugin_output/` were stale on two counts:
they were made at ISA while the plugin now applies `tbl_InvMeteo` (5 to
25 % on the BFFM2 methods on the fixture's cold and warm days), and they
predate the 5.3.2 helicopter placement and the runway placement of ANP
arrivals of this version (+8 to +16 % on the seven ANP arrivals for all
three methods). They were re-exported with `tools/regenerate_plugin_csvs.py`
(the plugin's `EmissionCalculatorService`, the code path of the QGIS
dialog, run without a display), and the comparison is now 0.00 % on 15 of
15 movements for the three methods with `--use-meteo` (movement 11,
CUSTOM, +0.01 % on `bffm2_traj`). The run with the ICCAIA NOx ambient
correction (`training_movements_bymode_nox_corr.csv`) and the
stationary-source rows (`training_sources_bymode.csv`) were re-exported the
same way; the workbook `data/training_validation_reference.xlsx` was rebuilt
from them (step 3). The plugin runs with the grid reference altitude set to
the study's airport elevation, as the QGIS dialog does; the NOx correction
reads it as the airport altitude (at the fixture's −5 m the corrected NOx is
0.04 % lower than with a reference altitude of 0).

### NOx ambient correction (bymode)

The plugin applied the ICCAIA correction to every flight segment of a
movement, approach included, while its own module and the standalone
restrict it to take-off and climb-out, the modes the simple method is
defined for. The plugin now gates on the segment mode (`NOX_CORRECTION_MODES`
in `MovementEmissionCalculator`); arrivals are no longer corrected (they
were 1 to 6 % low on the fixture's days). The reference carries the
correction too (`--apply-nox-corrections`, `_nox_ambient_factor`, written
out from Doc 9889 with the pressure in hPa); plugin = reference = standalone
on 15 of 15 movements (`test_plugin_csv_vs_reference.py`).

### Helicopter arrival (movement 15)

Until this round the reference placed helicopters as 5.2.0 did (no cut),
so it matched the 5.2.0 export and disagreed with the plugin and the
standalone of 5.3.2 and later by 19 % on the arrival (its approach starts
outside the 50 × 50 grid). The reference now builds the FOCA flight path
and the cut on its own (see "Helicopters" above); it equals the plugin on
the fixture at 914.4 m without gates and at 300 m with gate G4 as helipad
(0.00 % on 15 of 15 for `bymode`), and the standalone at 914.4, 600, 300
and 100 m with and without a gate (1e-10).
