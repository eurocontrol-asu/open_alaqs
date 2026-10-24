"""Review round of the 5.4.1 atmosphere aloft: bounds, degenerate inputs, plumbing.

Covers the findings of the 5.4.1 audit (23 Oct 2026):
  * the surface heat flux implied by an hourly row is bounded (600 W/m2 unstable,
    100 W/m2 stable) and a warning is logged;
  * a missing mixing height (None, NaN, 0, -999) keeps AUSTAL's stable cap;
  * invalid site parameters and absurd profile temperatures raise ValueError;
  * the profile cache is bounded and compact;
  * ISA meteo stays ISA at every height (standalone ISA dict, plugin without a meteo row);
  * engine tests use the station pressure (plugin module and standalone);
  * the headless runner and the standalone CLI accept the new options;
  * MEEM V1 above 3,000 ft uses the local T and p end to end (standalone = reference).
"""

from __future__ import annotations

import importlib.util
import logging
import sqlite3
from pathlib import Path

import pytest

from open_alaqs.core.tools import surface_layer_atmosphere as sla

REPO = Path(__file__).resolve().parents[1]
SITE = dict(z0=0.2, d0=1.2, ha=11.2)


# ---- heat-flux bound ---------------------------------------------------------------


def test_training_row_heat_flux_is_bounded(caplog):
    """15 m/s with L = -50 m (the 2 December row of the training fixtures) implies about
    9 kW/m2; the bound replaces L so that the flux is 600 W/m2, and logs it."""
    sla._profile.cache_clear()
    p = 99400.0
    ust0 = sla.friction_velocity(15.0, 11.2, 0.2, 1.2, -50.0)
    h0 = sla.implied_heat_flux(ust0, -50.0, 288.15, p)
    assert 8000.0 < h0 < 10000.0
    ust, lm, h, bounded = sla.bounded_stability(15.0, 11.2, 0.2, 1.2, -50.0, 288.15, p)
    assert bounded
    assert h == pytest.approx(600.0, rel=1e-6)
    assert lm < -50.0
    assert ust == pytest.approx(
        sla.friction_velocity(15.0, 11.2, 0.2, 1.2, lm), rel=1e-9
    )
    with caplog.at_level(logging.WARNING, logger=sla.__name__):
        t300 = sla.local_state(
            "surface_layer",
            288.15,
            p,
            0.7,
            300.0,
            15.0,
            -50.0,
            0.0,
            **SITE,
            mixing_height_m=914.4,
        )[0]
    assert any("heat flux" in r.getMessage() for r in caplog.records)
    # bounded: a few kelvin below the ground value, not 24 K
    assert -8.0 < t300 - 288.15 < -3.0


@pytest.mark.parametrize(
    "ws, lm",
    [
        (2.0, -10.0),
        (4.0, -30.0),
        (6.0, -100.0),
        (3.0, 200.0),
        (2.0, 50.0),
        (5.0, 99999.0),
    ],
)
def test_consistent_rows_are_not_bounded(ws, lm):
    """Rows of the METAR converter's Pasquill-Gifford classes with matching winds are
    below the bound and keep their L."""
    ust, lm_eff, h, bounded = sla.bounded_stability(
        ws, 11.2, 0.2, 1.2, lm, 293.15, 101325.0
    )
    assert not bounded
    assert lm_eff == lm
    assert abs(h) <= sla.HEAT_FLUX_MAX_UNSTABLE_W_M2


@pytest.mark.parametrize(
    "ws, lm", [(10.0, -10.0), (15.0, 10.0), (10.0, 50.0), (8.0, -0.5), (5.0, -1e-3)]
)
def test_inconsistent_rows_give_plausible_profiles(ws, lm):
    """Rows that gave -38 K to +150 K (and negative kelvin) before the bound stay within
    15 K of the ground value up to 900 m."""
    for h in (10.0, 100.0, 300.0, 900.0):
        t = sla.local_state(
            "surface_layer",
            288.15,
            101325.0,
            0.7,
            h,
            ws,
            lm,
            0.0,
            **SITE,
            mixing_height_m=914.4,
        )[0]
        assert abs(t - 288.15) < 15.0, (ws, lm, h, t)


