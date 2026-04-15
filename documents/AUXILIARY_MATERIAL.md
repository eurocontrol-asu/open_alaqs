# OpenALAQS User Guide - Auxiliary Material

## [Table of Contents](#table-of-contents)
- [OpenALAQS Database](#OpenALAQS-database)
  - [Aircraft and airport data](#aircraft-and-airport-data)
  - [Emissions factors](#emission-factors)
    - [Aircraft emissions](#aircraft-emissions)
    - [Non-aircraft emissions](#non-aircraft-emissions)
- [ANP](#anp)
  - [Aircraft trajectories](#aircraft-trajectories)
  - [Performance profiles](#performance-profiles)
- [BFFM2](#bffm2)
- [AUSTAL](#austal)
- [COPERT](#copert)
- [Smooth and Shift](#smooth-and-shift)

## [OpenALAQS Database](#OpenALAQS-database)
[(Back to top)](#table-of-contents)

The internal [`OpenALAQS database`](./../open_alaqs/database/data/) contains default emission factors for all airport sources. When the user creates a new study, these files are copied to the new `.alaqs` file. If the user has access to more up-to-date information, they can update the default data as described in the [`README`](./../README.md#updating-the-openalaqs-database-templates) file.

Alternatively, OpenALAQS files can be easily viewed and edited with [`DB Browser for SQLite`](https://sqlitebrowser.org/) an open source tool designed for manipulating SQLite database files.

### [Aircraft and airport data](#aircraft-and-airport-data)

The internal database contains an extensive list of aircraft (see [`default_aircraft`](./../open_alaqs/database/data/default_aircraft.csv)) along with information on the most representative engine, APU, departure/arrival profiles and other characteristics.

A list of airports is also available (see [`default_airports`](./../open_alaqs/database/data/default_airports.csv)) with information on their location and elevation above ground.

### [Emissions factors](#emission-factors)

#### Aircraft emissions

Aircraft emissions are calculated based on the recommendations of [`ICAO Doc. 9889`](https://www.icao.int/publications/documents/9889_cons_en.pdf).

Information on exhaust emissions of aircraft engines is taken from the [`ICAO Aircraft Engine Emissions Databank`](https://www.easa.europa.eu/en/domains/environment/icao-aircraft-engine-emissions-databank) (EEDB) and the [`FOCA Aircraft Piston Engine database`](https://www.bazl.admin.ch/bazl/fr/home/themen/umwelt/schadstoffe/emissions-des-moteurs/rapport-recapitulatif--annexes--banque-et-feuilles-de-donnees.html). Default emission factors are also provided for some turboprop engine types; additional information can be obtained from the confidential [`FOI Turboprop Emissions Database`](http://www.foi.se/en/our-knowledge/aeronautics-and-air-combat-simulation/fois-confidential-database-for-turboprop-engine-emissions.html).

For the BFFM2 emission calculation method, see the [BFFM2 section](#bffm2) below.

##### Engine emission index table (`default_aircraft_engine_ei`)

The engine EI table contains one row per engine per LTO mode (TX, AP, CL, TO). The key columns are:

| Column | Description |
|---|---|
| `engine_name` | ICAO engine designator |
| `mode` | LTO mode: TX, AP, CL, TO |
| `fuel_kg_sec` | Reference fuel flow (kg/s per engine, SLS) |
| `nox_ei`, `co_ei`, `hc_ei` | EEDB gas-phase emission indices (g/kg) |
| `sox_ei` | SOx emission index (g/kg); default 1.0 for jet fuel |
| `pm10_ei` | Total combustion PM10 EI (g/kg) = `pm10_nonvol` + `pm10_sul` + `pm10_organic` |
| `pm10_nonvol` | Non-volatile PM (nvPM) mass EI (g/kg) from ICAO EEDB |
| `pm10_sul` | Sulphate vPM EI (g/kg); see PM10 breakdown below |
| `pm10_organic` | Organic vPM EI (g/kg); see PM10 breakdown below |
| `p1_ei`, `p2_ei` | PM1.0 and PM2.5 EI placeholders (g/kg); currently equal to `pm10_ei` |
| `nvpm_number_ei` | nvPM number EI (#/kg) from ICAO EEDB |
| `press_ratio` | Overall pressure ratio (OPR) for MEEM V1 correction |
| `meem_nvpm_m_i_f00_avg` | MEEM V1: average nvPM mass EI at F00 (mg/kg) |
| `nvpm_m_max_mgkg` | MEEM V1: maximum nvPM mass EI (mg/kg) |
| `meem_nvpm_n_i_f00_avg` | MEEM V1: average nvPM number EI at F00 (#/kg) |
| `nvpm_n_max_nkg` | MEEM V1: maximum nvPM number EI (#/kg) |

##### PM10 breakdown

Aircraft PM10 emissions are decomposed into three physical components, stored separately to allow independent reporting and future updating:

**Non-volatile PM (`pm10_nonvol`)** — carbonaceous (soot) particles measured at ICAO SLS conditions and stored in the EEDB. Subject to MEEM V1 ambient correction if 5-point data is available (see below).

**Sulphate PM (`pm10_sul`)** — volatile sulphate particles formed from sulphur in the fuel. Computed from the fuel sulphur content (FSC) and a conversion efficiency ε using ICAO Doc 9889 Appendix D:

```
pm10_sul (g/kg) = FSC (kg/kg) × ε × 3 062 500
```

The database uses **FSC = 500 ppm (0.0005 kg/kg)** and **ε = 0.024** (CAEP14 default), giving a constant value of **36.75 mg/kg** for all engines and all modes.

**Organic vPM (`pm10_organic`)** — volatile organic particles from unburned hydrocarbons, calculated by the parameterised vPM method from ICAO Doc 9889 Appendix D:

```
pm10_organic (g/kg) = δ_k × EI_HC (g/kg)
```

where δ_k is the mode-specific conversion factor:

| Mode | δ_k |
|---|---|
| TO | 115 |
| CL | 76 |
| AP | 56.25 |
| TX | 6.17 |

**Total combustion PM10** = `pm10_nonvol` + `pm10_sul` + `pm10_organic`, stored in `pm10_ei`.

**Brake wear (FOA3).** For arriving aircraft with MTOW > 18 632 kg, the first taxi segment receives an additional PM10 contribution from tyre and brake wear:

```
PM10_brake_wear (g) = MTOW (kg) × 0.000476 − 8.74
```

This is added to the PM10, P1, and P2 output columns, but does not appear in the combustion sub-component columns (`pm10_nonvol_kg`, `pm10_sul_kg`, `pm10_organic_kg`).

**P1 / P2.** These output columns are placeholders for PM1.0 and PM2.5 respectively. They are currently set equal to PM10 (including brake wear for arrivals) because dedicated sub-micron EEDB emission indices are not yet available. They will be updated as the data becomes available.

##### MEEM V1 — nvPM ambient correction

The ICAO EEDB nvPM emission indices are measured at SLS conditions (T = 288.15 K, P = 101 325 Pa, Mach = 0). The nvPM EI varies with combustor inlet pressure. The **MEEM V1** correction from CAEP14 / ICAO Doc 9889 Appendix C accounts for this.

When 5-point nvPM data is available for an engine (columns `meem_nvpm_m_i_f00_avg`, `nvpm_m_max_mgkg`, `meem_nvpm_n_i_f00_avg`, `nvpm_n_max_nkg`), OpenALAQS applies the following procedure at every profile segment:

1. Compute the ISA and ambient combustor inlet pressures P3_ISA and P3_amb from the OPR (`press_ratio`) and the ambient conditions in `tbl_InvMeteo`.
2. Convert the actual thrust setting to a ground-reference (ISA) equivalent: `F_GR = F_act × (P3_ISA / P3_amb)`.
3. Interpolate the corrected nvPM mass EI from the 5-point curve using log-log interpolation; the number EI uses linear interpolation.

The correction applies to both Bymode and BFFM2. Engines without 5-point MEEM data fall back to the stored EEDB nvPM EI without correction.

**APU emissions** are calculated separately as a function of the APU model (`apu_id`) indicated for each aircraft in [`default_aircraft`](./../open_alaqs/database/data/default_aircraft.csv). The default APU emission factors and operating times are given in [`default_aircraft_apu_ef`](./../open_alaqs/database/data/default_aircraft_apu_ef.csv) and [`default_apu_times`](./../open_alaqs/database/data/default_apu_times.csv) respectively. Whether APU emissions are included for a given movement is controlled by the `apu_code` field in the movements table:

| `apu_code` | Meaning |
|---|---|
| −1 or 0 | No APU emissions (default when field is empty) |
| 1 | APU running at gate/stand only |
| 2 | APU running during full taxi |

**MES (Main Engine Start) emissions** are given in [`default_aircraft_start_ef`](./../open_alaqs/database/data/default_aircraft_start_ef.csv) per aircraft group. The unit of the stored values is **grams per aircraft per start event** — that is, the value represents the total emission for all engines on the aircraft for one engine-start event. No per-engine multiplication is applied in the code. MES emissions are calculated for departure movements only. Whether MES emissions are included is controlled by the `gate_emissions_code` field in the movements table:

| `gate_emissions_code` | Meaning |
|---|---|
| 0 | Suppress all gate emissions (GSE, GPU, and MES) |
| 1 | Include all gate emissions (default) |

#### Non-aircraft emissions

The corresponding GSE/GPU emission factors and activity times are included in the OpenALAQS database (see [`default_gate_profiles`](./../open_alaqs/database/data/default_gate_profiles.csv)). Emission factors are expressed in grams of pollutant per hour and are assigned by gate type, aircraft category, and operation type.

The internal OpenALAQS database also contains default emission factors for stationary sources (see [`default_stationary_ef`](./../open_alaqs/database/data/default_stationary_ef.csv)). These values can be modified if more up-to-date information is available.

## [ANP](#anp)
[(Back to top)](#table-of-contents)

The [`Aircraft Noise and Performance`](https://www.easa.europa.eu/en/domains/environment/policy-support-and-research/aircraft-noise-and-performance-anp-data) (ANP) database contains a standardized dataset with information related to aircraft flight performance under various conditions. This includes engine performance characteristics and flight profiles for a wide variety of aircraft types, including standard departure and approach procedures.

We note that in the context of EASA having a legal mandate to collect and verify the ANP data since Reg. (EU) 598/2014 has entered into force, the management and hosting of the ANP legacy data (version 2.3 and prior versions) have been transferred from EUROCONTROL to EASA in order to establish a single ANP data source.

### [Aircraft trajectories](#aircraft-trajectories)

In OpenALAQS, the ANP fixed-point profiles (see [`default_aircraft_profiles`](./../open_alaqs/database/data/default_aircraft_profiles.csv)) are used to calculate aircraft emissions. Each profile contains a series of points describing the aircraft trajectory (horizontal and vertical distance, true airspeed, power setting, and LTO mode). These points are converted into an aircraft trajectory for a given runway based on its geographic coordinates. Currently, only straight-line trajectories are supported.

Two profile types are supported:

**Standard ANP profiles** (`course = ANP2.x` or similar): coordinates are along-runway distances. The `x_m` and `y_m` columns represent the horizontal distance from the runway threshold along the runway axis and lateral offset respectively.

**ADS-B / CUSTOM profiles** (`course = CUSTOM`): coordinates are geodesic East/North offsets (in metres) from the runway intersection. These are generated from ADS-B recordings and represent the actual flown trajectory. The `fuel_flow_kgm` column, if populated, contains the estimated total-aircraft ambient fuel flow in kg/s for use by the BFFM2 method. Before BFFM2 uses this value, it divides by the engine count to obtain a per-engine estimate. If the per-engine estimate exceeds the EEDB takeoff fuel flow (indicating an unreliable ADS-B estimate), the calculator automatically falls back to power-setting interpolation and logs a warning.

> **Note:** The standard EHRD test case files (`EHRD.alaqs`, `EHRD_out.alaqs`) use only standard ANP profiles. ADS-B / CUSTOM profile support is available but requires the user to populate `default_aircraft_profiles` with custom entries before use.

<img src="./../open_alaqs/assets/anp_profiles_example.png" alt="Aircraft trajectories" width="70%">

### [Performance profiles](#performance-profiles)

The ratio of thrust to distance is used to define the cut-off between take-off and climb-out. During take-off, full thrust is required to accelerate the aircraft. As the aircraft reaches a certain distance and speed, thrust is reduced to a level appropriate for climb. This transition typically occurs at around 1000 feet of ground distance. This cut-off point separates the TO and CL modes in OpenALAQS.

The following figure illustrates this approach. For more information the user is referred to [`ECAC.CEAC Doc 29, Volume 2, Appendix B`](https://www.ecac-ceac.org/images/documents/ECAC-Doc_29_4th_edition_Dec_2016_Volume_2.pdf).

<img src="./../open_alaqs/assets/anp_dep_profile_example.png" alt="Performance profiles" width="50%">

## [BFFM2](#bffm2)
[(Back to top)](#table-of-contents)

The Boeing Fuel Flow Method 2 (BFFM2) is an advanced aircraft emission calculation method defined in SAE AIR-5715 and ICAO Doc. 9889. It is available as an alternative to the standard Bymode method in OpenALAQS.

For full technical details including the step-by-step procedure, ambient correction formulas, and validation results for the EHRD test case, see [`BFFM2.md`](documents/BFFM2_validation/BFFM2.md).

### Principle

Where Bymode assigns a fixed emission index per LTO mode (TX, AP, CL, TO) based on EEDB reference conditions, BFFM2 uses the actual power setting from each profile segment to derive a fuel-flow-dependent emission index. The method:

1. Converts the power setting to a reference fuel flow using twin-quadratic or piecewise-linear interpolation through the four EEDB breakpoints.
2. Applies ambient corrections (θ, δ, Mach number, humidity) to obtain the in-flight fuel flow.
3. Interpolates the emission index on a log-log curve through the four EEDB data points.
4. Computes the emission mass as `EI × FF × n_engines × time_in_segment / 1000`.

PM, SOx, and P1/P2 are not interpolated on the gas-phase curve. Instead, both Bymode and BFFM2 inject the mode-level EI values directly from the database (including MEEM V1 ambient correction for nvPM where 5-point data are available). BFFM2 therefore produces the same per-mode PM and SOx EI values as Bymode; differences in total PM between the two methods arise solely from differences in fuel burn driven by the different power-setting interpolation.

### Installation correction factors

Before log-log interpolation, the EEDB reference fuel flow values at each breakpoint are multiplied by installation correction factors (SAE AIR-5715):

| LTO mode | Correction factor |
|---|---|
| Takeoff (TO) | 1.010 |
| Climbout (CL) | 1.013 |
| Approach (AP) | 1.020 |
| Idle (TX) | 1.100 |

These corrections account for installation losses not captured in the engine-only EEDB certification data. They are applied automatically and are not user-configurable.

### Ambient corrections

+ **NOx**: `EI_corrected = EI_ref × exp(−19 × (ω − 0.00634)) × (δ^1.02 / θ^3.3)^0.5`
+ **CO and HC**: `EI_corrected = EI_ref × θ^3.3 / δ`

where θ = T / 288.15, δ = P / 101 325, and ω is the specific humidity (kg water / kg dry air). Ambient conditions are taken from `tbl_InvMeteo`.

### Important notes

+ **Do not enable Apply NOx Corrections together with BFFM2.** The BFFM2 formula already includes NOx ambient corrections internally. Enabling that option with BFFM2 active will double-correct the NOx emission index.
+ For the taxi phase, BFFM2 uses `engine_thrust_level_for_taxiing` (default 7%) for the moving segments. Queuing and stop-and-go idle phases always use true idle (7%) regardless of this setting.
+ For ADS-B / CUSTOM profiles, the `fuel_flow_kgm` column is used as the total-aircraft ambient fuel flow per segment. It is divided by the engine count before BFFM2 dispatch.

## [AUSTAL](#austal)
[(Back to top)](#table-of-contents)

The dispersion model [`AUSTAL`](https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/overview) is the reference implementation to Annex 2 of the German Environment Agency's Technical Instructions on Air Quality Control (TA Luft) and implements the specifications and requirements given therein.

The program is the successor of AUSTAL2000 (which was previously used with OpenALAQS), the reference implementation to Annex 3 of the TA Luft 2002. AUSTAL and AUSTAL2000 were developed by Janicke Consulting on behalf of the German Environment Agency and are freely available and widely used internationally.

AUSTAL 3.3.0 (released on 22.03.2024) has been developed and tested under Windows and Linux. It is exclusively provided, free of charge under the GNU Public Licence, from the dedicated webpage of the German Environment Agency.

AUSTAL must be installed separately. For more information and links, see the [AUSTAL README](../documents/AUSTAL/AUSTAL.md).

## [COPERT](#copert)
[(Back to top)](#table-of-contents)

The estimation of roadway traffic emissions (landside, airside and parking lots) in OpenALAQS is based on COPERT Emission Factors (EF) (version 5.4.52), the EU standard vehicle emissions calculator, developed by [`EMISIA`](https://www.emisia.com/utilities/copert/) for the European Environment Agency (EEA).

COPERT contains emission factors for more than 450 individual vehicle types considering factors such as vehicle type, age, mileage, and driving conditions. Its methodology comprises the road transport chapters in the [`EMEP/EEA Air Emissions Inventory Guidebook`](https://www.eea.europa.eu/publications/emep-eea-guidebook-2023) and is consistent with the 2006 IPCC Guidelines.

The implementation (see [`copert5.py`](./../open_alaqs/core/tools/copert5.py)) of the COPERT methodology in OpenALAQS preserves the core information from the original model, albeit with some simplification tailored to the scope of OpenALAQS. It generates typical emission factors for roadway segments or parking areas based on fleet year (as a proxy for Euro standard), country, fleet mix, number of vehicles, temperature, average speed, and roadway segment length.

The vehicle categories examined are Passenger Cars (PCs), Light Commercial Vehicles (LCVs), Heavy Duty Trucks (HDTs), buses and motorcycles. Only petrol and diesel engines are included. Emission factors are provided for 37 countries: EU27 Member States, EU27 aggregated, UK, Iceland, Norway, Switzerland, Liechtenstein, North Macedonia, Turkey, Albania, Serbia and Montenegro.

**Special remarks**:
+ HDTs petrol: only "Conventional" Euro standard option is available
+ Motorcycles: only "Petrol" fuel option is available
+ Buses: only "Diesel" fuel option is available
+ Evaporative emissions: only VOC pollutant is available
+ The EF include information for idling periods

The EF values used in OpenALAQS are available in [`default_vehicle_ef_copert5`](./../open_alaqs/database/data/default_vehicle_ef_copert5.csv).

## [Smooth and Shift](#smooth-and-shift)
[(Back to top)](#table-of-contents)

OpenALAQS calculates three-dimensional emission distributions for source groups associated with an airport. To apply this output to dispersion models, it is necessary to account for source dynamics such as turbulence, exhaust momentum from aircraft engines, and thermal plume rise. The effects of source dynamics can be included in an approximate manner within the spatial emission distribution through the "Smooth & Shift" approach, which involves smoothing and shifting the initial source extent.

This approach has been used to connect the emission grid provided by OpenALAQS' precursor model, ALAQS-AV, to dispersion models. The details are outlined in the report [`EEC/SEE/2005/016`](038_Derivation_of_Smooth_and_Shift_Parameters_for_ALAQS-AV.pdf) by EUROCONTROL. The "Smooth & Shift" parameters were originally derived from [`LASPORT`](https://www.janicke.de/en/lasport.html) (version 1.6) and have since been updated to reflect LASPORT version 2.2.

The "Smooth & Shift" parameters are transparently derived and easy to modify. They have been implemented for all airport-related sources, including aircraft, GSE, and GPU. APU emissions are incorporated into aircraft movements.

The figure below illustrates the change in the geometry of taxiing emissions after applying the "Smooth & Shift" parametrization. Each linestring segment of the taxiway (black line) is expanded into a polygon to account for source dynamics.

<img src="./../open_alaqs/assets/smooth-and-shift.png" alt="smooth and shift" width="50%">

The default values used in OpenALAQS are available in [`default_emission_dynamics`](./../open_alaqs/database/data/default_emission_dynamics.csv).
