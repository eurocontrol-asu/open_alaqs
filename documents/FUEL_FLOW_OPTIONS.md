# Fuel flow of the BFFM2 trajectory method: findings and proposed changes

October 2026. This note records what an ADS-B comparison showed about the
fuel-flow step of the `bffm2_traj` method and the changes proposed as a
result. O2 is implemented in 5.4.1 (section 3); the others are not. The
effects quoted for O1 and O2 were measured with a prototype in the
standalone.

## 1. The step in question

The trajectory method turns a profile point into emissions in three steps:

1. thrust at the point: the ANP net thrust share of the standard profile, or
   the thrust supplied with an ADS-B (CUSTOM) track;
2. fuel flow at the point: the ICAO engine databank curve (the four
   certification points, twin-quadratic interpolation) read at that thrust
   share, then scaled to ambient with the corrected-parameter scaling of
   gas-turbine performance, `ff_amb = ff_ref · δ · √θ` (until 5.4.0 the
   inverse of the BFFM2 relation, `ff_ref · δ / θ^3.8 / e^(0.2 M²)`, see
   section 3); δ and θ are those at the point's height
   (`atmosphere_model`, default `standard_lapse`, from 5.4.1; see
   `ATMOSPHERE_ALOFT.md`); or, for a CUSTOM track that
   carries `fuel_flow_kgm`, the supplied value (per engine, plausibility
   ceiling 1.5 × the take-off value);
3. emission indices: BFFM2 (SAE AIR-5715 / CAEP), `ff_ref` from the ambient
   fuel flow, log-log lookup, ambient and humidity corrections.

Step 3 is what the CAEP validation checks (section 4). Step 2 is not covered
by it: the CAEP validation takes the engine fuel flow as an input.

## 2. What the ADS-B comparison showed

Basis: five days of ADS-B tracks at a regional airport (NEEDED project,
July and August 2025), each track delivered with a per-point thrust and a
fuel flow from an aircraft-performance model, and the same movements run
through the three OpenALAQS methods. Details and figures are in the
project's own material; the findings that matter for the code:

- F1. The ICAO databank curve is a static test-bed curve. Read at an
  in-flight net thrust it under-states the fuel flow: at the same thrust
  the method's fuel was 23 to 34 % below the performance model's
  (737-800 take-off / climb / approach medians 0.73 / 0.68 / 0.66, A320
  0.77 / 0.70 / 0.75).
- F2. A speed factor `(0.4 + 0.45 M) / 0.4`, the Mach dependence of the
  thrust-specific fuel consumption of a high-bypass turbofan, removes most
  of the gap (737-800 0.94 / 0.95 / 0.83); scaling the fuel mass with the
  engine-similarity factor `δ √θ` instead of the BFFM2 factors removes the
  rest and the day-to-day spread (1.00 / 0.93 / 0.86; the spread of the
  take-off and climb medians across days falls from 0.20 to 0.02).
- F3. At inventory level the default looks right on departures because two
  errors cancel: the ANP profiles fly the full rated take-off thrust (the
  tracked flights lifted off at about 74 % of it) while the curve
  under-reads the fuel. Departures, five days pooled, method over
  performance model: fuel 0.81 (default), 0.98 (speed factor), 1.12
  (both); NOx 0.76, 1.15, 1.38.
- F4. The two mode methods (ICAO LTO, mode anchor) are high everywhere:
  fuel 1.11 to 1.22, NOx 1.38 to 1.48 of the performance model.
- F5. On concentrations the methods differ by a few percent within 1 km of
  the airport and by at most 0.5 µg/m³ at any monitoring station; road
  traffic dominates there.
- F6. A supplied fuel flow from a performance model is not usable below
  about Mach 0.2 (take-off roll, landing roll): at brake release the
  thrust is about 80 % of rated and the model fuel flow 15 % of the
  take-off value.
- F7. A few arrival tracks carry a speed step at a flap transition (about
  50 kt in 6 to 8 s of track time) that a thrust inversion turns into a
  large negative thrust and an implausible fuel flow.

## 3. Options O1 and O2

Status (5.4.1): O2 is the shipped behaviour, without a switch. It is a fix:
the inverse BFFM2 relation is an emission-index conversion, not a fuel-flow
model, and gave the wrong sign with temperature; `δ √θ` is the
corrected-parameter scaling of gas-turbine performance (the corrected fuel
flow, fuel flow / (δ √θ), is a function of the corrected thrust, thrust / δ,
and Mach). O1 is not shipped. The table describes the prototype.

| Option | What it would do |
| --- | --- |
| O1 speed correction | the fuel flow read from the ICAO curve at the ANP thrust share multiplied by `(0.4 + 0.45 M) / 0.4`, M the flight Mach `TAS / a(T)`, above idle (share > 0.08), not on the landing roll; supplied fuel flows, taxiing and the other methods unchanged |
| O2 similarity scaling | the ICAO-curve fuel flow scaled to ambient with `δ √θ` instead of `δ / θ^3.8 / e^(0.2 M²)`; the BFFM2 index step keeps its own conversion |

