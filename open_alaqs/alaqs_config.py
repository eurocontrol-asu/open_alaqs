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
    osm_attribute_mapping: dict[str, str]
    osm_import_default_values: dict[str, str]


LAYERS_CONFIG: dict[AlaqsLayerType, ALAQSLayerConfig] = {
    AlaqsLayerType.AREA: {
        "name": "Area Sources",
        "table_name": "shapes_area_sources",
        "ui_filename": "ui_area_sources.ui",
        "py_filename": "ui_area_sources.py",
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
            "building_id": "full_id",
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
        "osm_attribute_mapping": {"gate_id": "ref"},
        "osm_import_default_values": {
            "instudy": 1,
        },
    },
    AlaqsLayerType.PARKING: {
        "name": "Parkings",
        "table_name": "shapes_parking",
        "ui_filename": "ui_parkings.ui",
        "py_filename": "ui_parkings.py",
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
            "parking_id": "full_id",
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
