import math

from intent_policy import (
    ACTIVE_TRAJECTORY_MAX_AGE_S,
    command_heading,
    effective_fcu_yaw_age,
    estimate_alignment,
    quaternion_yaw,
    valid_fcu_yaw,
)


def test_alignment_waits_for_a_measurable_baseline():
    assert estimate_alignment((0.0, 0.0), (0.0, 0.0), (0.09, 0.0), (0.0, 0.09)) is None


def test_alignment_updates_before_freeze_from_live_run_evidence():
    estimate = estimate_alignment(
        (0.0, 0.0), (0.0, 0.0), (0.100, -0.011), (0.0, 0.074)
    )
    assert estimate is not None
    theta, map_distance, ned_distance, frozen = estimate
    assert math.isclose(math.degrees(theta), 96.28, abs_tol=0.2)
    assert map_distance >= 0.100
    assert ned_distance == 0.074
    assert frozen is False


def test_alignment_freezes_only_on_the_long_baseline():
    theta, _, _, frozen = estimate_alignment(
        (0.0, 0.0), (0.0, 0.0), (0.35, 0.0), (0.0, 0.35)
    )
    assert math.isclose(math.degrees(theta), 90.0)
    assert frozen is True


def test_alignment_rejects_inconsistent_position_scale():
    assert estimate_alignment(
        (0.0, 0.0), (0.0, 0.0), (0.2, 0.0), (0.01, 0.0)
    ) is None


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


def test_command_heading_accounts_for_worldmodel_body_frame_contract():
    # Run 20260824T045937 MCAP: map->NED=-171.13 deg, FCU yaw=+89.95 deg.
    # The adapter must publish in body/FRD, so the correct command is +98.92 deg.
    heading = command_heading(math.radians(-171.13), math.radians(89.95))
    assert math.isclose(math.degrees(heading), 98.92, abs_tol=0.01)
    # WorldModel rotates body intent by FCU yaw before sending LOCAL_NED.
    reconstructed_ned = heading + math.radians(89.95)
    assert math.isclose(
        math.degrees((reconstructed_ned + math.pi) % (2.0 * math.pi) - math.pi),
        -171.13,
        abs_tol=0.01,
    )
