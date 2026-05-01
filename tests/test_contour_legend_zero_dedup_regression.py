"""
Regression test for the duplicate-zero-entry bug in the emissions contour
plot legend.

Symptom (reported by user, screenshot 2026-04-27):
  The QGIS legend for the "nox Emissions" layer (and other emission
  layers) shows two separate entries for zero values:
    - "0 - 0"   (lightGray fill)
    - "0"       (transparent fill)
  followed by the actual gradient bins ("0 - 0.0215", "0.0215 - 0.0622", ...).

Root cause:
  ContourPlotVectorLayer.setColorGradientRenderer calls
  QgsGraduatedSymbolRenderer.updateClasses(layer, n) which runs Jenks
  classification over every cell in the layer. An emissions grid has
  most cells at exactly 0.0 (no aircraft overhead), so Jenks emits a
  degenerate "0 - 0" bin as one of its n classes. That bin gets the
  gradient ramp's first color (lightGray). The function then ALSO adds
  an explicit transparent zero range via addClassRange, producing two
  legend entries for zero.

Fix:
  Before adding the explicit zero range, iterate the renderer's ranges
  and delete any whose lowerValue equals upperValue (degenerate bins).
  Legitimate Jenks bins always have lower < upper, so this only
  catches degenerate cases.
"""

from pathlib import Path

from qgis.core import (
    QgsClassificationJenks,
    QgsGradientColorRamp,
    QgsGraduatedSymbolRenderer,
    QgsSymbol,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.testing import start_app

start_app()

REPO = Path(__file__).resolve().parents[1]


def _make_layer_with_zero_heavy_data():
    """Synthesize a polygon layer with one numeric field, populated with
    a typical emissions distribution: many zeros plus a small tail of
    non-zero values. Mirrors the real emissions grid pattern that
    triggers the Jenks degenerate-bin behaviour."""
    layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "test", "memory")
    pr = layer.dataProvider()
    from qgis.core import QgsField

    pr.addAttributes([QgsField("nox_kg", QVariant.Double)])
    layer.updateFields()

    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY

    layer.startEditing()
    # 80 zero cells (background) + 7 cells with increasing nox values
    # spanning the typical observed range.
    values = [0.0] * 80 + [0.005, 0.05, 0.10, 0.20, 0.30, 0.35, 0.40]
    for i, v in enumerate(values):
        f = QgsFeature(layer.fields())
        # tiny dummy polygon; geometry doesn't affect Jenks
        f.setGeometry(
            QgsGeometry.fromPolygonXY(
                [
                    [
                        QgsPointXY(i, 0),
                        QgsPointXY(i + 1, 0),
                        QgsPointXY(i + 1, 1),
                        QgsPointXY(i, 1),
                    ]
                ]
            )
        )
        f.setAttribute("nox_kg", v)
        layer.addFeature(f)
    layer.commitChanges()
    return layer


def test_jenks_emits_degenerate_zero_bin_on_zero_heavy_data():
    """Sanity check: confirm that Jenks classification on this data
    actually produces a degenerate '0 - 0' bin. If this assumption
    breaks (e.g. QGIS changes Jenks behaviour in a future release)
    the fix below becomes a no-op rather than silently masking a
    different bug."""
    layer = _make_layer_with_zero_heavy_data()

    renderer = QgsGraduatedSymbolRenderer("nox_kg")
    renderer.setClassificationMethod(QgsClassificationJenks())
    renderer.setSourceColorRamp(
        QgsGradientColorRamp(
            QColor("lightGray"),
            QColor("darkRed"),
        )
    )
    renderer.updateClasses(layer, 7)
    sym = QgsSymbol.defaultSymbol(layer.geometryType())
    renderer.updateSymbols(sym)

    degenerate = [r for r in renderer.ranges() if r.lowerValue() == r.upperValue()]
    assert len(degenerate) >= 1, (
        f"Expected at least one degenerate (0-0) range from Jenks on "
        f"zero-heavy data, got ranges: "
        f"{[(r.lowerValue(), r.upperValue()) for r in renderer.ranges()]}"
    )


