"""Configuration tab Method: the user's choice survives pollutant changes.

populate_calculation_methods() patches the method options on every pollutant
change: [bymode, BFFM2] for CO, HC and NOx, [bymode] otherwise. BFFM2 must
stay selected when switching between CO/HC/NOx, and must come back after a
pollutant without BFFM2 (e.g. CO -> SOx -> NOx).
"""

import pytest
from qgis.PyQt import QtWidgets
from qgis.testing import start_app

start_app()

from open_alaqs.core.modules.ModuleConfigurationWidget import (  # noqa: E402
    ModuleConfigurationWidget,
)

BOTH = ["bymode", "BFFM2"]
BYMODE = ["bymode"]


def _patch(widget, options):
    # what OpenAlaqsResultsAnalysis.populate_calculation_methods sends
    widget.patch_schema(
        {"method": {"initial_value": options[0], "widget_config": {"options": options}}}
    )


@pytest.fixture
def widget():
    w = ModuleConfigurationWidget(
        {
            "method": {
                "label": "Method",
                "widget_type": QtWidgets.QComboBox,
                "initial_value": "bymode",
                "widget_config": {"options": BOTH},
            }
        }
    )
    _patch(w, BOTH)
    return w


def _select(widget, value):
    combo = widget.get_widget("method")
    combo.setCurrentIndex(combo.findText(value))


def test_bffm2_kept_between_pollutants_that_offer_it(widget):
    _select(widget, "BFFM2")
    _patch(widget, BOTH)  # CO -> NOx
    assert widget.get_values()["method"] == "BFFM2"


def test_bffm2_restored_after_pollutant_without_it(widget):
    _select(widget, "BFFM2")
    _patch(widget, BYMODE)  # -> SOx
    assert widget.get_values()["method"] == "bymode"
    _patch(widget, BYMODE)  # -> PM10
    assert widget.get_values()["method"] == "bymode"
    _patch(widget, BOTH)  # -> NOx
    assert widget.get_values()["method"] == "BFFM2"


def test_explicit_bymode_not_overridden(widget):
    _select(widget, "BFFM2")
    _patch(widget, BYMODE)  # -> SOx: forced to bymode
    _patch(widget, BOTH)  # -> CO: BFFM2 back
    _select(widget, "bymode")  # the user picks bymode
    _patch(widget, BYMODE)
    _patch(widget, BOTH)
    assert widget.get_values()["method"] == "bymode"


def test_results_dialog_pollutant_switch():
    from qgis.testing.mocked import get_iface

    from open_alaqs.openalaqsdialog import OpenAlaqsResultsAnalysis

    dlg = OpenAlaqsResultsAnalysis(get_iface())
    pollutants = dlg.ui.pollutants_names
    config = dlg._emission_calculation_configuration_widget
    pollutants.setCurrentText("NOx")
    _select(config, "BFFM2")
    for name, expected in (("CO", "BFFM2"), ("SOx", "bymode"), ("HC", "BFFM2")):
        pollutants.setCurrentText(name)
        assert config.get_values()["method"] == expected, name


def test_loaded_configuration_clears_remembered_choice(widget):
    """A value set by init_values (e.g. loading a configuration) replaces the
    remembered BFFM2 choice: a later pollutant switch must not bring back a
    stale BFFM2."""
    _select(widget, "BFFM2")
    _patch(widget, BYMODE)  # -> SOx: forced to bymode, BFFM2 remembered
    widget.init_values({"method": "bymode"})  # configuration loaded
    _patch(widget, BOTH)  # -> NOx
    assert widget.get_values()["method"] == "bymode"


def test_no_choice_remembered_without_a_value(widget):
    """No (None, initial_value) entry is remembered when the setting had no
    value."""
    widget.get_values = lambda: {"method": None}
    _patch(widget, BYMODE)
    assert "method" not in widget._forced_fallbacks
