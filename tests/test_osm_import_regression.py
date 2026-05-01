"""
Regression test for OSM-to-ALAQS import: taxiway/runway feature filtering.

The default GDAL osmconf.ini does NOT expose `aeroway` or `ref` as
proper columns on the `lines` sub-layer; both go into the
`other_tags` HSTORE blob. That broke the OSM import filter
`"aeroway" = 'taxiway'` (and the runway equivalent), so taxiways and
runways were fetched from Overpass and shown in the OSM Lines preview
layer in the project, but the subsequent import-to-ALAQS step matched
zero features and silently inserted no rows in `shapes_taxiways` or
`shapes_runways`.

The fix bundles a custom osmconf.ini at
`open_alaqs/core/utils/osmconf.ini` and passes its path via the
`CONFIG_FILE` open option when constructing the QgsVectorLayer URIs
for the OSM sub-layers in `download_osm_airport_data`.

This test pins both halves of the contract:
  1. The bundled osmconf.ini exists and lists aeroway and ref in the
     [lines] attributes section.
  2. Opening an OSM XML through the GDAL driver with `CONFIG_FILE`
     pointing at the bundled config produces a `lines` layer with
     aeroway and ref as queryable columns.
"""

import configparser
import os
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
OSMCONF = REPO / "open_alaqs" / "core" / "utils" / "osmconf.ini"


def test_bundled_osmconf_ini_exists():
    assert OSMCONF.is_file(), (
        f"Bundled OSM config file missing at {OSMCONF}. Without it the "
        f"GDAL OSM driver falls back to the system default which does NOT "
        f"expose aeroway/ref on lines, breaking taxiway/runway import."
    )


def test_bundled_osmconf_lines_section_exposes_aeroway_and_ref():
    """The [lines] attributes list must include aeroway and ref so the
    QgsExpression filter `"aeroway" = 'taxiway'` actually has a column
    to match against."""
    cfg = configparser.ConfigParser()
    # GDAL osmconf.ini is INI-ish but uses keys without [section] for
    # closed_ways_are_polygons etc; ConfigParser tolerates with a default section.
    text = OSMCONF.read_text()
    # Strip top-level keys so ConfigParser can parse
    stripped = "[__top__]\n" + text
    cfg.read_string(stripped)
    assert "lines" in cfg.sections(), "[lines] section missing from bundled osmconf.ini"
    attrs = [a.strip() for a in cfg["lines"]["attributes"].split(",")]
    assert "aeroway" in attrs, (
        f"[lines] attributes missing 'aeroway'. Found: {attrs}. "
        f"Without aeroway as a column, taxiway and runway import filters "
        f"match zero features."
    )
    assert "ref" in attrs, (
        f"[lines] attributes missing 'ref'. Found: {attrs}. Without ref, "
        f"the osm_attribute_mapping `ref -> taxiway_id` and `ref -> runway_id` "
        f"cannot pull a value from the OSM feature."
    )


def test_gdal_osm_driver_with_bundled_config_exposes_aeroway_on_lines():
    """End-to-end: feed a tiny OSM XML with a tagged way through GDAL using
    the bundled config file via the OPTION:CONFIG_FILE open option, and
    confirm the resulting OGR layer has aeroway and ref as proper columns
    that can be queried."""
    pytest.importorskip("osgeo.ogr")
    from osgeo import ogr

    osm_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <node id="1" lat="51.95690" lon="4.43720"/>
  <node id="2" lat="51.95700" lon="4.43730"/>
  <way id="100">
    <nd ref="1"/>
    <nd ref="2"/>
    <tag k="aeroway" v="taxiway"/>
    <tag k="ref" v="A1"/>
  </way>
  <way id="101">
    <nd ref="1"/>
    <nd ref="2"/>
    <tag k="aeroway" v="runway"/>
    <tag k="ref" v="06/24"/>
  </way>
</osm>
"""
    fd, osm_path = tempfile.mkstemp(suffix=".osm")
    os.write(fd, osm_xml)
    os.close(fd)
    try:
        # Set the config file via env var (equivalent to the CONFIG_FILE
        # open option used at runtime by the QgsVectorLayer URI).
        old = os.environ.get("OSM_CONFIG_FILE")
        os.environ["OSM_CONFIG_FILE"] = str(OSMCONF)
        try:
            ds = ogr.Open(osm_path)
            assert ds is not None, "GDAL could not open the test OSM XML"
            lines = ds.GetLayerByName("lines")
            assert lines is not None, "lines sub-layer not found"

            # Must have aeroway and ref columns
            field_names = [
                lines.GetLayerDefn().GetFieldDefn(i).GetName()
                for i in range(lines.GetLayerDefn().GetFieldCount())
            ]
            assert "aeroway" in field_names, (
                f"GDAL with bundled config did not expose 'aeroway' on lines. "
                f"Got: {field_names}"
            )
            assert "ref" in field_names, (
                f"GDAL with bundled config did not expose 'ref' on lines. "
                f"Got: {field_names}"
            )

            # An attribute filter on aeroway must actually match
            lines.SetAttributeFilter("aeroway = 'taxiway'")
            taxiway_count = 0
            taxiway_ref = None
            for feat in lines:
                taxiway_count += 1
                taxiway_ref = feat.GetField("ref")
            assert taxiway_count == 1, (
                f"Expected 1 taxiway feature when filtering aeroway='taxiway'; "
                f"got {taxiway_count}. The filter is what the OSM-to-ALAQS "
                f"import path uses; if it doesn't work here it won't import "
                f"taxiways from real Overpass output either."
            )
            assert (
                taxiway_ref == "A1"
            ), f"Expected ref='A1' on the taxiway feature; got {taxiway_ref!r}."

            ds = None  # close
        finally:
            if old is None:
                os.environ.pop("OSM_CONFIG_FILE", None)
            else:
                os.environ["OSM_CONFIG_FILE"] = old
    finally:
        os.unlink(osm_path)


def test_taxiway_layer_config_uses_correct_attribute_mapping_direction():
    """Sanity check that the taxiway layer config's osm_attribute_mapping
    is in the {osm_attr: alaqs_attr} direction expected by the import
    code at openalaqsdialog.py _import_osm_data."""
    import os as _os

    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from open_alaqs.alaqs_config import LAYERS_CONFIG
    from open_alaqs.enums import AlaqsLayerType

    cfg = LAYERS_CONFIG[AlaqsLayerType.TAXIWAY]
    mapping = cfg["osm_attribute_mapping"]
    # osm_f.attributeMap().get(osm_attr_name) — so the KEY must be an OSM tag
    # name (in the lines layer columns) and the VALUE must be an ALAQS field.
    # OSM tag is 'ref', ALAQS field is 'taxiway_id'.
    assert "ref" in mapping, (
        f"Taxiway osm_attribute_mapping missing 'ref' as key. The import "
        f"code reads `osm_f.attributeMap().get(key)`, so the key must be an "
        f"OSM column. Got: {mapping}"
    )
    assert mapping["ref"] == "taxiway_id", (
        f"Taxiway osm_attribute_mapping['ref'] should be 'taxiway_id' "
        f"(the ALAQS field name); got {mapping['ref']!r}."
    )
