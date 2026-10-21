import os
from pathlib import Path, PurePath
from typing import Optional

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsAttributeTableConfig,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDataSourceUri,
    QgsDefaultValue,
    QgsEditFormConfig,
    QgsEditorWidgetSetup,
    QgsFillSymbol,
    QgsGeometry,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsValueMapFieldFormatter,
    QgsVectorLayer,
)
from qgis.gui import QgsFileWidget, QgsMapCanvas
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QLocale

from open_alaqs.alaqs_config import LAYERS_CONFIG
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.utils.qt import color_ui_background
from open_alaqs.enums import AlaqsLayerType

logger = get_logger(__name__)


def is_empty_text(text) -> bool:
    """True for an empty text or the QGIS NULL representation ("NULL"),
    which QGIS writes into a form line edit for a NULL attribute."""
    text = "" if text is None else str(text).strip()
    return text == "" or text == QgsApplication.nullRepresentation()


def is_null_value(value) -> bool:
    """True for None, a NULL QVariant and empty or NULL-representation text."""
    if value is None:
        return True
    if hasattr(value, "isNull") and value.isNull():
        return True
    return is_empty_text(value)


def parse_number(text: str, integer: bool):
    """Parse a number as QGIS shows it in a form, raising ValueError.

    QGIS writes numbers into the form with the locale's separators, for
    example 20000 as "20,000" (English) or "20.000" (German), and 30.3 as
    "30,3" under European locales (GitHub #159). Integers are read with the
    locale first, then plain Python syntax. Decimals are read the way QGIS
    saves them (QgsField.convertCompatible): plain "C" syntax first, so
    "0.125" stays 0.125 under a German or Dutch locale (where the locale
    alone would read the dot as a group separator and give 125), then the
    locale, then the tolerant convertToFloat.
    """
    locale = QLocale()
    if integer:
        number, ok = locale.toLongLong(text)
        if ok:
            return int(number)
        return int(text)
    try:
        return float(text)
    except ValueError:
        pass
    number, ok = locale.toDouble(text)
    if ok:
        return number
    from open_alaqs.core.tools.conversion import convertToFloat

    converted = convertToFloat(text, default=None)
    if converted is None:
        raise ValueError(f"cannot parse {text!r} as a number")
    return converted


def validate_field(ui_element, var_type):
    """
    Evaluates the text in a UI text field, returning the value if it is valid,
    or returning none and highlighting the field red if it is incorrect.

    :param ui_element:
    :return: value if field is correct, False if value is not correct

    TODO OPENGIS.ch: Do not return `False` when invalid, but return `None`. In the future one might want to validate boolean fields too.
    """
    if isinstance(ui_element, QtWidgets.QLineEdit):
        value = ui_element.text()
    elif isinstance(ui_element, QtWidgets.QComboBox):
        value = ui_element.currentText()
    elif isinstance(ui_element, QtWidgets.QDateTimeEdit):
        value = ui_element.dateTime().toString("yyyy-MM-dd HH:mm:ss")
    elif isinstance(ui_element, QgsFileWidget):
        value = ui_element.filePath()
    else:
        raise NotImplementedError(
            f"UI elements of type {type(ui_element)} are not supported for validation!"
        )

    value = value.strip()

    # QGIS shows a NULL attribute as the NULL representation text ("NULL")
    if is_empty_text(value):
        color_ui_background(ui_element, "red")
        ui_element.setToolTip("This value should not be empty")

        return False

    try:
        if var_type == "str":
            value = str(value)
        elif var_type == "int":
            value = parse_number(value, integer=True)
        elif var_type == "float":
            value = parse_number(value, integer=False)

        color_ui_background(ui_element, None)

        return value
    except Exception:
        color_ui_background(ui_element, "red")
        if var_type == "int":
            ui_element.setToolTip("This value should be a whole number")
        else:
            ui_element.setToolTip("This value should be a number")
        return False


