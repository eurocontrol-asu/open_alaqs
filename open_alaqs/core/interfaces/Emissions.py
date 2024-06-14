from enum import Enum
from typing import Literal, Tuple, cast

from shapely.geometry import GeometryCollection
from shapely.wkt import loads

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Store import Store

logger = get_logger(__name__)

defValues = {
    "fuel_kg": 0.0,
    "co_g": 0.0,
    "co2_g": 0.0,
    "hc_g": 0.0,
    "nox_g": 0.0,
    "sox_g": 0.0,
    "pm10_g": 0.0,
    "p1_g": 0.0,
    "p2_g": 0.0,
    "pm10_prefoa3_g": 0.0,
    "pm10_nonvol_g": 0.0,
    "pm10_sul_g": 0.0,
    "pm10_organic_g": 0.0,
    "nvpm_g": 0.0,
    "nvpm_number": 0.0,
}


class PollutantType(str, Enum):
    CO = "co"
    CO2 = "co2"
    HC = "hc"
    NOx = "nox"
    SOx = "sox"
    PM10 = "pm10"
    PM1 = "p1"
    PM2 = "p2"
    PM10Organic = "pm10_organic"
    PM10Prefoa3 = "pm10_prefoa3"
    PM10Nonvol = "pm10_nonvol"
    PM10Sul = "pm10_sul"
    nvPM = "nvpm"
    nvPMnumber = "nvpm_number"


class PollutantUnit(str, Enum):
    NONE = ""
    KG = "kg"
    GRAM = "g"


class EmissionIndex(Store):
    def __init__(self, initValues=None, defaultValues=None):
        if initValues is None:
            initValues = {}
        if defaultValues is None:
            defaultValues = {}
        Store.__init__(self, initValues, defaultValues)

    def getValue(self, name):
        name = name.lower()
        if "fuel" in name:
            return self.getFuel()
        elif "co2" in name:
            return self.get_value(PollutantType.CO2, "g_kg"), "g"
        elif "co" in name:
            return self.get_value(PollutantType.CO, "g_kg"), "g"
        elif "nox" in name or "no" in name:
            return self.get_value(PollutantType.NOx, "g_kg"), "g"
        # elif "sox" in name:
        elif "sox" in name or "so" in name:
            return self.get_value(PollutantType.SOx, "g_kg"), "g"
        elif "hc" in name:
            return self.get_value(PollutantType.HC, "g_kg"), "g"
        elif "pm10" in name or "p10" in name:
            return self.get_value(PollutantType.PM10, "g_kg"), "g"
        elif "pm1" in name or "p1" in name:
            return self.get_value(PollutantType.PM1, "g_kg"), "g"
        elif "pm2" in name or "p2" in name:
            return self.get_value(PollutantType.PM2, "g_kg"), "g"
        elif "nvpm_number" in name:
            return (cast(float, self.getObject("nvpm_number")), "g")
        elif "nvpm" in name:
            return self.get_value(PollutantType.nvPM, "g_kg"), "g"
        else:
            logger.error("Did not find key that matches name '%s'" % (name))

            return (None, None)

    def getFuel(self, unit="kg_sec"):
        return (self.getObject("fuel_%s" % unit), "kg")

    def get_value(
        self, pollutant_type: PollutantType, unit: Literal["kg_hour", "g_kg"]
    ) -> float:
        key = f"{pollutant_type.value}_{unit}"
        return self._objects[key]

    def __str__(self):
        val = "\n\t Emissions indices:"
        for pollutant_name, value in sorted(self.getObjects().items()):
            if not isinstance(value, float):
                val += "\n\t\t%s : %s" % (str(pollutant_name), str(value))
            else:
                val += "\n\t\t%s : %.5f" % (str(pollutant_name), float(value))
        return val

    def __iadd__(self, other):
        return self.__add__(other)

    def __imul__(self, other):
        return self.__mul__(other)


