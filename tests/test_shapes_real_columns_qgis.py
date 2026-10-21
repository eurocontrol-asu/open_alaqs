"""Headless QGIS checks of the REAL shapes columns.

The SpatiaLite provider types a DECIMAL column from its stored data: a
column of whole numbers became an integer field (a typed 2.5 was saved as
3, 25 under a German locale) and an empty layer a text field. The numeric
shapes columns are now declared REAL, typed Double with or without data.

Checked here: the fields of a converted training study and of a new study
from the template are Double and convert "2.5" to 2.5; opening an
unmigrated study logs one warning naming the migration; the form check
converts with the layer's own field, so it equals the save on an
unmigrated study too.
"""

from __future__ import annotations

import importlib
import logging
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from qgis.core import (  # noqa: E402
    QgsDataSourceUri,
    QgsField,
    QgsProject,
    QgsVectorLayer,
)
from qgis.gui import QgsAttributeForm  # noqa: E402
from qgis.PyQt import QtWidgets  # noqa: E402
from qgis.PyQt.QtCore import QVariant  # noqa: E402

from open_alaqs.alaqs_config import LAYERS_CONFIG  # noqa: E402
from open_alaqs.enums import AlaqsLayerType  # noqa: E402
from open_alaqs.openalaqsuitoolkit import (  # noqa: E402
    get_alaqs_layer,
    load_layers,
    parse_number,
    validate_field,
)

REPO = Path(__file__).resolve().parents[1]
TRAINING = REPO / "example" / "training" / "training.alaqs"
TEMPLATE = REPO / "open_alaqs" / "core" / "templates" / "project.alaqs"
CHECKED = {
    "shapes_parking": ["height", "speed", "distance"],
    "shapes_roadways": ["height", "speed", "distance"],
    "shapes_point_sources": ["height", "temperature"],
    "shapes_taxiways": ["speed"],
    "shapes_buildings": ["height"],
    "shapes_gates": ["gate_height"],
    "shapes_area_sources": ["height"],
    "shapes_receptor_points": ["height"],
}


def open_table(path: Path, table: str) -> QgsVectorLayer:
    uri = QgsDataSourceUri()
    uri.setDatabase(str(path))
    uri.setDataSource("", table, "geometry")
    layer = QgsVectorLayer(uri.uri(), table, "spatialite")
    assert layer.isValid(), layer.error().message()
    return layer


def unmigrate(db: Path, tables) -> None:
    """Pre-5.4.0 declarations (DECIMAL) for `tables` of the study `db`."""
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        mig = importlib.import_module("migrate_alaqs")
    finally:
        sys.path.remove(str(REPO / "scripts"))
    con = sqlite3.connect(db)
    old = sqlite3.connect(":memory:")
    for table in tables:
        old.execute(mig.get_create_sql(con, table).replace(" REAL", " DECIMAL"))
        mig.rebuild_table(con, table, [], old)
    con.commit()
    con.close()


@pytest.fixture
def study(tmp_path):
    """A copy: opening a layer writes statistics into the file."""
    path = tmp_path / "training.alaqs"
    shutil.copy(TRAINING, path)
    return path


@pytest.fixture
def new_study(tmp_path):
    path = tmp_path / "new.alaqs"
    shutil.copy(TEMPLATE, path)
    return path


@pytest.mark.parametrize("which", ["training", "template"])
@pytest.mark.parametrize("table", sorted(CHECKED))
def test_numeric_fields_are_double(study, new_study, which, table):
    layer = open_table(study if which == "training" else new_study, table)
    for name in CHECKED[table]:
        field = layer.fields()[layer.fields().indexOf(name)]
        assert field.type() == QVariant.Double, (table, name, field.typeName())
        assert field.convertCompatible("2.5") == 2.5


def test_flags_and_offsets_unchanged(study):
    runways = open_table(study, "shapes_runways")
    touchdown = runways.fields()[runways.fields().indexOf("touchdown")]
    assert touchdown.type() != QVariant.Double
    assert touchdown.convertCompatible("2.5") == 3
    taxiways = open_table(study, "shapes_taxiways")
    assert taxiways.fields()[taxiways.fields().indexOf("instudy")].type() != (
        QVariant.Double
    )


