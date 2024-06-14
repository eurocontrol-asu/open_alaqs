from typing import Optional

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import EmissionIndex
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.bffm2 import calculate_emission_index
from open_alaqs.core.tools.twin_quadratic_fit_method import (
    calculate_fuel_flow_from_power_setting,
)

logger = get_logger(__name__)

defaultEI = {
    "fuel_kg_sec": 0.0,
    "co_g_kg": 0.0,
    "co2_g_kg": 3.16 * 1000.0,
    "hc_g_kg": 0.0,
    "nox_g_kg": 0.0,
    "sox_g_kg": 0.0,
    "pm10_g_kg": 0.0,
    "p1_g_kg": 0.0,
    "p2_g_kg": 0.0,
    "smoke_number": 0.0,
    "smoke_number_maximum": 0.0,
    "fuel_type": "",
    "pm10_prefoa3_g_kg": 0.0,
    "pm10_nonvol_g_kg": 0.0,
    "pm10_sul_g_kg": 0.0,
    "pm10_organic_g_kg": 0.0,
    "nvpm_g_kg": 0.0,
    "nvpm_number_kg": 0.0,
}


class HelicopterEngineEmissionIndex(Store):
    def __init__(self):
        Store.__init__(self)

        self._modes_powersetting_map = {
            "GI1": 0.0,  # Idle Eng#1
            "GI2": 0.0,  # Idle Eng#2
            "AP": 0.0,  # Approach
            "TO": 0.0,  # Hover and Climb
        }

    def setModePowerSetting(self, mode, power_setting):
        self._modes_powersetting_map[mode] = power_setting

    def getPowerSettingByMode(self, mode):
        return self._modes_powersetting_map.get(mode)

    def getModes(self):
        return ["GI1", "GI2", "TO", "AP"]

    def setObject(self, mode, val):
        # if self.hasKey(mode):
        #     logger.warning("Already found engine ei with mode '%s' for engine with full name '%s'.
        #     Replacing existing entry." % (mode, val["engine_full_name"] if "engine_full_name" in val else "unknown"))

        ei_val = {}
        ei_val["fuel_kg_sec"] = (
            val["%s_ff_per_engine_kg_s" % (mode.lower())]
            if "%s_ff_per_engine_kg_s" % (mode.lower()) in val
            else 0.0
        )

        for k in ["co", "hc", "nox", "pm10"]:
            if k == "pm10":
                ei_val["%s_g_kg" % k] = val["%s_eipm_g_kg" % (mode.lower())]
            else:
                ei_val["%s_g_kg" % k] = val["%s_ei%s_g_kg" % (mode.lower(), k)]

        # AvGas 3.10 (Piston Engine Powered Helicopters) or 3.15 for Jet Fuel (Turboshaft Powered Helicopters)
        if "engine_type" in val:
            ei_val["co2_g_kg"] = (
                val["%s_ff_per_engine_kg_s" % (mode.lower())] * 3.10 * 1000
                if val["engine_type"] == "PISTON"
                else val["%s_ff_per_engine_kg_s" % (mode.lower())] * 3.16 * 1000
            )
        else:
            ei_val["co2_g_kg"] = (
                val["%s_ff_per_engine_kg_s" % (mode.lower())] * 3.16 * 1000
            )
        ei_val["fuel_type"] = "AvGas" if val["engine_type"] == "PISTON" else "Jet Fuel"

        # ToDo: Add all pollutants
        for k in [
            "sox",
            "p1",
            "p2",
            "smoke_number",
            "smoke_number_maximum",
            "pm10_prefoa3",
            "pm10_nonvol",
            "pm10_sul",
            "pm10_organic",
        ]:
            ei_val["%s_g_kg" % k] = 0.0
            ei_val["%s_g_kg" % k] = 0.0
            ei_val["%s_g_kg" % k] = 0.0
            ei_val["%s_g_kg" % k] = 0.0

        ei_val["time_min"] = val["%s_time_min" % (mode.lower())]

        self._objects[mode] = {
            "emission_index": EmissionIndex(initValues=ei_val, defaultValues=defaultEI),
            "source": val["source"] if "source" in val else "",
            "coolant": val["coolant"] if "coolant" in val else "",
            "combustion_technology": (
                val["combustion_technology"] if "combustion_technology" in val else ""
            ),
            "technology_age": val["technology_age"] if "technology_age" in val else "",
        }

        # update mode if provided
        # ToDo: Add "power_setting" to default_helicopter_engine_ei table in ALAQS DB
        # if "power_setting" in val:
        #     self.setModePowerSetting(mode, val["%s_power_setting"%(mode.lower())])

    def getEmissionIndexByMode(self, mode) -> Optional[EmissionIndex]:
        emission_index = None
        if self.hasKey(mode):
            emission_index = self.getObject(mode)
            if emission_index is not None and "emission_index" in emission_index:
                emission_index = emission_index["emission_index"]
        else:
            raise Exception("Did not find emission index for mode '%s'." % (str(mode)))
        return emission_index

    def getDefaultIndex(self, mode: str) -> dict:
        return {
            "mode": str(mode),
            "emission_index": EmissionIndex(defaultValues=defaultEI),
            "thrust": 0.0,
            "fuel_type": "",
            "source": "",
            "coolant": "",
            "combustion_technology": "",
            "technology_age": "",
        }

    def __str__(self):
        val = ""
        for mode, ps in sorted(
            list(self._modes_powersetting_map.items()), key=lambda x: x[1]
        ):
            val += "\n"
            val += "\t Power setting is %.2f for mode '%s':" % (float(ps), str(mode))
            val += "\t %s" % (
                "\n\t".join(str(self.getEmissionIndexByMode(mode)).split("\n"))
            )
        return val


