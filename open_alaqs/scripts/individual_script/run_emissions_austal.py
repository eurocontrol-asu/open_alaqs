"""
Emission Calculator Service CLI
Runs emission calculations from a config file and exports results in various formats.
"""

import argparse
import json
import logging
import os
import shutil
import sys
import tarfile
import tempfile
import warnings
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from qgis.core import QgsCoordinateTransformContext, QgsVectorFileWriter

from open_alaqs.core.EmissionCalculatorService import (
    EmissionCalculationConfig,
    EmissionCalculatorService,
)
from open_alaqs.core.modules.AUSTALOutputModule import AUSTALDispersionModule
from open_alaqs.core.modules.EmissionsQGISVectorLayerOutputModule import (
    EmissionsQGISVectorLayerOutputModule,
)
from open_alaqs.core.modules.TableViewWidgetOutputModule import (
    TableViewWidgetOutputModule,
    ViewType,
)
from open_alaqs.core.tools.Grid3D import Grid3D

# ============================================================================
# Logging Control
# ============================================================================

# Global flag to control verbose printing
_SHOW_LOGS = False


def set_show_logs(value):
    """Set the global show_logs flag."""
    global _SHOW_LOGS
    _SHOW_LOGS = value


class SuppressedStream:
    """A stream that discards all writes."""

    def write(self, data):
        pass

    def writelines(self, lines):
        pass

    def flush(self):
        pass

    @property
    def encoding(self):
        return "utf-8"

    def isatty(self):
        return False


# Preserve original OS streams so this module can always write directly
# to the user's terminal even when `sys.stdout`/`sys.stderr` are replaced
# by the suppression context manager.
_ORIG_STDOUT = sys.stdout
_ORIG_STDERR = sys.stderr


def announce(*args, sep=" ", end="\n", flush=True):
    """
    Print directly to the original stdout (bypasses suppression).
    Use this for user-visible messages that should always appear from
    this script even when `show_logs` is False.
    """
    try:
        text = sep.join(str(a) for a in args) + end
        _ORIG_STDOUT.write(text)
        if flush:
            _ORIG_STDOUT.flush()
    except Exception:
        # Best-effort fallback (may be suppressed if sys.stdout is replaced)
        try:
            print(*args, sep=sep, end=end, flush=flush)
        except Exception:
            pass


def announce_err(*args, sep=" ", end="\n", flush=True):
    """
    Print directly to the original stderr (bypasses suppression).
    """
    try:
        text = sep.join(str(a) for a in args) + end
        _ORIG_STDERR.write(text)
        if flush:
            _ORIG_STDERR.flush()
    except Exception:
        try:
            print(*args, sep=sep, end=end, flush=flush, file=sys.stderr)
        except Exception:
            pass


def _format_timedelta(td):
    """Format a timedelta into H:MM:SS.sss"""
    if td is None:
        return "n/a"
    total_seconds = td.total_seconds()
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{int(hours)}:{int(minutes):02d}:{seconds:06.3f}"


