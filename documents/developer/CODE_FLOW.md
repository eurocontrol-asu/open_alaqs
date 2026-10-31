# Code structure and calculation flow

This page is for maintainers. It maps the aircraft emission methods described in [AIRCRAFT_EMISSIONS.md](../methods/AIRCRAFT_EMISSIONS.md) to the files and functions of the plugin, and says what to change to add a helicopter category. The method itself (equations, options, limitations) is documented there, not here.

## Files of the aircraft emission calculation

| File | Role |
| --- | --- |
| `core/tools/bffm2.py` | BFFM2 formula: ambient corrections, log-log interpolation, CO/HC slope-to-mean-value rule, installation corrections (`calculate_emission_index`) |
| `core/tools/twin_quadratic_fit_method.py` | power setting to reference fuel flow by the twin-quadratic fit |
| `core/tools/meem_v1.py` | MEEM V1 nvPM index, MEEM V1 method (ICAO CAEP/13-MDG): mode value at or below 3000 ft; above, ISA + ΔT (or the segment's local T and p when passed), P3/T3, ground-reference thrust, linear interpolation and the (P3/P3_GR)^1.35 φ^2.5 correction; checked against reference cases by `tests/test_meem_v1.py` |
| `core/tools/meem_v2.py` | MEEM V2, implemented, not used |
| `core/tools/fuel_sulphur.py` | SOx index by fuel type |
| `core/tools/nox_correction_ambient.py` | ICCAIA NOx correction (bymode option) |
| `core/tools/surface_layer_atmosphere.py` | ambient conditions aloft (atmosphere models) |
| `core/tools/ads_b.py` | ADS-B file validation and import into `default_aircraft_profiles` (`CUSTOM` profiles) |
| `core/tools/runway_placement.py` | placement of the profiles on the runway, split of the taxi time |
| `core/interfaces/Engine.py` (`EngineEmissionIndex`) | steps 1 to 5 of BFFM2: twin-quadratic call, δ√θ scaling, cache, call to `bffm2.py`; `getEmissionIndexByModeWithMEEM()` applies MEEM V1 (`_meem_v1`) |
| `core/MovementEmissionCalculator.py` (`FlightEmissionCalculator`) | segment loop: reads profile points, computes Mach, chooses the fuel flow, calls `_get_emission_index_bffm2`, computes `t_seg`, calls `Emission.add()`; ICCAIA NOx correction (`_apply_nox_corrections`, modes in `NOX_CORRECTION_MODES`); local ambient per height (`local_ambient_conditions`, `_LocalAmbient`) |
| `core/MovementEmissionCalculator.py` (module level) | `_meem_ambient(method_config, T_amb, p_amb)`: the local ambient passed to MEEM V1 |
| `core/MovementEmissionCalculator.py` (`TaxiingEmissionCalculator`) | taxi loop: taxi index (bymode TX with MEEM, or BFFM2 `getEmissionIndexByEngineState()` with PM, SOx and P1/P2 from the TX mode index; no index: no taxi emissions), APU (`_apply_apu_emissions`), single-engine taxi and engine start (`_apply_single_engine_taxiing_emissions*`, `_do_apply_single_engine_taxiing_emissions`, `_apply_start_engine_emissions`; `gate_emissions_code` 0 drops all start emissions), queuing, stop-and-go (`AVERAGE_DURATION_OF_STOP_AND_GOS_IN_S`), brake wear |
| `core/MovementEmissionCalculator.py` (`GateEmissionCalculator`) | GSE and GPU at the gate; `_get_aircraft_group_match` picks the gate profile group (exact, else `difflib.get_close_matches`, else none: no GSE or GPU, logged at debug level only; intended for PROPELLER) |
| `core/GeoTransformation.py` (`TrajectoryTransformer.runway_alignment`) | places ANP and CUSTOM profile points on the runway |
| `core/modules/MovementSourceModule.py` | `process()` sets `max_height` from `ambient_conditions.getMixingHeight()` (the `vertical_limit_m` fallback under `except AttributeError` is not reached, because `getAmbientCondition` always returns an `AmbientCondition`), builds the `calc_method` dict and creates the calculators |
| `core/EmissionCalculatorService.py` | passes `method`, `meem_version`, `bffm2_ff_source` to the source modules |
| `core/EmissionCalculation.py` | `getAmbientCondition`: meteo row nearest in time for each period; `AmbientCondition()` (ISA, mixing height 914.4 m) when the meteo table is empty |
| `core/interfaces/AmbientCondition.py` | meteo row values with their defaults (empty `MixingHeight`: 914.4 m) |

## BFFM2 calculation flow

```text
User clicks "Calculate" (BFFM2 selected)
    │
    ▼
EmissionCalculatorService.calculate_emissions()
    passes method = 'BFFM2', meem_version, bffm2_ff_source to the source modules
    │
    ▼
MovementSourceModule.process()
    builds calc_method = {
        'name': 'BFFM2',
        'config': {
            'ambient_conditions': AmbientCondition(...),
            'apply_nox_corrections': False,
            'bffm2_ff_source': 'trajectory',  # or 'mode_anchor'
            ...
        }
    }
    ├── TaxiingEmissionCalculator  (BFFM2 gas-phase FF; PM/SOx/P1/P2 from mode EI; APU added on taxi segments)
    ├── GateEmissionCalculator     (GSE and GPU)
    └── FlightEmissionCalculator
            │
            ▼
            for each (start_point_, end_point_) in trajectory.getPointPairs():
                │
                ├── Mach = TAS / SOS
                ├── method['config'].update({'mach_number': Mach})
                │
                ├── engine_thrust = start_point_.getEngineThrust()
                ├── fuel_flow     = start_point_.getFuelFlow()        # from fuel_flow_kgm
                │
                ├── if no engine_thrust and no fuel_flow:
                │       bymode EI for the segment (warning)
                │
                ├── if bffm2_ff_source == 'mode_anchor':
                │       use mode-anchor FF  →  getEmissionIndexByFuelFlow()
                ├── elif fuel_flow > 0:
                │       ff_per_engine = fuel_flow / n_engines
                │       if ff_per_engine ≤ 1.5 × Wf_TO (ADSB_FF_CEILING_FACTOR):
                │           use ff_per_engine directly  →  getEmissionIndexByFuelFlow()
                │       else:
                │           use mode-anchor FF (summary warning per movement)
                │
                ├── getEmissionIndexByEngineState(engine_thrust, fuel_flow)
                │       ├── Wf_ref  = twin_quad(engine_thrust, EEDB)
                │       ├── Wf_amb  = Wf_ref × δ × √θ
                │       └── getEmissionIndexByFuelFlow(Wf_amb)
                │               └── calculate_emission_index(pollutant, Wf_amb, EEDB, ambient)
                │                       ├── install corrections → shift EEDB breakpoints
                │                       ├── Wf_ref_BFFM2 = Wf_amb/δ × θ^3.8 × exp(0.2M²)
                │                       ├── log–log interpolation  →  EI_raw
                │                       └── ambient correction  →  EI_corr (NOx/CO/HC)
                │
                ├── _get_emission_index_bffm2(mode, emission_index_bffm2)
                │       ├── mode_ei = getEmissionIndexByModeWithMEEM(mode, ..., altitude MSL, TAS)
                │       │       └── MEEM V1: mode EI at or below 3000 ft; above,
                │       │               MEEM V1 → pm10_nonvol (= nvpm_g_kg),
                │       │               pm10/p1/p2 moved by the same amount, nvpm_number_kg
                │       └── inject into copy of BFFM2 result:
                │               pm10, pm10_nonvol, pm10_sul, pm10_organic,
                │               nvpm_g_kg, nvpm_number_kg (not read by Emission.add),
                │               sox, p1, p2
                │
                ├── d      = ellipsoidal_2d_distance(start_point, end_point)
                ├── t_seg  = 2 × d / (TAS_start + TAS_end)
                ├── eff_t  = t_seg × n_engines
                └── mass   = EI_corr × Wf_amb × eff_t / 1000   [kg]
```

The segment distance uses `QgsDistanceArea.measureLine()` with the ellipsoid set, so it is the geodesic ground distance whatever the CRS of the emission layer.

## Taxi flow

With BFFM2, `TaxiingEmissionCalculator` always calls `Engine.getEmissionIndexByEngineState(engine_thrust_level_for_taxiing, method)`, which takes the power-setting branch (twin-quadratic fit, then ff_ref · δ · √θ) whatever `bffm2_ff_source` is. `mode_anchor` therefore changes only the flight segments.

Taxiing runs at Mach 0: `TaxiingEmissionCalculator.calculate_emissions` saves the Mach left in the shared `method['config']` by the flight calculator, sets it to 0 for the taxi index, and restores it afterwards. The ground ambient (station pressure, 2 m temperature) is set with `_LocalAmbient(config, 0.0)` for the same block.

## Adding a helicopter category

If a future revision of the FOCA guidance introduces a new helicopter category ([HELICOPTERS.md](../methods/HELICOPTERS.md#helicopter-categories)), three places change:

1. The `HelicopterCategory` enum in `core/tools/foca_heli.py`.
2. The `derive_category()` rule in the same file (the engine type, engine count and MTOM decision tree).
3. A new entry in `TRAJECTORY_PARAMS` in `core/tools/foca_heli_trajectory.py`, and a matching table in [HELICOPTERS.md](../methods/HELICOPTERS.md#trajectory-parameters) with a source for each field.

The trajectory generator's general logic (climb to the LTO ceiling, two-segment approach, hover at both ends) is shared by all categories and needs no change unless the FOCA method itself is restructured.

## See also

- [AIRCRAFT_EMISSIONS.md](../methods/AIRCRAFT_EMISSIONS.md): the methods
- [ATMOSPHERE_ALOFT.md](../methods/ATMOSPHERE_ALOFT.md): ambient conditions aloft
- [HELICOPTERS.md](../methods/HELICOPTERS.md): the FOCA 2015 helicopter method
