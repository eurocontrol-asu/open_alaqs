from builtins import str
from builtins import object
# from qgis.PyQt import QtGui, QtCore, QtWidgets
from PyQt5 import QtCore, QtGui, QtWidgets
#make class loadable also from external resources
try:
    from qgis.core import *
    # from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem
    # from qgis.core import QgsCoordinateReferenceSystem

except ImportError:
    pass

from tools import Conversions

# import alaqsutils
# import logging              # For unit testing. Can be commented out for distribution
# logger = logging.getLogger("alaqs.%s" % (__name__))
import os, sys
import alaqslogging
logger = alaqslogging.logging.getLogger(__name__)
logger.setLevel('DEBUG')
file_handler = alaqslogging.logging.FileHandler(alaqslogging.LOG_FILE_PATH)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = alaqslogging.logging.Formatter(log_format)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

class ContourPlotVectorLayer(object):
    """
    Class returns a new vector layer with data points that can be used to create a contour plot with the QGIS contour plugin
    """

    LAYER_NAME="Emissions"

    def __init__(self, config, header=None, data=None):
        self._layerName = ContourPlotVectorLayer.LAYER_NAME
        if "name" in config:
            self._layerName = config["name"]
        if "name_suffix" in config:
            self._layerName += config["name_suffix"]

        self._style = {}
        self.setStyle(config)

        self._vectorlayer = None
        self._myCrs = QgsCoordinateReferenceSystem(3857, QgsCoordinateReferenceSystem.EpsgCrsId)
        # except:
        #     self._myCrs = QgsCoordinateReferenceSystem(3857, 4326)

        self.createLayer(self._layerName)

        if not header is None:
            self.addHeader(header)
        # else:
        #     self.addHeader([("NOx", "double")])

        if not data is None:
            self.addData(data)

    def getLayerName(self):
        return self._layerName

    def setColorGradientRenderer(self, config={}):

        min_ = 0. if not "minValue" in config else config["minValue"]
        # max_ = 0. if not "maxValue" in config else config["maxValue"]

        numberOfClasses_ = 7 if not "numberOfClasses" in config else config["numberOfClasses"]

        color1_ = QtGui.QColor("white") if not "color1" in config else QtGui.QColor(config["color1"])
        color2_ = QtGui.QColor("red") if not "color2" in config else QtGui.QColor(config["color2"])
        # blue = QColor(0, 0, 255)
        # red = QColor(255, 0, 0)
        green = QtGui.QColor(0, 255, 0)
        yellow = QtGui.QColor(255, 255, 0)
        stop1 = QgsGradientStop(0.3, green)
        stop2 = QgsGradientStop(0.6, yellow)
        stops = [stop1, stop2]
        discrete = False
        colorRamp_ = QgsGradientColorRamp(color1_, color2_, discrete, stops)

        if not "fieldname" in config and not "fieldname" in self._style:
            raise Exception("Did not find field for color gradient renderer!! Add property 'fieldname' for method 'setColorGradientRenderer'.")

        columnName_ = config["fieldname"] if "fieldname" in config else self._style["fieldname"]

        symbol_ = QgsSymbol.defaultSymbol(self._vectorlayer.geometryType())
        symbol_.setOpacity(self._style["transparency"])
        symbol_.symbolLayer(0).setStrokeColor(QtCore.Qt.transparent)

        mode_ = QgsGraduatedSymbolRenderer.Pretty        # EqualInterval. Quantile. Jenks. StdDev. Pretty
        renderer_ = QgsGraduatedSymbolRenderer.createRenderer(self._vectorlayer, columnName_, numberOfClasses_, mode_, symbol_, colorRamp_)

        if min_ > 0.0:
            renderer_.updateRangeLowerValue(min(0, min_), min_)
            # renderer_.updateRangeLowerValue(0, 0.0)
            # renderer_.updateRangeUpperValue(0, min_)
            # renderer_.updateRangeLowerValue(1, min_)
            # renderer_.addClassRange(0.0, Conversions.convertToFloat(min_))
        self._vectorlayer.setRenderer(renderer_)

    def setSymbolRenderer(self):
        s_ = {
                'color' : str(self._style["color"]),
                'color_border' : str(self._style["color_border"]),
                'style' : str(self._style["style"]),
                'style_border' : str(self._style["style_border"])
        }#width_border

        symbol = None
        if self._style["isPolygon"]:
            symbol = QgsFillSymbol.createSimple(s_)
        else:
            symbol = QgsMarkerSymbol.createSimple(s_)

        symbol.setOpacity(1.-float(self._style["transparency"]))

        if not symbol is None:
            self._vectorlayer.setRenderer(QgsSingleSymbolRenderer( symbol ) )

    def setStyle(self, config):
        style = {}

        #set some default values for the layer configuration
        if "isPolygon" in config:
            style["isPolygon"] = config["isPolygon"]
        else:
            style["isPolygon"]=False

        if "transparency" in config:
            style["transparency"]=float(config["transparency"]) #takes values in [0,1]
            if style["transparency"]>1.:
                style["transparency"] = 1.
            if style["transparency"]<0.:
                style["transparency"] = 0.
        else:
            style["transparency"] = 0.75

        if "color" in config:
            style["color"]=str(config["color"]) #"R,G,B" or "#hexcode"
        else:
            style["color"] = "0,0,255"

        if "color_border" in config:
            style["color"]=str(config["color_border"]) #"R,G,B" or "#hexcode"
        else:
            style["color_border"] = "0,0,0"

        if "color_border" in config:
            style["color_border"]=str(config["color_border"]) #"R,G,B" or "#hexcode"
        else:
            style["color_border"] = "0,0,0"

        if "style" in config:
            style["style"]=str(config["style"]) #"R,G,B" or "#hexcode"
        else:
            style["style"] = "solid"

        if "style_border" in config:
            style["style_border"]=str(config["style_border"]) #"R,G,B" or "#hexcode"
        else:
            style["style_border"] = "solid"

        if "Label_enable" in config and config["Label_enable"]:
            style["Label_enable"] = config["Label_enable"]
        else:
            style["Label_enable"] = False

        if "fieldname" in config and not config["fieldname"] is None:
            style["fieldname"] = config["fieldname"]

        # if "minValue" in config:
        #     style["min"] = config["minValue"]
        # if "maxValue" in config:
        #     style["max"] = config["maxValue"]
        # logger.info("Min/Max: %s"%([style["min"], style["max"]]))

        self._style.update(style)
        # logger.debug(self._style)

    def getCrs(self):
        return self._myCrs

    def addHeader(self, header):
        """ Adds header to QgsVectorLayer

        Possible typenames are: int, double, float, real
        Argument is a list of tuples(name, value_type)

        Contour plugin requires a QgsField.typeName() with either "int", "double", "real", or "float"
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

            #and update the QgsVectorLayer
            self._vectorlayer.updateFields()
            self._vectorlayer.commitChanges()
            self._vectorlayer.updateExtents()
        else:
            QgsErrorMessage.logMessage("Could not create header for contour layer.", "Contour Plot", 4)

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
        self._data = data
        # data is a GeoDataFrame (keys: hash, geometry, zmin, zmax, Emission)

        if self._vectorlayer:

            pr = self._vectorlayer.dataProvider()
            self._vectorlayer.startEditing()

            # for point_value in data:
            # for point_value in data.index:

            for pv in data.index:
                # point_value = grid3D.loc[pv]
                point_value = data.loc[pv]

                if not (point_value.Q) or not (point_value.geometry):
                    continue

                # if not ("coordinates" in point_value) or not ("attributes" in point_value):
                #     continue

                #get the field map of the vectorlayer
                fields = pr.fields()
                #create a new feature
                feature = QgsFeature()
                #make a copy and give ownership to python
                feature.setFields(fields)

                #initialize attributes
                #for key in point_value["attributes"]:
                #    field_index = fields.indexFromName(str(key))
                #    if field_index > -1:
                #        feature.setAttribute(key, 0.)

                field_index = fields.indexFromName(point_value['hash'])
                # if field_index > -1:
                feat_value = Conversions.convertToFloat(point_value["Q"])
                    # feature.setAttribute(key, feat_value)
                if ("fieldname" in self._style):
                    feature.setAttribute(self._style["fieldname"], feat_value)
                else:
                    logger.debug("Could not find field/header for '%s'." % (str(self._style["fieldname"])))
                    # QgsMessageLog.logMessage("Could not find field/header for '%s'." % (str(self._style["fieldname"])), "ContourPlot", 4)

                # #attributes
                # # for key in point_value["attributes"]:
                # for key in point_value["attributes"]:
                #
                #     field_index = fields.indexFromName(str(key))
                #     if field_index > -1:
                #         feat_value = Conversions.convertToFloat(point_value["attributes"][key])
                #         feature.setAttribute(key, feat_value)
                #     else:
                #         QgsMessageLog.logMessage("Could not find field/header for '%s'."%(str(key)),"ContourPlot", 4)

                #geometry
                if self._style["isPolygon"]:
                    cell_bounds = point_value["geometry"].bounds
                    feature.setGeometry(QgsGeometry.fromPolygonXY([[
                        QgsPointXY(cell_bounds[0],cell_bounds[1]),
                        QgsPointXY(cell_bounds[2],cell_bounds[1]),
                        QgsPointXY(cell_bounds[2],cell_bounds[3]),
                        QgsPointXY(cell_bounds[0],cell_bounds[3])
                    ]]))

                else:
                    point_geo = point_value["geometry"].centroid
                    qgs_point_xy = QgsPointXY(point_geo.x, point_geo.y)
                    feature.setGeometry(QgsGeometry.fromPointXY(qgs_point_xy))

                #add feature to the layer
                (res, outFeats) = pr.addFeatures([feature])

            # update fields, layer extents, and finalize edits
            self._vectorlayer.updateFields()
            self._vectorlayer.updateExtents()
            self._vectorlayer.commitChanges()

        else:
            QgsMessageLog.logMessage("Could not find contour layer to add data.","ContourPlot", 4)
            return False

        return True

    def createLayer(self, name=""):
        if name=="":
            name = self._layerName #ContourPlotVectorLayer.LAYER_NAME
        if "fieldname" in self._style and self._style["fieldname"]:
            # name = "%s %s"%(self._style["fieldname"], ContourPlotVectorLayer.LAYER_NAME)
            name = "%s %s"%(self._style["fieldname"], self._layerName)

        # if "Label_enable" in self._style and self._style["Label_enable"]:
        #     logger.debug("Label enable is %s"%self._style["Label_enable"])
        #     self._vectorlayer.setCustomProperty("labeling/enabled", "true")

        if self._style["isPolygon"]:
            self._vectorlayer = QgsVectorLayer("Polygon", name, "memory")
        else:
            self._vectorlayer = QgsVectorLayer("Point", name, "memory")

        #set coordinate reference system
        self._vectorlayer.setCrs(self.getCrs())

        # if ("Label_enable" in self._style and "fieldname" in self._style):
        #     # if "Label_enable" in self._style and self._style["Label_enable"] and "fieldname" in self._style:
        #     self._vectorlayer.setCustomProperty("labeling", "pal")
        #     # self._vectorlayer.setCustomProperty("labeling/enabled",  self._style["Label_enable"])
        #     self._vectorlayer.setCustomProperty("labeling/enabled", True)
        #     self._vectorlayer.setCustomProperty("labeling/fontFamily", "Arial")
        #     self._vectorlayer.setCustomProperty("labeling/fontSize", "8")
        #     #self._vectorlayer.setCustomProperty("labeling/bufferSize", 0.15)
        #     #self._vectorlayer.setCustomProperty("labeling/bufferColor", "(255,0,255)")
        #     #self._vectorlayer.setCustomProperty("labeling/isExpression", True)
        #     self._vectorlayer.setCustomProperty("labeling/fieldName", self._style["fieldname"])
        #     self._vectorlayer.setCustomProperty("labeling/formatNumbers", True)
        #     self._vectorlayer.setCustomProperty("labeling/decimals", 0)
        #     self._vectorlayer.setCustomProperty("labeling/plussign", False)

            # self._vectorlayer.setCustomProperty("labeling/scaleMin", self._style["min"])
            # self._vectorlayer.setCustomProperty("labeling/scaleMax", self._style["max"])
            # self._vectorlayer.setCustomProperty("labeling/scaleMin", "")
            # self._vectorlayer.setCustomProperty("labeling/scaleMax", "")
            #number formatting
        #return self._vectorlayer

    def getLayer(self):
        return self._vectorlayer



