"""
Regression test for UI spin-box minimum bounds.

Qt's `QDoubleSpinBox` and `QSpinBox` default `minimum` to 0 when the .ui file
does not set it explicitly. Calling `setValue(negative)` on such a widget --
including from `airport_lookup()`'s feet-to-metres conversion path -- silently
clamps to 0 with no error. Manual entry of negative values is also rejected.

Concrete failure observed: a user picks EHRD (Rotterdam, AIP elevation
-15 ft = -5 m). `airport_lookup()` runs `setValue(round(-15 * 0.3048))`
i.e. `setValue(-5)`. With no minimum, Qt clamps to 0 and the user sees
0 m elevation in the form. The 0 is then saved to user_study_setup and
propagates to ISA temperature, NOx ambient correction, and the AUSTAL
reference altitude.

Fields that physically permit negative values must declare an explicit
`minimum` property. This test scans every .ui file and asserts that any
spin-box whose name implies a negative-allowing physical quantity has
an explicit `minimum`.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UI_DIR = REPO / "open_alaqs" / "ui"

# Substrings in widget names that imply negative values are physically valid.
# Add to this list when new fields are added.
NEGATIVE_REQUIRED = [
    "elevation",  # below-MSL airports (EHRD -5 m, EHAM -3 m, LLEY -385 m, etc.)
    "altitude",
    "latitude",  # Southern Hemisphere
    "longitude",  # Western Hemisphere
    "temperature",  # cold-climate airports (Anchorage, Reykjavik, ...)
    "depth",
    "lapse",
]

# Substrings that explicitly DO NOT need negatives (avoid false positives)
NEGATIVE_FORBIDDEN = [
    "fleet_year",
    "vertical_limit",  # LTO ceiling, hardcoded to 914.4 anyway
    "wind_speed",
    "wind_dir",
    "humidity",
    "pressure",
    "resolution",
    "cells",
    "year",
]


def _spin_widgets():
    """Yield (ui_filename, widget_name, props_dict) for every spin-box."""
    for ui in sorted(UI_DIR.glob("*.ui")):
        try:
            tree = ET.parse(ui)
        except ET.ParseError:
            continue
        for w in tree.iter("widget"):
            cls = w.attrib.get("class", "")
            if "SpinBox" not in cls:
                continue
            name = w.attrib.get("name", "")
            props = {}
            for p in w.findall("property"):
                pname = p.attrib["name"]
                pval = (
                    p.findtext("double") or p.findtext("number") or p.findtext("string")
                )
                props[pname] = pval
            yield ui.name, name, props


def _needs_minimum(widget_name: str) -> bool:
    n = widget_name.lower()
    if any(forb in n for forb in NEGATIVE_FORBIDDEN):
        return False
    return any(req in n for req in NEGATIVE_REQUIRED)


def test_negative_allowing_spinboxes_have_explicit_minimum():
    """All widgets whose names imply negative-valued physical quantities
    must declare an explicit `minimum` property in the .ui file.

    Without this, Qt silently clamps `setValue(negative)` to 0, masking
    incorrect input from both auto-populate paths and manual entry."""
    offenders = []
    for ui_name, widget_name, props in _spin_widgets():
        if not _needs_minimum(widget_name):
            continue
        if "minimum" not in props:
            offenders.append(f"{ui_name}::{widget_name}")
    assert not offenders, (
        "The following spin-box widgets allow negative physical quantities "
        "but have no explicit `minimum` property in the .ui file. Qt defaults "
        'minimum to 0 and silently clamps. Add `<property name="minimum">'
        "<double>...</double></property>` to each:\n  - " + "\n  - ".join(offenders)
    )


def test_airport_elevation_minimum_at_least_minus_500m():
    """The lowest real-world commercial airport (Bar Yehuda, LLEY) sits at
    -385 m. The plugin's spinBoxAirportElevation must accept at least -500 m
    to leave headroom for any IATA-listed below-MSL airfield."""
    found = False
    for _ui_name, widget_name, props in _spin_widgets():
        if widget_name != "spinBoxAirportElevation":
            continue
        found = True
        assert "minimum" in props, "spinBoxAirportElevation has no minimum"
        mn = float(props["minimum"])
        assert mn <= -500.0, (
            f"spinBoxAirportElevation minimum is {mn} m, must be ≤ -500 m to "
            f"accept Bar Yehuda (LLEY, -385 m) and similar below-MSL airports."
        )
    assert found, "spinBoxAirportElevation widget not found in any .ui"


def test_airport_temperature_minimum_at_least_minus_60c():
    """Annual mean temperatures at polar airports range down to about -56°C
    (Vostok). spinBoxAirportTemperature must accept at least -60°C to be
    usable for sub-arctic studies."""
    found = False
    for _ui_name, widget_name, props in _spin_widgets():
        if widget_name != "spinBoxAirportTemperature":
            continue
        found = True
        assert "minimum" in props, "spinBoxAirportTemperature has no minimum"
        mn = float(props["minimum"])
        assert (
            mn <= -60.0
        ), f"spinBoxAirportTemperature minimum is {mn} °C, must be ≤ -60 °C."
    assert found, "spinBoxAirportTemperature widget not found in any .ui"
