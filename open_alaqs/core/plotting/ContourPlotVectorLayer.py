from typing import Literal, Union

import pandas as pd
from qgis.core import (
    Qgis,
    QgsClassificationPrettyBreaks,
    QgsCoordinateReferenceSystem,
    QgsErrorMessage,
    QgsField,
    QgsGeometry,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsGraduatedSymbolRenderer,
    QgsPointXY,
    QgsSymbol,
    QgsVectorLayer,
    QgsVectorLayerUtils,
)
from qgis.PyQt import QtCore
from qgis.PyQt.QtGui import QColor

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools import conversion

logger = get_logger(__name__)


class ContourPlotVectorLayer:
    """
    Class returns a new vector layer with data points that can be used to create
     a contour plot with the QGIS contour plugin
    """

    LAYER_NAME = "Emissions"

    def __init__(
        self,
        layer_name: str,
        field_name: str,
        geometry_type: Union[
            Literal[Qgis.GeometryType.Polygon], Literal[Qgis.GeometryType.Point]
        ],
        enable_labels: bool,
    ) -> None:
        self.field_name = field_name
        self.enable_labels = enable_labels

        if field_name:
            layer_name = f"{field_name} {layer_name}"

        if geometry_type == Qgis.GeometryType.Point:
            self.layer = QgsVectorLayer("Point", layer_name, "memory")
        elif geometry_type == Qgis.GeometryType.Polygon:
            self.layer = QgsVectorLayer("Polygon", layer_name, "memory")
        else:
            raise NotImplementedError(
                "Layer geometry type '{geometry_type}' is not supported yet!"
            )

        # set coordinate reference system
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

        symbol = QgsSymbol.defaultSymbol(self.layer.geometryType())
        symbol.symbolLayer(0).setStrokeColor(QtCore.Qt.transparent)

        # Create and configure the renderer
        renderer = QgsGraduatedSymbolRenderer(self.field_name)
        renderer.setClassificationMethod(QgsClassificationPrettyBreaks())
        renderer.setSourceColorRamp(gradient_color_ramp)
        renderer.updateClasses(self.layer, classes_count)
        renderer.updateSymbols(symbol)

        self.layer.setRenderer(renderer)

    def addHeader(self, header):
        """Adds header to QgsVectorLayer

        Possible typenames are: int, double, float, real
        Argument is a list of tuples(name, value_type)

        Contour plugin requires a QgsField.typeName() with either "int",
        "double", "real", or "float"
        and crashes for strings.

        Example argument :
        header = [("value_NOx", "double"}, ("id", "int")]
        """
        self._header = header

        if self.layer:
            pr = self.layer.dataProvider()
            self.layer.startEditing()

            _h = []
            for name, type_string in header:
                _type = QtCore.QVariant.Double

                if type_string.lower() in ["double", "dbl", "real"]:
                    _type = QtCore.QVariant.Double
                elif type_string.lower() in ["int", "Integer"]:
                    _type = QtCore.QVariant.Int
                elif type_string.lower() in ["float", "flt"]:
                    _type = QtCore.QVariant.Float

                _h.append(QgsField(name, _type, type_string))

            pr.addAttributes(_h)

            # and update the QgsVectorLayer
            self.layer.updateFields()
            self.layer.commitChanges()
            self.layer.updateExtents()
        else:
            QgsErrorMessage.logMessage(
                "Could not create header for contour layer.", "Contour Plot", 4
            )

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

            if self.layer.geometryType() == Qgis.GeometryType.Polygon:
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
            elif self.layer.geometryType() == Qgis.GeometryType.Polygon:
                shapely_point = row["geometry"].centroid
                geom = QgsGeometry.fromPointXY(
                    QgsPointXY(shapely_point.x, shapely_point.y)
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
                raise Exception(
                    'Unable to add new feature to layer "{}": {}'.format(
                        self.layer.name(),
                        "".join(self.layer.dataProvider().errors()),
                    ),
                )

        if not self.layer.commitChanges():
            raise Exception(f'Failed to commit changes to layer "{self.layer.name()}"!')
