import math
from typing import Optional

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import EmissionIndex, PollutantType
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.bffm2 import calculate_emission_index
from open_alaqs.core.tools.twin_quadratic_fit_method import \
    calculate_fuel_flow_from_power_setting

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

        # Cache for BFFM2 emission index results, keyed by
        # (rounded_fuel_flow, installation_corrections, ambient_conditions).
        # Per-instance so different engines never share cached values.
        self._bffm2_cache: dict = {}

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

    def getEmissionIndexByModeWithMEEM(
        self,
        mode,
        p_amb_Pa,
        mach,
        power_setting=None,
        altitude_m=0.0,
        T_amb_K=None,
        meem_version="v1",
    ):
        """
        Per-mode EI with MEEM nvPM correction applied at actual segment
        conditions.  Routes to MEEM V1 (ICAO CAEP/13-MDG) or MEEM V2
        (ICAO CAEP/13-WG3) based on the ``meem_version`` kwarg.

        V1 (default) — interpolates nvPM EI on % max thrust.  For the
        LTO branch (altitude ≤ 914 m) this reduces to log-log mass
        interpolation and linear number interpolation at the segment's
        actual power setting.  For non-LTO it additionally applies the
        ISA altitude-correction chain (T/P at engine inlet, combustor
        inlet at altitude and at ground reference, GR-equivalent thrust)
        and the DLR enrichment factor φ.

        V2 — interpolates nvPM EI on BFFM2-adjusted fuel flow (FFadj in
        kg/s) per CAEP14 v12's preferred method.  FFadj anchor values are
        derived from each EEDB mode's fuel_kg_sec (which at ISA+Mach=0
        equals the reference FF).  The segment's target FFadj is computed
        from the mode's reference FF and the current ambient θ/δ/Mach via
        the BFFM2 formula.  The altitude-correction chain for non-LTO is
        identical to V1 — only the interpolation step differs.

        At LTO under real ambient conditions, V1 and V2 produce different
        numbers (~16% gap at the CAEP14 reference case for engine 10GE129
        at climb-out 253 ft, Mach 0.228).  They coincide only at exact
        ISA + Mach=0 + anchor-thrust conditions.

        Falls back to plain getEmissionIndexByMode(mode) without raising
        if any prerequisite is missing: fewer than 4 EEDB points, a mode
        without a power setting, a mode whose nvpm_g_kg or nvpm_number_kg
        is None, missing fuel_kg_sec for V2, or any exception in the MEEM
        computation.

        :param mode:          operating mode ("T/O","C/O","App","Idle" or
                              their aliases "TO","CL","AP","TX","Takeoff", ...).
        :param p_amb_Pa:      ambient static pressure in Pa at the segment.
        :param mach:          flight Mach number (≥ 0).
        :param power_setting: segment thrust F/F00 (0..1 typical).  V1 uses
                              this as the interpolation target.  For V2 it
                              is used only as a fallback for identifying
                              which mode's FF_ref to use when the requested
                              mode lacks fuel_kg_sec.
        :param altitude_m:    segment altitude above MSL (m).  >914 m
                              triggers altitude correction chain.
        :param T_amb_K:       optional ambient static temperature (K).  If
                              None, ISA at altitude_m is used.
        :param meem_version:  "v1" (default, CAEP/13-MDG) or "v2"
                              (CAEP/13-WG3 / CAEP14 v12 preferred).
        :return: EmissionIndex with MEEM-corrected nvpm_g_kg and
                 nvpm_number_kg; other fields unchanged from base bymode.
        """
        base_ei = self.getEmissionIndexByMode(mode)
        if base_ei is None:
            return None

        try:
            # Build anchor arrays from every mode on the engine that has
            # nvPM data. Sorted by thrust for V1, sorted by FFadj for V2.
            ts, mass_mgkg, number_nkg, ff_ref_kgs = [], [], [], []
            for m_, obj_ in self.getObjects().items():
                ei_ = obj_.get("emission_index") if isinstance(obj_, dict) else None
                if ei_ is None:
                    continue
                nvpm_m_g = ei_.getObject("nvpm_g_kg")
                nvpm_n = ei_.getObject("nvpm_number_kg")
                if nvpm_m_g is None or nvpm_n is None:
                    return base_ei
                power = self.getPowerSettingByMode(m_)
                if power is None:
                    continue
                ts.append(float(power))
                mass_mgkg.append(float(nvpm_m_g) * 1000.0)
                number_nkg.append(float(nvpm_n))
                # V2 requires each mode's EEDB reference fuel flow (kg/s)
                ff_ref_kgs.append(float(ei_.getObject("fuel_kg_sec") or 0.0))

            if len(ts) < 4:
                return base_ei

            if power_setting is None:
                ps_target = self.getPowerSettingByMode(mode)
                if ps_target is None:
                    alt = self.getAlternativeModeNames().get(mode)
                    if alt is not None:
                        ps_target = self.getPowerSettingByMode(alt)
                if ps_target is None:
                    return base_ei
                ps_target = float(ps_target)
            else:
                ps_target = max(0.0, min(1.2, float(power_setting)))

            opr = float(getattr(self, "_press_ratio", None) or 30.0)

            # Phase label: CAEP14 uses this to pick compressor efficiency
            # for the altitude correction. Map ALAQS mode → CAEP14 phase.
            phase = {
                "T/O": "TAKE OFF",
                "TO": "TAKE OFF",
                "Takeoff": "TAKE OFF",
                "C/O": "CLIMB OUT",
                "CL": "CLIMB OUT",
                "Climbout": "CLIMB OUT",
                "App": "APPROACH",
                "AP": "APPROACH",
                "Approach": "APPROACH",
                "Idle": "IDLE",
                "TX": "IDLE",
            }.get(mode, "CLIMB OUT")

            apply_alt = altitude_m is not None and float(altitude_m) > 914.0

            version = str(meem_version or "v1").lower()
            if version == "v2":
                # MEEM V2: interpolate on BFFM2-adjusted fuel flow.
                # Anchors are FF_ref per mode (which at ISA+Mach=0 equal FFadj).
                if any(ff <= 0 for ff in ff_ref_kgs):
                    # V2 requires FF for every mode; fall back to V1 if missing.
                    logger.debug("MEEM V2 fall-through (missing FF) for mode %s", mode)
                    version = "v1"

            if version == "v2":
                from open_alaqs.core.tools.meem_v2 import (
                    calculate_nvpm_ei_v2, compute_ffadj_for_segment)

                # Find this mode's FF_ref (the mode the segment is operating in)
                # and compute the segment's target FFadj at current ambient.
                # ps_target corresponds to the EEDB anchor thrust for this mode.
                # We approximate the segment's FF_ref by interpolating the
                # mode FFs on % thrust — i.e. if the segment is at 0.67 thrust
                # between anchors 0.30 (FF=0.225) and 0.85 (FF=0.658), the
                # segment's FF_ref sits between those two FF anchors.
                ts_sorted = sorted(zip(ts, ff_ref_kgs), key=lambda p: p[0])
                ts_s = [p[0] for p in ts_sorted]
                ff_s = [p[1] for p in ts_sorted]
                # Linear interpolation on (% thrust, FF_ref) to get segment FF_ref
                if ps_target <= ts_s[0]:
                    seg_ff_ref = ff_s[0]
                elif ps_target >= ts_s[-1]:
                    seg_ff_ref = ff_s[-1]
                else:
                    for i in range(len(ts_s) - 1):
                        if ts_s[i] <= ps_target <= ts_s[i + 1]:
                            if ts_s[i + 1] == ts_s[i]:
                                seg_ff_ref = ff_s[i]
                            else:
                                frac = (ps_target - ts_s[i]) / (ts_s[i + 1] - ts_s[i])
                                seg_ff_ref = ff_s[i] + frac * (ff_s[i + 1] - ff_s[i])
                            break
                    else:
                        seg_ff_ref = ff_s[-1]

                ffadj_target = compute_ffadj_for_segment(
                    ff_ref_kgs=seg_ff_ref,
                    altitude_m=float(altitude_m or 0.0),
                    mach=float(mach),
                    T_ambient_K=T_amb_K,
                    P_ambient_Pa=float(p_amb_Pa) if p_amb_Pa else None,
                )
                result = calculate_nvpm_ei_v2(
                    ffadj_target_kgs=ffadj_target,
                    ffadj_anchors=ff_s,  # already sorted by FF (since thrust & FF co-sort)
                    ei_mass_mgkg=[m for t, m in sorted(zip(ts, mass_mgkg))],
                    ei_number_nkg=[n for t, n in sorted(zip(ts, number_nkg))],
                    altitude_m=float(altitude_m or 0.0),
                    mach=float(mach),
                    opr=opr,
                    phase=phase,
                    apply_altitude_correction=apply_alt,
                    T_ambient_K=T_amb_K,
                    P_ambient_Pa=float(p_amb_Pa) if p_amb_Pa else None,
                )
            else:
                from open_alaqs.core.tools.meem_v1 import calculate_nvpm_ei

                result = calculate_nvpm_ei(
                    power_setting=ps_target,
                    thrust_settings=ts,
                    ei_mass_mgkg=mass_mgkg,
                    ei_number_nkg=number_nkg,
                    altitude_m=float(altitude_m or 0.0),
                    mach=float(mach),
                    opr=opr,
                    phase=phase,
                    apply_altitude_correction=apply_alt,
                    T_ambient_K=T_amb_K,
                    P_ambient_Pa=float(p_amb_Pa) if p_amb_Pa else None,
                )

            corrected = EmissionIndex(
                initValues=dict(base_ei._objects), defaultValues=defaultEI
            )
            corrected.setObject("nvpm_g_kg", result.nvpm_mass_ei_mgkg / 1000.0)
            corrected.setObject("nvpm_number_kg", result.nvpm_number_ei_nkg)
            return corrected
        except Exception as exc:
            logger.debug(
                "MEEM %s fall-through for mode %s: %s", meem_version, mode, exc
            )
            return base_ei

    def getICAOEngineEmissionsDB(self, index1_power=False, id2=None, format=""):
        icao_eedb: dict[float, EmissionIndex] = {}
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
            for p in [PollutantType.NOx, PollutantType.CO, PollutantType.HC]:
                icao_eedb_bffm2[p] = {}
                for m in icao_eedb:
                    icao_eedb_bffm2[p][map_names_[m] if m in map_names_ else m] = {
                        icao_eedb[m].getFuel()[0]: icao_eedb[m].get_value(p, "g_kg")
                    }  # units: kg, g/kg

            return icao_eedb_bffm2
        return icao_eedb

    def getEmissionIndexByEngineState(
        self, power_setting, method={"name": "BFFM2", "config": {}}, fuel_flow=None
    ):
        emission_index = None

        # If fuel flow is provided directly, skip power setting conversion and use fuel flow
        if fuel_flow is not None and fuel_flow > 0:
            return self.getEmissionIndexByFuelFlow(fuel_flow, method)
        else:
            logger.debug(
                f"Using power setting: {power_setting}% (fuel_flow={fuel_flow} not usable)"
            )

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
        elif method["name"].upper() == "BFFM2":

            # get map power-setting [%]:fuel flow [kg/s]
            _eedb_ff = self.getICAOEngineEmissionsDB(True, "fuel_kg_sec")
            ff_ref = calculate_fuel_flow_from_power_setting(power_setting, _eedb_ff)

            if ff_ref is None:
                return None

            # Convert reference FF to ambient FF before calling getEmissionIndexByFuelFlow,
            # which itself calls calculate_emission_index with the ambient FF and applies
            # the inverse correction internally:
            #     ff_ref_internal = ff_amb / delta * theta^3.8 * exp(0.2*M^2).
            # Without this pre-conversion the function double-applies the theta/delta/Mach
            # correction, producing a systematically wrong interpolation position on the
            # EEDB curve.  Formula per SAE AIR-5715 / CAEP14 (applied universally for both
            # LTO and non-LTO).
            try:
                _T = method["config"]["ambient_conditions"].getTemperature()
                _P = method["config"]["ambient_conditions"].getPressure()
                _mach = float(method["config"].get("mach_number", 0.0))
                _theta = _T / 288.15
                _delta = _P / 101325.0
            except (AttributeError, KeyError, TypeError) as _exc:
                # Ambient conditions unavailable — fall back to ISA (theta=1, delta=1, M=0)
                logger.warning(
                    "BFFM2 FF conversion: ambient_conditions unavailable (%s); "
                    "falling back to ISA.",
                    _exc,
                )
                _theta, _delta, _mach = 1.0, 1.0, 0.0

            fuel_flow = ff_ref * _delta / (_theta**3.8) / math.exp(0.2 * _mach**2)

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

        if method["name"].upper() == "BFFM2":
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
        """
        Compute the BFFM2 emission index for a given AMBIENT fuel flow.

        :param fuel_flow: Ambient fuel flow (kg/s).
                         When called from the power-setting path of
                         getEmissionIndexByEngineState, the caller is
                         responsible for converting the twin-quadratic
                         reference FF to ambient FF before calling here.
        :param method:   Method dict with name and config.
        """
        emission_index = EmissionIndex(initValues={}, defaultValues=defaultEI)

        if method["name"].upper() == "BFFM2":
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
                "mach_number": 0.00,  # airport LAQ default; cruise callers must supply Mach explicitly
                "relative_humidity": 0.6,
            }
            if (
                "config" in method
                and "ambient_conditions" in method["config"]
                and method["config"]["ambient_conditions"] is not None
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

            # Build a hashable cache key from all inputs that affect the result.
            # fuel_flow is rounded to 4 dp to avoid cache misses from floating-point
            # noise between otherwise-identical trajectory segments.
            _cache_key = (
                round(fuel_flow, 4),
                tuple(sorted(installation_corrections.items())),
                tuple(sorted(ambient_conditions.items())),
            )
            if _cache_key in self._bffm2_cache:
                # Shallow copy: EmissionIndex._objects is a flat dict of floats,
                # so dict() is safe and ~50x faster than deepcopy.  Callers may
                # freely mutate the returned object without affecting the cache.
                _cached = self._bffm2_cache[_cache_key]
                return EmissionIndex(
                    initValues=dict(_cached._objects), defaultValues=defaultEI
                )

            # Non-adjusted reference from EEDB at ISA conditions
            # maps fuel flow and emission indices
            icao_eedb_bffm2 = self.getICAOEngineEmissionsDB(format="BFFM2")
            # TODO OPENGIS.ch: this list is defined twice, once here and once in `getICAOEngineEmissionsDB`
            bffm2_keys = [PollutantType.NOx, PollutantType.CO, PollutantType.HC]

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
            self._bffm2_cache[_cache_key] = emission_index
            return emission_index
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
            "pm10_nonvol_g_kg": "pm10_nonvol",
            "pm10_sul_g_kg": "pm10_sul",
            "pm10_organic_g_kg": "pm10_organic",
            "nvpm_g_kg": "pm10_nonvol",  # same physical quantity — EEDB nvPM mass EI
            "nvpm_number_kg": "nvpm_number_ei",
        }

        # Map the values
        for ei_val_key, val_key in key_mapping.items():

            # Set the values with not update values with empty strings
            if val_key in val and isinstance(val.get(val_key), (int, float)):
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
