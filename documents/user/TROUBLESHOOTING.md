# Troubleshooting

This page lists the error messages and symptoms users most often meet, grouped by step of a study, with the cause and the fix. Each entry links to the page that explains the topic in full. Search this page for the words of the message you see (Ctrl+F, or the search box of the documentation site).

Most messages are also written to the OpenALAQS log: toolbar button **Review Open ALAQS logs** ([User Guide](USER_GUIDE.md#the-openalaqs-toolbar)).

## Contents

- [Installation](#installation)
- [Opening or updating a study](#opening-or-updating-a-study)
- [Input files](#input-files)
- [Emissions](#emissions)
- [Dispersion with AUSTAL](#dispersion-with-austal)
- [Running without QGIS](#running-without-qgis)

## Installation

**QGIS asks to install missing Python libraries when Open-ALAQS loads.**
The plugin needs libraries that QGIS does not ship. Accept the QPIP dialog, then restart QGIS once. Without QPIP, install `requirements.txt` in the QGIS Python. See [Install the dependencies](../../README.md#install-the-dependencies).

**The plugin does not appear after installing from a clone.**
The plugin is the `open_alaqs/` folder of the repository, not the repository root: `metadata.txt` must be directly inside the plugin folder. See [Install Open-ALAQS](../../README.md#install-open-alaqs).

## Opening or updating a study

**A form field turns red with "Upgrade the study with scripts/migrate_alaqs.py", or the log says "QGIS types the numeric columns ... as integer or text".**
The study was made with an earlier version. Update it with `scripts/migrate_alaqs.py`, after a backup. See [Upgrading](UPGRADING.md).

**The log says "default_helicopter table missing" and helicopter movements find no helicopter.**
The study predates the helicopter catalog. Run the migration with the reference data refresh. See [Upgrading from 5.3.x](UPGRADING.md#upgrading-from-53x).

**Results differ from those of an earlier version.**
This is expected when a release changes a method or the reference data. [Upgrading](UPGRADING.md) lists what changes, and the [CHANGELOG](../../CHANGELOG.md) gives the details.

**The OpenStreetMap import is disabled, or does nothing.**
The import needs the QuickOSM QGIS plugin. Without the airport latitude and longitude in the study setup it silently does nothing. Without **Also import the data into ALAQS database** the data go only to an *OpenStreetMap Layers* group. See [Import OpenStreetMap data](USER_GUIDE.md#import-openstreetmap-data).

## Input files

**"Headers of meteo csv file do not match".**
The meteo file must have exactly the ten headers, written with their units in brackets, for example `Temperature(K)`. A missing, extra or renamed header is refused. See [Meteorology](INPUT_FORMATS.md#meteorology). [`scripts/metar_to_alaqs_meteo.py`](../../scripts/README_metar_to_alaqs_meteo.md) writes a valid file from METAR observations.

**"Problem with movement file. See log file", or the movement columns are read in the wrong order.**
One bad row (date, fewer than 10 fields) refuses the whole file; the log names the row. One missing or misspelt header name makes the plugin read every column by position. Use the exact header names. See [Movements](INPUT_FORMATS.md#movements).

**"To import ADS-B data, at least one runway should exist in the study!"**
Draw the runways before selecting the ADS-B file. See [ADS-B tracks](INPUT_FORMATS.md#ads-b-tracks).

**The log says "Lack of profile_id" for a movement.**
The movement names a flight profile that is not in the study. The aircraft's default profile is used instead. Check the `profile_id` column of the movements file, or the profiles of the study. See [Flight profiles](../methods/AIRCRAFT_EMISSIONS.md#flight-profiles-anp).

**Engine test events are skipped.**
When the file is loaded from one source's form, rows for other sources are skipped and counted in the import summary. Use [`scripts/import_engine_test_events.py`](../../scripts/README.md#import_engine_test_eventspy) to load a file for several sources at once. Column specification: [Engine test events](INPUT_FORMATS.md#engine-test-events).

## Emissions

**BFFM2 is not offered for a pollutant.**
BFFM2 gives emission indices for NOx, CO and HC only. For another pollutant **Method** shows `bymode`; when you return to CO, HC or NOx, BFFM2 comes back if you had chosen it. See [Calculate emissions](USER_GUIDE.md#calculate-emissions-and-query-results).

**The NOx correction changes nothing.**
The correction applies to `bymode` only. BFFM2 includes its own ambient correction, and helicopters follow the FOCA method. See [NOx ambient correction](../methods/AIRCRAFT_EMISSIONS.md#nox-ambient-correction).

**A stationary source has no emissions.**
Check that it is in the study (**In Study** ticked) and that its activity and profiles are not zero. See [Point and area sources](../methods/STATIONARY_AND_ROAD.md#point-and-area-sources) and [Activity Profiles](USER_GUIDE.md#activity-profiles).

## Dispersion with AUSTAL

Each symptom below is explained, with its fix, in [Common failure modes](DISPERSION_AUSTAL.md#common-failure-modes).

- "No Executable Loaded" after picking AUSTAL.
- The run fails, or some substances have no results.
- "AUSTAL input files could not be created: the selected time period" when generating the input files.
- A result button says "No emission calculation loaded".
- Plot Time Series and Compliance Report stay disabled.

Two more:

**The site parameters (z0, d0, ha) of the Dispersion Models tab are not in `austal.txt`.**
The **Calculate Dispersion** dialog writes its own Roughness Length, Displacement Height and Anemometer Height, not those of the tab. Set them in the dialog before **Generate AUSTAL Input Files**. See [Site parameters](DISPERSION_AUSTAL.md#site-parameters).

**The dispersion results do not match the emission method chosen for the study.**
The **Calculate Dispersion** dialog recalculates the emissions with its own emission settings (default `bymode`, no NOx correction, no source dynamics). Set them to those of the study in the inventory option. See [Calculate Dispersion dialog](DISPERSION_AUSTAL.md#2-input-file-strategy).

## Running without QGIS

**`ModuleNotFoundError` for `open_alaqs...` when running the standalone pipeline.**
Run it from the repository root with `PYTHONPATH=.`. See [USAGE, Troubleshooting](../../openalaqs_standalone/USAGE.md#troubleshooting).

**`ModuleNotFoundError: No module named 'qgis'` when running a script.**
`scripts/emissions_austal`, `scripts/austal_from_csv` and the GSE application need the QGIS Python (for example the OSGeo4W Shell). The QGIS-free alternative is the standalone pipeline. See [Running without the QGIS window](WITHOUT_QGIS.md).

## See also

- [User Guide](USER_GUIDE.md)
- [Input formats](INPUT_FORMATS.md)
- [Dispersion modelling with AUSTAL](DISPERSION_AUSTAL.md)
- [Glossary](../GLOSSARY.md)
