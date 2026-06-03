# METAR → Open-ALAQS meteo.csv

Standalone utility that converts a stream of METAR weather observations into
the `meteo.csv` file Open-ALAQS reads during *Create Output*.

Source file: `scripts/metar_to_alaqs_meteo.py`.
No external Python dependencies (uses stdlib only).

## What the plugin expects in meteo.csv

The plugin's `core/interfaces/AmbientCondition.py::initAmbientCondition`
reads the CSV with these exact header names and units. The header names
include unit suffixes (`(K)`, `(Pa)`, `(0-1)`, etc.); drop the suffix and
the plugin logs *"Headers of meteo csv file do not match"* and the file
is rejected.

| column | unit | notes |
| --- | --- | --- |
| `Scenario` | text | free-form label, same value in every row |
| `DateTime(YYYY-mm-dd hh:mm:ss)` | UTC | `YYYY-MM-DD HH:MM:SS`, hourly |
| `Temperature(K)` | Kelvin | ambient air temperature (NOT °C) |
| `Humidity(kg_water/kg_dry_air)` | kg/kg | specific humidity / mixing ratio |
| `RelativeHumidity(0-1)` | fraction | 0..1 (NOT percent) |
| `SeaLevelPressure(Pa)` | Pascals | QNH × 100 (NOT hPa) |
| `WindSpeed(m/s)` | m/s | 10 m wind |
| `WindDirection(degrees)` | ° true | 0-360, written as `999` when missing or VRB |
| `ObukhovLength(m)` | m | per-hour from PG class, or 99999 (neutral) |
| `MixingHeight(m)` | m | per-hour from PG class, or fixed default 914.4 |

Sample row (PG-classified, cloudy night → class D, neutral L, mixing height 400 m):

```
Scenario,DateTime(YYYY-mm-dd hh:mm:ss),Temperature(K),Humidity(kg_water/kg_dry_air),RelativeHumidity(0-1),SeaLevelPressure(Pa),WindSpeed(m/s),WindDirection(degrees),ObukhovLength(m),MixingHeight(m)
default,2025-12-01 06:00:00,280.15,0.00538,0.871,101600,5.14,240,99999,400.0
```

## What this script does

1. Reads METAR observations from stdin or a file in one of three auto-detected
   formats (see *Supported input formats* below).
2. Parses each observation: timestamp, wind, temperature, dewpoint, QNH,
   sky condition (cloud cover in oktas).
3. Field-by-field plausibility check: temperature within [-90, +60] °C, QNH
   within [870, 1085] hPa, wind speed within [0, 250] kt, wind direction
   within [0, 360) °. Out-of-range fields are nulled (the row is kept).
4. Filters records to the `[--start, --end]` window. Deduplicates exact
   `(timestamp, METAR text)` pairs. On `(timestamp, different text)`
   collisions (e.g. METAR + amendment at the same minute) keeps the last
   record in input order.
5. Computes:
   * Temperature in Kelvin (T_C + 273.15)
   * Specific humidity from T, Td, P via Magnus-Tetens saturation vapour
     pressure: `e = RH * 611.2 * exp(17.625 * T_C / (243.04 + T_C))`,
     then `w = 0.622 * e / (p - e)` (WMO/AMS convention)
   * Relative humidity as a fraction 0-1 from T and Td (Magnus)
   * Pressure in Pascals (QNH × 100)
   * Wind speed in m/s (knots × 0.514444)
6. Buckets observations into hourly averages across the study window.
7. Forward-fills any hour with no observation from the most recent good hour.
8. When `--lat` and `--lon` are provided, classifies each hour into a
   Pasquill-Gifford stability class A-F using wind, oktas and solar
   elevation, then emits the corresponding `ObukhovLength` and
   `MixingHeight`. Without `--lat/--lon` the script emits a constant
   neutral atmosphere.
9. Writes the CSV with the schema above.
10. Prints a coverage report to stderr: source used, records retained,
    observed vs. forward-filled hours, per-field presence. Warns if
    coverage falls below `--coverage-floor` (default 70%).

## Supported input formats

The script auto-detects the format by inspecting the first non-blank line.
You can also force a specific adapter with `--source`.

