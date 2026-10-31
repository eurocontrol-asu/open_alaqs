# Database schema deprecations

This document tracks fields in `database/data/*.csv` that are retained for
compatibility but are unused at runtime. They are scheduled for removal in
a future schema-v2 migration.

## default_aircraft_engine_ei.csv: 12 of 37 columns deprecated

Columns dead at emissions-calculation runtime (populated by migration scripts,
never read by the calculation engine), except `fuel_type`, which selects the
SOx default (see the table):

| Column | Reason | Kept for |
|---|---|---|
| `coolant` | Pass-through in Engine.py, never consumed | Round-trip to user exports |
| `combustion_technology` | Pass-through only | Round-trip to user exports |
| `technology_age` | Pass-through only | Round-trip to user exports |
| `eng_type` | Only read by `update_default_aircraft_engine_ei_csv.py` migration | Migration tooling |
| `bpr` (bypass ratio) | Only read by migration script | Migration tooling |
| `remark` | Only written by migration scripts | Manual annotation |
| `smoke_number` | Stored in default-dict, never read | ICAO EEDB contract |
| `smoke_number_maximum` | Stored, never read | ICAO EEDB contract |
| `status` | Zero runtime references | Unused |
| `engine_name_type` | Populated by migration, never read | Migration tooling |
| `fuel_type` | Read: selects the SOx default (AvGas or jet fuel) when `sox_ei` is 0 or empty (`Engine.py`, `fuel_sulphur.sox_ei_g_kg`); the shipped CSV has `sox_ei` set in every row | SOx default for user tables without `sox_ei` |
| `manufacturer` | Engine table pass-through; the aircraft-table version is what's actually used | Duplicate of aircraft-table field |

**Impact**: 11 of 37 columns unread, plus `fuel_type` read only for the SOx
default. Removing the 12 shrinks the CSV by ~7% (about 13% with `nvpm_ei`) and
eliminates per-row `setObject` overhead.

## Additional finding: `nvpm_ei` redundancy

`nvpm_ei` is the 13th underutilised column but sits in a different category:
not deprecated, just redundant.

- `nvpm_ei` and `pm10_nonvol` are numerically identical in EEDB (both are the
  non-volatile PM mass emission index, in g/kg).
- 3692 of 3692 rows in ANP_out.alaqs have non-null `nvpm_ei`.
- `nvpm_ei` is declared in the schema dict, marked DEPRECATED
  (column list of `EngineEmissionIndicesDatabase.__init__` in `EngineDatabases.py`), but no calculation reads it.
- But production code reads the non-volatile PM mass EI via
  `ei_.getObject("nvpm_g_kg")`, and the `key_mapping` in `Engine.py` (`EngineEmissionIndex`)
  remaps `nvpm_g_kg` to the DB column `pm10_nonvol`. So the MEEM V1/V2 call
  path (`Engine._meem_v1`) gets the right value via `pm10_nonvol`.

**Conclusion**: no runtime impact today. The column is a CSV-export convenience
and an ICAO EEDB round-trip convenience. When schema v2 lands, the choice is
either drop `nvpm_ei` and keep `pm10_nonvol` as the single source of truth, or
drop `pm10_nonvol` and keep `nvpm_ei` (matches
ICAO EEDB 2021+ nomenclature). Current recommendation: drop `pm10_nonvol` and
keep `nvpm_ei` to align with ICAO EEDB, but this is a naming choice that
doesn't affect any calculation.

**Migration plan**:
1. schema-v1 (current): mark deprecated in `EngineDatabases.py`, document here.
2. schema-v2 (future release):
   - Drop columns from `EngineDatabases.py` schema dict:
     * all 12 deprecated columns and `nvpm_ei` (annotated DEPRECATED in the
       current schema, column list of `EngineEmissionIndicesDatabase.__init__`)
   - Regenerate `default_aircraft_engine_ei.csv` without these 13 fields (24 cols remaining).
   - Resolve the `nvpm_ei` vs `pm10_nonvol` redundancy (see the nvpm_ei
     finding above). Recommended: keep `nvpm_ei`, drop `pm10_nonvol`, update
     the `Engine.py` `key_mapping` from `"nvpm_g_kg": "pm10_nonvol"` to
     `"nvpm_g_kg": "nvpm_ei"`.
   - Add a one-shot `.alaqs` file migration that rewrites the
     `default_aircraft_engine_ei` table in-place when an old-schema file is
     opened. SQLite doesn't support `ALTER TABLE DROP COLUMN` before 3.35, so
     the migration must be `CREATE TABLE tmp; INSERT ... SELECT <new cols>;
     DROP old; RENAME tmp`.
   - Version-stamp the output files so downstream tools can detect schema.
     Proposed: write `PRAGMA user_version = 2` on migrated files.
   - Update the 14 tracked `.alaqs` files that carry the table similarly. Regenerate any
     reference outputs whose numeric values shift (none expected with the
     shipped data: the dropped columns are runtime-dead except `fuel_type`,
     whose SOx default is not used where `sox_ei` is set).

**Schema v2 entry points** (for the future implementer):
- Touch points in Python: `EngineDatabases.py` (schema dict), `Engine.py`
  (`key_mapping` if the nvpm rename is adopted, and the pass-through of
  coolant/combustion_technology/technology_age next to it).
- Touch points in data: `database/data/default_aircraft_engine_ei.csv`,
  the 14 tracked `.alaqs` files that carry the table, possibly the
  `open_alaqs/core/templates/inventory.alaqs` generated by
  `tools/template_build/generate_templates.py`.
- Touch points in docs: this file.

**Why defer**:
- No runtime impact from current state (verified). The 12 deprecated columns
  are unread, read only by migration scripts, or (`fuel_type`) read only for
  the SOx default when `sox_ei` is 0 or empty; `nvpm_ei` data flows
  through `pm10_nonvol` via Engine.py key_mapping.
- Schema v2 is a breaking change for external tools that consume .alaqs
  files. Shipping it should be coordinated with a release that already
  introduces other breaking changes, to avoid forward-compat churn for no
  immediate benefit.

## Related schema notes

- The CSVs in `database/data/` are the source of truth, populated externally
  and shipped with the code; the repository has no pipeline to regenerate
  them.
- The table `default_helicopter_engine_ei` is not part of the schema.
  Helicopters use `default_helicopter` and `default_helicopter_engines` with
  the FOCA 2015 LTO computation (`open_alaqs/core/tools/foca_heli.py`). For a
  study that still has the old table, pass `--drop-extra-tables` to
  `scripts/migrate_alaqs.py` to drop it, and
  `--refresh-reference-data --refresh-include-user-extensible` (or
  `--refresh-tables default_helicopter,default_helicopter_engines`) to fill
  the new tables from the CSVs. Without the refresh, Phase 1 creates them
  empty (`scripts/migrate_alaqs.py`: Phase 1 in the module docstring,
  `USER_EXTENSIBLE_REFRESH_TABLES`).
