from typing import cast

import pandas as pd
from qgis.core import (
    QgsCentroidFillSymbolLayer,
    QgsClassificationJenks,
    QgsCoordinateReferenceSystem,
    QgsField,
    QgsFillSymbol,
    QgsGeometry,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsGraduatedSymbolRenderer,
    QgsPointXY,
    QgsRendererRange,
    QgsSymbol,
    QgsVectorLayer,
    QgsVectorLayerUtils,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor

from open_alaqs.core.alaqslogging import get_logger

logger = get_logger(__name__)


class ContourPlotVectorLayer:
    """Class returns a new vector layer with data points that can be used to create a contour plot with the QGIS contour plugin"""

    LAYER_NAME = "Emissions"

    def __init__(
        self,
        layer_name: str,
        field_name: str,
        enable_labels: bool,
        use_centroid_symbol: bool,
        epsg: int = 3857,
    ) -> None:
        self.field_name = field_name
        self.enable_labels = enable_labels
        self.use_centroid_symbol = use_centroid_symbol

        if field_name:
            layer_name = f"{field_name} {layer_name}"

        self.layer = QgsVectorLayer("Polygon", layer_name, "memory")
        self.layer.setCrs(QgsCoordinateReferenceSystem.fromEpsgId(epsg))

        self._add_field(self.field_name)

    def setColorGradientRenderer(
        self,
        gradient_color1: QColor = QColor("lightGray"),
        gradient_color2: QColor = QColor("darkRed"),
        gradient_stop_colors: list[QColor] = [QColor("green"), QColor("yellow")],
        classes_count: int = 7,
    ) -> None:
        # Create the color gradient
        gradient_stops = []
        for color_idx, color in enumerate(gradient_stop_colors, 1):
            gradient_stops.append(
                QgsGradientStop(color_idx / (len(gradient_stop_colors) + 1), color)
            )

        gradient_color_ramp = QgsGradientColorRamp(
            gradient_color1, gradient_color2, False, gradient_stops
        )

        symbol = cast(QgsSymbol, QgsSymbol.defaultSymbol(self.layer.geometryType()))

        if self.use_centroid_symbol:
            symbol.changeSymbolLayer(0, QgsCentroidFillSymbolLayer())

        symbol.symbolLayer(0).setStrokeColor(Qt.GlobalColor.transparent)
        transparent_symbol = QgsFillSymbol()
        transparent_symbol.symbolLayer(0).setStrokeColor(Qt.GlobalColor.transparent)
        transparent_symbol.setColor(Qt.GlobalColor.transparent)

        # Create and configure the renderer
        renderer = QgsGraduatedSymbolRenderer(self.field_name)
        renderer.setClassificationMethod(QgsClassificationJenks())
        renderer.setSourceColorRamp(gradient_color_ramp)
        renderer.updateClasses(self.layer, classes_count)
        renderer.updateSymbols(symbol)

        # Strip degenerate zero-width ranges produced by Jenks. Jenks
        # classification of an emissions grid normally hits the case
        # where most cells are exactly zero (the airport-domain background:
        # no aircraft passes over them). Jenks then emits a "0 - 0" bin
        # as one of its classes, which gets painted with the gradient
        # ramp's first colour (lightGray) and labelled "0 - 0". That bin
        # collides with the explicit transparent "0" range added below,
        # producing two separate zero entries in the legend (the gray
        # "0 - 0" and the transparent "0") which is visually confusing.
        # Removing any range whose lower bound equals its upper bound
        # eliminates the degenerate bin without disturbing any legitimate
        # graduated bin (legitimate Jenks bins always have lower < upper).
        # Iterate in reverse so deletion doesn't shift indices.
        for idx in reversed(range(len(renderer.ranges()))):
            rng = renderer.ranges()[idx]
            if rng.lowerValue() == rng.upperValue():
                renderer.deleteClass(idx)

        renderer.addClassRange(QgsRendererRange(0.0, 0.0, transparent_symbol, "0"))
        renderer.sortByValue()

        self.layer.setRenderer(renderer)

    def _add_field(self, field_name: str) -> None:
        self.layer.startEditing()

        # QGIS 3.x QgsField expects QVariant.Double. The QMetaType-based
        # overload (QMetaType.Type.Double) was introduced in a later QGIS
        # release and raises TypeError on current plugin targets.
        if not self.layer.addAttribute(QgsField(field_name, QVariant.Double)):
            raise Exception(f'Could not add field "{field_name}"!')

        self.layer.updateFields()
        self.layer.commitChanges()
        self.layer.updateExtents()

    def addData(self, df: pd.DataFrame) -> None:
        """Add DataFrame data to the layer."""

        assert "geometry" in df.columns
        assert "Q" in df.columns

        if not self.layer.startEditing():
            raise Exception(f'Failed to start editing on layer "{self.layer.name()}"!')

        fields = self.layer.fields()

        attr_df_name = f"{self.field_name}_kg"
        df = df[df[attr_df_name] >= 0].copy()  # Filter out negative pollutants

        for _idx, row in df.iterrows():
            if not row["geometry"]:
                continue

            cell_bounds = row["geometry"].bounds
            geom = QgsGeometry.fromPolygonXY(
                [
                    [
                        QgsPointXY(cell_bounds[0], cell_bounds[1]),
                        QgsPointXY(cell_bounds[0], cell_bounds[3]),
                        QgsPointXY(cell_bounds[2], cell_bounds[3]),
                        QgsPointXY(cell_bounds[2], cell_bounds[1]),
                    ]
                ]
            )

            # TODO OPENGIS.ch: find a smarter way to add the "_kg" suffix
            # attr_df_name = f"{self.field_name}_kg"
            attr_index = fields.indexFromName(self.field_name)
            attrs = {
                attr_index: row[attr_df_name],
            }

            f = QgsVectorLayerUtils.createFeature(self.layer, geom, attrs)

            if not f.isValid():
                raise Exception(
                    f"Unable to create a valid feature to layer {self.layer.name()}!"
                )

            if not self.layer.addFeature(f):
                data_provider = self.layer.dataProvider()

                if data_provider is None:
                    errors = ["Missing dataprovider!"]
                else:
                    errors = data_provider.errors()

                raise Exception(
                    'Unable to add new feature to layer "{}": {}'.format(
                        self.layer.name(),
                        "".join(errors),
                    ),
                )

        if not self.layer.commitChanges():
            raise Exception(f'Failed to commit changes to layer "{self.layer.name()}"!')