@contextmanager
def suppress_external_output(enable_suppression):
    """
    Context manager that suppresses all stdout/stderr when enabled.
    This prevents external libraries from printing.

    Args:
        enable_suppression: If True, suppress output; if False, allow all output
    """
    if not enable_suppression:
        yield
        return

    # Save original Python streams
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr

    # Save module-level original streams so announce() can be restored
    prev_module_out = globals().get("_ORIG_STDOUT")
    prev_module_err = globals().get("_ORIG_STDERR")

    # Prepare suppressed Python-level streams
    null_stream = SuppressedStream()

    # Try to redirect native C-level stdout/stderr
    devnull_fd = None
    saved_fd_out = None
    saved_fd_err = None
    safe_out = None
    safe_err = None
    gdal_quiet = False
    qt_prev_handler = None

    try:
        # Create safe duplicates of the current stdout/stderr fds so it
        # can write to them (announce) even after it dup2 devnull onto
        # fd 1/2. Keep the duplicated fds open until restore.
        try:
            saved_fd_out = os.dup(1)
            saved_fd_err = os.dup(2)
            safe_out = os.fdopen(
                os.dup(saved_fd_out),
                "w",
                buffering=1,
                encoding="utf-8",
                errors="replace",
            )
            safe_err = os.fdopen(
                os.dup(saved_fd_err),
                "w",
                buffering=1,
                encoding="utf-8",
                errors="replace",
            )
            # Replace module-level originals used by announce()/announce_err()
            globals()["_ORIG_STDOUT"] = safe_out
            globals()["_ORIG_STDERR"] = safe_err
        except Exception:
            # If cannot duplicate fds, continue, announce may be suppressed
            safe_out = None
            safe_err = None

        # Quiet GDAL/OGR C-level messages if available
        try:
            from osgeo import gdal

            # Push quiet error handler
            gdal.PushErrorHandler("CPLQuietErrorHandler")
            gdal_quiet = True
        except Exception:
            gdal_quiet = False

        # Try to silence Qt message handler (best-effort)
        try:
            from qgis.PyQt import QtCore

            try:
                qt_prev_handler = QtCore.qInstallMessageHandler(
                    lambda *args, **kwargs: None
                )
            except Exception:
                qt_prev_handler = None
        except Exception:
            qt_prev_handler = None

        # Redirect native stdout/stderr to devnull so C-level prints disappear
        try:
            devnull_fd = os.open(os.devnull, os.O_RDWR)
            os.dup2(devnull_fd, 1)
            os.dup2(devnull_fd, 2)
        except Exception:
            # If redirecting native fds fails, continue — Python-level suppression still helps
            pass

        # Replace Python-level streams
        sys.stdout = null_stream
        sys.stderr = null_stream

        yield

    finally:
        # Restore Python-level streams
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr

        # Restore native stdout/stderr fds if they were changed
        try:
            if saved_fd_out is not None:
                os.dup2(saved_fd_out, 1)
            if saved_fd_err is not None:
                os.dup2(saved_fd_err, 2)
        except Exception:
            pass

        # Close devnull and duplicated fds
        try:
            if devnull_fd is not None:
                os.close(devnull_fd)
        except Exception:
            pass

        try:
            if safe_out is not None:
                safe_out.close()
        except Exception:
            pass
        try:
            if safe_err is not None:
                safe_err.close()
        except Exception:
            pass

        try:
            if saved_fd_out is not None:
                os.close(saved_fd_out)
        except Exception:
            pass
        try:
            if saved_fd_err is not None:
                os.close(saved_fd_err)
        except Exception:
            pass

        # Restore module-level announce streams
        try:
            globals()["_ORIG_STDOUT"] = prev_module_out
            globals()["_ORIG_STDERR"] = prev_module_err
        except Exception:
            pass

        # Restore GDAL/OGR error handler
        if gdal_quiet:
            try:
                from osgeo import gdal

                gdal.PopErrorHandler()
            except Exception:
                pass

        # Restore Qt message handler
        if qt_prev_handler is not None:
            try:
                from qgis.PyQt import QtCore

                QtCore.qInstallMessageHandler(qt_prev_handler)
            except Exception:
                pass


# ============================================================================
# Qt Application Setup
# ============================================================================


def ensure_qt_app():
    """
    Ensure a QApplication exists for modules that construct Qt widgets.

    Returns:
        tuple: (QApplication instance, bool indicating if app was created)
    """
    try:
        from qgis.PyQt.QtWidgets import QApplication
    except Exception:
        from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
        created = True
    else:
        created = False

    return app, created


# ============================================================================
# Configuration Parsing
# ============================================================================


