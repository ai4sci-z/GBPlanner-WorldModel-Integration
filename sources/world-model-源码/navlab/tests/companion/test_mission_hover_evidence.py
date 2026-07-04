from __future__ import annotations

from navlab.common.companion.mission.context import MissionContext
from navlab.common.companion.mission.evidence.hover import HoverEvidenceRecorder, summarize_hover_drift


def _append_sample(recorder: HoverEvidenceRecorder, *, now: float, x: float, y: float, z: float = -0.45) -> None:
    recorder.append_sample(
        now_monotonic=now,
        x_m=x,
        y_m=y,
        z_ned_m=z,
        elapsed_sec=now - 10.0,
        fcu_local_z_ned=z,
        fcu_local_height_m=-z,
        external_nav_height_m=-z + 0.01,
        rangefinder_range_m=0.55,
        rangefinder_relative_height_m=0.45,
    )


def test_hover_evidence_recorder_tracks_segments_and_samples() -> None:
    recorder = HoverEvidenceRecorder()

    assert recorder.update_phase(phase="hover_hold", now_monotonic=10.0, terminal=False) is True
    _append_sample(recorder, now=10.0, x=0.0, y=0.0)
    _append_sample(recorder, now=12.0, x=0.1, y=0.0)
    assert recorder.segment_count == 1

    window = recorder.selected_window()

    assert len(window.pose_samples) == 2
    assert len(window.altitude_samples) == 2
    assert window.altitude_samples[-1]["external_nav_height_m"] == 0.46
    assert summarize_hover_drift(window.pose_samples).duration_sec == 2.0


def test_hover_evidence_recorder_keeps_longest_segment() -> None:
    recorder = HoverEvidenceRecorder()

    recorder.update_phase(phase="hover_hold", now_monotonic=10.0, terminal=False)
    _append_sample(recorder, now=10.0, x=0.0, y=0.0)
    _append_sample(recorder, now=11.0, x=0.1, y=0.0)
    recorder.update_phase(phase="hover_settle", now_monotonic=12.0, terminal=False)

    recorder.update_phase(phase="hover_hold", now_monotonic=20.0, terminal=False)
    _append_sample(recorder, now=20.0, x=0.0, y=0.0)
    _append_sample(recorder, now=24.0, x=0.2, y=0.0)

    window = recorder.selected_window()

    assert recorder.segment_count == 2
    assert summarize_hover_drift(window.pose_samples).duration_sec == 4.0


def test_hover_evidence_recorder_remembers_active_segment_on_exit() -> None:
    recorder = HoverEvidenceRecorder()

    recorder.update_phase(phase="hover_hold", now_monotonic=10.0, terminal=False)
    _append_sample(recorder, now=10.0, x=0.0, y=0.0)
    _append_sample(recorder, now=13.0, x=0.3, y=0.0)
    recorder.update_phase(phase="hover_settle", now_monotonic=13.1, terminal=False)

    window = recorder.selected_window()

    assert recorder.active_started_at is None
    assert summarize_hover_drift(window.pose_samples).duration_sec == 3.0


def test_hover_evidence_recorder_records_samples_from_context() -> None:
    recorder = HoverEvidenceRecorder()
    ctx = MissionContext()
    ctx.clock.started_at_monotonic = 10.0
    ctx.clock.now_monotonic = 12.0
    ctx.state.pose.x_m = 1.0
    ctx.state.pose.y_m = 2.0
    ctx.state.pose.z_ned_m = -0.4
    ctx.state.pose.fcu_local_height_m = 0.4
    ctx.state.pose.external_nav_height_m = 0.41
    ctx.state.pose.rangefinder_range_m = 0.5
    ctx.state.pose.rangefinder_relative_height_m = 0.4

    assert recorder.record_context(ctx, phase="hover_hold", terminal=False) is True

    window = recorder.selected_window()
    assert window.pose_samples == [(12.0, 1.0, 2.0, -0.4)]
    assert window.altitude_samples[0]["elapsed_sec"] == 2.0
    assert window.altitude_samples[0]["fcu_local_height_m"] == 0.4


def test_hover_evidence_recorder_evaluates_completion_and_frozen_evidence() -> None:
    recorder = HoverEvidenceRecorder()

    recorder.update_phase(phase="hover_hold", now_monotonic=10.0, terminal=False)
    _append_sample(recorder, now=10.0, x=1.0, y=2.0, z=-0.5)
    _append_sample(recorder, now=12.0, x=1.02, y=2.01, z=-0.51)

    evaluation = recorder.evaluate_completion(
        target_alt_m=0.5,
        altitude_tolerance_m=0.1,
        hold_sec=2.0,
        duration_tolerance_sec=0.25,
        max_horizontal_drift_m=0.1,
        max_altitude_drift_m=0.1,
        local_position_count=3,
        crash_detected=False,
    )
    frozen = evaluation.frozen_hover_evidence(takeoff_ack_ok=True, crash_detected=False)

    assert evaluation.ok is True
    assert evaluation.reason == "hover_complete"
    assert frozen["hover_body_ok"] is True
    assert frozen["hover_drift"]["sample_count"] == 2
    assert frozen["takeoff_ack_ok"] is True


