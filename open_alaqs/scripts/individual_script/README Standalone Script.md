# [BETA] Standalone Script Emissions + AUSTAL Input Files — Usage Guide

This document explains how to run `run_emissions_austal.py` from the OSGeo4W Shell (recommended) and describes the expected configuration file format and available options.



**Why use OSGeo4W Shell**
- The script uses QGIS/PyQt and GDAL libraries. Launching it from the OSGeo4W Shell ensures the correct Python environment and native libraries are available.

**Basic Steps (OSGeo4W Shell)**
1. Open the *OSGeo4W Shell* from your Start menu.
2. Navigate to the folder containing `run_emissions_austal.py`. This is typically your per-user QGIS plugin install folder:

```powershell
# Typical per-user QGIS plugin install (use %APPDATA% to avoid hardcoding user):
cd %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\open_alaqs
```

3. Run the script using the `python-qgis` command with the path to your config text file. Use an absolute path for the config file:

```powershell
# Run using the QGIS-aware python wrapper (e.g. python-qgis) with the plugin installed in AppData:
python-qgis scripts\individual_script\run_emissions_austal.py "C:\path\to\my_config.txt" --csv --geojson --austal --timing
```

## Advanced: Alternative Execution Methods

### Calling python-qgis.bat directly (OSGeo4W Shell)

If the basic steps above failed or QGIS is installed system-wide and not available in your per-user plugins folder, you can call the QGIS Python batch file directly from the **OSGeo4W Shell**:

```powershell
# OSGeo4W Shell (Command Prompt) - use "call" command
call "C:\Program Files\QGIS <Version>\bin\python-qgis-ltr.bat" "C:\path\to\run_emissions_austal.py" "C:\path\to\config.txt" --csv --geojson --austal
```

Note: Replace `C:\Program Files\QGIS <Version>` with your actual QGIS installation directory. The batch file may be named `python-qgis.bat` or `python-qgis-ltr.bat` depending on your QGIS version.

### IDE Terminal (VS Code, PyCharm, PowerShell)

From any PowerShell terminal (including IDE terminals), use the `&` operator to call the batch file:

```powershell
# PowerShell - use "&" operator
& "C:\Program Files\QGIS <Version>\bin\python-qgis-ltr.bat" "C:\path\to\run_emissions_austal.py" "C:\path\to\config.txt" --csv --geojson --austal
```

Note: No Python environment configuration required. Replace `C:\Program Files\QGIS <Version>` with your actual QGIS installation directory. The batch file may be named `python-qgis.bat` or `python-qgis-ltr.bat` depending on your QGIS version.

### Using python-qgis shortcut (OSGeo4W Shell only)

The `python-qgis` command is only available from the **OSGeo4W Shell**, not from a regular PowerShell terminal. If you're already in the OSGeo4W Shell:

```powershell
cd C:\path\to\openalaqs
python-qgis open_alaqs\scripts\individual_script\run_emissions_austal.py "C:\path\to\config.txt" --csv --geojson --austal --timing
```

**Note:** If `python-qgis` is not recognized in your PowerShell terminal, you're not in the OSGeo4W Shell. Use the IDE Terminal method (with full path to `python-qgis-ltr.bat`) instead.

- Flags:
  - `--csv` : export emissions to a CSV file
  - `--geojson` : export emissions as GeoJSON (QGIS vector) and save QML style. It can be dragged and dropped directly in QGIS afterwards.
  - `--austal` : generate AUSTAL dispersion model input files
  - `--timing` : show elapsed time summary

**Configuration file (txt) format**
- The config file is a simple key=value plain text file. Lines starting with `#` are ignored. Example keys and their expected formats:

- `db_path` (required): path to the .alaqs inventory database (e.g., `C:\path\to\example_db_out.alaqs`)
- `start_dt_inclusive` (required): ISO datetime, e.g. `2024-01-01T00:00:00`
- `end_dt_inclusive` (required): ISO datetime, e.g. `2024-01-01T23:00:00`
- `time_interval_seconds` (required): integer number of seconds between timesteps, e.g. `3600`
 - `time_interval_seconds` (required): integer number of seconds between timesteps, e.g. `3600`
 - `pollutant` (required): pollutant code. Accepted values: `CO`, `CO2`, `HC`, `NOx`, `PM10`, `SOx`.
