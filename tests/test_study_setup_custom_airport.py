"""Study Setup with a custom airport: a code that is not in default_airports.

The code field accepted any text already, but the dialog said nothing, did
not move the map, and required a country. Now it shows a status line, zooms
to the typed coordinates, accepts an empty country for a custom airport and
rejects a code that is not 1 to 8 letters and digits. Import OSM data skips
the Nominatim lookup for a custom code and searches around the coordinates.
"""

from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from qgis.core import QgsRectangle  # noqa: E402
from qgis.gui import QgsMapCanvas  # noqa: E402

from open_alaqs.core import alaqs  # noqa: E402
from open_alaqs.core.alaqsdblite import ProjectDatabase  # noqa: E402
from open_alaqs.enums import AlaqsLayerType  # noqa: E402
from open_alaqs.openalaqsdialog import (  # noqa: E402
    CUSTOM_AIRPORT_STATUS,
    OpenAlaqsStudySetup,
    is_custom_airport_code,
)


class _Iface:
    def __init__(self):
        self.canvas = QgsMapCanvas()

    def mainWindow(self):
        return None

    def mapCanvas(self):
        return self.canvas


@pytest.fixture
def project(tmp_path):
    db = tmp_path / "custom.alaqs"
    assert alaqs.create_project(str(db)) is None
    saved = getattr(ProjectDatabase(), "path", None)
    ProjectDatabase().path = str(db)
    yield db
    if saved is not None:
        ProjectDatabase().path = saved


@pytest.fixture
def dialog(project):
    iface = _Iface()
    dlg = OpenAlaqsStudySetup(iface)
    dlg.ui.lineEditProjectName.setText("Fictional study")
    dlg.ui.lineEditAirportID.setText("1")
    yield dlg, iface
    dlg.deleteLater()


def test_is_custom_airport_code(project):
    assert not is_custom_airport_code("EHRD")
    assert is_custom_airport_code("XTST")
    assert is_custom_airport_code("ZZZZ")
    assert not is_custom_airport_code("")


def test_status_line_for_custom_code(dialog):
    dlg, _ = dialog
    dlg.ui.comboBoxAirportCode.setCurrentText("XTST")
    assert dlg.ui.labelAirportCodeStatus.text() == CUSTOM_AIRPORT_STATUS
    dlg.ui.comboBoxAirportCode.setCurrentText("EHRD")
    assert dlg.ui.labelAirportCodeStatus.text() == ""
    assert dlg.ui.lineEditAirportName.text() == "Rotterdam"
    dlg.ui.comboBoxAirportCode.setCurrentText("X-1")
    assert "1 to 8 letters or digits" in dlg.ui.labelAirportCodeStatus.text()


def test_zoom_to_typed_coordinates(dialog):
    dlg, iface = dialog
    dlg.ui.spinBoxAirportLatitude.setValue(-33.95)
    dlg.ui.spinBoxAirportLongitude.setValue(151.18)
    dlg.zoom_to_airport()
    extent = iface.canvas.extent()
    assert isinstance(extent, QgsRectangle)
    centre = extent.center()
    # The canvas CRS is the project CRS (EPSG:4326 for a new project).
    assert centre.x() == pytest.approx(151.18, abs=0.05)
    assert centre.y() == pytest.approx(-33.95, abs=0.05)


def test_custom_airport_saves_without_country(dialog, project):
    dlg, _ = dialog
    dlg.ui.comboBoxAirportCode.setCurrentText("XTST")
    dlg.ui.lineEditAirportName.setText("Fictional")
    dlg.ui.lineEditAirportCountry.setText("")
    dlg.ui.spinBoxAirportLatitude.setValue(-33.95)
    dlg.ui.spinBoxAirportLongitude.setValue(151.18)
    dlg.ui.spinBoxAirportElevation.setValue(6)
    dlg.ui.comboBoxRoadwayFleetYear.setCurrentText("2020")
    dlg.ui.comboBoxRoadwayCountry.setCurrentText("EU27")
    assert dlg.save_study_setup() is None
    setup = alaqs.load_study_setup()
    assert setup["airport_code"] == "XTST"
    assert setup["airport_country"] == ""
    assert setup["airport_latitude"] == pytest.approx(-33.95)
    assert setup["airport_longitude"] == pytest.approx(151.18)