### IEM ASOS CSV (`--source iem-csv`)

Sniff signal: first line starts with `station,valid,`.

The format returned by `https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py`.
Timestamp comes from the `valid` column (`YYYY-MM-DD HH:MM`), independent of
the METAR's own DDHHMM Z group. Multi-month windows are handled natively.

```
station,valid,metar
EHRD,2025-01-01 00:25,EHRD 010025Z 20022G32KT 8000 FEW015CB SCT024 BKN030 08/05 Q0995
EHRD,2025-01-01 00:55,EHRD 010055Z 20019KT 9999 FEW015CB SCT030 BKN041 07/05 Q0995
```

> **Warning**: the IEM endpoint treats `day2`/`month2`/`year2` as an
> EXCLUSIVE upper bound. To fetch through 31 December 2025 inclusive, set
> the upper bound to 2026/1/1. Setting it to 2025/12/31 silently truncates
> at 2025-12-30 23:59 UTC.

### Ogimet text (`--source ogimet`)

Sniff signal: first line starts with 12 digits followed by `METAR` or `SPECI`.

The format returned by `https://www.ogimet.com/cgi-bin/getmetar`. Each line
begins with the issue time in `YYYYMMDDHHMM` format. Multi-month windows
are handled natively. Trailing `=` is stripped.

```
202501010025 METAR EHRD 010025Z 20022G32KT 8000 FEW015CB SCT024 BKN030 08/05 Q0995=
202501010055 METAR EHRD 010055Z 20019KT 9999 FEW015CB SCT030 BKN041 07/05 Q0995=
```

Be polite when fetching: Ogimet documents 5 s minimum between requests.

### Raw METAR (`--source raw`)

Sniff signal: first line is a METAR string with no leading timestamp
(starts with the literal `METAR ` / `SPECI ` header or with a 4-letter
ICAO code followed by `DDHHMMZ`).

One METAR per line. No leading external timestamp, so the script
constructs the year/month from `--anchor-year-month` (or `--start` if the
anchor is omitted) and reads the day-of-month / time from each METAR's
DDHHMM Z group. The script walks the stream and advances the anchor month
whenever the day-of-month decreases sharply, so multi-month inputs work as
long as the file is chronologically ordered.

```
METAR EHRD 010025Z 20022G32KT 8000 FEW015CB SCT024 BKN030 08/05 Q0995
EHRD 010055Z 20019KT 9999 FEW015CB SCT030 BKN041 07/05 Q0995
SPECI EHRD 010125Z 21021KT 9999 -DZRA FEW015CB SCT024 BKN029 08/06 Q0995
```

> **Note**: the raw-METAR adapter relies on chronological ordering and the
> month-rollover heuristic. For best results with multi-month windows
> across out-of-order files, prefer one of the timestamped formats above.

## Source-quality checks

Every run emits a coverage report on stderr. Example:

```
--- Coverage report ---
  source:                 auto (sniffed)
  input records:          17513
  dropped (outside window): 1
  exact duplicates:       0
  collisions kept latest: 0
  parse failures:         0
  parsed observations:    17513
  hourly rows total:      8760
  hourly observed:        8760 (100.0%)
  hourly forward-filled:  0 (0.0%)
  temperature present:    8760 (100.0%)
  wind present:           8758 (100.0%)
  pressure present:       8760 (100.0%)
```

If any of three indicators (observed-hours, temperature presence, wind
presence) drops below `--coverage-floor` (default 70%), a `[coverage]
WARNING:` line is appended and the script exits with status 0 but logs
which indicator failed. Use this to spot sparse sources before you feed
the meteo.csv into Open-ALAQS.

## Stability classification (Pasquill-Gifford)

When `--lat` and `--lon` are supplied:

* **Solar elevation** is computed analytically from the airport coordinates
  using declination and the equation of time.
* **Cloud cover** in oktas is the maximum coverage among the METAR sky
  groups (FEW=2, SCT=4, BKN=6, OVC=8, VV=8). Absence of cloud groups is
  treated as 0 oktas (clear).
