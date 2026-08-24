import math

from intent_policy import (
    ACTIVE_TRAJECTORY_MAX_AGE_S,
    estimate_alignment,
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
