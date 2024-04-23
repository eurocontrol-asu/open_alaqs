from typing import Literal, Union

from qgis.core import (
    Qgis,
    QgsClassificationPrettyBreaks,
    QgsCoordinateReferenceSystem,
    QgsErrorMessage,
    QgsFeature,
    QgsField,
    QgsFillSymbol,
    QgsGeometry,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsGraduatedSymbolRenderer,
    QgsMarkerSymbol,
    QgsMessageLog,
    QgsPointXY,
    QgsSingleSymbolRenderer,
    QgsSymbol,
    QgsVectorLayer,
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

    def setSymbolRenderer(self):
        s_ = {
            "color": str(self._style["color"]),
            "color_border": str(self._style["color_border"]),
            "style": str(self._style["style"]),
            "style_border": str(self._style["style_border"]),
        }  # width_border

        symbol = None
        if self._style["isPolygon"]:
            symbol = QgsFillSymbol.createSimple(s_)
        else:
            symbol = QgsMarkerSymbol.createSimple(s_)

        symbol.setOpacity(1.0 - float(self._style["transparency"]))

        if symbol is not None:
            self.layer.setRenderer(QgsSingleSymbolRenderer(symbol))

    def setStyle(self, config):
        style = {}

        # set some default values for the layer configuration
        if "isPolygon" in config:
            style["isPolygon"] = config["isPolygon"]
        else:
            style["isPolygon"] = False

        if "transparency" in config:
            # takes values in [0,1]
            style["transparency"] = float(config["transparency"])
            if style["transparency"] > 1.0:
                style["transparency"] = 1.0
            if style["transparency"] < 0.0:
                style["transparency"] = 0.0
        else:
            style["transparency"] = 0.75

        if "color" in config:
            # "R,G,B" or "#hexcode"
            style["color"] = str(config["color"])
        else:
            style["color"] = "0,0,255"

        if "color_border" in config:
            # "R,G,B" or "#hexcode"
            style["color"] = str(config["color_border"])
        else:
            style["color_border"] = "0,0,0"

        if "color_border" in config:
            # "R,G,B" or "#hexcode"
            style["color_border"] = str(config["color_border"])
        else:
            style["color_border"] = "0,0,0"

        if "style" in config:
            # "R,G,B" or "#hexcode"
            style["style"] = str(config["style"])
        else:
            style["style"] = "solid"

        if "style_border" in config:
            # "R,G,B" or "#hexcode"
            style["style_border"] = str(config["style_border"])
        else:
            style["style_border"] = "solid"

        if "Label_enable" in config and config["Label_enable"]:
            style["Label_enable"] = config["Label_enable"]
        else:
            style["Label_enable"] = False

        if "fieldname" in config and config["fieldname"] is not None:
            style["fieldname"] = config["fieldname"]

        self._style.update(style)

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

    def addData(self, data):
        """Method to add data to the layer
        Example argument:
        data = [{
                "coordinates":{
                    "x":10,
                    "y":10
                },
                "attributes":{
                    "name":"foo",
                    "value":2323.,
                }
            }]
        """

        # data is a GeoDataFrame (keys: hash, geometry, zmin, zmax, Emission)
        self._data = data

        if self.layer:

            pr = self.layer.dataProvider()
            self.layer.startEditing()

            for pv in data.index:
                point_value = data.loc[pv]

                if not point_value.Q or not point_value.geometry:
                    continue

                # get the field map of the vectorlayer
                fields = pr.fields()
                # create a new feature
                feature = QgsFeature()
                # make a copy and give ownership to python
                feature.setFields(fields)

                fields.indexFromName(point_value["hash"])
                # if field_index > -1:
                feat_value = conversion.convertToFloat(point_value["Q"])
                # feature.setAttribute(key, feat_value)
                if "fieldname" in self._style:
                    feature.setAttribute(self._style["fieldname"], feat_value)
                else:
                    logger.debug(
                        "Could not find field/header for '%s'."
                        % (str(self._style["fieldname"]))
                    )

                # geometry
                if self._style["isPolygon"]:
                    cell_bounds = point_value["geometry"].bounds
                    feature.setGeometry(
                        QgsGeometry.fromPolygonXY(
                            [
                                [
                                    QgsPointXY(cell_bounds[0], cell_bounds[1]),
                                    QgsPointXY(cell_bounds[2], cell_bounds[1]),
                                    QgsPointXY(cell_bounds[2], cell_bounds[3]),
                                    QgsPointXY(cell_bounds[0], cell_bounds[3]),
                                ]
                            ]
                        )
                    )

                else:
                    point_geo = point_value["geometry"].centroid
                    qgs_point_xy = QgsPointXY(point_geo.x, point_geo.y)
                    feature.setGeometry(QgsGeometry.fromPointXY(qgs_point_xy))

                # add feature to the layer
                (res, outFeats) = pr.addFeatures([feature])

            # update fields, layer extents, and finalize edits
            self.layer.updateFields()
            self.layer.updateExtents()
            self.layer.commitChanges()

        else:
            QgsMessageLog.logMessage(
                "Could not find contour layer to add data.", "ContourPlot", 4
            )
            return False

        return True