def parse_config(txt_path):
    """
    Parse configuration from a text file with key=value format.

    Args:
        txt_path: Path to configuration file

    Returns:
        dict: Parsed configuration with appropriate types
    """
    config = {}

    # Read key-value pairs
    with open(txt_path, "r") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.strip().split("=", 1)
                config[key.strip()] = value.strip()

    # Parse datetime fields
    config["start_dt_inclusive"] = datetime.fromisoformat(config["start_dt_inclusive"])
    config["end_dt_inclusive"] = datetime.fromisoformat(config["end_dt_inclusive"])

    # Parse time interval
    config["time_interval"] = timedelta(seconds=int(config["time_interval_seconds"]))

    # Parse boolean fields
    config["should_apply_nox_corrections"] = (
        config.get("should_apply_nox_corrections", "False") == "True"
    )

    # Parse show_logs flag (default False)
    config["show_logs"] = str(config.get("show_logs", "False")).strip().lower() in (
        "true",
        "1",
        "yes",
    )

    # Parse numeric fields
    config["vertical_limit_m"] = float(config.get("vertical_limit_m", 914.4))

    # Parse source dynamics (string) and source names (comma-separated)
    raw_dynamics = str(config.get("source_dynamics", "none") or "none").strip()
    sd = raw_dynamics.lower()
    # Accept common synonyms and normalise to canonical values used by modules
    if sd in ("none", "no", "off", "0"):
        config["source_dynamics"] = "none"
    elif sd in ("default", "def"):
        config["source_dynamics"] = "default"
    elif sd in ("smooth", "shift"):
        config["source_dynamics"] = sd
    elif sd in ("smooth & shift", "smooth&shift", "smooth_shift", "smooth and shift"):
        config["source_dynamics"] = "smooth_shift"
    else:
        # Unknown value — keep as provided but lowercased; modules may validate further
        config["source_dynamics"] = sd

    raw_names = config.get("source_names", "")
    if isinstance(raw_names, str):
        # allow comma-separated list in the txt file
        config["source_names"] = [s.strip() for s in raw_names.split(",") if s.strip()]
    else:
        config["source_names"] = raw_names or []

    # Normalise paths (expand environment variables)
    for path_key in ["db_path", "austal_output_path", "emissions_output_path"]:
        if path_key in config:
            config[path_key] = os.path.expandvars(config[path_key])

    # Ensure there's a base name for emission outputs; default to 'emissions'
    config["emissions_output_name"] = config.get("emissions_output_name", "emissions")

    return config


def extract_grid_config(grid):
    """
    Extract grid configuration as a dictionary.

    Args:
        grid: Grid3D instance

    Returns:
        dict: Grid configuration parameters
    """
    return {
        "x_cells": getattr(grid, "_x_cells", None),
        "y_cells": getattr(grid, "_y_cells", None),
        "z_cells": getattr(grid, "_z_cells", None),
        "x_resolution": getattr(grid, "_x_resolution", None),
        "y_resolution": getattr(grid, "_y_resolution", None),
        "z_resolution": getattr(grid, "_z_resolution", None),
        "reference_latitude": getattr(grid, "_reference_latitude", 0.0),
        "reference_longitude": getattr(grid, "_reference_longitude", 0.0),
        "reference_altitude": getattr(grid, "_reference_altitude", 0.0),
    }


def create_emission_config(config_dict, grid_config):
    """
    Create EmissionCalculationConfig from parsed configuration.

    Args:
        config_dict: Parsed configuration dictionary
        grid_config: Grid configuration dictionary

    Returns:
        EmissionCalculationConfig: Configuration object
    """
    return EmissionCalculationConfig(
        db_path=config_dict["db_path"],
        start_dt_inclusive=config_dict["start_dt_inclusive"],
        end_dt_inclusive=config_dict["end_dt_inclusive"],
        time_interval=config_dict["time_interval"],
        pollutant=config_dict["pollutant"],
        method=config_dict.get("method", "bymode"),
        source_type=config_dict.get("source_type", "all"),
        source_names=config_dict.get("source_names", []),
        vertical_limit_m=config_dict.get("vertical_limit_m", 914.4),
        should_apply_nox_corrections=config_dict.get(
            "should_apply_nox_corrections", False
        ),
        source_dynamics=config_dict.get("source_dynamics", "none"),
        grid_config=grid_config,
    )