def _warnings(caplog):
    return [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "migrate_alaqs" in r.getMessage()
    ]


def test_unmigrated_study_warns_once_on_open(study, caplog):
    unmigrate(study, ["shapes_parking", "shapes_point_sources", "shapes_taxiways"])
    project = QgsProject.instance()
    project.removeAllMapLayers()
    try:
        with caplog.at_level(logging.WARNING):
            load_layers(None, str(study))
        records = _warnings(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert "scripts/migrate_alaqs.py" in message
        assert "Upgrading from 5.3.x" in message
        assert "height" in message and "speed" in message
        # the parking layer (loaded first of the three) is the one named
        assert "Parkings" in message
        assert get_alaqs_layer(AlaqsLayerType.PARKING) is not None
        # opening the study again warns again
        caplog.clear()
        project.removeAllMapLayers()
        with caplog.at_level(logging.WARNING):
            load_layers(None, str(study))
        assert len(_warnings(caplog)) == 1
    finally:
        project.removeAllMapLayers()


def test_migrated_study_does_not_warn(study, caplog):
    project = QgsProject.instance()
    project.removeAllMapLayers()
    try:
        with caplog.at_level(logging.WARNING):
            load_layers(None, str(study))
        assert _warnings(caplog) == []
    finally:
        project.removeAllMapLayers()


def test_form_check_converts_with_the_layer_field(study, tmp_path):
    old = tmp_path / "old.alaqs"
    shutil.copy(study, old)
    unmigrate(old, ["shapes_parking"])
    migrated = open_table(study, "shapes_parking")
    unmigrated = open_table(old, "shapes_parking")
    height_old = unmigrated.fields()[unmigrated.fields().indexOf("height")]
    assert height_old.type() == QVariant.LongLong  # whole numbers stored
    assert height_old.convertCompatible("2.5") == 3  # what QGIS saves there

    edit = QtWidgets.QLineEdit()
    edit.setObjectName("height")
    edit.setText("2.5")
    assert validate_field(edit, "float", layer=migrated) == 2.5
    # on the unmigrated study the check equals the save (3), not 2.5
    assert validate_field(edit, "float", layer=unmigrated) == 3
    assert validate_field(edit, "float") == 2.5  # no layer: a Double field
    assert parse_number("2.5", False, height_old) == 3
    assert parse_number("2.5", False, None) == 2.5
    # a text-typed field (an empty unmigrated layer) falls back to Double
    assert parse_number("2.5", False, QgsField("height", QVariant.String)) == 2.5
    with pytest.raises(ValueError):
        parse_number("2.5", True, QgsField("n", QVariant.String))
    # the integer check still requires a whole number with a Double field
    year = QtWidgets.QLineEdit()
    year.setObjectName("vehicle_year")
    year.setText("2019")
    assert validate_field(year, "int", layer=migrated) == 2019
    year.setText("2019.5")
    assert validate_field(year, "int", layer=migrated) is False


def test_form_check_finds_the_layer_of_the_attribute_form(study, tmp_path):
    """The forms call validate_field(widget, type) without a layer: the
    layer comes from the QgsAttributeForm QGIS builds the custom form in."""
    old = tmp_path / "old.alaqs"
    shutil.copy(study, old)
    unmigrate(old, ["shapes_parking"])
    _keep = []
    for path, expected in ((old, 3), (study, 2.5)):
        layer = open_table(path, "shapes_parking")
        form = QgsAttributeForm(layer)
        box = QtWidgets.QWidget(form)  # the custom .ui sits inside the form
        edit = QtWidgets.QLineEdit(box)
        edit.setObjectName("height")
        edit.setText("2.5")
        _keep.append((layer, form))
        assert validate_field(edit, "float") == expected, path
    other = QtWidgets.QLineEdit()
    other.setObjectName("height")
    other.setText("2.5")
    assert validate_field(other, "float") == 2.5
