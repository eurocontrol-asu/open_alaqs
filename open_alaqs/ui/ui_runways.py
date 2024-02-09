import re

from qgis.PyQt import QtWidgets

from open_alaqs.core.alaqslogging import get_logger

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
    logger.debug("This is the modified simple form")
    logger.debug(f"Layer {layer} and feature {feature}")
    logger.debug(f"Attributes of fields: {feature.fields().names()}")
    logger.debug(f"Attributes of feature: {feature.attributes()}")

    # Get all the fields from the form
    fields = dict(
        first_runway_number=form.findChild(QtWidgets.QComboBox, "first_runway_number"),
        first_runway_letter=form.findChild(QtWidgets.QComboBox, "first_runway_letter"),
        second_runway_number=form.findChild(
            QtWidgets.QComboBox, "second_runway_number"
        ),
        second_runway_letter=form.findChild(
            QtWidgets.QComboBox, "second_runway_letter"
        ),
        name_field=form.findChild(QtWidgets.QLineEdit, "runway_id"),
        capacity_field=form.findChild(QtWidgets.QLineEdit, "capacity"),
        offset_field=form.findChild(QtWidgets.QLineEdit, "touchdown"),
        speed_field=form.findChild(QtWidgets.QLineEdit, "max_queue_speed"),
        time_field=form.findChild(QtWidgets.QLineEdit, "peak_queue_time"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
    )

    # Hide the instudy field
    fields["instudy"].setHidden(True)

    # Seed the runway numbers and letters once
    populate_runway_numbers_once(fields)
    populate_runway_letters_once(fields)

    # If name_field is set, update the first runway number and letter
    try:

        # Extract the runways from the name field
        runway_1, runway_2 = fields["name_field"].text().split("/")

        logger.debug(f"Runway direction detect: {runway_1}/{runway_2}")
        logger.debug("Setting the runway numbers and letters")

        # Find the runway number and letter
        regex_search = re.search(r"^(\d{2})([LCR]?)$", runway_1)
        runway_1_number = regex_search.group(1)
        runway_1_letter = regex_search.group(2)

        # Get the index
        number_index = fields["first_runway_number"].findText(runway_1_number)
        letter_index = fields["first_runway_letter"].findText(runway_1_letter)

        # Set the runway number and letter
        fields["first_runway_number"].setCurrentIndex(number_index)
        fields["first_runway_letter"].setCurrentIndex(letter_index)

        logger.debug(f"first_runway_number set to {runway_1_number}")
        logger.debug(f"first_runway_letter set to {runway_1_letter}")

    except ValueError:
        # Not enough values to unpack
        pass
    except Exception as e:
        raise e

    # Only allow the first runway number and letter to be changed
    fields["first_runway_number"].currentIndexChanged["QString"].connect(
        lambda v: first_runway_number_changed(fields, v)
    )
    fields["first_runway_letter"].currentIndexChanged["QString"].connect(
        lambda v: first_runway_letter_changed(fields, v)
    )
    fields["name_field"].setReadOnly(True)
    fields["second_runway_number"].setEnabled(False)
    fields["second_runway_letter"].setEnabled(False)

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

    # Block the ok button (will be overwritten after validation)
    fields["button_box"].button(fields["button_box"].Ok).blockSignals(True)

    # Connect the instudy checkbox on save
    def on_save():
        form.changeAttribute(
            "first_runway_number", fields["first_runway_number"].currentText()
        )
        form.changeAttribute(
            "first_runway_letter", fields["first_runway_letter"].currentText()
        )
        form.changeAttribute(
            "second_runway_number", fields["second_runway_number"].currentText()
        )
        form.changeAttribute(
            "second_runway_letter", fields["second_runway_letter"].currentText()
        )
        feature["instudy"] = str(int(fields["instudy"].isChecked()))

    fields["button_box"].accepted.connect(on_save)


@run_once
def populate_runway_numbers_once(fields: dict):
    populate_runway_numbers(fields["second_runway_number"])
    populate_runway_numbers(fields["first_runway_number"])


@run_once
def populate_runway_letters_once(fields: dict):
    populate_runway_letters(fields["second_runway_letter"])
    populate_runway_letters(fields["first_runway_letter"])


def populate_runway_numbers(combobox_object):
    for i in range(1, 37):
        combobox_object.addItem("%02d" % i)


def populate_runway_letters(combobox_object):
    combobox_object.addItem("")
    combobox_object.addItem("L")
    combobox_object.addItem("R")
    combobox_object.addItem("C")


def first_runway_number_changed(fields: dict, *args, **kwargs):
    """
    Function that's executed when the number of the first runway changes
    """

    # Get the current number
    first_runway_number_value = int(fields["first_runway_number"].currentText())

    # Calculate the opposite
    if first_runway_number_value <= 18:
        second_runway_number_value = first_runway_number_value + 18
    else:
        second_runway_number_value = first_runway_number_value - 18

    # Update the second number
    index = fields["second_runway_number"].findText("%02d" % second_runway_number_value)
    fields["second_runway_number"].setCurrentIndex(index)

    # Update the runway name
    create_runway_id(fields)


def first_runway_letter_changed(fields: dict, *args, **kwargs):
    """
    Function that's executed when the letter of the first runway changes
    """

    # Get the current letter
    first_runway_letter_value = str(fields["first_runway_letter"].currentText())

    # Calculate the opposite
    second_runway_letter_value = ""

    if first_runway_letter_value == "L":
        second_runway_letter_value = "R"
    elif first_runway_letter_value == "R":
        second_runway_letter_value = "L"
    elif first_runway_letter_value == "":
        second_runway_letter_value = ""
    elif first_runway_letter_value == "C":
        second_runway_letter_value = "C"

    # Update the second letter
    index = fields["second_runway_letter"].findText(second_runway_letter_value)
    fields["second_runway_letter"].setCurrentIndex(index)

    # Update the runway name
    create_runway_id(fields)


def create_runway_id(fields: dict, *args, **kwargs):
    """
    Function to update the runway name after the runway number or letter changes.
    """

    # Get the full name of the first runway
    runway_1_name = fields["first_runway_number"].currentText()
    runway_1_name += fields["first_runway_letter"].currentText()
    runway_2_name = fields["second_runway_number"].currentText()
    runway_2_name += fields["second_runway_letter"].currentText()

    # Merge the two runway names
    runway_string = f"{runway_1_name}/{runway_2_name}"

    # Set the name of the new runway combination
    fields["name_field"].setText(runway_string)


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
        validate_field(fields["capacity_field"], "float"),
        validate_field(fields["offset_field"], "float"),
        validate_field(fields["speed_field"], "float"),
        validate_field(fields["time_field"], "float"),
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
