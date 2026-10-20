"""
Headless QGIS checks of the layer field configuration and of the custom
form fixes.

Part 1 loads every ALAQS layer from a copy of the training study through
`load_spatialite_layer` (the code path of opening a study) and checks the
aliases, the default values of a new feature, the read-only flags, the
in-study check box and the attribute-table column order and visibility.

Part 2 loads the custom .ui files with uic, as QGIS does, runs their
`form_open` and checks the fixed behaviours: the runway name of a new
runway, whole-metre touchdown offsets, the taxiway time placeholder, and
the point-source Type and Activity Unit.
"""

import shutil
import sqlite3
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from qgis.core import (  # noqa: E402
    QgsAttributeTableConfig,
    QgsFeature,
    QgsProject,
    QgsVectorLayerUtils,
)
from qgis.PyQt import QtWidgets, uic  # noqa: E402

from open_alaqs.alaqs_config import LAYERS_CONFIG  # noqa: E402
from open_alaqs.enums import AlaqsLayerType  # noqa: E402
from open_alaqs.openalaqsuitoolkit import (  # noqa: E402
    get_alaqs_layer,
    load_spatialite_layer,
)

REPO = Path(__file__).resolve().parents[1]
TRAINING = REPO / "example" / "training" / "training.alaqs"
UI_DIR = REPO / "open_alaqs" / "ui"


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    path = tmp_path_factory.mktemp("fieldcfg") / "training.alaqs"
    shutil.copy(TRAINING, path)
    return path


@pytest.fixture(scope="module")
def layers(study):
    project = QgsProject.instance()
    project.removeAllMapLayers()
    for layer_type in AlaqsLayerType:
        load_spatialite_layer(None, str(study), layer_type)
    loaded = {t: get_alaqs_layer(t) for t in AlaqsLayerType}
    yield loaded
    project.removeAllMapLayers()


@pytest.mark.parametrize("layer_type", list(AlaqsLayerType), ids=lambda t: t.value)
def test_layer_has_configured_aliases_defaults_and_flags(layers, layer_type):
    layer = layers[layer_type]
    assert layer is not None and layer.isValid()
    fields_cfg = LAYERS_CONFIG[layer_type]["fields"]
    fields = layer.fields()
    form_cfg = layer.editFormConfig()
    new = QgsVectorLayerUtils.createFeature(layer)
    present = [name for name in fields_cfg if fields.indexFromName(name) != -1]
    # The training study predates is_test_site; everything else is there.
    assert set(fields_cfg) - set(present) <= {"is_test_site"}
    for name in present:
        spec = fields_cfg[name]
        idx = fields.indexFromName(name)
        assert layer.attributeDisplayName(idx) == spec["alias"]
        assert form_cfg.readOnly(idx) == spec["read_only"], name
        if spec["default"] is not None:
            assert layer.defaultValueDefinition(idx).expression() == spec["default"]
            expected = spec["default"].strip("'")
            assert str(new[name]) == expected, (name, new[name])
        setup = layer.editorWidgetSetup(idx)
        if spec["widget"] == "checkbox":
            assert setup.type() == "CheckBox"
            assert setup.config()["CheckedState"] == "1"
            assert setup.config()["UncheckedState"] == "0"
        else:
            assert setup.type() != "ValueMap"


@pytest.mark.parametrize("layer_type", list(AlaqsLayerType), ids=lambda t: t.value)
def test_attribute_table_order_and_hidden_columns(layers, layer_type):
    layer = layers[layer_type]
    fields_cfg = LAYERS_CONFIG[layer_type]["fields"]
    columns = [
        c
        for c in layer.attributeTableConfig().columns()
        if c.type == QgsAttributeTableConfig.Type.Field
    ]
    names = [c.name for c in columns]
    expected = [n for n in fields_cfg if layer.fields().indexFromName(n) != -1]
    assert names == expected
    hidden = {c.name for c in columns if c.hidden}
    assert hidden == {n for n in expected if fields_cfg[n]["hidden_in_table"]}
    assert "oid" in hidden and names[-1] == "instudy"


