from qgis.PyQt import QtWidgets

from open_alaqs.core import alaqs, alaqsutils
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.enums import AlaqsLayerType
from open_alaqs.openalaqsuitoolkit import (
    add_combo_values,
    update_ok_button,
    validate_field,
)

logger = get_logger(__name__)

# Shown, never saved, when the selected emission factor has no unit
ACTIVITY_UNIT_PLACEHOLDER = "1000_m3 (legacy default)"


def activity_unit_text(activity_unit) -> str:
    """Text written into the Activity Unit field for an emission factor
    row: its unit, or an empty string when the row has none (the field
    then shows ACTIVITY_UNIT_PLACEHOLDER as placeholder text)."""
    if activity_unit is None:
        return ""
    return str(activity_unit).strip()


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
        # "Activity Unit" field (added in the point-sources v2 schema
        # migration, a per-source override of the EF row's unit). Filled in
        # from the selected EF row's `activity_unit` column by
        # `change_type_field`, editable. Legacy EF rows
        # have no unit; the field is then left empty and shows the
        # historical default "1000_m3 (legacy default)" as placeholder
        # text only, so that text is never saved.
        activity_unit=form.findChild(QtWidgets.QLineEdit, "activity_unit"),
        category=form.findChild(QtWidgets.QComboBox, "category"),
        point_type=form.findChild(QtWidgets.QComboBox, "point_type"),
        hour_profile=form.findChild(QtWidgets.QComboBox, "hour_profile"),
        daily_profile=form.findChild(QtWidgets.QComboBox, "daily_profile"),
        month_profile=form.findChild(QtWidgets.QComboBox, "month_profile"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
    )

    # The In Study check box is bound to the instudy column by QGIS (CheckBox
    # widget, "1" / "0", set in alaqs_config.py): it shows the stored value
    # and QGIS saves what the user sets, so the form does not write it.

    # The Activity Unit is filled in from the selected Type when the Type
    # changes and can be overridden per source (it is saved as typed). An
    # existing source keeps its stored unit: the Type is restored below
    # before the change handlers are connected.
    if fields["activity_unit"] is not None:
        fields["activity_unit"].setPlaceholderText(ACTIVITY_UNIT_PLACEHOLDER)

    # Category, Type and the profiles are value maps set in alaqs_config.py:
    # QGIS fills the combo boxes, shows the stored values (also when it
    # refreshes the form) and saves the choice. Profiles created after the
    # study was opened are added here.
    populate_hourly_profiles(fields["hour_profile"])
    populate_daily_profiles(fields["daily_profile"])
    populate_monthly_profiles(fields["month_profile"])

    # The Type list shows the types of the category shown, updated whenever
    # the category changes (also on a refresh), without touching the other
    # fields.
    filter_types(fields)
    fields["category"].currentIndexChanged.connect(lambda _i: filter_types(fields))

    # A category or type chosen by the user (activated, not a refresh)
    # fills in the type's defaults; a stored source keeps its values.
    fields["category"].activated.connect(lambda _i: category_chosen(fields))
    fields["point_type"].activated.connect(
        lambda _i: change_type_field(fields, fields["point_type"].currentText())
    )

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

    # OK is enabled only while the form is valid: validate now, then on
    # every change
    validate(fields)

    return form


def types_of_category(category_name: str) -> list[str]:
    """Descriptions of the emission factor rows of a category (by name)."""
    row = alaqs.get_point_category(category_name) if category_name else None
    if not row:
        return []
    return [t["description"] for t in alaqs.get_point_types(row["category"]) or []]


def filter_types(fields: dict) -> None:
    """Show in the Type list only the types of the selected category (the
    value map holds all types). The type shown stays visible."""
    combo = fields["point_type"]
    allowed = set(types_of_category(fields["category"].currentText().strip()))
    view = combo.view()
    for i in range(combo.count()):
        view.setRowHidden(
            i, combo.itemText(i) not in allowed and i != combo.currentIndex()
        )


@catch_errors
def category_chosen(fields: dict) -> None:
    """The user chose a category: select its first type and fill in that
    type's defaults; "Other" has no type and its parameters are typed in."""
    category_name = fields["category"].currentText().strip()
    combo = fields["point_type"]
    if category_name == "Other":
        combo.setCurrentIndex(-1)
        for key in ("height", "substance", "temperature", "diameter", "velocity"):
            fields[key].setEnabled(True)
        filter_types(fields)
        return
    types = types_of_category(category_name)
    index = combo.findText(types[0]) if types else -1
    combo.setCurrentIndex(index)
    filter_types(fields)
    change_type_field(fields, combo.currentText())


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
        if fields.get("activity_unit") is not None:
            fields["activity_unit"].setText("")

        return None

    # Extract the data
    data = alaqs.get_point_type(type_name)
    if not data:
        # Not a type name: keep the values
        return None

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

    # Activity unit (point-sources v2). Pulled from the selected EF
    # row's `activity_unit` column. Legacy rows from pre-v2 .alaqs
    # files have NULL here; the historical default was 1000 m^3 of
    # fuel gas. That default is only shown as placeholder text (set in
    # form_open), so the field stays empty and nothing is saved for it.
    activity_unit_field = fields.get("activity_unit")
    if activity_unit_field is not None:
        activity_unit_field.setText(activity_unit_text(data.get("activity_unit")))

    # Recommended temporal profiles (point-sources v2). When the EF
    # row carries `recommended_*_profile`, pre-select that profile in
    # each of the three profile dropdowns. The user can still
    # override; this only changes the default. Legacy EF rows have
    # NULL recommendations and we leave the existing selection alone.
    for field_key, ef_key in [
        ("hour_profile", "recommended_hour_profile"),
        ("daily_profile", "recommended_day_profile"),
        ("month_profile", "recommended_month_profile"),
    ]:
        recommended = data.get(ef_key)
        if not recommended:
            continue
        combo = fields.get(field_key)
        if combo is None:
            continue
        idx = combo.findText(recommended)
        if idx >= 0:
            combo.setCurrentIndex(idx)


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
        (fields["name"], validate_field(fields["name"], "str")),
        (fields["height"], validate_field(fields["height"], "float")),
        (fields["ops_year"], validate_field(fields["ops_year"], "float")),
        (fields["temperature"], validate_field(fields["temperature"], "float")),
        (fields["diameter"], validate_field(fields["diameter"], "float")),
        (fields["velocity"], validate_field(fields["velocity"], "float")),
        (fields["co_kg_k"], validate_field(fields["co_kg_k"], "float")),
        (fields["hc_kg_k"], validate_field(fields["hc_kg_k"], "float")),
        (fields["nox_kg_k"], validate_field(fields["nox_kg_k"], "float")),
        (fields["sox_kg_k"], validate_field(fields["sox_kg_k"], "float")),
        (fields["pm10_kg_k"], validate_field(fields["pm10_kg_k"], "float")),
        (fields["p1_kg_k"], validate_field(fields["p1_kg_k"], "float")),
        (fields["p2_kg_k"], validate_field(fields["p2_kg_k"], "float")),
    ]

    # OK enabled only when every field is valid
    update_ok_button(button_box, results, AlaqsLayerType.POINT_SOURCE)
