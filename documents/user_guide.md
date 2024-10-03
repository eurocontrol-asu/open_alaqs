# Open-ALAQS User Guide

## Table of Contents
- [Project Title](#project-title)
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
    - [Activity Profiles](#activity-profiles)
    - [Aircraft related Sources](#aircraft-sources)
    - [Stationary (Non-Aircraft) Sources](#non-aircraft-sources)
  - [Generating Emission Inventory](#generating-emission-inventory)
  - [Visualization of Results](#visualization-of-results)
  - [AUSTAL](#austal)
  - [COPERT](#copert)
  - [ANP](#anp-db)
  - [Open-ALAQS Database](#oa-database)
- [FAQs](#faqs)
- [Contact](#contact)

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

<p align="center">
  <img src="./../open_alaqs/assets/import-osm-data.PNG" alt="Import OSM Data" />
</p>

Using Nominatim, a search engine that uses the data from OpenStreetMap to provide geocoding (address to coordinates), directly from the Open-ALAQS toolbar the user can select and import airport related geographical data to the study. The image below illustrates the information that can be collected from OpenStreetMap.

<p align="center">
  <img src="./../open_alaqs/assets/import-osm-data-ex2.PNG" alt="Import OSM Data" />
</p>

## Define emission sources

### Add Features

### Edit Features

### Delete Features

### Visualize and Edit Attribute Values

### Activity Profiles

### Aircraft related Sources

### Stationary (Non-Aircraft) Sources

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
