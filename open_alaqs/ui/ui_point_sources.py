from qgis.PyQt import QtWidgets

from open_alaqs.core import alaqs, alaqsutils
from open_alaqs.core.alaqslogging import get_logger
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
    logger.debug("This is the modified simple form")
    logger.debug(f"Layer {layer} and feature {feature}")
    logger.debug(f"Attributes of fields: {feature.fields().names()}")
    logger.debug(f"Attributes of feature: {feature.attributes()}")

    # Get all the fields from the form
    fields = dict(
        name=form.findChild(QtWidgets.QLineEdit, "source_id"),
        height=form.findChild(QtWidgets.QLineEdit, "height"),
        co_kg_k=form.findChild(QtWidgets.QLineEdit, "co_kg_k"),
        hc_kg_k=form.findChild(QtWidgets.QLineEdit, "hc_kg_k"),
        nox_kg_k=form.findChild(QtWidgets.QLineEdit, "nox_kg_k"),
        sox_kg_k=form.findChild(QtWidgets.QLineEdit, "sox_kg_k"),
        pm10_kg_k=form.findChild(QtWidgets.QLineEdit, "pm10_kg_k"),
        p1_kg_k=form.findChild(QtWidgets.QLineEdit, "p1_kg_k"),
        p2_kg_k=form.findChild(QtWidgets.QLineEdit, "p2_kg_k"),
        substance=form.findChild(QtWidgets.QLineEdit, "substance"),
        temperature=form.findChild(QtWidgets.QLineEdit, "temperature"),
        diameter=form.findChild(QtWidgets.QLineEdit, "diameter"),
        velocity=form.findChild(QtWidgets.QLineEdit, "velocity"),
        ops_year=form.findChild(QtWidgets.QLineEdit, "ops_year"),
        category=form.findChild(QtWidgets.QComboBox, "category"),
        type=form.findChild(QtWidgets.QComboBox, "type"),
        hour_profile=form.findChild(QtWidgets.QComboBox, "hour_profile"),
        daily_profile=form.findChild(QtWidgets.QComboBox, "daily_profile"),
        month_profile=form.findChild(QtWidgets.QComboBox, "month_profile"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
    )

    # Hide the instudy field
    fields["instudy"].setHidden(True)

    # Seed the category field once
    populate_categories_once(fields["category"])

    # Seed the profiles
    populate_hourly_profiles(fields["hour_profile"])
    populate_daily_profiles(fields["daily_profile"])
    populate_monthly_profiles(fields["month_profile"])

    # Seed the type field if the category field changes
    fields["category"].currentTextChanged.connect(
        lambda v: change_category_field(fields, v)
    )

    # Set all fields to default if the type field changes
    fields["type"].currentTextChanged.connect(lambda v: change_type_field(fields, v))

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

    # Block the ok button (will be overwritten after validation)
    fields["button_box"].button(fields["button_box"].Ok).blockSignals(True)

    # Connect all QComboBoxes and the instudy checkbox on save
    def on_save():
        form.changeAttribute("category", fields["category"].currentText())
        form.changeAttribute("type", fields["type"].currentText())
        form.changeAttribute("hour_profile", fields["hour_profile"].currentText())
        form.changeAttribute("daily_profile", fields["daily_profile"].currentText())
        form.changeAttribute("month_profile", fields["month_profile"].currentText())
        feature["instudy"] = str(int(fields["instudy"].isChecked()))

    fields["button_box"].accepted.connect(on_save)

    return form


@run_once
def populate_categories_once(field):
    """
    Populate the categories fields only once
    """

    # Make sure the field is empty
    field.clear()
    field.addItem(None)

    # Get the available categories
    categories = alaqs.get_point_categories()

    if (categories is None) or (categories == []):
        logger.debug("No point source categories were found.")
        return

    # Add all categories to the list
    for category in categories:
        field.addItem(category["category_name"])

    # Set the default category to 0
    field.setCurrentIndex(0)

    # Make the list un-editable
    field.setEditable(False)


@catch_errors
def change_category_field(fields: dict, category: str):
    """
    Function that's executed when the point source category changes
    """

    # Get the selected category name
    category_name = category.strip()

    if category_name == "Other":
        # Edit the form fields
        fields["type"].clear()
        fields["type"].addItem("")

        fields["height"].setEnabled(True)
        fields["substance"].setEnabled(True)
        fields["temperature"].setEnabled(True)
        fields["diameter"].setEnabled(True)
        fields["velocity"].setEnabled(True)

        return

    if category_name == "":
        # Edit the form fields
        fields["type"].clear()
        fields["height"].setText("")
        fields["temperature"].setText("")
        fields["diameter"].setText("")
        fields["velocity"].setText("")
        fields["substance"].setText("")

        return

    category = alaqs.get_point_category(category_name)
    category_types = alaqs.get_point_types(category["category"])

    # Add all category types to the list
    fields["type"].clear()
    for category_type in category_types:
        fields["type"].addItem(category_type["description"])


@catch_errors
def change_type_field(fields: dict, type_name: str):
    if type_name == "":
        # Edit the form fields
        fields["height"].setText("")
        fields["temperature"].setText("")
        fields["diameter"].setText("")
        fields["velocity"].setText("")
        fields["substance"].setText("")
        fields["co_kg_k"].setText("")
        fields["hc_kg_k"].setText("")
        fields["nox_kg_k"].setText("")
        fields["sox_kg_k"].setText("")
        fields["pm10_kg_k"].setText("")
        fields["p1_kg_k"].setText("")
        fields["p2_kg_k"].setText("")

        return None

    # Extract the data
    data = alaqs.get_point_type(type_name)

    # Edit the form fields
    fields["height"].setText(str(data["z"]))
    fields["temperature"].setText(str(data["temperature"]))
    fields["diameter"].setText(str(data["diameter"]))
    fields["velocity"].setText(str(data["velocity"]))

    if data["SUBSTANCE"] == 1:
        fields["substance"].setText("Solid")
    elif data["SUBSTANCE"] == 2:
        fields["substance"].setText("Liquid")
    elif data["SUBSTANCE"] == 3:
        fields["substance"].setText("Gas")
    else:
        raise Exception("Substance could not be identified for this point type.")

    fields["co_kg_k"].setText(str(data["co_kg_k"]))
    fields["hc_kg_k"].setText(str(data["hc_kg_k"]))
    fields["nox_kg_k"].setText(str(data["nox_kg_k"]))
    fields["sox_kg_k"].setText(str(data["sox_kg_k"]))
    fields["pm10_kg_k"].setText(str(data["particulate_kg_k"]))
    fields["p1_kg_k"].setText(str(data["p1_kg_k"]))
    fields["p2_kg_k"].setText(str(data["p2_kg_k"]))


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
    button_box = fields["button_box"]

    # Validate all fields
    results = [
        validate_field(fields["name"], "str"),
        validate_field(fields["height"], "float"),
        validate_field(fields["ops_year"], "float"),
        validate_field(fields["temperature"], "float"),
        validate_field(fields["diameter"], "float"),
        validate_field(fields["velocity"], "float"),
        validate_field(fields["co_kg_k"], "float"),
        validate_field(fields["hc_kg_k"], "float"),
        validate_field(fields["nox_kg_k"], "float"),
        validate_field(fields["sox_kg_k"], "float"),
        validate_field(fields["pm10_kg_k"], "float"),
        validate_field(fields["p1_kg_k"], "float"),
        validate_field(fields["p2_kg_k"], "float"),
    ]

    # Block signals if any of the fields is invalid
    button_box.button(button_box.Ok).blockSignals("False" in str(results))