def test_profile_temperature_outside_range_raises():
    with pytest.raises(ValueError, match="outside"):
        sla._Profile("surface_layer", 288.15, 101325.0, 5.0, -0.5, 0.2, 1.2, None)


# ---- mixing height -----------------------------------------------------------------


@pytest.mark.parametrize("hm", [None, 2.0, 0.0, -1.0, -999.0, float("nan"), ""])
def test_missing_mixing_height_keeps_stable_cap(hm):
    """A missing mixing height does not remove AUSTAL's stable mixing height (getHm)."""
    ref = sla.local_state(
        "surface_layer",
        293.15,
        101325.0,
        0.7,
        900.0,
        4.0,
        30.0,
        0.0,
        0.3,
        None,
        None,
        None,
    )[0]
    got = sla.local_state(
        "surface_layer",
        293.15,
        101325.0,
        0.7,
        900.0,
        4.0,
        30.0,
        0.0,
        0.3,
        None,
        None,
        hm,
    )[0]
    assert got == pytest.approx(ref, abs=1e-12)
    assert abs(got - 293.15) < 2.0


# ---- site parameters, cache --------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        dict(z0=0.0),
        dict(z0=-0.1),
        dict(z0=0.2, d0=-1.0),
        dict(z0=0.2, d0=1.2, ha=1.0),
        dict(z0=float("nan")),
    ],
)
def test_invalid_site_parameters_raise(kw):
    with pytest.raises(ValueError, match="site parameters"):
        sla.site_parameters(**kw)


def test_site_parameter_defaults():
    assert sla.site_parameters() == pytest.approx((0.1, 0.6, 10.6))
    assert sla.site_parameters(0.3) == pytest.approx((0.3, 1.8, 11.8))


def test_profile_cache_is_bounded():
    assert sla._profile.cache_info().maxsize == 512
    prof = sla._profile(
        "surface_layer", 290.0, 101325.0, 3.0, -30.0, 0.0, 0.2, 1.2, 11.2, 800.0
    )
    # arrays of doubles, the height grid shared
    assert prof.t.typecode == "d" and prof.lnp.typecode == "d"
    assert not hasattr(prof, "h")


# ---- ISA meteo ---------------------------------------------------------------------


def test_plugin_without_meteo_row_keeps_isa():
    """AmbientCondition() (no tbl_InvMeteo row for the period) stays ISA at every height."""
    from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
    from open_alaqs.core.MovementEmissionCalculator import local_ambient_conditions

    cfg = {
        "atmosphere_model": "surface_layer",
        "ambient_conditions": AmbientCondition(),
    }
    assert local_ambient_conditions(cfg, 500.0) is None
    cfg["ambient_conditions"] = AmbientCondition({"id": 3, "Temperature": 288.15})
    assert local_ambient_conditions(cfg, 500.0) is not None


def test_standalone_isa_dict_has_no_boundary_layer_keys():
    """The standalone and the reference tell an ISA dict from a row by the WindSpeed key."""
    from openalaqs_standalone import movements as mv

    assert "WindSpeed" not in mv.ISA_AMBIENT
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE tbl_InvMeteo (DateTime TEXT, Temperature REAL, SeaLevelPressure REAL, "
        "RelativeHumidity REAL, Humidity REAL, WindSpeed REAL)"
    )
    conn.execute(
        "INSERT INTO tbl_InvMeteo VALUES ('2025-07-05 10:00:00', 295, 101800, 0.6, 0.01, 4)"
    )
    m = mv.get_meteo_at(conn, "2025-07-05 10:30:00", use_isa=False)
    # existing column kept, missing columns as the plugin's AmbientCondition defaults
    assert m["WindSpeed"] == 4.0
    assert m["ObukhovLength"] is None
    assert m["MixingHeight"] == pytest.approx(914.4)
    assert "WindSpeed" not in mv.get_meteo_at(conn, "2025-07-05 10:30:00", use_isa=True)


# ---- engine tests ------------------------------------------------------------------


