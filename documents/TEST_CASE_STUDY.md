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
| `EHRD_movements.csv` | Aircraft movements table for 2025-12-01 |
| `EHRD_meteo.csv` | Hourly meteorological data for 2025-12-01 |
| `EHRD.alaqs` | Pre-built study database (starting point) |
| `EHRD_out.alaqs` | Completed output file (reference result) |

The study covers a single day of operations at EHRD: six aircraft movements across three gates and two runway directions, combined with representative stationary sources (parking lot, roadway, power plant, terminal building). All movements use standard ANP profiles from the internal database.

---

### [Starting a Study](#starting-a-study)
[(Back to top)](#table-of-contents)

#### Setup a new study

Click the **CREATE** button in the OpenALAQS toolbar. In the *Create an Open ALAQS project file* dialog, choose a location and filename for your new study (e.g. `EHRD.alaqs`).

The **ALAQS Project Properties** window opens automatically. Fill in the following values for the EHRD test case:

**Airport tab**

| Field | Value |
|---|---|
| Project Name | OpenALAQS Training Course |
| ICAO Code | EHRD |
| Airport Name | Rotterdam |
| Country | NL |
| Latitude | 51.96 |
| Longitude | 4.44 |
| Elevation (m) | 0 |

Once you enter the ICAO code `EHRD`, the remaining airport fields are populated automatically from the internal database. You can adjust them if needed.

**Roadways tab**

| Field | Value |
|---|---|
| Average Fleet Year | 2020 |
| Country | Netherlands |

The average fleet year is used as a proxy for the Euro emission standard mix in the COPERT calculation. For a 2020 study at a Dutch airport, select 2020 and Netherlands.

Click **OK** to save the project properties. The study is now created and the QGIS layers panel will show all the OpenALAQS source layers (Gates, Runways, Taxiways, etc.), initially empty.

#### Open an existing study

To open the pre-built EHRD study provided with the training material, click the **OPEN** button in the OpenALAQS toolbar and navigate to `EHRD.alaqs`. All previously defined sources, profiles, and study settings will be restored.

#### Import OpenStreetMap data

OpenALAQS can import airport geometry directly from OpenStreetMap to speed up source definition. In the toolbar, click **Import OSM Data**, search for *Rotterdam The Hague Airport* using the Nominatim search box, and select the result.

Choose **Runways** and **Taxiways** as the layers to import. Review the imported features in the attribute table and verify:

- Each taxiway has a unique name (no duplicates)
- All taxiway speeds are set to a reasonable value (default ~15–30 km/h for EHRD)
- The runway is labelled `06/24` to match both operational directions

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

Open the attribute table via the **Attributes** toolbar or by right-clicking the layer in the Layers panel. All attribute values can be edited directly in the table when editing mode is active.

---

#### Aircraft related Sources

##### Gates

For the EHRD test case, create **three gates** at locations corresponding to the actual stands at Rotterdam airport. Each gate is a polygon enclosing one or more aircraft stands.

| Gate ID | Gate Type | Description |
|---|---|---|
| G2 | CARGO | Cargo apron, south of the terminal |
| G4 | REMOTE | Remote stand, accessed by bus |
| G7 | PIER | Pier-connected stand, terminal building |

When adding each gate, draw a polygon around the stand area and fill in the **gate_id** and **gate_type** attributes. Ensure each gate polygon is adjacent to at least one taxiway — the taxi route editor will connect them.

Gate type drives the GSE/GPU emission factors (from `default_gate_profiles`): PIER gates typically have lower GPU usage because a fixed electrical supply is available, while REMOTE and CARGO gates rely more on mobile GPU equipment.

##### Runways

Create a single runway feature for EHRD. Draw a linestring from the threshold of runway 06 to the threshold of runway 24, following the runway centreline.

| Field | Value |
|---|---|
| Runway ID | 06/24 |
| Capacity | 60 departures/hour |
| Touchdown offset | 250 m |

The runway ID `06/24` covers both directions of the same physical runway. OpenALAQS uses the runway direction specified in each movement record (either `06` or `24`) to determine the correct end for trajectory alignment.

The **touchdown offset** sets the point on the runway where the LTO trajectory begins for arriving aircraft (250 m from the threshold is a typical default for Category C/D jets at a medium airport).

##### Taxiways

Create taxiways covering the main taxiway system at EHRD. For this study, the following taxiways are used. All operate at a default taxi speed of **15 km/h**.

| Name | Description |
|---|---|
| B, C, D | Main apron taxiways |
| E, F, G, H | Connector taxiways |
| I, K, L, M | Northern taxiway system |
| N, O, P, Q | Southern taxiway system |
| R, T, U | Holding area and runway entry/exit |

Draw each taxiway segment as a linestring along the taxiway centreline. Use snapping to ensure segments connect at junctions. Each segment is given a unique **Name** and a **Speed** of 15 km/h.

> The distinction between taxiways (geometric segments) and taxi-routes (operational paths) is important. Taxiways are individual line segments. Taxi-routes link several taxiway segments into the path an aircraft follows from gate to runway. You define taxi-routes in the Routes Editor, described in the [Taxi routes](#taxi-routes) section.

##### Tracks

For all six EHRD movements, standard ANP profiles from `default_aircraft_profiles` are used — no custom tracks are required. The profile IDs are referenced directly in the movements table via `profile_id`. The Tracks layer in OpenALAQS is only needed when using custom ADS-B-derived trajectories with `course = CUSTOM`; it is not used in this study.

---

#### Stationary Sources

##### Parking Lots

Create a polygon representing the car park adjacent to the terminal. In the attribute form, enter the following values:

**Parameters**

| Field | Value |
|---|---|
| Parking ID | ParkingLot |
| Number per year (vehicles) | 20 000 |
| Speed (km/h) | 20 |
| Travel distance (m) | 250 |
| Idle time (min) | 0 |
| Average parking time (min) | *(leave default)* |

**Fleet mix** (must total 100%)

| Vehicle category | Share |
|---|---|
| PC Petrol | 35% |
| PC Diesel | 30% |
| LCV Petrol | 10% |
| LCV Diesel | 5% |
| HDV Petrol | 3% |
| HDV Diesel | 2% |
| Motorcycles | 10% |
| Buses Diesel | 5% |

After entering these values, click **Recalculate** in the **Emissions** tab to compute the COPERT emission factors. The resulting factors for this fleet mix and fleet year 2020 in the Netherlands are:

| Pollutant | EF (g/vehicle) |
|---|---|
| CO | 54.66 |
| HC | 4.05 |
| NOx | 95.82 |
| SOx | 0.286 |
| PM10 | 0.800 |

These pre-computed factors are stored in the `.alaqs` database and used directly in the emission calculation.

**Activity profile:** The default profile (all multipliers = 1.0) assumes the car park is equally active in all hours. See [Activity Profiles](#activity-profiles) for how to restrict parking hours if needed.

##### Roadways

Draw a polyline representing the main access road from the motorway to the terminal. The geodetic length of this road in the EHRD study is approximately **1025 m**.

| Field | Value |
|---|---|
| Roadway ID | Roadway |
| Movements per year | 20 000 |
| Speed (km/h) | 30 |

**Fleet mix** (must total 100%)

| Vehicle category | Share |
|---|---|
| PC Petrol | 35% |
| PC Diesel | 30% |
| LCV Petrol | 15% |
| LCV Diesel | 5% |
| HDV Petrol | 3% |
| HDV Diesel | 2% |
| Motorcycles | 5% |
| Buses Diesel | 5% |

Click **Recalculate** in the Emissions tab. The resulting COPERT emission factors include CO 0.181 g/km, NOx 0.341 g/km, HC 0.0118 g/km. These scale with the road length during the emission calculation.

##### Point sources

Create a point feature representing the airport power and heating plant, located near the terminal building.

| Field | Value |
|---|---|
| Source ID | Power |
| Category | Power/Heat Plant |
| Substance | Solid |
| Height (m) | 20 |
| Stack temperature (°C) | 400 |
| Stack diameter (m) | 1 |
| Exit velocity (m/s) | 15 |
| Units per year (operating hours) | 4380 |

The plant operates half the year (4380 of 8760 hours), giving an activity factor of 0.5 for any 1-hour calculation interval.

**Emission factors** — modify the default values for the *Power/Heat Plant / Solid* category:

| Pollutant | EF (kg / operating hour) |
|---|---|
| CO | 0.3002 |
| HC | 0.55 |
| NOx | 10.51 |
| SOx | 39.03 |
| PM10 | 60.04 |

> Emission factors for stationary sources can be edited directly in the default database table `default_stationary_ef` using DB Browser for SQLite, or overridden per source in the attribute form.

##### Area sources

Create a polygon covering the terminal building footprint. Area sources represent diffuse emissions from a large facility.

| Field | Value |
|---|---|
| Source ID | Terminal |
| Units per year (operating hours) | 8760 |
| Height (m) | 10 |

**Emission factors** — enter only a CO emission factor for this source to represent minor solvent or fuel handling emissions:

| Pollutant | EF (kg / operating hour) |
|---|---|
| CO | 0.1 |
| All others | 0 |

With 8760 operating hours per year and an activity factor of 1.0, this produces exactly **0.1 kg CO per hour** in each calculation interval.

##### Buildings

The terminal building can optionally be digitized as a polygon in the Buildings layer to improve dispersion modelling accuracy. Set the **Building height** to approximately 12 m. Buildings have no associated emission factors — they affect only the wind field in AUSTAL.

---

### [Activity Profiles](#activity-profiles)
[(Back to top)](#table-of-contents)

Activity profiles scale source emissions by time of day, day of week, and month of year. The default profile applies a multiplier of 1.0 for every hour, day, and month, meaning the source operates at full capacity throughout the year.

Access the **Activity Profiles Editor** via the toolbar. Click **Add Profile** to create a new profile.

**Exercise — car park closure:** Create a profile named `parking_hours` that reflects a car park closed from 23:00 to 04:00 (hours 23–04 = multiplier 0, all other hours = multiplier 1.0). Apply this profile to the `ParkingLot` source in its **Profiles** tab.

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

Create the following three taxi routes for this study:

**Route G4/24/A/1** — Arrivals from runway 24 to gate G4

| Field | Value |
|---|---|
| Gate | G4 |
| Runway | 24 |
| Operation | Arrival |
| Instance | 1 |
| Taxiway sequence | K → Q → L → P |
| Aircraft groups | All (JET BUSINESS, JET LARGE, JET MEDIUM, JET REGIONAL, JET SMALL, TURBOPROP, PROPELLER) |

**Route G7/24/A/1** — Arrivals from runway 24 to gate G7

| Field | Value |
|---|---|
| Gate | G7 |
| Runway | 24 |
| Operation | Arrival |
| Instance | 1 |
| Taxiway sequence | B → R → M → P |
| Aircraft groups | All |

**Route G2/24/D/1** — Departures from gate G2 to runway 24

| Field | Value |
|---|---|
| Gate | G2 |
| Runway | 24 |
| Operation | Departure |
| Instance | 1 |
| Taxiway sequence | K → R → T → F → D → U → P |
| Aircraft groups | All |

> **Note:** Departure movements to runway 06 at EHRD follow the same physical route as departures to runway 24 on the ground (EHRD has a single runway). The runway direction `06` or `24` only affects the LTO flight profile — the taxiway route is the same. Reference `G2/24/D/1` in the movements table for all departures regardless of runway direction.

#### Create output file

Click **Generate Emission Inventory** in the toolbar. Configure the following settings:

**Emission Inventory Output**

| Field | Value |
|---|---|
| Directory | Choose an output folder |
| File Name | `EHRD_out` |

**Movement Data**

| Field | Value |
|---|---|
| Movements Table | Browse to `EHRD_movements.csv` |
| Filter Start Date | 2025-12-01 06:00:00 |
| Filter End Date | 2025-12-01 07:00:00 |

**Meteorological Data**

| Field | Value |
|---|---|
| Meteorological Table | Browse to `EHRD_meteo.csv` |

**Modeled Domain** — these settings define the 3D grid used for spatial emission output and dispersion modelling.

| Field | Value |
|---|---|
| X Resolution | 250 m, 100 cells (25 km × 25 km domain) |
| Y Resolution | 250 m, 100 cells |
| Z Resolution | 50 m, 20 cells (up to 1000 m altitude) |

The domain is centred on the EHRD reference point (51.96°N, 4.44°E).

**Vertical Limit:** Leave at the default 914.4 m (3000 ft). Emissions above this altitude are excluded from the LTO inventory.

Click **Generate** to create `EHRD_out.alaqs`. This file copies all source definitions from the study database, combines them with the movements and meteorological data, and pre-computes the calculation grid. All subsequent emission calculations and dispersion runs use this output file.

> The computation time depends on domain size and resolution. The 100 × 100 × 20 grid used here is a reasonable balance between spatial detail and performance for a training exercise.

#### Movements table

The file `EHRD_movements.csv` (semicolon-delimited) defines the six aircraft movements in this study. All movements occur on 2025-12-01 between 06:00 and 07:00.

| OID | Aircraft | Engine | D/A | Gate | Runway | Runway time | Block time | Profile | Taxi route |
|---|---|---|---|---|---|---|---|---|---|
| 1 | A20N | LEAP-1A26 | A | G4 | 24 | 06:05 | 06:10 | JET-SMALL-A-1 | G4/24/A/1 |
| 2 | A20N | LEAP-1A26 | A | G7 | 24 | 06:15 | 06:20 | JET-SMALL-A-1 | G7/24/A/1 |
| 3 | A21N | PW1133G | D | G2 | 06 | 06:40 | 06:35 | JET-SMALL-D-2 | G2/24/D/1 |
| 11 | A21N | PW1133G | D | G2 | 06 | 06:41 | 06:36 | JET-SMALL-D-6 | G2/24/D/1 |
| 12 | E75L | CF34-8E5 | D | G2 | 06 | 06:45 | 06:40 | JET-MEDIUM-D-2 | G2/24/D/1 |
| 14 | E75L | CF34-8E5 | D | G2 | 06 | 06:50 | 06:45 | JET-MEDIUM-D-2 | G2/24/D/1 |

Key observations:

- **OIDs 1–2** are A320neo (A20N) arrivals via runway 24 with a 5-minute taxi-in time each.
- **OIDs 3 and 11** are A321neo (A21N / PW1133G) departures using two different ANP departure profiles: JET-SMALL-D-2 and JET-SMALL-D-6. These profiles have different runway distance schedules (D-2 is a shorter-field profile, D-6 represents a longer takeoff roll), resulting in measurable differences in NOx and CO when calculated with BFFM2.
- **OIDs 12 and 14** are E175 (E75L / CF34-8E5) departures, both using JET-MEDIUM-D-2.
- **All departures** have taxi time = 5 minutes (block_time to runway_time difference).
- `apu_code = 0` for all movements — APU emissions are excluded from this study.

**Exercise — ANP profile variant comparison:** Compare NOx emissions for OID 3 (JET-SMALL-D-2) against OID 11 (JET-SMALL-D-6) for the same A21N/PW1133G aircraft and engine. With the BFFM2 method, the two profiles will show different NOx and CO totals because they have different power schedule distributions across the LTO altitude range. JET-SMALL-D-6 has a longer climbout section at elevated thrust, typically resulting in higher BFFM2 NOx compared to D-2.

The movements table supports many optional fields. For this study all optional fields are left empty, which causes the calculator to apply defaults:

| Optional field | Default applied |
|---|---|
| `engine_name` | Most representative engine for the aircraft type |
| `engine_thrust_level_for_taxiing` | 0.07 (7% thrust, ICAO idle) |
| `taxi_engine_count` | All engines operating |
| `apu_code` | 0 (no APU) |
| `gate_emissions_code` | 1 (GSE, GPU and MES included) |

#### Meteorology

The file `EHRD_meteo.csv` provides 25 hourly records covering 2025-12-01 00:00 to 2025-12-02 00:00. The format uses semicolons as delimiters and the following columns:

```
Scenario ; DateTime(YYYY-mm-dd hh:mm:ss) ; Temperature(K) ; Humidity(kg_water/kg_dry_air) ;
RelativeHumidity(%) ; SeaLevelPressure(mb) ; WindSpeed(m/s) ; WindDirection(degrees) ;
ObukhovLength(m) ; MixingHeight(m)
```

Representative values for the 06:00 hour used in this study:

| Parameter | Value |
|---|---|
| Temperature | 280.5 K (7.35 °C) |
| Specific humidity | 0.00634 kg/kg |
| Relative humidity | 0.68 (68%) |
| Pressure | 97 600 Pa |
| Wind speed | 5 m/s |
| Wind direction | 225° (SW) |
| Obukhov length | 99 999 m (neutral stability) |
| Mixing height | 914.4 m |

The `Humidity` column (specific humidity) takes priority over `RelativeHumidity` when both are provided. For the BFFM2 ambient corrections, the specific humidity of 0.00634 kg/kg equals the ISA reference day humidity, so the NOx humidity correction factor is 1.0 for this dataset.

If the meteorology file is omitted, OpenALAQS falls back to ISA default conditions (T = 288.15 K, P = 101 325 Pa, H = 0.00634 kg/kg).

---

### [Calculate emissions and query results](#calculate-emissions-and-query-results)
[(Back to top)](#table-of-contents)

Click **Visualize Emission Calculation** in the toolbar and browse to `EHRD_out.alaqs`.

**Configuration tab — recommended settings for this study:**

| Setting | Value |
|---|---|
| Start | 2025-12-01 06:00:00 |
| End | 2025-12-01 07:00:00 |
| Method | BFFM2 |
| Apply NOx Corrections | ☐ (unchecked — must not be used with BFFM2) |
| Source Dynamics | none |
| Time Interval | 1 hour |
| Vertical Limit | 914.40 m |

> **Important:** Do not enable *Apply NOx Corrections* when using BFFM2. The BFFM2 method already applies P₃T₃ ambient corrections internally. Enabling both would double-correct the NOx emission index.

**Suggested exercises:**

1. **Parking CO emissions** — select *ParkingSource* from the source dropdown, choose CO as the pollutant. Click **View Emissions Table** to see the 0.1248 kg CO for the 06:00–07:00 interval. Then click **Plot Vector Layer** to see the spatial distribution on the grid.

2. **Movement NOx by method** — select *MovementSource*, NOx. Run with **ByMode** and export the CSV. Re-run with **BFFM2** and export again. Compare the total NOx:
   - ByMode gives higher NOx for departures (TO and CL modes use certified thrust EI values).
   - BFFM2 gives 20–50% lower NOx for arrivals (actual approach power is far below the 30% AP mode assumption).
   - BFFM2 gives 15–30% higher CO for arrivals (near-idle approach power has high CO EI).

3. **ANP profile variant comparison** — select *MovementSource*, filter to OID 3 vs OID 11 (both A321neo/PW1133G departures with different ANP profiles). With BFFM2 enabled, OID 11 (JET-SMALL-D-6) will show different NOx and CO compared to OID 3 (JET-SMALL-D-2) because the two profiles have different thrust schedules and altitude distributions. This illustrates the sensitivity of BFFM2 results to the choice of departure profile.

4. **PM10 sub-components** — select *MovementSource*, examine the `pm10_nonvol_kg`, `pm10_sul_kg`, and `pm10_organic_kg` output columns alongside `pm10_kg`. For departures, `pm10_kg = pm10_nonvol_kg + pm10_sul_kg + pm10_organic_kg` exactly. For arrivals, `pm10_kg` also includes the FOA3 brake-wear contribution (`MTOW × 0.000476 − 8.74` grams per movement), visible as a surplus in `pm10_kg` relative to the sub-component sum. Verify that `p1_kg = p2_kg = pm10_kg` for all movements.

5. **Smooth & Shift** — enable Source Dynamics in the Configuration tab. Re-run the Vector Layer visualisation. Observe how the taxi emission distribution widens and shifts downwind compared to the raw linestring geometry.

The log file (accessible via **Review Logs**) records one `BFFM2 dispatch confirmed` line per movement when BFFM2 is active, and WARNING messages if an ADS-B movement's fuel flow estimate exceeds the EEDB takeoff ceiling. No such warnings are expected for this study since all movements use standard ANP profiles.

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

2. Tick **Is Enabled** and select an output module (**View Emissions Table** is fastest). Click **Calculate**. OpenALAQS will compute emissions and write the three AUSTAL input files to the output directory.

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

The calculation time for the EHRD 25-hour study at Quality Level 1 on a modern laptop is typically 2–10 minutes.

#### Output data

AUSTAL writes concentration output files in `.dmna` format, one file per pollutant and statistical metric. For this study the most relevant are:

| File | Content |
|---|---|
| `nox-y00a.dmna` | NOx annual/period mean concentration (µg/m³) |
| `co-y00a.dmna` | CO period mean concentration |
| `nox-y00s.dmna` | Statistical uncertainty for NOx |

The values represent the **mean concentration over the simulated period** (2025-12-01 06:00–07:00), not an annual mean. Each file is a plain-text matrix of concentration values on the model grid. The grid is north-oriented; the first value in the matrix corresponds to the south-west corner of the domain.

Key interpretation note: this study simulates only 2 hours of a single day. Concentrations from this run are illustrative only and cannot be compared directly to air quality limit values, which require full annual averaging.

#### Visualize results

To display AUSTAL results on the QGIS map canvas:

1. Click **Calculate Dispersion** and open the results viewer.
2. Select `EHRD_out.alaqs` as the reference file.
3. Choose the pollutant (e.g. NOx) and averaging interval (annual mean).
4. Click **Visualise Results** to load the concentration grid as a QGIS vector layer.

The layer can be styled using QGIS symbology (graduated colour ramp) to produce a concentration contour map. Peak NOx concentrations will be visible near the runway threshold and along the departure climb track, with the plume extending downwind in the 225° south-west wind direction.

To inspect specific grid cells, use the **Results Table** option to export concentrations as a CSV, or use QGIS to query individual cell values by clicking on the layer.

---

*Test case prepared using EHRD operational data for the OpenALAQS Training Course, March 2026.*
*Airport: Rotterdam The Hague (EHRD) | Movements period: 2025-12-01 06:00–07:00 | Six movements, four source types.*
