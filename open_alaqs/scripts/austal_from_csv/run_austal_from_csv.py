"""
AUSTAL Input File Generator CLI — CSV mode
Generates AUSTAL dispersion-model input files from pre-calculated emissions
and meteorology CSV files and a key=value configuration file.

Usage (from OSGeo4W Shell):
    python-qgis run_austal_from_csv.py <config_txt> [--timing] [--dry-run] [--run-austal]

The config file uses key=value pairs (# comments are ignored).
Required keys:
    emissions_csv_path  — path to emissions CSV (TableViewWidgetOutputModule format)
    meteo_csv_path      — path to meteo CSV (AmbientConditionStore format)
    output_path         — directory where AUSTAL files will be written
    pollutants          — comma-separated list, e.g. NOx,CO,PM10
    x_cells, y_cells, z_cells
    x_resolution, y_resolution, z_resolution  (metres)
    reference_latitude, reference_longitude   (decimal degrees, WGS84 centre of grid)

Optional keys (defaults shown):
    reference_altitude      = 0.0
    quality_level           = 1
    mixing_height_enabled   = False
    options_string          = NOSTANDARD;SCINOTAT;Kmax=1
    roughness_length_m      = 0.2
    displacement_height_m   = 1.2
    anemometer_height_m     = 11.2
    austal_exe_path         = (path to austal.exe — runs AUSTAL after generation)
    show_logs               = False
"""

import argparse
import csv as _csv_mod
import logging
import os
import sqlite3
import subprocess
import sys
import warnings

# Track whether QGIS libs were successfully imported
b_qgis_libs_imported = False

try:
    from qgis.utils import spatialite_connect  # noqa: F401 – connectivity check only

    b_qgis_libs_imported = True
except ModuleNotFoundError as e:
    print(
        "error: QGIS libraries could not be imported.\n\n"
        "Run the script from the OSGeo4W Shell using the 'python-qgis' command:\n"
        "  python-qgis path/to/run_austal_from_csv.py <config_file> [options]\n\n"
        f"Details: {e}\n"
    )


# ---------------------------------------------------------------------------
# Plugin path discovery (mirrors run_emissions_austal.py)
# ---------------------------------------------------------------------------


def get_plugins_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Method 1: development workspace (script lives inside the plugin tree)
    system_plugins = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
    if os.path.exists(os.path.join(system_plugins, "open_alaqs")):
        return system_plugins

    # Method 2: workspace root
    workspace_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    if os.path.exists(os.path.join(workspace_root, "open_alaqs")):
        return workspace_root

    # Method 3: QGIS user plugins directory
    user_plugins = os.path.join(
        os.path.expanduser("~"),
        "AppData",
        "Roaming",
        "QGIS",
        "QGIS3",
        "profiles",
        "default",
        "python",
        "plugins",
    )
    if os.path.exists(os.path.join(user_plugins, "open_alaqs")):
        return user_plugins

    raise RuntimeError(
        f"Could not locate open_alaqs plugin. "
        f"Checked: {system_plugins}, {workspace_root}, {user_plugins}"
    )


plugins_dir = get_plugins_dir()
if plugins_dir not in sys.path:
    sys.path.insert(0, plugins_dir)


# ---------------------------------------------------------------------------
# Deferred open_alaqs import
# ---------------------------------------------------------------------------


