from PyQt5 import QtCore, QtWidgets

from open_alaqs.alaqs_core import alaqs
from open_alaqs.alaqs_core import alaqsutils
from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.tools.lib_alaqs_method import \
    roadway_emission_factors_alaqs_method

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
        name_field=form.findChild(QtWidgets.QLineEdit, "parking_id"),
        height_field=form.findChild(QtWidgets.QLineEdit, "height"),
        distance_field=form.findChild(QtWidgets.QLineEdit, "distance"),
        idle_time_field=form.findChild(QtWidgets.QLineEdit, "idle_time"),
        park_time_field=form.findChild(QtWidgets.QLineEdit, "park_time"),
        vehicle_light_field=form.findChild(QtWidgets.QLineEdit,
                                           "vehicle_light"),
        vehicle_medium_field=form.findChild(QtWidgets.QLineEdit,
                                            "vehicle_medium"),
        vehicle_heavy_field=form.findChild(QtWidgets.QLineEdit,
                                           "vehicle_heavy"),
        vehicle_year_field=form.findChild(QtWidgets.QLineEdit, "vehicle_year"),
        speed_field=form.findChild(QtWidgets.QLineEdit, "speed"),
        hour_profile_field=form.findChild(QtWidgets.QComboBox, "hour_profile"),
        daily_profile_field=form.findChild(QtWidgets.QComboBox,
                                           "daily_profile"),
        month_profile_field=form.findChild(QtWidgets.QComboBox,
                                           "month_profile"),
        co_gm_vh_field=form.findChild(QtWidgets.QLineEdit, "co_gm_vh"),
        hc_gm_vh_field=form.findChild(QtWidgets.QLineEdit, "hc_gm_vh"),
        nox_gm_vh_field=form.findChild(QtWidgets.QLineEdit, "nox_gm_vh"),
        sox_gm_vh_field=form.findChild(QtWidgets.QLineEdit, "sox_gm_vh"),
        pm10_gm_vh_field=form.findChild(QtWidgets.QLineEdit, "pm10_gm_vh"),
        p1_gm_vh_field=form.findChild(QtWidgets.QLineEdit, "p1_gm_vh"),
        p2_gm_vh_field=form.findChild(QtWidgets.QLineEdit, "p2_gm_vh"),
        method_field=form.findChild(QtWidgets.QLineEdit, "method"),
        recalculate=form.findChild(QtWidgets.QPushButton, "button_recalculate"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy")
    )

    # Disable method, height and park time fields
    fields['method_field'].setText("Open-ALAQS")
    fields['method_field'].setEnabled(False)
    fields['height_field'].setText("0")
    fields['height_field'].setEnabled(False)
    fields['park_time_field'].setText("0")
    fields['park_time_field'].setEnabled(False)

    # Seed the profiles
    populate_hourly_profiles(fields['hour_profile_field'])
    populate_daily_profiles(fields['daily_profile_field'])
    populate_monthly_profiles(fields['month_profile_field'])

    # Connect the recalculate button with the recalculate_emissions method
    fields['recalculate'].clicked.connect(lambda: recalculate_emissions(fields, form))

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

    # Block the ok button (will be overwritten after validation)
    fields['button_box'].button(fields['button_box'].Ok).blockSignals(True)

    # Connect the instudy checkbox on save
    def on_save():
        form.changeAttribute("hour_profile", fields['hour_profile_field'].currentText())
        form.changeAttribute("daily_profile", fields['daily_profile_field'].currentText())
        form.changeAttribute("month_profile", fields['month_profile_field'].currentText())
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


