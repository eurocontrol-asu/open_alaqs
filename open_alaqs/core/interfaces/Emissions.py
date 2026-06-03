from enum import Enum
from typing import Literal, Optional, Tuple

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
    PM10Nonvol = "pm10_nonvol"
    PM10Sul = "pm10_sul"


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

    def getFuel(self, unit="kg_sec"):
        return (self.getObject("fuel_%s" % unit), "kg")

    def get_value(
        self, pollutant_type: PollutantType, unit: Literal["kg_hour", "g_kg"]
    ) -> float:
        key = f"{pollutant_type.value}_{unit}"
        return self._objects.get(key, 0.0)

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

    def setGeometryText(self, var: Optional[str]):
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
        # Fast path: bypass Emission.__init__ / Store.__init__ / addObject() entirely.
        # All that is needed is a renamed copy of _objects (co_g → co_kg, etc.) plus
        # the two metadata attributes.  object.__new__ skips the constructor chain;
        # we then assign the three attributes directly.
        # This is safe because:
        #  - Emission has no __slots__ and no post-init side-effects beyond _objects,
        #    _geometry_wkt, and _vertical_ext.
        #  - The caller (MovementSourceModule) only reads get_value() / getGeometryText()
        #    / getVerticalExtent() on the result; it never calls add() on it.
        #  - We cannot mutate the source object because cached gate/flight/taxi emissions
        #    are shared across movements in the same group.
        new_em = object.__new__(Emission)
        new_em._objects = {
            (k[:-2] + "_kg" if (k.endswith("_g") and not k.endswith("_kg")) else k): (
                v / 1000.0 if (k.endswith("_g") and not k.endswith("_kg")) else v
            )
            for k, v in self._objects.items()
        }
        new_em._geometry_wkt = self._geometry_wkt
        new_em._vertical_ext = self._vertical_ext
        return new_em

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

    def add_from_mode_result(self, mode_result, scale: float = 1.0) -> None:
        """Add emissions from a FOCA-helicopter ``ModeResult`` (Phase 1).

        ``ModeResult`` carries pre-totalled values for one LTO mode (GI/TO/AP)
        including all engines: fuel_kg, nox_g, hc_g, co_g, pm_g, co2_g.

        Helicopters bypass the EmissionIndex pathway entirely (no precomputed
        EI table lookups under FOCA 2015 clean schema); ``compute_lto`` from
        ``foca_heli_utils`` returns the totals directly. This helper writes
        them into the standard ``Emission`` accumulator so downstream output
        modules treat helicopter emissions identically to fixed-wing ones.

        ``scale`` applies a multiplicative fraction (0.0-1.0) on the mode
        contribution. FOCA 2015 allocates Ground Idle (GI) emissions across
        the departure cycle (80% of GI) and the arrival cycle (20% of GI):
        callers pass scale=0.8 for departure GI and scale=0.2 for arrival
        GI. For TO and AP modes the convention is scale=1.0 (the default).

        PM mass is written to PM10 (helicopters' soot is total PM in FOCA's
        definition). PM1/PM2/PM10Organic/PM10Nonvol/PM10Sul are not split out;
        future enhancement can populate the size-fractionated buckets from
        FOCA's mean particle size formulas.
        """
        self.addValue("fuel_kg", mode_result.fuel_kg * scale)
        self.add_value(PollutantType.NOx, PollutantUnit.GRAM, mode_result.nox_g * scale)
        self.add_value(PollutantType.HC, PollutantUnit.GRAM, mode_result.hc_g * scale)
        self.add_value(PollutantType.CO, PollutantUnit.GRAM, mode_result.co_g * scale)
        self.add_value(PollutantType.PM10, PollutantUnit.GRAM, mode_result.pm_g * scale)
        self.add_value(PollutantType.CO2, PollutantUnit.GRAM, mode_result.co2_g * scale)

    def addGeneric(self, emission_index_, factor, unit, new_unit=""):
        for key in list(emission_index_.getObjects().keys()):
            self.addValue(
                "%s" % (self.rreplace(key, unit, new_unit, 1)),
                emission_index_.getObject("%s" % key) * factor,
            )

    def getFuel(self, unit: str = "kg") -> Tuple[float, str]:
        return self.getObject("fuel_%s" % unit), "kg"

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
        multiplier = 1

        # Fallback: if the Emission object hasn't been transposed to the
        # requested unit, read from the other unit's key and convert on the
        # fly.  The earlier version of this code had the multipliers inverted
        # (GRAM fallback used 0.001, KG fallback used 1000), which would
        # return a 10^6 -off value if ever triggered.  Not a production
        # regression because emissions are transposeToKilograms()'d before
        # reaching the callers, but the fallback is still reachable from
        # scripts and tests that call calculate_emissions_per_segment()
        # directly.
        if key not in self._objects:
            if unit == PollutantUnit.GRAM:
                # Stored in kg (co_kg); convert kg → g by ×1000.
                key = f"{pollutant_type.value}_{PollutantUnit.KG.value}"
                multiplier = 1000
            elif unit == PollutantUnit.KG:
                # Stored in g (co_g); convert g → kg by ÷1000.
                key = f"{pollutant_type.value}_{PollutantUnit.GRAM.value}"
                multiplier = 0.001

        return self._objects[key] * multiplier

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
