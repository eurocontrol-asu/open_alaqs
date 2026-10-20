"""nvPM and MEEM V1 columns of the shipped default_aircraft_engine_ei.

- nvpm_number_ei is a number emission index (#/kg fuel). Until October 2026
  the column held the ACT_PRF number rate (#/s) of the mode.
- press_ratio and the 5th MEEM point come from the CAEP14 FBE calculation
  sheet v14 (Engines_Database, EEDB v31), ACT_PRF for engines not in it.
- 1ZM001 (D-36) TX carries the ACT_PRF idle fuel flow and EIs (the EEDB has
  FF_ID 0).
The template project.alaqs carries the same values.
"""

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
CSV = REPO / "open_alaqs/database/data/default_aircraft_engine_ei.csv"
TEMPLATE = REPO / "open_alaqs/core/templates/project.alaqs"

# NVPM_N_<TO|CO|AP|ID>_N/KG of the sheet's Engines_Database
_SHEET_NUMBER = {
    "01P20CM127": (
        107147000375.795,
        92348579066.5577,
        276096126031350,
        13005424535946.3,
    ),
    "01P20CM128": (
        119654243894.608,
        100052658632.405,
        456827575055365,
        10901015768971.4,
    ),
    "11GE144": (464865790499195, 336013571246026, 141052815153605, 268931995685205),
}
_JETS_WITHOUT_OPR = {
    "B004",
    "B134",
    "B601",
    "B602",
    "B603",
    "ECTL_2",
    "ECTL_4",
    "ECTL_6",
    "ECTL_7",
    "ECTL_8",
    "ECTL_10",
    "ECTL_12",
    "ECTL_13",
}


@pytest.fixture(scope="module")
def ei():
    return pd.read_csv(CSV)


def test_number_ei_is_per_kg(ei):
    """The sheet's #/kg values, not the ACT_PRF rate (#/s)."""
    for engine, values in _SHEET_NUMBER.items():
        rows = ei[ei.engine_name == engine].set_index("mode")
        for mode, sheet in zip(("TO", "CL", "AP", "TX"), values):
            assert rows.loc[mode, "nvpm_number_ei"] == pytest.approx(sheet, rel=1e-8)
            rate = sheet * rows.loc[mode, "fuel_kg_sec"]
            assert rows.loc[mode, "nvpm_number_ei"] != pytest.approx(rate, rel=1e-3)


def test_number_ei_plausible_range(ei):
    """Non-zero number EIs lie between 1e9 and 1e17 #/kg (the lowest, about
    7e9, are lean-burn engines at TO and CL, as in the EEDB)."""
    nz = ei[ei.nvpm_number_ei > 0]
    assert len(nz) > 3000
    assert nz.nvpm_number_ei.min() > 1e9
    assert nz.nvpm_number_ei.max() < 1e17
    assert (ei.loc[ei.nvpm_number_ei > 0, "fuel_kg_sec"] > 0).all()


def test_press_ratio_coverage(ei):
    engines = ei.groupby("engine_name")
    assert (engines.press_ratio.nunique(dropna=False) == 1).all()
    first = engines.first()
    jets = first[first.engine_type == "J"]
    with_opr = jets[jets.press_ratio.notna()]
    assert len(with_opr) == 863
    assert (with_opr.press_ratio > 0).all()
    assert set(jets.index[jets.press_ratio.isna()]) == _JETS_WITHOUT_OPR
    assert first[first.engine_type != "J"].press_ratio.isna().all()
    assert first.loc["01P20CM128", "press_ratio"] == pytest.approx(33.3)
    assert first.loc["11GE144", "press_ratio"] == pytest.approx(27.2)


def test_fifth_point(ei):
    first = ei.groupby("engine_name").first()
    m5 = first[first.meem_nvpm_m_i_f00_avg > 0]
    n5 = first[first.meem_nvpm_n_i_f00_avg > 0]
    assert len(m5) == 51 and len(n5) == 51
    assert m5.nvpm_m_max_mgkg.notna().all() and n5.nvpm_n_max_nkg.notna().all()
    # GE9X: 5th point in the sheet (ACT_PRF has none)
    assert first.loc["GE9X", "meem_nvpm_m_i_f00_avg"] > 0
    assert first.loc["GE9X", "meem_nvpm_n_i_f00_avg"] == pytest.approx(0.575)


def test_1zm001_idle(ei):
    tx = ei[(ei.engine_name == "1ZM001") & (ei["mode"] == "TX")].iloc[0]
    assert tx.fuel_kg_sec == pytest.approx(0.092)
    assert tx.nox_ei == pytest.approx(5.5)
    assert tx.co_ei == pytest.approx(20.7)
    assert tx.hc_ei == pytest.approx(5.4)
    assert tx.pm10_nonvol == pytest.approx(0.076674, rel=1e-5)
    assert tx.nvpm_ei == tx.pm10_nonvol
    assert tx.nvpm_number_ei == pytest.approx(3.8668170410e15, rel=1e-9)
    assert tx.pm10_ei == pytest.approx(
        tx.pm10_nonvol + tx.pm10_sul + tx.pm10_organic, rel=1e-5
    )
    assert tx.p1_ei == tx.pm10_ei and tx.p2_ei == tx.pm10_ei
    assert tx.sox_ei == pytest.approx(0.75834)


def test_template_matches_csv(ei):
    cols = ["nvpm_number_ei", "press_ratio", "meem_nvpm_m_i_f00_avg", "fuel_kg_sec"]
    with sqlite3.connect(TEMPLATE) as conn:
        db = pd.read_sql(
            "SELECT engine_name, mode, " + ", ".join(cols) + " FROM "
            "default_aircraft_engine_ei",
            conn,
        )
    key = ["engine_name", "mode"]
    merged = ei[key + cols].merge(db, on=key, suffixes=("", "_db"))
    assert len(merged) == len(ei)
    for c in cols:
        a, b = merged[c], pd.to_numeric(merged[c + "_db"])
        same = (a.isna() & b.isna()) | ((a - b).abs() <= 1e-12 * a.abs())
        assert same.all(), c
