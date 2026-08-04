"""Unit tests for AUSTALDispersionModule._ti_type_label_for.

Verifies that the AUSTAL by-type aggregation gives engine-test sites
their own "engine_test" label even though they share the AreaSources
Python class with regular area sources. Without this, sparse
per-event engine-test emissions would be merged with (much larger,
constant) area-source emissions and both dispersion signatures
would be lost.

Requires the real QGIS environment (imports AUSTALOutputModule which
pulls in qgis.gui, qgis.PyQt.QtCore, etc.). Skipped on developer
sandboxes without QGIS, same as tests/test_austal_slot_compaction.py.
"""

from __future__ import annotations

import pytest

pytest.importorskip("qgis")

from open_alaqs.core.modules.AUSTALOutputModule import (  # noqa: E402
    AUSTALDispersionModule,
)


class _FakeAreaSources:
    """Duck-types AreaSources for the type-label check. Only the
    class name and isTestSite() accessor matter."""

    def __init__(self, is_test: bool):
        self._is_test = is_test

    def isTestSite(self) -> bool:
        return self._is_test


_FakeAreaSources.__name__ = "AreaSources"


class _FakeRoadwaySources:
    def isTestSite(self):  # pragma: no cover - defined only to prove
        # the class-name gate short-circuits before isTestSite is ever
        # consulted for non-Area sources.
        raise AssertionError("isTestSite() must not be consulted for RoadwaySources")


_FakeRoadwaySources.__name__ = "RoadwaySources"


def test_regular_area_source_labelled_area():
    src = _FakeAreaSources(is_test=False)
    assert AUSTALDispersionModule._ti_type_label_for(src) == "area"


def test_engine_test_area_source_labelled_engine_test():
    src = _FakeAreaSources(is_test=True)
    assert AUSTALDispersionModule._ti_type_label_for(src) == "engine_test"


def test_roadway_source_labelled_road_without_touching_istestsite():
    """Non-Area sources must not have isTestSite() invoked on them,
    even if they happen to expose it (guard against future subclasses
    that inherit the accessor)."""
    src = _FakeRoadwaySources()
    assert AUSTALDispersionModule._ti_type_label_for(src) == "road"


def test_area_source_without_istestsite_method_falls_back_to_area():
    """Very old AreaSources subclasses that predate the is_test_site
    schema won't have the accessor. Those must not raise; they fall
    back to 'area' unchanged."""

    class OldAreaSources:
        pass

    OldAreaSources.__name__ = "AreaSources"
    src = OldAreaSources()
    assert AUSTALDispersionModule._ti_type_label_for(src) == "area"


def test_istestsite_raising_is_swallowed():
    """A bad accessor implementation must not propagate through the
    aggregation. Fall through to 'area'."""

    class BrokenAreaSources:
        def isTestSite(self):
            raise RuntimeError("db down")

    BrokenAreaSources.__name__ = "AreaSources"
    src = BrokenAreaSources()
    assert AUSTALDispersionModule._ti_type_label_for(src) == "area"


def test_unknown_class_returns_empty_string():
    """Unknown source classes get "" (own bucket at aggregation time)."""

    class WeirdSource:
        pass

    src = WeirdSource()
    assert AUSTALDispersionModule._ti_type_label_for(src) == ""