def resolve_config_path(path):
    """
    Resolve a provided path to a config text file. Accepts directories,
    archives (.zip/.tar/.tar.gz/.tgz) or direct file paths.

    Returns the resolved file path or raises FileNotFoundError.
    """
    path = os.path.expandvars(path)
    if os.path.isdir(path):
        for name in ("example.txt", "config.txt", "settings.txt"):
            candidate = os.path.join(path, name)
            if os.path.exists(candidate):
                return candidate
        for fn in os.listdir(path):
            if fn.lower().endswith(".txt"):
                return os.path.join(path, fn)
        raise FileNotFoundError(f"No .txt config found in directory: {path}")

    if os.path.isfile(path):
        low = path.lower()
        if (
            low.endswith(".zip")
            or low.endswith(".tar")
            or low.endswith(".tar.gz")
            or low.endswith(".tgz")
        ):
            tmp = tempfile.mkdtemp(prefix="openalaqs_cfg_")
            try:
                if zipfile.is_zipfile(path):
                    with zipfile.ZipFile(path, "r") as z:
                        z.extractall(tmp)
                else:
                    with tarfile.open(path, "r:*") as t:
                        t.extractall(tmp)
                return resolve_config_path(tmp)
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
        else:
            return path


def load_config_interactive(initial_path):
    """
    Attempt to parse configuration from `initial_path`. If parsing fails and
    interactive input is available, prompt the user for an alternative path
    and retry until success or the user quits.

    Returns (config_dict, resolved_config_path)
    """
    config_path = initial_path
    while True:
        try:
            config_dict = parse_config(config_path)
            return config_dict, config_path
        except Exception as e:
            announce_err(f"Failed to parse config '{config_path}': {e}")
            if sys.stdin is not None and sys.stdin.isatty():
                announce(
                    "Please provide a path to a valid .txt config (or 'q' to quit): ",
                    end="",
                )
                try:
                    user_input = input().strip()
                except EOFError:
                    announce_err("No input available; exiting.")
                    sys.exit(1)

                if not user_input:
                    continue
                if user_input.lower() in ("q", "quit", "exit"):
                    announce_err("No valid config provided; exiting.")
                    sys.exit(1)
                try:
                    config_path = resolve_config_path(user_input)
                except Exception as e2:
                    announce_err(f"Invalid path: {e2}")
                    continue
                # loop and attempt to parse the new config_path
            else:
                announce_err(
                    "Config file invalid and no interactive input available; exiting."
                )
                sys.exit(1)


def validate_config_interactive(config_dict, config_path):
    """
    Validate required keys in `config_dict`. If validation fails and
    interactive input is available, prompt the user to provide an alternate
    config path and re-run parsing/validation until valid or user quits.

    Returns (validated_config_dict, resolved_config_path)
    """
    while True:
        validation_errors = []

        dbp = config_dict.get("db_path")
        if not dbp:
            validation_errors.append("Missing required key: db_path")
        else:
            if not os.path.exists(dbp):
                validation_errors.append(f"db_path does not exist: {dbp}")

        if (
            "start_dt_inclusive" not in config_dict
            or "end_dt_inclusive" not in config_dict
        ):
            validation_errors.append("Missing start_dt_inclusive or end_dt_inclusive")

        if "time_interval" not in config_dict:
            validation_errors.append("Missing or invalid time_interval_seconds")

        if not config_dict.get("pollutant"):
            validation_errors.append("Missing required key: pollutant")

        if not validation_errors:
            return config_dict, config_path

        announce("")
        announce("Configuration issues detected:")
        for err in validation_errors:
            announce_err(f"  - {err}")

        if sys.stdin is not None and sys.stdin.isatty():
            announce("")
            announce(
                "Enter a path to a valid .txt config, or type 'q' to quit: ", end=""
            )
            try:
                user_input = input().strip()
            except EOFError:
                announce_err("No input available; exiting.")
                sys.exit(1)

            if not user_input:
                continue
            if user_input.lower() in ("q", "quit", "exit"):
                announce_err("Exiting due to invalid configuration.")
                sys.exit(1)
            try:
                config_path = resolve_config_path(user_input)
                try:
                    config_dict = parse_config(config_path)
                except Exception as e3:
                    announce_err(f"Failed to parse new config: {e3}")
                    continue
            except Exception as e4:
                announce_err(f"Invalid path: {e4}")
                continue
        else:
            announce_err(
                "Configuration invalid and no interactive input available; exiting."
            )
            sys.exit(1)


