"""One set of AUSTAL site parameter defaults everywhere (5.4.1, 24 Oct 2026).

z0 = 0.1 m (the TA Luft roughness length of airports), d0 = 6 z0 (0.6 m), ha = 10 m + d0
(10.6 m), with d0 and ha derived from z0 whenever they are left empty (None, "", NULL; 0 in
the plugin's spin boxes, which cannot be empty). The single source of truth is
`open_alaqs.core.tools.surface_layer_atmosphere.site_parameters`; this module checks that
the plugin's AUSTAL output module, the Calculate Dispersion fallback, the standalone CLI
(both subcommands), orchestrate / make_config, austal_prep and the Dataiku example config
all agree with it. Before: 0.2 / 1.2 / 11.2 m in the plugin (three independent fields) and
0.3 m / 4 z0 / 11.2 m in the standalone `austal` pipeline and austal_prep.
"""

from __future__ import annotations

import argparse
import inspect
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_alaqs.core.tools import surface_layer_atmosphere as sla

REPO = Path(__file__).resolve().parents[1]
DEFAULTS = (0.1, 0.6, 10.6)


# ---- the single source of truth ----------------------------------------------------


def test_site_parameters_defaults_and_derivation():
    assert sla.DEFAULT_ROUGHNESS_LENGTH_M == 0.1
    assert sla.site_parameters() == DEFAULTS
    assert sla.site_parameters(0.25) == (0.25, 1.5, 11.5)
    assert sla.site_parameters(0.1) == DEFAULTS
    # derived values print cleanly (6 * 0.1 is 0.6, not 0.6000000000000001)
    assert tuple(str(v) for v in sla.site_parameters()) == ("0.1", "0.6", "10.6")
    # explicit values are kept
    assert sla.site_parameters(0.2, 1.2, 11.2) == (0.2, 1.2, 11.2)
    # d0 given, ha derived from it
    assert sla.site_parameters(0.1, 1.0) == (0.1, 1.0, 11.0)


@pytest.mark.parametrize("empty", [None, "", " ", "NULL", "null"])
def test_empty_values_are_derived(empty):
    assert sla.site_parameters(empty, empty, empty) == DEFAULTS
    assert sla.site_parameters(0.5, empty, empty) == (0.5, 3.0, 13.0)
    assert sla.site_parameters_from_settings(empty, empty, empty) == DEFAULTS


def test_settings_zero_means_derive():
    """The plugin's spin boxes cannot be empty: 0 derives the value from z0."""
    assert sla.site_parameters_from_settings(0, 0, 0) == DEFAULTS
    assert sla.site_parameters_from_settings(0.0, 0.0, 0.0) == DEFAULTS
    assert sla.site_parameters_from_settings(0.5, 0, 0) == (0.5, 3.0, 13.0)
    assert sla.site_parameters_from_settings(0.5, 1.0, 0) == (0.5, 1.0, 11.0)
    assert sla.site_parameters_from_settings(0.2, 1.2, 11.2) == (0.2, 1.2, 11.2)
    assert sla.site_parameters_from_settings("0", "0", "0") == DEFAULTS


# ---- plugin ------------------------------------------------------------------------


def test_austal_output_module_initial_values_and_derivation(tmp_path):
    pytest.importorskip("qgis")
    from open_alaqs.core.modules.AUSTALOutputModule import AUSTALDispersionModule

    schema = AUSTALDispersionModule.settings_schema
    assert (
        schema["roughness_length_m"]["initial_value"],
        schema["displacement_height_m"]["initial_value"],
        schema["anemometer_height_m"]["initial_value"],
    ) == DEFAULTS
    for key in ("displacement_height_m", "anemometer_height_m"):
        assert "0 = derive from z0" in schema[key]["tooltip"]
    assert "0.1" in schema["roughness_length_m"]["tooltip"]

    def site(values):
        m = AUSTALDispersionModule(dict(values, output_path=str(tmp_path)))
        return (m._roughness_level, m._displacement_height, m._anemometer_height)

    assert site({}) == DEFAULTS
    assert site({"roughness_length_m": None}) == DEFAULTS
    assert (
        site(
            {
                "roughness_length_m": 0.1,
                "displacement_height_m": 0,
                "anemometer_height_m": 0,
            }
        )
        == DEFAULTS
    )
    assert site(
        {
            "roughness_length_m": 0.5,
            "displacement_height_m": None,
            "anemometer_height_m": 0.0,
        }
    ) == (0.5, 3.0, 13.0)
    assert site(
        {
            "roughness_length_m": 0.2,
            "displacement_height_m": 1.2,
            "anemometer_height_m": 11.2,
        }
    ) == (0.2, 1.2, 11.2)