def test_runway_table_order(layers):
    layer = layers[AlaqsLayerType.RUNWAY]
    visible = [
        c.name
        for c in layer.attributeTableConfig().columns()
        if c.type == QgsAttributeTableConfig.Type.Field and not c.hidden
    ]
    assert visible == ["runway_id", "touchdown", "touchdown_2"]


# Part 2: custom forms -------------------------------------------------------


class _Form(QtWidgets.QDialog):
    """Stand-in for QgsAttributeForm: records changeAttribute calls."""

    def __init__(self):
        super().__init__()
        self.changes = []

    def changeAttribute(self, field, value):  # noqa: N802 (Qt name)
        self.changes.append((field, value))


def _open_form(layer_type, layer, texts=None, values=None):
    """Load the .ui and run form_open as QGIS does: QGIS executes the init
    file's source again for every form it opens (CodeSourceFile), so the
    @run_once helpers run once per form."""
    cfg = LAYERS_CONFIG[layer_type]
    form = _Form()
    uic.loadUi(str(UI_DIR / cfg["ui_filename"]), form)
    # Values the QGIS widget wrappers put in the line edits before form_open
    for name, text in (texts or {}).items():
        form.findChild(QtWidgets.QLineEdit, name).setText(text)
    init_file = UI_DIR / cfg["py_filename"]
    namespace = {"__name__": f"_qgis_form_{init_file.stem}"}
    exec(
        compile(init_file.read_text(encoding="utf-8"), str(init_file), "exec"),
        namespace,
    )
    feature = QgsFeature(layer.fields())
    for name, value in (values or {}).items():
        feature[name] = value
        # What the QGIS value-map wrapper shows for a value of a bound combo
        combo = form.findChild(QtWidgets.QComboBox, name)
        if combo is not None:
            combo.addItem(f"({value})", value)
            combo.setCurrentIndex(combo.count() - 1)
    namespace["form_open"](form, layer, feature)
    return form, namespace


def _ok_blocked(form):
    box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    return box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).signalsBlocked()


@pytest.mark.parametrize("shown", ["", "NULL"])
def test_new_runway_gets_a_name_and_can_be_saved(layers, shown):
    """A new runway's runway_id is NULL, which QGIS shows as the NULL
    representation text in the line edit."""
    from qgis.core import QgsApplication

    shown = shown and QgsApplication.nullRepresentation()
    form, _ = _open_form(
        AlaqsLayerType.RUNWAY, layers[AlaqsLayerType.RUNWAY], {"runway_id": shown}
    )
    assert form.findChild(QtWidgets.QLineEdit, "runway_id").text() == "01/19"
    assert not _ok_blocked(form)


def test_existing_runway_shows_both_ends(layers):
    form, _ = _open_form(
        AlaqsLayerType.RUNWAY, layers[AlaqsLayerType.RUNWAY], {"runway_id": "06L/24R"}
    )

    def combo(name):
        return form.findChild(QtWidgets.QComboBox, name).currentText()

    assert (combo("first_runway_number"), combo("first_runway_letter")) == ("06", "L")
    assert (combo("second_runway_number"), combo("second_runway_letter")) == ("24", "R")
    assert form.findChild(QtWidgets.QLineEdit, "runway_id").text() == "06L/24R"


@pytest.mark.parametrize(
    "text, blocked", [("250", False), ("0", False), ("", False), ("12.5", True)]
)
def test_runway_touchdown_offset_is_whole_metres(layers, text, blocked):
    form, _ = _open_form(AlaqsLayerType.RUNWAY, layers[AlaqsLayerType.RUNWAY])
    form.findChild(QtWidgets.QLineEdit, "touchdown").setText(text)
    assert _ok_blocked(form) is blocked
    form.findChild(QtWidgets.QLineEdit, "touchdown").setText("250")
    form.findChild(QtWidgets.QLineEdit, "touchdown_2").setText(text)
    assert _ok_blocked(form) is blocked


