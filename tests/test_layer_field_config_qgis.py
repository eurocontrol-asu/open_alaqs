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
    QgsDataSourceUri,
    QgsFeature,
    QgsProject,
    QgsVectorLayerUtils,
)
from qgis.PyQt import QtWidgets, uic  # noqa: E402

from open_alaqs.alaqs_config import LAYERS_CONFIG  # noqa: E402
from open_alaqs.enums import AlaqsLayerType  # noqa: E402
from open_alaqs.openalaqsuitoolkit import (  # noqa: E402
    get_alaqs_layer,
    is_null_value,
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
        elif spec["widget"] == "value_map":
            assert setup.type() == "ValueMap"
            mapped = [v for entry in setup.config()["map"] for v in entry.values()]
            for value in spec["value_map"].get("values", []):
                assert value in mapped
            stored = {str(v) for v in layer.uniqueValues(idx) if not is_null_value(v)}
            assert stored <= set(mapped), name
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
    namespace["form_open"](form, layer, feature)
    return form, namespace


def _ok_blocked(form):
    """OK is greyed out (disabled) while the form is invalid."""
    box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    return not box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).isEnabled()


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


def test_validate_field_rejects_null_representation():
    from qgis.core import QgsApplication

    from open_alaqs.openalaqsuitoolkit import validate_field

    edit = QtWidgets.QLineEdit()
    edit.setText(QgsApplication.nullRepresentation())
    assert validate_field(edit, "str") is False
    edit.setText("NAME")
    assert validate_field(edit, "str") == "NAME"


def test_osm_import_warning_does_not_index_full_id():
    src = (REPO / "open_alaqs" / "openalaqsdialog.py").read_text(encoding="utf-8")
    assert 'osm_f["full_id"]' not in src


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


# Combo boxes are value maps: refreshes, feature changes, saves ---------------

MULTISOURCE = (
    REPO
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / ("training_v3_multisource.alaqs")
)
COMBO_LAYERS = [
    AlaqsLayerType.GATE,
    AlaqsLayerType.PARKING,
    AlaqsLayerType.ROADWAY,
    AlaqsLayerType.POINT_SOURCE,
    AlaqsLayerType.AREA,
    AlaqsLayerType.TRACK,
]


def _attribute_form_of(widget):
    from qgis.gui import QgsAttributeForm
    from qgis.PyQt import sip

    (form,) = [
        sip.cast(w, QgsAttributeForm)
        for w in widget.findChildren(QtWidgets.QWidget)
        if w.metaObject().className() == "QgsAttributeForm"
    ]
    return form