def test_austal_output_module_writes_defaults_cleanly(tmp_path):
    """austal.txt gets z0 0.1, d0 0.6, ha 10.6 with the defaults."""
    pytest.importorskip("qgis")
    from open_alaqs.core.modules.AUSTALOutputModule import AUSTALDispersionModule

    m = AUSTALDispersionModule({"output_path": str(tmp_path)})
    lines = [
        f"z0\t{m._roughness_level}\t' roughness length (m)",
        f"d0\t{m._displacement_height}\t' displacement height (m)",
        f"ha\t{m._anemometer_height}\t' anemometer height (m)",
    ]
    assert [line.split("\t")[1] for line in lines] == ["0.1", "0.6", "10.6"]


def test_dispersion_analysis_fallback_uses_the_defaults():
    pytest.importorskip("qgis")
    from open_alaqs.gui.DispersionAnalysis import OpenAlaqsDispersionAnalysis as Dlg

    ui = SimpleNamespace(
        csv_quality_level_spinbox=SimpleNamespace(value=lambda: 2),
        csv_mixing_height_checkbox=SimpleNamespace(isChecked=lambda: False),
        csv_notaluft_checkbox=SimpleNamespace(isChecked=lambda: False),
    )
    fake = SimpleNamespace(ui=ui)
    cfg = Dlg._get_austal_config_from_ui(fake, mode="csv")
    assert (
        cfg["roughness_length_m"],
        cfg["displacement_height_m"],
        cfg["anemometer_height_m"],
    ) == DEFAULTS


def test_emission_calculator_service_derives_module_zeros():
    """A module setting of 0 (spin box) reaches the emission calculation as derived."""
    pytest.importorskip("qgis")
    from open_alaqs.core.EmissionCalculatorService import EmissionCalculatorService

    src = inspect.getsource(EmissionCalculatorService)
    assert "site_parameters_from_settings" in src


# ---- standalone and austal_prep ----------------------------------------------------


class _Captured(Exception):
    def __init__(self, parser):
        self.parser = parser


def _capture_parser(monkeypatch, run, argv):
    """Run a CLI entry point and return its argparse parser without executing it."""

    def _parse_args(self, args=None, namespace=None):
        raise _Captured(self)

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", _parse_args)
    with pytest.raises(_Captured) as exc:
        run(argv)
    return exc.value.parser


def _defaults(parser):
    return tuple(parser.get_default(k) for k in ("z0", "d0", "ha"))


def test_standalone_cli_aircraft_defaults(monkeypatch):
    from openalaqs_standalone import cli

    parser = _capture_parser(monkeypatch, cli.run_aircraft, ["x.alaqs", "--out", "o"])
    assert _defaults(parser) == (None, None, None)
    assert sla.site_parameters(*_defaults(parser)) == DEFAULTS
    help_text = parser.format_help()
    assert "default 0.1" in help_text
    assert "6 z0" in help_text and "10 m + d0" in help_text


def test_standalone_cli_austal_defaults(monkeypatch):
    from openalaqs_standalone import orchestrate

    parser = _capture_parser(monkeypatch, orchestrate.main, ["x.alaqs"])
    assert _defaults(parser) == (None, None, None)
    assert sla.site_parameters(*_defaults(parser)) == DEFAULTS
    help_text = parser.format_help()
    assert "default 0.1" in help_text
    assert "6 z0" in help_text and "10 m + d0" in help_text


def test_make_config_cli_defaults(monkeypatch):
    from austal_prep import make_config as ap_mc
    from openalaqs_standalone import make_config as sa_mc

    for mod in (sa_mc, ap_mc):
        parser = _capture_parser(monkeypatch, mod.main, ["x.alaqs", "o.json"])
        assert _defaults(parser) == (None, None, None)


