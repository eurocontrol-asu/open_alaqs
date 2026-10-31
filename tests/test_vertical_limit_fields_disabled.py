"""The two Vertical Limit fields have no effect and are shown disabled.

The LTO ceiling is the period's MixingHeight, 914.4 m when it is empty
(AmbientCondition default). MovementSourceModule.process uses the
vertical_limit_m it is given only on AttributeError, which cannot happen:
EmissionCalculation always passes an AmbientCondition. The study setup's
vertical_limit is stored but never read by the calculation.
"""

import datetime
import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from qgis.testing import start_app
from qgis.testing.mocked import get_iface

start_app()

from open_alaqs.core.alaqsdblite import ProjectDatabase  # noqa: E402
from open_alaqs.core.EmissionCalculatorService import (  # noqa: E402
    EmissionCalculationConfig,
    EmissionCalculatorService,
)
from open_alaqs.openalaqsdialog import (  # noqa: E402
    VERTICAL_LIMIT_UNUSED_TOOLTIP,
    OpenAlaqsResultsAnalysis,
    OpenAlaqsStudySetup,
)
from tests.utils import get_data_path  # noqa: E402

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)


@pytest.fixture(autouse=True)
def _isolate_singletons():
    from open_alaqs.core.alaqsdblite import Singleton

    saved_path = getattr(ProjectDatabase(), "path", None)
    saved_instances = dict(Singleton._instances)
    Singleton._instances.clear()
    try:
        yield
    finally:
        Singleton._instances.clear()
        Singleton._instances.update(saved_instances)
        if saved_path is not None:
            ProjectDatabase().path = saved_path


def _grab(widget, name):
    try:
        widget.grab().save(f"/tmp/C_{name}.png")
    except Exception:
        pass


def test_study_setup_vertical_limit_disabled(tmp_path):
    db = tmp_path / "AIRPORT_A.alaqs"
    shutil.copy(get_data_path("AIRPORT_A") / "AIRPORT_A.alaqs", db)
    ProjectDatabase().path = str(db)
    dlg = OpenAlaqsStudySetup(get_iface())
    spin = dlg.ui.spinBoxVerticalLimit
    assert not spin.isEnabled()
    assert spin.toolTip() == VERTICAL_LIMIT_UNUSED_TOOLTIP
    # the stored value is still loaded (schema compatibility)
    assert spin.value() == pytest.approx(914.4)
    dlg.show()
    _grab(dlg, "study_setup")


def test_configuration_tab_vertical_limit_disabled():
    ProjectDatabase().path = str(get_data_path("AIRPORT_A") / "AIRPORT_A.alaqs")
    dlg = OpenAlaqsResultsAnalysis(get_iface())
    widget = dlg._emission_calculation_configuration_widget
    spin = widget.get_widget("vertical_limit_m")
    assert not spin.isEnabled()
    assert spin.toolTip() == VERTICAL_LIMIT_UNUSED_TOOLTIP
    assert widget.get_values()["vertical_limit_m"] == 914.4
    dlg.show()
    _grab(widget, "configuration_tab")


def _plugin_nox_total(db, vertical_limit_m):
    with sqlite3.connect(db) as conn:
        g = conn.execute(
            "SELECT x_cells, y_cells, z_cells, x_resolution, y_resolution, z_resolution, "
            "reference_latitude, reference_longitude FROM grid_3d_definition"
        ).fetchone()
    keys = [
        "x_cells",
        "y_cells",
        "z_cells",
        "x_resolution",
        "y_resolution",
        "z_resolution",
        "reference_latitude",
        "reference_longitude",
    ]
    ProjectDatabase().path = db
    result = EmissionCalculatorService().calculate_emissions(
        EmissionCalculationConfig(
            db_path=db,
            pollutant="NOx",
            source_type="movements",
            grid_config=dict(zip(keys, g), reference_altitude=0.0),
            method="bymode",
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 4, 0),
            time_interval=timedelta(seconds=3600),
            vertical_limit_m=vertical_limit_m,
        )
    )
    assert result.success, result.error_message
    return sum(
        e.transposeToKilograms().getObject("nox_kg") or 0.0
        for period in result.emissions_data.values()
        for _, emissions in period
        for e in emissions
    )


def test_vertical_limit_values_have_no_effect(tmp_path):
    """Neither field changes the result, even with no MixingHeight."""
    if not FIXTURE.exists():
        pytest.skip(f"fixture not found: {FIXTURE}")
    db = str(tmp_path / "training.alaqs")
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE tbl_InvMeteo SET MixingHeight = NULL")
        conn.commit()
    reference = _plugin_nox_total(db, 914.4)
    from open_alaqs.core.alaqsdblite import Singleton

    Singleton._instances.clear()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE user_study_setup SET vertical_limit = 300")
        conn.commit()
    assert reference > 0.0
    assert _plugin_nox_total(db, 300.0) == pytest.approx(reference, rel=1e-12)
