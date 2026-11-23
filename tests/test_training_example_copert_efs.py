"""
Regression test: the parking and roadway emission factors stored in the
shipped training example must equal what **Recalculate** gives today.

The tutorial (documents/user/TUTORIAL_ROTTERDAM.md) tells the user to click
Recalculate on the ParkingLot and the Roadway and quotes the result. Until
this test, both example files kept factors computed before the 5.1.2
parking travel-distance fix (metres read as kilometres) and before the
COPERT 5 data review, e.g. parking CO 54.66 g/vehicle where Recalculate
gives 0.174. A trainee who followed the tutorial then missed every parking
and roadway value of training_validation_reference.xlsx.

The test recomputes the factors with the same function the forms call
(copert5.roadway_emission_factors, study setup of the file) and compares
them with the stored columns of training.alaqs and training_out.alaqs. If
COPERT data or the method change on purpose, recompute the factors in both
files and rebuild the example workbook (see
openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md).
"""

import shutil
import sqlite3
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from open_alaqs.core import alaqs  # noqa: E402
from open_alaqs.core.alaqsdblite import ProjectDatabase  # noqa: E402
from open_alaqs.core.tools import copert5  # noqa: E402
from open_alaqs.core.tools.copert5_utils import VEHICLE_CATEGORIES  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[1] / "example" / "training"
POLLUTANTS = ("co", "hc", "nox", "sox", "pm10", "p1", "p2")
FLEET = (
    "pc_p_percentage",
    "pc_d_percentage",
    "lcv_p_percentage",
    "lcv_d_percentage",
    "hdt_p_percentage",
    "hdt_d_percentage",
    "motorcycle_p_percentage",
    "bus_d_percentage",
)
SOURCES = (
    # table, key column, parking?, unit suffix of the stored factors
    ("shapes_parking", "parking_id", True, "gm_vh"),
    ("shapes_roadways", "roadway_id", False, "gm_km"),
)


def _stored_and_recomputed(db_path):
    saved = getattr(ProjectDatabase(), "path", None)
    ProjectDatabase().path = str(db_path)
    try:
        study = alaqs.load_study_setup()
        euro = alaqs.get_roadway_euro_standards(
            study["roadway_country"], study["roadway_fleet_year"]
        )
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        out = []
        for table, key, parking, unit in SOURCES:
            for row in conn.execute(f"SELECT * FROM {table}").fetchall():
                form = {
                    "name": row[key],
                    "height": row["height"],
                    "speed": row["speed"],
                    "parking": parking,
                }
                if parking:
                    form.update(
                        vehicle_year=row["vehicle_year"],
                        idle_time=float(row["idle_time"]),
                        travel_distance=float(row["distance"]),
                    )
                for field in FLEET:
                    form[field] = float(row[field])
                for short, category in VEHICLE_CATEGORIES.items():
                    form[f"{short}_euro_standard"] = euro[category]
                ef = copert5.roadway_emission_factors(form, study)
                for p in POLLUTANTS:
                    out.append(
                        (f"{table}:{row[key]}:{p}", row[f"{p}_{unit}"], ef[f"{p}_ef"])
                    )
        conn.close()
        return out
    finally:
        if saved is not None:
            ProjectDatabase().path = saved


@pytest.mark.parametrize("name", ["training.alaqs", "training_out.alaqs"])
def test_stored_copert_factors_match_recalculate(name, tmp_path):
    db = tmp_path / name
    shutil.copy(EXAMPLE / name, db)
    rows = _stored_and_recomputed(db)
    assert len(rows) == 2 * len(POLLUTANTS), "expected one parking and one roadway"
    stale = [
        (what, stored, fresh)
        for what, stored, fresh in rows
        if stored != pytest.approx(fresh, rel=1e-9, abs=1e-15)
    ]
    assert not stale, f"stored factors differ from Recalculate: {stale}"
