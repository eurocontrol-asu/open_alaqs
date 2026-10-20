"""
This is a file that contains some of the variables that can be changed to change
the appearance of a study created within ALAQS.
"""

from pathlib import Path
from typing import Optional, TypedDict

from open_alaqs.enums import AlaqsLayerType

# TODO OPENGIS.ch: Expose this as a user setting in the Generate Emissions Inventory -> Modelled Domain input group as a "Concentration Grid Factor" int field in the range [1, 100]
DEFAULT_CONCENTRATION_GRID_FACTOR = 2


class OsmFilter(TypedDict, total=False):
    within_aerodrome: bool
    search_radius_m: int
    tags: dict[str, str]


class FieldConfig(TypedDict, total=False):
    """Display settings of one column of an ALAQS layer.

    alias: the field name shown everywhere (form label, attribute table
        header, documentation). Title Case, units as "Name [unit]".
    default: QGIS expression string used as the default value of new
        features, or None for no default.
    read_only: True when the column is not editable in QGIS (form and
        attribute table). Only used for columns that no form writes;
        values that a custom form fills in itself (emission factors from
        Recalculate, Method) must stay writable, because
        QGIS drops the value of a read-only field when the form is saved.
    hidden_in_table: True to hide the column in the attribute table.
    widget: "checkbox" to edit the column as a check box storing "1" or
        "0"; "value_map" for a list of values (combo box), see value_map;
        None keeps the QGIS default widget.
    value_map: the values of a "value_map" widget: "values" (fixed list),
        "from" (a list read from the study when the layer is loaded, see
        openalaqsuitoolkit.VALUE_MAP_SOURCES) and "null_text" (the text
        shown for NULL, empty by default). Values already
        stored in the layer are always added, so none is shown as
        "(value)". Text and stored value are the same.
    """

    alias: str
    default: Optional[str]
    read_only: bool
    hidden_in_table: bool
    widget: Optional[str]
    value_map: dict


class ALAQSLayerConfig(TypedDict, total=False):
    name: str
    table_name: str
    ui_filename: str
    py_filename: str
    fill_color: Optional[str]
    border_color: Optional[str]
    line_color: Optional[str]
    line_width: Optional[float]
    label_enabled: bool
    label_position: int
    label_font_family: str
    label_font_size: int
    osm_filters: list[OsmFilter]
    # {OSM attribute name: ALAQS column name}, read by
    # OpenAlaqsOsmImport._import_osm_data in openalaqsdialog.py.
    osm_attribute_mapping: dict[str, str]
    osm_import_default_values: dict[str, str]
    # Ordered {column name: FieldConfig}; the order is the attribute-table
    # column order. Applied by openalaqsuitoolkit.apply_layer_field_config
    # each time a study is opened.
    fields: dict[str, FieldConfig]


def _field(
    alias: str,
    default: Optional[str] = None,
    read_only: bool = False,
    hidden_in_table: bool = False,
    widget: Optional[str] = None,
    value_map: Optional[dict] = None,
) -> FieldConfig:
    spec: FieldConfig = {
        "alias": alias,
        "default": default,
        "read_only": read_only,
        "hidden_in_table": hidden_in_table,
        "widget": widget,
    }
    if value_map is not None:
        spec["widget"] = "value_map"
        spec["value_map"] = value_map
    return spec


def _name(alias: str) -> FieldConfig:
    """A required name: empty (not NULL) for a new feature, so the form
    shows an empty box; the forms reject an empty name."""
    return _field(alias, "''")


def _oid() -> FieldConfig:
    return _field("OID", read_only=True, hidden_in_table=True)


def _instudy(default: str, used: bool) -> FieldConfig:
    """The in-study flag. `default` is typed like the column ("1" for INT
    and DECIMAL columns, "'1'" for TEXT columns). The flag is honoured by
    parkings, roadways, point sources and area sources only; on the other
    layers it is kept but hidden in the attribute table."""
    return _field("In Study", default, hidden_in_table=not used, widget="checkbox")


