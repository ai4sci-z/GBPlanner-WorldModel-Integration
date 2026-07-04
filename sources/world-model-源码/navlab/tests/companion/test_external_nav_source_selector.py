from math import isclose

from navlab.sim.companion.nodes.external_nav_source_selector import (
    SourceCandidate,
    _scan_reference_measurement_to_map_candidate,
    select_external_nav_source,
)


def _scan_status(**overrides):
    data = {
        "ready": True,
        "quality_good": True,
        "uses_gazebo_truth_input": False,
        "uses_known_map_input": False,
        "valid_beams": 384,
        "inlier_ratio": 0.62,
        "residual_rms_m": 0.12,
        "correction_eligibility": {
            "correction_allowed": True,
            "allowed_axes": ["x", "y"],
            "direction_cosine_min": 0.99,
            "x_sign_flips": 0,
            "y_sign_flips": 0,
        },
        "correction_intent": {
            "active": True,
            "blockers": [],
        },
    }
    data.update(overrides)
    return data


def test_stable_scan_reference_wins_when_cartographer_agrees():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.25, y_m=-0.21),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
    )

    assert decision.source == "scan_reference"
    assert decision.output_x_m == 0.27
    assert decision.output_y_m == -0.20
    assert decision.ready is True
    assert decision.publish is True
    assert decision.degraded is False
    assert decision.cartographer_scan_disagreement is False
    assert decision.uses_gazebo_truth_input is False
    assert decision.blockers == ()


def test_good_scan_reference_without_correction_axes_still_publishes_candidate():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.02, y_m=0.03),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan_status=_scan_status(
            correction_eligibility={
                "correction_allowed": False,
                "allowed_axes": [],
                "direction_cosine_min": None,
                "x_sign_flips": 0,
                "y_sign_flips": 0,
                "blockers": ["scan_reference_no_stable_axis"],
            }
        ),
        hover_phase="hover_settle",
        scan_status_age_ms=40.0,
    )

    assert decision.source == "scan_reference"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.blockers == ()


def test_scan_reference_measurement_to_map_candidate_applies_opposite_correction_intent():
    candidate = _scan_reference_measurement_to_map_candidate(
        SourceCandidate(
            frame_id="scan_reference",
            child_frame_id="base_link",
            x_m=0.20,
            y_m=-0.10,
            z_m=0.03,
            yaw_rad=0.05,
        ),
        SourceCandidate(
            frame_id="map",
            child_frame_id="base_link",
            x_m=2.0,
            y_m=3.0,
            z_m=0.10,
            yaw_rad=0.40,
        ),
    )

    assert candidate.frame_id == "map"
    assert candidate.child_frame_id == "base_link"
    assert isclose(candidate.x_m, 1.80)
    assert isclose(candidate.y_m, 3.10)
    assert isclose(candidate.z_m, 0.07)
    assert isclose(candidate.yaw_rad, 0.35)


def test_scan_reference_measurement_yaw_is_anchored_before_map_candidate_output():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.02, y_m=0.03, yaw_rad=3.1),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.01, y_m=0.02, yaw_rad=0.05),
        scan_status=_scan_status(
            correction_eligibility={
                "correction_allowed": False,
                "allowed_axes": [],
                "direction_cosine_min": None,
                "x_sign_flips": 0,
                "y_sign_flips": 0,
                "blockers": ["scan_reference_no_stable_axis"],
            }
        ),
        hover_phase="hover_settle",
        scan_status_age_ms=40.0,
        scan_reference_anchor=SourceCandidate(
            frame_id="map",
            child_frame_id="base_link",
            x_m=0.0,
            y_m=0.0,
            yaw_rad=0.40,
        ),
        last_accepted_output=SourceCandidate(
            frame_id="map",
            child_frame_id="base_link",
            x_m=0.0,
            y_m=0.0,
            yaw_rad=0.40,
        ),
    )

    assert decision.source == "scan_reference"
    assert isclose(decision.output_yaw_rad, 0.35)
    assert decision.reject_reason is None
    assert decision.publish is True


