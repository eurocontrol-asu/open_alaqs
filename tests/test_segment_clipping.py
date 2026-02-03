import pytest

import math
from open_alaqs.core.interfaces.AircraftTrajectory import TrajectoryPoint
from open_alaqs.core.tools import spatial


def create_trajectory_point(x, y, z, point_id=1):
    """Helper to create a TrajectoryPoint."""
    return TrajectoryPoint({
        "id": point_id,
        "x": x,
        "y": y,
        "z": z,
        "course": "TEST"
    })


def calculate_2d_distance(x1, y1, x2, y2):
    """Helper to calculate 2D Euclidean distance."""
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)


@pytest.fixture(scope="module")
def grid_bounds():
    """Standard grid bounds for testing (10km x 10km grid)."""
    return {
        "x_min": 555000.0,
        "x_max": 565000.0,
        "y_min": 6355000.0,
        "y_max": 6365000.0,
    }


def test_segment_fully_inside_grid(grid_bounds):
    """Test segment that is completely inside the grid bounds."""
    start = create_trajectory_point(560000, 6360000, 500, 1)
    end = create_trajectory_point(560100, 6360100, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
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


def test_segment_fully_outside_grid_left(grid_bounds):
    """Test segment that is completely outside grid (to the left)."""
    start = create_trajectory_point(554000, 6360000, 500, 1)
    end = create_trajectory_point(554100, 6360100, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    # Should return None for fully outside segment
    assert clipped_start is None
    assert clipped_end is None
    assert fraction == 0.0


def test_segment_fully_outside_grid_right(grid_bounds):
    """Test segment that is completely outside grid (to the right)."""
    start = create_trajectory_point(566000, 6360000, 500, 1)
    end = create_trajectory_point(566100, 6360100, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is None
    assert clipped_end is None
    assert fraction == 0.0


def test_segment_fully_outside_grid_above(grid_bounds):
    """Test segment that is completely outside grid (above)."""
    start = create_trajectory_point(560000, 6366000, 500, 1)
    end = create_trajectory_point(560100, 6366100, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is None
    assert clipped_end is None
    assert fraction == 0.0


def test_segment_fully_outside_grid_below(grid_bounds):
    """Test segment that is completely outside grid (below)."""
    start = create_trajectory_point(560000, 6354000, 500, 1)
    end = create_trajectory_point(560100, 6354100, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is None
    assert clipped_end is None
    assert fraction == 0.0


def test_segment_partially_in_grid_entering_left(grid_bounds):
    """Test segment that starts outside and enters the grid from the left."""
    start = create_trajectory_point(554900, 6360000, 500, 1)
    end = create_trajectory_point(555200, 6360000, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
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
    
    # Check fraction is less than 1
    assert 0.0 < fraction < 1.0


def test_segment_partially_in_grid_exiting_right(grid_bounds):
    """Test segment that exits the grid on the right side."""
    start = create_trajectory_point(564900, 6360000, 500, 1)
    end = create_trajectory_point(565200, 6360000, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    
    # Start should remain unchanged
    assert abs(clipped_start.getX() - 564900) < 1.0
    
    # End should be clipped to grid boundary
    assert abs(clipped_end.getX() - 565000) < 1.0
    
    assert 0.0 < fraction < 1.0


def test_distance_ratio_horizontal_segment(grid_bounds):
    """Test that distance ratio is computed correctly for horizontal segment."""
    # Segment from x=554900 to x=555300 (400m total), clipped to x=555000 to x=555300 (300m)
    start = create_trajectory_point(554900, 6360000, 500, 1)
    end = create_trajectory_point(555300, 6360000, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    
    # Original distance: 400m
    # Clipped distance: 300m (from 555000 to 555300)
    # Expected fraction: 300/400 = 0.75
    expected_fraction = 0.75
    assert abs(fraction - expected_fraction) < 0.01


def test_distance_ratio_diagonal_segment(grid_bounds):
    """Test that distance ratio is computed correctly for diagonal segment."""
    # Diagonal segment partially clipped
    start = create_trajectory_point(554000, 6360000, 500, 1)
    end = create_trajectory_point(560000, 6360000, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    
    # Original distance: 6000m
    # Clipped distance: from 555000 to 560000 = 5000m
    # Expected fraction: 5000/6000 ≈ 0.833
    original_dist = calculate_2d_distance(554000, 6360000, 560000, 6360000)
    clipped_dist = calculate_2d_distance(clipped_start.getX(), clipped_start.getY(), 
                                        clipped_end.getX(), clipped_end.getY())
    expected_fraction = clipped_dist / original_dist
    
    assert abs(fraction - expected_fraction) < 0.01


def test_z_coordinate_interpolation_horizontal(grid_bounds):
    """Test that Z coordinate is correctly interpolated when clipping horizontal segment."""
    # Segment from (554900, 6360000, 100) to (555200, 6360000, 400)
    # Should be clipped to start at x=555000
    start = create_trajectory_point(554900, 6360000, 100, 1)
    end = create_trajectory_point(555200, 6360000, 400, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    
    # Calculate expected Z at x=555000
    # Original segment: x goes from 554900 to 555200 (300m total)
    # Clipped starts at x=555000, which is 100m into the segment
    # t = 100/300 = 1/3
    # z = 100 + (1/3) * (400 - 100) = 100 + 100 = 200
    expected_z = 200
    
    assert abs(clipped_start.getZ() - expected_z) < 5.0


def test_z_coordinate_interpolation_diagonal(grid_bounds):
    """Test Z coordinate interpolation for diagonal segment crossing grid."""
    start = create_trajectory_point(554000, 6354000, 100, 1)
    end = create_trajectory_point(566000, 6366000, 900, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    
    # Verify Z interpolation is monotonic
    assert clipped_end.getZ() > clipped_start.getZ()
    assert clipped_start.getZ() > 100  # Higher than original start
    assert clipped_end.getZ() < 900  # Lower than original end
    assert 0 <= fraction < 1 # The segment was indeed clipped


def test_segment_crossing_grid_diagonally(grid_bounds):
    """Test diagonal segment that crosses the entire grid."""
    start = create_trajectory_point(554000, 6354000, 500, 1)
    end = create_trajectory_point(566000, 6366000, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    
    # Both points should be within grid boundaries
    assert grid_bounds["x_min"] <= clipped_start.getX() <= grid_bounds["x_max"]
    assert grid_bounds["x_min"] <= clipped_end.getX() <= grid_bounds["x_max"]
    assert grid_bounds["y_min"] <= clipped_start.getY() <= grid_bounds["y_max"]
    assert grid_bounds["y_min"] <= clipped_end.getY() <= grid_bounds["y_max"]
    
    assert 0.0 < fraction < 1.0


def test_zero_length_segment(grid_bounds):
    """Test segment where start and end points are identical."""
    start = create_trajectory_point(560000, 6360000, 500, 1)
    end = create_trajectory_point(560000, 6360000, 500, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    # Should handle zero-length segment gracefully
    assert clipped_start is not None
    assert clipped_end is not None
    assert fraction == 1.0


def test_segment_on_left_boundary(grid_bounds):
    """Test segment exactly on the left grid boundary."""
    start = create_trajectory_point(555000, 6360000, 500, 1)
    end = create_trajectory_point(555000, 6360100, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    assert abs(fraction - 1.0) < 1e-5


def test_segment_on_right_boundary(grid_bounds):
    """Test segment exactly on the right grid boundary."""
    start = create_trajectory_point(565000, 6360000, 500, 1)
    end = create_trajectory_point(565000, 6360100, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    assert abs(fraction - 1.0) < 1e-5


def test_segment_on_bottom_boundary(grid_bounds):
    """Test segment on the bottom grid boundary."""
    start = create_trajectory_point(560000, 6355000, 500, 1)
    end = create_trajectory_point(560100, 6355000, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    assert abs(fraction - 1.0) < 1e-5


def test_segment_on_top_boundary(grid_bounds):
    """Test segment on the top grid boundary."""
    start = create_trajectory_point(560000, 6365000, 500, 1)
    end = create_trajectory_point(560100, 6365000, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    assert abs(fraction - 1.0) < 1e-5


def test_segment_through_corner(grid_bounds):
    """Test segment that passes through a corner of the grid."""
    # Segment passing through bottom-left corner region
    start = create_trajectory_point(554000, 6354000, 100, 1)
    end = create_trajectory_point(556000, 6356000, 300, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    
    # Should be clipped to grid boundaries
    assert grid_bounds["x_min"] <= clipped_start.getX() <= grid_bounds["x_max"]
    assert grid_bounds["y_min"] <= clipped_start.getY() <= grid_bounds["y_max"]
    assert 0.0 < fraction < 1.0


def test_very_long_segment_through_grid(grid_bounds):
    """Test very long segment that passes through the grid."""
    start = create_trajectory_point(500000, 6300000, 1000, 1)
    end = create_trajectory_point(600000, 6400000, 2000, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    assert clipped_start is not None
    assert clipped_end is not None
    
    # Both points should be within bounds
    assert grid_bounds["x_min"] <= clipped_start.getX() <= grid_bounds["x_max"]
    assert grid_bounds["x_min"] <= clipped_end.getX() <= grid_bounds["x_max"]
    assert grid_bounds["y_min"] <= clipped_start.getY() <= grid_bounds["y_max"]
    assert grid_bounds["y_min"] <= clipped_end.getY() <= grid_bounds["y_max"]
    
    # Fraction should be very small (grid is small compared to segment)
    assert 0.0 < fraction < 0.5


def test_segment_tangent_to_boundary(grid_bounds):
    """Test segment that just touches the grid boundary."""
    # Horizontal segment just at the left boundary
    start = create_trajectory_point(554999, 6360000, 500, 1)
    end = create_trajectory_point(555001, 6360000, 600, 2)

    clipped_start, clipped_end, fraction = spatial.clip_segment_to_grid(
        start, end, grid_bounds
    )

    # Should clip the segment at the boundary
    assert clipped_start is not None or clipped_end is not None or fraction > 0.0


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
