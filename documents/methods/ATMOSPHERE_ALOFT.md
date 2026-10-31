# Ambient conditions aloft

This page describes how OpenALAQS computes the temperature, pressure and humidity at each flight segment's height, for modellers who use BFFM2 or MEEM V1. The values come from the study's hourly meteo row (`tbl_InvMeteo`, usually from METAR). The `ground_held` option instead uses the hourly ground values unchanged at every height up to the emission ceiling, with the sea-level pressure (QNH) as the ambient pressure.

The option is `atmosphere_model`. The code is `open_alaqs/core/tools/surface_layer_atmosphere.py`, shared by the plugin, the standalone and the CAEP14 reference implementation.

| `atmosphere_model` | Temperature aloft | Pressure | Humidity |
| --- | --- | --- | --- |
| `standard_lapse` (default) | 2 m temperature − 6.5 K/km (ISA lapse rate) | station pressure from QNH and the airport elevation, hydrostatic | humidity ratio of the ground air kept |
| `surface_layer` | AUSTAL 3.3 boundary-layer profile (`BlmTemp`) from the hour's wind, Obukhov length and mixing height | as above, with that profile | as above |
| `ground_held` | the 2 m temperature at every height | QNH at every height | the row's relative humidity |

**Why `standard_lapse` is the default.** A check against the De Bilt radiosondes of 2025 ([validation evidence](../developer/design/ATMOSPHERE_ALOFT_VALIDATION.md)) found the AUSTAL profile about 1 to 3 K too cold within the emission ceiling. It was not more accurate than the ISA lapse rate, and the ISA lapse rate needs neither the stability inputs nor the heat-flux bound. Both models get the fuel-flow factor δ√θ within 0.3 to 0.7 % RMS of the soundings, against 1.2 to 12.9 % for the ground row held. In summer the AUSTAL profile is the closer one above 300 m, so a summer study can choose `surface_layer`.