def test_scan_reference_measurement_is_anchored_before_map_candidate_output():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=2.03, y_m=3.04, yaw_rad=0.4),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.02, y_m=0.03),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        scan_reference_anchor=SourceCandidate(
            frame_id="map",
            child_frame_id="base_link",
            x_m=2.0,
            y_m=3.0,
            yaw_rad=0.4,
        ),
    )

    assert decision.source == "scan_reference"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.output_x_m == 1.98
    assert decision.output_y_m == 2.97
    assert decision.output_yaw_rad == 0.4
    assert decision.cartographer_scan_disagreement is False


def test_cartographer_scan_disagreement_rejects_without_continuity_anchor():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
    )

    assert decision.source == "not_ready"
    assert decision.ready is False
    assert decision.publish is False
    assert decision.reject_reason == "cartographer_scan_disagreement"
    assert "cartographer_scan_disagreement" in decision.blockers


def test_cartographer_scan_disagreement_allows_continuous_anchored_scan_candidate():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=1.4, y_m=-1.1, yaw_rad=0.2),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=-0.03, y_m=0.01),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        scan_reference_anchor=SourceCandidate(
            frame_id="map",
            child_frame_id="base_link",
            x_m=0.20,
            y_m=-0.10,
            yaw_rad=0.2,
        ),
        last_accepted_output=SourceCandidate(
            frame_id="map",
            child_frame_id="base_link",
            x_m=0.18,
            y_m=-0.09,
            yaw_rad=0.2,
        ),
        max_candidate_step_m=0.12,
    )

    assert decision.source == "scan_reference"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.cartographer_scan_disagreement is True
    assert decision.reject_reason is None
    assert decision.output_x_m == 0.23
    assert isclose(decision.output_y_m, -0.11)


def test_cartographer_scan_disagreement_holds_fresh_scan_reference():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.29, y_m=-0.22),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        last_good_scan_age_ms=120.0,
    )

    assert decision.source == "scan_reference_hold"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.degraded is True
    assert decision.reject_reason == "cartographer_scan_disagreement"
    assert decision.hold_reason == "cartographer_scan_disagreement"


def test_cartographer_scan_disagreement_uses_slam_continuity_during_hover_settle_after_hold_expires():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.04, y_m=0.03, yaw_rad=0.2),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.29, y_m=-0.22),
        scan_status=_scan_status(),
        hover_phase="hover_settle",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        last_good_scan_age_ms=900.0,
        last_accepted_output=SourceCandidate(
            frame_id="map",
            child_frame_id="base_link",
            x_m=0.03,
            y_m=0.02,
            yaw_rad=0.19,
        ),
    )

    assert decision.source == "slam_settle"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.degraded is True
    assert decision.reject_reason is None
    assert decision.output_x_m == 0.04
    assert decision.output_y_m == 0.03
    assert decision.hold_reason == "hover_settle_slam_continuity_candidate_step_jump"
    assert "cartographer_scan_disagreement" in decision.blockers
    assert "candidate_step_jump" in decision.blockers


def test_cartographer_scan_disagreement_after_hold_expires_rejects_large_candidate_step():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.04, y_m=0.03),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.80, y_m=-0.22),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        last_good_scan_age_ms=900.0,
        last_accepted_output=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.03, y_m=0.02),
    )

    assert decision.source == "not_ready"
    assert decision.ready is False
    assert decision.publish is False
    assert decision.reject_reason == "candidate_step_jump"
    assert decision.cartographer_scan_disagreement is True


def test_small_candidate_reacquire_slews_without_exceeding_per_frame_gate():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.20, y_m=0.0, yaw_rad=0.50),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.20, y_m=0.0, yaw_rad=0.50),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        last_accepted_output=SourceCandidate(
            frame_id="map",
            child_frame_id="base_link",
            x_m=0.0,
            y_m=0.0,
            yaw_rad=0.0,
        ),
        max_candidate_step_m=0.12,
        max_candidate_yaw_step_rad=0.35,
        max_candidate_reacquire_step_m=0.35,
        max_candidate_reacquire_yaw_step_rad=0.75,
    )

    assert decision.source == "scan_reference_slew"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.degraded is True
    assert isclose(decision.output_x_m, 0.12)
    assert decision.output_y_m == 0.0
    assert isclose(decision.output_yaw_rad, 0.35)
    assert decision.reject_reason is None
    assert decision.rejected_step_m == 0.2
    assert decision.rejected_yaw_step_rad == 0.5


