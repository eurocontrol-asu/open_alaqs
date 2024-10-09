# Open-ALAQS User Guide

## Table of Contents
- [User Guide](#project-title)
  - [Table of contents](#table-of-contents)
  - [Introduction](#introduction)
    - [General Information](#oa-geninfo)
    - [Installation](#installation-instructions)
  - [The Open-ALAQS Toolbar](#the-open-alaqs-toolbar)
  - [Starting a Study](#starting-a-study)
    - [Setup a new study](#setup-new-study)
    - [Open an existing study](#open-study)
    - [Import OpenStreetMap data](#import-osm-data)
  - [Define emission sources](#define-em-sources)
    - [Add Features](#add-features)
    - [Edit Features](#edit-features)
    - [Delete Features](#del-features)
    - [Visualize and Edit Attribute Values](#visu-features)
    - [Aircraft related Sources](#aircraft-sources)
      - [Gates](#gates-layer)
      - [Runways](#runways-layer)
      - [Taxiways](#taxiways-layer)
    - [Stationary (Non-Aircraft) Sources](#non-aircraft-sources)
  - [Activity Profiles](#activity-profiles)
  - [Generating Emission Inventory](#generating-emission-inventory)
  - [Visualization of Results](#visualization-of-results)
- [Auxiliary Material](#aux-material)
  - [AUSTAL](#austal)
  - [COPERT](#copert)
  - [ANP](#anp-db)
  - [Open-ALAQS Database](#oa-database)
- [Test Case Study](#test-case-study)
<!-- [FAQs](#faqs) -->
<!-- [Contact](#contact) -->

## Introduction
[(Back to top)](#table-of-contents)

Welcome to the **Open-ALAQS** user guide. This document will help you navigate the key features of the software, including setting up a study, emissions & dispersion calculations and exporting results in various formats.

### General Information
[(Back to top)](#table-of-contents)

Open-ALAQS is a [EUROCONTROL](https://www.eurocontrol.int/) open-source tool designed to model and analyze emissions from aircraft operations and various airport sources. It can calculate emission inventories, visualize data, and perform dispersion modeling with the help of [AUSTAL](https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/overview).

It is developed as a plugin for the open-source geographic information system [QGIS](https://qgis.org/), simplifying the definition of various airport elements (such as runways, taxiways, and buildings) and enabling the visualization of the spatial distribution of emissions and concentrations. It is fully based on an open architecture, making it easily adaptable to other GIS platforms and databases.

### Installation
[(Back to top)](#table-of-contents)

For installation instructions, check the [Installation Instructions](../README.md#installation).

## The Open-ALAQS Toolbar
[(Back to top)](#table-of-contents)

![toolbar.PNG](./../open_alaqs/assets/toolbar.PNG)

The toolbar consists of the following functions:

- **About**: General information about the current Open-ALAQS version.
- **Create Study**: Create a new Open-ALAQS project.
- **Open Study**: Open an existing Open-ALAQS project.
- **Close Study**: Close the current project.
- **Study Setup**: Contains general information about the study.
- **Import OSM Data**: Download and import data from OpenStreetMap (OSM).
- **Profile Editor**: Create activity profiles (hourly, daily, monthly).
- **Routes Editor**: Create taxi routes based on user-defined airport elements (gates, runways, taxiways).
- **Generate Emission Inventory**: Prepares the Open-ALAQS output file containing all study data.
- **Visualize Emissions Calculation**: Manages the emissions calculation, visualization, and export modules.
- **Calculate Dispersion**: Handles the dispersion calculation module.
- **Review Logs**: Opens the log file containing useful information about code execution.

The order of the toolbar buttons generally follows the sequence of steps needed to conduct a study using Open-ALAQS.

## Creating a Study
[(Back to top)](#table-of-contents)

This section describes the initial steps required to create an Open-ALAQS study.

### Setup a new study

To create a new project, click on the **CREATE** button in the Open-ALAQS toolbar. This action opens a pop-up window named **Create an Open ALAQS project file**, where the user is required to
select a **File name** for saving the new study (**.alaqs**).

After creating a project, the **ALAQS Project Properties** window opens automatically. In this window (tab **Airport**), the user must provide a project name and at least the ICAO code of the airport. The remaining fields (airport name, country, latitude, longitude, etc.) will be automatically filled based on the information in the internal database (see **default_airports.csv**). However, the user can manually edit this default information if needed.

The second tab (**Roadways**) contains the settings for calculating road traffic emissions with [COPERT](#copert). Users are required to specify the average fleet year (values range from 1990 to 2030 in steps of 5) and select a country for country-specific emissions factors(or alternatively EU27). It should be noted that the average fleet year should be viewed as a proxy between the average fleet age and the Euro 1, Euro 2, Euro 3, Euro 4, Euro 5, and Euro 6 vehicle emission standards.

<p align="center">
  <img src="./../open_alaqs/assets/alaqs-project-properties.PNG" alt="Project Properties 1" width="45%" />
  <img src="./../open_alaqs/assets/alaqs-project-properties2.PNG" alt="Project Properties 2" width="45%" />
</p>

The **ALAQS Project Properties** window, can also be accessed by clicking on the **Setup** button in the Open-ALAQS toolbar.

### Open an existing study

To open a previously created project, click on the **OPEN** button in the Open-ALAQS toolbar. This action opens a pop-up window (**Open an ALAQS database file**), allowing you to select an existing Open-ALAQS database (**.alaqs**) file.

### Import OpenStreetMap data

An additional functionality is added to Open-ALAQS to facilitate the creation of emission sources based on the geographic data (roads, buildings, points of interest, and more) provided by OpenStreetMap.

![import-osm-data.PNG](./../open_alaqs/assets/import-osm-data.PNG)

Using Nominatim, a search engine that uses the data from OpenStreetMap to provide geocoding (address to coordinates), directly from the Open-ALAQS toolbar the user can select and import airport related geographical data to the study. The image below illustrates the information that can be collected from OpenStreetMap.

![import-osm-data-ex2.PNG](./../open_alaqs/assets/import-osm-data-ex2.PNG)

## Define emission sources
[(Back to top)](#table-of-contents)

### Add Features

New objects can be added using the **Digitizing** toolbar.

![digitizing-toolbar.PNG](./../open_alaqs/assets/digitizing-toolbar.PNG)

More information on how to use this toolbar is provided in the [QGIS User Manual](https://docs.qgis.org/3.34/en/docs/user_manual/working_with_vector/editing_geometry_attributes.html#digitizing-an-existing-layer).

To create a new emission source, select the desired layer (e.g., taxiway or runway) to activate it and click **Toggle Editing** in the **Digitizing** toolbar. Then click **Add Feature** to start designing the new feature. Once finished, right click and fill the attribute fields in the pop-up window.

![layers.PNG](./../open_alaqs/assets/layers.PNG)

### Edit Features

Using the **Digitizing** toolbar in editing mode (**Toggle Editing**), it is possible to employ the **Vertex Tool** to edit objects.

### Delete Features

To delete one or more features, first select the geometry using the **Selection** toolbar (_Select Features by area or single click_) and use the **Delete Selected** tool to delete the feature(s). Multiple selected features can be deleted at once. Selection can also be done from the Attributes table.

### Visualize and Edit Attribute Values

Attribute values can also be modified after an object's creation via the **Attributes** toolbar.

![attributes.PNG](./../open_alaqs/assets/attributes.PNG)

The **Open Attribute Table** functionality can be accessed through the **Attributes** toolbar or via the **Layers** panel (by right-clicking on the appropriate layer).

### Aircraft related Sources

Calculating aircraft emissions requires the definition of three distinct layers: runways, taxiways, gates. For each of these features, the user must provide the required attributes. Defining Tracks (i.e., aircraft trajectories) is also possible; however, this functionnality is not yet fully implemented.

#### Gates

An airport gate refers to a designated location at an airport where aircraft park for boarding and disembarking passengers, loading/unloading cargo, and receiving services like refuelling, catering, and maintenance.

In Open-ALAQS, gates are represented as polygons. Each gate can encompass several aircraft stands. The more stands grouped together within a single gate area, the less data preparation is needed (e.g., fewer taxi routes to define). However, if the gate area is too large, it might no longer accurately represent the location of the emissions.

Calculating gate emissions requires establishing the sum of four emission sources: GSE (Ground Support Equipment), GPU (Ground Power Unit), APU (Auxiliary Power Unit) and MES (Main Engine Start).

![gates.PNG](./../open_alaqs/assets/gates.PNG)

When adding a gate, the following information is required:
+ Gate type (PIER, REMOTE or CARGO)
+ Gate height _not yet fully implemented_

In Open-ALAQS, GSE and GPU emissions factors, expressed in terms of grams of pollutant per hour, is assigned to each gate as a function of:
+ The gate type (PIER, REMOTE or CARGO)
+ The aircraft category (JET BUSINESS/REGIONAL/SMALL/MEDIUM/LARGE,TURBOPROPS,PISTON)
+ The operation type (Arrival or Departure)

The corresponding GSE/GPU emission factors and activity time are included in the Open-ALAQS database (see [default_gate_profiles](./../open_alaqs/database/data/default_gate_profiles.csv)).

APU emissions are calculated separately as a function of the APU model (apu_id) indicated for each aircraft (if available) in the database (see [default_aircraft](./../open_alaqs/database/data/default_aircraft.csv)).

The default APU emission factors and operating times are given in the database files: [default_aircraft_apu_ef](./../open_alaqs/database/data/default_aircraft_apu_ef.csv) and [default_apu_times](./../open_alaqs/database/data/default_apu_times.csv) respectively.

Default MES emission factors per aircraft group are given in the table [default_aircraft_start_ef](./../open_alaqs/database/data/default_aircraft_start_ef.csv).

#### Runways

Runways are linear features that define the vertical plane where approach, landing, take-off, and climb-out operations occur. Each end of the runway is designated as a specific runway, depending on the direction of movement.

When adding a taxiway, the following information is required:
+ Capacity (departures/hour) - _not yet fully implemented_
+ Touchdown offset (meters) - _not yet fully implemented_
+ Maximum queue speed (km/h) - _not yet fully implemented_
+ Peak queue time (minutes) - _not yet fully implemented_

![runways-layer.PNG](./../open_alaqs/assets/runways-layer.PNG)

Airport runways are named based on their compass heading, rounded to the nearest 10 degrees. The runway number corresponds to the first two digits of its compass direction. For example, a
runway aligned with 10 degrees is labeled as "01" while one aligned with 190 degrees is labeled "19".

Since runways can be used in both directions, each end has a different number, differing by 18 (180 degrees). For example, a runway labeled "01" on one end will be "19" on the opposite
end. If an airport has parallel runways, they may be further differentiated by letters like "L" (Left), "C"(Center), or "R" (Right).

The runway emissions are calculated based on the aircraft trajectories (profiles) provided in the [Aircraft Noise and Performance (ANP)](https://www.easa.europa.eu/en/domains/environment/policy-support-and-research/aircraft-noise-and-performance-anp-data) database. For more information, see the [ANP](#anp-db) section.

#### Taxiways

An airport taxiway is a designated path that connects runways with terminals, gates, runways or other parts of the airport. When adding a taxiway in an Open-ALAQS study, the following information is mandatory:
+ Name
+ Speed (km/h)

![taxiways-layer.PNG](./../open_alaqs/assets/taxiways-layer.PNG)

The length of each taxiway is calculated automatically from its geometry and the time spent on it is calculated from the indicated speed and length. Recommended taxiing speeds vary in relation to ambient conditions, traffic, aircraft position on the taxi route etc. Typical taxiing speeds lie between 10 and 40 km/h (~5 and ~25 kts).

It is important to distinguish between taxiways and taxi-routes. Taxi-routes describe the operational path that will be followed by an aircraft for a runway / stand / movement type (arrival or departure) combination. Taxi-routes are defined as a series of taxiway segments in Open-ALAQS. It greatly facilitates the capturing of taxi-route details (such as curved turns) since when defining taxi routes, multiple taxiway segments can be combined.

The process of defining taxi routes is detailed in the [Test Case Study](#test-case-study) section.

#### Tracks

Aircraft tracks can be designed to indicate the aircraft trajectory. When adding aircraft tracks, the following information is mandatory:
+ Track Name
+ Runway (from the list of previously defined runways)
+ Operation Type (Arrival or Departure)

![tracks-layer.PNG](./../open_alaqs/assets/tracks-layer.PNG)

We note that this functionality is **not yet fully implemented** in Open-ALAQS. The default [ANP](https://www.easa.europa.eu/en/domains/environment/policy-support-and-research/aircraft-noise-and-performance-anp-data) profiles are used to indicate the aircraft trajectories.

### Stationary (Non-Aircraft) Sources

## Activity Profiles
[(Back to top)](#table-of-contents)

Activity Profiles are used to describe the relative hourly/daily/monthly operational mode for each airport emission source. The **Activity Profiles Editor** in the Open-ALAQS toolbar can be used to review, edit, and create custom profiles.

![activity-profiles.PNG](./../open_alaqs/assets/activity-profiles.PNG)

Each activity multiplier is a decimal number, between 0 and 1. The default profile values are 1 (i.e., 100%) meaning the emission source is fully active. On the other hand, if, the emission source is deactivated during a specific time interval (e.g., during night-time curfew) the user can modify accordingly the activity profile by setting the corresponding multiplier to 0 for this specific period (hour, day, or month).

## Generating Emission Inventory
[(Back to top)](#table-of-contents)

## Visualization of Results
[(Back to top)](#table-of-contents)

# Auxiliary Material
[(Back to top)](#table-of-contents)

## AUSTAL
[(Back to top)](#table-of-contents)

The dispersion model [AUSTAL](https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/overview) is the reference implementation to Annex 2 of the German Environment Agency’s Technical Instructions on Air Quality Control (TA Luft) and implements the specifications and requirements given therein.

The program is the successor of AUSTAL2000 (which was previously used with Open-ALAQS), the reference implementation to Annex 3 of the TA Luft 2002. AUSTAL and AUSTAL2000 were developed by Janicke Consulting on behalf of the German Environment Agency and are freely available and widely used internationally.

AUSTAL 3.3.0 (released on 22.03.2024) has been developed and tested under Windows and Linux. It is exclusively provided, free of charge under the GNU Public Licence, from the dedicated webpage
of the German Environment Agency.

No installation is needed for use with Open-ALAQS as the executables are already included in the Open-ALAQS package.

## COPERT
[(Back to top)](#table-of-contents)

## ANP
[(Back to top)](#table-of-contents)

## Open-ALAQS Database
[(Back to top)](#table-of-contents)

# Test Case Study
[(Back to top)](#table-of-contents)

In this section a test case study is presented. The purpose of this training exercise is to guide the first-time user throughout the main steps of an Open-ALAQS project. This test case is based on theoretical data only. All the necessary input files are provided in the [example](./../open_alaqs/example/) directory of the Open-ALAQS plugin.
