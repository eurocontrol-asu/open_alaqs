"""
This class provides the module to calculate emissions of movements.
"""

import abc
import copy
import difflib
import math
from datetime import datetime
from typing import Any, Optional, Tuple, TypedDict

import pandas as pd
from qgis.core import (
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsPolygon,
)
from shapely.geometry import LineString, MultiLineString
from shapely.wkt import loads

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Aircraft import Aircraft
from open_alaqs.core.interfaces.AircraftTrajectory import (
    AircraftTrajectory,
    AircraftTrajectoryPoint,
    TrajectoryPoint,
)
from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
from open_alaqs.core.interfaces.Emissions import (
    Emission,
    EmissionIndex,
    PollutantType,
    PollutantUnit,
)
from open_alaqs.core.interfaces.Engine import Engine
from open_alaqs.core.interfaces.Movement import (
    EmissionsDict,
    Movement,
    MovementStore,
    defaultEmissions,
)
from open_alaqs.core.interfaces.Runway import Runway
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.interfaces.SourceModule import SourceModule
from open_alaqs.core.interfaces.Taxiway import TaxiwayRoute
from open_alaqs.core.interfaces.Track import Track
from open_alaqs.core.tools import conversion, spatial
from open_alaqs.core.tools.nox_correction_ambient import (
    nox_correction_for_ambient_conditions,
)

logger = get_logger(__name__)


class CalcMethodConfigDict(TypedDict):
    apply_smooth_and_shift: str
    apply_nox_corrections: bool
    airport_altitude: float
    installation_corrections: dict[str, float]
    ambient_conditions: AmbientCondition


class CalcMethodDict(TypedDict):

    name: str
    config: CalcMethodConfigDict


