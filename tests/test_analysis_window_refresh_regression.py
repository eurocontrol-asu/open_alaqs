"""
Regression test for the Emissions Inventory Analysis window stale-source bug.

Symptom: open the Analysis window with one inventory file (file A), wait
for source list to populate, then change the file picker to file B. The
source-type/source-name dropdowns continue to show file A's content.

Root cause: every Source store (`AreaSourcesStore`, `AircraftStore`,
`AircraftTrajectoryStore`, …) is a `Singleton` via
`open_alaqs.core.tools.Singleton`. The metaclass's `__call__` method
returns the cached instance without ever inspecting the new `db_path`
argument:

    def __call__(cls, *args, **kw):
        if cls.instance is None:
            cls.instance = super(Singleton, cls).__call__(*args, **kw)
        return cls.instance

So `AreaSourcesStore("/path/A.alaqs")` builds the singleton bound to A,
and the next call `AreaSourcesStore("/path/B.alaqs")` returns the same
instance bound to A.

`EmissionCalculation.__init__` calls `Singleton.reset_all()` when the
DB path changes, but that only fires at calculate time -- by then the
user has already picked source types/names from a stale dropdown.

Fix: `result_file_path_changed` (the file-picker callback in the
analysis dialog) now calls `Singleton.reset_all()` and re-binds
`ProjectDatabase().path` before re-populating the source-type combo.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_singleton_reset_all_clears_every_registered_singleton():
    """The mechanism the dialog now uses must actually clear all stores.
    Pinning Singleton.reset_all behaviour so a future refactor that
    breaks the registry pattern fails loud here, not at user-report time."""
    from open_alaqs.core.interfaces.Aircraft import AircraftStore

    # Pick a couple of representative stores and make sure they're in the
    # registry (i.e. the metaclass found them at import time).
    from open_alaqs.core.interfaces.AreaSources import AreaSourcesStore
    from open_alaqs.core.tools.Singleton import Singleton

    assert AreaSourcesStore in Singleton._registry
    assert AircraftStore in Singleton._registry

    # Create a sentinel instance (don't care what's inside; we only
    # need to verify reset clears it).
    AreaSourcesStore.instance = object()
    AircraftStore.instance = object()
    assert AreaSourcesStore.instance is not None
    assert AircraftStore.instance is not None

    Singleton.reset_all()

    assert AreaSourcesStore.instance is None, (
        "Singleton.reset_all() did not clear AreaSourcesStore. "
        "The Analysis-window refresh fix relies on this."
    )
    assert (
        AircraftStore.instance is None
    ), "Singleton.reset_all() did not clear AircraftStore."


def test_result_file_path_changed_calls_singleton_reset():
    """Lock the source line: the dialog handler must invoke
    Singleton.reset_all() when the user picks a new inventory file."""
    src = (REPO / "open_alaqs" / "openalaqsdialog.py").read_text()

    # Find the result_file_path_changed function body
    needle = "def result_file_path_changed(self, path):"
    start = src.find(needle)
    assert start != -1, "result_file_path_changed not found in openalaqsdialog.py"
    # Take the next ~3000 chars; the function is short and the next def
    # comes well within that.
    body = src[start : start + 3000]

    # The function ends at the next "def " at the same indentation; cut there.
    next_def = body.find("\n    def ", 1)
    if next_def != -1:
        body = body[:next_def]

    assert "Singleton.reset_all()" in body, (
        "result_file_path_changed must call Singleton.reset_all() so the "
        "source-listing dropdowns reload from the newly picked file. "
        "Without this, switching the inventory file shows the old file's "
        "sources because every Store is a Singleton that ignores its "
        "db_path argument on subsequent constructs."
    )

    assert "ProjectDatabase()" in body and ".path = path" in body, (
        "result_file_path_changed must also re-bind ProjectDatabase().path "
        "to the newly selected file. ProjectDatabase is itself a Singleton "
        "that's cleared by reset_all(); re-binding its path immediately "
        "ensures the next source_type_changed() picks up the right file "
        "without waiting for a separate project-open event."
    )


def test_singleton_persistent_classes_survive_reset():
    """The reset must NOT clear classes marked persistent (module
    registries populated at import time). Otherwise the dialog reset
    would wipe out the SourceModuleRegistry, breaking the
    populate_source_types() call that immediately follows."""
    from open_alaqs.core.tools.Singleton import Singleton

    # Define a throwaway persistent singleton inside the test
    class FakePersistentRegistry(metaclass=Singleton):
        _singleton_persistent = True

    # Construct the singleton, then reset_all
    inst = FakePersistentRegistry()
    assert inst is not None
    Singleton.reset_all()

    # Persistent class must still have its instance
    assert FakePersistentRegistry.instance is inst, (
        "A class marked _singleton_persistent=True must survive "
        "Singleton.reset_all(). The SourceModuleRegistry depends on this."
    )