def _fleet_mix() -> dict[str, FieldConfig]:
    return {
        "pc_p_percentage": _field("PC (Petrol) [%]"),
        "pc_d_percentage": _field("PC (Diesel) [%]"),
        "lcv_p_percentage": _field("LCV (Petrol) [%]"),
        "lcv_d_percentage": _field("LCV (Diesel) [%]"),
        "hdt_p_percentage": _field("HDT (Petrol) [%]"),
        "hdt_d_percentage": _field("HDT (Diesel) [%]"),
        "motorcycle_p_percentage": _field("Motorcycle [%]"),
        "bus_d_percentage": _field("Bus [%]"),
    }


def _profiles(hour: str, day: str, month: str) -> dict[str, FieldConfig]:
    return {
        hour: _field(
            "Hourly Profile", "'default'", value_map={"from": "hour_profiles"}
        ),
        day: _field("Daily Profile", "'default'", value_map={"from": "day_profiles"}),
        month: _field(
            "Monthly Profile", "'default'", value_map={"from": "month_profiles"}
        ),
    }


def _emission_factors(suffix: str, unit: str) -> dict[str, FieldConfig]:
    names = ("co", "hc", "nox", "sox", "pm10", "p1", "p2")
    labels = ("CO", "HC", "NOx", "SOx", "PM10", "P1", "P2")
    return {
        f"{name}_{suffix}": _field(f"{label} [{unit}]")
        for name, label in zip(names, labels)
    }


