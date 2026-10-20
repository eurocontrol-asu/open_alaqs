"""tools/test_fixtures/rebuild_training_example_inventory.py: --input-dir, --end.

Without arguments the script must behave as before (example/training,
movements up to 2025-12-03 09:00:00, output example/training/training_out.alaqs).
"""

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "test_fixtures" / "rebuild_training_example_inventory.py"
EX = REPO / "example" / "training"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("_rebuild_training", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_defaults_unchanged(mod):
    args = mod.parse_args([])
    assert args.input_dir == EX
    assert args.end == "2025-12-03 09:00:00"
    assert args.out == str(EX / "training_out.alaqs")
    params = mod.model_parameters(args.input_dir, args.end)
    assert params == mod.MODEL_PARAMETERS
    assert params["movement_path"] == str(EX / "training_movements.csv")
    assert params["study_start_date"] == "2025-12-01 06:00:00"
    assert params["study_end_date"] == "2025-12-03 09:00:00"


def test_input_dir_and_end(mod, tmp_path):
    args = mod.parse_args(["--input-dir", str(tmp_path), "--end", "2025-12-02T10:00"])
    assert args.out == str(tmp_path / "training_out.alaqs")
    params = mod.model_parameters(args.input_dir, args.end)
    assert params["movement_path"] == str(tmp_path / "training_movements.csv")
    assert params["study_end_date"] == "2025-12-02 10:00:00"
    # the module default is not modified
    assert mod.MODEL_PARAMETERS["study_end_date"] == "2025-12-03 09:00:00"
    assert mod.MODEL_PARAMETERS["movement_path"] == str(EX / "training_movements.csv")


def test_out_overrides_input_dir_default(mod, tmp_path):
    out = tmp_path / "x.alaqs"
    args = mod.parse_args(["--input-dir", str(tmp_path), "--out", str(out)])
    assert args.out == str(out)


def test_bad_end_is_rejected(mod):
    with pytest.raises(SystemExit):
        mod.parse_args(["--end", "tomorrow"])
