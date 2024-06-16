from typing import Iterable, cast

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
from open_alaqs.core.tools import conversion

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
    ) -> None:
        self.field_name = field_name
        self.enable_labels = enable_labels
        self.use_centroid_symbol = use_centroid_symbol

        if field_name:
            layer_name = f"{field_name} {layer_name}"

        self.layer = QgsVectorLayer("Polygon", layer_name, "memory")
        self.layer.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

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
        transparent_symbol.setColor(QColor("transparent"))

        # Create and configure the renderer
        renderer = QgsGraduatedSymbolRenderer(self.field_name)
        renderer.setClassificationMethod(QgsClassificationJenks())
        renderer.setSourceColorRamp(gradient_color_ramp)
        renderer.updateClasses(self.layer, classes_count)
        renderer.updateSymbols(symbol)
        renderer.addClassRange(QgsRendererRange(0.0, 0.0, transparent_symbol, "0"))
        renderer.sortByValue()

        self.layer.setRenderer(renderer)

    def addHeader(self, headers: Iterable[tuple[str, QVariant.Type]]) -> None:
        """Adds header to QgsVectorLayer"""

        self.layer.startEditing()

        for field_name, field_type in headers:
            if not self.layer.addAttribute(QgsField(field_name, field_type)):
                raise Exception(
                    f'Could not add field "{field_name}" with {field_type=}!'
                )

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

            attr_index = fields.indexFromName(self.field_name)
            attrs = {
                attr_index: conversion.convertToFloat(row["Q"]),
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
