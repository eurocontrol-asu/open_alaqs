"""`python -m austal_prep` honours the writer keys of config.json.

source_aggregation (and source_offset_cells, max_receptors) are fields of
AustalStudyConfig that the runner uses, and both make_config scripts write
them, but the CLI built the study config without them, so the dataclass
defaults always applied. apply_nox_corrections and atmosphere_model are
emission-calculation keys: austal_prep reads emissions already computed
(emissions.parquet) and has no use for them.
"""

import json
from types import SimpleNamespace

import pytest

import austal_prep.__main__ as cli

GRID = {"dd": 250.0, "nx": 10, "ny": 10, "x0": -1250.0, "y0": -1250.0, "sk": [0, 3]}


def test_keys_read_from_config():
    study = cli._build_study_config(
        {
            "title": "t",
            "grid": GRID,
            "source_aggregation": "none",
            "source_offset_cells": 3,
            "max_receptors": None,
        }
    )
    assert study.source_aggregation == "none"
    assert study.source_offset_cells == 3
    assert study.max_receptors is None


def test_defaults_when_absent():
    study = cli._build_study_config({"title": "t", "grid": GRID})
    assert study.source_aggregation == "by_type_per_pollutant"
    assert study.source_offset_cells == 2
    assert study.max_receptors == 20


def test_invalid_aggregation_stops():
    with pytest.raises(SystemExit):
        cli._build_study_config(
            {"title": "t", "grid": GRID, "source_aggregation": "by_pollutant"}
        )


def test_main_passes_aggregation_to_runner(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"title": "t", "grid": GRID, "source_aggregation": "by_type"})
    )
    seen = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            output_dir=tmp_path,
            n_sources=0,
            n_hours=0,
            pollutants_used=[],
            n_grid_files_written=0,
            missing_meteo_hours=[],
            sources_skipped_no_geometry=[],
            sources_skipped_no_emissions=[],
        )

    monkeypatch.setattr(cli, "run_austal_prep", fake_run)
    args = ["--config", str(cfg), "--output-dir", str(tmp_path)]
    for flag in ("--sources", "--emissions", "--receptors", "--meteo"):
        args += [flag, str(tmp_path / "x")]
    assert cli.main(args) == 0
    assert seen["study_config"].source_aggregation == "by_type"
