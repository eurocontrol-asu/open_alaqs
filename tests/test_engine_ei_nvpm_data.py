"""nvPM and MEEM V1 columns of the shipped default_aircraft_engine_ei.

- nvpm_number_ei is a number emission index (#/kg fuel). Until October 2026
  the column held the ACT_PRF number rate (#/s) of the mode.
- press_ratio and the 5th MEEM point come from the CAEP14 FBE calculation
  sheet v14 (Engines_Database, EEDB v31), ACT_PRF for engines not in it.
- 28 ACT_PRF engines without a twin in the table were added in October
  2026 (08P28CM141 to 156, 08P28RR154 to 163, EEA-J9, EEA-J10); E190's
  default engine is EEA-J10 (ACT_PRF aircraft_engine E190-A). The other 48
  ACT_PRF engines missing from the table are duplicates of rows under other
  ids and are not added.
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
    "EEA-J9",
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
    assert len(with_opr) == 890
    assert (with_opr.press_ratio > 0).all()
    assert set(jets.index[jets.press_ratio.isna()]) == _JETS_WITHOUT_OPR
    assert first[first.engine_type != "J"].press_ratio.isna().all()
    assert first.loc["01P20CM128", "press_ratio"] == pytest.approx(33.3)
    assert first.loc["11GE144", "press_ratio"] == pytest.approx(27.2)


def test_fifth_point(ei):
    first = ei.groupby("engine_name").first()
    m5 = first[first.meem_nvpm_m_i_f00_avg > 0]
    n5 = first[first.meem_nvpm_n_i_f00_avg > 0]
    assert len(m5) == 77 and len(n5) == 75
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


_NEW_ENGINES = (
    [f"08P28CM{i}" for i in range(141, 157)]
    + [f"08P28RR{i}" for i in range(154, 164)]
    + ["EEA-J9", "EEA-J10"]
)
# ACT_PRF ids that duplicate rows already in the table (not added)
_DUPLICATES = (
    ["01P21RR124", "EEA-J6", "EEA-P1"]
    + [f"EEA-J{i}" for i in (1, 2, 3, 4, 5, 7, 8, 15)]
    + [f"EEA-T{i}" for i in range(1, 16)]
    + [f"FOCA-{i}" for i in range(1, 23)]
)


def test_new_engines_present(ei):
    rows = ei[ei.engine_name.isin(_NEW_ENGINES)]
    assert len(rows) == 4 * len(_NEW_ENGINES) == 112
    for eng, g in rows.groupby("engine_name"):
        assert sorted(g["mode"]) == ["AP", "CL", "TO", "TX"], eng
        assert dict(zip(g["mode"], g.thrust)) == {
            "TO": 1.0,
            "CL": 0.85,
            "AP": 0.3,
            "TX": 0.07,
        }
    assert (rows.engine_type == "J").all() and (rows.fuel_type == "Jet Fuel").all()
    assert (rows.source == "ACT_PRF (CAEP14/ICAO EEDB)").all()
    assert (rows.sox_ei == 0.75834).all()
    assert ei.oid.is_unique


def test_new_engines_values():
    """Per-kg values: ACT_PRF rate / fuel flow (PM: 6 significant digits of
    the rate), for two of the engines (ACT_PRF ENGINE_LTO_VALUES)."""
    ei = pd.read_csv(CSV).set_index(["engine_name", "mode"])
    # (engine, mode): fuel kg/s, NOx kg/s, nvPM mass kg/s, nvPM number #/s
    ref = {
        ("EEA-J10", "TX"): (0.081, 0.0002916, 0.000001340361199, 67596973715000),
        ("EEA-J10", "TO"): (0.779, 0.0172159, 0.000378425371466, 2385589226100000),
    }
    for key, (fuel, nox, mass, number) in ref.items():
        r = ei.loc[key]
        assert r.fuel_kg_sec == pytest.approx(fuel, rel=1e-12)
        assert r.nox_ei == pytest.approx(nox * 1000.0 / fuel, rel=1e-9)
        assert r.pm10_nonvol == pytest.approx(
            float("%.6g" % mass) * 1000.0 / fuel, rel=1e-12
        )
        assert r.nvpm_number_ei == pytest.approx(number / fuel, rel=1e-12)
        assert r.pm10_ei == pytest.approx(
            r.pm10_nonvol + r.pm10_sul + r.pm10_organic, rel=1e-5
        )
        assert r.p1_ei == r.pm10_ei and r.p2_ei == r.pm10_ei
        assert r.nvpm_ei == r.pm10_nonvol
    first = ei.reset_index().groupby("engine_name").first()
    assert first.loc["EEA-J10", "press_ratio"] == pytest.approx(29.0)
    assert pd.isna(first.loc["EEA-J9", "press_ratio"])
    assert first.loc["08P28RR154", "meem_nvpm_m_i_f00_avg"] == pytest.approx(0.575)
    assert first.loc["08P28CM149", "meem_nvpm_n_i_f00_avg"] == 0.0


def test_duplicates_not_added(ei):
    assert len(_DUPLICATES) == 48
    assert not ei.engine_name.isin(_DUPLICATES).any()


def test_e190_default_engine():
    ac = pd.read_csv(REPO / "open_alaqs/database/data/default_aircraft.csv")
    e190 = ac[ac.icao == "E190"].iloc[0]
    assert e190.engine == "EEA-J10" and e190.engine_name == "EEA-J10"
    assert int(e190.engine_count) == 2
    with sqlite3.connect(TEMPLATE) as conn:
        assert conn.execute(
            "SELECT engine, engine_name FROM default_aircraft WHERE icao='E190'"
        ).fetchone() == ("EEA-J10", "EEA-J10")
        n = conn.execute(
            "SELECT COUNT(*) FROM default_aircraft_engine_ei WHERE engine_name=?",
            ("EEA-J10",),
        ).fetchone()[0]
    assert n == 4


_FOCA = (
    ["P001", "P002", "P003", "P004", "P011", "P111", "P121", "P131"]
    + [f"PF{i:02d}" for i in range(1, 15)]
    + ["B601", "B602", "B603", "B004", "B134"]
    + ["T601", "T602", "T603", "T717", "T790"]
)
_FOCA_SOURCE = "ACT_PRF 2.6.3 (CAEP14 FOCA 2026-10-09)"


def test_foca_engines_from_act_prf_2_6_3(ei):
    rows = ei[ei.engine_name.isin(_FOCA)]
    assert len(rows) == 4 * len(_FOCA) == 128
    assert (rows.source == _FOCA_SOURCE).all()
    assert (ei.source == _FOCA_SOURCE).sum() == 128
    for c in (
        "press_ratio",
        "meem_nvpm_m_i_f00_avg",
        "meem_nvpm_n_i_f00_avg",
        "nvpm_m_max_mgkg",
        "nvpm_n_max_nkg",
    ):
        assert rows[c].isna().all(), c


def test_foca_values():
    """B601 TO, B004 and P001 TX: rate / fuel of ACT_PRF 2.6.3 (CAEP14 FOCA,
    2026-10-09). B004 and B134 take the file's sulphate and organic vPM
    (their parts sum to PMtotal); B601 to B603 keep 0 (the file's parts
    exceed PMtotal for them)."""
    ei = pd.read_csv(CSV).set_index(["engine_name", "mode"])
    b = ei.loc[("B601", "TO")]
    assert b.fuel_kg_sec == pytest.approx(0.121)
    assert b.pm10_ei == pytest.approx(0.25, rel=1e-9)
    for e in ("B601", "B602", "B603"):
        g = ei.loc[e]
        assert (g.pm10_sul == 0.0).all() and (g.pm10_organic == 0.0).all(), e
    for e in ("B004", "B134"):
        g = ei.loc[e]
        assert (g.pm10_sul > 0).all(), e
        parts = g.pm10_nonvol + g.pm10_sul + g.pm10_organic
        assert ((parts - g.pm10_ei).abs() <= 1e-5 * g.pm10_ei).all(), e
    assert b.nvpm_number_ei == pytest.approx(8.83e13 / 0.121, rel=1e-9)
    p = ei.loc[("P001", "TX")]
    assert p.fuel_kg_sec == pytest.approx(0.0012)
    assert p.pm10_sul == 0.0 and p.pm10_organic == 0.0


def test_foca_turboprops_burn_jet_fuel(ei):
    """FOCA turboprops: jet fuel and its SOx EI; no turboprop is AvGas."""
    tp = ei[ei.engine_name.isin(["T601", "T602", "T603", "T717", "T790"])]
    assert len(tp) == 20
    assert (tp.fuel_type == "Jet Fuel").all()
    assert (tp.sox_ei == 0.75834).all()
    assert not (ei[ei.engine_type == "T"].fuel_type == "AvGas").any()
