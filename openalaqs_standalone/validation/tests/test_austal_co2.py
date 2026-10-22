"""`python -m openalaqs_standalone austal --pollutants co2`.

The stationary computes have no CO2 emission factors and raised
KeyError: 'co2' (compute_road ROAD_POLLUTANT_COLS). CO2 is now accepted:
the stationary sources contribute 0 and are not asked for it, with
exactly one info line saying so, and the aircraft CO2 is written. Runs on
the training example, 3 hours.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from openalaqs_standalone.__main__ import main

REPO = Path(__file__).resolve().parents[3]
ALAQS = REPO / "example" / "training" / "training_out.alaqs"


def _run(out: Path, pollutants: str, capsys) -> tuple[pd.DataFrame, str]:
    rc = main(
        [
            "austal",
            str(ALAQS),
            "--out",
            str(out),
            "--year",
            "2025",
            "--pollutants",
            pollutants,
            "--include-aircraft",
            "--start",
            "2025-12-01T06:00",
            "--end",
            "2025-12-01T09:00",
        ]
    )
    assert rc == 0
    stdout = capsys.readouterr().out
    em = pd.read_parquet(out / "emissions_folder" / "emissions.parquet")
    return em, stdout


@pytest.fixture(scope="module")
def _skip_without_fixture():
    if not ALAQS.is_file():
        pytest.skip(f"missing {ALAQS}")


def test_co2_only_aircraft_written_stationary_zero(
    tmp_path, capsys, _skip_without_fixture
):
    em, stdout = _run(tmp_path / "co2", "co2", capsys)

    co2_lines = [ln for ln in stdout.splitlines() if ln.strip().startswith("co2:")]
    assert co2_lines == [
        "  co2: stationary sources contribute 0 (no CO2 emission factors); "
        "CO2 comes from the aircraft movements"
    ]
    assert set(em["pollutant"]) == {"co2"}
    assert em["source_id"].str.startswith("aircraft:").all()
    assert em["kg_in_hour"].sum() > 0
    assert (tmp_path / "co2" / "emissions_folder" / "co2_emissions.gpkg").is_file()


def test_co2_with_other_pollutants_leaves_them_unchanged(
    tmp_path, capsys, _skip_without_fixture
):
    em_mix, out_mix = _run(tmp_path / "mix", "nox,co2", capsys)
    em_nox, out_nox = _run(tmp_path / "nox", "nox", capsys)
    em_co2, _ = _run(tmp_path / "co2", "co2", capsys)

    assert sum(ln.strip().startswith("co2:") for ln in out_mix.splitlines()) == 1
    assert not any(ln.strip().startswith("co2:") for ln in out_nox.splitlines())

    key = ["timestamp", "source_id", "pollutant"]
    nox_mix = em_mix[em_mix.pollutant == "nox"].sort_values(key).reset_index(drop=True)
    pd.testing.assert_frame_equal(
        nox_mix, em_nox.sort_values(key).reset_index(drop=True)
    )
    co2_mix = em_mix[em_mix.pollutant == "co2"].sort_values(key).reset_index(drop=True)
    pd.testing.assert_frame_equal(
        co2_mix, em_co2.sort_values(key).reset_index(drop=True)
    )
    # stationary sources still carry NOx in the mixed run
    assert (~nox_mix["source_id"].str.startswith("aircraft:")).any()
