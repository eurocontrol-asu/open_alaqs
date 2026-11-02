# Input file formats

This page describes the CSV files you give OpenALAQS: aircraft movements, meteorology, ADS-B tracks, engine test events and receptor points. It is for users who prepare these files for a study. Each section gives the delimiter, the columns and an example taken from the training files in `example/training/`.

- [Movements](#movements)
- [Meteorology](#meteorology)
- [ADS-B tracks](#ads-b-tracks)
- [Engine test events](#engine-test-events)
- [Receptor points](#receptor-points)

## Movements

One row per aircraft movement (arrival or departure, fixed-wing or helicopter). You select the file in **Movements Table** of the **Calculate Emissions Inventory** window (see [Calculate Emissions Inventory window](USER_GUIDE.md#calculate-emissions-inventory-window)).

**Delimiter:** semicolon (`;`) only. A comma-separated file is not read.

**Header:** the first row names the columns. Write the names exactly as in the table below. Every column must be in the header, even when its values are empty; only `gate_emissions_code` may be left out. The plugin then maps the columns by name. A trailing `domestic` column (old files) is ignored.

If any name is missing, misspelt or unknown, the plugin ignores the whole header and reads every column by position. A file without a header line (its first row starts with a date) is also read by position, and its first row is kept as a movement. A row of 20 fields is read in the order of the table below. Any other row is read in the old order of 19 columns: the table below **without** `gate_emissions_code`, which then takes its default. If the header ends with `domestic` (old files), every row is read in the old order of 19 columns, followed by `gate_emissions_code` when the row has it; the `domestic` value is ignored. The log shows a warning that names the unknown and missing header names. Keep `runway_time` as the first column: the file check reads the date range from it.

**Dates:** `YYYY-MM-DD HH:MM:SS`. When you select the file, every row is checked. A single row whose first field is not such a date, or that has fewer than 10 fields, refuses the whole file: the status line reads "Problem with movement file. See log file", and the log names the row.

| Column | Unit | Required | Meaning | Default when empty |
|---|---|---|---|---|
| `runway_time` | date and time | yes | Time on the runway: for an arrival the touchdown (A-CDM ALDT), for a departure the start of the take-off roll. An A-CDM take-off time (ATOT) is wheels-off: take the take-off roll off it first. | |
| `block_time` | date and time | yes | Time at the gate: in-block for an arrival, off-block for a departure. The taxi time is the difference between the two times; for an arrival the landing roll of its profile is taken out of it. | |
| `aircraft` | | yes | ICAO aircraft type designator. For a helicopter, the ICAO code or a variant label of the helicopter catalog (see [Helicopters](USER_GUIDE.md#helicopters-foca-2015)). | |
| `gate` | | yes | Name of the gate (as in the Gates layer). | |
| `departure_arrival` | | yes | `A` = arrival, `D` = departure. | |
| `runway` | | yes | Runway end used (as in the Runways layer, for example `24`). | |
| `engine_name` | | no | Engine identifier from the engine table. | the aircraft's default engine |
| `profile_id` | | no | Flight profile. An ANP profile, or the `flight_id` of an imported ADS-B flight (see [ADS-B tracks](#ads-b-tracks)). | the aircraft's default profile |
| `track_id` | | no | Name of a track of the Tracks layer (`shapes_tracks`) with the movement's runway and direction: the plugin lays the flight profile along it, which changes the trajectory and the emissions. The standalone pipeline does not follow tracks. | |
| `taxi_route` | | yes | Name of the taxi route, as built in the Taxiway Routes Editor (gate/runway/A or D/instance, for example `G4/24/A/1`). | |
| `tow_ratio` | fraction (at most 1.0) | no | Take-off weight divided by the maximum take-off weight. Used only by the bymode NOx correction, on take-off and climb-out. 0, a negative value or NaN is replaced by 1, with a warning in the log. | 1.0 |
| `apu_code` | | no | APU use: `-1` or `0` no APU; `1` APU at the stand only; `2` APU during the whole taxi. | 0 |
| `gate_emissions_code` | | no | `0` leaves out the gate emissions (GSE, GPU and main engine start) of this movement; `1` includes them. | 1 |
| `taxi_engine_count` | engines | no | Engines running during taxi (single-engine taxi). Never more than the aircraft's engines. | 2 |
| `set_time_of_main_engine_start_after_block_off_in_s` | s | no | Departure: time after off-block during which the aircraft taxis on `taxi_engine_count` engines. Used before the next column when both are set. | |
| `set_time_of_main_engine_start_before_takeoff_in_s` | s | no | Departure: time before take-off at which the other engines are started. | |
| `set_time_of_main_engine_off_after_runway_exit_in_s` | s | no | Arrival: time after the runway exit during which all engines run before the others are shut down. | |
| `engine_thrust_level_for_taxiing` | fraction | no | Taxi thrust (0.07 = 7 %, the ICAO value). Used by BFFM2 only; bymode uses the taxi (TX) mode values. A value below 0 or above 1.05 (for example 7 for 7 %) is rejected with an error in the log, and the taxi then uses the TX mode values. | 0.07 |
| `taxi_fuel_ratio` | ratio | no | Single-engine taxi fuel flow divided by the idle fuel flow. Multiplies the emissions of the taxi segments in single-engine taxi (and of the single-engine part of a departure's queue) only; taxi on all engines is not affected, so it has no effect without a main engine start or off time. Plugin and standalone alike. | 1.0 |
| `number_of_stop_and_gos` | count | no | Stop-and-go events during taxi. Each adds a short burst at the taxi emission index to the queuing segment. | 0 |

How the taxi columns are used is described in [Aircraft emissions: taxiing](../methods/AIRCRAFT_EMISSIONS.md#taxiing) and [APU, GSE and engine start](../methods/AIRCRAFT_EMISSIONS.md#apu-gse-and-engine-start).

Example (header and first two rows of `example/training/training_movements.csv`):

```
runway_time;block_time;aircraft;gate;departure_arrival;runway;engine_name;profile_id;track_id;taxi_route;tow_ratio;apu_code;gate_emissions_code;taxi_engine_count;set_time_of_main_engine_start_after_block_off_in_s;set_time_of_main_engine_start_before_takeoff_in_s;set_time_of_main_engine_off_after_runway_exit_in_s;engine_thrust_level_for_taxiing;taxi_fuel_ratio;number_of_stop_and_gos
2025-12-01 06:05:00;2025-12-01 06:10:00;A20N;G4;A;24;01P20CM128;JET-SMALL-A-1;;G4/24/A/1;;0;0;2;;;;0.07;1;0
2025-12-01 06:15:00;2025-12-01 06:10:00;A20N;G4;D;24;01P20CM128;JET-SMALL-D-1;;G4/24/D/1;;0;0;2;;;;0.07;1;0
```

## Meteorology

Hourly ambient conditions for the emission calculation (BFFM2, NOx correction, mixing height) and for dispersion. You select the file in **Meteorological Table** of the **Calculate Emissions Inventory** window. The file is optional: without it, ISA conditions are used.

**Delimiter:** comma, semicolon or tab, detected from the file.

**Header:** exactly the ten headers below, written as shown, units in brackets included. A missing, extra or differently written header is rejected with "Headers of meteo csv file do not match..". "yes (column)" means the column must be there; an empty value takes the default.

| Column | Unit | Required | Meaning | Default when empty |
|---|---|---|---|---|
| `Scenario` | | yes | Label of the meteo set. The calculation uses every row, whatever the label. | |
| `DateTime(YYYY-mm-dd hh:mm:ss)` | date and time | yes | Start of the hour. | |
| `Temperature(K)` | K | yes (column) | Air temperature at 2 m (kelvin, not °C). | 288.15 |
| `Humidity(kg_water/kg_dry_air)` | kg/kg | yes (column) | Humidity ratio. Not used by the emission calculation: the humidity is derived from the relative humidity. | 0.00634 |
| `RelativeHumidity(0-1)` | fraction | yes (column) | Relative humidity, 0 to 1 (not percent). | 0.6 |
| `SeaLevelPressure(Pa)` | Pa | yes (column) | Sea-level pressure (QNH × 100, not hPa). | 101325 |
| `WindSpeed(m/s)` | m/s | yes (column) | Wind speed at the anemometer. | 0 |
| `WindDirection(degrees)` | degrees | yes (column) | Direction the wind comes from (0 = north). | 0 |
| `ObukhovLength(m)` | m | yes (column) | Atmospheric stability; 99999 is neutral. | 99999 |
| `MixingHeight(m)` | m | yes (column) | Mixing height. Also the LTO ceiling for aircraft in that hour. | 914.4 |

Each calculation interval uses the meteo row nearest to its start. A row whose temperature or pressure is not a positive number stops the calculation with a message naming the row's date. How the values are used aloft is described in [Ambient conditions aloft](../methods/ATMOSPHERE_ALOFT.md). To build the file from METAR reports, see [`scripts/README_metar_to_alaqs_meteo.md`](../../scripts/README_metar_to_alaqs_meteo.md).

Example (header and first two rows of `example/training/training_meteo.csv`):

```
Scenario,DateTime(YYYY-mm-dd hh:mm:ss),Temperature(K),Humidity(kg_water/kg_dry_air),RelativeHumidity(0-1),SeaLevelPressure(Pa),WindSpeed(m/s),WindDirection(degrees),ObukhovLength(m),MixingHeight(m)
default,2025-12-01 00:00:00,280.5,0.00446,0.68,97600,5.0,225,99999,914.4
default,2025-12-01 01:00:00,280.5,0.00446,0.68,97600,5.0,225,99999,914.4
```

## ADS-B tracks

Observed flight trajectories that replace the ANP profile of selected movements. You select the file in **ADS-B Table** of the **Calculate Emissions Inventory** window. The file is optional. The study must have at least one runway, otherwise the file is rejected ("To import ADS-B data, at least one runway should exist in the study!").

**Delimiter:** comma, semicolon or tab, detected from the file.

**Header:** column names as below. Other columns (callsign, registration, ...) are ignored.

Each `flight_id` becomes a flight profile of that name. A movement uses it when its `profile_id` in the [movements file](#movements) is that `flight_id`; the movement row also gives the runway and taxi route used to place the track, and the engine used to check the fuel flow. Whether a flight is an arrival or a departure is taken from its altitude: descending is an arrival.

| Column | Unit | Required | Meaning |
|---|---|---|---|
| `flight_id` | | yes | Groups the rows of one flight. Rows in time order. |
| `latitude` | degrees (WGS84) | yes | |
| `longitude` | degrees (WGS84) | yes | |
| `altitude` | ft above mean sea level | yes | The airport elevation is subtracted; points of the take-off roll and of the landing roll are set to the ground. |
| `tas` | kt | yes | True airspeed. |
| `power_setting` | fraction | one of `power_setting` or `fuel_flow` in each row | Engine power setting, 0 to 1 (values outside 0 to 1.5 are rejected). The old name `thrust` is accepted, with a warning in the log. |
| `fuel_flow` | kg/s, whole aircraft | one of `power_setting` or `fuel_flow` in each row | Fuel flow of all engines together. Values below the ICAO idle fuel flow are kept; the log names each such flight. |
| `timestamp` | `YYYY-MM-DD HH:MM:SS` | no | For your reference only. The time of the flight comes from the movement's `runway_time` and `block_time`. |

Do not include the ground taxi: taxi emissions come from the taxi routes, and taxi rows would be read as flight points at zero height. How ADS-B tracks are used in the emission calculation is described in [Aircraft emissions: ADS-B](../methods/AIRCRAFT_EMISSIONS.md#ads-b).

Example (header and first two rows of `example/training/training_ads_b_data.csv`):

```
flight_id,timestamp,latitude,longitude,altitude,tas,power_setting,fuel_flow
1764584438_PHBBA,2025-12-01 10:20:38,51.96246,4.455433,-15.0,11.0,0.9239,1.5688
1764584438_PHBBA,2025-12-01 10:20:42,51.962556,4.455224,-15.0,25.0,0.8655,1.4512
```

## Engine test events

Engine run-ups on an engine test site (an area source with **Engine Test Site** ticked). You load the file with **Load engine test events CSV...** in the area-source form (see [Engine test sites](USER_GUIDE.md#engine-test-sites)) or with the script [`scripts/import_engine_test_events.py`](../../scripts/README.md#import_engine_test_eventspy).

**Delimiter:** comma. UTF-8 text.

**Header:** column names as below, in any order. Empty cells take the default.

| Column | Unit | Required | Meaning | Default when empty |
|---|---|---|---|---|
| `source_id` | | yes (optional when loaded from a source's form) | **Source Name** of the test-site area source. From a source's form, rows for other sources are skipped and counted in the summary. | the form's source |
| `start_datetime` | ISO 8601 (`YYYY-MM-DDTHH:MM:SS`) | yes | Start of the test. | |
| `end_datetime` | ISO 8601 | yes | End of the test; must be after the start. | |
| `aircraft_type` | | yes | ICAO aircraft type designator. | |
| `test_id` | | no | Your own reference. | |
| `engine_uid` | | no | Engine identifier from the engine table. | the aircraft's default engine |
| `engine_count` | engines | no | Engines tested (positive whole number). | the aircraft's engine count |
| `t_TX_s` | s per engine | no | Running time at idle (taxi mode). | 0 |
| `t_AP_s` | s per engine | no | Running time at approach power. | 0 |
| `t_CL_s` | s per engine | no | Running time at climb-out power. | 0 |
| `t_TO_s` | s per engine | no | Running time at take-off power. | 0 |
| `instudy` | | no | `1` include the event, `0` leave it out. | 1 |

The import rejects a row with an empty required value, a date that is not ISO 8601, an end not after the start, a negative or non-whole running time, an invalid `engine_count` or `instudy`, or the same `source_id`, `start_datetime` and `aircraft_type` as an earlier row. It warns, without rejecting the row, about an unknown source, aircraft type or engine, a source that is not a test site, and running times longer than the event (60 s tolerance). How the events become emissions is described in [Engine test sites](../methods/STATIONARY_AND_ROAD.md#engine-test-sites).

Example (header and first two rows of `example/training/training_engine_test_events.csv`):

```
source_id,start_datetime,end_datetime,aircraft_type,test_id,engine_uid,engine_count,t_TX_s,t_AP_s,t_CL_s,t_TO_s,instudy
TESTPAD_A,2025-01-15T09:00:00,2025-01-15T09:15:00,C25C,LOG-2025-001,,,600,0,300,0,1
TESTPAD_A,2025-01-15T10:30:00,2025-01-15T10:50:00,PC24,LOG-2025-002,,,900,180,0,0,1
```

## Receptor points

Points where AUSTAL writes a concentration time series (for **Plot Time Series** and **Compliance Report**). AUSTAL takes at most 20 receptors; further rows are dropped with a warning in the log. Two places accept a receptor file, and they read it differently.

**In the Calculate Dispersion dialog** (**Receptors CSV**, both Generate modes, see [Calculate Dispersion dialog](DISPERSION_AUSTAL.md#calculate-dispersion-dialog)):

- Delimiter: comma.
- Header names are not case-sensitive; `lon` and `lat` are accepted for `longitude` and `latitude`.

| Column | Unit | Required | Meaning | Default when empty |
|---|---|---|---|---|
| `longitude` | degrees or metres, per `EPSG` | yes | x coordinate. | |
| `latitude` | degrees or metres, per `EPSG` | yes | y coordinate. | |
| `EPSG` | | no | Coordinate system of the two columns, the same in every row. | 4326 (WGS84) |
| `id` | | no | Receptor name. | |
| `height` | m | no | Receptor height above ground, written to AUSTAL for each receptor. | 1.5 |

**On the Configuration tab** of **Visualize Emission Calculation** (**Receptor Points**, used by the AUSTAL module of the Dispersion Models tab):

- Delimiter: comma, semicolon or tab, detected from the file.
- Header names are case-sensitive.

| Column | Unit | Required | Meaning | Default when empty |
|---|---|---|---|---|
| `longitude` | degrees or metres, per `EPSG` | yes, unless `geometry` is given | x coordinate. | |
| `latitude` | degrees or metres, per `EPSG` | yes, unless `geometry` is given | y coordinate. | |
| `geometry` | WKT | instead of `longitude` and `latitude` | Point in WKT, for example `POINT (4.44 51.96)`. | |
| `EPSG` (or `crs`) | | yes | Coordinate system, the same in every row. Without it no receptor is written (warning in the log). | |
| `altitude` | m | no | Receptor height above ground. | 1.5 |
| `id` | | no | Receptor name. | |

No receptor file ships with the training example. This example (points near the training airport) works in both places:

```
id,longitude,latitude,EPSG
R1,4.4400,51.9600,4326
R2,4.4500,51.9700,4326
```

**Receptors CSV in the dialog: which points are used.**

- With **Generate AUSTAL Input Files from OpenALAQS Emission Inventory File**: the Receptors CSV when it is given and readable. Otherwise the receptor points stored in the inventory, if it has any (points marked as not in study are skipped), each at its stored height (1.5 m when empty). The plugin has no receptor layer to draw such points: the inventory holds them only if they were added outside the plugin windows. Without points, AUSTAL runs without receptors.
- With **Generate AUSTAL Input Files from CSV**: the Receptors CSV only.
- A Receptors CSV that cannot be read (wrong delimiter, no `longitude`/`latitude` column) is skipped with only a warning in the log, and the inventory's points, or none, are used instead. If **Plot Time Series** stays disabled after a run with a Receptors CSV, check the log.

See [Dispersion with AUSTAL](DISPERSION_AUSTAL.md#results) for what the receptors enable.

## See also

- [User guide](USER_GUIDE.md): where each file is selected in the plugin.
- [Tutorial with the Rotterdam training data](TUTORIAL_ROTTERDAM.md): the training files in a full study.
- [Dispersion with AUSTAL](DISPERSION_AUSTAL.md): receptor results.
- [Without QGIS](WITHOUT_QGIS.md): the same files in the QGIS-free tools.