def test_hover_settle_slam_continuity_holds_last_accepted_output_on_large_step():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.35, y_m=0.0),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=-0.30, y_m=0.0),
        scan_status=_scan_status(),
        hover_phase="hover_settle",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.0, y_m=0.0),
        last_good_scan_age_ms=900.0,
        last_accepted_output=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.0, y_m=0.0),
    )

    assert decision.source == "hover_settle_hold"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.degraded is True
    assert decision.reject_reason is None
    assert decision.rejected_step_m == 0.35
    assert decision.output_x_m == 0.0
    assert decision.output_y_m == 0.0
    assert decision.hold_reason == "hover_settle_last_accepted_hold_candidate_step_jump"


def test_hover_settle_slam_continuity_can_seed_without_last_accepted_output():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.35, y_m=0.0),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=-0.30, y_m=0.0),
        scan_status=_scan_status(),
        hover_phase="hover_settle",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.0, y_m=0.0),
        last_good_scan_age_ms=900.0,
    )

    assert decision.source == "slam_settle"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.degraded is True


def test_quality_bad_fails_closed_to_not_ready_without_fresh_hold():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        scan_status=_scan_status(quality_good=False),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
    )

    assert decision.source == "not_ready"
    assert decision.ready is False
    assert decision.publish is False
    assert "scan_reference_quality_not_good" in decision.blockers


def test_stale_scan_status_fails_closed_to_not_ready():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=900.0,
    )

    assert decision.source == "not_ready"
    assert decision.ready is False
    assert decision.publish is False
    assert "scan_reference_status_stale" in decision.blockers


def test_scan_reference_horizontal_drift_high_does_not_cut_continuous_candidate():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.30, y_m=0.0),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.28, y_m=0.0),
        scan_status=_scan_status(horizontal_drift_m=0.28),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        max_scan_reference_drift_m=0.25,
        last_accepted_output=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.24, y_m=0.0),
    )

    assert decision.source == "scan_reference"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.degraded is True
    assert "scan_reference_horizontal_drift_high" in decision.blockers


def test_scan_reference_horizontal_drift_high_still_fails_closed_without_continuity_anchor():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.28, y_m=0.0),
        scan_status=_scan_status(horizontal_drift_m=0.28),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        max_scan_reference_drift_m=0.25,
    )

    assert decision.source == "not_ready"
    assert decision.ready is False
    assert decision.publish is False
    assert decision.reject_reason == "cartographer_scan_disagreement"
    assert "scan_reference_horizontal_drift_high" in decision.blockers
    assert "cartographer_scan_disagreement" in decision.blockers


def test_high_drift_candidate_holds_when_tracking_window_is_unstable():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.30, y_m=0.0, yaw_rad=0.4),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.31, y_m=0.0, yaw_rad=0.4),
        scan_status=_scan_status(
            horizontal_drift_m=0.31,
            correction_eligibility={
                "correction_allowed": False,
                "allowed_axes": [],
                "direction_cosine_min": None,
                "x_sign_flips": 0,
                "y_sign_flips": 0,
                "blockers": ["scan_reference_no_stable_axis"],
            },
        ),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        max_scan_reference_drift_m=0.25,
        last_good_scan=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.24, y_m=0.0, yaw_rad=0.4),
        last_good_scan_age_ms=120.0,
        last_accepted_output=SourceCandidate(
            frame_id="map", child_frame_id="base_link", x_m=0.24, y_m=0.0, yaw_rad=0.4
        ),
    )

    assert decision.source == "scan_reference_hold"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.degraded is True
    assert decision.reject_reason == "scan_reference_high_drift_tracking_unstable"
    assert "scan_reference_horizontal_drift_high" in decision.blockers
    assert "scan_reference_high_drift_tracking_not_allowed" in decision.blockers


