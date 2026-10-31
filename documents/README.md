# OpenALAQS documentation

This index lists every document, by what you want to do and by reader. Installation and a quick overview are in the [main README](../README.md). Unknown term: see the [glossary](GLOSSARY.md). Error message: see [Troubleshooting](user/TROUBLESHOOTING.md).

## By task

| How to... | Read |
|---|---|
| install the plugin | [README, Installation](../README.md#installation) |
| install AUSTAL | [AUSTAL installation](AUSTAL/AUSTAL.md) |
| learn with a complete example | [Tutorial: Rotterdam The Hague Airport](user/TUTORIAL_ROTTERDAM.md) |
| build a study: airport layout and sources | [User Guide, Define emission sources](user/USER_GUIDE.md#define-emission-sources) |
| prepare the movements file | [Input formats, Movements](user/INPUT_FORMATS.md#movements) |
| prepare the meteorological file | [Input formats, Meteorology](user/INPUT_FORMATS.md#meteorology), or convert METAR with [metar_to_alaqs_meteo.py](../scripts/README_metar_to_alaqs_meteo.md) |
| use recorded flight tracks (ADS-B) | [Input formats, ADS-B tracks](user/INPUT_FORMATS.md#ads-b-tracks) |
| model an engine run-up pad | [User Guide, Engine test sites](user/USER_GUIDE.md#engine-test-sites) |
| set when stationary sources emit | [User Guide, Activity Profiles](user/USER_GUIDE.md#activity-profiles) |
| generate the inventory | [User Guide, Calculate Emissions Inventory window](user/USER_GUIDE.md#calculate-emissions-inventory-window) |
| choose the emission method and calculate | [User Guide, Calculate emissions](user/USER_GUIDE.md#calculate-emissions-and-query-results) |
| run AUSTAL and map the concentrations | [Dispersion modelling with AUSTAL](user/DISPERSION_AUSTAL.md) |
| check compliance with the EU limit values | [Dispersion, The compliance report](user/DISPERSION_AUSTAL.md#the-compliance-report) |
| open a study made with an earlier version | [Upgrading](user/UPGRADING.md) |
| run batch calculations without QGIS | [Running without the QGIS window](user/WITHOUT_QGIS.md) |
| fix an error message | [Troubleshooting](user/TROUBLESHOOTING.md) |
| check that the installation gives the reference results | [Validation guide](validation/VALIDATION_GUIDE.md) |

## For users

| Document | Content |
|---|---|
| [User Guide](user/USER_GUIDE.md) | the plugin step by step: toolbar, study, sources, profiles, inventory, emissions |
| [Tutorial: Rotterdam The Hague Airport](user/TUTORIAL_ROTTERDAM.md) | the shipped example built from scratch, with the values to enter |
| [Input formats](user/INPUT_FORMATS.md) | movements, meteorology, ADS-B, engine test events, receptor points |
| [Dispersion modelling with AUSTAL](user/DISPERSION_AUSTAL.md) | Calculate Dispersion dialog, Dispersion Models tab, site parameters, AUSTAL files, results |
| [AUSTAL installation](AUSTAL/AUSTAL.md) | download, install, the settings file |
| [Upgrading](user/UPGRADING.md) | what changes between versions and how to update a study |
| [Running without the QGIS window](user/WITHOUT_QGIS.md) | the command-line tools and when to use each |
| [Troubleshooting](user/TROUBLESHOOTING.md) | error messages and fixes |
| [Glossary](GLOSSARY.md) | terms and abbreviations |
| [Training course (PDF)](pdf/Airport%20Local%20Air%20Quality%20Studies%20with%20OpenALAQS%20-%20Training%20Course.pdf) | the slides of the training course (March 2026); [errata](user/TRAINING_COURSE_ERRATA.md) for 5.4.1 |

## For modellers: how the results are calculated

| Document | Content |
|---|---|
| [Aircraft emissions](methods/AIRCRAFT_EMISSIONS.md) | bymode and BFFM2, fuel flow, NOx correction, particulate matter, taxiing, APU, GSE, engine start, flight profiles, ADS-B |
| [Ambient conditions aloft](methods/ATMOSPHERE_ALOFT.md) | temperature, pressure and humidity at each segment's height |
| [Helicopters](methods/HELICOPTERS.md) | FOCA 2015 method, catalog, trajectories |
| [Stationary sources and road traffic](methods/STATIONARY_AND_ROAD.md) | COPERT roadways and parkings, point and area sources, engine test sites, Smooth & Shift |
| [Reference data](methods/REFERENCE_DATA.md) | the default database tables and where their data come from |
| [Derivation of the Smooth & Shift parameters (PDF)](pdf/038_Derivation_of_Smooth_and_Shift_Parameters_for_ALAQS-AV.pdf) | EUROCONTROL report EEC/SEE/2005/016 |

## Validation

| Document | Content |
|---|---|
| [Validation guide](validation/VALIDATION_GUIDE.md) | the checks V1 to V5, how to run them and the tolerances |
| [CAEP14 reference validation](../openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md) | the reference implementation and how to update it |

## Command-line tools

| Document | Content |
|---|---|
| [Standalone pipeline: usage](../openalaqs_standalone/USAGE.md) | commands, options, config.json, output folders |
| [Standalone pipeline: architecture](../openalaqs_standalone/README.md) | modules, conventions, limitations, tests |
| [Scripts](../scripts/README.md) | migrate_alaqs, import_engine_test_events, the other scripts |
| [METAR to meteo](../scripts/README_metar_to_alaqs_meteo.md) | building the meteorological file from METAR |
| [emissions_austal](../scripts/emissions_austal/README.md), [austal_from_csv](../scripts/austal_from_csv/README.md) | emissions and AUSTAL inputs with the plugin code |
| [GSE application](../gse_application/README.md) | ground support equipment emissions |
| [Example configurations](../example/training/recipe_config.README.md), [example engine test events](../example/training/training_engine_test_events.README.md) | files of the training example |

## For maintainers

| Document | Content |
|---|---|
| [Code structure and calculation flow](developer/CODE_FLOW.md) | where each step of the calculation is in the code |
| [Known regression patterns](developer/REGRESSION_PATTERNS.md) | symptoms, causes and where to look |
| [Aircraft profiles provenance](developer/AIRCRAFT_PROFILES_PROVENANCE.md), [COPERT dataset provenance](developer/DATASET_PROVENANCE.md) | origin and corrections of the reference data |
| [Schema deprecations](developer/DEPRECATIONS.md) | unused database columns and the schema plan |
| [Design: atmosphere aloft validation](developer/design/ATMOSPHERE_ALOFT_VALIDATION.md) | design note and its evidence |
| [Template build](../tools/template_build/README.md), [ANP 2.2 profiles builder](../tools/anp22_profiles/README.md), [Test fixtures](../tools/test_fixtures/README.md) | tools that rebuild the shipped data |
| [CHANGELOG](../CHANGELOG.md) | what changed in each version |

## Writing documentation

Each topic has one page; other pages give a sentence and link to it, so a change is made in one place. Before a pull request, run `python3 tools/check_doc_links.py` from the repository root. To preview the documentation site with search, see [README, Documentation site](../README.md#documentation-site).
