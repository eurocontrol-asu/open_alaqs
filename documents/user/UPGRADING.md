# Upgrading from an earlier version

This page is for users who open a study made with an earlier version of OpenALAQS. It lists which results change and how to update the study file.

- [Upgrading from 5.4.0](#upgrading-from-540)
- [Upgrading from 5.3.x](#upgrading-from-53x)

## Upgrading from 5.4.0

OpenALAQS 5.4.1 changes the BFFM2 fuel flow and the ambient conditions used at each flight segment's height. The full list is in the [`CHANGELOG`](../../CHANGELOG.md); the atmosphere models are described in [`ATMOSPHERE_ALOFT.md`](../methods/ATMOSPHERE_ALOFT.md).

**Recalculate:**

- **Every BFFM2 inventory** (`bffm2_traj` and `bffm2_anchor`). The fuel flow read on the ICAO curve at the thrust share is now scaled with delta sqrt(theta), and each segment uses the temperature and pressure at its height (default `standard_lapse`). On the example inventory, `bffm2_traj` NOx falls by 11 % and CO2 by 5 %; warm or windy studies can change by more than 10 % in NOx.
- **`bymode` inventories with segments above 3,000 ft** (hours whose mixing height exceeds 914.4 m), for PM10 only: MEEM V1 nvPM now uses the local temperature and pressure (-0.01 % on the example). Fuel, NOx, CO, HC and SOx of `bymode` are unchanged.
- **Engine tests computed with BFFM2** in the plugin (station pressure, fuel-flow scaling).
- **AUSTAL dispersion runs that kept the default site parameters.** The defaults of the AUSTAL module changed (they were 0.2 / 1.2 / 11.2 m); the new defaults are in [Site parameters](DISPERSION_AUSTAL.md#site-parameters). Studies that saved explicit values keep them.

**No setting gives 5.4.0 BFFM2 results back.** "Atmosphere Aloft" = `ground_held` restores the 5.4.0 ambient conditions (the hourly row at every height, the sea-level pressure as the ambient pressure) but not the old fuel-flow scaling, which was wrong and has no switch. Use `ground_held` to see how much of a change comes from the atmosphere.

The option "Atmosphere Aloft" is in the emission calculation dialog, see [Calculate emissions and query results](USER_GUIDE.md#calculate-emissions-and-query-results). Studies themselves need no migration.

**A 5.3.x study migrated with the 5.4.0 script** whose forms still refuse a decimal (field red, "Upgrade the study with scripts/migrate_alaqs.py"), or whose log still says "QGIS types the numeric columns ... as integer or text" when it is opened: run the script of this version on it once more (step 2 of [How to update a study](#how-to-update-a-study)).

## Upgrading from 5.3.x

This section covers a study made with OpenALAQS 5.3.x. A study made with 5.0.x to 5.2.x is updated the same way, see step 2 of [How to update a study](#how-to-update-a-study). The full list of changes is in the [`CHANGELOG`](../../CHANGELOG.md).

The changes of 5.4.1 apply too: a 5.3.x study opened in 5.4.1 also gets the BFFM2, atmosphere aloft and AUSTAL default changes listed there, so also read [Upgrading from 5.4.0](#upgrading-from-540).

### Results that change

Recalculate a study after the upgrade if any of these applies to it:

| Change | Studies affected |
|---|---|
| Runway placement of ANP profiles: arrivals touch down at the landing threshold plus the runway's **Touchdown Offset** (else the profile's own 50 ft crossing), departures start their take-off roll where the taxi route last meets the runway (see [Runways](USER_GUIDE.md#runways)) | every study with ANP arrivals or departures |
| The **Touchdown Offset** of the first-named runway end (`touchdown`) was stored but not used; it is now used, and the second end has its own offset (`touchdown_2`) | studies with a non-zero `touchdown` |
| Arrival `runway_time` is the touchdown (A-CDM ALDT); the landing roll of the profile is taken out of the arrival taxi time (block time minus runway time) | every study with arrivals; check how `runway_time` was filled in |
| A movement whose taxi time comes out at 0 s (block time equal to runway time, or an arrival whose block to runway time is no longer than its landing roll) keeps its APU, stop-and-go and brake-wear emissions; only the route and queuing get no time. It lost all its taxi emissions before | studies with such movements |
| Aircraft SOx comes from the fuel sulphur: 0.758 g/kg for jet fuel, 0.2 g/kg for AvGas (it was 0) | every study with aircraft |
| BFFM2 segment Mach is TAS / a, with a = √(γ R T) | `BFFM2` studies with meteo away from ISA |
| MEEM V1 nvPM above 3000 ft above the aerodrome follows the MEEM V1 method of ICAO CAEP/13-MDG (OPR from `press_ratio`, ISA + ΔT) | hours whose `MixingHeight` is above 914.4 m |
| The NOx ambient correction (**Apply NOx Corrections**, bymode) applies to take-off and climb-out segments only; it was applied to every flight segment | bymode with the correction on: arrival NOx goes up |
| **In Study** (parkings, roadways, point and area sources) is saved from the form; a source drawn through the form in 5.3.x got an empty flag and was left out of the calculation, and unticking the box saved nothing | studies with sources created or edited through the form |
| **Engine Test Site** (area sources) is saved from the form; ticking or unticking it had no effect | studies with engine test sites |
| The airport altitude of aircraft movements (NOx correction, MEEM V1) comes from the study's airport elevation (`user_study_setup`), not from the grid reference altitude | studies where the two differ |
| A taxi route is oriented by its own gate, not by the gate of the first movement that uses it | studies where movements use a route defined for another gate |
| Engine data (`default_aircraft_engine_ei`): FOCA engines from ACT_PRF 2.6.3 (B601 to B603 PM10; turboprops T601, T602, T603, T717 and T790 now jet fuel, SOx 0.758 g/kg), 1ZM001 taxi values (were 0), OPR and 5th nvPM point for MEEM V1 | studies with these engines, once the engine table is refreshed (see below) |
| Standalone `austal`: receptors are clipped to the study grid (they were clipped to a 75 x 250 m square, which dropped receptors inside a larger grid); the UTM zone is the plugin's; the AUSTAL reference point is the grid reference, not the airport | standalone runs with receptors outside that square, in the southern hemisphere or on a zone boundary, or with the grid reference away from the airport |
| `scripts/emissions_austal`: `smooth & shift` and `should_apply_nox_corrections` are read as documented (they could be ignored before) | runs of that script with these settings |

### A study keeps its own engine, aircraft and profile tables

A project `.alaqs` carries its own copies of the reference tables, among them `default_aircraft`, `default_aircraft_engine_ei` and `default_aircraft_profiles`. **Calculate Emissions Inventory** copies them from the open project into every new inventory; the inventory template has none. A study made with 5.3.6 therefore keeps the 5.3.6 engine data after the upgrade:

+ `press_ratio` and the 5th nvPM point are empty, so MEEM V1 uses OPR 30 above 3000 ft;
+ the old FOCA rows (B601 to B603 PM10, turboprops as AvGas) and 1ZM001 with fuel flow and EIs 0 in taxi;
+ `nvpm_number_ei` in #/s instead of #/kg (no output column carries nvPM number).

Only a 0 or empty `sox_ei` is replaced at run time (by 0.758 g/kg for jet fuel, 0.2 g/kg for AvGas, from the row's `fuel_type`).

A study made with 5.3.0 to 5.3.5 also lacks the 5.3.6 corrections of `default_aircraft` and `default_aircraft_profiles` (the ANP v2.2 type profiles and default profiles, see the 5.3.6 entry of the `CHANGELOG`): refreshing the engine table alone (step 2, second command) is enough only for a 5.3.6 study; a 5.3.0 to 5.3.5 study needs the full refresh (step 2, third command), or at least those three tables (`--refresh-reference-data --refresh-tables default_aircraft,default_aircraft_engine_ei,default_aircraft_profiles`).

### How to update a study

1. For a new study, create a new project (**Create an Open ALAQS project**): it is made from the template of this version and has the current tables.
2. For an existing study, update the `.alaqs` with `scripts/migrate_alaqs.py`. The script is not in the plugin zip: run it with Python 3 from a checkout of the repository at this version (it reads the templates and CSVs of that checkout). Close the study in QGIS first. The script writes a backup (`<name>.bak-<timestamp>.alaqs`) unless `--no-backup` is given.
   + Schema only (adds `touchdown_2`, `engine_test_events`, `is_test_site` and the other missing tables and columns, empty, and the three named point-source profiles `heating_season`, `cooling_season` and `business_hours` in the month, day and hour profile tables, with the script's own values, unless a profile of that name exists; a new project has none of them; converts the numeric columns of the layers to `REAL`, see below):
     ```bash
     python scripts/migrate_alaqs.py study.alaqs
     ```
     What the schema step does to the numeric columns of the layers (height, speed, fleet percentages, emission factors, ...):
     - In 5.3.x QGIS could round a decimal typed in a form (2.5 saved as 3) or store it as text ("30,3"). The script converts these columns to numbers. Values are kept; a text that reads as a number becomes that number.
     - Texts it cannot read are listed as `WARNING: <table>.<column>: <n> value(s) are not numbers and are left as text: ...`. Correct them in QGIS. A text such as "1,234" is left too, since it could mean 1.234 or 1234.
     - A study already migrated with the 5.4.0 script needs this step once more; the plan then shows `~ STATISTICS <layer>`.
     - Until the study is migrated, it opens and calculates as before, but the log says "Upgrade the study with scripts/migrate_alaqs.py", and a form refuses a decimal in such a field (field red, tooltip "QGIS would save this value as ...").
   + Schema and the engine table (replaces every row of `default_aircraft_engine_ei`, including rows you added or edited):
     ```bash
     python scripts/migrate_alaqs.py study.alaqs --refresh-reference-data --refresh-tables default_aircraft_engine_ei
     ```
   + Schema and all reference tables, including the user-extensible ones (`default_aircraft`, `default_aircraft_engine_ei`, `default_aircraft_profiles`, `default_aircraft_apu_ef`, `default_aircraft_start_ef`, `default_gate_profiles`, `default_helicopter`, `default_helicopter_engines`):
     ```bash
     python scripts/migrate_alaqs.py study.alaqs --refresh-reference-data --refresh-include-user-extensible
     ```
     This overwrites every row you added or edited in those tables, CUSTOM (ADS-B) profiles stored in the project's `default_aircraft_profiles` included (see [`scripts/README.md`](../../scripts/README.md#migrate_alaqspy)). Add `--dry-run` to see the plan first.
   + A study made with 5.0.x to 5.2.x is updated the same way. The schema step creates its missing tables and columns empty (`default_helicopter` and `default_helicopter_engines`, the 5.2.0 columns of `default_aircraft_engine_ei` and `default_stationary_ef`, `shapes_point_sources.activity_unit`), so such a study needs the full refresh (third command) to get the current helicopter catalog, engine, aircraft and profile data; without it helicopter movements find an empty catalog (the log says "default_helicopter table missing" or lists no helicopters). The refresh reports row counts only ("9243 rows -> 9218 rows (-25)"), not which rows go: a movement file that names a removed CUSTOM profile falls back to the aircraft's default profile with a "Lack of profile_id" warning in the log, so export the profiles you added before refreshing.
   + An existing inventory (`<name>_out.alaqs`) opens and calculates in **Visualize Emission Calculation** without migration (checked here for inventories made with 5.0.0 to 5.4.0; it keeps the engine and profile tables it was made with, and the results do not change with the migration). `python scripts/migrate_alaqs.py <name>_out.alaqs` updates it with the inventory template, selected from the `_out.alaqs` suffix; its `grid_3d_definition` and `cache_runway_trajectories` tables, which every inventory has and the template does not, are reported as extra and left in place.
3. Check **Touchdown Offset, Runway 1 [m]** and **Touchdown Offset, Runway 2 [m]** of each runway (`touchdown_2` is empty after the migration: each arrival profile's own distance), **In Study** of the stationary sources and **Engine Test Site** of the area sources.
4. Generate the inventory again (**Calculate Emissions Inventory**) with the ADS-B file, if any: the ADS-B tracks are imported into the new inventory, and at an airport with a non-zero elevation the points of the take-off roll and of the landing are now set to the ground (height 0).
5. Recalculate (**Visualize Emission Calculation**).

## See also

- [User guide](USER_GUIDE.md): the plugin windows named on this page.
- [`scripts/README.md`](../../scripts/README.md#migrate_alaqspy): all options of the migration script.
- [Ambient conditions aloft](../methods/ATMOSPHERE_ALOFT.md): the atmosphere models of 5.4.1.
