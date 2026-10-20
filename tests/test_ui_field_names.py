"""
Field naming of the nine ALAQS layers (QGIS-free).

One name per field: the label of the custom form, the attribute-table alias
and the documentation use the same string, defined once in the `fields` map
of each layer in `open_alaqs/alaqs_config.py`. These tests pin:

  * every configured column exists in the project template, and every
    template column is configured (so no column is shown with its raw name);
  * each form label next to a field widget equals that field's alias;
  * the defaults are typed like their column (TEXT defaults are quoted);
  * the in-study flag is shown only on the layers whose calculation uses it;
  * the OSM attribute mappings are {OSM attribute: ALAQS column}, the
    direction read by `_import_osm_data` in `openalaqsdialog.py`.
"""

import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from open_alaqs.alaqs_config import (
    ALAQS_ROOT_PATH,
    ALAQS_TEMPLATE_DB_FILENAME,
    LAYERS_CONFIG,
    field_alias,
)
from open_alaqs.enums import AlaqsLayerType

UI_DIR = ALAQS_ROOT_PATH / "ui"
TEMPLATE = ALAQS_ROOT_PATH / ALAQS_TEMPLATE_DB_FILENAME

# Form labels that do not name a database column.
NON_FIELD_LABELS = {
    AlaqsLayerType.RUNWAY: {"Runway 1", "Runway 2"},
}

# Layers whose emission calculation skips sources with instudy = '0'
# (Source.isInStudy, used by the parking, roadway, point and area modules).
INSTUDY_HONOURED = {
    AlaqsLayerType.PARKING,
    AlaqsLayerType.ROADWAY,
    AlaqsLayerType.POINT_SOURCE,
    AlaqsLayerType.AREA,
}

LAYERS = list(AlaqsLayerType)


def _template_columns(table: str) -> dict[str, str]:
    con = sqlite3.connect(f"file:{TEMPLATE}?mode=ro", uri=True)
    try:
        rows = con.execute(f'PRAGMA table_info("{table}")').fetchall()
    finally:
        con.close()
    return {r[1]: r[2].upper() for r in rows if r[1] != "geometry"}


def _string(widget: ET.Element, prop: str):
    for p in widget.findall("property"):
        if p.get("name") == prop:
            s = p.find("string")
            return s.text if s is not None else None
    return None


def _label_field_pairs(ui_file: Path):
    """Yield (label text, field widget name or None) for every QLabel in a
    grid or form layout: the field is the widget in column 1 of the same
    row, or the first input widget of a layout in column 1 (None when
    there is none)."""
    inputs = {"QLineEdit", "QComboBox", "QCheckBox"}
    root = ET.parse(ui_file).getroot()
    for layout in root.iter("layout"):
        rows: dict[str, dict[str, ET.Element]] = {}
        for item in layout.findall("item"):
            if item.get("row") is None:
                continue
            child = item.find("widget")
            if child is None:
                child = item.find("layout")
            if child is not None:
                rows.setdefault(item.get("row"), {})[item.get("column")] = child
        for cells in rows.values():
            label = cells.get("0")
            if label is None or label.tag != "widget" or label.get("class") != "QLabel":
                continue
            partner = cells.get("1")
            name = None
            if partner is not None and partner.tag == "widget":
                name = partner.get("name")
            elif partner is not None:
                nested = [w for w in partner.iter("widget") if w.get("class") in inputs]
                name = nested[0].get("name") if nested else None
            yield _string(label, "text"), name


@pytest.mark.parametrize("layer", LAYERS, ids=lambda t: t.value)
def test_fields_cover_every_template_column(layer):
    cfg = LAYERS_CONFIG[layer]
    columns = _template_columns(cfg["table_name"])
    assert columns, f"{cfg['table_name']} missing from the template"
    assert set(cfg["fields"]) == set(columns), (
        f"{cfg['name']}: configured {sorted(set(cfg['fields']) ^ set(columns))} "
        "differ from the template columns"
    )


@pytest.mark.parametrize("layer", LAYERS, ids=lambda t: t.value)
def test_aliases_follow_the_convention(layer):
    fields = LAYERS_CONFIG[layer]["fields"]
    aliases = [spec["alias"] for spec in fields.values()]
    assert len(aliases) == len(set(aliases)), f"duplicate aliases {aliases}"
    for alias in aliases:
        # Units in square brackets only, never "(m)" or "[in %]"
        assert not re.search(r"\((m|km/h|min|minutes|meters|metres)\)", alias)
        assert "[in " not in alias
        # Title Case: every word longer than three letters starts upper case
        for word in re.findall(r"[A-Za-z]+", alias.split("[")[0]):
            if len(word) > 3:
                assert word[0].isupper(), f"{alias!r}: {word!r} not capitalised"
    # oid first and hidden, instudy last
    names = list(fields)
    assert names[0] == "oid" and fields["oid"]["hidden_in_table"]
    assert fields["oid"]["read_only"]
    assert names[-1] == "instudy"


@pytest.mark.parametrize("layer", LAYERS, ids=lambda t: t.value)
def test_form_labels_equal_aliases(layer):
    cfg = LAYERS_CONFIG[layer]
    fields = cfg["fields"]
    allowed = NON_FIELD_LABELS.get(layer, set())
    seen = set()
    for text, widget_name in _label_field_pairs(UI_DIR / cfg["ui_filename"]):
        if widget_name in fields:
            assert text == fields[widget_name]["alias"], (
                f"{cfg['ui_filename']}: label {text!r} of {widget_name!r} "
                f"should be {fields[widget_name]['alias']!r}"
            )
            seen.add(widget_name)
        else:
            assert text in allowed, (
                f"{cfg['ui_filename']}: label {text!r} is not next to a "
                f"configured field ({widget_name!r})"
            )
    # Every column with a form widget other than the in-study check box has
    # its label (the widget objectName equals the column name).
    root = ET.parse(UI_DIR / cfg["ui_filename"]).getroot()
    widget_names = {w.get("name") for w in root.iter("widget")}
    labelled = (widget_names & set(fields)) - {"instudy"}
    assert labelled == seen, f"fields without a matching label: {labelled - seen}"
    # The in-study check box text is the alias too
    for w in root.iter("widget"):
        if w.get("name") == "instudy":
            assert _string(w, "text") == fields["instudy"]["alias"]