@pytest.fixture
def dual_view(tmp_path):
    """An attribute table in form view (QgsDualView, AttributeEditor) on a
    copy of the multi-source study, two sample tracks added. Yields an
    opener returning (layer, view, form, run_init); run_init runs the
    layer's form_open as QGIS's legacy init does on each feature change."""
    from qgis.core import QgsEditFormConfig, QgsFeatureRequest, QgsSettings
    from qgis.gui import QgsAttributeEditorContext, QgsDualView, QgsGui, QgsMapCanvas

    from open_alaqs.core.alaqsdblite import ProjectDatabase

    QgsSettings().setValue("qgis/enableMacros", "Never")
    if not QgsGui.editorWidgetRegistry().factories():
        QgsGui.editorWidgetRegistry().initEditors()
    db = tmp_path / "multisource.alaqs"
    shutil.copy(MULTISOURCE, db)
    previous = getattr(ProjectDatabase(), "path", None)
    ProjectDatabase().path = str(db)
    canvas = QgsMapCanvas()
    _KEEP.append(canvas)
    opened = []

    def _own(layer_type):
        load_spatialite_layer(None, str(db), layer_type)
        (layer,) = [
            lyr
            for lyr in QgsProject.instance().mapLayersByName(
                LAYERS_CONFIG[layer_type]["name"]
            )
            if str(db) in lyr.source()
        ]
        opened.append(layer)
        return layer

    def open_view(layer_type, sql=None):
        if sql:
            con = sqlite3.connect(db)
            con.execute(sql)
            con.commit()
            con.close()
        if layer_type == AlaqsLayerType.TRACK:
            runway = _own(AlaqsLayerType.RUNWAY)
            tracks = _own(AlaqsLayerType.TRACK)
            for name, direction, op in (
                ("T1", "06", "Departure"),
                ("T2", "24", "Arrival"),
            ):
                feature = QgsFeature(tracks.fields())
                feature.setGeometry(next(runway.getFeatures()).geometry())
                feature["track_id"] = name
                feature["runway"] = direction
                feature["departure_arrival"] = op
                feature["instudy"] = 1
                assert tracks.dataProvider().addFeatures([feature])[0]
            QgsProject.instance().removeMapLayers([tracks.id()])
            opened.remove(tracks)
        if layer_type == AlaqsLayerType.BUILDING:
            area = _own(AlaqsLayerType.AREA)
            buildings = _own(AlaqsLayerType.BUILDING)
            feature = QgsFeature(buildings.fields())
            feature.setGeometry(next(area.getFeatures()).geometry())
            feature["building_id"] = "B1"
            feature["height"] = 12
            feature["instudy"] = 1
            assert buildings.dataProvider().addFeatures([feature])[0]
            QgsProject.instance().removeMapLayers([buildings.id()])
            opened.remove(buildings)
        layer = _own(layer_type)
        form_cfg = layer.editFormConfig()
        form_cfg.setInitFunction("")
        form_cfg.setInitCodeSource(
            QgsEditFormConfig.PythonInitCodeSource.CodeSourceNone
        )
        layer.setEditFormConfig(form_cfg)
        view = QgsDualView()
        view.init(layer, canvas, QgsFeatureRequest(), QgsAttributeEditorContext())
        view.setView(QgsDualView.ViewMode.AttributeEditor)
        _KEEP.append(view)
        fids = sorted(f.id() for f in layer.getFeatures())
        view.setCurrentEditSelection([fids[0]])
        form = _attribute_form_of(view)
        init_file = UI_DIR / LAYERS_CONFIG[layer_type]["py_filename"]
        namespace = {"__name__": f"_qgis_form_{init_file.stem}"}
        code = compile(init_file.read_text(encoding="utf-8"), str(init_file), "exec")
        exec(code, namespace)

        def run_init():
            namespace["form_open"](form, layer, form.feature())

        run_init()
        return layer, view, form, run_init, fids

    yield open_view
    for layer in opened:
        if layer.isEditable():
            layer.rollBack()
    ProjectDatabase().path = previous


def _bound_combos(layer, form):
    return [
        c
        for c in form.findChildren(QtWidgets.QComboBox)
        if layer.fields().indexFromName(c.objectName()) != -1
    ]


def _assert_plain(layer, form):
    """Every bound combo shows the stored value (or its NULL text) and no
    "(value)" placeholder item exists."""
    feature = form.feature()
    for combo in _bound_combos(layer, form):
        items = [combo.itemText(i) for i in range(combo.count())]
        assert not [t for t in items if t.startswith("(") and t.endswith(")")], (
            combo.objectName(),
            items,
        )
        stored = feature[combo.objectName()]
        null_text = (
            LAYERS_CONFIG_BY_LAYER[layer.name()]["fields"][combo.objectName()]
            .get("value_map", {})
            .get("null_text", "")
        )
        expected = null_text if is_null_value(stored) else str(stored)
        assert combo.currentText() == expected, (combo.objectName(), stored)


LAYERS_CONFIG_BY_LAYER = {cfg["name"]: cfg for cfg in LAYERS_CONFIG.values()}


@pytest.mark.parametrize("layer_type", COMBO_LAYERS, ids=lambda t: t.value)
def test_combos_show_plain_values_on_refresh(dual_view, layer_type):
    layer, view, form, run_init, fids = dual_view(layer_type)
    assert _bound_combos(layer, form)
    _assert_plain(layer, form)
    layer.startEditing()  # QGIS refreshes the form
    _assert_plain(layer, form)
    for fid in (fids[-1], fids[0]):
        view.setCurrentEditSelection([fid])
        run_init()
        _assert_plain(layer, form)
    layer.rollBack()
    _assert_plain(layer, form)


def test_gate_type_change_saved_as_plain_value(dual_view):
    layer, view, form, run_init, fids = dual_view(AlaqsLayerType.GATE)
    layer.startEditing()
    combo = form.findChild(QtWidgets.QComboBox, "gate_type")
    new_value = "CARGO" if combo.currentText() != "CARGO" else "REMOTE"
    combo.setCurrentIndex(combo.findText(new_value))
    assert form.save()
    assert layer.commitChanges()
    assert layer.getFeature(fids[0])["gate_type"] == new_value
    _assert_plain(layer, form)


