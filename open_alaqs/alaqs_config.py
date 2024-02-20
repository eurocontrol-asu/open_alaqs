"""
This is a file that contains some of the variables that can be changed to change
the appearance of a study created within ALAQS.
"""


from pathlib import Path
from typing import Optional, TypedDict

from open_alaqs.enums import AlaqsLayerType


class ALAQSLayerConfig(TypedDict):
    name: str
    table_name: str
    ui_filename: str
    py_filename: str
    fill_color: Optional[str]
    border_color: Optional[str]
    line_width: Optional[int]
    line_color: Optional[int]
    label_enabled: bool
    label_position: int
    label_font_family: str
    label_font_size: int
    osm_tags: list[dict[str, str]]
    osm_attribute_mapping: dict[str, str]


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
        "osm_search_radius_m": 1000,
        "osm_tags": [
            {
                "building": "industrial",
            },
            {
                "building": "apartments",
            },
        ],
        "osm_attribute_mapping": {
            "building_id": "full_id",
            "height": "height",
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
        "osm_search_radius_m": 5000,
        "osm_tags": [
            # {
            #     "aeroway": "parking_position",
            # },
            {
                "aeroway": "apron",
            },
        ],
        "osm_attribute_mapping": {"gate_id": "ref"},
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
        "osm_search_radius_m": 5000,
        "osm_tags": [
            {
                "amenity": "parking",
            },
        ],
        "osm_attribute_mapping": {
            "parking_id": "full_id",
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
        "line_width": "0.75",
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
    },
    AlaqsLayerType.TAXIWAY: {
        "name": "Taxiways",
        "table_name": "shapes_taxiways",
        "ui_filename": "ui_taxiways.ui",
        "py_filename": "ui_taxiways.py",
        "fill_color": None,
        "border_color": None,
        "line_color": "46,255,53",
        "line_width": "0.5",
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
        "osm_search_radius_m": 5000,
        "osm_tags": [
            {
                "aeroway": "taxiway",
            },
        ],
        "osm_attribute_mapping": {
            "ref": "taxiway_id",
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
        "line_width": "2",
        "label_enabled": False,
        "label_position": 1,
        "label_font_family": "Arial",
        "label_font_size": 8,
        "osm_search_radius_m": 5000,
        "osm_tags": [
            {
                "aeroway": "runway",
            },
        ],
        "osm_attribute_mapping": {
            "ref": "runway_id",
        },
    },
}


ALAQS_ROOT_PATH = Path(__file__).absolute().parent
ALAQS_TEMPLATE_DB_FILENAME = "core/templates/project.alaqs"
