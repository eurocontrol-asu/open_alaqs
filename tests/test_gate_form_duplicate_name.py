"""Gate form: advisory mark for a duplicate Gate Name.

Movements refer to gates by name, and with two gates of the same name the
calculation uses one of them only. The gate form (ui_gates.py) looks up
the other gates' names on the layer and, when one matches, colours the
name box (QGIS's soft-failure yellow) and sets a tooltip. It is advisory:
OK keeps its own logic, nothing is renamed, and no QGIS constraint is set
(a unique constraint makes QgsVectorLayerUtils.createFeature rename a
duplicate, "G7" to "G7_1").

The training study has gates G2, G4 and G7.
"""

import shutil
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from qgis.core import (  # noqa: E402
    QgsEditFormConfig,
    QgsFieldConstraints,
    QgsProject,
    QgsSettings,
    QgsVectorLayerUtils,
)
from qgis.gui import QgsAttributeEditorContext, QgsAttributeForm, QgsGui  # noqa: E402
from qgis.PyQt import QtWidgets  # noqa: E402

from open_alaqs.alaqs_config import LAYERS_CONFIG  # noqa: E402
from open_alaqs.core.alaqsdblite import ProjectDatabase  # noqa: E402
from open_alaqs.enums import AlaqsLayerType  # noqa: E402
from open_alaqs.openalaqsuitoolkit import load_spatialite_layer  # noqa: E402
from open_alaqs.ui.ui_gates import (  # noqa: E402
    DUPLICATE_NAME_STYLE,
    DUPLICATE_NAME_TOOLTIP,
    other_gates_with_name,
)

REPO = Path(__file__).resolve().parents[1]
TRAINING = REPO / "example" / "training" / "training.alaqs"
UI_DIR = REPO / "open_alaqs" / "ui"
UI_TOOLTIP = "Enter a unique name for your gate"  # ui_gates.ui
_KEEP = []  # forms stay alive: deleting them while connected crashes


@pytest.fixture
def gates(tmp_path):
    QgsSettings().setValue("qgis/enableMacros", "Never")
    if not QgsGui.editorWidgetRegistry().factories():
        QgsGui.editorWidgetRegistry().initEditors()
    db = tmp_path / "study.alaqs"
    shutil.copy(TRAINING, db)
    previous = getattr(ProjectDatabase(), "path", None)
    ProjectDatabase().path = str(db)
    load_spatialite_layer(None, str(db), AlaqsLayerType.GATE)
    (layer,) = [
        lyr
        for lyr in QgsProject.instance().mapLayersByName("Gates")
        if str(db) in lyr.source()
    ]
    layer.startEditing()
    yield layer
    layer.rollBack()
    QgsProject.instance().removeMapLayer(layer.id())
    ProjectDatabase().path = previous


def _open_form(layer, feature, add=False):
    """QgsAttributeForm with the gate .ui and field config, then form_open,
    as QGIS runs it (the Python init is run explicitly, see
    test_layer_field_config_qgis.py)."""
    form_cfg = layer.editFormConfig()
    keep = (form_cfg.initFunction(), form_cfg.initCodeSource())
    form_cfg.setInitFunction("")
    form_cfg.setInitCodeSource(QgsEditFormConfig.PythonInitCodeSource.CodeSourceNone)
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
    init_file = UI_DIR / LAYERS_CONFIG[AlaqsLayerType.GATE]["py_filename"]
    namespace = {"__name__": f"_qgis_form_{init_file.stem}"}
    exec(
        compile(init_file.read_text(encoding="utf-8"), str(init_file), "exec"),
        namespace,
    )
    namespace["form_open"](form, layer, form.feature())
    _KEEP.append(form)
    return form


def _ok(form):
    box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    return box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)


def _name_box(form):
    return form.findChild(QtWidgets.QLineEdit, "gate_id")


def _type(form, text):
    _name_box(form).setText(text)
    QtWidgets.QApplication.processEvents()