class MovementSourceModule(SourceModule):
    """
    Calculate emissions due to movements
    """

    @staticmethod
    def getModuleName():
        return "MovementSource"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        SourceModule.__init__(self, values_dict)

        if self.getDatabasePath() is not None:
            movement_store = MovementStore(self.getDatabasePath())
            self.setStore(movement_store)

        self._calculation_limit = {"max_height": 914.4, "height_unit_in_feet": False}

        self._installation_corrections = {
            "Takeoff": 1.010,  # 100%
            "Climbout": 1.012,  # 85%
            "Approach": 1.020,  # 30%
            "Idle": 1.100,  # 7%
        }

        self._ambient_conditions = AmbientCondition()

        self._method = {"name": values_dict.get("method", "")}
        self._nox_correction = values_dict.get("should_apply_nox_corrections", False)
        self._smooth_and_shift = values_dict.get("source_dynamics", "none")
        self._reference_altitude = values_dict.get("reference_altitude", 0.0)

    def getMethod(self):
        return self._method

    def setMethod(self, var):
        self._method = var

    def getApplyNOxCorrection(self):
        return self._nox_correction

    def setApplyNOxCorrection(self, var):
        self._nox_correction = var

    def getApplySmoothAndShift(self) -> str:
        return self._smooth_and_shift

    def setApplySmoothAndShift(self, var):
        self._smooth_and_shift = var

    def smoothAndShiftEnabled(self) -> bool:
        sas = self.getApplySmoothAndShift()
        return sas == "default" or sas == "smooth & shift"

    def getAirportAltitude(self):
        return self._reference_altitude

    def setAirportAltitude(self, var):
        self._reference_altitude = var

    def getCalculationLimit(self):
        return self._calculation_limit

    def setCalculationLimit(self, var):
        self._calculation_limit = var

    def getAmbientConditions(self):
        return self._ambient_conditions

    def setAmbientConditions(self, var):
        self._ambient_conditions = var

    def getInstallationCorrections(self):
        return self._installation_corrections

    def setInstallationCorrections(self, var):
        self._installation_corrections = var

    # def getMovements(self):
    #     return pd.DataFrame.from_dict(self.getStore().getMovementDatabase().getEntries(), orient='index')

    @staticmethod
    def getDefaultProfileName(movement):
        if movement.isDeparture():
            return movement.getAircraft().getDefaultDepartureProfileName()
        return movement.getAircraft().getDefaultArrivalProfileName()

    def addAdditionalColumnsToDataFrame(self):
        """
        Add additional movement information to the dataframe
        """

        # Set default emissions
        default_emission = Emission(defaultValues=defaultEmissions)

        # Create a function that returns a list of default emissions
        def _default_emissions(*args):
            return {
                "emissions": default_emission,
                "distance_time": 0.0,
                "distance_space": 0.0,
            }

        # Load movements from DataFrame
        df = self.getDataframe()

        # Add the runway times
        df.loc[:, "RunwayTime"] = [mov.getRunwayTime() for mov in df["Sources"]]

        # Add the gate
        df.loc[:, "gate"] = [mov.getGate().getName() for mov in df["Sources"]]

        # Add the aircraft and aircraft group
        df.loc[:, "aircraft"] = [mov.getAircraft().getName() for mov in df["Sources"]]
        df.loc[:, "ac_group"] = [mov.getAircraft().getGroup() for mov in df["Sources"]]

        # Add the engine
        df.loc[:, "engine"] = [
            mov.getAircraftEngine().getName() for mov in df["Sources"]
        ]

        # Add the departure/arrival
        df.loc[:, "departure_arrival"] = [
            mov.getDepartureArrivalFlag() for mov in df["Sources"]
        ]

        # Add the profile id
        df.loc[:, "profile_id"] = df["Sources"].apply(self.getDefaultProfileName)
        # Then update with _profile_id where available
        for i, mov in enumerate(df["Sources"]):
            if hasattr(mov, "_profile_id") and mov._profile_id:
                df.at[i, "profile_id"] = mov._profile_id

        # try:
        #     default_profiles = df["Sources"].apply(self.getDefaultProfileName)
        #     profile_ids = [getattr(mov, '_profile_id', None) for mov in df["Sources"]]
        #     # Use _profile_id where it exists, otherwise keep default
        #     df.loc[:, "profile_id"] = [pid if pid is not None else default
        #                       for pid, default in zip(profile_ids, default_profiles)]
        #     df.loc[:, "profile_id"] = [mov._profile_id for mov in df["Sources"]]
        # except Exception as e:
        #     # Fallback to just default profiles if anything goes wrong
        #     df.loc[:, "profile_id"] = df["Sources"].apply(self.getDefaultProfileName)
        #     logger.error(f"Error processing profile IDs: {e}")

        # Add default gate and flight emissions
        empty_series = pd.Series(index=df.index, dtype=object)
        df.loc[:, "GateEmissions"] = empty_series.apply(
            _default_emissions
        )  # TODO: apply may have performance issues
        df.loc[:, "FlightEmissions"] = empty_series.apply(_default_emissions)

        # Update the DataFrame
        self._dataframe = df.astype("object")

    def _getMovementsIndicesBySourceNames(
        self, df: pd.DataFrame, source_names: list[str]
    ) -> pd.Series:
        cache_key = tuple(sorted(source_names))

        if cache_key not in self._cachedMovementIndexBySourceNames:
            self._cachedMovementIndexBySourceNames[cache_key] = df.apply(
                lambda r: r["Sources"].getName() in source_names,
                axis=1,
            )

        return self._cachedMovementIndexBySourceNames[cache_key]

    def beginJob(self):
        self.loadSources()
        self.convertSourcesToDataFrame()
        self.addAdditionalColumnsToDataFrame()

        # reset the movement index cache
        self._cachedMovementIndexBySourceNames: dict[tuple[str, ...], pd.Series] = {}

    def process(
        self,
        start_dt: datetime,
        end_dt: datetime,
        source_names=None,
        runway_names=None,
        ambient_conditions=None,
        vertical_limit_m: float = 914.4,
        **kwargs,
    ) -> list[Tuple[datetime, Source, Emission]]:
        if runway_names is None:
            runway_names = []
        if source_names is None:
            source_names = []
        result_ = []

        try:
            self.getCalculationLimit()[
                "max_height"
            ] = ambient_conditions.getMixingHeight()
        except AttributeError:
            self.getCalculationLimit()["max_height"] = vertical_limit_m
            logger.info(
                "Taking default mixing height (3000ft) on %s",
                start_dt,
            )

        limit_ = self.getCalculationLimit()
        limit_["height_unit_in_feet"] = False

        calc_method: CalcMethodDict = {
            "name": self.getMethod()["name"],
            "config": {
                "apply_smooth_and_shift": self.getApplySmoothAndShift(),
                "apply_nox_corrections": self.getApplyNOxCorrection(),
                "airport_altitude": self.getAirportAltitude(),
                "installation_corrections": self.getInstallationCorrections(),
                "ambient_conditions": ambient_conditions,
            },
        }

        # Load movements from DataFrame
        df = self.getDataframe()
        # Get the movements that match the source names
        if source_names and "all" not in source_names:
            df = df[self._getMovementsIndicesBySourceNames(df, source_names)]

        # Get the movements between start and end time of this period
        relevant_movements = (df["RunwayTime"] >= start_dt.timestamp()) & (
            df["RunwayTime"] < end_dt.timestamp()
        )

        # Return an empty list if there are no movements in this period
        if df[relevant_movements].empty:
            return []

        """
        Calculate Gate Emissions
        """

        # Perform the gate calculation once for each group
        gate_columns = ["gate", "ac_group", "departure_arrival"]
        for _name, group in df[relevant_movements].groupby(gate_columns):

            movement = group["Sources"].iloc[0]
            if runway_names and movement.getRunway().getName() not in runway_names:
                continue

            gate = movement.getGate()
            if gate is None:
                logger.warning(
                    "Did not find a gate for movement '%s'" % (movement.getName())
                )
                continue  # The corresponding df column already has a default emission dict

            gate_emission_calculator = GateEmissionCalculator(
                gate, movement.getAircraft(), movement.getDepartureArrivalFlag()
            )
            gate_emissions = gate_emission_calculator.calculate_emissions()

            MovementSourceModule.drop_zero_value_emissions(
                gate_emissions,
                f"Gate: {_name[0]}, AC Group: {_name[1]} and arr/dep: {_name[2]}",
            )

            # Apply GeoTransformation, changes are applied in-place
            if self.smoothAndShiftEnabled():
                VerticalExtentTransformer().transform_emissions(gate_emissions)

            # Update the gate emissions
            for ix in group.index:
                df.at[ix, "GateEmissions"] = gate_emissions

        """
        Calculate Flight Emissions
        """

        # Configure the flight emissions calculation
        mode_ = ""
        at_runway_ = True

        # flight_columns=["aircraft","engine","profile_id", "departure_arrival"]
        # flight_columns = ["engine", "profile_id"]
        flight_columns = [
            "engine",
            "profile_id",
            # The profile and engine will calculate the pollutant emissions correctly, but the Emissions geometry will be incorrect.
            # This is because the Profile shows the path of the airplane ignoring the azimuth of the Runway,
            # and it's geometry is stored precalculated with the Runway in the resulting FlightEmissions object.
            # However, the geometry needs to be rotated to match the respective Runway of each Movement.
            lambda idx: df.loc[idx]["Sources"].getRunway().getName(),
        ]
        for grouped_values, group in df[relevant_movements].groupby(flight_columns):

            # Determine the flight emissions
            movement = group["Sources"].iloc[0]

            trajectory = (
                movement.getTrajectoryAtRunway()
                if at_runway_
                else movement.getTrajectory()
            )
            if trajectory is None:
                logger.warning(
                    "Did not find a trajectory for movement '%s'" % (movement.getName())
                )
                continue  # The corresponding df column already has a default emission dict

            flight_emission_calculator = FlightEmissionCalculator(
                trajectory,
                movement.getAircraft(),
                movement.getAircraftEngine(),
                movement.getTakeoffWeightRatio(),
                movement.getDepartureArrivalFlag(),
                movement.getName(),
                at_runway=at_runway_,
                method=calc_method,
                mode=mode_,
                limit=limit_,
            )
            flight_emissions = flight_emission_calculator.calculate_emissions()

            MovementSourceModule.drop_zero_value_emissions(
                flight_emissions,
                f"Engine: {grouped_values[0]}, profile id: {grouped_values[1]}",
            )

            # Apply GeoTransformation, changes are applied in-place
            if self.smoothAndShiftEnabled():
                SmoothAndShiftTransformer(
                    movement.getAircraft(),
                    self.getApplySmoothAndShift(),
                    lto_mode=mode_,
                ).transform_emissions(flight_emissions)
            else:
                VerticalExtentTransformer(0, 0).transform_emissions(flight_emissions)

            # Update the flight emissions
            for ix in group.index:
                df.at[ix, "FlightEmissions"] = flight_emissions

        """
        Calculate Taxiing Emissions
        """
        for movement_name, movement in self.getSources().items():

            # process only movements of the runway under study
            if runway_names and not (movement.getRunway().getName() in runway_names):
                continue
            if (
                source_names
                and ("all" not in source_names)
                and (movement.getName() not in source_names)
            ):
                continue
            # Fetch movements that use this runway for this time period
            if not (
                start_dt.timestamp() <= movement.getRunwayTime() < end_dt.timestamp()
            ):
                continue

            # Add Taxiing Emissions
            if movement.getTaxiRoute() is None:
                te = []
                logger.error(
                    "Did not find a taxi route for movement '%s'. Cannot calculate taxiing emissions.",
                    movement.getName(),
                )
            else:
                taxiing_emission_calculator = TaxiingEmissionCalculator(movement)
                te = taxiing_emission_calculator.calculate_emissions()

                MovementSourceModule.drop_zero_value_emissions(te, "Taxiing")

                # Apply GeoTransformation, changes are applied in-place
                if self.smoothAndShiftEnabled():
                    SmoothAndShiftTransformer(
                        movement.getAircraft(),
                        self.getApplySmoothAndShift(),
                        lto_mode="TX",
                    ).transform_emissions(te)

            # add Gate Emissions
            ge = df[df["Sources"] == movement]["GateEmissions"].iloc[0]

            # add Flight Emissions
            fe = df[df["Sources"] == movement]["FlightEmissions"].iloc[0]

            emissions_extended = te + ge + fe

            if emissions_extended:
                emissions_ = []
                for em_ in emissions_extended:
                    if "emissions" in em_ and em_["emissions"] is not None:
                        emissions_.append(em_["emissions"].transposeToKilograms())

                emissions_extended = emissions_
            else:
                logger.warning("No Emissions for %s:" % (movement_name))
                # emissions_extended = [Emission(defaultValues=defaultEmissions)]
                emissions_extended = None

            result_.append((start_dt, movement, emissions_extended))

        return result_

    def endJob(self):
        SourceModule.endJob(self)

    @staticmethod
    def drop_zero_value_emissions(emissions, source):
        to_remove = []
        for index, em_ in enumerate(emissions):
            if em_["emissions"].isZero():
                logger.warning(
                    f"Skip zero value emissions for {source} - index {index}"
                )
                to_remove.append(index)
        if to_remove:
            logger.warning(
                f"Removed: {len(to_remove)} over {len(emissions)} emissions because zero value"
            )
        for index in reversed(to_remove):
            emissions.pop(index)


