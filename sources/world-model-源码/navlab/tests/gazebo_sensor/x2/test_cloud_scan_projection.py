from __future__ import annotations

import math

from navlab.sim.gazebo_sensor.cloud_scan_projection import PointXYZ, project_points_to_ranges


def test_cloud_scan_projection_keeps_wall_shape_not_static_circle() -> None:
    points = [PointXYZ(1.0, -0.5), PointXYZ(1.0, 0.0), PointXYZ(1.0, 0.5)]

    ranges = project_points_to_ranges(points, beam_count=9, range_min_m=0.1, range_max_m=8.0)

    finite = [value for value in ranges if math.isfinite(value)]
    assert len(finite) == 3
    assert min(finite) == 1.0
    assert max(finite) > min(finite)
    assert sum(1 for value in ranges if math.isfinite(value) and abs(value - 1.5) < 1e-6) == 0


def test_cloud_scan_projection_keeps_nearest_point_per_beam() -> None:
    ranges = project_points_to_ranges(
        [PointXYZ(2.0, 0.0), PointXYZ(1.0, 0.0)],
        beam_count=9,
        range_min_m=0.1,
        range_max_m=8.0,
    )

    center = len(ranges) // 2
    assert ranges[center] == 1.0


def test_cloud_scan_projection_uses_nan_for_no_hit() -> None:
    ranges = project_points_to_ranges([PointXYZ(20.0, 0.0)], beam_count=9, range_min_m=0.1, range_max_m=8.0)

    assert all(not math.isfinite(value) for value in ranges)
