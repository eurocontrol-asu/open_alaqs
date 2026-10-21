"""UTM zone choice and AUSTAL config reference point, shared by the plugin and the standalone.

* `open_alaqs.core.tools.utm.utm_epsg` returns the first UTM CRS of the PROJ database query the plugin's Grid3D
  has always used (hemisphere from the latitude, lower zone on a zone boundary, no Norway/Svalbard exceptions);
  geometry.grid_bounds_3857, both make_config and orchestrate use it.
* make_config centres the AUSTAL config on grid_3d_definition reference_latitude/longitude (the centre of the
  emission grid), and on the airport of user_study_setup only when the grid definition has none.
"""

from __future__ import annotations

import json
import sqlite3

import pyproj
import pytest
from pyproj import CRS
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info

from austal_prep import make_config as ap_make_config
from open_alaqs.core.tools.utm import utm_epsg
from openalaqs_standalone import geometry as geo
from openalaqs_standalone import make_config as sa_make_config


def _pyproj_query_first(lat: float, lon: float) -> int:
    """The query of the plugin's Grid3D before the helper existed (first result)."""
    found = query_utm_crs_info(
        datum_name="WGS 84",
        area_of_interest=AreaOfInterest(
            west_lon_degree=lon,
            south_lat_degree=lat,
            east_lon_degree=lon,
            north_lat_degree=lat,
        ),
    )
    return int(CRS.from_authority(found[0].auth_name, found[0].code).to_epsg())


@pytest.mark.parametrize(
    "lat, lon, expected",
    [
        (51.9574278, 4.4417028, 32631),  # training study (Rotterdam)
        (-33.9, 151.2, 32756),  # Sydney: southern hemisphere
        (51.5, 0.0, 32630),  # on the zone 30/31 boundary: lower zone
        (50.0, 6.0, 32631),  # on the zone 31/32 boundary: lower zone
        (-20.0, 6.0, 32731),  # boundary, southern hemisphere
        (60.0, 5.0, 32631),  # Norway 32V exception NOT applied
        (78.2, 15.6, 32633),  # Svalbard
        (0.0, 4.0, 32631),  # equator: northern code
        (84.0, 10.0, 32632),  # northern edge of UTM
        (-80.0, 10.0, 32732),  # southern edge of UTM
    ],
)
def test_utm_epsg_cases(lat, lon, expected):
    assert utm_epsg(lat, lon) == expected


def test_utm_epsg_agrees_with_pyproj_query():
    """Same result as the plugin's pyproj query, on and around zone boundaries and the equator.

    Each PROJ database query takes about 0.2 s, so the sample is kept small.
    """
    points = [
        (lat, lon)
        for lat in (-56.0, 0.0, 51.5, 60.0, 78.2)
        for lon in (-180.0, -0.01, 0.0, 0.01, 6.0, 9.0, 151.2, 180.0)
    ] + [(-80.0, 3.0), (84.0, 3.0), (-0.5, 3.0), (0.5, 3.0)]
    for lat, lon in points:
        assert utm_epsg(lat, lon) == _pyproj_query_first(lat, lon), (lat, lon)


@pytest.mark.parametrize("lat", [85.0, -81.0])
def test_utm_epsg_outside_coverage(lat):
    with pytest.raises(ValueError, match="outside UTM coverage"):
        utm_epsg(lat, 10.0)


def test_grid_bounds_uses_helper():
    for lat, lon in [(-33.9, 151.2), (51.5, 0.0), (50.0, 6.0), (-20.0, 6.0)]:
        gb = geo.grid_bounds_3857(10, 10, 250.0, 250.0, lat, lon)
        assert gb["utm_epsg"] == utm_epsg(lat, lon)


# ---------------------------------------------------------------------------
# make_config reference point
# ---------------------------------------------------------------------------

AIRPORT = (51.9574278, 4.4417028)