class GeoTransformation(abc.ABC):
    def __init__(self):
        pass

    @abc.abstractmethod
    def transform_emissions(self, emissions_dict_list: list[EmissionsDict]):
        """
        Applies a GeoTransformation to a list of EmissionsDict in-place.
        """
        raise NotImplementedError

    @staticmethod
    def runway_alignment(
        trajectory,
        track: Track,
        runway: Runway,
        runway_time: str,
        runway_direction: str,
        taxi_route: TaxiwayRoute,
        departure_arrival: str,
    ):
        if trajectory is None:
            logger.error(
                "Could not find trajectory for movement at runway "
                f"time '{runway_time}'."
            )
            return None

        if runway is None:
            logger.error(
                "Could not find runway for movement at runway time " f"'{runway_time}'."
            )
            return None

        if runway_direction not in runway.getDirections():
            logger.error(
                f"Could not find runway direction "
                f"'{runway_direction}' (movement runway "
                f"time='{runway_time}'."
            )
            return None

        # Set the EPSG identifiers for the source and target projection
        epsg_id_source = 3857  # WGS 84 / Pseudo-Mercator
        epsg_id_target = 4326  # WGS 84
        coord_tr = spatial.create_coordinate_transform(epsg_id_source, epsg_id_target)

        # Create a measure object
        qgs_d = spatial.create_distance_area(epsg_id_source)

        runway_geom = QgsGeometry.fromWkt(runway.getGeometryText())
        runway_backup_point, runway_azimuth_deg = (
            GeoTransformation.get_runway_dir_azimuth(
                trajectory,
                runway,
                runway_geom,
                runway_direction,
                qgs_d,
            )
        )

        taxi_geom = QgsGeometry.fromWkt(taxi_route.getSegmentsAsLineString().wkt)
        # NOTE QGIS 3.34.2 is returning and empty geometry and newer QGIS is returning a null geometry
        runway_intersection_projected = runway_geom.buffer(1, 10).intersection(
            taxi_geom
        )

        if (
            runway_intersection_projected.isNull()
            or runway_intersection_projected.isEmpty()
        ):
            # TODO OPENGIS.ch: in addition to just logging here,
            # make sure the taxiway and the runway are intersecting, otherwise you cannot save the Movement
            logger.error(
                'No intersection point between runway "%s" and taxi route "%s"',
                runway_direction,
                taxi_route.getName(),
            )
            runway_intersection_geographic = coord_tr.transform(runway_backup_point)
        else:
            runway_intersection_geographic = coord_tr.transform(
                runway_intersection_projected.centroid().asPoint()
            )

        if not GeoTransformation.has_track(track, taxi_route, departure_arrival):
            ac_trajectory = AircraftTrajectory(
                trajectory,
                skipPointInitialization=True,
            )
            ac_trajectory.setIsCartesian(False)

            for point in trajectory.getPoints():

                # ToDo: if NEEDED ... then
                if point._course == "CUSTOM":

                    x_offset = point.getX()  # Along the runway
                    y_offset = (
                        point.getY()
                    )  # Perpendicular to the runway (e.g. lateral deviation)

                    # Step 1: Move EAST by x_offset meters (azimuth=90°)
                    lon_east, lat_east = qgs_d.computeSpheroidProject(
                        runway_intersection_geographic,
                        x_offset,
                        math.radians(90),  # Azimuth: 90° = East
                    )

                    # Step 2: Move NORTH by y_offset meters (azimuth=0°)
                    lon_new, lat_new = qgs_d.computeSpheroidProject(
                        QgsPointXY(lon_east, lat_east),
                        y_offset,
                        math.radians(0),  # Azimuth: 0° = North
                    )

                    # Create geographic point (EPSG:4326)
                    target_point_geographic = QgsPointXY(lon_new, lat_new)

                else:

                    # the target point is with cartesian coordinates, therefore we can calculate the distance with Pythagorian theorem
                    distance = spatial.getDistanceXY(point.getX(), point.getY())

                    # get target point (calculation in 4326 projection)
                    target_point_geographic = qgs_d.computeSpheroidProject(
                        runway_intersection_geographic,
                        distance,
                        math.radians(runway_azimuth_deg),
                    )

                target_point_projected = coord_tr.transform(
                    target_point_geographic,
                    QgsCoordinateTransform.ReverseTransform,
                )

                trajectory_point = AircraftTrajectoryPoint(point)
                # Update x and y coordinates (z coordinate is not updated by distance calculation)
                trajectory_point.setCoordinates(
                    target_point_projected.x(),
                    target_point_projected.y(),
                    point.getZ(),
                )
                ac_trajectory.addPoint(trajectory_point)
        else:
            # process track
            # ToDo: from track prepare trajectory points

            # build distance to point array from aircraft profile
            profile_points = trajectory.getPoints()
            profile_distances = []
            previous_point = (0.0, 0.0, 0.0)
            cumulative_distance = 0.0
            for point in profile_points:
                point = point.getCoordinates()
                distance = spatial.getDistanceBetweenPoints(
                    point[0],
                    point[1],
                    point[2],
                    previous_point[0],
                    previous_point[1],
                    previous_point[2],
                )
                cumulative_distance = cumulative_distance + distance
                profile_distances.append(cumulative_distance)
                previous_point = point

            difference = track.getGeometry().difference(runway.getGeometry().buffer(10))
            track_line = difference
            max_length = 0.0
            # check if the track has been broken into multipe parts, pick the longest one
            if difference.geom_type == "MultiLineString":
                for line in difference.geoms:
                    if line.length > max_length:
                        max_length = line.length
                        track_line = line

            track_line_points = list(track_line.coords)
            if track.getDepartureArrivalFlag() == "A":
                # reverse arrival track so ordering begins at runway
                track_line_points.reverse()

            (point, point_wkt) = spatial.reproject_Point(
                runway_intersection_geographic.x(),
                runway_intersection_geographic.y(),
                epsg_id_target,
                epsg_id_source,
            )
            track_line_points.insert(0, (point.GetX(), point.GetY(), 0))
            track_line = LineString(track_line_points)

            ac_trajectory = AircraftTrajectory()
            ac_trajectory.setIdentifier(trajectory.getIdentifier())
            ac_trajectory.setStage(trajectory.getStage())
            ac_trajectory.setSource(trajectory.getSource())
            ac_trajectory.setDepartureArrivalFlag(trajectory.getDepartureArrivalFlag())
            ac_trajectory.setWeight(trajectory.getWeight())

            # match track points to the closest point from the profile trajectory
            previous_point = list(track_line.coords)[0]
            cumulative_distance = 0.0
            for point in track_line.coords:
                distance = spatial.getDistanceBetweenPoints(
                    point[0],
                    point[1],
                    point[2],
                    previous_point[0],
                    previous_point[1],
                    previous_point[2],
                )
                cumulative_distance = cumulative_distance + distance

                closest_distance = profile_distances[-1]
                closest_idx = len(profile_distances) - 1
                for idx, qgs_d in enumerate(profile_distances):
                    if abs(distance - qgs_d) < closest_distance:
                        closest_distance = abs(distance - qgs_d)
                        closest_idx = idx

                trajectory_point = AircraftTrajectoryPoint(profile_points[closest_idx])
                trajectory_point.setCoordinates(point[0], point[1], point[2])
                trajectory_point.updateGeometryText()
                ac_trajectory.addPoint(trajectory_point)
            ac_trajectory.updateGeometryText()

        return ac_trajectory

    @staticmethod
    def get_runway_dir_azimuth(
        trajectory,
        runway: Runway,
        runway_geom: QgsGeometry,
        runway_direction: str,
        qgs_d: QgsDistanceArea,
    ):
        runway_points = runway_geom.get().points()

        # Step 1: Geometry endpoints
        pt1, pt2 = QgsPointXY(runway_points[0]), QgsPointXY(runway_points[-1])
        # Parse runway directions
        dirs = [int("".join(filter(str.isdigit, d))) for d in runway.getDirections()]
        if len(dirs) != 2:
            raise Exception(f"Expected 2 runway directions, got {dirs}")

        # Parse active direction
        active = int("".join(filter(str.isdigit, runway_direction)))
        if active not in dirs:
            raise Exception(f"Active direction {active} not in {dirs}")

        # Compute geometry azimuth
        azimuth = math.degrees(qgs_d.bearing(pt1, pt2)) % 360
        expected = {d: (d * 10) % 360 for d in dirs}
        diffs = {
            d: min(abs(azimuth - hdg), 360 - abs(azimuth - hdg))
            for d, hdg in expected.items()
        }

        # Assign direction labels to geometry points
        start_dir = min(diffs, key=diffs.get)
        end_dir = [d for d in dirs if d != start_dir][0]
        points = {start_dir: pt1, end_dir: pt2}

        # Determine trajectory direction
        is_dep = trajectory.getDepartureArrivalFlag() == "D"
        opp = end_dir if active == start_dir else start_dir
        backup = points[active] if is_dep else points[opp]
        target = points[opp] if is_dep else points[active]

        runway_backup_point = backup
        runway_azimuth_deg = math.degrees(qgs_d.bearing(backup, target)) % 360

        return runway_backup_point, runway_azimuth_deg

    @staticmethod
    def has_track(
        track: Track, taxi_route: TaxiwayRoute, departure_arrival: str
    ) -> bool:
        if track is None:
            return False

        if taxi_route.getRunway() != track.getRunway():
            logger.warning(
                "Paired taxi route '%s' and track '%s' do not share the same runway, reverting movement to default airplane profile"
                % (taxi_route.getName(), track.getName())
            )
            return False

        if departure_arrival != track.getDepartureArrivalFlag():
            logger.warning(
                "Track '%s' departure/arrival flag does not match movement, using default airplane profile instead"
                % (track.getName())
            )
            return False

        return True

    @staticmethod
    def create_polygon_3d(aircraft, sas_method, lto_mode, point_1, point_2):
        """
        Create polygon faces using QgsPolygon.
        """
        if lto_mode == "TX":
            z2_ = 0
        else:
            point_1.getZ()
            z2_ = point_2.getZ()

        if lto_mode == "TO" and z2_ > 0:
            lto_mode = "CL"

        # Define hor_ext, ver_ext and ver_shift

        # take the default vertical extension
        d_v = aircraft.getEmissionDynamicsByMode()[lto_mode].getEmissionDynamics(
            sas_method
        )["vertical_extension"]

        d_h = aircraft.getEmissionDynamicsByMode()[lto_mode].getEmissionDynamics(
            sas_method
        )["horizontal_extension"]
        s_v = aircraft.getEmissionDynamicsByMode()[lto_mode].getEmissionDynamics(
            sas_method
        )["vertical_shift"]

        # define the horizontal and vertical extent and vertical shift
        if lto_mode == "TX" or lto_mode == "TO":
            ver_ext = aircraft.getEmissionDynamicsByMode()[
                lto_mode
            ].getEmissionDynamics(sas_method)["vertical_extension"]
        else:
            ver_ext = aircraft.getEmissionDynamicsByMode()[
                lto_mode
            ].getEmissionDynamics("default")["vertical_extension"]
        ver_shift = s_v
        hor_ext = d_h / 2  # half width

        # Get original coordinates
        if lto_mode == "TX":
            start_coords = [point_1.x(), point_1.y(), 0]
            end_coords = [point_2.x(), point_2.y(), 0]
        else:
            start_coords = [point_1.getX(), point_1.getY(), point_1.getZ()]
            end_coords = [point_2.getX(), point_2.getY(), point_2.getZ()]

        # Calculate perpendicular vector
        dx = end_coords[0] - start_coords[0]
        dy = end_coords[1] - start_coords[1]
        length = (dx**2 + dy**2) ** 0.5
        perp_x = -dy / length
        perp_y = dx / length

        # Apply vertical shift
        if sas_method == "default":
            z_shifted_start = start_coords[2] + ver_shift
            z_shifted_end = end_coords[2] + ver_shift
            z_upper_start = z_shifted_start + ver_ext
            z_upper_end = z_shifted_end + ver_ext

        elif sas_method == "sas":
            z_shifted_start = start_coords[2] - (ver_ext + d_v) / 2
            z_shifted_end = end_coords[2] - (ver_ext + d_v) / 2
            z_upper_start = start_coords[2] + ver_ext
            z_upper_end = end_coords[2] + ver_ext

        else:
            z_shifted_start = start_coords[2]
            z_shifted_end = end_coords[2]
            z_upper_start = z_shifted_start
            z_upper_end = z_shifted_end
            hor_ext = 0

        # Create 3D vertices using QgsPoint
        vertices = [
            # Lower face vertices
            QgsPoint(
                start_coords[0] + hor_ext * perp_x,
                start_coords[1] + hor_ext * perp_y,
                max(0, z_shifted_start),
            ),
            QgsPoint(
                start_coords[0] - hor_ext * perp_x,
                start_coords[1] - hor_ext * perp_y,
                max(0, z_shifted_start),
            ),
            QgsPoint(
                end_coords[0] - hor_ext * perp_x,
                end_coords[1] - hor_ext * perp_y,
                max(0, z_shifted_end),
            ),
            QgsPoint(
                end_coords[0] + hor_ext * perp_x,
                end_coords[1] + hor_ext * perp_y,
                max(0, z_shifted_end),
            ),
            # Upper face vertices
            QgsPoint(
                start_coords[0] + hor_ext * perp_x,
                start_coords[1] + hor_ext * perp_y,
                max(0, z_upper_start),
            ),
            QgsPoint(
                start_coords[0] - hor_ext * perp_x,
                start_coords[1] - hor_ext * perp_y,
                max(0, z_upper_start),
            ),
            QgsPoint(
                end_coords[0] - hor_ext * perp_x,
                end_coords[1] - hor_ext * perp_y,
                max(0, z_upper_end),
            ),
            QgsPoint(
                end_coords[0] + hor_ext * perp_x,
                end_coords[1] + hor_ext * perp_y,
                max(0, z_upper_end),
            ),
        ]

        # Define face indices (same as original)
        face_indices = [
            [0, 1, 2, 3],
            [4, 5, 6, 7],  # Bottom and top
            [0, 1, 5, 4],
            [1, 2, 6, 5],  # Sides
            [2, 3, 7, 6],
            [3, 0, 4, 7],
        ]

        # Create QGIS polygons for each face
        polygons = []
        for face in face_indices:
            # Create a linestring for each face
            line_string = QgsLineString()
            for i in face:
                line_string.addVertex(vertices[i])
            # Close the ring by adding first vertex again
            line_string.addVertex(vertices[face[0]])

            # Create polygon geometry
            polygon = QgsPolygon()
            polygon.setExteriorRing(line_string)
            polygons.append(QgsGeometry(polygon))

        # Create a multi-polygon geometry
        volume_geometry = QgsGeometry.collectGeometry(polygons)

        return (
            volume_geometry,
            z_shifted_start,
            z_shifted_end,
            z_upper_start,
            z_upper_end,
        )