# ============================================================================
# Export Functions
# ============================================================================


def parse_view_type(view_type_str):
    """
    Parse view type string to ViewType enum.

    Args:
        view_type_str: String representation of view type

    Returns:
        ViewType: Corresponding enum value
    """
    normalized = (
        view_type_str.strip().lower()
        if isinstance(view_type_str, str)
        else "by aggregation"
    )

    if normalized in ("by aggregation", "aggregation", "aggregate"):
        return ViewType.BY_AGGREGATION
    elif normalized in ("by source", "source"):
        return ViewType.BY_SOURCE
    else:
        return ViewType.BY_AGGREGATION


def filter_empty_emissions(rows, pollutant_cols):
    """
    Filter out rows where all pollutant columns are empty or zero.

    Args:
        rows: List of emission data rows
        pollutant_cols: List of pollutant column names

    Returns:
        list: Filtered rows with at least one non-zero pollutant value
    """

    def is_empty_value(v):
        return v is None or v == "" or (isinstance(v, (int, float)) and float(v) == 0.0)

    return [
        row
        for row in rows
        if not all(is_empty_value(row.get(col)) for col in pollutant_cols)
    ]


def export_csv(result, config, config_dict, grid, emissions_output_path):
    """
    Export emissions data to CSV format.

    Args:
        result: Emission calculation result
        config: EmissionCalculationConfig object
        config_dict: Raw configuration dictionary
        grid: Grid3D instance
        emissions_output_path: Output directory path
    """
    emissions_base = config_dict.get("emissions_output_name", "emissions")
    csv_path = os.path.join(emissions_output_path, f"{emissions_base}.csv")

    # Parse view type
    view_type_enum = parse_view_type(config_dict.get("view_type", "by aggregation"))

    # Create table module
    values = {
        "start_dt_inclusive": config.start_dt_inclusive,
        "end_dt_inclusive": config.end_dt_inclusive,
        "view_type": view_type_enum,
        "grid": grid,
        "parent": None,
    }

    try:
        table_module = TableViewWidgetOutputModule(values)

        # Process emissions data
        table_module.beginJob()
        for timestamp, rows in result.emissions_data.items():
            table_module.process(timestamp, rows)
        table_module.endJob()

        # Filter empty rows
        all_fields = (
            list(table_module.fields.keys()) if hasattr(table_module, "fields") else []
        )
        meta_cols = {"timestamp", "wkt", "source_type", "source_name"}
        pollutant_cols = [c for c in all_fields if c not in meta_cols]

        filtered_rows = filter_empty_emissions(
            getattr(table_module, "rows", []), pollutant_cols
        )
        table_module.rows = filtered_rows

        # Export to CSV
        table_module.export_to_csv(csv_path)
        announce(f"CSV exported to {csv_path}")

    except Exception as e:
        announce_err(f"Failed to export CSV: {e}")


def save_layer_style(layer, style_path):
    """
    Extract and save layer style to QML file.

    Args:
        layer: QGIS vector layer
        style_path: Path to save QML style file

    Returns:
        str: Style XML string, or None if unavailable
    """
    style_xml = None

    # Try to save named style to QML
    try:
        if hasattr(layer, "saveNamedStyle"):
            layer.saveNamedStyle(style_path)
            if os.path.exists(style_path):
                with open(style_path, "r", encoding="utf-8") as sf:
                    style_xml = sf.read()
    except Exception:
        pass

    # Fallback: extract renderer XML
    if not style_xml:
        try:
            renderer = layer.renderer()
            style_xml = renderer.dumpToXml()

            # Write fallback style to QML file
            try:
                with open(style_path, "w", encoding="utf-8") as sf:
                    sf.write(style_xml)
            except Exception:
                pass
        except Exception:
            pass

    return style_xml


