from __future__ import annotations

from math import isclose

from navlab.common.companion.mission.evidence.summary import (
    build_hover_status_payload,
    build_landing_summary,
    mission_phase_summary_fields,
    summarize_post_airborne_nav_loss,
)
from navlab.common.companion.mission.fsm import MissionPhaseRecorder
from navlab.common.companion.mission.stages.hover import HoverInputs
from navlab.common.companion.mission.stages.landing import (
    LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER,
    LANDING_POLICY_GUIDED_DESCENT,
)


def _snapshot():
    recorder = MissionPhaseRecorder(started_at_monotonic=10.0)
    recorder.transition(now_monotonic=12.0, state="S6 hover_hold", reason="holding", guard="hover_hold")
    return recorder.snapshot(now_monotonic=13.5)


def test_mission_phase_summary_fields_keep_legacy_public_names() -> None:
    fields = mission_phase_summary_fields(_snapshot())

    assert fields["mission_phase_state"] == "S6 hover_hold"
    assert fields["mission_phase_state_entered_at_sec"] == 2.0
    assert fields["mission_phase_last_transition_reason"] == "holding"
    assert fields["mission_phase_blocker"] is None
    assert fields["mission_phase_history"][-1]["guard"] == "hover_hold"


def test_hover_status_payload_preserves_position_and_prefix_evidence() -> None:
    inputs = HoverInputs(
        external_nav_ready=True,
        mavlink_external_nav_ready=True,
        fcu_local_position_ready=True,
        imu_ready=True,
        slam_quality_good=True,
        slam_quality="good",
        ready_elapsed_sec=2.0,
        current_yaw_rad=0.2,
        expected_mode_seen=True,
        armed_seen=True,
        airborne_seen=True,
        takeoff_ack_ok=True,
        airborne_elapsed_sec=1.0,
        hover_elapsed_sec=3.0,
        current_x=1.25,
        current_y=-0.5,
        current_z_ned=-0.45,
        current_height_m=0.45,
        external_nav_height_m=0.44,
        rangefinder_relative_height_m=0.43,
        target_z_ned=-0.45,
        slam_quality_loss_duration_sec=0.0,
        external_nav_loss_duration_sec=0.0,
        mavlink_external_nav_loss_duration_sec=0.0,
        fcu_local_position_loss_duration_sec=0.0,
    )

    payload = build_hover_status_payload(
        phase="hover_hold",
        reason="holding",
        fsm_snapshot=_snapshot(),
        prefix_pipeline={"active_stage": "takeoff", "terminal": False},
        inputs=inputs,
        slam_quality_reason="ok",
        setpoints_sent_count=42,
        local_position_count=10,
        rangefinder_count=9,
        current_yaw_rad=0.2,
        hold_x=1.0,
        hold_y=-0.25,
        hold_yaw_rad=0.1,
        hover_health={"phase": "hover_health_hold", "band": "green", "sim_auto_continue_allowed": True},
    )

    assert payload["phase"] == "hover_hold"
    assert payload["prefix_pipeline"]["active_stage"] == "takeoff"
    assert payload["position"]["x"] == 1.25
    assert payload["position"]["hold_yaw_rad"] == 0.1
    assert payload["mission_phase_state"] == "S6 hover_hold"
    assert payload["hover_health"]["phase"] == "hover_health_hold"
    assert payload["hover_health"]["band"] == "green"
    assert payload["hover_health_phase"] == "hover_health_hold"
    assert payload["mission_phase_substate"] == "hover_health_hold"


