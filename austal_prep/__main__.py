"""
Command-line interface for austal_prep.

Usage:
    python -m austal_prep \\
        --sources sources.parquet \\
        --emissions emissions.parquet \\
        --receptors receptors.csv \\
        --meteo meteo.csv \\
        --output-dir out/ \\
        --config austal_config.yaml

Or programmatically:
    from austal_prep import run_austal_prep, AustalStudyConfig, GridSpec
    report = run_austal_prep(...)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from austal_prep.config import AustalStudyConfig, GridSpec
from austal_prep.runner import run_austal_prep


def _load_config_yaml(path: Path) -> dict:
    """Load study config from YAML or JSON. YAML support requires
    PyYAML; JSON is always available."""
    text = path.read_text()
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            sys.exit(
                "PyYAML is required to load .yaml configs. "
                "Either install pyyaml or convert your config to JSON."
            )
        return yaml.safe_load(text)
    return json.loads(text)


def _build_study_config(cfg: dict) -> AustalStudyConfig:
    """Convert a parsed config dict into an AustalStudyConfig."""
    grid_cfg = cfg["grid"]
    grid = GridSpec(
        dd=float(grid_cfg["dd"]),
        nx=int(grid_cfg["nx"]),
        ny=int(grid_cfg["ny"]),
        x0=float(grid_cfg["x0"]),
        y0=float(grid_cfg["y0"]),
        sk=[float(s) for s in grid_cfg["sk"]],
        reference_x=float(grid_cfg.get("reference_x", 0.0)),
        reference_y=float(grid_cfg.get("reference_y", 0.0)),
        utm_epsg=int(grid_cfg["utm_epsg"]) if "utm_epsg" in grid_cfg else None,
    )
    return AustalStudyConfig(
        title=cfg["title"],
        grid=grid,
        qs=int(cfg.get("qs", 3)),
        z0=float(cfg.get("z0", 0.3)),
        d0=float(cfg.get("d0", 1.2)),
        ha=float(cfg.get("ha", 11.2)),
        os_options=cfg.get("os_options", "NOSTANDARD;SCINOTAT;Kmax=1"),
        pm10_fine_fraction=float(cfg.get("pm10_fine_fraction", 0.9)),
        mixing_height_included=bool(cfg.get("mixing_height_included", True)),
        grid_writer_mode=cfg.get("grid_writer_mode", "time_indexed"),
        source_height=float(cfg.get("source_height", 0.0)),
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="austal_prep",
        description="Generate AUSTAL input files from emissions+sources parquets.",
    )
    p.add_argument(
        "--sources",
        type=Path,
        required=True,
        help="sources.parquet (cross-project schema)",
    )
    p.add_argument(
        "--emissions",
        type=Path,
        required=True,
        help="emissions.parquet (cross-project schema)",
    )
    p.add_argument(
        "--receptors",
        type=Path,
        required=True,
        help="Receptor CSV (columns: name, x, y, z)",
    )
    p.add_argument(
        "--meteo",
        type=Path,
        required=True,
        help="Meteo CSV (timestamp, wind_direction_deg, wind_speed_ms, "
        "obukhov_length_m, mixing_height_m)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Where to write austal.txt + series.dmna + per-source grid files",
    )
    p.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Study config (YAML or JSON; see docs for fields)",
    )
    p.add_argument(
        "--pollutants",
        nargs="+",
        default=None,
        help="Optional whitelist of pollutants. Default: all in emissions parquet.",
    )
    p.add_argument(
        "--start", default=None, help="Optional ISO start datetime (inclusive)"
    )
    p.add_argument("--end", default=None, help="Optional ISO end datetime (inclusive)")
    p.add_argument(
        "--processes",
        type=int,
        default=None,
        help="Number of worker processes for per-source grid "
        "file writes. Default: cpu_count(). Use 1 to "
        "disable multiprocessing (serial path). "
        "Overrides any `processes` key in the config "
        "YAML/JSON.",
    )
    args = p.parse_args(argv)

    cfg = _load_config_yaml(args.config)
    study = _build_study_config(cfg)

    from datetime import datetime

    start_dt = datetime.fromisoformat(args.start) if args.start else None
    end_dt = datetime.fromisoformat(args.end) if args.end else None

    # processes precedence: CLI --processes overrides any `processes`
    # key in the config file, which overrides the default (None ->
    # os.cpu_count() inside the parallel driver).
    processes = args.processes
    if processes is None and cfg.get("processes") is not None:
        processes = int(cfg["processes"])

    report = run_austal_prep(
        sources_parquet=args.sources,
        emissions_parquet=args.emissions,
        receptor_csv=args.receptors,
        meteo_csv=args.meteo,
        output_dir=args.output_dir,
        study_config=study,
        selected_pollutants=args.pollutants,
        start_dt=start_dt,
        end_dt=end_dt,
        processes=processes,
    )

    # Print a summary
    print(f"AUSTAL prep complete. Output: {report.output_dir}")
    print(f"  Sources written:        {report.n_sources}")
    print(f"  Hours written:          {report.n_hours}")
    print(
        f"  Processes (multiproc):  "
        f"{processes if processes is not None else 'cpu_count'}"
    )
    print(f"  Pollutants:             {report.pollutants_used}")
    print(f"  Grid files written:     {report.n_grid_files_written}")
    if report.missing_meteo_hours:
        print(
            f"  WARNING: {len(report.missing_meteo_hours)} meteo hours "
            f"missing (filled with sentinels)"
        )
    if report.sources_skipped_no_geometry:
        print(
            f"  WARNING: {len(report.sources_skipped_no_geometry)} sources "
            f"had no overlap with the grid: "
            f"{report.sources_skipped_no_geometry}"
        )
    if report.sources_skipped_no_emissions:
        print(
            f"  Note: {len(report.sources_skipped_no_emissions)} sources had "
            f"no emissions in the time window"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