def load_spatialite_layer(
    iface,
    database_path: str,
    alaqs_layer: AlaqsLayerType,
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
    if not layer.isValid():
        QtWidgets.QMessageBox.information(
            iface.mainWindow() if iface and iface.mainWindow() else None,
            "Info",
            f'Layer "{layer.name()}" is not valid! Error: {layer.error()}',
        )
        return

    lconfig = layer.editFormConfig()
    lconfig.setInitCodeSource(QgsEditFormConfig.PythonInitCodeSource.CodeSourceFile)
    lconfig.setUiForm(os.path.join(plugin_dir, "ui", layer_config["ui_filename"]))
    lconfig.setInitFilePath(os.path.join(plugin_dir, "ui", layer_config["py_filename"]))
    lconfig.setInitFunction("form_open")
    layer.setEditFormConfig(lconfig)
    layer.setCrs(QgsCoordinateReferenceSystem.fromEpsgId(3857))

    apply_layer_field_config(layer, alaqs_layer)

    set_layer_style(layer, alaqs_layer)

    project.addMapLayer(layer, False)

    tree_root = project.layerTreeRoot()
    tree_root.addLayer(layer)


CHECKBOX_WIDGET_CONFIG = {
    "CheckedState": "1",
    "UncheckedState": "0",
    # The attribute table of QGIS 3.34 shows a check-box field as text, not
    # as a tick: "true" / "false" (0) reads better than the stored "1" / "0".
    "TextDisplayMethod": 0,
}


def _sqlite_read_only_uri(path: PurePath) -> str:
    """SQLite URI that opens the absolute `path` read-only.

    The path is percent-encoded (as_uri), so a "#", "?" or "%" in a folder
    or file name is read as part of the name, not as a URI fragment, query
    or escape. A Windows UNC path (as_uri gives "file://server/share/...")
    is written "file:////server/share/...": SQLite rejects a URI authority
    other than "localhost", and reads the path "//server/share/..." as UNC.
    """
    uri = path.as_uri()
    if uri.startswith("file://") and not uri.startswith("file:///"):
        uri = "file:////" + uri[len("file://") :]
    return uri + "?mode=ro"


def _study_values(database_path: str, sql: str) -> list[str]:
    """First column of `sql` on the study, as text; [] when the table or
    the file is missing (older studies, memory layers in tests)."""
    import sqlite3

    try:
        if not database_path:
            return []
        uri = _sqlite_read_only_uri(Path(database_path).resolve())
        con = sqlite3.connect(uri, uri=True)
        try:
            rows = con.execute(sql).fetchall()
        finally:
            con.close()
    except (sqlite3.Error, OSError, ValueError):
        return []
    return [str(r[0]) for r in rows if r[0] is not None and str(r[0]).strip()]


def _runway_directions(database_path: str) -> list[str]:
    directions = []
    for runway_id in _study_values(
        database_path,
        "SELECT runway_id FROM shapes_runways ORDER BY runway_id COLLATE NOCASE",
    ):
        directions += [d.strip() for d in runway_id.split("/") if d.strip()]
    return directions


def _profile_names(table: str):
    def names(database_path: str) -> list[str]:
        return ["default"] + _study_values(
            database_path,
            f"SELECT profile_name FROM {table} ORDER BY profile_name COLLATE NOCASE",
        )

    return names


# Lists read from the study for the "from" key of a value map
VALUE_MAP_SOURCES = {
    "hour_profiles": _profile_names("user_hour_profile"),
    "day_profiles": _profile_names("user_day_profile"),
    "month_profiles": _profile_names("user_month_profile"),
    "stationary_categories": lambda db: _study_values(
        db,
        "SELECT category_name FROM default_stationary_category "
        "ORDER BY category_name COLLATE NOCASE",
    ),
    "stationary_types": lambda db: _study_values(
        db, "SELECT description FROM default_stationary_ef ORDER BY oid"
    ),
    "runway_directions": _runway_directions,
}


def value_map_values(layer: QgsVectorLayer, idx: int, spec: dict) -> list[str]:
    """The values of a value-map field: the fixed ones, those read from
    the study, then any other value already stored in the layer (so QGIS
    never shows a stored value as "(value)"), without duplicates."""
    values = list(spec.get("values", []))
    source = spec.get("from")
    if source:
        database = QgsDataSourceUri(layer.source()).database()
        values += VALUE_MAP_SOURCES[source](database)
    stored = sorted(str(v) for v in layer.uniqueValues(idx) if not is_null_value(v))
    unique = []
    for value in values + stored:
        if value not in unique:
            unique.append(value)
    return unique


def value_map_config(values: list[str], spec: dict) -> dict:
    """ValueMap editor config: the text shown is the stored value. NULL is
    listed first, shown as "null_text" (empty by default), so a NULL value
    is not shown as "(NULL)"; the forms reject an empty choice where a
    value is required."""
    entries = [{spec.get("null_text", ""): QgsValueMapFieldFormatter.NULL_VALUE}]
    entries += [{value: value} for value in values]
    return {"map": entries}


def add_combo_values(combo, values) -> None:
    """Add `values` missing from a value-map combo box (for example a
    profile or runway created after the study was opened). Items are added
    with the value as data, as QGIS's value-map widget expects, so they are
    selected and saved like the configured ones; nothing is removed."""
    if combo is None:
        return
    for value in values:
        if value is None or str(value).strip() == "":
            continue
        if combo.findData(str(value)) == -1:
            combo.addItem(str(value), str(value))


def update_ok_button(button_box, checks, alaqs_layer=None, extra=()) -> bool:
    """Enable the form's OK button only when every check passed.

    checks: (widget, result) pairs, result as returned by validate_field
    (False when invalid). extra: display names of other failed checks.
    The disabled button's tooltip names the fields to fix. Returns True
    when the form is valid.
    """
    invalid = []
    for widget, result in checks:
        if isinstance(result, bool) and not result:
            name = widget.objectName()
            if alaqs_layer is not None:
                from open_alaqs.alaqs_config import field_alias

                name = field_alias(alaqs_layer, name)
            invalid.append(name)
    invalid += list(extra)
    ok = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    ok.blockSignals(False)
    ok.setEnabled(not invalid)
    ok.setToolTip("" if not invalid else "Missing or invalid: " + ", ".join(invalid))
    return not invalid


def apply_layer_field_config(layer: QgsVectorLayer, alaqs_layer: AlaqsLayerType):
    """Apply the `fields` settings of LAYERS_CONFIG to a loaded layer.

    Sets, per column: the alias (attribute-table header and the name used
    in the documentation), the default value expression for new features,
    the read-only flag, the check-box widget of the in-study flag, and the
    attribute-table column order and visibility. The layers are rebuilt
    from the .alaqs file every time a study is opened, so this runs at each
    load. Columns missing from an older study are skipped.
    """
    fields_config = LAYERS_CONFIG[alaqs_layer].get("fields", {})
    if not fields_config:
        return

    fields = layer.fields()
    form_config = layer.editFormConfig()
    for name, spec in fields_config.items():
        idx = fields.indexFromName(name)
        if idx == -1:
            continue
        layer.setFieldAlias(idx, spec["alias"])
        if spec.get("default") is not None:
            layer.setDefaultValueDefinition(idx, QgsDefaultValue(spec["default"]))
        form_config.setReadOnly(idx, bool(spec.get("read_only")))
        if spec.get("widget") == "checkbox":
            layer.setEditorWidgetSetup(
                idx, QgsEditorWidgetSetup("CheckBox", dict(CHECKBOX_WIDGET_CONFIG))
            )
        elif spec.get("widget") == "value_map":
            values = value_map_values(layer, idx, spec.get("value_map", {}))
            layer.setEditorWidgetSetup(
                idx,
                QgsEditorWidgetSetup(
                    "ValueMap", value_map_config(values, spec["value_map"])
                ),
            )
    layer.setEditFormConfig(form_config)

    table_config = layer.attributeTableConfig()
    table_config.update(layer.fields())
    columns = list(table_config.columns())
    configured = []
    for name, spec in fields_config.items():
        for column in columns:
            if (
                column.name == name
                and column.type == QgsAttributeTableConfig.Type.Field
            ):
                column.hidden = bool(spec.get("hidden_in_table"))
                configured.append(column)
                columns.remove(column)
                break
    # Columns not in the configuration (for example the actions column)
    # keep their relative order after the configured ones.
    table_config.setColumns(configured + columns)
    layer.setAttributeTableConfig(table_config)


def load_basemap_layers(project: Optional[QgsProject] = None) -> None:
    """Loads a preset of online XYZ basemap layers to the current project. Does nothing if "Basemaps" layer group already exists in the layer tree.

    Note on `project=None` + internal resolution: the previous signature
    was `project: QgsProject = QgsProject.instance()` which evaluated the
    singleton at function-definition time (i.e. at module import).
    Python evaluates default arguments once, at def time, so importing
    this module before `QgsApplication.initQgis()` has completed caused
    the incomplete singleton to be captured. A side effect was that
    QGIS's WKT-to-authid resolver could no longer map CRS WKTs read from
    GPKG files to their EPSG codes — a confusing late-binding corruption
    that surfaced in test_emission_calculation's CRS comparison. Using
    `None` as the sentinel and resolving inside the body avoids that.
    """
    if project is None:
        project = QgsProject.instance()
    xyz_layer_definitions = {
        "Google Satellite": "https://mt1.google.com/vt/lyrs%3Ds%26x%3D{x}%26y%3D{y}%26z%3D{z}",
        "Google Maps": "https://mt1.google.com/vt/lyrs%3Dm%26x%3D{x}%26y%3D{y}%26z%3D{z}",
        "OpenStreetMap Standard": "https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png",
        "Esri Gray (light)": "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/%7Bz%7D/%7By%7D/%7Bx%7D",
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


def set_layer_style(layer: QgsVectorLayer, alaqs_layer: AlaqsLayerType):
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
    for alaqs_layer in AlaqsLayerType:
        load_spatialite_layer(iface, database_path, alaqs_layer)


def get_alaqs_layer(layer_type: AlaqsLayerType) -> Optional[QgsVectorLayer]:
    layer_config = LAYERS_CONFIG[layer_type]
    matching_layers = QgsProject.instance().mapLayersByName(layer_config["name"])

    if len(matching_layers) != 1:
        return None

    return matching_layers[0]


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
    layer_root.removeChildNode(layer_root.findGroup("OpenStreetMap Layers"))


def set_default_zoom(canvas: QgsMapCanvas, lat: float, lon: float) -> None:
    MAP_SCALE = 5000

    project = QgsProject.instance()
    crs_src = QgsCoordinateReferenceSystem.fromEpsgId(4326)
    crs_tranform = QgsCoordinateTransform(crs_src, project.crs(), project)

    geom = QgsGeometry.fromPointXY(QgsPointXY(lon, lat))
    geom.transform(crs_tranform)
    transformed_point = geom.asPoint()

    rect = QgsRectangle(
        float(transformed_point.x()) - MAP_SCALE,
        float(transformed_point.y()) - MAP_SCALE,
        float(transformed_point.x()) + MAP_SCALE,
        float(transformed_point.y()) + MAP_SCALE,
    )
    canvas.setExtent(rect)
    canvas.refresh()


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
