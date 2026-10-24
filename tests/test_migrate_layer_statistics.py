"""`scripts/migrate_alaqs.py` drops the SpatiaLite per-column statistics of a
rebuilt table, so QGIS types the retyped columns from their declaration.

QGIS writes `geometry_columns_field_infos` (UpdateLayerStatistics) each
time a layer is edited, and when the rows exist it types the fields from
them, not from the declared column types. A 5.3.x study edited in QGIS has
rows saying the DECIMAL columns held integers (whole numbers) or text
(empty layer). The migration rebuilt the table with REAL columns but left
those rows, so QGIS kept typing the columns as integer or text: the forms
still refused a decimal with "Upgrade the study with
scripts/migrate_alaqs.py", which the user had just run, and the study
still logged the unmigrated warning when opened. The rows of a rebuilt
table are now deleted; QGIS then types REAL as Double (5.4.1).
"""

from __future__ import annotations

import importlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from qgis.core import QgsFeature, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant
from qgis.testing import start_app

start_app()

REPO = Path(__file__).resolve().parents[1]
MIGRATE = REPO / "scripts" / "migrate_alaqs.py"
TRAINING = REPO / "example" / "training" / "training.alaqs"
TABLE = "shapes_parking"
COLUMNS = ["height", "speed", "distance", "idle_time"]


@pytest.fixture
def mig():
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        yield importlib.import_module("migrate_alaqs")
    finally:
        sys.path.remove(str(REPO / "scripts"))


def _layer(db: Path) -> QgsVectorLayer:
    layer = QgsVectorLayer(
        f"dbname='{db}' table=\"{TABLE}\" (geometry) sql=", TABLE, "spatialite"
    )
    assert layer.isValid()
    return layer


def _field_types(db: Path) -> dict[str, int]:
    fields = _layer(db).fields()
    return {c: fields[fields.indexOf(c)].type() for c in COLUMNS}


def _edit_in_qgis(db: Path) -> None:
    """Add a copy of the first feature through the provider, as a user
    editing the layer does: QGIS then writes the layer statistics."""
    layer = _layer(db)
    assert layer.startEditing()
    first = next(layer.getFeatures())
    feature = QgsFeature(layer.fields())
    feature.setGeometry(first.geometry())
    attributes = first.attributes()
    attributes[0] = None
    attributes[layer.fields().indexOf("parking_id")] = "P_STATS"
    feature.setAttributes(attributes)
    assert layer.addFeature(feature)
    assert layer.commitChanges(), layer.commitErrors()


def _field_infos(db: Path):
    with sqlite3.connect(db) as con:
        return con.execute(
            "SELECT column_name, integer_values, double_values, text_values "
            "FROM geometry_columns_field_infos WHERE f_table_name = ? "
            "ORDER BY column_name",
            (TABLE,),
        ).fetchall()


@pytest.fixture
def edited_old_study(mig, tmp_path):
    """A 5.3.x-style study (DECIMAL columns holding whole numbers) that was
    edited in QGIS, so it carries the integer statistics."""
    from tests.test_migrate_shapes_real_columns import unmigrate

    db = tmp_path / "study.alaqs"
    shutil.copy(TRAINING, db)
    unmigrate(mig, db, tables=[TABLE])
    _edit_in_qgis(db)
    infos = {row[0]: row[1:] for row in _field_infos(db)}
    assert infos, "QGIS did not write geometry_columns_field_infos"
    assert all(infos[c][0] > 0 and infos[c][1] == 0 for c in COLUMNS), infos
    assert all(t == QVariant.LongLong for t in _field_types(db).values())
    return db


def test_qgis_types_the_migrated_columns_double(edited_old_study):
    db = edited_old_study
    res = subprocess.run(
        [sys.executable, str(MIGRATE), str(db), "--no-backup"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert f"~ RETYPE {TABLE}: " in res.stdout
    assert _field_infos(db) == []
    with sqlite3.connect(db) as con:
        # the layer's own statistics row (extent, row count) is kept
        assert con.execute(
            "SELECT count(*) FROM geometry_columns_statistics WHERE f_table_name = ?",
            (TABLE,),
        ).fetchone() == (1,)
        assert con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0] == 2
    assert all(t == QVariant.Double for t in _field_types(db).values())

    from open_alaqs.openalaqsuitoolkit import unmigrated_numeric_fields

    assert unmigrated_numeric_fields(_layer(db), TABLE) == []


def test_no_metadata_table_is_a_no_op(mig, tmp_path):
    db = tmp_path / "plain.sqlite"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE shapes_parking (oid INTEGER PRIMARY KEY, height REAL)"
        )
        assert mig.drop_layer_field_statistics(con, "shapes_parking") == 0


def test_study_retyped_by_the_540_script_gets_its_statistics_removed(
    edited_old_study, mig
):
    """The 5.4.0 script rebuilt the table and kept the statistics. On such a
    study the plan has a STATISTICS step and nothing else; applying it
    restores the Double typing, and a second run finds nothing to do."""
    db = edited_old_study
    with sqlite3.connect(db) as con, sqlite3.connect(
        REPO / "open_alaqs" / "core" / "templates" / "project.alaqs"
    ) as ref:
        mig.rebuild_table(con, TABLE, [], ref)  # as the 5.4.0 script did ...
        con.commit()
    with sqlite3.connect(db) as con:  # ... with the statistics kept
        con.executemany(
            "INSERT INTO geometry_columns_field_infos (f_table_name, f_geometry_column, "
            "ordinal, column_name, null_values, integer_values, double_values, "
            "text_values, blob_values, max_size, integer_min, integer_max, "
            "double_min, double_max) VALUES (?, 'geometry', ?, ?, 0, 1, 0, 0, 0, "
            "NULL, 0, 0, NULL, NULL)",
            [(TABLE, i, c) for i, c in enumerate(COLUMNS)],
        )
    assert all(t == QVariant.LongLong for t in _field_types(db).values())
    res = subprocess.run(
        [sys.executable, str(MIGRATE), str(db), "--dry-run"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "RETYPE" not in res.stdout
    assert f"~ STATISTICS {TABLE}: " in res.stdout
    assert str(COLUMNS[0]) in res.stdout
    res = subprocess.run(
        [sys.executable, str(MIGRATE), str(db), "--no-backup"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert _field_infos(db) == []
    assert all(t == QVariant.Double for t in _field_types(db).values())
    res = subprocess.run(
        [sys.executable, str(MIGRATE), str(db), "--dry-run"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert "STATISTICS" not in res.stdout and "RETYPE" not in res.stdout, res.stdout
