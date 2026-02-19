"""
Backend for generating AUSTAL input files from pre-calculated emissions CSV,
meteorology CSV, grid config, AUSTAL config and output directory.

Emissions CSV schema
--------------------
Required columns:  timestamp, wkt
Optional columns:  source_type, source_name  (used for logging only; can be omitted)
Pollutant columns: any column ending in _kg is read automatically; columns for
                   pollutants not present in the file can simply be absent.
Rows without a WKT geometry are skipped.

Meteorology CSV schema
----------------------
Required column:
    DateTime(YYYY-mm-dd hh:mm:ss)   datetime of the observation

Columns written to the AUSTAL series.dmna file:
    WindSpeed(m/s)          wind speed             
    WindDirection(degrees)  wind direction    
    ObukhovLength(m)        Obukhov length         
    MixingHeight(m)         mixing layer height    

Columns parsed but NOT forwarded to AUSTAL (can be omitted):
    Temperature(K)                  
    Humidity(kg_water/kg_dry_air)   
    RelativeHumidity(%)             
    SeaLevelPressure(Pa)            
    Scenario                        

Any other columns are ignored.

grid_config dict schema
-----------------------
Required keys (all have fallback defaults if omitted):
    x_cells             int     number of grid cells in X            
    y_cells             int     number of grid cells in Y            
    z_cells             int     number of grid cells in Z            
    x_resolution        float   cell size in X  (m)                  
    y_resolution        float   cell size in Y  (m)                  
    z_resolution        float   cell size in Z  (m)                  
    reference_latitude  float   grid origin latitude  (deg)  
    reference_longitude float   grid origin longitude (deg)  
    reference_altitude  float   grid origin altitude  (m)            

austal_config dict schema
-------------------------
Required keys (all have fallback defaults if omitted):
    quality_level           int     AUSTAL quality level (1 to 3)    default 1
    roughness_length_m      float   aerodynamic roughness length (m) default 0.2
    options_string          str     AUSTAL options flags             default "NOSTANDARD;SCINOTAT;Kmax=1"

Optional keys:
    is_enabled              bool    enable the module                default False
    mixing_height_enabled   bool    pass mixing height to AUSTAL     default False
    displacement_height_m   float   zero-plane displacement (m)      default 6 * roughness_length_m
    anemometer_height_m     float   anemometer height (m)            default 10 + 6 * roughness_length_m

The keys output_path, pollutants_list, title, grid and receptors are set
internally by generate_austal_from_csv and must not be included in austal_config.
"""

import csv as _csv
import os
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, List
import geopandas as gpd

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
from open_alaqs.core.modules.AUSTALOutputModule import AUSTALDispersionModule
from open_alaqs.core.tools.Grid3D import Grid3D
from open_alaqs.core.interfaces.Emissions import Emission

from qgis.utils import spatialite_connect

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Column names (match TableViewWidgetOutputModule._prepare_fields)
# ---------------------------------------------------------------------------
_COL_TIMESTAMP = "timestamp"
_COL_WKT = "wkt"
_COL_SOURCE_NAME = "source_name"
_METEO_DT_FMT = "%Y-%m-%d %H:%M:%S"
_SENTINEL_WKT = frozenset({"-", "none", "null", ""})


# ---------------------------------------------------------------------------
# Temporary SpatiaLite database
# ---------------------------------------------------------------------------


