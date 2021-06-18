from collections import OrderedDict

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.Emissions import EmissionIndex
from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.interfaces.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.Store import Store
from open_alaqs.alaqs_core.tools import Spatial

logger = get_logger(__name__)


class Gate:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._id = str(val["gate_id"]) if "gate_id" in val else None
        self._type = str(val["gate_type"]) if "gate_type" in val else None
        self._height = float(val["gate_height"]) if "gate_height" in val and not val["gate_height"] is None else 0.

        self._instudy = int(val["instudy"]) if "instudy" in val else 1
        self._geometry_text = str(val["geometry"]) if "geometry" in val else ""

        if self._geometry_text and not self._height is None:
            self.setGeometryText(Spatial.addHeightToGeometryWkt(self.getGeometryText(), self.getHeight()))

        self._emission_profiles = []

    def getName(self):
        return self._id
    def setName(self, val):
        self._id = val

    def getEmissionProfiles(self):
        return self._emission_profiles

    def getEmissionProfileGroups(self, source_type=""):
        found_ = []
        for profile_ in self.getEmissionProfiles():
            if source_type and not profile_.getEmissionSourceType().lower() == source_type.lower():
                continue
            found_.append(profile_.getAircraftGroup())
        return found_

    # def getEmissionProfile(self, ac_group, source_type):
    #     found = None
    #     if not (ac_group is None or source_type is None):
    #         for profile_ in self.getEmissionProfiles():
    #             if profile_.getEmissionSourceType().lower() == source_type.lower() and profile_.getAircraftGroup().lower() == ac_group.lower():
    #                 found = profile_
    #     return found

    # def getEmissionIndex(self, ac_group, source_type):
    #     found = None
    #     if not (ac_group is None or source_type is None):
    #         for profile_ in self.getEmissionProfiles():
    #             if profile_.getEmissionSourceType().lower() == source_type.lower() and profile_.getAircraftGroup().lower() == ac_group.lower():
    #                 found = profile_
    #
    #     if not found is None:
    #         return found.getEmissionIndex()
    #     logger.error("Did not find a gate emission profile for source type '%s' and aircraft group '%s'. Update the table 'default_gate_profiles' to include emission indices for this source." % (source_type, ac_group))
    #     return found

    def getEmissionProfile(self, ac_group, op_type, source_type):
        found = None
        if not (ac_group is None or source_type is None):
            for profile_ in self.getEmissionProfiles():
                if profile_.getEmissionSourceType().lower() == source_type.lower() and profile_.getAircraftGroup().lower() == ac_group.lower() and \
                                profile_.getOPtype().lower() == op_type.lower():
                    found = profile_
        return found

    def getEmissionIndex(self, ac_group, op_type, source_type):
        found = None
        if not (ac_group is None or source_type is None or op_type is None):
            for profile_ in self.getEmissionProfiles():
                if profile_.getEmissionSourceType().lower() == source_type.lower() and profile_.getAircraftGroup().lower() == ac_group.lower() and \
                                profile_.getOPtype().lower() == op_type.lower():
                    found = profile_

        if not found is None:
            return found.getEmissionIndex()
        # logger.error("Did not find a gate emission profile for source type '%s' and aircraft group '%s'. "
        #              "Update the table 'default_gate_profiles' to include emission indices for this source." % (source_type, ac_group))
        return found


    def addEmissionProfile(self, emission_profile):
        if not emission_profile in self._emission_profiles:
            self._emission_profiles.append(emission_profile)

    def getEmissionIndexGPU(self, ac_group, op_type):
        return self.getEmissionIndex(ac_group, op_type, source_type="gpu")

    def getEmissionIndexGSE(self, ac_group, op_type):
        return self.getEmissionIndex(ac_group, op_type, source_type="gse")

    def setEmissionIndex(self, val):
        self._emissionIndex = val

    def getHeight(self):
        return self._height
    def setHeight(self, var):
        self._height = var

    def getType(self):
        return self._type
    def setType(self, var):
        self._type = var

    def getGeometryText(self):
        return self._geometry_text
    def setGeometryText(self, val):
        self._geometry_text = val

    def getInStudy(self):
        return self._instudy
    def setInStudy(self, val):
        self._instudy = val

    def __str__(self):
        val = "\n Gate with id '%s'" % (self.getName())
        val += "\n\t Type: %s" % (self.getType())
        val += "\n\t Height: %f" % (self.getHeight())
        val += "\n\t Associated emission profiles:\n\t %s" % ("\t".join([str(x).replace("\n", "\n\t\t") for x in self.getEmissionProfiles()]))
        val += "\n\t Instudy: %i" % (self.getInStudy())
        val += "\n\t Geometry text: '%s'" % (self.getGeometryText())
        return val


class GateStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'Gate' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        self._gate_db = GateDatabase(self._db_path)
        self._default_gate_profiles = DefaultGateEmissionProfileStore(self._db_path)

        #instantiate all gate objects
        self.initGate()

    def getDefaultGateEmissionProfiles(self):
        return self._default_gate_profiles

    def initGate(self):
        for key, gate_dict in list(self.getGateDatabase().getEntries().items()):
            #add gate to store
            gate = Gate(gate_dict)
            #add emission profiles
            for _, profile in list(self.getDefaultGateEmissionProfiles().getObjects().items()):

                if profile.getGateType().lower() == gate.getType().lower():
                    gate.addEmissionProfile(profile)

            self.setObject(gate_dict["gate_id"] if "gate_id" in gate_dict else "unknown", gate)

    def getGateDatabase(self):
        return self._gate_db


class GateDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to gate shape file in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="shapes_gates",
                 table_columns_type_dict=None,
                 primary_key="",
                 geometry_columns=None
                 ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                ("gate_id", "TEXT"),
                ("gate_height", "DECIMAL"),
                ("gate_type", "TEXT"),
                ("instudy", "DECIMAL")
            ])
        if geometry_columns is None:
            geometry_columns = [{
                "column_name": "geometry",
                "SRID": 3857,
                "geometry_type": "POLYGON",
                "geometry_type_dimension": 2
            }]

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key,
                                 geometry_columns)

        if self._db_path:
            self.deserialize()


class DefaultGateEmissionProfile:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._gate_type = str(val["gate_type"]) if "gate_type" in val else None
        self._ac_group = str(val["ac_group"]) if "ac_group" in val else None

        self._source_emission_type = str(val["emis_type"]) if "emis_type" in val else None
        self._source_emission_unit = str(val["emis_unit"]).lower() if "emis_unit" in val else None

        self._time_unit = str(val["time_unit"]).lower() if "time_unit" in val else None

        if not self.getEmissionSourceUnit() == "grams/hour":
            logger.error("Wrong input field '%s' in default_gate_profiles: %s. Should be '%s'." % ("emis_unit", self.getEmissionSourceUnit(), "grams/hour"))
            raise Exception("Wrong input field '%s' in default_gate_profiles: %s. Should be '%s'." % ("emis_unit", self.getEmissionSourceUnit(), "grams/hour"))

        if not self.getTimeUnit() == "minutes":
            logger.error("Wrong input field '%s' in default_gate_profiles: %s. Should be '%s'." % ("time_unit", self.getTimeUnit(), "minutes"))
            raise Exception("Wrong input field '%s' in default_gate_profiles: %s. Should be '%s'." % ("time_unit", self.getTimeUnit(), "minutes"))

        # self._departure = float(val["departure"]) if "departure" in val else 0.
        # self._arrival = float(val["arrival"]) if "arrival" in val else 0.
        self._op_type = str(val["op_type"]) if "op_type" in val else None
        self._time = float(val["time"]) if "time" in val else 0.

        initValues = {}
        defaultValues = {}
        suffix = "_kg_hour"
        for key_ in ["co", "hc", "nox", "sox", "pm10"]:
            if key_ in val:
                initValues[key_ + suffix] = float(val[key_])/1000.
                defaultValues[key_ + suffix] = 0.

        self._emissionIndex = EmissionIndex(initValues, defaultValues=defaultValues)

    def getAircraftGroup(self):
        return self._ac_group
    def setAircraftGroup(self, var):
        self._ac_group = var

    def getGateType(self):
        return self._gate_type
    def setGateType(self, var):
        self._gate_type = var

    def getEmissionSourceType(self):
        return self._source_emission_type
    def setEmissionSourceType(self, var):
        self._source_emission_type = var

    def getEmissionSourceUnit(self):
        return self._source_emission_unit
    def setEmissionSourceUnit(self, var):
        self._source_emission_unit = var

    def getTimeUnit(self):
        return self._time_unit
    def setTimeUnit(self, var):
        self._time_unit = var

    # def getDepartureOccupancy(self):
    #     return self._departure
    # def setDepartureOccupancy(self, var):
    #     self._departure = var
    #
    # def getArrivalOccupancy(self):
    #     return self._arrival
    # def setArrivalOccupancy(self, var):
    #     self._arrival = var

    def getOccupancy(self):
        return self._time
    def setOccupancy(self, var):
        self._time = var

    def getOPtype(self):
        return self._op_type
    def setOPtype(self, var):
        self._op_type = var

    def getEmissionIndex(self):
        return self._emissionIndex
    def setEmissionIndex(self, val):
        self._emissionIndex = val

    def __str__(self):
        val = "\n DefaultGateEmissionProfile"
        val += "\n\t Gate-Type: %s" % (self.getGateType())
        val += "\n\t Aircraft-Group: %s" % (self.getAircraftGroup())
        val += "\n\t EmissionSource-Type: %s" % (self.getEmissionSourceType())
        val += "\n\t DEBUG: EmissionSource-Unit: %s" % (self.getEmissionSourceUnit())
        val += "\n\t DEBUG: Time-Unit: %s" % (self.getTimeUnit())
        val += "\n\t Occupancy: %f" % (self.getOccupancy())
        val += "\n\t Operation type: %s" % (self.getOPtype())

        # val += "\n\t Departure Occupancy: %f" % (self.getDepartureOccupancy())
        # val += "\n\t Arrival Occupancy: %f" % (self.getArrivalOccupancy())
        val += "%s" % (self.getEmissionIndex())
        return val


class DefaultGateEmissionProfileStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'DefaultGateEmissionProfile' objects
    """

    def __init__(self, db_path=""):
        Store.__init__(self)

        self._db_path = db_path
        self._db = DefaultGateEmissionProfileDatabase(db_path)

        # instantiate all gate objects
        self.initDefaultGateEmissionProfile()

    def initDefaultGateEmissionProfile(self):
        for key, profile_dict in list(self.getDefaultGateEmissionProfileDatabase().getEntries().items()):
            #add profile to store
            self.setObject(profile_dict["oid"] if "oid" in profile_dict else "unknown", DefaultGateEmissionProfile(profile_dict))

    def getDefaultGateEmissionProfileDatabase(self):
        return self._db


class DefaultGateEmissionProfileDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to default gate profiles in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="default_gate_profiles",
                 table_columns_type_dict=None,
                 primary_key="",
                 geometry_columns=None
                 ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                ("gate_type", "VARCHAR(20)"),
                ("ac_group", "VARCHAR(20)"),
                ("emis_type", "VARCHAR(10)"),
                ("time_unit", "VARCHAR(20)"),
                ("op_type", "VARCHAR(20)"),
                ("time", "DECIMAL"),
                ("emis_unit", "VARCHAR(20)"),
                ("co", "DECIMAL"),
                ("hc", "DECIMAL"),
                ("nox", "DECIMAL"),
                ("sox", "DECIMAL"),
                ("pm10", "DECIMAL"),
                ("source", "TEXT"),
            ])
        if geometry_columns is None:
            geometry_columns = []

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key,
                                 geometry_columns)

        if self._db_path:
            self.deserialize()


# if __name__ == "__main__":
#     logger.setLevel(logging.DEBUG)
#
#     path_to_database = os.path.join("..", "..", "example/", "CAEPport", "CAEPport_out.alaqs")
#
#     if not os.path.isfile(path_to_database):
#         # fix_print_with_import
#         print("Path to database %s does not exist !"%path_to_database)
#     else:
#         # fix_print_with_import
#         print("Path to database found in: %s "%os.path.abspath(path_to_database))
#
#     store = GateStore(path_to_database)
#
#     ac_group = "TURBOPROP"
#     departure_arrival = "D"
#     source_type = "GPU"
#
#     for gate_name, gate in list(store.getObjects().items()):
#
#         # fix_print_with_import
#         print(gate_name, gate.getType())
#         # print gate.getEmissionIndexGPU("JET LARGE", "A")
#         # print gate.getEmissionIndexGSE("JET LARGE", "D")
#
#         profile_ = gate.getEmissionProfile(ac_group, departure_arrival, source_type)
#         if profile_:
#             # fix_print_with_import
#             print(profile_)



