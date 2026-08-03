from qgis.PyQt import QtWidgets

from open_alaqs.core import alaqs, alaqsutils
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.openalaqsuitoolkit import validate_field
from open_alaqs.ui._area_sources_helpers import (
    seed_is_test_site_from_feature,
    write_is_test_site_to_feature,
)

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


def _open_load_events_dialog(form, fields, feature):
    """Launch OpenAlaqsImportEngineTestEvents scoped to the current source.

    Called from the "Load engine test events CSV..." button on the area
    source form. Discovers the currently-loaded project's DB path via
    ``ProjectDatabase().path``, reads the source_id from the form's
    ``name_field`` (which is the ``source_id`` line edit — the same value
    that will be written to the feature on save), and passes both into
    the dialog.

    Refuses if:
      * the source_id field is empty (nothing to scope to yet), or
      * ProjectDatabase().path returns nothing (unlikely in the QGIS
        flow, but defensive).
    """
    from qgis.PyQt.QtWidgets import QMessageBox

    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.openalaqsdialog import OpenAlaqsImportEngineTestEvents

    source_id = (fields["name_field"].text() or "").strip()
    if not source_id:
        QMessageBox.warning(
            form,
            "Missing source name",
            "Enter a Source Name before loading engine test events. "
            "The events need to be tied to this source's identifier.",
        )
        return

    try:
        db_path = ProjectDatabase().path
    except Exception:
        db_path = None
    if not db_path:
        QMessageBox.warning(
            form,
            "No project loaded",
            "The currently-loaded ALAQS project could not be found. "
            "Save the study before loading engine test events.",
        )
        return

    dialog = OpenAlaqsImportEngineTestEvents(
        iface=None, database_path=db_path, source_id=source_id
    )
    dialog.exec()


