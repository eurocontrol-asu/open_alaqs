# Aircraft profile catalogue: provenance (ANP v2.2)

This document records where the rows of
`open_alaqs/database/data/default_aircraft_profiles.csv` and the default
profile columns of `open_alaqs/database/data/default_aircraft.csv` come from,
what was corrected in the amendment of October 2026, and how to reproduce it.

Last updated: 2026-10-12.

## 1. Sources

* **ANP database v2.2** (EUROCONTROL, release of 22 February 2018): aircraft,
  default weights, fixed-point profiles, procedural steps, engine coefficients
  and the substitution workbook "ANP v2.2 Aircraft substitutions - jets &
  heavy props (22022018)". No other ANP release is used.
* **ECAC Doc 29, 5th edition, Volume 2**, Appendix B: the performance model
  behind the procedural profiles (used here to check the table, not to
  recompute it).
* **The 5.3.5 tables** (git revision `c8a55cd`, md5 `c15a3e26...` and
  `ad1c2604...`), and the history of the profile CSV, in particular the
  version before commit `ab42da5` (2024-09-26).

The table carries no build tool from before 2026. Its x, z and TAS were
produced from ANP v2.2 at ISA, sea level, 15 °C, no wind, with an
implementation of Doc 29 Appendix B, as these checks show:

| Check | Result |
|---|---|
| Fixed-point profiles: x, z, TAS and power against `Default_fixed_point_profiles.csv` (ft x 0.3048, kt x 0.514444, power = setting / static thrust) | 76 profiles exact (to 1e-6); `757300-A-1` exact against the pre-`ab42da5` table |
| Jet departures: brake-release power against (E + 15 H) / static thrust | 382 of 524 within 0.001, 95% within 0.005 |
| Lift-off TAS against C·√W (take-off flap, stage weight, sea level) | 311 of 322 within 1 kt |
| Departure thrust at every point against eq. B-9 (jets) and B-12 (propellers), ISA | 114 aircraft, 5,240 points: median ratio 1.0001 (TO), 0.9997 (CL); every aircraft within 1% except ECLIPSE500 (0.982) |
| 7378MAX and A350-941 procedures | departures follow `ICAO_A`; `A350-941-A-1` follows `DEFAULT1` |
| Stage `M` | stored as `-D-0` (7373B2, 737400, 737500, 7378MAX, A350-941) |
| Departure weights | equal the v2.2 stage weight (lb x 0.453592) wherever present |
| Arrival weights | equal the v2.2 stage-1 departure weight (134 of 134 arrivals that had one) |

The geometry is therefore kept as it is; the amendment corrects only what is
listed in section 2.

## 2. Corrections (October 2026)

1. **Type profiles restored.** Commit `ab42da5` created the 48 group profiles
   (`JET-*`, `PISTON-*`, `TURBOPROP-*`) by renaming type profiles. The table
   before that commit holds each source with identical rows. The 47 type IDs
   that disappeared (including every profile of GIIB, HS748A and PA30) are
   restored as copies of their group, placed just before it. The two A330
   arrivals: `JET-LARGE-A-1` = `A330-343-A-1`, `JET-MEDIUM-A-1` =
   `A330-301-A-1`. The full list is `GROUP_SOURCE` in the builder.
2. **`757300-A-1` restored.** Commit `e9b087b` renamed its first 27 rows, so
   it started at 50 ft. It is rebuilt from the v2.2 fixed points (31 points),
   identical to the pre-`ab42da5` rows.
3. **`CNA206-D-1`.** In ANP v2.2 the CNA206 `DEFAULT` fixed-point departure,
   labelled stage 1, is point for point the `3600LB` departure (stage 3,
   3,600 lb, = `CNA206-D-3`), while the stage-1 weight is 3,000 lb. The old
   row set was the `DEFAULT` profile. It is rebuilt from `3000LB`, as
   `CNA20T-D-1` already was.
4. **Power** (`power` = corrected net thrust / max sea-level static thrust):
   * `CNT (% of Max Static Thrust)` aircraft (17): the stored value was the
     percentage divided by the static thrust. It is multiplied by
     static thrust / 100. Checks: the departures then match eq. B-12 (median
     ratio 0.997), and the approach decelerate points equal the ANP
     `Start Thrust` / 100 for all 17 aircraft.
   * RPM aircraft (CNA206, CNA20T, PA28, PA31): the stored value was RPM /
     static thrust. Power is left empty. The plugin then uses the by-mode
     emission index for those segments (BFFM2 trajectory) and does not read
     power otherwise.
   * Values above 1.0 are capped at 1.0 (196 points in 110 profiles; the
     largest were propeller thrust at low speed, up to 1.51 for DHC830, and
     777300 at brake release, 1.14). Before, BFFM2 trajectory mode rejected
     the 23 profiles with values above 1.05 and fell back to the mode-anchor
     emission index.
