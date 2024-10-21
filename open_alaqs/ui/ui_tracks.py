from qgis.PyQt import QtWidgets

from open_alaqs.core import alaqs
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.utils.qt import populate_combobox
from open_alaqs.openalaqsuitoolkit import validate_field

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
        name_field=form.findChild(QtWidgets.QLineEdit, "track_id"),
        runway_field=form.findChild(QtWidgets.QComboBox, "runway"),
        arrdep_field=form.findChild(QtWidgets.QComboBox, "departure_arrival"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
    )

    # Hide the instudy field
    fields["instudy"].setHidden(True)

    # Seed the combo boxes
    populate_combo_boxes(fields)

    # Remove brackets from the departure/arrival field when it's already set
    try:

        # Get the current value of the feature
        current_feature_value = feature.attribute("departure_arrival")
        print(current_feature_value)

        # Get the current value of the form
        current_field_value = fields["arrdep_field"].currentText()

        # If the form value is with brackets, replace the value in the combobox
        if current_field_value == f"({current_feature_value})":
            # Set the value without brackets
            fields["arrdep_field"].setCurrentText(current_feature_value)
            # Get the index of the value with brackets
            arrdep_index = fields["arrdep_field"].findText(current_field_value)
            # Remove the value with brackets
            fields["arrdep_field"].removeItem(arrdep_index)
        else:
            arrdep_index = fields["arrdep_field"].findText(current_feature_value)
            fields["arrdep_field"].setCurrentIndex(arrdep_index)

    except KeyError:
        pass
    except Exception as e:
        raise e

    # Remove brackets from the runway field when it's already set
    try:

        # Get the current value of the feature
        current_feature_value = feature.attribute("runway")

        # Get the current value of the form
        current_field_value = fields["runway_field"].currentText()

        # If the form value is with brackets, replace the value in the combobox
        if current_field_value == f"({current_feature_value})":
            # Set the value without brackets
            fields["runway_field"].setCurrentText(current_feature_value)
            # Get the index of the value with brackets
            rwy_index = fields["runway_field"].findText(current_field_value)
            # Remove the value with brackets
            fields["runway_field"].removeItem(rwy_index)
        else:
            rwy_index = fields["runway_field"].findText(current_feature_value)
            fields["runway_field"].setCurrentIndex(rwy_index)

    except KeyError:
        pass
    except Exception as e:
        raise e

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))
        if isinstance(value, QtWidgets.QComboBox):
            fields[key].currentTextChanged.connect(lambda: validate(fields))

    # Block the ok button (will be overwritten after validation)
    fields["button_box"].button(fields["button_box"].Ok).blockSignals(True)

    # Connect all QComboBoxes and the instudy checkbox on save
    def on_save():
        form.changeAttribute("runway", fields["runway_field"].currentText())
        form.changeAttribute("departure_arrival", fields["arrdep_field"].currentText())
        feature["instudy"] = str(int(fields["instudy"].isChecked()))

    fields["button_box"].accepted.connect(on_save)


@run_once
def populate_combo_boxes(fields: dict):
    # Populate the arrival/departure field
    populate_combobox(fields["arrdep_field"], ["Arrival", "Departure"])

    runways = alaqs.get_runways()
    if runways is None or runways == []:
        msg_box = QtWidgets.QMessageBox()
        msg_box.setIcon(QtWidgets.QMessageBox.Critical)
        msg_box.setWindowTitle("Critical error")
        msg_box.setText("Please define your runways before creating tracks.")
        msg_box.exec_()
    else:

        runway_options = []

        for runway in runways:
            directions = runway["runway_id"].split("/")
            for direction in directions:
                runway_options.append(direction.strip())

        populate_combobox(fields["runway_field"], runway_options, add_empty=True)


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
        validate_field(fields["runway_field"], "str"),
        validate_field(fields["arrdep_field"], "str"),
    ]

    # Block signals if any of the fields is invalid
    button_box.button(button_box.Ok).blockSignals("False" in str(results))