def test_taxiway_time_is_placeholder_only(layers):
    form, _ = _open_form(AlaqsLayerType.TAXIWAY, layers[AlaqsLayerType.TAXIWAY])
    time = form.findChild(QtWidgets.QLineEdit, "time")
    assert time.text() == ""
    assert time.placeholderText() == "Calculated"
    assert not time.isEnabled()


@pytest.fixture
def point_study(tmp_path):
    """Training copy with one emission factor row without activity unit."""
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    path = tmp_path / "points.alaqs"
    shutil.copy(TRAINING, path)
    con = sqlite3.connect(path)
    row = con.execute(
        "SELECT ef.description, c.category_name FROM default_stationary_ef ef "
        "JOIN default_stationary_category c ON c.category = ef.category "
        "ORDER BY ef.oid LIMIT 1"
    ).fetchone()
    con.execute(
        "UPDATE default_stationary_ef SET activity_unit = NULL WHERE description = ?",
        [row[0]],
    )
    con.commit()
    con.close()
    previous = getattr(ProjectDatabase(), "path", None)
    ProjectDatabase().path = str(path)
    yield {"type": row[0], "category": row[1]}
    ProjectDatabase().path = previous


def test_point_source_type_saved_and_unit_not_invented(layers, point_study):
    from open_alaqs.ui.ui_point_sources import ACTIVITY_UNIT_PLACEHOLDER

    form, _ = _open_form(
        AlaqsLayerType.POINT_SOURCE, layers[AlaqsLayerType.POINT_SOURCE]
    )
    category = form.findChild(QtWidgets.QComboBox, "category")
    point_type = form.findChild(QtWidgets.QComboBox, "point_type")
    assert point_type is not None
    category.setCurrentText(point_study["category"])
    point_type.setCurrentText(point_study["type"])
    assert point_type.currentText() == point_study["type"]
    unit = form.findChild(QtWidgets.QLineEdit, "activity_unit")
    assert unit.text() == ""
    assert unit.placeholderText() == ACTIVITY_UNIT_PLACEHOLDER
    form.findChild(QtWidgets.QDialogButtonBox, "buttonBox").accepted.emit()
    assert ("point_type", point_study["type"]) in form.changes
    assert all(field != "type" for field, _ in form.changes)


def test_activity_unit_text():
    from open_alaqs.ui.ui_point_sources import activity_unit_text

    assert activity_unit_text(None) == ""
    assert activity_unit_text("1000_m3") == "1000_m3"
    assert activity_unit_text(" hr ") == "hr"


def test_validation_messages_use_display_names():
    from open_alaqs.ui import ui_parkings, ui_roadways

    assert ui_parkings.display_name("vehicle_year_field") == "Vehicles per Year"
    assert ui_parkings.display_name("idle_time_field") == "Idle Time [min]"
    assert ui_parkings.display_name("pc_p_percentage") == "PC (Petrol) [%]"
    assert ui_roadways.display_name("name_field") == "Roadway Name"
    assert ui_roadways.display_name("vehicle_year_field") == "Vehicles per Year"


# Stored combo values, NULL names, helpers ------------------------------------


@pytest.fixture
def study_db(study):
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    previous = getattr(ProjectDatabase(), "path", None)
    ProjectDatabase().path = str(study)
    yield study
    ProjectDatabase().path = previous


def _combo(form, name):
    return form.findChild(QtWidgets.QComboBox, name)


def test_gate_form_shows_stored_type(layers, study_db):
    form, _ = _open_form(
        AlaqsLayerType.GATE,
        layers[AlaqsLayerType.GATE],
        texts={"gate_id": "G2", "gate_height": "0"},
        values={"gate_type": "CARGO"},
    )
    combo = _combo(form, "gate_type")
    assert combo.currentText() == "CARGO"
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "PIER",
        "REMOTE",
        "CARGO",
    ]


