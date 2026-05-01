#!/usr/bin/env python3
"""
Regenerate reference outputs used by `test_emission_calculation` —
16 datasets across AIRPORT_A and ANP, covering .gpkg vector-layer
references and .csv tabular references.

WHY THIS EXISTS
---------------
The test's xfail reason from the current tree:

    The feature geometries in current output differ slightly from the
    shipped references due to the ~62% mid-latitude coordinate accuracy
    improvement [from the Grid3D UTM-origin fix + spatial.py B1-B10].
    Fix: regenerate the reference .gpkg files via
    EmissionsQGISVectorLayerOutputModule against the current calculator.

In other words, the shipped references were produced before the rebuild's
spatial fixes and no longer match the (now correct) calculator output.

This script runs the exact same dialog flow the test uses and writes the
resulting outputs (vector layers as .gpkg, tables as .csv) to their
expected file paths. After running, the test's `checkLayersEqual()` and
`compare_text_files()` comparisons pass, and the xfail mark can be
removed.

USAGE
-----
From the repo root:

    QT_QPA_PLATFORM=offscreen python tests/regenerate_emission_calculation_references.py

Then:

    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_emission_calculation.py

The single parametrization `test_emission_calculation` should pass.
The xfail mark on it can then be removed.

WHAT THIS SCRIPT DOES
---------------------
For each of the 16 datasets:
  1. Reads the dataset spec (db_path, inventory_path, pollutant, etc.)
  2. Instantiates `OpenAlaqsResultsAnalysis` with a mocked iface
  3. Sets source_type / pollutant / table_view_type from the spec
  4. Calls `dlg.runOutputModule(OutputModule)` to produce the layer or
     table — the exact flow the test exercises
  5. For `EmissionsQGISVectorLayerOutputModule`: writes the resulting
     QgsVectorLayer to `expected_file_path` as GPKG
  6. For `TableViewWidgetOutputModule`: calls `export_to_csv` to write
     the CSV to `expected_file_path`

IMPORTANT
---------
The script mutates `tests/data/AIRPORT_A/*.gpkg`, `tests/data/ANP/*.gpkg`,
and the two `.csv` reference files in `tests/data/AIRPORT_A/`. Make a
backup of those files before running if you want to diff against the
current state.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root is 1 level up from this file
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from qgis.core import (  # noqa: E402
    QgsCoordinateTransformContext,
    QgsMapLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.testing import start_app  # noqa: E402
from qgis.testing.mocked import get_iface  # noqa: E402

start_app()

# Imports that require QGIS being started
from open_alaqs.core.alaqsdblite import ProjectDatabase  # noqa: E402
from open_alaqs.core.modules.ModuleManager import (  # noqa: E402
    OutputAnalysisModuleRegistry,
)
from open_alaqs.core.modules.TableViewWidgetOutputModule import ViewType  # noqa: E402
from open_alaqs.openalaqs import OpenALAQS  # noqa: E402
from open_alaqs.openalaqsdialog import OpenAlaqsResultsAnalysis  # noqa: E402
from tests.utils import get_data_path  # noqa: E402


# For regeneration we need to write to the SOURCE fixtures in tests/data/,
# not to the tmp copies that tests normally operate on. We therefore build
# paths via `get_data_path()` directly rather than the `get_vector_layer_path()`
# helper that tests use (which calls `get_copy_path()` → `/tmp/`).
def _fixture_path(relative: str) -> str:
    """Return absolute path to a file under tests/data/, for regeneration."""
    return str(get_data_path() / relative)


def build_datasets() -> list[dict]:
    """
    Return the same dataset list as test_emission_calculation.datasets_to_test,
    but with expected_file_path resolved to the source fixtures (not tmp copies).

    Kept in sync with tests/test_emission_calculation.py. If the test's
    list ever changes, update this one in lockstep.
    """
    return [
        # AIRPORT_A
        {
            "title": "AIRPORT_A (Rotterdam, NL) Emission calculation test (CO), vector layer",
            "db_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A.alaqs"),
            "inventory_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "CO",
            "study_start_date": "2025-12-01 06:00:00",
            "study_end_date": "2025-12-03 08:00:00",
            "expected_file_path": _fixture_path("AIRPORT_A/vector_layer_co.gpkg"),
        },
        {
            "title": "AIRPORT_A (Rotterdam, NL) Emission calculation test (PM10), vector layer",
            "db_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A.alaqs"),
            "inventory_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "PM10",
            "study_start_date": "2025-12-01 06:00:00",
            "study_end_date": "2025-12-03 08:00:00",
            "expected_file_path": _fixture_path("AIRPORT_A/vector_layer_pm10.gpkg"),
        },
        {
            "title": "AIRPORT_A (Rotterdam, NL) Emission calculation test (CO), Emissions Table by Aggregation (CSV)",
            "db_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A.alaqs"),
            "inventory_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            "module_name": "TableViewWidgetOutputModule",
            "pollutant": "CO",
            "study_start_date": "2025-12-01 06:00:00",
            "study_end_date": "2025-12-03 08:00:00",
            "expected_file_path": _fixture_path(
                "AIRPORT_A/AIRPORT_A_emissions_table_by_aggregation_co.csv"
            ),
        },
        {
            "title": "AIRPORT_A (Rotterdam, NL) Emission calculation test (PM10), Emissions Table by Grid Cell (CSV)",
            "db_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A.alaqs"),
            "inventory_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            "module_name": "TableViewWidgetOutputModule",
            "pollutant": "PM10",
            "table_view_type": ViewType.BY_GRID_CELL,
            "study_start_date": "2025-12-01 06:00:00",
            "study_end_date": "2025-12-03 08:00:00",
            "expected_file_path": _fixture_path(
                "AIRPORT_A/AIRPORT_A_emissions_table_by_grid_cell_pm10.csv"
            ),
        },
        {
            "title": "AIRPORT_A (Rotterdam, NL) Emission calculation test for Movement Source (CO), vector layer",
            "db_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A.alaqs"),
            "inventory_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "MovementSource",
            "pollutant": "CO",
            "study_start_date": "2025-12-01 06:00:00",
            "study_end_date": "2025-12-03 08:00:00",
            "expected_file_path": _fixture_path(
                "AIRPORT_A/vector_layer_co_movement_source_centroids.gpkg"
            ),
        },
        # ANP — full-aggregate by pollutant
        {
            "title": "ANP - CO emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path("ANP/ANP_vector_layer_co.gpkg"),
        },
        {
            "title": "ANP - PM10 emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "PM10",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path("ANP/ANP_vector_layer_pm10.gpkg"),
        },
        {
            "title": "ANP - NOx emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "NOx",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path("ANP/ANP_vector_layer_nox.gpkg"),
        },
        {
            "title": "ANP - HC emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "HC",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path("ANP/ANP_vector_layer_hc.gpkg"),
        },
        {
            "title": "ANP - SOx emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "SOx",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path("ANP/ANP_vector_layer_sox.gpkg"),
        },
        {
            "title": "ANP - CO2 emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "CO2",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path("ANP/ANP_vector_layer_co2.gpkg"),
        },
        # ANP — per-source-type aggregates (CO only)
        {
            "title": "ANP - MovementSource, CO emissions",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "MovementSource",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path(
                "ANP/ANP_vector_layer_co_movement_source.gpkg"
            ),
        },
        {
            "title": "ANP - AreaSource, CO emissions",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "AreaSource",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path(
                "ANP/ANP_vector_layer_co_area_source.gpkg"
            ),
        },
        {
            "title": "ANP - ParkingSource, CO emissions",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "ParkingSource",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path(
                "ANP/ANP_vector_layer_co_parking_source.gpkg"
            ),
        },
        {
            "title": "ANP - PointSource, CO emissions",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "PointSource",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path(
                "ANP/ANP_vector_layer_co_point_source.gpkg"
            ),
        },
        {
            "title": "ANP - RoadwaySource, CO emissions",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "RoadwaySource",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": _fixture_path(
                "ANP/ANP_vector_layer_co_roadway_source.gpkg"
            ),
        },
    ]


def write_vector_layer_as_gpkg(layer: QgsVectorLayer, out_path: str) -> None:
    """
    Write a QgsVectorLayer to a GeoPackage file.

    If out_path already exists, it is removed first — GPKG writer
    otherwise appends a new layer with a timestamp suffix instead of
    overwriting.
    """
    if Path(out_path).exists():
        Path(out_path).unlink()

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.fileEncoding = "UTF-8"
    # The test loads layers via `QgsVectorLayer("<path>.gpkg|layername=output", ...)`
    # where "output" comes from `get_vector_layer_path(relative, "output")`.
    # We must therefore write the layer inside the GPKG with this exact name,
    # not the file stem, or `layer.isValid()` returns False on the test side.
    opts.layerName = "output"

    res, err_msg = QgsVectorFileWriter.writeAsVectorFormatV2(
        layer, out_path, QgsCoordinateTransformContext(), opts
    )
    if res != 0:
        raise RuntimeError(f"Failed to write {out_path}: {res}, {err_msg}")


def regenerate_one(dataset: dict, plugin: OpenALAQS) -> None:
    """Run a single dataset through the dialog and write its output."""
    title = dataset["title"]
    print(f"\n=== {title} ===")

    # Point the shared ProjectDatabase at this dataset's db
    project_database = ProjectDatabase()
    project_database.path = dataset["db_path"]

    inventory_path = dataset["inventory_path"]
    module_name = dataset["module_name"]
    out_path = dataset["expected_file_path"]

    OutputModule = OutputAnalysisModuleRegistry().get_module(module_name)
    if OutputModule is None:
        raise RuntimeError(f"OutputModule {module_name} not registered")

    dlg = OpenAlaqsResultsAnalysis(plugin.iface)
    dlg.result_file_path_changed(inventory_path)
    dlg.ui.result_file_path.setFilePath(inventory_path)

    if "source_type" in dataset:
        idx = dlg.ui.source_types.findText(dataset["source_type"])
        if idx != -1:
            dlg.ui.source_types.setCurrentIndex(idx)
            print(f"  source type = {dataset['source_type']}")

    # Set pollutant
    poll_idx = dlg.ui.pollutants_names.findText(dataset["pollutant"])
    dlg.ui.pollutants_names.setCurrentIndex(poll_idx)

    # Set table view type for TableViewWidgetOutputModule datasets
    if module_name == "TableViewWidgetOutputModule" and "table_view_type" in dataset:
        from qgis.PyQt import QtWidgets  # local import, only needed here

        tab_bar = dlg.ui.output_modules_tab_widget.tabBar()
        for i in range(dlg.ui.output_modules_tab_widget.count()):
            if tab_bar.tabText(i) == "Emissions table":
                module_config_widget = dlg.ui.output_modules_tab_widget.widget(
                    i
                ).widget()
                combobox = module_config_widget.get_widget("view_type")
                vt_idx = combobox.findText(dataset["table_view_type"].value)
                combobox.setCurrentIndex(vt_idx)
                print(f"  view type = {combobox.currentText()}")
                break

    # Run the calculation + output module — same path as the test
    output_module, res = dlg.runOutputModule(OutputModule)

    # Write the result to the expected file path
    if module_name == "EmissionsQGISVectorLayerOutputModule":
        if not isinstance(res, QgsMapLayer):
            raise RuntimeError(f"Expected QgsMapLayer, got {type(res).__name__}")
        if not isinstance(res, QgsVectorLayer):
            raise RuntimeError(f"Expected QgsVectorLayer, got {type(res).__name__}")
        write_vector_layer_as_gpkg(res, out_path)
        print(f"  wrote GPKG: {out_path}")
    elif module_name == "TableViewWidgetOutputModule":
        # Delete existing so export_to_csv writes a clean file
        if Path(out_path).exists():
            Path(out_path).unlink()
        output_module.export_to_csv(out_path)
        print(f"  wrote CSV: {out_path}")
    else:
        raise RuntimeError(f"Unknown module_name: {module_name}")


def main() -> None:
    """Regenerate all 16 reference files.

    Supports `--start-index N` (0-indexed) to skip already-regenerated
    datasets — useful when a long run is OOM-killed partway and we want
    to resume without re-doing completed work.
    """
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Index of first dataset to process (default 0). Datasets before "
        "this index are skipped — use to resume after partial completion.",
    )
    parser.add_argument(
        "--end-index",
        type=int,
        default=None,
        help="Index of last dataset to process, exclusive (default: all).",
    )
    args = parser.parse_args()

    plugin = OpenALAQS(get_iface())
    try:
        datasets = build_datasets()
        end = args.end_index if args.end_index is not None else len(datasets)
        subset = datasets[args.start_index : end]
        print(
            f"Regenerating datasets [{args.start_index}:{end}] "
            f"({len(subset)} of {len(datasets)} total)..."
        )
        for i, dataset in enumerate(subset, start=args.start_index):
            try:
                print(f"\n[{i}/{len(datasets) - 1}]", end=" ")
                regenerate_one(dataset, plugin)
            except Exception as e:
                print(f"  FAILED: {e}")
                raise
        print("\nDone.")
    finally:
        plugin.unload()


if __name__ == "__main__":
    main()
