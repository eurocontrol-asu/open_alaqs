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
- Parses one METAR record per line from an input text stream (stdin or a file)
- Computes per-observation ambient temperature (K), pressure (Pa), relative
  humidity (fraction), specific humidity (kg/kg), and wind components,
  hourly-averaged over the study period
- When --lat and --lon are supplied, computes per-hour Pasquill-Gifford
  stability class from wind, cloud cover and solar elevation, and emits the
  corresponding Obukhov length and mixing height (van Ulden & Holtslag 1985 /
  Nieuwstadt 1981).  Without lat/lon, falls back to a fixed neutral atmosphere
  (L = 99999 m, MH = 914.4 m or whatever --mixing-height specifies).
- Writes a CSV with columns matching the Open-ALAQS meteo.csv schema EXACTLY
  as `core/interfaces/AmbientCondition.py` reads it (header names with unit
  suffixes, SI units throughout)

Where the METAR data comes from
-------------------------------
The caller is responsible for obtaining the METAR stream.  Recommended
sources:

  * NOAA Aviation Weather Center ADDS text data service
      https://aviationweather.gov/adds/dataserver  (bulk METAR endpoint)
      Anonymous, no API key.  Rate-limited; batch your requests.

  * Iowa Environmental Mesonet ASOS archive
      https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py
      Year-long pulls, anonymous, rate-limited.  Includes the raw METAR
      text in the `metar` column.

  * ogimet.com historic METAR archive
      Useful for dates more than a week in the past.  Rate-limited.

  * pymetar / python-metar pip packages
      Thin wrappers over the above; may simplify polling and caching.

This script does NOT include network code.  Fetch the METAR stream with
curl, wget, a Python script you control, or any of the options above; then
pipe it into this script.  Keeping fetch and parse decoupled means sites
with restrictive network policies can still use the parsing half offline.

METAR parsing
-------------
Uses a minimal in-house parser covering the observation groups Open-ALAQS
needs (time, wind, temperature/dewpoint, QNH, sky condition).  A more
complete parser (python-metar) can be slotted in by replacing
`parse_metar()` with `Metar.Metar(line)` and extracting the same fields
plus the sky-condition list.  The in-house parser is kept to avoid a hard
dependency on a network-fetching library whose install path varies across
QGIS Python environments.

Stability classification (when --lat and --lon are given)
---------------------------------------------------------
Per hour, the script assigns a Pasquill-Gifford class A through F from
three inputs:

  * 10 m wind speed in m/s
  * total cloud cover in oktas, parsed from the METAR sky condition groups
    (FEW = 2, SCT = 4, BKN = 6, OVC and VV = 8; the maximum coverage among
    reported layers is taken, and an absence of cloud groups is treated as
    clear sky / 0 oktas)
  * solar elevation, computed analytically from the airport coordinates
    using declination and the equation of time

The classifier follows Pasquill (1961) as tabulated by Turner (1970):

  * Solar elevation >  0 deg: daytime insolation table.  Insolation is
    graded "strong" (>60 deg), "strong/moderate" (35-60 deg, on cloud),
    "moderate/slight" (15-35 deg, on cloud) or "slight" (0-15 deg, low
    sun).  Heavy cloud (6-7 oktas) downgrades insolation one step;
    total overcast (8 oktas) forces class D.
  * Solar elevation <= 0 deg: cloud-dependent night-time table.  With
    >= 4 oktas of cloud the hour falls in D or E depending on wind;
    with < 4 oktas the hour falls in E or F.

Each PG class maps to a representative Obukhov length (van Ulden &
Holtslag 1985, as adopted in OPS):

  L = -10 (A), -30 (B), -100 (C), 99999 (D), +200 (E), +50 (F)  [m]

and a representative mixing height (Nieuwstadt 1981):

  H = 1500 (A), 1000 (B), 600 (C), 400 (D), 200 (E), 100 (F)  [m]

When --mixing-height is also supplied on the command line, the per-hour
PG-derived MH is capped at that value (useful for LTO studies that want
to keep the CAEP14 3000 ft / 914.4 m ceiling).