def import_openalaqs_modules():
    """Import open_alaqs modules after sys.path has been configured."""
    global generate_austal_from_csv

    try:
        from open_alaqs.core.tools.austal_csv_generation import (
            generate_austal_from_csv,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to import open_alaqs modules: {exc}") from exc


# ---------------------------------------------------------------------------
# Output streams (bypass suppression)
# ---------------------------------------------------------------------------

_ORIG_STDOUT = sys.stdout
_ORIG_STDERR = sys.stderr


def announce(*args, sep=" ", end="\n", flush=True):
    """Print directly to the original stdout, bypassing any suppression."""
    try:
        _ORIG_STDOUT.write(sep.join(str(a) for a in args) + end)
        if flush:
            _ORIG_STDOUT.flush()
    except Exception:
        try:
            print(*args, sep=sep, end=end, flush=flush)
        except Exception:
            pass


def announce_err(*args, sep=" ", end="\n", flush=True):
    """Print directly to the original stderr, bypassing any suppression."""
    try:
        _ORIG_STDERR.write(sep.join(str(a) for a in args) + end)
        if flush:
            _ORIG_STDERR.flush()
    except Exception:
        try:
            print(*args, sep=sep, end=end, flush=flush, file=sys.stderr)
        except Exception:
            pass


def _format_timedelta(td):
    """Format a timedelta as H:MM:SS.sss."""
    if td is None:
        return "n/a"
    total = td.total_seconds()
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{int(hours)}:{int(minutes):02d}:{seconds:06.3f}"


# ---------------------------------------------------------------------------
# Configuration parsing
# ---------------------------------------------------------------------------


def parse_config(txt_path):
    """Parse a key=value configuration file.

    Args:
        txt_path: Path to the .txt configuration file.

    Returns:
        dict: Parsed configuration with appropriate Python types.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If a required key is missing or has an invalid value.
    """
    if not os.path.isfile(txt_path):
        raise FileNotFoundError(f"Config file not found: {txt_path}")

    raw = {}
    with open(txt_path, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            raw[key.strip()] = value.strip()

    config = {}

    # Paths
    for key in ("emissions_csv_path", "meteo_csv_path", "output_path"):
        val = raw.get(key, "")
        config[key] = os.path.expandvars(val) if val else ""

    # Pollutants (comma-separated)
    raw_pollutants = raw.get("pollutants", "")
    config["pollutants"] = [p.strip() for p in raw_pollutants.split(",") if p.strip()]

    # Grid config: either from a file or from manual key=value entries
    grid_file = raw.get("grid_file_path", "")
    if grid_file:
        grid_file = os.path.expandvars(grid_file)
    config["grid_file_path"] = grid_file

    if grid_file and os.path.isfile(grid_file):
        config["grid_config"] = _load_grid_from_file(grid_file)
    else:
        config["grid_config"] = {
            "x_cells": int(raw.get("x_cells", 0)),
            "y_cells": int(raw.get("y_cells", 0)),
            "z_cells": int(raw.get("z_cells", 0)),
            "x_resolution": float(raw.get("x_resolution", 0)),
            "y_resolution": float(raw.get("y_resolution", 0)),
            "z_resolution": float(raw.get("z_resolution", 0)),
            "reference_latitude": float(raw.get("reference_latitude", 0.0)),
            "reference_longitude": float(raw.get("reference_longitude", 0.0)),
            "reference_altitude": float(raw.get("reference_altitude", 0.0)),
        }

    # AUSTAL dispersion module settings
    config["austal_config"] = {
        "is_enabled": True,
        "quality_level": int(raw.get("quality_level", 1)),
        "mixing_height_enabled": raw.get("mixing_height_enabled", "False").strip().lower()
        in ("true", "1", "yes"),
        "options_string": raw.get("options_string", "NOSTANDARD;SCINOTAT;Kmax=1"),
        "roughness_length_m": float(raw.get("roughness_length_m", 0.2)),
        "displacement_height_m": float(raw.get("displacement_height_m", 1.2)),
        "anemometer_height_m": float(raw.get("anemometer_height_m", 11.2)),
    }

    # AUSTAL executable path (optional — run AUSTAL after generating input files)
    austal_exe = raw.get("austal_exe_path", "")
    if austal_exe:
        austal_exe = os.path.expandvars(austal_exe)
    config["austal_exe_path"] = austal_exe

    # Logging control
    config["show_logs"] = raw.get("show_logs", "False").strip().lower() in (
        "true",
        "1",
        "yes",
    )

    return config


def _load_grid_from_file(grid_file):
    """Load grid configuration from a CSV or .alaqs file.

    Args:
        grid_file: Path to grid file (.csv or .alaqs).

    Returns:
        dict: Grid configuration with x_cells, y_cells, etc.

    Raises:
        ValueError: If the file format is unsupported or cannot be parsed.
    """
    if grid_file.endswith(".alaqs"):
        try:
            conn = sqlite3.connect(grid_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT x_cells, y_cells, z_cells, "
                "x_resolution, y_resolution, z_resolution, "
                "reference_latitude, reference_longitude "
                'FROM "grid_3d_definition" LIMIT 1'
            )
            row = cursor.fetchone()
            alt_row = None
            try:
                cursor.execute('SELECT airport_elevation FROM "user_study_setup" LIMIT 1')
                alt_row = cursor.fetchone()
            except Exception:
                pass
            conn.close()

            if row is None:
                raise ValueError(f"No grid_3d_definition found in {grid_file}")

            return {
                "x_cells": int(row["x_cells"]),
                "y_cells": int(row["y_cells"]),
                "z_cells": int(row["z_cells"]),
                "x_resolution": float(row["x_resolution"]),
                "y_resolution": float(row["y_resolution"]),
                "z_resolution": float(row["z_resolution"]),
                "reference_latitude": float(row["reference_latitude"]),
                "reference_longitude": float(row["reference_longitude"]),
                "reference_altitude": float(alt_row["airport_elevation"]) if alt_row else 0.0,
            }
        except (sqlite3.Error, ValueError) as exc:
            raise ValueError(f"Could not load grid from ALAQS file: {exc}") from exc

    elif grid_file.endswith(".csv"):
        try:
            with open(grid_file, "r", encoding="utf-8") as fh:
                reader = _csv_mod.DictReader(fh)
                for row in reader:
                    return {
                        "x_cells": int(row.get("x_cells", 50)),
                        "y_cells": int(row.get("y_cells", 50)),
                        "z_cells": int(row.get("z_cells", 1)),
                        "x_resolution": float(row.get("x_resolution", 100)),
                        "y_resolution": float(row.get("y_resolution", 100)),
                        "z_resolution": float(row.get("z_resolution", 50)),
                        "reference_latitude": float(row.get("reference_latitude", 0.0)),
                        "reference_longitude": float(row.get("reference_longitude", 0.0)),
                        "reference_altitude": float(row.get("reference_altitude", 0.0)),
                    }
            raise ValueError(f"Grid CSV file is empty: {grid_file}")
        except (OSError, ValueError) as exc:
            raise ValueError(f"Could not load grid from CSV file: {exc}") from exc

    else:
        raise ValueError(
            f"Unsupported grid file format: {grid_file}. "
            "Use a .csv or .alaqs file."
        )


def validate_config(config):
    """Validate required keys and file existence in a parsed config dict.

    Args:
        config: Parsed config dict returned by parse_config().

    Returns:
        list[str]: List of validation error messages (empty if valid).
    """
    errors = []

    if not config.get("emissions_csv_path"):
        errors.append("Missing required key: emissions_csv_path")
    elif not os.path.isfile(config["emissions_csv_path"]):
        errors.append(f"emissions_csv_path does not exist: {config['emissions_csv_path']}")

    if not config.get("meteo_csv_path"):
        errors.append("Missing required key: meteo_csv_path")
    elif not os.path.isfile(config["meteo_csv_path"]):
        errors.append(f"meteo_csv_path does not exist: {config['meteo_csv_path']}")

    if not config.get("output_path"):
        errors.append("Missing required key: output_path")

    if not config.get("pollutants"):
        errors.append("Missing required key: pollutants (comma-separated list)")

    # Grid: either grid_file_path or manual grid keys must be provided
    gc = config.get("grid_config", {})
    grid_file = config.get("grid_file_path", "")
    has_manual_grid = gc.get("x_cells", 0) > 0 and gc.get("y_cells", 0) > 0

    if grid_file and not os.path.isfile(grid_file):
        errors.append(f"grid_file_path does not exist: {grid_file}")
    elif not grid_file and not has_manual_grid:
        errors.append(
            "Missing grid definition: provide either grid_file_path "
            "or manual grid keys (x_cells, y_cells, etc.)"
        )

    # AUSTAL executable (optional, but must exist if provided)
    austal_exe = config.get("austal_exe_path", "")
    if austal_exe and not os.path.isfile(austal_exe):
        errors.append(f"austal_exe_path does not exist: {austal_exe}")

    return errors


def load_config_interactive(initial_path):
    """Parse config from initial_path, retrying interactively on failure.

    Args:
        initial_path: Path to the initial config file.

    Returns:
        tuple: (config_dict, resolved_path)
    """
    config_path = initial_path
    while True:
        try:
            return parse_config(config_path), config_path
        except Exception as exc:
            announce_err(f"Failed to parse config '{config_path}': {exc}")
            if sys.stdin is not None and sys.stdin.isatty():
                announce("Provide a path to a valid config (or 'q' to quit): ", end="")
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
                config_path = os.path.expandvars(user_input)
            else:
                announce_err("Config invalid and no interactive input available; exiting.")
                sys.exit(1)


def validate_config_interactive(config, config_path):
    """Validate config, retrying interactively if invalid.

    Args:
        config: Parsed config dict.
        config_path: Path the config was loaded from.

    Returns:
        tuple: (validated_config_dict, config_path)
    """
    while True:
        errors = validate_config(config)
        if not errors:
            return config, config_path

        announce("")
        announce("Configuration issues:")
        for err in errors:
            announce_err(f"  - {err}")

        if sys.stdin is not None and sys.stdin.isatty():
            announce("")
            announce("Enter a path to a valid config (or 'q' to quit): ", end="")
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
            config_path = os.path.expandvars(user_input)
            try:
                config, config_path = load_config_interactive(config_path)
            except SystemExit:
                raise
        else:
            announce_err("Configuration invalid and no interactive input; exiting.")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """Main execution function."""
    from datetime import datetime as _dt

    parser = argparse.ArgumentParser(
        description="Generate AUSTAL input files from emissions and meteo CSVs."
    )
    parser.add_argument("config_txt", help="Path to key=value config .txt file")
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Print elapsed time on completion",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Parse and validate config without generating files",
    )
    parser.add_argument(
        "--run-austal",
        action="store_true",
        dest="run_austal",
        help="Run the AUSTAL executable after generating input files (requires austal_exe_path in config)",
    )
    args = parser.parse_args()

    # Resolve config file
    config_path = os.path.expandvars(args.config_txt)
    config, config_path = load_config_interactive(config_path)
    config, config_path = validate_config_interactive(config, config_path)

    show_logs = config["show_logs"]
    if not show_logs:
        logging.disable(logging.CRITICAL)
        warnings.filterwarnings("ignore")
    else:
        logging.disable(logging.NOTSET)
        logging.basicConfig(level=logging.INFO)

    announce("=" * 60)
    announce("AUSTAL Input File Generator — CSV mode".center(60))
    announce("=" * 60)
    announce("")
    announce(f"Config:        {config_path}")
    announce(f"Emissions CSV: {config['emissions_csv_path']}")
    announce(f"Meteo CSV:     {config['meteo_csv_path']}")
    announce(f"Output path:   {config['output_path']}")
    announce(f"Pollutants:    {', '.join(config['pollutants'])}")
    if config.get("austal_exe_path"):
        announce(f"AUSTAL exe:    {config['austal_exe_path']}")
    if config.get("grid_file_path"):
        announce(f"Grid file:     {config['grid_file_path']}")
    gc = config["grid_config"]
    announce(
        f"Grid:          {gc['x_cells']}x{gc['y_cells']}x{gc['z_cells']} cells, "
        f"{gc['x_resolution']}x{gc['y_resolution']}x{gc['z_resolution']}m, "
        f"origin ({gc['reference_latitude']}, {gc['reference_longitude']}, "
        f"{gc['reference_altitude']}m)"
    )
    announce(
        f"Quality level: {config['austal_config']['quality_level']}   "
        f"Mixing height: {config['austal_config']['mixing_height_enabled']}"
    )
    announce("")

    if args.dry_run:
        announce("Dry run — no files will be generated.")
        sys.exit(0)

    import_openalaqs_modules()

    start_time = _dt.now()

    try:
        announce("=" * 60)
        announce("Generating AUSTAL input files".center(60))
        announce("=" * 60)
        announce("")

        generate_austal_from_csv(
            emissions_csv_path=config["emissions_csv_path"],
            meteo_csv_path=config["meteo_csv_path"],
            grid_config=config["grid_config"],
            austal_config=config["austal_config"],
            output_dir=config["output_path"],
            selected_pollutants=config["pollutants"],
        )

    except (FileNotFoundError, ValueError) as exc:
        announce_err(f"\nInput error: {exc}")
        sys.exit(1)
    except RuntimeError as exc:
        announce_err(f"\nGeneration failed: {exc}")
        sys.exit(1)
    except Exception as exc:
        announce_err(f"\nUnexpected error: {exc}")
        sys.exit(1)

    gen_end_time = _dt.now()

    announce("")
    announce("=" * 60)
    announce("AUSTAL input files generated successfully".center(60))
    announce("=" * 60)
    announce(f"Output: {config['output_path']}")

    # ── Run AUSTAL executable if requested via --run-austal ──────────
    austal_exe = config.get("austal_exe_path", "")
    ran_austal = False
    if args.run_austal:
        if not austal_exe:
            announce_err(
                "\n--run-austal was requested but austal_exe_path is not set in the config."
            )
            sys.exit(1)
        if not os.path.isfile(austal_exe):
            announce_err(
                f"\n--run-austal was requested but austal_exe_path does not exist: {austal_exe}"
            )
            sys.exit(1)

        ran_austal = True
        announce("")
        announce("=" * 60)
        announce("Running AUSTAL dispersion model".center(60))
        announce("=" * 60)
        announce("")
        announce(f"Executable: {austal_exe}")
        announce(f"Work dir:   {config['output_path']}")
        announce("")

        try:
            cmd = [austal_exe, os.path.abspath(config["output_path"])]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="latin-1",
            )

            if proc.stdout:
                for line in proc.stdout.strip().splitlines():
                    announce(f"  [AUSTAL] {line}")
            if proc.stderr:
                for line in proc.stderr.strip().splitlines():
                    announce_err(f"  [AUSTAL err] {line}")

            if proc.returncode != 0:
                announce_err(
                    f"\nAUSTAL exited with code {proc.returncode}."
                )
                sys.exit(proc.returncode)

            announce("")
            announce("AUSTAL completed successfully.")
        except OSError as exc:
            announce_err(f"\nFailed to run AUSTAL: {exc}")
            sys.exit(1)

    end_time = _dt.now()

    if args.timing:
        announce("")
        announce("-" * 60)
        announce("Timing summary".center(60))
        announce("-" * 60)
        announce(f"  Generation:    {_format_timedelta(gen_end_time - start_time)}")
        if ran_austal:
            announce(f"  AUSTAL run:    {_format_timedelta(end_time - gen_end_time)}")
        announce(f"  Total elapsed: {_format_timedelta(end_time - start_time)}")


if __name__ == "__main__":
    if b_qgis_libs_imported:
        main()
