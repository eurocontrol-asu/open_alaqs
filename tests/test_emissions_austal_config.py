"""scripts/emissions_austal/run_emissions_austal.py: config parsing.

- source_dynamics: the smooth-and-shift spellings were normalised to
  "smooth_shift", which MovementSourceModule.smoothAndShiftEnabled does not
  recognise (it takes "default" or "smooth & shift"), so they ran without
  source dynamics; unknown values passed through silently.
- should_apply_nox_corrections: only the exact string "True" enabled it;
  "true", "1", "yes" meant False.
- austal_settings: the txt value stayed a string and
  `dict.update(str)` failed in run_calculation; it is now a JSON object.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "emissions_austal"
    / "run_emissions_austal.py"
)


@pytest.fixture(scope="module")
def mod():
    saved = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location("_run_emissions_austal", SCRIPT)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        # the script puts its plugin directory first on sys.path
        sys.path[:] = saved
    return m


def _write(tmp_path, extra=""):
    p = tmp_path / "cfg.txt"
    p.write_text(
        "db_path=x.alaqs\n"
        "start_dt_inclusive=2025-12-01T06:00:00\n"
        "end_dt_inclusive=2025-12-01T07:00:00\n"
        "time_interval_seconds=3600\n"
        "pollutant=NOx\n" + extra
    )
    return p


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("none", "none"),
        ("OFF", "none"),
        ("default", "default"),
        ("Default", "default"),
        ("smooth & shift", "smooth & shift"),
        ("smooth_shift", "smooth & shift"),
        ("Smooth&Shift", "smooth & shift"),
        ("smooth and shift", "smooth & shift"),
        ("sas", "smooth & shift"),
    ],
)
def test_source_dynamics_mapping(mod, tmp_path, raw, expected):
    cfg = mod.parse_config(_write(tmp_path, f"source_dynamics={raw}\n"))
    assert cfg["source_dynamics"] == expected


def test_source_dynamics_values_are_ones_the_movement_module_enables(mod):
    """Every non-"none" result must switch smooth-and-shift on in the plugin's
    MovementSourceModule (smoothAndShiftEnabled), and "none" must not."""
    from types import SimpleNamespace

    from open_alaqs.core.modules.MovementSourceModule import MovementSourceModule

    for raw, value in mod._SOURCE_DYNAMICS.items():
        stub = SimpleNamespace(getApplySmoothAndShift=lambda v=value: v)
        enabled = MovementSourceModule.smoothAndShiftEnabled(stub)
        assert enabled == (value != "none"), raw


@pytest.mark.parametrize("raw", ["smooth", "shift", "smooht", "yes"])
def test_source_dynamics_unknown_value_is_an_error(mod, tmp_path, raw):
    with pytest.raises(ValueError, match="source_dynamics"):
        mod.parse_config(_write(tmp_path, f"source_dynamics={raw}\n"))


def test_source_dynamics_default_when_absent(mod, tmp_path):
    assert mod.parse_config(_write(tmp_path))["source_dynamics"] == "none"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("True", True),
        ("true", True),
        ("1", True),
        ("YES", True),
        ("False", False),
        ("false", False),
        ("0", False),
        ("no", False),
    ],
)
def test_nox_corrections_strict_bool(mod, tmp_path, raw, expected):
    cfg = mod.parse_config(_write(tmp_path, f"should_apply_nox_corrections={raw}\n"))
    assert cfg["should_apply_nox_corrections"] is expected


@pytest.mark.parametrize("raw", ["", "Tru", "on", "2", "None"])
def test_nox_corrections_invalid_is_an_error(mod, tmp_path, raw):
    with pytest.raises(ValueError, match="should_apply_nox_corrections"):
        mod.parse_config(_write(tmp_path, f"should_apply_nox_corrections={raw}\n"))


def test_nox_corrections_default_false(mod, tmp_path):
    assert mod.parse_config(_write(tmp_path))["should_apply_nox_corrections"] is False


def test_austal_settings_json_from_txt(mod, tmp_path):
    cfg = mod.parse_config(
        _write(
            tmp_path,
            'austal_settings={"quality_level": 2, "options_string": "SCINOTAT"}\n',
        )
    )
    assert cfg["austal_settings"] == {"quality_level": 2, "options_string": "SCINOTAT"}


def test_austal_settings_absent_is_not_added(mod, tmp_path):
    assert "austal_settings" not in mod.parse_config(_write(tmp_path))


@pytest.mark.parametrize("raw", ["{'quality_level': 2}", "[1, 2]", "quality_level=2"])
def test_austal_settings_invalid_is_an_error(mod, tmp_path, raw):
    with pytest.raises(ValueError, match="austal_settings"):
        mod.parse_config(_write(tmp_path, f"austal_settings={raw}\n"))


def test_austal_settings_dict_from_python_callers_and_round_trip(mod):
    settings = {"quality_level": 3, "roughness_length_m": 0.5}
    assert mod.parse_austal_settings(settings) == settings
    assert mod.parse_austal_settings(None) == {}
    assert mod.parse_austal_settings("") == {}
    text = mod.format_austal_settings(settings)
    assert json.loads(text) == settings
    assert mod.parse_austal_settings(text) == settings
