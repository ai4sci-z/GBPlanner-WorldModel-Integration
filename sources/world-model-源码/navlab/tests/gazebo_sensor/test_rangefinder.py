from __future__ import annotations

import math

from navlab.sim.gazebo_sensor.benewake_tfmini_serial import encode_tfmini_frame
from navlab.sim.gazebo_sensor.range_projection import select_down_range_m


def test_down_rangefinder_selects_nearest_valid_range() -> None:
    distance = select_down_range_m([math.inf, 4.0, 0.01, 1.2, 7.0], min_m=0.05, max_m=6.0)

    assert distance == 1.2


def test_down_rangefinder_ignores_invalid_ranges() -> None:
    distance = select_down_range_m([math.inf, math.nan, 0.01, 7.0], min_m=0.05, max_m=6.0)

    assert distance is None


def test_range_projection_does_not_export_mavlink_helpers() -> None:
    import navlab.sim.gazebo_sensor.range_projection as range_projection

    assert not hasattr(range_projection, "mavlink_constant")
    assert not hasattr(range_projection, "meters_to_centimeters")


def test_benewake_tfmini_frame_matches_ardupilot_sitl_format() -> None:
    frame = encode_tfmini_frame(1.23)

    assert frame[:2] == b"\x59\x59"
    assert frame[2] == 123
    assert frame[3] == 0
    assert frame[4:8] == b"\x01\x01\x07\x00"
    assert frame[8] == sum(frame[:8]) & 0xFF
