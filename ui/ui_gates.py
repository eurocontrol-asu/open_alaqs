from PyQt5 import QtWidgets

from open_alaqs.alaqs_core.alaqslogging import get_logger

logger = get_logger(__name__)


def run_once(f):
    """
    Decorator to make sure the function is executed only once.

    :param f: function to execute
    :return:
    """

    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper.has_run = True
            return f(*args, **kwargs)

    wrapper.has_run = False
    return wrapper


def form_open(form, layer, feature):
    logger.debug(f"This is the modified simple form")
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

    # Hide the instudy field
    fields["instudy"].setHidden(True)

    # Disable the height field
    fields["height_field"].setToolTip("Not implemented")
    fields["height_field"].setText("0")
    fields["height_field"].setEnabled(False)

    # Seed the combo boxes only once
    populate_combo_boxes(fields)

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))
    fields["type_field"].currentTextChanged.connect(lambda: validate(fields))

    # Block the ok button (will be overwritten after validation)
    fields["button_box"].button(fields["button_box"].Ok).blockSignals(True)

    # Connect the instudy checkbox on save
    def on_save():
        form.changeAttribute("gate_type", fields["type_field"].currentText())
        feature["instudy"] = str(int(fields["instudy"].isChecked()))

    fields["button_box"].accepted.connect(on_save)


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
        validate_field(fields["type_field"], "str"),
        validate_field(fields["height_field"], "float"),
    ]

    # Block signals if any of the fields is invalid
    button_box.button(button_box.Ok).blockSignals(
        ("False" in str(results)) or (results[1] not in ("PIER", "REMOTE", "CARGO"))
    )


def validate_field(ui_element, var_type):
    try:
        if var_type is "str":
            try:
                value = str(ui_element.currentText()).strip()
            except Exception:
                value = str(ui_element.text()).strip()
            if value is "":
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be a string")
                return False
            else:
                color_ui_background(ui_element, "white")
                return value

        elif var_type is "int":
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

        elif var_type is "float":
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
    if color is "red":
        ui_element.setStyleSheet("background-color: rgba(255, 107, 107, 150);")
    elif color is "white":
        ui_element.setStyleSheet("background-color: rgba(255, 255, 255, 255);")
    else:
        pass


@run_once
def populate_combo_boxes(fields: dict):
    fields["type_field"].addItem("PIER")
    fields["type_field"].addItem("REMOTE")
    fields["type_field"].addItem("CARGO")