def form_open(form, layer, feature):
    logger.debug("This is the modified simple form")
    logger.debug(f"Layer {layer} and feature {feature}")
    logger.debug(f"Attributes of fields: {feature.fields().names()}")
    logger.debug(f"Attributes of feature: {feature.attributes()}")

    # Get all the fields from the form
    fields = dict(
        name_field=form.findChild(QtWidgets.QLineEdit, "source_id"),
        unit_field=form.findChild(QtWidgets.QLineEdit, "unit_year"),
        height_field=form.findChild(QtWidgets.QLineEdit, "height"),
        heat_flux_field=form.findChild(QtWidgets.QLineEdit, "heat_flux"),
        hour_profile_field=form.findChild(QtWidgets.QComboBox, "hourly_profile"),
        daily_profile_field=form.findChild(QtWidgets.QComboBox, "daily_profile"),
        month_profile_field=form.findChild(QtWidgets.QComboBox, "monthly_profile"),
        co_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "co_kg_unit"),
        hc_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "hc_kg_unit"),
        nox_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "nox_kg_unit"),
        sox_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "sox_kg_unit"),
        pm10_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "pm10_kg_unit"),
        p1_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "p1_kg_unit"),
        p2_kg_unit_field=form.findChild(QtWidgets.QLineEdit, "p2_kg_unit"),
        button_box=form.findChild(QtWidgets.QDialogButtonBox, "buttonBox"),
        instudy=form.findChild(QtWidgets.QCheckBox, "instudy"),
        is_test_site=form.findChild(QtWidgets.QCheckBox, "is_test_site"),
        load_events_csv=form.findChild(QtWidgets.QPushButton, "load_events_csv"),
    )

    # Hide the instudy field
    fields["instudy"].setHidden(True)

    # Seed the is_test_site checkbox from the feature. Values arrive as
    # TEXT '1' / '0' (matching the DB), NULL (from ALTER TABLE ADD COLUMN
    # on migrated projects), or absent entirely (pre-v1b schema — the
    # widget still exists on the form but has nothing to read).
    seed_is_test_site_from_feature(fields["is_test_site"], feature)

    # Wire the "Load engine test events CSV..." button. It is enabled
    # only when the source is flagged as a test site. Clicking it opens
    # the OpenAlaqsImportEngineTestEvents dialog scoped to this source.
    if fields["load_events_csv"] is not None:
        fields["load_events_csv"].setEnabled(fields["is_test_site"].isChecked())
        fields["is_test_site"].toggled.connect(fields["load_events_csv"].setEnabled)
        fields["load_events_csv"].clicked.connect(
            lambda: _open_load_events_dialog(form, fields, feature)
        )

    # Re-run validation whenever the test-site toggle changes: the set
    # of required fields differs between test-site and regular modes.
    fields["is_test_site"].toggled.connect(lambda _checked: validate(fields))

    # Disable heat flux fields
    fields["heat_flux_field"].setText("0")
    fields["heat_flux_field"].setEnabled(False)

    # Seed the profiles
    populate_hourly_profiles(fields["hour_profile_field"])
    populate_daily_profiles(fields["daily_profile_field"])
    populate_monthly_profiles(fields["month_profile_field"])

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

    # Block the ok button (will be overwritten after validation)
    fields["button_box"].button(fields["button_box"].StandardButton.Ok).blockSignals(
        True
    )

    # Connect all QComboBoxes and the instudy checkbox on save
    def on_save():
        form.changeAttribute(
            "hourly_profile", fields["hour_profile_field"].currentText()
        )
        form.changeAttribute(
            "daily_profile", fields["daily_profile_field"].currentText()
        )
        form.changeAttribute(
            "monthly_profile", fields["month_profile_field"].currentText()
        )
        feature["instudy"] = str(int(fields["instudy"].isChecked()))
        # is_test_site as TEXT '1' / '0' to match the DB column type
        # (see EngineTestEvents.py schema). AreaSources.isTestSite()
        # reads by string comparison.
        write_is_test_site_to_feature(fields["is_test_site"], feature)

        # For test sites, the compute path ignores unit_year and the
        # *_kg_unit rate columns. Auto-fill "0" on any that the user
        # left blank so the DB stores a valid numeric rather than NULL
        # (which some downstream code doesn't handle). Users who care
        # can override these values, but there's no reason to force
        # them to.
        if fields["is_test_site"].isChecked():
            fields_to_zero_fill = [
                "unit_field",
                "co_kg_unit_field",
                "hc_kg_unit_field",
                "nox_kg_unit_field",
                "sox_kg_unit_field",
                "pm10_kg_unit_field",
                "p1_kg_unit_field",
                "p2_kg_unit_field",
            ]
            for f_name in fields_to_zero_fill:
                widget = fields.get(f_name)
                if widget is not None and not widget.text().strip():
                    widget.setText("0")

    fields["button_box"].accepted.connect(on_save)


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

    When the "Engine test site" checkbox is ticked, the emissions and
    unit-rate fields are irrelevant (the compute path reads events from
    ``engine_test_events`` and ignores the ``*_kg_unit`` columns). Those
    fields are skipped in validation so the user can save the source
    without filling in numbers that will never be used. ``on_save()``
    auto-fills them with ``"0"`` so the DB stores something valid.

    Source name, height, and heat flux are validated regardless — they
    matter for both regular area sources AND test sites (height for
    dispersion positioning, name for the source_id, heat flux is
    already 0 and disabled).
    """

    # Get the button box
    button_box = fields["button_box"]

    # Fields validated for every area source.
    results = [
        validate_field(fields["name_field"], "str"),
        validate_field(fields["height_field"], "float"),
        validate_field(fields["heat_flux_field"], "float"),
    ]

    # Fields validated only for regular area sources. Skipped when the
    # source is a test site.
    is_test_site = (
        fields.get("is_test_site") is not None and fields["is_test_site"].isChecked()
    )
    if not is_test_site:
        results.extend(
            [
                validate_field(fields["co_kg_unit_field"], "float"),
                validate_field(fields["hc_kg_unit_field"], "float"),
                validate_field(fields["nox_kg_unit_field"], "float"),
                validate_field(fields["sox_kg_unit_field"], "float"),
                validate_field(fields["pm10_kg_unit_field"], "float"),
                validate_field(fields["p1_kg_unit_field"], "float"),
                validate_field(fields["p2_kg_unit_field"], "float"),
            ]
        )

    # Block signals if any of the fields is invalid
    button_box.button(button_box.StandardButton.Ok).blockSignals(
        "False" in str(results)
    )