Effect of the prototype on the training fixture (`bffm2_traj`, ISA,
relative to the options off): O1 raised CO₂ by 7.6 to 13 % and NOx by 15 to
79 %; O2 at ISA only drops the `e^(0.2 M²)` term (0.4 to 0.6 % CO₂), with the
fixture's cold and warm days −7 to +8 %.

The NOx response of O1 depends on the engine's index curve between
climb-out and take-off. On the A20N departure (01P20CM128, a staged lean-burn
combustor: 13.38 g/kg at climb-out, 30.80 g/kg at take-off, log-log slope
4.3) O1 lifts four of the five airborne segments above the take-off fuel
flow, where BFFM2 caps the index at the take-off value: of the +1.88 kg NOx,
0.30 kg came from the extra fuel and 1.58 kg (84 %) from the index. With the
same fuel change and a take-off index on the approach-to-climb-out slope
(14.45 g/kg) the response was +22.5 %; the E190 (11GE144, slope 1.0) gave
+26.5 %. For staged combustors the BFFM2 log-log interpolation between the
two upper ICAO points therefore amplifies the effect of O1 on NOx.

O1 would not act on the take-off roll: the roll is one profile segment whose
Mach is read at its start point (brake release, TAS 0), so the factor is 1
there.

Why O1 and O2 are not defaults, nor shipped as options yet:

- At inventory level two errors cancel today (F3): the ANP departures fly
  full rated thrust while the static curve under-reads the fuel. O1 and O2
  alone remove one of the pair; on the five ADS-B days departure NOx goes
  from −24 % (default) to +38 % (both options) of the performance model.
  They belong together with O3.
- The evidence compares with a performance model (Poll-Schumann), whose own
  temperature form is `δ √θ`-like, not with measured fuel; a check against
  flight-recorder fuel is open.
- The source of the `(0.4 + 0.45 M) √θ` TSFC trend (textbook design trend)
  is to be confirmed, and the take-off roll is not covered.

## 4. Validation

- CAEP validation, index step: `calculate_emission_index` reproduces the
  CAEP reference results for the LEAP-1A24 case at a non-LTO point (lean
  burn, v2 indices, exponent 0.3: EI NOx 60.2017 g/kg) and at an LTO point
  (standard indices, exponent 0.5: 17.6525 g/kg), CO and HC to 1e-14, the
  reference fuel flow to 1e-9. Pinned in
  `openalaqs_standalone/validation/tests/test_caep14_sheet_reference_case.py`.
- Fuel-flow step as shipped: plugin = reference = standalone on the 15
  fixture movements (`test_plugin_csv_vs_reference.py`), O2 included since
  5.4.1.

Procedure and numbers: `openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md`.

## 5. Proposed changes (O2 implemented in 5.4.1, the others not)

| ID | Change | Default | Where |
| --- | --- | --- | --- |
| O1, O2 | the two options of section 3 (O2 shipped in 5.4.1 as the behaviour, not an option), in the plugin (`MovementEmissionCalculator`, a checkbox pair in the calculation dialog), the standalone and the reference implementation | off | `open_alaqs/core`, `open_alaqs/gui`, `openalaqs_standalone` |
| O3 reduced take-off thrust | scale the take-off roll and initial climb thrust of an ANP departure profile by a per-type factor (evidence: 0.74 for the 737-800), or use ANP reduced-thrust procedures where ANP has them; removes the second half of the cancelling pair of F3 | off | profile handling, a `default_aircraft` column |
| O4 runway rule for supplied fuel flows | a CUSTOM point below Mach 0.2 with a fuel flow flagged out of range takes the ICAO curve at its thrust share with O1, capped at take-off (F6); today done upstream by the study that supplies the track | on for flagged points | ADS-B loader, `compute_aircraft` supplied-fuel-flow path |
| O5 plausibility floor | a CUSTOM point with thrust share below −0.05 is marked unreliable: thrust 0, supplied fuel flow replaced by the near-idle value, counted in the run diagnostics; the delivered value is kept between −0.05 and 0 (idle at speed) (F7) | on | same loader, `runway_checks.csv`-style diagnostics |
| O6 ceiling logging | keep the 1.5 × take-off ceiling on supplied fuel flows; log the points that hit it | as is | `compute_aircraft` |
| O7 documentation | this note, the user guide and the changelog once O1 to O5 are decided; the alternatives examined and not adopted: BADA (licence), pycontrails Poll-Schumann (Mach ≥ 0.2, one average engine per type), OpenAP (no speed term), Acropole (neural network, no thrust input) | | `documents/` |
| O8 fuel-flow source switch | for CUSTOM tracks, choose between the supplied fuel flow and the supplied thrust through the ICAO curve with O1 and O2, so a track supplier's thrust can be used without its fuel model; on the two days run (5 July and 5 August), the thrust-only chain on the static curve gave fuel 11 % and NOx 23 % below the supplied fuel on departures; with the speed factor, fuel within 1 to 1.4 % and NOx within 1.4 to 3.9 % | supplied | `compute_aircraft`, loader, dialog |

What stays in every case: the three methods, the BFFM2 index step, taxi at
the ICAO idle point, the study engine per movement.
