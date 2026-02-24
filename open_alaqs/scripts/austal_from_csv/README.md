# [BETA] Standalone Script to use AUSTAL from CSV Files — Usage Guide

This document explains how to run `run_austal_from_csv.py` from the OSGeo4W Shell (recommended) and describes the expected configuration file format and available options.

This script generates AUSTAL dispersion-model input files directly from pre-calculated **emissions CSV** and **meteorology CSV** files, without requiring an OpenALAQS `.alaqs` database. This is useful when emissions have already been computed (e.g. by `run_emissions_austal.py`) and you want to regenerate or customise the AUSTAL input files independently.

---

## Why use OSGeo4W Shell

- The script uses QGIS/PyQt and GDAL libraries (SpatiaLite). Launching it from the OSGeo4W Shell ensures the correct Python environment and native libraries are available.

## Basic Steps (OSGeo4W Shell)

1. Open the **OSGeo4W Shell** from your Start menu.
2. Navigate to the folder containing `run_austal_from_csv.py`. This is typically your per-user QGIS plugin install folder:

```powershell
# Typical per-user QGIS plugin install (use %APPDATA% to avoid hardcoding user):
cd %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\open_alaqs
```

3. Run the script using the `python-qgis` command with the path to your config text file:

```powershell
python-qgis scripts\austal_from_csv\run_austal_from_csv.py "C:\path\to\my_config.txt" --timing
```

---

## Advanced: Alternative Execution Methods

### Calling python-qgis.bat directly (OSGeo4W Shell)

If the basic steps above failed or QGIS is installed system-wide:

```powershell
# OSGeo4W Shell (Command Prompt) — use "call" command
call "C:\Program Files\QGIS <Version>\bin\python-qgis-ltr.bat" "C:\path\to\run_austal_from_csv.py" "C:\path\to\config.txt" --timing
```

Note: Replace `C:\Program Files\QGIS <Version>` with your actual QGIS installation directory. The batch file may be named `python-qgis.bat` or `python-qgis-ltr.bat` depending on your QGIS version.

### IDE Terminal (VS Code, PyCharm, PowerShell)

From any PowerShell terminal (including IDE terminals), use the `&` operator:

```powershell
# PowerShell — use "&" operator
& "C:\Program Files\QGIS <Version>\bin\python-qgis-ltr.bat" "C:\path\to\run_austal_from_csv.py" "C:\path\to\config.txt" --timing
```

### Using python-qgis shortcut (OSGeo4W Shell only)

The `python-qgis` command is only available from the **OSGeo4W Shell**, not from a regular PowerShell terminal:

```powershell
cd C:\path\to\openalaqs
python-qgis open_alaqs\scripts\austal_from_csv\run_austal_from_csv.py "C:\path\to\config.txt" --timing
```

**Note:** If `python-qgis` is not recognised in your PowerShell terminal, you're not in the OSGeo4W Shell. Use the IDE Terminal method (with full path to `python-qgis-ltr.bat`) instead.

---

## Command-Line Flags

| Flag        | Description                                              |
|-------------|----------------------------------------------------------|
| `--timing`  | Print elapsed time summary on completion                 |
| `--dry-run` | Parse and validate config without generating any files   |

---

## Configuration File Format

The config file is a simple **key=value** plain text file. Lines starting with `#` are comments and ignored. Environment variables (e.g. `%USERPROFILE%`) are expanded in path values.

See `example.txt` in this folder for a complete annotated example.

### Required Keys

| Key                     | Type   | Description                                                     |
|-------------------------|--------|-----------------------------------------------------------------|
| `emissions_csv_path`    | path   | Path to emissions CSV (TableViewWidgetOutputModule format)      |
| `meteo_csv_path`        | path   | Path to meteorology CSV (AmbientConditionStore format)          |
| `output_path`           | path   | Directory where AUSTAL input files will be written              |
| `pollutants`            | string | Comma-separated pollutant list (e.g. `NOx,CO,PM10`)            |

### Grid Definition (one of the two options is required)

**Option A — Grid file** (simplest):

| Key                     | Type   | Description                                                     |
|-------------------------|--------|-----------------------------------------------------------------|
| `grid_file_path`        | path   | Path to a `.csv` or `.alaqs` file containing the grid definition|

The CSV must have a header row with columns: `x_cells`, `y_cells`, `z_cells`, `x_resolution`, `y_resolution`, `z_resolution`, `reference_latitude`, `reference_longitude`, `reference_altitude`, followed by a single data row. An `.alaqs` file is read from its `grid_3d_definition` and `user_study_setup` tables.

**Option B — Manual grid keys:**

| Key                     | Type   | Description                                                     |
|-------------------------|--------|-----------------------------------------------------------------|
| `x_cells`               | int    | Number of grid cells in X                                       |
| `y_cells`               | int    | Number of grid cells in Y                                       |
| `z_cells`               | int    | Number of grid cells in Z                                       |
| `x_resolution`          | float  | Cell size in X (metres)                                         |
| `y_resolution`          | float  | Cell size in Y (metres)                                         |
| `z_resolution`          | float  | Cell size in Z (metres)                                         |
| `reference_latitude`    | float  | Grid origin latitude (decimal degrees, WGS84)                  |
| `reference_longitude`   | float  | Grid origin longitude (decimal degrees, WGS84)                 |

