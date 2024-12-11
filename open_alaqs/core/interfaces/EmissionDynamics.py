from collections import OrderedDict, defaultdict
from enum import StrEnum
from typing import TypedDict, cast

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)

defaultEDs = {
    "horizontal_shift": 0.0,
    "horizontal_extension": 0.0,
    "vertical_shift": 0.0,
    "vertical_extension": 0.0,
}


class FlightStage(StrEnum):
    TX = "TX"
    AP = "AP"
    TO = "TO"
    CL = "CL"


class EmissionsDynamicsRow(TypedDict):
    oid: int
    dynamics_id: int
    dynamics_name: str
    ac_group: str
    flight_stage: FlightStage
    horizontal_extent_m: float
    vertical_extent_m: float
    exit_velocity_m_per_s: float
    decay_time_s: float
    horizontal_shift_m: float
    vertical_shift_m: float
    horizontal_extent_m_sas: float
    vertical_extent_m_sas: float
    vertical_shift_m_sas: float


class EmissionDynamics:
    def __init__(self, db_row: EmissionsDynamicsRow):
        self.name = db_row["dynamics_name"]
        self.flight_stage = db_row["flight_stage"]
        self.ac_group = db_row["ac_group"]

        self._emission_dynamics = {}
        self._emission_dynamics["sas"] = {
            # TODO OPENGIS.ch: it seems the column `horizontal_shift_m_sas` does not exist in the `default_emission_dynamics` table. We put 0 by default as it used to work before.
            # "horizontal_shift": (db_row["horizontal_shift_m_sas"] or 0),
            "horizontal_shift": 0,
            "horizontal_extension": (db_row["horizontal_extent_m_sas"] or 0),
            "vertical_shift": (db_row["vertical_shift_m_sas"] or 0),
            "vertical_extension": (db_row["vertical_extent_m_sas"] or 0),
        }
        self._emission_dynamics["default"] = {
            "horizontal_shift": (db_row["horizontal_shift_m"] or 0),
            "horizontal_extension": (db_row["horizontal_extent_m"] or 0),
            "vertical_shift": (db_row["vertical_shift_m"] or 0),
            "vertical_extension": (db_row["vertical_extent_m"] or 0),
        }

    def getModes(self):
        return list(self._emission_dynamics.keys())

    def getEmissionDynamics(self, mode):
        if mode in self._emission_dynamics:
            return self._emission_dynamics[mode]
        return {}

    def __str__(self):
        val = "\n Emission Dynamics for source category '%s'" % (self.name)
        for mode in self.getModes():
            val += "\n\t Emissions in mode '%s':" % (mode)
            for key, value in list(self.getEmissionDynamics(mode).items()):
                val += "\n\t\t %s: %f" % (key, value)
        return val


class EmissionDynamicsStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'APU' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path
        self._db = EmissionDynamicsDatabase(db_path, deserialize=True)

        # instantiate all objects
        self.initEDs()

    def initEDs(self):
        for key, ed_dict in list(
            self.getEmissionDynamicsDatabase().getEntries().items()
        ):
            # add apu to store
            self.setObject(
                ed_dict["oid"] if "oid" in ed_dict else "unknown",
                EmissionDynamics(ed_dict),
            )

    def getEmissionDynamicsDatabase(self):
        return self._db

    def get_emissions_dynamics(self) -> dict[str, dict[FlightStage, EmissionDynamics]]:
        result: dict[str, dict[FlightStage, EmissionDynamics]] = defaultdict(dict)

        for row in self.getObjects().values():
            if not row.ac_group or not row.flight_stage:
                continue

            row = cast(EmissionDynamics, row)

            assert row.flight_stage not in result[row.ac_group]
            assert row.flight_stage in FlightStage

            result[row.ac_group][row.flight_stage] = row

        return result


class EmissionDynamicsDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to emission dynamics as stored in the database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="default_emission_dynamics",
        table_columns_type_dict=None,
        primary_key="",
        geometry_columns=None,
        deserialize=True,
    ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                    ("dynamics_id", "INTEGER"),
                    ("dynamics_name", "TEXT"),
                    ("ac_group", "TEXT"),
                    ("flight_stage", "TEXT"),
                    ("horizontal_extent_m", "DECIMAL"),
                    ("vertical_extent_m", "DECIMAL"),
                    ("exit_velocity_m_per_s", "DECIMAL"),
                    ("decay_time_s", "DECIMAL"),
                    ("horizontal_shift_m", "DECIMAL"),
                    ("vertical_shift_m", "DECIMAL"),
                    ("horizontal_extent_m_sas", "DECIMAL"),
                    ("vertical_extent_m_sas", "DECIMAL"),
                    ("vertical_shift_m_sas", "DECIMAL"),
                ]
            )
        if geometry_columns is None:
            geometry_columns = []

        SQLSerializable.__init__(
            self,
            db_path_string,
            table_name_string,
            table_columns_type_dict,
            primary_key,
            geometry_columns,
        )

        if self._db_path and deserialize:
            self.deserialize()
