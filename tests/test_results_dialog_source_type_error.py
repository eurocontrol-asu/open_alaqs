"""The Source type list of the results dialog reports a study input error.

`OpenAlaqsResultsAnalysis.source_type_changed` is a Qt slot: choosing
"MovementSource" builds a MovementStore, which raises on the same input
errors as the calculation (a runway designator that matches several or no
runway end, an unknown gate or engine). An exception out of a slot is a raw
QGIS Python error dialog, so the slot now reports it in the message bar, as
`update_emissions` does ("Calculation Failed"), and leaves the names list at
"all" (rc7 review R3).
"""

import sqlite3
from unittest import mock

import pytest
from qgis.testing import start_app
from qgis.testing.mocked import get_iface

from openalaqs_standalone.validation.tests.test_parallel_runways import (
    SRC,
    make_parallel,
)

start_app()


@pytest.fixture(autouse=True)
def _restore_project_database():
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.tools.Singleton import Singleton

    previous = getattr(ProjectDatabase(), "path", None)
    Singleton.reset_all()
    yield
    Singleton.reset_all()
    ProjectDatabase().path = previous


@pytest.fixture(scope="module")
def plugin():
    from open_alaqs.openalaqs import OpenALAQS

    instance = OpenALAQS(get_iface())
    yield instance
    instance.unload()


def _dialog(plugin, inventory):
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.openalaqsdialog import OpenAlaqsResultsAnalysis

    ProjectDatabase().path = str(inventory)
    dlg = OpenAlaqsResultsAnalysis(plugin.iface)
    dlg.result_file_path_changed(str(inventory))
    dlg.ui.result_file_path.setFilePath(str(inventory))
    return dlg


def _select(dlg, source_type):
    index = dlg.ui.source_types.findText(source_type)
    assert index >= 0, [
        dlg.ui.source_types.itemText(i) for i in range(dlg.ui.source_types.count())
    ]
    with mock.patch.object(dlg.message_bar, "pushWarning") as push:
        dlg.ui.source_types.setCurrentIndex(index)
        if dlg.ui.source_types.currentIndex() == index:
            dlg.source_type_changed()  # the signal fired already or not at all
    return push


def test_ambiguous_runway_is_reported_in_the_message_bar(plugin, tmp_path):
    db = make_parallel(SRC, tmp_path / "parallel.alaqs")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE user_aircraft_movements SET runway = '24' WHERE oid = 1")
    dlg = _dialog(plugin, db)
    push = _select(dlg, "MovementSource")  # must not raise out of the slot
    assert push.call_count >= 1
    title, text = push.call_args[0]
    assert title == "Invalid Study Input"
    assert "runway '24' matches 06L/24R and 06R/24L" in text
    assert [
        dlg.ui.source_names.itemText(i) for i in range(dlg.ui.source_names.count())
    ] == ["all"]


def test_valid_study_lists_the_movements(plugin, tmp_path):
    db = tmp_path / "single.alaqs"
    db.write_bytes(SRC.read_bytes())
    dlg = _dialog(plugin, db)
    push = _select(dlg, "MovementSource")
    assert push.call_count == 0
    names = [
        dlg.ui.source_names.itemText(i) for i in range(dlg.ui.source_names.count())
    ]
    assert names[0] == "all" and len(names) > 1