def recalculate_emissions(fields, form):
    try:
        # Validate all relevant fields
        name = validate_field(fields['name_field'], "str")
        vehicle_year = validate_field(fields['vehicle_year_field'], "int")
        height = validate_field(fields['height_field'], "float")
        speed = validate_field(fields['speed_field'], "float")
        travel_distance = validate_field(fields['distance_field'], "float")
        idle_time = validate_field(fields['idle_time_field'], "float")
        park_time = validate_field(fields['park_time_field'], "float")
        vehicle_light = validate_field(fields['vehicle_light_field'], "float")
        vehicle_medium = validate_field(fields['vehicle_medium_field'], "float")
        vehicle_heavy = validate_field(fields['vehicle_heavy_field'], "float")
        method = str(fields['method_field'].text())

        if name is False or vehicle_year is False or height is False or speed is False or vehicle_light is False or \
                vehicle_medium is False or vehicle_heavy is False or method is False or \
                travel_distance is False or idle_time is False or park_time is False:
            msg_box = QtWidgets.QMessageBox()
            msg_box.setText("Please complete all fields first")
            msg_box.exec_()
            return False

        # Put all the values in a dictionary
        form_data_dict = dict()
        form_data_dict['name'] = name
        form_data_dict['vehicle_year'] = vehicle_year
        form_data_dict['height'] = height
        form_data_dict['speed'] = speed
        form_data_dict['vehicle_light'] = float(vehicle_light)
        form_data_dict['vehicle_medium'] = float(vehicle_medium)
        form_data_dict['vehicle_heavy'] = float(vehicle_heavy)
        form_data_dict['idle_time'] = float(idle_time)
        form_data_dict['park_time'] = float(park_time)
        form_data_dict['travel_distance'] = float(travel_distance)
        form_data_dict['parking'] = True

        # Check if percentages add up to 100
        vl = float(fields['vehicle_light_field'].text())
        vm = float(fields['vehicle_medium_field'].text())
        vh = float(fields['vehicle_heavy_field'].text())
        if (vl + vm + vh) != 100:
            QtWidgets.QMessageBox().warning(form, "Error",
                                            "Fleet mix must be decimal values that total 100%",
                                            QtWidgets.QMessageBox.Cancel)
            return False

        emission_profile = None
        if method == "Open-ALAQS":
            # Calculate emissions according to the ALAQS method
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            emission_profile = roadway_emission_factors_alaqs_method(
                form_data_dict)
            QtWidgets.QApplication.restoreOverrideCursor()

        # Update the emission fields
        fields['co_gm_vh_field'].setText(str(emission_profile['co_ef']))
        fields['hc_gm_vh_field'].setText(str(emission_profile['hc_ef']))
        fields['nox_gm_vh_field'].setText(str(emission_profile['nox_ef']))
        fields['sox_gm_vh_field'].setText(str(emission_profile['sox_ef']))
        fields['pm10_gm_vh_field'].setText(str(emission_profile['pm10_ef']))
        fields['p1_gm_vh_field'].setText(str(emission_profile['p1_ef']))
        fields['p2_gm_vh_field'].setText(str(emission_profile['p2_ef']))

    except Exception as e:
        msg_box = QtWidgets.QMessageBox()
        msg_box.setText("Emissions could not be calculated: %s" % e)
        msg_box.exec_()
        error = alaqsutils.print_error(populate_hourly_profiles.__name__,
                                       Exception, e)
        return error


def validate(fields):
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
        validate_field(fields['vehicle_year_field'], "int"),
        validate_field(fields['height_field'], "float"),
        validate_field(fields['speed_field'], "float"),
        validate_field(fields['distance_field'], "float"),
        validate_field(fields['idle_time_field'], "float"),
        validate_field(fields['park_time_field'], "float"),
        validate_field(fields['vehicle_light_field'], "float"),
        validate_field(fields['vehicle_medium_field'], "float"),
        validate_field(fields['vehicle_heavy_field'], "float"),
        validate_field(fields['co_gm_vh_field'], "float"),
        validate_field(fields['hc_gm_vh_field'], "float"),
        validate_field(fields['nox_gm_vh_field'], "float"),
        validate_field(fields['sox_gm_vh_field'], "float"),
        validate_field(fields['pm10_gm_vh_field'], "float"),
        validate_field(fields['p1_gm_vh_field'], "float"),
        validate_field(fields['p2_gm_vh_field'], "float")
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
