"""Phase 4b: unit tests for the is_test_site UI helpers.

QGIS-free. Tests import from ``open_alaqs.ui._area_sources_helpers``
(dependency-free by design), so no QGIS session or plugin bootstrap is
needed.

Coverage:
  * seed_is_test_site_from_feature: '1'/'0'/None/missing/whitespace/
    unexpected/int-1 handling.
  * write_is_test_site_to_feature: writes '1' when checked, '0' when
    unchecked.
  * Roundtrip: seed → toggle → write → re-seed lands on same state.
"""

from __future__ import annotations

from open_alaqs.ui._area_sources_helpers import (
    seed_is_test_site_from_feature,
    write_is_test_site_to_feature,
)

# ── Fakes ──────────────────────────────────────────────────────────────


class _FakeCheckbox:
    """QCheckBox stand-in with .setChecked / .isChecked."""

    def __init__(self, checked: bool = False):
        self._checked = checked

    def setChecked(self, val: bool) -> None:
        self._checked = bool(val)

    def isChecked(self) -> bool:
        return self._checked


class _FakeFeature:
    """QgsFeature stand-in supporting ``feature['key']`` reads/writes
    and KeyError on missing keys."""

    def __init__(self, data: dict = None):
        self._data = dict(data or {})

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value

    def __contains__(self, key):
        return key in self._data


# ═══════════════════════════════════════════════════════════════════════
# Section 1: seed helper
# ═══════════════════════════════════════════════════════════════════════


def test_seed_from_feature_value_1_checks_the_box():
    cb = _FakeCheckbox()
    seed_is_test_site_from_feature(cb, _FakeFeature({"is_test_site": "1"}))
    assert cb.isChecked() is True


def test_seed_from_feature_value_0_leaves_unchecked():
    cb = _FakeCheckbox(checked=True)  # start wrong to verify write
    seed_is_test_site_from_feature(cb, _FakeFeature({"is_test_site": "0"}))
    assert cb.isChecked() is False


def test_seed_from_feature_value_none_leaves_unchecked():
    """NULL in DB (from ALTER TABLE ADD COLUMN on migrated projects)
    arrives as Python None."""
    cb = _FakeCheckbox(checked=True)
    seed_is_test_site_from_feature(cb, _FakeFeature({"is_test_site": None}))
    assert cb.isChecked() is False


def test_seed_from_feature_missing_key_leaves_unchecked_no_exception():
    """Pre-v1b schema: the .ui still declares the widget but the feature
    layer's schema has no is_test_site column. Read must not raise."""
    cb = _FakeCheckbox(checked=True)
    seed_is_test_site_from_feature(cb, _FakeFeature({}))
    assert cb.isChecked() is False


def test_seed_from_feature_whitespace_around_one_still_checks():
    cb = _FakeCheckbox()
    seed_is_test_site_from_feature(cb, _FakeFeature({"is_test_site": "  1  "}))
    assert cb.isChecked() is True


def test_seed_from_feature_unexpected_value_leaves_unchecked():
    """Defensive: something unexpected like 'yes' or '2' shouldn't check
    the box. Only literal '1' does."""
    for val in ("yes", "2", "", "TRUE"):
        cb = _FakeCheckbox(checked=True)
        seed_is_test_site_from_feature(cb, _FakeFeature({"is_test_site": val}))
        assert cb.isChecked() is False, f"unexpected {val!r} should leave unchecked"


def test_seed_from_feature_integer_one_also_checks():
    """QgsFeature attribute reads can return int rather than str
    depending on how the layer's field type is inferred (INTEGER vs
    TEXT). Support both by stringifying before comparison."""
    cb = _FakeCheckbox()
    seed_is_test_site_from_feature(cb, _FakeFeature({"is_test_site": 1}))
    assert cb.isChecked() is True


def test_seed_from_feature_integer_zero_leaves_unchecked():
    cb = _FakeCheckbox(checked=True)
    seed_is_test_site_from_feature(cb, _FakeFeature({"is_test_site": 0}))
    assert cb.isChecked() is False


# ═══════════════════════════════════════════════════════════════════════
# Section 2: write helper
# ═══════════════════════════════════════════════════════════════════════


def test_write_writes_1_when_checked():
    feature = _FakeFeature({"is_test_site": "0"})
    cb = _FakeCheckbox(checked=True)
    write_is_test_site_to_feature(cb, feature)
    assert feature["is_test_site"] == "1"


def test_write_writes_0_when_unchecked():
    feature = _FakeFeature({"is_test_site": "1"})
    cb = _FakeCheckbox(checked=False)
    write_is_test_site_to_feature(cb, feature)
    assert feature["is_test_site"] == "0"


def test_write_creates_key_when_absent():
    """A pre-v1b feature layer that gained is_test_site during the
    edit session; the write should still work."""
    feature = _FakeFeature({})  # key missing
    cb = _FakeCheckbox(checked=True)
    write_is_test_site_to_feature(cb, feature)
    assert feature["is_test_site"] == "1"


# ═══════════════════════════════════════════════════════════════════════
# Section 3: roundtrip
# ═══════════════════════════════════════════════════════════════════════


def test_roundtrip_from_seeded_state():
    """Seed → user toggles → write → re-seed a fresh box → same state.
    Guards against future edits to seed/write drift."""
    feature = _FakeFeature({"is_test_site": "0"})
    cb = _FakeCheckbox()

    seed_is_test_site_from_feature(cb, feature)
    assert cb.isChecked() is False

    cb.setChecked(True)  # user toggles on
    write_is_test_site_to_feature(cb, feature)
    assert feature["is_test_site"] == "1"

    cb2 = _FakeCheckbox()
    seed_is_test_site_from_feature(cb2, feature)
    assert cb2.isChecked() is True


def test_roundtrip_toggling_back_off():
    feature = _FakeFeature({"is_test_site": "1"})
    cb = _FakeCheckbox()

    seed_is_test_site_from_feature(cb, feature)
    assert cb.isChecked() is True

    cb.setChecked(False)
    write_is_test_site_to_feature(cb, feature)
    assert feature["is_test_site"] == "0"

    cb2 = _FakeCheckbox()
    seed_is_test_site_from_feature(cb2, feature)
    assert cb2.isChecked() is False
