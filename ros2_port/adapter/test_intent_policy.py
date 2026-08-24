import math

from intent_policy import (
    ACTIVE_TRAJECTORY_MAX_AGE_S,
    effective_fcu_yaw_age,
    map_velocity_to_body_frd,
    quaternion_yaw,
    valid_fcu_yaw,
    valid_odom_frames,
)


def test_one_shot_path_lifetime_covers_the_acceptance_window():
    assert ACTIVE_TRAJECTORY_MAX_AGE_S > 90.0


def test_fcu_yaw_normalizes_quaternion_and_rejects_invalid_input():
    yaw = quaternion_yaw(0.0, 0.0, math.sqrt(2.0), math.sqrt(2.0))
    assert math.isclose(math.degrees(yaw), 90.0, abs_tol=1e-6)
    assert quaternion_yaw(0.0, 0.0, 0.0, 0.0) is None
    assert quaternion_yaw(0.0, 0.0, math.nan, 1.0) is None


def test_fcu_yaw_must_be_fresh_for_motion():
    assert valid_fcu_yaw(math.radians(89.95), 0.55) is True
    assert valid_fcu_yaw(math.radians(89.95), 2.01) is False
    assert valid_fcu_yaw(None, 0.1) is False


def test_fcu_yaw_age_includes_upstream_attitude_and_status_age():
    age = effective_fcu_yaw_age(
        pose_age_s=0.05,
        reported_attitude_age_s=0.40,
        status_age_s=0.25,
    )
    assert math.isclose(age, 0.65)
    assert valid_fcu_yaw(math.radians(89.95), age) is True
    # LOCAL_POSITION_NED may keep refreshing the pose while ATTITUDE is stale.
    stale_age = effective_fcu_yaw_age(0.05, 2.10, 0.10)
    assert valid_fcu_yaw(math.radians(89.95), stale_age) is False
    assert math.isinf(effective_fcu_yaw_age(0.05, None, 0.10))


def test_body_mapping_requires_exact_map_to_base_link_odometry_frames():
    assert valid_odom_frames("map", "base_link") is True
    assert valid_odom_frames("odom", "base_link") is False
    assert valid_odom_frames("map", "base_footprint") is False
    assert valid_odom_frames("map", "") is False


def test_map_velocity_uses_ros_body_left_but_emits_frd_right():
    assert map_velocity_to_body_frd(1.0, 0.0, 0.0) == (1.0, 0.0)
    assert map_velocity_to_body_frd(0.0, 1.0, 0.0) == (0.0, -1.0)
    forward, right = map_velocity_to_body_frd(0.0, 1.0, math.pi / 2.0)
    assert math.isclose(forward, 1.0, abs_tol=1e-12)
    assert math.isclose(right, 0.0, abs_tol=1e-12)


def test_body_mapping_matches_fifth_m5_run_axis_swap_evidence():
    # Both M5 bags have map yaw ~=0 deg and FCU NED yaw ~=90 deg. A map +x
    # command must be body-forward; the controller rotates it to NED +y,
    # matching the observed numeric relation NED=(map_y,map_x).
    forward, right = map_velocity_to_body_frd(
        math.cos(math.radians(5.0)),
        math.sin(math.radians(5.0)),
        math.radians(0.2),
    )
    assert math.isclose(math.degrees(math.atan2(right, forward)), -4.8, abs_tol=0.01)
    fcu_yaw = math.radians(89.95)
    north = math.cos(fcu_yaw) * forward - math.sin(fcu_yaw) * right
    east = math.sin(fcu_yaw) * forward + math.cos(fcu_yaw) * right
    assert math.isclose(north, math.sin(math.radians(5.0)), abs_tol=0.004)
    assert math.isclose(east, math.cos(math.radians(5.0)), abs_tol=0.004)
    assert map_velocity_to_body_frd(1.0, 0.0, math.nan) is None
