"""
This class provides GeoTransformations.
"""

import abc
import math

from qgis.core import (
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsPolygon,
)
from shapely.geometry import LineString

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Aircraft import Aircraft
from open_alaqs.core.interfaces.AircraftTrajectory import (
    AircraftTrajectory,
    AircraftTrajectoryPoint,
)
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.Runway import Runway
from open_alaqs.core.interfaces.Taxiway import TaxiwayRoute
from open_alaqs.core.interfaces.Track import Track
from open_alaqs.core.MovementEmissionCalculator import EmissionsDict
from open_alaqs.core.tools import spatial

logger = get_logger(__name__)


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
    def create_polygon_3d(
        aircraft, sas_method, lto_mode, point_1: QgsPoint, point_2: QgsPoint
    ):
        """
        Create polygon faces using QgsPolygon.
        """
        if lto_mode == "TX":
            z2_ = 0
        else:
            z2_ = point_2.z()

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
            start_coords = [point_1.x(), point_1.y(), point_1.z()]
            end_coords = [point_2.x(), point_2.y(), point_2.z()]

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

    def transform_emissions(self, emissions_dict_list: list[EmissionsDict]):
        for emissions_dict in emissions_dict_list:
            for emission in emissions_dict["emissions"]:
                tx_geom = QgsGeometry.fromWkt(emission.getGeometryText())
                seg_points = spatial.get_line_vertices(tx_geom)

                all_tx_polygons = []
                zsh_start = zsh_end = zup_start = zup_end = 0
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


class TrajectoryTransformer:
    def __init__(
        self,
        trajectory,
        track: Track,
        runway: Runway,
        runway_time: str,
        runway_direction: str,
        taxi_route: TaxiwayRoute,
        departure_arrival: str,
    ):
        self._trajectory = trajectory
        self._track = track
        self._runway = runway
        self._runway_time = runway_time
        self._runway_direction = runway_direction
        self._taxi_route = taxi_route
        self._departure_arrival = departure_arrival

    def runway_alignment(self):
        if self._trajectory is None:
            logger.error(
                "Could not find trajectory for movement at runway "
                f"time '{self._runway_time}'."
            )
            return None

        if self._runway is None:
            logger.error(
                "Could not find runway for movement at runway time "
                f"'{self._runway_time}'."
            )
            return None

        if self._runway_direction not in self._runway.getDirections():
            logger.error(
                f"Could not find runway direction "
                f"'{self._runway_direction}' (movement runway "
                f"time='{self._runway_time}'."
            )
            return None

        # Set the EPSG identifiers for the source and target projection
        epsg_id_source = 3857  # WGS 84 / Pseudo-Mercator
        epsg_id_target = 4326  # WGS 84
        coord_tr = spatial.create_coordinate_transform(epsg_id_source, epsg_id_target)

        # Create a measure object
        qgs_d = spatial.create_distance_area(epsg_id_source)

        runway_geom = QgsGeometry.fromWkt(self._runway.getGeometryText())
        runway_backup_point, runway_azimuth_deg = self._get_runway_dir_azimuth(
            runway_geom, qgs_d
        )

        taxi_geom = QgsGeometry.fromWkt(self._taxi_route.getSegmentsAsLineString().wkt)
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
                self._runway_direction,
                self._taxi_route.getName(),
            )
            runway_intersection_geographic = coord_tr.transform(runway_backup_point)
        else:
            runway_intersection_geographic = coord_tr.transform(
                runway_intersection_projected.centroid().asPoint()
            )

        if not self._has_track():
            ac_trajectory = AircraftTrajectory(
                self._trajectory,
                skipPointInitialization=True,
            )
            ac_trajectory.setIsCartesian(False)

            for point in self._trajectory.getPoints():

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
            # Process track
            # ToDo: from track prepare trajectory points

            # build distance to point array from aircraft profile
            profile_points = self._trajectory.getPoints()
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

            difference = self._track.getGeometry().difference(
                self._runway.getGeometry().buffer(10)
            )
            track_line = difference
            max_length = 0.0
            # Check if the track has been broken into multipe parts, pick the longest one
            if difference.geom_type == "MultiLineString":
                for line in difference.geoms:
                    if line.length > max_length:
                        max_length = line.length
                        track_line = line

            track_line_points = list(track_line.coords)
            if self._track.getDepartureArrivalFlag() == "A":
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
            ac_trajectory.setIdentifier(self._trajectory.getIdentifier())
            ac_trajectory.setStage(self._trajectory.getStage())
            ac_trajectory.setSource(self._trajectory.getSource())
            ac_trajectory.setDepartureArrivalFlag(
                self._trajectory.getDepartureArrivalFlag()
            )
            ac_trajectory.setWeight(self._trajectory.getWeight())

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
                for idx, profile_distance in enumerate(profile_distances):
                    if abs(distance - profile_distance) < closest_distance:
                        closest_distance = abs(distance - profile_distance)
                        closest_idx = idx

                trajectory_point = AircraftTrajectoryPoint(profile_points[closest_idx])
                trajectory_point.setCoordinates(point[0], point[1], point[2])
                trajectory_point.updateGeometryText()
                ac_trajectory.addPoint(trajectory_point)
            ac_trajectory.updateGeometryText()

        return ac_trajectory

    def _get_runway_dir_azimuth(
        self,
        runway_geom: QgsGeometry,
        qgs_d: QgsDistanceArea,
    ):
        runway_points = runway_geom.get().points()

        # Step 1: Geometry endpoints
        pt1, pt2 = QgsPointXY(runway_points[0]), QgsPointXY(runway_points[-1])
        # Parse runway directions
        dirs = [
            int("".join(filter(str.isdigit, d))) for d in self._runway.getDirections()
        ]
        if len(dirs) != 2:
            raise Exception(f"Expected 2 runway directions, got {dirs}")

        # Parse active direction
        active = int("".join(filter(str.isdigit, self._runway_direction)))
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
        is_dep = self._trajectory.getDepartureArrivalFlag() == "D"
        opp = end_dir if active == start_dir else start_dir
        backup = points[active] if is_dep else points[opp]
        target = points[opp] if is_dep else points[active]

        runway_backup_point = backup
        runway_azimuth_deg = math.degrees(qgs_d.bearing(backup, target)) % 360

        return runway_backup_point, runway_azimuth_deg

    def _has_track(self) -> bool:
        if self._track is None:
            return False

        if self._taxi_route.getRunway() != self._track.getRunway():
            logger.warning(
                "Paired taxi route '%s' and track '%s' do not share the same runway, reverting movement to default airplane profile"
                % (self._taxi_route.getName(), self._track.getName())
            )
            return False

        if self._departure_arrival != self._track.getDepartureArrivalFlag():
            logger.warning(
                "Track '%s' departure/arrival flag does not match movement, using default airplane profile instead"
                % (self._track.getName())
            )
            return False

        return True
