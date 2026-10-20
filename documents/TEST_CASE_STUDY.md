# Open-ALAQS User Guide - Test Case Study

## [Table of Contents](#table-of-contents)
[(Back to top)](#table-of-contents)
- [Test Case Study](#test-case-study)
  - [Starting a Study](#starting-a-study)
    - [Setup a new study](#setup-a-new-study)
    - [Open an existing study](#open-an-existing-study)
    - [Import OpenStreetMap data](#import-openstreetmap-data)
  - [Define emission sources](#define-emission-sources)
    - [Add Features](#add-features)
    - [Edit Features](#edit-features)
    - [Delete Features](#delete-features)
    - [Visualize and Edit Attribute Values](#visualize-and-edit-attribute-values)
    - [Aircraft related Sources](#aircraft-related-sources)
      - [Gates](#gates)
      - [Runways](#runways)
      - [Taxiways](#taxiways)
      - [Tracks](#tracks)
    - [Stationary Sources](#stationary-sources)
      - [Parking Lots](#parking-lots)
      - [Roadways](#roadways)
      - [Point sources](#point-sources)
      - [Area sources](#area-sources)
      - [Buildings](#buildings)
  - [Activity Profiles](#activity-profiles)
  - [Generate Emissions Inventory](#generate-emissions-inventory)
    - [Taxi routes](#taxi-routes)
    - [Create output file](#create-output-file)
    - [Movements table](#movements-table)
    - [Meteorology](#meteorology)
  - [Calculate emissions and query results](#calculate-emissions-and-query-results)
  - [Dispersion modeling with AUSTAL](#dispersion-modeling-with-austal)
    - [Input data](#input-data)
    - [Running AUSTAL](#running-austal)
    - [Output data](#output-data)
    - [Visualize results](#visualize-results)

---

## [Test Case Study](#test-case-study)
[(Back to top)](#table-of-contents)

This guide walks through a complete OpenALAQS study using **Rotterdam The Hague Airport (EHRD)** as the test case. All input files needed for this exercise are provided:

| File | Description |
|---|---|
| `training_movements.csv` | Aircraft movements table (13 movements across 3 days) |
| `training_meteo.csv` | Hourly meteorological data (75 rows covering the 73 hours from 2025-12-01 00:00 through 2025-12-04 00:00; 00:00 on 2 and 3 December appears twice) |
| `training.alaqs` | Pre-built study database (starting point) |
| `training_out.alaqs` | Completed output file (reference result) |

The study covers three days of operations at EHRD: 13 aircraft movements across three gates and two runway directions, combined with representative stationary sources (parking lot, roadway, power plant, terminal building). Twelve movements use standard ANP profiles from the internal database; one movement uses a CUSTOM ADS-B-derived profile (`1764584438_PHBBA`, imported from `training_ads_b_data.csv` when the inventory is generated) to illustrate the trajectory override mechanism.

---

### [Starting a Study](#starting-a-study)
[(Back to top)](#table-of-contents)

#### Setup a new study

Click the **CREATE** button in the OpenALAQS toolbar. In the *Create an Open ALAQS project file* dialog, choose a location and filename for your new study (e.g. `training.alaqs`).

The **ALAQS Project Properties** window opens automatically. Fill in the following values for the EHRD test case:

**Airport tab**

| Field | Value |
|---|---|
| Project Name | OpenALAQS Training Course |
| ICAO Code | EHRD |
| Airport Name | Rotterdam |
| Country | NL |
| Latitude | 51.9574278 |
| Longitude | 4.4417028 |
| Elevation (m) | -5 |

Once you enter the ICAO code `EHRD`, the remaining airport fields are populated automatically from the internal database (which holds the elevation in feet, −15 ft; the form converts it to metres, −5 m). You can adjust them if needed.

**Roadways tab**

| Field | Value |
|---|---|
| Average Fleet Year | 2020 |
| Country | Netherlands |

The average fleet year is used as a proxy for the Euro emission standard mix in the COPERT calculation. For a 2020 study at a Dutch airport, select 2020 and Netherlands.

Click **OK** to save the project properties. The study is now created and the QGIS layers panel will show all the OpenALAQS source layers (Gates, Runways, Taxiways, etc.), initially empty.

#### Open an existing study

To open the pre-built EHRD study provided with the training material, click the **OPEN** button in the OpenALAQS toolbar and navigate to `training.alaqs`. All previously defined sources, profiles, and study settings will be restored.

#### Import OpenStreetMap data

OpenALAQS can import airport geometry directly from OpenStreetMap to speed up source definition. In the toolbar, click **Import OSM Data**, search for *Rotterdam The Hague Airport* using the Nominatim search box, and select the result.

Choose **Runways** and **Taxiways** as the layers to import. Review the imported features in the attribute table and verify:

- Each taxiway has a unique **Taxiway Name** (no duplicates)
- Every **Speed [km/h]** is set to a reasonable value (about 15 to 30 for EHRD)
- The **Runway Name** is `06/24` to match both operational directions

> **Note:** OSM data quality varies. Always check imported features against charts or published aerodrome data before use. You may need to delete duplicates, rename features, or adjust geometry.

---

### [Define emission sources](#define-emission-sources)
[(Back to top)](#table-of-contents)

#### Add Features

New source geometries are added using the QGIS **Digitizing** toolbar. Select the target layer in the Layers panel to activate it, then click **Toggle Editing** followed by **Add Feature**. Draw the geometry on the map canvas and right-click to finish, then fill in the attribute form that appears.

For point sources, click a single location on the canvas. For linear features (taxiways, runways, roadways), click a series of vertices defining the path. For polygon features (gates, parking lots, area sources), click the boundary vertices and close the polygon by right-clicking.

Enable **snapping** in the QGIS toolbar to ensure gate polygons connect cleanly to taxiways and that taxiway segments meet without gaps. Gaps between features prevent taxi route creation and will cause calculation errors.

#### Edit Features

To edit an existing geometry, select the layer, enable **Toggle Editing**, then use the **Vertex Tool** to move or delete individual vertices.

#### Delete Features

Select one or more features using the **Select Features by area or single click** tool, then press the **Delete Selected** button. Multiple features can be selected and deleted together.

#### Visualize and Edit Attribute Values

Open the attribute table via the **Attributes** toolbar or by right-clicking the layer in the Layers panel. All attribute values can be edited directly in the table when editing mode is active. The table headers use the field names of the forms (the names in bold below); the internal **OID** column is hidden, and **In Study** is shown (as true / false in the table, as a check box in the form) on parkings, roadways, point sources and area sources only. All training sources are in study.

---

#### Aircraft related Sources

##### Gates

For the EHRD test case, create **three gates** at locations corresponding to the actual stands at Rotterdam airport. Each gate is a polygon enclosing one or more aircraft stands.

| Gate Name | Gate Type | Description |
|---|---|---|
| G2 | CARGO | Cargo apron, south of the terminal |
| G4 | REMOTE | Remote stand, accessed by bus |
| G7 | PIER | Pier-connected stand, terminal building |

When adding each gate, draw a polygon around the stand area and fill in the **Gate Name** and **Gate Type** fields. Ensure each gate polygon is adjacent to at least one taxiway: the taxi route editor will connect them.

Gate type drives the GSE/GPU emission factors (from `default_gate_profiles`): PIER gates typically have lower GPU usage because a fixed electrical supply is available, while REMOTE and CARGO gates rely more on mobile GPU equipment.

##### Runways

Create a single runway feature for EHRD. Draw a linestring from the threshold of runway 06 to the threshold of runway 24, following the runway centreline.

| Field | Value |
|---|---|
| Runway 1 | 06 (Runway 2 = 24 and **Runway Name** = 06/24 are filled in) |
| **Touchdown Offset, Runway 1 [m]** | 250 |
| **Touchdown Offset, Runway 2 [m]** | 250 |

The runway ID `06/24` covers both directions of the same physical runway. OpenALAQS uses the runway direction specified in each movement record (either `06` or `24`) to determine the correct end for trajectory alignment.

The touchdown offset (**Touchdown Offset, Runway 1 [m]** and **Touchdown Offset, Runway 2 [m]**, whole metres) sets where arriving aircraft touch down, measured from the landing threshold of each runway end (Runway 1 = the first-named end, 06 here). Leave it empty or 0 to use each arrival profile's own touchdown distance (the profile crosses the threshold at 50 ft: about 290 m before touchdown on a 3° approach). 250 m puts the threshold crossing at about 13 m on a 3° approach.

##### Taxiways

Create taxiways covering the main taxiway system at EHRD. For this study, the following taxiways are used.

| Taxiway Name | Speed [km/h] |
|---|---|
| B, F, N, V, V0, V1, V1E, V2, V3, V6, Y | 15 |
| Y1, Y2 | 30 |

Draw each taxiway segment as a linestring along the taxiway centreline. Use snapping to ensure segments connect at junctions. Each segment is given a unique **Taxiway Name** and the **Speed [km/h]** above. V0 joins the end of V to the V1/V3/Y junction, and V1E continues V1 to the runway 06 threshold; both are drawn for this example, not taken from the aerodrome chart.

> The distinction between taxiways (geometric segments) and taxi-routes (operational paths) is important. Taxiways are individual line segments. Taxi-routes link several taxiway segments into the path an aircraft follows from gate to runway. You define taxi-routes in the Routes Editor, described in the [Taxi routes](#taxi-routes) section.

##### Tracks

Twelve of the thirteen EHRD movements use standard ANP profiles from `default_aircraft_profiles`. One movement (row 11, A20N departure on day 3) uses the CUSTOM ADS-B-derived profile `1764584438_PHBBA` to illustrate the trajectory override mechanism. The profile is not in the study file: it is imported from `training_ads_b_data.csv` into the inventory when the inventory is generated (ADS-B Data, below), together with a second track (`1764583565_PHRTM`, an arrival) that no movement uses. Profile IDs are referenced directly in the movements table via `profile_id`; the Tracks layer is not used in this study since CUSTOM profiles are read from `default_aircraft_profiles`, not from the Tracks layer.

---

#### Stationary Sources

##### Parking Lots

Create a polygon representing the car park adjacent to the terminal. In the attribute form, enter the following values:

**Parameters**

| Field | Value |
|---|---|
| **Parking Name** | ParkingLot |
| **Vehicles per Year** | 20 000 |
| **Height [m]** | 0 |
| **Speed [km/h]** | 20 |
| **Travel Distance [m]** | 250 |
| **Idle Time [min]** | 0 |

**Fleet mix** (must total 100%)

| Field | Value |
|---|---|
| **PC (Petrol) [%]** | 35 |
| **PC (Diesel) [%]** | 30 |
| **LCV (Petrol) [%]** | 10 |
| **LCV (Diesel) [%]** | 5 |
| **HDT (Petrol) [%]** | 3 |
| **HDT (Diesel) [%]** | 2 |
| **Motorcycle [%]** | 10 |
| **Bus [%]** | 5 |

After entering these values, click **Recalculate** in the **Emissions** tab to compute the COPERT emission factors. The resulting factors for this fleet mix and fleet year 2020 in the Netherlands are:

| Field | Value |
|---|---|
| **CO [g/vehicle]** | 54.66 |
| **HC [g/vehicle]** | 4.05 |
| **NOx [g/vehicle]** | 95.82 |
| **SOx [g/vehicle]** | 0.286 |
| **PM10 [g/vehicle]** | 0.800 |

These pre-computed factors are stored in the `.alaqs` database and used directly in the emission calculation.

**Activity profile:** The default profile (all multipliers = 1.0) assumes the car park is equally active in all hours. See [Activity Profiles](#activity-profiles) for how to restrict parking hours if needed.

##### Roadways

Draw a polyline representing the main access road from the motorway to the terminal. The geodetic length of this road in the EHRD study is approximately **1025 m**.

| Field | Value |
|---|---|
| **Roadway Name** | Roadway |
| **Vehicles per Year** | 20 000 |
| **Height [m]** | 0 |
| **Speed [km/h]** | 30 |

**Fleet mix** (must total 100%)

| Field | Value |
|---|---|
| **PC (Petrol) [%]** | 35 |
| **PC (Diesel) [%]** | 30 |
| **LCV (Petrol) [%]** | 15 |
| **LCV (Diesel) [%]** | 5 |
| **HDT (Petrol) [%]** | 3 |
| **HDT (Diesel) [%]** | 2 |
| **Motorcycle [%]** | 5 |
| **Bus [%]** | 5 |

Click **Recalculate** in the Emissions tab. The resulting COPERT emission factors include **CO [g/km]** 0.181, **NOx [g/km]** 0.341 and **HC [g/km]** 0.0118. These scale with the road length during the emission calculation.

##### Point sources

Create a point feature representing the airport power and heating plant, located near the terminal building.

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

The plant operates half the year (4380 of 8760 hours), giving an activity factor of 0.5 for any 1-hour calculation interval.

**Emission factors**: modify the default values for the *Power/Heat Plant / Solid* category (one unit is one operating hour here):

| Field | Value |
|---|---|
| **CO [kg/unit]** | 0.3002 |
| **HC [kg/unit]** | 0.55 |
| **NOx [kg/unit]** | 10.51 |
| **SOx [kg/unit]** | 39.03 |
| **PM10 [kg/unit]** | 60.04 |

> Emission factors for stationary sources can be edited directly in the default database table `default_stationary_ef` using DB Browser for SQLite, or overridden per source in the attribute form.

##### Area sources

Create a polygon covering the terminal building footprint. Area sources represent diffuse emissions from a large facility.

| Field | Value |
|---|---|
| **Source Name** | Terminal |
| **Units per Year** | 8760 (operating hours) |
| **Height [m]** | 10 |

**Emission factors**: enter only a CO emission factor for this source to represent minor solvent or fuel handling emissions (one unit is one operating hour):

| Field | Value |
|---|---|
| **CO [kg/unit]** | 0.1 |
| All others | 0 |

With 8760 operating hours per year and an activity factor of 1.0, this produces exactly **0.1 kg CO per hour** in each calculation interval.

##### Buildings

The terminal building can optionally be digitized as a polygon in the Buildings layer to improve dispersion modelling accuracy. Set **Height [m]** to approximately 12. Buildings have no associated emission factors: they affect only the wind field in AUSTAL.

---

### [Activity Profiles](#activity-profiles)
[(Back to top)](#table-of-contents)

Activity profiles scale source emissions by time of day, day of week, and month of year. The default profile applies a multiplier of 1.0 for every hour, day, and month, meaning the source operates at full capacity throughout the year.

Access the **Activity Profiles Editor** via the toolbar. Click **Add Profile** to create a new profile.

**Exercise (car park closure):** Create a profile named `parking_hours` that reflects a car park closed from 23:00 to 04:00 (hours 23 to 04 = multiplier 0, all other hours = multiplier 1.0). Apply this profile to the `ParkingLot` source as its **Hourly Profile** (Profiles tab).

| Hour (local) | Multiplier |
|---|---|
| 00:00–04:00 | 0.0 |
| 05:00–22:00 | 1.0 |
| 23:00 | 0.0 |

For this training study all sources use the **default** profile (all multipliers = 1.0) unless you choose to apply the custom parking profile as the exercise above.

---

### [Generate Emissions Inventory](#generate-emissions-inventory)
[(Back to top)](#table-of-contents)

#### Taxi routes

Taxi routes define the sequence of taxiway segments an aircraft follows between a gate and the runway. They are required for calculating taxiway emissions. Open the **Routes Editor** from the toolbar.

For each route, select the **Gate**, **Runway direction**, and **Operation type** (Arrival or Departure), then choose the ordered sequence of taxiway segment names. Finally, select the **aircraft groups** that use this route (for EHRD all groups share the same routes).

Create twelve taxi routes for this study: for each of the three gates G2, G4 and G7, one arrival and one departure route per runway direction (06 and 24). List a departure route's taxiways from the stand to the runway, and an arrival route's from the runway to the stand. One route is detailed below; the table after it lists all twelve. Each row of `training_movements.csv` references the route of its runway direction.

**Route G4/24/A/1**: arrivals from runway 24 to gate G4

| Field | Value |
|---|---|
| Gate | G4 |
| Runway | 24 |
| Operation | Arrival |
| Instance | 1 |
| Taxiway sequence | V3 → Y → Y1 |
| Aircraft groups | All (JET BUSINESS, JET LARGE, JET MEDIUM, JET REGIONAL, JET SMALL, TURBOPROP, PROPELLER) |

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

All routes use instance 1 and all aircraft groups.

> **Note:** The taxi route sets where a departure lines up (where the route last meets the runway) and where an arrival leaves the runway, so each runway direction needs its own routes. Routes drawn for the other direction would line departures up partway along the runway and make arrivals leave it at high speed; the runway checks in the log (see Results Analysis) report such cases.

#### Create output file

Click **Generate Emission Inventory** in the toolbar. Configure the following settings:

**Emission Inventory Output**

| Field | Value |
|---|---|
| Directory | Choose an output folder |
| File Name | `training_out` |

**Movement Data**

| Field | Value |
|---|---|
| Movements Table | Browse to `training_movements.csv` |
| Filter Start Date | 2025-12-01 06:00:00 |
| Filter End Date | 2025-12-03 09:00:00 (the dialog's default: the last movement's hour + 1 h) |

**Meteorological Data**

| Field | Value |
|---|---|
| Meteorological Table | Browse to `training_meteo.csv` |

**ADS-B Data (Optional)**

| Field | Value |
|---|---|
| ADS-B Table | Browse to `training_ads_b_data.csv` |

The two tracks in this file are imported into the inventory as CUSTOM profiles (`1764584438_PHBBA`, used by movement 11, and `1764583565_PHRTM`, unused), placed from the runway and taxi route that the movement table gives for the flight (PHBBA); PHRTM, which no movement uses, is placed at the closest runway end. Heights are taken above the airport elevation; the take-off roll, reported at −15 ft, is set to the ground. The tracks are an example: their `fuel_flow` (aircraft total) is twice the ICAO fuel flow of the A20N engine 01P20CM128 interpolated at the row's `power_setting` (0.65 to 1.57 kg/s for PHBBA; PHRTM, with the same curve and its power raised to idle where it was below, 0.18 to 0.21 kg/s). Only the BFFM2 trajectory method uses it.

**Modeled Domain** — these settings define the 3D grid used for spatial emission output and dispersion modelling.

| Field | Value |
|---|---|
| X Resolution | 250 m, 100 cells (25 km × 25 km domain) |
| Y Resolution | 250 m, 100 cells |
| Z Resolution | 50 m, 20 cells (up to 1000 m altitude) |

The domain is centred on the EHRD reference point (51.9574278°N, 4.4417028°E).

**Vertical Limit:** this dialog has no Vertical Limit field (the inventory records 914.4 m). For aircraft movements the ceiling of each hour is the meteorological `MixingHeight`: 914.4 m on 1 December, 1500 m on 2 December and 600 m on 3 December in `training_meteo.csv`.

Click **Generate** to create `training_out.alaqs`. This file copies all source definitions from the study database, combines them with the movements and meteorological data, and pre-computes the calculation grid. All subsequent emission calculations and dispersion runs use this output file.

> The computation time depends on domain size and resolution. The 100 × 100 × 20 grid used here is a reasonable balance between spatial detail and performance for a training exercise.

#### Movements table

The file `training_movements.csv` (semicolon-delimited) defines the 13 aircraft movements in this study, spanning 2025-12-01 06:05 through 2025-12-03 08:05. The table below shows five representative rows; consult the file directly for the complete set.

| # | runway_time | aircraft | gate | op | runway | engine | profile_id | taxi route |
|---|---|---|---|---|---|---|---|---|
| 1 | 2025-12-01 06:05 | A20N | G4 | A | 24 | 01P20CM128 (LEAP-1A26) | JET-SMALL-A-1 | G4/24/A/1 |
| 2 | 2025-12-01 06:15 | A20N | G4 | D | 24 | 01P20CM128 (LEAP-1A26) | JET-SMALL-D-1 | G4/24/D/1 |
| 3 | 2025-12-01 06:40 | E190 | G7 | A | 24 | 11GE144 (CF34-10E) | JET-REGIONAL-A-1 | G7/24/A/1 |
| 8 | 2025-12-02 07:30 | E190 | G4 | D | 06 | 11GE144 (CF34-10E) | JET-REGIONAL-D-1 | G4/06/D/1 |
| 11 | 2025-12-03 07:00 | A20N | G2 | D | 24 | 01P20CM128 (LEAP-1A26) | **1764584438_PHBBA** (CUSTOM) | G2/24/D/1 |

Key observations:

- **Aircraft mix.** Two ICAO types: A20N (Airbus A320neo, JET SMALL, 8 movements) and E190 (Embraer ERJ-190, JET REGIONAL, 5 movements). Each is paired with its default engine: `01P20CM128` (CFM LEAP-1A26) and `11GE144` (CF34-10E) respectively.
- **Profile mix.** Twelve movements use standard ANP profiles (`JET-SMALL-A-1`, `JET-SMALL-D-1`, `JET-REGIONAL-A-1`, `JET-REGIONAL-D-1`). Row 11 uses the CUSTOM ADS-B profile `1764584438_PHBBA` — same A20N aircraft, but the trajectory is overridden by the CUSTOM points from `default_aircraft_profiles`.
- **Operation split.** 7 arrivals, 6 departures, distributed across the three days. Each day's activity is clustered in the early-morning hours.
- **Runway direction.** Most movements use runway 24; three rows (6, 8, 13) use runway 06.
- **APU and gate emissions suppressed.** All 13 rows have `apu_code = 0` and `gate_emissions_code = 0`, so APU and gate (GSE/GPU/MES) emissions are excluded in this study. This isolates the aircraft trajectory contribution for comparison against the bymode/BFFM2 methodology output.

The movements table supports many optional fields. In this study `engine_name`, `profile_id`, `taxi_engine_count` (2), `engine_thrust_level_for_taxiing` (0.07), `taxi_fuel_ratio` (1) and `number_of_stop_and_gos` (0) are filled on every row, `apu_code` and `gate_emissions_code` are 0, and `track_id`, `tow_ratio` and the main-engine-start times are empty. When a field is empty the calculator applies these defaults:

| Optional field | Default applied when empty |
|---|---|
| `engine_name` | Most representative engine for the aircraft type |
| `engine_thrust_level_for_taxiing` | 0.07 (7% thrust, ICAO idle) |
| `taxi_engine_count` | All engines operating |
| `tow_ratio` | 1.0 |
| `number_of_stop_and_gos` | 0 |

Note that the *system* default for `gate_emissions_code` when the field is empty is **1** (gate emissions enabled), but this study explicitly overrides it to **0** for every row.

#### Meteorology

The file `training_meteo.csv` provides 75 rows covering the 73 hours from 2025-12-01 00:00 through 2025-12-04 00:00 (00:00 on 2 and 3 December appears twice). The format is comma-delimited with the following columns:

```
Scenario, DateTime(YYYY-mm-dd hh:mm:ss), Temperature(K), Humidity(kg_water/kg_dry_air),
RelativeHumidity(0-1), SeaLevelPressure(Pa), WindSpeed(m/s), WindDirection(degrees),
ObukhovLength(m), MixingHeight(m)
```

Representative values for the 06:00 hour on 2025-12-01:

| Parameter | Value |
|---|---|
| Temperature | 280.5 K (7.35 °C) |
| Specific humidity | 0.00446 kg/kg |
| Relative humidity | 0.68 |
| Pressure | 97 600 Pa |
| Wind speed | 5 m/s |
| Wind direction | 225° (SW) |
| Obukhov length | 99 999 m (neutral stability) |
| Mixing height | 914.4 m |

The `Humidity` column (specific humidity) takes priority over `RelativeHumidity` when both are provided. On 1 and 2 December the specific humidity (0.00446 and 0.00381 kg/kg) is **below** the ISA reference day humidity (0.00634 kg/kg), so the BFFM2 NOx humidity factor exp(−19 (h − 0.00634)) is **above 1.0** (drier air raises NOx); on 3 December (0.01463 kg/kg) it is 0.85.

If the meteorology file is omitted, OpenALAQS falls back to ISA default conditions (T = 288.15 K, P = 101 325 Pa, H = 0.00634 kg/kg).

---

### [Calculate emissions and query results](#calculate-emissions-and-query-results)
[(Back to top)](#table-of-contents)

Click **Visualize Emission Calculation** in the toolbar and browse to `training_out.alaqs`.

**Configuration tab — recommended settings for this study:**

| Setting | Value |
|---|---|
| Start | 2025-12-01 06:00:00 |
| End | 2025-12-03 09:00:00 (filled in from the inventory) |
| Method | BFFM2 |
| Apply NOx Corrections | ☐ (unchecked; it has no effect with BFFM2) |
| Source Dynamics | none |
| Time Interval | 1 hour |
| Vertical Limit | 914.40 m |

> **Note:** *Apply NOx Corrections* applies to the bymode method only (take-off and climb-out segments); with BFFM2 it is ignored, since BFFM2 applies its own ambient correction.

**Suggested exercises:**

1. **Parking CO emissions**: select *ParkingSource* from the source dropdown, choose CO as the pollutant. Click **View Emissions Table** to see the 0.1248 kg CO for the 06:00–07:00 interval. Then click **Plot Vector Layer** to see the spatial distribution on the grid.

2. **Movement NOx by method**: select *MovementSource*, NOx. Run with **ByMode** and export the CSV. Re-run with **BFFM2** and export again. Compare the total NOx:
   - ByMode gives higher NOx for departures (BFFM2: 50 % less on the six departures).
   - BFFM2 gives 29 % less NOx for the arrivals (2 to 50 % per movement).
   - BFFM2 gives 8 % more CO for the arrivals (1 to 18 % per movement).

3. **Per-aircraft method drift**: extend exercise 2 by splitting the per-movement CSV by aircraft type. Compare the BFFM2-minus-ByMode NOx delta for the eight A20N movements versus the five E190 movements. Because the two aircraft have different engine power schedules and different default ANP profiles, the BFFM2 correction shifts them differently. On this study the drift is larger on the A20N arrivals (NOx 39 % below ByMode) than on the E190 arrivals (12 % below). This illustrates that BFFM2 vs ByMode differences are aircraft-type dependent, not just mode dependent.

4. **PM10 sub-components**: select *MovementSource*, examine the `pm10_nonvol_kg`, `pm10_sul_kg`, and `pm10_organic_kg` output columns alongside `pm10_kg`. For departures, `pm10_kg = pm10_nonvol_kg + pm10_sul_kg + pm10_organic_kg` exactly. For arrivals, `pm10_kg` also includes the FOA3 brake-wear contribution (`MTOW × 0.000476 − 8.74` grams per movement), visible as a surplus in `pm10_kg` relative to the sub-component sum. Verify that `p1_kg = p2_kg = pm10_kg` for all movements.

5. **Smooth & Shift**: enable Source Dynamics in the Configuration tab. Re-run the Vector Layer visualisation. Observe how the taxi emission distribution widens and shifts downwind compared to the raw linestring geometry.

The log file (accessible via **Review Logs**) reports an ADS-B fuel flow above 1.5 times the EEDB take-off value (none here: movement 11's ADS-B fuel flow is at most 0.78 kg/s per engine, against 1.5 × 0.861 kg/s) and taxi routes that do not fit the runway (an arrival leaving the runway above 50 kt, or a route that meets the runway only before the touchdown). For this study it reports none.

---

### [Dispersion modeling with AUSTAL](#dispersion-modeling-with-austal)
[(Back to top)](#table-of-contents)

#### Input data

AUSTAL requires three input files, which OpenALAQS prepares automatically:

| File | Content |
|---|---|
| `austal.txt` | Site parameters, grid definition, roughness, Obukhov length |
| `series.dmna` | Hourly meteorological time series (wind speed, direction, Obukhov length) |
| `e****.dmna` | 3D emission grid for each source type and pollutant |

To prepare the input files:

1. In the **Dispersion Models** tab of the *Visualize Emission Calculation* window, configure AUSTAL:

| Parameter | Value |
|---|---|
| Roughness Length | 0.2 m |
| Displacement Height | 1.2 m |
| Anemometer Height | 11.2 m |
| Title | EHRD_training |
| Quality Level | 1 |
| Is Enabled | ☑ checked |
| Options String | *(leave blank for standard run)* |

2. Tick **Is Enabled** and click an output button (**View Emissions Table** is fastest). OpenALAQS will compute emissions and write the three AUSTAL input files to the output directory.

**Quality Level** controls the number of simulation particles in AUSTAL:
- Level 1 (default) — fast, ~10% statistical uncertainty, suitable for training
- Level 3–4 — high accuracy, significantly slower, used for regulatory submissions

**Options String** examples:
- `NOSTANDARD` — enables non-standard configurations (e.g. custom wind fields)
- `SCINOTAT` — forces scientific notation in output files
- `NOSTANDARD;Kmax=3` — writes concentration output for the lowest 3 vertical layers

#### Running AUSTAL

Click **Calculate Dispersion** in the toolbar. In the dialog:

1. Set the **AUSTAL executable path** to the location of your AUSTAL installation (e.g. `C:/AUSTAL/austal.exe` on Windows or `/opt/austal/austal` on Linux).
2. Set the **Work Directory** to the folder where the AUSTAL input files were written.
3. Click **Run AUSTAL**.

A progress log (`austal.log`) is written to the Work Directory. AUSTAL can also be run independently from a terminal using:

```bash
austal /path/to/work/directory/austal.txt
```

The calculation time for the EHRD 51-hour study period at Quality Level 1 on a modern laptop is typically 2–10 minutes.

#### Output data

AUSTAL writes concentration output files in `.dmna` format, one file per pollutant and statistical metric. For this study the most relevant are:

| File | Content |
|---|---|
| `nox-y00a.dmna` | NOx annual/period mean concentration (µg/m³) |
| `co-y00a.dmna` | CO period mean concentration |
| `nox-y00s.dmna` | Statistical uncertainty for NOx |

The values represent the **mean concentration over the simulated period** (2025-12-01 06:00 through 2025-12-03 09:00, 51 hours), not an annual mean. Each file is a plain-text matrix of concentration values on the model grid. The grid is north-oriented; the first value in the matrix corresponds to the south-west corner of the domain.

Key interpretation note: this study spans a 51-hour window across three days, but actual aircraft activity is clustered in early-morning hours (~06:00–08:00 daily, ~6 hours of operations total). Concentrations from this run are illustrative only and cannot be compared directly to air quality limit values, which require full annual averaging.

#### Visualize results

To display AUSTAL results on the QGIS map canvas:

1. Click **Calculate Dispersion**; after a run, section 4 (Result Visualisation) is filled in (or use **Load Existing Results** with the Work Directory).
2. Choose the pollutant (e.g. NOx) and the averaging (annual mean).
3. Click **Plot Vector Layer** to load the concentration grid as a QGIS vector layer.

The layer can be styled using QGIS symbology (graduated colour ramp) to produce a concentration contour map. Peak NOx concentrations will be visible near the runway threshold and along the departure climb track, with the plume extending downwind of each day's wind (from 225° on 1 December, 270° on 2 December, 180° on 3 December).

To inspect specific grid cells, query individual cell values by clicking on the layer, or open its attribute table.

---

*Test case prepared using EHRD operational data for the OpenALAQS Training Course, March 2026.*
*Airport: Rotterdam The Hague (EHRD) | Movements period: 2025-12-01 06:05 to 2025-12-03 08:05 | Thirteen movements, four source types.*
