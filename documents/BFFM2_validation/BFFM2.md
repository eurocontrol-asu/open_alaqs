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
    - [Step 5 — PM, SOx and P1/P2 injection](#step-5--pm-sox-and-p1p2-injection)
    - [Step 6 — Segment emission mass](#step-6--segment-emission-mass)
  - [Fuel flow interpolation methods](#fuel-flow-interpolation-methods)
    - [Twin-quadratic fit (ALAQS default)](#twin-quadratic-fit-alaqs-default)
    - [Piecewise-linear interpolation (CAEP14 / ICAO)](#piecewise-linear-interpolation-caep14--icao)
  - [Installation corrections](#installation-corrections)
  - [Humidity correction](#humidity-correction)
  - [MEEM V1 — nvPM ambient correction](#meem-v1--nvpm-ambient-correction)
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

The BFFM2 calculation for a single profile segment proceeds in six steps. Steps 1–4 cover the gas-phase pollutants (NOx, CO, HC); Step 5 covers PM, SOx and the P1/P2 columns; Step 6 computes the emission mass.

---

##### Step 1 — Fuel flow at reference conditions

The power setting `P` (a dimensionless fraction from 0 to 1, where 1 = maximum takeoff thrust) is converted to a reference fuel flow `Wf_ref` at ICAO SLS conditions (T = 288.15 K, p = 101 325 Pa, M = 0) using the twin-quadratic fit described in [Fuel flow interpolation methods](#fuel-flow-interpolation-methods).

The twin-quadratic method applies an idle floor clamp only at very low power settings:

```
if P < 0.07:
    Wf_ref = max(parabola_value, Wf_TX)
```

For P ≥ 0.07 the twin-quadratic value is used directly; the parabola passes through `(0.07, Wf_TX)` by construction, so the unclamped value rarely goes sub-idle in practice. The `mode_anchor` fuel-flow source uses the EEDB anchor fuel flow and needs no clamp.

---

##### Step 2 — Convert to BFFM2 reference fuel flow

The per-engine ambient fuel flow `Wf_amb` (from Step 1, or supplied directly via ADS-B's `fuel_flow_kgm` column) is projected to BFFM2 reference fuel flow using the CAEP14 universal correction:

```
θ = T_amb / 288.15
δ = p_amb / 101 325
M = TAS / SOS

Wf_ref_BFFM2 = (Wf_amb / δ) × θ^3.8 × exp(0.2 × M²)
```

where `SOS = √(γ R T_amb)` (γ = 1.4, R = 287.05287 J/(kg K), ICAO Doc 7488; 340.29 m/s at ISA sea level) is the speed of sound at ambient temperature, as the CAEP validation workbook computes it, and M is the true Mach number at the start of the segment. Until October 2026 the code used the linear form `331.3 + 0.606 × (T_amb − 273.15)`, 0.03 % high at ISA and 0.16 % high at 243.6 K and at 307 K (the coldest and warmest hours of the training meteo); the effect on M² is below 0.4 %, on the results below 0.01 %.

Until October 2026 the code (plugin, standalone and CAEP14 reference implementation) multiplied this by
`√(288.15 / T_amb)`, which is not a Mach number away from ISA; it now computes `TAS / SOS` as written here
(`openalaqs_standalone/validation/tests/test_segment_mach.py`). Mach enters only through `exp(0.2 × M²)`, so the
change is small: on the training fixture's days (280.5 to 295 K) up to 0.08 % on NOx with `bffm2_anchor` and 0.02 % with
`bffm2_traj`, nothing at ISA and nothing for `bymode`.

`Wf_ref_BFFM2` is the value used for the log-log interpolation in Step 3. CAEP14 prescribes this universal form for all flight phases; the older ICAO Doc 9889 Appendix 2 decomposition (separate `δ/√θ` ambient correction at LTO only, followed by a Mach correction at high altitude) is not used. See the inline comments at `bffm2.py:95-99` and `bffm2.py:236-239` for the rationale.

---

##### Step 3 — Emission index interpolation on the log–log curve

The EEDB contains four reference points for each pollutant (NOx, CO, HC): one per LTO mode, expressed as `(Wf_ref_i, EI_i)`. OpenALAQS applies the default **installation correction factors** (see [Installation corrections](#installation-corrections)) to the reference fuel flows before interpolation, shifting the x-axis breakpoints slightly to account for thrust losses due to engine installation effects.

The corrected reference fuel flows and their corresponding EI values are plotted in log₁₀ space. The emission index at `Wf_ref_BFFM2` is obtained by linear interpolation between the two surrounding breakpoints:

```
log10(EI) = log10(EI_i) + [log10(EI_{i+1}) - log10(EI_i)] ×
             [log10(Wf) - log10(Wf_i)] / [log10(Wf_{i+1}) - log10(Wf_i)]
```

**CO / HC special handling.** The CO and HC log-log curves are non-monotonic: EI is high at idle, drops steeply through Approach, and remains approximately flat through Climbout and Takeoff. OpenALAQS applies the CAEP14 v14 "HC_CO Slope To Mean Value" rule: for any fuel flow above the Approach anchor, the EI is snapped to `lin_av`, the linear average of the Climbout and Takeoff anchor EIs. This produces a step discontinuity at the Approach boundary. For engines where the standard shape is not detected (the intersection of the Idle to Approach line with the `lin_av` line falls outside [Approach, Climbout]), the EI is interpolated log-linearly from the Approach anchor to (Climbout FF, `lin_av`) and held at `lin_av` above Climbout.

**Extrapolation capping.** If `Wf_ref_BFFM2` falls below the idle breakpoint, the idle EI is used. If it exceeds the takeoff breakpoint, NOx takes the takeoff EI and CO/HC stay at `lin_av` (mean of the Climbout and Takeoff EIs). No extrapolation beyond the EEDB range is performed.

---

##### Step 4 — Ambient corrections

The raw interpolated EI is corrected for ambient conditions:

**NOx** (SAE AIR-5715 humidity and P₃T₃ correction):

```
h = −19 × (ω − 0.00634)           # humidity coefficient; ω in kg H₂O / kg dry air
EI_NOx_corr = EI_NOx × exp(h) × (δ^1.02 / θ^3.3)^0.5
```

where `ω` is the specific humidity, computed from relative humidity `RH`, ambient temperature and pressure if not provided directly:

```
p_sat = 6.107 × 10^(7.5 × T_C / (237.3 + T_C))   [mbar; T_C in °C]
ω = 0.622 × RH × p_sat / (p_mb − RH × p_sat)
```

At the ICAO reference humidity (ω = 0.00634 kg/kg), `exp(h) = 1` and the humidity term vanishes.

**CO and HC** (temperature and pressure correction only):

```
EI_CO_corr  = EI_CO  × (θ^3.3 / δ^1.02)
EI_HC_corr  = EI_HC  × (θ^3.3 / δ^1.02)
```

---

##### Step 5 — PM, SOx and P1/P2 injection

BFFM2 does not interpolate PM or SOx on a gas-phase log-log curve. Instead, after the gas-phase interpolation in Steps 3–4, the following quantities are injected directly from the mode-level EI stored in the database:

- **`pm10_g_kg`** = `pm10_ei` (total combustion PM10: nonvol + sulphate + organic)
- **`pm10_nonvol_g_kg`** = `pm10_nonvol` (stored value; the MEEM V1 result is computed but not written to any output column, see [MEEM V1](#meem-v1--nvpm-ambient-correction))
- **`pm10_sul_g_kg`** = `pm10_sul` (0.04896 g/kg stored value = FSC 0.068 % × ε 0.024 × 96/32)
- **`pm10_organic_g_kg`** = `pm10_organic`
- **`nvpm_number_kg`** = MEEM V1 value (not written to any output column)
- **`sox_g_kg`** = `sox_ei` (1.32736 g/kg for jet fuel, 0.2 g/kg for AvGas in the shipped `default_aircraft_engine_ei`; 0 or empty is replaced by the fuel's value, `fuel_sulphur.py`)
- **`p1_g_kg`**, **`p2_g_kg`** = `p1_ei` = `p2_ei` = `pm10_ei` (PM1.0 / PM2.5 placeholders, currently equal to PM10)

The MEEM V1 result is stored in `nvpm_g_kg` and `nvpm_number_kg` (`Engine.py:294-295`), which `Emission.add` does not read (`Emissions.py:167-171`); `pm10_kg` and `pm10_nonvol_kg` use the stored EIs.

---

##### Step 6 — Segment emission mass

The emission mass for one profile segment is:

```
mass_pollutant = EI_corr  [g/kg]
              × Wf_amb    [kg/s, per engine]
              × n_engines
              × t_seg     [s]
              / 1000       [→ kg]
```

where the segment time is derived from the geodesic distance between the two profile points and the average True Airspeed at start and end of the segment:

```
t_seg = 2 × d_geodesic / (TAS_start + TAS_end)
```

The geodesic distance is the ellipsoidal ground distance computed by QGIS `QgsDistanceArea.measureLine()` with the ellipsoid set, so it accounts for the map projection and returns true ground distance in metres regardless of the CRS of the emission layer.

---

#### Fuel flow interpolation methods

Step 1 always uses the twin-quadratic fit. The **BFFM2 Fuel-Flow Source** option of the calculation panel chooses between `trajectory` (twin-quadratic at the segment power) and `mode_anchor` (the EEDB fuel flow of the segment's mode).

##### Twin-quadratic fit (ALAQS default)

The LTO thrust range is split into two sub-ranges at the Climbout breakpoint (P = 0.85). A separate quadratic polynomial `Wf = aP² + bP + c` is fitted through three EEDB points in each range:

- **Low range** (0 < P ≤ 0.85): fit through TX (P = 0.07), AP (P = 0.30), CL (P = 0.85)
- **High range** (0.85 < P ≤ 1.00): fit through AP (P = 0.30), CL (P = 0.85), TO (P = 1.00)

Both parabolas pass exactly through their three data points. The idle floor clamp (`max(result, Wf_TX)`) prevents the low-range parabola from returning physically impossible sub-idle values at very low power settings.

This is the original ALAQS method and is the backward-compatible default.

##### Piecewise-linear interpolation (CAEP14 / ICAO)

Piecewise-linear interpolation is not implemented.

> **Note.** For P < 0.07 the twin-quadratic method applies `max(parabola_value, Wf_TX)`. For 1.0 < P ≤ 1.05 the power setting is clamped to 1.0 (with a logged warning) and the high-range parabola is evaluated, effectively returning the TO fuel flow. For P > 1.05 the fit raises `ValueError`; the calculator catches it, logs one warning per movement and uses the mode-anchor EI for that segment.

---

#### Installation corrections

Engine installation in the airframe causes small losses in net thrust and slight changes in fuel flow relative to the bare-engine values measured on the EEDB test stand. BFFM2 accounts for this by multiplying the EEDB reference fuel flow breakpoints by mode-specific installation correction factors *before* the log–log interpolation. This shifts the interpolation x-axis breakpoints without changing the EI y-axis values.

OpenALAQS applies the following default correction factors (CAEP14 default; originally from SAE AIR-5715):

| LTO mode | Installation correction factor |
|----------|-------------------------------|
| Takeoff  | 1.010 |
| Climbout | 1.013 |
| Approach | 1.020 |
| Idle     | 1.100 |

These are applied internally in `bffm2.py` at the start of each call to `calculate_emission_index()` and cannot currently be overridden through the QGIS UI. Custom values can be passed programmatically via the `installation_corrections` dict argument.

The corrections shift the reference fuel flow breakpoints to slightly higher values, which moves the interpolated EI marginally toward lower-fuel-flow (lower-EI for NOx, higher-EI for CO/HC) regions of the curve. The practical effect on total LTO NOx is small, typically 1 to 3 %.

---

#### Humidity correction

The EEDB emission indices for NOx are measured under a standard reference humidity of ω₀ = 0.00634 kg H₂O per kg dry air (as defined in SAE AIR-5715). At other humidity levels, the correction factor is:

```
exp(−19 × (ω − 0.00634))
```

- **ω < 0.00634** (drier than standard): `exp(h) > 1` → NOx correction is positive
- **ω > 0.00634** (more humid than standard): `exp(h) < 1` → NOx correction is negative
- **ω = 0.00634** (standard humidity): no correction

The specific humidity ω is computed from the ambient conditions stored in the `tbl_InvMeteo` table of the `.alaqs` database: always from `RelativeHumidity` (0 to 1), `Temperature` (K) and `SeaLevelPressure` (Pa) with the Magnus saturation vapour pressure formula (`bffm2.py:220-221`). The `Humidity` column is not used by BFFM2 (`Engine.py:645-660` passes temperature, pressure, Mach and relative humidity only).

CO and HC are not corrected for humidity.

---

#### MEEM V1 — nvPM ambient correction

The EEDB nvPM mass and number emission indices are measured at SLS conditions (T = 288.15 K, P = 101 325 Pa, Mach = 0). MEEM V1 (`core/tools/meem_v1.py`, called from `Engine.getEmissionIndexByModeWithMEEM()`) is computed for both Bymode and BFFM2 as follows:

1. The nvPM mass EI is interpolated log-log, and the number EI linearly, on the four EEDB modes (TX, AP, CL, TO; `pm10_nonvol` and `nvpm_number_ei`) at the segment power setting.
2. Above 914 m (`Engine.py:210`) the thrust is first converted to a ground-reference thrust and the enrichment factor is applied:
   ```
   F_GR = F × P3_GR / P3_alt,   P3 = P_total × OPR   (meem_v1.py:154-157, 284-306)
   ```
   OPR is read from `press_ratio`; when it is empty, as in the shipped data, 30 is used (`Engine.py:192`). At or below 914 m the interpolation is at the segment power setting itself, with no pressure dependence (`meem_v1.py:417-442`).

The four 5-point columns (`meem_nvpm_m_i_f00_avg`, `nvpm_m_max_mgkg`, `meem_nvpm_n_i_f00_avg`, `nvpm_n_max_nkg`) are loaded (`EngineDatabases.py:277-280`) but not used by the calculation; they are empty in the shipped data.

The MEEM V1 result is stored in `nvpm_g_kg` and `nvpm_number_kg` (`Engine.py:294-295`). `Emission.add` adds only the `PollutantType` keys (`Emissions.py:167-171`), so this result is not written to any output column; `pm10_nonvol_kg` and `pm10_kg` use the stored EIs.

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

The EEDB CO curve is U-shaped: high at idle (~20–24 g/kg), dropping to a minimum (`lin_av` ~0.2–0.6 g/kg) near Climbout/Takeoff power. Near-idle approach segments get CO EI ≈ idle level in BFFM2, whereas bymode uses the lower AP value (~2–4 g/kg). For departures, both methods give similar CO because most departure segments are at or near TO/CL power where CO EI is at the `lin_av` floor. HC follows the same qualitative pattern.

| Movement type | Typical CO: BFFM2 vs Bymode |
|---------------|------------------------------|
| Arrivals | +18% to +30% |
| Departures | ±2% |

**PM: BFFM2 is lower than Bymode for all movements**

PM and SOx are fuel-proportional (EI is injected from the mode database, not interpolated). BFFM2 computes a different total fuel burn than Bymode because it uses the actual power schedule rather than fixed mode fractions, typically resulting in 12–25% less LTO fuel for EHRD movements. PM and SOx totals scale accordingly.

**Interpretation guideline.** A BFFM2–bymode NOx difference of 20–55% is normal and expected for LTO. A difference outside this range should be investigated. For CO, +15–35% on arrivals and ±2% on departures is normal.

---

#### ADS-B profile specifics

OpenALAQS supports profiles derived from ADS-B recordings in addition to standard ICAO ANP profiles. ADS-B profiles are stored in `default_aircraft_profiles` with `course = 'CUSTOM'`, and their x_m and y_m coordinates represent East and North offsets (in metres) from the runway intersection rather than along-runway distances.

**GeoTransformation.** For CUSTOM profiles, the plugin's `TrajectoryTransformer.runway_alignment()` places each profile point at `runway_intersection + x_m East + y_m North` using geodesic projection on the WGS84 ellipsoid (`computeSpheroidProject`). The resulting EPSG:3857 coordinates are then used for the geometry output. Because EPSG:3857 uses a Mercator projection, the Euclidean distance between two projected points is approximately `sec(latitude)` times the geodesic ground distance. However, OpenALAQS always measures segment distances using `QgsDistanceArea.measureLine()` with the ellipsoid set, which returns the true geodesic distance and is not affected by the Mercator scale factor.

**fuel_flow_kgm column.** ADS-B profiles may have the `fuel_flow_kgm` column populated with the estimated total-aircraft fuel flow in kg/s (sum over all engines), as recorded or derived from the ADS-B data. When this value is non-zero, OpenALAQS uses it in the BFFM2 calculation as follows:

1. The value is divided by the aircraft engine count to obtain the per-engine ambient fuel flow.
2. The per-engine value is compared to 1.5 × the EEDB Takeoff fuel flow (`ADSB_FF_CEILING_FACTOR`, `MovementEmissionCalculator.py:45`).
3. At or below it, the value is passed directly to the BFFM2 interpolation, bypassing the power-setting → twin-quad step.
4. Above it, the segment uses the EEDB fuel flow of its mode (mode anchor), and one warning per movement reports the number of segments (`MovementEmissionCalculator.py:815-824`).

Standard ICAO profiles have `fuel_flow_kgm = 0`, so this logic is inert for those profiles.

> **Important.** The ADS-B fuel flow estimate is derived from aircraft performance models applied to ADS-B position/speed data, not from direct fuel measurement. Its accuracy varies with aircraft type. Always check the QGIS log for `ADS-B ff/engine exceeded the plausibility ceiling` messages, which indicate that the estimate was replaced by the mode-anchor fuel flow on the segments counted.

---

#### Implementation in OpenALAQS

##### Code structure

The BFFM2 implementation is spread across the following files:

| File | Role |
|------|------|
| `core/tools/bffm2.py` | Core formula: ambient corrections, log–log interpolation, CO/HC slope-to-mean-value logic, installation corrections |
| `core/tools/twin_quadratic_fit_method.py` | Power setting → reference fuel flow via twin-quadratic polynomial (Step 1, ALAQS default) |
| `core/tools/meem_v1.py` | MEEM V1 nvPM EI: interpolation on the four EEDB modes; above 914 m, P3 computation and F_GR conversion |
| `core/interfaces/Engine.py` (`EngineEmissionIndex` class) | Orchestrates Steps 1–5: twin-quad call, ambient correction, cache, call to `bffm2.py`; `getEmissionIndexByModeWithMEEM()` applies MEEM V1 |
| `core/MovementEmissionCalculator.py` (`FlightEmissionCalculator` class) | Segment loop: reads profile points, computes Mach, calls `_get_emission_index_bffm2`, computes `t_seg`, calls `Emission.add()` |
| `core/MovementEmissionCalculator.py` (`TaxiingEmissionCalculator` class) | Taxi loop: calls `getEmissionIndexByEngineState()` for gas-phase NOx/CO/HC, then injects PM/SOx/P1/P2 from mode EI |
| `core/modules/MovementSourceModule.py` | `process()` builds the `calc_method` dict and creates the calculators |
| `core/EmissionCalculatorService.py` | Passes `method`, `meem_version`, `bffm2_ff_source` to the source modules |

##### Calculation flow

```
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
                ├── if BFFM2 and fuel_flow > 0:
                │       ff_per_engine = fuel_flow / n_engines
                │       if ff_per_engine ≤ 1.5 × Wf_TO:
                │           use ff_per_engine directly  →  getEmissionIndexByFuelFlow()
                │       else:
                │           use mode-anchor FF (summary warning per movement)
                │
                ├── getEmissionIndexByEngineState(engine_thrust, fuel_flow)
                │       ├── Wf_ref  = twin_quad(engine_thrust, EEDB)
                │       ├── Wf_amb  = Wf_ref × δ / θ^3.8 / exp(0.2 M²)
                │       └── getEmissionIndexByFuelFlow(Wf_amb)
                │               └── calculate_emission_index(pollutant, Wf_amb, EEDB, ambient)
                │                       ├── install corrections → shift EEDB breakpoints
                │                       ├── Wf_ref_BFFM2 = Wf_amb/δ × θ^3.8 × exp(0.2M²)
                │                       ├── log–log interpolation  →  EI_raw
                │                       └── ambient correction  →  EI_corr (NOx/CO/HC)
                │
                ├── _get_emission_index_bffm2(mode, emission_index_bffm2)
                │       ├── mode_ei = getEmissionIndexByModeWithMEEM(mode, P_amb, Mach)
                │       │       └── MEEM V1 (F_GR conversion above 914 m only):
                │       │               log-log interpolation → nvpm_g_kg
                │       │               linear interpolation  → nvpm_number_kg
                │       └── inject into copy of BFFM2 result:
                │               pm10, pm10_nonvol (stored), pm10_sul, pm10_organic,
                │               nvpm_g_kg, nvpm_number_kg (not read by Emission.add),
                │               sox, p1, p2
                │
                ├── d      = ellipsoidal_2d_distance(start_point, end_point)
                ├── t_seg  = 2 × d / (TAS_start + TAS_end)
                ├── eff_t  = t_seg × n_engines
                └── mass   = EI_corr × Wf_amb × eff_t / 1000   [kg]
```

##### Key parameters in the database

| Table | Column | Description |
|-------|--------|-------------|
| `default_aircraft_engine_ei` | `engine_name` | ICAO engine designator |
| `default_aircraft_engine_ei` | `mode` | LTO mode: TX, AP, CL, TO |
| `default_aircraft_engine_ei` | `fuel_kg_sec` | EEDB reference fuel flow (kg/s per engine, SLS) |
| `default_aircraft_engine_ei` | `nox_ei`, `co_ei`, `hc_ei` | EEDB emission indices (g/kg) |
| `default_aircraft_engine_ei` | `pm10_nonvol` | nvPM mass EI (g/kg) |
| `default_aircraft_engine_ei` | `pm10_sul` | Sulphate vPM EI (g/kg); 0.04896 g/kg stored constant (FSC 680 ppm, ε = 0.024, SO4/S = 96/32) |
| `default_aircraft_engine_ei` | `pm10_organic` | Organic vPM EI (g/kg) |
| `default_aircraft_engine_ei` | `pm10_ei` | Total PM10 EI = nonvol + sul + organic (g/kg) |
| `default_aircraft_engine_ei` | `p1_ei`, `p2_ei` | PM1.0 / PM2.5 placeholders; currently = `pm10_ei` |
| `default_aircraft_engine_ei` | `press_ratio` | OPR for MEEM V1 above 914 m (empty in the shipped data; 30 is used) |
| `default_aircraft_engine_ei` | `meem_nvpm_m_i_f00_avg` | nvPM mass EI at F00 (mg/kg); loaded, not used, empty in the shipped data |
| `default_aircraft_engine_ei` | `nvpm_m_max_mgkg` | max nvPM mass EI (mg/kg); loaded, not used, empty in the shipped data |
| `default_aircraft_engine_ei` | `meem_nvpm_n_i_f00_avg` | nvPM number EI at F00 (#/kg); loaded, not used, empty in the shipped data |
| `default_aircraft_engine_ei` | `nvpm_n_max_nkg` | max nvPM number EI (#/kg); loaded, not used, empty in the shipped data |
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

- **MEEM V1 result not in the output.** The MEEM V1 nvPM EIs are stored in `nvpm_g_kg` and `nvpm_number_kg` (`Engine.py:294-295`), which `Emission.add` does not read (`Emissions.py:167-171`). The output uses the stored `pm10_nonvol` and `pm10_ei`.

- **ADS-B fuel flow accuracy.** The fuel flow stored in `fuel_flow_kgm` for ADS-B profiles is an estimate derived from aircraft performance models, not a direct measurement. For some engine types the estimate can be significantly higher than the EEDB TO value; above 1.5 × that value the plugin uses the mode-anchor fuel flow for the segment. Users should verify the QGIS log for warning messages after any BFFM2 run involving ADS-B profiles.

- **Straight-line ANP trajectories.** Standard ANP profiles
  (`course = ANP2.2`) without a track are placed along the runway
  centreline (arrivals touch down at the landing threshold plus the
  runway Touchdown Offset, else the profile's 50 ft crossing
  distance; departures brake-release at the line-up point); with a
  track assigned to the movement they follow the track. ADS-B
  derived profiles (`course = CUSTOM`) are not subject to this
  limitation: their `x_m` and `y_m` columns carry East/North
  geodesic offsets from the runway intersection and can describe
  arbitrary curved trajectories, including SID/STAR turns recorded
  in the source ADS-B data.

- **Meteo per period.** Each time period uses the `tbl_InvMeteo` record nearest in time (`EmissionCalculation.py:122-136`); conditions are constant within a period.
