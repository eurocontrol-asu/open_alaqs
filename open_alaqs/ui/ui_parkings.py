from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.utils import OverrideCursor

from open_alaqs.core import alaqs, alaqsutils
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools import copert5
from open_alaqs.core.tools.copert5_utils import VEHICLE_CATEGORIES
from open_alaqs.openalaqsuitoolkit import validate_field

logger = get_logger("open_alaqs.ui.ui_parkings")


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
            alaqsutils.print_error(f.__name__, Exception, e, log=logger)

    return wrapper


def form_open(form, layer, feature):
    logger.debug("This is the modified simple form")
    logger.debug(f"Layer {layer} and feature {feature}")
    logger.debug(f"Attributes of fields: {feature.fields().names()}")
    logger.debug(f"Attributes of feature: {feature.attributes()}")

    fields = dict(
        name_field=form.findChild(QtWidgets.QLineEdit, "parking_id"),
        vehicle_year_field=form.findChild(QtWidgets.QLineEdit, "vehicle_year"),
        height_field=form.findChild(QtWidgets.QLineEdit, "height"),
        distance_field=form.findChild(QtWidgets.QLineEdit, "distance"),
        idle_time_field=form.findChild(QtWidgets.QLineEdit, "idle_time"),
        speed_field=form.findChild(QtWidgets.QLineEdit, "speed"),
        # The fleet mix fields
        pc_p_percentage=form.findChild(QtWidgets.QLineEdit, "pc_p_percentage"),
        pc_d_percentage=form.findChild(QtWidgets.QLineEdit, "pc_d_percentage"),
        lcv_p_percentage=form.findChild(QtWidgets.QLineEdit, "lcv_p_percentage"),
        lcv_d_percentage=form.findChild(QtWidgets.QLineEdit, "lcv_d_percentage"),
        hdt_p_percentage=form.findChild(QtWidgets.QLineEdit, "hdt_p_percentage"),
        hdt_d_percentage=form.findChild(QtWidgets.QLineEdit, "hdt_d_percentage"),
        motorcycle_p_percentage=form.findChild(
            QtWidgets.QLineEdit, "motorcycle_p_percentage"
        ),
        bus_d_percentage=form.findChild(QtWidgets.QLineEdit, "bus_d_percentage"),
        hour_profile_field=form.findChild(QtWidgets.QComboBox, "hour_profile"),
        daily_profile_field=form.findChild(QtWidgets.QComboBox, "daily_profile"),
        month_profile_field=form.findChild(QtWidgets.QComboBox, "month_profile"),
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
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
    )

    # Hide the instudy field
    fields["instudy"].setHidden(True)

    # Seed the profiles
    populate_hourly_profiles(fields["hour_profile_field"])
    populate_daily_profiles(fields["daily_profile_field"])
    populate_monthly_profiles(fields["month_profile_field"])

    # Connect the recalculate button with the recalculate_emissions method
    fields["recalculate"].clicked.connect(lambda: recalculate_emissions(fields, form))

    # Disable various fields
    fields["method_field"].setText("Open-ALAQS")
    fields["method_field"].setEnabled(False)

    # Connect the comboboxes to validation
    fields["hour_profile_field"].currentTextChanged.connect(lambda: validate(fields))
    fields["daily_profile_field"].currentTextChanged.connect(lambda: validate(fields))
    fields["month_profile_field"].currentTextChanged.connect(lambda: validate(fields))

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

    # Block the ok button (will be overwritten after validation)
    fields["button_box"].button(fields["button_box"].Ok).blockSignals(True)

    # Connect all QComboBoxes and the instudy checkbox on save
    def on_save():
        form.changeAttribute("hour_profile", fields["hour_profile_field"].currentText())
        form.changeAttribute(
            "daily_profile", fields["daily_profile_field"].currentText()
        )
        form.changeAttribute(
            "month_profile", fields["month_profile_field"].currentText()
        )
        feature["instudy"] = str(int(fields["instudy"].isChecked()))

    fields["button_box"].accepted.connect(on_save)


