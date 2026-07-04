from __future__ import annotations

import json

from navlab.common.companion.mission.command_adapter import MissionCommandRuntime
from navlab.common.companion.mission.evidence.landing import (
    LandingEvidenceRecorder,
    build_landing_intent_payload,
    compute_landing_descent_setpoint,
)
from navlab.common.companion.mission.evidence.summary import MissionSummaryWriter


def test_command_runtime_owns_retry_deadlines_and_counts() -> None:
    runtime = MissionCommandRuntime()

    assert runtime.due("mode_command", 0.0) is True
    runtime.defer("mode_command", 2.5)
    assert runtime.due("mode_command", 2.0) is False
    assert runtime.due("mode_command", 2.5) is True

    runtime.count("arm")
    runtime.count("arm")
    runtime.count_setpoint()

    assert runtime.sent_counts["arm"] == 2
    assert runtime.sent_counts["local_position_yaw_setpoint"] == 1
    assert runtime.setpoints_sent == 1


def test_landing_evidence_recorder_owns_samples_touchdown_and_handoff() -> None:
    recorder = LandingEvidenceRecorder()

    recorder.start_with_hover_evidence(
        10.0,
        frozen_hover_evidence={
            "hover_body_ok": True,
            "hover_drift": {"duration_sec": 20.0},
        },
    )
    recorder.start_descent(11.0, current_z_ned=-0.4, fallback_z_ned=-0.5)
    recorder.append_descent_sample_from_pose(
        now_monotonic=11.0,
        current_range_m=0.45,
        ground_range_m=0.05,
        current_z_ned=-0.4,
        ground_z_ned=0.0,
        current_vz_mps=0.1,
    )
    recorder.append_descent_sample_from_pose(
        now_monotonic=12.0,
        current_range_m=0.25,
        ground_range_m=0.05,
        current_z_ned=-0.2,
        ground_z_ned=0.0,
        current_vz_mps=0.1,
    )
    first = recorder.update_touchdown_candidate(
        now_monotonic=12.0,
        raw_candidate=True,
        landed_state_on_ground=False,
        confirm_sec=0.5,
    )
    second = recorder.update_touchdown_candidate(
        now_monotonic=12.6,
        raw_candidate=True,
        landed_state_on_ground=False,
        confirm_sec=0.5,
    )
    recorder.mark_land_command_sent(now_monotonic=13.0, mode_before_land=4)
    recorder.mark_land_mode_seen(0.3)
    recorder.mark_mode_after_land(9)

    assert recorder.started_at_monotonic == 10.0
    assert recorder.state == "task_body_complete"
    assert recorder.frozen_hover_evidence["hover_body_ok"] is True
    assert recorder.start_z_ned == -0.4
    assert len(recorder.descent_samples) == 2
    assert recorder.descent_samples[-1][-1] == "rangefinder_relative_height"
    assert first is False
    assert second is True
    assert recorder.touchdown_confirmed is True
    assert recorder.land_command_sent is True
    assert recorder.mode_before_land == 4
    assert recorder.mode_after_land == 9
    assert recorder.land_mode_seen_elapsed_sec == 0.3


def test_landing_helpers_build_intent_and_descent_setpoint() -> None:
    payload = build_landing_intent_payload(
        source="controller",
        policy="guided_descent",
        reason="hover_complete",
        updated_ms=123,
    )
    setpoint = compute_landing_descent_setpoint(
        hold_x_m=1.0,
        hold_y_m=2.0,
        hold_yaw_rad=0.3,
        current_x_m=9.0,
        current_y_m=9.0,
        current_yaw_rad=0.9,
        start_z_ned=-0.5,
        fallback_start_z_ned=-0.4,
        ground_z_ned=0.0,
        descent_started_at_monotonic=10.0,
        now_monotonic=12.0,
        nominal_descent_rate_mps=0.1,
        rangefinder_relative_height_m=0.2,
        slowdown_altitude_m=0.5,
        near_ground_descent_rate_mps=0.02,
        current_z_ned=-0.45,
        setpoint_lookahead_sec=1.0,
    )

    assert payload == {
        "source": "controller",
        "kind": "land_in_place",
        "policy": "guided_descent",
        "reason": "hover_complete",
        "updated_ms": 123,
    }
    assert setpoint.x_m == 1.0
    assert setpoint.y_m == 2.0
    assert setpoint.yaw_rad == 0.3
    assert setpoint.effective_descent_rate_mps == 0.02
    assert setpoint.z_ned_m == -0.46


