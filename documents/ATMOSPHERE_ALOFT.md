# Ambient conditions aloft (OpenALAQS 5.4.1)

OpenALAQS 5.4.1 computes the temperature, pressure and humidity at each flight segment's height from the study's hourly meteo row (`tbl_InvMeteo`, usually from METAR). Until 5.4.0 the hourly ground values were used unchanged at every height up to the emission ceiling, with the sea-level pressure (QNH) as the ambient pressure.

The option is `atmosphere_model`. The code is `open_alaqs/core/tools/surface_layer_atmosphere.py`, shared by the plugin, the standalone and the CAEP14 reference implementation.

| `atmosphere_model` | Temperature aloft | Pressure | Humidity |
| --- | --- | --- | --- |
| `standard_lapse` (default) | 2 m temperature − 6.5 K/km (ISA lapse rate) | station pressure from QNH and the airport elevation, hydrostatic | humidity ratio of the ground air kept |
| `surface_layer` | AUSTAL 3.3 boundary-layer profile (`BlmTemp`) from the hour's wind, Obukhov length and mixing height | as above, with that profile | as above |
| `ground_held` | the 2 m temperature at every height (5.4.0) | QNH at every height (5.4.0) | the row's relative humidity (5.4.0) |

**Why `standard_lapse` is the default.** An earlier 5.4.1 candidate had `surface_layer` as the default. A check against the De Bilt radiosondes of 2025 (section 6) found the AUSTAL profile about 1 to 3 K too cold within the emission ceiling. It was not more accurate than the ISA lapse rate, and the ISA lapse rate needs neither the stability inputs nor the heat-flux bound. Both models get the fuel-flow factor δ√θ within 0.3 to 0.7 % RMS of the soundings, against 1.2 to 12.9 % for the ground row held. In summer the AUSTAL profile is the closer one above 300 m, so a summer study can choose `surface_layer` (section 6).

**`ground_held` is not 5.4.0.** It restores the 5.4.0 ambient conditions only; the 5.4.1 fuel-flow fix (δ√θ) has no switch.

## 1. Inputs

| Input | Source | Used by |
| --- | --- | --- |
| `Temperature` (K) | `tbl_InvMeteo`, hourly | all models: 2 m temperature ta |
| `SeaLevelPressure` (Pa) | `tbl_InvMeteo` (QNH) | station pressure |
| `RelativeHumidity` (0 to 1) | `tbl_InvMeteo` | humidity ratio of the ground air |
| `WindSpeed` (m/s), `ObukhovLength` (m), `MixingHeight` (m) | `tbl_InvMeteo` | `surface_layer` (u*, stability, top of the stability term); `MixingHeight` is also the emission ceiling, unchanged |
| Airport elevation (m) | `user_study_setup.airport_elevation` | station pressure |
| z0, d0, ha (m) | the study's AUSTAL settings | `surface_layer` only |

