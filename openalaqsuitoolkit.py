import os

from qgis.PyQt import QtWidgets
from qgis.core import *

from open_alaqs.alaqs_config import PARKING_LABEL_ENABLED, AREA_LABEL_ENABLED, \
    AREA_LABEL_FONT, AREA_LABEL_FONT_SIZE, AREA_LABEL_POSITION, \
    AREA_FILL_COLOR, AREA_BORDER_COLOR, BUILDING_LABEL_ENABLED, \
    BUILDING_LABEL_FONT, BUILDING_LABEL_FONT_SIZE, BUILDING_LABEL_POSITION, \
    BUILDING_FILL_COLOR, BUILDING_BORDER_COLOR, GATE_LABEL_ENABLED, \
    GATE_LABEL_FONT, GATE_LABEL_FONT_SIZE, GATE_LABEL_POSITION, \
    GATE_FILL_COLOR, GATE_BORDER_COLOR, PARKING_LABEL_FONT, \
    PARKING_LABEL_FONT_SIZE, PARKING_LABEL_POSITION, PARKING_FILL_COLOR, \
    PARKING_BORDER_COLOR, ROADWAY_LABEL_ENABLED, ROADWAY_LABEL_FONT, \
    ROADWAY_LABEL_FONT_SIZE, ROADWAY_LABEL_POSITION, ROADWAY_LINE_WIDTH, \
    ROADWAY_LINE_COLOR, TAXIWAY_LABEL_ENABLED, TAXIWAY_LABEL_FONT, \
    TAXIWAY_LABEL_FONT_SIZE, TAXIWAY_LABEL_POSITION, TAXIWAY_LINE_WIDTH, \
    TAXIWAY_LINE_COLOR, RUNWAY_LABEL_ENABLED, RUNWAY_LABEL_FONT, \
    RUNWAY_LABEL_FONT_SIZE, RUNWAY_LABEL_POSITION, RUNWAY_LINE_COLOR, \
    RUNWAY_LINE_WIDTH
from open_alaqs.alaqs_core.alaqslogging import get_logger

logger = get_logger(__name__)


def validate_field(ui_element, var_type):
    """
    Evaluates the text in a UI text field, returning the value if it is valid,
    or returning none and highlighting the field red if it is incorrect.

    :param ui_element:
    :return: value if field is correct, False if value is not correct
    """
    try:
        if var_type == "str":
            try:
                value = str(ui_element.currentText()).strip()
            except:
                value = str(ui_element.text()).strip()
            if value == "":
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be a string")
                return False
            else:
                color_ui_background(ui_element, "white")
                return value

        elif var_type == "int":
            try:
                value = str(ui_element.currentText()).strip()
            except:
                value = str(ui_element.text()).strip()
            try:
                if value == "" or value is None:
                    raise Exception()
                value = int(value)
                color_ui_background(ui_element, "white")
                return value
            except:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be an integer")
                return False

        elif var_type == "float":
            try:
                value = str(ui_element.currentText()).strip()
            except:
                value = str(ui_element.text()).strip()
            try:
                if value == "" or value is None:
                    raise Exception()
                value = float(value)
                color_ui_background(ui_element, "white")
                return value
            except:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be a float")
                return False
    except:
        return False


def color_ui_background(ui_element, color):
    """
    This function changes the background color of a UI object. This is used to
    alert users to incorrect values.

    :param ui_element:
    :param color:
    """
    if color == "red":
        ui_element.setStyleSheet("background-color: rgba(255, 107, 107, 150);")
    elif color == "white":
        ui_element.setStyleSheet("background-color: rgba(255, 255, 255, 255);")
    else:
        pass