def _study(path, airport=AIRPORT, grid_ref=None, cells=50, res=250.0):
    """Minimal .alaqs: user_study_setup and, unless grid_ref is None, grid_3d_definition."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE user_study_setup (oid INTEGER, project_name TEXT, airport_name TEXT, "
        "airport_latitude REAL, airport_longitude REAL)"
    )
    conn.execute(
        "INSERT INTO user_study_setup VALUES (1, 'test', 'Test airport', ?, ?)",
        airport,
    )
    if grid_ref is not None:
        conn.execute(
            "CREATE TABLE grid_3d_definition (grid_3d_id TEXT, x_cells INTEGER, y_cells INTEGER, "
            "z_cells INTEGER, x_resolution REAL, y_resolution REAL, z_resolution REAL, "
            "reference_latitude REAL, reference_longitude REAL)"
        )
        conn.execute(
            "INSERT INTO grid_3d_definition VALUES ('g', ?, ?, 20, ?, ?, 50, ?, ?)",
            (cells, cells, res, res, grid_ref[0], grid_ref[1]),
        )
    conn.commit()
    conn.close()
    return path


def _utm_xy(epsg, lat, lon):
    return pyproj.Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)


@pytest.mark.parametrize(
    "module", [sa_make_config, ap_make_config], ids=["standalone", "austal_prep"]
)
def test_make_config_uses_grid_reference(tmp_path, module, capsys):
    """Grid reference 0.02 deg east of the airport: the config is centred on the emission grid centre."""
    grid_ref = (AIRPORT[0], AIRPORT[1] + 0.02)
    alaqs = _study(tmp_path / "study.alaqs", grid_ref=grid_ref)
    cfg = module.make_config(alaqs, tmp_path / "config.json")
    assert json.loads((tmp_path / "config.json").read_text()) == cfg
    g = cfg["grid"]
    assert g["utm_epsg"] == 32631
    gx, gy = _utm_xy(32631, *grid_ref)
    ax, ay = _utm_xy(32631, *AIRPORT)
    assert g["reference_x"] == pytest.approx(gx, abs=1e-6)
    assert g["reference_y"] == pytest.approx(gy, abs=1e-6)
    assert gx - ax == pytest.approx(
        1374.2, abs=1.0
    )  # the offset the airport reference used to introduce
    # Same centre as the emission grid built by geometry.grid_bounds_3857.
    gb = geo.grid_bounds_3857(50, 50, 250.0, 250.0, *grid_ref)
    assert gb["utm_epsg"] == g["utm_epsg"]
    assert g["reference_x"] == pytest.approx(gb["ref_x_utm"], abs=1e-6)
    assert g["reference_y"] == pytest.approx(gb["ref_y_utm"], abs=1e-6)
    assert (
        "WARNING: grid_3d_definition has no reference point"
        not in capsys.readouterr().out
    )


@pytest.mark.parametrize(
    "module", [sa_make_config, ap_make_config], ids=["standalone", "austal_prep"]
)
def test_make_config_falls_back_to_airport(tmp_path, module, capsys):
    alaqs = _study(tmp_path / "study.alaqs", grid_ref=None)
    cfg = module.make_config(alaqs, tmp_path / "config.json")
    ax, ay = _utm_xy(32631, *AIRPORT)
    assert cfg["grid"]["utm_epsg"] == 32631
    assert cfg["grid"]["reference_x"] == pytest.approx(ax, abs=1e-6)
    assert cfg["grid"]["reference_y"] == pytest.approx(ay, abs=1e-6)
    assert (
        "WARNING: grid_3d_definition has no reference point" in capsys.readouterr().out
    )


@pytest.mark.parametrize(
    "module", [sa_make_config, ap_make_config], ids=["standalone", "austal_prep"]
)
@pytest.mark.parametrize(
    "ref, expected",
    [
        ((51.5, 0.0), 32630),
        ((-33.9, 151.2), 32756),
        ((50.0, 6.0), 32631),
        ((-20.0, 6.0), 32731),
    ],
)
def test_make_config_zone_matches_plugin(tmp_path, module, ref, expected):
    """Longitude 0.0 is a real reference (no sentinel); southern hemisphere and zone boundaries as the plugin."""
    alaqs = _study(tmp_path / "study.alaqs", airport=ref, grid_ref=ref)
    cfg = module.make_config(alaqs, tmp_path / "config.json")
    assert (
        cfg["grid"]["utm_epsg"]
        == expected
        == geo.grid_bounds_3857(10, 10, 250.0, 250.0, *ref)["utm_epsg"]
    )
    x, y = _utm_xy(expected, *ref)
    assert cfg["grid"]["reference_x"] == pytest.approx(x, abs=1e-6)
    assert cfg["grid"]["reference_y"] == pytest.approx(y, abs=1e-6)


@pytest.mark.parametrize(
    "module", [sa_make_config, ap_make_config], ids=["standalone", "austal_prep"]
)
def test_make_config_without_any_reference_raises(tmp_path, module):
    alaqs = _study(tmp_path / "study.alaqs", airport=(None, None), grid_ref=None)
    with pytest.raises(ValueError, match="no reference point"):
        module.make_config(alaqs, tmp_path / "config.json")


def test_orchestrate_reference_and_zone(tmp_path):
    """orchestrate takes its receptor CRS and domain centre from the same reference as make_config."""
    from openalaqs_standalone import orchestrate as orch

    alaqs = _study(tmp_path / "study.alaqs", airport=AIRPORT, grid_ref=(51.5, 0.0))
    meta = orch._airport_metadata(alaqs)
    lat, lon = orch._reference_lat_lon(alaqs, meta)
    assert (lat, lon) == (51.5, 0.0)
    assert orch._utm_epsg(lat, lon) == 32630