@pytest.mark.parametrize(
    "layer_type, columns",
    [
        (AlaqsLayerType.PARKING, ("hour_profile", "daily_profile", "month_profile")),
        (AlaqsLayerType.ROADWAY, ("hour_profile", "daily_profile", "month_profile")),
        (
            AlaqsLayerType.POINT_SOURCE,
            ("hour_profile", "daily_profile", "month_profile"),
        ),
        (AlaqsLayerType.AREA, ("hourly_profile", "daily_profile", "monthly_profile")),
    ],
    ids=lambda v: v.value if isinstance(v, AlaqsLayerType) else "",
)
def test_forms_show_stored_profiles(layers, study_db, layer_type, columns):
    """A profile that is not in the list (e.g. deleted) is still shown,
    instead of the form falling back to "default"."""
    values = dict(zip(columns, ("night_shift", "weekdays", "summer")))
    form, _ = _open_form(layer_type, layers[layer_type], values=values)
    for column, value in values.items():
        assert _combo(form, column).currentText() == value, column


def test_point_source_form_keeps_stored_type_and_factors(layers, study_db):
    con = sqlite3.connect(study_db)
    category, description = con.execute(
        "SELECT c.category_name, ef.description FROM default_stationary_ef ef "
        "JOIN default_stationary_category c ON c.category = ef.category "
        "WHERE c.category_name != 'Other' ORDER BY ef.oid DESC LIMIT 1"
    ).fetchone()
    con.close()
    form, _ = _open_form(
        AlaqsLayerType.POINT_SOURCE,
        layers[AlaqsLayerType.POINT_SOURCE],
        texts={"co_kg_k": "123.4", "height": "7"},
        values={"category": category, "point_type": description},
    )
    assert _combo(form, "category").currentText() == category
    assert _combo(form, "point_type").currentText() == description
    # The type defaults did not replace the stored values
    assert form.findChild(QtWidgets.QLineEdit, "co_kg_k").text() == "123.4"
    assert form.findChild(QtWidgets.QLineEdit, "height").text() == "7"


def test_point_source_form_without_stored_type_keeps_it_empty(layers, study_db):
    form, _ = _open_form(
        AlaqsLayerType.POINT_SOURCE,
        layers[AlaqsLayerType.POINT_SOURCE],
        values={"category": "Power/Heat Plant"},
    )
    assert _combo(form, "category").currentText() == "Power/Heat Plant"
    assert _combo(form, "point_type").currentText() == ""


@pytest.mark.parametrize(
    "layer_type, name, others",
    [
        (AlaqsLayerType.TAXIWAY, "taxiway_id", {"speed": "15"}),
        (AlaqsLayerType.BUILDING, "building_id", {"height": "12"}),
        (AlaqsLayerType.GATE, "gate_id", {"gate_height": "0"}),
    ],
    ids=lambda v: v.value if isinstance(v, AlaqsLayerType) else "",
)
def test_null_name_blocks_ok(layers, study_db, layer_type, name, others):
    from qgis.core import QgsApplication

    form, _ = _open_form(layer_type, layers[layer_type])
    for field, text in others.items():
        form.findChild(QtWidgets.QLineEdit, field).setText(text)
    line = form.findChild(QtWidgets.QLineEdit, name)
    for text in ("", QgsApplication.nullRepresentation()):
        line.setText(text)
        assert _ok_blocked(form), repr(text)
    line.setText("A1")
    assert not _ok_blocked(form)


def test_validate_field_rejects_null_representation():
    from qgis.core import QgsApplication

    from open_alaqs.openalaqsuitoolkit import validate_field

    edit = QtWidgets.QLineEdit()
    edit.setText(QgsApplication.nullRepresentation())
    assert validate_field(edit, "str") is False
    edit.setText("NAME")
    assert validate_field(edit, "str") == "NAME"


def test_select_combo_value():
    from open_alaqs.openalaqsuitoolkit import select_combo_value

    combo = QtWidgets.QComboBox()
    combo.addItem("(CARGO)", "CARGO")
    combo.addItems(["PIER", "REMOTE", "CARGO", "(x) real item"])
    select_combo_value(combo, "CARGO")
    assert combo.currentText() == "CARGO" and combo.count() == 4
    select_combo_value(combo, "MISSING")
    assert combo.currentText() == "MISSING"
    combo.setCurrentIndex(0)
    select_combo_value(combo, None)
    assert combo.currentText() == "PIER"
    combo.insertItem(0, "(NULL)", "{2839923C-8B7D-419E-B84B-CA2FE9B80EC7}")
    select_combo_value(combo, None)
    assert combo.findText("(NULL)") == -1


