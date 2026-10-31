"""populate_routes warns about missing routes only when the study has none."""

import logging
from types import SimpleNamespace
from unittest import mock

from open_alaqs import openalaqsdialog


class _Combo:
    def __init__(self):
        self.items = []
        self.current = None

    def clear(self):
        self.items = []

    def addItem(self, text):
        self.items.append(text)

    def findText(self, text):
        return self.items.index(text) if text in self.items else -1

    def setCurrentIndex(self, i):
        self.current = i


def _run(routes, select_name, caplog):
    fake = SimpleNamespace(ui=SimpleNamespace(routes=_Combo()))
    with mock.patch.object(
        openalaqsdialog.alaqs, "get_taxiway_routes", return_value=routes
    ), caplog.at_level(logging.DEBUG):
        openalaqsdialog.OpenAlaqsTaxiRoutes.populate_routes(fake, select_name)
    return fake.ui.routes, [r.getMessage() for r in caplog.records]


def test_routes_present_without_selection_does_not_warn(caplog):
    combo, messages = _run([(1, "G2", "G2/24/D/1")], None, caplog)
    assert combo.items == ["G2/24/D/1"]
    assert not any("No routes defined" in m for m in messages)


def test_no_routes_warns(caplog):
    combo, messages = _run(None, None, caplog)
    assert combo.items == []
    assert any("No routes defined" in m for m in messages)


def test_selection_is_applied(caplog):
    combo, _ = _run([(1, "a", "R1"), (2, "b", "R2")], "R2", caplog)
    assert combo.current == 1