**Site parameters** (`surface_layer` only). One default everywhere (`surface_layer_atmosphere.site_parameters`): z0 = 0.1 m (the TA Luft value for airports), d0 = 6 z0 (0.6 m), ha = 10 m + d0 (10.6 m); d0 and ha are derived from z0 whenever they are left empty. How to choose them is in the user guide, [Roughness length, displacement height and anemometer height](USER_GUIDE.md#roughness-length-displacement-height-and-anemometer-height).
- **Plugin:** the AUSTAL module's `roughness_length_m`, `displacement_height_m` and `anemometer_height_m` (0 in a spin box means "derive from z0"); without an AUSTAL module, the defaults.
- **Standalone `aircraft` subcommand and the headless runner:** `--z0`, `--d0`, `--ha` (`atmosphere_z0_m`, `atmosphere_d0_m`, `atmosphere_ha_m`); the same defaults.
- **Standalone `austal` subcommand, `austal_prep` and Dataiku:** the AUSTAL configuration's `z0`, `d0` and `ha`, used for the AUSTAL input and the emissions alike; the same defaults.

## 2. Formulas

Heights h are in metres above the airport; negative heights are taken as 0.

### 2.1 Station pressure (all aloft models)

QNH is reduced to the airport elevation with the ISA relation that defines QNH:

```
p_stn = QNH * (1 - 0.0065 * elevation / 288.15) ^ 5.25588
```

The correction against 5.4.0 is +0.05 % at an airport at −4.6 m and about +22 % in δ at a 1,650 m airport.

### 2.2 `standard_lapse`

```
T(h) = ta - 0.0065 h
ln p(h) = ln p_stn - (g0 / R) ∫0^h dz / T(z)        g0 = 9.80665, R = 287.053
```

The integral uses the trapezoidal rule on a 5 m grid from 0 to 3,000 m, computed once per hourly row and cached; ln p is interpolated linearly between grid points. Above 3,000 m it continues with the closed form. Against the analytic ISA solution the error is below 1 × 10⁻⁸.

### 2.3 `surface_layer`

**Friction velocity.** AUSTAL's first estimate (`u2lInitialize`, `TalBlm.c`): the wind speed at the anemometer height divided by the simple Prandtl profile per unit u* (`StdUuPrandtl`), with z = ha − d0 and κ = 0.4:

```
L > 0:  u/u* = [ ln(z/z0) + 5 (z - z0)/L ] / kappa
L < 0:  u/u* = [ 2 (atan(x) - atan(x0)) + ln( (x0+1)^2 (x0^2+1) z / ((x+1)^2 (x^2+1) z0) ) ] / kappa
        x = (1 - 15 z/L)^(1/4),  x0 = (1 - 15 z0/L)^(1/4)
```

AUSTAL refines u* iteratively only when the first layer of its two-layer wind model lies below the anemometer; that refinement is not reproduced. An `ObukhovLength` of 0 or missing is treated as neutral (L = 99,999 m), as in AUSTAL.

**Temperature** (`BlmTemp`, `TalBlm.c`, boundary-layer version 0; the AUSTAL manual does not give the formula):

```
z    = h - d0             (z = 6 z0 if h < d0 + 6 z0)
T*   = ta / (kappa g) * u*^2 / L                                    g = 9.8066 m/s2
T(h) = ta + (T*/kappa) [ Theta(z, L) - Theta(2 m, L) ]
          - 9.766557 K/km * (z - 2)                                  for z < 200 m
          - 9.766557 K/km * (200 - 2) - 8.5 K/km * (z - 200)         for z >= 200 m
```

| Range (ζ = z/L) | Theta |
| --- | --- |
| L > 0, ζ < 0.5 | ln ζ + 5ζ − 7 ln 2 + 4 |
| L > 0, 0.5 ≤ ζ < 10 | 8 ln ζ + 4.25/ζ − 0.5/ζ² |
| L > 0, ζ ≥ 10 | 0.7585 ζ + 8 ln 10 − 7.165 |
| L < 0 | ln\|ζ\| − 2 ln(1 + √(1 − 15ζ)) |

**Top of the stability term.** The formula applies up to the hour's mixing height. In stable hours it applies at most up to AUSTAL's stable mixing height (`getHm`): 0.3 u*/f · sqrt(f L/u*) when that root is below 1, between 20 and 800 m, with f = 1.1 × 10⁻⁴ 1/s. Above that height the temperature continues at −8.5 K/km. A missing, NaN or non-positive mixing height keeps the `getHm` cap.

**Heat-flux bound** (OpenALAQS, not AUSTAL). u* and L imply a surface sensible heat flux:

```
H = -rho cp ta u*^3 / (kappa g L)
```

- **Why a bound is needed.** A meteo file can hold combinations no real surface layer has. The training fixtures' 2 December row (15 m/s with L = −50 m) implies about 9 kW/m², and the profile would be 24 K colder than the ground at 300 m.
- **The bound.** When |H| exceeds 600 W/m² (L < 0) or 100 W/m² (L > 0), L is replaced by the value that gives the bounded flux with the row's wind (u* recomputed, iterated), and a warning is logged once per row and process.
- **What the limits are.** Engineering limits, not AUSTAL or VDI 3783 values. AUSTAL's `TalBlm.h` defines limits on 1/L that no AUSTAL 3.3.0 source file uses (searched).
- **Rows from the METAR converter.** `scripts/metar_to_alaqs_meteo.py` assigns L per Pasquill-Gifford class, independent of the wind, so the strongest winds of each unstable class can exceed the bound. This is suspected as the main source of bounded hours, not checked in the converter.

**Departures from AUSTAL.** AUSTAL uses `BlmTemp` only for plume rise, with a fixed ambient temperature of 10 °C and 70 % at 2 m (manual 3.3, section 3.4). That value can be changed once per run with the NOSTANDARD option `Ta=`. Using the profile with hourly temperatures is an OpenALAQS extension:

| Detail | AUSTAL `BlmTemp` | OpenALAQS |
| --- | --- | --- |
| T* | fixed 283.15 K | hour's ta |
| Limits | profile held between −30 °C and +40 °C | none |
| Height range | any height | stability term up to the mixing height (stable: at most `getHm`), then −8.5 K/km |
| Below 2 m | height from d0, floor 6 z0 | ta; the profile steps at 2 m (up to 0.3 K) and is back at ta at d0 + 2 m |
| Heat flux | not bounded | bounded at 600 / 100 W/m² |

`blm_temperature(..., austal_exact=True)` is the unmodified port, kept for the comparison with AUSTAL's code.

### 2.4 Humidity (both aloft models)

Water vapour is conserved: the humidity ratio of the ground air is kept at every height.

```
omega = 0.62197058 RH p_sat(ta) / (p_stn - RH p_sat(ta))
RH(h) = omega p(h) / (p_sat(T(h)) (0.62197058 + omega))
```

p_sat is the BFFM2 saturation formula, 6.107 · 10^(7.5 t / (237.3 + t)) mbar. RH(h) only carries ω into BFFM2, which converts it back exactly. It exceeds 1 in a layer that would be saturated (section 7).

### 2.5 Input checks

- **Stopping errors.** A temperature or sea-level pressure that is not a positive number, a profile temperature outside 180 to 340 K, or invalid site parameters (z0 ≤ 0, d0 < 0, ha ≤ d0) stop the run. The message names the meteo row's date and, for a bounded hour, the row's own L.
- **ISA meteo stays ISA at every height.** This applies to the standalone `--isa-meteo` and to a period without a `tbl_InvMeteo` row.

## 3. Where OpenALAQS uses it

| Calculation | Height | 5.4.0 | 5.4.1 (`standard_lapse`, `surface_layer`) |
| --- | --- | --- | --- |
| Flight segments: Mach (TAS / speed of sound) | segment start | ground T | T(h) |
| `bffm2_traj` fuel flow, ff_ref · δ · √θ | segment start | (old scaling) ground T, QNH | T(h), p(h) |
| BFFM2 NOx, CO and HC indices (both BFFM2 methods) | segment start | ground T, QNH, RH | T(h), p(h), RH(h) |
| BFFM2 taxi, roll | 0 | ground T, QNH | ta, p_stn |
| `bymode` fuel and indices; `bffm2_anchor` fuel | | ICAO mode values | unchanged |
| MEEM V1 nvPM above 3,000 ft (all methods, `bymode` included) | segment start | CAEP sheet: ISA + ΔT at altitude | T(h), p(h); ΔT not used |
| `bymode` ICCAIA NOx correction (option) | | ground row | unchanged |
| BFFM2 engine tests (plugin) | 0 | ground T, QNH | ta, p_stn |
| Engine tests, standalone `austal` pipeline | | ICAO mode values ("snap") | unchanged ("snap") |
| Emission ceiling | | `MixingHeight` | unchanged |

## 4. Effect on BFFM2 NOx: why the two BFFM2 methods can move in opposite directions

The BFFM2 NOx index is `EI_ref(ff_ref) · e^h · (δ^1.02 / θ^3.3)^0.5`, with `ff_ref = ff_amb / δ · θ^3.8 · e^(0.2M²)` read on the engine's log-log curve.

- **`bffm2_traj`:** the ambient fuel flow itself is scaled with δ√θ. Colder, thinner air lowers the fuel and moves ff_ref only a little. NOx falls with any aloft model.
- **`bffm2_anchor`:** the ICAO anchor fuel flow is used unscaled as the ambient fuel flow. Colder air lowers ff_ref through θ^3.8 and moves the reading down the curve. On a steep leg this lowers the index far more than the ambient factor θ^−1.65 raises it.

On the fixture engine (LEAP-1A26, 13.4 g/kg at 0.71 kg/s and 30.8 g/kg at 0.861 kg/s), at the take-off anchor and 283 K, the NOx index changes as follows:

| Change of the ambient | NOx index |
| --- | --- |
| 1 K colder | −5.2 % |
| 3 K colder | −14.8 % |
| 5 % lower pressure | +22 % |

At 293 K the same anchor sits past the take-off point, where the curve is flat, and the effect is under 2 %. The sensitivity depends on where ff_ref lands on the curve.

Totals against the ground row held, training fixture `training_v3` and example inventory:

| NOx | `standard_lapse` | `surface_layer` |
| --- | --- | --- |
| `bffm2_traj`, training_v3 | −2.9 % | −3.3 % |
| `bffm2_anchor`, training_v3 | +1.2 % | −1.0 % |
| `bffm2_traj`, example | −4.6 % | −5.2 % |
| `bffm2_anchor`, example | +0.6 % | −1.1 % |

The colder `surface_layer` profile turns the anchor result negative. This is BFFM2 as specified, applied to a fixed anchor fuel flow, not a defect. It does make `bffm2_anchor` NOx aloft sensitive to temperature errors: a 1 to 3 K error moves a take-off-anchor segment by 5 to 15 %.

## 5. Consistency with AUSTAL

- **Same:** the hourly wind, Obukhov length and mixing height drive both the dispersion and `surface_layer`, except in hours bounded by the heat flux. There the emissions use the replaced L while the AUSTAL time series keeps the row's L.
- **Not used by AUSTAL:** the temperature. AUSTAL disperses with its fixed 10 °C, which enters only its plume-rise model PLURIS. PLURIS runs only for sources with a diameter and exit velocity (`dq`, `vq`), and OpenALAQS writes neither.
- **Concentrations do not depend on this choice.** The "smooth & shift" source dynamics use fixed extents per aircraft group and stage, independent of the atmosphere. AUSTAL's concentrations do not depend on temperature or pressure.

## 6. Check against the De Bilt radiosondes (2025)

**Method:**

1. **Data.** De Bilt (WMO 06260, IGRA2 station NLM00006260, the Netherlands) from the NOAA NCEI IGRA2 archive: 450 soundings of 2025 with a surface level and data above 1 km; 354 at 00 UTC, 88 at 12 UTC.
2. **Heights.** Computed hypsometrically from pressure, temperature and dew-point depression. Checked against the geopotential heights reported at 925 and 850 hPa: mean −0.8 m, sd 2.4 m, at most 6 m.
3. **Observed values.** T(z) − T(surface) at 100, 300, 600 and 900 m, interpolated between significant levels. WMO significant levels are chosen so that linear interpolation stays within about 1 K.
4. **Model.** Each model driven by the hourly meteo row (converted from METAR) of an airport about 50 km from De Bilt, for the same UTC hour, with site parameters z0 0.3 m, d0 1.2 m, ha 11.2 m (the standalone `austal` defaults at the time; the 5.4.1 defaults are 0.1 / 0.6 / 10.6 m, section 1). The airport's 2 m temperature is on average 0.4 K warmer than De Bilt's surface (sd 1.6 K). The comparison uses differences from each site's own surface.
5. **Scripts.** The check scripts are not part of the repository; the soundings are public (IGRA2).

**Results within the emission ceiling** (bias / RMS in K, model minus observed):

| Height | n | `standard_lapse` | `surface_layer` | ground row held |
| --- | --- | --- | --- | --- |
| 100 m | 450 | −1.3 / 2.9 | −1.5 / 2.8 | −0.7 / 2.6 |
| 300 m | 206 | +0.3 / 1.4 | −1.2 / 1.7 | +2.3 / 2.7 |
| 600 m | 67 | +1.9 / 2.6 | −1.9 / 2.6 | +5.8 / 6.1 |
| 900 m | 34 | +2.0 / 3.1 | −2.7 / 3.5 | +7.8 / 8.2 |

**By time of day** (within the ceiling):

| Time | Height | n | `standard_lapse` | `surface_layer` | ground row held |
| --- | --- | --- | --- | --- | --- |
| 00 UTC | 100 m | 354 | −1.9 / 3.2 | −1.7 / 3.0 | −1.3 / 2.8 |
| 00 UTC | 300 m | 113 | −0.5 / 1.2 | −1.3 / 1.7 | +1.4 / 1.8 |
| 12 UTC | 100 m | 88 | +0.9 / 1.1 | −1.0 / 1.5 | +1.5 / 1.6 |
| 12 UTC | 300 m | 88 | +1.4 / 1.7 | −1.1 / 1.6 | +3.4 / 3.5 |
| 12 UTC | 600 m | 65 | +1.9 / 2.6 | −1.9 / 2.6 | +5.8 / 6.1 |
| 12 UTC | 900 m | 33 | +2.0 / 3.2 | −2.8 / 3.5 | +7.9 / 8.2 |

**By season** (within the ceiling, RMS in K; n in brackets). The all-year result does not hold in summer:

| Season | 100 m: `standard_lapse` / `surface_layer` | 300 m | 600 m | 900 m |
| --- | --- | --- | --- | --- |
| Winter (DJF) | 1.9 / 1.8 (110) | 1.3 / 1.8 (64) | 2.1 / 3.6 (10) | 1.5 / 2.0 (1) |
| Spring (MAM) | 3.8 / 3.7 (115) | 1.7 / 1.4 (37) | 2.7 / 2.1 (22) | 3.0 / 3.8 (16) |
| Summer (JJA) | 3.0 / 2.9 (113) | 1.7 / 1.6 (44) | 3.0 / 1.9 (21) | 3.6 / 2.3 (11) |
| Autumn (SON) | 2.4 / 2.3 (112) | 1.3 / 1.7 (61) | 1.9 / 3.1 (14) | 2.4 / 4.5 (6) |
| July and August only | 2.9 / 2.8 (76) | 1.7 / 1.5 (27) | 3.0 / 1.5 (15) | 3.8 / 1.6 (8) |

In summer, and above all at 600 and 900 m in daytime convective hours, the AUSTAL profile is closer to the soundings (`surface_layer` closer in 81 to 93 % of those cases). The ISA lapse is then about 3 K too warm, because the convective layer follows the dry adiabat. In winter and autumn the ISA lapse is closer. The summer advantage rests on few soundings above 300 m (8 to 21); in fuel-flow terms it is worth at most 0.2 percentage points of RMS.

**Fuel-flow factor** δ√θ at height relative to the ground, model against observed, RMS within the ceiling:

| Height | `standard_lapse` | `surface_layer` | ground row held |
| --- | --- | --- | --- |
| 100 m | 0.5 % | 0.5 % | 1.2 % |
| 300 m | 0.3 % | 0.3 % | 4.1 % |
| 600 m | 0.5 % | 0.5 % | 8.5 % |
| 900 m | 0.6 % | 0.7 % | 12.9 % |

**Reading:**

- **The large part of 5.4.1 is confirmed.** It is the pressure drop with height, from the station pressure and hydrostatics: the ground row held is off by 1 to 13 % in the fuel-flow factor.
- **The temperature shape is a second-order matter for fuel.**
  - The AUSTAL profile is systematically too cold over the year.
  - The ISA lapse is too warm by day, when the convective layer is near the dry adiabat, and too cold near the ground at night (inversions).
  - Their all-year RMS errors are similar; in summer daytime aloft the AUSTAL profile is better, in winter and autumn the ISA lapse.
  - Neither meets 1.5 K RMS at 900 m over the year.
- **Choice of the default.** `standard_lapse` was chosen on the all-year result, its smaller bias, and because it needs no stability inputs. A summer study with daytime traffic can justify `surface_layer` on the summer numbers above. The effect on fuel is below 0.2 points either way; on NOx it is larger (section 4).
- **The 100 m errors are dominated by night-time surface inversions** (+1.3 K observed on average at 00 UTC), which none of the models reproduces.
- **For NOx the temperature matters more.** The BFFM2 ambient factor moves by about 0.6 % per K, and a `bffm2_anchor` take-off segment by up to 5 % per K (section 4).

**Limits of the check:**
- one station, about 50 km inland;
- 78 % of the soundings at night, while most flights are by day;
- interpolation between significant levels;
- the airport's row and the De Bilt sounding describe slightly different air.

## 7. Limitations

- **Saturated layers.** The ground humidity ratio is kept at every height (the engine ingests the total water). The relative humidity passed to BFFM2 exceeds 1 in a layer that would be saturated, and the lapse rate there stays dry (`surface_layer`) or ISA, where the real lapse is moist adiabatic (about 5 to 6 K/km).
  - At 900 m (regardless of the ceiling), `surface_layer` gives RH > 1 in 385 of the 450 De Bilt cases, while the soundings show a saturated layer (dew-point depression ≤ 1 K) below 900 m in 233.
  - Capping ω at saturation would raise the NOx index of such segments by several per cent (about +7 % for ω from 0.0146 to 0.011).
  - Neither treatment is validated.
- **Above the mixing height,** `surface_layer` continues at −8.5 K/km to any height, and `standard_lapse` at −6.5 K/km. Emissions stop at the mixing height unless the vertical limit is raised above it.
- **No validation against measured fuel or NOx.**
- **Not tested:** whole years outside 2025; airports at altitude.

## 8. Code validation

- **AUSTAL C code.** `BlmTemp`, `getTheta`, `StdUuPrandtl` and `getHm`, copied verbatim from AUSTAL 3.3.0 `TalBlm.c` and compiled, agree with the port to 7 × 10⁻⁵ K over 2,592 cases (`tests/test_surface_layer_atmosphere.py` pins the C values).
- **Hydrostatics.** Against the analytic ISA solution: 1 × 10⁻⁸.
- **Parity.** Plugin, standalone and CAEP14 reference agree to 4 × 10⁻¹¹ for every model.
- **Tests.** Bounds, degenerate inputs and plumbing: `tests/test_atmosphere_review_541.py`.

## 9. History

| Date | Step |
| --- | --- |
| 23 October 2026 | `surface_layer` introduced as default. An external review confirmed the formulas against AUSTAL's code and noted that AUSTAL never evaluates them with hourly temperatures. |
| 23 October | Audit: heat-flux bound, missing mixing height, site-parameter validation, ISA meteo, engine-test pressure. |
| 24 October | Independent reviews: the anchor sign (section 4), saturation and documentation. De Bilt sounding check (section 6), then `standard_lapse` made the default. |

## Sources

- AUSTAL 3.3.0 source code: `TalBlm.c` (`BlmTemp`, `getTheta`, `StdUuPrandtl`, `u2lInitialize`, `getHm`), `TalBlm.h`.
- AUSTAL 3.3 Programmbeschreibung (2024-03-22), section 3.4 (fixed ambient 10 °C and 70 %), footnote 34 (`Ta=`), section 3.5.2 (time series).
- NOAA NCEI, Integrated Global Radiosonde Archive version 2 (IGRA2), station NLM00006260 (De Bilt), `data-por` file downloaded 24 October 2026.
- SAE AIR5715 / CAEP14 BFFM2 (`open_alaqs/core/tools/bffm2.py`).
