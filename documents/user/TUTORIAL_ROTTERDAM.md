# Tutorial: a study of Rotterdam The Hague Airport

This tutorial walks through a complete OpenALAQS study of Rotterdam The Hague Airport (EHRD) with the training data shipped with OpenALAQS. It is for new users of the QGIS plugin. It gives the values to enter and the results to expect; what each window and setting does is explained in the [User Guide](USER_GUIDE.md) and the pages linked from each step.

**What you will build.** A study of three days of operations at EHRD: 13 aircraft movements over three gates and both runway directions, plus a car park, an access road, a power plant and the terminal as stationary sources. You will create the emission inventory, calculate emissions with two methods and compare them, and run a dispersion calculation with AUSTAL.

**Files used.** The training files in `example/training`, listed in [README, Quick start](../../README.md#quick-start-with-the-training-example). `training_out.alaqs` is the finished inventory, to compare with yours; `training_validation_reference.xlsx` holds the reference emissions per movement, per hour and per source type.

Contents:
- [1. Create the study](#1-create-the-study)
- [2. Import OpenStreetMap data (optional)](#2-import-openstreetmap-data-optional)
- [3. Aircraft sources](#3-aircraft-sources)
- [4. Stationary sources](#4-stationary-sources)
- [5. Activity profile exercise](#5-activity-profile-exercise)
- [Generate Emissions Inventory](#generate-emissions-inventory)
- [Calculate emissions](#calculate-emissions)
- [Dispersion with AUSTAL](#dispersion-with-austal)

To start from the finished study instead of building it, click **Load an Open ALAQS project** on the toolbar and open `training.alaqs`. It already holds all sources and the taxi routes: continue at [Create the inventory](#create-the-inventory).

## 1. Create the study

Click **Create an Open ALAQS project** and save the new study, for example as `training.alaqs` in a folder of your own. In the *ALAQS Project Properties* window enter (see [Starting a study](USER_GUIDE.md#starting-a-study)):

| Field | Value |
|---|---|
| Project Name | OpenALAQS Training Course |
| **Airport tab** | |
| ICAO Code | EHRD |
| Name | Rotterdam |
| Country | NL |
| Latitude (decimal) | 51.9574278 |
| Longitude (decimal) | 4.4417028 |
| Airport Elevation AMSL | -5 m |
| Average Temperature | 15 °C |
| **Roadways tab** | |
| Average Fleet Year | 2020 |
| Country | Netherlands |

When you enter `EHRD`, the name, country, coordinates and elevation are filled in from the internal database (stored as -15 ft, shown as -5 m). Enter Average Temperature by hand. Leave **Vertical Limit** as it is: the plugin does not use it ([LTO ceiling](../methods/AIRCRAFT_EMISSIONS.md#lto-ceiling-and-segment-clipping)). Click **Save**. The source layers (Gates, Runways, Taxiways, ...) appear empty in the QGIS layers panel.

## 2. Import OpenStreetMap data (optional)

With the QuickOSM plugin installed, click **Import OSM data**. The aerodrome is found from the ICAO code and the coordinates of the saved study. Tick **Selective import** and choose **Runways** and **Taxiways** (unticked, every layer type is imported). Tick **Also import the data into ALAQS database**; without it the data only appear in an *OpenStreetMap Layers* group and the study layers stay empty. See [Import OpenStreetMap data](USER_GUIDE.md#import-openstreetmap-data). Then check in the attribute tables that:

- each taxiway has its own **Taxiway Name**;
- every **Speed [km/h]** is between about 15 and 30;
- the **Runway Name** is `06/24`.

OSM data varies in quality: compare it with the aerodrome chart and fix duplicates or geometry. Or skip this step and draw the sources yourself as below.

## 3. Aircraft sources

Draw each source with the QGIS digitizing tools and fill in its form ([Define emission sources](USER_GUIDE.md#define-emission-sources)). Turn on snapping so that gates touch taxiways and taxiway segments meet: gaps break the taxi routes.

**Gates.** Three polygons around the stands, each touching a taxiway:

| Gate Name | Gate Type | Where |
|---|---|---|
| G2 | CARGO | cargo apron, south of the terminal |
| G4 | REMOTE | remote stand, reached by bus |
| G7 | PIER | pier stand at the terminal |

The gate type selects the ground support and ground power emission factors.

**Runway.** One line along the runway centreline over the full pavement, from one end to the other (the bundled geometry runs from the 24 end to the 06 end):

| Field | Value |
|---|---|
| Runway 1 | 06 (Runway 2 = 24 and **Runway Name** = 06/24 are filled in) |
| **Touchdown Offset, Runway 1 [m]** | 250 |
| **Touchdown Offset, Runway 2 [m]** | 250 |

Each movement names the runway end it uses (`06` or `24`). With a touchdown offset of 250 m, arrivals cross the threshold at about 13 m on a 3° approach.

**Taxiways.** One line per segment along the centreline:

| Taxiway Name | Speed [km/h] |
|---|---|
| B, F, N, V, V0, V1, V1E, V2, V3, V6, Y | 15 |
| Y1, Y2 | 30 |

V0 joins the end of V to the V1/V3/Y junction, and V1E continues V1 to the runway 06 threshold. Both are drawn for this example and are not on the aerodrome chart.

**Tracks.** Leave the Tracks layer empty. Twelve movements use standard ANP flight profiles; movement 11 uses the ADS-B profile `1764584438_PHBBA`, imported with the inventory (see [Create the inventory](#create-the-inventory)).

## 4. Stationary sources

**Parking lot.** A polygon for the car park next to the terminal:

| Field | Value |
|---|---|
| **Parking Name** | ParkingLot |
| **Vehicles per Year** | 20 000 |
| **Height [m]** | 0 |
| **Speed [km/h]** | 20 |
| **Travel Distance [m]** | 250 |
| **Idle Time [min]** | 0 |
| **PC (Petrol) [%]** / **PC (Diesel) [%]** | 35 / 30 |
| **LCV (Petrol) [%]** / **LCV (Diesel) [%]** | 10 / 5 |
| **HDT (Petrol) [%]** / **HDT (Diesel) [%]** | 3 / 2 |
| **Motorcycle [%]** / **Bus [%]** | 10 / 5 |

Click **Recalculate** on the **Emissions** tab. You should get:

| Field | Value |
|---|---|
| **CO [g/vehicle]** | 54.66 |
| **HC [g/vehicle]** | 4.05 |
| **NOx [g/vehicle]** | 95.82 |
| **SOx [g/vehicle]** | 0.286 |
| **PM10 [g/vehicle]** | 0.800 |

**Roadway.** A line for the access road from the motorway to the terminal, about 1025 m long:

| Field | Value |
|---|---|
| **Roadway Name** | Roadway |
| **Vehicles per Year** | 20 000 |
| **Height [m]** | 0 |
| **Speed [km/h]** | 30 |
| **PC (Petrol) [%]** / **PC (Diesel) [%]** | 35 / 30 |
| **LCV (Petrol) [%]** / **LCV (Diesel) [%]** | 15 / 5 |
| **HDT (Petrol) [%]** / **HDT (Diesel) [%]** | 3 / 2 |
| **Motorcycle [%]** / **Bus [%]** | 5 / 5 |

After **Recalculate** you should see **CO [g/km]** 0.181, **NOx [g/km]** 0.341 and **HC [g/km]** 0.0118. How COPERT factors are derived: [Road traffic and parkings](../methods/STATIONARY_AND_ROAD.md#road-traffic-and-parkings-copert).

**Point source.** A point near the terminal for the power and heating plant ([Point sources](USER_GUIDE.md#point-sources)):

| Field | Value |
|---|---|
| **Source Name** | Power |
| **Category** | Power/Heat Plant |
| **Type** | Bituminous Coal : Pulverized (> 10^8 BTU/HR) |
| **Substance** | Solid |
| **Height [m]** | 20 |
| **Temperature [°C]** | 400 |
| **Diameter [m]** | 1 |
| **Gas Velocity [m/s]** | 15 |
| **Activity per Year** | 4380 (operating hours) |
| **Activity Unit** | hr |

Keep the default emission factors of this type: **CO** 0.3002, **HC** 0.55, **NOx** 10.51, **SOx** 39.03, **PM10** 60.04 kg/unit. Only the unit differs from the shipped default (per `1000_kg`): here one unit is one operating hour. 4380 of 8760 hours gives half the hourly factor in each hour.

**Area source.** A polygon over the terminal footprint ([Area sources](USER_GUIDE.md#area-sources)):

| Field | Value |
|---|---|
| **Source Name** | Terminal |
| **Units per Year** | 8760 (operating hours) |
| **Height [m]** | 10 |
| **CO [kg/unit]** | 0.1 |
| All other factors | 0 |

This gives exactly 0.1 kg CO in every hour.

**Buildings.** You may draw the terminal in the Buildings layer (**Height [m]** about 12). OpenALAQS does not pass buildings to AUSTAL yet, so this changes no result.

All training sources are in study and use the default activity profile (1.0 in every hour, day and month).

## 5. Activity profile exercise

Optional. Click **Edit profiles** and create an hourly profile `parking_hours` for a car park closed from 23:00 to 05:00 ([Activity profiles](USER_GUIDE.md#activity-profiles)):

| Hour (local) | Multiplier |
|---|---|
| 00:00 to 04:00 | 0.0 |
| 05:00 to 22:00 | 1.0 |
| 23:00 | 0.0 |

Each hour runs to the next, so hour 04 ends at 05:00. Set it as the **Hourly Profile** of `ParkingLot` (Profiles tab). The results quoted below assume the default profile; remove the custom one again to reproduce them.

## Generate Emissions Inventory

### Taxi routes

Click **Define taxi routes** and create twelve routes: for each gate G2, G4 and G7, one arrival and one departure route per runway direction. How the editor works is in [Taxi routes](USER_GUIDE.md#taxi-routes). For every route use **Instance** 1 and move all **Aircraft Groups** to **Selected**. List a departure's taxiways from the stand to the runway and an arrival's from the runway to the stand.

| Route | Taxiway sequence | Where it meets the runway |
|---|---|---|
| G2/24/D/1 | F → N → V → V6 | line-up 82 m from the 24 threshold |
| G4/24/D/1 | Y1 → Y → V0 → V → V6 | line-up 82 m from the 24 threshold |
| G7/24/D/1 | B → Y2 → Y → V0 → V → V6 | line-up 82 m from the 24 threshold |
| G2/24/A/1 | V3 → V0 → N → F | exit 1441 m from the 24 threshold |
| G4/24/A/1 | V3 → Y → Y1 | exit 1441 m from the 24 threshold |
| G7/24/A/1 | V3 → Y → Y2 → B | exit 1441 m from the 24 threshold |
| G2/06/D/1 | F → N → V0 → V1 → V1E | line-up at the 06 threshold |
| G4/06/D/1 | Y1 → Y → V1 → V1E | line-up at the 06 threshold |
| G7/06/D/1 | B → Y2 → Y → V1 → V1E | line-up at the 06 threshold |
| G2/06/A/1 | V6 → V → N → F | exit 2116 m from the 06 threshold |
| G4/06/A/1 | V6 → V → V0 → Y → Y1 | exit 2116 m from the 06 threshold |
| G7/06/A/1 | V6 → V → V0 → Y → Y2 → B | exit 2116 m from the 06 threshold |

Each runway direction needs its own routes, because the route sets where a departure lines up and where an arrival leaves the runway.

### Create the inventory

Click **Calculate Emissions Inventory** and enter:

| Field | Value |
|---|---|
| Directory | a folder of your choice |
| File Name | `training` (the plugin adds `_out.alaqs`: the file is `training_out.alaqs`) |
| Movements Table | `training_movements.csv` |
| Filter Start Date | 2025-12-01 06:00:00 |
| Filter End Date | 2025-12-03 09:00:00 (the default: last movement's hour + 1 h) |
| Meteorological Table | `training_meteo.csv` |
| ADS-B Table | `training_ads_b_data.csv` |
| X Resolution | 250 m, 100 cells |
| Y Resolution | 250 m, 100 cells |
| Z Resolution | 50 m, 20 cells |

The grid is 25 km × 25 km and 1000 m high, centred on the airport reference point. The dialog has no vertical limit field: for aircraft the ceiling of each hour is the `MixingHeight` of the meteorology (914.4 m on 1 December, 1500 m on 2 December, 600 m on 3 December).

Click **Create Inventory**. The two ADS-B tracks are imported as CUSTOM profiles: `1764584438_PHBBA`, used by movement 11, and `1764583565_PHRTM`, which no movement uses. They are illustrative: their speeds and climb are those of a light aircraft, and only their fuel flow follows the A20N's ICAO curve. See [ADS-B](../methods/AIRCRAFT_EMISSIONS.md#ads-b) and the [ADS-B file format](INPUT_FORMATS.md#ads-b-tracks).

### Movements table

`training_movements.csv` (format: [Movements](INPUT_FORMATS.md#movements)) has 13 movements with runway times from 2025-12-01 06:05 to 2025-12-03 08:00. Five of them:

| # | runway_time | aircraft | gate | op | runway | engine | profile_id | taxi route |
|---|---|---|---|---|---|---|---|---|
| 1 | 2025-12-01 06:05 | A20N | G4 | A | 24 | 01P20CM128 (LEAP-1A26) | JET-SMALL-A-1 | G4/24/A/1 |
| 2 | 2025-12-01 06:15 | A20N | G4 | D | 24 | 01P20CM128 (LEAP-1A26) | JET-SMALL-D-1 | G4/24/D/1 |
| 3 | 2025-12-01 06:40 | E190 | G7 | A | 24 | 11GE144 (CF34-10E) | JET-REGIONAL-A-1 | G7/24/A/1 |
| 8 | 2025-12-02 07:30 | E190 | G4 | D | 06 | 11GE144 (CF34-10E) | JET-REGIONAL-D-1 | G4/06/D/1 |
| 11 | 2025-12-03 07:00 | A20N | G2 | D | 24 | 01P20CM128 (LEAP-1A26) | 1764584438_PHBBA (CUSTOM) | G2/24/D/1 |

- 8 A20N (JET SMALL) and 5 E190 (JET REGIONAL) movements, each with its default engine.
- 7 arrivals and 6 departures, in the early morning of each day. Rows 6, 8 and 13 use runway 06, the others runway 24.
- All rows have `apu_code` = 0 and `gate_emissions_code` = 0, so the study has no APU and no gate emissions. Every row sets `taxi_engine_count` 2, `engine_thrust_level_for_taxiing` 0.07, `taxi_fuel_ratio` 1 and `number_of_stop_and_gos` 0.

### Meteorology

`training_meteo.csv` (format: [Meteorology](INPUT_FORMATS.md#meteorology)) covers 2025-12-01 00:00 to 2025-12-04 00:00. The row of 2025-12-01 06:00:

| Parameter | Value |
|---|---|
| Temperature | 280.5 K |
| Humidity | 0.00446 kg/kg |
| Relative humidity | 0.68 |
| Sea-level pressure | 97 600 Pa |
| Wind speed | 5 m/s |
| Wind direction | 225° |
| Obukhov length | 99 999 m (neutral) |
| Mixing height | 914.4 m |

On 1 and 2 December the air is drier than the ISA reference (humidity ratio 0.00446 and 0.00381 kg/kg in the file, against 0.00634 kg/kg), so the BFFM2 humidity correction raises NOx; on 3 December (0.01463 kg/kg in the file) the factor is 0.85. The calculation derives the humidity from the relative humidity, temperature and pressure, which gives nearly the same values (0.0148 kg/kg on 3 December). See [NOx ambient correction](../methods/AIRCRAFT_EMISSIONS.md#nox-ambient-correction).

## Calculate emissions

Click **Visualize Emission Calculation** and open your `training_out.alaqs` (or the shipped one). On the **Configuration** tab ([Calculate emissions and query results](USER_GUIDE.md#calculate-emissions-and-query-results)):

| Setting | Value |
|---|---|
| Start | 2025-12-01 06:00:00 |
| End | 2025-12-03 09:00:00 |
| Method | BFFM2 |
| Apply NOx Corrections | not ticked (no effect with BFFM2) |
| Source Dynamics | none |
| Time Interval | 1 hour |

**Method** offers BFFM2 only while the pollutant is CO, HC or NOx. For another pollutant (for example PM10 in exercise 4) it shows bymode; when you return to NOx, BFFM2 comes back.

**Exercises.** The expected values come from `training_validation_reference.xlsx`.

1. **Parking CO.** Select *ParkingSource* and CO, click **View Emissions Table**: 0.1248 kg CO in the 06:00 to 07:00 hour. Then click **Plot Vector Layer** to see it on the grid.
2. **NOx by method.** Select *MovementSource* and NOx. Calculate with **bymode**, export the table, then with **BFFM2**, and compare the totals ([BFFM2](../methods/AIRCRAFT_EMISSIONS.md#bffm2)). Over the 13 movements NOx is 31.84 kg with bymode and 16.61 kg with BFFM2. BFFM2 gives 52 % less NOx on the six departures (41 to 60 % per movement) and 35 % less on the seven arrivals (19 to 45 %). On the arrivals it gives 8 % more CO (1 to 16 %).
3. **Differences by aircraft type.** Split exercise 2 by aircraft. On the arrivals BFFM2 NOx is 43 % below bymode for the A20N and 23 % below for the E190: the difference depends on the aircraft, not only on the mode.
4. **PM10 parts.** With *MovementSource*, compare `pm10_kg` with `pm10_nonvol_kg + pm10_sul_kg + pm10_organic_kg`. They are equal for departures. For arrivals `pm10_kg` is higher by the brake wear. `p1_kg` and `p2_kg` equal `pm10_kg`. See [Particulate matter](../methods/AIRCRAFT_EMISSIONS.md#particulate-matter).
5. **Smooth & Shift.** Set **Source Dynamics** to *smooth & shift* and plot the vector layer again. Taxi emissions are spread over a band 190 m wide for the A20N and 100 m for the E190, from the ground up to 50 m and 25 m. See [Smooth and shift](../methods/STATIONARY_AND_ROAD.md#source-dynamics-smooth-and-shift).

**Log check.** Open **Review Open ALAQS logs**. For this study it reports no ADS-B fuel flow above 1.5 times the EEDB take-off value and no taxi route that does not fit the runway.

## Dispersion with AUSTAL

Install AUSTAL first ([AUSTAL installation](../AUSTAL/AUSTAL.md#installation)). Here the input files are written from the BFFM2 calculation on the [Dispersion Models tab](DISPERSION_AUSTAL.md#dispersion-models-tab), then AUSTAL runs from the [Calculate Dispersion dialog](DISPERSION_AUSTAL.md#calculate-dispersion-dialog).

1. Keep the Configuration tab of [Calculate emissions](#calculate-emissions). Check that the pollutant is CO, HC or NOx and that **Method** is BFFM2. On the **Dispersion Models** tab set:

   | Setting | Value |
   |---|---|
   | Is Enabled | ticked |
   | Title | EHRD_training |
   | Roughness Length | 0.1 m |
   | Displacement Height | 0.6 m |
   | Anemometer Height | 10.6 m |
   | Quality Level | 1 |
   | Options String | `NOSTANDARD;SCINOTAT;Kmax=1` |

   The site parameters are the defaults; for EHRD the emission-weighted roughness of the airport ground sources is 0.105 m, class 0.10 (see [Site parameters](DISPERSION_AUSTAL.md#site-parameters)).
2. Select source type `all` and NOx, click **View Emissions Table**, and choose an empty folder when asked. The [input files](DISPERSION_AUSTAL.md#austal-input-files) are written there.
3. Click **Calculate Dispersion**. Select the AUSTAL executable, then **Use Existing AUSTAL Input Files** with that folder as **Work Directory**, and click **Run AUSTAL**.
4. In section 4, tick **Grid Management** and set **File** to `training_out.alaqs`. Choose **Pollutant** NOx and **Averaging** `annual mean`, and click **Plot Vector Layer**.

The map shows `nox-y00a.dmna`: the mean NOx concentration over the 51 hours from 2025-12-01 06:00 to 2025-12-03 09:00, not an annual mean. Compare the pattern with the wind during the movement hours: from 225° on 1 December, 270° on 2 December and 180° on 3 December. The aircraft operate only about two hours each morning, so these concentrations illustrate the method and cannot be compared with limit values.

The training inventory has no receptor points, so **Plot Time Series** and **Compliance Report** stay disabled. To try them, generate the inputs in the dialog with **Generate AUSTAL Input Files from OpenALAQS Emission Inventory File**, a **Receptors CSV** (for example the two points of the [receptor example](INPUT_FORMATS.md#receptor-points)) and **NOTALUFT** ticked; see [Results](DISPERSION_AUSTAL.md#results).

## See also

- [User Guide](USER_GUIDE.md)
- [Dispersion modelling with AUSTAL](DISPERSION_AUSTAL.md)
- [Aircraft emission methods](../methods/AIRCRAFT_EMISSIONS.md#methods)
- [Validation guide](../validation/VALIDATION_GUIDE.md)
