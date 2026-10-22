"""`scripts/migrate_alaqs.py --drop-extra-columns` keeps the table definition.

The column drop used to rebuild the table from name -> type only, so
PRIMARY KEY, NOT NULL and defaults were lost (shapes_runways.oid lost its
key when `capacity` was dropped). Now SQLite >= 3.35 drops the column in
place (ALTER TABLE ... DROP COLUMN), and the rebuild fallback takes the
kept columns' definitions from the reference template.
"""

from __future__ import annotations

import importlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MIGRATE = REPO / "scripts" / "migrate_alaqs.py"
TRAINING = REPO / "example" / "training" / "training.alaqs"


@pytest.fixture
def mig():
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        yield importlib.import_module("migrate_alaqs")
    finally:
        sys.path.remove(str(REPO / "scripts"))


def _schema(conn, table):
    return sorted(
        conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE tbl_name = ?", (table,)
        ).fetchall()
    )


def test_split_table_body(mig):
    sql = (
        'CREATE TABLE "t" ("oid" INTEGER PRIMARY KEY NOT NULL, '
        "name TEXT DEFAULT 'a,b' NOT NULL, [x y] DECIMAL(10, 2), "
        "CHECK (oid > 0), UNIQUE (name))"
    )
    items = mig._split_table_body(sql)
    assert [n for n, _ in items] == ["oid", "name", "x y", None, None]
    assert items[1][1] == "name TEXT DEFAULT 'a,b' NOT NULL"
    assert items[2][1] == "[x y] DECIMAL(10, 2)"


@pytest.mark.parametrize("force_rebuild", [False, True])
def test_drop_extra_column_keeps_runway_key_and_triggers(
    tmp_path, monkeypatch, force_rebuild
):
    db = tmp_path / "study.alaqs"
    shutil.copy(TRAINING, db)
    with sqlite3.connect(db) as conn:
        before_schema = _schema(conn, "shapes_runways")
        before_rows = conn.execute(
            "SELECT rowid, * FROM shapes_runways ORDER BY rowid"
        ).fetchall()
        before_gc = conn.execute(
            "SELECT * FROM geometry_columns WHERE f_table_name='shapes_runways'"
        ).fetchall()
        conn.execute("ALTER TABLE shapes_runways ADD COLUMN capacity INTEGER")
    if force_rebuild:
        # Run main() in-process with the version check forced below 3.35 so
        # that the rebuild path is taken.
        sys.path.insert(0, str(REPO / "scripts"))
        try:
            mig = importlib.import_module("migrate_alaqs")
            monkeypatch.setattr(mig, "_sqlite_version", lambda conn: (3, 34, 0))
            assert mig.main([str(db), "--drop-extra-columns", "--no-backup"]) == 0
        finally:
            sys.path.remove(str(REPO / "scripts"))
    else:
        res = subprocess.run(
            [sys.executable, str(MIGRATE), str(db), "--drop-extra-columns"]
            + ["--no-backup"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stdout + res.stderr
    with sqlite3.connect(db) as conn:
        info = {r[1]: r for r in conn.execute("PRAGMA table_info(shapes_runways)")}
        assert "capacity" not in info
        assert (
            info["oid"][2] == "INTEGER" and info["oid"][3] == 1 and info["oid"][5] == 1
        )
        assert _schema(conn, "shapes_runways") == before_schema
        assert (
            conn.execute(
                "SELECT rowid, * FROM shapes_runways ORDER BY rowid"
            ).fetchall()
            == before_rows
        )
        assert (
            conn.execute(
                "SELECT * FROM geometry_columns WHERE f_table_name='shapes_runways'"
            ).fetchall()
            == before_gc
        )
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_rebuild_takes_reference_definitions(mig, tmp_path, capsys):
    src = sqlite3.connect(tmp_path / "src.db")
    ref = sqlite3.connect(tmp_path / "ref.db")
    ref.execute(
        'CREATE TABLE "t" ("oid" INTEGER PRIMARY KEY NOT NULL, '
        '"name" TEXT NOT NULL DEFAULT \'x\', "v" REAL, UNIQUE (name))'
    )
    # Source: key lost, extra column, an index and a trigger on the table
    src.execute('CREATE TABLE "t" ("oid" INTEGER, "v" REAL, "name" TEXT, "cap" INT)')
    src.execute("CREATE INDEX t_cap ON t(cap)")
    src.execute("CREATE INDEX t_v ON t(v)")
    src.execute("CREATE TABLE log (n TEXT)")
    src.execute(
        "CREATE TRIGGER t_ins AFTER INSERT ON t BEGIN "
        "INSERT INTO log VALUES (NEW.name); END"
    )
    src.executemany(
        "INSERT INTO t VALUES (?, ?, ?, ?)", [(3, 1.5, "a", 7), (5, None, "b", 8)]
    )
    # The indexed column cannot be dropped in place: the rebuild runs
    mig.apply_drop_columns(src, "t", ["cap"], ref)
    assert "t_cap" in capsys.readouterr().err
    info = [r[1:] for r in src.execute("PRAGMA table_info(t)")]
    assert info == [
        ("oid", "INTEGER", 1, None, 1),
        ("v", "REAL", 0, None, 0),
        ("name", "TEXT", 1, "'x'", 0),
    ]
    assert src.execute("SELECT rowid, * FROM t ORDER BY oid").fetchall() == [
        (3, 3, 1.5, "a"),
        (5, 5, None, "b"),
    ]
    names = {r[0] for r in src.execute("SELECT name FROM sqlite_master")}
    assert {"t_v", "t_ins"} <= names and "t_cap" not in names
    assert not any(n.endswith("__migtmp") for n in names)
    src.execute("INSERT INTO t (v, name) VALUES (2.0, 'c')")
    assert src.execute("SELECT oid FROM t WHERE name='c'").fetchone()[0] == 6
    # the trigger is back: it logs the new row after the two original ones
    assert src.execute("SELECT n FROM log").fetchall() == [("a",), ("b",), ("c",)]
    with pytest.raises(sqlite3.IntegrityError):
        src.execute("INSERT INTO t (name) VALUES ('a')")
