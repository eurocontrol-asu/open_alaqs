"""Tests for the Helicopter.getEmissionDynamicsByMode fix (issue #340).

The bug: ``Helicopter`` didn't implement ``getEmissionDynamicsByMode``,
so ``GeoTransformation.create_polygon_3d`` raised ``AttributeError`` on
any helicopter movement — the existing ``except (KeyError, TypeError)``
tuple did not catch AttributeError.

The fix: ``Helicopter.getEmissionDynamicsByMode()`` returns ``{}``. Then
``{}[lto_mode]`` raises ``KeyError`` which IS caught, and zero-extension
defaults are applied (matching the behaviour of a fixed-wing aircraft
with no ``default_emission_dynamics`` entry).
"""

from __future__ import annotations

import sys
import types

import pytest

# ── Stub the qgis chain so Helicopter is importable without QGIS ──


def _install_qgis_stubs():
    """Install minimal qgis stubs so ``Helicopter`` is importable outside
    a QGIS session (e.g. on a developer's sandbox running plain Python).

    CRITICAL: only installs stubs when the real ``qgis`` package is NOT
    already importable. On a real QGIS environment (e.g. CI), the real
    modules are used and this function is a no-op. Without this guard,
    stubs would shadow the real qgis modules for every other test that
    pytest imports after this one (see failure of
    ``test_contour_legend_zero_dedup_regression``,
    ``test_layer_replacement_regression``, and ``test_spatial_tools`` on
    the fix-helicopter-dynamics CI run before this fix).
    """
    try:
        import qgis  # noqa: F401

        # Real QGIS is available. Do nothing.
        return
    except ImportError:
        pass

    for name in (
        "qgis",
        "qgis.PyQt",
        "qgis.PyQt.QtWidgets",
        "qgis.PyQt.QtGui",
        "qgis.PyQt.QtCore",
        "qgis.core",
        "qgis.utils",
    ):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)

    sys.modules["qgis.utils"].spatialite_connect = lambda *a, **kw: None
    sys.modules["qgis.utils"].iface = None
    for sym in (
        "QgsProject",
        "QgsVectorLayer",
        "QgsCoordinateReferenceSystem",
        "QgsCoordinateTransform",
        "QgsGeometry",
        "QgsFeature",
        "QgsField",
        "QgsFields",
        "QgsMessageLog",
        "Qgis",
        "QgsWkbTypes",
        "QgsPointXY",
    ):
        setattr(sys.modules["qgis.core"], sym, type(sym, (), {}))


_install_qgis_stubs()

try:
    from open_alaqs.core.interfaces.Helicopter import Helicopter

    HAS_MODULE = True
except Exception:  # pragma: no cover
    HAS_MODULE = False


pytestmark = pytest.mark.skipif(
    not HAS_MODULE, reason="Helicopter class not importable"
)


# ═══════════════════════════════════════════════════════════════════════
# Section 1: the fix itself — method exists and returns {}
# ═══════════════════════════════════════════════════════════════════════


def _make_heli():
    """Minimum Helicopter constructor call. Uses the dict-init form so
    we don't depend on positional args that may change."""
    return Helicopter(val={"icao": "AS50", "variant_label": "test", "name": "test"})


def test_helicopter_has_getEmissionDynamicsByMode():
    """Regression: the method must exist. Its absence was the root
    cause of the AttributeError in issue #340."""
    h = _make_heli()
    assert hasattr(h, "getEmissionDynamicsByMode")
    assert callable(h.getEmissionDynamicsByMode)


def test_helicopter_getEmissionDynamicsByMode_returns_empty_dict():
    """Contract: the method returns an empty dict so that subscript
    access raises KeyError (which the caller catches) rather than
    AttributeError (which the caller does not)."""
    h = _make_heli()
    result = h.getEmissionDynamicsByMode()
    assert result == {}


# ═══════════════════════════════════════════════════════════════════════
# Section 2: end-to-end — the crash site now falls through cleanly
# ═══════════════════════════════════════════════════════════════════════


def test_helicopter_dynamics_subscript_raises_KeyError_not_AttributeError():
    """The precise contract exercised by GeoTransformation.create_polygon_3d:
    ``aircraft.getEmissionDynamicsByMode()[lto_mode]`` must raise KeyError
    on helicopters, not AttributeError. KeyError is caught by the
    existing exception tuple; AttributeError would abort the whole
    inventory build."""
    h = _make_heli()
    with pytest.raises(KeyError):
        h.getEmissionDynamicsByMode()["T/O"]
    with pytest.raises(KeyError):
        h.getEmissionDynamicsByMode()["Idle"]

    # Explicitly assert it's NOT AttributeError.
    try:
        h.getEmissionDynamicsByMode()["T/O"]
    except KeyError:
        pass
    except AttributeError as exc:  # pragma: no cover
        pytest.fail(
            f"Regression: helicopter dynamics subscript raised AttributeError, "
            f"which would abort inventory builds. Got: {exc}"
        )