def test_orchestrate_and_make_config_signatures():
    from austal_prep import make_config as ap_mc
    from openalaqs_standalone import make_config as sa_mc
    from openalaqs_standalone import orchestrate

    for fn in (orchestrate.orchestrate, sa_mc.make_config, ap_mc.make_config):
        params = inspect.signature(fn).parameters
        assert tuple(params[k].default for k in ("z0", "d0", "ha")) == (
            None,
            None,
            None,
        ), fn
    assert sla.site_parameters(None, None, None) == DEFAULTS


def test_make_config_writes_the_defaults(tmp_path):
    """make_config on the training fixture: config.json carries 0.1 / 0.6 / 10.6."""
    from openalaqs_standalone import make_config as sa_mc

    fixture = (
        REPO / "openalaqs_standalone" / "validation" / "data" / "training_v3.alaqs"
    )
    if not fixture.exists():
        pytest.skip("training_v3 fixture not present")
    alaqs = tmp_path / "tv3.alaqs"
    shutil.copy(fixture, alaqs)
    out = tmp_path / "config.json"
    cfg = sa_mc.make_config(alaqs, out)
    assert (cfg["z0"], cfg["d0"], cfg["ha"]) == DEFAULTS
    written = json.loads(out.read_text())
    assert (written["z0"], written["d0"], written["ha"]) == DEFAULTS
    cfg = sa_mc.make_config(alaqs, out, z0=0.5)
    assert (cfg["z0"], cfg["d0"], cfg["ha"]) == (0.5, 3.0, 13.0)


def test_austal_prep_config_defaults_and_null():
    from austal_prep.__main__ import _build_study_config
    from austal_prep.config import AustalStudyConfig, GridSpec

    grid = GridSpec(dd=250.0, nx=10, ny=10, x0=-1250.0, y0=-1250.0, sk=[0.0, 3.0])
    study = AustalStudyConfig(title="t", grid=grid)
    assert (study.z0, study.d0, study.ha) == DEFAULTS
    study = AustalStudyConfig(title="t", grid=grid, z0=0.5)
    assert (study.z0, study.d0, study.ha) == (0.5, 3.0, 13.0)
    study = AustalStudyConfig(title="t", grid=grid, z0=0.2, d0=1.2, ha=11.2)
    assert (study.z0, study.d0, study.ha) == (0.2, 1.2, 11.2)

    grid_cfg = {
        "dd": 250.0,
        "nx": 10,
        "ny": 10,
        "x0": -1250.0,
        "y0": -1250.0,
        "sk": [0, 3],
    }
    study = _build_study_config({"title": "t", "grid": grid_cfg})
    assert (study.z0, study.d0, study.ha) == DEFAULTS
    study = _build_study_config(
        {"title": "t", "grid": grid_cfg, "z0": 0.1, "d0": None, "ha": None}
    )
    assert (study.z0, study.d0, study.ha) == DEFAULTS


def test_austal_prep_writer_prints_defaults_cleanly(tmp_path):
    import numpy as np

    from austal_prep.config import AustalStudyConfig, GridSpec
    from austal_prep.writers.austal_txt import write_austal_config

    grid = GridSpec(dd=250.0, nx=10, ny=10, x0=-1250.0, y0=-1250.0, sk=[0.0, 3.0])
    out = write_austal_config(
        tmp_path / "austal.txt",
        AustalStudyConfig(title="t", grid=grid),
        ["01"],
        ["nox"],
        {"xp": [], "yp": [], "hp": []},
        np.array([[True]]),
    )
    values = {
        line.split("\t")[0]: line.split("\t")[1]
        for line in out.read_text().splitlines()
        if line.split("\t")[0] in ("z0", "d0", "ha")
    }
    assert values == {"z0": "0.1", "d0": "0.6", "ha": "10.6"}


def test_recipe_config_example_agrees():
    cfg = json.loads(
        (REPO / "example" / "training" / "recipe_config.example.json").read_text()
    )
    assert cfg["z0"] == 0.1
    assert cfg["d0"] is None and cfg["ha"] is None
    assert sla.site_parameters(cfg["z0"], cfg["d0"], cfg["ha"]) == DEFAULTS
    assert "6 z0" in cfg["_d0"] and "10 m + d0" in cfg["_ha"]
