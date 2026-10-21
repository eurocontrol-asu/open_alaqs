"""Form numbers under a German or Dutch locale are read as QGIS saves them.

Under de_DE the locale reads "." as a group separator, so the locale alone
turned "0.125" into 125.0 and "12.345" into 12345.0, while QGIS itself
saves the line edit text with QgsField.convertCompatible, which reads
"0.125" as 0.125. The parking and roadway Recalculate also used bare
float() on the fleet mix text, which raised on "12,5".
"""

import pytest
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QLocale, QVariant
from qgis.testing import start_app

start_app()


@pytest.fixture(params=["de_DE", "nl_NL"])
def comma_locale(request):
    previous = QLocale()
    QLocale.setDefault(QLocale(request.param))
    yield request.param
    QLocale.setDefault(previous)


def _line_edit(text):
    edit = QtWidgets.QLineEdit()
    edit.setText(text)
    return edit


@pytest.mark.parametrize(
    "text, expected",
    [
        ("0.125", 0.125),
        ("12.345", 12.345),
        ("30,3", 30.3),
        ("12,5", 12.5),
        ("1.234,5", 1234.5),
    ],
)
def test_float_field_reads_like_qgis_saves(comma_locale, text, expected):
    from qgis.core import QgsField

    from open_alaqs.openalaqsuitoolkit import validate_field

    saved = QgsField("value", QVariant.Double).convertCompatible(text)
    assert saved == pytest.approx(expected)
    assert validate_field(_line_edit(text), "float") == pytest.approx(expected)


def test_integer_field_keeps_the_locale_group_separator(comma_locale):
    from open_alaqs.openalaqsuitoolkit import validate_field

    assert validate_field(_line_edit(QLocale().toString(20000)), "int") == 20000


FLEET = [
    "pc_p_percentage",
    "pc_d_percentage",
    "lcv_p_percentage",
    "lcv_d_percentage",
    "hdt_p_percentage",
    "hdt_d_percentage",
    "motorcycle_p_percentage",
    "bus_d_percentage",
]


class _Reached(Exception):
    pass


@pytest.mark.parametrize("module_name", ["ui_parkings", "ui_roadways"])
def test_recalculate_accepts_comma_fleet_mix(comma_locale, monkeypatch, module_name):
    """Recalculate gets past the fleet mix (8 x "12,5" = 100 %) with the
    validated values instead of raising in float("12,5")."""
    import importlib

    module = importlib.import_module(f"open_alaqs.ui.{module_name}")
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec_", lambda self: 0, raising=False)
    reached = {}

    def load_study_setup():
        reached["yes"] = True
        raise _Reached()

    monkeypatch.setattr(module.alaqs, "load_study_setup", load_study_setup)
    fields = {
        "name_field": _line_edit("P1"),
        "vehicle_year_field": _line_edit("2020"),
        "height_field": _line_edit("0,5"),
        "speed_field": _line_edit("15,5"),
        "distance_field": _line_edit("0.125"),
        "idle_time_field": _line_edit("30,0"),
    }
    for name in FLEET:
        fields[name] = _line_edit("12,5")
    try:
        if module_name == "ui_parkings":
            module.recalculate_emissions(fields, None)
        else:
            module.recalculate_emissions(fields)
    except _Reached:
        pass
    assert reached.get("yes"), "Recalculate stopped before the study setup"