def test_osm_import_warning_does_not_index_full_id():
    src = (REPO / "open_alaqs" / "openalaqsdialog.py").read_text(encoding="utf-8")
    assert 'osm_f["full_id"]' not in src


def test_new_point_source_type_has_no_null_item(layers, study_db):
    form, _ = _open_form(
        AlaqsLayerType.POINT_SOURCE,
        layers[AlaqsLayerType.POINT_SOURCE],
        values={"point_type": None},
    )
    assert _combo(form, "point_type").findText("(NULL)") == -1


# In Study and Activity Unit through a real QgsAttributeForm ------------------

INSTUDY_LAYERS = [
    AlaqsLayerType.PARKING,
    AlaqsLayerType.ROADWAY,
    AlaqsLayerType.POINT_SOURCE,
    AlaqsLayerType.AREA,
]
_KEEP = []  # forms stay alive: deleting them while connected crashes


@pytest.fixture
def form_layer(tmp_path):
    """Open one layer of a fresh training copy; yields an opener that
    builds a QgsAttributeForm (custom .ui, field config, widget wrappers)
    and runs the layer's form_open on it, as QGIS does once the feature
    is set. QGIS's own Python init needs the application's Python runner,
    so the init code is disabled in the form config and run explicitly."""
    from qgis.core import QgsEditFormConfig, QgsSettings
    from qgis.gui import QgsAttributeEditorContext, QgsAttributeForm, QgsGui

    from open_alaqs.core.alaqsdblite import ProjectDatabase

    QgsSettings().setValue("qgis/enableMacros", "Never")
    if not QgsGui.editorWidgetRegistry().factories():
        QgsGui.editorWidgetRegistry().initEditors()
    db = tmp_path / "study.alaqs"
    shutil.copy(TRAINING, db)
    previous = getattr(ProjectDatabase(), "path", None)
    ProjectDatabase().path = str(db)
    opened = []

    def open_layer(layer_type, instudy=None, is_test_site=None):
        table = LAYERS_CONFIG[layer_type]["table_name"]
        con = sqlite3.connect(db)
        oid = con.execute(f"SELECT min(oid) FROM {table}").fetchone()[0]
        if instudy is not None:
            con.execute(f"UPDATE {table} SET instudy = ? WHERE oid = ?", [instudy, oid])
            con.commit()
        if is_test_site is not None:
            # The training study predates the column (migrate_alaqs.py adds it)
            columns = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            if "is_test_site" not in columns:
                con.execute(f"ALTER TABLE {table} ADD COLUMN is_test_site TEXT")
            con.execute(
                f"UPDATE {table} SET is_test_site = ? WHERE oid = ?",
                [is_test_site, oid],
            )
            con.commit()
        con.close()
        load_spatialite_layer(None, str(db), layer_type)
        # The module fixture holds layers of the same name: pick this copy's
        (layer,) = [
            lyr
            for lyr in QgsProject.instance().mapLayersByName(
                LAYERS_CONFIG[layer_type]["name"]
            )
            if str(db) in lyr.source()
        ]
        opened.append(layer)
        layer.startEditing()

        def open_form(feature, add=False):
            cfg = LAYERS_CONFIG[layer_type]
            form_cfg = layer.editFormConfig()
            keep = (form_cfg.initFunction(), form_cfg.initCodeSource())
            form_cfg.setInitFunction("")
            form_cfg.setInitCodeSource(
                QgsEditFormConfig.PythonInitCodeSource.CodeSourceNone
            )
            layer.setEditFormConfig(form_cfg)
            form = QgsAttributeForm(layer, feature, QgsAttributeEditorContext())
            form.setMode(
                QgsAttributeEditorContext.Mode.AddFeatureMode
                if add
                else QgsAttributeEditorContext.Mode.SingleEditMode
            )
            form_cfg.setInitFunction(keep[0])
            form_cfg.setInitCodeSource(keep[1])
            layer.setEditFormConfig(form_cfg)
            init_file = UI_DIR / cfg["py_filename"]
            namespace = {"__name__": f"_qgis_form_{init_file.stem}"}
            code = compile(
                init_file.read_text(encoding="utf-8"), str(init_file), "exec"
            )
            exec(code, namespace)
            namespace["form_open"](form, layer, form.feature())
            _KEEP.append(form)
            return form

        def save(form):
            form.findChild(QtWidgets.QDialogButtonBox, "buttonBox").accepted.emit()
            assert layer.commitChanges()
            layer.startEditing()

        def stored(column, row_oid=None):
            con = sqlite3.connect(db)
            row = con.execute(
                f"SELECT {column} FROM {table} WHERE oid = ?",
                [row_oid if row_oid is not None else oid],
            ).fetchone()
            con.close()
            return row[0]

        return layer, oid, open_form, save, stored

    yield open_layer
    for layer in opened:
        if layer.isEditable():
            layer.rollBack()
    ProjectDatabase().path = previous