def embed_style_in_geojson(geojson_path, style_xml):
    """
    Embed style XML into GeoJSON file.

    Args:
        geojson_path: Path to GeoJSON file
        style_xml: Style XML string to embed
    """
    try:
        with open(geojson_path, "r", encoding="utf-8") as gf:
            gj = json.load(gf)

        gj["openalaqs_style"] = style_xml

        with open(geojson_path, "w", encoding="utf-8") as gf:
            json.dump(gj, gf, ensure_ascii=False)

        announce(f"Embedded style into {geojson_path}")

    except Exception as e:
        announce_err(f"Failed to embed style into GeoJSON: {e}")


def export_geojson(result, config, config_dict, grid, emissions_output_path):
    """
    Export emissions data to GeoJSON format with QGIS styling.

    Args:
        result: Emission calculation result
        config: EmissionCalculationConfig object
        config_dict: Raw configuration dictionary
        grid: Grid3D instance
        emissions_output_path: Output directory path
    """
    emissions_base = config_dict.get("emissions_output_name", "emissions")
    geojson_path = os.path.join(emissions_output_path, f"{emissions_base}.geojson")

    # Create QGIS vector layer module
    qgis_values = {
        "start_dt_inclusive": config.start_dt_inclusive,
        "end_dt_inclusive": config.end_dt_inclusive,
        "pollutant": config.pollutant,
        "use_centroid_symbol": False,
        "should_add_labels": False,
        "grid": grid,
    }

    qgis_module = EmissionsQGISVectorLayerOutputModule(qgis_values)

    # Process emissions data
    qgis_module.beginJob()
    for timestamp, emissions_rows in result.emissions_data.items():
        qgis_module.process(timestamp, emissions_rows)
    layer = qgis_module.endJob()

    if not layer:
        announce("No QGIS vector layer generated.")
        return

    # Write GeoJSON file
    try:
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GeoJSON"
        opts.fileEncoding = "UTF-8"

        res, err_msg = QgsVectorFileWriter.writeAsVectorFormatV2(
            layer, geojson_path, QgsCoordinateTransformContext(), opts
        )

        if res != 0:
            announce_err(f"Failed to export QGIS vector: {res}, {err_msg}")
            return

        announce(f"QGIS vector exported to {geojson_path}")

        # Extract and save layer style
        style_path = os.path.join(emissions_output_path, f"{emissions_base}.qml")
        style_xml = save_layer_style(layer, style_path)

        # Embed style in GeoJSON
        if style_xml:
            embed_style_in_geojson(geojson_path, style_xml)
        else:
            announce("No style available to embed or save.")

    except Exception as e:
        announce_err(f"Failed to save GeoJSON using QGIS API: {e}")


def export_austal(austal_output_path):
    """
    Export AUSTAL dispersion model input files.

    Args:
        austal_output_path: Output directory path
    """
    # Ensure output path exists
    abs_austal_path = os.path.abspath(austal_output_path)
    os.makedirs(abs_austal_path, exist_ok=True)

    # Try to write files if they dont already exist
    try:
        austal_module = AUSTALDispersionModule({"output_path": abs_austal_path})
        try:
            austal_module.writeInputFile()
        except FileExistsError:
            # It's fine if file already existed the contents will be reported
            pass
        except Exception as e:
            announce_err(f"Failed to write Austal input files: {e}")
    except Exception as e:
        announce_err(f"Failed to initialize AUSTAL module: {e}")

    # Always report the AUSTAL output directory and its contents so the user
    # can verify what was created
    try:
        files = sorted(os.listdir(abs_austal_path))
        announce(f"AUSTAL output path: {abs_austal_path}")
        if not files:
            announce("AUSTAL output directory is empty")
            return

    except Exception as e:
        announce_err(f"Could not list AUSTAL output directory: {e}")


# ============================================================================
# Main Execution
# ============================================================================


