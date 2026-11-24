"""Emissions Inventory Analysis: enabling AUSTAL after an earlier result.

The AUSTAL module runs inside the emission calculation, which the dialog
caches after the first table, plot or map. Only the emission settings
dropped the cache, so ticking "Is Enabled" on the AUSTAL tab after an
earlier result reused the cached calculation: no folder was asked for and
no AUSTAL input file was written. The AUSTAL settings now drop the cache
as the emission settings do.
"""

import os
import shutil
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from qgis.PyQt import QtWidgets  # noqa: E402

from open_alaqs.core.tools.Singleton import Singleton  # noqa: E402
from open_alaqs.openalaqsdialog import OpenAlaqsResultsAnalysis  # noqa: E402

TRAINING_OUT = (
    Path(__file__).resolve().parents[1] / "example" / "training" / "training_out.alaqs"
)


@pytest.fixture(autouse=True)
def _fresh_singletons():
    Singleton.reset_all()
    yield
    Singleton.reset_all()


@pytest.fixture
def asked(tmp_path, monkeypatch):
    """Answer AUSTAL's folder dialog with tmp_path/austal_out; count the asks."""
    calls = []

    def choose_folder(*_args, **_kwargs):
        calls.append(1)
        out = tmp_path / "austal_out"
        os.makedirs(out, exist_ok=True)
        return str(out)

    monkeypatch.setattr(QtWidgets.QFileDialog, "getExistingDirectory", choose_folder)
    return calls


@pytest.fixture
def dialog(tmp_path, monkeypatch, asked):
    inventory = tmp_path / "training_out.alaqs"
    shutil.copy(TRAINING_OUT, inventory)
    # The table result is a dialog: do not show it.
    monkeypatch.setattr(QtWidgets.QDialog, "show", lambda self: None)
    dlg = OpenAlaqsResultsAnalysis(None)
    dlg.ui.result_file_path.setFilePath(str(inventory))
    yield dlg
    dlg.deleteLater()


def _austal_settings(dlg):
    tab = dlg.ui.dispersion_modules_tab_widget
    names = [tab.tabText(i) for i in range(tab.count())]
    return tab.widget(names.index("AUSTAL")).widget()


def test_austal_settings_drop_the_cached_calculation(dialog):
    dialog.outputModuleRequested("TableViewWidgetOutputModule")
    assert dialog._emission_calculation_ is not None

    settings = _austal_settings(dialog)
    settings._settings_widgets["is_enabled"].setChecked(True)
    assert dialog._emission_calculation_ is None

    dialog.outputModuleRequested("TableViewWidgetOutputModule")
    assert dialog._emission_calculation_ is not None
    settings._settings_widgets["roughness_length_m"].setValue(0.5)
    assert dialog._emission_calculation_ is None


def test_austal_enabled_after_a_table_writes_its_input_files(dialog, asked, tmp_path):
    out = tmp_path / "austal_out"
    dialog.outputModuleRequested("TableViewWidgetOutputModule")
    assert asked == []

    _austal_settings(dialog)._settings_widgets["is_enabled"].setChecked(True)
    dialog.outputModuleRequested("TableViewWidgetOutputModule")

    assert asked == [1]
    assert list(dialog._emission_calculation_.getDispersionModules()) == ["AUSTAL"]
    assert (out / "austal.txt").is_file()
    assert (out / "series.dmna").is_file()