Output schema (Open-ALAQS meteo.csv)
------------------------------------
Header names and units are mandatory and match what
`core/interfaces/AmbientCondition.py::initAmbientCondition` parses from
the CSV.  Column order is fixed:

    Scenario                               text, e.g. "default"
    DateTime(YYYY-mm-dd hh:mm:ss)          UTC, hourly
    Temperature(K)                         Kelvin
    Humidity(kg_water/kg_dry_air)          specific humidity, mixing ratio
    RelativeHumidity(0-1)                  fraction (NOT percent)
    SeaLevelPressure(Pa)                   Pascals (NOT hPa)
    WindSpeed(m/s)                         metres per second
    WindDirection(degrees)                 0-360 true
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
prior versions.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

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
_RE_QNH_A = re.compile(r"\bA(\d{4})\b")  # US inHg×100
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
    """Parse one METAR line into a MetarObs, or None if it cannot be parsed."""
    line = line.strip()
    if not line or line.startswith(("METAR", "SPECI")) and len(line) < 30:
        # Header only, no observation
        return None

    # Time group gives day-of-month/HH/MM UTC
    m = _RE_TIME.search(line)
    if not m:
        return None
    day, hh, mm = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # Assume the observation's day-of-month is in the same month as report_day;
    # fall back to the previous month if day > today (handles month rollover).
    try:
        t = dt.datetime(
            report_day.year, report_day.month, day, hh, mm, tzinfo=dt.timezone.utc
        )
    except ValueError:
        prev = report_day.replace(day=1) - dt.timedelta(days=1)
        t = dt.datetime(prev.year, prev.month, day, hh, mm, tzinfo=dt.timezone.utc)

    # Station ID is the first 4-letter group after the header
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
            # A-group is inHg × 100.  Convert to hPa.
            inhg = float(ma.group(1)) / 100.0
            qnh_hpa = inhg * 33.8639

    # Sky condition: take the max okta value among all reported layers.
    # Absent sky groups = 0 oktas (clear).  This matches the convention used
    # in the IEM ASOS / OPS pipeline (cloud_oktas function in compare_meteo.py).
    oktas = 0
    for tok in _RE_SKY.findall(line):
        oktas = max(oktas, _oktas_from_token(tok))

    return MetarObs(
        time_utc=t,
        station=station,
        wind_dir_deg=wind_dir,
        wind_speed_kt=wind_spd,
        temp_c=temp,
        dewpoint_c=dew,
        qnh_hpa=qnh_hpa,
        oktas=oktas,
    )


# --------------------------------------------------------------------------- #
# Derived quantities                                                          #
# --------------------------------------------------------------------------- #


def relative_humidity_from_temp_dew(temp_c: float, dew_c: float) -> float:
    """Magnus formula, returns RH as a fraction 0-1."""
    a, b = 17.625, 243.04
    num = math.exp((a * dew_c) / (b + dew_c))
    den = math.exp((a * temp_c) / (b + temp_c))
    rh = num / den
    return max(0.0, min(1.0, rh))


def saturation_vapor_pressure_pa(temp_c: float) -> float:
    """Magnus-Tetens saturation vapor pressure of water in Pa.

    es(T) = 611.2 * exp(17.625 * T / (243.04 + T))   for T in °C, es in Pa.
    Standard form used in atmospheric science; agrees with WMO Annex VI to
    within 0.05 % over -40 .. +50 °C.
    """
    return 611.2 * math.exp(17.625 * temp_c / (243.04 + temp_c))


def specific_humidity_kg_per_kg(
    temp_c: float, dew_c: float, p_total_pa: float
) -> float:
    """Specific humidity (mixing ratio) in kg water / kg dry air.

    Computed from RH * es(T) to give the actual vapour pressure, then
    w = 0.622 * e / (p - e) per WMO/AMS convention. The 0.622 factor is
    the molar mass ratio M_w / M_d.
    """
    rh = relative_humidity_from_temp_dew(temp_c, dew_c)
    es = saturation_vapor_pressure_pa(temp_c)
    e = rh * es
    # Guard against unphysical p_total <= e (would happen with grossly
    # malformed input, never with real METAR).
    if p_total_pa <= e:
        return 0.0
    return 0.62198 * e / (p_total_pa - e)


def wind_kt_to_ms(kt: float) -> float:
    return kt * 0.514444


def solar_elevation_deg(dt_utc: dt.datetime, lat: float, lon: float) -> float:
    """Solar elevation in degrees from declination and equation of time.

    Closed-form approximation suitable for the PG classification (which only
    cares about elevation bands at 0/15/35/60 deg).  Lat/lon in decimal
    degrees, positive north / east.
    """
    doy = dt_utc.timetuple().tm_yday
    hour = dt_utc.hour + dt_utc.minute / 60.0
    decl = math.radians(23.45 * math.sin(math.radians(360.0 / 365.0 * (doy - 81))))
    B = math.radians(360.0 / 365.0 * (doy - 81))
    eot = 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)  # minutes
    solar_time = hour + lon / 15.0 + eot / 60.0
    ha = math.radians(15.0 * (solar_time - 12.0))
    lat_r = math.radians(lat)
    sin_elev = math.sin(lat_r) * math.sin(decl) + math.cos(lat_r) * math.cos(
        decl
    ) * math.cos(ha)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))


