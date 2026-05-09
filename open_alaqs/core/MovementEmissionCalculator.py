"""
This class provides the emission calculation for movements.
"""

import abc
import difflib
from typing import Any, Optional, Tuple, TypedDict

from shapely.geometry import MultiLineString
from shapely.wkt import loads

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Aircraft import Aircraft
from open_alaqs.core.interfaces.AircraftTrajectory import (
    AircraftTrajectoryPoint,
    TrajectoryPoint,
)
from open_alaqs.core.interfaces.Emissions import (
    Emission,
    EmissionIndex,
    PollutantType,
    PollutantUnit,
)
from open_alaqs.core.interfaces.Engine import Engine
from open_alaqs.core.interfaces.Movement import Movement, defaultEmissions
from open_alaqs.core.tools import conversion, spatial
from open_alaqs.core.tools.nox_correction_ambient import (
    nox_correction_for_ambient_conditions,
)

logger = get_logger(__name__)


class EmissionsDict(TypedDict):
    distance_space: float
    distance_time: float
    emissions: list[Emission]


class MovementEmissionCalculator(abc.ABC):

    def __init__(self, departure_arrival: str):
        self._departure_arrival = departure_arrival

    def _is_arrival(self) -> bool:
        return self._departure_arrival.lower() not in ["d", "dep", "departure"]

    def _is_departure(self) -> bool:
        return not self._is_arrival()

    @abc.abstractmethod
    def calculate_emissions(self) -> list[EmissionsDict]:
        raise NotImplementedError


class GateEmissionCalculator(MovementEmissionCalculator):

    def __init__(self, gate, aircraft, departure_arrival, gate_emissions_code=1):
        MovementEmissionCalculator.__init__(self, departure_arrival)
        self._gate = gate
        self._aircraft = aircraft
        self._gate_emissions_code = gate_emissions_code

    def _calculate_ground_equipment_emissions(self, source_type):
        emissions = Emission(defaultValues=defaultEmissions)
        ac_group = self._get_aircraft_group_match(source_type)  # e.g. 'JET SMALL'
        occupancy_in_min = self._get_gate_occupancy(ac_group, source_type)

        emission_index = self._gate.getEmissionIndex(
            ac_group, self._departure_arrival, source_type
        )
        pollutants = (
            PollutantType.CO,
            PollutantType.HC,
            PollutantType.NOx,
            PollutantType.SOx,
            PollutantType.PM10,
        )

        if emission_index is not None:
            for pollutant_type in pollutants:
                value_kg_hour = emission_index.get_value(pollutant_type, "kg_hour")
                emissions.add_value(
                    pollutant_type,
                    PollutantUnit.GRAM,
                    # TODO OPENGIS.ch: move the kg_hour conversion within the `Emission.add_value` method
                    (value_kg_hour * 1000.0 * occupancy_in_min / 60.0),
                )

            emissions.setGeometryText(self._gate.getGeometryText())
            return {
                "distance_space": 0.0,
                "distance_time": 0.0,
                "emissions": [emissions],
            }

        return {}

    def calculate_emissions(self) -> list[EmissionsDict]:
        """Calculate gate emissions for a specific source based on the source
         name and time period. The method for calculating emissions from gates
         requires establishing the sum of four types of emissions:

        1. Emissions from GSE - Data comes from default_gate
        2. Emissions from GPU
        3. Emissions from APU
        4. Emissions from Main Engine Start-up
        """
        if not self._gate_emissions_code:
            return []

        emissions: list[EmissionsDict] = []

        # Calculate emissions for ground equipment (i.e. GSE and GPU)
        if self._aircraft.getGroup() != "HELICOPTER":
            gse_emissions = self._calculate_ground_equipment_emissions("gse")
            if gse_emissions:
                emissions.append(gse_emissions)

            gpu_emissions = self._calculate_ground_equipment_emissions("gpu")
            if gpu_emissions:
                emissions.append(gpu_emissions)

        return emissions

    def _get_aircraft_group_match(self, source_type):
        ac_group = self._aircraft.getGroup()
        if ac_group in self._gate.getEmissionProfileGroups(source_type=source_type):
            return ac_group

        matched = difflib.get_close_matches(
            ac_group,
            self._gate.getEmissionProfileGroups(source_type=source_type),
        )
        if matched:
            if not matched[0].lower() == ac_group.lower():
                logger.warning(
                    "Did not find a gate emission profile for source type '%s' and aircraft group '%s', "
                    "but matched to '%s'. Probably update the table 'default_gate_profiles'."
                    % (source_type, matched[0], ac_group)
                )
            return matched[0]

        return None

    def _get_gate_occupancy(self, ac_group, source_type):
        occupancy_in_min = 0.0
        profile_ = self._gate.getEmissionProfile(
            ac_group, self._departure_arrival, source_type
        )
        if profile_ is not None:
            occupancy_in_min = profile_.getOccupancy()

        return occupancy_in_min