def add_spatialite_layer(iface, database_path, table_name, display_name,
                         edit_form, edit_py, edit_init):
    """
    This function is used to load a new layer into QGIS

    :param database_path: the file path to the current spatialite database to be
     loaded
    :param table_name: the name of the feature table from which geometry is
     being loaded
    :param display_name: the name to be attached to the layer when loaded
    :param edit_form: the file name of the ui associated with this layer
    :param edit_init: the file name of the py file that controls the form
     validation and actions add_spatialite_layer(iface, database_path,
      "shapes_point_sources", "Point Sources", 'ui_point_sources.ui',
       'ui_point_sources.py', 'ui_point_sources.form_open')
    """

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    uri = QgsDataSourceUri()  # QGIS3
    uri.setDatabase(database_path)

    schema = ''
    geom_column = 'geometry'
    uri.setDataSource(schema, table_name, geom_column)
    layer = QgsVectorLayer(uri.uri(), display_name, 'spatialite')

    lconfig = layer.editFormConfig()
    lconfig.setInitCodeSource(QgsEditFormConfig.PythonInitCodeSource.File)
    lconfig.setUiForm(os.path.join(plugin_dir, 'ui', edit_form))
    lconfig.setInitFilePath(os.path.join(plugin_dir, 'ui', edit_py))
    lconfig.setInitFunction(edit_init)
    layer.setEditFormConfig(lconfig)
    layer.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

    # By default the source is accounted for in the study - comment this part
    # or set to 0 to ignore
    # instudy_idx = layer.fieldNameIndex("instudy")
    # in QGIS3
    instudy_idx = layer.fields().indexFromName("instudy")
    if instudy_idx != -1:
        editor_widget_setup = QgsEditorWidgetSetup('ValueMap',
                                                   {'map': {u'1': 1, u'0': 0}})
        layer.setEditorWidgetSetup(instudy_idx, editor_widget_setup)

    if display_name == "Area Sources":
        style_area_sources(layer)
    elif display_name == "Buildings":
        style_buildings(layer)
    elif display_name == "Gates":
        style_gates(layer)
    elif display_name == "Parkings":
        style_parkings(layer)
    elif display_name == "Point Sources":
        style_point_sources(layer)
    elif display_name == "Roadways":
        style_roadways(layer)
    elif display_name == "Runways":
        style_runways(layer)
    elif display_name == "Taxiways":
        style_taxiways(layer)

    if not layer.isValid():
        QtWidgets.QMessageBox.information(
            iface.mainWindow() if iface and iface.mainWindow() else None,
            "Info", "That is not a valid layer...")
    # QgsMapLayerRegistry.instance().addMapLayers([layer])
    QgsProject.instance().addMapLayers([layer])


def style_area_sources(layer):
    """
    This function adds styling to the Area Source layer. Values come from
     alaqsconfig.py
    :param layer: The vector layer that is to be styled
    """
    try:
        layer.setCustomProperty("labeling", "pal")
        layer.setCustomProperty("labeling/enabled", AREA_LABEL_ENABLED)
        layer.setCustomProperty("labeling/fontFamily", AREA_LABEL_FONT)
        layer.setCustomProperty("labeling/fontSize", AREA_LABEL_FONT_SIZE)
        layer.setCustomProperty("labeling/placement", AREA_LABEL_POSITION)
        layer.setCustomProperty("labeling/fieldName", "source_id")

        props = {
            'color': AREA_FILL_COLOR,
            'style': 'solid',
            'color_border': AREA_BORDER_COLOR,
            'style_border': 'solid'
        }
        s = QgsFillSymbol.createSimple(props)
        layer.setRenderer(QgsSingleSymbolRenderer(s))

        logger.debug("Styles applied to Area layer")
    except Exception as e:
        logger.error(style_area_sources.__name__, Exception, e)


def style_buildings(layer):
    """
    This function adds styling to the Buildings layer. Values come from
     alaqsconfig.py
    :param layer: The vector layer that is to be styled
    """
    try:
        layer.setCustomProperty("labeling", "pal")
        layer.setCustomProperty("labeling/enabled", BUILDING_LABEL_ENABLED)
        layer.setCustomProperty("labeling/fontFamily", BUILDING_LABEL_FONT)
        layer.setCustomProperty("labeling/fontSize", BUILDING_LABEL_FONT_SIZE)
        layer.setCustomProperty("labeling/placement", BUILDING_LABEL_POSITION)
        layer.setCustomProperty("labeling/fieldName", "building_id")

        props = {
            'color': BUILDING_FILL_COLOR,
            'style': 'solid',
            'color_border': BUILDING_BORDER_COLOR,
            'style_border': 'solid'
        }
        s = QgsFillSymbol.createSimple(props)
        layer.setRenderer(QgsSingleSymbolRenderer(s))

        logger.debug("Styles applied to Buildings layer")
    except Exception as e:
        logger.error(style_buildings.__name__, Exception, e)


def style_gates(layer):
    """
    This function adds styling to the Gates layer. Values come from
     alaqsconfig.py
    :param layer: The vector layer that is to be styled
    """
    try:
        layer.setCustomProperty("labeling", "pal")
        layer.setCustomProperty("labeling/enabled", GATE_LABEL_ENABLED)
        layer.setCustomProperty("labeling/fontFamily", GATE_LABEL_FONT)
        layer.setCustomProperty("labeling/fontSize", GATE_LABEL_FONT_SIZE)
        layer.setCustomProperty("labeling/placement", GATE_LABEL_POSITION)
        layer.setCustomProperty("labeling/fieldName", "gate_id")

        props = {
            'color': GATE_FILL_COLOR,
            'style': 'solid',
            'color_border': GATE_BORDER_COLOR,
            'style_border': 'solid'
        }
        s = QgsFillSymbol.createSimple(props)
        layer.setRenderer(QgsSingleSymbolRenderer(s))

        logger.debug("Styles applied to Buildings layer")
    except Exception as e:
        logger.error(style_gates.__name__, Exception, e)