def pasquill_gifford(wind_ms: float, oktas: int, solar_elev: float) -> str:
    """Assign a Pasquill-Gifford class A-F.

    Cloud-dependent night rule (Pasquill 1961 / Turner 1970), with low-sun
    daytime (0 < elev <= 15 deg) treated as 'slight' insolation and total
    overcast forcing D.  This is the corrected form used in the project's
    Dataiku notebook (compare_meteo.py); see notebook history for rationale.
    """
    # Night
    if solar_elev <= 0:
        if oktas >= 4:  # cloudy night
            if wind_ms < 2:
                return "E"
            elif wind_ms < 3:
                return "E"
            elif wind_ms < 5:
                return "D"
            else:
                return "D"
        else:  # clear / nearly clear night
            if wind_ms < 3:
                return "F"
            elif wind_ms < 5:
                return "E"
            elif wind_ms < 6:
                return "D"
            else:
                return "D"

    # Total overcast daytime is D regardless of insolation band
    if oktas >= 8:
        return "D"

    # Daytime insolation band
    if solar_elev > 60:
        ins = "strong"
    elif solar_elev > 35:
        ins = "strong" if oktas <= 3 else "moderate"
    elif solar_elev > 15:
        ins = "moderate" if oktas <= 4 else "slight"
    else:  # 0 < solar_elev <= 15
        ins = "slight"

    # Heavy cloud (6-7 oktas) downgrades insolation one step
    if oktas >= 6:
        ins = {"strong": "moderate", "moderate": "slight", "slight": "slight"}[ins]

    # Pasquill (1961) daytime table
    table = {
        "strong": [(2, "A"), (3, "A"), (5, "B"), (6, "C"), (999, "C")],
        "moderate": [(2, "A"), (3, "B"), (5, "B"), (6, "C"), (999, "D")],
        "slight": [(2, "B"), (3, "C"), (5, "C"), (6, "D"), (999, "D")],
    }
    for threshold, cls in table[ins]:
        if wind_ms < threshold:
            return cls
    return "D"


# PG -> Obukhov length [m] (van Ulden & Holtslag 1985, as adopted in OPS)
PG_TO_L = {"A": -10.0, "B": -30.0, "C": -100.0, "D": 99999.0, "E": 200.0, "F": 50.0}