def _instudy_box(form):
    return form.findChild(QtWidgets.QCheckBox, "instudy")


@pytest.mark.parametrize("layer_type", INSTUDY_LAYERS, ids=lambda t: t.value)
def test_in_study_stored_0_shown_unticked_and_kept(form_layer, layer_type):
    layer, oid, open_form, save, stored = form_layer(layer_type, instudy="0")
    form = open_form(layer.getFeature(oid))
    box = _instudy_box(form)
    assert box.isVisibleTo(form) and box.isEnabled()
    assert not box.isChecked()
    save(form)
    assert stored("instudy") == "0"


@pytest.mark.parametrize("layer_type", INSTUDY_LAYERS, ids=lambda t: t.value)
def test_in_study_untick_saves_0_and_tick_saves_1(form_layer, layer_type):
    layer, oid, open_form, save, stored = form_layer(layer_type)
    form = open_form(layer.getFeature(oid))
    assert _instudy_box(form).isChecked()
    _instudy_box(form).setChecked(False)
    save(form)
    assert stored("instudy") == "0"
    form = open_form(layer.getFeature(oid))
    assert not _instudy_box(form).isChecked()
    _instudy_box(form).setChecked(True)
    save(form)
    assert stored("instudy") == "1"


@pytest.mark.parametrize("layer_type", INSTUDY_LAYERS, ids=lambda t: t.value)
def test_in_study_new_feature_defaults_to_1(form_layer, layer_type):
    layer, oid, open_form, save, stored = form_layer(layer_type)
    geometry = layer.getFeature(oid).geometry()
    form = open_form(QgsVectorLayerUtils.createFeature(layer, geometry), add=True)
    assert _instudy_box(form).isChecked()
    save(form)
    con_oid = max(f.id() for f in layer.getFeatures())
    assert stored("instudy", con_oid) == "1"


@pytest.mark.parametrize(
    "layer_type",
    # Tracks and Buildings have no feature in the training study
    [AlaqsLayerType.RUNWAY, AlaqsLayerType.TAXIWAY, AlaqsLayerType.GATE],
    ids=lambda t: t.value,
)
def test_in_study_hidden_in_forms_that_ignore_it(form_layer, layer_type):
    layer, oid, open_form, save, stored = form_layer(layer_type, instudy="0")
    form = open_form(layer.getFeature(oid))
    assert not _instudy_box(form).isVisibleTo(form)
    save(form)
    assert str(stored("instudy")) == "0"