LAYERS_CONFIG: dict[AlaqsLayerType, ALAQSLayerConfig] = {
    AlaqsLayerType.AREA: {
        "name": "Area Sources",
        "table_name": "shapes_area_sources",
        "ui_filename": "ui_area_sources.ui",
        "py_filename": "ui_area_sources.py",
        "fields": {
            "oid": _oid(),
            "source_id": _name("Source Name"),
            "is_test_site": _field("Engine Test Site", "'0'", widget="checkbox"),
            "unit_year": _field("Units per Year"),
            "height": _field("Height [m]", "0"),
            "heat_flux": _field("Heat Flux [MW]", "0", read_only=True),
            **_profiles("hourly_profile", "daily_profile", "monthly_profile"),
            **_emission_factors("kg_unit", "kg/unit"),
            "instudy": _instudy("'1'", used=True),
        },
        "fill_color": "255,51,51",
        "border_color": "0,0,0,100",
        "line_width": None,
        "line_color": None,
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
    },
    AlaqsLayerType.BUILDING: {
        "name": "Buildings",
        "table_name": "shapes_buildings",
        "ui_filename": "ui_buildings.ui",
        "py_filename": "ui_buildings.py",
        "fields": {
            "oid": _oid(),
            "building_id": _name("Building Name"),
            "height": _field("Height [m]", "0"),
            "instudy": _instudy("1", used=False),
        },
        "fill_color": "168,168,168",
        "border_color": "0,0,0,255",
        "line_width": None,
        "line_color": None,
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
        "osm_filters": [
            {
                "within_aerodrome": True,
                "tags": {
                    "building": "transportation",
                },
            },
            {
                "within_aerodrome": True,
                "tags": {
                    "building": "retail",
                },
            },
            {
                "within_aerodrome": True,
                "tags": {
                    "building": "office",
                },
            },
            {
                "within_aerodrome": True,
                "tags": {
                    "building": "commerical",
                },
            },
            {
                "within_aerodrome": True,
                "tags": {
                    "building": "hotel",
                },
            },
            {
                "within_aerodrome": True,
                "tags": {
                    "building": "service",
                },
            },
            {
                "within_aerodrome": True,
                "tags": {
                    "building": "silo",
                },
            },
            {
                "within_aerodrome": True,
                "tags": {
                    "building": "warehouse",
                },
            },
            {
                "within_aerodrome": True,
                "tags": {
                    "building": "industrial",
                },
            },
        ],
        "osm_attribute_mapping": {
            "full_id": "building_id",
            "height": "height",
        },
        "osm_import_default_values": {
            "instudy": 1,
        },
    },
    AlaqsLayerType.GATE: {
        "name": "Gates",
        "table_name": "shapes_gates",
        "ui_filename": "ui_gates.ui",
        "py_filename": "ui_gates.py",
        "fields": {
            "oid": _oid(),
            "gate_id": _name("Gate Name"),
            "gate_type": _field(
                "Gate Type", "'PIER'", value_map={"values": ["PIER", "REMOTE", "CARGO"]}
            ),
            "gate_height": _field("Height [m]", "0"),
            "instudy": _instudy("'1'", used=False),
        },
        "fill_color": "255,153,51",
        "border_color": "0,0,0,255",
        "line_width": None,
        "line_color": None,
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
        "osm_filters": [
            {
                "within_aerodrome": True,
                "tags": {
                    "aeroway": "apron",
                },
            }
        ],
        "osm_attribute_mapping": {"ref": "gate_id"},
        "osm_import_default_values": {
            "instudy": 1,
        },
    },
    AlaqsLayerType.PARKING: {
        "name": "Parkings",
        "table_name": "shapes_parking",
        "ui_filename": "ui_parkings.ui",
        "py_filename": "ui_parkings.py",
        "fields": {
            "oid": _oid(),
            "parking_id": _name("Parking Name"),
            "vehicle_year": _field("Vehicles per Year"),
            "height": _field("Height [m]", "0"),
            "speed": _field("Speed [km/h]"),
            "distance": _field("Travel Distance [m]"),
            "idle_time": _field("Idle Time [min]"),
            **_fleet_mix(),
            **_profiles("hour_profile", "daily_profile", "month_profile"),
            **_emission_factors("gm_vh", "g/vehicle"),
            "method": _field("Method"),
            "instudy": _instudy("'1'", used=True),
        },
        "fill_color": "100,149,237",
        "border_color": "0,0,0,255",
        "line_width": None,
        "line_color": None,
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
        "osm_filters": [
            {
                "within_aerodrome": True,
                "tags": {
                    "amenity": "parking",
                },
            }
        ],
        "osm_attribute_mapping": {
            "full_id": "parking_id",
        },
        "osm_import_default_values": {
            "hour_profile": "default",
            "daily_profile": "default",
            "month_profile": "default",
            "instudy": 1,
        },
    },
    AlaqsLayerType.POINT_SOURCE: {
        "name": "Point Sources",
        "table_name": "shapes_point_sources",
        "ui_filename": "ui_point_sources.ui",
        "py_filename": "ui_point_sources.py",
        "fields": {
            "oid": _oid(),
            "source_id": _name("Source Name"),
            "category": _field("Category", value_map={"from": "stationary_categories"}),
            # All types; the form shows those of the selected category
            "point_type": _field("Type", value_map={"from": "stationary_types"}),
            "substance": _field("Substance"),
            "ops_year": _field("Activity per Year"),
            "height": _field("Height [m]", "0"),
            "activity_unit": _field("Activity Unit"),
            "temperature": _field("Temperature [°C]"),
            "diameter": _field("Diameter [m]"),
            "velocity": _field("Gas Velocity [m/s]"),
            **_profiles("hour_profile", "daily_profile", "month_profile"),
            **_emission_factors("kg_k", "kg/unit"),
            "instudy": _instudy("'1'", used=True),
        },
        "fill_color": None,
        "border_color": None,
        "line_color": None,
        "line_width": None,
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
    },
    AlaqsLayerType.ROADWAY: {
        "name": "Roadways",
        "table_name": "shapes_roadways",
        "ui_filename": "ui_roadways.ui",
        "py_filename": "ui_roadways.py",
        "fields": {
            "oid": _oid(),
            "roadway_id": _name("Roadway Name"),
            "vehicle_year": _field("Vehicles per Year"),
            "height": _field("Height [m]", "0"),
            "speed": _field("Speed [km/h]"),
            "distance": _field("Distance [m]"),
            "scenario": _field("Scenario", value_map={"null_text": "Not Applicable"}),
            **_fleet_mix(),
            **_profiles("hour_profile", "daily_profile", "month_profile"),
            **_emission_factors("gm_km", "g/km"),
            "method": _field("Method"),
            "instudy": _instudy("'1'", used=True),
        },
        "fill_color": None,
        "border_color": None,
        "line_color": "255,255,0",
        "line_width": 0.75,
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
        "osm_filters": [
            {
                "within_aerodrome": False,
                "search_radius_m": 3000,
                "tags": {
                    "highway": "motorway",
                },
            },
            {
                "within_aerodrome": False,
                "search_radius_m": 3000,
                "tags": {
                    "highway": "trunk",
                },
            },
            {
                "within_aerodrome": False,
                "search_radius_m": 3000,
                "tags": {
                    "highway": "primary",
                },
            },
            {
                "within_aerodrome": False,
                "search_radius_m": 3000,
                "tags": {
                    "highway": "secondary",
                },
            },
            {
                "within_aerodrome": False,
                "search_radius_m": 3000,
                "tags": {
                    "highway": "tertiary",
                },
            },
        ],
        "osm_attribute_mapping": {
            "ref": "roadway_id",
        },
        "osm_import_default_values": {
            "hour_profile": "default",
            "daily_profile": "default",
            "month_profile": "default",
            "instudy": 1,
        },
    },
    AlaqsLayerType.TAXIWAY: {
        "name": "Taxiways",
        "table_name": "shapes_taxiways",
        "ui_filename": "ui_taxiways.ui",
        "py_filename": "ui_taxiways.py",
        "fields": {
            "oid": _oid(),
            "taxiway_id": _name("Taxiway Name"),
            "speed": _field("Speed [km/h]"),
            # Not read by the calculation (the time comes from length and
            # speed): not in the form, hidden in the attribute table
            "time": _field("Time [min]", read_only=True, hidden_in_table=True),
            "instudy": _instudy("1", used=False),
        },
        "fill_color": None,
        "border_color": None,
        "line_color": "46,255,53",
        "line_width": 0.5,
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
        "osm_filters": [
            {
                "within_aerodrome": True,
                "tags": {
                    "aeroway": "taxiway",
                },
            }
        ],
        "osm_attribute_mapping": {
            "ref": "taxiway_id",
        },
        "osm_import_default_values": {
            "instudy": 1,
        },
    },
    AlaqsLayerType.TRACK: {
        "name": "Tracks",
        "table_name": "shapes_tracks",
        "ui_filename": "ui_tracks.ui",
        "py_filename": "ui_tracks.py",
        "fields": {
            "oid": _oid(),
            "track_id": _name("Track Name"),
            "runway": _field(
                "Runway Direction", value_map={"from": "runway_directions"}
            ),
            "departure_arrival": _field(
                "Operation Type", value_map={"values": ["Arrival", "Departure"]}
            ),
            "instudy": _instudy("1", used=False),
        },
        "fill_color": None,
        "border_color": None,
        "line_color": None,
        "line_width": None,
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
    },
    AlaqsLayerType.RUNWAY: {
        "name": "Runways",
        "table_name": "shapes_runways",
        "ui_filename": "ui_runways.ui",
        "py_filename": "ui_runways.py",
        "fields": {
            "oid": _oid(),
            "runway_id": _name("Runway Name"),
            "touchdown": _field("Touchdown Offset, Runway 1 [m]", "0"),
            "touchdown_2": _field("Touchdown Offset, Runway 2 [m]", "0"),
            "instudy": _instudy("1", used=False),
        },
        "fill_color": None,
        "border_color": None,
        "line_color": "235,235,235",
        "line_width": 2,
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
        "osm_within_aerodrome": True,
        "osm_filters": [
            {
                "within_aerodrome": True,
                "tags": {
                    "aeroway": "runway",
                },
            }
        ],
        "osm_attribute_mapping": {
            "ref": "runway_id",
        },
        "osm_import_default_values": {
            "instudy": 1,
        },
    },
}


ALAQS_ROOT_PATH = Path(__file__).absolute().parent
ALAQS_TEMPLATE_DB_FILENAME = "core/templates/project.alaqs"


def field_alias(alaqs_layer: AlaqsLayerType, column: str) -> str:
    """Return the display name of a column (form label, attribute-table
    header, documentation name), or the column name when it has none."""
    spec = LAYERS_CONFIG[alaqs_layer].get("fields", {}).get(column)
    return spec["alias"] if spec else column
