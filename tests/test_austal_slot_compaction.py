"""Unit tests for AUSTALDispersionModule._ti_compact_legacy_slots.

Regression guard for the bug where a selected pollutant with zero total
emissions, positioned BEFORE a non-zero pollutant, left an interior hole
in the source-slot numbering (e.g. surviving slots 01,02,03,04,06 after a
zero-SOx slot 05 was dropped). AUSTAL enumerates grid source directories
sequentially from the source-column count in austal.txt, so the hole made
it look for a directory that was never created and abort with:

    The grid source directory '.../05' is missing!
    AUSTAL terminated because of invalid input.

These tests do not require QGIS. They build a bare module instance with
object.__new__ and populate only the slot-keyed state the method touches,
plus a temporary output directory for the directory-rename step.

Run from the openalaqs repo root:
    pytest tests/test_austal_slot_compaction.py -v
"""

from collections import OrderedDict
from pathlib import Path

from open_alaqs.core.modules.AUSTALOutputModule import AUSTALDispersionModule


def _make_module(out_dir, survivor_ids):
    """Build a bare module with the minimal slot-keyed state populated
    for the given surviving slot ids, plus on-disk directories for each.
    """
    mod = object.__new__(AUSTALDispersionModule)
    mod._total_sources = OrderedDict((sid, ["x"]) for sid in survivor_ids)
    mod._timeID_per_source = OrderedDict((sid, 1) for sid in survivor_ids)
    mod._gridfile_written = {sid: {1} for sid in survivor_ids}
    mod._results = {
        "2025-06-01:01": {sid: {"x": 1.0, "timeID": 1} for sid in survivor_ids}
    }
    # getOutputPathAsPath() is the only path accessor the method uses.
    out = Path(out_dir)
    mod.getOutputPathAsPath = lambda: out
    for sid in survivor_ids:
        (out / sid).mkdir(parents=True, exist_ok=True)
    return mod


def _dirs(out_dir):
    return sorted(
        p.name
        for p in Path(out_dir).iterdir()
        if p.is_dir() and not p.name.endswith("__compact_tmp")
    )


def test_interior_hole_is_closed(tmp_path):
    """The user's exact case: SOx slot 05 dropped, survivors
    01,02,03,04,06. CO2 (06) must be renamed to 05 so directories,
    _total_sources and series/austal stay contiguous 01..05.
    """
    mod = _make_module(tmp_path, ["01", "02", "03", "04", "06"])
    mod._ti_compact_legacy_slots()

    assert list(mod._total_sources.keys()) == ["01", "02", "03", "04", "05"]
    assert _dirs(tmp_path) == ["01", "02", "03", "04", "05"]
    # All slot-keyed state moved in lockstep.
    assert sorted(mod._timeID_per_source.keys()) == ["01", "02", "03", "04", "05"]
    assert sorted(mod._gridfile_written.keys()) == ["01", "02", "03", "04", "05"]
    res_slots = sorted(k for k in mod._results["2025-06-01:01"] if k != "timeID")
    assert res_slots == ["01", "02", "03", "04", "05"]


def test_two_holes_are_closed(tmp_path):
    """Slots 03 and 05 dropped: survivors 01,02,04,06 -> 01,02,03,04."""
    mod = _make_module(tmp_path, ["01", "02", "04", "06"])
    mod._ti_compact_legacy_slots()

    assert list(mod._total_sources.keys()) == ["01", "02", "03", "04"]
    assert _dirs(tmp_path) == ["01", "02", "03", "04"]


def test_contiguous_is_noop(tmp_path):
    """Already contiguous survivors (no dropped slot, or last-slot
    dropped) must be left untouched - preserves bit-identical output.
    """
    mod = _make_module(tmp_path, ["01", "02"])
    # Snapshot identity of state objects to prove no rebuild happened.
    ts_before = mod._total_sources
    mod._ti_compact_legacy_slots()

    assert list(mod._total_sources.keys()) == ["01", "02"]
    assert _dirs(tmp_path) == ["01", "02"]
    # No remap => the original dict object is retained (no rebuild).
    assert mod._total_sources is ts_before


def test_single_survivor_renumbered_to_01(tmp_path):
    """A lone survivor at 04 (everything before it dropped) -> 01."""
    mod = _make_module(tmp_path, ["04"])
    mod._ti_compact_legacy_slots()

    assert list(mod._total_sources.keys()) == ["01"]
    assert _dirs(tmp_path) == ["01"]


def test_empty_total_sources_is_safe(tmp_path):
    """No legacy slots at all (all-stationary run) must not raise."""
    mod = _make_module(tmp_path, [])
    # Remove the directories created for an empty list (none) and call.
    mod._ti_compact_legacy_slots()
    assert list(mod._total_sources.keys()) == []