* **Daytime** (solar elevation > 0°) uses the Pasquill (1961) insolation
  table: strong (>60°), strong/moderate (35-60°), moderate/slight (15-35°),
  or slight (0-15°, low sun). Heavy cloud (6-7 oktas) downgrades insolation
  one step; total overcast (8 oktas) forces class D.
* **Night-time** (solar elevation ≤ 0°) uses the cloud-dependent table:
  ≥4 oktas → D or E depending on wind; <4 oktas → F (wind <3 m/s), E (3-5),
  or D (≥5).
* PG class → Obukhov length (van Ulden & Holtslag 1985, as in OPS):
  A=−10, B=−30, C=−100, D=99999, E=+200, F=+50 m.
* PG class → mixing height (Nieuwstadt 1981):
  A=1500, B=1000, C=600, D=400, E=200, F=100 m.
* When `--mixing-height` is also passed on the command line, the
  PG-derived mixing height is **capped** at that value (useful for LTO
  studies that want to retain the CAEP14 3000 ft / 914.4 m ceiling).

If `--lat` and `--lon` are omitted, `ObukhovLength` is fixed at 99999
(effectively neutral) and `MixingHeight` is fixed at the value of
`--mixing-height` (default 914.4 m). This matches the legacy behaviour
of the script and the plugin's own training data.

## What this script does NOT do

It does not fetch METAR data. The caller is responsible for obtaining the
observations. Recommended sources:

- **Iowa Environmental Mesonet ASOS archive** — year-long pulls, includes
  raw METAR text in the `metar` column, anonymous, rate-limited.
  Watch the exclusive end-date convention noted above.
- **NOAA Aviation Weather Center** text data service
  https://aviationweather.gov/adds/dataserver — anonymous, rate-limited.
- **ogimet.com** METAR archive — good for historical dates, rate-limited
  (≥5 s between requests).
- **metar-taf.com API** — requires an API key, near-real-time.
- **pymetar** / **python-metar** pip packages — thin wrappers over the
  above.

Keeping fetch and parse decoupled lets sites with restrictive network
policies use the parse half offline, and lets users plug in whichever
network stack they already trust.

## Usage

```bash
# Auto-detect format. Works for IEM CSV, Ogimet text, or raw METAR.
python3 scripts/metar_to_alaqs_meteo.py \
    --station EHRD --lat 51.95 --lon 4.44 \
    --start 2025-01-01T00:00 \
    --end   2025-12-31T23:00 \
    --scenario "EHRD_2025" \
    --input  ehrd_2025_iem.csv \
    --output EHRD_2025_meteo.csv

# Force a specific adapter
python3 scripts/metar_to_alaqs_meteo.py \
    --source ogimet \
    --station EHRD --lat 51.95 --lon 4.44 \
    --start 2025-01-01T00:00 --end 2025-12-31T23:00 \
    --input  ehrd_ogimet.txt --output EHRD_2025_meteo.csv

# Raw METARs, no embedded timestamp. Anchor falls back to --start.
python3 scripts/metar_to_alaqs_meteo.py \
    --source raw \
    --anchor-year-month 2025-06 \
    --station EHRD --lat 51.95 --lon 4.44 \
    --start 2025-06-01T00:00 --end 2025-06-30T23:00 \
    --input ehrd_jun_raw.txt --output EHRD_jun_meteo.csv

# Mixing height capped at the CAEP14 LTO ceiling
python3 scripts/metar_to_alaqs_meteo.py \
    --station EHRD --lat 51.95 --lon 4.44 \
    --mixing-height 914.4 \
    --start 2025-12-01T06:00 --end 2025-12-03T09:00 \
    --input metar_rotterdam_dec_1_3.txt --output AIRPORT_A_meteo.csv

# Legacy fixed-neutral mode (no PG classification)
python3 scripts/metar_to_alaqs_meteo.py \
    --station EHRD \
    --start 2025-12-01T06:00 --end 2025-12-03T09:00 \
    --input metar_rotterdam_dec_1_3.txt --output AIRPORT_A_meteo.csv

# Piped from curl
curl "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=EHRD&data=metar&year1=2025&month1=1&day1=1&year2=2026&month2=1&day2=1&tz=UTC&format=onlycomma" \
  | python3 scripts/metar_to_alaqs_meteo.py \
        --station EHRD --lat 51.95 --lon 4.44 \
        --start 2025-01-01T00:00 --end 2025-12-31T23:00 \
        --output EHRD_2025_meteo.csv

# CSV plus stability/windrose plots in one invocation
python3 scripts/metar_to_alaqs_meteo.py \
    --station EHRD --lat 51.95 --lon 4.44 \
    --start 2025-01-01T00:00 --end 2025-12-31T23:00 \
    --scenario "EHRD_2025" \
    --input  ehrd_2025_iem.csv \
    --output EHRD_2025_meteo.csv \
    --plots-dir plots/
# writes plots/ehrd_2025_stability.html and plots/ehrd_2025_windrose.html
```

