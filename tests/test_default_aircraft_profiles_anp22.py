"""
Checks on the ANP v2.2 aircraft profile catalogue
(`open_alaqs/database/data/default_aircraft_profiles.csv`) and on the default
profiles of `default_aircraft.csv`.

These run on the committed CSVs only; they do not need the ANP tables. The
builder that produced the CSVs is `tools/anp22_profiles/build_anp22_profiles.py`
and the provenance is in `documents/AIRCRAFT_PROFILES_PROVENANCE.md`.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

DATA = Path(__file__).parents[1] / "open_alaqs" / "database" / "data"

# Removed ANP 2.1 profiles.
ANP21_PREFIXES = ("COMJET-", "DHC-2FLT-", "GASEPF-")
GROUP_RE = r"^(JET-(BUSINESS|LARGE|MEDIUM|REGIONAL|SMALL)|PISTON|TURBOPROP)-[AD]-\d+$"

# ANP v2.2 aircraft whose power parameter is RPM: no thrust, power left empty.
RPM_AIRCRAFT = {"CNA206", "CNA20T", "PA28", "PA31"}
# ANP v2.2 aircraft whose power parameter is "CNT (% of Max Static Thrust)".
PCT_AIRCRAFT = {
    "BEC58P", "C130", "C130E", "CNA172", "CNA441", "CVR580", "DC3", "DC6",
    "DHC6", "DHC6QP", "DHC7", "DHC8", "DHC830", "HS748A", "L188", "SD330", "SF340",
}  # fmt: skip

# Aircraft and procedures that exist only in later ANP releases; none of them
# may appear in a table built from ANP v2.2.
LATER_ANP_IDS = (
    "ATR72", "7879", "A320-270N", "A321-270N", "A330-743L",
    "ERJ190-300", "ERJ190-400", "FAL900EX", "G650ER",
)  # fmt: skip

# group -> source profile (see tools/anp22_profiles/build_anp22_profiles.py)
GROUP_SOURCE_SAMPLE = {
    "JET-SMALL-D-4": "A321-232-D-1",
    "JET-LARGE-A-1": "A330-343-A-1",
    "JET-MEDIUM-A-1": "A330-301-A-1",
    "TURBOPROP-D-1": "CNA441-D-1",
    "PISTON-D-1": "CNA172-D-1",
    "PISTON-D-2": "PA31-D-1",
    "TURBOPROP-D-4": "EMB120-D-1",
}


@pytest.fixture(scope="module")
def profiles() -> pd.DataFrame:
    d = pd.read_csv(DATA / "default_aircraft_profiles.csv")
    d["ac"] = d.profile_id.str.replace(r"-[AD]-\d+$", "", regex=True)
    return d


@pytest.fixture(scope="module")
def aircraft() -> pd.DataFrame:
    return pd.read_csv(DATA / "default_aircraft.csv")


def _anp(profiles):
    return profiles


def test_rows_contiguous_and_ordered(profiles):
    assert (profiles.oid.diff().dropna() == 1).all()
    for pid, g in profiles.groupby("profile_id", sort=False):
        assert (g.oid.diff().dropna() == 1).all(), f"{pid}: rows not contiguous"
        assert list(g.point) == list(range(1, len(g) + 1)), f"{pid}: points not 1..n"


def test_geometry(profiles):
    for pid, g in profiles.groupby("profile_id", sort=False):
        x, z, v = g.x_m.to_numpy(), g.z_m.to_numpy(), g.tas_metres.to_numpy()
        assert (np.diff(x) > 0).all(), f"{pid}: x not strictly increasing"
        assert (z >= 0).all(), f"{pid}: negative altitude"
        assert not ((v[:-1] == 0) & (v[1:] == 0)).any(), f"{pid}: segment at zero speed"
        if g.arrival_departure.iloc[0] == "D":
            assert x[0] == 0 and z[0] == 0, f"{pid}: departure does not start at 0, 0"
        else:
            assert z[-1] == 0, f"{pid}: arrival does not end on the ground"


def test_modes(profiles):
    for pid, g in profiles.groupby("profile_id", sort=False):
        m = list(g["mode"])
        assert set(m) <= {"TO", "CL", "AP"}, f"{pid}: modes {set(m)}"
        if g.arrival_departure.iloc[0] == "D":
            if "CL" in m:
                assert "TO" not in m[m.index("CL") :], f"{pid}: TO after CL"
        else:
            assert set(m) == {"AP"}, f"{pid}: arrival mode not AP"


def test_power_range(profiles):
    p = profiles.power.dropna()
    assert (p >= 0).all() and (p <= 1.0).all(), (p.min(), p.max())


def test_rpm_aircraft_have_no_power(profiles):
    rpm = _anp(profiles)[_anp(profiles).ac.isin(RPM_AIRCRAFT)]
    assert len(rpm) > 0
    assert rpm.power.isna().all()


def test_percentage_aircraft_power_is_a_thrust_fraction(profiles):
    """A percentage divided again by the static thrust gives departures below
    0.35 (CNA172 had 0.33). Corrected, every departure reaches at least 0.5."""
    d = _anp(profiles)
    d = d[d.ac.isin(PCT_AIRCRAFT) & (d.arrival_departure == "D")]
    assert set(d.ac) == PCT_AIRCRAFT
    mx = d.groupby("profile_id").power.max()
    assert (mx >= 0.5).all(), mx[mx < 0.5].to_dict()


def test_weights(profiles):
    w = _anp(profiles).groupby("profile_id").weight_kgs.agg(["min", "max"])
    assert (w["min"] > 0).all(), w[~(w["min"] > 0)].index.tolist()
    assert (w["min"] == w["max"]).all()


def test_ids_and_course(profiles):
    ids = set(_anp(profiles).profile_id)
    for pid in ids:
        assert re.match(GROUP_RE, pid) or re.match(r"^.+-[AD]-\d+$", pid), pid
    for bad in LATER_ANP_IDS:
        assert not any(i.startswith(bad + "-") for i in ids), bad
    assert set(_anp(profiles).course) == {"ANP2.2"}


def test_restored_type_profiles_present(profiles):
    ids = set(profiles.profile_id)
    for pid in [
        "GIIB-A-1", "GIIB-D-1", "HS748A-A-1", "HS748A-D-1", "PA30-A-1", "PA30-D-1",
        "A321-232-D-1", "CNA441-D-1", "ECLIPSE500-D-1", "BEC58P-D-1",
        "A330-301-A-1", "A330-343-A-1", "7378MAX-D-0", "A350-941-D-0",
    ]:  # fmt: skip
        assert pid in ids, pid


def test_757300_arrival_complete(profiles):
    g = profiles[profiles.profile_id == "757300-A-1"]
    assert len(g) == 31
    assert g.x_m.iloc[0] == pytest.approx(-164435 * 0.3048)


def test_737800_arrival_fixed_points(profiles):
    g = profiles[profiles.profile_id == "737800-A-1"]
    assert len(g) == 31
    assert g.x_m.iloc[0] == pytest.approx(-144240 * 0.3048)
    assert g.power.iloc[0] == pytest.approx(345 / 26300, abs=1e-8)


def test_7378max_brake_release_uses_v22_static_thrust(profiles):
    # ANP v2.2: static thrust 27,000 lb; MaxTakeoff E + 15 H = 26,356 lb.
    g = profiles[profiles.profile_id == "7378MAX-D-1"]
    assert g.power.iloc[0] == pytest.approx(26356 / 27000, abs=1e-3)


@pytest.mark.parametrize("group,source", sorted(GROUP_SOURCE_SAMPLE.items()))
def test_groups_are_copies(profiles, group, source):
    cols = ["x_m", "z_m", "tas_metres", "power", "weight_kgs"]
    g = profiles[profiles.profile_id == group][cols].to_numpy(dtype=float)
    s = profiles[profiles.profile_id == source][cols].to_numpy(dtype=float)
    assert g.shape == s.shape
    assert np.allclose(g, s, equal_nan=True)


def test_default_profiles_exist(profiles, aircraft):
    ids = set(profiles.profile_id)
    for col, ad in (("departure_profile", "D"), ("arrival_profile", "A")):
        vals = aircraft[col].dropna()
        missing = sorted(set(vals) - ids)
        assert not missing, f"{col}: {missing[:10]}"
        ads = (
            profiles.drop_duplicates("profile_id")
            .set_index("profile_id")
            .arrival_departure
        )
        assert (ads.loc[vals] == ad).all(), col


def test_default_departures_are_stage_1(aircraft):
    d = aircraft.departure_profile.dropna()
    typed = d[~d.str.match(GROUP_RE)]
    assert len(typed) > 0
    assert typed.str.endswith("-D-1").all()
    a = aircraft.arrival_profile.dropna()
    assert a.str.endswith("-A-1").all()


def test_default_proxies_same_class(aircraft, profiles):
    """Rule (b) proxies keep the propulsion class. Spot checks."""
    m = aircraft.set_index("icao")
    assert m.loc["B738", "departure_profile"] == "737800-D-1"
    assert m.loc["A320", "departure_profile"] == "A320-211-D-1"
    assert m.loc["C172", "departure_profile"] == "CNA172-D-1"
    assert m.loc["C208", "departure_profile"] == "CNA208-D-1"


def test_no_anp21_profiles(profiles):
    assert not profiles.profile_id.str.startswith(ANP21_PREFIXES).any()
    assert set(profiles.course) == {"ANP2.2"}