class EngineEmissionIndex(Store):
    def __init__(self):
        Store.__init__(self)

        self._modes_powersetting_map = {
            "T/O": 1.0,  # Takeoff
            "C/O": 0.85,  # Climbout
            "App": 0.30,  # Approach
            "Idle": 0.07,  # Idle
        }

    def setModePowerSetting(self, mode, power_setting):
        self._modes_powersetting_map[mode] = power_setting

    def getPowerSettingByMode(self, mode):
        return self._modes_powersetting_map.get(mode)

    def getAlternativeModeNames(self):
        return {
            "TX": "Idle",
            "AP": "App",
            "CL": "C/O",
            "TO": "T/O",
            "Idle": "TX",
            "App": "AP",
            "C/O": "CL",
            "T/O": "TO",
            "Takeoff": "T/O",
            "Climbout": "C/O",
            "Approach": "AP",
        }

    def getEmissionIndexByMode(self, mode) -> Optional[EmissionIndex]:
        emission_index = None

        # fix naming conventions
        if not self.hasKey(mode):
            if mode in self.getAlternativeModeNames() and self.hasKey(
                self.getAlternativeModeNames()[mode]
            ):
                mode = self.getAlternativeModeNames()[mode]

        if self.hasKey(mode):
            emission_index = self.getObject(mode)

            if emission_index is not None and "emission_index" in emission_index:
                emission_index = emission_index["emission_index"]
        else:
            raise Exception("Did not find emission index for mode '%s'." % (str(mode)))

        return emission_index

    def getICAOEngineEmissionsDB(self, index1_power=False, id2=None, format=""):
        icao_eedb = {}
        for mode_, obj_ in list(self.getObjects().items()):
            emission_index_ = (
                obj_["emission_index"] if "emission_index" in obj_ else None
            )

            index1 = mode_
            if index1_power:
                index1 = self.getPowerSettingByMode(mode_)

            if not (emission_index_ is None or index1 is None):
                if id2 is not None and emission_index_.hasKey(id2):
                    icao_eedb[index1] = emission_index_.getObject(id2)
                else:
                    icao_eedb[index1] = emission_index_

        if not len(list(icao_eedb.keys())) == 4:
            logger.error(
                "Found only %i data points for combinations of engine-thrust setting [%%] and "
                "fuel flow [kg/s], 4 points expected."
                % (int(len(list(icao_eedb.keys()))))
            )
            logger.debug(icao_eedb)

        if format.lower() == "bffm2":
            icao_eedb_bffm2 = {}
            map_names_ = {
                "App": "Approach",
                "AP": "Approach",
                "TO": "Takeoff",
                "T/O": "Takeoff",
                "CL": "Climbout",
                "C/O": "Climbout",
                "TX": "Idle",
            }
            for p in ["NOx", "CO", "HC"]:
                icao_eedb_bffm2[p] = {}
                for m in icao_eedb:
                    icao_eedb_bffm2[p][map_names_[m] if m in map_names_ else m] = {
                        icao_eedb[m].getFuel()[0]: icao_eedb[m].getValue(p)[0]
                    }  # units: kg, g/kg

            return icao_eedb_bffm2
        return icao_eedb

    def getEmissionIndexByPowerSetting(
        self, power_setting, method={"name": "BFFM2", "config": {}}
    ):
        emission_index = None

        if method["name"] == "matching":
            # match power setting with mode
            mode_with_min_delta = ""
            for index_mode, mode in enumerate(self._modes_powersetting_map.keys()):
                if not index_mode or (
                    index_mode
                    and (
                        abs(self._modes_powersetting_map[mode] - power_setting)
                        < abs(
                            self._modes_powersetting_map[mode_with_min_delta]
                            - power_setting
                        )
                    )
                ):
                    mode_with_min_delta = mode
            emission_index = self.getEmissionIndexByMode(mode_with_min_delta)

        elif method["name"] == "linear_scaling":
            # scale power setting with linear interpolation between surrounding modes
            mode1 = ""
            mode2 = ""
            # find mode1
            for index_mode, mode in enumerate(self._modes_powersetting_map.keys()):
                if not mode1:
                    mode1 = mode

                # use matching to nearest point, but not matching to nearest neighbour!
                if (
                    not self._modes_powersetting_map[mode1]
                    == self._modes_powersetting_map[mode]
                ):
                    if abs(self._modes_powersetting_map[mode] - power_setting) < abs(
                        self._modes_powersetting_map[mode1] - power_setting
                    ):
                        mode1 = mode
            # find mode2
            for index_mode, mode in enumerate(self._modes_powersetting_map.keys()):
                if (
                    self._modes_powersetting_map[mode]
                    == self._modes_powersetting_map[mode1]
                ):
                    continue

                if not mode2:
                    mode2 = mode

                # use matching to nearest point, but not matching to nearest neighbour!
                if (
                    not self._modes_powersetting_map[mode2]
                    == self._modes_powersetting_map[mode]
                ):
                    if abs(self._modes_powersetting_map[mode] - power_setting) < abs(
                        self._modes_powersetting_map[mode2] - power_setting
                    ):
                        mode2 = mode

            # y = a*x +b
            # logger.debug("Power_setting is %f, surrounding modes are mode1='%s', mode2='%s'" % (power_setting, mode1,mode2))
            if mode1 and mode2:
                emission_index_a = (
                    self.getEmissionIndexByMode(mode2)
                    - self.getEmissionIndexByMode(mode1)
                ) / (
                    self._modes_powersetting_map[mode2]
                    - self._modes_powersetting_map[mode1]
                )
                emission_index_b = (
                    self.getEmissionIndexByMode(mode1)
                    - self._modes_powersetting_map[mode1] * emission_index_a
                )

                emission_index = emission_index_a * power_setting + emission_index_b
            else:
                raise Exception(
                    "Did not find mode: mode1='%s', mode2='%s'" % (mode1, mode2)
                )

        # twin quadratic fit to convert power setting to fuel flow
        elif method["name"] == "BFFM2":

            # get map power-setting [%]:fuel flow [kg/s]
            fuel_flow = calculate_fuel_flow_from_power_setting(
                power_setting, self.getICAOEngineEmissionsDB(True, "fuel_kg_sec")
            )
            if fuel_flow is None:
                return None

            # apply method (e.g. BFFM2) to convert fuel flow to emission index
            # logger.debug("Converted power setting of %.3f [%%] to fuel flow of %.3f kg/s." % (power_setting, fuel_flow))
            emission_index = self.getEmissionIndexByFuelFlow(fuel_flow, method)
        else:
            logger.error("Method '%s' not implemented." % (method["name"]))

        return emission_index

    def plot(
        self, method={"name": "BFFM2", "config": {}}, suffix="", multipage={}, title=""
    ):
        config = {}
        if "config" in method:
            config.update(method["config"])

        if method["name"] == "BFFM2":
            # Installation effects
            installation_corrections = {}
            if (
                "config" in method
                and "installation_corrections" in method["config"]
                and method["config"]["installation_corrections"]
            ):
                installation_corrections.update(
                    method["config"]["installation_corrections"]
                )

            # Ambient conditions
            ambient_conditions = {}
            if (
                config
                and "ambient_conditions" in config
                and config["ambient_conditions"]
            ):
                ambient_conditions.update(config["ambient_conditions"])

            # Non-adjusted reference from EEDB at ISA conditions
            # maps fuel flow and emission indices
            self.getICAOEngineEmissionsDB(format="BFFM2")
            logger.debug("ICAO EEDB in format '%s':" % ("BFFM2"))
            # logger.debug(icao_eedb_bffm2)
            # for pollutant in ["NOx", "CO", "HC"]:
            #     BFFM2.plotEmissionIndexNominal(
            #         pollutant,
            #         icao_eedb_bffm2,
            #         ambient_conditions={} if not (config and "ambient_conditions" in config and config["ambient_conditions"]) else config["ambient_conditions"],
            #         installation_corrections={} if not (config and "installation_corrections" in config and config["installation_corrections"]) else config["installation_corrections"],
            #         range_relative_fuelflow=[0.80, 1.2] if not ("relative_range" in config and config["relative_range"]) else config["relative_range"],
            #         steps=51 if not ("steps" in config and config["steps"]) else config["steps"],
            #         suffix=suffix,
            #         multipage=multipage,
            #         title=title
            #     )

    def getEmissionIndexByFuelFlow(
        self, fuel_flow, method={"name": "BFFM2", "config": {}}
    ):
        emission_index = EmissionIndex(initValues={}, defaultValues=defaultEI)

        if method["name"] == "BFFM2":
            bffm2_keys = ["NOx", "CO", "HC"]

            # Installation effects
            installation_corrections = {}
            if (
                "config" in method
                and "installation_corrections" in method["config"]
                and method["config"]["installation_corrections"]
            ):
                installation_corrections.update(
                    method["config"]["installation_corrections"]
                )

            ambient_conditions = {
                "temperature_in_Kelvin": 288.15,
                "pressure_in_Pa": 1013.25 * 100,
                "mach_number": 0.84,  # TrueAirspeed/340.29
                "relative_humidity": 0.6,
            }
            if (
                "config" in method
                and "ambient_conditions" in method["config"]
                and method["config"]["ambient_conditions"]
            ):
                # $$
                try:
                    ac = {
                        "temperature_in_Kelvin": method["config"][
                            "ambient_conditions"
                        ].getTemperature(),
                        "pressure_in_Pa": method["config"][
                            "ambient_conditions"
                        ].getPressure(),
                        "mach_number": (
                            method["config"]["mach_number"]
                            if "mach_number" in list(method["config"].keys())
                            else 0.00
                        ),
                        "relative_humidity": method["config"][
                            "ambient_conditions"
                        ].getRelativeHumidity(),
                    }
                except Exception:
                    ac = ambient_conditions
                ambient_conditions.update(ac)

            # Non-adjusted reference from EEDB at ISA conditions
            # maps fuel flow and emission indices
            icao_eedb_bffm2 = self.getICAOEngineEmissionsDB(format="BFFM2")

            # Do the calculation
            emission_index.setObject("fuel_kg_sec", fuel_flow)
            for pollutant in bffm2_keys:
                val = calculate_emission_index(
                    pollutant,
                    fuel_flow,
                    icao_eedb_bffm2,
                    ambient_conditions=ambient_conditions,
                    installation_corrections=installation_corrections,
                )
                if "co" in pollutant.lower() and "co2" not in pollutant.lower():
                    emission_index.setObject("co_g_kg", val)
                if "nox" in pollutant.lower():
                    emission_index.setObject("nox_g_kg", val)
                if "hc" in pollutant.lower():
                    emission_index.setObject("hc_g_kg", val)
                # logger.debug("Calculated emission index '%s' for fuel flow '%.5f' is '%.5f'" % (pollutant, fuel_flow, val))
        else:
            logger.error(
                "Interpolation of emission indices with method '%s' not implemented."
                % (method["name"])
            )

        return emission_index

    def setObject(self, mode: str, val: dict):
        # if self.hasKey(mode):
        #     logger.warning("Already found engine ei with mode '%s' for engine with full name '%s'. Replacing existing entry." % (mode, val["engine_full_name"] if "engine_full_name" in val else "unknown"))

        # Create an empty dictionary to store the emission index values
        ei_val = {}

        # Create a dictionary with the key mapping
        key_mapping = {
            "fuel_kg_sec": "fuel_kg_sec",
            "smoke_number": "smoke_number",
            "smoke_number_maximum": "smoke_number_maximum",
            "co_g_kg": "co_ei",
            "hc_g_kg": "hc_ei",
            "nox_g_kg": "nox_ei",
            "sox_g_kg": "sox_ei",
            "pm10_g_kg": "pm10_ei",
            "p1_g_kg": "p1_ei",
            "p2_g_kg": "p2_ei",
            "pm10_prefoa3_g_kg": "pm10_prefoa3_ei",
            "pm10_nonvol_g_kg": "pm10_nonvol_ei",
            "pm10_sul_g_kg": "pm10_sul_ei",
            "pm10_organic_g_kg": "pm10_organic_ei",
            "nvpm_g_kg": "nvpm_ei",
            "nvpm_number_kg": "nvpm_number_ei",
        }

        # Map the values
        for ei_val_key, val_key in key_mapping.items():

            # Set the values with not update values with empty strings
            if val_key in val and isinstance(val.get(val_key), float):
                ei_val[ei_val_key] = val[val_key]

        # Create the emission index
        emission_index = EmissionIndex(initValues=ei_val, defaultValues=defaultEI)

        # Set the emission index for the specified mode
        self._objects[mode] = {
            "emission_index": emission_index,
            "source": val.get("source", ""),
            "coolant": val.get("coolant", ""),
            "combustion_technology": val.get("combustion_technology", ""),
            "technology_age": val.get("technology_age", ""),
        }

        # Update the mode if provided
        if "thrust" in val:
            self.setModePowerSetting(mode, val["thrust"])

    def getModes(self) -> list:
        return list(self.getObjects().keys())

    def getDefaultIndex(self, mode) -> dict:
        return {
            "mode": str(mode),
            "emission_index": EmissionIndex(defaultValues=defaultEI),
            "thrust": 0.0,
            "fuel_type": "",
            "source": "",
            "coolant": "",
            "combustion_technology": "",
            "technology_age": "",
        }

    def __str__(self):
        val = ""
        for mode, ps in sorted(
            list(self._modes_powersetting_map.items()), key=lambda x: x[1]
        ):
            val += "\n"
            val += "\t Power setting is %.2f for mode '%s':" % (float(ps), str(mode))
            val += "\t %s" % (
                "\n\t".join(str(self.getEmissionIndexByMode(mode)).split("\n"))
            )
        return val


class Engine:
    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {
                "name": "unknown",
                "emission_index": None,
                "start_emission_factors": None,
            }

        self._name = values_dict["name"] if "name" in values_dict else "unknown"
        # self._full_name = values_dict["full_name"] if "full_name" in values_dict else None
        self._emission_index = (
            values_dict["emission_index"] if "emission_index" in values_dict else None
        )
        self._start_emissions = (
            values_dict["start_emission_factors"]
            if "start_emission_factors" in values_dict
            else None
        )

    def setStartEmissions(self, ef):
        self._start_emissions = ef

    def getStartEmissions(self):
        return self._start_emissions

    def setEmissionIndex(self, ei):
        self._emission_index = ei

    def getEmissionIndex(self) -> Optional[EmissionIndex]:
        return self._emission_index

    def getName(self):
        return self._name

    # def setFullName(self, val):
    #     self._full_name = val
    # def getFullName(self):
    #     return self._full_name

    def __str__(self):
        val = "\n Engine with name '%s':" % (self.getName())
        val += "\n\t Emission indices: %s" % (
            "\n\t".join(str(self.getEmissionIndex()).split("\n"))
        )
        return val
