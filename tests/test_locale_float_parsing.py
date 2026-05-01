"""
Regression test for GitHub #159 — locale issue for float when cloning
alaqs sqlite db.

Scenario: user clones a .alaqs file, edits height values via raw SQL
(e.g. sets shapes_gates.height = 30.3), reopens in OpenALAQS on a
European-locale QGIS. Qt displays "30.3" as "30,3" and bare float()
in validate_field rejects it.

Fix covers:
- `convertToFloat` accepts decimal comma + comma/dot thousands
- `validate_field("float")` routes through convertToFloat
- `Source.py` base class + 8 interface files (Gate, Taxiway, Runway,
  Area, Parking, Point, Roadway, UserTimeProfiles) use convertToFloat
  for DB-sourced values
"""


class TestIssue159ConvertToFloat:
    """Unit-level tests for the locale-tolerant convertToFloat."""

    def test_us_decimal_dot(self):
        from open_alaqs.core.tools.conversion import convertToFloat

        assert convertToFloat("30.3") == 30.3
        assert convertToFloat("1234.56") == 1234.56
        assert convertToFloat("-3.14") == -3.14

    def test_european_decimal_comma(self):
        """The reporter's exact scenario: DB stores 30.3, Qt displays 30,3."""
        from open_alaqs.core.tools.conversion import convertToFloat

        assert convertToFloat("30,3") == 30.3
        assert convertToFloat("42,5") == 42.5
        assert convertToFloat("-3,14") == -3.14

    def test_european_thousands_plus_decimal(self):
        from open_alaqs.core.tools.conversion import convertToFloat

        assert convertToFloat("1.234,56") == 1234.56
        assert convertToFloat("10.000,0") == 10000.0

    def test_us_thousands_plus_decimal(self):
        """Python's float() doesn't accept thousands ',' so we handle it."""
        from open_alaqs.core.tools.conversion import convertToFloat

        assert convertToFloat("1,234.56") == 1234.56
        assert convertToFloat("10,000.0") == 10000.0

    def test_native_numeric_unchanged(self):
        from open_alaqs.core.tools.conversion import convertToFloat

        assert convertToFloat(1.23) == 1.23
        assert convertToFloat(0) == 0
        assert convertToFloat(-5) == -5

    def test_none_and_empty_use_default(self):
        from open_alaqs.core.tools.conversion import convertToFloat

        assert convertToFloat(None, default=0.0) == 0.0
        assert convertToFloat("", default=99.0) == 99.0
        assert convertToFloat(None) is None
        assert convertToFloat("") is None

    def test_garbage_returns_default(self):
        from open_alaqs.core.tools.conversion import convertToFloat

        assert convertToFloat("abc", default=0.0) == 0.0
        assert convertToFloat("1.2.3.4", default=0.0) == 0.0
        assert convertToFloat("1,2,3", default=0.0) == 0.0


class TestIssue159SourceUsesConvertToFloat:
    """Smoke test that Source and subclasses actually use convertToFloat
    (catches accidental reverts to bare float())."""

    def test_source_accepts_comma_height(self):
        """Source base class — covers all shape sources via inheritance."""
        from open_alaqs.core.interfaces.Source import Source

        s = Source({"height": "30,3"})
        assert s._height == 30.3

    def test_gate_accepts_comma_height(self):
        from open_alaqs.core.interfaces.Gate import Gate

        g = Gate({"gate_height": "45,5", "gate_id": "T", "gate_type": "REMOTE"})
        assert g._height == 45.5

    def test_taxiway_accepts_comma_values(self):
        from open_alaqs.core.interfaces.Taxiway import TaxiwaySegment

        t = TaxiwaySegment({"taxiway_id": "T1", "height": "12,3", "speed": "36,0"})
        assert t._height == 12.3
        # 36 km/h / 3.6 = 10.0 m/s
        assert abs(t._speed_in_m_s - 10.0) < 1e-9

    def test_parking_accepts_comma_values(self):
        from open_alaqs.core.interfaces.ParkingSources import ParkingSources

        p = ParkingSources(
            {
                "vehicle_year": "2020",
                "distance": "1,5",
                "idle_time": "30,0",
                "speed": "15,5",
            }
        )
        assert p._distance == 1.5
        assert p._idle_time == 30.0
        assert p._speed == 15.5


class TestIssue159ValidateFieldAcceptsComma:
    """validate_field('float') must accept comma decimals — this was
    the reporter's exact observation (red-highlighted form field)."""

    def _make_line_edit(self, text: str):
        from qgis.PyQt import QtWidgets
        from qgis.testing import start_app

        start_app()
        w = QtWidgets.QLineEdit()
        w.setText(text)
        return w

    def test_validate_field_float_accepts_dot(self):
        from open_alaqs.openalaqsuitoolkit import validate_field

        w = self._make_line_edit("30.3")
        assert validate_field(w, "float") == 30.3

    def test_validate_field_float_accepts_comma(self):
        """GitHub #159 — this was the failing case."""
        from open_alaqs.openalaqsuitoolkit import validate_field

        w = self._make_line_edit("30,3")
        assert validate_field(w, "float") == 30.3

    def test_validate_field_float_rejects_garbage(self):
        from open_alaqs.openalaqsuitoolkit import validate_field

        w = self._make_line_edit("not-a-number")
        assert validate_field(w, "float") is False