def test_point_source_type_widget_is_bound_to_point_type():
    root = ET.parse(UI_DIR / "ui_point_sources.ui").getroot()
    names = {w.get("name") for w in root.iter("widget")}
    assert "point_type" in names and "type" not in names


@pytest.mark.parametrize("layer", LAYERS, ids=lambda t: t.value)
def test_defaults_are_typed_like_their_column(layer):
    cfg = LAYERS_CONFIG[layer]
    columns = _template_columns(cfg["table_name"])
    for name, spec in cfg["fields"].items():
        default = spec["default"]
        if default is None:
            continue
        if columns[name] == "TEXT":
            assert re.fullmatch(r"'[^']*'", default), f"{name}: {default!r}"
        else:
            assert re.fullmatch(r"-?\d+(\.\d+)?", default), f"{name}: {default!r}"


def test_agreed_defaults():
    def default(layer, column):
        return LAYERS_CONFIG[layer]["fields"][column]["default"]

    assert default(AlaqsLayerType.RUNWAY, "touchdown") == "0"
    assert default(AlaqsLayerType.RUNWAY, "touchdown_2") == "0"
    assert default(AlaqsLayerType.GATE, "gate_type") == "'PIER'"
    assert default(AlaqsLayerType.GATE, "gate_height") == "0"
    assert default(AlaqsLayerType.BUILDING, "height") == "0"
    for layer in LAYERS:
        assert default(layer, "instudy") in ("1", "'1'")
    for layer, prefix in (
        (AlaqsLayerType.PARKING, "hour"),
        (AlaqsLayerType.ROADWAY, "hour"),
        (AlaqsLayerType.POINT_SOURCE, "hour"),
        (AlaqsLayerType.AREA, "hourly"),
    ):
        fields = LAYERS_CONFIG[layer]["fields"]
        profiles = [c for c in fields if c.endswith("_profile")]
        assert len(profiles) == 3 and f"{prefix}_profile" in profiles
        assert all(fields[c]["default"] == "'default'" for c in profiles)


@pytest.mark.parametrize("layer", LAYERS, ids=lambda t: t.value)
def test_instudy_shown_only_where_used(layer):
    spec = LAYERS_CONFIG[layer]["fields"]["instudy"]
    assert spec["widget"] == "checkbox"
    assert spec["alias"] == "In Study"
    assert spec["hidden_in_table"] == (layer not in INSTUDY_HONOURED)


def test_read_only_columns():
    """Read-only is only set on columns no form writes: QGIS drops the
    value of a read-only field on save, so the form-filled columns
    (emission factors, Method, Activity Unit) stay writable."""
    read_only = {
        (layer, name)
        for layer in LAYERS
        for name, spec in LAYERS_CONFIG[layer]["fields"].items()
        if spec["read_only"] and name != "oid"
    }
    assert read_only == {
        (AlaqsLayerType.TAXIWAY, "time"),
        (AlaqsLayerType.AREA, "heat_flux"),
    }


def test_shared_names():
    assert field_alias(AlaqsLayerType.PARKING, "vehicle_year") == "Vehicles per Year"
    assert field_alias(AlaqsLayerType.ROADWAY, "vehicle_year") == "Vehicles per Year"
    assert field_alias(AlaqsLayerType.TRACK, "departure_arrival") == "Operation Type"
    assert field_alias(AlaqsLayerType.TRACK, "runway") == "Runway Direction"
    assert field_alias(AlaqsLayerType.AREA, "heat_flux") == "Heat Flux [MW]"
    assert field_alias(AlaqsLayerType.PARKING, "unknown_column") == "unknown_column"


@pytest.mark.parametrize(
    "layer",
    [t for t in LAYERS if "osm_attribute_mapping" in LAYERS_CONFIG[t]],
    ids=lambda t: t.value,
)
def test_osm_attribute_mapping_is_osm_to_alaqs(layer):
    """`_import_osm_data` reads `osm_f.attributeMap().get(key)` and writes
    the value into the ALAQS column named by the mapping value."""
    cfg = LAYERS_CONFIG[layer]
    columns = _template_columns(cfg["table_name"])
    for osm_name, alaqs_name in cfg["osm_attribute_mapping"].items():
        assert (
            alaqs_name in columns
        ), f"{cfg['name']}: mapping value {alaqs_name!r} is not a column"
        assert osm_name not in columns or osm_name == alaqs_name, (
            f"{cfg['name']}: mapping key {osm_name!r} is an ALAQS column; "
            "the mapping must be {OSM attribute: ALAQS column}"
        )


def test_osm_import_reads_mapping_as_osm_to_alaqs():
    """Pin the reader side: the import loop takes the key as the OSM
    attribute name and the value as the ALAQS field name."""
    src = (ALAQS_ROOT_PATH / "openalaqsdialog.py").read_text(encoding="utf-8")
    assert re.search(
        r"for osm_attr_name, alaqs_attr_name in layer_config\.get\(\s*"
        r'"osm_attribute_mapping"',
        src,
    )
    assert "osm_f.attributeMap().get(osm_attr_name)" in src
    assert "alaqs_fields.indexFromName(alaqs_attr_name)" in src
