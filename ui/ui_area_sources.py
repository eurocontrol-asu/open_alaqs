from PyQt5 import QtWidgets

from open_alaqs.alaqs_core import alaqs, alaqsutils
from open_alaqs.alaqs_core.alaqslogging import get_logger

logger = get_logger(__name__)


def catch_errors(f):
    """
    Decorator to catch all errors when executing the function.
    This decorator catches errors and writes them to the log.

    :param f: function to execute
    :return:
    """

    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            alaqsutils.print_error(f.__name__, Exception, e)

    return wrapper


def form_open(form, layer, feature):
    logger.debug(f"This is the modified simple form")
    logger.debug(f"Layer {layer} and feature {feature}")
    logger.debug(f"Attributes of fields: {feature.fields().names()}")
    logger.debug(f"Attributes of feature: {feature.attributes()}")

    # Get all the fields from the form
    fields = dict(
        name_field=form.findChild(QtWidgets.QLineEdit, "source_id"),
        unit_field=form.findChild(QtWidgets.QLineEdit, "unit_year"),
        height_field=form.findChild(QtWidgets.QLineEdit, "height"),
        heat_flux_field=form.findChild(QtWidgets.QLineEdit, "heat_flux"),
        hour_profile_field=form.findChild(QtWidgets.QComboBox,
                                          "hourly_profile"),
        daily_profile_field=form.findChild(QtWidgets.QComboBox,
                                           "daily_profile"),
        month_profile_field=form.findChild(QtWidgets.QComboBox,
                                           "monthly_profile"),
        co_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "co_kg_unit"),
        hc_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "hc_kg_unit"),
        nox_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "nox_kg_unit"),
        sox_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "sox_kg_unit"),
        pm_total_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "pm_total_kg_unit"),
        p1_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "p1_kg_unit"),
        p2_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "p2_kg_unit"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy")
    )

    # Hide the instudy field
    fields['instudy'].setHidden(True)

    # Disable the height and heat flux fields
    fields['height_field'].setText('0')
    fields['height_field'].setEnabled(False)
    fields['heat_flux_field'].setText('0')
    fields['heat_flux_field'].setEnabled(False)

    # Seed the profiles
    populate_hourly_profiles(fields['hour_profile_field'])
    populate_daily_profiles(fields['daily_profile_field'])
    populate_monthly_profiles(fields['month_profile_field'])

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

    # Block the ok button (will be overwritten after validation)
    fields['button_box'].button(fields['button_box'].Ok).blockSignals(True)

    # Connect all QComboBoxes and the instudy checkbox on save
    def on_save():
        form.changeAttribute("hourly_profile",
                             fields['hour_profile_field'].currentText())
        form.changeAttribute("daily_profile",
                             fields['daily_profile_field'].currentText())
        form.changeAttribute("monthly_profile",
                             fields['month_profile_field'].currentText())
        feature["instudy"] = str(int(fields['instudy'].isChecked()))
    fields['button_box'].accepted.connect(on_save)


@catch_errors
def populate_hourly_profiles(field):
    # Make sure the field is empty
    field.clear()

    # Set the default field
    field.addItem("default")

    # Get the available hourly profiles
    hourly_profiles = alaqs.get_hourly_profiles()

    if (hourly_profiles is None) or (hourly_profiles == []):
        logger.debug("No hourly profiles were found.")
        return

    # Add all the hourly profiles to the list (except the default profile)
    for profile in hourly_profiles:
        if profile[1] != "default":
            field.addItem(profile[1])

    # Set the default category to 0 and make the list un-editable
    field.setCurrentIndex(0)
    field.setEditable(False)


@catch_errors
def populate_daily_profiles(field):
    # Make sure the field is empty
    field.clear()

    # Set the default field
    field.addItem("default")

    # Get the available daily profiles
    daily_profiles = alaqs.get_daily_profiles()

    if (daily_profiles is None) or (daily_profiles == []):
        logger.debug("No daily profiles were found.")
        return

    # Add all the daily profiles to the list (except the default profile)
    for profile in daily_profiles:
        if profile[1] != "default":
            field.addItem(profile[1])

    # Set the default category to 0 and make the list un-editable
    field.setCurrentIndex(0)
    field.setEditable(False)


@catch_errors
def populate_monthly_profiles(field):
    # Make sure the field is empty
    field.clear()

    # Set the default field
    field.addItem("default")

    # Get the available monthly profiles
    monthly_profiles = alaqs.get_monthly_profiles()

    if (monthly_profiles is None) or (monthly_profiles == []):
        logger.debug("No monthly profiles were found.")
        return

    # Add all the monthly profiles to the list (except the default profile)
    for profile in monthly_profiles:
        if profile[1] != "default":
            field.addItem(profile[1])

    # Set the default category to 0 and make the list un-editable
    field.setCurrentIndex(0)
    field.setEditable(False)


def validate(fields: dict):
    """
    This function validates that all of the required fields have been completed
    correctly. If they have, the attributes are committed to the feature.
    Otherwise an error message is displayed and the incorrect field is
    highlighted in red.
    """

    # Get the button box
    button_box = fields['button_box']

    # Validate all fields
    results = [
        validate_field(fields['name_field'], "str"),
        validate_field(fields['height_field'], "float"),
        validate_field(fields['heat_flux_field'], "float"),
        validate_field(fields['co_kg_unit_field'], "float"),
        validate_field(fields['hc_kg_unit_field'], "float"),
        validate_field(fields['nox_kg_unit_field'], "float"),
        validate_field(fields['sox_kg_unit_field'], "float"),
        validate_field(fields['pm_total_kg_unit_field'], "float"),
        validate_field(fields['p1_kg_unit_field'], "float"),
        validate_field(fields['p2_kg_unit_field'], "float")
    ]

    # Block signals if any of the fields is invalid
    button_box.button(button_box.Ok).blockSignals("False" in str(results))


def validate_field(ui_element, var_type):
    try:
        if var_type is "str":
            try:
                value = str(ui_element.currentText()).strip()
            except:
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
            except:
                value = str(ui_element.text()).strip()
            try:
                if value == "" or value is None:
                    raise Exception()
                value = int(value)
                color_ui_background(ui_element, "white")
                return value
            except:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be an integer")
                return False

        elif var_type is "float":
            try:
                value = str(ui_element.currentText()).strip()
            except:
                value = str(ui_element.text()).strip()
            try:
                if value == "" or value is None:
                    raise Exception()
                value = float(value)
                color_ui_background(ui_element, "white")
                return value
            except:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be a float")
                return False
    except:
        return False


def color_ui_background(ui_element, color):
    if color is "red":
        ui_element.setStyleSheet("background-color: rgba(255, 107, 107, 150);")
    elif color is "white":
        ui_element.setStyleSheet("background-color: rgba(255, 255, 255, 255);")
    else:
        pass