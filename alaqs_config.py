"""
This is a file that contains some of the variables that can be changed to change
the appearance of a study created within ALAQS.
"""


from typing import TypedDict

from open_alaqs.enums import ALAQSLayer


class ALAQSLayerConfig(TypedDict):
    name: str
    table_name: str
    ui_filename: str
    py_filename: str
    fill_color: str | None
    border_color: str | None
    line_width: int | None
    line_color: int | None
    label_enabled: bool
    label_position: int
    label_font_family: str
    label_font_size: int


LAYERS_CONFIG: dict[ALAQSLayer, ALAQSLayerConfig] = {
    ALAQSLayer.AREA: {
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
    ALAQSLayer.BUILDING: {
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
    },
    ALAQSLayer.GATE: {
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
    },
    ALAQSLayer.PARKING: {
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
    },
    ALAQSLayer.POINT_SOURCE: {
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
    ALAQSLayer.ROADWAY: {
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
    ALAQSLayer.TAXIWAY: {
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
    },
    ALAQSLayer.TRACK: {
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
    ALAQSLayer.RUNWAY: {
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
    },
}
