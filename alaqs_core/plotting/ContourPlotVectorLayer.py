from PyQt5 import QtCore, QtGui
from qgis.core import (
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

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.tools import conversion

logger = get_logger(__name__)


class ContourPlotVectorLayer:
    """
    Class returns a new vector layer with data points that can be used to create
     a contour plot with the QGIS contour plugin
    """

    LAYER_NAME = "Emissions"

    def __init__(self, config, header=None, data=None):
        self._layerName = ContourPlotVectorLayer.LAYER_NAME
        if "name" in config:
            self._layerName = config["name"]
        if "name_suffix" in config:
            self._layerName += config["name_suffix"]

        self._style = {}
        self.setStyle(config)

        self._vectorlayer = None
        self._myCrs = QgsCoordinateReferenceSystem("EPSG:3857")
        # except Exception:
        #     self._myCrs = QgsCoordinateReferenceSystem(3857, 4326)

        self.createLayer(self._layerName)

        if header is not None:
            self.addHeader(header)
        # else:
        #     self.addHeader([("NOx", "double")])

        if data is not None:
            self.addData(data)

    def getLayerName(self):
        return self._layerName

    def setColorGradientRenderer(self, config=None):
        if config is None:
            config = {}

        # Get the minimum value
        min_ = config.get("minValue", 0.0)

        # Get the number of classes
        numberOfClasses_ = config.get("numberOfClasses", 7)

        # Create the color gradient
        color1_ = QtGui.QColor(config.get("color1", "white"))
        color2_ = QtGui.QColor(config.get("color2", "red"))
        green = QtGui.QColor(0, 255, 0)
        yellow = QtGui.QColor(255, 255, 0)
        stop1 = QgsGradientStop(0.3, green)
        stop2 = QgsGradientStop(0.6, yellow)
        stops = [stop1, stop2]
        discrete = False
        QgsGradientColorRamp(color1_, color2_, discrete, stops)

        if "fieldname" not in config and "fieldname" not in self._style:
            raise Exception(
                "Did not find field for color gradient renderer!!"
                " Add property 'fieldname' for method "
                "'setColorGradientRenderer'."
            )

        columnName_ = config.get("fieldname", self._style["fieldname"])

        symbol_ = QgsSymbol.defaultSymbol(self._vectorlayer.geometryType())
        symbol_.setOpacity(self._style["transparency"])
        symbol_.symbolLayer(0).setStrokeColor(QtCore.Qt.transparent)

        # Set the classification method
        method_ = QgsClassificationPrettyBreaks()

        # Create and configure the renderer
        renderer_ = QgsGraduatedSymbolRenderer(columnName_)
        renderer_.setClassificationMethod(method_)
        renderer_.updateClasses(self._vectorlayer, numberOfClasses_)
        renderer_.updateSymbols(symbol_)
        # todo: Add the custom color ramp

        if min_ > 0.0:
            renderer_.updateRangeLowerValue(min(0, min_), min_)

        self._vectorlayer.setRenderer(renderer_)

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
            self._vectorlayer.setRenderer(QgsSingleSymbolRenderer(symbol))

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

    def getCrs(self):
        return self._myCrs

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

        if self._vectorlayer:
            pr = self._vectorlayer.dataProvider()
            self._vectorlayer.startEditing()

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
            self._vectorlayer.updateFields()
            self._vectorlayer.commitChanges()
            self._vectorlayer.updateExtents()
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

        if self._vectorlayer:

            pr = self._vectorlayer.dataProvider()
            self._vectorlayer.startEditing()

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
            self._vectorlayer.updateFields()
            self._vectorlayer.updateExtents()
            self._vectorlayer.commitChanges()

        else:
            QgsMessageLog.logMessage(
                "Could not find contour layer to add data.", "ContourPlot", 4
            )
            return False

        return True

    def createLayer(self, name=""):
        if name == "":
            # ContourPlotVectorLayer.LAYER_NAME
            name = self._layerName
        if "fieldname" in self._style and self._style["fieldname"]:
            name = "%s %s" % (self._style["fieldname"], self._layerName)

        if self._style["isPolygon"]:
            self._vectorlayer = QgsVectorLayer("Polygon", name, "memory")
        else:
            self._vectorlayer = QgsVectorLayer("Point", name, "memory")

        # set coordinate reference system
        self._vectorlayer.setCrs(self.getCrs())

    def getLayer(self):
        return self._vectorlayer