Options:

- `--lat <deg>` / `--lon <deg>` airport coordinates. Both required together
  to enable PG-based stability classification.
- `--mixing-height <m>` mixing height. Without `--lat/--lon` it is the
  constant value used for every row (default 914.4 m). With `--lat/--lon`
  it caps the PG-derived value.
- `--source {auto,iem-csv,ogimet,raw}` input format. Default `auto`.
- `--anchor-year-month YYYY-MM` anchor year/month for `--source raw`.
  Defaults to the year/month of `--start`.
- `--coverage-floor <fraction>` warn if observed-hours, temperature or
  wind presence drops below this fraction (default 0.7).
- `--plots-dir <path>` if set, write the stability and windrose HTML plots
  into this directory after the CSV.  Files are named
  `{station}_{year}_stability.html` and `{station}_{year}_windrose.html`
  (year is the year of `--start`).  Stability requires `--lat/--lon` for
  PG classification; without them only the windrose is produced and a
  notice is logged to stderr.
- `--input -` (default) read from stdin.
- omit `--output` and the file will be written to `meteo.csv` in the CWD.

## Limitations

* **Raw-METAR adapter assumes chronological ordering** and uses a
  month-rollover heuristic (day-of-month decreasing by more than 5 days
  triggers a month advance). For out-of-order files, prefer the IEM CSV
  or Ogimet adapters which carry an authoritative timestamp.
* **Forward-fill is unbounded** in the script's current implementation.
  An hour with no observation inherits the previous hour's values
  indefinitely. The coverage report surfaces this, but the script does
  not enforce a hard cap on the gap length.
* **Wind direction missing/VRB is written as `999`** by convention. The
  plugin's `AmbientCondition.py` may or may not treat this as a
  sentinel; post-process the column if your downstream consumer expects
  blank instead.
* **Specific humidity is approximated** from RH and saturation vapour
  pressure, not directly measured. This is the standard convention but
  introduces a small bias (~0.1% RH equivalent) versus a direct
  observation.

## Swapping in `python-metar`

The in-house parser is minimal. If you prefer the `python-metar` package,
replace the body of `parse_metar()` with:

```python
from metar.Metar import Metar
m = Metar(line)

# Sky cover -> oktas (max over reported layers)
SKY_TO_OKTAS = {"CLR":0,"SKC":0,"NSC":0,"NCD":0,"CAVOK":0,
                "FEW":2,"SCT":4,"BKN":6,"OVC":8,"VV":8}
oktas = 0
for layer in m.sky:           # list of (cover, height, type) tuples
    cover = layer[0]
    oktas = max(oktas, SKY_TO_OKTAS.get(cover, 0))

obs = MetarObs(
    time_utc=m.time.replace(tzinfo=dt.timezone.utc),
    station=m.station_id,
    wind_dir_deg=None if m.wind_dir is None else m.wind_dir.value(),
    wind_speed_kt=None if m.wind_speed is None else m.wind_speed.value("KT"),
    temp_c=None if m.temp is None else m.temp.value("C"),
    dewpoint_c=None if m.dewpt is None else m.dewpt.value("C"),
    qnh_hpa=None if m.press is None else m.press.value("HPA"),
    oktas=oktas,
)
return _validate(obs)
```

The rest of the pipeline stays the same; the script will still emit
Kelvin, Pa, kg/kg, fraction-RH, and PG-classified L/MH because the unit
conversions and stability logic live in `write_alaqs_meteo_csv`, not in
`parse_metar`.
