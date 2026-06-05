# Road traffic / COPERT dataset provenance

This document captures what is currently known and unknown about the road
traffic emission factor data in OpenALAQS, the relationship between its
CSV source and the embedded SQLite caches, and the procedure for a future
refresh against a newer COPERT release. The intent is to make any future
data maintenance easier and to be honest about gaps in the historical
record.

Last updated: 2026-06-05.

## 1. The data file

**Path**: `open_alaqs/database/data/default_vehicle_ef_copert5.csv`

**Rows**: 46435

**Schema** (20 columns):

| Column | Type | Description |
| --- | --- | --- |
| `vehicle_category` | string | Aggregate category: Passenger Cars, Light Commercial Vehicles, Heavy Duty Trucks, Motorcycles, Buses. |
| `fuel` | string | Petrol or Diesel. No CNG, LPG, hybrid, PHEV, or BEV. |
| `euro_standard` | string | Emission standard: Conventional, Euro 1...Euro 6 d (LDV); Conventional, Euro I...Euro VI D/E (HDV); various legacy classes for motorcycles. Does not include Euro 7 / Euro VII. |
| `country` | string | 38 country aggregates. Includes EU27 and EU28 placeholders (see integrity note in §4). |
| `pollutant` | string | CH4, CO, CO2, NH3, NOx, PM0.1, PM2.5, PM10, SO2, VOC. |
| `hot-cold-evaporation` | string | One of: Hot, Cold, Evaporation. |
| `evaporation_split` | string | For Evaporation rows only: Diurnal, Hot soak, Running losses. NULL for Hot and Cold rows. |
| `10`...`130` | float | 13 columns, one per 10 km/h speed bin from 10 to 130. Units are pollutant-dependent (g/km for Hot and Cold exhaust rows; g/day-equivalent for Evaporation rows, with values speed-invariant per row). |

## 2. Source COPERT version

**Documented version**: COPERT 5.4.52. Cited in
`open_alaqs/core/tools/copert5_utils.py` at line 35 and in
`documents/AUXILIARY_MATERIAL.md`.

**Source Guidebook**: EMEP/EEA air pollutant emission inventory guidebook
2019, Update October 2020. Cited at `copert5_utils.py:3`. This is the
generation of the Guidebook the bulk methodology in `copert5*.py` was
implemented against. Specific items verified against the 2023 Update 2025
chapter as part of the 2026 review are cited inline in `copert5.py`,
`copert5_utils.py`, and `AUXILIARY_MATERIAL.md` using the uniform format
`EMEP/EEA Guidebook 2023 Update 2025, chapter <NFR-code>, §<section> (p.<page>)`.

**Items not currently in the repo record**:

- The exact ingest date.
- The provenance of the per-country aggregation: whether the values came
  directly from COPERT 5.4.52 software outputs run by a third party (e.g.
  Emisia), or whether they were derived from a separate per-country fleet
  composition layer applied to underlying Guidebook parameters, or some
  other path. The country-aggregated form of the data implies a fleet
  composition was applied at ingest time, but the composition itself is
  not stored or documented.
- The reference temperature implicit in the Cold-cycle rows (Cold EFs in
  COPERT 5.9.1 are temperature-dependent via a polynomial; the 5.4.52
  pre-computed values in this CSV imply a fixed reference temperature was
  used, but it is not recorded).

These gaps are not fixable from the data alone. A future refresh (see §5)
is the right opportunity to re-record them.

## 3. Embedded SQLite caches

The CSV is the source of truth. Seven `.alaqs` files in the repo embed a
copy of the table `default_vehicle_ef_copert5` and must remain consistent
with the CSV:

| `.alaqs` file | Purpose |
| --- | --- |
| `open_alaqs/core/templates/project.alaqs` | Project template seeded into every new study. |
| `example/training/training.alaqs` | Training example, pre-run state. |
| `example/training/training_out.alaqs` | Training example, post-inventory state. |
| `tests/data/generic/generic_out.alaqs` | Generic regression fixture. |
| `tests/data/ANP/ANP.alaqs` | ANP regression fixture, pre-run. |
| `tests/data/ANP/ANP_out.alaqs` | ANP regression fixture, post-inventory. |
| `gse_application/tests/example_db.alaqs` | GSE application test fixture. |

Two `.alaqs` files have the table schema present but with zero rows
(treated as fresh templates filled at runtime): `open_alaqs/core/templates/
inventory.alaqs` and `scripts/emissions_austal/sample_data/Inventory.alaqs`.
These are left alone during data refresh.

