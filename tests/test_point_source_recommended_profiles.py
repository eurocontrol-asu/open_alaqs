"""The recommended profile names of default_stationary_ef are hints only.

A new study (core/templates/project.alaqs) has no user profiles, so the
names heating_season, cooling_season and business_hours do not exist
there. The point source form must then keep 'default' in the profile
lists, never store a name that does not exist (which would fall back to
the uniform profile without a word). When the study has a profile of that
name (migrated study, or created by the user), it is pre-selected.
"""

import sqlite3
from pathlib import Path

import pytest

from open_alaqs.ui import ui_point_sources

REPO = Path(__file__).resolve().parents[1]


class _FakeLineEdit:
    def __init__(self):
        self.text = ""

    def setText(self, value):
        self.text = value


class _FakeCombo:
    def __init__(self, items):
        self.items = list(items)
        self.index = 0

    def findText(self, text):
        return self.items.index(text) if text in self.items else -1

    def setCurrentIndex(self, index):
        self.index = index

    def currentText(self):
        return self.items[self.index] if self.index >= 0 else ""


def _ef_row():
    return {
        "z": 20,
        "temperature": 400,
        "diameter": 1,
        "velocity": 15,
        "SUBSTANCE": 2,
        "co_kg_k": 2.5,
        "hc_kg_k": 0.36,
        "nox_kg_k": 10.5,
        "sox_kg_k": 1.05,
        "particulate_kg_k": 0.3,
        "p1_kg_k": 0,
        "p2_kg_k": 0,
        "activity_unit": "hr",
        "recommended_month_profile": "default",
        "recommended_day_profile": "business_hours",
        "recommended_hour_profile": "business_hours",
    }


def _fields(profile_names):
    keys = (
        "height temperature diameter velocity substance co_kg_k hc_kg_k "
        "nox_kg_k sox_kg_k pm10_kg_k p1_kg_k p2_kg_k activity_unit"
    ).split()
    fields = {k: _FakeLineEdit() for k in keys}
    for key in ("hour_profile", "daily_profile", "month_profile"):
        fields[key] = _FakeCombo(["default"] + profile_names)
    return fields


@pytest.mark.parametrize("template", ["project.alaqs", "inventory.alaqs"])
def test_templates_ship_no_user_profiles(template):
    path = REPO / "open_alaqs" / "core" / "templates" / template
    conn = sqlite3.connect(str(path))
    try:
        for table in ("user_hour_profile", "user_day_profile", "user_month_profile"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        conn.close()


def test_missing_recommended_profile_keeps_default(monkeypatch):
    monkeypatch.setattr(ui_point_sources.alaqs, "get_point_type", lambda n: _ef_row())
    fields = _fields([])  # new study: only 'default'
    ui_point_sources.change_type_field(fields, "Diesel >600 hp")
    for key in ("hour_profile", "daily_profile", "month_profile"):
        assert fields[key].currentText() == "default"


def test_existing_recommended_profile_is_preselected(monkeypatch):
    monkeypatch.setattr(ui_point_sources.alaqs, "get_point_type", lambda n: _ef_row())
    fields = _fields(["business_hours", "heating_season"])
    ui_point_sources.change_type_field(fields, "Diesel >600 hp")
    assert fields["hour_profile"].currentText() == "business_hours"
    assert fields["daily_profile"].currentText() == "business_hours"
    assert fields["month_profile"].currentText() == "default"