# PG -> mixing height [m] (Nieuwstadt 1981)
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

    For each hour produces a dict with keys temp_c, dew_c, rh, qnh_hpa,
    wind_dir_deg, wind_speed_ms, oktas.  Missing observations are
    forward-filled from the most recent populated hour.

    :raises RuntimeError: if the first hour has no data to forward-fill from.
    """
    # Drop microsecond-resolution tz to allow naive comparisons
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
            # Average oktas across observations in the hour, then round to
            # nearest integer.  Oktas is ordinal so this is an approximation;
            # for the typical 1-2 obs per hour it's the same as the median.
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
            }
            last_good = record
            yield record
        elif last_good is not None:
            carried = dict(last_good)
            carried["datetime"] = h
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


# Header names and order the plugin's AmbientCondition CSV reader requires.
# Source of truth: open_alaqs/core/interfaces/AmbientCondition.py::initAmbientCondition.
# Do NOT change these without updating that file in lockstep.
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

# Sentinel value used by the plugin's training data to mean "effectively
# neutral atmosphere" when no real Obukhov length is available. Picked over
# blank because the plugin's CSV-to-dict conversion treats blanks as None
# and downstream code coerces None to 0, which is wrong (zero L means
# strongly stratified, not neutral).
_OBUKHOV_NEUTRAL_M = 99999.0
_DEFAULT_MIXING_HEIGHT_M = 914.4  # CAEP14 LTO ceiling = 3000 ft × 0.3048


def _per_row_l_and_mh(
    row: dict,
    lat: Optional[float],
    lon: Optional[float],
    mh_cap_m: Optional[float],
) -> "tuple[float, float, Optional[str]]":
    """Return (Obukhov L, mixing height, PG class or None) for a single row.

    Behaviour:
      * If lat/lon are None or wind speed is missing, fall back to neutral
        L and to mh_cap_m (or the default 914.4 m) for MH.
      * Otherwise classify the hour with the corrected Pasquill-Gifford
        scheme and look up L and MH from the standard tables.  When mh_cap_m
        is set, the PG-derived MH is capped at that value.
    """
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
    """Write an Open-ALAQS meteo.csv. Returns the number of rows written.

    Header names and units match exactly what AmbientCondition.py reads:
      Temperature in K (not °C), pressure in Pa (not hPa), RH as fraction
      0-1 (not %), and a separate specific-humidity column in kg/kg.

    When `lat` and `lon` are supplied, ObukhovLength and MixingHeight are
    derived per row from the corrected Pasquill-Gifford classification.
    Otherwise both are constant: L = 99999 m (neutral), MH = the value of
    `mixing_height_cap_m` if given, else 914.4 m (CAEP14 LTO ceiling).
    """
    n = 0
    with open(out_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(_COLUMNS)
        for r in rows:
            # Convert °C -> K
            temp_k = "" if r["temp_c"] is None else f"{r['temp_c'] + 273.15:.2f}"

            # Convert hPa -> Pa
            p_pa_str = "" if r["qnh_hpa"] is None else f"{r['qnh_hpa'] * 100.0:.0f}"

            # Specific humidity (kg/kg) requires T, Td, and total pressure
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

            # RH as fraction 0-1 (NOT percent)
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
                    "" if r["wind_dir_deg"] is None else f"{r['wind_dir_deg']:.0f}",
                    f"{L:.0f}",
                    f"{MH:.1f}",
                ]
            )
            n += 1
    return n


# --------------------------------------------------------------------------- #
# Driver                                                                      #
# --------------------------------------------------------------------------- #


def read_metar_stream(fh, report_day: dt.date) -> Iterator[MetarObs]:
    """Yield parsed MetarObs for each non-empty line in fh."""
    for line in fh:
        line = line.strip()
        if not line:
            continue
        obs = parse_metar(line, report_day)
        if obs is not None:
            yield obs


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(
        description="Convert a METAR stream into an Open-ALAQS meteo.csv.",
    )
    p.add_argument(
        "--station",
        required=False,
        default="",
        help="Expected ICAO station code (informational; METARs are "
        "still parsed regardless of their station field)",
    )
    p.add_argument(
        "--lat",
        type=float,
        default=None,
        help="Airport latitude in decimal degrees (positive N). "
        "Required together with --lon to enable Pasquill-Gifford "
        "stability classification; without them the script "
        "emits a constant neutral atmosphere.",
    )
    p.add_argument(
        "--lon",
        type=float,
        default=None,
        help="Airport longitude in decimal degrees (positive E). " "See --lat.",
    )
    p.add_argument(
        "--start",
        required=True,
        help="Study start, ISO-8601 UTC, e.g. 2025-12-01T06:00",
    )
    p.add_argument("--end", required=True, help="Study end (inclusive), ISO-8601 UTC")
    p.add_argument(
        "--scenario", default="default", help="Scenario name written to every row"
    )
    p.add_argument(
        "--input", default="-", help="Path to METAR file, or '-' for stdin (default)"
    )
    p.add_argument(
        "--output", default="meteo.csv", help="Output CSV path (default meteo.csv)"
    )
    p.add_argument(
        "--mixing-height",
        type=float,
        default=None,
        help="Mixing height in metres.  When --lat/--lon are given, "
        "this is treated as an upper cap on the PG-derived "
        "value (useful for keeping the CAEP14 3000 ft / 914.4 m "
        "LTO ceiling).  Without --lat/--lon, it is the "
        "constant value written for every row; if omitted "
        "in that case the default is 914.4 m.",
    )
    args = p.parse_args(argv)

    if (args.lat is None) != (args.lon is None):
        p.error("--lat and --lon must be supplied together")

    start = dt.datetime.fromisoformat(args.start)
    end = dt.datetime.fromisoformat(args.end)
    if end < start:
        p.error("--end must be >= --start")

    fh = sys.stdin if args.input == "-" else open(args.input, "r")
    try:
        hourly = hourly_average(
            read_metar_stream(fh, report_day=start.date()),
            start=start,
            end=end,
        )
        n = write_alaqs_meteo_csv(
            hourly,
            args.scenario,
            args.output,
            lat=args.lat,
            lon=args.lon,
            mixing_height_cap_m=args.mixing_height,
        )
    finally:
        if fh is not sys.stdin:
            fh.close()

    mode = "PG-classified" if args.lat is not None else "fixed-neutral"
    print(f"Wrote {n} hourly rows to {args.output} ({mode})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