def test_high_drift_candidate_fails_closed_after_tracking_hold_expires():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.30, y_m=0.0, yaw_rad=0.4),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.31, y_m=0.0, yaw_rad=0.4),
        scan_status=_scan_status(
            horizontal_drift_m=0.31,
            correction_eligibility={
                "correction_allowed": False,
                "allowed_axes": [],
                "direction_cosine_min": None,
                "x_sign_flips": 0,
                "y_sign_flips": 0,
                "blockers": ["scan_reference_no_stable_axis"],
            },
        ),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        max_scan_reference_drift_m=0.25,
        last_good_scan=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.24, y_m=0.0, yaw_rad=0.4),
        last_good_scan_age_ms=900.0,
        last_accepted_output=SourceCandidate(
            frame_id="map", child_frame_id="base_link", x_m=0.24, y_m=0.0, yaw_rad=0.4
        ),
    )

    assert decision.source == "not_ready"
    assert decision.ready is False
    assert decision.publish is False
    assert decision.reject_reason == "scan_reference_high_drift_tracking_unstable"
    assert "scan_reference_horizontal_drift_high" in decision.blockers
    assert "scan_reference_high_drift_tracking_axes_empty" in decision.blockers


def test_high_drift_candidate_requires_active_correction_intent():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.30, y_m=0.0, yaw_rad=0.4),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.31, y_m=0.0, yaw_rad=0.4),
        scan_status=_scan_status(
            horizontal_drift_m=0.31,
            correction_eligibility={
                "correction_allowed": True,
                "allowed_axes": ["x", "y"],
                "direction_cosine_min": 0.99,
                "x_sign_flips": 0,
                "y_sign_flips": 0,
            },
            correction_intent={
                "active": False,
                "blockers": ["scan_reference_correction_consecutive_window_short"],
            },
        ),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        max_scan_reference_drift_m=0.25,
        last_good_scan=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.24, y_m=0.0, yaw_rad=0.4),
        last_good_scan_age_ms=120.0,
        last_accepted_output=SourceCandidate(
            frame_id="map", child_frame_id="base_link", x_m=0.24, y_m=0.0, yaw_rad=0.4
        ),
    )

    assert decision.source == "scan_reference_hold"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.reject_reason == "scan_reference_high_drift_tracking_unstable"
    assert "scan_reference_high_drift_intent_not_active" in decision.blockers
    assert "scan_reference_high_drift_intent_has_blockers" in decision.blockers


def test_sign_flip_does_not_block_quality_candidate_by_itself():
    status = _scan_status(
        correction_eligibility={
            "correction_allowed": True,
            "allowed_axes": ["x", "y"],
            "direction_cosine_min": 0.99,
            "x_sign_flips": 1,
            "y_sign_flips": 0,
        }
    )
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.02, y_m=0.03),
        scan_status=status,
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
    )

    assert decision.source == "scan_reference"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.blockers == ()


def test_sign_flip_with_large_candidate_step_is_still_rejected():
    status = _scan_status(
        correction_eligibility={
            "correction_allowed": True,
            "allowed_axes": ["x", "y"],
            "direction_cosine_min": -0.5,
            "x_sign_flips": 1,
            "y_sign_flips": 0,
        }
    )
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=1.7, y_m=0.0),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=1.7, y_m=0.0),
        scan_status=status,
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        last_accepted_output=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.0, y_m=0.0),
    )

    assert decision.source == "not_ready"
    assert decision.ready is False
    assert decision.publish is False
    assert decision.reject_reason == "candidate_step_jump"
    assert decision.rejected_step_m == 1.7


def test_non_hover_phase_uses_explicit_slam_bootstrap_source():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        scan_status=_scan_status(),
        hover_phase="complete",
        scan_status_age_ms=40.0,
    )

    assert decision.source == "slam_bootstrap"
    assert decision.ready is True
    assert decision.publish is True
    assert "not_hover_correction_phase" in decision.blockers


