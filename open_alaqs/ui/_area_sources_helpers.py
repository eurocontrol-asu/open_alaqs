"""Small helpers shared by ``ui_area_sources.py``.

Kept dependency-free (no qgis, no plugin imports) so unit tests can
exercise them without a QGIS session or the full plugin import chain.
"""

from __future__ import annotations


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


def write_is_test_site_to_feature(checkbox, feature) -> None:
    """Write the checkbox state back to ``feature["is_test_site"]`` as
    the TEXT ``'1'`` or ``'0'`` matching the DB column type.

    ``AreaSources.isTestSite()`` reads by string comparison so the
    integer/text distinction matters for round-trip consistency.
    """
    feature["is_test_site"] = str(int(checkbox.isChecked()))


__all__ = [
    "seed_is_test_site_from_feature",
    "write_is_test_site_to_feature",
]