def setup_output_directories(config_dict, config_path=None):
    """
    Determine and create output directories.

    Behavior:
    - If explicit `austal_output_path` / `emissions_output_path` are present in
      `config_dict`, those paths are used (environment variables expanded).
    - Otherwise, if `config_path` is provided, defaults are created under the
      same directory as the config file: `<config_dir>/outputs/austal/` and
      `<config_dir>/outputs/emissions/`.
    - If `config_path` is not provided, falls back to relative defaults
      `outputs/austal/` and `outputs/emissions/` (created relative to the
      current working directory).

    Args:
        config_dict: Configuration dictionary
        config_path: Path to the config `.txt` file (optional)

    Returns:
        tuple: (austal_output_path, emissions_output_path)
    """

    # Helper to expand and normalise a candidate path
    def _norm_path(p):
        if p is None:
            return None
        p = os.path.expandvars(p)
        return os.path.abspath(p)

    # Prefer explicit config values when provided
    raw_austal = config_dict.get("austal_output_path")
    raw_emissions = config_dict.get("emissions_output_path")

    if raw_austal:
        austal_output_path = _norm_path(raw_austal)
    else:
        if config_path:
            cfg_dir = os.path.dirname(os.path.abspath(config_path))
            austal_output_path = os.path.join(cfg_dir, "outputs", "austal")
        else:
            austal_output_path = os.path.abspath("outputs/austal/")

    if raw_emissions:
        emissions_output_path = _norm_path(raw_emissions)
    else:
        if config_path:
            cfg_dir = os.path.dirname(os.path.abspath(config_path))
            emissions_output_path = os.path.join(cfg_dir, "outputs", "emissions")
        else:
            emissions_output_path = os.path.abspath("outputs/emissions/")

    # Create directories if missing
    try:
        os.makedirs(austal_output_path, exist_ok=True)
    except Exception:
        pass
    try:
        os.makedirs(emissions_output_path, exist_ok=True)
    except Exception:
        pass

    return austal_output_path, emissions_output_path


def run_calculation(
    config_dict, config_path, austal_output_path, args, suppress_output
):
    """Run the emission calculation within a suppression context.

    Returns: (result, config, grid, calc_start, calc_end)
    """
    with suppress_external_output(suppress_output):
        announce("=" * 60)
        announce("Loading Grid".center(60))
        announce("=" * 60)
        announce("")
        announce(f"From: {config_dict['db_path']}")
        grid = Grid3D(db_path=config_dict["db_path"], deserialize=True)
        grid_config = extract_grid_config(grid)
        announce("Grid loaded successfully")
        announce("")

        config = create_emission_config(config_dict, grid_config)

        if args.austal:
            austal_cfg = {"is_enabled": True, "output_path": austal_output_path}
            if config_dict.get("austal_settings"):
                austal_cfg.update(config_dict.get("austal_settings"))
            config.dispersion_modules_config = {"AUSTAL": austal_cfg}

        announce("=" * 60)
        announce("Calculating Emissions".center(60))
        announce("=" * 60)
        announce("")
        announce(f"Period: {config.start_dt_inclusive} to {config.end_dt_inclusive}")
        announce(f"Pollutant: {config.pollutant}")

        service = EmissionCalculatorService()
        calc_start = datetime.now()
        result = service.calculate_emissions(config)
        calc_end = datetime.now()

        if not result.success:
            announce_err(f"\nError: {result.error_message}")
            sys.exit(1)

    return result, config, grid, calc_start, calc_end


def run_exports(
    result,
    config,
    config_dict,
    grid,
    emissions_output_path,
    austal_output_path,
    args,
    suppress_output,
):
    """Run export steps (CSV, GeoJSON, AUSTAL) within suppression context.

    Returns: (export_start, export_end)
    """
    export_start = datetime.now()
    with suppress_external_output(suppress_output):
        if args.csv:
            announce("")
            announce("Exporting CSV...")
            export_csv(result, config, config_dict, grid, emissions_output_path)

        if args.geojson:
            announce("")
            announce("Exporting GeoJSON...")
            export_geojson(result, config, config_dict, grid, emissions_output_path)

        if args.austal:
            announce("")
            announce("Exporting AUSTAL files...")
            export_austal(austal_output_path)

    export_end = datetime.now()
    return export_start, export_end


