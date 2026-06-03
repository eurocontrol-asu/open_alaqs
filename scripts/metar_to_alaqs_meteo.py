#!/usr/bin/env python3
"""
metar_to_alaqs_meteo.py
========================
Prepare an Open-ALAQS-compatible meteo.csv from a stream of METAR observations.

This is a standalone utility.  It is NOT invoked by the Open-ALAQS plugin at
run time; users run it once to produce the meteo.csv that the plugin reads
during "Create Output".

Scope
-----
- Accepts METAR observations in three formats (auto-detected by default):
    * IEM ASOS CSV  : "station,valid,metar" header
    * Ogimet text   : leading 12-digit YYYYMMDDHHMM timestamp per line
    * Raw METAR     : one METAR per line, anchored to a year/month
- Computes per-observation ambient temperature (K), pressure (Pa), relative
  humidity (fraction), specific humidity (kg/kg), and wind components,
  hourly-averaged over the study period.
- When --lat and --lon are supplied, computes per-hour Pasquill-Gifford
  stability class from wind, cloud cover and solar elevation, and emits the
  corresponding Obukhov length and mixing height (van Ulden & Holtslag 1985 /
  Nieuwstadt 1981).  Without lat/lon, falls back to a fixed neutral
  atmosphere (L = 99999 m, MH = 914.4 m or whatever --mixing-height
  specifies).
- Writes a CSV with columns matching the Open-ALAQS meteo.csv schema EXACTLY
  as core/interfaces/AmbientCondition.py reads it (header names with unit
  suffixes, SI units throughout).
- Prints a coverage report at the end of the run: source used, records
  retained, original vs. forward-filled hours, per-field coverage.

Recommended METAR sources
-------------------------
The caller is responsible for obtaining the METAR stream.  This script does
NOT include network code; fetch upstream, then pipe in.  Recommended:

  * Iowa Environmental Mesonet ASOS archive
      https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py
      Returns CSV with 'station,valid,metar' columns.  Anonymous,
      rate-limited.  NB: the request's day2/month2/year2 is treated as an
      EXCLUSIVE upper bound; to fetch through 31 December 2025 inclusive,
      set the upper bound to 2026/1/1.
  * NOAA Aviation Weather Center text data service
      https://aviationweather.gov/adds/dataserver  (bulk METAR endpoint).
  * ogimet.com historic METAR archive.  Useful for dates more than a week
      old.  Rate-limited (5 s minimum between requests).
  * pymetar / python-metar pip packages: thin wrappers over the above.

Stability classification (when --lat and --lon are given)
---------------------------------------------------------
Per hour, the script assigns a Pasquill-Gifford class A-F from three
inputs: 10 m wind speed, total cloud cover in oktas (FEW=2, SCT=4, BKN=6,
OVC and VV=8; max coverage among reported layers; absence of cloud groups
= 0 oktas), and analytically-computed solar elevation.

Daytime insolation (Pasquill 1961 / Turner 1970):
  * Solar elevation > 60 deg: strong
  * 35-60 deg: strong or moderate depending on cloud
  * 15-35 deg: moderate or slight depending on cloud
  * 0-15 deg: slight (low-sun, common at mid-latitudes in winter)
  * Heavy cloud (6-7 oktas) downgrades insolation one step
  * Total overcast (8 oktas) forces class D

Night-time (cloud-dependent):
  * >= 4 oktas: D or E depending on wind
  * < 4 oktas: F (wind < 3), E (3-5), D (5+)

PG -> Obukhov length (van Ulden & Holtslag 1985, as adopted in OPS):
  L = -10 (A), -30 (B), -100 (C), 99999 (D), +200 (E), +50 (F)  [m]

PG -> mixing height (Nieuwstadt 1981):
  H = 1500 (A), 1000 (B), 600 (C), 400 (D), 200 (E), 100 (F)  [m]

When --mixing-height is supplied, the per-hour PG-derived MH is capped at
that value (useful for LTO studies that want to keep the CAEP14 3000 ft /
914.4 m ceiling).

Output schema (Open-ALAQS meteo.csv)
------------------------------------
Header names and units are mandatory and match what
core/interfaces/AmbientCondition.py::initAmbientCondition parses from the
CSV.  Column order is fixed:

    Scenario                               text, e.g. "default"
    DateTime(YYYY-mm-dd hh:mm:ss)          UTC, hourly
    Temperature(K)                         Kelvin
    Humidity(kg_water/kg_dry_air)          specific humidity, mixing ratio
    RelativeHumidity(0-1)                  fraction (NOT percent)
    SeaLevelPressure(Pa)                   Pascals (NOT hPa)
    WindSpeed(m/s)                         metres per second
    WindDirection(degrees)                 0-360 true, "999" if missing/VRB
    ObukhovLength(m)                       metres; 99999 = effectively neutral
    MixingHeight(m)                        metres

Missing observations in an hour are forward-filled from the previous hour.
If the first hour has no observation the script exits with an error.

Usage
-----
    python3 metar_to_alaqs_meteo.py \\
        --station EHRD --lat 51.95 --lon 4.44 \\
        --start 2025-12-01T06:00 \\
        --end   2025-12-03T09:00 \\
        --scenario "AIRPORT_A training" \\
        --input  metar_rotterdam_dec_1_3.txt \\
        --output AIRPORT_A_meteo.csv

Without --lat/--lon the script reverts to fixed-neutral L and MH as in
prior versions.  See README for the full list of options.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional, Tuple

# --------------------------------------------------------------------------- #
# METAR parsing                                                               #
# --------------------------------------------------------------------------- #


@dataclass
class MetarObs:
    """A minimal subset of METAR fields needed for Open-ALAQS meteo.csv."""

    time_utc: dt.datetime
    station: str
    wind_dir_deg: Optional[float]  # 0-360, None if VRB or missing
    wind_speed_kt: Optional[float]  # knots
    temp_c: Optional[float]  # celsius
    dewpoint_c: Optional[float]  # celsius
    qnh_hpa: Optional[float]  # sea-level pressure hPa
    oktas: int  # 0-8, max coverage among layers; 0 if none parsed


# ---- Patterns for the individual METAR groups we care about ----

_RE_TIME = re.compile(r"\b(\d{2})(\d{2})(\d{2})Z\b")  # DDHHMM
_RE_WIND = re.compile(r"\b(VRB|\d{3})(\d{2,3})(?:G\d{2,3})?KT\b")
_RE_TEMP_DEW = re.compile(r"\b(M?\d{2})/(M?\d{2})\b")
_RE_QNH_Q = re.compile(r"\bQ(\d{4})\b")  # Europe hPa
_RE_QNH_A = re.compile(r"\bA(\d{4})\b")  # US inHg x100
_RE_STATION = re.compile(r"\b([A-Z]{4})\b")
_RE_SKY = re.compile(
    r"\b(SKC|CLR|NSC|NCD|CAVOK|FEW\d{3}|SCT\d{3}|BKN\d{3}|OVC\d{3}|VV\d{3})\b"
)


def _to_float_m(s: str) -> float:
    """Convert METAR temperature-style '05' or 'M03' to float celsius."""
    if s.startswith("M"):
        return -float(s[1:])
    return float(s)


def _oktas_from_token(tok: str) -> int:
    """Map a METAR sky-group token to oktas (0-8)."""
    if tok in ("SKC", "CLR", "NSC", "NCD", "CAVOK"):
        return 0
    if tok.startswith("VV"):
        return 8
    return {"FEW": 2, "SCT": 4, "BKN": 6, "OVC": 8}.get(tok[:3], 0)


def parse_metar(line: str, report_day: dt.date) -> Optional[MetarObs]:
    """Parse one METAR line into a MetarObs, or None if it cannot be parsed.

    `report_day` provides the year/month context for the DDHHMM Z group.
    For inputs spanning more than one calendar month, prefer
    `parse_metar_with_timestamp(t_utc, line)` instead, which takes an
    authoritative timestamp from outside the line.
    """
    line = line.strip()
    if not line or line.startswith(("METAR", "SPECI")) and len(line) < 30:
        return None

    # Time group gives day-of-month/HH/MM UTC
    m = _RE_TIME.search(line)
    if not m:
        return None
    day, hh, mm = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        t = dt.datetime(
            report_day.year, report_day.month, day, hh, mm, tzinfo=dt.timezone.utc
        )
    except ValueError:
        prev = report_day.replace(day=1) - dt.timedelta(days=1)
        t = dt.datetime(prev.year, prev.month, day, hh, mm, tzinfo=dt.timezone.utc)

    # Station ID
    stn_match = _RE_STATION.search(line)
    station = stn_match.group(1) if stn_match else ""

    # Wind
    wind_dir = wind_spd = None
    mw = _RE_WIND.search(line)
    if mw:
        dir_str = mw.group(1)
        wind_dir = None if dir_str == "VRB" else float(dir_str)
        wind_spd = float(mw.group(2))

    # Temperature / dewpoint
    temp = dew = None
    mt = _RE_TEMP_DEW.search(line)
    if mt:
        temp = _to_float_m(mt.group(1))
        dew = _to_float_m(mt.group(2))

    # QNH
    qnh_hpa = None
    mq = _RE_QNH_Q.search(line)
    if mq:
        qnh_hpa = float(mq.group(1))
    else:
        ma = _RE_QNH_A.search(line)
        if ma:
            inhg = float(ma.group(1)) / 100.0
            qnh_hpa = inhg * 33.8639

    # Sky condition: max okta value among reported layers; absence = 0 oktas
    oktas = 0
    for tok in _RE_SKY.findall(line):
        oktas = max(oktas, _oktas_from_token(tok))

    obs = MetarObs(
        time_utc=t,
        station=station,
        wind_dir_deg=wind_dir,
        wind_speed_kt=wind_spd,
        temp_c=temp,
        dewpoint_c=dew,
        qnh_hpa=qnh_hpa,
        oktas=oktas,
    )
    return _validate(obs)


def parse_metar_with_timestamp(t_utc: dt.datetime, line: str) -> Optional[MetarObs]:
    """Parse one METAR line, using an authoritative external timestamp.

    Use this when the caller already knows the issue time independently of
    the METAR's DDHHMM Z group: IEM CSV's `valid` column, Ogimet's leading
    12-digit prefix, a bulletin header, etc.  Avoids the multi-month
    ambiguity of `parse_metar(line, report_day)`.
    """
    obs = parse_metar(line, t_utc.date())
    if obs is not None:
        obs.time_utc = t_utc
    return obs


def _validate(obs: Optional[MetarObs]) -> Optional[MetarObs]:
    """Field-by-field plausibility check; nulls broken fields, keeps the row.

    Bounds:
      * temperature, dewpoint: [-90, +60] degC
      * QNH: [870, 1085] hPa
      * wind speed: [0, 250] kt
      * wind direction: [0, 360) deg

    Wider than any real METAR ever needs but tight enough to catch
    encoding/parser errors (e.g. a stray 9999 read as a wind speed).
    """
    if obs is None:
        return None
    if obs.temp_c is not None and not (-90.0 <= obs.temp_c <= 60.0):
        obs.temp_c = None
    if obs.dewpoint_c is not None and not (-90.0 <= obs.dewpoint_c <= 60.0):
        obs.dewpoint_c = None
    if obs.qnh_hpa is not None and not (870.0 <= obs.qnh_hpa <= 1085.0):
        obs.qnh_hpa = None
    if obs.wind_speed_kt is not None and not (0.0 <= obs.wind_speed_kt <= 250.0):
        obs.wind_speed_kt = None
    if obs.wind_dir_deg is not None and not (0.0 <= obs.wind_dir_deg < 360.0):
        obs.wind_dir_deg = None
    return obs


# --------------------------------------------------------------------------- #
# Derived quantities                                                          #
# --------------------------------------------------------------------------- #


def relative_humidity_from_temp_dew(temp_c: float, dew_c: float) -> float:
    """Magnus-form RH as a fraction (0-1) from dry-bulb and dewpoint."""
    a, b = 17.625, 243.04
    rh = math.exp(a * dew_c / (b + dew_c)) / math.exp(a * temp_c / (b + temp_c))
    return max(0.0, min(1.0, rh))


def saturation_vapor_pressure_pa(temp_c: float) -> float:
    """Magnus-Tetens saturation vapour pressure (Pa) for temperature in degC.

    es(T) = 611.2 * exp(17.625 * T / (243.04 + T))   for T in degC, es in Pa.
    Standard form used in atmospheric science; agrees with WMO Annex VI to
    within 0.05 % over -40 .. +50 degC.
    """
    return 611.2 * math.exp(17.625 * temp_c / (243.04 + temp_c))


def specific_humidity_kg_per_kg(
    temp_c: float, dew_c: float, p_total_pa: float
) -> float:
    """Specific humidity (mixing ratio) in kg water / kg dry air."""
    rh = relative_humidity_from_temp_dew(temp_c, dew_c)
    es = saturation_vapor_pressure_pa(temp_c)
    e = rh * es
    if p_total_pa <= e:
        return 0.0
    return 0.62198 * e / (p_total_pa - e)


def wind_kt_to_ms(kt: float) -> float:
    return kt * 0.514444


def solar_elevation_deg(dt_utc: dt.datetime, lat: float, lon: float) -> float:
    """Solar elevation in degrees from declination and equation of time."""
    doy = dt_utc.timetuple().tm_yday
    hour = dt_utc.hour + dt_utc.minute / 60.0
    decl = math.radians(23.45 * math.sin(math.radians(360.0 / 365.0 * (doy - 81))))
    B = math.radians(360.0 / 365.0 * (doy - 81))
    eot = 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)
    solar_time = hour + lon / 15.0 + eot / 60.0
    ha = math.radians(15.0 * (solar_time - 12.0))
    lat_r = math.radians(lat)
    sin_elev = math.sin(lat_r) * math.sin(decl) + math.cos(lat_r) * math.cos(
        decl
    ) * math.cos(ha)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))


def pasquill_gifford(wind_ms: float, oktas: int, solar_elev: float) -> str:
    """Assign a Pasquill-Gifford class A-F (Pasquill 1961 / Turner 1970)."""
    if solar_elev <= 0:
        if oktas >= 4:
            if wind_ms < 2:
                return "E"
            elif wind_ms < 3:
                return "E"
            elif wind_ms < 5:
                return "D"
            else:
                return "D"
        else:
            if wind_ms < 3:
                return "F"
            elif wind_ms < 5:
                return "E"
            elif wind_ms < 6:
                return "D"
            else:
                return "D"

    if oktas >= 8:
        return "D"

    if solar_elev > 60:
        ins = "strong"
    elif solar_elev > 35:
        ins = "strong" if oktas <= 3 else "moderate"
    elif solar_elev > 15:
        ins = "moderate" if oktas <= 4 else "slight"
    else:
        ins = "slight"

    if oktas >= 6:
        ins = {"strong": "moderate", "moderate": "slight", "slight": "slight"}[ins]

    table = {
        "strong": [(2, "A"), (3, "A"), (5, "B"), (6, "C"), (999, "C")],
        "moderate": [(2, "A"), (3, "B"), (5, "B"), (6, "C"), (999, "D")],
        "slight": [(2, "B"), (3, "C"), (5, "C"), (6, "D"), (999, "D")],
    }
    for threshold, cls in table[ins]:
        if wind_ms < threshold:
            return cls
    return "D"


PG_TO_L = {"A": -10.0, "B": -30.0, "C": -100.0, "D": 99999.0, "E": 200.0, "F": 50.0}
PG_TO_MH = {"A": 1500.0, "B": 1000.0, "C": 600.0, "D": 400.0, "E": 200.0, "F": 100.0}


# --------------------------------------------------------------------------- #
# Hourly resampling                                                           #
# --------------------------------------------------------------------------- #


def _hour_bucket(t: dt.datetime) -> dt.datetime:
    return t.replace(minute=0, second=0, microsecond=0)


def hourly_average(
    obs_stream: Iterable[MetarObs],
    start: dt.datetime,
    end: dt.datetime,
) -> Iterator[dict]:
    """Bucket METARs into hourly averages across [start, end] inclusive.

    For each hour produces a dict with keys datetime, temp_c, dew_c, rh,
    qnh_hpa, wind_dir_deg, wind_speed_ms, oktas.  Missing observations are
    forward-filled from the most recent populated hour.  Adds a `_source`
    key with value 'observed' or 'forward_fill' for downstream coverage
    reporting; the CSV writer ignores this key.

    :raises RuntimeError: if the first hour has no data to forward-fill from.
    """
    if start.tzinfo is not None:
        start = start.replace(tzinfo=None)
    if end.tzinfo is not None:
        end = end.replace(tzinfo=None)

    buckets: "OrderedDict[dt.datetime, list]" = OrderedDict()
    hour = start.replace(minute=0, second=0, microsecond=0)
    while hour <= end:
        buckets[hour] = []
        hour += dt.timedelta(hours=1)

    for obs in obs_stream:
        t_naive = (
            obs.time_utc.replace(tzinfo=None) if obs.time_utc.tzinfo else obs.time_utc
        )
        h = t_naive.replace(minute=0, second=0, microsecond=0)
        if h in buckets:
            buckets[h].append(obs)

    last_good: Optional[dict] = None
    for h, observations in buckets.items():
        if observations:
            temps = [o.temp_c for o in observations if o.temp_c is not None]
            dews = [o.dewpoint_c for o in observations if o.dewpoint_c is not None]
            qnhs = [o.qnh_hpa for o in observations if o.qnh_hpa is not None]
            wdir = [o.wind_dir_deg for o in observations if o.wind_dir_deg is not None]
            wspd = [
                wind_kt_to_ms(o.wind_speed_kt)
                for o in observations
                if o.wind_speed_kt is not None
            ]
            okt = [o.oktas for o in observations]
            temp_c = sum(temps) / len(temps) if temps else None
            dew_c = sum(dews) / len(dews) if dews else None
            rh = (
                relative_humidity_from_temp_dew(temp_c, dew_c)
                if temp_c is not None and dew_c is not None
                else None
            )
            oktas_avg = int(round(sum(okt) / len(okt))) if okt else 0
            record = {
                "datetime": h,
                "temp_c": temp_c,
                "dew_c": dew_c,
                "rh": rh,
                "qnh_hpa": sum(qnhs) / len(qnhs) if qnhs else None,
                "wind_dir_deg": sum(wdir) / len(wdir) if wdir else None,
                "wind_speed_ms": sum(wspd) / len(wspd) if wspd else None,
                "oktas": max(0, min(8, oktas_avg)),
                "_source": "observed",
            }
            last_good = record
            yield record
        elif last_good is not None:
            carried = dict(last_good)
            carried["datetime"] = h
            carried["_source"] = "forward_fill"
            yield carried
        else:
            raise RuntimeError(
                f"No METAR data for first hour {h.isoformat()} and no prior hour "
                "to forward-fill from.  Provide observations covering or preceding "
                "the study start time."
            )


# --------------------------------------------------------------------------- #
# CSV writer                                                                  #
# --------------------------------------------------------------------------- #


_COLUMNS = [
    "Scenario",
    "DateTime(YYYY-mm-dd hh:mm:ss)",
    "Temperature(K)",
    "Humidity(kg_water/kg_dry_air)",
    "RelativeHumidity(0-1)",
    "SeaLevelPressure(Pa)",
    "WindSpeed(m/s)",
    "WindDirection(degrees)",
    "ObukhovLength(m)",
    "MixingHeight(m)",
]

_OBUKHOV_NEUTRAL_M = 99999.0
_DEFAULT_MIXING_HEIGHT_M = 914.4


def _per_row_l_and_mh(
    row: dict,
    lat: Optional[float],
    lon: Optional[float],
    mh_cap_m: Optional[float],
) -> "Tuple[float, float, Optional[str]]":
    if lat is None or lon is None or row.get("wind_speed_ms") is None:
        return (
            _OBUKHOV_NEUTRAL_M,
            _DEFAULT_MIXING_HEIGHT_M if mh_cap_m is None else mh_cap_m,
            None,
        )

    se = solar_elevation_deg(row["datetime"].replace(tzinfo=dt.timezone.utc), lat, lon)
    pg = pasquill_gifford(row["wind_speed_ms"], row.get("oktas", 0) or 0, se)
    L = PG_TO_L[pg]
    MH = PG_TO_MH[pg] if mh_cap_m is None else min(PG_TO_MH[pg], mh_cap_m)
    return (L, MH, pg)


def write_alaqs_meteo_csv(
    rows: Iterable[dict],
    scenario: str,
    out_path: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    mixing_height_cap_m: Optional[float] = None,
) -> int:
    """Write an Open-ALAQS meteo.csv.  Returns the number of rows written."""
    n = 0
    with open(out_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(_COLUMNS)
        for r in rows:
            temp_k = "" if r["temp_c"] is None else f"{r['temp_c'] + 273.15:.2f}"
            p_pa_str = "" if r["qnh_hpa"] is None else f"{r['qnh_hpa'] * 100.0:.0f}"
            if (
                r["temp_c"] is not None
                and r["dew_c"] is not None
                and r["qnh_hpa"] is not None
            ):
                q = specific_humidity_kg_per_kg(
                    r["temp_c"], r["dew_c"], r["qnh_hpa"] * 100.0
                )
                q_str = f"{q:.5f}"
            else:
                q_str = ""
            rh_str = "" if r["rh"] is None else f"{r['rh']:.3f}"

            L, MH, _pg = _per_row_l_and_mh(r, lat, lon, mixing_height_cap_m)

            w.writerow(
                [
                    scenario,
                    r["datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                    temp_k,
                    q_str,
                    rh_str,
                    p_pa_str,
                    "" if r["wind_speed_ms"] is None else f"{r['wind_speed_ms']:.2f}",
                    "999" if r["wind_dir_deg"] is None else f"{r['wind_dir_deg']:.0f}",
                    f"{L:.0f}",
                    f"{MH:.1f}",
                ]
            )
            n += 1
    return n


# --------------------------------------------------------------------------- #
# Optional HTML plots (stability bar, windrose)                               #
# --------------------------------------------------------------------------- #
# Standalone HTML files matching the format produced by the project's Dataiku
# notebook (meteo_plots.txt, cell 3) and the separate metar_plots.py helper.
# Stdlib-only; the JS for the bar chart is loaded from a Chart.js CDN, the
# windrose is a hand-rolled SVG.


def _enrich_with_pg(rows: list, lat: Optional[float], lon: Optional[float]) -> None:
    """Add a 'pg' key (PG class A-F or None) to every row in place.

    Uses the same calculation as _per_row_l_and_mh so the stability plot's
    class assignment matches the CSV's ObukhovLength column row-for-row.
    Rows where lat/lon or wind speed are missing get pg=None and are
    excluded from the stability plot.
    """
    for r in rows:
        _L, _MH, pg = _per_row_l_and_mh(r, lat, lon, None)
        r["pg"] = pg


def build_stability_html(rows: Iterable[dict], icao: str) -> str:
    """Render the monthly PG stacked-bar stability plot as inline HTML."""
    pg_classes = ["A/B", "C", "D", "E", "F"]
    months_lbl = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]

    counts = {m: {c: 0 for c in pg_classes} for m in range(1, 13)}
    totals = {m: 0 for m in range(1, 13)}
    by_class = {c: 0 for c in pg_classes}
    n = 0
    for r in rows:
        pg = r.get("pg")
        if pg is None:
            continue
        cls = "A/B" if pg in ("A", "B") else pg
        month = r["datetime"].month
        counts[month][cls] += 1
        totals[month] += 1
        by_class[cls] += 1
        n += 1

    monthly = {
        c: [round(counts[m][c] / max(totals[m], 1) * 100, 1) for m in range(1, 13)]
        for c in pg_classes
    }

    unstable = round((by_class["A/B"] + by_class["C"]) / max(n, 1) * 100, 1)
    neutral = round(by_class["D"] / max(n, 1) * 100, 1)
    stable = round((by_class["E"] + by_class["F"]) / max(n, 1) * 100, 1)

    return f"""<style>