- `method` (optional): calculation method, accepted values `bymode` or `BFFM2` (default `bymode`)
 - `source_type` (optional): source filtering (string or `all`). Accepted values: `AreaSource`, `MovementSource`, `ParkingSource`, `PointSource`, `RoadwaySource`, or `all` (default).
- `source_names` (optional): comma-separated list of source names to include, e.g. `GateA,GateB`
- `source_dynamics` (optional): handling mode for source dynamics; default `none` (accepted values include `none`, `default`, `smooth & shift`)
- `vertical_limit_m` (optional): vertical limit in meters (float), default `914.4`
- `should_apply_nox_corrections` (optional): `True` or `False` (case-insensitive)
- `show_logs` (optional): `True` or `False` — when `True`, external logs are shown
- `austal_output_path` (optional): output directory for AUSTAL files (overrides default)
- `emissions_output_path` (optional): output directory for CSV/GeoJSON (overrides default)
- `emissions_output_name` (optional): base name for CSV/GeoJSON files (default `emissions`).


**Valid option values (summary)**
- `db_path` (required): path to the ALaqs database file. Must point to an existing `.alaqs` file or other supported DB.
- `start_dt_inclusive` / `end_dt_inclusive` (required): ISO 8601 datetimes, e.g. `2024-01-01T00:00:00`.
- `time_interval_seconds` (required): integer seconds, e.g. `3600`.
`pollutant` (required): pollutant identifier (string). Accepted values: `CO`, `CO2`, `HC`, `NOx`, `PM10`, `SOx` — must match pollutant keys used by your database/calculation modules.
- `method` (optional): calculation method. Accepted values: `bymode` (default) or `BFFM2`.
- `source_type` (optional): filter by source type (string) or `all` (default).
 - `source_type` (optional): high-level type filter. Accepted values: `AreaSource`, `MovementSource`, `ParkingSource`, `PointSource`, `RoadwaySource`, or `all` (default).
- `source_names` (optional): comma-separated list of source names to include, e.g. `GateA,GateB`.
- `vertical_limit_m` (optional): float, vertical calculation limit in metres (default `914.4`).
 - `source_dynamics` (optional): string controlling source dynamics handling; accepted values include `none`, `default`, `smooth & shift` (various synonyms accepted, parser normalises them).
- `should_apply_nox_corrections` (optional): boolean `True` or `False`.
- `show_logs` (optional): boolean `True` or `False` — when `True`, logs and external output are not suppressed.
- `emissions_output_name` (optional): base name for CSV/GeoJSON files (default `emissions`).
- `emissions_output_path` / `austal_output_path` (optional): output directories. If omitted, defaults are used (see below) and the script will create the directories if missing.
- `view_type` (optional, used for CSV export): values accepted (case-insensitive) - `by aggregation`, `aggregation`, `aggregate` (all map to aggregation) or `by source`, `source` (maps to per-source view).
- `austal_settings` (optional): additional settings passed to the AUSTAL module (module-specific structure).

**Source filtering options**
- `source_type` (optional): high-level filter by source type (string), for example `all`, `ground`, `terminal`, etc. When not provided the script defaults to `all`.
- `source_names` (optional): comma-separated list of specific source names to include. Example: `source_names=GateA,GateB`. If omitted or empty, and `source_type` is not used to filter, the calculation will include all sources.
- `source_dynamics` (optional): how to handle source dynamics. Accepted, case-insensitive values include:
  - `none` — no dynamics handling (default)
  - `default` — use module default dynamics behaviour
  - `smooth & shift`, `smooth_shift`, `smooth&shift` — enable smooth-and-shift dynamics handling

Examples:
```
source_type=all
source_names=GateA,GateB
source_dynamics=smooth_shift
```

If you want to include all sources explicitly:
```
source_names=
source_dynamics=none
```

Notes on `source_names` / `source_dynamics`:
- If `source_names` is omitted (and `source_type` is not used to filter), the calculation will include all sources by default.
- Provide `source_names` in the txt file as a comma-separated string; the script will convert it to a list (e.g. `source_names=GateA,GateB`).
- `source_dynamics` is passed through to the emission calculation;