def style_parkings(layer):
    """
    This function adds styling to the Parking layer. Values come from
     alaqsconfig.py
    :param layer: The vector layer that is to be styled
    """
    try:
        layer.setCustomProperty("labeling", "pal")
        layer.setCustomProperty("labeling/enabled", PARKING_LABEL_ENABLED)
        layer.setCustomProperty("labeling/fontFamily", PARKING_LABEL_FONT)
        layer.setCustomProperty("labeling/fontSize", PARKING_LABEL_FONT_SIZE)
        layer.setCustomProperty("labeling/placement", PARKING_LABEL_POSITION)
        layer.setCustomProperty("labeling/fieldName", "parking_id")

        props = {
            'color': PARKING_FILL_COLOR,
            'style': 'solid',
            'color_border': PARKING_BORDER_COLOR,
            'style_border': 'solid'
        }
        s = QgsFillSymbol.createSimple(props)
        layer.setRenderer(QgsSingleSymbolRenderer(s))

        logger.debug("Styles applied to Parkings layer")
    except Exception as e:
        logger.error(style_parkings.__name__, Exception, e)


def style_point_sources(layer):
    """
    This function adds styling to the Point sources layer. Values come from
     alaqsconfig.py
    :param layer: The vector layer that is to be styled
    """
    try:
        layer.setCustomProperty("labeling", "pal")
        layer.setCustomProperty("labeling/enabled", "false")
        layer.setCustomProperty("labeling/fontFamily", "Arial")
        layer.setCustomProperty("labeling/fontSize", "10")
        layer.setCustomProperty("labeling/fieldName", "source_id")
        layer.setCustomProperty("labeling/placement", "2")
    except Exception as e:
        logger.error(style_point_sources.__name__, Exception, e)


def style_roadways(layer):
    """
    This function adds styling to the Roadways layer. Values come from
     alaqsconfig.py
    :param layer: The vector layer that is to be styled
    """
    try:
        layer.setCustomProperty("labeling", "pal")
        layer.setCustomProperty("labeling/enabled", ROADWAY_LABEL_ENABLED)
        layer.setCustomProperty("labeling/fontFamily", ROADWAY_LABEL_FONT)
        layer.setCustomProperty("labeling/fontSize", ROADWAY_LABEL_FONT_SIZE)
        layer.setCustomProperty("labeling/placement", ROADWAY_LABEL_POSITION)
        layer.setCustomProperty("labeling/fieldName", "roadway_id")

        props = {
            'width': ROADWAY_LINE_WIDTH,
            'color': ROADWAY_LINE_COLOR
        }
        s = QgsLineSymbol.createSimple(props)
        layer.setRenderer(QgsSingleSymbolRenderer(s))

        logger.debug("Styles applied to Roadways layer")
    except Exception as e:
        logger.error(style_roadways.__name__, Exception, e)


def style_taxiways(layer):
    """
    This function adds styling to the Taxiways layer. Values come from
     alaqsconfig.py
    :param layer: The vector layer that is to be styled
    """
    try:
        layer.setCustomProperty("labeling", "pal")
        layer.setCustomProperty("labeling/enabled", TAXIWAY_LABEL_ENABLED)
        layer.setCustomProperty("labeling/fontFamily", TAXIWAY_LABEL_FONT)
        layer.setCustomProperty("labeling/fontSize", TAXIWAY_LABEL_FONT_SIZE)
        layer.setCustomProperty("labeling/placement", TAXIWAY_LABEL_POSITION)
        layer.setCustomProperty("labeling/fieldName", "taxiway_id")

        props = {'width': TAXIWAY_LINE_WIDTH, 'color': TAXIWAY_LINE_COLOR}
        s = QgsLineSymbol.createSimple(props)
        layer.setRenderer(QgsSingleSymbolRenderer(s))

        logger.debug("Styles applied to Taxiways layer")
    except Exception as e:
        logger.error(style_taxiways.__name__, Exception, e)


