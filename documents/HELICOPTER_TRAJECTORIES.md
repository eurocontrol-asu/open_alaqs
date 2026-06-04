# Helicopter trajectory parameter sources

This document records the source of every per-category trajectory
parameter used by `open_alaqs/core/tools/foca_heli_trajectory.py`. The
trajectory generator builds the 3D geometry of a helicopter LTO from
these parameters; the FOCA 2015 emission method (in `foca_heli.py`)
then maps that geometry to fuel burn and emissions.

The four helicopter categories below match the FOCA 2015 classification
in section 2.4: PISTON, SINGLE_TURBOSHAFT, TWIN_TURBOSHAFT_LIGHT (twin
turboshaft with MTOM ≤ 3400 kg), TWIN_TURBOSHAFT_HEAVY (twin
turboshaft with MTOM > 3400 kg).

Primary reference:

  > Rindlisbacher T., Chabbey L., "Guidance on the Determination of
  > Helicopter Emissions", Swiss Federal Office of Civil Aviation
  > (FOCA), Edition 2, December 2015. Ref: COO.2207.111.2.2015750.

Cited below as **FOCA 2015**. Section / Appendix references are to
that document unless stated otherwise.

## Global constants

| symbol | value | source |
|---|---|---|
| `LTO_CEILING_FT` | 3000 ft AGL | ICAO LTO cycle definition (Annex 16 Vol. II Appendix 3 §1.2) |
| `HOVER_ALT_FT` | 5 ft AGL | FOCA Appendix A (hover IGE altitude convention) |
| `HOVER_DURATION_S` | 18 s | FOCA Appendix A (assumed universal across categories) |
| Twin-turboshaft MTOM threshold | 3400 kg | FOCA §2.4 |

## Per-category parameters

### PISTON

Representative airframe: Robinson R22. Selected as the canonical
piston single because it dominates the FOCA fleet sample and its
performance is published in the R22 Pilot's Operating Handbook (POH)
in matching units.

| field | value | source |
|---|---|---|
| `climb_roc_fpm` | 500 | R22 POH §4 (normal climb rate at sea-level ISA) |
| `climb_tas_kt` | 60 | R22 POH §4 (Vy, best rate of climb speed) |
| `cruise_tas_kt` | 75 | R22 POH §5 (75% MCP cruise TAS at 4000 ft) |
| `approach_tas_initial_kt` | 60 | Operational convention (Vy is used as the approach entry speed for piston helicopters per FOCA Appendix A) |
| `approach_tas_final_kt` | 30 | Operational convention (slow-down to translational-lift speed before hover) |
| `approach_rod_initial_fpm` | 500 | Symmetric with climb ROC; FOCA Appendix A descent profile |
| `approach_rod_final_fpm` | 250 | Reduced ROD for final segment; FOCA Appendix A descent profile |
| `approach_start_nm` | 5.0 | Distance at which descent from LTO ceiling commences. FOCA Appendix A. |

### SINGLE_TURBOSHAFT

The FOCA 2015 reference table is specified for this category directly.

| field | value | source |
|---|---|---|
| `climb_roc_fpm` | 1000 | FOCA Appendix A |
| `climb_tas_kt` | 60 | FOCA Appendix A |
| `cruise_tas_kt` | 120 | FOCA §2.1 worked example |
| `approach_tas_initial_kt` | 60 | FOCA Appendix A "DCT" (descent) row |
| `approach_tas_final_kt` | 30 | FOCA Appendix A |
| `approach_rod_initial_fpm` | 700 | FOCA Appendix A |
| `approach_rod_final_fpm` | 250 | FOCA Appendix A |
| `approach_start_nm` | 5.0 | FOCA Appendix A |

### TWIN_TURBOSHAFT_LIGHT

Twin turboshaft helicopters with MTOM ≤ 3400 kg. Representative
airframes include the Eurocopter EC135, AS355, BO105. FOCA 2015 does
not publish a separate trajectory table for this category; the
values below are obtained by scaling up from SINGLE_TURBOSHAFT in
proportion to the typical performance ratio observed across the
representative airframes (flight manuals: EC135 §4-5, AS355 §4-5).

| field | value | source |
|---|---|---|
| `climb_roc_fpm` | 1500 | Scaled from FOCA Appendix A SINGLE_TURBOSHAFT; corroborated against EC135 P2 flight manual §4-5 (sea-level Vy ROC, AUW 2720 kg) |
| `climb_tas_kt` | 80 | EC135 / AS355 flight manuals (Vy at AUW representative for light twin) |
| `cruise_tas_kt` | 150 | EC135 / AS355 flight manuals (recommended cruise TAS, sea-level, ISA) |
| `approach_tas_initial_kt` | 80 | Symmetric with climb_tas_kt (FOCA Appendix A convention) |
| `approach_tas_final_kt` | 40 | Operational convention (final approach to hover; faster than single because of higher disk loading) |
| `approach_rod_initial_fpm` | 700 | FOCA Appendix A initial descent ROD (unchanged across light categories) |
| `approach_rod_final_fpm` | 300 | Scaled from SINGLE_TURBOSHAFT final ROD |
| `approach_start_nm` | 6.0 | Slightly longer than single because of higher initial TAS (descent angle preserved) |