def main():
    """Main execution function."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run Emission Service from config txt")
    parser.add_argument("config_txt", help="Path to config txt file")
    parser.add_argument("--csv", action="store_true", help="Export emissions as CSV")
    parser.add_argument(
        "--geojson",
        action="store_true",
        help="Export emissions as GeoJSON (QGIS vector)",
    )
    parser.add_argument(
        "--austal", action="store_true", help="Export Austal input files"
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Show elapsed time summary for calculation and exports",
    )
    args = parser.parse_args()
    
    # Resolve initial config path (directory, archive or file)
    try:
        config_path = resolve_config_path(args.config_txt)
    except FileNotFoundError as e:
        if sys.stdin is not None and sys.stdin.isatty():
            announce_err(str(e))
            while True:
                announce(
                    "Enter a path to a valid .txt config, or type 'q' to quit: ", end=""
                )
                try:
                    user_input = input().strip()
                except EOFError:
                    announce_err("No input available; exiting.")
                    sys.exit(1)

                if not user_input:
                    continue
                if user_input.lower() in ("q", "quit", "exit"):
                    announce_err("No config provided; exiting.")
                    sys.exit(1)
                try:
                    config_path = resolve_config_path(user_input)
                    break
                except Exception as e2:
                    announce_err(f"Invalid path: {e2}")
                    continue
        else:
            announce_err(str(e))
            sys.exit(1)

    # Parse configuration (with interactive retry) and validate it
    config_dict, config_path = load_config_interactive(config_path)
    config_dict, config_path = validate_config_interactive(config_dict, config_path)
    
    # Set global show_logs flag
    show_logs = config_dict.get("show_logs", False)
    set_show_logs(show_logs)

    # Configure logging based on show_logs
    if not show_logs:
        # Disable all logging from libraries
        logging.disable(logging.CRITICAL)
        # Suppress warnings from pandas, GDAL, etc.
        warnings.filterwarnings("ignore")
    else:
        logging.disable(logging.NOTSET)
        logging.basicConfig(level=logging.INFO)

    announce("=" * 60)
    announce("Emission Calculator Service".center(60))
    announce("=" * 60)
    announce("")

    # Timing variables (optional)
    start_time = None
    calc_start = None
    calc_end = None
    export_start = None
    export_end = None

    # Start measuring total runtime at the point we begin heavy work
    start_time = datetime.now()

    # Setup output directories (if config file path is provided, defaults
    # for missing output paths are created next to the config file)
    austal_output_path, emissions_output_path = setup_output_directories(
        config_dict, config_path
    )
    announce("Output directories configured:")
    announce(f"  - Emissions: {emissions_output_path}")
    announce(f"  - AUSTAL: {austal_output_path}")
    announce("")

    # Suppress external library output when show_logs is False
    suppress_output = not show_logs

    result, config, grid, calc_start, calc_end = run_calculation(
        config_dict, config_path, austal_output_path, args, suppress_output
    )

    # Initialize Qt app if needed for exports
    app = None
    created_qt_app = False
    needs_qt = args.csv or args.geojson

    if needs_qt:
        with suppress_external_output(suppress_output):
            app, created_qt_app = ensure_qt_app()

    try:
        # Export results
        if args.csv or args.geojson or args.austal:
            announce("=" * 60)
            announce("Exporting Results".center(60))
            announce("=" * 60)

        export_start, export_end = run_exports(
            result,
            config,
            config_dict,
            grid,
            emissions_output_path,
            austal_output_path,
            args,
            suppress_output,
        )

        announce("")
        announce("=" * 60)
        announce("All operations completed successfully".center(60))
        announce("=" * 60)
        # Timing summary
        if args.timing:
            total_end = datetime.now()
            total = total_end - start_time if start_time else None
            announce("")
            announce("-" * 60)
            announce("Timing summary".center(60))
            announce("-" * 60)
            announce("")
            announce(f"Total elapsed: {_format_timedelta(total)}")
            if calc_start and calc_end:
                announce(f"Calculation:   {_format_timedelta(calc_end - calc_start)}")
            if export_start and export_end:
                announce(
                    f"Exports:       {_format_timedelta(export_end - export_start)}"
                )

    finally:
        # Clean up Qt application if it was created before for some modules
        if created_qt_app and app is not None:
            try:
                app.quit()
                app.deleteLater()
            except Exception:
                pass


if __name__ == "__main__":
    main()
