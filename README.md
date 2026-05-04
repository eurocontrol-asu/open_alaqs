# Open-ALAQS

QGIS plugin for airport emissions inventory and dispersion. Builds an annual emissions inventory from runway, taxiway, gate, stationary, and movement sources, and exports AUSTAL-ready dispersion inputs.

<img src="./open_alaqs/assets/oa-logo.jpg" alt="Open-ALAQS logo" width="50%">

## Table of contents

- [Open-ALAQS](#open-alaqs)
  - [Table of contents](#table-of-contents)
  - [Installation](#installation)
    - [Install QGIS](#install-qgis)
    - [Install dependencies](#install-dependencies)
    - [Install Open-ALAQS](#install-open-alaqs)
  - [Quick start](#quick-start)
    - [Example files](#example-files)
    - [Training example study](#training-example-study)
    - [Beta: Standalone Emissions + AUSTAL Inputs export script](#beta-standalone-emissions--austal-inputs-export-script)
  - [Workflow](#workflow)
  - [Emission calculation methods](#emission-calculation-methods)
  - [Meteorological data](#meteorological-data)
  - [GSE Application](#gse-application)
  - [Development](#development)
    - [Code style](#code-style)
    - [Debugging](#debugging)
    - [Updating the Open-ALAQS database templates](#updating-the-open-alaqs-database-templates)
    - [Unit tests](#unit-tests)
  - [Validation](#validation)
  - [Recent changes](#recent-changes)
  - [Contribute](#contribute)
  - [License](#license)
  - [Contact](#contact)

## Installation

[(Back to top)](#table-of-contents)

To use Open-ALAQS you need to install QGIS, plus a few external Python libraries the plugin depends on.

### Install QGIS

Download and install QGIS for your operating system following the official [QGIS documentation](https://qgis.org/download/).

If you are running on Windows, install via the [OSGeo4W installer](https://qgis.org/resources/installation-guide/#osgeo4w-installer) following the `Advanced Install` route.

> **Note:** If not installed using the OSGeo4W Network Installer, please uninstall any old version and install the new version using OSGeo4W or follow the QGIS installation guide. During installation, accept the unmet dependencies and license agreements.

### Install dependencies

Open-ALAQS is built on top of QGIS and a few external libraries that require separate installation. The full list is in `requirements.txt`.

**Primary method:** Use QPIP (Python Dependency Manager for QGIS Plugins) to check and install the required dependencies directly inside QGIS. See the **Install Open-ALAQS** section below for details.

**Alternative method:** Install the libraries manually using `pip install` in the Python environment used by QGIS:

```bash
pip install -r requirements.txt
```

<details>
<summary>OSGeo4W manual installation</summary>

Find and install these packages from the OSGeo4W shell:

- `qgis-ltr-full` (3.34.x or newer)
- `python3-fiona`
- `python3-geopandas` (2.x.x)

</details>

### Install Open-ALAQS

Open-ALAQS is published as a QGIS plugin. The cleanest way to install it is to clone the repository into the QGIS plugin directory for your platform:

- **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\open_alaqs\`
- **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/open_alaqs/`
- **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/open_alaqs/`

Then enable Open-ALAQS in the QGIS Plugin Manager (Plugins → Manage and Install Plugins → Installed → tick "Open-ALAQS").

The first time the plugin loads, QPIP will detect missing dependencies and offer to install them in the QGIS Python environment:

<img src="./open_alaqs/assets/install_dependencies_via_qpip.png" alt="QPIP dependency dialog" width="80%">

<img src="./open_alaqs/assets/install_plugin_dependencies.png" alt="QPIP install dialog" width="80%">

After dependencies are installed, restart QGIS once and Open-ALAQS will be available from the menu and toolbar:

<img src="./open_alaqs/assets/screenshot.png" alt="Open-ALAQS in QGIS" width="80%">

## Quick start

[(Back to top)](#table-of-contents)

### Example files

Two example studies ship with the repository:

- `example/training/` — a self-contained study used for tutorials and validation, including pre-computed reference values to compare your run against.
- `tests/data/AIRPORT_A/` — the same study used by the regression test suite, with full pre-computed emissions tables and APU/CAEP14 comparison spreadsheets.

### Training example study

The training study lives in `example/training/` and contains:

- `training.alaqs` — the unprocessed study database (geometry, sources, study setup)
- `training_out.alaqs` — the processed inventory database (Generate Emission Inventory output)
- `training_movements.csv` — aircraft movements input
- `training_meteo.csv` — hourly meteorological input
- `training_ads_b_data.csv` — ADS-B trajectory input (used by the BFFM2 trajectory method)
- `training_validation_reference.xlsx` — reference values for verifying your installation

For a step-by-step walk-through of opening, configuring, and running a study, see the [User Guide](documents/USER_GUIDE.md).

### Beta: Standalone Emissions + AUSTAL Inputs export script

A beta standalone script generates emissions exports (CSV/GeoJSON) and AUSTAL input files outside the QGIS plugin. It is experimental and may contain incomplete features.

- Script location: [`scripts/emissions_austal/run_emissions_austal.py`](scripts/emissions_austal/run_emissions_austal.py)
- Usage: see [`scripts/emissions_austal/README.md`](scripts/emissions_austal/README.md)
- A METAR-to-meteo converter is provided in [`scripts/metar_to_alaqs_meteo.py`](scripts/metar_to_alaqs_meteo.py) (see [`scripts/README_metar_to_alaqs_meteo.md`](scripts/README_metar_to_alaqs_meteo.md)) for producing the meteo CSV from raw METAR observations.
- A schema migration tool for upgrading legacy `.alaqs` files to the current schema is provided in [`scripts/migrate_alaqs.py`](scripts/migrate_alaqs.py).

See [`scripts/README.md`](scripts/README.md) for the full inventory of standalone scripts.

## Workflow

[(Back to top)](#table-of-contents)

1. Build the airport study (runways, taxiways, gates, stationary sources) in a QGIS project.
2. Open *Create Output* to bake the study into an inventory database, supplying a movements CSV and a meteorological CSV (see [Meteorological data](#meteorological-data)).
3. Run *Generate Emission Inventory* on the baked inventory to calculate emissions with the selected method.
4. For dispersion runs, see [`documents/AUSTAL/AUSTAL_OPERATION.md`](documents/AUSTAL/AUSTAL_OPERATION.md).

## Emission calculation methods

[(Back to top)](#table-of-contents)

Open-ALAQS ships three aircraft emission methods selectable at run time:

- **bymode** — multiplies anchor-mode fuel flow × anchor-mode EI × time × engine count. No ambient corrections. Use as a tautological baseline.
- **BFFM2 (trajectory)** — default BFFM2 path. For each trajectory segment resolves fuel flow from the segment's sub-mode power setting via the twin-quadratic fit, applies SAE AIR-5715 atmospheric corrections for NOx, and snaps CO/HC to the horizontal mean(CL, TO) value above the APP anchor in the standard-intersection case (CAEP14 v14 rule).
- **BFFM2 (mode_anchor)** — uses the mode anchor fuel flow (IDLE/APP/CL/TO EEDB values) as the BFFM2 input, still applying ambient corrections. Useful when trajectories lack per-segment sub-mode fidelity.

PM is via MEEM V1 at LTO (EEDB nvPM anchors unchanged at LTO altitudes). The MEEM V2 base method (ICAO CAEP/13-WG3) is also implemented for non-LTO altitudes. The MDG4 / Staged Combustion update is not implemented.

For BFFM2 implementation details see [`documents/BFFM2_validation/BFFM2.md`](documents/BFFM2_validation/BFFM2.md).

## Meteorological data

[(Back to top)](#table-of-contents)

Open-ALAQS expects an hourly meteo CSV during output creation. A standalone utility for producing it from a METAR stream ships in `scripts/`:

- [`scripts/metar_to_alaqs_meteo.py`](scripts/metar_to_alaqs_meteo.py) — parses METAR observations from stdin or a file, computes relative humidity from T/Td, buckets hourly, writes the ALAQS-schema CSV.
- [`scripts/README_metar_to_alaqs_meteo.md`](scripts/README_metar_to_alaqs_meteo.md) — usage and notes on where to fetch METAR data (NOAA Aviation Weather Center, ogimet.com, metar-taf.com API, python-metar). Fetching is deliberately left to the user; the script focuses on parsing and resampling.

## GSE Application

[(Back to top)](#table-of-contents)

A separate companion utility for ground support equipment (GSE) emissions lives in `gse_application/`. Launch with:

```bash
python3 gse_application/gse.py
```

See [`gse_application/README.md`](gse_application/README.md) for full documentation.

## Development

[(Back to top)](#table-of-contents)

### Code style

Open-ALAQS uses `pre-commit` to enforce code style and basic checks (autoflake, isort, black, flake8). Hooks run on every commit if `pre-commit` is installed in your local clone:

```bash
pip install pre-commit
pre-commit install
```

### Debugging

For debugging the plugin inside QGIS, you can enable QGIS's Python console (Plugins → Python Console) and use standard Python debugging tools.

### Updating the Open-ALAQS database templates

The plugin's `.alaqs` files are cloned from two template databases at `open_alaqs/core/templates/project.alaqs` (the project file users edit in QGIS) and `open_alaqs/core/templates/inventory.alaqs` (the inventory output file produced by Generate Emission Inventory).

Templates are built by `tools/template_build/generate_templates.py` from three inputs:

- `tools/template_build/spatialite_base.alaqs` — the bare SpatiaLite scaffold
- `tools/template_build/sql/*.sql` — table-creation scripts
- `open_alaqs/database/data/*.csv` — frozen reference-data CSVs

To regenerate the templates after editing source files:

```bash
python3 tools/template_build/generate_templates.py
```

The script needs a working QGIS Python environment; see [`tools/template_build/README.md`](tools/template_build/README.md) for the exact invocation on each platform.

### Unit tests

The full test suite runs offscreen and requires no display:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=$PWD python3 -m pytest tests/
```

## Validation

[(Back to top)](#table-of-contents)

Open-ALAQS is validated against the CAEP14 v14 reference spreadsheet (`CAEP14_FBE_Engines_Emissions_Calculation_Sheet_v14.xlsx`) to floating-point precision across bymode, BFFM2 trajectory, and BFFM2 mode_anchor methods, with non-volatile PM matching EEDB anchors exactly via MEEM V1 at LTO.

The full validation matrix, per-engine results, and cross-platform agreement evidence are in [`documents/BFFM2_validation/BFFM2.md`](documents/BFFM2_validation/BFFM2.md).

## Recent changes

[(Back to top)](#table-of-contents)

See [`CHANGELOG.md`](CHANGELOG.md) for fixes and behaviour changes in this and previous releases.

## Contribute

[(Back to top)](#table-of-contents)

Contributions are welcome. Please open an issue to discuss substantive changes before submitting a pull request, so the work is aligned with what the project needs. For small fixes (typos, documentation corrections, missing test cases), a direct pull request is fine.

When opening a pull request:

- Run the test suite locally and confirm it passes.
- Run `pre-commit run --all-files` and confirm all hooks pass.
- Include a regression test for any behaviour change.
- Reference the issue number in the PR title or body.

## License

[(Back to top)](#table-of-contents)

This software is published under European Union Public Licence v. 1.2 ([`LICENCE.md`](LICENCE.md)) with certain amendments described in [`AMENDMENT_TO_EUPL_license.md`](AMENDMENT_TO_EUPL_license.md), reflecting EUROCONTROL's status as an international organisation.

## Contact

[(Back to top)](#table-of-contents)

For questions, bug reports, or feature requests, please open an issue on the [GitHub repository](https://github.com/eurocontrol-asu/open_alaqs/issues).