.stab-wrap{{padding:1rem 0;font-family:system-ui,sans-serif}}
.stab-legend{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:12px;font-size:12px;color:#666}}
.stab-swatch{{width:10px;height:10px;border-radius:2px;display:inline-block;margin-right:4px}}
.stab-card{{background:#f7f7f5;border-radius:8px;padding:10px 16px;text-align:center;flex:1;min-width:80px}}
.stab-card-label{{font-size:11px;color:#666}}
.stab-card-value{{font-size:20px;font-weight:500;color:#222}}
@media (prefers-color-scheme:dark){{
  .stab-wrap{{color:#e0deda}}
  .stab-card{{background:#26261f}}
  .stab-card-label{{color:#888780}}
  .stab-card-value{{color:#e0deda}}
}}
</style>
<div class="stab-wrap">
  <div class="stab-legend">
    <span><span class="stab-swatch" style="background:#D85A30"></span>A/B - unstable (-10 to -30 m)</span>
    <span><span class="stab-swatch" style="background:#EF9F27"></span>C - slightly unstable (-100 m)</span>
    <span><span class="stab-swatch" style="background:#888780"></span>D - neutral (99999 m)</span>
    <span><span class="stab-swatch" style="background:#5DCAA5"></span>E - slightly stable (+200 m)</span>
    <span><span class="stab-swatch" style="background:#185FA5"></span>F - stable (+50 m)</span>
  </div>
  <div style="position:relative;width:100%;height:280px;"><canvas id="stabChart_{icao}"></canvas></div>
  <div style="display:flex;justify-content:space-between;margin-top:20px;gap:8px;flex-wrap:wrap;">
    <div class="stab-card">
      <div class="stab-card-label">unstable (A/B/C)</div>
      <div class="stab-card-value">{unstable}%</div>
    </div>
    <div class="stab-card">
      <div class="stab-card-label">neutral (D)</div>
      <div class="stab-card-value">{neutral}%</div>
    </div>
    <div class="stab-card">
      <div class="stab-card-label">stable (E/F)</div>
      <div class="stab-card-value">{stable}%</div>
    </div>
    <div class="stab-card">
      <div class="stab-card-label">hours modelled</div>
      <div class="stab-card-value">{n:,}</div>
    </div>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
(function(){{
const months = {json.dumps(months_lbl)};
const monthly = {json.dumps(monthly)};
const colors = ['#D85A30','#EF9F27','#888780','#5DCAA5','#185FA5'];
const classes = ['A/B','C','D','E','F'];
new Chart(document.getElementById('stabChart_{icao}'), {{
  type: 'bar',
  data: {{
    labels: months,
    datasets: classes.map((c,i) => ({{
      label: c, data: monthly[c], backgroundColor: colors[i], stack: 'pg', borderWidth: 0
    }}))
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.raw.toFixed(1)}}%` }} }}
    }},
    scales: {{
      x: {{ stacked: true, ticks: {{ color:'#888780', font:{{size:11}}, autoSkip:false, maxRotation:0 }}, grid:{{display:false}} }},
      y: {{ stacked: true, min:0, max:100,
            ticks: {{ color:'#888780', font:{{size:11}}, callback: v => v+'%' }},
            grid: {{ color:'rgba(136,135,128,0.15)', lineWidth:0.5 }} }}
    }}
  }}
}});
}})();
</script>
"""


def build_windrose_html(rows: Iterable[dict], icao: str) -> str:
    """Render the 16-sector windrose as inline HTML/SVG."""
    sectors = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    rows = list(rows)

    valid = [
        r
        for r in rows
        if r.get("wind_speed_ms") is not None and r.get("wind_dir_deg") is not None
    ]
    n_total = len(valid)
    if n_total == 0:
        return f'<p style="color:#888;padding:1rem 0;">No wind data for {icao}</p>'

    n_calm = sum(1 for r in valid if r["wind_speed_ms"] < 0.5)
    calms_pct = round(100.0 * n_calm / n_total, 1)

    # 16 sectors x 4 speed bins (0.5-2, 2-5, 5-10, >=10 m/s).  Calms (<0.5)
    # are excluded from the rose bars and reported separately above.
    sector_counts = [[0, 0, 0, 0] for _ in range(16)]
    for r in valid:
        ws = r["wind_speed_ms"]
        if ws < 0.5:
            continue
        wd = r["wind_dir_deg"] % 360
        sec = int((wd + 11.25) // 22.5) % 16
        if ws < 2.0:
            sb = 0
        elif ws < 5.0:
            sb = 1
        elif ws < 10.0:
            sb = 2
        else:
            sb = 3
        sector_counts[sec][sb] += 1

    data = [[round(100.0 * c / n_total, 3) for c in row] for row in sector_counts]

    return f"""<style>
.wr-wrap{{display:flex;flex-direction:column;align-items:center;padding:1rem 0;font-family:system-ui,sans-serif}}
.wr-legend{{display:flex;gap:16px;margin-top:12px;font-size:12px;color:#666}}
.wr-swatch{{width:10px;height:10px;border-radius:2px;display:inline-block;margin-right:4px}}
@media (prefers-color-scheme:dark){{
  .wr-wrap{{color:#e0deda}}
  .wr-legend{{color:#888780}}
}}
</style>
<div class="wr-wrap">
  <svg id="wr_{icao}" viewBox="0 0 440 440" width="100%" style="max-width:440px;"></svg>
  <div class="wr-legend">
    <span><span class="wr-swatch" style="background:#B5D4F4"></span>0-2 m/s</span>
    <span><span class="wr-swatch" style="background:#378ADD"></span>2-5 m/s</span>
    <span><span class="wr-swatch" style="background:#185FA5"></span>5-10 m/s</span>
    <span><span class="wr-swatch" style="background:#0C447C"></span>&gt;10 m/s</span>
  </div>
  <p style="font-size:12px;color:#888;margin-top:8px;">Calms (&lt;0.5 m/s): {calms_pct}% of hours not shown</p>
</div>
<script>
(function(){{
const sectors = {json.dumps(sectors)};
const data = {json.dumps(data)};
const colors = ['#B5D4F4','#378ADD','#185FA5','#0C447C'];
const ns=16, cx=220, cy=220, maxR=170;
const totals = data.map(r => r.reduce((a,b)=>a+b,0));
const maxPct = Math.max(...totals) || 1;
const isDark = matchMedia('(prefers-color-scheme:dark)').matches;
const textCol = isDark ? '#c2c0b6' : '#444441';
const gridCol = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.07)';
const svg = document.getElementById('wr_{icao}');
function pct2r(p) {{ return p / maxPct * maxR; }}
function polar(deg, r) {{
  const a = (deg-90)*Math.PI/180;
  return [cx + r*Math.cos(a), cy + r*Math.sin(a)];
}}
[Math.round(maxPct/3), Math.round(2*maxPct/3), Math.round(maxPct)].forEach(p => {{
  const r = pct2r(p);
  const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
  c.setAttribute('cx',cx); c.setAttribute('cy',cy); c.setAttribute('r',r);
  c.setAttribute('fill','none'); c.setAttribute('stroke',gridCol); c.setAttribute('stroke-width','0.5');
  svg.appendChild(c);
  const t = document.createElementNS('http://www.w3.org/2000/svg','text');
  t.setAttribute('x',cx+4); t.setAttribute('y',cy-r+3);
  t.setAttribute('font-size','9'); t.setAttribute('fill',textCol); t.setAttribute('opacity','0.6');
  t.textContent = p+'%'; svg.appendChild(t);
}});
for(let i=0;i<ns;i++) {{
  const [x2,y2] = polar(i*360/ns, maxR+8);
  const l = document.createElementNS('http://www.w3.org/2000/svg','line');
  l.setAttribute('x1',cx); l.setAttribute('y1',cy);
  l.setAttribute('x2',x2); l.setAttribute('y2',y2);
  l.setAttribute('stroke',gridCol); l.setAttribute('stroke-width','0.5');
  svg.appendChild(l);
}}
const halfW = (2*Math.PI/ns)*0.42;
for(let si=0;si<ns;si++) {{
  const base = (si*360/ns - 90)*Math.PI/180;
  let rIn=0;
  for(let bi=0;bi<4;bi++) {{
    const val = data[si][bi];
    if(val<0.001){{ rIn+=val; continue; }}
    const rOut = pct2r(rIn+val);
    const a1=base-halfW, a2=base+halfW;
    const pts = [[rIn,a1],[rOut,a1],[rOut,a2],[rIn,a2]].map(([r,a])=>[cx+r*Math.cos(a),cy+r*Math.sin(a)]);
    const path = document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d',`M${{pts[0]}} L${{pts[1]}} A${{rOut}},${{rOut}} 0 0,1 ${{pts[2]}} L${{pts[3]}} A${{rIn}},${{rIn}} 0 0,0 ${{pts[0]}} Z`);
    path.setAttribute('fill',colors[bi]); path.setAttribute('stroke','none');
    svg.appendChild(path);
    rIn+=val;
  }}
}}
sectors.forEach((s,i) => {{
  const [x,y] = polar(i*360/ns, maxR+20);
  const t = document.createElementNS('http://www.w3.org/2000/svg','text');
  t.setAttribute('x',x); t.setAttribute('y',y);
  t.setAttribute('text-anchor','middle'); t.setAttribute('dominant-baseline','middle');
  t.setAttribute('font-size','10'); t.setAttribute('fill',textCol);
  t.textContent=s; svg.appendChild(t);
}});
}})();
</script>
"""


def _write_plots(
    rows: list,
    plots_dir: str,
    icao: str,
    year: int,
    lat: Optional[float],
    lon: Optional[float],
    file=sys.stderr,
) -> None:
    """Render the stability and windrose HTML files into plots_dir.

    Stability requires lat/lon (needed for PG classification); without them
    a notice is printed and only the windrose is produced.  Filenames are
    {icao.lower()}_{year}_stability.html and {icao.lower()}_{year}_windrose.html.
    """
    os.makedirs(plots_dir, exist_ok=True)
    label = (icao or "STATION").upper()

    if lat is not None and lon is not None:
        _enrich_with_pg(rows, lat, lon)
        stab_path = os.path.join(plots_dir, f"{label.lower()}_{year}_stability.html")
        with open(stab_path, "w", encoding="utf-8") as f:
            f.write(build_stability_html(rows, label))
        print(f"[plots] wrote {stab_path}", file=file)
    else:
        print(
            "[plots] skipping stability plot: --lat and --lon are required "
            "to assign PG classes.",
            file=file,
        )

    wind_path = os.path.join(plots_dir, f"{label.lower()}_{year}_windrose.html")
    with open(wind_path, "w", encoding="utf-8") as f:
        f.write(build_windrose_html(rows, label))
    print(f"[plots] wrote {wind_path}", file=file)


# --------------------------------------------------------------------------- #
# Input adapters                                                              #
# --------------------------------------------------------------------------- #
# Each adapter consumes a text file-like object and yields (t_utc, raw_metar)
# tuples.  The top-level `iter_observations` sniffs the first non-blank line
# and routes to the right adapter, or honours an explicit --source override.


_RE_OGIMET_LINE = re.compile(r"^(\d{12})\s+(?:METAR|SPECI)\s+(.+?)=?\s*$")


def _iter_iem_csv(fh) -> Iterator[Tuple[dt.datetime, str]]:
    """IEM ASOS CSV: 'station,valid,metar[,...]' with valid = 'YYYY-MM-DD HH:MM'."""
    rdr = csv.DictReader(fh)
    if (
        rdr.fieldnames is None
        or "valid" not in rdr.fieldnames
        or "metar" not in rdr.fieldnames
    ):
        raise ValueError(
            "IEM CSV adapter requires columns 'valid' and 'metar'; "
            f"got {rdr.fieldnames}"
        )
    for row in rdr:
        valid = (row.get("valid") or "").strip()
        metar = (row.get("metar") or "").strip()
        if not valid or not metar:
            continue
        try:
            t = dt.datetime.strptime(valid, "%Y-%m-%d %H:%M").replace(
                tzinfo=dt.timezone.utc
            )
        except ValueError:
            continue
        yield t, metar


def _iter_ogimet(fh) -> Iterator[Tuple[dt.datetime, str]]:
    """Ogimet text: '<YYYYMMDDHHMM> METAR <station> ...='."""
    for raw in fh:
        m = _RE_OGIMET_LINE.match(raw.strip())
        if not m:
            continue
        ts_str, body = m.group(1), m.group(2)
        try:
            t = dt.datetime(
                int(ts_str[:4]),
                int(ts_str[4:6]),
                int(ts_str[6:8]),
                int(ts_str[8:10]),
                int(ts_str[10:12]),
                tzinfo=dt.timezone.utc,
            )
        except ValueError:
            continue
        yield t, body


def _iter_raw_metars(
    fh, anchor_year_month: Tuple[int, int]
) -> Iterator[Tuple[dt.datetime, str]]:
    """One METAR per line, no external timestamp.

    Constructs (t_utc, line) using the METAR's DDHHMM Z group and an anchor
    (year, month) for the first record.  Walks the stream and advances the
    anchor month when the day-of-month decreases sharply, which is the
    standard month-rollover signal in chronologically-ordered METAR feeds.
    """
    if anchor_year_month is None:
        raise ValueError(
            "Raw METAR adapter requires --anchor-year-month YYYY-MM "
            "(defaults to the month of --start)."
        )
    cur_year, cur_month = anchor_year_month
    last_day = 0
    for raw in fh:
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("METAR ") or raw.startswith("SPECI "):
            body = raw.split(None, 1)[1] if " " in raw else raw
        else:
            body = raw
        m = _RE_TIME.search(body)
        if not m:
            continue
        day = int(m.group(1))
        hh = int(m.group(2))
        mm = int(m.group(3))
        if last_day > 0 and day < last_day - 5:
            if cur_month == 12:
                cur_year += 1
                cur_month = 1
            else:
                cur_month += 1
        last_day = day
        try:
            t = dt.datetime(cur_year, cur_month, day, hh, mm, tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        yield t, body


def sniff_format(first_line: str) -> Optional[str]:
    """Guess the input format from the first non-blank line.

    Returns 'iem-csv', 'ogimet', 'raw', or None if no signal matches.
    """
    s = first_line.strip()
    if not s:
        return None
    if s.lower().startswith("station,valid"):
        return "iem-csv"
    if re.match(r"^\d{12}\s+(?:METAR|SPECI)\b", s):
        return "ogimet"
    if re.match(r"^(?:METAR|SPECI)\s+[A-Z]{4}", s) or re.match(
        r"^[A-Z]{4}\s+\d{6}Z\b", s
    ):
        return "raw"
    return None


def iter_observations(
    input_path: str,
    source: str = "auto",
    anchor_year_month: Optional[Tuple[int, int]] = None,
) -> Iterator[Tuple[dt.datetime, str]]:
    """Top-level dispatcher.  Yields (t_utc, raw_metar) for every observation."""
    if input_path == "-":
        text = sys.stdin.read()
        if not text.strip():
            return iter([])
        first = text.split("\n", 1)[0]
        fh_outer = io.StringIO(text)
    else:
        # Find the first non-blank line for sniffing, then reopen for reading.
        with open(input_path, "r", encoding="utf-8") as f:
            first = ""
            while True:
                line = f.readline()
                if line == "":  # EOF
                    break
                if line.strip():
                    first = line
                    break
        fh_outer = open(input_path, "r", encoding="utf-8")

    fmt = source if source != "auto" else sniff_format(first)
    if fmt is None:
        fh_outer.close()
        raise ValueError(
            "Could not auto-detect input format.  Pass --source explicitly. "
            f"First non-blank line: {first[:200]!r}"
        )

    if fmt == "iem-csv":
        yield from _iter_iem_csv(fh_outer)
    elif fmt == "ogimet":
        yield from _iter_ogimet(fh_outer)
    elif fmt == "raw":
        yield from _iter_raw_metars(fh_outer, anchor_year_month)
    else:
        fh_outer.close()
        raise ValueError(f"Unknown --source value: {fmt!r}")
    fh_outer.close()


# --------------------------------------------------------------------------- #
# Defensive checks on the normalised (t_utc, raw) stream                      #
# --------------------------------------------------------------------------- #


def filter_window(
    stream: Iterable[Tuple[dt.datetime, str]],
    start: dt.datetime,
    end: dt.datetime,
    stats: dict,
) -> Iterator[Tuple[dt.datetime, str]]:
    """Drop records outside [start, end] UTC.  Tallies drops in stats."""
    s = start if start.tzinfo else start.replace(tzinfo=dt.timezone.utc)
    e = end if end.tzinfo else end.replace(tzinfo=dt.timezone.utc)
    n_dropped = 0
    for t, m in stream:
        if t < s or t > e:
            n_dropped += 1
            continue
        yield t, m
    stats["n_dropped_outside_window"] = n_dropped


def dedup_stream(
    stream: Iterable[Tuple[dt.datetime, str]], stats: dict
) -> Iterator[Tuple[dt.datetime, str]]:
    """Materialise the stream, drop exact (t,text) duplicates, keep the last
    record on (t, different text) collisions, then yield sorted by t."""
    buf: "dict[dt.datetime, str]" = {}
    n_in = 0
    n_exact = 0
    n_collision = 0
    for t, m in stream:
        n_in += 1
        if t in buf:
            if buf[t] == m:
                n_exact += 1
            else:
                n_collision += 1
                buf[t] = m  # keep latest
        else:
            buf[t] = m
    stats["n_input_records"] = n_in
    stats["n_exact_duplicates"] = n_exact
    stats["n_collisions_kept_latest"] = n_collision
    stats["n_after_dedup"] = len(buf)
    for t in sorted(buf):
        yield t, buf[t]


# --------------------------------------------------------------------------- #
# Coverage report                                                             #
# --------------------------------------------------------------------------- #


def coverage_report(
    hourly_rows: list, stats: dict, coverage_floor: float, file=sys.stderr
) -> bool:
    """Print a summary block.  Returns False if coverage is below the floor."""
    total = len(hourly_rows)
    if total == 0:
        print("[coverage] No hourly rows produced.", file=file)
        return False

    n_observed = sum(1 for r in hourly_rows if r.get("_source") == "observed")
    n_filled = total - n_observed
    n_with_t = sum(1 for r in hourly_rows if r.get("temp_c") is not None)
    n_with_w = sum(1 for r in hourly_rows if r.get("wind_speed_ms") is not None)
    n_with_p = sum(1 for r in hourly_rows if r.get("qnh_hpa") is not None)

    print("--- Coverage report ---", file=file)
    print(f"  source:                 {stats.get('source', 'unknown')}", file=file)
    print(f"  input records:          {stats.get('n_input_records', 'n/a')}", file=file)
    print(
        f"  dropped (outside window): {stats.get('n_dropped_outside_window', 0)}",
        file=file,
    )
    print(
        f"  exact duplicates:       {stats.get('n_exact_duplicates', 0)}",
        file=file,
    )
    print(
        f"  collisions kept latest: {stats.get('n_collisions_kept_latest', 0)}",
        file=file,
    )
    print(f"  parse failures:         {stats.get('n_parse_failures', 0)}", file=file)
    print(f"  parsed observations:    {stats.get('n_parsed', 0)}", file=file)
    print(f"  hourly rows total:      {total}", file=file)
    print(
        f"  hourly observed:        {n_observed} ({100 * n_observed / total:.1f}%)",
        file=file,
    )
    print(
        f"  hourly forward-filled:  {n_filled} ({100 * n_filled / total:.1f}%)",
        file=file,
    )
    print(
        f"  temperature present:    {n_with_t} ({100 * n_with_t / total:.1f}%)",
        file=file,
    )
    print(
        f"  wind present:           {n_with_w} ({100 * n_with_w / total:.1f}%)",
        file=file,
    )
    print(
        f"  pressure present:       {n_with_p} ({100 * n_with_p / total:.1f}%)",
        file=file,
    )

    # The floor check fires if any of three indicators falls below the
    # threshold: fraction of hours with an actual observation (rather than
    # forward-fill), and fraction of hours with usable temperature and wind.
    # Heavy forward-filling shouldn't pass silently; it usually means the
    # source is too sparse for the requested window.
    floor = coverage_floor
    indicators = {
        "observed": n_observed / total,
        "temperature": n_with_t / total,
        "wind": n_with_w / total,
    }
    failing = {k: v for k, v in indicators.items() if v < floor}
    if failing:
        details = ", ".join(f"{k} {100 * v:.1f}%" for k, v in failing.items())
        print(
            f"[coverage] WARNING: {details} below floor {100 * floor:.1f}%. "
            f"Consider fetching from a different source or widening the window.",
            file=file,
        )
        return False
    return True


# --------------------------------------------------------------------------- #
# Backward-compat wrapper                                                     #
# --------------------------------------------------------------------------- #


def read_metar_stream(fh, report_day: dt.date) -> Iterator[MetarObs]:
    """Legacy line-per-METAR reader retained for backward compatibility.

    Prefer iter_observations() + parse_metar_with_timestamp() for new code.
    """
    for line in fh:
        line = line.strip()
        if not line:
            continue
        obs = parse_metar(line, report_day)
        if obs is not None:
            yield obs


# --------------------------------------------------------------------------- #
# Driver                                                                      #
# --------------------------------------------------------------------------- #


def _parse_anchor(s: Optional[str]) -> Optional[Tuple[int, int]]:
    if s is None:
        return None
    try:
        y, m = s.split("-")
        return (int(y), int(m))
    except (ValueError, AttributeError):
        raise argparse.ArgumentTypeError(
            f"--anchor-year-month must be YYYY-MM, got {s!r}"
        )


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(
        description="Convert a METAR stream into an Open-ALAQS meteo.csv.",
    )
    p.add_argument(
        "--station",
        default="",
        help="Expected ICAO station code (informational; METARs are still "
        "parsed regardless of their station field).",
    )
    p.add_argument(
        "--lat",
        type=float,
        default=None,
        help="Airport latitude in decimal degrees (positive N).  Required "
        "together with --lon to enable Pasquill-Gifford stability "
        "classification; without them the script emits a constant neutral "
        "atmosphere.",
    )
    p.add_argument("--lon", type=float, default=None, help="Airport longitude.")
    p.add_argument(
        "--start",
        required=True,
        help="Study start, ISO-8601 UTC (e.g. 2025-01-01T00:00).",
    )
    p.add_argument(
        "--end",
        required=True,
        help="Study end, ISO-8601 UTC (inclusive of the last hour).",
    )
    p.add_argument(
        "--scenario", default="default", help="Scenario name written to every row."
    )
    p.add_argument(
        "--input", default="-", help="Path to METAR file, or '-' for stdin (default)."
    )
    p.add_argument(
        "--output", default="meteo.csv", help="Output CSV path (default meteo.csv)."
    )
    p.add_argument(
        "--mixing-height",
        type=float,
        default=None,
        help="With --lat/--lon: cap on the PG-derived mixing height.  Without: "
        "constant value written for every row (default 914.4 m).",
    )
    p.add_argument(
        "--source",
        default="auto",
        choices=["auto", "iem-csv", "ogimet", "raw"],
        help="Input format.  'auto' (default) sniffs the first line and "
        "dispatches to one of: 'iem-csv' (station,valid,metar), 'ogimet' "
        "(YYYYMMDDHHMM prefix), or 'raw' (line-per-METAR with --anchor-year-month).",
    )
    p.add_argument(
        "--anchor-year-month",
        default=None,
        help="For --source raw: anchor for the first record's year/month "
        "(YYYY-MM).  Defaults to the year/month of --start.",
    )
    p.add_argument(
        "--coverage-floor",
        type=float,
        default=0.7,
        help="Warn if usable hour coverage (min of temperature and wind "
        "presence) falls below this fraction.  Default 0.7.",
    )
    p.add_argument(
        "--plots-dir",
        default=None,
        help="If set, write the stability and windrose HTML plots into this "
        "directory after the CSV.  Filenames are {station}_{year}_stability.html "
        "and {station}_{year}_windrose.html.  Stability requires --lat/--lon; "
        "windrose works either way.",
    )
    args = p.parse_args(argv)

    if (args.lat is None) != (args.lon is None):
        p.error("--lat and --lon must be supplied together")

    start = dt.datetime.fromisoformat(args.start)
    end = dt.datetime.fromisoformat(args.end)
    if end < start:
        p.error("--end must be >= --start")

    anchor = _parse_anchor(args.anchor_year_month) or (start.year, start.month)

    stats: dict = {}
    obs_stream = iter_observations(
        args.input, source=args.source, anchor_year_month=anchor
    )
    stats["source"] = args.source if args.source != "auto" else "auto (sniffed)"

    obs_stream = filter_window(obs_stream, start, end, stats)
    obs_stream = dedup_stream(obs_stream, stats)

    parsed_list: list = []
    n_parse_failures = 0
    for t, line in obs_stream:
        obs = parse_metar_with_timestamp(t, line)
        if obs is None:
            n_parse_failures += 1
            continue
        parsed_list.append(obs)
    stats["n_parse_failures"] = n_parse_failures
    stats["n_parsed"] = len(parsed_list)

    if not parsed_list:
        print(
            "[fatal] No usable observations after parsing.  Check --source, "
            "--start/--end, and the input file.",
            file=sys.stderr,
        )
        return 2

    hourly_rows = list(hourly_average(parsed_list, start=start, end=end))

    n = write_alaqs_meteo_csv(
        hourly_rows,
        args.scenario,
        args.output,
        lat=args.lat,
        lon=args.lon,
        mixing_height_cap_m=args.mixing_height,
    )

    mode = "PG-classified" if args.lat is not None else "fixed-neutral"
    print(f"Wrote {n} hourly rows to {args.output} ({mode})", file=sys.stderr)
    coverage_report(hourly_rows, stats, args.coverage_floor)

    if args.plots_dir:
        _write_plots(
            hourly_rows,
            args.plots_dir,
            icao=args.station,
            year=start.year,
            lat=args.lat,
            lon=args.lon,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