def test_recent_good_scan_is_held_through_short_quality_drop():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.29, y_m=-0.22),
        scan_status=_scan_status(quality_good=False),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        last_good_scan_age_ms=120.0,
    )

    assert decision.source == "scan_reference_hold"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.degraded is True
    assert decision.output_x_m == 0.27
    assert decision.output_y_m == -0.20
    assert decision.hold_age_ms == 120.0
    assert decision.hold_reason == "last_good_scan_reference_within_ttl"
    assert "scan_reference_quality_not_good" in decision.blockers


def test_recent_good_scan_hold_expires_after_ttl():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.29, y_m=-0.22),
        scan_status=_scan_status(quality_good=False),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        last_good_scan_age_ms=900.0,
        max_hold_age_ms=750.0,
    )

    assert decision.source == "not_ready"
    assert decision.ready is False
    assert decision.publish is False


def test_recent_good_scan_hold_is_disabled_outside_hover_phase_for_bootstrap():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.29, y_m=-0.22),
        scan_status=_scan_status(quality_good=False),
        hover_phase="complete",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.27, y_m=-0.20),
        last_good_scan_age_ms=120.0,
    )

    assert decision.source == "slam_bootstrap"
    assert decision.ready is True
    assert decision.publish is True
    assert "not_hover_correction_phase" in decision.blockers


def test_scan_reference_missing_in_hover_is_not_ready():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=None,
        scan_status={},
        hover_phase="hover_hold",
        scan_status_age_ms=-1.0,
    )

    assert decision.source == "not_ready"
    assert decision.ready is False
    assert decision.publish is False
    assert decision.reject_reason == "scan_reference_odom_missing"


def test_scan_reference_missing_before_hover_uses_bootstrap():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.01, y_m=0.02),
        scan=None,
        scan_status={},
        hover_phase="wait_ready",
        scan_status_age_ms=-1.0,
    )

    assert decision.source == "slam_bootstrap"
    assert decision.ready is True
    assert decision.publish is True


def test_large_candidate_step_is_rejected_and_holds_last_good():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=1.7, y_m=0.0),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=1.7, y_m=0.0),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.0, y_m=0.0),
        last_good_scan_age_ms=100.0,
        last_accepted_output=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.0, y_m=0.0),
    )

    assert decision.source == "scan_reference_hold"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.reject_reason == "candidate_step_jump"
    assert decision.rejected_step_m == 1.7
    assert decision.output_x_m == 0.0
    assert decision.output_y_m == 0.0


def test_large_candidate_step_without_fresh_hold_is_not_ready():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=1.7, y_m=0.0),
        scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=1.7, y_m=0.0),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.0, y_m=0.0),
        last_good_scan_age_ms=900.0,
        last_accepted_output=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.0, y_m=0.0),
    )

    assert decision.source == "not_ready"
    assert decision.ready is False
    assert decision.publish is False
    assert decision.reject_reason == "candidate_step_jump"
    assert decision.rejected_step_m == 1.7


def test_large_candidate_yaw_is_rejected_and_holds_last_good():
    decision = select_external_nav_source(
        slam=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.02, y_m=0.0, yaw_rad=3.1),
        scan=SourceCandidate(
            frame_id="scan_reference",
            child_frame_id="base_link",
            x_m=0.02,
            y_m=0.0,
            yaw_rad=3.1,
        ),
        scan_status=_scan_status(),
        hover_phase="hover_hold",
        scan_status_age_ms=40.0,
        last_good_scan=SourceCandidate(frame_id="scan_reference", child_frame_id="base_link", x_m=0.0, y_m=0.0),
        last_good_scan_age_ms=100.0,
        last_accepted_output=SourceCandidate(frame_id="map", child_frame_id="base_link", x_m=0.0, y_m=0.0),
    )

    assert decision.source == "scan_reference_hold"
    assert decision.ready is True
    assert decision.publish is True
    assert decision.reject_reason == "candidate_yaw_jump"
    assert decision.rejected_yaw_step_rad == 3.1
