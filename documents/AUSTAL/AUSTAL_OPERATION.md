# AUSTAL Dispersion Analysis - Operating Guide

End-to-end walkthrough of the **Calculate Dispersion** dialog, from the QGIS toolbar to a vector layer plotted on the canvas. Covers each numbered section of the dialog in the order a user works through them. For initial AUSTAL installation and `austal.settings` setup, see `AUSTAL.md` in this folder; this guide assumes those are already done.

---

## Where to find the dialog

In QGIS, click the **Calculate Dispersion** button on the OpenALAQS toolbar (icon: `dispersion_model.png`). The dialog opens with five collapsible sections, numbered roughly in execution order.

---

## 1. AUSTAL Executable

The first section, `executableGroupBox`. Tells the plugin which AUSTAL binary to invoke.

- **Field**: `a2k_executable_path`. Use the file picker to point at `austal.exe` (Windows) or `austal` (Linux). The filter only shows files matching that name.
- **Status**: a coloured label below the field reports `Executable Loaded` (green) or `No Executable Loaded` (yellow). Until the label is green, the rest of the dialog produces validation errors when you press Run.
- **Persistence**: the path is saved in `QgsSettings` under `open_alaqs/a2k_executable_path` and restored on next launch, so this step is one-time per machine.
- **AUSTAL Help button**: opens this section's setup documentation (`AUSTAL.md`).

---

## 2. Input File Strategy

The second section, `inputStrategyGroupBox`. Picks where AUSTAL's input files come from. Three radio buttons; pick exactly one.

| Radio | When to use |
|---|---|
| **Use Existing AUSTAL Input Files** | You have a folder with hand-prepared `austal.txt` / `series.dmna` / `zeitreihe.dmna` etc. The plugin will only run AUSTAL against that folder; it will not generate anything. |
| **Generate AUSTAL Input Files from OpenALAQS Emission Inventory File** | You have an OpenALAQS `*_out.alaqs` file from a prior emissions inventory run. The plugin generates the AUSTAL inputs from it (emissions + meteo + grid) and then runs AUSTAL. |
| **Generate AUSTAL Input Files from CSV** | You have an emissions CSV and a meteo CSV from outside OpenALAQS. The plugin assembles AUSTAL inputs from those two files. |

Each radio reveals its own input fields below. The status label (`existingFilesStatusLabel`, `alaqsGenerationStatusLabel`, or `external_files_feedback`) reports what's still missing - work through the gaps until it goes green.

For the two "Generate" modes, the plugin writes the resulting AUSTAL input files into the **work directory** you specify, then proceeds to step 3 in the same folder.

### Datetime range

Both Generate modes show start/end datetime pickers. They default to a placeholder value but auto-populate to the inventory's actual time range as soon as you select the source file. Pick the slice of the inventory you want to disperse - this is a subset selection, not a recompute.

---

## Grid Configuration & Grid Management

Two grid sections appear inside step 2. They are **separate**:

### Calculation Configuration / Grid Management (`gridManagementGroupBox`)
Sets the receptor grid that AUSTAL will compute concentrations on. Either:
- pull it from an OpenALAQS `*_out.alaqs` file (the plugin reads `grid_3d_definition`), or
- type it manually in the **Grid Details** sub-section (x_cells, y_cells, x_resolution, y_resolution, ref lat/lon).

The grid you set here is the one written into AUSTAL's input file. Cell size is in **true ground metres**: the plugin builds the grid in local UTM, so a 100 m cell here is 100 m on the ground (modulo a ~2% mercator-projection effect when the grid is later reprojected for QGIS display).

The status panel below the inputs reports the active grid: number of cells, resolution, and reference lat/lon.

### Grid Management for visualisation (`alaqsGridGroupBox`, inside section 4)
A **second** grid pointer used **only for plotting**. When AUSTAL writes its result `.dmna` files, they reference cell indices, not lat/lon. To draw them on the map you also need a grid definition. This second selector lets you pick an `*_out.alaqs` or grid CSV that matches the run. In the common case where you generated inputs from an `*_out.alaqs`, point both sections at the same file.

There's also a **Save Grid as CSV** button (`saveGridCsvBtn`) that writes the current grid out to a CSV, and an **Update File** button (`updateFileBtn`) that re-reads the grid file if you've edited it externally.

---

## 3. Execution

The third section, `runGroupBox`. One button: **Run AUSTAL** (`RunA2K`).

