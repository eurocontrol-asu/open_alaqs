from collections import OrderedDict

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


class EmissionDynamics:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._dynamics_name = str(val.get("dynamics_name", ""))
        self._emission_dynamics = {}

        self._emission_dynamics["sas"] = {
            "horizontal_shift": val["horizontal_shift_m_sas"]
            if "horizontal_shift_m_sas" in val
            else 0.0,
            "horizontal_extension": val["horizontal_extent_m_sas"]
            if "horizontal_extent_m_sas" in val
            else 0.0,
            "vertical_shift": val["vertical_shift_m_sas"]
            if "vertical_shift_m_sas" in val
            else 0.0,
            "vertical_extension": val["vertical_extent_m_sas"]
            if "vertical_extent_m_sas" in val
            else 0.0,
        }
        self._emission_dynamics["default"] = {
            "horizontal_shift": val["horizontal_shift_m"]
            if "horizontal_shift_m" in val
            else 0.0,
            "horizontal_extension": val["horizontal_extent_m"]
            if "horizontal_extent_m" in val
            else 0.0,
            "vertical_shift": val["vertical_shift_m"]
            if "vertical_shift_m" in val
            else 0.0,
            "vertical_extension": val["vertical_extent_m"]
            if "vertical_extent_m" in val
            else 0.0,
        }

    def getDynamicsGroup(self):
        return self._dynamics_name

    def setDynamicsGroup(self, val):
        self._dynamics_name = val

    def getModes(self):
        return list(self._emission_dynamics.keys())

    def getEmissionDynamics(self, mode):
        if mode in self._emission_dynamics:
            return self._emission_dynamics[mode]
        return {}

    def setEmissionDynamics(self, mode, direction, val):
        if direction in [
            "horizontal_shift",
            "horizontal_extension",
            "vertical_shift",
            "vertical_extension",
        ]:
            if direction in self._emissions[mode]:
                self._emissions[mode][direction] = val

    def __str__(self):
        val = "\n Emission Dynamics for source category '%s'" % (
            self.getDynamicsGroup()
        )
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

    # def getMaxVerticalValues(self):
    #     max_sas = list(
    #         set([abs(values.getEmissionDynamics('sas')['vertical_shift']) for key, values in self.getObjects().items()]))
    #     max_default = list(set(
    #         [abs(values.getEmissionDynamics('default')['vertical_shift']) for key, values in self.getObjects().items()]))
    #     max_values = list(set(max_default + max_sas))
    #     max_values.sort()
    #     return max_values


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


# if __name__ == "__main__":
#
#     #add Emission Dynamics table to databases
#     for path_to_database in [
#         os.path.join("..", "..", "example/", "test_movs.alaqs")
#         # os.path.join("..", "..", "example", "blank.alaqs")
#         # os.path.join("..", "templates", "new_blank_study.alaqs")
#         # os.path.join("..", "templates", "inventory_template.alaqs")
#     ]:
#         if not os.path.isfile(path_to_database):
#             raise Exception("File %s doesn't exist !")
#
#         db = EmissionDynamicsDatabase(path_to_database, deserialize=True)
#
#         # for index, entry in enumerate([{
#         #     "aircraft_group":"JET LARGE+APU",
#
#         # },
#         # }]):
#         #     entry["oid"] = index
#         #     db.setEntry(index, entry)
#         #
#         # db.serialize()
#
#         ed_store = EmissionDynamicsStore(path_to_database)
#
#         # for ed_name, ed_ in ed_store.getObjects().items():
#             # print ed_name,  ed_.getDynamicsGroup()
#             # print "Default: %s" % ed_.getEmissionDynamics('default')
#             # print "Smooth & Shift: %s"% ed_.getEmissionDynamics('sas')