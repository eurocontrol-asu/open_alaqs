# OpenALAQS User Guide - BFFM2 implementation

## Table of Contents

- [Aircraft emissions](#aircraft-emissions)
- [The Boeing Fuel Flow Method II](#the-boeing-fuel-flow-method-ii)
  - [Overview](#overview)
  - [Method description](#method-description)
    - [Step 1 — Fuel flow at reference conditions](#step-1--fuel-flow-at-reference-conditions)
    - [Step 2 — Convert to ambient fuel flow](#step-2--convert-to-ambient-fuel-flow)
    - [Step 3 — Emission index interpolation on the log–log curve](#step-3--emission-index-interpolation-on-the-loglog-curve)
    - [Step 4 — Ambient corrections](#step-4--ambient-corrections)
    - [Step 5 — Segment emission mass](#step-5--segment-emission-mass)
  - [Fuel flow interpolation methods](#fuel-flow-interpolation-methods)
    - [Twin-quadratic fit (ALAQS default)](#twin-quadratic-fit-alaqs-default)
    - [Piecewise-linear interpolation (CAEP14 / ICAO)](#piecewise-linear-interpolation-caep14--icao)
  - [Installation corrections](#installation-corrections)
  - [Humidity correction](#humidity-correction)
  - [Comparison with the Bymode method](#comparison-with-the-bymode-method)
  - [ADS-B profile specifics](#ads-b-profile-specifics)
  - [Implementation in OpenALAQS](#implementation-in-openalaqs)
    - [Code structure](#code-structure)
    - [Calculation flow](#calculation-flow)
    - [Key parameters in the database](#key-parameters-in-the-database)
    - [LTO ceiling and segment clipping](#lto-ceiling-and-segment-clipping)
  - [Known limitations](#known-limitations)

---

## Aircraft emissions

Aircraft emissions in OpenALAQS are calculated according to the ICAO LTO cycle framework described in ICAO Doc. 9889. For each movement, the plugin computes emissions for three separate phases — taxiing, gate operations, and the flight profile — and sums them to produce a per-movement total for each pollutant.

The flight phase can be calculated using one of two methods selectable from the QGIS calculation panel:

| Method | Description |
|--------|-------------|
| **Bymode** | Assigns a fixed emission index (EI) and fuel flow to each LTO mode (TX, AP, CL, TO) from the ICAO Engine Emissions Databank (EEDB). All approach segments use the AP-mode EI regardless of the actual thrust stored in the profile. |
| **BFFM2** | Uses the actual thrust setting from each profile point to derive a fuel-flow-dependent emission index. Ambient conditions (temperature, pressure, humidity, Mach number) are applied at every segment. |

This section documents the BFFM2 method in detail.

---

### The Boeing Fuel Flow Method II

#### Overview

The Boeing Fuel Flow Method II (BFFM2) was developed by Boeing and formalised in SAE AIR-5715. It is the standard methodology adopted by ICAO and CAEP for computing aircraft engine emissions at conditions other than the ICAO standard sea-level static (SLS) reference at which the EEDB was measured. The method maps any in-flight power setting to an estimated fuel flow, then interpolates the corresponding emission index from the four EEDB reference points (Idle/TX, Approach/AP, Climbout/CL, Takeoff/TO) on a log–log curve, and finally corrects that EI for ambient temperature, pressure, humidity and Mach number.

The central advantage of BFFM2 over the simpler bymode method is that it uses the actual thrust schedule stored in each profile point rather than the nominal power setting associated with the mode label. This is particularly significant for approach segments, which are often flown at near-idle thrust even though they are labelled `AP` in the profile.

**Reference:** SAE AIR-5715, *Procedure for the Calculation of Aircraft Emissions*; ICAO Doc. 9889, *Airport Air Quality Manual*, Chapter 2.

---

#### Method description

The BFFM2 calculation for a single profile segment proceeds in five steps.

---

##### Step 1 — Fuel flow at reference conditions

The power setting `P` (a dimensionless fraction from 0 to 1, where 1 = maximum takeoff thrust) is converted to a reference fuel flow `Wf_ref` at ICAO SLS conditions (T = 288.15 K, p = 101 325 Pa, M = 0) using one of the two interpolation methods described in [Fuel flow interpolation methods](#fuel-flow-interpolation-methods).

Both methods are bounded from below by the idle (TX) fuel flow:

```
Wf_ref = max(interpolated_value, Wf_TX)
```

This prevents physically impossible sub-idle values from the quadratic fit at very low power settings.

---

##### Step 2 — Convert to ambient fuel flow

The reference fuel flow is corrected for actual ambient conditions using the ICAO correction factors θ (temperature ratio) and δ (pressure ratio):

```
θ = T_amb / 288.15
δ = p_amb / 101 325

Wf_amb = Wf_ref × δ / √θ
```

`Wf_amb` is the per-engine ambient fuel flow in kg/s. This is the value used both for the log–log interpolation in Step 3 and for computing fuel burned in Step 5.

The Mach number correction to the reference fuel flow is applied *inside* the BFFM2 interpolation (Step 3) rather than here, consistent with SAE AIR-5715:

```
Wf_ref_BFFM2 = (Wf_amb / δ) × θ^3.8 × exp(0.2 × M²)
```

where M is the True Mach number at the start of the segment:

```
M = (TAS / SOS) × √(288.15 / T_amb)
```

and SOS = 331.3 + 0.606 × (T_amb − 273.15) m/s.

---

##### Step 3 — Emission index interpolation on the log–log curve

The EEDB contains four reference points for each pollutant (NOx, CO, HC): one per LTO mode, expressed as `(Wf_ref_i, EI_i)`. OpenALAQS applies the default **installation correction factors** (see [Installation corrections](#installation-corrections)) to the reference fuel flows before interpolation, shifting the x-axis breakpoints slightly to account for thrust losses due to engine installation effects.

The corrected reference fuel flows and their corresponding EI values are plotted in log₁₀ space. The emission index at `Wf_ref_BFFM2` is obtained by linear interpolation between the two surrounding breakpoints:

```
log10(EI) = log10(EI_i) + [log10(EI_{i+1}) - log10(EI_i)] ×
             [log10(Wf) - log10(Wf_i)] / [log10(Wf_{i+1}) - log10(Wf_i)]
```

**CO special handling.** The CO log–log curve is non-monotonic: CO EI is high at idle, drops steeply to a minimum (the "Lean Azeotropic Value", LAV) near the Approach–Climbout boundary, and then remains approximately flat through Climbout and Takeoff. OpenALAQS detects whether the CO curve has this standard shape and, if so, applies a horizontal segment at the LAV once the fuel flow exceeds the AP–CL intersection point. For engines where this standard shape is not detected, a simple linear interpolation is used throughout.

**Extrapolation capping.** If `Wf_ref_BFFM2` falls below the idle breakpoint, the idle EI is used. If it exceeds the takeoff breakpoint, the takeoff EI is used. No extrapolation beyond the EEDB range is performed.

---

##### Step 4 — Ambient corrections

The raw interpolated EI is corrected for ambient conditions:

**NOx** (SAE AIR-5715 humidity and P₃T₃ correction):

```
h = −19 × (ω − 0.00634)           # humidity coefficient; ω in kg H₂O / kg dry air
EI_NOx_corr = EI_NOx × exp(h) × (δ^x / θ^3.3)^0.5
```

where `x = 1.0` (default P₃T₃ exponent) and `ω` is the specific humidity, computed from relative humidity `RH`, ambient temperature and pressure if not provided directly:

```
p_sat = 6.107 × 10^(7.5 × T_C / (237.3 + T_C))   [mbar; T_C in °C]
ω = 0.622 × RH × p_sat / (p_mb − RH × p_sat)
```

At the ICAO reference humidity (ω = 0.00634 kg/kg), `exp(h) = 1` and the humidity term vanishes.

**CO and HC** (temperature and pressure correction only):

```
EI_CO_corr  = EI_CO  × (θ^3.3 / δ^1.0)
EI_HC_corr  = EI_HC  × (θ^3.3 / δ^1.0)
```

---

##### Step 5 — Segment emission mass

The emission mass for one profile segment is:

```
mass_pollutant = EI_corr  [g/kg]
              × Wf_amb    [kg/s, per engine]
              × n_engines
              × t_seg     [s]
              / 1000       [→ kg]
```

where the segment time is derived from the geodesic distance between the two profile points and the average True Airspeed at start and end of the segment:

```
t_seg = 2 × d_geodesic / (TAS_start + TAS_end)
```

The geodesic distance is the ellipsoidal ground distance computed by QGIS `QgsDistanceArea.measureLine()` with the ellipsoid set, so it accounts for the map projection and returns true ground distance in metres regardless of the CRS of the emission layer.

---

#### Fuel flow interpolation methods

Two methods are available for converting the power setting to reference fuel flow in Step 1. The method is selected via the **FF Interpolation** combo box in the QGIS calculation panel.

##### Twin-quadratic fit (ALAQS default)

The LTO thrust range is split into two sub-ranges at the Climbout breakpoint (P = 0.85). A separate quadratic polynomial `Wf = aP² + bP + c` is fitted through three EEDB points in each range:

- **Low range** (0 < P ≤ 0.85): fit through TX (P = 0.07), AP (P = 0.30), CL (P = 0.85)
- **High range** (0.85 < P ≤ 1.00): fit through AP (P = 0.30), CL (P = 0.85), TO (P = 1.00)

Both parabolas pass exactly through their three data points. The idle floor clamp (`max(result, Wf_TX)`) prevents the low-range parabola from returning physically impossible sub-idle values at very low power settings.

This is the original ALAQS method and is the backward-compatible default.

##### Piecewise-linear interpolation (CAEP14 / ICAO)

The four EEDB breakpoints are connected by three straight line segments in P–Wf space:

- TX (P = 0.07) → AP (P = 0.30)
- AP (P = 0.30) → CL (P = 0.85)
- CL (P = 0.85) → TO (P = 1.00)

This is the interpolation assumed in the ICAO CAEP14 BFFM2 reference calculator and produces results that are generally within 1–2% of the twin-quadratic values for standard EHRD movements.

> **Note.** For power settings below 7% (P < 0.07), both methods return the TX idle fuel flow (idle floor clamp). For P > 1.0, the TO fuel flow is returned.

---

#### Installation corrections

Engine installation in the airframe causes small losses in net thrust and slight changes in fuel flow relative to the bare-engine values measured on the EEDB test stand. BFFM2 accounts for this by multiplying the EEDB reference fuel flow breakpoints by mode-specific installation correction factors *before* the log–log interpolation. This shifts the interpolation x-axis breakpoints without changing the EI y-axis values.

OpenALAQS applies the following default correction factors from SAE AIR-5715:

| LTO mode | Installation correction factor |
|----------|-------------------------------|
| Takeoff  | 1.010 |
| Climbout | 1.013 |
| Approach | 1.020 |
| Idle     | 1.100 |

These are applied internally in `bffm2.py` at the start of each call to `calculate_emission_index()` and cannot currently be overridden through the QGIS UI. Custom values can be passed programmatically via the `installation_corrections` dict argument.

The corrections shift the reference fuel flow breakpoints to slightly higher values, which moves the interpolated EI marginally toward lower-fuel-flow (higher-EI for NOx) regions of the curve. The practical effect on total LTO NOx is small, typically 1–3%.

---

#### Humidity correction

The EEDB emission indices for NOx are measured under a standard reference humidity of ω₀ = 0.00634 kg H₂O per kg dry air (as defined in SAE AIR-5715). At other humidity levels, the correction factor is:

```
exp(−19 × (ω − 0.00634))
```

- **ω < 0.00634** (drier than standard): `exp(h) > 1` → NOx correction is positive
- **ω > 0.00634** (more humid than standard): `exp(h) < 1` → NOx correction is negative
- **ω = 0.00634** (standard humidity): no correction

The specific humidity ω is computed from the ambient conditions stored in the `tbl_InvMeteo` table of the `.alaqs` database. If the `Humidity` column (specific humidity in kg/kg) is populated directly, it is used as-is. Otherwise ω is computed from `RelativeHumidity` (0–1), `Temperature` (K) and `SeaLevelPressure` (Pa) using the Magnus saturation vapour pressure formula.

CO and HC are not corrected for humidity.

---

#### Comparison with the Bymode method

The two methods produce systematically different results because they handle the actual thrust schedule differently.

**NOx: BFFM2 is typically lower than Bymode for LTO**

The EEDB NOx curve is steep: EI rises from ~5 g/kg at idle to ~25 g/kg at takeoff. Bymode assigns the nominal mode EI (e.g. the AP value, ~9–14 g/kg) to all approach segments regardless of the actual thrust in the profile. BFFM2 sees the actual profile power, which for approach segments is typically far below the nominal 30% AP thrust, mapping to the idle region of the NOx curve (~5 g/kg). The cumulative result is that BFFM2 NOx is substantially lower for arrival movements and moderately lower for departures.

For the EHRD test case:

| Movement type | Typical NOx: BFFM2 vs Bymode | Primary driver |
|---------------|------------------------------|----------------|
| Arrivals | −5% to −53% | Profile approach power near idle → low NOx EI in BFFM2 |
| Departures | −21% to −36% | Intermediate climb power below CL nominal |

**CO: BFFM2 is higher for arrivals, similar for departures**

The EEDB CO curve is U-shaped: high at idle (~20–24 g/kg), dropping to a minimum (LAV ~0.2–0.6 g/kg) near Climbout/Takeoff power. Near-idle approach segments get CO EI ≈ idle level in BFFM2, whereas bymode uses the lower AP value (~2–4 g/kg). For departures, both methods give similar CO because most departure segments are at or near TO/CL power where CO EI is at the LAV floor. HC follows the same qualitative pattern.

| Movement type | Typical CO: BFFM2 vs Bymode |
|---------------|------------------------------|
| Arrivals | +18% to +30% |
| Departures | ±2% |

**Interpretation guideline.** A BFFM2–bymode NOx difference of 20–55% is normal and expected for LTO. A difference outside this range should be investigated. For CO, +15–35% on arrivals and ±2% on departures is normal.

---

#### ADS-B profile specifics

OpenALAQS supports profiles derived from ADS-B recordings in addition to standard ICAO ANP profiles. ADS-B profiles are stored in `default_aircraft_profiles` with `course = 'CUSTOM'`, and their x_m and y_m coordinates represent East and North offsets (in metres) from the runway intersection rather than along-runway distances.

**GeoTransformation.** For CUSTOM profiles, the plugin's `TrajectoryTransformer.runway_alignment()` places each profile point at `runway_intersection + x_m East + y_m North` using geodesic projection on the WGS84 ellipsoid (`computeSpheroidProject`). The resulting EPSG:3857 coordinates are then used for the geometry output. Because EPSG:3857 uses a Mercator projection, the Euclidean distance between two projected points is approximately `sec(latitude)` times the geodesic ground distance. However, OpenALAQS always measures segment distances using `QgsDistanceArea.measureLine()` with the ellipsoid set, which returns the true geodesic distance and is not affected by the Mercator scale factor.

**fuel_flow_kgm column.** ADS-B profiles may have the `fuel_flow_kgm` column populated with the estimated total-aircraft fuel flow in kg/s (sum over all engines), as recorded or derived from the ADS-B data. When this value is non-zero, OpenALAQS uses it in the BFFM2 calculation as follows:

1. The value is divided by the aircraft engine count to obtain the per-engine ambient fuel flow.
2. The per-engine value is compared to the EEDB Takeoff fuel flow (`Wf_TO`).
3. If the per-engine value is at or below `Wf_TO` (i.e. physically plausible), it is passed directly to the BFFM2 interpolation, bypassing the power-setting → twin-quad step.
4. If the per-engine value exceeds `Wf_TO` (indicating an unreliable ADS-B fuel flow estimate), the plugin falls back to the standard twin-quad / power-setting path and logs a `WARNING`.

Standard ICAO profiles have `fuel_flow_kgm = 0`, so this logic is inert for those profiles.

> **Important.** The ADS-B fuel flow estimate is derived from aircraft performance models applied to ADS-B position/speed data, not from direct fuel measurement. Its accuracy varies with aircraft type. Always check the QGIS log for `WARNING: ADS-B ff/engine exceeds EEDB TO ceiling` messages, which indicate that the estimate is being ignored and twin-quad is used instead.

---

#### Implementation in OpenALAQS

##### Code structure

The BFFM2 implementation is spread across the following files:

| File | Role |
|------|------|
| `core/tools/bffm2.py` | Core formula: ambient corrections, log–log interpolation, CO LAV logic, installation corrections |
| `core/tools/twin_quadratic_fit_method.py` | Power setting → reference fuel flow via twin-quadratic polynomial (Step 1, ALAQS default) |
| `core/interfaces/Engine.py` (`EngineEmissionIndex` class) | Orchestrates Steps 1–3: twin-quad call, ambient correction, cache, call to `bffm2.py` |
| `core/MovementEmissionCalculator.py` (`FlightEmissionCalculator` class) | Segment loop: reads profile points, computes Mach, calls `_get_emission_index_bffm2`, computes `t_seg`, calls `Emission.add()` |
| `core/modules/MovementSourceModule.py` | Creates `FlightEmissionCalculator` instances, passes `calc_method` dict |
| `core/EmissionCalculatorService.py` | Builds the `calc_method` dict, sets `method['name'] = 'BFFM2'` and ambient conditions |

##### Calculation flow

```
User clicks "Calculate" (BFFM2 selected)
    │
    ▼
EmissionCalculatorService.run()
    builds calc_method = {
        'name': 'BFFM2',
        'config': {
            'ambient_conditions': AmbientCondition(...),
            'apply_nox_corrections': False,
            'ff_method': 'twin_quadratic'  # or 'linear'
        }
    }
    │
    ▼
MovementSourceModule.calculate_emissions()
    ├── TaxiingEmissionCalculator  (TX mode, BFFM2 with idle-floor FF)
    ├── GateEmissionCalculator     (bymode; APU and GSE)
    └── FlightEmissionCalculator
            │
            ▼
            for each (start_point_, end_point_) in trajectory.getPointPairs():
                │
                ├── Mach = TAS / SOS × √(288.15 / T_amb)
                ├── method['config'].update({'mach_number': Mach})
                │
                ├── engine_thrust = start_point_.getEngineThrust()
                ├── fuel_flow     = start_point_.getFuelFlow()        # from fuel_flow_kgm
                │
                ├── if BFFM2 and fuel_flow > 0:
                │       ff_per_engine = fuel_flow / n_engines
                │       if ff_per_engine ≤ Wf_TO:
                │           use ff_per_engine directly  →  getEmissionIndexByFuelFlow()
                │       else:
                │           WARNING; fuel_flow = None  →  twin-quad path
                │
                ├── getEmissionIndexByEngineState(engine_thrust, fuel_flow)
                │       ├── Wf_ref  = twin_quad(engine_thrust, EEDB)   # or linear
                │       ├── Wf_amb  = Wf_ref × δ / √θ
                │       └── getEmissionIndexByFuelFlow(Wf_amb)
                │               └── calculate_emission_index(pollutant, Wf_amb, EEDB, ambient)
                │                       ├── install corrections → shift EEDB breakpoints
                │                       ├── Wf_ref_BFFM2 = Wf_amb/δ × θ^3.8 × exp(0.2M²)
                │                       ├── log–log interpolation  →  EI_raw
                │                       └── ambient correction  →  EI_corr
                │
                ├── d      = ellipsoidal_2d_distance(start_point, end_point)
                ├── t_seg  = 2 × d / (TAS_start + TAS_end)
                ├── eff_t  = t_seg × n_engines
                └── mass   = EI_corr × Wf_amb × eff_t / 1000   [kg]
```

##### Key parameters in the database

| Table | Column | Description |
|-------|--------|-------------|
| `default_aircraft_engine_ei` | `engine_name` | ICAO engine designator |
| `default_aircraft_engine_ei` | `mode` | LTO mode: TX, AP, CL, TO |
| `default_aircraft_engine_ei` | `fuel_kg_sec` | EEDB reference fuel flow (kg/s per engine, SLS) |
| `default_aircraft_engine_ei` | `nox_ei`, `co_ei`, `hc_ei` | EEDB emission indices (g/kg) |
| `default_aircraft_profiles` | `power` | Thrust ratio (0–1) at each profile point |
| `default_aircraft_profiles` | `tas_metres` | True Airspeed (m/s) at each profile point |
| `default_aircraft_profiles` | `z_m` | Altitude above runway (m) at each profile point |
| `default_aircraft_profiles` | `fuel_flow_kgm` | Optional: total-aircraft ambient FF (kg/s); non-zero for ADS-B profiles |
| `default_aircraft_profiles` | `course` | `'CUSTOM'` for ADS-B profiles; ANP designator otherwise |
| `tbl_InvMeteo` | `Temperature` | Ambient temperature (K) |
| `tbl_InvMeteo` | `SeaLevelPressure` | Ambient pressure (Pa) |
| `tbl_InvMeteo` | `RelativeHumidity` | Relative humidity (0–1) |
| `tbl_InvMeteo` | `Humidity` | Specific humidity (kg/kg); used directly if populated |
| `tbl_InvMeteo` | `MixingHeight` | LTO ceiling (m); default 914.4 m (3 000 ft) |

##### LTO ceiling and segment clipping

Only profile segments within the LTO ceiling (default 914.4 m above the runway, stored as `MixingHeight` in `tbl_InvMeteo`) contribute to the emission calculation. Segments entirely above the ceiling are excluded. Segments that cross the ceiling are clipped: the upper endpoint is replaced with a linearly interpolated point at exactly the ceiling altitude, and the geodesic distance and emission mass are scaled accordingly.

---

#### Known limitations

- **No Mach correction for taxi.** Taxiing BFFM2 uses `Mach = 0.0` (as defined by the EEDB measurement conditions for the idle mode), which is correct.

- **Installation corrections are not user-configurable via the UI.** The SAE AIR-5715 defaults are always applied. Custom values require a Python call with an explicit `installation_corrections` dict.

- **ADS-B fuel flow accuracy.** The fuel flow stored in `fuel_flow_kgm` for ADS-B profiles is an estimate derived from aircraft performance models, not a direct measurement. For some engine types (notably certain regional jets) the estimate can be significantly higher than the EEDB TO value, in which case the plugin automatically falls back to the power-setting path. Users should verify the QGIS log for `WARNING` messages after any BFFM2 run involving ADS-B profiles.

- **Straight-line trajectories only.** OpenALAQS currently supports only straight-line departure and arrival tracks. Curved procedures (e.g. SID turns) are approximated as straight lines.

- **Single meteo record per study.** All movements in a study share the same ambient conditions from `tbl_InvMeteo`. Variation in conditions across the study period is not modelled.


