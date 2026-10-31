# Running Open-ALAQS without the QGIS window

Which tool to use when you want to work on a study from a terminal instead
of the QGIS window. It is for users who run batch jobs, build input files or
upgrade studies outside QGIS.

Some of these tools still need the Python that comes with QGIS (on Windows,
the OSGeo4W Shell), because they run the plugin's own code. The others run
with any Python 3 from a checkout of the repository.

| Tool | What it does | Needs QGIS Python? | Input | Output | When to use |
| --- | --- | --- | --- | --- | --- |
| [`openalaqs_standalone aircraft`](../../openalaqs_standalone/USAGE.md#per-movement-emissions-aircraft) | Computes the emissions of each aircraft movement (fixed-wing, helicopters; gate, APU and engine start included) with the three calculation methods | No (numpy, pandas, pyarrow, shapely, pyproj) | Inventory `.alaqs` (`*_out.alaqs`) | One CSV of per-movement totals; optionally the aircraft AUSTAL sources and emissions (parquet) | Movement-by-movement tables, large studies, parallel runs, checks against the plugin |
| [`openalaqs_standalone austal`](../../openalaqs_standalone/USAGE.md#austal-ready-folders-austal) | Builds AUSTAL-ready inputs for the whole study: stationary sources from the emission factors stored in the study, aircraft optionally | No (as above) | Inventory `.alaqs` whose road and parking emission factors were written by the plugin | Six folders: sources, emissions (parquet and one GeoPackage per pollutant), receptors, meteo, config, empty AUSTAL folder | Dispersion inputs for a full year or a time window, in a pipeline without QGIS |
| [`scripts/emissions_austal`](../../scripts/emissions_austal/README.md) (beta) | Runs the plugin's emission calculation without opening the QGIS window, and optionally writes the AUSTAL input files | Yes (imports the QGIS libraries) | Inventory `.alaqs` and a key=value config file | Emissions CSV, GeoJSON with QML style, AUSTAL input files | The plugin's own results for all source types, in batch from the OSGeo4W Shell |
| [`scripts/austal_from_csv`](../../scripts/austal_from_csv/README.md) (beta) | Writes AUSTAL input files from emissions already computed, and can start AUSTAL | Yes (imports the QGIS libraries) | Emissions CSV (plugin table, *by source* view), meteo CSV, grid definition | `austal.txt`, `series.dmna`, one emission grid file per source group and time step | New AUSTAL inputs with another grid or quality level, without recomputing emissions |
| [`scripts/metar_to_alaqs_meteo.py`](../../scripts/README_metar_to_alaqs_meteo.md) | Converts METAR weather reports into the plugin's hourly meteorology file, with optional stability classification | No (standard library only) | METAR text, IEM ASOS CSV or Ogimet text | `meteo.csv` (and optional HTML plots) | Building the meteorology file of a study from airport weather reports |
| [`scripts/migrate_alaqs.py`](../../scripts/README.md#migrate_alaqspy) | Upgrades a study file to the current schema; optionally refreshes reference tables | No (standard library only) | `.alaqs` from an earlier version | The same file, upgraded in place, with a backup copy | Opening a study made with an earlier version (see [UPGRADING.md](UPGRADING.md)) |
| [`scripts/migrate_alaqs_gui.py`](../../scripts/README.md#migrate_alaqs_guipy) | A window with the options of `migrate_alaqs.py` | No, but needs PyQt5 (the QGIS Python has it) | As `migrate_alaqs.py` | As `migrate_alaqs.py` | As `migrate_alaqs.py`, when you prefer a window to the command line |
| [`scripts/import_engine_test_events.py`](../../scripts/README.md#import_engine_test_eventspy) | Loads engine run-up events into a study, with a dry run that checks every row first | No (standard library only) | Project `.alaqs` with test-site area sources, and an events CSV ([format](INPUT_FORMATS.md#engine-test-events)) | Rows in the study's engine test events table | Many events at once, or events kept in a spreadsheet log |
| [`gse_application`](../../gse_application/README.md) | Assigns ground support equipment to movement categories and computes their emissions | Yes (imports the QGIS libraries) | GSE list (CSV or `.alaqs`) and movements (CSV or `.alaqs`) | Gate emission profiles as CSV, or written into the gate profiles table of the `.alaqs` | Preparing study-specific gate (GSE) emission profiles |

"Needs QGIS Python" was checked against the imports of each tool. None of
these tools is installed with the plugin: get them from a checkout of the
repository. `openalaqs_standalone`, `migrate_alaqs.py` and
`import_engine_test_events.py` also read files of the plugin folder of that
checkout (calculation code, study templates), so run them from the
repository root as their pages show.

See also:

- [openalaqs_standalone USAGE.md](../../openalaqs_standalone/USAGE.md): install, commands and options of the standalone
- [scripts/README.md](../../scripts/README.md): all command-line scripts
- [INPUT_FORMATS.md](INPUT_FORMATS.md): the input file formats
- [DISPERSION_AUSTAL.md](DISPERSION_AUSTAL.md): running AUSTAL from the plugin