@catch_errors
def recalculate_emissions(fields: dict, form):
    try:

        # Set the fleet mix percentages
        fleet_percentage_fields = [
            "pc_p_percentage",
            "pc_d_percentage",
            "lcv_p_percentage",
            "lcv_d_percentage",
            "hdt_p_percentage",
            "hdt_d_percentage",
            "motorcycle_p_percentage",
            "bus_d_percentage",
        ]

        # Set the types per field (for validation)
        field_types = {
            "name_field": "str",
            "vehicle_year_field": "int",
            "height_field": "float",
            "speed_field": "float",
            "distance_field": "float",
            "idle_time_field": "float",
        }
        for field_name in fleet_percentage_fields:
            field_types[field_name] = "float"

        # Validate the input
        valid_fields = {}
        validation_errors = []
        for field_name, field_type in field_types.items():
            field_value = validate_field(fields[field_name], field_type)
            if isinstance(field_value, bool) and not field_value:
                logger.error(
                    f"{field_name} should be of type {field_type}, "
                    f"the current value is {field_value}"
                )
                validation_errors.append(field_name)
            else:
                valid_fields[field_name] = field_value
        if validation_errors:
            msg = (
                f"Please complete all fields first. The following "
                f"{len(validation_errors)} fields are incomplete or "
                f"incorrect:\n- " + ("\n- ".join(validation_errors))
            )
            msg_box = QtWidgets.QMessageBox()
            msg_box.setText(msg)
            msg_box.exec_()
            return False

        # Calculate the total
        fleet_percentage_total = sum(
            [float(fields[f].text()) for f in fleet_percentage_fields]
        )

        if fleet_percentage_total != 100:
            msg_box = QtWidgets.QMessageBox()
            msg_box.setText(
                "Fleet mix must be decimal values that total 100%. "
                f"Current sum is {fleet_percentage_total}%."
            )
            msg_box.exec_()
            return False

        # Get the relevant validated fields
        name = valid_fields["name_field"]
        vehicle_year = valid_fields["vehicle_year_field"]
        height = valid_fields["height_field"]
        speed = valid_fields["speed_field"]
        travel_distance = valid_fields["distance_field"]
        idle_time = valid_fields["idle_time_field"]

        # Prepare the input for the roadway emission factors calculation method
        form_data = {
            "name": name,
            "vehicle_year": vehicle_year,
            "height": height,
            "speed": speed,
            "idle_time": float(idle_time),
            "travel_distance": float(travel_distance),
            "parking": True,
        }
        for field_name in fleet_percentage_fields:
            form_data[field_name] = float(fields[field_name].text())

        # Get the study data for additional information needed
        study_data = alaqs.load_study_setup()

        # Get the roadway method
        roadway_method = study_data["roadway_method"]

        # Get the roadway country and fleet year
        roadway_country = study_data["roadway_country"]
        roadway_fleet_year = study_data["roadway_fleet_year"]

        # Get the Euro standards
        euro_standards = alaqs.get_roadway_euro_standards(
            roadway_country, roadway_fleet_year
        )

        # Log the Euro standards
        val = "\n\tEuro Standards:"
        for vehicle_category, euro_standard in sorted(euro_standards.items()):
            val += f"\n\t\t{vehicle_category} : {euro_standard}"
        logger.info(val)

        for short_vehicle_category, vehicle_category in VEHICLE_CATEGORIES.items():
            form_data[f"{short_vehicle_category}_euro_standard"] = euro_standards[
                vehicle_category
            ]

        # Calculate emissions according to the ALAQS method
        emission_profile = {}
        if roadway_method == "COPERT 5":
            with OverrideCursor(Qt.WaitCursor):
                emission_profile = copert5.roadway_emission_factors(
                    form_data, study_data
                )

        # Update the emission fields
        fields["co_gm_vh_field"].setText(str(emission_profile["co_ef"]))
        fields["hc_gm_vh_field"].setText(str(emission_profile["hc_ef"]))
        fields["nox_gm_vh_field"].setText(str(emission_profile["nox_ef"]))
        fields["sox_gm_vh_field"].setText(str(emission_profile["sox_ef"]))
        fields["pm10_gm_vh_field"].setText(str(emission_profile["pm10_ef"]))
        fields["p1_gm_vh_field"].setText(str(emission_profile["p1_ef"]))
        fields["p2_gm_vh_field"].setText(str(emission_profile["p2_ef"]))

    except Exception as e:
        logger.error(str(e), exc_info=e)

        msg_box = QtWidgets.QMessageBox()
        msg_box.setText("Emissions could not be calculated: %s" % e)
        msg_box.exec_()
        raise e


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
        validate_field(fields["vehicle_year_field"], "int"),
        validate_field(fields["height_field"], "float"),
        validate_field(fields["speed_field"], "float"),
        validate_field(fields["distance_field"], "float"),
        validate_field(fields["idle_time_field"], "float"),
        validate_field(fields["pc_p_percentage"], "float"),
        validate_field(fields["pc_d_percentage"], "float"),
        validate_field(fields["lcv_p_percentage"], "float"),
        validate_field(fields["lcv_d_percentage"], "float"),
        validate_field(fields["hdt_p_percentage"], "float"),
        validate_field(fields["hdt_d_percentage"], "float"),
        validate_field(fields["motorcycle_p_percentage"], "float"),
        validate_field(fields["bus_d_percentage"], "float"),
        validate_field(fields["hour_profile_field"], "str"),
        validate_field(fields["daily_profile_field"], "str"),
        validate_field(fields["month_profile_field"], "str"),
        validate_field(fields["co_gm_vh_field"], "float"),
        validate_field(fields["hc_gm_vh_field"], "float"),
        validate_field(fields["nox_gm_vh_field"], "float"),
        validate_field(fields["sox_gm_vh_field"], "float"),
        validate_field(fields["pm10_gm_vh_field"], "float"),
        validate_field(fields["p1_gm_vh_field"], "float"),
        validate_field(fields["p2_gm_vh_field"], "float"),
    ]

    # Block signals if any of the fields is invalid
    button_box.button(button_box.Ok).blockSignals("False" in str(results))
