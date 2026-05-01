"""
Regression test for the duplicate-layer bug in
`OpenAlaqsResultsAnalysis.handleOutputModuleResult`.

Symptom (reported by user):
  Switching the BFFM2 fuel-flow source dropdown from "trajectory" to
  "mode_anchor" and clicking "Add to map" again leaves the canvas
  rendering the previous result. The new layer is added to the project
  but the old one is not removed, so two layers with the same name
  ("nox Emissions") coexist; the legend shows both and rendering order
  may favour the stale one.

Root cause:
  The replacement loop iterated `self._iface.mapCanvas().layers()`,
  which reports only the layers currently in the canvas's render set.
  Hidden/un-rendered layers slip through. QGIS allows the project to
  hold multiple layers with the same name (layers are keyed by id, not
  name), so the new layer is added alongside the old one.

Fix:
  Iterate `QgsProject.instance().mapLayers()` (project-wide layer
  registry). Catches every existing layer with the matching name
  regardless of canvas visibility.
"""

from pathlib import Path

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
)
from qgis.testing import start_app

start_app()

REPO = Path(__file__).resolve().parents[1]


def _make_layer(name: str) -> QgsVectorLayer:
    return QgsVectorLayer("Polygon?crs=EPSG:3857", name, "memory")


def test_qgis_project_allows_duplicate_layer_names():
    """Sanity check pinning the QGIS behaviour that drives the bug:
    addMapLayer does NOT dedup by name. Two layers with the same name
    coexist in the project. If this assumption ever changes, the fix
    becomes a no-op rather than masking a different problem."""
    proj = QgsProject.instance()
    proj.removeAllMapLayers()

    l1 = _make_layer("nox Emissions")
    l2 = _make_layer("nox Emissions")
    proj.addMapLayer(l1)
    proj.addMapLayer(l2)

    same_named = [
        lyr for lyr in proj.mapLayers().values() if lyr.name() == "nox Emissions"
    ]
    assert len(same_named) == 2, (
        f"QgsProject auto-dedups layers by name (found {len(same_named)} "
        f"matching). The fix in handleOutputModuleResult relies on "
        f"explicit name-based dedup; if QGIS now does it automatically "
        f"the explicit code is redundant."
    )

    proj.removeAllMapLayers()


def test_handle_output_replaces_layer_via_project_registry():
    """End-to-end check: simulate the dialog flow. Add a 'nox Emissions'
    layer to the project (without going through the canvas), then call
    the replacement logic with a new layer of the same name. After the
    call, only the new layer must remain.

    The previous code used mapCanvas().layers() which would have missed
    the un-canvas-bound layer; the fix uses QgsProject.mapLayers() which
    catches it.
    """
    proj = QgsProject.instance()
    proj.removeAllMapLayers()

    # 1. Pre-existing "nox Emissions" layer in the project, NOT added to
    #    any canvas. Models the case where the user toggled visibility
    #    off, or the canvas's render set was filtered for any reason.
    old = _make_layer("nox Emissions")
    proj.addMapLayer(old)
    old_id = old.id()

    # 2. New layer with the same name (e.g., the result of recalculating
    #    with a different bffm2_ff_source).
    new = _make_layer("nox Emissions")
    new_id = new.id()

    # 3. Apply the same logic the production code uses. Inlined here
    #    rather than importing handleOutputModuleResult because that
    #    method also touches the canvas + iface, neither of which is
    #    available in headless tests.
    ids_to_remove = [
        lyr.id() for lyr in proj.mapLayers().values() if lyr.name() == new.name()
    ]
    if ids_to_remove:
        proj.removeMapLayers(ids_to_remove)
    proj.addMapLayers([new])

    # 4. After the swap, exactly one layer with that name must remain,
    #    and it must be the NEW one.
    matching = [
        lyr for lyr in proj.mapLayers().values() if lyr.name() == "nox Emissions"
    ]
    assert len(matching) == 1, (
        f"Expected exactly one 'nox Emissions' layer after swap; "
        f"found {len(matching)}. Project: "
        f"{[(lyr.name(), lyr.id()) for lyr in proj.mapLayers().values()]}"
    )
    assert matching[0].id() == new_id, (
        f"Wrong layer survived the swap: id={matching[0].id()}; "
        f"expected new_id={new_id}, old_id was={old_id}"
    )

    proj.removeAllMapLayers()


def test_replacement_uses_project_mapLayers_not_canvas_layers():
    """Static source check: the replacement loop in openalaqsdialog.py
    must consult QgsProject.instance().mapLayers(), not
    self._iface.mapCanvas().layers(). Catches a regression where a
    future refactor reverts to the canvas-local view and silently
    re-introduces the stale-layer bug."""
    src = (REPO / "open_alaqs" / "openalaqsdialog.py").read_text()

    # Find handleOutputModuleResult body
    needle = "def handleOutputModuleResult(self, output_module: Any, res: Any)"
    start = src.find(needle)
    assert start != -1, "handleOutputModuleResult not found"
    # Take ~3000 chars (function is short); find the next def at column 4
    body = src[start : start + 3000]
    next_def = body.find("\n    def ", 1)
    if next_def != -1:
        body = body[:next_def]

    assert "QgsProject.instance().mapLayers()" in body, (
        "handleOutputModuleResult must use QgsProject.instance().mapLayers() "
        "for name-based dedup. Using mapCanvas().layers() misses hidden / "
        "unbound layers and re-introduces the stale-layer bug."
    )
    # And the canvas-only iteration pattern must NOT appear inside the
    # name-comparison loop. mapCanvas() is still used elsewhere in the
    # function (CRS lookup, refresh) so we look specifically for the
    # iteration pattern that drove the bug.
    assert "for layer in self._iface.mapCanvas().layers():" not in body, (
        "handleOutputModuleResult still iterates mapCanvas().layers() "
        "for layer replacement. This misses hidden layers; switch to "
        "QgsProject.instance().mapLayers().values()."
    )
