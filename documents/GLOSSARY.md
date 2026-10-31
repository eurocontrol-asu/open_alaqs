# Glossary

Short definitions of the terms and abbreviations used in the OpenALAQS documentation, in alphabetical order. Each entry links to the page that explains the term in full.

[A](#a) · [B](#b) · [C](#c) · [D](#d) · [E](#e) · [F](#f) · [G](#g) · [I](#i) · [L](#l) · [M](#m) · [N](#n) · [O](#o) · [P](#p) · [Q](#q) · [R](#r) · [S](#s) · [T](#t) · [V](#v) · [Z](#z)

## A

**.alaqs file**: an OpenALAQS file (SQLite). The *study* file holds the geometry, the sources and the study setup; the *inventory* file (`<name>_out.alaqs`) is made from it by *Calculate Emissions Inventory*, with the movements and the meteorology. [User Guide](user/USER_GUIDE.md#calculate-emissions-inventory-window)

**Activity profile**: hourly, daily and monthly factors that spread the annual activity of a stationary source over the year. [User Guide](user/USER_GUIDE.md#activity-profiles), [method](methods/STATIONARY_AND_ROAD.md#point-and-area-sources)

**ADS-B**: recorded flight tracks (position, height, speed, power setting or fuel flow) that replace the standard flight profile of selected movements. [Format](user/INPUT_FORMATS.md#ads-b-tracks), [method](methods/AIRCRAFT_EMISSIONS.md#ads-b)

**ANP**: the Aircraft Noise and Performance database (EUROCONTROL/EASA), source of the standard departure and arrival profiles. [Flight profiles](methods/AIRCRAFT_EMISSIONS.md#flight-profiles-anp), [provenance](developer/AIRCRAFT_PROFILES_PROVENANCE.md)

**APU**: auxiliary power unit of an aircraft, set per movement with `apu_code`. [Method](methods/AIRCRAFT_EMISSIONS.md#apu-gse-and-engine-start), [movements format](user/INPUT_FORMATS.md#movements)

**Atmosphere Aloft** (`atmosphere_model`): how the temperature, pressure and humidity at each flight segment's height are derived from the hourly meteorological row: `standard_lapse` (default, ISA lapse rate), `surface_layer` (AUSTAL boundary-layer profile) or `ground_held` (ground values at every height). [Ambient conditions aloft](methods/ATMOSPHERE_ALOFT.md)

**AUSTAL**: the Lagrangian dispersion model of the German TA Luft, used by OpenALAQS for concentrations. [Installation](AUSTAL/AUSTAL.md), [use](user/DISPERSION_AUSTAL.md)

## B

**BFFM2**: Boeing Fuel Flow Method 2 (SAE AIR 5715). It derives the NOx, CO and HC emission indices from the fuel flow, corrected for ambient conditions. [BFFM2](methods/AIRCRAFT_EMISSIONS.md#bffm2)

**bymode**: the method that uses the ICAO engine emission indices and fuel flow of each LTO mode. [Methods](methods/AIRCRAFT_EMISSIONS.md#methods)

## C

**CAEP14 reference**: the project's independent implementation of the CAEP/14 engine emissions calculation, used to check the plugin and the standalone pipeline. [CAEP14 reference validation](../openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md)

**COPERT**: the EU road-transport emission model; OpenALAQS uses its emission factors (with the EMEP/EEA Guidebook) for roadways and parkings. [Method](methods/STATIONARY_AND_ROAD.md#road-traffic-and-parkings-copert), [data](methods/REFERENCE_DATA.md#copert-road-vehicle-emission-factors)

**CUSTOM profile**: a flight profile made from an ADS-B track. [ADS-B](methods/AIRCRAFT_EMISSIONS.md#ads-b)

## D

**d0**: displacement height of the wind profile, in m. See *Site parameters*.

**δ, θ (delta, theta)**: ambient pressure and temperature divided by their ISA sea-level values; the fuel flow derived from a power setting (BFFM2 `trajectory` source, taxi) is scaled with δ√θ. [Fuel flow](methods/AIRCRAFT_EMISSIONS.md#fuel-flow)

## E

**EEDB**: the ICAO Aircraft Engine Emissions Databank: certified fuel flow, emission indices and nvPM of each engine and LTO mode. [Reference data](methods/REFERENCE_DATA.md#aircraft-engine-emission-indices)

**Engine test site**: an area source flagged as a run-up pad; its emissions come from a list of engine test events instead of emission factors. [User Guide](user/USER_GUIDE.md#engine-test-sites), [method](methods/STATIONARY_AND_ROAD.md#engine-test-sites), [format](user/INPUT_FORMATS.md#engine-test-events)

## F

**FOA3**: the ICAO First Order Approximation for volatile particulate matter (sulphate and organic). [Particulate matter](methods/AIRCRAFT_EMISSIONS.md#particulate-matter)

**FOCA 2015**: the Swiss Federal Office of Civil Aviation guidance on helicopter emissions, used for helicopter movements. [Helicopters](methods/HELICOPTERS.md)

**Fuel-flow source**: for BFFM2, where the fuel flow of a segment comes from: `trajectory` (from the segment's thrust, scaled to ambient) or `mode_anchor` (the EEDB fuel flow of the segment's mode). [Fuel-flow sources](methods/AIRCRAFT_EMISSIONS.md#fuel-flow-sources)

## G

**GSE, GPU**: ground support equipment and ground power unit at the gate. [Method](methods/AIRCRAFT_EMISSIONS.md#gse-and-gpu)

## I

**ICCAIA NOx correction**: the correction of the bymode NOx emission index for ambient temperature, humidity and take-off weight (`tow_ratio`) on take-off and climb-out (*Apply NOx Corrections*). [NOx ambient correction](methods/AIRCRAFT_EMISSIONS.md#nox-ambient-correction)

**In Study**: the attribute that includes a source in the calculation. [User Guide](user/USER_GUIDE.md#visualize-and-edit-attribute-values)

**ISA**: the ICAO International Standard Atmosphere (15 °C and 1013.25 hPa at sea level, 6.5 K/km lapse rate).

## L

**LTO cycle**: the ICAO landing and take-off cycle below 3,000 ft (914.4 m) above the aerodrome, with the modes taxi (TX), approach (AP), climb-out (CL) and take-off (TO). [LTO modes](methods/AIRCRAFT_EMISSIONS.md#lto-modes)

## M

**Mach number**: the true airspeed divided by the speed of sound at the local temperature. BFFM2 uses the Mach number of each flight segment's start point to convert the fuel flow to reference conditions; taxi uses 0. [BFFM2, step 2](methods/AIRCRAFT_EMISSIONS.md#step-2-reference-fuel-flow)

**Main engine start (MES)**: the emissions of starting the main engines, and the time of the start during taxi. [Main engine start](methods/AIRCRAFT_EMISSIONS.md#main-engine-start)

**MEEM V1**: the ICAO CAEP/13-MDG method that gives the nvPM emission indices of the segments above 3,000 ft. [MEEM V1](methods/AIRCRAFT_EMISSIONS.md#meem-v1-nvpm-above-3000-ft)

**Mixing height**: height of the atmospheric boundary layer, in m, from the meteo file. It is also the emission ceiling of each hour. [Meteorology](user/INPUT_FORMATS.md#meteorology)

## N

**NOTALUFT**: an AUSTAL option that writes per-hour concentrations, needed for time series and the compliance report. [Calculate Dispersion dialog](user/DISPERSION_AUSTAL.md#calculate-dispersion-dialog)

**nvPM, vPM**: non-volatile (soot) and volatile particulate matter. [Particulate matter](methods/AIRCRAFT_EMISSIONS.md#particulate-matter)

## O

**Obukhov length**: a measure of atmospheric stability, in m, from the meteo file. [Meteorology](user/INPUT_FORMATS.md#meteorology)

## P

**Profile** (flight profile): the sequence of points (distance, height, speed, power) that a movement flies; standard profiles come from ANP. [Flight profiles](methods/AIRCRAFT_EMISSIONS.md#flight-profiles-anp)

## Q

**QNH**: the sea-level pressure reported in METAR, given in the meteo file as `SeaLevelPressure(Pa)`. [Ambient conditions aloft](methods/ATMOSPHERE_ALOFT.md)

**Quality level**: the AUSTAL setting of the number of particles (`qs`); a higher level lowers the statistical uncertainty and lengthens the run. [Calculate Dispersion dialog](user/DISPERSION_AUSTAL.md#calculate-dispersion-dialog)

## R

**Receptor point**: a point where AUSTAL writes a concentration time series. [Format](user/INPUT_FORMATS.md#receptor-points)

## S

**Site parameters**: the roughness length z0, the displacement height d0 and the anemometer height ha written to AUSTAL. [Site parameters](user/DISPERSION_AUSTAL.md#site-parameters)

**Smooth & Shift, source dynamics**: spreading of the aircraft emissions over a volume around the flight path, to represent the initial spread of the exhaust plume (options `none`, `default`, `smooth & shift`). [Source dynamics](methods/STATIONARY_AND_ROAD.md#source-dynamics-smooth-and-shift)

**Standalone pipeline**: `openalaqs_standalone`, the QGIS-free implementation of the calculation for batch runs. [Running without the QGIS window](user/WITHOUT_QGIS.md)

## T

**TA Luft**: the German Technical Instructions on Air Quality Control, which define AUSTAL and its default parameters. [Dispersion modelling with AUSTAL](user/DISPERSION_AUSTAL.md)

**Time in mode**: the duration of each LTO mode of a movement. [Methods](methods/AIRCRAFT_EMISSIONS.md#methods)

## V

**Vertical limit**: a field of the study setup and of the calculation settings that the plugin does not use; the LTO ceiling of each hour is the meteo mixing height, or 914.4 m when there is none. [LTO ceiling](methods/AIRCRAFT_EMISSIONS.md#lto-ceiling-and-segment-clipping)

## Z

**z0**: roughness length of the land cover, in m See *Site parameters*.
