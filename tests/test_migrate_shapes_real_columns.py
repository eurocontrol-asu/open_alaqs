"""`scripts/migrate_alaqs.py` converts the DECIMAL columns of the shapes
layers to REAL.

The QGIS SpatiaLite provider does not map DECIMAL to Double: it types the
column from its stored data (integer when the values are whole numbers,
text when the layer is empty), so a decimal typed in a form was rounded
(2.5 saved as 3, 25 under a German locale) or stored as text ("30,3").
The templates now declare REAL (typed Double, 2.5 saved as 2.5) and the
migration rebuilds the tables of existing studies with the reference
definitions, casting text values to numbers where they read as one.
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
TEMPLATES = REPO / "open_alaqs" / "core" / "templates"
TRAINING = REPO / "example" / "training" / "training.alaqs"

# Every numeric column of the shapes layers: REAL in the templates. The
# flags (instudy) and the whole-metre touchdown offsets stay as they are.
REAL_COLUMNS = {
    "shapes_area_sources": [
        "height",
        "heat_flux",
        "co_kg_unit",
        "hc_kg_unit",
        "nox_kg_unit",
        "sox_kg_unit",
        "pm10_kg_unit",
        "p1_kg_unit",
        "p2_kg_unit",
    ],
    "shapes_buildings": ["height"],
    "shapes_gates": ["gate_height"],
    "shapes_parking": [
        "height",
        "distance",
        "idle_time",
        "pc_p_percentage",
        "pc_d_percentage",
        "lcv_p_percentage",
        "lcv_d_percentage",
        "hdt_p_percentage",
        "hdt_d_percentage",
        "motorcycle_p_percentage",
        "bus_d_percentage",
        "vehicle_year",
        "speed",
        "co_gm_vh",
        "hc_gm_vh",
        "nox_gm_vh",
        "sox_gm_vh",
        "pm10_gm_vh",
        "p1_gm_vh",
        "p2_gm_vh",
    ],
    "shapes_point_sources": [
        "height",
        "temperature",
        "diameter",
        "velocity",
        "co_kg_k",
        "hc_kg_k",
        "nox_kg_k",
        "sox_kg_k",
        "pm10_kg_k",
        "p1_kg_k",
        "p2_kg_k",
    ],
    "shapes_receptor_points": ["xcoord", "ycoord", "height"],
    "shapes_roadways": [
        "height",
        "distance",
        "speed",
        "pc_p_percentage",
        "pc_d_percentage",
        "lcv_p_percentage",
        "lcv_d_percentage",
        "hdt_p_percentage",
        "hdt_d_percentage",
        "motorcycle_p_percentage",
        "bus_d_percentage",
        "co_gm_km",
        "hc_gm_km",
        "nox_gm_km",
        "sox_gm_km",
        "pm10_gm_km",
        "p1_gm_km",
        "p2_gm_km",
    ],
    "shapes_runways": [],
    "shapes_taxiways": ["speed", "time"],
    "shapes_tracks": [],
}
UNCHANGED_COLUMNS = {
    ("shapes_runways", "instudy"): "DECIMAL",
    ("shapes_taxiways", "instudy"): "DECIMAL",
    ("shapes_runways", "touchdown"): "INT",
    ("shapes_runways", "touchdown_2"): "INT",
    ("shapes_roadways", "vehicle_year"): "TEXT",
    ("shapes_area_sources", "unit_year"): "TEXT",
    ("shapes_point_sources", "ops_year"): "TEXT",
}


@pytest.fixture
def mig():
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        yield importlib.import_module("migrate_alaqs")
    finally:
        sys.path.remove(str(REPO / "scripts"))


def declared_types(path, table):
    con = sqlite3.connect(path)
    try:
        return {
            r[1]: (r[2] or "").upper()
            for r in con.execute(f"PRAGMA table_info({table})")
        }
    finally:
        con.close()


def unmigrate(mig, db: Path, tables=None) -> None:
    """Give the shapes tables of `db` their pre-5.4.0 declarations (DECIMAL
    instead of REAL), as a study created with 5.3.x has them."""
    con = sqlite3.connect(db)
    old = sqlite3.connect(":memory:")
    for table in tables or REAL_COLUMNS:
        sql = mig.get_create_sql(con, table)
        old.execute(sql.replace(" REAL", " DECIMAL"))
        mig.rebuild_table(con, table, [], old)
    con.commit()
    con.close()


@pytest.mark.parametrize("template", ["project.alaqs", "inventory.alaqs"])
def test_templates_declare_the_numeric_shapes_columns_real(template):
    path = TEMPLATES / template
    for table, columns in REAL_COLUMNS.items():
        types = declared_types(path, table)
        real = [c for c, t in types.items() if t == "REAL"]
        assert sorted(real) == sorted(columns), table
        assert not [c for c, t in types.items() if t == "DECIMAL" and c != "instudy"]
    for (table, column), typ in UNCHANGED_COLUMNS.items():
        assert declared_types(path, table)[column] == typ


@pytest.mark.parametrize(
    "study",
    sorted(
        p.relative_to(REPO)
        for pattern in (
            "example/training/*.alaqs",
            "openalaqs_standalone/validation/data/*.alaqs",
            "tests/data/*/*.alaqs",
            "gse_application/tests/*.alaqs",
            "scripts/emissions_austal/sample_data/*.alaqs",
        )
        for p in REPO.glob(pattern)
    ),
    ids=str,
)
def test_bundled_studies_are_migrated(study):
    for table, columns in REAL_COLUMNS.items():
        types = declared_types(REPO / study, table)
        for column in columns:
            assert types[column] == "REAL", (table, column)
        assert types.get("instudy") != "REAL"


def test_number_from_text(mig):
    assert mig.number_from_text("2.5") == 2.5
    assert mig.number_from_text(" 30,3 ") == 30.3
    assert mig.number_from_text("1e3") == 1000.0
    assert mig.number_from_text("-7") == -7.0
    for text in ("", "  ", "abc", "1,234.5", "1.234,5", "1,2,3", "nan", "inf", "1_000"):
        assert mig.number_from_text(text) is None, text
    # a comma with three decimals is ambiguous (1.234 or a grouped 1234): left
    assert mig.number_from_text("1,234") is None
    assert mig.number_from_text("-1,234") is None
    assert mig.number_from_text("1,23") == 1.23
    assert mig.number_from_text("1,2345") == 1.2345


def test_plan_retypes_shapes_columns_only(mig, tmp_path):
    src = sqlite3.connect(tmp_path / "src.db")
    ref = sqlite3.connect(tmp_path / "ref.db")
    for con, typ in ((src, "DECIMAL"), (ref, "REAL")):
        con.execute(
            f'CREATE TABLE "shapes_x" ("oid" INTEGER PRIMARY KEY NOT NULL, "height" {typ}, "instudy" TEXT)'
        )
        con.execute(
            f'CREATE TABLE "default_y" ("oid" INTEGER PRIMARY KEY NOT NULL, "v" {typ})'
        )
    plan = mig.diff_schemas(src, ref, False, False)
    assert plan.retype_columns == [("shapes_x", {"height": ("DECIMAL", "REAL")})]
    assert plan.warnings == [
        "default_y.v: source type 'DECIMAL' differs from reference 'REAL' (left unchanged)"
    ]
    assert not plan.is_empty()


def test_retype_keeps_rows_keys_triggers_and_casts_text(mig, tmp_path, capsys):
    src = sqlite3.connect(tmp_path / "src.db")
    ref = sqlite3.connect(tmp_path / "ref.db")
    ref.execute(
        'CREATE TABLE "shapes_t" ("oid" INTEGER PRIMARY KEY NOT NULL, "v" REAL, "n" TEXT)'
    )
    src.execute(
        'CREATE TABLE "shapes_t" ("oid" INTEGER PRIMARY KEY NOT NULL, "v" DECIMAL, "n" TEXT)'
    )
    src.execute("CREATE TABLE log (n TEXT)")
    src.execute(
        "CREATE TRIGGER t_ins AFTER INSERT ON shapes_t BEGIN INSERT INTO log VALUES (NEW.n); END"
    )
    rows = [
        (2, 30, "int"),
        (3, "2.5", "text decimal"),
        (5, "30,3", "decimal comma"),
        (6, "abc", "not a number"),
        (7, "", "empty"),
        (8, 1.25, "real"),
        (9, None, "null"),
    ]
    src.executemany("INSERT INTO shapes_t VALUES (?, ?, ?)", rows)
    src.commit()
    plan = mig.diff_schemas(src, ref, False, False)
    src.execute("BEGIN")
    mig.apply_plan(src, ref, plan)
    mig.verify_after(src, plan, ref)
    src.execute("COMMIT")
    err = capsys.readouterr().err
    assert (
        "shapes_t.v: 1 value(s) are not numbers and are left as text: 'abc' (rowid 6)"
        in err
    )
    info = [r[1:] for r in src.execute("PRAGMA table_info(shapes_t)")]
    assert info == [
        ("oid", "INTEGER", 1, None, 1),
        ("v", "REAL", 0, None, 0),
        ("n", "TEXT", 0, None, 0),
    ]
    assert src.execute(
        "SELECT rowid, oid, v, typeof(v) FROM shapes_t ORDER BY rowid"
    ).fetchall() == [
        (2, 2, 30.0, "real"),
        (3, 3, 2.5, "real"),
        (5, 5, 30.3, "real"),
        (6, 6, "abc", "text"),
        (7, 7, None, "null"),
        (8, 8, 1.25, "real"),
        (9, 9, None, "null"),
    ]
    src.execute("INSERT INTO shapes_t (v, n) VALUES ('12.5', 'new')")
    assert src.execute("SELECT oid, v FROM shapes_t WHERE n='new'").fetchone() == (
        10,
        12.5,
    )
    # the trigger is back (and did not fire on the rebuild's copy)
    assert src.execute("SELECT n FROM log").fetchall() == [(n,) for _, _, n in rows] + [
        ("new",)
    ]
    assert src.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def _shapes_objects(con):
    return sorted(
        con.execute(
            "SELECT type, name, tbl_name FROM sqlite_master "
            "WHERE tbl_name LIKE 'shapes_%' AND sql IS NOT NULL"
        ).fetchall()
    )


def _numeric_rows(con, table, columns):
    cols = ", ".join(f'"{c}"' for c in ["oid"] + columns)
    out = []
    for row in con.execute(f"SELECT {cols} FROM {table} ORDER BY oid"):
        out.append(
            tuple(
                (
                    float(v)
                    if isinstance(v, (int, float)) and not isinstance(v, bool)
                    else v
                )
                for v in row
            )
        )
    return out


def test_migrate_unmigrated_training_copy(mig, tmp_path):
    db = tmp_path / "study.alaqs"
    shutil.copy(TRAINING, db)
    unmigrate(mig, db)
    with sqlite3.connect(db) as con:
        assert declared_types(db, "shapes_parking")["height"] == "DECIMAL"
        before = {t: _numeric_rows(con, t, c) for t, c in REAL_COLUMNS.items()}
        objects_before = _shapes_objects(con)
        gc_before = con.execute(
            "SELECT * FROM geometry_columns ORDER BY f_table_name"
        ).fetchall()
    res = subprocess.run(
        [sys.executable, str(MIGRATE), str(db), "--dry-run"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "~ RETYPE shapes_parking: " in res.stdout
    assert "height DECIMAL -> REAL" in res.stdout
    res = subprocess.run(
        [sys.executable, str(MIGRATE), str(db), "--no-backup"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    with sqlite3.connect(db) as con:
        for table, columns in REAL_COLUMNS.items():
            types = declared_types(db, table)
            assert all(types[c] == "REAL" for c in columns), table
            assert _numeric_rows(con, table, columns) == before[table]
            pk = [r[1] for r in con.execute(f"PRAGMA table_info({table})") if r[5]]
            assert pk == ["oid"]
        assert _shapes_objects(con) == objects_before
        assert (
            con.execute(
                "SELECT * FROM geometry_columns ORDER BY f_table_name"
            ).fetchall()
            == gc_before
        )
        assert con.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    # Nothing left to do: the plan of a migrated study has no retype
    res = subprocess.run(
        [sys.executable, str(MIGRATE), str(db), "--dry-run"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert "RETYPE" not in res.stdout


@pytest.fixture
def study_536(tmp_path):
    """The 5.3.6 training_v3 study (DECIMAL shapes columns, taxiway `time`
    holding the text 'Calculated' in 11 rows)."""
    path = tmp_path / "training_v3_536.alaqs"
    try:
        data = subprocess.run(
            [
                "git",
                "show",
                "b15e444:openalaqs_standalone/validation/data/training_v3.alaqs",
            ],
            cwd=str(REPO),
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"5.3.6 study not available from git: {exc}")
    path.write_bytes(data)
    return path


def test_migrate_536_study(mig, study_536):
    db = study_536
    with sqlite3.connect(db) as con:
        assert declared_types(db, "shapes_parking")["speed"] == "DECIMAL"
        before = {t: _numeric_rows(con, t, c) for t, c in REAL_COLUMNS.items()}
        objects_before = _shapes_objects(con)
        calculated = con.execute(
            "SELECT rowid FROM shapes_taxiways WHERE time = 'Calculated' ORDER BY rowid"
        ).fetchall()
        assert len(calculated) == 11
    res = subprocess.run(
        [sys.executable, str(MIGRATE), str(db), "--no-backup"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    # one warning per column, with the count and three examples, not one per row
    warnings = [line for line in res.stderr.splitlines() if line.startswith("WARNING")]
    assert len(warnings) == 1
    assert warnings[0].startswith(
        "WARNING: shapes_taxiways.time: 11 value(s) are not numbers and are left "
        f"as text: 'Calculated' (rowid {calculated[0][0]}), "
    )
    assert "and 8 more" in warnings[0]
    with sqlite3.connect(db) as con:
        for table, columns in REAL_COLUMNS.items():
            types = declared_types(db, table)
            assert all(types[c] == "REAL" for c in columns), table
            assert _numeric_rows(con, table, columns) == before[table], table
            assert [
                r[1] for r in con.execute(f"PRAGMA table_info({table})") if r[5]
            ] == ["oid"]
        assert declared_types(db, "shapes_runways")["instudy"] == "DECIMAL"
        assert _shapes_objects(con) == objects_before
        assert con.execute("PRAGMA integrity_check").fetchone() == ("ok",)
