# recipe_config.json - parameter reference

A `recipe_config.json` file placed next to the `.alaqs` file is a portable
parameter record. Any orchestrator that runs the standalone can read it to
drive the run; the file convention exists so the parameters used for a
study live alongside the data rather than in a CLI history.

## Files in this folder

- `recipe_config.minimal.json` - a short, real example (the 6 most common
 parameters). Copy this, rename to `recipe_config.json`, edit values, drop
 alongside your `.alaqs`. Done.
- `recipe_config.example.json` - every parameter the orchestrator
 understands, with each parameter's value followed by a `_<name>`
 documentation key explaining what it does. The `_`-prefixed keys are
 documentation only; they are ignored at runtime. Use this as a reference,
 then copy the lines you actually want into your real `recipe_config.json`.

## Mapping to the standalone CLI

Every parameter in this file corresponds to a CLI flag on the
`openalaqs_standalone austal` subcommand (and most also on the
`openalaqs_standalone aircraft` subcommand):

| `recipe_config.json` key | CLI flag |
| -------------------------- | ------------------------------ |
| `year` | `--year` |
| `include_aircraft` | `--include-aircraft` |
| `aircraft_method` | `--aircraft-method` |
| `use_isa_meteo` | `--use-isa-meteo` |
| `apply_nox_corrections` | `--apply-nox-corrections` |
| `source_dynamics` | `--source-dynamics` |
| `pollutants` | `--pollutants` |
| `start` / `end` | `--start` / `--end` |
| `processes` | `--processes` |
| `meteo_year_shift` | `--meteo-year-shift` |
| `receptor_source_epsg` | `--receptor-source-epsg` |
| `receptor_target_epsg` | `--receptor-target-epsg` |
| `receptor_name_col` | `--receptor-name-col` |
| `receptor_x_col` | `--receptor-x-col` |
| `receptor_y_col` | `--receptor-y-col` |
| `title` | `--title` |
| `qs` | `--qs` |
| `grid_size` | `--grid-size` (DEPRECATED) |
| `grid_step` | `--grid-step` (DEPRECATED) |

Two keys have no CLI equivalent and are honoured only by external
orchestrators that manage their own input / output staging:

| Key | What it does |
| ---------------------- | ----------------------------------------------------------------------- |
| `alaqs_filename` | Picks one `.alaqs` from a folder containing several |
| `clear_output_folders` | Empties pre-existing output folders before writing (no-op for the CLI) |

Running the standalone from a terminal? Skip the JSON and pass the flags
directly:

```bash
python -m openalaqs_standalone austal training_out.alaqs \
 --year 2025 --include-aircraft --aircraft-method bymode \
 --apply-nox-corrections --processes 8 \
 --start 2025-07-17 --end 2025-07-23 \
 --pollutants co,hc,nox,pm10,pm25 \
 --out ./inputs/
```
