# recipe_config.json - parameter reference

A `recipe_config.json` file placed next to the `.alaqs` file is a portable
parameter record. Any orchestrator that runs the standalone can read it to
drive the run; the file convention exists so the parameters used for a
study live alongside the data rather than in a CLI history.

## Files in this folder

- `recipe_config.minimal.json` - a short, real example (the 6 most common
 parameters). Copy this, rename to `recipe_config.json`, edit values, drop
 alongside your `.alaqs`. Done.
- `recipe_config.example.json` - the parameters of the CLI table below
 plus `alaqs_filename` and `clear_output_folders`, with each parameter's
 value followed by a `_<name>` documentation key explaining what it does. The `_`-prefixed keys are
 documentation only; they are ignored at runtime. Use this as a reference,
 then copy the lines you actually want into your real `recipe_config.json`.

## Mapping to the standalone CLI

Every parameter in this file corresponds to a CLI flag on the
`openalaqs_standalone austal` subcommand (a few also on the `aircraft`
subcommand: `--processes`, `--source-dynamics`, `--apply-nox-corrections`,
with `--method` and `--isa-meteo` in place of `--aircraft-method` and
`--use-isa-meteo`):

| `recipe_config.json` key | CLI flag |
| -------------------------- | ------------------------------ |
| `year` | `--year` |
| `include_aircraft` | `--include-aircraft` |
| `aircraft_method` | `--aircraft-method` |
| `use_isa_meteo` | `--use-isa-meteo` |
| `atmosphere_model` | `--atmosphere-model` (5.4.1) |
| `z0` / `d0` / `ha` | `--z0` / `--d0` / `--ha` (AUSTAL config and atmosphere aloft; defaults z0 0.1 m, d0 6 z0, ha 10 m + d0, derived when null) |
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

The `austal` flag `--grid-writer-mode` (default `hybrid`) has no key in
this file. The Dataiku recipe of the Dataiku update package reads three
more keys that are not in it: `grid_writer_mode`, `tag_outputs` and
`alaqs_names` (the last two are described in the recipe's header).

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
 --start 2025-12-01 --end 2025-12-04 \
 --pollutants co,hc,nox,pm10,pm25 \
 --out ./inputs/
```
