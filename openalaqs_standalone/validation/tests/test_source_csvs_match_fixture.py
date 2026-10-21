"""`validation/data/source_csvs/training_movements.csv` is the movement table
of `training_v3.alaqs` (15 movements, the two AS50 included), and the study
description of the three training_v3 files counts them."""

import csv
import sqlite3
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"


def _connect(name):
    return sqlite3.connect(f"file:{DATA / name}?mode=ro", uri=True)


def test_movements_csv_is_the_training_v3_movement_table():
    with open(DATA / "source_csvs" / "training_movements.csv", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    with _connect("training_v3.alaqs") as conn:
        cur = conn.execute("SELECT * FROM user_aircraft_movements ORDER BY oid")
        cols = [d[0] for d in cur.description][1:]
        table = [["" if v is None else str(v) for v in r[1:]] for r in cur]
    assert rows[0] == cols
    assert rows[1:] == table
    assert len(table) == 15
    assert sum(r[cols.index("aircraft")] == "AS50" for r in table) == 2


@pytest.mark.parametrize(
    "name",
    [
        "training_v3.alaqs",
        "training_v3_gatemovements.alaqs",
        "training_v3_multisource.alaqs",
    ],
)
def test_study_info_counts_the_movements(name):
    with _connect(name) as conn:
        (info,) = conn.execute("SELECT study_info FROM user_study_setup").fetchone()
        (n,) = conn.execute("SELECT COUNT(*) FROM user_aircraft_movements").fetchone()
    assert f"{n} movements" in info
