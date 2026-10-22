"""OSM import: commercial buildings and duplicate gate names.

1. The building filter had the tag value "commerical", so OSM
   building=commercial was never in the Overpass query nor matched by the
   local filter of `OpenAlaqsOsmImport._import_osm_data`.
2. An OSM apron `ref` can give a gate name already in the Gates layer (or
   repeated in the import). The import keeps every feature as it is and
   logs one warning listing those names.
"""

import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from qgis.core import (  # noqa: E402
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)
from qgis.testing import start_app  # noqa: E402

start_app()

from open_alaqs import openalaqsuitoolkit as oautk  # noqa: E402
from open_alaqs.alaqs_config import LAYERS_CONFIG  # noqa: E402
from open_alaqs.core.utils.osm import get_query_body  # noqa: E402
from open_alaqs.enums import AlaqsLayerType  # noqa: E402
from open_alaqs.openalaqsdialog import (  # noqa: E402
    OpenAlaqsOsmImport,
    _osm_duplicate_gate_message,
)

OSMCONF = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "open_alaqs",
    "core",
    "utils",
    "osmconf.ini",
)

NODES = """
  <node id="1" lat="51.9560" lon="4.4370"/>
  <node id="2" lat="51.9560" lon="4.4380"/>
  <node id="3" lat="51.9570" lon="4.4380"/>
  <node id="4" lat="51.9570" lon="4.4370"/>
  <node id="5" lat="51.9580" lon="4.4370"/>
  <node id="6" lat="51.9580" lon="4.4380"/>
  <node id="7" lat="51.9590" lon="4.4370"/>
  <node id="8" lat="51.9590" lon="4.4380"/>
"""


def _osm(tmp_path, ways):
    p = tmp_path / "t.osm"
    p.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<osm version="0.6" generator="test">{NODES}{ways}</osm>\n'
    )
    layer = QgsVectorLayer(
        f"{p}|layername=multipolygons|option:CONFIG_FILE={OSMCONF}",
        "multipolygons",
        "ogr",
    )
    assert layer.isValid()
    return layer


def _way(way_id, nodes, tags):
    nds = "".join(f'<nd ref="{n}"/>' for n in nodes + nodes[:1])
    tg = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items())
    return f'<way id="{way_id}">{nds}{tg}</way>'


def _run_import(polygons):
    empty = QgsVectorLayer("Point?crs=EPSG:4326", "empty", "memory")
    OpenAlaqsOsmImport._import_osm_data(
        None,
        {
            Qgis.GeometryType.Point: empty,
            Qgis.GeometryType.Line: empty,
            Qgis.GeometryType.Polygon: polygons,
        },
    )


@pytest.fixture
def project_layer():
    added = []

    def make(uri, name, layer_type):
        layer = QgsVectorLayer(uri, name, "memory")
        oautk.apply_layer_field_config(layer, layer_type)
        QgsProject.instance().addMapLayer(layer)
        added.append(layer)
        return layer

    yield make
    for layer in added:
        QgsProject.instance().removeMapLayer(layer.id())


# ----------------------------------------------------------------------
# 1. building=commercial
# ----------------------------------------------------------------------


def _building_values():
    return [
        f["tags"].get("building")
        for f in LAYERS_CONFIG[AlaqsLayerType.BUILDING]["osm_filters"]
    ]


def test_building_filter_has_commercial_not_typo():
    values = _building_values()
    assert "commercial" in values
    assert "commerical" not in values


def test_overpass_query_asks_for_commercial_buildings():
    aerodrome = {"osm_type": "way", "osm_id": 123}
    query = get_query_body([AlaqsLayerType.BUILDING], (51.95, 4.43), aerodrome)
    assert '["building"="commercial"]' in query
    assert "commerical" not in query


def test_commercial_building_is_imported(tmp_path, project_layer):
    buildings = project_layer(
        "Polygon?crs=EPSG:4326&field=oid:integer&field=building_id:string"
        "&field=height:double&field=instudy:integer",
        "Buildings",
        AlaqsLayerType.BUILDING,
    )
    polygons = _osm(
        tmp_path,
        _way(10, [1, 2, 3, 4], {"building": "commercial"})
        + _way(11, [4, 3, 6, 5], {"building": "house"}),
    )
    _run_import(polygons)
    assert buildings.featureCount() == 1


# ----------------------------------------------------------------------
# 2. duplicate gate names
# ----------------------------------------------------------------------


def _gates_layer(project_layer, existing):
    gates = project_layer(
        "Polygon?crs=EPSG:4326&field=oid:integer&field=gate_id:string"
        "&field=gate_type:string&field=gate_height:double&field=instudy:string",
        "Gates",
        AlaqsLayerType.GATE,
    )
    feats = []
    for name in existing:
        f = QgsFeature(gates.fields())
        f.setGeometry(QgsGeometry.fromWkt("POLYGON((0 0,1 0,1 1,0 1,0 0))"))
        f["gate_id"] = name
        feats.append(f)
    gates.dataProvider().addFeatures(feats)
    return gates


def _gate_warnings(caplog):
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and "gate name(s)" in r.getMessage()
    ]


def test_duplicate_gate_names_warn_once_and_keep_features(
    tmp_path, project_layer, caplog
):
    gates = _gates_layer(project_layer, ["G7", "G1"])
    polygons = _osm(
        tmp_path,
        _way(20, [1, 2, 3, 4], {"aeroway": "apron", "ref": "G7"})
        + _way(21, [4, 3, 6, 5], {"aeroway": "apron", "ref": "G8"})
        + _way(22, [5, 6, 8, 7], {"aeroway": "apron", "ref": "G8"})
        + _way(23, [1, 2, 6, 5], {"aeroway": "apron"}),
    )
    with caplog.at_level(logging.INFO):
        _run_import(polygons)

    assert _gate_warnings(caplog) == [
        'OSM import: gate name(s) already in layer "Gates": G7; gate name(s) '
        "repeated in the import: G8; check and rename before calculating."
    ]
    # nothing renamed or dropped: 2 existing + 4 imported
    names = sorted(str(f["gate_id"]) for f in gates.getFeatures())
    assert gates.featureCount() == 6
    assert names.count("G7") == 2 and names.count("G8") == 2


def test_unique_gate_names_no_warning(tmp_path, project_layer, caplog):
    gates = _gates_layer(project_layer, ["G1"])
    polygons = _osm(
        tmp_path,
        _way(20, [1, 2, 3, 4], {"aeroway": "apron", "ref": "G7"})
        + _way(21, [4, 3, 6, 5], {"aeroway": "apron", "ref": "G8"}),
    )
    with caplog.at_level(logging.INFO):
        _run_import(polygons)
    assert _gate_warnings(caplog) == []
    assert gates.featureCount() == 3


@pytest.mark.parametrize(
    "existing, imported, expected",
    [
        ({"G7"}, ["G7"], 'gate name(s) already in layer "Gates": G7;'),
        (set(), ["A", "A", "A"], "gate name(s) repeated in the import: A;"),
        ({"G7"}, ["G7", "G7"], 'already in layer "Gates": G7; check'),
        (set(), [None, None, "B"], None),
    ],
)
def test_duplicate_gate_message(existing, imported, expected):
    msg = _osm_duplicate_gate_message(existing, imported)
    if expected is None:
        assert msg is None
    else:
        assert expected in msg
        assert msg.startswith("OSM import: ")
        assert msg.endswith("; check and rename before calculating.")
