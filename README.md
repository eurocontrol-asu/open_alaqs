# Open-ALAQS — QGIS plugin for airport emissions inventory

Open-ALAQS is a QGIS plugin that produces Eurocontrol ALAQS airport emissions
inventories from movement data, meteorological data, and airport layout.
This release adds dual-mode BFFM2, corrects several calculation paths, and
validates against the CAEP14 reference spreadsheet (v14) across 13
representative segment conditions.

## Installation

Clone into the QGIS plugin directory:

- Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\open_alaqs\`
- macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/open_alaqs/`
- Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/open_alaqs/`

Then enable Open-ALAQS in the QGIS Plugin Manager.

## Workflow

1. Build the airport study (runways, taxiways, gates, stationary sources) in a
   QGIS project.
2. Open *Create Output* to bake the study into an inventory database, supplying
   a movements CSV and a meteorological CSV (see below).
3. Run *Generate Emission Inventory* on the baked inventory to calculate
   emissions with the selected method.

## Emission calculation methods

Open-ALAQS ships three aircraft emission methods selectable at run time:

- **bymode** — multiplies anchor-mode fuel flow × anchor-mode EI × time × engine
  count. No ambient corrections. Use as a tautological baseline.
- **BFFM2 (trajectory)** — default BFFM2 path. For each trajectory segment
  resolves fuel flow from the segment's sub-mode power setting via the twin-
  quadratic fit, applies SAE AIR-5715 atmospheric corrections for NOx, and
  snaps CO/HC to the horizontal mean(CL, TO) value above the APP anchor in the
  standard-intersection case (CAEP14 v14 rule).
- **BFFM2 (mode_anchor)** — uses the mode anchor fuel flow (IDLE/APP/CL/TO EEDB
  values) as the BFFM2 input, still applying ambient corrections. Useful when
  trajectories lack per-segment sub-mode fidelity.

PM is via MEEM V1 at LTO (EEDB nvPM anchors unchanged at LTO altitudes). The
MEEM V2 base method (ICAO CAEP/13-WG3) is also implemented for non-LTO
altitudes. The MDG4 / Staged Combustion update is not implemented.

## Meteorological data

Open-ALAQS expects an hourly meteo CSV during output creation. A standalone
utility for producing it from a METAR stream ships in `scripts/`:

- `scripts/metar_to_alaqs_meteo.py` — parses METAR observations from stdin or a
  file, computes relative humidity from T/Td, buckets hourly, writes the
  ALAQS-schema CSV.
- `scripts/README_metar_to_alaqs_meteo.md` — usage and notes on where to fetch
  METAR data (NOAA Aviation Weather Center, ogimet.com, metar-taf.com API,
  python-metar). Fetching is deliberately left to the user; the script focuses
  on parsing and resampling.

A migration tool is also provided for upgrading legacy `.alaqs` files to the
current schema:

- `scripts/migrate_alaqs.py` — comparative schema diff against
  the current blank-study template. Adds missing tables/columns, runs
  data-preserving renames (e.g. legacy 1D axial profile → 3D Cartesian),
  reports extras without dropping them by default. Single-transaction with
  automatic rollback + backup-restore on failure.

See `scripts/README.md` for the full inventory.

## Validation state

The plugin is validated against `CAEP14_FBE_Engines_Emissions_Calculation_Sheet_v14.xlsx`.

- **Cross-platform**: QGIS on Windows and the same pipeline on Linux produce
  identical grand totals to 4 decimal places across 13 movements × 4 pollutants
  × 3 methods (156 values, 0.00 % drift).
- **BFFM2 vs CAEP14 v14**: plugin matches CAEP14 v14 to floating-point
  precision on all metrics (fuel, CO, HC, NOx, CO2) across Bymode, BFFM2
  trajectory, and BFFM2 mode_anchor methods. See
  `CAEP14_v14_validation.xlsx` (delivered alongside the plugin) for the
  per-movement comparison sheets. Validation covers 2 engines (LEAP-1A26,
  CF34-8E5), 4 modes (TX/AP/CL/TO), and 3 meteo scenarios (cold-moist,
  mild-dry, warm-humid), both trajectory and anchor sub-modes.
- **MEEM V1 at LTO**: non-volatile PM matches EEDB anchors exactly
  (0.684 / 2.989 / 1.235 / 1.627 mg/kg for 01P20CM128).
- **Grand totals (AIRPORT_A, 13 movements, engine-only scope)**:

  | method | CO (kg) | HC (kg) | NOx (kg) | fuel (kg) |
  |---|---|---|---|---|
  | bymode | 21.97 | 1.234 | 23.49 | 1742.80 |
  | BFFM2 trajectory | 22.24 | 1.248 | 14.07 | 1544.14 |
  | BFFM2 anchor | 21.73 | 1.246 | 21.21 | 1744.56 |

  Every column above agrees with the CAEP14 v14 reference to floating-point
  precision (0.000 % drift). Paired comparison with CAEP14 v14 reference is
  in `CAEP14_v14_validation.xlsx`.

## Notable corrections in this release

- **Taxi Mach state-leak isolation** — `TaxiingEmissionCalculator.calculate_emissions`
  now forces `mach_number = 0.0` for taxi operations. The shared
  `method["config"]` dict was being mutated per flight segment by
  `FlightEmissionCalculator`, leaking the previous segment's terminal Mach
  (typically 0.15-0.40) into taxi BFFM2 lookups and producing 0.5-3 %
  under-prediction on taxi fuel flow. CAEP14 v14 spec says ground operations
  are M=0.
- **Climbout installation correction** — `MovementSourceModule` CAEP14 v14
  installation correction for Climbout corrected from 1.012 to 1.013
  (agreement with the `bffm2.py` docstring, comment, and default — the 1.012
  override was a typo).
- **MES double-count fix** — single-engine taxi main-engine-start emissions
  are now added exactly once per movement instead of once per taxi segment
  inside the MES window. Affects movements with `gate_emissions_code=1` AND
  `set_time_of_main_engine_start_after_block_off_in_s` (or the before-takeoff
  variant) set AND multi-segment taxi routes.
- **Gate emissions gating** — `MovementSourceModule` now forwards the movement's
  `gate_emissions_code` to the gate emissions path, so `code=0` movements no
  longer leak POLYGON-geometry entries.
- **Stop-and-Go engine-count** — stop-and-go emissions now multiply by
  `number_of_engines`, matching the convention used for taxi and queuing time.
  Affects movements with `number_of_stop_and_gos > 0`; no effect on
  engine-only validation scope where stops are zeroed out.
- **CO/HC interpolation alignment with CAEP14 v14** — in the standard
  SL/HL-intersection case, EI now snaps to the horizontal mean value for any
  segment fuel flow above the APP anchor (SAE AIR-5715 "HC_CO Slope To Mean
  Value" rule). The previous implementation smoothed the step by
  interpolating up to the intersection; that disagreed with v14 by up to 8×
  EI at warm-humid AP-anchor conditions.
- **Log-noise suppression** — `OutputModule`, `TableViewWidgetOutputModule`,
  and `AUSTALOutputModule` no longer log ERROR for zero-valued placeholder
  emissions synthesised for empty periods. Real missing-geometry bugs still
  surface.
- **AUSTAL diagnostic fixes** — `checkTimeIntervalinResults` now logs at
  ERROR level (was DEBUG) when the series.dmna / austal.txt files disagree,
  and `checkHoursinResults` warning text and end_date assignment are now
  consistent at start + 23 h (AUSTAL convention: a day is 24 inclusive
  timestamps from 01:00..00:00).
- **Dual-mode BFFM2** — the BFFM2 path accepts a `bffm2_ff_source` config
  field (`trajectory` default, or `mode_anchor`). Exposed in the Generate
  Emission Inventory dialog via a dropdown.
- **UI simplification** — the Create Output dialog's "Advanced Options"
  group (Method dropdown with "ALAQS" as the sole choice, Towing Speed, and
  Vertical Limit) has been removed. Method was never routed to any consumer,
  Towing Speed was written to a dict key no downstream code read, and Vertical
  Limit wrote to a DB column nothing queried — the actual LTO ceiling is
  `EmissionCalculatorService.vertical_limit_m = 914.4` m (CAEP standard),
  hardcoded at the calculation boundary.
- **Below-MSL airport elevation entry** — `spinBoxAirportElevation` and
  `spinBoxAirportTemperature` now declare explicit `minimum` properties.
  Without them, Qt defaulted to 0 and silently clamped any negative value,
  so picking EHRD (Rotterdam, AIP -5 m) populated the form with 0 m.
  Below-MSL airports (EHRD, EHAM, LLEY, etc.) and cold-climate annual
  means now round-trip correctly.
- **CSV receptor altitude optional** — the receptor CSV loader now accepts a
  3-column file (id, longitude, latitude) without silently producing an
  empty GeoDataFrame. Default receptor breathing height (1.5 m) is applied
  downstream by `AUSTALOutputModule.getGridXYFromReferencePoint`.

- **Runway form simplification** — `max_queue_speed` and `peak_queue_time`
  columns dropped from `shapes_runways`. Both were dead weight: defined in
  the schema, the Runway interface getters/setters, and the form widget,
  but no downstream consumer ever read them (`getQueueSpeed` / `getPeakQueueTime`
  had zero call sites outside `Runway.py`). The remaining `capacity` and
  `touchdown` fields are still defined for future use (capacity is real
  airport metadata; touchdown_offset is needed for proper arrival-emission
  placement past the threshold).
- **ADS-B CSV schema simplification** — `track`, `vertical_rate`,
  `groundspeed`, `nodes`, `taxi` columns dropped from the documented schema.
  None of them were ever consumed by the validator or importer. The
  `taxi` column in particular was a soft warning that ground-taxi GPS
  points should not be in the trajectory CSV (the plugin handles ground
  emissions via taxiway routes); it is now documented in the validator
  docstring instead. Required columns: `flight_id, latitude, longitude,
  altitude, tas`. At least one of: `power_setting, fuel_flow`. Any
  additional columns in the user's CSV (aircraft_type, registration,
  squawk, callsign, weather, etc.) are silently ignored — real-world
  ADS-B exports rarely contain only the required columns.
- **`thrust` renamed to `power_setting`** — the column the validator and
  BFFM2 twin-quad fit treats as a 0..1 engine power-setting fraction is
  now named accordingly. Validator rejects values outside `[0, 1.5]`
  (rare values up to ~1.05 occur during high-power takeoff segments;
  anything above is almost certainly a unit error like raw Newtons).
  Legacy `thrust` column accepted as an alias with a deprecation warning;
  values from the legacy alias bypass the range check to keep old files
  loading.
- **Analysis-window source-list refresh** — picking a different inventory
  file in the Emissions Inventory Analysis dialog now correctly re-loads
  the source list. Prior bug: every Source store
  (`AreaSourcesStore`, `AircraftStore`, `AircraftTrajectoryStore`, etc.)
  uses the `Singleton` metaclass; `__call__` ignores the `db_path`
  argument on subsequent constructs and returns the cached instance bound
  to the FIRST file. The reset only fired during `EmissionCalculation.__init__`
  at calc time, leaving the source-listing dropdowns stale. Fixed in
  `result_file_path_changed` by calling `Singleton.reset_all()` and
  re-binding `ProjectDatabase().path` immediately after path validation.
- **Emissions legend deduplication** — the QGIS "nox Emissions" /
  "co Emissions" / etc. layer legends previously showed two zero entries
  (a gray "0 - 0" from a degenerate Jenks bin and a white "0" from the
  explicit transparent range). Most grid cells in an emissions raster
  are exactly zero, so Jenks classification was emitting a "0 - 0"
  bin that was never stripped before the explicit transparent zero
  range was added. `setColorGradientRenderer` now deletes any
  zero-width range from the Jenks output before adding the explicit
  zero range.

- **Emissions Inventory layer dedup** — switching the BFFM2 fuel-flow
  source dropdown from "trajectory" to "mode_anchor" and re-running the
  Add to map action no longer leaves a stale "nox Emissions" / "co
  Emissions" / etc. layer alongside the new one. Prior code iterated
  `mapCanvas().layers()` for name-based dedup, which excludes any
  layer the user has hidden in the legend or that has been removed
  from the canvas's render set without being deleted from the project.
  QGIS does not auto-dedup layer names (two layers can coexist with the
  same name; layers are keyed by id). Now iterates
  `QgsProject.instance().mapLayers()` so any prior layer with the
  matching name is removed regardless of canvas state.
- **Meteo CSV schema drift fixed** — the GUI validator at
  `OpenAlaqsInventory.examine_met_file` and the loader at
  `AmbientCondition.initAmbientCondition` previously had two separate
  copies of the meteo CSV schema dict. An earlier unit fix
  (`RelativeHumidity(%)` → `(0-1)`, `SeaLevelPressure(mb)` → `(Pa)`)
  was applied to the loader only, so every CSV satisfying the loader
  failed the GUI validator with a "Headers of meteo csv file do not
  match" popup. Schema is now hoisted to a module-level constant
  `METEO_CSV_HEADERS` in `core/interfaces/AmbientCondition.py` and
  imported by both consumers. Drift is impossible.

## Test suite

```
cd /path/to/open_alaqs
QT_QPA_PLATFORM=offscreen PYTHONPATH=$PWD python3 -m pytest tests/
```

Current status: 290 passed, 5 skipped, 0 failed.

## License

EUPL-1.2 with EUROCONTROL amendments. See `LICENCE.md` and
`AMENDMENT_TO_EUPL_license.md`.