Accepted `source_dynamics` values (case-insensitive):
- `none` — no dynamics handling (default)
- `default` — use module default dynamics behaviour
- `smooth & shift` (also accepted as `smooth_shift`, `smooth&shift`) — enable smooth-and-shift dynamics handling

The parser normalises common synonyms to the canonical values `none`, `default`, `smooth`, `shift`, or `smooth_shift` before building the calculation config.

Notes on defaults and creation:
- When `emissions_output_path` or `austal_output_path` are provided in the config they are used as-is (environment variables expanded) and will be created if missing.
- When those keys are NOT present, the script now creates default `outputs/emissions/` and `outputs/austal/` next to the provided config `.txt` file (i.e. in the same directory as the config). If the config was provided as a relative path or the script was given a directory/archive, the resolved config file location is used. If no config file path is available, the script falls back to the relative defaults `outputs/emissions/` and `outputs/austal/` created relative to the current working directory.

**QGIS plugin / open_alaqs path**
- If you run the script from inside the QGIS Python environment (for example when the project is installed as a QGIS plugin), ensure the Python import path points to the installed plugin location rather than the repository source tree. Typical plugin install locations vary by OS and QGIS profile; use QGIS' Plugin Manager or check your QGIS profile directory for `python/plugins/open_alaqs` and ensure that directory is discoverable by Python when running the script from the QGIS Python console or a QGIS-enabled shell.

**Minimal example config**
```
# Minimal required config for run_emissions_austal.py
# Required keys:
#  - db_path: path to your .alaqs database
#  - start_dt_inclusive / end_dt_inclusive: ISO datetimes
#  - time_interval_seconds: integer seconds between timesteps
#  - pollutant: pollutant code (e.g. CO, NOx, PM10)

db_path= C:\path\to\my_study.alaqs
start_dt_inclusive=2024-01-01T00:00:00
end_dt_inclusive=2024-01-01T23:00:00
time_interval_seconds=3600
pollutant=NOx

# Optional (example): control output base name and paths
# emissions_output_name=my_emissions
# emissions_output_path=outputs\emissions\
# austal_output_path=outputs\austal\
```

**Output files**
- CSV: `{emissions_output_path}/{emissions_output_name}.csv` (default name `emissions`)
- GeoJSON: `{emissions_output_path}/{emissions_output_name}.geojson` plus `{emissions_output_name}.qml` for style (if available). The script also attempts to embed the QML style into the GeoJSON as `openalaqs_style`.
- AUSTAL inputs: files written inside the configured `austal_output_path`.

Naming the emissions outputs
- You can control the base filename used for CSV/GeoJSON/QML outputs with the `emissions_output_name` key in the config file. When provided, the script uses that string as the base name; otherwise it falls back to `emissions`.
- Example: if you set `emissions_output_name=my_emissions`, the script writes `my_emissions.csv`, `my_emissions.geojson` and `my_emissions.qml` (if a style is available) inside the `emissions_output_path`.

Using AUSTAL/GeoJSON outputs in QGIS
- GeoJSON/QML pairing: The GeoJSON vector exported by the script can be loaded into QGIS for visualising dispersion outputs. The script writes a `.geojson` vector and, when available, a matching `.qml` style file with the same base name (for example `emissions.geojson` and `emissions.qml`).
- Keep files together: To make QGIS automatically apply the style when you drag & drop the vector file into QGIS, ensure the `.qml` style file is located in the same directory as the vector and has the same base filename as the vector file. If you move or copy the vector, copy the `.qml` next to it.
- Embedded style: The script attempts to embed the style into the GeoJSON under the `openalaqs_style` property, but QGIS applies external `.qml` files when loading styles automatically; if the style is not applied on import, use `Layer ► Properties ► Symbology ► Style ► Load QML` to assign the `.qml` manually.

**Troubleshooting**
- If QGIS imports fail, confirm you're running from OSGeo4W Shell so the required native libraries are on PATH.
- If the script reports `db_path does not exist`, verify the path and that environment variables are expanded correctly.
- If you need more verbose logs, set `show_logs=True` in the config or pass a config with `show_logs=True`.

**Source**
- Script location: `open_alaqs/scripts/individual_script/run_emissions_austal.py`