**`ground_held` changes the ambient conditions only.** The fuel flow is still scaled with δ√θ ([Scaling to the ambient](AIRCRAFT_EMISSIONS.md#scaling-to-the-ambient)), which has no switch.

## Inputs

| Input | Source | Used by |
| --- | --- | --- |
| `Temperature` (K) | `tbl_InvMeteo`, hourly | all models: 2 m temperature ta |
| `SeaLevelPressure` (Pa) | `tbl_InvMeteo` (QNH) | station pressure |
| `RelativeHumidity` (0 to 1) | `tbl_InvMeteo` | humidity ratio of the ground air |
| `WindSpeed` (m/s), `ObukhovLength` (m), `MixingHeight` (m) | `tbl_InvMeteo` | `surface_layer` (u*, stability, top of the stability term); `MixingHeight` is also the emission ceiling, unchanged |
| Airport elevation (m) | `user_study_setup.airport_elevation` | station pressure |
| z0, d0, ha (m) | the study's AUSTAL settings | `surface_layer` only |

**Site parameters** (`surface_layer` only). z0, d0 and ha are the AUSTAL site parameters (default z0 = 0.1 m, d0 = 6 z0, ha = 10 m + d0; d0 and ha are derived from z0 when left empty). How to choose and set them: [site parameters](../user/DISPERSION_AUSTAL.md#site-parameters); standalone options: [USAGE.md](../../openalaqs_standalone/USAGE.md).

## Formulas

Heights h are in metres above the airport; negative heights are taken as 0.

### Station pressure (all aloft models)

QNH is reduced to the airport elevation with the ISA relation that defines QNH:

```
p_stn = QNH * (1 - 0.0065 * elevation / 288.15) ^ 5.25588
```

Compared with QNH as the ambient pressure (`ground_held`), δ at the ground rises by 0.05 % at an airport at −4.6 m and falls by about 18 % at a 1,650 m airport (QNH overstates δ there by about 22 %).

### `standard_lapse`

```
T(h) = ta - 0.0065 h
ln p(h) = ln p_stn - (g0 / R) ∫0^h dz / T(z)        g0 = 9.80665, R = 287.053
```

The integral uses the trapezoidal rule on a 5 m grid from 0 to 3,000 m, computed once per hourly row and cached; ln p is interpolated linearly between grid points. Above 3,000 m it continues with the closed form. Against the analytic ISA solution the error is below 1 × 10⁻⁸.

### `surface_layer`

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

**Top of the stability term.** The formula applies up to the hour's mixing height. In stable hours it applies at most up to AUSTAL's stable mixing height (`getHm`): 0.3 u*/f · sqrt(f L/u*) when that root is below 1, between 20 and 800 m, with f = 1.1 × 10⁻⁴ 1/s. Above that height the temperature continues at −8.5 K/km. A missing or non-finite mixing height, or one of 2 m or less (0, −999 and NaN are common missing codes; `_clean_mixing_height`), keeps the `getHm` cap.

**Heat-flux bound** (OpenALAQS, not AUSTAL). u* and L imply a surface sensible heat flux:

```
H = -rho cp ta u*^3 / (kappa g L)
```

- **Why a bound is needed.** A meteo file can hold combinations no real surface layer has. The training fixtures' 2 December row (15 m/s with L = −50 m) implies about 9 kW/m², and the profile would be 24 K colder than the ground at 300 m.
- **The bound.** When |H| exceeds 600 W/m² (L < 0) or 100 W/m² (L > 0), L is replaced by the value that gives the bounded flux with the row's wind (u* recomputed, iterated), and a warning is logged once per row and process.
- **What the limits are.** Engineering limits, not AUSTAL or VDI 3783 values. AUSTAL's `TalBlm.h` defines limits on 1/L that no AUSTAL 3.3.0 source file uses (searched).
- **Rows from the METAR converter.** `scripts/metar_to_alaqs_meteo.py` assigns L per Pasquill-Gifford class, independent of the wind, so the strongest winds of each unstable class can exceed the bound ([open question](../developer/design/ATMOSPHERE_ALOFT_VALIDATION.md#open-questions)).

**Departures from AUSTAL.** AUSTAL uses `BlmTemp` only for plume rise, with a fixed ambient temperature of 10 °C and 70 % at 2 m (manual 3.3, section 3.4). That value can be changed once per run with the NOSTANDARD option `Ta=`. Using the profile with hourly temperatures is an OpenALAQS extension:

| Detail | AUSTAL `BlmTemp` | OpenALAQS |
| --- | --- | --- |
| T* | fixed 283.15 K | hour's ta |
| Limits | profile held between −30 °C and +40 °C | none |
| Height range | any height | stability term up to the mixing height (stable: at most `getHm`), then −8.5 K/km |
| Below 2 m | height from d0, floor 6 z0 | ta; the profile steps at 2 m (up to 0.3 K) and is back at ta at d0 + 2 m |
| Heat flux | not bounded | bounded at 600 / 100 W/m² |

`blm_temperature(..., austal_exact=True)` is the unmodified port, kept for the comparison with AUSTAL's code.

### Humidity (both aloft models)

Water vapour is conserved: the humidity ratio of the ground air is kept at every height.

```
omega = 0.62197058 RH p_sat(ta) / (p_stn - RH p_sat(ta))
RH(h) = omega p(h) / (p_sat(T(h)) (0.62197058 + omega))
```

p_sat is the BFFM2 saturation formula, 6.107 · 10^(7.5 t / (237.3 + t)) mbar. RH(h) only carries ω into BFFM2, which converts it back exactly. It exceeds 1 in a layer that would be saturated ([Limitations](#limitations)).

### Input checks

- **Stopping errors.** A temperature or sea-level pressure that is not a positive number, a profile temperature outside 180 to 340 K, or invalid site parameters (z0 ≤ 0, d0 < 0, ha ≤ d0) stop the run. The message names the meteo row's date and, for a bounded hour, the row's own L.
- **ISA meteo stays ISA at every height.** This applies to the standalone `--isa-meteo` and to a period without a `tbl_InvMeteo` row.

## Where OpenALAQS uses it

| Calculation | Height | `ground_held` | `standard_lapse`, `surface_layer` |
| --- | --- | --- | --- |
| Flight segments: Mach (TAS / speed of sound) | segment start | ground T | T(h) |
| `bffm2_traj` fuel flow, ff_ref · δ · √θ | segment start | ground T, QNH | T(h), p(h) |
| BFFM2 NOx, CO and HC indices (both BFFM2 methods) | segment start | ground T, QNH, RH | T(h), p(h), RH(h) |
| BFFM2 taxi (fuel ff_ref · δ · √θ and indices, both BFFM2 methods), roll | 0 | ground T, QNH | ta, p_stn |
| `bymode` fuel and indices; `bffm2_anchor` fuel on flight segments | | ICAO mode values | unchanged |
| MEEM V1 nvPM above 3,000 ft (all methods, `bymode` included) | segment start | MEEM V1: ISA + ΔT at altitude | T(h), p(h); ΔT not used |
| `bymode` ICCAIA NOx correction (option) | | ground row | unchanged |
| BFFM2 engine tests (plugin) | 0 | ground T, QNH | ta, p_stn |
| Engine tests, standalone `austal` pipeline | | ICAO mode values ("snap") | unchanged ("snap") |
| Emission ceiling | | `MixingHeight` | unchanged |

## Effect on BFFM2 NOx

This section explains why the two BFFM2 methods can move in opposite directions.

The BFFM2 NOx index is `EI_ref(ff_ref) · e^h · (δ^1.02 / θ^3.3)^0.5`, with `ff_ref = ff_amb / δ · θ^3.8 · e^(0.2M²)` read on the engine's log-log curve.

- **`bffm2_traj`:** the ambient fuel flow itself is scaled with δ√θ. Colder, thinner air lowers the fuel and moves ff_ref only a little. NOx falls with any aloft model.
- **`bffm2_anchor`:** on flight segments the ICAO anchor fuel flow is used unscaled as the ambient fuel flow (taxi segments are scaled as with `bffm2_traj`). Colder air lowers ff_ref through θ^3.8 and moves the reading down the curve. On a steep leg this lowers the index far more than the ambient factor θ^−1.65 raises it.

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

## Consistency with AUSTAL

- **Same:** the hourly wind, Obukhov length and mixing height drive both the dispersion and `surface_layer`, except in hours bounded by the heat flux. There the emissions use the replaced L while the AUSTAL time series keeps the row's L.
- **Not used by AUSTAL:** the temperature. AUSTAL disperses with its fixed 10 °C, which enters only its plume-rise model PLURIS. PLURIS runs only for sources with a diameter and exit velocity (`dq`, `vq`), and OpenALAQS writes neither.
- **Concentrations do not depend on this choice.** The "smooth & shift" source dynamics use fixed extents per aircraft group and stage, independent of the atmosphere. AUSTAL's concentrations do not depend on temperature or pressure.

## Limitations

- **Saturated layers.** The ground humidity ratio is kept at every height (the engine ingests the total water). The relative humidity passed to BFFM2 exceeds 1 in a layer that would be saturated, and the lapse rate there stays dry (`surface_layer`) or ISA, where the real lapse is moist adiabatic (about 5 to 6 K/km).
  - At 900 m (regardless of the ceiling), `surface_layer` gives RH > 1 in 385 of the 450 De Bilt cases, while the soundings show a saturated layer (dew-point depression ≤ 1 K) below 900 m in 233.
  - Capping ω at saturation would raise the NOx index of such segments by several per cent (about +7 % for ω from 0.0146 to 0.011).
  - Neither treatment is validated.
- **Above the mixing height,** `surface_layer` continues at −8.5 K/km to any height, and `standard_lapse` at −6.5 K/km. Emissions stop at the LTO ceiling, normally the hour's mixing height ([LTO ceiling](AIRCRAFT_EMISSIONS.md#lto-ceiling-and-segment-clipping)).
- **No validation against measured fuel or NOx.**
- **Not tested:** whole years outside 2025; airports at altitude.

## Validation

The check against the De Bilt radiosondes and the code validation (AUSTAL C code, hydrostatics, parity) are in [ATMOSPHERE_ALOFT_VALIDATION.md](../developer/design/ATMOSPHERE_ALOFT_VALIDATION.md).

## Sources

- AUSTAL 3.3.0 source code: `TalBlm.c` (`BlmTemp`, `getTheta`, `StdUuPrandtl`, `u2lInitialize`, `getHm`), `TalBlm.h`.
- AUSTAL 3.3 Programmbeschreibung (2024-03-22), section 3.4 (fixed ambient 10 °C and 70 %), footnote 34 (`Ta=`), section 3.5.2 (time series).
- NOAA NCEI, Integrated Global Radiosonde Archive version 2 (IGRA2), station NLM00006260 (De Bilt), `data-por` file downloaded 24 October 2026.
- SAE AIR5715 / CAEP14 BFFM2 (`open_alaqs/core/tools/bffm2.py`).

## See also

- [AIRCRAFT_EMISSIONS.md](AIRCRAFT_EMISSIONS.md): BFFM2, MEEM V1 and the fuel flow that use these values
- [DISPERSION_AUSTAL.md](../user/DISPERSION_AUSTAL.md#site-parameters): site parameters z0, d0 and ha
- [ATMOSPHERE_ALOFT_VALIDATION.md](../developer/design/ATMOSPHERE_ALOFT_VALIDATION.md): validation evidence
