from qgis.core import QgsExpression, QgsFeatureRequest
from qgis.gui import QgsEditorWidgetWrapper
from qgis.PyQt import QtWidgets

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.enums import AlaqsLayerType
from open_alaqs.openalaqsuitoolkit import (
    update_ok_button,
    validate_field,
)

logger = get_logger(__name__)

# Advisory mark for a gate name another gate already has (the colour QGIS
# uses for a soft constraint failure). OK is not affected.
DUPLICATE_NAME_STYLE = "background-color: rgba(255, 200, 45, 0.3);"
DUPLICATE_NAME_TOOLTIP = (
    "Another gate has this name. Movements refer to gates by name and "
    "would use one of them only; rename before calculating."
)


def form_open(form, layer, feature):
    logger.debug("This is the modified simple form")
    logger.debug(f"Layer {layer} and feature {feature}")
    logger.debug(f"Attributes of fields: {feature.fields().names()}")
    logger.debug(f"Attributes of feature: {feature.attributes()}")

    # Get all the fields from the form
    fields = dict(
        name_field=form.findChild(QtWidgets.QLineEdit, "gate_id"),
        type_field=form.findChild(QtWidgets.QComboBox, "gate_type"),
        height_field=form.findChild(QtWidgets.QLineEdit, "gate_height"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
    )
    # For the duplicate-name check: the layer and the edited feature's id
    # (a new feature matches no stored gate, so all gates are compared)
    fields["layer"] = layer
    fields["fid"] = feature.id() if feature is not None else None
    # the .ui tooltip, shown again once the name is valid and unique
    fields["name_tooltip"] = fields["name_field"].toolTip()

    # Hide the instudy field
    fields["instudy"].setHidden(True)

    # Gate Type is a value map (PIER, REMOTE, CARGO) set in alaqs_config.py:
    # QGIS fills the combo box, shows the stored value and saves the choice.

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))
    fields["type_field"].currentTextChanged.connect(lambda: validate(fields))
    # QGIS resets the name box's style when it updates the field's
    # constraint status or shows / hides it (editing switched on or off
    # with the form open); validate again afterwards so the mark stays.
    name_wrapper = QgsEditorWidgetWrapper.fromWidget(fields["name_field"])
    if name_wrapper is not None:
        name_wrapper.constraintStatusChanged.connect(lambda *_: validate(fields))
        name_wrapper.constraintResultVisibleChanged.connect(lambda *_: validate(fields))

    # OK is enabled only while the form is valid: validate now, then on
    # every change
    validate(fields)


def validate(fields: dict):
    """
    This function validates that all of the required fields have been completed
    correctly. If they have, the attributes are committed to the feature.
    Otherwise an error message is displayed and the incorrect field is
    highlighted in red.
    """

    # Get the button box
    button_box = fields["button_box"]

    # Validate all fields
    results = [
        (fields["name_field"], validate_field(fields["name_field"], "str")),
        (fields["type_field"], validate_field(fields["type_field"], "str")),
        (fields["height_field"], validate_field(fields["height_field"], "float")),
    ]
    # after validate_field, which resets the style of a valid name
    if results[0][1] is not False:
        if not mark_duplicate_name(
            fields["name_field"], fields.get("layer"), fields.get("fid")
        ):
            fields["name_field"].setToolTip(fields.get("name_tooltip", ""))

    # OK enabled only when every field is valid
    update_ok_button(button_box, results, AlaqsLayerType.GATE)


def other_gates_with_name(layer, name: str, fid=None) -> list:
    """Ids of the gates other than `fid` whose Gate Name is `name`
    (stored and edit-buffer features, names compared after trimming)."""
    if layer is None or not name:
        return []
    request = QgsFeatureRequest().setFilterExpression(
        f'trim("gate_id") = {QgsExpression.quotedValue(name)}'
    )
    request.setFlags(QgsFeatureRequest.Flag.NoGeometry)
    request.setNoAttributes()
    return [f.id() for f in layer.getFeatures(request) if f.id() != fid]


def mark_duplicate_name(name_field, layer, fid=None) -> bool:
    """Colour the Gate Name box and set its tooltip when another gate has
    the same name. Advisory only: nothing is changed and OK is not
    affected. Returns True for a duplicate name."""
    name = name_field.text().strip()
    if not other_gates_with_name(layer, name, fid):
        return False
    name_field.setStyleSheet(DUPLICATE_NAME_STYLE)
    name_field.setToolTip(DUPLICATE_NAME_TOOLTIP)
    return True
