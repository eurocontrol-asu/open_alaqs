from qgis.PyQt import QtWidgets

from open_alaqs.core.alaqslogging import get_logger

logger = get_logger(__name__)


def form_open(form, layer, feature):
    logger.debug("This is the modified simple form")
    logger.debug(f"Layer {layer} and feature {feature}")
    logger.debug(f"Attributes of fields: {feature.fields().names()}")
    logger.debug(f"Attributes of feature: {feature.attributes()}")

    # Get all the fields from the form
    fields = dict(
        name_field=form.findChild(QtWidgets.QLineEdit, "building_id"),
        height_field=form.findChild(QtWidgets.QLineEdit, "height"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
    )

    # Hide the instudy field
    fields["instudy"].setHidden(True)

    # height not used in this ALAQS version
    fields["height_field"].setText("0")
    fields["height_field"].setEnabled(False)

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

    # Block the ok button (will be overwritten after validation)
    fields["button_box"].button(fields["button_box"].Ok).blockSignals(True)

    # Connect all QComboBoxes and the instudy checkbox on save
    def on_save():
        feature["instudy"] = str(int(fields["instudy"].isChecked()))

    fields["button_box"].accepted.connect(on_save)

    return form


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
        validate_field(fields["name_field"], "str"),
        validate_field(fields["height_field"], "float"),
    ]

    # Block signals if any of the fields is invalid
    button_box.button(button_box.Ok).blockSignals("False" in str(results))


def validate_field(ui_element, var_type):
    try:
        if var_type == "str":
            try:
                value = str(ui_element.currentText()).strip()
            except Exception:
                value = str(ui_element.text()).strip()
            if value == "":
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be a string")
                return False
            else:
                color_ui_background(ui_element, "white")
                return value

        elif var_type == "int":
            try:
                value = str(ui_element.currentText()).strip()
            except Exception:
                value = str(ui_element.text()).strip()
            try:
                if value == "" or value is None:
                    raise Exception()
                value = int(value)
                color_ui_background(ui_element, "white")
                return value
            except Exception:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be an integer")
                return False

        elif var_type == "float":
            try:
                value = str(ui_element.currentText()).strip()
            except Exception:
                value = str(ui_element.text()).strip()
            try:
                if value == "" or value is None:
                    raise Exception()
                value = float(value)
                color_ui_background(ui_element, "white")
                return value
            except Exception:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be a float")
                return False
    except Exception:
        return False


def color_ui_background(ui_element, color):
    if color == "red":
        ui_element.setStyleSheet("background-color: rgba(255, 107, 107, 150);")
    elif color == "white":
        ui_element.setStyleSheet("background-color: rgba(255, 255, 255, 255);")
    else:
        pass