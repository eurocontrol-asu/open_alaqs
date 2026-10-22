from qgis.PyQt import QtWidgets

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.enums import AlaqsLayerType
from open_alaqs.openalaqsuitoolkit import (
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
        name_field=form.findChild(QtWidgets.QLineEdit, "taxiway_id"),
        speed_field=form.findChild(QtWidgets.QLineEdit, "speed"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
    )

    # Hide the instudy field
    fields["instudy"].setHidden(True)

    # No Time field: the calculation takes the taxiing time from the
    # taxiway length and the speed (Taxiway.py); the time column is unused.

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

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
        (fields["speed_field"], validate_field(fields["speed_field"], "float")),
    ]

    # OK enabled only when every field is valid
    update_ok_button(button_box, results, AlaqsLayerType.TAXIWAY)
