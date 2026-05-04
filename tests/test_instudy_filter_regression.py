"""Regression test for the `instudy` filter fix.

Bug:
  The `instudy` column has been part of the spatialite schema for
  roadways, parking, gates, point sources, area sources, and runways
  for a long time, but no module ever read it. Sources marked
  `instudy='0'` were silently included in the emission calculation,
  producing wrong totals.

  User-facing trigger: a synthetic test in the EHRD study with an
  area source `D_excluded`, `instudy='0'`, `unit_year=1000` produced
  10,000 kg/yr NOx in the QGIS output instead of the expected 0.

  Code path that went wrong:
    1. SQLSerializable.deserialize() runs `SELECT * FROM <table>`
       with no WHERE clause, loading every row regardless of
       instudy.
    2. *SourceModule.process() iterates every loaded source without
       checking the flag.
    3. The 8 schema definitions of `instudy` had zero read-side
       references in the entire core/ tree.

Fix:
  - Source.__init__ captures `instudy` and exposes `isInStudy()`.
    Subclasses (RoadwaySources, ParkingSources, PointSources,
    AreaSources) inherit through their existing super() calls; no
    per-subclass change needed.
  - Gate.__init__ does the same separately because Gate doesn't
    inherit from Source.
  - Runway.__init__ captures `_in_study` for forward-compat with
    Phase 3 movement support; the filter is not yet wired in.
  - Each *SourceModule.process() loop adds
        if not source.isInStudy(): continue
    after the existing source_names filter.

This test pins the unit-level contract (Source / Gate / Runway
__init__ correctly reads the flag and exposes it via isInStudy()).
The integration-level filter behavior in *SourceModule.process()
is exercised by existing module tests in the rebuild's CI.
"""

import sys
import types


# Stub qgis namespace for standalone import (same pattern as the
# other regression test files).
def _ensure_qgis_stubs():
    if "qgis" not in sys.modules:
        sys.modules["qgis"] = types.ModuleType("qgis")

    qgis_utils = sys.modules.get("qgis.utils") or types.ModuleType("qgis.utils")

    def _spatialite_connect(db_name, *args, **kwargs):
        import sqlite3

        return sqlite3.connect(db_name)

    qgis_utils.spatialite_connect = _spatialite_connect
    sys.modules["qgis.utils"] = qgis_utils
    sys.modules["qgis"].utils = qgis_utils

    if "qgis.core" not in sys.modules:
        qgis_core = types.ModuleType("qgis.core")

        class _QgsStub:
            Info = Warning = Critical = 0

            def __getattr__(self, name):
                return _QgsStub()

            def __call__(self, *args, **kwargs):
                return None

        qgis_core.Qgis = _QgsStub()
        qgis_core.QgsMessageLog = _QgsStub()
        sys.modules["qgis.core"] = qgis_core
        sys.modules["qgis"].core = qgis_core


_ensure_qgis_stubs()


from open_alaqs.core.interfaces.Source import Source  # noqa: E402

# Gate and Runway pull in shapely / osgeo at module load. Try to
# import them; if the env can't satisfy the deps, mark the relevant
# tests as skip rather than failing the file.
try:
    from open_alaqs.core.interfaces.Gate import Gate  # noqa: E402

    _HAS_GATE = True
except Exception:
    _HAS_GATE = False
try:
    from open_alaqs.core.interfaces.Runway import Runway  # noqa: E402

    _HAS_RUNWAY = True
except Exception:
    _HAS_RUNWAY = False


import pytest  # noqa: E402

# ---------------------------------------------------------------------------
# Source (base class) - inherited by Roadway/Parking/Point/Area sources
# ---------------------------------------------------------------------------


class TestSourceInStudyFlag:
    def test_default_is_in_study(self):
        """A bare-minimum Source row (no `instudy` key) is treated as
        in-study. This preserves legacy behavior for non-DB inputs
        (programmatic construction, tests)."""
        s = Source({})
        assert s.isInStudy() is True

    def test_explicit_in_study(self):
        s = Source({"instudy": "1"})
        assert s.isInStudy() is True

    def test_explicit_not_in_study(self):
        s = Source({"instudy": "0"})
        assert s.isInStudy() is False

    def test_whitespace_tolerant(self):
        """SQLite TEXT columns can have leading/trailing whitespace
        from sloppy DB tooling. The reader should still parse '1'
        with surrounding spaces correctly."""
        assert Source({"instudy": " 1 "}).isInStudy() is True
        assert Source({"instudy": "  0  "}).isInStudy() is False

    def test_unknown_value_treated_as_excluded(self):
        """Anything other than '1' (post-strip) is treated as
        excluded. This is the conservative interpretation: if a user
        sets `instudy='maybe'` or `instudy='2'`, exclude rather than
        guess. Keeps the contract simple."""
        for val in ["2", "yes", "true", "TRUE", "y", ""]:
            assert (
                Source({"instudy": val}).isInStudy() is False
            ), f"Source with instudy={val!r} should NOT be in study"


# ---------------------------------------------------------------------------
# Gate - parallel implementation, separate class hierarchy
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_GATE, reason="Gate requires shapely/osgeo")
class TestGateInStudyFlag:
    def test_default_is_in_study(self):
        g = Gate({"gate_id": "G01", "gate_type": "PIER"})
        assert g.isInStudy() is True

    def test_excluded_gate(self):
        g = Gate({"gate_id": "G01", "gate_type": "PIER", "instudy": "0"})
        assert g.isInStudy() is False


# ---------------------------------------------------------------------------
# Runway - capture only, filter not yet wired (Phase 3)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_RUNWAY, reason="Runway requires shapely/osgeo")
class TestRunwayInStudyFlag:
    def test_default_is_in_study(self):
        r = Runway({"runway_id": "06/24"})
        assert r.isInStudy() is True

    def test_excluded_runway(self):
        r = Runway({"runway_id": "06/24", "instudy": "0"})
        assert r.isInStudy() is False