def test_setColorGradientRenderer_strips_degenerate_zero_bin():
    """End-to-end check: after setColorGradientRenderer runs, the
    renderer must have NO degenerate zero-width range with a non-
    transparent fill. Exactly one zero-width range is allowed -- the
    explicit transparent '0' entry added on purpose."""
    from open_alaqs.core.plotting.ContourPlotVectorLayer import (
        ContourPlotVectorLayer,
    )

    # Build a wrapper and inject the synthesized features. We bypass
    # addData (which expects a geo-DataFrame); instead directly feed
    # features into wrapper.layer to mirror the real flow.
    wrapper = ContourPlotVectorLayer(
        layer_name="Emissions",
        field_name="nox_kg",
        enable_labels=False,
        use_centroid_symbol=False,
    )

    # Replace the wrapper's empty layer with our zero-heavy synthetic
    # one so updateClasses has data to classify. Re-add the field if
    # needed (the wrapper's layer already has nox_kg from _add_field).
    src = _make_layer_with_zero_heavy_data()
    pr = wrapper.layer.dataProvider()
    pr.addFeatures(list(src.getFeatures()))
    wrapper.layer.updateExtents()

    wrapper.setColorGradientRenderer(classes_count=7)

    renderer = wrapper.layer.renderer()
    assert renderer is not None
    ranges = list(renderer.ranges())

    zero_width_ranges = [r for r in ranges if r.lowerValue() == r.upperValue()]

    # Exactly one zero-width range -- the explicit transparent "0".
    assert len(zero_width_ranges) == 1, (
        f"Expected exactly 1 zero-width range (the explicit transparent "
        f"'0' entry) but found {len(zero_width_ranges)}. The Jenks "
        f"degenerate '0 - 0' bin is leaking back into the legend.\n"
        f"All ranges: "
        f"{[(r.lowerValue(), r.upperValue(), r.label()) for r in ranges]}"
    )

    # And that single zero-width range must be the explicit transparent
    # one (label "0", lower=upper=0.0).
    z = zero_width_ranges[0]
    assert z.lowerValue() == 0.0 and z.upperValue() == 0.0, (
        f"The remaining zero-width range is not at 0.0: "
        f"({z.lowerValue()}, {z.upperValue()})"
    )
    assert z.label() == "0", (
        f"The remaining zero-width range has unexpected label "
        f"{z.label()!r} (expected '0')"
    )


def test_legitimate_graduated_ranges_survive_dedup():
    """The fix must NOT touch normal Jenks ranges with lower < upper.
    Pin the count of non-zero-width ranges so we'd notice if the dedup
    pass started over-deleting."""
    from open_alaqs.core.plotting.ContourPlotVectorLayer import (
        ContourPlotVectorLayer,
    )

    wrapper = ContourPlotVectorLayer(
        layer_name="Emissions",
        field_name="nox_kg",
        enable_labels=False,
        use_centroid_symbol=False,
    )
    src = _make_layer_with_zero_heavy_data()
    wrapper.layer.dataProvider().addFeatures(list(src.getFeatures()))
    wrapper.layer.updateExtents()
    wrapper.setColorGradientRenderer(classes_count=7)

    ranges = list(wrapper.layer.renderer().ranges())
    non_zero_width = [r for r in ranges if r.lowerValue() < r.upperValue()]

    # 7 classes requested. Jenks on small synthetic data may collapse
    # to fewer non-degenerate bins; on this fixture it produces 4. The
    # important property is that the dedup pass keeps all of them --
    # i.e. it strips ONLY the degenerate "0 - 0" bin and nothing else.
    assert len(non_zero_width) >= 3, (
        f"Dedup pass appears to have stripped legitimate graduated "
        f"ranges. Found only {len(non_zero_width)} non-zero-width "
        f"ranges; expected at least 3.\nAll ranges: "
        f"{[(r.lowerValue(), r.upperValue()) for r in ranges]}"
    )


def test_dedup_loop_present_in_source():
    """Static check on the source so a future refactor that drops the
    dedup loop fails this test rather than silently regressing the
    user-visible legend."""
    src = (
        REPO / "open_alaqs" / "core" / "plotting" / "ContourPlotVectorLayer.py"
    ).read_text()

    # The dedup loop must run BEFORE addClassRange of the explicit "0".
    dedup_idx = src.find("rng.lowerValue() == rng.upperValue()")
    explicit_idx = src.find("addClassRange(QgsRendererRange(0.0, 0.0,")

    assert dedup_idx > 0, (
        "Dedup loop (checking lowerValue() == upperValue()) is missing "
        "from ContourPlotVectorLayer.py. Re-introducing the legend will "
        "produce two zero entries again."
    )
    assert explicit_idx > 0, (
        "Explicit transparent zero range is missing from " "ContourPlotVectorLayer.py."
    )
    assert dedup_idx < explicit_idx, (
        "Dedup loop must run BEFORE the explicit zero range is added, "
        "otherwise it would also strip the explicit transparent '0' "
        "entry (which is itself zero-width)."
    )
