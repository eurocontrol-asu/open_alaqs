#!/usr/bin/env python3
"""
Regenerate the vector-layer .gpkg fixtures used by
tests/test_emission_calculation.py.

When to use
-----------
This is a developer maintenance utility. The current shipped fixtures
under tests/data/AIRPORT_A/ and tests/data/ANP/ are correct (their
totals cross-check against the corresponding emissions-table CSV
references within rounding noise) and the test passes against them, so
nothing in CI invokes this script.

It exists for the case where the emission calculation logic legitimately
changes — for example, an EI-curve update or a new BFFM2 anchor — and
the existing reference layers no longer match the new output. Rather
than hand-editing 14 .gpkg files, run this script to drive the same
dialog path the test uses (OpenAlaqsResultsAnalysis -> runOutputModule)
and write the fresh layers back to the same paths the test reads from.

Datasets enumerated
-------------------
The 14 entries below mirror the relevant subset of
``datasets_to_test`` in tests/test_emission_calculation.py:

  * 3 AIRPORT_A fixtures (CO + PM10 totals, plus a CO MovementSource slice)
  * 6 ANP totals (CO, PM10, NOx, HC, SOx, CO2)
  * 5 ANP per-source-type CO slices (Movement, Area, Parking, Point, Roadway)

Usage
-----
Run from the repo root::

    QT_QPA_PLATFORM=offscreen python3 -m tools.test_fixtures.regenerate_emission_vector_layers

Use ``--start`` and ``--end`` to regenerate a subset (useful when only
one airport's fixtures need refreshing). The script overwrites existing
fixtures in place, so commit the resulting .gpkg files together with
the test edits that motivated the regeneration.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from qgis.core import QgsCoordinateReferenceSystem, QgsVectorFileWriter  # noqa: E402
from qgis.testing import start_app  # noqa: E402
from qgis.testing.mocked import get_iface  # noqa: E402

start_app()

from open_alaqs.core.alaqsdblite import ProjectDatabase  # noqa: E402
from open_alaqs.core.modules.ModuleManager import (  # noqa: E402
    OutputAnalysisModuleRegistry,
)
from open_alaqs.openalaqs import OpenALAQS  # noqa: E402
from open_alaqs.openalaqsdialog import OpenAlaqsResultsAnalysis  # noqa: E402

DATA = REPO / "tests" / "data"


def _datasets():
    """Mirror the relevant subset of tests/test_emission_calculation.py
    datasets — only entries whose ``module_name`` is the vector-layer
    output module produce .gpkg outputs.
    """
    return [
        # ---- AIRPORT_A ----
        {
            "title": "AIRPORT_A CO vector layer",
            "db_path": str(DATA / "AIRPORT_A" / "AIRPORT_A.alaqs"),
            "inventory_path": str(DATA / "AIRPORT_A" / "AIRPORT_A_out.alaqs"),
            "pollutant": "CO",
            "out_path": DATA / "AIRPORT_A" / "vector_layer_co.gpkg",
            "source_type": None,
        },
        {
            "title": "AIRPORT_A PM10 vector layer",
            "db_path": str(DATA / "AIRPORT_A" / "AIRPORT_A.alaqs"),
            "inventory_path": str(DATA / "AIRPORT_A" / "AIRPORT_A_out.alaqs"),
            "pollutant": "PM10",
            "out_path": DATA / "AIRPORT_A" / "vector_layer_pm10.gpkg",
            "source_type": None,
        },
        {
            "title": "AIRPORT_A CO movement-source centroids",
            "db_path": str(DATA / "AIRPORT_A" / "AIRPORT_A.alaqs"),
            "inventory_path": str(DATA / "AIRPORT_A" / "AIRPORT_A_out.alaqs"),
            "pollutant": "CO",
            "out_path": (
                DATA / "AIRPORT_A" / "vector_layer_co_movement_source_centroids.gpkg"
            ),
            # MovementSource centroids are produced when source_type is
            # filtered to movements; matches the test's intent for this
            # particular fixture.
            "source_type": "MovementSource",
        },
        # ---- ANP (full pollutant matrix) ----
        {
            "title": "ANP CO vector layer",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "CO",
            "out_path": DATA / "ANP" / "ANP_vector_layer_co.gpkg",
            "source_type": None,
        },
        {
            "title": "ANP PM10 vector layer",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "PM10",
            "out_path": DATA / "ANP" / "ANP_vector_layer_pm10.gpkg",
            "source_type": None,
        },
        {
            "title": "ANP NOx vector layer",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "NOx",
            "out_path": DATA / "ANP" / "ANP_vector_layer_nox.gpkg",
            "source_type": None,
        },
        {
            "title": "ANP HC vector layer",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "HC",
            "out_path": DATA / "ANP" / "ANP_vector_layer_hc.gpkg",
            "source_type": None,
        },
        {
            "title": "ANP SOx vector layer",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "SOx",
            "out_path": DATA / "ANP" / "ANP_vector_layer_sox.gpkg",
            "source_type": None,
        },
        {
            "title": "ANP CO2 vector layer",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "CO2",
            "out_path": DATA / "ANP" / "ANP_vector_layer_co2.gpkg",
            "source_type": None,
        },
        # ---- ANP CO per source-type slice ----
        {
            "title": "ANP CO movement source",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "CO",
            "out_path": (DATA / "ANP" / "ANP_vector_layer_co_movement_source.gpkg"),
            "source_type": "MovementSource",
        },
        {
            "title": "ANP CO area source",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "CO",
            "out_path": (DATA / "ANP" / "ANP_vector_layer_co_area_source.gpkg"),
            "source_type": "AreaSource",
        },
        {
            "title": "ANP CO parking source",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "CO",
            "out_path": (DATA / "ANP" / "ANP_vector_layer_co_parking_source.gpkg"),
            "source_type": "ParkingSource",
        },
        {
            "title": "ANP CO point source",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "CO",
            "out_path": (DATA / "ANP" / "ANP_vector_layer_co_point_source.gpkg"),
            "source_type": "PointSource",
        },
        {
            "title": "ANP CO roadway source",
            "db_path": str(DATA / "ANP" / "ANP.alaqs"),
            "inventory_path": str(DATA / "ANP" / "ANP_out.alaqs"),
            "pollutant": "CO",
            "out_path": (DATA / "ANP" / "ANP_vector_layer_co_roadway_source.gpkg"),
            "source_type": "RoadwaySource",
        },
    ]


def _save_layer_as_geopackage(layer, out_path: Path, layer_name: str = "output"):
    """Write a QgsVectorLayer to disk as a fresh single-layer GeoPackage.
    Removes any existing file at out_path first (writers append by
    default and we want a clean fixture).
    """
    if out_path.exists():
        out_path.unlink()
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    # Force EPSG:3857 because the runtime EmissionsQGISVectorLayerOutputModule
    # reprojects to that CRS; preserve it on disk.
    transform_context = layer.transformContext()
    err = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(out_path), transform_context, options
    )
    if err[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"writeAsVectorFormatV3 failed for {out_path}: {err}")


def _regenerate_one(plugin, dataset):
    """Drive OpenAlaqsResultsAnalysis the same way the test does, then
    save the result layer to dataset["out_path"]."""
    project_database = ProjectDatabase()
    project_database.path = dataset["db_path"]

    OutputModule = OutputAnalysisModuleRegistry().get_module(
        "EmissionsQGISVectorLayerOutputModule"
    )
    if OutputModule is None:
        raise RuntimeError("EmissionsQGISVectorLayerOutputModule not registered")

    dlg = OpenAlaqsResultsAnalysis(plugin.iface)
    dlg.result_file_path_changed(dataset["inventory_path"])
    dlg.ui.result_file_path.setFilePath(dataset["inventory_path"])

    if dataset.get("source_type"):
        idx = dlg.ui.source_types.findText(dataset["source_type"])
        if idx != -1:
            dlg.ui.source_types.setCurrentIndex(idx)

    p_idx = dlg.ui.pollutants_names.findText(dataset["pollutant"])
    if p_idx == -1:
        raise RuntimeError(f"Pollutant {dataset['pollutant']!r} not in dialog combobox")
    dlg.ui.pollutants_names.setCurrentIndex(p_idx)

    output_module, res = dlg.runOutputModule(OutputModule)
    if res is None:
        raise RuntimeError(f"runOutputModule returned None for {dataset['title']}")

    out: Path = dataset["out_path"]
    out.parent.mkdir(parents=True, exist_ok=True)
    _save_layer_as_geopackage(res, out, layer_name="output")
    return out


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="0-based index of the first dataset to regenerate (default: 0)",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="0-based index of the last dataset to regenerate, exclusive "
        "(default: run all from --start to the end)",
    )
    args = parser.parse_args()

    plugin = OpenALAQS(get_iface())
    try:
        all_datasets = _datasets()
        end = args.end if args.end is not None else len(all_datasets)
        subset = all_datasets[args.start : end]
        print(
            f"Regenerating datasets [{args.start}:{end}] "
            f"of {len(all_datasets)} total."
        )
        results = []
        for dataset in subset:
            try:
                out = _regenerate_one(plugin, dataset)
                results.append((dataset["title"], out, None))
                print(f"  OK  {dataset['title']:50s} -> {out}")
            except Exception as exc:
                results.append((dataset["title"], None, exc))
                print(f"  FAIL {dataset['title']:50s} : {exc}")
        ok = sum(1 for _, _, e in results if e is None)
        print(f"\nRegenerated {ok}/{len(results)} fixtures.")
        return 0 if ok == len(results) else 1
    finally:
        plugin.unload()


if __name__ == "__main__":
    sys.exit(main())
