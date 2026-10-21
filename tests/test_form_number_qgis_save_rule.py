"""The form check of a number reads exactly what QGIS saves.

`parse_number` fell back to the tolerant `convertToFloat` (and `int()` for
integers), so the check accepted texts that QGIS saves differently or as
NULL (QgsField.convertCompatible, the rule of QGIS's text edit widget): de
"1,234.5" checked as 1234.5 but saved 1.2345, fr "1.234,5" saved NULL,
"1_000" saved NULL, en "30,3" checked 30.3 but saved 303, "nan" and "inf"
were accepted. The check now uses convertCompatible itself and rejects a
failed or non-finite conversion; an integer must also be a whole number
for the locale.

rc6 external review F2: convertCompatible falls back to the C locale, so
under an English locale "30,3" passed the check silently as 303 (QGIS
saves 303). The text must now also read as the same number with the
current locale (QLocale.toDouble): en "30,3", "1,5", de "30.3", "0.125"
(the locale reads 125) are rejected, the field is red and the tooltip
names the decimal separator of the locale.
"""

import math

import pytest
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QLocale, QVariant
from qgis.testing import start_app

start_app()

LOCALES = ["de_DE", "fr_FR", "en_US", "nl_NL"]
TEXTS = [
    "1,234.5",
    "1.234,5",
    "1_000",
    "nan",
    "inf",
    "-inf",
    "30,3",
    "30.3",
    "-1,5",
    "1,5",
    "0.125",
    "12,5",
    "12.5",
    "20.000",
    "20,000",
    "20000",
    "1e3",
    "abc",
]


@pytest.fixture(params=LOCALES)
def locale(request):
    previous = QLocale()
    QLocale.setDefault(QLocale(request.param))
    yield request.param
    QLocale.setDefault(previous)


def _check(text, var_type):
    from open_alaqs.openalaqsuitoolkit import validate_field

    edit = QtWidgets.QLineEdit()
    edit.setText(text)
    return validate_field(edit, var_type)


def _saved(text, field_type):
    """What QGIS saves for the text (None for NULL)."""
    from qgis.core import QgsField

    try:
        return QgsField("value", field_type).convertCompatible(text)
    except ValueError:
        return None


# (locale, typed, form check): the rows of the review's table
@pytest.mark.parametrize(
    "loc, text, expected",
    [
        # F2: the locale cannot read these as the number QGIS saves
        ("de_DE", "1,234.5", False),  # QGIS saves 1.2345
        ("en_US", "1.234,5", False),  # QGIS saves 1.2345
        ("fr_FR", "1.234,5", False),
        ("de_DE", "1_000", False),
        ("en_US", "1_000", False),
        ("en_US", "1,5", False),  # QGIS saves 15
        ("en_US", "30,3", False),  # QGIS saves 303
        ("en_US", "-1,5", False),  # QGIS saves -15
        ("en_US", "1,234.5", 1234.5),
        ("en_US", "30.3", 30.3),
        ("en_US", "0.125", 0.125),
        ("de_DE", "30,3", 30.3),
        ("fr_FR", "30,3", 30.3),
        ("nl_NL", "30,3", 30.3),
        ("de_DE", "30.3", False),  # QGIS saves 30.3, the locale reads nothing
        ("de_DE", "0.125", False),  # QGIS saves 0.125, the locale reads 125
        ("de_DE", "0,125", 0.125),
        ("de_DE", "20.000", False),  # QGIS saves 20, the locale reads 20000
        ("nl_NL", "1.234,5", 1234.5),
        ("en_US", "nan", False),
        ("de_DE", "inf", False),
    ],
)
def test_float_table(loc, text, expected):
    previous = QLocale()
    QLocale.setDefault(QLocale(loc))
    try:
        got = _check(text, "float")
    finally:
        QLocale.setDefault(previous)
    if expected is False:
        assert got is False
    else:
        assert got == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize(
    "loc, text, separator",
    [("en_US", "30,3", "."), ("en_US", "1,5", "."), ("de_DE", "30.3", ",")],
)
def test_wrong_decimal_separator_is_red_with_the_locale_separator(
    loc, text, separator
):
    """F2: a decimal separator the locale cannot read is refused (QGIS would
    save 303 for "30,3" in English) and the tooltip names the expected one."""
    from open_alaqs.openalaqsuitoolkit import validate_field

    previous = QLocale()
    QLocale.setDefault(QLocale(loc))
    try:
        edit = QtWidgets.QLineEdit()
        edit.setText(text)
        assert validate_field(edit, "float") is False
        assert edit.toolTip() == (
            "This value should be a number: use the decimal separator of "
            f"your locale ({separator})"
        )
        assert "background-color: rgba(255, 107, 107" in edit.styleSheet()
    finally:
        QLocale.setDefault(previous)


@pytest.mark.parametrize("text", TEXTS)
def test_float_check_is_what_qgis_saves(locale, text):
    """An accepted value is what QGIS saves, and it is accepted only when
    the locale reads the same number from the text (F2)."""
    saved = _saved(text, QVariant.Double)
    got = _check(text, "float")
    number, ok = QLocale().toDouble(text)
    if saved is None or not math.isfinite(saved) or not ok or number != saved:
        assert got is False
    else:
        assert got is not False and got == saved


@pytest.mark.parametrize("text", TEXTS + ["12.5", "-7", "+5"])
def test_integer_check_is_what_qgis_saves(locale, text):
    saved = _saved(text, QVariant.LongLong)
    got = _check(text, "int")
    if got is not False:
        assert got == saved
    number, ok = QLocale().toLongLong(text)
    if saved is None or not ok or number != saved:
        assert got is False


def test_integer_rules(locale):
    group = QLocale().toString(20000)  # "20.000", "20 000" (narrow no-break), "20,000"
    assert _check(group, "int") == 20000
    assert _check("20000", "int") == 20000
    for text in ("12.5", "12,5", "1_000", "nan", "1e3"):
        assert _check(text, "int") is False, text