def test_summarize_post_airborne_nav_loss_reports_window_evidence() -> None:
    summary = summarize_post_airborne_nav_loss(
        [
            {
                "phase": "hover_settle",
                "airborne_seen": True,
                "airborne_elapsed_sec": 6.1,
                "external_nav_ready": False,
                "slam_quality": "stale",
                "slam_quality_good": False,
                "slam_quality_reason": "odom_stale",
                "slam_quality_loss_duration_sec": 5.45,
                "external_nav_loss_duration_sec": 5.45,
                "mavlink_external_nav_ready": False,
                "mavlink_external_nav_loss_duration_sec": 4.7,
                "fcu_local_position_ready": True,
            },
            {
                "phase": "abort",
                "reason": "slam_quality_lost_after_airborne",
                "airborne_seen": True,
                "airborne_elapsed_sec": 8.05,
                "external_nav_ready": False,
                "slam_quality": "stale",
                "slam_quality_good": False,
                "slam_quality_reason": "odom_stale",
                "slam_quality_loss_duration_sec": 7.4,
                "external_nav_loss_duration_sec": 7.4,
                "mavlink_external_nav_ready": False,
                "mavlink_external_nav_loss_duration_sec": 6.65,
                "fcu_local_position_ready": True,
            },
        ]
    )

    assert summary["slam_quality"]["seen"] is True
    assert summary["slam_quality"]["max_duration_sec"] == 7.4
    assert summary["slam_quality"]["last_reason"] == "odom_stale"
    assert summary["slam_quality"]["last_bad_phase"] == "abort"
    assert isclose(summary["slam_quality"]["inferred_started_airborne_elapsed_sec"], 0.65)
    assert summary["external_nav"]["seen"] is True
    assert summary["mavlink_external_nav"]["max_duration_sec"] == 6.65
    assert summary["fcu_local_position"]["seen"] is False


def test_ap_land_summary_treats_descent_profile_as_audit_only() -> None:
    summary = build_landing_summary(
        fsm_snapshot=_snapshot(),
        policy=LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER,
        state="landing_complete",
        started=True,
        frozen_hover_evidence={"ok": True},
        land_command_sent=True,
        land_command_sent_time_sec=5.0,
        land_command_accepted=True,
        mode_before_land="GUIDED",
        mode_after_land="LAND",
        land_mode_seen=True,
        land_mode_seen_elapsed_sec=0.4,
        landed_state_timeline=[],
        landing_duration_sec=4.0,
        touchdown_confirmed=True,
        touchdown_confirmed_time_sec=8.0,
        disarmed=True,
        motors_safe=True,
        require_disarm=True,
        require_motors_safe=True,
        touchdown_confirm_sec=0.5,
        force_disarm_grace_sec=3.0,
        force_disarm_after_touchdown=False,
        force_disarm_used=False,
        landing_setpoint_lookahead_sec=0.2,
        landing_slowdown_altitude_m=0.6,
        landing_near_ground_descent_rate_mps=0.01,
        last_range_m=0.0,
        last_rangefinder_relative_height_m=0.0,
        last_z_ned=0.0,
        last_vz_mps=1.2,
        landed_state="ON_GROUND",
        fcu_land_params={},
        descent_profile={"ok": False, "speed_ok": False, "bounce_ok": False},
        landing_blockers=[],
    )

    assert summary["ok"] is True
    assert summary["descent_profile_enforced"] is False
    assert summary["blockers"] == []


def test_guided_descent_summary_enforces_descent_profile() -> None:
    summary = build_landing_summary(
        fsm_snapshot=_snapshot(),
        policy=LANDING_POLICY_GUIDED_DESCENT,
        state="landing_complete",
        started=True,
        frozen_hover_evidence={"ok": True},
        land_command_sent=True,
        land_command_sent_time_sec=5.0,
        land_command_accepted=True,
        mode_before_land="GUIDED",
        mode_after_land="GUIDED",
        land_mode_seen=False,
        land_mode_seen_elapsed_sec=None,
        landed_state_timeline=[],
        landing_duration_sec=4.0,
        touchdown_confirmed=True,
        touchdown_confirmed_time_sec=8.0,
        disarmed=True,
        motors_safe=True,
        require_disarm=True,
        require_motors_safe=True,
        touchdown_confirm_sec=0.5,
        force_disarm_grace_sec=3.0,
        force_disarm_after_touchdown=False,
        force_disarm_used=False,
        landing_setpoint_lookahead_sec=0.2,
        landing_slowdown_altitude_m=0.6,
        landing_near_ground_descent_rate_mps=0.01,
        last_range_m=0.0,
        last_rangefinder_relative_height_m=0.0,
        last_z_ned=0.0,
        last_vz_mps=1.2,
        landed_state="ON_GROUND",
        fcu_land_params={},
        descent_profile={"ok": False, "speed_ok": False, "bounce_ok": True},
        landing_blockers=[],
    )

    assert summary["ok"] is False
    assert summary["descent_profile_enforced"] is True
    assert "landing_descent_too_fast" in summary["blockers"]