Parity between CSV and the seven populated caches is checked by
`tests/test_database.py::test_example_csv` and
`tests/test_database.py::test_template_data`. After any edit to the CSV,
re-sync the caches with `tools/data_integrity_fixes/sync_csv_into_alaqs_caches.py`
or both parity tests will fail.

## 4. Data integrity status (as of 2026-06-05)

Four data integrity items have been investigated. Status:

| # | Item | Status |
| --- | --- | --- |
| 1 | Suspected Switzerland 10× PM10 error | Not reproducible. Switzerland PM10 rows are bit-identical to Germany/Italy/France/Austria/EU28. Closed. |
| 2 | PM10 < PM2.5 in 639 row pairs (2505 cells) | Fixed via `tools/data_integrity_fixes/fix_pm10_at_least_pm25.py`. PM10[speed] = max(PM10[speed], PM2.5[speed]) per violating cell, satisfying physical constraint and Guidebook §1.1 PM10=PM2.5=TSP equality for road exhaust. |
| 3 | EU27/EU28 labelling mismatch (EU27 has 1137 rows across 9 pollutants but no PM10; EU28 has 118 rows, all PM10) | Open. Caused by ingestion-layer artifact at the time the EU-aggregate rows were generated. Not fixable from the existing CSV alone (the missing PM10 rows for EU27 are not derivable without source data); deferred to a future data refresh. |
| 4 | NH3 values ~10× lower than EMEP/EEA Guidebook Tier 2 references (Table 3-17) | Open. PC Petrol Hot NH3 at 50 km/h reads ~1.4 mg/km vs ~10-50 mg/km in the Guidebook Tier 2. Affects all PC Petrol rows checked; broader scope not characterised. Currently inert because NH3 is not exposed in the road traffic emissions output pipeline. Deferred to a future data refresh. |

## 5. Refreshing to a newer COPERT release

The OpenALAQS dataset is in a country-aggregated form: per-country values pre-computed at 13 speed bins (10, 20, ..., 130 km/h) with a fixed reference temperature for cold-cycle rows. Newer COPERT releases (e.g. 5.9.1, October 2025) ship their underlying methodology data as per-(category, fuel, segment, technology, Euro standard) polynomial parameters with no country dimension, plus a separate fleet composition layer applied at COPERT software runtime. A refresh therefore involves both ingesting new parameters AND choosing how to produce the country aggregate that the OpenALAQS schema expects.

The expected refresh procedure, when undertaken:

1. **Source authoritative per-country EF aggregates** for the target COPERT
   version. The recommended path is to run the licensed COPERT software
   (Emisia) for each of the 38 country aggregates, with national fleet
   composition inputs, and export per-(category, fuel, Euro standard,
   speed) emission factor tables.
2. **Validate one cell against the COPERT software UI** before bulk
   reformatting, to confirm the export format and units.
3. **Reformat the exports** into the OpenALAQS CSV schema documented in
   §1. Map any new fuels (CNG, LPG, hybrid, PHEV, BEV) and new Euro
   standards (Euro 7, Euro VII) to scope by either (a) extending the
   schema, (b) skipping them for minimal-effort refresh, or (c) handling
   them in a follow-on.
4. **Replace `default_vehicle_ef_copert5.csv`** with the new file.
5. **Run `tools/data_integrity_fixes/sync_csv_into_alaqs_caches.py`** to
   propagate the new data into the seven embedded `.alaqs` caches.
6. **Re-run `tests/test_copert5.py` and `tests/test_database.py`**;
   update expected values in the former where appropriate (numerical
   regressions will need new pinned values with documenting comments).
7. **Re-verify the four data integrity items** above against the new
   dataset. PM10 < PM2.5 and Switzerland 10× should not recur in
   well-formed COPERT 5.9.1 data (Appendix 4 uses a single "PM Exhaust"
   label). EU27/EU28 labelling and NH3 magnitude should be checked
   explicitly.
8. **Update this document** with the new version's provenance facts
   (exact COPERT version, ingest date, fleet composition source).

## 6. Out of scope for this document

Other vehicle / aircraft / GSE emission factor datasets in
`open_alaqs/database/data/` (`default_aircraft_engine_ei.csv`,
`default_aircraft_apu_ef.csv`, `default_aircraft_start_ef.csv`,
`default_helicopter_engine_ei.csv`, `default_gse_emission_factors.csv`,
`default_stationary_*.csv`) are separately maintained and are not part
of the COPERT road traffic data. See `DEPRECATIONS.md` for aircraft
engine EI column-level deprecations.
