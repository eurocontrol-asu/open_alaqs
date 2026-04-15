# OpenALAQS User Guide

## Table of Contents

- [Introduction](#introduction)
- [The OpenALAQS Toolbar](#the-openalaqs-toolbar)
- [Starting a Study](#starting-a-study)
- [Define emission sources](#define-emission-sources)
- [Activity Profiles](#activity-profiles)
- [Generate Emissions Inventory](#generate-emissions-inventory)
- [Calculate emissions and query results](#calculate-emissions-and-query-results)
- [Dispersion modeling with AUSTAL](#dispersion-modeling-with-austal)

---

## Introduction

Welcome to the OpenALAQS user guide. This document will help you navigate the key features of the software, including setting up a study, emissions & dispersion calculations and exporting results in various formats.

### General Information

OpenALAQS is a EUROCONTROL open-source tool designed to model and analyze emissions from aircraft operations and various airport sources. It can calculate emission inventories, visualize data, and perform dispersion modeling with the help of AUSTAL.

It is developed as a plugin for the open-source geographic information system QGIS, simplifying the definition of various airport elements (such as runways, taxiways, and buildings) and enabling the visualization of the spatial distribution of emissions and concentrations. It is fully based on an open architecture, making it easily adaptable to other GIS platforms and databases.

### Installation

For installation instructions, check the Installation Instructions.

---

## The OpenALAQS Toolbar

The toolbar consists of the following functions:

- **About**: General information about the current OpenALAQS version.
- **Create Study**: Create a new OpenALAQS project.
- **Open Study**: Open an existing OpenALAQS project.
- **Close Study**: Close the current project.
- **Study Setup**: Contains general information about the study.
- **Import OSM Data**: Download and import data from OpenStreetMap (OSM).
- **Profile Editor**: Create activity profiles (hourly, daily, monthly).
- **Routes Editor**: Create taxi routes based on user-defined airport elements (gates, runways, taxiways).
- **Generate Emission Inventory**: Prepares the OpenALAQS output file containing all study data.
- **Visualize Emissions Calculation**: Manages the emissions calculation, visualization, and export modules.
- **Calculate Dispersion**: Handles the dispersion calculation module.
- **Review Logs**: Opens the log file containing useful information about code execution. When running BFFM2, the log records a confirmation line per movement (`BFFM2 dispatch confirmed`) and per-segment diagnostics at DEBUG level. Warnings appear when ADS-B fuel flow estimates exceed the EEDB takeoff ceiling and the calculator falls back to power-setting interpolation.

The order of the toolbar buttons generally follows the sequence of steps needed to conduct a study using OpenALAQS.

---

## Starting a Study

This section describes the initial steps required to create an OpenALAQS study.

### Setup a new study

To create a new project, click on the **CREATE** button in the OpenALAQS toolbar. This action opens a pop-up window named *Create an Open ALAQS project file*, where the user is required to select a **File name** for saving the new study (`.alaqs`).

After creating a project, the **ALAQS Project Properties** window opens automatically. In this window (tab **Airport**), the user must provide a project name and at least the ICAO code of the airport. The remaining fields (airport name, country, latitude, longitude, etc.) will be automatically filled based on the information in the internal database (see `default_airports.csv`). However, the user can manually edit this default information if needed.

The second tab (**Roadways**) contains the settings for calculating road traffic emissions with COPERT. Users are required to specify the average fleet year (values range from 1990 to 2030 in steps of 5) and select a country for country-specific emissions factors (or alternatively EU27). It should be noted that the average fleet year should be viewed as a proxy between the average fleet age and the Euro 1–6 vehicle emission standards.

The **ALAQS Project Properties** window can also be accessed by clicking on the **Setup** button in the OpenALAQS toolbar.

### Open an existing study

To open a previously created project, click on the **OPEN** button in the OpenALAQS toolbar. This action opens a pop-up window (*Open an ALAQS database file*), allowing you to select an existing OpenALAQS database (`.alaqs`) file.

### Import OpenStreetMap data

An additional functionality is added to OpenALAQS to facilitate the creation of emission sources based on the geographic data (roads, buildings, points of interest, and more) provided by OpenStreetMap.

Using Nominatim, a search engine that uses the data from OpenStreetMap to provide geocoding (address to coordinates), directly from the OpenALAQS toolbar the user can select and import airport-related geographical data to the study.

---

## Define emission sources

### Add Features

New objects can be added using the **Digitizing** toolbar. More information on how to use this toolbar is provided in the QGIS User Manual.

To create a new emission source, select the desired layer (e.g., taxiway or runway) to activate it and click **Toggle Editing** in the Digitizing toolbar. Then click **Add Feature** to start designing the new feature. Once finished, right-click and fill the attribute fields in the pop-up window.

### Edit Features

Using the Digitizing toolbar in editing mode (**Toggle Editing**), it is possible to employ the **Vertex Tool** to edit objects.

### Delete Features

To delete one or more features, first select the geometry using the Selection toolbar (*Select Features by area or single click*) and use the **Delete Selected** tool to delete the feature(s). Multiple selected features can be deleted at once. Selection can also be done from the Attributes table.

### Visualize and Edit Attribute Values

Attribute values can also be modified after an object's creation via the **Attributes** toolbar. The **Open Attribute Table** functionality can be accessed through the Attributes toolbar or via the Layers panel (by right-clicking on the appropriate layer).

### Aircraft related Sources

Calculating aircraft emissions requires the definition of three distinct layers: runways, taxiways, gates. For each of these features, the user must provide the required attributes. Defining Tracks (i.e., aircraft trajectories) is also possible; see the Tracks section below.

#### Gates

An airport gate refers to a designated location at an airport where aircraft park for boarding and disembarking passengers, loading/unloading cargo, and receiving services like refuelling, catering, and maintenance.

In OpenALAQS, gates are represented as polygons. Each gate can encompass several aircraft stands. The more stands grouped together within a single gate area, the less data preparation is needed (e.g., fewer taxi routes to define). However, if the gate area is too large, it might no longer accurately represent the location of the emissions.

Calculating gate emissions requires establishing the sum of four emission sources: GSE (Ground Support Equipment), GPU (Ground Power Unit), APU (Auxiliary Power Unit) and MES (Main Engine Start).

When adding a gate, the following information is required:

- Gate type (PIER, REMOTE or CARGO)
- Gate height *(not yet implemented)*

In OpenALAQS, GSE and GPU emission factors, expressed in terms of grams of pollutant per hour, are assigned to each gate as a function of:

- The gate type (PIER, REMOTE or CARGO)
- The aircraft category (JET BUSINESS/REGIONAL/SMALL/MEDIUM/LARGE, TURBOPROPS, PISTON)
- The operation type (Arrival or Departure)

More information on the corresponding GSE/GPU, APU and MES emission factors and activity time is available in the [Auxiliary Material](AUXILIARY_MATERIAL.md).

#### Runways

Runways are linear features that define the vertical plane where approach, landing, take-off, and climb-out operations occur. Each end of the runway is designated as a specific runway depending on the direction of movement.

When adding a runway, the required attributes are its name and geometry. The following fields are present in the interface but are not yet implemented: Capacity (departures/hour), Touchdown offset (meters), Maximum queue speed (km/h), Peak queue time (minutes).

Airport runways are named based on their compass heading, rounded to the nearest 10 degrees. Since runways can be used in both directions, each end has a different number, differing by 18 (180 degrees). Parallel runways may be further differentiated by letters L (Left), C (Center), or R (Right).

Runway emissions are calculated based on the aircraft trajectories (profiles) provided in the Aircraft Noise and Performance (ANP) database. For more information, see the [ANP section](AUXILIARY_MATERIAL.md#anp).

#### Taxiways

An airport taxiway is a designated path that connects runways with terminals, gates, or other parts of the airport. When adding a taxiway in an OpenALAQS study, the following information is mandatory:

- Name
- Speed (km/h)

The length of each taxiway is calculated automatically from its geometry and the time spent on it is calculated from the indicated speed and length. Recommended taxiing speeds vary in relation to ambient conditions, traffic, and aircraft position on the taxi route. Typical taxiing speeds lie between 10 and 40 km/h (~5 and ~25 kts).

It is important to distinguish between taxiways and taxi-routes. Taxi-routes describe the operational path that will be followed by an aircraft for a runway / stand / movement type (arrival or departure) combination. Taxi-routes are defined as a series of taxiway segments in OpenALAQS. The process of defining taxi routes is detailed in the Test Case Study.

#### Tracks

Aircraft tracks define custom aircraft trajectories. When adding aircraft tracks, the following information is mandatory:

- Track Name
- Runway (from the list of previously defined runways)
- Operation Type (Arrival or Departure)

Standard departure and approach trajectories are taken from ANP fixed-point profiles (see `profile_id` in the Movements table). Alternatively, ADS-B-derived profiles can be used by setting `profile_id` to a profile with `course = CUSTOM` in `default_aircraft_profiles`. In CUSTOM profiles, the `x_m` and `y_m` coordinates are East/North geodesic offsets from the runway intersection rather than along-runway distances, and the optional `fuel_flow_kgm` column carries the estimated total-aircraft ambient fuel flow (kg/s) used by BFFM2. See the [Auxiliary Material](AUXILIARY_MATERIAL.md#aircraft-trajectories) for details.

### Stationary Sources

For non-aircraft emissions four additional emission sources can be considered: point sources, roadways and parking lots, area sources, buildings.

#### Parking Lots

Emissions from parking areas for vehicles are estimated based on the COPERT methodology.

When adding an airport parking lot, the following information is required:

**Parameters**
- **Number per year**: Total number of vehicles per year
- **Height**: Height at which emissions are released (in meters) *(not yet implemented)*
- **Speed**: Average travel speed in parking (in km/h)
- **Travel distance**: Average travel distance in parking (in meters)
- **Idle time**: Vehicle average idling time between entry and exit (in minutes)
- **Average parking time**: Average time a vehicle remains on parking (in minutes)

**Profiles**: Hourly, Daily or Monthly activity profiles

**Fleet mix**: PC (Petrol/Diesel), LDV (Petrol/Diesel), HDV (Petrol/Diesel), Motorcycles, Buses (percentages summing to 100%)

The user should ensure that the fleet mix totals 100%. Custom emission factors are calculated (using the **Recalculate** button in the **Emissions** tab) for each parking area using COPERT version 5.4.52, based on the parameters above as well as the average fleet year and country specified at the beginning of the study setup.

#### Roadways

Airside or landside emissions are calculated using the same COPERT methodology as described above.

When adding a roadway, the following information is required:

**Parameters**
- **Movements per year**: Number of annual vehicle movements
- **Height**: Height at which emissions are released (in meters) *(not yet implemented)*
- **Speed**: Vehicle speed on roadway (in km/h)

**Profiles**: Hourly, Daily or Monthly activity profiles

**Fleet mix**: same categories as for Parking Lots

#### Point sources

Stationary or infrastructure-related emissions from airport facilities, such as power and heating plants, incinerators, training fires, and fuel storage tanks, are represented as point sources in OpenALAQS.

When adding a point source, the following information is required:

**Parameters**
- **Category**: Source category (Tank, Incinerator, Other, Power/Heat plant, Solvent degreaser, Surface coating)
- **Type**: Category specific type (Oil or diesel, Automobile gasoline, Aviation gasoline, JP4, JP5, JET A)
- **Height**: Height at which emissions are released (in meters) *(not yet implemented)*
- **Units per year**: Operating hours per year

**Profiles**: Hourly, Daily or Monthly activity profiles

The internal OpenALAQS database contains default emission factors for each category and type (see `default_stationary_ef`). The emission calculation is: `emission (kg) = EF (kg/unit) × units_per_year × (interval_hours / 8760)`.

#### Area sources

This layer allows users to include emissions from custom, user-defined sources not covered by the standard OpenALAQS sources, as long as they have the relevant emission factor information.

When adding an area source, the following information is required:

- **Units per year**: Number of operating hours per year
- **Height**: Height at which emissions are released (in meters) *(not yet implemented)*
- **Heat Flux**: Heat flux (in Megawatts) *(not yet implemented)*
- **Emissions**: Emission factors for CO, HC, NOX, SOX, PM10 (in kg/unit)
- **Profiles**: Hourly, Daily or Monthly activity profiles (default or custom)

The emission calculation is identical to point sources: `emission (kg) = EF (kg/unit) × units_per_year × (interval_hours / 8760)`. Beyond the standard pollutants, two additional user-defined pollutants **P1** and **P2** can be specified. For aircraft movements, P1 and P2 are placeholders for PM1.0 and PM2.5 respectively, currently set equal to PM10 until dedicated emission indices become available in the EEDB (see PM10 sub-components below).

#### Buildings

Buildings are not currently considered emission sources. However, they can significantly impact dispersion modelling by affecting wind patterns and turbulence. This functionality is not yet implemented and is included in the layers list for future use.

---

## Activity Profiles

Activity Profiles are used to describe the relative hourly/daily/monthly operational mode for each airport emission source. The **Activity Profiles Editor** in the OpenALAQS toolbar can be used to review, edit, and create custom profiles.

Each activity multiplier is a decimal number between 0 and 1. The default profile values are 1 (i.e., 100%), meaning the emission source is fully active. If the emission source is deactivated during a specific time interval (e.g., during night-time curfew), the user can set the corresponding multiplier to 0 for that specific period.

---

## Generate Emissions Inventory

This section covers all the necessary steps for preparing an emission inventory using OpenALAQS.

### Taxi routes

Taxi-routes describe the operational path of an aircraft between the runway and the gate (or vice versa). Taxi-routes can be defined using the **Taxiway Routes Editor**.

To define a taxi route in OpenALAQS, the user has to first create the taxi-route by selecting the gate, runway and operation type (arrival or departure). More than one taxi-route can be defined for the same combination of gate, runway and operation type, using a different instance number. Once defined, the corresponding taxiway segments have to be selected together with the aircraft groups that can make use of the specific taxi-route.

### Create output file

Before calculating emissions, the user must generate an OpenALAQS file that includes all user-defined elements of the study (e.g., emission sources) and the default internal database (e.g., emission factors).

The corresponding interface allows the user to set the path for saving the output file, select movements and meteorological data, set time filters, define the domain and its spatial resolution and configure other advanced settings:

**Emission Inventory Output**
- **Directory**: The path (directory) to the output file
- **File Name**: The name of the output file to be generated

**Movement Data**
- **Movements Table**: A placeholder to select the table containing data about aircraft movements
- **Filter Start Date / End Date**: Date selectors to filter the movement data

**Meteorological Data**
- **Meteorological Table**: A placeholder for importing meteorological data

**Modeled Domain**
- **X Resolution**: Spatial resolution in the X-axis (default: 250 m, 50 cells)
- **Y Resolution**: Spatial resolution in the Y-axis (default: 250 m, 50 cells)
- **Z Resolution**: Vertical spatial resolution (default: 50 m, 20 cells)

**Advanced Options**
- **Method**: A pre-processing method field, currently set to "ALAQS" *(not yet implemented — this is separate from the emission calculation method selected in the Calculate emissions panel)*
- **Towing Speed**: A field specifying towing speed, set to 10.00 km/h *(not yet implemented)*
- **Vertical Limit**: The vertical extent of the LTO domain, set by default to 914.40 meters (approximately 3000 feet). This value also serves as the LTO ceiling in the emission calculator, and should match the `MixingHeight` value used in the meteorological data.

The user must provide a comma-delimited `.csv` file containing aircraft operations (see Movements table below). An automatic check is performed to ensure that all fields in the movements and meteorology files are in the correct format (e.g., dates should follow the format YYYY-MM-DD HH:MM:SS). The meteorology file is optional; if it is missing or contains invalid data, default values based on ISA conditions will be used.

> **Note:** All movements in a study share a single ambient condition record from the meteorological table. OpenALAQS does not model temporal variation in ambient conditions across the study period.

### Movements table

This table contains all the aircraft movements occurring at the airport during a certain period. It must include the following mandatory fields:

| Field | Description |
|---|---|
| `runway_time` | Date and time of arrival at the runway (YYYY-MM-DD HH:MM:SS) |
| `block_time` | Date and time of arrival at the gate (YYYY-MM-DD HH:MM:SS) |
| `aircraft` | ICAO aircraft type designator |
| `gate` | Stand used for the aircraft operation |
| `departure_arrival` | Type of operation (A = arrival, D = departure) |
| `runway` | Name of the runway used |
| `taxi_route` | Name of the taxi route used |
| `apu_code` | APU usage control — see table below |
| `gate_emissions_code` | Gate emission control — see table below |

**`apu_code` values:**

| Code | Meaning |
|---|---|
| −1 or 0 | No APU emissions (default when field is empty) |
| 1 | APU running at gate/stand only |
| 2 | APU running during full taxi |

**`gate_emissions_code` values:**

| Code | Meaning |
|---|---|
| 0 | Suppress all gate emissions (GSE, GPU, and MES) for this movement |
| 1 | Include all gate emissions (default) |

The following optional parameters can be left empty. They will only be used if the user provides specific values; otherwise default values from the internal database will be used.

| Field | Description | Status |
|---|---|---|
| `aircraft_registration` | Aircraft registration number | Not yet implemented |
| `engine_name` | Engine identifier (from the internal database) | Active |
| `profile_id` | Performance profile identifier. Standard ANP profiles use `course = ANP2.x`. ADS-B-derived profiles use `course = CUSTOM` with East/North coordinate offsets and an optional `fuel_flow_kgm` column for BFFM2. | Active |
| `track_id` | Aircraft trajectory identifier | Not yet implemented |
| `tow_ratio` | Take-off gross weight divided by maximum take-off weight (≤ 1.0). Applied only when **Apply NOx Corrections** is enabled (Bymode method only). Default: 1.0. | Active (Bymode + NOx corrections only) |
| `taxi_engine_count` | Number of engines used during taxiing (single-engine taxi). Used together with the MES timing fields. | Active |
| `set_time_of_main_engine_start_after_block_off_in_s` | Duration in seconds after block-off during which single-engine taxi applies (departure). Takes priority over `_before_takeoff` if both are set. | Active |
| `set_time_of_main_engine_start_before_takeoff_in_s` | Duration in seconds before takeoff at which the remaining engines are started (departure). Used when `_after_block_off` is not set. | Active |
| `set_time_of_main_engine_off_after_runway_exit_in_s` | Duration in seconds after runway exit during which full-engine taxi applies before engines are cut (arrival). | Active |
| `engine_thrust_level_for_taxiing` | Taxi thrust level as a fraction (ICAO default: 0.07 = 7%). Only affects the BFFM2 emission index for the moving taxi phase; queuing always uses true idle (7%) regardless of this setting. | Active |
| `taxi_fuel_ratio` | Ratio between actual fuel flow and idle fuel flow during taxi. Acts as a direct multiplier on taxi segment emissions. Default: 1.0. | Active |
| `number_of_stop_and_gos` | Number of stop-and-go events during taxiing. Each event is modelled as two phases: 21 s at idle (deceleration + hold, per ECAC Doc 29 Vol. 2 Appendix B) plus 11 s at ~15% thrust (acceleration). Emissions are distributed proportionally across all taxiway segments. | Active |
| `domestic` | Domestic/international flag (Y or N) | Not used (read but has no effect on calculations) |

### Meteorology

OpenALAQS requires meteorological data to accurately calculate emissions using advanced methods (BFFM2, NOx corrections) and for dispersion calculations.

The required meteorological parameters are:

| Parameter | Unit | Notes |
|---|---|---|
| `Scenario` | — | Simulation name identifier |
| `DateTime` | YYYY-MM-DD HH:MM:SS | |
| `Temperature` | K | |
| `Humidity` | kg water / kg dry air | Used directly if non-zero; takes priority over `RelativeHumidity` |
| `RelativeHumidity` | % | Used to derive specific humidity if `Humidity` is zero or empty |
| `SeaLevelPressure` | Pa | |
| `WindSpeed` | m/s | |
| `WindDirection` | degrees | |
| `ObukhovLength` | m | |
| `MixingHeight` | m | Also used as the LTO ceiling in the emission calculator (default 914.4 m). Should match the **Vertical Limit** in the output file settings. |

If `Humidity` (specific humidity in kg/kg) is populated and non-zero, it is used directly. If it is empty or zero, specific humidity is derived from `RelativeHumidity`, `Temperature`, and `SeaLevelPressure`. When both fields are populated, `Humidity` takes precedence.

Input data may come from local or national data providers (e.g., METAR, SYNOP) or reanalysis data. If the meteorology file is missing or contains invalid data, default ISA conditions are used.

> **Note:** All movements in a study share a single meteorological record. Variation in ambient conditions across the study period is not modelled.

---

## Calculate emissions and query results

To calculate emissions and visualize the results, click the **Visualize Emission Calculation** button in the OpenALAQS toolbar. A new window will appear, allowing you to browse all source types and names. Emissions from aircraft-related sources (gates, taxiways and runways) are grouped together under the name **MovementSource**.

In the settings panel on the bottom left of the main window, the user can configure the calculation settings, the output formats and the settings for the dispersion model.

In the **Configuration** tab, the user can specify the general settings for the emissions calculation:

- **Start (incl.)** / **End (incl.)**: Define the emission calculation period *(optional)*
- **Method**: Select the calculation method — `ByMode` or `BFFM2`. See below for a description of each.
- **Apply NOx Corrections**: Applies the ICCAIA NOx correction for ambient temperature, humidity, and aircraft weight (via `tow_ratio`). **This option must only be used with the ByMode method.** Enabling it together with BFFM2 double-corrects ambient NOx, because BFFM2 already applies its own ambient correction internally.
- **Source Dynamics**: Select source dynamics method (*set to "none" by default*)
- **Time Interval**: Set the time interval for the calculation (*1 hour by default*)
- **Vertical Limit**: Specify the vertical limit in meters (*914.40 m by default*)
- **Receptor Points**: Specify receptor points using a `.csv` file *(optional)*

**Calculation methods:**

| Method | Description |
|---|---|
| **ByMode** | Uses ICAO EEDB emission indices for each LTO mode (TO, CL, AP, TX) directly, based on the time-in-mode from the movement profile. Simple and fast. |
| **BFFM2** | Boeing Fuel Flow Method 2. Uses the actual power setting from each profile segment to derive a fuel-flow-dependent emission index via log-log interpolation through the four EEDB breakpoints. Applies ambient corrections for temperature, pressure, and humidity. Typically gives 20–50% lower NOx and 15–30% higher CO for arrivals compared to ByMode. See [BFFM2.md](documents/BFFM2_validation/BFFM2.md) for the full methodology. |

After changing the calculation method, click **Calculate** again before exporting results.

### PM10 output columns

The emission output CSV contains the following PM-related columns for aircraft movements:

| Column | Contents |
|---|---|
| `pm10_kg` | Total PM10 = combustion PM10 + brake wear (arrivals only) |
| `pm10_nonvol_kg` | Non-volatile PM (nvPM mass), MEEM V1 ambient-corrected where 5-point EEDB data are available |
| `pm10_sul_kg` | Sulphate vPM = 36.75 mg/kg × fuel burned (FSC 500 ppm, ε = 0.024) |
| `pm10_organic_kg` | Organic vPM = δ_k × HC_EI × fuel burned |
| `p1_kg` | PM1.0 placeholder; currently equal to `pm10_kg` |
| `p2_kg` | PM2.5 placeholder; currently equal to `pm10_kg` |

For departure movements, `pm10_kg = pm10_nonvol_kg + pm10_sul_kg + pm10_organic_kg` exactly. For arrivals, `pm10_kg` additionally includes a brake-wear contribution per the FOA3 formula (`MTOW × 0.000476 − 8.74` grams), which is visible as a surplus over the sub-component sum on the first taxi segment. `p1_kg` and `p2_kg` include brake wear and equal `pm10_kg` for all movements. Detailed information on the PM10 breakdown methodology is in the [Auxiliary Material](AUXILIARY_MATERIAL.md#pm10-breakdown).

In the **Output Formats** tab:

- **Emissions table**: Output view type (by aggregation, by source or by grid cell)
- **Time Series**: Define x-axis title, marker and receptor points
- **Vector Layer**: Settings for visualisation of results on a grid

In the **Dispersion Models** tab, the user can specify general settings for the dispersion model (see [Dispersion modeling with AUSTAL](#dispersion-modeling-with-austal)).

There are three ways to visualize calculated emissions:

- View results in table format (**View Emissions Table**)
- View results as a time series (**Plot Time Series**)
- Visualize results on a grid (**Plot Vector Layer**)

---

## Dispersion modeling with AUSTAL

The connection of OpenALAQS with AUSTAL was realized based on the existing architecture of the OpenALAQS code. In order to retain the flexibility of OpenALAQS, two new modules were developed: one for producing the input files for the dispersion model and a second for running AUSTAL and exploring the calculated concentrations.

### Input data

The dispersion module will only be activated if the **Is Enabled** checkbox is checked. By default, this checkbox is unchecked. Once enabled, the user must select one of the output modules (**View Emissions Table**, **Plot Time Series**, or **Plot Vector Layer**).

The following parameters need to be defined:

- **Roughness Length**: Height above ground where wind speed theoretically becomes zero. Depends on terrain type (e.g., forests, urban areas, flat fields).
- **Displacement Height**: Height at which the wind profile starts to be affected by obstacles on the ground, such as buildings or trees.
- **Anemometer Height**: Height at which wind speed measurements are taken. Default: 10 m.
- **Quality Level**: Determines the number of simulation particles (range: −4 to +4). Higher values increase accuracy but also computation time.
- **Options String**:
  - `NOSTANDARD`: Activates non-standard calculation configurations.
  - `SCINOTAT`: Forces output in scientific notation with four significant decimal places.
  - `Kmax=1`: Limits the simulation to near-ground (surface-level) calculations.

The necessary input files for a simulation with AUSTAL are:

- **austal.txt**: Contains all main input parameters.
- **series.dmna**: Time series of meteorological parameters (wind direction, wind speed, Obukhov length) as subsequent hourly means for an integer number of days.
- **grid file** (e\*\*\*\*.dmna): Emission data on a three-dimensional grid.

### Running AUSTAL

To launch a simulation with AUSTAL, click **Calculate Dispersion** in the OpenALAQS toolbar. Specify the path to the AUSTAL executable and the project directory (**Work Directory**) where all output files will be written. Click **Run AUSTAL** to start the dispersion calculation. AUSTAL can also be run independently outside OpenALAQS.

By default, a file named `austal.log` is generated at the end of the dispersion calculation. Option **Erase Log File at the Start of the Calculation** deletes any existing log file before the calculation.

### Output data

AUSTAL calculates substance-specific annual means and possibly daily or hourly means with a given number of exceedances. The annual mean is the mean over the time period defined by the provided file `series.dmna`.

For example, the annual mean concentration file for HC is `hc-y00a.dmna` ('00' refers to the grid, 'a' refers to additional load). The statistical uncertainty is provided in the corresponding file `hc-y00s.dmna`. Concentrations are in micrograms per cubic metre.

By default, the concentration file only contains the ground layer (K=1). Using the `NOSTANDARD` option, more layers can be written out (e.g. `NOSTANDARD;Kmax=3` in `austal.txt`).

### Visualize results

To explore the results of a simulation, the user must select the OpenALAQS file used for the calculation (to ensure the exact grid and date are applied), and then choose one of the output modules:

- **Visualise Results** as a vector layer
- **Plot Time Series** to display results as a time series
- **Results Table** to view results in table format