class Emission(Store):
    # def __init__(self, initValues=defValues, defaultValues=defValues):
    def __init__(self, initValues=None, defaultValues=None):
        if initValues is None:
            initValues = {}
        if defaultValues is None:
            defaultValues = {}
        Store.__init__(self, initValues, defaultValues)

        self._geometry_wkt = None
        # self._vertical_ext = {"z_min": 0, "z_max": 0, "delta_z":None}
        self._vertical_ext = {"z_min": 0, "z_max": 0}

        # self._category = ""

    def isZero(self):
        for key, value in self.getObjects().items():
            if value is not None and float(value) != 0.0:
                return False
        return True

    def getGeometryText(self) -> str:
        return self._geometry_wkt

    def getGeometry(self):
        if self._geometry_wkt:
            return loads(str(self._geometry_wkt))
        else:
            return loads(GeometryCollection().wkt)
        # return Spatial.ogr.CreateGeometryFromWkt(self._geometry_wkt)

    def setGeometryText(self, var: str):
        self._geometry_wkt = var

    # Added for Smooth & Shift
    def getVerticalExtent(self):
        return self._vertical_ext

    def setVerticalExtent(self, var):
        if not ("z_min" in list(var.keys()) and "z_max" in list(var.keys())):
            logger.warning(
                "Vertical extent not updated from dictionary, could not find min/max values"
            )
        else:
            dz = var["z_max"] - var["z_min"]
            var.update({"delta_z": dz})
            self._vertical_ext.update(var)

    def transposeToKilograms(self):
        emissions_ = Emission()
        emissions_.setGeometryText(self.getGeometryText())
        emissions_.setVerticalExtent(self.getVerticalExtent())

        for key in list(self.getObjects().keys()):
            if "_g" in key and key.index("_g") == len(key) - 2:
                # add new key
                emissions_.addObject("%s_kg" % (key[:-2]), self.getObject(key) / 1000.0)
            else:
                emissions_.addObject(key, self.getObject(key))
        return emissions_

    def add(self, emission_index_: EmissionIndex, time_s_in_mode: float):
        """
        Add emissions based on an emission index for given time.
        :param emission_index_: the emission index
        :param time_s_in_mode: the time in a certain mode, multiplied by number
         of engines (s)
        """

        # Calculate and set the fuel burned in kg
        fuel_burned = emission_index_.getObject("fuel_kg_sec") * time_s_in_mode
        self.addValue("fuel_kg", fuel_burned)

        # Determine the total emissions for each pollutant
        for pollutant_type in PollutantType:
            pollutant_ei = emission_index_.get_value(pollutant_type, "g_kg")
            self.add_value(
                pollutant_type, PollutantUnit.GRAM, pollutant_ei * fuel_burned
            )

    def addGeneric(self, emission_index_, factor, unit, new_unit=""):
        for key in list(emission_index_.getObjects().keys()):
            self.addValue(
                "%s" % (self.rreplace(key, unit, new_unit, 1)),
                emission_index_.getObject("%s" % key) * factor,
            )

    def getValue(self, name: str, unit: str = "kg") -> Tuple[float, str]:
        name = name.lower()
        if "fuel" in name:
            return self.getFuel(unit=unit)
        elif "co2" in name:
            return self.get_emission(PollutantType.CO2, unit)
        elif "co" in name:
            return self.get_emission(PollutantType.CO, unit)
        elif "nox" in name or "no" in name:
            return self.get_emission(PollutantType.NOx, unit)
        elif "sox" in name:
            return self.get_emission(PollutantType.SOx, unit)
        elif "hc" in name:
            return self.get_emission(PollutantType.HC, unit)
        elif "pm10" in name:
            if "prefoa3" in name:
                return self.get_emission(PollutantType.PM10Prefoa3, unit)
            elif "nonvol" in name:
                return self.get_emission(PollutantType.PM10Nonvol, unit)
            elif "sul" in name:
                return self.get_emission(PollutantType.PM10Sul, unit)
            elif "organic" in name:
                return self.get_emission(PollutantType.PM10Organic, unit)
            else:
                return self.get_emission(PollutantType.PM10, unit)
        elif "pm1" in name or "p1" in name:
            return self.get_emission(PollutantType.PM1, unit)
        elif "pm2" in name or "p2" in name:
            return self.get_emission(PollutantType.PM2, unit)
        elif "nvpm_number" in name:
            return cast(float, self.getObject("nvpm_number")), ""
        elif "nvpm" in name:
            return self.get_emission(PollutantType.nvPM, unit)

        logger.error("Did not find key that matches name '%s'" % name)
        return None, None

    def getFuel(self, unit: str = "kg") -> Tuple[float, str]:
        return self.getObject("fuel_%s" % unit), "kg"

    def getnvPMnumber(self) -> Tuple[float, str]:
        return self.getObject("nvpm_number"), ""

    def get_emission(self, polutant_type: PollutantType, unit="g") -> Tuple[float, str]:
        return cast(float, self.getObject(f"{polutant_type.value}_{unit}")), unit

    def addValue(self, key, val) -> bool:
        if self.hasKey(key):
            self.setObject(key, self.getObject(key) + val)
            return True
        else:
            return False

    def addFuel(self, val_in_kgrams):
        return self.addValue("fuel_kg", val_in_kgrams)

    def add_value(
        self,
        pollutant_type: PollutantType,
        unit: PollutantUnit,
        value: float,
    ) -> None:
        key = f"{pollutant_type.value}_{unit.value}"
        self._objects[key] += value

    def get_value(self, pollutant_type: PollutantType, unit: PollutantUnit) -> float:
        key = f"{pollutant_type.value}_{unit.value}"
        return self._objects[key]

    def __str__(self):
        val = "Emissions:"
        val += "\n Geometry wkt: '%s'" % (str(self.getGeometryText()))
        val += "\n Vertical Extent: '%s'" % (str(self.getVerticalExtent()))

        for pollutant_name, value in sorted(self.getObjects().items()):
            val += "\n\t\t%s : %.3f" % (
                str(pollutant_name),
                float(value) if value is not None else 0.0,
            )
        return val

    def rreplace(self, s, old, new, occurrence):
        li = s.rsplit(old, occurrence)
        return new.join(li)
