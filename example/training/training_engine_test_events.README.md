# training_engine_test_events.csv

Sample CSV of engine test events (run-ups) for the engine-test-site workflow.

## What it demonstrates

Five events on a single test-pad area source (`TESTPAD_A`), covering both
required and optional columns, both twin- and single-engine setups, and
implicit- and explicit-engine cases:

| Row | Aircraft | Engine (uid → default) | `engine_count` | Modes exercised |
|-----|----------|------------------------|----------------|-----------------|
| 1   | C25C     | aircraft default       | aircraft default (=2) | TX, CL |
| 2   | PC24     | aircraft default       | aircraft default (=2) | TX, AP |
| 3   | C25C     | aircraft default       | 2 explicit     | TX, AP, CL |
| 4   | PC24     | aircraft default       | 1 explicit     | TX, AP, CL |
| 5   | C25C     | aircraft default       | aircraft default (=2) | TX, AP, CL, TO |

Rows 1, 2, and 5 leave `engine_count` empty — the compute path falls back
to `default_aircraft.engine_count` for the aircraft type. Rows 3 and 4
show the explicit override.

Every row leaves `engine_uid` empty; the compute path falls back to the
aircraft's default engine (from `default_aircraft.engine`).

## How to load

1. Migrate the training study if it predates engine-test-site support:
   ```
   python scripts/migrate_alaqs.py example/training/training.alaqs
   ```
2. In QGIS, open `example/training/training.alaqs`. Create an area source
   named `TESTPAD_A` at the desired location, or edit an existing area
   source and rename its `source_id` to `TESTPAD_A`.
3. Tick the **Engine test site** checkbox on the source form. The rate
   fields on the Emissions tab and the Profiles combo boxes gray out.
4. Click **Load engine test events CSV...**. Browse to this file, review
   the validation summary (5 valid rows, 0 errors, 0 warnings expected),
   click Apply.
5. Save the source form (OK).
6. Regenerate the emission inventory. In Results Analysis, select
   `EngineTestSource` and `TESTPAD_A` to inspect per-hour emissions.
   Non-zero hours: 2025-01-15 09:00, 2025-01-15 10:00, 2025-01-16 08:00,
   2025-02-03 11:00, 2025-02-03 14:00.

## CSV format quick reference

Required columns: `source_id`, `start_datetime`, `end_datetime`,
`aircraft_type`.

Optional columns: `test_id`, `engine_uid`, `engine_count`, `t_TX_s`,
`t_AP_s`, `t_CL_s`, `t_TO_s`, `instudy`.

Datetimes in ISO-8601 (`YYYY-MM-DDTHH:MM:SS`). Mode times in seconds per
engine. Empty `engine_uid` / `engine_count` fall back to the aircraft's
defaults. See `documents/USER_GUIDE.md` §Engine test sites for the full
specification.

## Adapting to a different year

If the study's inventory period is not 2025, update the dates via SQL
or edit the CSV before loading:

```
python -c "
import sqlite3
c = sqlite3.connect('training.alaqs')
c.execute(\"UPDATE engine_test_events SET start_datetime = REPLACE(start_datetime, '2025-', '2026-'), end_datetime = REPLACE(end_datetime, '2025-', '2026-') WHERE source_id='TESTPAD_A'\")
c.commit()
"
```

Events dated outside the inventory period contribute zero to the
inventory (no overlap with any inventory hour).