When you click it, the plugin:
1. Validates that all upstream sections are green (executable, input strategy, grid). If anything is missing, a popup names the gap and the run is cancelled.
2. Updates `executionStatusLabel` to `Running AUSTAL...` and disables the button.
3. Spawns the AUSTAL executable as a subprocess in the work directory you configured. AUSTAL processes the inputs and writes its results (a `.dmna` file per pollutant per averaging period) into a sub-folder of the work directory.
4. On exit, parses the AUSTAL log; success makes the status label green, any non-zero exit code shows the AUSTAL error verbatim.

AUSTAL is single-threaded and CPU-bound; even modest grids take several minutes to a few hours. The QGIS UI stays responsive (the subprocess runs in the background) but you cannot start a second run from the same dialog until the first finishes.

---

## 4. Result Visualisation

The fourth section, `visualisationGroupBox`. Three buttons that all read from the **Results Directory** field (`resultsWorkDirectoryPath`).

The Results Directory is auto-set to the work directory after a successful run. You can also point it at any other AUSTAL output folder via the **Load Existing Results** sub-section, which is how you visualise a run that finished outside this session.

| Button | What it does |
|---|---|
| **ResultsTable** | Opens a tabular view of the per-pollutant per-time-step grid totals. No grid required - reads the `.dmna` headers directly. |
| **VisualiseResults** | Calls `QGISVectorLayerDispersionModule`. Builds a polygon vector layer (one feature per grid cell, attribute = concentration) and adds it to the QGIS canvas. **Requires the visualisation grid** (the second grid section) to be set. |
| **PlotTimeSeries** | Calls `TimeSeriesDispersionModule`. Plots concentration-vs-time at a single point (or averaged over the grid) in a popup chart. |

The status label `visualisationStatusLabel` greys these buttons out until their preconditions are met (results directory exists, grid loaded for the polygon button, etc.). Hover the label for the specific reason.

### About the vector layer plot

The polygon layer is rendered in EPSG:3857 (web mercator) so it stacks correctly with QGIS basemaps. Each cell's geometry comes from the grid you selected in the visualisation grid section; each cell's attribute value comes from the corresponding `.dmna` file. Default styling is a graduated colour ramp on the concentration field, but the layer is a normal `QgsVectorLayer` - you can edit its symbology, classify by different fields if multiple pollutants are loaded, or export it to GeoPackage from the QGIS layers panel.

---

## Typical end-to-end session

1. Open **Calculate Dispersion**.
2. **§1**: file-pick the AUSTAL executable (one-time per machine; it persists).
3. **§2**: pick a strategy. Most common: select **Generate from OpenALAQS Emission Inventory File**, browse to your `*_out.alaqs`, set the work directory and the time window.
4. **§2 / Grid Configuration**: confirm the grid was inherited from the inventory file. If not, fill in the details manually.
5. **§3**: click **Run AUSTAL**. Wait for green status.
6. **§4 / Grid Management**: point at the same `*_out.alaqs` so the plot has a grid.
7. **§4**: click **VisualiseResults**. The polygon layer appears on the QGIS canvas.

---

## Common failure modes

- **`No Executable Loaded` even after picking the file** - the file picker doesn't accept anything not named `austal.exe` or `austal`. If you have `austal_3.3.exe`, rename it.
- **Run completes but the `.dmna` files are missing** - check that the AUSTAL installation has the `austal.settings` file from this OpenALAQS folder copied in. The default `austal.settings` shipped with AUSTAL writes to a different output schema and the plugin won't find the results.
- **`VisualiseResults` button stays disabled** - the visualisation grid (`alaqsGridGroupBox`) is unset. The execution grid and the visualisation grid are independent fields; both must be filled, even when they point at the same file.
- **Polygons appear in the wrong place on the map** - the visualisation grid does not match the run's grid. AUSTAL output cells are indexed; if you give the plotter a different reference lat/lon or cell size, it will draw cells at the wrong coordinates. Re-select the same `*_out.alaqs` for both grid sections.
- **Run takes hours and you're not sure it's progressing** - check the AUSTAL log file in the work directory. AUSTAL writes progress to `austal.log` (or similar) as it iterates over time steps; if the file is growing, the run is alive.

---

## Files written by a successful run

In the work directory after a green run:

```
work/
├── austal.txt              # input file the plugin generated (or yours, if "use existing")
├── series.dmna             # time-resolved emission series
├── zeitreihe.dmna          # meteo time series (only if generated by plugin)
├── work/                   # AUSTAL's own output sub-folder
│   ├── austal.log          # run log
│   ├── pollutant-001.dmna  # per-pollutant per-period grid result
│   ├── pollutant-002.dmna
│   └── ...
└── meta.txt                # OpenALAQS-emitted run metadata
```

The visualisation buttons read from `work/` (the inner one). If you move the folder, point the Results Directory at the new location and the same buttons will still work.
