from enum import Enum


class ALAQSLayer(str, Enum):
    AREA = "area"
    BUILDING = "building"
    GATE = "gate"
    PARKING = "parking"
    POINT_SOURCE = "point_source"
    ROADWAY = "roadway"
    TAXIWAY = "taxiway"
    TRACK = "track"
    RUNWAY = "runway"
