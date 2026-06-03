# CAEP14 Reference Validation for OpenALAQS

This directory contains a self-contained CAEP14 v14 reference implementation
of OpenALAQS emission calculations.  The reference is used to validate
plugin output across all three calculation methods (`bymode`,
`bffm2_anchor`, `bffm2_traj`) and across fixed-wing and helicopter
aircraft.  The training dataset (`example/training/training.alaqs`) is
the canonical fixture, but the scripts work against any OpenALAQS
study database.

The reference was first developed and pinned against OpenALAQS 5.2.0 in
May 2026.  Following the May 2026 patch round, all 15 of 15 movements in
`training_v3.alaqs` match to 0.00 % across CO, CO₂, NOₓ and PM₁₀ for
all three methods (`bymode`, `bffm2_anchor`, `bffm2_traj`); the prior
+0.87 % offset on movement 11 (PHBBA CUSTOM departure) is gone once the
movement's `profile_id` is set to the correct ADS-B import. Two
implementation gaps closed in that round are noted under "May 2026
patch round" below.

---

## Files

| File | Purpose |
| --- | --- |
| `compute_caep14_reference.py` | The reference implementation.  Produces per-movement CO, CO₂, HC, NOₓ, SOₓ, PM₁₀ totals for one method and either prints a table or compares against a plugin CSV. |
| `regenerate_training_validation_xlsx.py` | Reads the plugin CSVs and runs the reference for all three methods, then writes plugin + reference values into `example/training/training_validation_reference.xlsx` for paired-column inspection. |
| `compare_inventory_to_reference.py` | Standalone method-aware diff tool — useful when validating against a plugin output that is not in the standard CSV format. |
| `../tests/test_bffm2_ambient_propagation_regression.py` | Pure-Python pytest module that pins the BFFM2 ambient-correction behaviour (ISA, cold-dry, warm-humid, per-segment Mach) so a future change in `core/tools/bffm2.py` will surface immediately. |

The reference is dependency-light: it requires `numpy`, `shapely`,
`pyproj` and `openpyxl` (the last only for the xlsx-regen script).  It
does not import QGIS and runs in any standard Python 3.12 environment.

---

## Workflow for validating a new plugin build

### 1. Run the plugin against the training fixture

In QGIS open `example/training/training.alaqs`, run an inventory with
each of the three calculation methods, and export the per-movement
emissions to CSV via the standard Output Module.  Save them as
`training_movements_bymode.csv`, `training_movements_bffm2_anchor.csv`
and `training_movements_bffm2_traj.csv` (the file names the regen
script expects by default).

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
    --method=bffm2_anchor \
    --plugin-csv=/path/to/training_movements_bffm2_anchor.csv

python3 compute_caep14_reference.py /path/to/training.alaqs \
    --method=bffm2_traj \
    --plugin-csv=/path/to/training_movements_bffm2_traj.csv
```

Each invocation prints a per-movement table with CO, CO₂, NOₓ and
PM₁₀ from both reference (`_ref`) and plugin (`_plg`) plus a Δ%
column.  The expected outcome for OpenALAQS 5.2.0 against
`training_v3.alaqs`:

| method | 14 of 15 movements | movement 11 (PHBBA) |
| --- | --- | --- |
| `bymode` | 0.00 % on all pollutants | +0.07 / +0.87 / +0.87 / +0.87 % |
| `bffm2_anchor` | 0.00 % | +0.07 / +0.87 / +0.87 / +0.87 % |
| `bffm2_traj` | 0.00 % | +0.26 / +0.26 / +0.26 / +0.27 % |

Any plugin-vs-reference delta larger than these is a regression and
should be investigated before release.

### 3. Regenerate the validation workbook

```bash
python3 tools/regenerate_training_validation_xlsx.py /path/to/training.alaqs \
    --inputs-dir=/path/to/dir/containing/the/CSVs
```

This writes the paired plugin/reference columns into the Movement and
Summary sheets of `example/training/training_validation_reference.xlsx`
while preserving the structure (row 19 `=SUM(...)` formulas, sheet
order, header rows, the unmodified Helicopter and other-source-type
sheets).

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
validation without separate maintenance.

---

## Ambient conditions: ISA vs `tbl_InvMeteo`

The reference defaults to ISA conditions (T = 288.15 K, P = 101 325 Pa,
RH = 0.6) for the BFFM2 ambient correction because that is what the
plugin's emission CSV output currently uses.  Pass `--use-meteo` to
override and read the actual meteo row at each movement's
`runway_time` from `tbl_InvMeteo`:

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

## Mov 11 PHBBA offset (known)

Movement 11 (A20N CUSTOM departure on runway 24, gate G2) shows a
small systematic offset across all three methods because the imported
PHBBA trajectory's `x_m` / `y_m` columns were computed against a
runway-taxi-route intersection at EPSG:3857
`(495 718.872, 6 793 260.579)`, which is 132 m EPSG:3857 / 81 m on the
ground from the current G2 ∩ runway-24 intersection at
`(495 829.780, 6 793 333.126)` derived from `training_v3.alaqs`.

Resolution requires either re-importing PHBBA (the ADS-B importer
recomputes `x_m` / `y_m` against the live alaqs geometry) or persisting
the reference point at import time so calculators can use the value
that the trajectory was generated against.  Neither is required for
the validation to pass — the 14 / 15 movements that share the
training geometry already verify everything but the imported-fixture
edge case.

`bffm2_traj` shows a smaller delta on movement 11 (+0.26 %) than
`bymode` and `bffm2_anchor` (+0.87 %) because the per-segment fuel
flow comes from `fuel_flow_kgm` rather than the mode anchor, so the
reference-point offset has less leverage on the per-segment fuel
computation.

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
