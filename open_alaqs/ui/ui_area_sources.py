from qgis.PyQt import QtWidgets

from open_alaqs.core import alaqs, alaqsutils
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.enums import AlaqsLayerType
from open_alaqs.openalaqsuitoolkit import (
    add_combo_values,
    is_empty_text,
    update_ok_button,
    validate_field,
)
from open_alaqs.ui._area_sources_helpers import (
    seed_is_test_site_from_feature,
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


def _apply_test_site_field_state(fields, is_test_site: bool) -> None:
    """Enable or disable form fields that are irrelevant to an
    engine-test site.

    An engine-test-site area source gets its emissions from per-event
    records in ``engine_test_events``, so the following fields on the
    area-source form are ignored at compute time:

      * Units per Year (``unit_field``) on the Parameters tab
      * All seven ``*_kg_unit`` emission-rate fields on the Emissions
        tab
      * The three activity-profile combo boxes on the Profiles tab

    Signalling "these fields are irrelevant" is done by two mechanisms:

      * The ``unit_field`` (Parameters tab, index 0) is disabled
        individually. Direct ``QLineEdit.setEnabled(False)`` gives the
        grayed-out look.
      * The Profiles tab (index 1) and Emissions tab (index 2) are
        disabled at the ``QTabWidget`` level. ``setTabEnabled(i,
        False)`` grays out the tab label and makes it unclickable.
        Per-widget ``setEnabled`` calls on the fields inside those
        tabs don't produce the expected visual effect in the QGIS
        attribute form (fields inside inactive tabs stay looking
        active), which is why the individual-widget approach that
        worked for ``unit_field`` doesn't work here.

    Height and Source Name stay enabled regardless (height matters
    for dispersion positioning; name is the source identifier).
    Heat flux stays disabled (read-only, 0 for new area sources).
    """
    # Individual field on the always-visible Parameters tab.
    unit_field = fields.get("unit_field")
    if unit_field is not None:
        unit_field.setEnabled(not is_test_site)

    # Tab-level disable for Profiles (index 1) and Emissions (index 2).
    # The tabWidget itself is looked up lazily since form_open doesn't
    # store it in the fields dict.
    tab_widget = fields.get("tab_widget")
    if tab_widget is not None:
        for tab_index in (1, 2):
            tab_widget.setTabEnabled(tab_index, not is_test_site)


def _zero_fill_test_site_fields(fields) -> None:
    """Fill "0" into the blank Units per Year and *_kg_unit fields, so a
    test site stores numbers rather than NULL (which some downstream code
    does not handle). Values the user entered are kept."""
    for f_name in (
        "unit_field",
        "co_kg_unit_field",
        "hc_kg_unit_field",
        "nox_kg_unit_field",
        "sox_kg_unit_field",
        "pm10_kg_unit_field",
        "p1_kg_unit_field",
        "p2_kg_unit_field",
    ):
        widget = fields.get(f_name)
        if widget is not None and is_empty_text(widget.text()):
            widget.setText("0")


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
    if is_empty_text(source_id):
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
        # The QTabWidget wrapping the Parameters / Profiles / Emissions
        # tabs. Used by _apply_test_site_field_state to gray out the
        # Profiles and Emissions tabs when the checkbox is ticked.
        tab_widget=form.findChild(QtWidgets.QTabWidget, "tabWidget"),
    )

    # The In Study check box is bound to the instudy column by QGIS (CheckBox
    # widget, "1" / "0", set in alaqs_config.py): it shows the stored value
    # and QGIS saves what the user sets, so the form does not write it.

    # Seed the is_test_site checkbox from the feature. Values arrive as
    # TEXT '1' / '0' (matching the DB), NULL (from ALTER TABLE ADD COLUMN
    # on migrated projects), or absent entirely (pre-v1b schema — the
    # widget still exists on the form but has nothing to read).
    seed_is_test_site_from_feature(fields["is_test_site"], feature)
    # The check box is also bound to is_test_site by QGIS (CheckBox widget,
    # '1' / '0', set in alaqs_config.py), which saves it with the form.

    # Wire the "Load engine test events CSV..." button. It is enabled
    # only when the source is flagged as a test site. Clicking it opens
    # the OpenAlaqsImportEngineTestEvents dialog scoped to this source.
    if fields["load_events_csv"] is not None:
        fields["load_events_csv"].setEnabled(fields["is_test_site"].isChecked())
        fields["is_test_site"].toggled.connect(fields["load_events_csv"].setEnabled)
        fields["load_events_csv"].clicked.connect(
            lambda: _open_load_events_dialog(form, fields, feature)
        )

    # For test sites the compute path ignores unit_year and the *_kg_unit
    # rate columns: fill "0" into the blank ones when the box is ticked
    # (and at open for a test site), before the form is saved.
    if fields["is_test_site"].isChecked():
        _zero_fill_test_site_fields(fields)
    fields["is_test_site"].toggled.connect(
        lambda checked: checked and _zero_fill_test_site_fields(fields)
    )

    # Re-run validation whenever the test-site toggle changes: the set
    # of required fields differs between test-site and regular modes.
    fields["is_test_site"].toggled.connect(lambda _checked: validate(fields))

    # Enable/disable the fields that a test site ignores (compute reads
    # events from engine_test_events instead). Called once at form-open
    # to apply the initial state, and re-called on every toggle so the
    # visual state tracks the checkbox.
    _apply_test_site_field_state(fields, fields["is_test_site"].isChecked())
    fields["is_test_site"].toggled.connect(
        lambda checked: _apply_test_site_field_state(fields, checked)
    )

    # Heat Flux is not entered (read-only, 0 for new sources)
    fields["heat_flux_field"].setEnabled(False)

    # Seed the profiles
    populate_hourly_profiles(fields["hour_profile_field"])
    populate_daily_profiles(fields["daily_profile_field"])
    populate_monthly_profiles(fields["month_profile_field"])

    # Add input validation to text fields in the form
    for key, value in fields.items():
        if isinstance(value, QtWidgets.QLineEdit):
            fields[key].textChanged.connect(lambda: validate(fields))

    # OK is enabled only while the form is valid: validate now, then on
    # every change
    validate(fields)


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

    When the "Engine test site" checkbox is ticked, the emissions and
    unit-rate fields are irrelevant (the compute path reads events from
    ``engine_test_events`` and ignores the ``*_kg_unit`` columns). Those
    fields are skipped in validation so the user can save the source
    without filling in numbers that will never be used. ``on_save()``
    auto-fills them with ``"0"`` so the DB stores something valid.

    Source name and height are validated regardless: they matter for
    both regular area sources AND test sites (height for dispersion
    positioning, name for the source_id). Heat flux is read-only, so it
    is only checked when it holds a value.
    """

    # Get the button box
    button_box = fields["button_box"]

    # Fields validated for every area source.
    results = [
        (fields["name_field"], validate_field(fields["name_field"], "str")),
        (fields["height_field"], validate_field(fields["height_field"], "float")),
    ]
    if not is_empty_text(fields["heat_flux_field"].text()):
        results.append(
            (
                fields["heat_flux_field"],
                validate_field(fields["heat_flux_field"], "float"),
            )
        )

    # Fields validated only for regular area sources. Skipped when the
    # source is a test site.
    is_test_site = (
        fields.get("is_test_site") is not None and fields["is_test_site"].isChecked()
    )
    if not is_test_site:
        results.extend(
            [
                (
                    fields["co_kg_unit_field"],
                    validate_field(fields["co_kg_unit_field"], "float"),
                ),
                (
                    fields["hc_kg_unit_field"],
                    validate_field(fields["hc_kg_unit_field"], "float"),
                ),
                (
                    fields["nox_kg_unit_field"],
                    validate_field(fields["nox_kg_unit_field"], "float"),
                ),
                (
                    fields["sox_kg_unit_field"],
                    validate_field(fields["sox_kg_unit_field"], "float"),
                ),
                (
                    fields["pm10_kg_unit_field"],
                    validate_field(fields["pm10_kg_unit_field"], "float"),
                ),
                (
                    fields["p1_kg_unit_field"],
                    validate_field(fields["p1_kg_unit_field"], "float"),
                ),
                (
                    fields["p2_kg_unit_field"],
                    validate_field(fields["p2_kg_unit_field"], "float"),
                ),
            ]
        )

    # OK enabled only when every field is valid
    update_ok_button(button_box, results, AlaqsLayerType.AREA)