def test_hover_completion_rejects_large_span_even_when_endpoint_drift_is_small() -> None:
    recorder = HoverEvidenceRecorder()

    recorder.update_phase(phase="hover_hold", now_monotonic=10.0, terminal=False)
    _append_sample(recorder, now=10.0, x=0.0, y=0.0)
    _append_sample(recorder, now=11.0, x=0.2, y=0.0)
    _append_sample(recorder, now=12.0, x=0.0, y=0.0)

    evaluation = recorder.evaluate_completion(
        target_alt_m=0.45,
        altitude_tolerance_m=0.1,
        hold_sec=2.0,
        duration_tolerance_sec=0.25,
        max_horizontal_drift_m=0.1,
        max_altitude_drift_m=0.1,
        local_position_count=3,
        crash_detected=False,
    )

    assert evaluation.ok is False
    assert evaluation.reason == "hover_span_unstable"
    assert evaluation.drift.horizontal_drift_m == 0.0
    assert evaluation.acceptance["horizontal_drift_ok"] is True
    assert evaluation.acceptance["horizontal_span_ok"] is False


def test_hover_completion_allows_target_exceed_below_hard_cap_as_yellow() -> None:
    recorder = HoverEvidenceRecorder()

    recorder.update_phase(phase="hover_hold", now_monotonic=10.0, terminal=False)
    _append_sample(recorder, now=10.0, x=0.0, y=0.0)
    _append_sample(recorder, now=11.0, x=0.118, y=0.0)
    _append_sample(recorder, now=12.0, x=0.0, y=0.0)

    evaluation = recorder.evaluate_completion(
        target_alt_m=0.45,
        altitude_tolerance_m=0.1,
        hold_sec=2.0,
        duration_tolerance_sec=0.25,
        max_horizontal_drift_m=0.1,
        hover_span_target_m=0.1,
        hover_span_hard_cap_m=0.15,
        max_altitude_drift_m=0.1,
        local_position_count=3,
        crash_detected=False,
    )

    assert evaluation.ok is True
    assert evaluation.reason == "hover_complete"
    assert evaluation.acceptance["horizontal_span_ok"] is True
    assert evaluation.acceptance["horizontal_span_target_ok"] is False
    assert evaluation.acceptance["horizontal_span_tier"] == "yellow"


def test_hover_completion_rejects_external_nav_loss_after_airborne() -> None:
    recorder = HoverEvidenceRecorder()

    recorder.update_phase(phase="hover_hold", now_monotonic=10.0, terminal=False)
    _append_sample(recorder, now=10.0, x=0.0, y=0.0)
    _append_sample(recorder, now=12.0, x=0.02, y=0.0)

    evaluation = recorder.evaluate_completion(
        target_alt_m=0.45,
        altitude_tolerance_m=0.1,
        hold_sec=2.0,
        duration_tolerance_sec=0.25,
        max_horizontal_drift_m=0.1,
        max_altitude_drift_m=0.1,
        local_position_count=3,
        crash_detected=False,
        external_nav_loss_duration_sec=1.2,
    )

    assert evaluation.ok is False
    assert evaluation.reason == "external_nav_lost_after_airborne"
    assert evaluation.acceptance["no_external_nav_loss_after_airborne"] is False


def test_hover_completion_rejects_slam_quality_jump() -> None:
    recorder = HoverEvidenceRecorder()

    recorder.update_phase(phase="hover_hold", now_monotonic=10.0, terminal=False)
    _append_sample(recorder, now=10.0, x=0.0, y=0.0)
    _append_sample(recorder, now=12.0, x=0.02, y=0.0)

    evaluation = recorder.evaluate_completion(
        target_alt_m=0.45,
        altitude_tolerance_m=0.1,
        hold_sec=2.0,
        duration_tolerance_sec=0.25,
        max_horizontal_drift_m=0.1,
        max_altitude_drift_m=0.1,
        local_position_count=3,
        crash_detected=False,
        slam_quality="jump",
        slam_quality_reason="pose_or_yaw_jump",
    )
    frozen = evaluation.frozen_hover_evidence(takeoff_ack_ok=True, crash_detected=False)

    assert evaluation.ok is False
    assert evaluation.reason == "slam_quality_jump_in_hover_window"
    assert evaluation.acceptance["no_slam_quality_jump_in_hover_window"] is False
    assert frozen["hover_acceptance"]["slam_quality_reason"] == "pose_or_yaw_jump"
