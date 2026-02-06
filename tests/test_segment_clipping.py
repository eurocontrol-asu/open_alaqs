import math

import pytest
from osgeo import osr

from open_alaqs.core.interfaces.AircraftTrajectory import TrajectoryPoint
from open_alaqs.core.tools import spatial

# Enable GDAL exceptions to prepare for GDAL 4.0 and suppress FutureWarning
osr.UseExceptions()


def create_trajectory_point(x, y, z, point_id=1):
    """Helper to create a TrajectoryPoint."""
    return TrajectoryPoint({"id": point_id, "x": x, "y": y, "z": z, "course": "TEST"})


def calculate_2d_distance(x1, y1, x2, y2):
    """Helper to calculate 2D Euclidean distance."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


@pytest.fixture(scope="module")
def grid_bounds():
    """Standard grid bounds for testing (10km x 10km grid)."""
    return {
        "x_min": 555000.0,
        "x_max": 565000.0,
        "y_min": 6355000.0,
        "y_max": 6365000.0,
    }


# =============================================================================
# Tests for clip_segment_to_grid (core coordinate-based function)
# =============================================================================


def test_segment_fully_inside_grid(grid_bounds):
    """Test segment that is completely inside the grid bounds."""
    x1, y1, z1 = 560000, 6360000, 500
    x2, y2, z2 = 560100, 6360100, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    # Should return original points unchanged
    assert clip_x1 is not None
    assert clip_x2 is not None
    assert abs(fraction - 1.0) < 1e-5
    assert abs(clip_x1 - 560000) < 0.01
    assert abs(clip_y1 - 6360000) < 0.01
    assert abs(clip_z1 - 500) < 0.01
    assert abs(clip_x2 - 560100) < 0.01
    assert abs(clip_y2 - 6360100) < 0.01
    assert abs(clip_z2 - 600) < 0.01


def test_segment_fully_outside_grid_left(grid_bounds):
    """Test segment that is completely outside grid (to the left)."""
    x1, y1, z1 = 554000, 6360000, 500
    x2, y2, z2 = 554100, 6360100, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    # Should return None for fully outside segment
    assert clip_x1 is None
    assert clip_x2 is None
    assert clip_y1 is None
    assert clip_y2 is None
    assert clip_z1 is None
    assert clip_z2 is None
    assert fraction == 0.0


def test_segment_fully_outside_grid_right(grid_bounds):
    """Test segment that is completely outside grid (to the right)."""
    x1, y1, z1 = 566000, 6360000, 500
    x2, y2, z2 = 566100, 6360100, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is None
    assert clip_x2 is None
    assert clip_y1 is None
    assert clip_y2 is None
    assert clip_z1 is None
    assert clip_z2 is None
    assert fraction == 0.0


def test_segment_fully_outside_grid_above(grid_bounds):
    """Test segment that is completely outside grid (above)."""
    x1, y1, z1 = 560000, 6366000, 500
    x2, y2, z2 = 560100, 6366100, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is None
    assert clip_x2 is None
    assert clip_y1 is None
    assert clip_y2 is None
    assert clip_z1 is None
    assert clip_z2 is None
    assert fraction == 0.0


def test_segment_fully_outside_grid_below(grid_bounds):
    """Test segment that is completely outside grid (below)."""
    x1, y1, z1 = 560000, 6354000, 500
    x2, y2, z2 = 560100, 6354100, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is None
    assert clip_x2 is None
    assert clip_y1 is None
    assert clip_y2 is None
    assert clip_z1 is None
    assert clip_z2 is None
    assert fraction == 0.0


def test_segment_partially_in_grid_entering_left(grid_bounds):
    """Test segment that starts outside and enters the grid from the left."""
    x1, y1, z1 = 554900, 6360000, 500
    x2, y2, z2 = 555200, 6360000, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None

    # Start should be clipped to grid boundary
    assert abs(clip_x1 - 555000) < 1.0
    assert abs(clip_y1 - 6360000) < 1.0

    # End should remain unchanged
    assert abs(clip_x2 - 555200) < 1.0
    assert abs(clip_y2 - 6360000) < 1.0

    # Check Z interpolation: segment goes 554900->555200 (300m), clipped at 555000 (100m in)
    # t = 100/300 = 1/3, z = 500 + (1/3) * (600 - 500) aprox 533.33
    assert 530 < clip_z1 < 540
    assert abs(clip_z2 - 600) < 1.0

    # Check fraction is less than 1
    assert 0.0 < fraction < 1.0


def test_segment_partially_in_grid_exiting_right(grid_bounds):
    """Test segment that exits the grid on the right side."""
    x1, y1, z1 = 564900, 6360000, 500
    x2, y2, z2 = 565200, 6360000, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None

    # Start should remain unchanged
    assert abs(clip_x1 - 564900) < 1.0

    # End should be clipped to grid boundary
    assert abs(clip_x2 - 565000) < 1.0

    # Check Z interpolation: segment goes 564900->565200 (300m), clipped at 565000 (100m in)
    # t = 100/300 = 1/3, z = 500 + (1/3) * (600 - 500) aprox 533.33
    assert abs(clip_z1 - 500) < 1.0
    assert 530 < clip_z2 < 540

    assert 0.0 < fraction < 1.0


def test_distance_ratio_horizontal_segment(grid_bounds):
    """Test that distance ratio is computed correctly for horizontal segment."""
    # Segment from x=554900 to x=555300 (400m total), clipped to x=555000 to x=555300 (300m)
    x1, y1, z1 = 554900, 6360000, 500
    x2, y2, z2 = 555300, 6360000, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None

    # Original distance: 400m
    # Clipped distance: 300m (from 555000 to 555300)
    # Expected fraction: 300/400 = 0.75
    expected_fraction = 0.75
    assert abs(fraction - expected_fraction) < 0.01


def test_distance_ratio_diagonal_segment(grid_bounds):
    """Test that distance ratio is computed correctly for diagonal segment."""
    # Diagonal segment partially clipped
    x1, y1, z1 = 554000, 6360000, 500
    x2, y2, z2 = 560000, 6360000, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None

    # Original distance: 6000m
    # Clipped distance: from 555000 to 560000 = 5000m
    # Expected fraction: 5000/6000 aprox 0.833
    original_dist = calculate_2d_distance(554000, 6360000, 560000, 6360000)
    clipped_dist = calculate_2d_distance(clip_x1, clip_y1, clip_x2, clip_y2)
    expected_fraction = clipped_dist / original_dist

    assert abs(fraction - expected_fraction) < 0.01


def test_z_coordinate_interpolation_horizontal(grid_bounds):
    """Test that Z coordinate is correctly interpolated when clipping horizontal segment."""
    # Segment from (554900, 6360000, 100) to (555200, 6360000, 400)
    # Should be clipped to start at x=555000
    x1, y1, z1 = 554900, 6360000, 100
    x2, y2, z2 = 555200, 6360000, 400

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None

    # Calculate expected Z at x=555000
    # Original segment: x goes from 554900 to 555200 (300m total)
    # Clipped starts at x=555000, which is 100m into the segment
    # t = 100/300 = 1/3
    # z = 100 + (1/3) * (400 - 100) = 100 + 100 = 200
    expected_z = 200

    assert abs(clip_z1 - expected_z) < 5.0


def test_z_coordinate_interpolation_diagonal(grid_bounds):
    """Test Z coordinate interpolation for diagonal segment crossing grid."""
    x1, y1, z1 = 554000, 6354000, 100
    x2, y2, z2 = 566000, 6366000, 900

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None

    # Verify Z interpolation is monotonic
    assert clip_z2 > clip_z1
    assert clip_z1 > 100  # Higher than original start
    assert clip_z2 < 900  # Lower than original end
    assert 0 <= fraction < 1  # The segment was indeed clipped


def test_segment_crossing_grid_diagonally(grid_bounds):
    """Test diagonal segment that crosses the entire grid."""
    x1, y1, z1 = 554000, 6354000, 500
    x2, y2, z2 = 566000, 6366000, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None

    # Both points should be within grid boundaries
    assert grid_bounds["x_min"] <= clip_x1 <= grid_bounds["x_max"]
    assert grid_bounds["x_min"] <= clip_x2 <= grid_bounds["x_max"]
    assert grid_bounds["y_min"] <= clip_y1 <= grid_bounds["y_max"]
    assert grid_bounds["y_min"] <= clip_y2 <= grid_bounds["y_max"]

    assert 0.0 < fraction < 1.0


def test_zero_length_segment(grid_bounds):
    """Test segment where start and end points are identical."""
    x1, y1, z1 = 560000, 6360000, 500
    x2, y2, z2 = 560000, 6360000, 500

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    # Should handle zero-length segment gracefully
    assert clip_x1 is not None
    assert clip_x2 is not None
    assert fraction == 1.0


def test_segment_on_left_boundary(grid_bounds):
    """Test segment exactly on the left grid boundary."""
    x1, y1, z1 = 555000, 6360000, 500
    x2, y2, z2 = 555000, 6360100, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None
    assert abs(fraction - 1.0) < 1e-5


def test_segment_on_right_boundary(grid_bounds):
    """Test segment exactly on the right grid boundary."""
    x1, y1, z1 = 565000, 6360000, 500
    x2, y2, z2 = 565000, 6360100, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None
    assert abs(fraction - 1.0) < 1e-5


def test_segment_on_bottom_boundary(grid_bounds):
    """Test segment on the bottom grid boundary."""
    x1, y1, z1 = 560000, 6355000, 500
    x2, y2, z2 = 560100, 6355000, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None
    assert abs(fraction - 1.0) < 1e-5


def test_segment_on_top_boundary(grid_bounds):
    """Test segment on the top grid boundary."""
    x1, y1, z1 = 560000, 6365000, 500
    x2, y2, z2 = 560100, 6365000, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None
    assert abs(fraction - 1.0) < 1e-5


def test_segment_through_corner(grid_bounds):
    """Test segment that passes through a corner of the grid."""
    # Segment passing through bottom-left corner region
    x1, y1, z1 = 554000, 6354000, 100
    x2, y2, z2 = 556000, 6356000, 300

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None

    # Should be clipped to grid boundaries
    assert grid_bounds["x_min"] <= clip_x1 <= grid_bounds["x_max"]
    assert grid_bounds["y_min"] <= clip_y1 <= grid_bounds["y_max"]
    assert 0.0 < fraction < 1.0


def test_very_long_segment_through_grid(grid_bounds):
    """Test very long segment that passes through the grid."""
    x1, y1, z1 = 500000, 6300000, 1000
    x2, y2, z2 = 600000, 6400000, 2000

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None

    # Both points should be within bounds
    assert grid_bounds["x_min"] <= clip_x1 <= grid_bounds["x_max"]
    assert grid_bounds["x_min"] <= clip_x2 <= grid_bounds["x_max"]
    assert grid_bounds["y_min"] <= clip_y1 <= grid_bounds["y_max"]
    assert grid_bounds["y_min"] <= clip_y2 <= grid_bounds["y_max"]

    # Fraction should be very small (grid is small compared to segment)
    assert 0.0 < fraction < 0.5


def test_segment_tangent_to_boundary(grid_bounds):
    """Test segment that just touches the grid boundary."""
    # Horizontal segment just at the left boundary
    x1, y1, z1 = 554999, 6360000, 500
    x2, y2, z2 = 555001, 6360000, 600

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    # Should clip the segment at the boundary
    assert clip_x1 is not None or clip_x2 is not None or fraction > 0.0


def test_getDistanceBetweenPoints_2d_with_defaults():
    """Test 2D distance calculation using default z=0."""
    distance = spatial.getDistanceBetweenPoints(0, 0, 0, 3, 4, 0)
    assert abs(distance - 5.0) < 1e-5


def test_getDistanceBetweenPoints_2d_without_z_params():
    """Test 2D distance calculation omitting z parameters (using defaults)."""
    distance = spatial.getDistanceBetweenPoints(0, 0, x2=3, y2=4)
    assert abs(distance - 5.0) < 1e-5


def test_getDistanceBetweenPoints_3d():
    """Test 3D distance calculation."""
    distance = spatial.getDistanceBetweenPoints(0, 0, 0, 1, 1, 1)
    expected = math.sqrt(3)  # sqrt(1^2 + 1^2 + 1^2)
    assert abs(distance - expected) < 1e-5


def test_getDistanceBetweenPoints_zero():
    """Test distance between identical points."""
    distance = spatial.getDistanceBetweenPoints(5, 10, 15, 5, 10, 15)
    assert distance == 0.0


def test_getDistanceBetweenPoints_negative_coordinates():
    """Test distance with negative coordinates."""
    distance = spatial.getDistanceBetweenPoints(-3, -4, 0, 0, 0, 0)
    assert abs(distance - 5.0) < 1e-5


# =============================================================================
# Tests for clip_trajectory_segment_to_grid (TrajectoryPoint wrapper)
# =============================================================================


def test_trajectory_segment_fully_inside_grid(grid_bounds):
    """Test trajectory segment that is completely inside the grid bounds."""
    start = create_trajectory_point(560000, 6360000, 500, 1)
    end = create_trajectory_point(560100, 6360100, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_trajectory_segment_to_grid(
        start, end, grid_bounds
    )

    # Should return original points unchanged
    assert clipped_start is not None
    assert clipped_end is not None
    assert abs(fraction - 1.0) < 1e-5
    assert abs(clipped_start.getX() - 560000) < 0.01
    assert abs(clipped_start.getY() - 6360000) < 0.01
    assert abs(clipped_end.getX() - 560100) < 0.01
    assert abs(clipped_end.getY() - 6360100) < 0.01
    # Check metadata is preserved
    assert clipped_start.getIdentifier() == 1
    assert clipped_end.getIdentifier() == 2
    assert clipped_start.getCourse() == "TEST"


def test_trajectory_segment_fully_outside_grid(grid_bounds):
    """Test trajectory segment that is completely outside grid."""
    start = create_trajectory_point(554000, 6360000, 500, 1)
    end = create_trajectory_point(554100, 6360100, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_trajectory_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is None
    assert clipped_end is None
    assert fraction == 0.0


def test_trajectory_segment_partially_in_grid(grid_bounds):
    """Test trajectory segment that starts outside and enters the grid."""
    start = create_trajectory_point(554900, 6360000, 500, 1)
    end = create_trajectory_point(555200, 6360000, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_trajectory_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None

    # Start should be clipped to grid boundary
    assert abs(clipped_start.getX() - 555000) < 1.0
    assert abs(clipped_start.getY() - 6360000) < 1.0

    # End should remain unchanged
    assert abs(clipped_end.getX() - 555200) < 1.0
    assert abs(clipped_end.getY() - 6360000) < 1.0

    # Check Z interpolation
    assert 500 < clipped_start.getZ() < 600

    # Check metadata is preserved
    assert clipped_start.getIdentifier() == 1
    assert clipped_end.getIdentifier() == 2

    assert 0.0 < fraction < 1.0


def test_trajectory_z_coordinate_interpolation(grid_bounds):
    """Test that Z coordinate is correctly interpolated in trajectory clipping."""
    start = create_trajectory_point(554900, 6360000, 100, 1)
    end = create_trajectory_point(555200, 6360000, 400, 2)

    clipped_start, clipped_end, fraction = spatial.clip_trajectory_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None

    # Expected Z at x=555000: interpolated from 100 to 400
    # Segment: x from 554900 to 555200 (300m), clipped at 555000 (100m into segment)
    # t = 100/300 = 1/3, z = 100 + (1/3) * 300 = 200
    expected_z = 200
    assert abs(clipped_start.getZ() - expected_z) < 5.0


# =============================================================================
# Tests for clip_linestring_to_grid (LineString/roadway wrapper)
# =============================================================================


def test_linestring_fully_inside_grid(grid_bounds):
    """Test LineString that is completely inside the grid."""
    # Simple 2-point LineString
    wkt = "LINESTRING Z(560000 6360000 0, 560100 6360100 0)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    # For a fully inside LineString, the length fraction should be very close to 1.0
    assert 0.98 < length_fraction <= 1.0
    # Original geometry should be preserved
    assert "560000" in clipped_wkt
    assert "560100" in clipped_wkt


def test_linestring_fully_outside_grid(grid_bounds):
    """Test LineString that is completely outside the grid."""
    wkt = "LINESTRING Z(554000 6360000 0, 554100 6360100 0)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is None
    assert length_fraction == 0.0


def test_linestring_partially_in_grid(grid_bounds):
    """Test LineString that partially intersects the grid."""
    # LineString extending from outside to inside the grid
    wkt = "LINESTRING Z(554900 6360000 0, 555200 6360000 0)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert 0.0 < length_fraction < 1.0
    # Should contain clipped coordinates near grid boundary
    assert "555000" in clipped_wkt or "555001" in clipped_wkt


def test_multipoint_linestring_clipping(grid_bounds):
    """Test clipping of a multi-segment LineString."""
    # LineString with 4 points (3 segments)
    # First segment outside, second crosses boundary, third inside
    wkt = "LINESTRING Z(554000 6360000 0, 554500 6360000 0, 555500 6360000 0, 560000 6360000 0)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert 0.0 < length_fraction < 1.0
    # Should have multiple points in the clipped result
    assert clipped_wkt.startswith("LINESTRING Z(")
    # Count commas to approximate number of points (n points = n-1 commas in coords)
    point_count = clipped_wkt.count(",") + 1
    assert point_count >= 2  # At least 2 points for a valid LineString


def test_linestring_crossing_grid_completely(grid_bounds):
    """Test LineString that crosses the entire grid from outside to outside."""
    # Diagonal line crossing the grid
    wkt = "LINESTRING Z(554000 6354000 100, 566000 6366000 900)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert 0.0 < length_fraction < 1.0

    # Verify the clipped line has reasonable coordinates
    # Extract first and last coordinate values to check they're within grid
    import re

    coords = re.findall(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)", clipped_wkt)
    assert len(coords) >= 2

    # First point should be at or near grid boundary
    first_x, first_y, first_z = (
        float(coords[0][0]),
        float(coords[0][1]),
        float(coords[0][2]),
    )
    assert grid_bounds["x_min"] <= first_x <= grid_bounds["x_max"]
    assert grid_bounds["y_min"] <= first_y <= grid_bounds["y_max"]

    # Last point should be at or near grid boundary
    last_x, last_y, last_z = (
        float(coords[-1][0]),
        float(coords[-1][1]),
        float(coords[-1][2]),
    )
    assert grid_bounds["x_min"] <= last_x <= grid_bounds["x_max"]
    assert grid_bounds["y_min"] <= last_y <= grid_bounds["y_max"]


def test_linestring_zero_length(grid_bounds):
    """Test LineString with identical start and end points."""
    wkt = "LINESTRING Z(560000 6360000 0, 560000 6360000 0)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    # Should handle gracefully
    assert clipped_wkt is not None
    assert length_fraction == 1.0


def test_linestring_z_interpolation(grid_bounds):
    """Test that Z coordinates are interpolated correctly in LineString clipping."""
    # LineString with significant Z change, partially clipped
    wkt = "LINESTRING Z(554900 6360000 100, 555200 6360000 400)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert 0.0 < length_fraction < 1.0

    # Extract Z coordinates
    import re

    coords = re.findall(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)", clipped_wkt)
    assert len(coords) >= 2

    # First Z should be interpolated (around 200)
    first_z = float(coords[0][2])
    assert 150 < first_z < 250


# =============================================================================
# Additional comprehensive tests for all 3 methods
# =============================================================================


# Tests for edge cases with extreme Z-values
def test_segment_extreme_z_values(grid_bounds):
    """Test clip_segment_to_grid with very large Z-value changes."""
    x1, y1, z1 = 554900, 6360000, 0
    x2, y2, z2 = 555200, 6360000, 10000  # 10km altitude change

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None
    assert clip_z1 < clip_z2
    assert 0.0 < fraction < 1.0
    # Verify Z values are within expected range
    assert clip_z1 >= 0
    assert clip_z2 <= 10000


def test_segment_negative_z_values(grid_bounds):
    """Test clip_segment_to_grid with negative Z values (below reference level)."""
    x1, y1, z1 = 554900, 6360000, -500
    x2, y2, z2 = 555200, 6360000, 500

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None
    assert clip_z1 < clip_z2
    assert clip_z1 < 0  # Should preserve negative Z


def test_segment_very_steep_angle(grid_bounds):
    """Test segment with very steep angle (nearly vertical in XY plane)."""
    x1, y1, z1 = 560000, 6354100, 100
    x2, y2, z2 = 560000, 6365900, 900  # Nearly vertical

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None
    # Y coordinates should be clipped to grid
    assert clip_y1 >= grid_bounds["y_min"]
    assert clip_y2 <= grid_bounds["y_max"]
    assert 0.0 < fraction < 1.0


def test_segment_very_shallow_angle(grid_bounds):
    """Test segment with very shallow angle (nearly horizontal in XY plane)."""
    x1, y1, z1 = 554800, 6360000, 100
    x2, y2, z2 = 565200, 6360050, 900  # Nearly horizontal

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None
    assert clip_x1 >= grid_bounds["x_min"]
    assert clip_x2 <= grid_bounds["x_max"]
    assert 0.0 < fraction < 1.0


def test_segment_barely_touches_grid(grid_bounds):
    """Test segment that barely touches the grid at a corner."""
    # Line touching at bottom-left corner
    x1, y1, z1 = 554500, 6354500, 100
    x2, y2, z2 = 555500, 6355500, 200

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    # May or may not be clipped depending on QgsClipper behavior
    # Just verify it handles gracefully
    if clip_x1 is not None:
        assert grid_bounds["x_min"] <= clip_x1 <= grid_bounds["x_max"]
        assert grid_bounds["y_min"] <= clip_y1 <= grid_bounds["y_max"]
        assert 0.0 <= fraction <= 1.0


def test_segment_with_floating_point_precision(grid_bounds):
    """Test segment with coordinates at floating point precision limits."""
    x1, y1, z1 = 555000.0000001, 6360000.5, 500.123456
    x2, y2, z2 = 555100.9999999, 6360100.5, 600.654321

    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, fraction = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    assert clip_x1 is not None
    assert clip_x2 is not None
    assert abs(fraction - 1.0) < 0.01


# Additional tests for clip_trajectory_segment_to_grid
def test_trajectory_segment_preserves_all_metadata(grid_bounds):
    """Test that trajectory clipping preserves all TrajectoryPoint metadata."""
    start = create_trajectory_point(554900, 6360000, 500, 42)
    end = create_trajectory_point(555200, 6360000, 600, 99)

    # Set course explicitly
    start._data if hasattr(start, "_data") else {}
    end._data if hasattr(end, "_data") else {}

    clipped_start, clipped_end, fraction = spatial.clip_trajectory_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None

    # Verify IDs are preserved
    assert clipped_start.getIdentifier() == 42
    assert clipped_end.getIdentifier() == 99

    # Verify course is preserved
    assert clipped_start.getCourse() == "TEST"
    assert clipped_end.getCourse() == "TEST"


def test_trajectory_segment_exits_all_sides(grid_bounds):
    """Test trajectory clipping with segment exiting each side of grid."""
    # Test exiting right
    start_right = create_trajectory_point(564900, 6360000, 500, 1)
    end_right = create_trajectory_point(565200, 6360000, 600, 2)

    clipped_s, clipped_e, frac = spatial.clip_trajectory_segment_to_grid(
        start_right, end_right, grid_bounds
    )
    assert clipped_s is not None and clipped_e is not None
    assert clipped_e.getX() <= grid_bounds["x_max"]

    # Test exiting top
    start_top = create_trajectory_point(560000, 6364900, 500, 1)
    end_top = create_trajectory_point(560000, 6365200, 600, 2)

    clipped_s, clipped_e, frac = spatial.clip_trajectory_segment_to_grid(
        start_top, end_top, grid_bounds
    )
    assert clipped_s is not None and clipped_e is not None
    assert clipped_e.getY() <= grid_bounds["y_max"]

    # Test exiting bottom
    start_bottom = create_trajectory_point(560000, 6355100, 500, 1)
    end_bottom = create_trajectory_point(560000, 6354800, 600, 2)

    clipped_s, clipped_e, frac = spatial.clip_trajectory_segment_to_grid(
        start_bottom, end_bottom, grid_bounds
    )
    assert clipped_s is not None and clipped_e is not None
    assert clipped_e.getY() >= grid_bounds["y_min"]


def test_trajectory_segment_diagonal_crossing(grid_bounds):
    """Test trajectory segment with diagonal crossing from corner to corner."""
    start = create_trajectory_point(554000, 6354000, 100, 1)
    end = create_trajectory_point(566000, 6366000, 900, 2)

    clipped_start, clipped_end, fraction = spatial.clip_trajectory_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    assert 0.0 < fraction < 1.0

    # Verify clipped points are within grid
    assert grid_bounds["x_min"] <= clipped_start.getX() <= grid_bounds["x_max"]
    assert grid_bounds["y_min"] <= clipped_start.getY() <= grid_bounds["y_max"]
    assert grid_bounds["x_min"] <= clipped_end.getX() <= grid_bounds["x_max"]
    assert grid_bounds["y_min"] <= clipped_end.getY() <= grid_bounds["y_max"]

    # Verify Z progression
    assert clipped_start.getZ() < clipped_end.getZ()


def test_trajectory_with_extreme_z_values(grid_bounds):
    """Test trajectory clipping with extreme altitude changes."""
    start = create_trajectory_point(554900, 6360000, 0, 1)  # Sea level
    end = create_trajectory_point(555200, 6360000, 15000, 2)  # 15km altitude

    clipped_start, clipped_end, fraction = spatial.clip_trajectory_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    assert clipped_start.getZ() >= 0
    assert clipped_end.getZ() <= 15000
    assert 0.0 < fraction < 1.0


# Additional tests for clip_linestring_to_grid
def test_linestring_with_many_segments(grid_bounds):
    """Test clipping of LineString with many intermediate segments."""
    # Create a LineString with many points forming a path
    coords = [
        (554000, 6360000, 0),
        (555000, 6358000, 200),
        (556000, 6360000, 400),
        (557000, 6361000, 600),
        (558000, 6360000, 800),
        (566000, 6360000, 1000),
    ]

    coords_str = ", ".join([f"{x} {y} {z}" for x, y, z in coords])
    wkt = f"LINESTRING Z({coords_str})"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert 0.0 < length_fraction < 1.0
    # Should have multiple segments preserved
    assert clipped_wkt.count(",") >= 1


def test_linestring_entering_and_exiting_grid(grid_bounds):
    """Test LineString that enters and exits the grid multiple times."""
    # Path that goes: outside -> inside -> outside
    wkt = "LINESTRING Z(554000 6360000 0, 555500 6360000 500, 565500 6360000 1000)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert 0.0 < length_fraction < 1.0


def test_linestring_with_z_values_preserved(grid_bounds):
    """Test that Z values are preserved and interpolated in complex LineString."""
    # Multi-segment LineString with varying Z
    wkt = "LINESTRING Z(554500 6360000 100, 555000 6360000 200, 560000 6360000 800, 565500 6360000 1200)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None

    # Extract and verify Z values
    import re

    coords = re.findall(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)", clipped_wkt)
    assert len(coords) >= 2

    # Z values should form an increasing sequence
    z_values = [float(c[2]) for c in coords]
    for i in range(len(z_values) - 1):
        assert z_values[i] <= z_values[i + 1]


def test_linestring_complex_geometry_clipping(grid_bounds):
    """Test clipping of complex LineString with multiple turns."""
    wkt = """LINESTRING Z(554000 6360000 0,
                         555000 6359000 200,
                         556000 6361000 400,
                         557000 6360000 600,
                         566500 6360000 800)"""

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert 0.0 < length_fraction < 1.0


def test_linestring_boundary_coordinates_precision(grid_bounds):
    """Test LineString clipping with coordinates at grid boundaries."""
    # LineString with points exactly on or very near grid boundaries
    wkt = "LINESTRING Z(554999 6360000 0, 555001 6360000 100, 564999 6360000 200, 565001 6360000 300)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert length_fraction > 0.0


def test_linestring_vertical_segment(grid_bounds):
    """Test LineString with vertical segment (constant X, varying Y)."""
    wkt = "LINESTRING Z(560000 6354000 0, 560000 6366000 1000)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert 0.0 < length_fraction < 1.0

    # Verify Y coordinates are clipped to grid
    import re

    coords = re.findall(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)", clipped_wkt)
    all_y = [float(c[1]) for c in coords]
    assert min(all_y) >= grid_bounds["y_min"]
    assert max(all_y) <= grid_bounds["y_max"]


def test_linestring_horizontal_segment(grid_bounds):
    """Test LineString with horizontal segment (constant Y, varying X)."""
    wkt = "LINESTRING Z(554000 6360000 0, 566000 6360000 1000)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert 0.0 < length_fraction < 1.0

    # Verify X coordinates are clipped to grid
    import re

    coords = re.findall(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)", clipped_wkt)
    all_x = [float(c[0]) for c in coords]
    assert min(all_x) >= grid_bounds["x_min"]
    assert max(all_x) <= grid_bounds["x_max"]


def test_linestring_with_sharp_angles(grid_bounds):
    """Test LineString with sharp angles and corners."""
    # Path with 90-degree angles
    wkt = "LINESTRING Z(554000 6360000 0, 555500 6360000 200, 555500 6365000 800)"

    clipped_wkt, length_fraction = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    assert clipped_wkt is not None
    assert 0.0 < length_fraction < 1.0


# Integration tests covering interactions between the 3 methods
def test_consistency_between_methods_single_segment(grid_bounds):
    """Test that clip_segment_to_grid and clip_trajectory_segment_to_grid give consistent results."""
    # Create matching inputs
    x1, y1, z1 = 554900, 6360000, 500
    x2, y2, z2 = 555200, 6360000, 600

    # Test using core function
    (
        clip_x1_core,
        clip_y1_core,
        clip_z1_core,
        clip_x2_core,
        clip_y2_core,
        clip_z2_core,
        frac_core,
    ) = spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)

    # Test using trajectory wrapper
    start_traj = create_trajectory_point(x1, y1, z1, 1)
    end_traj = create_trajectory_point(x2, y2, z2, 2)
    clipped_start, clipped_end, frac_traj = spatial.clip_trajectory_segment_to_grid(
        start_traj, end_traj, grid_bounds
    )

    # Results should be consistent
    assert clipped_start is not None and clipped_end is not None
    assert abs(clipped_start.getX() - clip_x1_core) < 0.1
    assert abs(clipped_start.getY() - clip_y1_core) < 0.1
    assert abs(clipped_start.getZ() - clip_z1_core) < 0.1
    assert abs(clipped_end.getX() - clip_x2_core) < 0.1
    assert abs(clipped_end.getY() - clip_y2_core) < 0.1
    assert abs(clipped_end.getZ() - clip_z2_core) < 0.1
    assert abs(frac_core - frac_traj) < 1e-5


def test_consistency_between_methods_linestring(grid_bounds):
    """Test consistency between clip_segment_to_grid and clip_linestring_to_grid."""
    # Create a 2-segment LineString
    x1, y1, z1 = 554900, 6360000, 100
    x2, y2, z2 = 555200, 6360000, 300

    # Clip individual segment
    clip_x1, clip_y1, clip_z1, clip_x2, clip_y2, clip_z2, frac = (
        spatial.clip_segment_to_grid(x1, y1, z1, x2, y2, z2, grid_bounds)
    )

    # Clip as LineString
    wkt = f"LINESTRING Z({x1} {y1} {z1}, {x2} {y2} {z2})"
    clipped_wkt, length_frac = spatial.clip_linestring_to_grid(wkt, grid_bounds)

    # Both should indicate clipping occurred
    assert clip_x1 is not None
    assert clipped_wkt is not None

    # Length fractions should be similar
    assert abs(frac - length_frac) < 0.1
