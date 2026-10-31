# Atmosphere aloft: validation evidence

This page holds the checks behind the atmosphere models of [ATMOSPHERE_ALOFT.md](../../methods/ATMOSPHERE_ALOFT.md): the comparison with the De Bilt radiosondes and the validation of the code. It is for maintainers and reviewers; the models, their inputs and limitations are described on the methods page.

## Check against the De Bilt radiosondes (2025)

**Method:**

1. **Data.** De Bilt (WMO 06260, IGRA2 station NLM00006260, the Netherlands) from the NOAA NCEI IGRA2 archive: 450 soundings of 2025 with a surface level and data above 1 km; 354 at 00 UTC, 88 at 12 UTC.
2. **Heights.** Computed hypsometrically from pressure, temperature and dew-point depression. Checked against the geopotential heights reported at 925 and 850 hPa: mean −0.8 m, sd 2.4 m, at most 6 m.
3. **Observed values.** T(z) − T(surface) at 100, 300, 600 and 900 m, interpolated between significant levels. WMO significant levels are chosen so that linear interpolation stays within about 1 K.
4. **Model.** Each model driven by the hourly meteo row (converted from METAR) of an airport about 50 km from De Bilt, for the same UTC hour, with site parameters z0 0.3 m, d0 1.2 m, ha 11.2 m (not the current defaults of 0.1 / 0.6 / 10.6 m). The airport's 2 m temperature is on average 0.4 K warmer than De Bilt's surface (sd 1.6 K). The comparison uses differences from each site's own surface.
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

- **The main effect is confirmed.** It is the pressure drop with height, from the station pressure and hydrostatics: the ground row held is off by 1 to 13 % in the fuel-flow factor.
- **The temperature shape is a second-order matter for fuel.**
  - The AUSTAL profile is systematically too cold over the year.
  - The ISA lapse is too warm by day, when the convective layer is near the dry adiabat, and too cold near the ground at night (inversions).
  - Their all-year RMS errors are similar; in summer daytime aloft the AUSTAL profile is better, in winter and autumn the ISA lapse.
  - Neither meets 1.5 K RMS at 900 m over the year.
- **Choice of the default.** `standard_lapse` was chosen on the all-year result, its smaller bias, and because it needs no stability inputs. A summer study with daytime traffic can justify `surface_layer` on the summer numbers above. The effect on fuel is below 0.2 points either way; on NOx it is larger ([effect on BFFM2](../../methods/ATMOSPHERE_ALOFT.md#effect-on-bffm2-nox)).
- **The 100 m errors are dominated by night-time surface inversions** (+1.3 K observed on average at 00 UTC), which none of the models reproduces.
- **For NOx the temperature matters more.** The BFFM2 ambient factor moves by about 0.6 % per K, and a `bffm2_anchor` take-off segment by up to 5 % per K ([effect on BFFM2](../../methods/ATMOSPHERE_ALOFT.md#effect-on-bffm2-nox)).

**Limits of the check:**
- one station, about 50 km inland;
- 78 % of the soundings at night, while most flights are by day;
- interpolation between significant levels;
- the airport's row and the De Bilt sounding describe slightly different air.

## Code validation

- **AUSTAL C code.** `BlmTemp`, `getTheta`, `StdUuPrandtl` and `getHm`, copied verbatim from AUSTAL 3.3.0 `TalBlm.c` and compiled, agree with the port to 7 × 10⁻⁵ K over 2,592 cases; that comparison harness is not in the repository. `tests/test_surface_layer_atmosphere.py` pins 4 of the C cases: u* to a relative 1 × 10⁻⁶ and the temperature at 4 heights each (16 values) to 2 × 10⁻⁴ K.
- **Hydrostatics.** Against the analytic ISA solution: 1 × 10⁻⁸.
- **Parity.** Plugin, standalone and CAEP14 reference agree to 4 × 10⁻¹¹ for every model.
- **Tests.** Bounds, degenerate inputs and plumbing: `tests/test_atmosphere_review_541.py`.

## Open questions

- **Bounded hours from METAR meteo.** `scripts/metar_to_alaqs_meteo.py` assigns the Obukhov length per Pasquill-Gifford class, independent of the wind, so the strongest winds of each unstable class can exceed the heat-flux bound of `surface_layer` ([heat-flux bound](../../methods/ATMOSPHERE_ALOFT.md#surface_layer)). This is suspected as the main source of bounded hours; it has not been checked in the converter.

## Sources

- AUSTAL 3.3.0 source code: `TalBlm.c` (`BlmTemp`, `getTheta`, `StdUuPrandtl`, `getHm`).
- NOAA NCEI, Integrated Global Radiosonde Archive version 2 (IGRA2), station NLM00006260 (De Bilt), `data-por` file downloaded 24 October 2026.

## See also

- [ATMOSPHERE_ALOFT.md](../../methods/ATMOSPHERE_ALOFT.md): the atmosphere models
- [AIRCRAFT_EMISSIONS.md](../../methods/AIRCRAFT_EMISSIONS.md): where BFFM2 and MEEM V1 use them