def test_point_source_activity_unit_kept_and_editable(form_layer):
    layer, oid, open_form, save, stored = form_layer(AlaqsLayerType.POINT_SOURCE)
    con = sqlite3.connect(TRAINING)
    expected_type, expected_unit = con.execute(
        "SELECT point_type, activity_unit FROM shapes_point_sources WHERE oid = ?",
        [oid],
    ).fetchone()
    con.close()
    form = open_form(layer.getFeature(oid))
    unit = form.findChild(QtWidgets.QLineEdit, "activity_unit")
    assert unit.isEnabled() and not unit.isReadOnly()
    assert form.findChild(QtWidgets.QComboBox, "point_type").currentText() == (
        expected_type or ""
    )
    assert unit.text() == (expected_unit or "")
    save(form)
    assert stored("activity_unit") == expected_unit
    assert stored("point_type") == expected_type
    form = open_form(layer.getFeature(oid))
    form.findChild(QtWidgets.QLineEdit, "activity_unit").setText("1000_kg")
    save(form)
    assert stored("activity_unit") == "1000_kg"
    form = open_form(layer.getFeature(oid))
    assert form.findChild(QtWidgets.QLineEdit, "activity_unit").text() == "1000_kg"


def _test_site_box(form):
    return form.findChild(QtWidgets.QCheckBox, "is_test_site")


def test_engine_test_site_stored_1_shown_ticked_and_kept(form_layer):
    layer, oid, open_form, save, stored = form_layer(
        AlaqsLayerType.AREA, is_test_site="1"
    )
    form = open_form(layer.getFeature(oid))
    assert _test_site_box(form).isChecked()
    assert form.findChild(QtWidgets.QPushButton, "load_events_csv").isEnabled()
    save(form)
    assert stored("is_test_site") == "1"


def test_engine_test_site_tick_and_untick_saved(form_layer):
    layer, oid, open_form, save, stored = form_layer(
        AlaqsLayerType.AREA, is_test_site="0"
    )
    form = open_form(layer.getFeature(oid))
    assert not _test_site_box(form).isChecked()
    assert not form.findChild(QtWidgets.QPushButton, "load_events_csv").isEnabled()
    _test_site_box(form).setChecked(True)
    assert form.findChild(QtWidgets.QPushButton, "load_events_csv").isEnabled()
    save(form)
    assert stored("is_test_site") == "1"
    form = open_form(layer.getFeature(oid))
    assert _test_site_box(form).isChecked()
    _test_site_box(form).setChecked(False)
    save(form)
    assert stored("is_test_site") == "0"


def test_engine_test_site_new_feature_defaults_to_0(form_layer):
    layer, oid, open_form, save, stored = form_layer(
        AlaqsLayerType.AREA, is_test_site="0"
    )
    geometry = layer.getFeature(oid).geometry()
    form = open_form(QgsVectorLayerUtils.createFeature(layer, geometry), add=True)
    assert not _test_site_box(form).isChecked()
    save(form)
    assert stored("is_test_site", max(f.id() for f in layer.getFeatures())) == "0"


def test_engine_test_site_zero_fills_blank_rates_before_save(form_layer):
    layer, oid, open_form, save, stored = form_layer(
        AlaqsLayerType.AREA, is_test_site="0"
    )
    form = open_form(layer.getFeature(oid))
    form.findChild(QtWidgets.QLineEdit, "hc_kg_unit").setText("")
    _test_site_box(form).setChecked(True)
    assert form.findChild(QtWidgets.QLineEdit, "hc_kg_unit").text() == "0"
    assert form.findChild(QtWidgets.QLineEdit, "co_kg_unit").text() == "0.1"
    save(form)
    assert stored("hc_kg_unit") == 0
    assert stored("co_kg_unit") == 0.1


def test_engine_test_events_button_opens_dialog_for_the_source(form_layer, monkeypatch):
    import open_alaqs.openalaqsdialog as dialog_module
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    opened = []

    class _Dialog:
        def __init__(self, iface=None, database_path=None, source_id=None):
            opened.append((database_path, source_id))

        def exec(self):
            return 0

    monkeypatch.setattr(dialog_module, "OpenAlaqsImportEngineTestEvents", _Dialog)
    layer, oid, open_form, save, stored = form_layer(
        AlaqsLayerType.AREA, is_test_site="1"
    )
    form = open_form(layer.getFeature(oid))
    form.findChild(QtWidgets.QPushButton, "load_events_csv").click()
    assert opened == [(ProjectDatabase().path, layer.getFeature(oid)["source_id"])]
