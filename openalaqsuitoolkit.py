import os

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDataSourceUri,
    QgsEditFormConfig,
    QgsEditorWidgetSetup,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPoint,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)
from qgis.PyQt import QtWidgets

from open_alaqs.alaqs_config import LAYERS_CONFIG
from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.enums import ALAQSLayer

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
            except Exception:
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
            except Exception:
                value = str(ui_element.text()).strip()
            try:
                if value == "" or value is None:
                    raise Exception()
                value = int(value)
                color_ui_background(ui_element, "white")
                return value
            except Exception:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be an integer")
                return False

        elif var_type == "float":
            try:
                value = str(ui_element.currentText()).strip()
            except Exception:
                value = str(ui_element.text()).strip()
            try:
                if value == "" or value is None:
                    raise Exception()
                value = float(value)
                color_ui_background(ui_element, "white")
                return value
            except Exception:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be a float")
                return False
    except Exception:
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


def load_spatialite_layer(
    iface,
    database_path: str,
    alaqs_layer: ALAQSLayer,
):
    """
    This function is used to load a new layer into QGIS

    :param database_path: the file path to the current spatialite database to be
     loaded
    :param alaqs_layer: the type of layer we are trying to load
    """
    project = QgsProject.instance()
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    uri = QgsDataSourceUri()
    uri.setDatabase(database_path)

    layer_config = LAYERS_CONFIG[alaqs_layer]

    schema = ""
    geom_column = "geometry"
    uri.setDataSource(schema, layer_config["table_name"], geom_column)
    layer = QgsVectorLayer(uri.uri(), layer_config["name"], "spatialite")

    lconfig = layer.editFormConfig()
    lconfig.setInitCodeSource(QgsEditFormConfig.PythonInitCodeSource.CodeSourceFile)
    lconfig.setUiForm(os.path.join(plugin_dir, "ui", layer_config["ui_filename"]))
    lconfig.setInitFilePath(os.path.join(plugin_dir, "ui", layer_config["py_filename"]))
    lconfig.setInitFunction("form_open")
    layer.setEditFormConfig(lconfig)
    layer.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

    instudy_idx = layer.fields().indexFromName("instudy")
    if instudy_idx != -1:
        editor_widget_setup = QgsEditorWidgetSetup(
            "ValueMap", {"map": {"1": 1, "0": 0}}
        )
        layer.setEditorWidgetSetup(instudy_idx, editor_widget_setup)

    if not layer.isValid():
        QtWidgets.QMessageBox.information(
            iface.mainWindow() if iface and iface.mainWindow() else None,
            "Info",
            "That is not a valid layer...",
        )

    set_layer_style(layer, alaqs_layer)

    project.addMapLayer(layer, False)

    tree_root = project.layerTreeRoot()
    tree_root.addLayer(layer)


def load_basemap_layers(project: QgsProject = QgsProject.instance()) -> None:
    """Loads a preset of online XYZ basemap layers to the current project. Does nothing if "Basemaps" layer group already exists in the layer tree."""
    xyz_layer_definitions = {
        "Google Satellite": "https://mt1.google.com/vt/lyrs%3Ds%26x%3D{x}%26y%3D{y}%26z%3D{z}",
        "Google Maps": "https://mt1.google.com/vt/lyrs%3Dm%26x%3D{x}%26y%3D{y}%26z%3D{z}",
        "OpenStreetMap Standard": "http://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png",
        "Esri Gray (light)": "http://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/%7Bz%7D/%7By%7D/%7Bx%7D",
        "Esri Imagery": "https://server.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/tile/%7Bz%7D/%7By%7D/%7Bx%7D",
    }

    tree_root = QgsProject.instance().layerTreeRoot()
    basemaps_group = tree_root.findGroup("Basemaps")

    if basemaps_group:
        return

    basemaps_group = tree_root.addGroup("Basemaps")
    basemaps_group.setIsMutuallyExclusive(True)

    for layer_name, layer_source in xyz_layer_definitions.items():
        rl = QgsRasterLayer(
            f"type=xyz&url={layer_source}",
            layer_name,
            "wms",
        )

        if rl.isValid():
            project.addMapLayer(rl, False)
            basemaps_group.addLayer(rl)
        else:
            logger.debug(
                f'Invalid layer "{layer_name}" with datasource "{layer_source}"'
            )


def set_layer_style(layer: QgsVectorLayer, alaqs_layer: ALAQSLayer):
    """
    This function adds styling to the giiven layer.
    :param layer: The vector layer that is to be styled
    :param alaqs_layer: The type of the ALAQS layer
    """
    config = LAYERS_CONFIG[alaqs_layer]

    try:
        layer.setCustomProperty("labeling", "pal")
        layer.setCustomProperty("labeling/enabled", config["label_enabled"])
        layer.setCustomProperty("labeling/fontFamily", config["label_font_family"])
        layer.setCustomProperty("labeling/fontSize", config["label_font_size"])
        layer.setCustomProperty("labeling/placement", config["label_position"])
        layer.setCustomProperty("labeling/fieldName", "source_id")

        props = {}

        if config["fill_color"] is not None:
            props["color"] = config["fill_color"]
            props["style"] = "solid"

        if config["border_color"] is not None:
            props["color_border"] = config["border_color"]
            props["style_border"] = "solid"

        if config["line_width"] is not None:
            props["width"] = config["line_width"]

        if config["line_color"] is not None:
            props["color"] = config["line_color"]

        if layer.geometryType() == Qgis.GeometryType.Polygon:
            symbol = QgsFillSymbol.createSimple(props)
        elif layer.geometryType() == Qgis.GeometryType.Line:
            symbol = QgsLineSymbol.createSimple(props)
        elif layer.geometryType() == Qgis.GeometryType.Point:
            symbol = QgsMarkerSymbol.createSimple(props)
        else:
            raise NotImplementedError("Unknown layer geometry type: {}")

        layer.setRenderer(QgsSingleSymbolRenderer(symbol))

        logger.debug("Styles applied to Area layer")
    except Exception as e:
        logger.error(set_layer_style.__name__, Exception, e)


def load_layers(iface, database_path):
    for alaqs_layer in ALAQSLayer:
        load_spatialite_layer(iface, database_path, alaqs_layer)


def delete_alaqs_layers(iface):
    project = QgsProject.instance()
    layer_names = [
        "Tracks",
        "Taxiways",
        "Runways",
        "Roadways",
        "Point Sources",
        "Parkings",
        "Gates",
        "Buildings",
        "Area Sources",
    ]

    layers = [layer for layer in project.mapLayers().values()]

    for layer in layers:
        layer_name = layer.name()
        if layer_name in layer_names:
            project.removeMapLayers([layer.id()])

    layer_root = project.layerTreeRoot()
    layer_root.removeChildNode(layer_root.findGroup("Basemaps"))


def set_default_zoom(canvas, lat, lon):
    try:
        scale = 5000
        crs_src = QgsCoordinateReferenceSystem("EPSG:4326")
        crs_dest = QgsCoordinateReferenceSystem("EPSG:3857")
        xform = QgsCoordinateTransform(crs_src, crs_dest)

        arp = xform.transform(QgsPoint(float(lon), float(lat)))
        rect = QgsRectangle(
            float(arp[0]) - scale,
            float(arp[1]) - scale,
            float(arp[0]) + scale,
            float(arp[1]) + scale,
        )
        canvas.setExtent(rect)
        canvas.refresh()
        return None
    except Exception:
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

            except Exception:
                pass

        # Select those features
        layer.setSelectedFeatures(to_select)

    except Exception as e:
        logger.error(set_selected_feature.__name__, Exception, e)