@contextmanager
def _temp_spatialite_db():
    """Create, yield path to, and delete a temporary SpatiaLite database.

    The database has SpatiaLite metadata initialised so that ST_Transform
    queries succeed inside the context.

    Yields:
        str: Absolute path to the temporary database file.

    Raises:
        RuntimeError: If SpatiaLite cannot be initialised.
    """
    fd, path = tempfile.mkstemp(suffix=".db", prefix="openalaqs_austal_")
    os.close(fd)
    try:
        conn = spatialite_connect(path)
        # Populate geometry_columns and spatial_ref_sys so ST_Transform works
        # The (1) argument suppresses "table already exists" on newer SpatiaLite
        # fall back to no-arg form for older versions
        try:
            conn.execute("SELECT InitSpatialMetaData(1)")
        except Exception:
            try:
                conn.execute("SELECT InitSpatialMetaData()")
            except Exception as exc:
                conn.close()
                raise RuntimeError(
                    f"Could not initialise SpatiaLite metadata: {exc}"
                ) from exc
        conn.commit()
        conn.close()
        yield path
    finally:
        # Remove the temp file on exit, even if an exception was raised
        try:
            os.unlink(path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Minimal Source adapter
# ---------------------------------------------------------------------------


class _CsvSourceAdapter:
    """Satisfies the Source interface expected by AUSTALDispersionModule."""

    def __init__(self, name: str, height: float = 0.0) -> None:
        self._name = name
        self._height = height

    def getName(self) -> str:
        return self._name

    def getHeight(self) -> float:
        return self._height


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def parse_emissions_csv(path: str) -> Dict[datetime, List[dict]]:
    """Parse an emissions CSV into a dict keyed by timestamp.

    Args:
        path: Path to the CSV produced by TableViewWidgetOutputModule.

    Returns:
        Dict mapping datetime to list of row dicts for that timestep.

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If required columns are missing or no valid rows found.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Emissions CSV not found: {path}")

    # Group rows by timestamp so each timestep can be processed in one batch
    rows_by_ts: Dict[datetime, List[dict]] = defaultdict(list)

    with open(path, newline="", encoding="utf-8") as fh:
        reader = _csv.DictReader(fh)
        headers = list(reader.fieldnames or [])

        # Fail early if either required column is absent
        for required in (_COL_TIMESTAMP, _COL_WKT):
            if required not in headers:
                raise ValueError(
                    f"Emissions CSV missing required column '{required}': {path}"
                )

        for row in reader:
            raw_ts = (row.get(_COL_TIMESTAMP) or "").strip()
            if not raw_ts:
                continue
            try:
                ts = datetime.fromisoformat(raw_ts)
            except ValueError:
                logger.warning(
                    "parse_emissions_csv: skipping row with bad timestamp '%s'",
                    raw_ts,
                )
                continue
            rows_by_ts[ts].append(dict(row))

    # Collect source types and a sample movement WKT for diagnostic logging
    all_source_types = set()
    movement_wkt_sample = None
    for ts_rows in rows_by_ts.values():
        for r in ts_rows:
            st = r.get("source_type", "")
            all_source_types.add(st)
            if movement_wkt_sample is None and "ovement" in st:
                movement_wkt_sample = (r.get(_COL_WKT) or "")[:300]

    if movement_wkt_sample is None:
        logger.warning("No movement rows found in the CSV")
        
    if not rows_by_ts:
        raise ValueError(f"Emissions CSV contains no valid rows: {path}")

    return dict(rows_by_ts)


def parse_meteo_csv(path: str) -> Dict[datetime, "AmbientCondition"]:
    """Parse a meteorology CSV into a dict keyed by datetime.

    Args:
        path: Path to the CSV with AmbientConditionStore column headers.

    Returns:
        Dict mapping datetime to AmbientCondition instance.

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If no valid rows are found.
    """

    if not os.path.isfile(path):
        raise FileNotFoundError(f"Meteo CSV not found: {path}")

    result: Dict[datetime, AmbientCondition] = {}

    with open(path, newline="", encoding="utf-8") as fh:
        reader = _csv.DictReader(fh)
        for i, row in enumerate(reader):
            raw_dt = (row.get("DateTime(YYYY-mm-dd hh:mm:ss)") or "").strip()
            if not raw_dt:
                continue
            try:
                ts = datetime.strptime(raw_dt, _METEO_DT_FMT)
            except ValueError:
                logger.warning(
                    "Row %d has unparseable DateTime '%s'", i, raw_dt
                )
                continue

            ac_dict = {
                "id": i,
                "Scenario": row.get("Scenario", "default"),
                "DateTime": raw_dt,
                # Not forwarded to AUSTAL
                "Temperature": _safe_float(row.get("Temperature(K)"), 288.15),
                "Humidity": _safe_float(
                    row.get("Humidity(kg_water/kg_dry_air)"), 0.00634
                ),
                "RelativeHumidity": _safe_float(row.get("RelativeHumidity(%)"), 0.6),
                "SeaLevelPressure": _safe_float(
                    row.get("SeaLevelPressure(mb)"), 1013.25
                ),
                # Written to series.dmna as ua, ra, lm, hm respectively
                "WindSpeed": _safe_float(row.get("WindSpeed(m/s)"), 0.0),
                "WindDirection": _safe_float(row.get("WindDirection(degrees)"), 0.0),
                "ObukhovLength": _safe_float(row.get("ObukhovLength(m)"), 99999.0),  # 99999 = neutral stability
                "MixingHeight": _safe_float(row.get("MixingHeight(m)"), 914.4),
                "SpeedOfSound": 340.29,
            }
            result[ts] = AmbientCondition(ac_dict)

    if not result:
        raise ValueError(f"Meteo CSV contains no valid rows: {path}")

    return result


# ---------------------------------------------------------------------------
# Domain-object construction helpers
# ---------------------------------------------------------------------------


def _safe_float(value, default: float = 0.0) -> float:
    """Convert value to float, returning default on any failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_grid3d(grid_config: dict, temp_db_path: str):
    """Construct a Grid3D from config dict using temp_db_path for SpatiaLite.

    Passing temp_db_path as db_path satisfies the ST_Transform calls in
    Grid3D._calculate_origin_xy() and
    AUSTALDispersionModule.getGridXYFromReferencePoint() without requiring
    an ALAQS database.

    Args:
        grid_config: Dict with x_cells, y_cells, z_cells, x_resolution,
            y_resolution, z_resolution, reference_latitude,
            reference_longitude, reference_altitude.
        temp_db_path: Path to an initialised SpatiaLite database.

    Returns:
        Grid3D instance.
    """

    return Grid3D(db_path=temp_db_path, grid_config=grid_config, deserialize=False)


def _build_emission(row: dict):
    """Construct an Emission object from a CSV row dict.

    Pollutant columns are identified by the '_kg' suffix.  The WKT geometry
    is set from the 'wkt' column; sentinel values (empty, '-', 'none', 'null')
    are treated as absent geometry and stored as None.

    Args:
        row: CSV row as a flat dict.

    Returns:
        Emission instance with pollutant values and optional geometry.
    """

    # All *_kg columns are treated as pollutant quantities; non-numeric values become 0.0
    pollutant_values = {
        col: _safe_float(val)
        for col, val in row.items()
        if col.endswith("_kg")
    }
    em = Emission(initValues=pollutant_values)
    raw_wkt = (row.get(_COL_WKT) or "").strip()
    # Store None for sentinel values so callers can use a simple "if wkt is None" check
    em.setGeometryText(None if raw_wkt.lower() in _SENTINEL_WKT else raw_wkt)
    return em


def _lookup_ambient(ts: datetime, meteo_map: Dict[datetime, "AmbientCondition"]):
    """Return the AmbientCondition for ts, falling back to the nearest entry.

    Args:
        ts: Target datetime.
        meteo_map: Dict of datetime to AmbientCondition.

    Returns:
        AmbientCondition closest in absolute time to ts.
    """
    if ts in meteo_map:
        return meteo_map[ts]
    nearest = min(meteo_map.keys(), key=lambda t: abs((t - ts).total_seconds()))
    logger.warning(
        "_lookup_ambient: no exact match for %s; using nearest at %s", ts, nearest
    )
    return meteo_map[nearest]


def _infer_time_interval(timestamps: List[datetime]) -> timedelta:
    """Infer the timestep duration from a sorted list of timestamps.

    Args:
        timestamps: Sorted list of datetime objects.

    Returns:
        Timedelta between the first two entries; 1 hour if fewer than 2.
    """
    if len(timestamps) < 2:
        return timedelta(hours=1)
    return timestamps[1] - timestamps[0]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_austal_from_csv(
    emissions_csv_path: str,
    meteo_csv_path: str,
    grid_config: dict,
    austal_config: dict,
    output_dir: str,
    selected_pollutants: List[str],
) -> None:
    """Generate AUSTAL input files from pre-calculated emissions and meteo CSVs.

    Reads the emissions CSV (TableViewWidgetOutputModule format) and the
    meteorology CSV (AmbientConditionStore format), then drives
    AUSTALDispersionModule to write austal.txt, series.dmna, and the per-
    pollutant grid .dmna files into output_dir.

    Args:
        emissions_csv_path: Path to the emissions CSV file.
        meteo_csv_path: Path to the meteorology CSV file.
        grid_config: Dict with x_cells, y_cells, z_cells, x_resolution,
            y_resolution, z_resolution, reference_latitude,
            reference_longitude, reference_altitude.
        austal_config: Dict with AUSTAL module settings (is_enabled,
            quality_level, mixing_height_enabled, options_string,
            roughness_length_m, displacement_height_m, anemometer_height_m).
        output_dir: Directory where AUSTAL input files will be written.
        selected_pollutants: List of pollutant names (e.g. ['NOx', 'PM10']).

    Raises:
        FileNotFoundError: If either CSV path does not exist.
        ValueError: If CSV data is invalid or contains no geometry rows.
        RuntimeError: If AUSTALDispersionModule fails to write files.
    """

    logger.info("Emissions File=%s", emissions_csv_path)
    logger.info("Meteo File=%s", meteo_csv_path)
    logger.info("Output Directory=%s", output_dir)
    logger.info("Selected Pollutants=%s", selected_pollutants)

    # Parse both inputs up front so format errors are caught before AUSTAL initialises
    rows_by_ts = parse_emissions_csv(emissions_csv_path)
    meteo_map = parse_meteo_csv(meteo_csv_path)
    
    has_geometry = any(
        (row.get(_COL_WKT) or "").strip().lower() not in _SENTINEL_WKT
        for ts_rows in rows_by_ts.values()
        for row in ts_rows
    )
    if not has_geometry:
        raise ValueError(
            "All rows in the emissions CSV have no WKT geometry."
        )

    sorted_timestamps = sorted(rows_by_ts.keys())
    # Interval is used to compute end_ts = ts + time_interval for each process() call
    time_interval = _infer_time_interval(sorted_timestamps)
    logger.info(
        "generate_austal_from_csv: %d timesteps, interval=%s",
        len(sorted_timestamps),
        time_interval,
    )

    os.makedirs(output_dir, exist_ok=True)

    # Temp SpatiaLite DB is only needed during Grid3D init and beginJob for ST_Transform;
    # it is deleted automatically when the context exits
    with _temp_spatialite_db() as temp_db_path:
        grid = _build_grid3d(grid_config, temp_db_path)

        # Merge caller config with the keys controlled internally by this function
        module_cfg = dict(austal_config)
        module_cfg.update(
            {
                "output_path": output_dir,
                "pollutants_list": selected_pollutants,
                "title": "OpenALAQS CSV AUSTAL generation",
                "grid": grid,
                "receptors": gpd.GeoDataFrame(),  # no receptor points in CSV mode
            }
        )

        austal = AUSTALDispersionModule(module_cfg)
        # beginJob writes the austal.txt header and initialises internal state
        austal.beginJob()

        for ts in sorted_timestamps:
            end_ts = ts + time_interval
            result_tuples = []

            for row in rows_by_ts[ts]:
                em = _build_emission(row)
                wkt = em.getGeometryText()
                # Skip rows with no geometry; they cannot be assigned to a grid cell
                if wkt is None:
                    logger.debug(
                        "[%s] source '%s' has no WKT — skipped",
                        ts,
                        row.get(_COL_SOURCE_NAME, "?"),
                    )
                    continue
                source = _CsvSourceAdapter(
                    name=row.get(_COL_SOURCE_NAME) or "csv_source",
                    height=0.0,
                )
                # process() expects a list of (source, [emission]) tuples
                result_tuples.append((source, [em]))

            # Skip timesteps with no spatially-locatable sources
            if not result_tuples:
                continue

            ambient = _lookup_ambient(ts, meteo_map)
            austal.process(ts, end_ts, result_tuples, ambient)

        # endJob flushes series.dmna and per-pollutant grid files to disk
        success = austal.endJob()

    if not success:
        raise RuntimeError(
            "AUSTALDispersionModule.endJob() returned False; "
            "check the log for details."
        )

    logger.info("AUSTAL Input file were created from CSVs in %s", output_dir)
