"""UTM zone (EPSG code) for a WGS84 point, shared by the plugin and the standalone (QGIS-free).

`utm_epsg(lat, lon)` asks the PROJ database (pyproj `query_utm_crs_info`, datum "WGS 84") for the UTM CRSs whose
area of use contains the point and returns the first one, as the plugin's Grid3D has always done. Results:
* the hemisphere follows the latitude (326xx north of the equator, 327xx south of it);
* on a zone boundary (e.g. lon 0.0, 6.0) the point is in both zones and the first (lower) code is taken, e.g.
  lon 0.0 lat 51.5 gives 32630, lon 6.0 lat 50.0 gives 32631;
* the equator itself belongs to both hemispheres and gives the northern code;
* the PROJ areas of use are the plain 6 degree bands: the Norway 32V and Svalbard X-band exceptions of the
  military grid are NOT applied (lat 60.0 lon 5.0 gives 32631, not 32632).
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=256)
def utm_epsg(lat: float, lon: float) -> int:
    """Return the EPSG code of the UTM zone for a WGS84 point (first match of the PROJ database query).

    Raises:
        ValueError: if the point is outside UTM coverage (UTM is defined from 80 S to 84 N).
        RuntimeError: if pyproj cannot reach the PROJ data directory, or if proj.db is reachable but returns no
            UTM CRS for a point inside the UTM band (outdated or inconsistent proj.db, PROJ/pyproj version
            mismatch). These are installation issues, not invalid input.
    """
    import pyproj
    from pyproj import CRS
    from pyproj.aoi import AreaOfInterest
    from pyproj.database import query_utm_crs_info
    from pyproj.exceptions import DataDirError

    lat = float(lat)
    lon = float(lon)
    try:
        utm_crs_list = query_utm_crs_info(
            datum_name="WGS 84",
            area_of_interest=AreaOfInterest(
                west_lon_degree=lon,
                south_lat_degree=lat,
                east_lon_degree=lon,
                north_lat_degree=lat,
            ),
        )
    except DataDirError as e:
        # pyproj cannot find a valid PROJ data directory (proj.db missing, or PROJ_DATA / PROJ_LIB pointing
        # nowhere). This is a QGIS/PROJ install problem, not an Open ALAQS bug.
        raise RuntimeError(
            "PROJ data directory is not accessible to pyproj. "
            "This is a QGIS/PROJ installation issue, not an Open "
            "ALAQS bug. Check the PROJ_DATA environment variable "
            "(or PROJ_LIB for PROJ < 9.1), or "
            "pyproj.datadir.get_data_dir(). "
            f"Underlying error: {e}"
        ) from e

    if not utm_crs_list:
        # UTM is defined for 80 S to 84 N (asymmetric).
        if -80.0 <= lat <= 84.0:
            # Inside UTM coverage but no CRS: proj.db is reachable (otherwise the call above would have raised
            # DataDirError) but inconsistent, most likely an outdated proj.db or a PROJ/pyproj version mismatch
            # where the datum_name="WGS 84" filter matches zero rows.
            try:
                data_dir = pyproj.datadir.get_data_dir()
            except DataDirError:
                data_dir = "<unavailable>"
            raise RuntimeError(
                f"pyproj returned no UTM CRS for valid coordinates "
                f"lat={lat}, lon={lon}. PROJ database is reachable "
                f"but appears inconsistent (possibly an outdated "
                f"proj.db or a PROJ/pyproj version mismatch). "
                f"pyproj data dir: {data_dir}. This is a QGIS/PROJ "
                f"installation issue, not an Open ALAQS bug."
            )
        raise ValueError(
            f"No UTM CRS found for lat={lat}, lon={lon}. "
            f"Location is outside UTM coverage (UTM is defined "
            f"for latitudes 80°S to 84°N)."
        )

    return int(
        CRS.from_authority(utm_crs_list[0].auth_name, utm_crs_list[0].code).to_epsg()
    )
