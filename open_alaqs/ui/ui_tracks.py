from qgis.PyQt import QtWidgets

from open_alaqs.core import alaqs
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.enums import AlaqsLayerType
from open_alaqs.openalaqsuitoolkit import (
    add_combo_values,
    update_ok_button,
    validate_field,
)

logger = get_logger(__name__)


def form_open(form, layer, feature):
    logger.debug("This is the modified simple form")
    logger.debug(f"Layer {layer} and feature {feature}")
    logger.debug(f"Attributes of fields: {feature.fields().names()}")
    logger.debug(f"Attributes of feature: {feature.attributes()}")

    # Get all the fields from the form
    fields = dict(
        name_field=form.findChild(QtWidgets.QLineEdit, "track_id"),
        runway_field=form.findChild(QtWidgets.QComboBox, "runway"),
        arrdep_field=form.findChild(QtWidgets.QComboBox, "departure_arrival"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
    )

    # Hide the instudy field
    fields["instudy"].setHidden(True)

    # Runway Direction and Operation Type are value maps set in
    # alaqs_config.py: QGIS fills the combo boxes, shows the stored values
    # and saves the choice. Runways added after the study was opened are
    # added here.
    add_runway_directions(fields)

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))
        if isinstance(value, QtWidgets.QComboBox):
            fields[key].currentTextChanged.connect(lambda: validate(fields))

    # OK is enabled only while the form is valid: validate now, then on
    # every change
    validate(fields)


def add_runway_directions(fields: dict):
    """Add the directions of the study's runways to the Runway Direction
    list (the value map is built when the study opens)."""
    runways = alaqs.get_runways()
    if runways is None or runways == []:
        msg_box = QtWidgets.QMessageBox()
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("Critical error")
        msg_box.setText("Please define your runways before creating tracks.")
        msg_box.exec()
        return
    directions = []
    for runway in runways:
        directions += [d.strip() for d in str(runway["runway_id"]).split("/")]
    add_combo_values(fields["runway_field"], directions)


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
        (fields["runway_field"], validate_field(fields["runway_field"], "str")),
        (fields["arrdep_field"], validate_field(fields["arrdep_field"], "str")),
    ]

    # OK enabled only when every field is valid
    update_ok_button(button_box, results, AlaqsLayerType.TRACK)
