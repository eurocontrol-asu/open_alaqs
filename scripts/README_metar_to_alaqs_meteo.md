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
| `WindDirection(degrees)` | ° true | 0–360 |
| `ObukhovLength(m)` | m | per-hour from PG class, or 99999 (neutral) |
| `MixingHeight(m)` | m | per-hour from PG class, or fixed default 914.4 |

Sample row (PG-classified, cloudy night → class D, neutral L, mixing height 400 m):

```
Scenario,DateTime(YYYY-mm-dd hh:mm:ss),Temperature(K),Humidity(kg_water/kg_dry_air),RelativeHumidity(0-1),SeaLevelPressure(Pa),WindSpeed(m/s),WindDirection(degrees),ObukhovLength(m),MixingHeight(m)
default,2025-12-01 06:00:00,280.15,0.00538,0.871,101600,5.14,240,99999,400.0
```

## What this script does

1. Reads METAR observations one per line from stdin or a file.
2. Parses each observation: timestamp, wind, temperature, dewpoint, QNH,
   sky condition (cloud cover in oktas).
3. Computes:
   * Temperature in Kelvin (T_C + 273.15)
   * Specific humidity from T, Td, P via Magnus-Tetens saturation vapour
     pressure: `e = RH * 611.2 * exp(17.625 * T_C / (243.04 + T_C))`,
     then `w = 0.622 * e / (p - e)` (WMO/AMS convention)
   * Relative humidity as a fraction 0–1 from T and Td (Magnus)
   * Pressure in Pascals (QNH × 100)
   * Wind speed in m/s (knots × 0.514444)
4. Buckets observations into hourly averages across the study window.
5. Forward-fills any hour with no observation from the most recent good hour.
6. When `--lat` and `--lon` are provided, classifies each hour into a
   Pasquill-Gifford stability class A-F using wind, oktas and solar
   elevation, then emits the corresponding `ObukhovLength` and
   `MixingHeight`. Without `--lat/--lon` the script emits a constant
   neutral atmosphere.
7. Writes the CSV with the schema above.

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
  ≥4 oktas → D or E depending on wind; <4 oktas → E or F.
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

- **NOAA Aviation Weather Center** ADDS text data service
  https://aviationweather.gov/adds/dataserver — anonymous, rate-limited
- **Iowa Environmental Mesonet ASOS archive** — year-long pulls, includes
  raw METAR text in the `metar` column, anonymous, rate-limited
- **ogimet.com** METAR archive — good for historical dates
- **metar-taf.com API** — requires an API key, near-real-time
- **pymetar** / **python-metar** pip packages — thin wrappers over the above

Keeping fetch and parse decoupled lets sites with restrictive network
policies use the parse half offline, and lets users plug in whichever
network stack they already trust.

## Usage

```bash
# With a file of METAR lines, PG-classified (lat/lon supplied)
python3 scripts/metar_to_alaqs_meteo.py \
    --station EHRD --lat 51.95 --lon 4.44 \
    --start 2025-12-01T06:00 \
    --end   2025-12-03T09:00 \
    --scenario "AIRPORT_A training" \
    --input  metar_rotterdam_dec_1_3.txt \
    --output AIRPORT_A_meteo.csv

# Same, with mixing height capped at the CAEP14 LTO ceiling
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
curl "https://aviationweather.example/metar?station=EHRD&hours=72" \
  | python3 scripts/metar_to_alaqs_meteo.py \
        --station EHRD --lat 51.95 --lon 4.44 \
        --start 2025-12-01T06:00 --end 2025-12-03T09:00 \
        --output AIRPORT_A_meteo.csv
```

Options:

- `--lat <deg>` / `--lon <deg>` airport coordinates. Both required together
  to enable PG-based stability classification.
- `--mixing-height <m>` mixing height. Without `--lat/--lon` it is the
  constant value used for every row (default 914.4 m). With `--lat/--lon`
  it caps the PG-derived value.
- `--input -` (default) read from stdin
- omit `--output` and the file will be written to `meteo.csv` in the CWD

## Expected input format

One METAR per line, standard ICAO encoding. Example:

```
EHRD 010700Z 24010KT 9999 SCT020 07/05 Q1016 NOSIG
EHRD 010800Z 23012KT 9999 BKN030 08/05 Q1016 NOSIG
EHRD 010900Z 22014KT 9999 OVC050 09/05 Q1015 NOSIG
EHRD 012100Z 24004KT 9999 CAVOK 06/04 Q1014 NOSIG
```

Header lines `METAR` / `SPECI` are ignored. VRB wind direction is recorded
as blank. Both `Qnnnn` (hPa) and `Annnn` (inHg × 100) pressure groups are
supported. Sky-condition tokens `SKC`, `CLR`, `NSC`, `NCD`, `CAVOK`,
`FEWnnn`, `SCTnnn`, `BKNnnn`, `OVCnnn`, `VVnnn` are all recognised.

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
```

The rest of the pipeline stays the same; the script will still emit
Kelvin, Pa, kg/kg, fraction-RH, and PG-classified L/MH because the unit
conversions and stability logic live in `write_alaqs_meteo_csv`, not in
`parse_metar`.