def test_standalone_engine_test_station_pressure():
    from openalaqs_standalone.compute_engine_test import _station_pressure_meteo

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE user_study_setup (airport_elevation REAL)")
    conn.execute("INSERT INTO user_study_setup VALUES (1650.0)")
    row = {"T_K": 290.0, "P_Pa": 101325.0, "RH": 0.5, "WindSpeed": 3.0}
    got = _station_pressure_meteo(conn, row, None)
    assert got["P_Pa"] == pytest.approx(sla.station_pressure_from_qnh(101325.0, 1650.0))
    assert got["P_Pa"] < 84000.0
    assert _station_pressure_meteo(conn, row, "ground_held")["P_Pa"] == 101325.0
    isa = {"T_K": 288.15, "P_Pa": 101325.0, "RH": 0.6}
    assert _station_pressure_meteo(conn, isa, None)["P_Pa"] == 101325.0


def test_plugin_engine_test_station_pressure():
    from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
    from open_alaqs.core.modules.EngineTestSourceModule import EngineTestSourceModule

    m = EngineTestSourceModule({"reference_altitude": 1650.0})
    row = AmbientCondition(
        {"id": 1, "Temperature": 290.0, "SeaLevelPressure": 101325.0}
    )
    got = m._at_station_pressure(row)
    assert got.getPressure() == pytest.approx(
        sla.station_pressure_from_qnh(101325.0, 1650.0)
    )
    assert row.getPressure() == 101325.0  # the period's row is untouched
    m_gh = EngineTestSourceModule(
        {"reference_altitude": 1650.0, "atmosphere_model": "ground_held"}
    )
    assert m_gh._at_station_pressure(row).getPressure() == 101325.0


# ---- runners -----------------------------------------------------------------------


def test_standalone_cli_accepts_atmosphere_options(tmp_path):
    from openalaqs_standalone import cli

    with pytest.raises(SystemExit) as exc:
        cli.run_aircraft(["--help"])
    assert exc.value.code == 0


def test_cli_help_lists_options(capsys):
    from openalaqs_standalone import cli

    with pytest.raises(SystemExit):
        cli.run_aircraft(["--help"])
    out = capsys.readouterr().out
    for opt in (
        "--atmosphere-model",
        "--z0",
        "--d0",
        "--ha",
    ):
        assert opt in out


