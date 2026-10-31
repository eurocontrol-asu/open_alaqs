# OpenALAQS reference data

This page describes the default data that ships with OpenALAQS: the tables of the study database, where their values come from, and where their provenance is recorded. It is for modellers who want to check or update the default emission factors; the methods that use these tables are described on the method pages linked from each section.

- [OpenALAQS database](#openalaqs-database)
- [Aircraft and airport data](#aircraft-and-airport-data)
- [Aircraft engine emission indices](#aircraft-engine-emission-indices)
- [APU, main engine start and ground support equipment](#apu-main-engine-start-and-ground-support-equipment)
- [Helicopters](#helicopters)
- [ANP flight profiles](#anp-flight-profiles)
- [COPERT road vehicle emission factors](#copert-road-vehicle-emission-factors)
- [Stationary source emission factors](#stationary-source-emission-factors)
- [Emission dynamics](#emission-dynamics)

## OpenALAQS database

The internal [`OpenALAQS database`](../../open_alaqs/database/data) contains default emission factors for all airport sources. When the user creates a new study, these files are copied to the new `.alaqs` file. The study keeps its copy: a study made with an older version keeps the older tables until they are refreshed (see [Upgrading from 5.3.x](../user/UPGRADING.md#upgrading-from-53x)). If the user has access to more up-to-date information, they can update the default data as described in the [`README`](../../README.md#updating-the-open-alaqs-database-templates) file.

Alternatively, OpenALAQS files can be easily viewed and edited with [`DB Browser for SQLite`](https://sqlitebrowser.org/) an open source tool designed for manipulating SQLite database files.

## Aircraft and airport data

The internal database contains an extensive list of aircraft (see [`default_aircraft`](../../open_alaqs/database/data/default_aircraft.csv)) along with information on the most representative engine, APU, departure/arrival profiles and other characteristics.

A list of airports is also available (see [`default_airports`](../../open_alaqs/database/data/default_airports.csv)) with information on their location and elevation (feet above mean sea level).

## Aircraft engine emission indices

Aircraft emissions are calculated based on the recommendations of [`ICAO Doc. 9889`](https://www.icao.int/sites/default/files/environmental-protection/Documents/Publications/9889_cons_en.pdf). The methods are described in [Aircraft emissions](AIRCRAFT_EMISSIONS.md#methods).

Information on exhaust emissions of aircraft engines is taken from the [`ICAO Aircraft Engine Emissions Databank`](https://www.easa.europa.eu/en/domains/environment/icao-aircraft-engine-emissions-databank) (EEDB) and the [`FOCA Aircraft Piston Engine database`](https://www.bazl.admin.ch/en/engine-emissions). Default emission factors are also provided for some turboprop engine types; additional information can be obtained from the confidential [`FOI Turboprop Emissions Database`](http://www.foi.se/en/our-knowledge/aeronautics-and-air-combat-simulation/fois-confidential-database-for-turboprop-engine-emissions.html).

### Engine emission index table (`default_aircraft_engine_ei`)

The engine EI table contains one row per engine per LTO mode (TX, AP, CL, TO). The key columns are:

| Column | Description |
|---|---|
| `engine_name` | ICAO engine designator |
| `mode` | LTO mode: TX, AP, CL, TO |
| `fuel_kg_sec` | Reference fuel flow (kg/s per engine, SLS) |
| `nox_ei`, `co_ei`, `hc_ei` | EEDB gas-phase emission indices (g/kg) |
| `sox_ei` | SOx (as SO2) emission index (g/kg): 0.758 for the Jet Fuel rows and 0.2 for the AvGas rows of the shipped data; a 0 or empty value is replaced by the value of the row's fuel |
| `pm10_ei` | Total combustion PM10 EI (g/kg) = `pm10_nonvol` + `pm10_sul` + `pm10_organic` (to rounding), except for the FOCA pistons and turboprops (P*, PF*, T601 to T603, T717, T790; `source` "ACT_PRF 2.6.3 (CAEP14 FOCA 2026-10-09)"), whose `pm10_ei` is the FOCA total PM of the file: the file gives no volatile and sulphate parts for them, so they carry no `pm10_sul` and `pm10_organic`. For the FOCA business jets the file gives the parts: B004 and B134 take them (they sum to the file's total); for B601, B602 and B603 the file's parts do not sum to its total (0.84 to 1.60 times, by mode), and `pm10_ei` is the sum of the parts, nvPM + volatile + sulphate |
| `pm10_nonvol` | Non-volatile PM (nvPM) mass EI (g/kg) from ICAO EEDB |
| `pm10_sul` | Sulphate vPM EI (g/kg): a constant 0.04896 g/kg (48.96 mg/kg) for the Jet Fuel engines with PM data, 0 for the AvGas rows |
| `pm10_organic` | Organic vPM EI (g/kg), from the EEDB HC EI of the mode |
| `p1_ei`, `p2_ei` | PM1.0 and PM2.5 EI placeholders (g/kg); currently equal to `pm10_ei` |
| `nvpm_number_ei` | nvPM number EI (#/kg) from ICAO EEDB |
| `press_ratio` | Overall pressure ratio (OPR) for MEEM V1 above 3000 ft above the aerodrome: the ICAO EEDB v31 value, ACT_PRF for engines not in it; set for 890 jet engines, empty for the others (30 is then used) |
| `meem_nvpm_m_i_f00_avg` | Thrust of the 5th nvPM mass point for MEEM V1 (used when above 0, with `nvpm_m_max_mgkg`); same sources; above 0 for 77 engines (51 EEDB 5-point engines and 26 ACT_PRF 5-point engines), 0 for the 4-point engines |
| `nvpm_m_max_mgkg` | Maximum nvPM mass EI (mg/kg), same sources; the 5th mass point when `meem_nvpm_m_i_f00_avg` is above 0, otherwise not used |
| `meem_nvpm_n_i_f00_avg` | Thrust of the 5th nvPM number point for MEEM V1 (used when above 0, with `nvpm_n_max_nkg`); same sources as the mass point |
| `nvpm_n_max_nkg` | Maximum nvPM number EI (#/kg), same sources; the 5th number point when `meem_nvpm_n_i_f00_avg` is above 0, otherwise not used |

How the PM columns are derived (sulphate and organic vPM, SOx from the fuel sulphur content, MEEM V1 above 3000 ft, brake wear) is described in [Aircraft emissions: particulate matter](AIRCRAFT_EMISSIONS.md#particulate-matter). Columns that are no longer read are listed in [`DEPRECATIONS.md`](../developer/DEPRECATIONS.md).

## APU, main engine start and ground support equipment

- APU emission factors and operating times: [`default_aircraft_apu_ef`](../../open_alaqs/database/data/default_aircraft_apu_ef.csv) and [`default_apu_times`](../../open_alaqs/database/data/default_apu_times.csv). The APU model of each aircraft is the `apu_id` column of `default_aircraft`.
- Main engine start (MES) emissions per aircraft group: [`default_aircraft_start_ef`](../../open_alaqs/database/data/default_aircraft_start_ef.csv) (unit `gram/aircraft` in the CSV, applied once per engine started).
- GSE and GPU emission factors and activity times: [`default_gate_profiles`](../../open_alaqs/database/data/default_gate_profiles.csv). The emission factors are in grams of pollutant per hour, by gate type, aircraft category and operation type.

How these tables are used, and how the `apu_code` and `gate_emissions_code` fields of the movements switch them on, is described in [Aircraft emissions: APU, GSE and engine start](AIRCRAFT_EMISSIONS.md#apu-gse-and-engine-start).

## Helicopters

Helicopters have their own catalog (`default_helicopter`, `default_helicopter_engines`) and no stored emission indices: emissions are computed with the FOCA 2015 method. See [Helicopters](HELICOPTERS.md).

## ANP flight profiles

The [`Aircraft Noise and Performance`](https://www.easa.europa.eu/en/domains/environment/policy-support-and-research/aircraft-noise-and-performance-anp-data) (ANP) database contains a standardized dataset with information related to aircraft flight performance under various conditions. This includes engine performance characteristics and flight profiles for a wide variety of aircraft types, including standard departure and approach procedures.

We note that in the context of EASA having a legal mandate to collect and verify the ANP data since Reg. (EU) 598/2014 has entered into force, the management and hosting of the ANP legacy data (version 2.3 and prior versions) have been transferred from EUROCONTROL to EASA in order to establish a single ANP data source.

OpenALAQS stores the ANP fixed-point profiles in [`default_aircraft_profiles`](../../open_alaqs/database/data/default_aircraft_profiles.csv). Each profile is a series of points with horizontal and vertical distance, true airspeed, power setting and LTO mode. Profiles with `course = CUSTOM` are not ANP profiles: they hold trajectories derived from ADS-B recordings. The sources of the catalogue and the corrections made to it are recorded in [`AIRCRAFT_PROFILES_PROVENANCE.md`](../developer/AIRCRAFT_PROFILES_PROVENANCE.md). How the profiles are placed on the runway and used in the emission calculation is described in [Aircraft emissions: flight profiles (ANP)](AIRCRAFT_EMISSIONS.md#flight-profiles-anp).

## COPERT road vehicle emission factors

The roadway and parking emission factors (landside, airside and parking lots) come from COPERT (version 5.4.52), the EU standard vehicle emissions calculator, developed by [`EMISIA`](https://copert.emisia.com/) for the European Environment Agency (EEA).

COPERT contains emission factors for more than 450 individual vehicle types considering factors such as vehicle type, age, mileage, and driving conditions. Its methodology comprises the road transport chapters in the [`EMEP/EEA Air Emissions Inventory Guidebook`](https://www.eea.europa.eu/publications/emep-eea-guidebook-2023) and is consistent with the 2006 IPCC Guidelines.

The vehicle categories in the OpenALAQS table are Passenger Cars (PCs), Light Commercial Vehicles (LCVs), Heavy Duty Trucks (HDTs), buses and motorcycles. Only petrol and diesel engines are included. Emission factors are provided for 38 entries: 26 EU Member States (Slovakia is not currently present in the dataset), the EU27 and EU28 aggregates, plus UK, Iceland, Norway, Switzerland, Liechtenstein, North Macedonia, Turkey, Albania, Serbia, and Montenegro.

Special remarks:

- HDTs petrol: only "Conventional" Euro standard option is available.
- Motorcycles: only "Petrol" fuel option is available.
- Buses: only "Diesel" fuel option is available.
- Evaporative emissions: only VOC pollutant is available.
- The emission factors include information for idling periods.

The values are in [`default_vehicle_ef_copert5`](../../open_alaqs/database/data/default_vehicle_ef_copert5.csv), with separate rows for `Hot`, `Cold` and `Evaporation` conditions and one column per 10 km/h speed bin from 10 to 130 km/h. Two data items are open:

- EU27 / EU28 labelling mismatch: the EU27 country aggregate is missing PM10 rows (EU28 has them instead). Correcting it requires re-running the ingest to produce a consistent EU-aggregate set.
- NH3 values appear about 10 times lower than the Guidebook Tier 2 references. This has no effect on results because NH3 is not an output of the road traffic calculation.

The file layout, the source COPERT version and these data items are documented in [`DATASET_PROVENANCE.md`](../developer/DATASET_PROVENANCE.md). How the factors become fleet-averaged emission factors and hourly emissions is described in [Stationary and road sources: road traffic and parkings](STATIONARY_AND_ROAD.md#road-traffic-and-parkings-copert).

## Stationary source emission factors

[`default_stationary_ef`](../../open_alaqs/database/data/default_stationary_ef.csv) holds the default emission factors of point sources, by category and type. The seven categories are *Other* (0), *Incinerator* (1), *Power/Heat Plant* (2), *Fuel Tank* (3), *Solvent Degreaser* (4), *Surface Coating* (5) and *Stationary IC Engine* (6). The main columns are:

| Column | Description |
|---|---|
| `category`, `type`, `description` | Source category, type within the category, and its name |
| `co_kg_k`, `hc_kg_k`, `nox_kg_k`, `sox_kg_k`, `particulate_kg_k`, `p1_kg_k`, `p2_kg_k` | Emission factors in kg per activity unit |
| `activity_unit` | Unit the factors refer to: `1000_m3` (natural gas), `1000_L` (liquid fuel throughput), `1000_kg` (waste, coating), `hr` (engine operating hours) |
| `reference` | Source of the factors: US EPA AP-42 (sections 1.4, 3.3 and 3.4) or EMEP/EEA (1.A.4); `AP-42 (legacy mapping)` for the rows carried over from earlier versions |
| `deprecated` | `1` for the legacy rows kept so that older studies still resolve, `0` for the current rows |
| `recommended_hour_profile`, `recommended_day_profile`, `recommended_month_profile` | Suggested activity profile names for the type |

The shipped table has 64 rows, 14 of them current. The factors can be modified if more up-to-date information is available. The calculation is described in [Stationary and road sources: point and area sources](STATIONARY_AND_ROAD.md#point-and-area-sources).

## Emission dynamics

[`default_emission_dynamics`](../../open_alaqs/database/data/default_emission_dynamics.csv) holds the source dynamics parameters per aircraft group and LTO mode: horizontal extent, vertical extent and vertical shift, once for the `default` method and once for the `smooth & shift` method (columns ending in `_sas`). The values were originally derived from [`LASPORT`](https://www.janicke.de/en/lasport.html) v1.6 and later updated to LASPORT v2.2. Their use is described in [Stationary and road sources: source dynamics](STATIONARY_AND_ROAD.md#source-dynamics-smooth-and-shift).

See also: [Aircraft emissions](AIRCRAFT_EMISSIONS.md), [Stationary and road sources](STATIONARY_AND_ROAD.md), [Helicopters](HELICOPTERS.md), [Dataset provenance (COPERT)](../developer/DATASET_PROVENANCE.md).