class TaxiingEmissionCalculator(MovementEmissionCalculator):

    AVERAGE_DURATION_OF_STOP_AND_GOS_IN_S = 9.0
    TAXIING_TIME_THRESHOLD = 0.0

    def __init__(self, movement: Movement, method=None, mode="TX"):
        MovementEmissionCalculator.__init__(self, movement.getDepartureArrivalFlag())
        self._taxi_route = movement.getTaxiRoute()
        self._gate = movement.getGate()
        self._aircraft = movement.getAircraft()
        self._engine = movement.getAircraftEngine()
        self._engine_thrust_level_taxiing = movement.getEngineThrustLevelTaxiing()
        self._block_time = movement.getBlockTime()
        self._runway_time = movement.getRunwayTime()
        self._apu_code = movement.getAPUCode()
        self._gate_emissions_code = movement.getGateEmissionsCode()
        self._taxi_engine_count = movement.getTaxiEngineCount()
        self._taxi_fuel_ratio = movement.getTaxiFuelRatio()
        self._number_of_stops = movement.getNumberOfStops()
        self._movement_name = movement.getName()

        self._set_time_of_main_engine_start_before_takeoff_in_s = (
            movement.getSingleEngineTaxiingTimeOfMainEngineStartBeforeTakeoff()
        )
        self._set_time_of_main_engine_start_after_block_off_in_s = (
            movement.getSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff()
        )
        self._set_time_of_main_engine_off_after_runway_exit_in_s = (
            movement.getSingleEngineTaxiingMainEngineOffAfterRunwayExit()
        )

        self._method = method or {"name": "bymode", "config": {}}
        self._mode = mode

        self._total_taxiing_time = None
        if self._block_time is not None and self._runway_time is not None:
            self._total_taxiing_time = abs(self._block_time - self._runway_time)

        self._start_emissions = self._engine.getStartEmissions()
        self._include_start_emissions = self._start_emissions is not None

        # Tracks whether the start emissions for the engines covered by
        # single-engine taxi have already been added (once per movement).
        # Without this guard, _do_apply_single_engine_taxiing_emissions
        # would add them per taxi segment within the MES window, producing
        # K x taxi_engine_count x start_emissions overcount when the MES
        # window spans K > 1 segments.
        self._single_engine_start_added = False

    def calculate_emissions(self) -> list[EmissionsDict]:
        emissions: list[EmissionsDict] = []

        # CAEP14 v14: taxi is a ground operation with M=0. The shared
        # self._method["config"] dict is mutated by FlightEmissionCalculator
        # per segment to carry the per-segment Mach into the BFFM2 / MEEM
        # lookups. Without this isolation, taxi inherits the leftover Mach
        # from the previous flight's last trajectory segment, producing
        # 0.5-3% under-prediction of taxi fuel flow and a proportional
        # propagation to all pollutants. Force M=0 here for both bymode
        # (MEEM PM lookup) and BFFM2 (EI lookup + MEEM PM injection).
        _saved_mach = self._method["config"].get("mach_number", 0.0)
        self._method["config"]["mach_number"] = 0.0
        try:
            if self._method["name"] == "bymode":
                try:
                    ac = self._method["config"]["ambient_conditions"]
                    p_amb = float(ac.getPressure())
                    mver = str(self._method["config"].get("meem_version", "v1"))
                    emission_index_ = (
                        self._engine.getEmissionIndex().getEmissionIndexByModeWithMEEM(
                            self._mode,
                            p_amb,
                            0.0,
                            meem_version=mver,
                        )
                    )
                except Exception:
                    emission_index_ = (
                        self._engine.getEmissionIndex().getEmissionIndexByMode(
                            self._mode
                        )
                    )
            else:  # BFFM2 method
                # get emission indices based on the engine-thrust/fuel flow setting as defined in the movements table; fuel flow has priority
                emission_index_ = (
                    self._engine.getEmissionIndex().getEmissionIndexByEngineState(
                        self._engine_thrust_level_taxiing, method=self._method
                    )
                )
                # Inject PM and SOx from the mode EI — BFFM2 only computes NOx/CO/HC
                if emission_index_ is not None:
                    try:
                        mver = str(self._method["config"].get("meem_version", "v1"))
                        mode_ei_ = self._engine.getEmissionIndex().getEmissionIndexByModeWithMEEM(
                            self._mode,
                            float(
                                self._method["config"][
                                    "ambient_conditions"
                                ].getPressure()
                            ),
                            0.0,
                            meem_version=mver,
                        )
                    except Exception:
                        mode_ei_ = (
                            self._engine.getEmissionIndex().getEmissionIndexByMode(
                                self._mode
                            )
                        )
                if mode_ei_ is not None:
                    emission_index_ = EmissionIndex(
                        initValues=dict(emission_index_._objects)
                    )
                    for _field in (
                        "pm10_g_kg",
                        "pm10_nonvol_g_kg",
                        "pm10_sul_g_kg",
                        "pm10_organic_g_kg",
                        "nvpm_g_kg",
                        "nvpm_number_kg",
                        "p1_g_kg",
                        "p2_g_kg",
                    ):
                        _v = mode_ei_.getObject(_field)
                        if _v is not None:
                            emission_index_.setObject(_field, _v)
                    from open_alaqs.core.interfaces.Emissions import PollutantType

                    emission_index_.setObject(
                        "sox_g_kg",
                        mode_ei_.get_value(PollutantType.SOx, "g_kg"),
                    )
        finally:
            # Restore the prior Mach so subsequent operations on this method
            # dict are unaffected by the taxi isolation.
            self._method["config"]["mach_number"] = _saved_mach

        if emission_index_ is None:
            logger.error(
                "Did not find emission index for aircraft with type '%s'."
                % self._aircraft
            )
            return emissions

        if self._aircraft.getGroup() != "HELICOPTER":

            # calculate taxiing_length and taxiing_time_from_segments (initial)
            taxiing_length = 0.0
            init_taxiing_time_from_segments = 0.0
            for taxiway_segment_ in self._taxi_route.getSegments():
                taxiing_length += taxiway_segment_.getLength()
                init_taxiing_time_from_segments += taxiway_segment_.getTime()

            if self._total_taxiing_time is None:
                self._total_taxiing_time = init_taxiing_time_from_segments

            if self._total_taxiing_time <= self.TAXIING_TIME_THRESHOLD:
                logger.warning(
                    "The movement '%s' was skipped as the taxi route was not defined properly."
                    % self._movement_name
                )
                return emissions

            # In m/s
            taxiing_average_speed = conversion.convertToFloat(
                taxiing_length
            ) / conversion.convertToFloat(self._total_taxiing_time)

            # Total taxiing time for calculating taxiing emissions is taken from the Movements Table
            # Queuing emissions are added when taxiing time (traffic log) is greater than user defined taxiroute info (speed, time, etc)
            queuing_time = (
                (self._total_taxiing_time - init_taxiing_time_from_segments)
                if self._total_taxiing_time > init_taxiing_time_from_segments
                else 0
            )

            taxiing_time_while_aircraft_moving = 0.0

            apu_t, apu_em = self._load_apu_info()

            # Set the geometry as line with linear interpolation between start and endpoint
            for index_segment_, taxiway_segment_ in enumerate(
                self._taxi_route.getSegments()
            ):
                em_ = Emission(defaultValues=defaultEmissions)
                em_.setGeometryText(taxiway_segment_.getGeometryText())

                # Add emission factors,
                # Multiply by occupancy time and number of engines

                # If time spent in segments < taxiing time in movement table
                if self._total_taxiing_time <= init_taxiing_time_from_segments:
                    new_taxiway_segment_time = (
                        taxiway_segment_.getLength() / taxiing_average_speed
                    )
                else:
                    new_taxiway_segment_time = (
                        taxiway_segment_.getLength() / taxiway_segment_.getSpeed()
                    )

                taxiing_time_while_aircraft_moving += new_taxiway_segment_time

                number_of_engines = self._aircraft.getEngineCount()
                taxi_fuel_ratio = 1.0

                # APU emissions
                self._apply_apu_emissions(
                    em_, index_segment_, apu_t, apu_em, new_taxiway_segment_time
                )

                # Single engine taxiing emissions
                number_of_engines_, taxi_fuel_ratio_ = (
                    self._apply_single_engine_taxiing_emissions(
                        em_, index_segment_, taxiing_time_while_aircraft_moving
                    )
                )
                if number_of_engines_ is not None:
                    number_of_engines = number_of_engines_
                if taxi_fuel_ratio_ is not None:
                    taxi_fuel_ratio = taxi_fuel_ratio_

                em_.add(
                    emission_index_,
                    new_taxiway_segment_time * number_of_engines * taxi_fuel_ratio,
                )

                # Queuing emissions
                if index_segment_ == len(self._taxi_route.getSegments()) - 1:
                    em_.add(emission_index_, queuing_time * number_of_engines)

                    # Stop & Go emissions
                    if (
                        self._number_of_stops is not None
                        and self._number_of_stops > 0.0
                    ):
                        # Stop-and-Go emissions add AVERAGE_DURATION (9 s) per stop at idle
                        # thrust. Must multiply by number_of_engines to match the convention
                        # used for regular taxiing (line above) and for queuing time — the
                        # emission_index is per engine per kg fuel, and fuel burn scales
                        # with engine count. Prior version omitted * number_of_engines,
                        # producing half the correct emissions on twin-engine aircraft.
                        em_.add(
                            emission_index_,
                            self.AVERAGE_DURATION_OF_STOP_AND_GOS_IN_S
                            * self._number_of_stops
                            * number_of_engines,
                        )

                emissions.append(
                    {
                        "emissions": [em_],
                        "distance_time": new_taxiway_segment_time + queuing_time,
                        "distance_space": taxiway_segment_.getLength(),
                    }
                )

        else:  # "HELICOPTER"
            self._apply_taxiing_emissions_for_helicopters(emissions)

        return emissions

    def _apply_apu_emissions(
        self, em_, index_segment_, apu_t, apu_em, new_taxiway_segment_time
    ):
        """
        Add APU emissions to a taxi segment emission object.

        apu_code semantics (set on the movement):
          -1 / 0  No APU — skip all APU emissions.
           1      APU running at gate/stand only (first taxi segment receives
                  the full apu_t time; all other segments receive nothing).
           2      APU running during the entire taxi phase.  If apu_t is less
                  than the total taxi time each segment gets its proportional
                  share; if apu_t >= total taxi time the first segment absorbs
                  the overshoot and all segments receive their moving time.
        """
        # Explicit "no APU" codes — skip without loading any emissions.
        if self._apu_code <= 0:
            return

        apu_time = 0
        if (apu_t is not None and apu_em is not None) and (apu_t > 0):
            # APU emissions will be added to the stand only
            if self._apu_code == 1 and index_segment_ == 0:
                apu_time = apu_t
            # APU emissions will be added to the stand and the taxiroute
            elif self._apu_code == 2:
                if apu_t < self._total_taxiing_time:
                    # + additional time based on the assumption that the APU is running longer than usual
                    # first segment taxiing time is included in apu_t (assumption)
                    apu_time = (
                        apu_t if index_segment_ == 0 else new_taxiway_segment_time
                    )

                elif apu_t >= self._total_taxiing_time:
                    # first segment gets most of the APU emissions, rest is as per taxiing time
                    apu_time = (
                        (apu_t - self._total_taxiing_time) + new_taxiway_segment_time
                        if index_segment_ == 0
                        else new_taxiway_segment_time
                    )

            if "fuel_kg_sec" in apu_em:
                em_.addFuel(apu_em["fuel_kg_sec"] * apu_time)
            if "co2_g_s" in apu_em:
                em_.add_value(
                    PollutantType.CO2,
                    PollutantUnit.GRAM,
                    apu_em["co2_g_s"] * apu_time,
                )
            if "co_g_s" in apu_em:
                em_.add_value(
                    PollutantType.CO,
                    PollutantUnit.GRAM,
                    apu_em["co_g_s"] * apu_time,
                )
            if "hc_g_s" in apu_em:
                em_.add_value(
                    PollutantType.HC,
                    PollutantUnit.GRAM,
                    apu_em["hc_g_s"] * apu_time,
                )
            if "nox_g_s" in apu_em:
                em_.add_value(
                    PollutantType.NOx,
                    PollutantUnit.GRAM,
                    apu_em["nox_g_s"] * apu_time,
                )
            if "sox_g_s" in apu_em:
                em_.add_value(
                    PollutantType.SOx,
                    PollutantUnit.GRAM,
                    apu_em["sox_g_s"] * apu_time,
                )
            if "pm10_g_s" in apu_em:
                em_.add_value(
                    PollutantType.PM10,
                    PollutantUnit.GRAM,
                    apu_em["pm10_g_s"] * apu_time,
                )

    def _load_apu_info(self) -> Tuple[int, Any]:
        apu_time_ = 0
        apu_emis_ = None

        gate_type = self._gate.getType()
        ac_type = self._aircraft.getGroup()

        if ac_type and gate_type:
            apu_emis_ = self._aircraft.getApuEmissions()
            _apu_times = self._aircraft.getApuTimes()

            if _apu_times is not None:
                _ac_apu_times = _apu_times.get(ac_type, {})
                _gate_apu_times = _ac_apu_times.get(gate_type, {})
                apu_time_ = _gate_apu_times.get(
                    "arr_s" if self._is_arrival() else "dep_s", 0
                )
            else:
                logger.info(
                    "No APU info for %s (AC type: %s, gate type: %s)"
                    % (self._movement_name, ac_type, gate_type)
                )

        return apu_time_, apu_emis_

    def _apply_single_engine_taxiing_emissions(
        self,
        emission: Emission,
        index_segment: int,
        taxiing_time_while_aircraft_moving: float,
    ) -> Tuple[int, float]:

        if self._is_departure():
            return self._apply_single_engine_taxiing_emissions_for_departure(
                emission, index_segment, taxiing_time_while_aircraft_moving
            )
        else:
            return self._apply_single_engine_taxiing_emissions_for_arrival(
                emission, index_segment, taxiing_time_while_aircraft_moving
            )

    def _apply_single_engine_taxiing_emissions_for_departure(
        self,
        emission: Emission,
        index_segment: int,
        taxiing_time_while_aircraft_moving: float,
    ) -> Tuple[Optional[int], Optional[float]]:

        number_of_engines = None
        taxi_fuel_ratio = None

        if self._taxi_engine_count is None:
            logger.info("No Taxi Engine Count for %s", self._movement_name)
            return number_of_engines, taxi_fuel_ratio

        if self._set_time_of_main_engine_start_after_block_off_in_s is not None:
            if (
                taxiing_time_while_aircraft_moving
                <= self._set_time_of_main_engine_start_after_block_off_in_s
            ):

                number_of_engines, taxi_fuel_ratio = (
                    self._do_apply_single_engine_taxiing_emissions(emission)
                )

        elif self._set_time_of_main_engine_start_before_takeoff_in_s is not None:
            if abs(
                taxiing_time_while_aircraft_moving
                + self._set_time_of_main_engine_start_before_takeoff_in_s
            ) >= abs(self._runway_time - self._block_time):

                number_of_engines, taxi_fuel_ratio = (
                    self._do_apply_single_engine_taxiing_emissions(emission)
                )

        self._apply_start_engine_emissions(emission, index_segment)

        return number_of_engines, taxi_fuel_ratio

    def _do_apply_single_engine_taxiing_emissions(
        self, emission: Emission
    ) -> Tuple[int, float]:
        number_of_engines = float(
            min(self._taxi_engine_count, self._aircraft.getEngineCount())
        )
        taxi_fuel_ratio = self._taxi_fuel_ratio

        # CAEP14 / ALAQS: each engine contributes one start_emissions event
        # for the entire movement, not per taxi segment. The caller invokes
        # this method once for every taxi segment that falls inside the MES
        # window; without the guard the start emissions for the
        # taxi_engine_count engines would be added K times for K segments.
        # The complementary (N - taxi_engine_count) engines are added once
        # by _apply_start_engine_emissions at index_segment == 0.
        if self._include_start_emissions and not self._single_engine_start_added:
            number_of_engines_to_start = number_of_engines
            emission += self._start_emissions * number_of_engines_to_start
            self._single_engine_start_added = True

        return number_of_engines, taxi_fuel_ratio

    def _apply_start_engine_emissions(self, emission: Emission, index_segment: int):
        if not getattr(self, "_gate_emissions_code", 1):
            return
        if self._include_start_emissions and index_segment == 0:
            # Default value if both times (after_block_off and before_takeoff) are None
            number_of_engines_to_start = self._aircraft.getEngineCount()

            if (
                self._set_time_of_main_engine_start_after_block_off_in_s is not None
                or self._set_time_of_main_engine_start_before_takeoff_in_s is not None
            ):
                number_of_engines_to_start -= float(
                    min(
                        self._taxi_engine_count,
                        self._aircraft.getEngineCount(),
                    )
                )

            emission += self._start_emissions * number_of_engines_to_start

    def _apply_single_engine_taxiing_emissions_for_arrival(
        self,
        emission: Emission,
        index_segment: int,
        taxiing_time_while_aircraft_moving: float,
    ) -> Tuple[Optional[int], Optional[float]]:
        if (
            index_segment == 0
            and self._aircraft.getMTOW() is not None
            and self._aircraft.getMTOW() > 18632
        ):  # in kg
            brake_wear_g = self._aircraft.getMTOW() * 0.000476 - 8.74
            for pollutant in (PollutantType.PM10, PollutantType.PM1, PollutantType.PM2):
                emission.add_value(pollutant, PollutantUnit.GRAM, brake_wear_g)

        number_of_engines = None
        taxi_fuel_ratio = None

        if (
            self._taxi_engine_count is not None
            and self._set_time_of_main_engine_off_after_runway_exit_in_s is not None
            and abs(taxiing_time_while_aircraft_moving)
            >= self._set_time_of_main_engine_off_after_runway_exit_in_s
        ):
            number_of_engines = float(
                min(
                    self._taxi_engine_count,
                    self._aircraft.getEngineCount(),
                )
            )
            taxi_fuel_ratio = self._taxi_fuel_ratio

        return number_of_engines, taxi_fuel_ratio

    def _apply_taxiing_emissions_for_helicopters(self, emissions: list[EmissionsDict]):
        # Helicopter taxiing emissions will be added to the first segment of the taxiway
        tx_segs = self._taxi_route.getSegments()
        taxiway_segment_1 = tx_segs[0] if tx_segs else None

        if (
            not self._total_taxiing_time
            or self._total_taxiing_time <= 0
            or taxiway_segment_1 is None
        ):
            return

        em_ = Emission(defaultValues=defaultEmissions)
        em_.setGeometryText(taxiway_segment_1.getGeometryText())

        # Check number of engines. If 2, get GI2 as well.
        if self._aircraft.getEngineCount() > 1:
            ei1 = self._engine.getEmissionIndex().getEmissionIndexByMode("GI1")
            tx_time_1 = (
                ei1.getObject("time_min") * 60.0 if ei1.hasKey("time_min") else 0.0
            )
            em_.add(ei1, max(self._total_taxiing_time, tx_time_1))

            ei2 = self._engine.getEmissionIndex().getEmissionIndexByMode("GI2")
            tx_time_2 = (
                ei2.getObject("time_min") * 60.0 if ei2.hasKey("time_min") else 0.0
            )
            em_.add(
                ei2,
                max(self._total_taxiing_time * tx_time_2 / tx_time_1, tx_time_2),
            )
            em_.add(ei2, self._total_taxiing_time)

        else:
            emission_index_ = self._engine.getEmissionIndex().getEmissionIndexByMode(
                "GI1"
            )
            em_.add(emission_index_, self._total_taxiing_time)

        emissions.append(
            {
                "emissions": [em_],
                "distance_time": self._total_taxiing_time,
                "distance_space": 0.0,
            }
        )