def test_mission_summary_writer_atomically_writes_json(tmp_path) -> None:
    path = tmp_path / "mission_summary.json"

    MissionSummaryWriter(path).write({"ok": True, "reason": "done"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True, "reason": "done"}
    assert not path.with_name(path.name + ".tmp").exists()


def test_hover_mission_summary_runtime_builds_final_summary(tmp_path) -> None:
    from navlab.common.companion.mission import MissionClock, MissionContext, MissionPhaseRecorder
    from navlab.common.companion.mission.command_adapter import MissionCommandRuntime
    from navlab.common.companion.mission.evidence.hover import HoverEvidenceRecorder
    from navlab.common.companion.mission.mavlink_protocol import mavlink
    from navlab.common.companion.mission.runtime_state import (
        MavlinkRuntimeCollections,
        MavlinkRuntimeState,
        MissionRuntimeAdapterConfig,
        MissionRuntimeStateAdapter,
    )
    from navlab.common.companion.mission.summary_runtime import HoverMissionSummaryConfig, HoverMissionSummaryRuntime

    config = HoverMissionSummaryConfig(
        summary_file=str(tmp_path / "mission_summary.json"),
        mode="GUIDED",
        mode_number=4,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.2,
        hover_hold_sec=1.0,
        hover_health_min_observation_sec=1.0,
        hover_health_stable_required_sec=0.5,
        hover_health_max_wait_sec=5.0,
        operator_confirm_required=False,
        operator_confirm_timeout_sec=3.0,
        hover_duration_tolerance_sec=0.25,
        max_horizontal_drift_m=0.5,
        hover_span_target_m=0.5,
        hover_span_hard_cap_m=0.5,
        max_altitude_drift_m=0.3,
        preflight_ready_sec=1.0,
        max_wait_ready_sec=10.0,
        hover_settle_sec=1.0,
        require_external_nav=True,
        require_imu_status=True,
        send_position_setpoints=True,
        landing_policy="ap_land_mode_after_hover",
        require_disarm=True,
        require_motors_safe=True,
        touchdown_confirm_sec=0.2,
        force_disarm_grace_sec=1.0,
        force_disarm_after_touchdown=False,
        landing_setpoint_lookahead_sec=1.0,
        landing_slowdown_altitude_m=0.6,
        landing_near_ground_descent_rate_mps=0.01,
        max_landing_descent_rate_mps=0.6,
        touchdown_altitude_m=0.12,
    )
    summary_runtime = HoverMissionSummaryRuntime(config)
    ctx = MissionContext(clock=MissionClock(started_at_monotonic=10.0, now_monotonic=13.0))
    ctx.state.hover.body_ok = True
    ctx.state.hover.phase_counts = {"hover_hold": 2, "complete": 1}
    ctx.state.hover.hold_x_m = 1.0
    ctx.state.hover.hold_y_m = 2.0
    ctx.state.hover.hold_yaw_rad = 0.3
    ctx.state.hover.health_started_at_monotonic = 12.0
    ctx.state.hover.health_green_since_monotonic = 12.5
    ctx.state.hover.health_phase = "sim_auto_continue"
    ctx.state.hover.health_band = "green"
    ctx.state.hover.health_reason = "hover_health_green_stable"
    ctx.state.hover.health_observed_sec = 4.0
    ctx.state.hover.health_stable_sec = 3.5
    hover_evidence = HoverEvidenceRecorder()
    ctx.state.pose.x_m = 1.0
    ctx.state.pose.y_m = 2.0
    ctx.state.pose.z_ned_m = -0.45
    ctx.state.pose.fcu_local_height_m = 0.45
    ctx.state.pose.external_nav_height_m = 0.45
    ctx.state.pose.rangefinder_range_m = 0.45
    ctx.state.pose.rangefinder_relative_height_m = 0.45
    hover_evidence.record_context(ctx, phase="hover_hold", terminal=False)
    ctx.clock.now_monotonic = 14.0
    ctx.state.pose.x_m = 1.01
    hover_evidence.record_context(ctx, phase="hover_hold", terminal=False)
    landing = LandingEvidenceRecorder()
    landing.start_with_hover_evidence(15.0, frozen_hover_evidence={"hover_body_ok": True})
    landing.state = "landing_complete"
    landing.touchdown_confirmed = True
    landing.touchdown_confirmed_time = 16.0
    landing.mark_land_command_sent(now_monotonic=15.0, mode_before_land=4)
    landing.mark_land_mode_seen(0.4)
    runtime = MavlinkRuntimeState(
        current_custom_mode=9,
        expected_mode_seen=True,
        armed_seen=False,
        guided_seen_ever=True,
        armed_seen_ever=True,
        airborne_seen=True,
        current_x=1.01,
        current_y=2.0,
        current_z=-0.45,
        ground_z_ned=0.0,
        current_range_m=0.45,
        ground_range_m=0.0,
        current_yaw_rad=0.3,
        gps_global_origin_seen=True,
        home_position_seen=True,
    )
    collections = MavlinkRuntimeCollections(
        accepted_command_ids={mavlink.MAV_CMD_NAV_TAKEOFF, mavlink.MAV_CMD_NAV_LAND},
    )
    command_runtime = MissionCommandRuntime(setpoints_sent=2, sent_counts={"takeoff": 1})
    adapter_config = MissionRuntimeAdapterConfig(1.0, True, True, False, 0.45)
    runtime_adapter = MissionRuntimeStateAdapter(started_at_monotonic=10.0)
    runtime_adapter.apply_external_nav_status('{"ready":true,"state":"healthy"}', now_monotonic=16.0)
    fsm = MissionPhaseRecorder(started_at_monotonic=10.0)
    fsm.transition(now_monotonic=16.0, state="S12 landing_complete", reason="landing_complete")

    summary = summary_runtime.build_final_summary(
        ok=True,
        reason="hover_complete",
        landing_ok=True,
        now_monotonic=16.0,
        started_at_monotonic=10.0,
        fsm_snapshot=fsm.snapshot(now_monotonic=16.0),
        prefix_pipeline={"terminal": True},
        status_history=[
            {
                "phase": "hover_hold",
                "hover_health": {
                    "phase": "sim_auto_continue",
                    "band": "green",
                    "reason": "hover_health_green_stable",
                    "blockers": [],
                },
            }
        ],
        ctx=ctx,
        runtime_adapter=runtime_adapter,
        runtime_adapter_config=adapter_config,
        runtime=runtime,
        command_runtime=command_runtime,
        collections=collections,
        hover_evidence=hover_evidence,
        landing_evidence=landing,
    )
    summary_runtime.write_final_summary(summary_file=config.summary_file, summary=summary)

    assert summary["ok"] is True
    assert summary["landing"]["ok"] is True
    assert summary["hover_drift"]["sample_count"] == 2
    assert summary["hover_drift"]["horizontal_span_ok"] is True
    assert summary["hover_drift"]["no_external_nav_loss_after_airborne"] is True
    assert summary["hover_drift"]["no_slam_quality_jump_in_hover_window"] is True
    assert summary["runtime_hover_health_final"]["schema"] == "navlab.runtime_hover_health.v1"
    assert summary["runtime_hover_health_final"]["phase"] == "sim_auto_continue"
    assert summary["runtime_hover_health_final"]["band"] == "green"
    assert summary["runtime_hover_health_final"]["sim_auto_continue_allowed"] is True
    assert summary["runtime_hover_health_final"]["mission_phase_substate"] == "sim_auto_continue"
    assert json.loads((tmp_path / "mission_summary.json").read_text())["landing"]["state"] == "landing_complete"


def test_hover_mission_summary_runtime_freezes_abort_runtime_health(tmp_path) -> None:
    from navlab.common.companion.mission import MissionContext
    from navlab.common.companion.mission.summary_runtime import HoverMissionSummaryConfig, HoverMissionSummaryRuntime

    config = HoverMissionSummaryConfig(
        summary_file=str(tmp_path / "mission_summary.json"),
        mode="GUIDED",
        mode_number=4,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.2,
        hover_hold_sec=1.0,
        hover_health_min_observation_sec=1.0,
        hover_health_stable_required_sec=0.5,
        hover_health_max_wait_sec=5.0,
        operator_confirm_required=True,
        operator_confirm_timeout_sec=3.0,
        hover_duration_tolerance_sec=0.25,
        max_horizontal_drift_m=0.5,
        hover_span_target_m=0.5,
        hover_span_hard_cap_m=0.5,
        max_altitude_drift_m=0.3,
        preflight_ready_sec=1.0,
        max_wait_ready_sec=10.0,
        hover_settle_sec=1.0,
        require_external_nav=True,
        require_imu_status=True,
        send_position_setpoints=True,
        landing_policy="ap_land_mode_after_hover",
        require_disarm=True,
        require_motors_safe=True,
        touchdown_confirm_sec=0.2,
        force_disarm_grace_sec=1.0,
        force_disarm_after_touchdown=False,
        landing_setpoint_lookahead_sec=1.0,
        landing_slowdown_altitude_m=0.6,
        landing_near_ground_descent_rate_mps=0.01,
        max_landing_descent_rate_mps=0.6,
        touchdown_altitude_m=0.12,
    )
    ctx = MissionContext()
    ctx.state.hover.health_phase = "hover_health_blocked"
    ctx.state.hover.health_band = "red"
    ctx.state.hover.health_reason = "external_nav_lost_after_airborne"
    ctx.state.hover.health_observed_sec = 6.0
    ctx.state.hover.health_stable_sec = 0.0
    ctx.state.hover.operator_confirm_allowed = False
    ctx.state.hover.operator_confirm_received = False

    health = HoverMissionSummaryRuntime(config)._runtime_hover_health_final(
        ctx,
        [
            {
                "hover_health": {
                    "phase": "hover_health_blocked",
                    "band": "red",
                    "reason": "external_nav_lost_after_airborne",
                    "blockers": ["external_nav_lost_after_airborne"],
                }
            }
        ],
    )

    assert health["schema"] == "navlab.runtime_hover_health.v1"
    assert health["phase"] == "hover_health_blocked"
    assert health["band"] == "red"
    assert health["blockers"] == ["external_nav_lost_after_airborne"]
    assert health["operator_confirm_required"] is True
    assert health["operator_confirm_allowed"] is False
    assert health["real_operator_confirm_allowed"] is False


def test_hover_mission_summary_runtime_requires_hover_span_for_drift_ok(tmp_path) -> None:
    from navlab.common.companion.mission.evidence.hover import HoverDriftSummary
    from navlab.common.companion.mission.summary_runtime import HoverMissionSummaryConfig, HoverMissionSummaryRuntime

    config = HoverMissionSummaryConfig(
        summary_file=str(tmp_path / "mission_summary.json"),
        mode="GUIDED",
        mode_number=4,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.2,
        hover_hold_sec=2.0,
        hover_health_min_observation_sec=1.0,
        hover_health_stable_required_sec=0.5,
        hover_health_max_wait_sec=5.0,
        operator_confirm_required=False,
        operator_confirm_timeout_sec=3.0,
        hover_duration_tolerance_sec=0.25,
        max_horizontal_drift_m=0.1,
        hover_span_target_m=0.1,
        hover_span_hard_cap_m=0.15,
        max_altitude_drift_m=0.3,
        preflight_ready_sec=1.0,
        max_wait_ready_sec=10.0,
        hover_settle_sec=1.0,
        require_external_nav=True,
        require_imu_status=True,
        send_position_setpoints=True,
        landing_policy="ap_land_mode_after_hover",
        require_disarm=True,
        require_motors_safe=True,
        touchdown_confirm_sec=0.2,
        force_disarm_grace_sec=1.0,
        force_disarm_after_touchdown=False,
        landing_setpoint_lookahead_sec=1.0,
        landing_slowdown_altitude_m=0.6,
        landing_near_ground_descent_rate_mps=0.01,
        max_landing_descent_rate_mps=0.6,
        touchdown_altitude_m=0.12,
    )
    drift = HoverDriftSummary(
        sample_count=3,
        duration_sec=2.0,
        horizontal_span_m=0.2,
        z_span_m=0.01,
        horizontal_drift_m=0.0,
        z_drift_m=0.0,
    )

    payload = HoverMissionSummaryRuntime(config)._hover_drift_payload(drift, "tight")

    assert payload["horizontal_drift_ok"] is True
    assert payload["horizontal_span_ok"] is False
    assert payload["ok"] is False


def test_hover_mission_summary_runtime_reports_slam_jump_evidence(tmp_path) -> None:
    from navlab.common.companion.mission.evidence.hover import HoverDriftSummary
    from navlab.common.companion.mission.summary_runtime import HoverMissionSummaryConfig, HoverMissionSummaryRuntime

    config = HoverMissionSummaryConfig(
        summary_file=str(tmp_path / "mission_summary.json"),
        mode="GUIDED",
        mode_number=4,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.2,
        hover_hold_sec=2.0,
        hover_health_min_observation_sec=1.0,
        hover_health_stable_required_sec=0.5,
        hover_health_max_wait_sec=5.0,
        operator_confirm_required=False,
        operator_confirm_timeout_sec=3.0,
        hover_duration_tolerance_sec=0.25,
        max_horizontal_drift_m=0.1,
        hover_span_target_m=0.1,
        hover_span_hard_cap_m=0.15,
        max_altitude_drift_m=0.3,
        preflight_ready_sec=1.0,
        max_wait_ready_sec=10.0,
        hover_settle_sec=1.0,
        require_external_nav=True,
        require_imu_status=True,
        send_position_setpoints=True,
        landing_policy="ap_land_mode_after_hover",
        require_disarm=True,
        require_motors_safe=True,
        touchdown_confirm_sec=0.2,
        force_disarm_grace_sec=1.0,
        force_disarm_after_touchdown=False,
        landing_setpoint_lookahead_sec=1.0,
        landing_slowdown_altitude_m=0.6,
        landing_near_ground_descent_rate_mps=0.01,
        max_landing_descent_rate_mps=0.6,
        touchdown_altitude_m=0.12,
    )
    drift = HoverDriftSummary(
        sample_count=3,
        duration_sec=2.0,
        horizontal_span_m=0.02,
        z_span_m=0.01,
        horizontal_drift_m=0.01,
        z_drift_m=0.0,
    )

    payload = HoverMissionSummaryRuntime(config)._hover_drift_payload(
        drift,
        "tight",
        slam_quality="jump",
        slam_quality_reason="pose_or_yaw_jump",
        external_nav_status_payload={
            "slam_quality_report": {
                "max_observed_position_jump_m": 1.7,
                "max_observed_yaw_jump_rad": 3.1,
            }
        },
    )

    assert payload["jump_seen_in_hover_window"] is True
    assert payload["no_slam_quality_jump_in_hover_window"] is False
    assert payload["max_observed_position_jump_m"] == 1.7
    assert payload["max_observed_yaw_jump_rad"] == 3.1
    assert payload["ok"] is False