def test_profile_change_saved_and_new_profile_listed(dual_view):
    layer, view, form, run_init, fids = dual_view(AlaqsLayerType.PARKING)
    con = sqlite3.connect(QgsDataSourceUri(layer.source()).database())
    con.execute("INSERT INTO user_hour_profile (profile_name) VALUES ('night_shift')")
    con.commit()
    con.close()
    run_init()  # the form adds profiles created after the study was opened
    layer.startEditing()
    combo = form.findChild(QtWidgets.QComboBox, "hour_profile")
    combo.setCurrentIndex(combo.findText("night_shift"))
    assert form.save()
    assert layer.commitChanges()
    assert layer.getFeature(fids[0])["hour_profile"] == "night_shift"
    layer.startEditing()
    _assert_plain(layer, form)


def test_point_source_refresh_keeps_values_and_type_list_follows_category(dual_view):
    from open_alaqs.core import alaqs

    # Custom emission factors: a type's defaults filled in on a refresh would
    # replace them
    layer, view, form, run_init, fids = dual_view(
        AlaqsLayerType.POINT_SOURCE, "UPDATE shapes_point_sources SET co_kg_k = 123.4"
    )
    category = form.findChild(QtWidgets.QComboBox, "category")
    point_type = form.findChild(QtWidgets.QComboBox, "point_type")
    co = form.findChild(QtWidgets.QLineEdit, "co_kg_k")
    for step in ("start editing", "switch", "switch back", "stop editing"):
        if step == "start editing":
            layer.startEditing()
        elif step == "stop editing":
            layer.rollBack()
        else:
            view.setCurrentEditSelection([fids[-1] if step == "switch" else fids[0]])
            run_init()
        assert float(co.text()) == 123.4, step
    layer.startEditing()
    # Visible types are those of the category shown
    row = alaqs.get_point_category(category.currentText())
    allowed = {t["description"] for t in alaqs.get_point_types(row["category"])}
    visible = {
        point_type.itemText(i)
        for i in range(point_type.count())
        if not point_type.view().isRowHidden(i)
    }
    assert visible <= allowed | {point_type.currentText()}
    # The user picks another category: its first type and that type's
    # defaults are filled in, and the plain values are saved
    others = [
        category.itemText(i)
        for i in range(category.count())
        if category.itemText(i) not in ("Other", category.currentText())
    ]
    target = next(c for c in others if c)
    category.setCurrentIndex(category.findText(target))
    category.activated.emit(category.currentIndex())
    row = alaqs.get_point_category(target)
    first_type = alaqs.get_point_types(row["category"])[0]
    assert point_type.currentText() == first_type["description"]
    assert co.text() == str(first_type["co_kg_k"])
    assert form.save()
    assert layer.commitChanges()
    saved = layer.getFeature(fids[0])
    assert saved["category"] == target
    assert saved["point_type"] == first_type["description"]


# OK button -------------------------------------------------------------------

NAME_COLUMNS = {
    AlaqsLayerType.RUNWAY: "runway_id",
    AlaqsLayerType.TAXIWAY: "taxiway_id",
    AlaqsLayerType.GATE: "gate_id",
    AlaqsLayerType.TRACK: "track_id",
    AlaqsLayerType.BUILDING: "building_id",
    AlaqsLayerType.PARKING: "parking_id",
    AlaqsLayerType.ROADWAY: "roadway_id",
    AlaqsLayerType.POINT_SOURCE: "source_id",
    AlaqsLayerType.AREA: "source_id",
}


def _ok(form):
    box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    return box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)


