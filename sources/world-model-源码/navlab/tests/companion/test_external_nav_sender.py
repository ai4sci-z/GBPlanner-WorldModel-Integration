from __future__ import annotations

import math
import time
from types import SimpleNamespace

from navlab.common.pose import quaternion_from_yaw
from navlab.real.companion.nodes.external_nav import (
    MavlinkExternalNavSender,
    _yaw_from_ros_quat_enu,
    rate_limit_xy,
    rate_limit_yaw,
    ros_enu_position_to_mavlink_local_frd,
    ros_enu_yaw_to_mavlink_local_frd,
)


def _pose_with_yaw(yaw_rad: float) -> SimpleNamespace:
    qx, qy, qz, qw = quaternion_from_yaw(yaw_rad)
    return SimpleNamespace(orientation=SimpleNamespace(x=qx, y=qy, z=qz, w=qw))


def _yaw_from_frd_quat(q: list[float]) -> float:
    w, x, y, z = q
    return math.atan2(2.0 * ((w * z) + (x * y)), 1.0 - (2.0 * ((y * y) + (z * z))))


def _roll_pitch_from_frd_quat(q: list[float]) -> tuple[float, float]:
    w, x, y, z = q
    roll = math.atan2(2.0 * ((w * x) + (y * z)), 1.0 - (2.0 * ((x * x) + (y * y))))
    pitch = math.asin(max(-1.0, min(1.0, 2.0 * ((w * y) - (z * x)))))
    return roll, pitch


def _sender_without_ros(max_yaw_rate_radps: float = 0.0) -> MavlinkExternalNavSender:
    sender = MavlinkExternalNavSender.__new__(MavlinkExternalNavSender)
    sender._use_fcu_roll_pitch = True
    sender._align_yaw_to_fcu = True
    sender._fcu_roll_rad = 0.0
    sender._fcu_pitch_rad = 0.0
    sender._fcu_yaw_rad = -0.5
    sender._fcu_rollspeed_radps = 0.0
    sender._fcu_pitchspeed_radps = 0.0
    sender._last_fcu_attitude_monotonic = time.monotonic()
    sender._yaw_alignment_offset_rad = None
    sender._max_yaw_rate_radps = max_yaw_rate_radps
    sender._last_sent_yaw_rad = None
    sender._last_sent_yaw_monotonic = 0.0
    return sender


def test_odometry_quaternion_aligns_initial_slam_yaw_to_fcu_attitude() -> None:
    sender = _sender_without_ros()

    first = sender._odometry_quaternion(_pose_with_yaw(0.1))
    second = sender._odometry_quaternion(_pose_with_yaw(0.2))

    assert math.isclose(_yaw_from_frd_quat(first), -0.5, abs_tol=1e-6)
    assert sender._yaw_alignment_offset_rad is not None
    assert math.isclose(_yaw_from_frd_quat(second), -0.6, abs_tol=1e-6)


def test_odometry_quaternion_can_send_raw_slam_yaw_without_alignment() -> None:
    sender = _sender_without_ros()
    sender._align_yaw_to_fcu = False

    q = sender._odometry_quaternion(_pose_with_yaw(0.1))

    assert math.isclose(_yaw_from_frd_quat(q), (math.pi * 0.5) - 0.1, abs_tol=1e-6)
    assert sender._yaw_alignment_offset_rad is None
    assert math.isclose(_yaw_from_ros_quat_enu(_pose_with_yaw(0.1).orientation), 0.1, abs_tol=1e-6)
    assert math.isclose(ros_enu_yaw_to_mavlink_local_frd(0.1), (math.pi * 0.5) - 0.1, abs_tol=1e-6)


def test_ros_enu_position_maps_to_mavlink_local_frd_axes() -> None:
    assert ros_enu_position_to_mavlink_local_frd(x_enu_m=2.0, y_enu_m=3.0, z_enu_m=0.5) == (
        3.0,
        -2.0,
        -0.5,
    )


def test_ros_map_west_axis_projects_to_negative_local_east() -> None:
    assert ros_enu_position_to_mavlink_local_frd(x_enu_m=-0.5, y_enu_m=0.35, z_enu_m=0.5) == (
        0.35,
        0.5,
        -0.5,
    )


def test_odometry_quaternion_does_not_feed_fcu_roll_pitch_back_to_external_nav() -> None:
    sender = _sender_without_ros()
    sender._fcu_roll_rad = 0.4
    sender._fcu_pitch_rad = -0.3

    q = sender._odometry_quaternion(_pose_with_yaw(0.1))
    roll, pitch = _roll_pitch_from_frd_quat(q)

    assert math.isclose(roll, 0.0, abs_tol=1e-6)
    assert math.isclose(pitch, 0.0, abs_tol=1e-6)
    assert math.isclose(_yaw_from_frd_quat(q), -0.5, abs_tol=1e-6)


def test_rate_limit_xy_keeps_slam_horizontal_spikes_from_reaching_fcu() -> None:
    x_m, y_m = rate_limit_xy(
        target_x=1.0,
        target_y=0.0,
        last_x=0.0,
        last_y=0.0,
        dt_sec=0.1,
        max_speed_mps=0.2,
    )

    assert math.isclose(x_m, 0.02)
    assert math.isclose(y_m, 0.0)


def test_rate_limit_xy_can_be_disabled() -> None:
    assert rate_limit_xy(
        target_x=1.0,
        target_y=0.5,
        last_x=0.0,
        last_y=0.0,
        dt_sec=0.1,
        max_speed_mps=0.0,
    ) == (1.0, 0.5)


def test_rate_limit_yaw_keeps_slam_yaw_spikes_from_reaching_fcu() -> None:
    yaw = rate_limit_yaw(
        target_yaw_rad=1.5,
        last_yaw_rad=0.0,
        dt_sec=0.1,
        max_yaw_rate_radps=0.2,
    )

    assert math.isclose(yaw, 0.02)


def test_odometry_quaternion_rate_limits_aligned_slam_yaw() -> None:
    sender = _sender_without_ros(max_yaw_rate_radps=0.1)
    first = sender._odometry_quaternion(_pose_with_yaw(0.1), now_monotonic=10.0)
    second = sender._odometry_quaternion(_pose_with_yaw(1.6), now_monotonic=10.5)

    assert math.isclose(_yaw_from_frd_quat(first), -0.5, abs_tol=1e-6)
    assert math.isclose(_yaw_from_frd_quat(second), -0.55, abs_tol=1e-6)


def test_roll_pitch_speeds_are_zero_when_fcu_roll_pitch_is_used() -> None:
    sender = _sender_without_ros()
    sender._fcu_rollspeed_radps = 0.12
    sender._fcu_pitchspeed_radps = -0.34
    twist = SimpleNamespace(angular=SimpleNamespace(x=9.5, y=6.1))

    rollspeed, pitchspeed = sender._roll_pitch_speeds(twist, now_monotonic=time.monotonic())

    assert math.isclose(rollspeed, 0.0)
    assert math.isclose(pitchspeed, 0.0)


def test_roll_pitch_speeds_fall_back_to_odom_when_fcu_attitude_is_stale() -> None:
    sender = _sender_without_ros()
    sender._last_fcu_attitude_monotonic = 1.0
    twist = SimpleNamespace(angular=SimpleNamespace(x=9.5, y=6.1))

    rollspeed, pitchspeed = sender._roll_pitch_speeds(twist, now_monotonic=3.0)

    assert math.isclose(rollspeed, 9.5)
    assert math.isclose(pitchspeed, -6.1)
