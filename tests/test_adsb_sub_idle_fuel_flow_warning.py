"""ADS-B import: fuel flows below the engine's ICAO idle fuel flow.

The importer keeps every supplied `fuel_flow` value as given (no clamp)
and logs one warning per flight that has points below the idle (TX)
fuel flow of its engine, aircraft total (TX fuel_kg_sec x engine count),
naming the flight and the number of points.

Fixture: the training example. Flight 1764584438_PHBBA is in the
movement CSV (A20N, engine 01P20CM128, 2 engines, TX 0.091 kg/s per
engine, so 0.182 kg/s for the aircraft); flight 1764583565_PHRTM is not,
so its check is skipped.
"""

import logging
import shutil
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from qgis.testing import start_app

from open_alaqs.core.alaqsdblite import ProjectDatabase
from open_alaqs.core.tools.ads_b import _idle_fuel_flow_by_flight, import_adsb_file

start_app()

EX = Path(__file__).resolve().parents[1] / "example" / "training"
FLIGHT = "1764584438_PHBBA"
IDLE_TOTAL = 0.091 * 2


@pytest.fixture
def training_db(tmp_path):
    dst = tmp_path / "training_out.alaqs"
    shutil.copy(EX / "training_out.alaqs", dst)
    ProjectDatabase().path = str(dst)
    yield dst
    try:
        ProjectDatabase().path = None
    except Exception:
        pass


def _ads_b_messages(caplog, level):
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == level and r.name.endswith("ads_b")
    ]


def test_idle_lookup_resolves_engine_and_engine_count(training_db):
    mdf = pd.read_csv(EX / "training_movements.csv", sep=";")
    lookup = _idle_fuel_flow_by_flight(mdf, str(training_db))
    engine, idle = lookup[FLIGHT]
    assert engine == "01P20CM128"
    assert idle == pytest.approx(IDLE_TOTAL)


def test_sub_idle_fuel_flow_warns_once_per_flight_and_is_not_clamped(
    training_db, caplog
):
    csv = EX / "training_ads_b_data.csv"
    adsb = pd.read_csv(csv)
    expected_below = int(
        (adsb.loc[adsb.flight_id == FLIGHT, "fuel_flow"] < IDLE_TOTAL).sum()
    )
    assert expected_below > 0

    conn = sqlite3.connect(training_db)
    oid0 = conn.execute("SELECT MAX(oid) FROM default_aircraft_profiles").fetchone()[0]
    conn.close()

    with caplog.at_level(logging.INFO):
        ok, msg = import_adsb_file(
            str(csv), str(training_db), str(EX / "training_movements.csv")
        )
    assert ok, msg

    warnings = [
        m for m in _ads_b_messages(caplog, logging.WARNING) if "idle fuel flow" in m
    ]
    assert len(warnings) == 1
    assert FLIGHT in warnings[0]
    assert f"{expected_below} of" in warnings[0]
    assert "01P20CM128" in warnings[0]

    infos = [m for m in _ads_b_messages(caplog, logging.INFO) if "check skipped" in m]
    assert len(infos) == 1 and "1 flight(s)" in infos[0]

    # Values imported unchanged (no clamp to idle).
    conn = sqlite3.connect(training_db)
    stored = [
        r[0]
        for r in conn.execute(
            "SELECT fuel_flow_kgm FROM default_aircraft_profiles "
            "WHERE oid > ? AND profile_id = ? ORDER BY point",
            (oid0, FLIGHT),
        )
    ]
    conn.close()
    assert stored == pytest.approx(
        adsb.loc[adsb.flight_id == FLIGHT, "fuel_flow"].tolist()
    )


def test_no_warning_when_fuel_flow_at_or_above_idle(training_db, tmp_path, caplog):
    adsb = pd.read_csv(EX / "training_ads_b_data.csv")
    adsb = adsb[adsb.flight_id == FLIGHT].copy()
    adsb["fuel_flow"] = IDLE_TOTAL
    csv = tmp_path / "adsb_at_idle.csv"
    adsb.to_csv(csv, index=False)

    with caplog.at_level(logging.INFO):
        ok, msg = import_adsb_file(
            str(csv), str(training_db), str(EX / "training_movements.csv")
        )
    assert ok, msg
    assert not [
        m for m in _ads_b_messages(caplog, logging.WARNING) if "idle fuel flow" in m
    ]