def style_runways(layer):
    """
    This function adds styling to the Runways layer. Values come from
     alaqsconfig.py
    :param layer: The vector layer that is to be styled
    """
    try:
        layer.setCustomProperty("labeling", "pal")
        layer.setCustomProperty("labeling/enabled", RUNWAY_LABEL_ENABLED)
        layer.setCustomProperty("labeling/fontFamily", RUNWAY_LABEL_FONT)
        layer.setCustomProperty("labeling/fontSize", RUNWAY_LABEL_FONT_SIZE)
        layer.setCustomProperty("labeling/placement", RUNWAY_LABEL_POSITION)
        layer.setCustomProperty("labeling/fieldName", "runway_id")

        props = {'width': RUNWAY_LINE_WIDTH, 'color': RUNWAY_LINE_COLOR}
        s = QgsLineSymbol.createSimple(props)
        layer.setRenderer(QgsSingleSymbolRenderer(s))

        logger.debug("Styles applied to Runways layer")
    except Exception as e:
        logger.error(style_runways.__name__, Exception, e)


def load_layers(iface, database_path):
    add_spatialite_layer(iface, database_path, "shapes_point_sources",
                         "Point Sources", 'ui_point_sources.ui',
                         'ui_point_sources.py', 'form_open')
    add_spatialite_layer(iface, database_path, "shapes_taxiways", "Taxiways",
                         'ui_taxiways.ui', 'ui_taxiways.py',
                         'form_open')
    add_spatialite_layer(iface, database_path, "shapes_runways", "Runways",
                         'ui_runways.ui', 'ui_runways.py', 'form_open')
    add_spatialite_layer(iface, database_path, "shapes_roadways", "Roadways",
                         'ui_roadways.ui', 'ui_roadways.py',
                         'form_open')
    add_spatialite_layer(iface, database_path, "shapes_parking", "Parkings",
                         'ui_parkings.ui', 'ui_parkings.py',
                         'form_open')
    add_spatialite_layer(iface, database_path, "shapes_gates", "Gates",
                         'ui_gates.ui', 'ui_gates.py', 'form_open')
    add_spatialite_layer(iface, database_path, "shapes_buildings", "Buildings",
                         'ui_buildings.ui', 'ui_buildings.py',
                         'form_open')
    add_spatialite_layer(iface, database_path, "shapes_area_sources",
                         "Area Sources", 'ui_area_sources.ui',
                         'ui_area_sources.py', 'form_open')
    add_spatialite_layer(iface, database_path, "shapes_tracks", "Tracks",
                         'ui_tracks.ui', 'ui_tracks.py', 'form_open')


def delete_alaqs_layers(iface):
    layer_names = ["Tracks", "Taxiways", "Runways", "Roadways", "Point Sources",
                   "Parkings", "Gates", "Buildings", "Area Sources"]

    # QGIS2
    # layers = iface.legendInterface().layers()
    # QGIS3
    layers = [layer for layer in QgsProject.instance().mapLayers().values()]

    for layer in layers:
        layer_name = layer.name()
        if layer_name in layer_names:
            # QgsMapLayerRegistry.instance().removeMapLayers([layer.id()])
            QgsProject.instance().removeMapLayers([layer.id()])


def set_default_zoom(canvas, lat, lon):
    try:
        scale = 5000
        crs_src = QgsCoordinateReferenceSystem("EPSG:4326")
        crs_dest = QgsCoordinateReferenceSystem("EPSG:3857")
        xform = QgsCoordinateTransform(crs_src, crs_dest)

        arp = xform.transform(QgsPoint(float(lon), float(lat)))
        rect = QgsRectangle(float(arp[0]) - scale, float(arp[1]) - scale,
                            float(arp[0]) + scale, float(arp[1]) + scale)
        canvas.setExtent(rect)
        canvas.refresh()
        return None
    except:
        pass


def get_layer(iface, layer_name):
    try:
        # layers = iface.legendInterface().layers() - QGIS2
        layers = [layer for layer in QgsProject.instance().mapLayers().values()]

        for layer in layers:
            if layer.name() == layer_name:
                return layer
        return None
    except Exception as e:
        logger.error(get_layer.__name__, Exception, e)


def set_selected_feature(layer, features):
    try:
        # A blank list to hold the ID of the features we want selected
        to_select = []

        # We make this layer active for the moment
        layer.select([])

        # Loop over features and record the ID of those we're highlighting
        for feature in layer:
            try:
                if len(feature.attributes()) > 1:
                    # generic index for name
                    attribute_name = str(feature.attributes()[1])
                    if attribute_name in features:
                        to_select.append(feature.id())
                else:
                    # raise Exception(str(feature.attributes()))
                    pass

            except Exception as e:
                pass

        # Select those features
        layer.setSelectedFeatures(to_select)

    except Exception as e:
        logger.error(set_selected_feature.__name__, Exception, e)