### TWIN_TURBOSHAFT_HEAVY

Twin turboshaft helicopters with MTOM > 3400 kg. The reference
airframe is the AS332L1 Super Puma (MTOM 8600 kg), for which a
complete technical data set is published in the AS332L1 Pilot's
Operating Manual. FOCA 2015 documents the methodology for this
category but uses single-turboshaft performance values in its
worked example; this implementation uses heavy-twin values to avoid
under-estimating LTO duration at large airframes.

Note: Appendix C of the FOCA 2015 PDF lists power-setting values for
this category that pre-date the 2015 update (legacy 2009-era values
remained in the MODEL column despite text updates). The numbers used
here are the post-2015 corrected values, as documented in the
`foca_heli.py` "Known FOCA 2015 PDF inconsistencies" docstring.

| field | value | source |
|---|---|---|
| `climb_roc_fpm` | 1920 | AS332L1 Technical Data, ROC at AUW 8000 kg, climb at Vy 70 kt |
| `climb_tas_kt` | 70 | AS332L1 Technical Data Vy |
| `cruise_tas_kt` | 139 | AS332L1 Technical Data recommended cruise TAS at 8000 kg |
| `approach_tas_initial_kt` | 70 | Symmetric with climb_tas_kt |
| `approach_tas_final_kt` | 40 | Operational convention (final approach to hover) |
| `approach_rod_initial_fpm` | 700 | FOCA Appendix A initial descent ROD |
| `approach_rod_final_fpm` | 300 | Operational convention |
| `approach_start_nm` | 7.0 | Longer approach distance scales with cruise TAS (descent angle preserved at ~3°) |

## Approach geometry

For all four categories the approach is modelled as two segments:

1. `approach_start_nm` → 500 ft AGL: initial descent at
   `approach_tas_initial_kt` and `approach_rod_initial_fpm`.
2. 500 ft AGL → hover (5 ft AGL): final descent at
   `approach_tas_final_kt` and `approach_rod_final_fpm`.

The 500-ft intermediate altitude (`FINAL_BREAK_ALT_FT` in
`foca_heli_trajectory.py`) represents a typical final-approach
altitude for the deceleration profile. Hover is held for
`HOVER_DURATION_S` (18 s) before touchdown.

## Departure geometry

Symmetric with approach: takeoff hover for `HOVER_DURATION_S` at
`HOVER_ALT_FT`, then translational-lift acceleration into climb at
`climb_tas_kt` and `climb_roc_fpm`. Climb continues until
`LTO_CEILING_FT` (3000 ft AGL). The horizontal distance covered
during climb depends on the climb angle (climb_tas vs climb_roc) and
is computed by the trajectory generator.

## What is not parameterised

The following are **not** category-specific and are handled
elsewhere:

- **Fuel flow and emission indices**. Computed live from the
  helicopter's engine type, max shaft horsepower, engine count, and
  category at each FOCA LTO mode (Ground Idle, Takeoff, Climb-out,
  Approach). See `compute_lto()` in `foca_heli_utils.py`. The
  per-pollutant fuel-flow and emission-index helpers
  (`piston_fuel_flow_kg_s`, `turboshaft_ei_nox_g_kg`, etc.) live in
  `foca_heli.py`.
- **Mode time-in-mode allocation**. The trajectory generator emits
  per-segment timing (`t_s` field on each `TrajectoryPoint`); the
  emission calculator integrates fuel flow over these times.
- **APU and gate emissions**. APU is skipped because the helicopter
  taxi branch (`_apply_taxiing_emissions_for_helicopters` in
  `MovementEmissionCalculator.py`) does not call the APU code path
  — `apu_code` is not consulted on this branch. For gate emissions,
  `gate_emissions_code` is still respected (the gate function returns
  early if it is 0); when gate emissions are enabled, GSE and GPU
  sub-components are explicitly skipped for helicopters, but MES (Main
  Engine Start) is computed normally.

## Adding a new category

If a new FOCA category is introduced in a future revision of the
guidance document, additions are required in three places:

1. The `HelicopterCategory` enum in
   `open_alaqs/core/tools/foca_heli.py`.
2. The `derive_category()` rule in the same file (the
   engine_type / engine_count / mtom decision tree).
3. A new entry in `TRAJECTORY_PARAMS` in
   `open_alaqs/core/tools/foca_heli_trajectory.py`, plus a
   corresponding row in this document with per-field source
   citations.

The trajectory generator's general logic (climb to LTO ceiling,
two-segment approach, hover bookends) is shared across categories
and should not require change unless the underlying FOCA
methodology is restructured.
