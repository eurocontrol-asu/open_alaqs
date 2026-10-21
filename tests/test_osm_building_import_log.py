"""OSM import: one log line reporting the building import.

`OpenAlaqsOsmImport._import_osm_data` logs how many buildings it added and
where their heights come from: the OSM feature's `height` column when it
has one, else the Buildings layer's default value (0 m from
LAYERS_CONFIG). With the bundled osmconf.ini the GDAL OSM driver does not
expose `height` as a column on the multipolygons layer (the tag ends up in
`other_tags`), so a building tagged height=12 still gets the default; the
log line says so.
"""

import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from qgis.core import Qgis, QgsProject, QgsVectorLayer  # noqa: E402
from qgis.testing import start_app  # noqa: E402

start_app()

from open_alaqs import openalaqsuitoolkit as oautk  # noqa: E402
from open_alaqs.enums import AlaqsLayerType  # noqa: E402
from open_alaqs.openalaqsdialog import OpenAlaqsOsmImport  # noqa: E402

OSMCONF = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "open_alaqs",
    "core",
    "utils",
    "osmconf.ini",
)

OSM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <node id="1" lat="51.9560" lon="4.4370"/>
  <node id="2" lat="51.9560" lon="4.4380"/>
  <node id="3" lat="51.9570" lon="4.4380"/>
  <node id="4" lat="51.9570" lon="4.4370"/>
  <node id="5" lat="51.9580" lon="4.4370"/>
  <node id="6" lat="51.9580" lon="4.4380"/>
  <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="building" v="office"/><tag k="height" v="12"/></way>
  <way id="11"><nd ref="4"/><nd ref="3"/><nd ref="6"/><nd ref="5"/><nd ref="4"/>
    <tag k="building" v="hotel"/></way>
  <way id="12"><nd ref="1"/><nd ref="2"/><nd ref="6"/><nd ref="1"/>
    <tag k="building" v="house"/></way>
</osm>
"""


@pytest.fixture
def buildings_layer():
    layer = QgsVectorLayer(
        "Polygon?crs=EPSG:4326&field=oid:integer&field=building_id:string"
        "&field=height:double&field=instudy:integer",
        "Buildings",
        "memory",
    )
    oautk.apply_layer_field_config(layer, AlaqsLayerType.BUILDING)
    QgsProject.instance().addMapLayer(layer)
    yield layer
    QgsProject.instance().removeMapLayer(layer.id())


def test_building_import_logs_count_and_height_source(
    buildings_layer, tmp_path, caplog
):
    osm_path = tmp_path / "b.osm"
    osm_path.write_text(OSM_XML)
    polygons = QgsVectorLayer(
        f"{osm_path}|layername=multipolygons|option:CONFIG_FILE={OSMCONF}",
        "multipolygons",
        "ogr",
    )
    assert polygons.isValid()
    empty = QgsVectorLayer("Point?crs=EPSG:4326", "empty", "memory")

    with caplog.at_level(logging.INFO):
        OpenAlaqsOsmImport._import_osm_data(
            None,
            {
                Qgis.GeometryType.Point: empty,
                Qgis.GeometryType.Line: empty,
                Qgis.GeometryType.Polygon: polygons,
            },
        )

    # office + hotel match the building filters, house does not
    assert buildings_layer.featureCount() == 2
    lines = [r.getMessage() for r in caplog.records if "OSM import:" in r.getMessage()]
    assert lines == [
        'OSM import: 2 building(s) added to layer "Buildings"; height from the '
        "OSM height tag for 0, the layer default (0 m) for 2."
    ]
    heights = sorted(f["height"] for f in buildings_layer.getFeatures())
    assert heights == [0, 0]


def test_null_osm_height_is_not_counted_nor_written(buildings_layer, caplog):
    """An OSM source with a `height` column (a custom osmconf.ini): a NULL
    height is a NULL QVariant, not None. It was counted as "from the OSM
    height tag" and written over the layer default; it is now skipped."""
    from qgis.core import QgsFeature, QgsGeometry
    from qgis.PyQt.QtCore import QVariant

    polygons = QgsVectorLayer(
        "Polygon?crs=EPSG:4326&field=full_id:string&field=building:string"
        "&field=height:double",
        "multipolygons",
        "memory",
    )
    features = []
    for i, (full_id, height) in enumerate([("w10", 12.0), ("w11", None)]):
        f = QgsFeature(polygons.fields())
        x = 4.437 + 0.001 * i
        f.setGeometry(
            QgsGeometry.fromWkt(
                f"POLYGON(({x} 51.956, {x + 0.001} 51.956, {x + 0.001} 51.957, "
                f"{x} 51.957, {x} 51.956))"
            )
        )
        f["full_id"] = full_id
        f["building"] = "office"
        f["height"] = height
        features.append(f)
    assert polygons.dataProvider().addFeatures(features)[0]
    null_height = [
        f.attributeMap().get("height")
        for f in polygons.getFeatures()
        if f["full_id"] == "w11"
    ][0]
    assert null_height is not None and isinstance(null_height, QVariant)
    empty = QgsVectorLayer("Point?crs=EPSG:4326", "empty", "memory")

    with caplog.at_level(logging.INFO):
        OpenAlaqsOsmImport._import_osm_data(
            None,
            {
                Qgis.GeometryType.Point: empty,
                Qgis.GeometryType.Line: empty,
                Qgis.GeometryType.Polygon: polygons,
            },
        )

    lines = [r.getMessage() for r in caplog.records if "OSM import:" in r.getMessage()]
    assert lines == [
        'OSM import: 2 building(s) added to layer "Buildings"; height from the '
        "OSM height tag for 1, the layer default (0 m) for 1."
    ]
    heights = {f["building_id"]: f["height"] for f in buildings_layer.getFeatures()}
    assert heights == {"w10": 12.0, "w11": 0}