class VerticalExtentTransformer(GeoTransformation):
    def __init__(self, lower_edge=0, upper_edge=5):
        GeoTransformation.__init__(self)
        self._lower_edge = lower_edge
        self._upper_edge = upper_edge

    def transform_emissions(self, emissions_dict_list: list[EmissionsDict]):
        for emissions_dict in emissions_dict_list:
            for emission in emissions_dict["emissions"]:
                self.transform_emission(emission)

    def transform_emission(self, emission: Emission):
        emission.setVerticalExtent(
            {"z_min": self._lower_edge, "z_max": self._upper_edge}
        )


class SmoothAndShiftTransformer(GeoTransformation):
    def __init__(self, aircraft: Aircraft, sas: str, lto_mode: str = ""):
        GeoTransformation.__init__(self)
        self._aircraft = aircraft
        self._sas_method = "default" if sas == "default" else "sas"
        self._lto_mode = lto_mode

    # def transform_emissions_2(self, emission: Emission):
    #     multi_polygon_geom, zsh_start, zsh_end, zup_start, zup_end = (
    #         self.create_polygon_3d(self._aircraft, self._sas_method, self._lto_mode, start_point_, end_point_)
    #     )
    #
    #     # Set the emissions geometry
    #     emission.setGeometryText(multi_polygon_geom.asWkt())
    #
    #     # Set vertical extent
    #     vertical_extent_transformer = VerticalExtentTransformer(
    #         min(zsh_start, zsh_end), max(zup_start, zup_end)
    #     )
    #     vertical_extent_transformer.transform_emission(emission)

    def transform_emissions(self, emissions_dict_list: list[EmissionsDict]):
        for emissions_dict in emissions_dict_list:
            for emission in emissions_dict["emissions"]:
                tx_geom = QgsGeometry.fromWkt(emission.getGeometryText())
                seg_points = tx_geom.asPolyline()

                all_tx_polygons = []
                zsh_start = zsh_end = zup_start, zup_end = 0
                # Loop through each pair of adjacent points
                for i in range(len(seg_points) - 1):
                    start_point_ = seg_points[i]
                    end_point_ = seg_points[i + 1]

                    if (
                        start_point_.x() == end_point_.x()
                        and start_point_.y() == end_point_.y()
                    ):
                        # logger.warning(f"Skipping zero-length segment at index {i}.")
                        continue  # Jump to next iteration

                    (
                        qgs_multipolygon,
                        zsh_start,
                        zsh_end,
                        zup_start,
                        zup_end,
                    ) = GeoTransformation.create_polygon_3d(
                        self._aircraft,
                        self._sas_method,
                        self._lto_mode,
                        start_point_,
                        end_point_,
                    )
                    all_tx_polygons.append(qgs_multipolygon)

                # Combine all polygons into a single MultiPolygon
                combined_polygon = (
                    QgsGeometry.collectGeometry(all_tx_polygons)
                    if all_tx_polygons
                    else None
                )
                if combined_polygon:
                    emission.setGeometryText(combined_polygon.asWkt())
                    vertical_extent_transformer = VerticalExtentTransformer(
                        min(zsh_start, zsh_end), max(zup_start, zup_end)
                    )
                    vertical_extent_transformer.transform_emission(emission)

                else:
                    logger.warning("Could not apply exhaust dynamics to emissions")


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
                "emissions": emissions,
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
                self._engine.getEmissionIndex().getEmissionIndexByPowerSetting(
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
                        "emissions": em_,
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
                + self._set_time_of_main_engine_start_after_block_off_in_s
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
                "emissions": self.em_,
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
            "emissions": heli_emissions,
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
        except Exception:
            mach_value = {"mach_number": 0.0}
        self._method["config"].update(mach_value)

        # Apply height limits
        # (Output start and end points are used in the rest of the method)
        start_point, end_point = FlightEmissionCalculator.apply_height_limits(
            start_point_, end_point_, self._limit
        )
        if start_point is None and end_point is None:
            emissions.setGeometryText(None)
            return {
                "emissions": emissions,
                "distance_time": float(time_in_segment_s),
                "distance_space": float(space_in_segment_m),
            }

        emissions.setGeometryText(
            spatial.getLineGeometryText(
                start_point.getGeometryText(), end_point.getGeometryText()
            )
        )

        # Emissions calculation

        # Ellipsoidal (2D) distance in meters
        space_in_segment_m = spatial.ellipsoidal_2d_distance(
            start_point, end_point, 3857
        )

        # Time in seconds
        time_in_segment_s = (2 * space_in_segment_m) / (
            end_point_.getTrueAirspeed() + start_point.getTrueAirspeed()
        )

        emission_index_ = self._get_emission_index(
            start_point.getMode(), start_point.getEngineThrust()
        )

        if self._method["config"]["apply_nox_corrections"]:
            self._apply_nox_corrections(emission_index_, start_point.getMode())

        if emission_index_ is None:
            logger.error(
                "Did not find emission index for aircraft with type '%s'."
                % self._aircraft
            )

        # Calculate the effective time (s)
        effective_time_s = float(time_in_segment_s) * self._aircraft.getEngineCount()

        emissions.add(emission_index_, effective_time_s)

        return {
            "emissions": emissions,
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

    def _get_emission_index(self, mode: str, engine_thrust: float) -> EmissionIndex:
        emission_index_ = None
        if self._method["name"] == "bymode":
            emission_index_ = self._get_emission_index_bymode(mode)
        elif self._method["name"] == "BFFM2":
            emission_index_ = self._get_emission_index_bffm2(mode, engine_thrust)

        return emission_index_

    def _get_emission_index_bymode(self, mode: str) -> EmissionIndex:
        emission_index_ = self._engine.getEmissionIndex().getEmissionIndexByMode(mode)

        return copy.deepcopy(emission_index_)

    def _get_emission_index_bffm2(
        self, mode: str, engine_thrust: float
    ) -> EmissionIndex:
        # Get emission indices based on the engine-thrust setting of the particular segment
        emission_index_ = (
            self._engine.getEmissionIndex().getEmissionIndexByPowerSetting(
                engine_thrust, method=self._method
            )
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
