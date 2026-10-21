from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.utils import OverrideCursor

from open_alaqs.alaqs_config import field_alias
from open_alaqs.core import alaqs, alaqsutils
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools import copert5
from open_alaqs.core.tools.copert5_utils import VEHICLE_CATEGORIES
from open_alaqs.enums import AlaqsLayerType
from open_alaqs.openalaqsuitoolkit import (
    add_combo_values,
    update_ok_button,
    validate_field,
)

logger = get_logger("open_alaqs.ui.ui_roadways")


# Keys of the `fields` dict built in form_open that are not column names,
# mapped to their column, so messages can use the field display names.
FIELD_COLUMNS = {
    "name_field": "roadway_id",
    "vehicle_year_field": "vehicle_year",
    "height_field": "height",
    "speed_field": "speed",
}


def display_name(field_key: str) -> str:
    """Display name (as on the form) of an entry of the `fields` dict."""
    return field_alias(AlaqsLayerType.ROADWAY, FIELD_COLUMNS.get(field_key, field_key))


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
        name_field=form.findChild(QtWidgets.QLineEdit, "roadway_id"),
        vehicle_year_field=form.findChild(QtWidgets.QLineEdit, "vehicle_year"),
        height_field=form.findChild(QtWidgets.QLineEdit, "height"),
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
        co_gm_km_field=form.findChild(QtWidgets.QLineEdit, "co_gm_km"),
        hc_gm_km_field=form.findChild(QtWidgets.QLineEdit, "hc_gm_km"),
        nox_gm_km_field=form.findChild(QtWidgets.QLineEdit, "nox_gm_km"),
        sox_gm_km_field=form.findChild(QtWidgets.QLineEdit, "sox_gm_km"),
        pm10_gm_km_field=form.findChild(QtWidgets.QLineEdit, "pm10_gm_km"),
        p1_gm_km_field=form.findChild(QtWidgets.QLineEdit, "p1_gm_km"),
        p2_gm_km_field=form.findChild(QtWidgets.QLineEdit, "p2_gm_km"),
        scenario_field=form.findChild(QtWidgets.QComboBox, "scenario"),
        method_field=form.findChild(QtWidgets.QLineEdit, "method"),
        recalculate=form.findChild(QtWidgets.QPushButton, "button_recalculate"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
    )

    # The In Study check box is bound to the instudy column by QGIS (CheckBox
    # widget, "1" / "0", set in alaqs_config.py): it shows the stored value
    # and QGIS saves what the user sets, so the form does not write it.

    # Seed the profiles
    populate_hourly_profiles(fields["hour_profile_field"])
    populate_daily_profiles(fields["daily_profile_field"])
    populate_monthly_profiles(fields["month_profile_field"])

    # Connect the emissions recalculation method
    fields["recalculate"].clicked.connect(lambda: recalculate_emissions(fields))

    # Disable various fields. The emission factors are filled in by
    # Recalculate only.
    fields["method_field"].setText("COPERT5")
    fields["method_field"].setEnabled(False)
    for pollutant in ("co", "hc", "nox", "sox", "pm10", "p1", "p2"):
        fields[f"{pollutant}_gm_km_field"].setEnabled(False)
    fields["scenario_field"].setEnabled(False)

    # Connect the comboboxes to validation
    fields["hour_profile_field"].currentTextChanged.connect(lambda: validate(fields))
    fields["daily_profile_field"].currentTextChanged.connect(lambda: validate(fields))
    fields["month_profile_field"].currentTextChanged.connect(lambda: validate(fields))

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

    # OK is enabled only while the form is valid: validate now, then on
    # every change
    validate(fields)

    return form


