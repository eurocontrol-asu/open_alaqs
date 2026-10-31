# Training course: errata

The [training course slides](../pdf/Airport%20Local%20Air%20Quality%20Studies%20with%20OpenALAQS%20-%20Training%20Course.pdf) (March 2026) predate plugin 5.4.1. Where the slides and this documentation differ, the documentation is correct. The differences:

- The plugin version shown (3.0.DEV) is outdated; see [Installation](../../README.md#installation).
- The **Vertical Limit** fields are greyed out and have no effect. The LTO ceiling is the meteo mixing height, or 914.4 m without meteo; see [LTO ceiling and segment clipping](../methods/AIRCRAFT_EMISSIONS.md#lto-ceiling-and-segment-clipping).
- The **Generate Emission Inventory** window no longer has Advanced Options and has a new **ADS-B Table** field; see [Calculate Emissions Inventory window](USER_GUIDE.md#calculate-emissions-inventory-window).
- The movements file is semicolon-separated, and its columns and `apu_code` values have changed; see [Movements](INPUT_FORMATS.md#movements).
- The meteo headers are `RelativeHumidity(0-1)` and `SeaLevelPressure(Pa)`; the relative humidity is a fraction; see [Meteorology](INPUT_FORMATS.md#meteorology).
- Activity profiles are relative shapes. A zero moves emissions to other hours and does not lower the annual total; see [Activity profiles](USER_GUIDE.md#activity-profiles).
- The Configuration tab has new settings: **Atmosphere Aloft** (default `standard_lapse`), **BFFM2 Fuel-Flow Source** and **Time Interval**; see [Calculate emissions and query results](USER_GUIDE.md#calculate-emissions-and-query-results).
- The AUSTAL site defaults are 0.1 m, 0.6 m and 10.6 m, not 0.2, 1.2 and 11.2 m; see [Site parameters](DISPERSION_AUSTAL.md#site-parameters).
- The **Calculate Dispersion** dialog now writes the AUSTAL inputs itself, with pollutants, receptors, NOTALUFT and emission settings; see [Calculate Dispersion dialog](DISPERSION_AUSTAL.md#calculate-dispersion-dialog).
- The taxi routes editor has two tabs, **Create new route** and **Edit route**; see [Taxi routes](USER_GUIDE.md#taxi-routes).
- Road traffic emissions do not include tyre and brake wear; see [Pollutant mapping](../methods/STATIONARY_AND_ROAD.md#pollutant-mapping).
- Helicopters, engine test sites and the compliance report are not in the slides; see [Helicopters (FOCA 2015)](USER_GUIDE.md#helicopters-foca-2015), [Engine test sites](USER_GUIDE.md#engine-test-sites) and [The compliance report](DISPERSION_AUSTAL.md#the-compliance-report).
