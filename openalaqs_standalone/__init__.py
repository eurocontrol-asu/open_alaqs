"""
openalaqs_standalone: a QGIS-free OpenALAQS emission calculator.

SCOPE: this package has two halves.

  Stationary sources (the original half): an ALAQS -> AUSTAL adapter.
  The stationary compute_* modules read pre-computed emission factors
  from the .alaqs file (written there by an upstream OpenALAQS plugin
  run) and spread them across the calendar year (8760 or 8784 hours)
  using activity profiles. They do NOT recompute COPERT5 or apply EF
  adjustments; the .alaqs file must have been produced by an upstream
  plugin run including any required patches (e.g. the PR2 cold-start
  fix).

  Aircraft sources (the Phase A0 half): a real emission calculator.
  The aircraft modules compute per-movement emissions from the
  trajectory profiles, engine emission indices, and BFFM2 ambient
  corrections in the .alaqs file -- they do not spread a pre-computed
  factor, they run the CAEP14 emission pipeline. Validated against the
  reference implementation and the plugin-output CSVs in validation/.

The .alaqs file is a SpatiaLite database containing source geometries,
emission factors, temporal profiles, trajectories, meteo data, and
study metadata. Geometry is read as raw WKB; the package never loads
the mod_spatialite native extension.

Stationary modules:
    extract_sources    SpatiaLite -> sources.parquet (all source types)
    compute_road       roadways:  spreads pre-computed g/km
    compute_parking    parking:   spreads pre-computed g/vh
    compute_point      stationary point sources: spreads kg/k * ops_year
    compute_area       area sources:             spreads kg/unit * unit_year

Aircraft modules (Phase A0, A2):
    geometry           QGIS-free spatial primitives + WKB blob reader
    movements          .alaqs database accessors for the aircraft pipeline
    compute_aircraft   fixed-wing per-movement emissions, 3 methods
    compute_helicopter FOCA helicopter per-movement emissions
    compute_gate_movements  per-movement gate (GSE + GPU) emissions,
                       driven by the movements and the gate profiles
                       (Phase A2). Folded into each movement's
                       total_em_kg and also kept as a separate
                       gate_em_kg field.
    compute_movements  dispatch + study-level driver (per-movement
                       totals, including the folded-in gate emissions)

Distribution and output (Phases A3, A5):
    distribute         per-(time bucket, grid cell) emission distribution
                       (the "(c)" output); hourly or sub-hour in time,
                       per grid cell in space. Sub-hour is for general
                       emission-results output, never for AUSTAL.
    austal_aircraft    turns the gridded aircraft emissions into the
                       emissions.parquet + sources.parquet pair the
                       austal_prep package consumes, one synthetic area
                       source per occupied grid cell. Always hourly.
    parallel           a multiprocessing driver for the movement
                       compute (Phase A4): runs the same per-movement
                       work as compute_all_movements across a process
                       pool, with results bit-identical to the serial
                       driver. A drop-in replacement for studies with
                       many movements.

Utilities (study-independent):
    adapt_meteo        OpenALAQS meteo -> standard meteo.csv
    adapt_receptors    CIMLK / RD receptors -> UTM receptors.csv
    make_config        scaffold a config.json from .alaqs metadata + grid

Entry points:
    cli / __main__     `python -m openalaqs_standalone <command>`:
                       `aircraft` runs the per-movement aircraft core
                       (including gate emissions) and, with
                       --austal-out, writes the AUSTAL aircraft input
                       pair (Phase A5); with --processes N, runs the
                       movement compute across N worker processes
                       (Phase A4). `austal` builds the six-folder
                       input structure for stationary sources, and
                       writes per-pollutant gpkgs to
                       <out>/inventory_gpkgs/.
    orchestrate        the austal_prep pipeline driver (the `austal`
                       command); also importable as a Python function
                       for embedding in external pipelines. With
                       --include-aircraft it folds the
                       aircraft movement emissions into the same
                       sources.parquet and emissions.parquet as the
                       stationary sources, so one austal_prep run
                       covers the whole study.

The phase plan A0-A5 is complete: the aircraft pipeline runs
end-to-end, the movement compute parallelises, the AUSTAL and
GeoPackage outputs exist, and a single `austal --include-aircraft`
run produces the combined stationary + aircraft AUSTAL input.
"""

__version__ = "0.9.0"
