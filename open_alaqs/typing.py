from typing import TypedDict


class StudySetup(TypedDict):
    project_name = str
    airport_name = str
    airport_id = str
    airport_code = str
    airport_country = str
    airport_latitude = float
    airport_longitude = float
    airport_elevation = float
    airport_temperature = float
    vertical_limit = float
    parking_method = str
    roadway_method = str
    roadway_fleet_year = str
    roadway_country = str
    study_info = str


class AirportDict(TypedDict):
    oid: int
    airport_code: str
    airport_name: str
    airport_country: str
    airport_latitude: float
    airport_longitude: float
    airport_elevation: int
