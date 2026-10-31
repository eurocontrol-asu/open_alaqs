# Helicopters

This page is the reference for helicopter emissions in OpenALAQS: the FOCA 2015 method, the helicopter catalog, and the trajectory that places the emissions in space. It is for modellers who need to know how helicopter movements are computed or who want to add a helicopter type.

- [FOCA 2015 method](#foca-2015-method)
- [Helicopter categories](#helicopter-categories)
- [Default catalog](#default-catalog)
- [What is not computed for helicopters](#what-is-not-computed-for-helicopters)
- [Trajectory parameters](#trajectory-parameters)
- [Approach geometry](#approach-geometry)
- [Departure geometry](#departure-geometry)
- [Adding a new category](#adding-a-new-category)

Primary reference:

> Rindlisbacher T., Chabbey L., "Guidance on the Determination of
> Helicopter Emissions", Swiss Federal Office of Civil Aviation
> (FOCA), Edition 2, December 2015. Ref: COO.2207.111.2.2015750.

Cited below as **FOCA 2015**. Section and appendix references are to that document unless stated otherwise.

## FOCA 2015 method

Helicopter movements use the same Movements table as fixed-wing aircraft. The `aircraft` field holds an ICAO type designator (or a variant label, see [Default catalog](#default-catalog)). Each identifier is first looked up in the helicopter catalog (`default_helicopter`); a match is computed as a helicopter, otherwise the fixed-wing catalog (`default_aircraft`) is used. No flag in the Movements table marks a helicopter: the lookup decides.

Emissions are computed live with the FOCA 2015 method from each helicopter's engine type, maximum shaft horsepower, engine count and category, for the FOCA LTO modes (ground idle, take-off, climb-out, approach). No precomputed emission indices are stored. The FOCA path is the same whatever the **Method** selected on the Configuration tab (Bymode or BFFM2).

FOCA gives no SOx. OpenALAQS computes it as the mode fuel times 0.758 g/kg for turboshaft engines (jet fuel) or 0.2 g/kg for piston engines (AvGas), the fuel sulphur values of [Aircraft emissions: particulate matter](AIRCRAFT_EMISSIONS.md#particulate-matter).

The mode masses are then placed along a helicopter trajectory (see [Trajectory parameters](#trajectory-parameters)): ground idle as a point at the take-off or touchdown spot, the active mode along the flight path, cut at the LTO ceiling (the hour's mixing height, see [Aircraft emissions](AIRCRAFT_EMISSIONS.md#lto-ceiling-and-segment-clipping)) and the grid. The share of the active mode's time spent below the ceiling and inside the grid scales its FOCA mass.

Two inconsistencies of the FOCA 2015 PDF were resolved during implementation: the leading coefficient of the piston fuel flow, and the Appendix C power settings of the twin-heavy category. For the latter, Appendix C lists values that pre-date the 2015 update (legacy 2009-era values remained in the MODEL column despite text updates); OpenALAQS uses the post-2015 corrected values (Table 4).

In the code: `open_alaqs/core/tools/foca_heli.py` (fuel flow and emission index formulas; the "Known FOCA 2015 PDF inconsistencies" docstring), `foca_heli_utils.compute_lto` (mode masses), `foca_heli_trajectory.active_mode_retained` (cut at the ceiling and the grid), `fuel_sulphur.py` (SOx).

## Helicopter categories

Each movement is classified at run time into one of the four FOCA 2015 categories (section 2.4) from engine type, engine count and MTOM. The category is not stored.

| Category | Rule |
|---|---|
| `PISTON` | `engine_type = PISTON` |
| `SINGLE_TURBOSHAFT` | `engine_type = TURBOSHAFT`, one engine |
| `TWIN_TURBOSHAFT_LIGHT` | `engine_type = TURBOSHAFT`, two or more engines, MTOM ≤ 3400 kg |
| `TWIN_TURBOSHAFT_HEAVY` | `engine_type = TURBOSHAFT`, two or more engines, MTOM > 3400 kg |

The 3400 kg threshold is defined in FOCA 2015 section 2.4. A twin turboshaft without MTOM cannot be classified and is rejected. The category drives both the emission formulas and the trajectory geometry.

In the code: `derive_category` in `open_alaqs/core/tools/foca_heli.py`.

## Default catalog

The catalog has 60 helicopter rows in `default_helicopter`, covering common types (ICAO codes R22, A109, EC35, AS32, S76, S92 and others), and 86 engine rows in `default_helicopter_engines`, covering the corresponding turboshaft and piston engines.

| Table | Field | Notes |
|---|---|---|
| `default_helicopter` | `icao` | ICAO type designator |
| | `variant_label` | Distinguishes several rows per ICAO (e.g. `A109E_POWER` and `A109II`). The logical key is `(icao, variant_label)`. |
| | `manufacturer`, `name` | Free text |
| | `mtow_kg` | Maximum take-off weight in kilograms (used for the category) |
| | `engine_count` | Number of engines (used for the category) |
| | `engine`, `engine_name` | Reference a row of `default_helicopter_engines` |
| | `max_shp_per_engine` | Maximum shaft horsepower per engine |
| | `is_default` | `1` for the default variant of the ICAO code |
| `default_helicopter_engines` | `engine_name` | Logical key |
| | `engine_full_name` | Free text |
| | `engine_type` | `PISTON` or `TURBOSHAFT` |
| | `max_shp_per_engine` | Used when the helicopter row does not give one |
| | `source` | Provenance citation |

The Movements table has no `variant_label` column. Its `aircraft` column takes either an ICAO code (the default variant is used) or a `variant_label` (that row is used). When an identifier matches both an ICAO code and a variant label, the ICAO code wins.

To add a helicopter type, insert a row into `default_helicopter` that references an existing engine of `default_helicopter_engines` (or insert the engine row first). The minimum fields are `icao`, `variant_label`, `mtow_kg`, `engine_count`, `engine`, `engine_name`, `max_shp_per_engine` and `is_default`. Movements whose `aircraft` matches the new row are then computed with the FOCA method.

## What is not computed for helicopters

- **APU, GSE, GPU and main engine start.** None are computed for helicopters, whatever `apu_code` and `gate_emissions_code` say. The gate calculation is not run for a helicopter movement: the gate is only the helipad, the origin of the trajectory. Helicopters have no taxi route; the helicopter taxi step adds ground idle only. The FOCA 2015 LTO cycle covers ground idle, take-off, climb-out, approach and landing on its own, so nothing is counted twice.
- **Above the LTO ceiling.** The helicopter trajectory ends at 3000 ft above ground (ICAO LTO definition) and is cut at the hour's mixing height when that is lower; emissions above are not modelled.

In the code: `MovementSourceModule.process` skips the gate calculator for helicopters; `TaxiingEmissionCalculator._apply_taxiing_emissions_for_helicopters` adds ground idle.

## Trajectory parameters

The trajectory generator builds the 3D geometry of a helicopter LTO from the per-category parameters below. The four categories are those of [Helicopter categories](#helicopter-categories). Fuel flow, emission indices and mode masses are not trajectory parameters: they come from the [FOCA 2015 method](#foca-2015-method). The trajectory times are used only to cut the active mode at the LTO ceiling and the grid.

In the code: `TRAJECTORY_PARAMS` in `open_alaqs/core/tools/foca_heli_trajectory.py`.

### Global constants

| symbol | value | source |
|---|---|---|
| `LTO_CEILING_FT` | 3000 ft AGL | ICAO LTO cycle definition (Annex 16 Vol. II Appendix 3 §1.2) |
| `HOVER_ALT_FT` | 5 ft AGL | FOCA Appendix A (hover IGE altitude convention) |
| `HOVER_DURATION_S` | 18 s | FOCA Appendix A (assumed universal across categories) |
| Twin-turboshaft MTOM threshold | 3400 kg | FOCA §2.4 |

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
| `approach_start_nm` | 5.0 | Distance at which descent from LTO ceiling commences. FOCA Appendix A. Not used by the generator (see [Approach geometry](#approach-geometry)). |

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
| `approach_start_nm` | 5.0 | FOCA Appendix A. Not used by the generator (see [Approach geometry](#approach-geometry)). |

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
| `approach_start_nm` | 6.0 | Slightly longer than single because of higher initial TAS (descent angle preserved). Not used by the generator (see [Approach geometry](#approach-geometry)). |

### TWIN_TURBOSHAFT_HEAVY

Twin turboshaft helicopters with MTOM > 3400 kg. The reference
airframe is the AS332L1 Super Puma (MTOM 8600 kg), for which a
complete technical data set is published in the AS332L1 Pilot's
Operating Manual. FOCA 2015 documents the methodology for this
category but uses single-turboshaft performance values in its
worked example; this implementation uses heavy-twin values to avoid
under-estimating LTO duration at large airframes.

The FOCA mode power settings of this category are discussed in [FOCA 2015 method](#foca-2015-method).

| field | value | source |
|---|---|---|
| `climb_roc_fpm` | 1920 | AS332L1 Technical Data, ROC at AUW 8000 kg, climb at Vy 70 kt |
| `climb_tas_kt` | 70 | AS332L1 Technical Data Vy |
| `cruise_tas_kt` | 139 | AS332L1 Technical Data recommended cruise TAS at 8000 kg |
| `approach_tas_initial_kt` | 70 | Symmetric with climb_tas_kt |
| `approach_tas_final_kt` | 40 | Operational convention (final approach to hover) |
| `approach_rod_initial_fpm` | 700 | FOCA Appendix A initial descent ROD |
| `approach_rod_final_fpm` | 300 | Operational convention |
| `approach_start_nm` | 7.0 | Longer approach distance scales with cruise TAS (descent angle preserved at ~3°). Not used by the generator (see [Approach geometry](#approach-geometry)). |

## Approach geometry

The arrival fills the FOCA approach time
(5.5 min):

1. a level segment at the LTO ceiling at `approach_tas_initial_kt`,
   when the two descents take less than the approach time;
2. a descent at `approach_tas_initial_kt` and
   `approach_rod_initial_fpm` to 500 ft AGL;
3. a final descent at `approach_tas_final_kt` and
   `approach_rod_final_fpm` to hover (5 ft AGL).

When the two descents take longer than the approach time, both are
shortened in proportion: the arrival still starts at the LTO ceiling, the
break between the two descents moves up (PISTON about 1030 ft,
SINGLE_TURBOSHAFT about 520 ft instead of 500 ft) and the final descent is
steeper than `approach_rod_final_fpm`. The arrival then starts about 8.7 km (PISTON),
8.4 km (SINGLE_TURBOSHAFT), 11.5 km (TWIN_TURBOSHAFT_LIGHT) and
10.4 km (TWIN_TURBOSHAFT_HEAVY) from the touchdown spot.
`approach_start_nm` is not used by the generator. Hover is held for
`HOVER_DURATION_S` (18 s) before touchdown.

In the code: `build_arrival` and `FINAL_BREAK_ALT_FT` in `foca_heli_trajectory.py`.

## Departure geometry

Ground idle at the origin for 80 % of the GI time, hover for
`HOVER_DURATION_S` at `HOVER_ALT_FT`, then climb at `climb_tas_kt`
and `climb_roc_fpm` until the LTO ceiling (3000 ft AGL) or the end of
the FOCA take-off time (PISTON stops at about 2000 ft); any remaining
take-off time is flown level at `cruise_tas_kt`.

The origin is the centroid of the movement's gate (helipad), else the
runway end; arrivals approach from the approach side along the runway
heading. Ground idle after landing is 20 % of the GI time.

In the code: `build_departure` in `foca_heli_trajectory.py`; `runway_alignment_for_helicopter` in `open_alaqs/core/GeoTransformation.py`.

## Adding a new category

What to change in the code for a new FOCA category is in [CODE_FLOW.md](../developer/CODE_FLOW.md#adding-a-helicopter-category).

See also: [Aircraft emissions](AIRCRAFT_EMISSIONS.md), [Reference data](REFERENCE_DATA.md), [User Guide: movements](../user/USER_GUIDE.md#generate-emissions-inventory), [Input formats: movements](../user/INPUT_FORMATS.md#movements).