def test_headless_runner_reads_new_keys():
    spec = importlib.util.spec_from_file_location(
        "run_emissions_austal",
        REPO / "scripts" / "emissions_austal" / "run_emissions_austal.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # pragma: no cover - needs the QGIS bindings
        pytest.skip(f"runner import needs QGIS: {exc}")
    src = (
        REPO / "scripts" / "emissions_austal" / "run_emissions_austal.py"
    ).read_text()
    for key in (
        "bffm2_ff_source",
        "atmosphere_model",
        "atmosphere_z0_m",
    ):
        assert key in src
    from open_alaqs.core.EmissionCalculatorService import EmissionCalculationConfig

    mod.EmissionCalculationConfig = (
        EmissionCalculationConfig  # set by the runner's lazy import
    )
    cfg = mod.create_emission_config(
        {
            "db_path": "x.alaqs",
            "start_dt_inclusive": None,
            "end_dt_inclusive": None,
            "time_interval": None,
            "pollutant": "NOx",
            "atmosphere_model": "ground_held",
            "bffm2_ff_source": "mode_anchor",
            "atmosphere_z0_m": 0.5,
        },
        {},
    )
    assert cfg.atmosphere_model == "ground_held"
    assert cfg.bffm2_ff_source == "mode_anchor"
    assert cfg.atmosphere_z0_m == 0.5


# ---- MEEM V1 above 3,000 ft, end to end --------------------------------------------


def test_meem_local_ambient_end_to_end(tmp_path):
    """On the example inventory (mixing heights up to 1,500 m), bymode PM10 above 3,000 ft
    differs between surface_layer and ground_held, NOx does not, and the standalone equals
    the CAEP14 reference per movement for both models."""
    import shutil

    src = REPO / "example" / "training" / "training_out.alaqs"
    if not src.exists():
        pytest.skip("example inventory not found")
    study = tmp_path / "example.alaqs"
    shutil.copy(src, study)
    spec = importlib.util.spec_from_file_location(
        "compute_caep14_reference",
        REPO
        / "openalaqs_standalone"
        / "validation"
        / "tools"
        / "compute_caep14_reference.py",
    )
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    from openalaqs_standalone.compute_movements import (
        build_context,
        compute_for_movement,
    )

    try:
        rconn = ref._connect(str(study))
    except Exception as exc:  # pragma: no cover - environment without SpatiaLite
        pytest.skip(f"CAEP14 reference needs mod_spatialite: {exc}")
    ctx_ref = {
        "runway": ref._get_runway(rconn),
        "grid_bounds": ref._grid_bounds_3857(rconn),
    }
    out = {}
    with sqlite3.connect(study) as conn:
        oids = [
            r[0]
            for r in conn.execute(
                "SELECT oid FROM user_aircraft_movements ORDER BY oid"
            )
        ]
        ctx_sa = build_context(conn)
        for model in ("surface_layer", "ground_held"):
            for oid in oids:
                kw = dict(
                    method="bymode", use_isa_meteo=False, atmosphere={"model": model}
                )
                sa = compute_for_movement(conn, oid, ctx_sa, **kw)
                rr = ref.compute_for_movement(rconn, oid, ctx_ref, **kw)
                if sa is None or rr is None:
                    continue
                for p in ("nox", "pm10"):
                    assert rr["total_em_kg"][p] == pytest.approx(
                        sa["total_em_kg"][p], rel=1e-9, abs=1e-12
                    ), (model, oid, p)
                out[(model, oid)] = sa["total_em_kg"]
    rconn.close()
    diff = [
        o
        for o in oids
        if (("surface_layer", o) in out)
        and abs(out[("surface_layer", o)]["pm10"] - out[("ground_held", o)]["pm10"])
        > 1e-12
    ]
    assert diff, "no movement reaches MEEM V1 above 3,000 ft"
    for o in oids:
        if ("surface_layer", o) in out:
            assert out[("surface_layer", o)]["nox"] == pytest.approx(
                out[("ground_held", o)]["nox"], rel=1e-12
            )


# ---- review of 24 Oct 2026: input checks and error messages --------------------------


@pytest.mark.parametrize("qnh", [0.0, -5.0, float("nan")])
def test_bad_sea_level_pressure_raises(qnh):
    with pytest.raises(ValueError, match="sea-level pressure"):
        sla.local_state("standard_lapse", 290.0, qnh, 0.6, 100.0)


def test_bad_temperature_raises():
    with pytest.raises(ValueError, match="temperature"):
        sla.local_state("standard_lapse", float("nan"), 101325.0, 0.6, 100.0)


def test_plugin_error_names_the_meteo_row():
    """A Celsius temperature in tbl_InvMeteo stops the run with the row's date."""
    from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
    from open_alaqs.core.MovementEmissionCalculator import local_ambient_conditions

    ac = AmbientCondition(
        {"id": 7, "DateTime": "2025-07-05 10:00:00", "Temperature": 21.0}
    )
    with pytest.raises(ValueError, match="2025-07-05") as exc:
        local_ambient_conditions({"ambient_conditions": ac}, 300.0)
    assert "outside 180 to 340 K" in str(exc.value)


def test_bounded_row_error_gives_the_rows_own_l():
    with pytest.raises(ValueError, match="row's own L is -50"):
        sla._profile.__wrapped__(
            "surface_layer", 21.0, 101325.0, 15.0, -50.0, 0.0, 0.2, 1.2, 11.2, 914.4
        )


def test_standalone_meteo_row_carries_its_date():
    from openalaqs_standalone import movements as mv

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE tbl_InvMeteo (DateTime TEXT, Temperature REAL, SeaLevelPressure REAL, "
        "RelativeHumidity REAL, Humidity REAL)"
    )
    conn.execute(
        "INSERT INTO tbl_InvMeteo VALUES ('2025-07-05 10:00:00', 295, 101800, 0.6, 0.01)"
    )
    assert mv.get_meteo_at(conn, "2025-07-05 10:30:00", use_isa=False)["DateTime"] == (
        "2025-07-05 10:00:00"
    )