@pytest.mark.parametrize(
    "layer_type",
    [t for t in AlaqsLayerType if t != AlaqsLayerType.RUNWAY],
    ids=lambda t: t.value,
)
def test_new_feature_form_has_empty_name_and_ok_disabled(dual_view, layer_type):
    """A new feature shows an empty name box (default '') and OK greyed
    out, its tooltip naming the field; "NULL" is rejected too."""
    from qgis.core import QgsApplication
    from qgis.gui import QgsAttributeEditorContext, QgsAttributeForm

    from open_alaqs.alaqs_config import field_alias

    layer, view, _, _, fids = dual_view(layer_type)
    layer.startEditing()
    feature = QgsVectorLayerUtils.createFeature(
        layer, layer.getFeature(fids[0]).geometry()
    )
    form = QgsAttributeForm(layer, feature, QgsAttributeEditorContext())
    form.setMode(QgsAttributeEditorContext.Mode.AddFeatureMode)
    _KEEP.append(form)
    init_file = UI_DIR / LAYERS_CONFIG[layer_type]["py_filename"]
    namespace = {"__name__": f"_qgis_form_{init_file.stem}"}
    exec(
        compile(init_file.read_text(encoding="utf-8"), str(init_file), "exec"),
        namespace,
    )
    namespace["form_open"](form, layer, form.feature())
    column = NAME_COLUMNS[layer_type]
    name = form.findChild(QtWidgets.QLineEdit, column)
    assert name.text() == ""
    assert not _ok(form).isEnabled()
    assert field_alias(layer_type, column) in _ok(form).toolTip()
    name.setText(QgsApplication.nullRepresentation())
    assert not _ok(form).isEnabled()
    name.setText("A1")
    assert field_alias(layer_type, column) not in _ok(form).toolTip()


@pytest.mark.parametrize(
    "layer_type, fill",
    [
        (AlaqsLayerType.TAXIWAY, {"speed": "15"}),
        (AlaqsLayerType.BUILDING, {}),
        (AlaqsLayerType.GATE, {}),
    ],
    ids=lambda v: v.value if isinstance(v, AlaqsLayerType) else "",
)
def test_ok_enabled_once_the_new_feature_is_valid(dual_view, layer_type, fill):
    from qgis.gui import QgsAttributeEditorContext, QgsAttributeForm

    layer, view, _, _, fids = dual_view(layer_type)
    layer.startEditing()
    feature = QgsVectorLayerUtils.createFeature(
        layer, layer.getFeature(fids[0]).geometry()
    )
    form = QgsAttributeForm(layer, feature, QgsAttributeEditorContext())
    form.setMode(QgsAttributeEditorContext.Mode.AddFeatureMode)
    _KEEP.append(form)
    init_file = UI_DIR / LAYERS_CONFIG[layer_type]["py_filename"]
    namespace = {"__name__": f"_qgis_form_{init_file.stem}"}
    exec(
        compile(init_file.read_text(encoding="utf-8"), str(init_file), "exec"),
        namespace,
    )
    namespace["form_open"](form, layer, form.feature())
    assert not _ok(form).isEnabled()
    for column, text in fill.items():
        form.findChild(QtWidgets.QLineEdit, column).setText(text)
    form.findChild(QtWidgets.QLineEdit, NAME_COLUMNS[layer_type]).setText("NEW1")
    assert _ok(form).isEnabled()
    assert _ok(form).toolTip() == ""


def test_taxiway_form_has_no_time_field():
    root = UI_DIR / "ui_taxiways.ui"
    assert 'name="time"' not in root.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "text, integer, expected",
    [
        ("20000", True, 20000),
        (None, True, None),
        ("30.3", False, 30.3),
        ("30,3", False, 30.3),
        ("1e3", False, 1000.0),
    ],
)
def test_parse_number_accepts_the_form_display(text, integer, expected):
    from qgis.PyQt.QtCore import QLocale

    from open_alaqs.openalaqsuitoolkit import parse_number

    if text is None:  # 20000 as QGIS shows it with the locale's separator
        text = QLocale().toString(20000)
        expected = 20000
    assert parse_number(text, integer) == expected


def test_parse_number_rejects_decimals_for_integers():
    from open_alaqs.openalaqsuitoolkit import parse_number

    with pytest.raises(ValueError):
        parse_number("12.5", integer=True)


@pytest.mark.parametrize("layer_type", list(AlaqsLayerType), ids=lambda t: t.value)
def test_existing_training_feature_can_be_saved(form_layer, layer_type):
    """An unchanged valid feature opens with OK enabled (numbers such as
    20000 vehicles are shown with the locale's group separator)."""
    if layer_type in (AlaqsLayerType.TRACK, AlaqsLayerType.BUILDING):
        pytest.skip("no feature in the training study")
    layer, oid, open_form, save, stored = form_layer(layer_type)
    form = open_form(layer.getFeature(oid))
    assert _ok(form).isEnabled(), _ok(form).toolTip()
