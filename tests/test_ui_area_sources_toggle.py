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
    and KeyError on missing keys.

    IMPORTANT: assignment to a key not present at construction time
    raises KeyError, mirroring the real QgsFeature behaviour (fields
    must be declared on the layer's schema). This is stricter than a
    plain dict — the original Phase 4b tests used a dict-based fake
    that silently accepted new keys, which masked the bug fixed on
    the fix-is-test-site-write-keyerror branch (KeyError on save
    against a pre-v1b .alaqs whose shapes_area_sources layer has no
    is_test_site field).
    """

    def __init__(self, data: dict = None):
        self._data = dict(data or {})

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        if key not in self._data:
            raise KeyError(key)
        self._data[key] = value

    def __contains__(self, key):
        return key in self._data


class _FakeFeatureLegacyDict:
    """Loose dict-like fake, kept for the ONE test that intentionally
    exercises a feature whose field set is unknown at construction time
    (e.g. a study created on the current schema where every field is
    present). Real QgsFeature would allow the assignment in that case
    because the field is declared on the layer.
    """

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
    result = write_is_test_site_to_feature(cb, feature)
    assert feature["is_test_site"] == "1"
    assert result is True


def test_write_writes_0_when_unchecked():
    feature = _FakeFeature({"is_test_site": "1"})
    cb = _FakeCheckbox(checked=False)
    result = write_is_test_site_to_feature(cb, feature)
    assert feature["is_test_site"] == "0"
    assert result is True


def test_write_returns_false_when_field_absent_no_crash(caplog):
    """A pre-v1b .alaqs whose shapes_area_sources layer has no
    is_test_site field: assignment raises KeyError. The helper must
    catch it, log a WARNING pointing at migrate_alaqs.py, and return
    False so callers know the state wasn't persisted.

    This test would have caught the KeyError-on-save bug reported
    against Phase 4b if the original tests hadn't used a dict-based
    fake that permissively accepted new keys.
    """
    import logging

    feature = _FakeFeature({})  # NO is_test_site field
    cb = _FakeCheckbox(checked=True)

    with caplog.at_level(logging.WARNING):
        result = write_is_test_site_to_feature(cb, feature)

    assert result is False
    # The field is NOT added; the feature is unchanged.
    assert "is_test_site" not in feature
    # The WARNING mentions the migration command.
    assert any("migrate_alaqs" in rec.message for rec in caplog.records)


def test_write_still_works_on_a_present_but_null_field():
    """After migrate_alaqs.py runs, the field exists with NULL. The
    write should succeed (setting the string value replaces the NULL)."""
    feature = _FakeFeature({"is_test_site": None})
    cb = _FakeCheckbox(checked=True)
    result = write_is_test_site_to_feature(cb, feature)
    assert result is True
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