class FlightEmissionCalculator(MovementEmissionCalculator):

    def __init__(
        self,
        trajectory,
        aircraft: Aircraft,
        engine: Engine,
        take_off_weight_ratio: float,
        departure_arrival: str,
        movement_name: str,
        at_runway: bool = True,
        method=None,
        mode: str = "",
        limit=None,
    ):
        MovementEmissionCalculator.__init__(self, departure_arrival)
        self._trajectory = trajectory
        self._aircraft = aircraft
        self._engine = engine
        self._take_off_weight_ratio = take_off_weight_ratio
        self._movement_name = movement_name

        self._at_runway = at_runway
        self._method = method or {"name": "bymode", "config": {}}
        self._mode = mode
        self._limit = limit or {}

        self._pm10_exception_shown = False
        self._sox_g_kg_exception_shown = False

    def calculate_emissions(self) -> list[EmissionsDict]:
        emissions: list[EmissionsDict] = []
        distance_time_all_segments_in_mode = 0.0
        distance_space_all_segments_in_mode = 0.0

        if self._aircraft.getGroup() != "HELICOPTER":
            # Get all individual segments (pairs  of points) for the particular
            # mode
            for start_point_, end_point_ in self._trajectory.getPointPairs(self._mode):
                emissions_dict_ = self.calculate_emissions_per_segment(
                    start_point_,
                    end_point_,
                )
                # TODO: Evaluate the usage of distance_time and distance_space.
                distance_time_all_segments_in_mode += emissions_dict_["distance_time"]
                distance_space_all_segments_in_mode += emissions_dict_["distance_space"]
                emissions.append(emissions_dict_)

            # Emit a single summary warning if any segments triggered the ADS-B
            # ceiling guard (replaces per-segment warnings).
            count = getattr(self, "_ceiling_fallback_count", 0)
            if count:
                logger.warning(
                    "BFFM2 %s: ADS-B ff/engine exceeded EEDB TO ceiling (%.4f kg/s) "
                    "on %d segment(s); power-setting interpolation used for those segments.",
                    self._movement_name,
                    self._ceiling_fallback_ceiling,
                    count,
                )
        else:
            self._apply_flight_emissions_for_helicopters(emissions)

        return emissions

    def _apply_flight_emissions_for_helicopters(self, emissions: list[EmissionsDict]):
        # Based on FOCA Guidance on the Determination of Helicopter Emissions and the FOCA Engine Emissions Databank
        heli_emissions = Emission(defaultValues=defaultEmissions)
        emission_index_ = self._engine.getEmissionIndex()

        number_of_engines = (
            self._aircraft.getEngineCount()
            if (
                self._aircraft is not None
                and self._aircraft.getEngineCount() is not None
            )
            else 1
        )

        # Get all individual segments (pairs  of points) for the geometry
        emissions_geo = []
        for start_point_, end_point_ in self._trajectory.getPointPairs(self._mode):
            emissions_geo.append(
                loads(
                    spatial.getLineGeometryText(
                        start_point_.getGeometryText(), end_point_.getGeometryText()
                    )
                )
            )
        entire_heli_geometry = MultiLineString(emissions_geo)
        heli_emissions.setGeometryText(entire_heli_geometry)
        space_in_segment_ = entire_heli_geometry.length

        # Emissions are calculated for the whole trajectory, not for each segment
        ei_ = (
            emission_index_.getEmissionIndexByMode("TO")
            if self._is_departure()
            else emission_index_.getEmissionIndexByMode("AP")
        )
        time_in_segment_ = (
            ei_.getObject("time_min") * 60.0 if ei_.hasKey("time_min") else 0.0
        )

        heli_emissions.add(ei_, time_in_segment_ * number_of_engines)
        emissions_dict_ = {
            "emissions": [heli_emissions],
            "distance_time": float(time_in_segment_),
            "distance_space": float(space_in_segment_),
        }
        emissions.append(emissions_dict_)

    def calculate_emissions_per_segment(
        self, start_point_: TrajectoryPoint, end_point_: TrajectoryPoint
    ):
        emissions = Emission(defaultValues=defaultEmissions)
        time_in_segment_s = 0.0
        space_in_segment_m = 0.0

        # ToDo : Permanent definition
        try:
            T = self._method["config"]["ambient_conditions"].getTemperature()
            # Celsius temperature: T − 273.15
            speed_of_sound = float(331.3 + 0.606 * (T - 273.15))  # in m/s
            mach_value = {
                "mach_number": (start_point_.getTrueAirspeed() / speed_of_sound)
                * ((288.15 / float(T)) ** (1.0 / 2))
            }
            ambient_temp_K = (
                T  # Use the temperature directly from the ambient conditions
            )
        except Exception:
            mach_value = {"mach_number": 0.0}
            ambient_temp_K = 288.15

        # Set up the mach number and the temperature in the local variables
        self._method["config"].update(mach_value)
        self._current_mach = mach_value["mach_number"]
        self._current_ambient_temp = ambient_temp_K

        # Apply height limits
        # (Output start and end points are used in the rest of the method)
        start_point, end_point = FlightEmissionCalculator.apply_height_limits(
            start_point_, end_point_, self._limit
        )

        # Set the geometry to None if both points were clipped by the height limit
        if start_point is None and end_point is None:
            emissions.setGeometryText(None)
            return {
                "emissions": [emissions],
                "distance_time": float(time_in_segment_s),
                "distance_space": float(space_in_segment_m),
            }

        # Check if segment is within grid bounds (2D check)
        grid_bounds = self._limit.get("grid_bounds", None)

        if grid_bounds is not None:
            # Try to clip segment to grid bounds
            clipped_start, clipped_end, distance_fraction = (
                spatial.clip_trajectory_segment_to_grid(
                    start_point, end_point, grid_bounds
                )
            )

            if clipped_start is None or clipped_end is None:
                emissions.setGeometryText(None)
                return {
                    "emissions": [emissions],
                    "distance_time": float(time_in_segment_s),
                    "distance_space": float(space_in_segment_m),
                }

            # If segment was partially clipped, use clipped points
            if distance_fraction < 1.0:
                start_point = clipped_start
                end_point = clipped_end

        # Create the geometry for this segment (using height-limited and grid-clipped points)
        segment_geometry_wkt = spatial.getLineGeometryText(
            start_point.getGeometryText(), end_point.getGeometryText()
        )

        emissions.setGeometryText(segment_geometry_wkt)

        # Emissions calculation

        # Ellipsoidal (2D) distance in meters (using height and clipped points)
        space_in_segment_m = spatial.ellipsoidal_2d_distance(
            start_point, end_point, 3857
        )

        # Time in seconds - use original points for TrueAirspeed
        _tas_start = start_point_.getTrueAirspeed() or 0.0
        _tas_end = end_point_.getTrueAirspeed() or 0.0
        _speed_sum = _tas_start + _tas_end
        if _speed_sum == 0.0:
            logger.warning(
                "Both start and end TrueAirspeed are zero for segment "
                "(start: %s, end: %s); time_in_segment_s set to 0.",
                start_point_.getGeometryText(),
                end_point_.getGeometryText(),
            )
            time_in_segment_s = 0.0
        else:
            time_in_segment_s = (2 * space_in_segment_m) / _speed_sum

        # Use original start point for emission index calculation (fuel flow, power setting, mode)
        engine_thrust = start_point_.getEngineThrust()
        fuel_flow = start_point_.getFuelFlow()
        mode = start_point_.getMode() or "AP"  # guard empty string (Bug #23 residual)
        # Segment altitude above MSL (metres) — needed by MEEM V1 for the
        # LTO/non-LTO branch.  getZ() returns None for points without an
        # explicit elevation; default to 0.
        altitude_m = float(start_point_.getZ() or 0.0)

        # Bug #22: None engine_thrust would crash calculate_fuel_flow_from_power_setting
        # inside the BFFM2 path. Fall back to bymode for that segment so one bad
        # trajectory point doesn't abort the entire movement.
        if engine_thrust is None and fuel_flow is None:
            method_name = self._method["name"].lower()
            if method_name == "bffm2":
                logger.warning(
                    "No engine thrust or fuel flow for segment (mode=%s, z=%.1f); "
                    "using bymode EI for this segment.",
                    mode,
                    altitude_m,
                )
                emission_index_ = self._get_emission_index_bymode(
                    mode,
                    engine_thrust=None,
                    altitude_m=altitude_m,
                )
            else:
                emission_index_ = self._get_emission_index(
                    mode,
                    0.07,
                    fuel_flow,
                    altitude_m=altitude_m,
                )
        else:
            # Two BFFM2 strategies for resolving the segment fuel flow used by
            # the EI log-log interpolation. Controlled by
            # self._method["config"]["bffm2_ff_source"]:
            #
            #   "trajectory" (default): use the segment's own FF. If
            #       fuel_flow_kgm is supplied (ADS-B profiles with an FF
            #       estimator), divide by engine_count to get per-engine FF.
            #       Otherwise the BFFM2 EI lookup delegates to
            #       twin_quadratic_fit_method on the segment's power_setting
            #       (from the DB `power` column, = THR_SET_lb / max_thrust_lb
            #       per ANP source data). Preserves sub-mode thrust variation.
            #       Matches the CAEP14 v14 BFFM2 workflow.
            #
            #   "mode_anchor": always use the EEDB anchor FF for the segment's
            #       mode label, overriding both supplied fuel_flow_kgm (unless
            #       it's within the TO-anchor ceiling) and the twin_quadratic
            #       path. Disables sub-mode resolution but still applies BFFM2
            #       atmospheric and humidity corrections. Matches the CAEP14
            #       v14 LTO-mode workflow + ambient corrections.
            #
            # fuel_flow_kgm values that exceed the EEDB TO ceiling are always
            # replaced by the mode anchor (treated as implausible input).
            ff_source = (
                self._method["config"].get("bffm2_ff_source", "trajectory")
                if self._method["name"].lower() == "bffm2"
                else "trajectory"
            )
            _ff_for_index = fuel_flow
            if self._method["name"].lower() == "bffm2":
                n_eng = self._aircraft.getEngineCount() or 1
                try:
                    _mode_ei = self._engine.getEmissionIndex().getEmissionIndexByMode(
                        mode
                    )
                    ff_anchor = _mode_ei.getObject("fuel_kg_sec") if _mode_ei else None
                except Exception:
                    ff_anchor = None
                try:
                    _to_ei = self._engine.getEmissionIndex().getEmissionIndexByMode(
                        "TO"
                    )
                    ff_to_ceiling = _to_ei.getObject("fuel_kg_sec") if _to_ei else None
                except Exception:
                    ff_to_ceiling = None

                if ff_source == "mode_anchor" and ff_anchor is not None:
                    # Force anchor FF regardless of supplied value.
                    _ff_for_index = ff_anchor
                elif fuel_flow is not None and fuel_flow > 0:
                    ff_per_engine = fuel_flow / n_eng
                    if ff_to_ceiling and ff_per_engine > ff_to_ceiling:
                        # Supplied FF exceeds physical maximum — fall back.
                        if not hasattr(self, "_ceiling_fallback_count"):
                            self._ceiling_fallback_count = 0
                            self._ceiling_fallback_max = ff_per_engine
                            self._ceiling_fallback_ceiling = ff_to_ceiling
                        self._ceiling_fallback_count += 1
                        if ff_per_engine > self._ceiling_fallback_max:
                            self._ceiling_fallback_max = ff_per_engine
                        _ff_for_index = ff_anchor
                    else:
                        _ff_for_index = ff_per_engine
                # else: fuel_flow is None and ff_source=="trajectory"
                # leave _ff_for_index as None so _get_emission_index_bffm2
                # falls through to the twin_quadratic path on engine_thrust.
            emission_index_ = self._get_emission_index(
                mode,
                engine_thrust,
                fuel_flow=_ff_for_index,
                altitude_m=altitude_m,
            )

        if emission_index_ is None:
            logger.error(
                "Did not find emission index for aircraft with type '%s'."
                % self._aircraft
            )
            return {
                "emissions": [emissions],
                "distance_time": float(time_in_segment_s),
                "distance_space": float(space_in_segment_m),
            }

        if (
            self._method["config"]["apply_nox_corrections"]
            and self._method["name"].lower() != "bffm2"
        ):
            self._apply_nox_corrections(emission_index_, start_point_.getMode())

        # Calculate the effective time (s)
        effective_time_s = float(time_in_segment_s) * self._aircraft.getEngineCount()

        # Add the emissions based on the emissions index and effective time
        emissions.add(emission_index_, effective_time_s)
        return {
            "emissions": [emissions],
            "distance_time": float(time_in_segment_s),
            "distance_space": float(space_in_segment_m),
        }

    @staticmethod
    def apply_height_limits(
        start_point: TrajectoryPoint,
        end_point: TrajectoryPoint,
        limit: dict,
    ) -> Tuple[TrajectoryPoint, TrajectoryPoint]:
        start_point_, end_point_ = start_point, end_point

        if "max_height" in limit:
            unit_in_feet = limit.get("height_unit_in_feet", False)

            # TODO OPENGIS.ch: if the height of the emission is above the "ICAO threshold" of 914.14 meters, we ignore all the following emissions,
            # as assumed they are getting higher and higher than this point
            if (
                start_point.getZ(unit_in_feet) >= limit["max_height"]
                and end_point.getZ(unit_in_feet) >= limit["max_height"]
            ):
                return None, None  # Ignore point

            elif (
                start_point.getZ(unit_in_feet)
                > limit["max_height"]
                > end_point.getZ(unit_in_feet)
            ):
                # make a copy of the point and modify height
                start_point_ = AircraftTrajectoryPoint(start_point)
                start_point_.setZ(limit["max_height"], unit_in_feet)

            elif (
                start_point.getZ(unit_in_feet)
                < limit["max_height"]
                < end_point.getZ(unit_in_feet)
            ):
                # make a copy of the point and modify height
                end_point_ = AircraftTrajectoryPoint(end_point_)
                end_point_.setZ(limit["max_height"], unit_in_feet)

        return start_point_, end_point_

    def _get_emission_index(
        self,
        mode: str,
        engine_thrust: float,
        fuel_flow: float = None,
        altitude_m: float = 0.0,
    ) -> EmissionIndex:
        emission_index_ = None
        method_name = self._method[
            "name"
        ].lower()  # normalise once; UI may pass "bffm2" or "BFFM2"
        if method_name == "bymode":
            emission_index_ = self._get_emission_index_bymode(
                mode,
                engine_thrust=engine_thrust,
                altitude_m=altitude_m,
            )
        elif method_name == "bffm2":
            emission_index_ = self._get_emission_index_bffm2(
                mode,
                engine_thrust,
                fuel_flow,
                altitude_m=altitude_m,
            )
        else:
            logger.warning(
                "Unknown calculation method '%s' for movement '%s'; emission index is None.",
                self._method["name"],
                self._movement_name,
            )

        return emission_index_

    def _get_emission_index_bymode(
        self,
        mode: str,
        engine_thrust: float = None,
        altitude_m: float = 0.0,
    ) -> EmissionIndex:
        try:
            ac = self._method["config"]["ambient_conditions"]
            p_amb = float(ac.getPressure())
            mach = float(self._method["config"].get("mach_number", 0.0))
            T_amb = (
                float(ac.getTemperature()) if ac.getTemperature() is not None else None
            )
            mver = str(self._method["config"].get("meem_version", "v1"))
            src = self._engine.getEmissionIndex().getEmissionIndexByModeWithMEEM(
                mode,
                p_amb,
                mach,
                power_setting=engine_thrust,
                altitude_m=altitude_m,
                T_amb_K=T_amb,
                meem_version=mver,
            )
        except Exception:
            src = self._engine.getEmissionIndex().getEmissionIndexByMode(mode)
        # Shallow-copy the flat float dict — no nested objects, so deepcopy is unnecessary.
        return EmissionIndex(initValues=dict(src._objects))

    def _get_emission_index_bffm2(
        self,
        mode: str,
        engine_thrust: float,
        fuel_flow: float = None,
        altitude_m: float = 0.0,
    ) -> EmissionIndex:
        # Get emission indices based on the engine-thrust setting or fuel flow of that specific segment
        emission_index_ = self._engine.getEmissionIndex().getEmissionIndexByEngineState(
            engine_thrust, method=self._method, fuel_flow=fuel_flow
        )

        # Get the MEEM-corrected per-mode EI for PM fields.
        # BFFM2 computes gas-phase EI only (NOx/CO/HC); PM is always from the EEDB.
        try:
            ac = self._method["config"]["ambient_conditions"]
            p_amb = float(ac.getPressure())
            mach = float(self._method["config"].get("mach_number", 0.0))
            T_amb = (
                float(ac.getTemperature()) if ac.getTemperature() is not None else None
            )
            mver = str(self._method["config"].get("meem_version", "v1"))
            mode_ei = self._engine.getEmissionIndex().getEmissionIndexByModeWithMEEM(
                mode,
                p_amb,
                mach,
                power_setting=engine_thrust,
                altitude_m=altitude_m,
                T_amb_K=T_amb,
                meem_version=mver,
            )
        except Exception:
            mode_ei = self._engine.getEmissionIndex().getEmissionIndexByMode(mode)

        if emission_index_ is None:
            copy_emission_index_ = EmissionIndex(initValues=dict(mode_ei._objects))
        else:
            copy_emission_index_ = EmissionIndex(
                initValues=dict(emission_index_._objects)
            )
            for field in (
                "pm10_g_kg",
                "pm10_nonvol_g_kg",
                "pm10_sul_g_kg",
                "pm10_organic_g_kg",
                "nvpm_g_kg",
                "nvpm_number_kg",
                "p1_g_kg",
                "p2_g_kg",
            ):
                val = mode_ei.getObject(field)
                if val is not None:
                    try:
                        copy_emission_index_.setObject(field, val)
                    except Exception:
                        if not self._pm10_exception_shown:
                            logger.error(
                                "Couldn't set PM field %s (%s)",
                                field,
                                self._movement_name,
                            )
                            self._pm10_exception_shown = True
            sox_g_kg = mode_ei.get_value(PollutantType.SOx, "g_kg")
            try:
                copy_emission_index_.setObject("sox_g_kg", sox_g_kg)
            except Exception:
                if not self._sox_g_kg_exception_shown:
                    logger.error(
                        "Couldn't add emission index for SOx (%s)", self._movement_name
                    )
                    self._sox_g_kg_exception_shown = True

        return copy_emission_index_

    def _apply_nox_corrections(self, emission_index: EmissionIndex, mode: str):
        if self._method["name"] == "bymode":
            logger.info("Applying NOx Correction for Ambient Conditions")
            nox_g_kg = emission_index.get_value(PollutantType.NOx, "g_kg")
        else:
            logger.info(
                "Applying NOx Correction for Ambient Conditions. NOx EI will be calculated using 'By mode' method."
            )
            nox_g_kg = (
                self._engine.getEmissionIndex()
                .getEmissionIndexByMode(mode)
                .get_value(PollutantType.NOx, "g_kg")
            )

        corr_nox_ei = nox_correction_for_ambient_conditions(
            (nox_g_kg, "g"),
            self._method["config"]["airport_altitude"],
            self._take_off_weight_ratio,
            ac=self._method["config"]["ambient_conditions"],
        )
        emission_index.setObject("nox_g_kg", corr_nox_ei)