5. **Weights** filled where empty (73 profiles), with the v2.2 stage weight
   for departures (`M` for `-D-0`) and the stage-1 weight for arrivals.
6. **Groups.** Every group keeps its ID and is a copy of its source after the
   corrections above. Three groups had a source of another propulsion class
   and now copy a same-class profile: `PISTON-D-1` = `CNA172-D-1` (was
   ECLIPSE500, a jet), `PISTON-D-2` = `PA31-D-1` (was CNA208, a turboprop;
   PA31 is an RPM aircraft, so this group has no power), `TURBOPROP-D-4` =
   `EMB120-D-1` (was IA1125, a jet).
7. **Type defaults** (`default_aircraft.csv`, columns `departure_profile`,
   `arrival_profile`). Before, every type pointed to a group. Now:
   * (a) 184 types in the substitution workbook ("by ICAO code" tab): the
     `ANP_PROXY`. For the 21 codes with variants, the variant that matches
     the type's default engine when the engine identifies one, otherwise the
     first row (`VARIANT_CHOICE` in the builder gives the basis per code).
   * (b) 474 other types with an MTOW, a fixed-wing class (first letter L, A
     or S) and propulsion J, T or P: the ANP v2.2 aircraft with the same
     engine type and engine count (the `engine_count` column; VC10 has 4
     there and 2 in its class string) and the nearest MTOW.
   * (c) 1,261 types keep their group: 1,252 have no MTOW, the rest have no
     same-class ANP aircraft (single-engine jets, a three-engine piston) or
     are not fixed-wing.
   Departures use stage 1 (`<proxy>-D-1`), arrivals `<proxy>-A-1`. Engines
   are not changed. The mapping, with rule and basis per type, is
   `tools/anp22_profiles/output/default_aircraft_mapping.csv`.

8. **ANP 2.1 profiles removed.** COMJET, DHC-2FLT and GASEPF (13 profiles,
   137 rows, `course` = `ANP2.1`) are not ANP v2.2 aircraft. No type
   defaulted to them, no committed `.alaqs` used them outside the profile
   table, and they had no weight and no power. Existing studies keep their
   own copy of the table; in a new study, a movement that names one of them
   gets the aircraft's default profile, with a warning.

Unchanged: all modes (except in the rebuilt `CNA206-D-1`, which keeps the
old mode sequence), `course` (`ANP2.2`, now on every row), and every other
profile ID that existed before.

## 3. Effect

* Profiles: 797 to 831 IDs, 8,806 to 9,218 rows (47 IDs restored, 13 ANP
  2.1 IDs removed). The x, z, TAS and mode of
  every profile that existed are unchanged, except `757300-A-1`,
  `CNA206-D-1`, `PISTON-D-1`, `PISTON-D-2` and `TURBOPROP-D-4`.
* `PISTON-D-1` (default for most light aircraft until now) climbed like a
  jet: 94 s below 914 m. As CNA172 it takes 300 s.
* Movements without a `profile_id` now get a type-specific profile for 658
  types (rules a and b), e.g. B738 `737800-D-1` instead of `JET-SMALL-D-4`
  (A321-232 stage 1), C172 `CNA172-D-1` instead of `PISTON-D-1`.
* 196 types default to an RPM aircraft (PA28, CNA206, PA31), so their
  segments have no power and BFFM2 trajectory mode uses the by-mode emission
  index there, with a warning per segment.

## 4. Reproducing

```bash
python3 tools/anp22_profiles/build_anp22_profiles.py --anp-dir /path/to/anp_v2_2
python3 tools/test_fixtures/regenerate_default_aircraft_profiles.py
python3 tools/test_fixtures/regenerate_default_aircraft.py
```

The builder reads the 5.3.5 tables from git revision `c8a55cd` (md5 checked)
and the ANP v2.2 tables from `--anp-dir`. The ANP tables are not in the
repository. Output md5 for the inputs above: profiles `16160d7c...`, aircraft
`4e36bcc1...`. Checks that need only the committed CSVs are in
`tests/test_default_aircraft_profiles_anp22.py`.

The fixture scripts update the seven `.alaqs` files listed in them. They keep
study-specific rows (CUSTOM ADS-B profiles, HELIPROF rows, extra types) and
drop the removed ANP 2.1 profiles. The
ANP and AIRPORT_A fixtures have their own `default_aircraft` (other engines
and names), so only their profile tables are updated. The standalone
validation databases (`openalaqs_standalone/validation/data/`) are snapshots
and are not changed.

## 5. Open points

* ANP terms of use for redistributing derived profiles.
* Modes of fixed-point departures are kept as they were (e.g. `777300-D-1`
  switches to CL at 1,565 ft, before its thrust cutback).
* Arrival placement in the plugin (touchdown on the taxi-route exit) is a
  code issue, not a data one.