### Optional Keys

| Key                       | Type   | Default                         | Description                                      |
|---------------------------|--------|---------------------------------|--------------------------------------------------|
| `reference_altitude`      | float  | `0.0`                           | Grid origin altitude (m above sea level)         |
| `quality_level`           | int    | `1`                             | AUSTAL quality level (1=fastest, 3=most accurate)|
| `mixing_height_enabled`   | bool   | `False`                         | Include mixing height in AUSTAL series file      |
| `options_string`          | string | `NOSTANDARD;SCINOTAT;Kmax=1`    | AUSTAL options flags                             |
| `roughness_length_m`      | float  | `0.2`                           | Aerodynamic roughness length (m)                 |
| `displacement_height_m`   | float  | `1.2`                           | Zero-plane displacement height (m)               |
| `anemometer_height_m`     | float  | `11.2`                          | Anemometer height (m)                            |
| `show_logs`               | bool   | `False`                         | Show detailed logs during generation             |

### Accepted Pollutant Values

`CO2`, `CO`, `HC`, `NOx`, `SOx`, `PM10`

### Boolean Values

Boolean keys accept (case-insensitive): `True`, `1`, `yes` for true; anything else is treated as false.

---

## Input CSV Formats

### Emissions CSV

The emissions CSV must follow the **TableViewWidgetOutputModule** format:

| Column           | Required | Description                                           |
|------------------|----------|-------------------------------------------------------|
| `timestamp`      | Yes      | Datetime of the emission record                       |
| `wkt`            | Yes      | WKT geometry string (rows without WKT are skipped)    |
| `source_type`    | No       | Source type label (used for logging only)              |
| `source_name`    | No       | Source name label (used for logging only)              |
| `*_kg`           | Yes      | Any column ending in `_kg` is read as a pollutant emission (e.g. `nox_kg`, `co_kg`) |

### Meteorology CSV

The meteorology CSV must follow the **AmbientConditionStore** format:

| Column                             | Required | Description                    |
|------------------------------------|----------|--------------------------------|
| `DateTime(YYYY-mm-dd hh:mm:ss)`   | Yes      | Observation datetime           |
| `WindSpeed(m/s)`                   | Yes      | Wind speed                     |
| `WindDirection(degrees)`           | Yes      | Wind direction                 |
| `ObukhovLength(m)`                 | Yes      | Obukhov length                 |
| `MixingHeight(m)`                  | Yes      | Mixing layer height            |

Optional meteorology columns (parsed but not forwarded to AUSTAL):
- `Temperature(K)`
- `Humidity(kg_water/kg_dry_air)`
- `RelativeHumidity(%)`
- `SeaLevelPressure(Pa)`
- `Scenario`

---

## Minimal Example Configs

### Using a grid file (Option A)

```ini
emissions_csv_path=C:\data\emissions.csv
meteo_csv_path=C:\data\meteo.csv
output_path=C:\data\austal_output
pollutants=NOx,PM10
grid_file_path=C:\data\grid.csv
```

### Using manual grid keys (Option B)

```ini
emissions_csv_path=C:\data\emissions.csv
meteo_csv_path=C:\data\meteo.csv
output_path=C:\data\austal_output
pollutants=NOx,PM10
x_cells=50
y_cells=50
z_cells=1
x_resolution=100
y_resolution=100
z_resolution=50
reference_latitude=48.6900
reference_longitude=9.2220
```

---

## Output Files

The script generates the following AUSTAL input files inside the `output_path` directory:

- `austal.txt` — main AUSTAL configuration file
- `series.dmna` / `series.dmna` header + data — meteorology time series
- Source emission files — one per active source/timestep

These files can be used directly with the AUSTAL executable or loaded back via the QGIS plugin's "Use Existing AUSTAL Input Files" option.

---

## Workflow: Using with run_emissions_austal.py

A typical two-step workflow:

1. **Generate emissions** using the `run_emissions_austal.py` script (in `scripts/individual_script/`), which exports a CSV file with `--csv` flag.
2. **Generate AUSTAL input files** using this script, pointing `emissions_csv_path` to the CSV output from step 1.

This separation allows you to:
- Recalculate AUSTAL inputs with different grid/quality settings without re-running the emission calculation
- Use emissions from external tools or modified/filtered CSVs
- Batch-process multiple grid configurations from the same emissions data

---

## QGIS Plugin / open_alaqs Path

If you run the script from inside the QGIS Python environment (e.g. when the project is installed as a QGIS plugin), ensure the Python import path points to the installed plugin location. The script automatically searches:
1. Development workspace (script inside plugin tree)
2. Workspace root
3. QGIS user plugins directory (`%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins`)

---

## Troubleshooting

- **QGIS import failure**: Confirm you're running from the OSGeo4W Shell so the required native libraries (GDAL, SpatiaLite) are available.
- **"emissions_csv_path does not exist"**: Verify the path and that environment variables are expanded correctly.
- **"Could not initialise SpatiaLite metadata"**: This typically means the SpatiaLite extension is not available. Run from the OSGeo4W Shell.
- **Verbose logging**: Set `show_logs=True` in the config for detailed output.

---

## Source

- Script location: `open_alaqs/scripts/austal_from_csv/run_austal_from_csv.py`
- Example config: `open_alaqs/scripts/austal_from_csv/example.txt`