def test_known_airport_still_needs_country(dialog, monkeypatch):
    dlg, _ = dialog
    shown = []
    from qgis.PyQt import QtWidgets

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "information",
        lambda *a, **k: shown.append(a[2]),
    )
    dlg.ui.comboBoxAirportCode.setCurrentText("EHRD")
    dlg.ui.lineEditAirportCountry.setText("")
    dlg.ui.comboBoxRoadwayFleetYear.setCurrentText("2020")
    dlg.ui.comboBoxRoadwayCountry.setCurrentText("EU27")
    dlg.save_study_setup()
    assert shown and "Airport country" in shown[0]


def test_bad_code_is_rejected(dialog, monkeypatch):
    dlg, _ = dialog
    shown = []
    from qgis.PyQt import QtWidgets

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "information",
        lambda *a, **k: shown.append(a[2]),
    )
    dlg.ui.comboBoxAirportCode.setCurrentText("TOO-LONG-CODE")
    dlg.ui.lineEditAirportName.setText("Fictional")
    dlg.ui.comboBoxRoadwayFleetYear.setCurrentText("2020")
    dlg.ui.comboBoxRoadwayCountry.setCurrentText("EU27")
    dlg.save_study_setup()
    assert shown and "Airport ICAO code" in shown[0]


def test_osm_custom_airport_skips_nominatim(monkeypatch):
    from open_alaqs.core.utils import osm

    calls = []
    monkeypatch.setattr(
        osm,
        "get_nominatum_feature_by_icao_code",
        lambda code: calls.append(code) or None,
    )
    captured = {}
    real = osm.get_query_body

    def fake_query_body(layer_types, coords, aerodrome, aerodrome_radius_m=None):
        captured["aerodrome"] = aerodrome
        captured["radius"] = aerodrome_radius_m
        return real(layer_types, coords, aerodrome, aerodrome_radius_m)

    monkeypatch.setattr(osm, "get_query_body", fake_query_body)
    # Stop before any network access: the Processing check fails outside QGIS.
    monkeypatch.setattr(osm.utils, "plugins", {})
    monkeypatch.setattr(osm.QMessageBox, "critical", lambda *a, **k: None)

    osm.download_osm_airport_data(
        [AlaqsLayerType.BUILDING], (-33.95, 151.18), "XTST", lookup_aerodrome=False
    )
    assert calls == []
    assert captured["aerodrome"] is None
    assert captured["radius"] == osm.OSM_CUSTOM_AIRPORT_RADIUS_M == 3000
    body = real(
        [AlaqsLayerType.BUILDING, AlaqsLayerType.ROADWAY],
        (-33.95, 151.18),
        None,
        osm.OSM_CUSTOM_AIRPORT_RADIUS_M,
    )
    assert "area(" not in body
    # buildings (within_aerodrome) at the custom radius, roads at their own
    assert "around:3000, -33.95,151.18" in body
    assert "around:1000" not in body
    # without the custom radius the within_aerodrome filters use the default
    body_default = real([AlaqsLayerType.BUILDING], (-33.95, 151.18), None)
    assert "around:1000, -33.95,151.18" in body_default

    osm.download_osm_airport_data(
        [AlaqsLayerType.BUILDING], (51.95, 4.43), "EHRD", lookup_aerodrome=True
    )
    assert calls == ["EHRD"]


def test_ui_file_has_the_new_widgets():
    ui = (
        Path(__file__).resolve().parents[1] / "open_alaqs" / "ui" / "ui_study_setup.ui"
    ).read_text()
    assert 'name="labelAirportCodeStatus"' in ui
    assert 'name="pushButtonZoomToAirport"' in ui
