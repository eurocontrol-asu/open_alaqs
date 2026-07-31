"""Small helpers shared by ``ui_area_sources.py``.

Kept dependency-free (no qgis, no plugin imports) so unit tests can
exercise them without a QGIS session or the full plugin import chain.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def seed_is_test_site_from_feature(checkbox, feature) -> None:
    """Read ``feature["is_test_site"]`` and set the checkbox state.

    Tolerated shapes for the field value:
      * ``'1'`` (or trimmed whitespace equivalent, or integer 1) → checked
      * anything else (``'0'``, NULL/None, empty string, unexpected
        values) → unchecked
      * KeyError (pre-v1b schema without the column) → unchecked

    ``checkbox`` must have ``.setChecked(bool)``. ``feature`` must
    support ``feature[key]`` reads with KeyError on missing keys.
    """
    try:
        raw = feature["is_test_site"]
    except (KeyError, IndexError):
        checkbox.setChecked(False)
        return
    if raw is None:
        checkbox.setChecked(False)
        return
    checkbox.setChecked(str(raw).strip() == "1")


def write_is_test_site_to_feature(checkbox, feature) -> bool:
    """Write the checkbox state back to ``feature["is_test_site"]`` as
    the TEXT ``'1'`` or ``'0'`` matching the DB column type.

    ``AreaSources.isTestSite()`` reads by string comparison so the
    integer/text distinction matters for round-trip consistency.

    Returns True if the write succeeded, False if the feature layer
    doesn't have the ``is_test_site`` field. The False case happens
    when the ``.alaqs`` study was created (or last opened by) a plugin
    version older than v1b, before ``is_test_site`` was added to
    ``shapes_area_sources``. In that case the write is silently skipped
    (rather than raising KeyError and crashing the save), and a WARNING
    is logged pointing at ``scripts/migrate_alaqs.py``.

    Real ``QgsFeature`` objects only accept assignment to fields that
    are declared on their layer's schema; assignment to a missing field
    raises KeyError. This is different from a plain dict, which was the
    stand-in used in the Phase 4b unit tests — hence the original tests
    passed but a real QGIS session with a legacy ``.alaqs`` raised
    KeyError on save (see hotfix branch fix-is-test-site-write-keyerror).
    """
    try:
        feature["is_test_site"] = str(int(checkbox.isChecked()))
        return True
    except KeyError:
        _logger.warning(
            "Cannot persist 'is_test_site' checkbox: the feature layer "
            "has no 'is_test_site' field. This means your .alaqs study "
            "was created by a plugin version older than the one that "
            "added engine-test-site support. Migrate the study to gain "
            "the new column:\n"
            "  python scripts/migrate_alaqs.py /path/to/study.alaqs\n"
            "Then close and reopen the project in QGIS. Other edits on "
            "this feature are being saved normally; only the checkbox "
            "state is dropped."
        )
        return False


__all__ = [
    "seed_is_test_site_from_feature",
    "write_is_test_site_to_feature",
]