def _gate(layer, name):
    return next(f for f in layer.getFeatures() if f["gate_id"] == name)


def test_no_constraint_on_gate_name(gates):
    idx = gates.fields().indexFromName("gate_id")
    constraints = gates.fields().at(idx).constraints()
    assert (
        not constraints.constraints() & QgsFieldConstraints.Constraint.ConstraintUnique
    )


def test_new_gate_with_duplicate_name_is_marked_ok_enabled_and_saved(gates):
    feature = QgsVectorLayerUtils.createFeature(gates, _gate(gates, "G2").geometry())
    assert feature["gate_id"] == ""  # the default stays ''
    form = _open_form(gates, feature, add=True)
    form.findChild(QtWidgets.QLineEdit, "gate_height").setText("0")
    _type(form, "G7")
    box = _name_box(form)
    assert box.styleSheet() == DUPLICATE_NAME_STYLE
    assert box.toolTip() == DUPLICATE_NAME_TOOLTIP
    assert _ok(form).isEnabled(), _ok(form).toolTip()

    n_before = gates.featureCount()
    assert form.save()
    assert gates.featureCount() == n_before + 1
    names = [f["gate_id"] for f in gates.getFeatures()]
    assert names.count("G7") == 2  # not renamed


def test_rename_to_duplicate_and_back(gates):
    form = _open_form(gates, _gate(gates, "G2"))
    box = _name_box(form)
    assert box.styleSheet() == ""  # its own name is not a duplicate
    _type(form, "G7")
    assert box.styleSheet() == DUPLICATE_NAME_STYLE
    assert box.toolTip() == DUPLICATE_NAME_TOOLTIP
    assert _ok(form).isEnabled()
    _type(form, "G2")
    assert box.styleSheet() == ""
    assert box.toolTip() == UI_TOOLTIP
    assert _ok(form).isEnabled()
    _type(form, "")  # empty: the form's own check still blocks OK
    assert not _ok(form).isEnabled()
    _type(form, "G99")
    assert box.styleSheet() == "" and box.toolTip() == UI_TOOLTIP
    assert _ok(form).isEnabled()


def test_edited_feature_own_name_is_not_a_duplicate(gates):
    g7 = _gate(gates, "G7")
    assert other_gates_with_name(gates, "G7", g7.id()) == []
    assert other_gates_with_name(gates, "G7", None) == [g7.id()]
    assert other_gates_with_name(gates, "g7", None) == []  # names are exact
    form = _open_form(gates, g7)
    assert _name_box(form).styleSheet() == ""


def test_createfeature_copy_keeps_name(gates):
    src = _gate(gates, "G7")
    copy = QgsVectorLayerUtils.createFeature(
        gates, src.geometry(), dict(enumerate(src.attributes()))
    )
    assert copy["gate_id"] == "G7"


def _add_duplicate(layer, name="G7"):
    src = _gate(layer, name)
    feature = QgsVectorLayerUtils.createFeature(
        layer, src.geometry(), dict(enumerate(src.attributes()))
    )
    assert layer.addFeature(feature)
    return next(
        f for f in layer.getFeatures() if f["gate_id"] == name and f.id() != src.id()
    )


def test_existing_duplicate_marked_when_form_opens(gates):
    dup = _add_duplicate(gates)
    form = _open_form(gates, dup)
    QtWidgets.QApplication.processEvents()
    assert _name_box(form).styleSheet() == DUPLICATE_NAME_STYLE
    assert _ok(form).isEnabled()


def test_mark_survives_editing_toggled_with_form_open(gates):
    """QGIS resets the box style when editing is switched on with the form
    open (constraint result shown); the mark is put back."""
    _add_duplicate(gates)
    assert gates.commitChanges()  # layer not editable now
    *_, dup = [f for f in gates.getFeatures() if f["gate_id"] == "G7"]
    form = _open_form(gates, dup)
    gates.startEditing()
    QtWidgets.QApplication.processEvents()
    assert _name_box(form).styleSheet() == DUPLICATE_NAME_STYLE
