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
        # ── Coordinate setup ────────────────────────────────────────────────
        if lto_mode == "TX":
            z2_ = 0
        else:
            z2_ = point_2.z()

        # B2 FIX: reclassify TO → CL before any dynamics lookup.
        # Previously the reclassification happened after d_v/d_h/s_v were already
        # fetched, then ver_ext was fetched with "default" instead of sas_method,
        # mixing parameters from different method lookups in the sas z-shift formula.
        if lto_mode == "TO" and z2_ > 0:
            lto_mode = "CL"

        if lto_mode == "TX":
            start_coords = [point_1.x(), point_1.y(), 0]
            end_coords = [point_2.x(), point_2.y(), 0]
        else:
            start_coords = [point_1.x(), point_1.y(), point_1.z()]
            end_coords = [point_2.x(), point_2.y(), point_2.z()]

        # B1 FIX: guard against XY-identical points reaching this function.
        # The caller checks x==x and y==y but that check uses QgsPoint.x()/y()
        # which may differ by floating-point epsilon after coordinate transforms.
        # An explicit length check here prevents ZeroDivisionError.
        dx = end_coords[0] - start_coords[0]
        dy = end_coords[1] - start_coords[1]
        length = (dx**2 + dy**2) ** 0.5
        if length == 0.0:
            raise ValueError(
                "create_polygon_3d: zero-length XY segment — "
                f"start={start_coords}, end={end_coords}"
            )

        # ── Dynamics lookup — E1 FIX: fetch once, not five times ─────────────
        # B4 FIX: guard against KeyError if the aircraft group has no entry for
        # this mode in the default_emission_dynamics table.
        try:
            mode_dynamics = aircraft.getEmissionDynamicsByMode()[lto_mode]
        except (KeyError, TypeError):
            logger.warning(
                "No emission dynamics found for mode '%s' on aircraft '%s'. "
                "Using zero-extension defaults.",
                lto_mode,
                aircraft.getICAOIdentifier() if aircraft else "unknown",
            )
            mode_dynamics = None

        if mode_dynamics is not None:
            try:
                sas_params = mode_dynamics.getEmissionDynamics(sas_method)
            except (KeyError, TypeError):
                sas_params = mode_dynamics.getEmissionDynamics("default")

            d_h = sas_params["horizontal_extension"]
            s_v = sas_params["vertical_shift"]
            d_v = sas_params["vertical_extension"]

            # ver_ext must come from the same method as d_v.
            # The original code used "default" for airborne modes (CL/AP) and
            # sas_method for TX/TO, which mixed "default" and "sas" columns in
            # the sas z-shift formula: z - (ver_ext + d_v) / 2.
            # Since d_v and ver_ext are both "vertical_extension" from the same
            # EmissionDynamics object, they must use the same method lookup so
            # the formula is consistent.  sas_method is already normalised to
            # either "default" or "sas" in __init__, so this is always correct.
            ver_ext = d_v
        else:
            d_h = d_v = s_v = ver_ext = 0.0

        # ── Polygon geometry ─────────────────────────────────────────────────
        hor_ext = d_h / 2  # half-width
        ver_shift = s_v

        perp_x = -dy / length
        perp_y = dx / length

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
            line_string = QgsLineString()
            for i in face:
                line_string.addVertex(vertices[i])
            # Close the ring by adding first vertex again
            line_string.addVertex(vertices[face[0]])
            polygon = QgsPolygon()
            polygon.setExteriorRing(line_string)
            polygons.append(QgsGeometry(polygon))

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
    def __init__(
        self,
        aircraft: Aircraft,
        sas: str,
        is_arrival: bool,
        lto_mode: str = "",
    ):
        GeoTransformation.__init__(self)
        self._aircraft = aircraft
        self._sas_method = "default" if sas == "default" else "sas"

        self._is_arrival = is_arrival
        self._lto_mode = lto_mode

    def transform_emissions(self, emissions_dict_list: list[EmissionsDict]):
        for emissions_dict in emissions_dict_list:
            for emission in emissions_dict["emissions"]:
                tx_geom = QgsGeometry.fromWkt(emission.getGeometryText())
                seg_points = spatial.get_line_vertices(tx_geom)

                all_tx_polygons = []
                # B3 FIX: track z-envelope across ALL segments, not just the
                # last one.  Previously zsh/zup vars were overwritten each
                # iteration so VerticalExtentTransformer only saw the final
                # segment's values, producing a wrong envelope for trajectories
                # spanning multiple altitude bands.
                z_min_all = float("inf")
                z_max_all = float("-inf")

                for i in range(len(seg_points) - 1):
                    start_point_ = seg_points[i]
                    end_point_ = seg_points[i + 1]

                    if (
                        start_point_.x() == end_point_.x()
                        and start_point_.y() == end_point_.y()
                    ):
                        continue

                    lto_mode = self._lto_mode
                    if not lto_mode:
                        if self._is_arrival:
                            lto_mode = "AP"
                        else:
                            lto_mode = "TO" if start_point_.z() == 0 else "CL"

                    try:
                        (
                            qgs_multipolygon,
                            zsh_start,
                            zsh_end,
                            zup_start,
                            zup_end,
                        ) = GeoTransformation.create_polygon_3d(
                            self._aircraft,
                            self._sas_method,
                            lto_mode,
                            start_point_,
                            end_point_,
                        )
                    except (ValueError, ZeroDivisionError) as exc:
                        logger.warning(
                            "Skipping zero-length segment at index %d in "
                            "SmoothAndShift transform: %s",
                            i,
                            exc,
                        )
                        continue

                    all_tx_polygons.append(qgs_multipolygon)
                    z_min_all = min(z_min_all, zsh_start, zsh_end)
                    z_max_all = max(z_max_all, zup_start, zup_end)

                combined_polygon = (
                    QgsGeometry.collectGeometry(all_tx_polygons)
                    if all_tx_polygons
                    else None
                )
                if combined_polygon and z_min_all != float("inf"):
                    emission.setGeometryText(combined_polygon.asWkt())
                    # E4 FIX: set vertical extent directly — no throwaway object.
                    emission.setVerticalExtent({"z_min": z_min_all, "z_max": z_max_all})
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
        runway_backup_point, _runway_target_point, runway_azimuth_deg = (
            self._get_runway_dir_azimuth(runway_geom, qgs_d)
        )

        # Trajectory origin selection (mirrors the standalone's
        # `_intersection_cached` behaviour, see
        # openalaqs_standalone/compute_aircraft.py around the "ANCHOR
        # SELECTION" comment): for BOTH arrivals and departures the
        # origin is the taxi-route/runway intersection point, with a
        # direction-appropriate fallback when the taxi route does not
        # intersect the runway.
        #
        #   DEPARTURE: origin = taxi-route runway-intersection point
        #              (where the aircraft enters the runway). Fallback =
        #              active threshold (brake-release point = the runway
        #              endpoint the aircraft is departing FROM).
        #              Walk azimuth = motion direction = runway_azimuth_deg.
        #
        #   ARRIVAL:   origin = taxi-route runway-intersection point
        #              (where the aircraft exits the runway). No rollout
        #              shift: the trajectory profile already encodes the
        #              rollout via its x>0 points, and the standalone /
        #              CAEP14 reference both anchor at the unshifted
        #              intersection. Fallback = active threshold
        #              (touchdown point).
        #              Walk azimuth = motion direction = (runway_azimuth_deg
        #              + 180) % 360. _get_runway_dir_azimuth returns for
        #              arrivals an azimuth pointing from opp toward active
        #              (approach direction); we flip for the motion walk.
        #
        # The projection loop below also handles the SIGN of profile-x so
        # arrival approach points (x<0) walk in the approach direction and
        # rollout points (x>0) walk in the motion direction.  For departures
        # all profile x are non-negative and the sign-flip is a no-op.
        #
        # Why both arr and dep use the intersection:
        #   - ANP profiles: identical result to the old "active threshold"
        #     anchor in the common case where the takeoff roll lies inside
        #     the inventory grid (no grid clipping).
        #   - CUSTOM (ADS-B imported) profiles: the importer
        #     (core/tools/ads_b.py) anchors imported (x_m, y_m) at the
        #     runway-taxi intersection, so the runtime anchor MUST match
        #     or the trajectory shifts by the threshold-to-intersection
        #     distance (~80-130 m at most airports, producing visible
        #     downstream offsets).
        #   - Arrivals: the rollout-shift in the prior version was a fix
        #     for visual continuity but it shifted the touchdown point
        #     away from the runway threshold by rollout_length, producing
        #     a -3-5% NOx offset on the approach segments. The standalone
        #     CAEP14 reference does NOT shift; we now match.
        is_dep = self._departure_arrival == "D"

        # Compute the runway-exit / runway-entry point of the taxi route.
        # Same call for both arr and dep; the intersection is geometric.
        exit_point_projected = (
            spatial.get_intersection_point_runway_and_taxi_route(
                self._runway, self._taxi_route
            )
            if self._taxi_route is not None
            else None
        )

        if is_dep:
            trajectory_walk_azimuth_deg = runway_azimuth_deg
            if exit_point_projected is None or exit_point_projected.isEmpty():
                # Fall back to the active threshold (brake-release point).
                runway_intersection_projected = runway_backup_point
                logger.info(
                    "No runway-taxi intersection for departure movement at "
                    "runway time '%s' (taxi route '%s'); using active "
                    "threshold as trajectory origin.",
                    self._runway_time,
                    self._taxi_route.getName() if self._taxi_route else "?",
                )
            else:
                runway_intersection_projected = exit_point_projected
        else:
            trajectory_walk_azimuth_deg = (runway_azimuth_deg + 180.0) % 360.0
            if exit_point_projected is None or exit_point_projected.isEmpty():
                # Fall back to the active threshold (touchdown point).
                runway_intersection_projected = _runway_target_point
                logger.info(
                    "No runway-taxi intersection for arrival movement at "
                    "runway time '%s' (taxi route '%s'); using active "
                    "threshold as trajectory origin.",
                    self._runway_time,
                    self._taxi_route.getName() if self._taxi_route else "?",
                )
            else:
                runway_intersection_projected = exit_point_projected

        runway_intersection_geographic = coord_tr.transform(
            runway_intersection_projected
        )

        if not self._has_track():
            ac_trajectory = AircraftTrajectory(
                self._trajectory,
                skipPointInitialization=True,
            )
            ac_trajectory.setIsCartesian(False)

            original_trajectory_points = self._trajectory.getPoints()
            if not original_trajectory_points:
                return ac_trajectory

            def _add_trajectory_point(original_point, new__point_projected):
                _trajectory_point = AircraftTrajectoryPoint(original_point)
                # Update x and y coordinates (z coordinate is not updated by distance calculation)
                _trajectory_point.setCoordinates(
                    new__point_projected.x(),
                    new__point_projected.y(),
                    original_point.getZ(),
                )
                ac_trajectory.addPoint(_trajectory_point)

            if original_trajectory_points[0]._course == "CUSTOM":
                # Project ref point (3857) to UTM
                ref_proj_x = runway_intersection_projected.x()
                ref_proj_y = runway_intersection_projected.y()

                utm_zone = int((runway_intersection_geographic.x() + 180) // 6) + 1
                utm_epsg = utm_zone + (
                    32600 if runway_intersection_projected.y() >= 0 else 32700
                )
                utm_3857_transform = spatial.create_coordinate_transform(utm_epsg, 3857)

                ref_utm = utm_3857_transform.transform(
                    ref_proj_x, ref_proj_y, QgsCoordinateTransform.ReverseTransform
                )

                for point in original_trajectory_points:
                    x_offset = point.getX()
                    y_offset = point.getY()

                    # Convert the utm reference point applying the offsets to 3857
                    target_point_projected = utm_3857_transform.transform(
                        ref_utm.x() + x_offset, ref_utm.y() + y_offset
                    )

                    _add_trajectory_point(point, target_point_projected)
            else:
                for point in original_trajectory_points:
                    # The target point is in cartesian coordinates relative to
                    # the trajectory origin, with x along the runway azimuth
                    # and y across it (ANP profile convention).  ANP profiles
                    # use y=0 always, so the relevant geometry is one-dimensional
                    # along the runway axis.
                    #
                    # The SIGN of profile-x carries direction relative to motion:
                    #   x ≥ 0  → ahead of the origin in motion direction
                    #            (departure takeoff/climbout; arrival rollout)
                    #   x < 0  → behind the origin in motion direction
                    #            (arrival approach points, which are behind
                    #            touchdown when measured along the motion axis)
                    # computeSpheroidProject only accepts non-negative
                    # distances, so we walk |distance| at the configured
                    # azimuth for x≥0 and at (azimuth+180) for x<0.  This is
                    # a no-op for departure profiles (all profile x are
                    # non-negative there).
                    x_val = point.getX()
                    y_val = point.getY()
                    distance = math.hypot(x_val, y_val)
                    effective_azimuth_deg = (
                        trajectory_walk_azimuth_deg
                        if x_val >= 0
                        else (trajectory_walk_azimuth_deg + 180.0) % 360.0
                    )

                    # get target point (calculation in 4326 projection)
                    target_point_geographic = qgs_d.computeSpheroidProject(
                        runway_intersection_geographic,
                        distance,
                        math.radians(effective_azimuth_deg),
                    )

                    target_point_projected = coord_tr.transform(
                        target_point_geographic,
                        QgsCoordinateTransform.ReverseTransform,
                    )

                    _add_trajectory_point(point, target_point_projected)
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

            track_line_points.insert(
                0,
                (
                    runway_intersection_projected.x(),
                    runway_intersection_projected.y(),
                    0,
                ),
            )
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
                    if abs(cumulative_distance - profile_distance) < closest_distance:
                        closest_distance = abs(cumulative_distance - profile_distance)
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
        # Use self._departure_arrival (set by the constructor) rather than
        # self._trajectory.getDepartureArrivalFlag(), so this helper also works
        # when called from the helicopter path where the input trajectory is None
        # (the helicopter trajectory is generated from FOCA category, not loaded
        # from default_aircraft_profiles).
        is_dep = self._departure_arrival == "D"
        opp = end_dir if active == start_dir else start_dir
        backup = points[active] if is_dep else points[opp]
        target = points[opp] if is_dep else points[active]

        runway_backup_point = backup
        runway_target_point = target
        runway_azimuth_deg = math.degrees(qgs_d.bearing(backup, target)) % 360

        return runway_backup_point, runway_target_point, runway_azimuth_deg

    def runway_alignment_for_helicopter(self, category_str: str):
        """Build a runway-aligned FOCA helicopter LTO trajectory.

        Replaces the legacy HELIPROF-based path for helicopters: instead of
        loading a pre-defined 8-point profile from default_aircraft_profiles
        and translating it (where all 8 points sit at local x=y=0, collapsing
        to a vertical column at the runway threshold), we generate the LTO
        trajectory live via the per-category FOCA formulas, producing a
        proper arc with realistic horizontal motion (5-11 km along-track,
        climb/descent between ground and 3000 ft LTO ceiling).

        :param category_str: FOCA helicopter category string. One of
            'PISTON', 'SINGLE_TURBOSHAFT', 'TWIN_TURBOSHAFT_LIGHT',
            'TWIN_TURBOSHAFT_HEAVY'. Coming from Helicopter.getCategory().
        :return: AircraftTrajectory with points in the project CRS
            (EPSG:3857). Returns None if inputs are invalid.

        Coordinate convention:
            For DEPARTURE: trajectory's local x=0 is the takeoff point
            (active end of runway). Local +x is the departure direction.
            World origin = backup_point. World walk azimuth = runway azimuth.

            For ARRIVAL: trajectory's local x=0 is the touchdown point
            (active end of runway). Local +x is the direction OPPOSITE to
            motion (back along the approach path). World origin = target_point.
            World walk azimuth = (runway_azimuth + 180) % 360.
        """
        if self._runway is None:
            logger.error(
                "Helicopter trajectory: no runway for movement at runway time '%s'.",
                self._runway_time,
            )
            return None

        if self._runway_direction not in self._runway.getDirections():
            logger.error(
                "Helicopter trajectory: runway direction '%s' not in "
                "available directions %s (runway time '%s').",
                self._runway_direction,
                self._runway.getDirections(),
                self._runway_time,
            )
            return None

        # Resolve helicopter category to enum
        from open_alaqs.core.interfaces.AircraftTrajectory import (
            AircraftTrajectory,
            AircraftTrajectoryPoint,
        )
        from open_alaqs.core.tools.foca_heli import HelicopterCategory
        from open_alaqs.core.tools.foca_heli_trajectory import (
            build_arrival,
            build_departure,
        )

        try:
            category = HelicopterCategory(category_str)
        except ValueError:
            logger.error(
                "Helicopter trajectory: unknown category '%s' for movement at "
                "runway time '%s'.",
                category_str,
                self._runway_time,
            )
            return None

        # Geodesic projection setup (same EPSG codes as the fixed-wing path)
        epsg_id_source = 3857
        epsg_id_target = 4326
        coord_tr = spatial.create_coordinate_transform(epsg_id_source, epsg_id_target)
        qgs_d = spatial.create_distance_area(epsg_id_source)

        runway_geom = QgsGeometry.fromWkt(self._runway.getGeometryText())
        backup_point, target_point, runway_azimuth_deg = self._get_runway_dir_azimuth(
            runway_geom,
            qgs_d,
        )

        is_dep = self._departure_arrival == "D"
        local_pts = build_departure(category) if is_dep else build_arrival(category)
        if not local_pts:
            logger.error(
                "Helicopter trajectory: builder produced no points for "
                "category '%s', departure_arrival '%s'.",
                category_str,
                self._departure_arrival,
            )
            return None

        # World origin and walk direction for projecting local cartesian points
        # to geographic positions.
        if is_dep:
            origin_projected = backup_point
            walk_azimuth_deg = runway_azimuth_deg
        else:
            origin_projected = target_point
            walk_azimuth_deg = (runway_azimuth_deg + 180.0) % 360.0
        origin_geographic = coord_tr.transform(origin_projected)
        walk_azimuth_rad = math.radians(walk_azimuth_deg)

        # Build a fresh AircraftTrajectory. The metadata fields (profile id,
        # stage, weight) are not used by the helicopter emission path, but we
        # populate them with sensible defaults so downstream logging is sane.
        ac_trajectory = AircraftTrajectory(
            {
                "profile_id": f"HELI-{category_str}-{self._departure_arrival or '?'}",
                "stage": 1,
                "arrival_departure": self._departure_arrival,
                "weight_kgs": None,
            }
        )
        ac_trajectory.setIsCartesian(False)

        for idx, lp in enumerate(local_pts, start=1):
            # Local cartesian distance from origin. Z is altitude (project-
            # independent), x is along-track. y is always 0 for the FOCA
            # helicopter trajectories (no lateral motion).
            distance = math.hypot(lp.x_m, lp.y_m)
            if distance == 0:
                # Avoid degenerate spheroid projection; world position = origin
                target_geographic = origin_geographic
            else:
                target_geographic = qgs_d.computeSpheroidProject(
                    origin_geographic,
                    distance,
                    walk_azimuth_rad,
                )
            target_projected = coord_tr.transform(
                target_geographic,
                QgsCoordinateTransform.ReverseTransform,
            )

            tp = AircraftTrajectoryPoint(
                {
                    "id": idx,
                    "geometry_text": "",
                    "x": target_projected.x(),
                    "y": target_projected.y(),
                    "z": lp.z_m,
                    "tas_metres": lp.tas_m_s,
                    "mode": lp.mode,
                    "course": "",
                    "fuel_flow": None,
                    "weight": None,
                    "power": None,
                }
            )
            tp.setCoordinates(target_projected.x(), target_projected.y(), lp.z_m)
            ac_trajectory.addPoint(tp)

        return ac_trajectory

    def _has_track(self) -> bool:
        if self._track is None:
            return False

        if self._taxi_route is None:
            return False

        taxi_runway = self._taxi_route.getRunway()
        track_runway = self._track.getRunway()

        # Guard against either runway being None (can happen when the DB row
        # has a NULL runway field or the store lookup returns None).
        if taxi_runway is None or track_runway is None:
            logger.warning(
                "Runway is None for taxi route '%s' or track '%s'; reverting to default airplane profile.",
                self._taxi_route.getName(),
                self._track.getName(),
            )
            return False

        # Compare only the direction portion: taxi route stores e.g. "06",
        # track stores the full runway name e.g. "06/24".
        if taxi_runway not in track_runway:
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