def recalculate_emissions(fields: dict):
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
                validation_errors.append(display_name(field_name))
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
            msg_box.exec()
            return False

        # Calculate the total
        fleet_percentage_total = sum([valid_fields[f] for f in fleet_percentage_fields])

        if fleet_percentage_total != 100:
            msg_box = QtWidgets.QMessageBox()
            msg_box.setText(
                "Fleet mix must be decimal values that total 100%. "
                f"Current sum is {fleet_percentage_total}%."
            )
            msg_box.exec()
            return False

        # Get the relevant validated fields
        name = valid_fields["name_field"]
        height = valid_fields["height_field"]
        speed = valid_fields["speed_field"]

        # Prepare the input for the roadway emission factors calculation method
        form_data = {
            "name": name,
            "height": height,
            "speed": speed,
            "parking": False,
        }
        for field_name in fleet_percentage_fields:
            form_data[field_name] = valid_fields[field_name]

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
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                emission_profile = copert5.roadway_emission_factors(
                    form_data, study_data
                )

        # Update the emission fields
        fields["co_gm_km_field"].setText(str(emission_profile["co_ef"]))
        fields["hc_gm_km_field"].setText(str(emission_profile["hc_ef"]))
        fields["nox_gm_km_field"].setText(str(emission_profile["nox_ef"]))
        fields["sox_gm_km_field"].setText(str(emission_profile["sox_ef"]))
        fields["pm10_gm_km_field"].setText(str(emission_profile["pm10_ef"]))
        fields["p1_gm_km_field"].setText(str(emission_profile["p1_ef"]))
        fields["p2_gm_km_field"].setText(str(emission_profile["p2_ef"]))

    except Exception as e:
        logger.error(str(e), exc_info=e)

        msg_box = QtWidgets.QMessageBox()
        msg_box.setText("Emissions could not be calculated: %s" % e)
        msg_box.exec()
        raise e

    return True


@catch_errors
def populate_hourly_profiles(field):
    """Add the study's hourly profiles missing from the list (profiles created
    after the study was opened). The list itself is a value map set when
    the study opens; QGIS shows the stored value and saves the choice."""
    profiles = alaqs.get_hourly_profiles() or []
    add_combo_values(field, ["default"] + [profile[1] for profile in profiles])


@catch_errors
def populate_daily_profiles(field):
    """Add the study's daily profiles missing from the list (profiles created
    after the study was opened). The list itself is a value map set when
    the study opens; QGIS shows the stored value and saves the choice."""
    profiles = alaqs.get_daily_profiles() or []
    add_combo_values(field, ["default"] + [profile[1] for profile in profiles])


@catch_errors
def populate_monthly_profiles(field):
    """Add the study's monthly profiles missing from the list (profiles created
    after the study was opened). The list itself is a value map set when
    the study opens; QGIS shows the stored value and saves the choice."""
    profiles = alaqs.get_monthly_profiles() or []
    add_combo_values(field, ["default"] + [profile[1] for profile in profiles])


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
        (
            fields["vehicle_year_field"],
            validate_field(fields["vehicle_year_field"], "int"),
        ),
        (fields["height_field"], validate_field(fields["height_field"], "float")),
        (fields["speed_field"], validate_field(fields["speed_field"], "float")),
        # validate_field(fields['distance_field'], "float"),
        (fields["pc_p_percentage"], validate_field(fields["pc_p_percentage"], "float")),
        (fields["pc_d_percentage"], validate_field(fields["pc_d_percentage"], "float")),
        (
            fields["lcv_p_percentage"],
            validate_field(fields["lcv_p_percentage"], "float"),
        ),
        (
            fields["lcv_d_percentage"],
            validate_field(fields["lcv_d_percentage"], "float"),
        ),
        (
            fields["hdt_p_percentage"],
            validate_field(fields["hdt_p_percentage"], "float"),
        ),
        (
            fields["hdt_d_percentage"],
            validate_field(fields["hdt_d_percentage"], "float"),
        ),
        (
            fields["motorcycle_p_percentage"],
            validate_field(fields["motorcycle_p_percentage"], "float"),
        ),
        (
            fields["bus_d_percentage"],
            validate_field(fields["bus_d_percentage"], "float"),
        ),
        (
            fields["hour_profile_field"],
            validate_field(fields["hour_profile_field"], "str"),
        ),
        (
            fields["daily_profile_field"],
            validate_field(fields["daily_profile_field"], "str"),
        ),
        (
            fields["month_profile_field"],
            validate_field(fields["month_profile_field"], "str"),
        ),
        (fields["co_gm_km_field"], validate_field(fields["co_gm_km_field"], "float")),
        (fields["hc_gm_km_field"], validate_field(fields["hc_gm_km_field"], "float")),
        (fields["nox_gm_km_field"], validate_field(fields["nox_gm_km_field"], "float")),
        (fields["sox_gm_km_field"], validate_field(fields["sox_gm_km_field"], "float")),
        (
            fields["pm10_gm_km_field"],
            validate_field(fields["pm10_gm_km_field"], "float"),
        ),
        (fields["p1_gm_km_field"], validate_field(fields["p1_gm_km_field"], "float")),
        (fields["p2_gm_km_field"], validate_field(fields["p2_gm_km_field"], "float")),
    ]

    # OK enabled only when every field is valid
    update_ok_button(button_box, results, AlaqsLayerType.ROADWAY)
