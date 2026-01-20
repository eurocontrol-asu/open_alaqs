"""
This class provides the emission calculation for movements.
"""

import abc
import copy
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


def clip_segment_to_grid(
    start_point: TrajectoryPoint, end_point: TrajectoryPoint, grid_bounds: dict
) -> tuple:
    """
    Clip a segment to grid bounds. Returns the clipped start and end points (or None if fully outside).
    Also returns the fraction of the original segment that remains after clipping.

    Args:
        start_point: The start point of the segment
        end_point: The end point of the segment
        grid_bounds: Dict with x_min, x_max, y_min, y_max

    Returns:
        tuple: (clipped_start, clipped_end, distance_fraction)
        where distance_fraction is the ratio of clipped distance to original distance
    """
    x1, y1 = start_point.getX(), start_point.getY()
    x2, y2 = end_point.getX(), end_point.getY()

    grid_x_min = grid_bounds["x_min"]
    grid_x_max = grid_bounds["x_max"]
    grid_y_min = grid_bounds["y_min"]
    grid_y_max = grid_bounds["y_max"]

    # Calculate original distance for fraction calculation
    original_distance = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    # Parametric line: P(t) = P1 + t*(P2 - P1), where t in [0, 1]
    dx = x2 - x1
    dy = y2 - y1

    # Find t values where the line enters/exits the grid
    t_min = 0.0
    t_max = 1.0

    # Clip against x bounds
    if dx != 0:
        t_x_min = (grid_x_min - x1) / dx
        t_x_max = (grid_x_max - x1) / dx
        if t_x_min > t_x_max:
            t_x_min, t_x_max = t_x_max, t_x_min
        t_min = max(t_min, t_x_min)
        t_max = min(t_max, t_x_max)
    else:
        # Vertical line, check if within x bounds
        if not (grid_x_min <= x1 <= grid_x_max):
            return None, None, 0.0

    # Clip against y bounds
    if dy != 0:
        t_y_min = (grid_y_min - y1) / dy
        t_y_max = (grid_y_max - y1) / dy
        if t_y_min > t_y_max:
            t_y_min, t_y_max = t_y_max, t_y_min
        t_min = max(t_min, t_y_min)
        t_max = min(t_max, t_y_max)
    else:
        # Horizontal line, check if within y bounds
        if not (grid_y_min <= y1 <= grid_y_max):
            return None, None, 0.0

    # Check if there's any intersection
    if t_min >= t_max:
        return None, None, 0.0

    # Calculate clipped endpoints
    clip_x1 = x1 + t_min * dx
    clip_y1 = y1 + t_min * dy
    clip_z1 = start_point.getZ() + t_min * (end_point.getZ() - start_point.getZ())

    clip_x2 = x1 + t_max * dx
    clip_y2 = y1 + t_max * dy
    clip_z2 = start_point.getZ() + t_max * (end_point.getZ() - start_point.getZ())

    # Create clipped trajectory points using dict format
    clipped_start_dict = {
        "id": start_point.getIdentifier(),
        "x": clip_x1,
        "y": clip_y1,
        "z": clip_z1,
        "course": start_point.getCourse(),
    }
    clipped_start = TrajectoryPoint(clipped_start_dict)

    clipped_end_dict = {
        "id": end_point.getIdentifier(),
        "x": clip_x2,
        "y": clip_y2,
        "z": clip_z2,
        "course": end_point.getCourse(),
    }
    clipped_end = TrajectoryPoint(clipped_end_dict)

    # Calculate distance fraction
    clipped_distance = ((clip_x2 - clip_x1) ** 2 + (clip_y2 - clip_y1) ** 2) ** 0.5
    distance_fraction = (
        clipped_distance / original_distance if original_distance > 0 else 1.0
    )

    return clipped_start, clipped_end, distance_fraction


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

    def __init__(self, gate, aircraft, departure_arrival):
        MovementEmissionCalculator.__init__(self, departure_arrival)
        self._gate = gate
        self._aircraft = aircraft

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
        ac_group = None
        if ac_group in self._gate.getEmissionProfileGroups():
            ac_group = self._aircraft.getGroup()
        else:
            matched = difflib.get_close_matches(
                self._aircraft.getGroup(),
                self._gate.getEmissionProfileGroups(source_type=source_type),
            )
            if matched:
                ac_group = matched[0]
                if not ac_group.lower() == self._aircraft.getGroup().lower():
                    logger.warning(
                        "Did not find a gate emission profile for source type '%s' and aircraft group '%s', "
                        "but matched to '%s'. Probably update the table 'default_gate_profiles'."
                        % (source_type, ac_group, self._aircraft.getGroup())
                    )

        return ac_group

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

    def calculate_emissions(self) -> list[EmissionsDict]:
        emissions: list[EmissionsDict] = []

        # ToDo: Only bymode method for now.
        if self._method["name"] == "bymode":
            emission_index_ = self._engine.getEmissionIndex().getEmissionIndexByMode(
                self._mode
            )
        else:
            # get emission indices based on the engine-thrust setting as defined in the movements table
            emission_index_ = (
                self._engine.getEmissionIndex().getEmissionIndexByEngineState(
                    self._engine_thrust_level_taxiing, method=self._method
                )
            )

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
                        em_.add(
                            emission_index_,
                            self.AVERAGE_DURATION_OF_STOP_AND_GOS_IN_S
                            * self._number_of_stops,
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
        # Load APU time and emission factors
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
            else:
                apu_time = 0

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

        if self._include_start_emissions:
            number_of_engines_to_start = number_of_engines
            emission += self._start_emissions * number_of_engines_to_start

        return number_of_engines, taxi_fuel_ratio

    def _apply_start_engine_emissions(self, emission: Emission, index_segment: int):
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
            emission.add_value(
                PollutantType.PM10,
                PollutantUnit.GRAM,
                self._aircraft.getMTOW() * 0.000476 - 8.74,
            )

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
            clipped_start, clipped_end, distance_fraction = clip_segment_to_grid(
                start_point, end_point, grid_bounds
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
        time_in_segment_s = (2 * space_in_segment_m) / (
            end_point_.getTrueAirspeed() + start_point_.getTrueAirspeed()
        )

        # Use original start point for emission index calculation (fuel flow, power setting, mode)
        emission_index_ = self._get_emission_index(
            start_point_.getMode(),
            start_point_.getEngineThrust(),
            fuel_flow=start_point_.getFuelFlow(),
        )

        if self._method["config"]["apply_nox_corrections"]:
            self._apply_nox_corrections(emission_index_, start_point_.getMode())

        if emission_index_ is None:
            logger.error(
                "Did not find emission index for aircraft with type '%s'."
                % self._aircraft
            )

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
        self, mode: str, engine_thrust: float, fuel_flow: float = None
    ) -> EmissionIndex:
        emission_index_ = None
        if self._method["name"] == "bymode":
            emission_index_ = self._get_emission_index_bymode(mode)
        elif self._method["name"] == "BFFM2":
            emission_index_ = self._get_emission_index_bffm2(
                mode, engine_thrust, fuel_flow
            )

        return emission_index_

    def _get_emission_index_bymode(self, mode: str) -> EmissionIndex:
        emission_index_ = self._engine.getEmissionIndex().getEmissionIndexByMode(mode)

        return copy.deepcopy(emission_index_)

    def _get_emission_index_bffm2(
        self, mode: str, engine_thrust: float, fuel_flow: float = None
    ) -> EmissionIndex:
        # Get emission indices based on the engine-thrust setting or fuel flow of that specific segment
        emission_index_ = self._engine.getEmissionIndex().getEmissionIndexByEngineState(
            engine_thrust, method=self._method, fuel_flow=fuel_flow
        )

        # ToDo: Permanent fix for PM10
        if emission_index_ is None:
            # logger.error("Error: Cannot calculate EI w. BFFM2. The 'by mode' method will be used for source: '%s'" %(self.getName()))
            copy_emission_index_ = (
                self._engine.getEmissionIndex().getEmissionIndexByMode(mode)
            )
        else:
            copy_emission_index_ = copy.deepcopy(emission_index_)

            pm10_g_kg = (
                self._engine.getEmissionIndex()
                .getEmissionIndexByMode(mode)
                .get_value(PollutantType.PM10, "g_kg")
            )
            try:
                copy_emission_index_.setObject("pm10_g_kg", pm10_g_kg[0])
            except Exception:
                if not self._pm10_exception_shown:
                    logger.error(
                        "Couldn't add emission index for PM10 (%s)"
                        % self._movement_name
                    )
                    self._pm10_exception_shown = True

            sox_g_kg = (
                self._engine.getEmissionIndex()
                .getEmissionIndexByMode(mode)
                .get_value(PollutantType.SOx, "g_kg")
            )
            try:
                copy_emission_index_.setObject("sox_g_kg", sox_g_kg[0])
            except Exception:
                if not self._sox_g_kg_exception_shown:
                    logger.error(
                        "Couldn't add emission index for SOx (%s)" % self._movement_name
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
            nox_g_kg,
            self._method["config"]["airport_altitude"],
            self._take_off_weight_ratio,
            ac=self._method["config"]["ambient_conditions"],
        )
        emission_index.setObject("nox_g_kg", corr_nox_ei)
