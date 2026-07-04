"""Summary payload builders shared by companion mission runtimes."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from navlab.common.companion.mission.fsm import MissionPhaseSnapshot
from navlab.common.companion.mission.stages.hover import HoverInputs
from navlab.common.companion.mission.stages.landing import (
    fcu_land_params_report,
    landing_acceptance_ok,
    landing_controller_for_state,
    landing_descent_profile_enforced,
    landing_handoff_confirmed,
    landing_policy_uses_ap_land_mode,
)


def _finite_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _status_signal_bad(row: Mapping[str, object], signal: str) -> bool:
    if signal == "slam_quality":
        if "slam_quality_good" in row:
            return row.get("slam_quality_good") is not True
        return row.get("slam_quality") != "good"
    return row.get(signal) is False


def summarize_post_airborne_nav_loss(status_history: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Summarize post-airborne nav loss windows from hover status history."""

    specs = {
        "slam_quality": ("slam_quality_loss_duration_sec", "slam_quality_reason"),
        "external_nav": ("external_nav_loss_duration_sec", "reason"),
        "mavlink_external_nav": ("mavlink_external_nav_loss_duration_sec", "reason"),
        "fcu_local_position": ("fcu_local_position_loss_duration_sec", "reason"),
    }
    summaries: dict[str, object] = {}
    for signal, (duration_key, reason_key) in specs.items():
        ready_signal = signal if signal == "slam_quality" else f"{signal}_ready"
        bad_rows = [
            row for row in status_history if row.get("airborne_seen") is True and _status_signal_bad(row, ready_signal)
        ]
        if not bad_rows:
            summaries[signal] = {"seen": False, "active": False, "max_duration_sec": 0.0}
            continue
        max_duration = max((_finite_float(row.get(duration_key)) or 0.0 for row in bad_rows), default=0.0)
        first = bad_rows[0]
        last = bad_rows[-1]
        last_airborne_elapsed = _finite_float(last.get("airborne_elapsed_sec"))
        inferred_started = None
        if last_airborne_elapsed is not None:
            inferred_started = max(0.0, last_airborne_elapsed - max_duration)
        summaries[signal] = {
            "seen": True,
            "active": _status_signal_bad(last, ready_signal),
            "max_duration_sec": max_duration,
            "first_bad_phase": first.get("phase"),
            "last_bad_phase": last.get("phase"),
            "first_bad_airborne_elapsed_sec": _finite_float(first.get("airborne_elapsed_sec")),
            "last_bad_airborne_elapsed_sec": last_airborne_elapsed,
            "inferred_started_airborne_elapsed_sec": inferred_started,
            "last_reason": last.get(reason_key),
        }
    return summaries


def mission_phase_summary_fields(snapshot: MissionPhaseSnapshot) -> dict[str, object]:
    """Return the legacy mission FSM summary field set."""

    return {
        "mission_phase_state": snapshot.state,
        "mission_phase_state_entered_at_sec": snapshot.state_entered_at_sec,
        "mission_phase_last_transition_reason": snapshot.last_transition_reason,
        "mission_phase_blocker": snapshot.blocker,
        "mission_phase_history": [entry.to_dict() for entry in snapshot.history],
    }


def build_hover_status_payload(
    *,
    phase: str,
    reason: str,
    fsm_snapshot: MissionPhaseSnapshot,
    prefix_pipeline: Mapping[str, object],
    inputs: HoverInputs,
    slam_quality_reason: str,
    setpoints_sent_count: int,
    local_position_count: int,
    rangefinder_count: int,
    current_yaw_rad: float | None,
    hold_x: float | None,
    hold_y: float | None,
    hold_yaw_rad: float | None,
    hover_health: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the `/navlab/hover/status` JSON-compatible payload."""

    payload = {
        "phase": phase,
        "reason": reason,
        **mission_phase_summary_fields(fsm_snapshot),
        "prefix_pipeline": dict(prefix_pipeline),
        "external_nav_ready": inputs.external_nav_ready,
        "slam_quality": inputs.slam_quality,
        "slam_quality_good": inputs.slam_quality_good,
        "slam_quality_reason": slam_quality_reason,
        "slam_quality_loss_duration_sec": inputs.slam_quality_loss_duration_sec,
        "external_nav_loss_duration_sec": inputs.external_nav_loss_duration_sec,
        "mavlink_external_nav_ready": inputs.mavlink_external_nav_ready,
        "mavlink_external_nav_loss_duration_sec": inputs.mavlink_external_nav_loss_duration_sec,
        "fcu_local_position_ready": inputs.fcu_local_position_ready,
        "fcu_local_position_loss_duration_sec": inputs.fcu_local_position_loss_duration_sec,
        "imu_ready": inputs.imu_ready,
        "ready_elapsed_sec": inputs.ready_elapsed_sec,
        "expected_mode_seen": inputs.expected_mode_seen,
        "armed_seen": inputs.armed_seen,
        "airborne_seen": inputs.airborne_seen,
        "takeoff_ack_ok": inputs.takeoff_ack_ok,
        "airborne_elapsed_sec": inputs.airborne_elapsed_sec,
        "hover_elapsed_sec": inputs.hover_elapsed_sec,
        "setpoints_sent_count": setpoints_sent_count,
        "local_position_count": local_position_count,
        "rangefinder_count": rangefinder_count,
        "position": {
            "x": inputs.current_x,
            "y": inputs.current_y,
            "z_ned": inputs.current_z_ned,
            "height_m": inputs.current_height_m,
            "external_nav_height_m": inputs.external_nav_height_m,
            "rangefinder_relative_height_m": inputs.rangefinder_relative_height_m,
            "target_z_ned": inputs.target_z_ned,
            "yaw_rad": current_yaw_rad,
            "hold_x": hold_x,
            "hold_y": hold_y,
            "hold_yaw_rad": hold_yaw_rad,
        },
    }
    if hover_health is not None:
        hover_health_payload = dict(hover_health)
        payload["hover_health"] = hover_health_payload
        hover_health_phase = hover_health_payload.get("phase")
        if hover_health_phase is not None:
            payload["hover_health_phase"] = hover_health_phase
            payload["mission_phase_substate"] = hover_health_phase
    return payload


def build_landing_summary(
    *,
    fsm_snapshot: MissionPhaseSnapshot,
    policy: str,
    state: str,
    started: bool,
    frozen_hover_evidence: Mapping[str, object],
    land_command_sent: bool,
    land_command_sent_time_sec: float | None,
    land_command_accepted: bool,
    mode_before_land: str | None,
    mode_after_land: str | None,
    land_mode_seen: bool,
    land_mode_seen_elapsed_sec: float | None,
    landed_state_timeline: Sequence[Mapping[str, object]],
    landing_duration_sec: float | None,
    touchdown_confirmed: bool,
    touchdown_confirmed_time_sec: float | None,
    disarmed: bool,
    motors_safe: bool,
    require_disarm: bool,
    require_motors_safe: bool,
    touchdown_confirm_sec: float,
    force_disarm_grace_sec: float,
    force_disarm_after_touchdown: bool,
    force_disarm_used: bool,
    landing_setpoint_lookahead_sec: float,
    landing_slowdown_altitude_m: float,
    landing_near_ground_descent_rate_mps: float,
    last_range_m: float | None,
    last_rangefinder_relative_height_m: float | None,
    last_z_ned: float | None,
    last_vz_mps: float | None,
    landed_state: str,
    fcu_land_params: Mapping[str, float],
    descent_profile: Mapping[str, object],
    landing_blockers: Sequence[str],
) -> dict[str, object]:
    """Build the landing summary/status payload."""

    landing_controller = landing_controller_for_state(state, landing_policy=policy)
    descent_profile_enforced = landing_descent_profile_enforced(policy)
    ok = landing_acceptance_ok(
        landing_policy=policy,
        land_command_sent=land_command_sent,
        land_command_accepted=land_command_accepted,
        land_mode_seen=land_mode_seen,
        touchdown_confirmed=touchdown_confirmed,
        disarmed=disarmed,
        motors_safe=motors_safe,
        require_disarm=require_disarm,
        require_motors_safe=require_motors_safe,
        descent_profile_ok=descent_profile.get("ok") is True,
    )
    auto_disarm_by_land_mode = bool(landing_controller == "ap_land_mode" and disarmed and not force_disarm_used)
    blockers = list(dict.fromkeys(landing_blockers))
    if started:
        if not touchdown_confirmed:
            blockers.append("touchdown_not_confirmed")
        if require_disarm and not disarmed:
            blockers.append("disarm_not_confirmed")
        if require_motors_safe and not motors_safe:
            blockers.append("motors_not_safe")
        if landing_policy_uses_ap_land_mode(policy) and not landing_handoff_confirmed(
            landing_policy=policy,
            land_command_sent=land_command_sent,
            land_command_accepted=land_command_accepted,
            land_mode_seen=land_mode_seen,
        ):
            blockers.append("ap_land_mode_handoff_not_confirmed")
        if descent_profile_enforced and descent_profile.get("speed_ok") is not True:
            blockers.append("landing_descent_too_fast")
        if descent_profile_enforced and descent_profile.get("bounce_ok") is not True:
            blockers.append("landing_post_touchdown_bounce")
    else:
        blockers.append("landing_not_started")

    return {
        "ok": ok,
        "claim": "evaluated" if started else "not_evaluated",
        "policy": policy,
        "state": state,
        "landing_controller": landing_controller,
        "official_land_mode_descent_control": landing_policy_uses_ap_land_mode(policy),
        "descent_profile_enforced": descent_profile_enforced,
        "frozen_hover_evidence": dict(frozen_hover_evidence),
        **mission_phase_summary_fields(fsm_snapshot),
        "return_home": {
            "required": False,
            "ok": True,
            "state": "not_required",
            "distance_to_home_m": None,
            "duration_sec": None,
        },
        "land_command_sent": land_command_sent,
        "land_command_sent_time_sec": land_command_sent_time_sec,
        "land_command_accepted": land_command_accepted,
        "mode_before_land": mode_before_land,
        "mode_after_land": mode_after_land,
        "land_mode_seen": land_mode_seen,
        "land_mode_seen_elapsed_sec": land_mode_seen_elapsed_sec,
        "landed_state_timeline": list(landed_state_timeline)[-40:],
        "landing_duration_sec": landing_duration_sec,
        "landed_confirmed": touchdown_confirmed,
        "touchdown_confirmed": touchdown_confirmed,
        "disarmed": disarmed,
        "motors_safe": motors_safe,
        "require_disarm": require_disarm,
        "require_motors_safe": require_motors_safe,
        "touchdown_confirm_sec": touchdown_confirm_sec,
        "touchdown_confirmed_time_sec": touchdown_confirmed_time_sec,
        "force_disarm_grace_sec": force_disarm_grace_sec,
        "force_disarm_after_touchdown": force_disarm_after_touchdown,
        "force_disarm_used": force_disarm_used,
        "auto_disarm_by_land_mode": auto_disarm_by_land_mode,
        "landing_setpoint_lookahead_sec": landing_setpoint_lookahead_sec,
        "landing_slowdown_altitude_m": landing_slowdown_altitude_m,
        "landing_near_ground_descent_rate_mps": landing_near_ground_descent_rate_mps,
        "uses_gazebo_truth_as_input": False,
        "last_range_m": last_range_m,
        "last_rangefinder_relative_height_m": last_rangefinder_relative_height_m,
        "last_z_ned": last_z_ned,
        "last_vz_mps": last_vz_mps,
        "landed_state": landed_state,
        "fcu_land_params": fcu_land_params_report(dict(fcu_land_params)),
        "descent_profile": dict(descent_profile),
        "blockers": sorted(set(blockers)) if not ok else [],
    }


class MissionSummaryBuilder:
    """Build the final mission summary payload from explicit mission snapshots."""

    def build(
        self,
        *,
        ok: bool,
        reason: str,
        fsm_snapshot: MissionPhaseSnapshot,
        hover_body_ok: bool,
        landing_ok: bool,
        phases_seen: Sequence[str],
        phase_counts: Mapping[str, int],
        prefix_pipeline: Mapping[str, object],
        status_history: Sequence[Mapping[str, object]],
        mode: str,
        mode_number: int,
        guided_seen: bool,
        armed_seen: bool,
        airborne_seen: bool,
        takeoff_ack_ok: bool,
        arm_ack_ok: bool,
        crash_detected: bool,
        setpoints_sent_count: int,
        local_position_count: int,
        rangefinder_count: int,
        target_alt_m: float,
        ground_z_ned: float | None,
        target_z_ned: float,
        current_z_ned: float | None,
        current_height_m: float | None,
        altitude_error_m: float | None,
        hover_altitude_crosscheck: Mapping[str, object],
        preflight_ready_sec: float,
        max_wait_ready_sec: float,
        hover_settle_sec: float,
        hover_altitude_tolerance_m: float,
        hover_hold_sec: float,
        hover_span_target_m: float,
        hover_span_hard_cap_m: float,
        hover_health_min_observation_sec: float,
        hover_health_stable_required_sec: float,
        hover_health_max_wait_sec: float,
        operator_confirm_required: bool,
        operator_confirm_timeout_sec: float,
        runtime_hover_health_final: Mapping[str, object],
        hover_hold_duration_sec: float,
        hover_hold_segments_seen: int,
        require_external_nav: bool,
        external_nav_ready: bool,
        external_nav_status_age_sec: float,
        external_nav_status_history: Sequence[Mapping[str, object]],
        mavlink_external_nav_ready: bool,
        fcu_local_position_ready: bool,
        mavlink_external_nav_status_age_sec: float,
        mavlink_external_nav_status: Mapping[str, object],
        mavlink_external_nav_status_history: Sequence[Mapping[str, object]],
        require_imu_status: bool,
        send_position_setpoints: bool,
        hover_drift: Mapping[str, object],
        last_position: Mapping[str, float | None],
        hold_position: Mapping[str, float | None],
        last_yaw_rad: float | None,
        hold_yaw_rad: float | None,
        message_counts: Mapping[str, int],
        sent_commands: Mapping[str, int],
        accepted_command_ids: Sequence[int],
        command_acks: Sequence[Mapping[str, int]],
        statustext: Sequence[Mapping[str, int | str]],
        ekf_flags_seen: Sequence[int],
        gps_global_origin_seen: bool,
        home_position_seen: bool,
        landing_summary: Mapping[str, Any],
    ) -> dict[str, object]:
        """Return the JSON-compatible final mission summary."""

        bounded_status_history = list(status_history)[-40:]
        return {
            "ok": ok,
            "reason": reason,
            **mission_phase_summary_fields(fsm_snapshot),
            "hover_body_ok": hover_body_ok,
            "landing_ok": landing_ok,
            "phases_seen": sorted(phases_seen),
            "phase_counts": dict(sorted(phase_counts.items())),
            "prefix_pipeline": dict(prefix_pipeline),
            "status_history": bounded_status_history,
            "post_airborne_nav_loss": summarize_post_airborne_nav_loss(bounded_status_history),
            "mode": mode,
            "mode_number": mode_number,
            "guided_seen": guided_seen,
            "armed_seen": armed_seen,
            "airborne_seen": airborne_seen,
            "takeoff_ack_ok": takeoff_ack_ok,
            "arm_ack_ok": arm_ack_ok,
            "crash_detected": crash_detected,
            "setpoints_sent_count": setpoints_sent_count,
            "local_position_count": local_position_count,
            "rangefinder_count": rangefinder_count,
            "target_alt_m": target_alt_m,
            "takeoff_alt_m": target_alt_m,
            "ground_z_ned": ground_z_ned,
            "target_z_ned": target_z_ned,
            "current_z_ned": current_z_ned,
            "current_height_m": current_height_m,
            "altitude_error_m": altitude_error_m,
            "hover_altitude_sources": hover_altitude_crosscheck.get("sources"),
            "hover_altitude_crosscheck": dict(hover_altitude_crosscheck),
            "preflight_ready_sec": preflight_ready_sec,
            "max_wait_ready_sec": max_wait_ready_sec,
            "hover_settle_sec": hover_settle_sec,
            "hover_altitude_tolerance_m": hover_altitude_tolerance_m,
            "hover_hold_sec": hover_hold_sec,
            "hover_span_target_m": hover_span_target_m,
            "hover_span_hard_cap_m": hover_span_hard_cap_m,
            "hover_slo_policy_source": "go_runtime_config",
            "hover_health_min_observation_sec": hover_health_min_observation_sec,
            "hover_health_stable_required_sec": hover_health_stable_required_sec,
            "hover_health_max_wait_sec": hover_health_max_wait_sec,
            "operator_confirm_required": operator_confirm_required,
            "operator_confirm_timeout_sec": operator_confirm_timeout_sec,
            "runtime_hover_health_final": dict(runtime_hover_health_final),
            "hover_hold_duration_sec": hover_hold_duration_sec,
            "hover_hold_segments_seen": hover_hold_segments_seen,
            "require_external_nav": require_external_nav,
            "external_nav_ready": external_nav_ready,
            "external_nav_status_age_sec": external_nav_status_age_sec,
            "external_nav_status_history": list(external_nav_status_history)[-40:],
            "mavlink_external_nav_ready": mavlink_external_nav_ready,
            "fcu_local_position_ready": fcu_local_position_ready,
            "mavlink_external_nav_status_age_sec": mavlink_external_nav_status_age_sec,
            "mavlink_external_nav_status": dict(mavlink_external_nav_status),
            "mavlink_external_nav_status_history": list(mavlink_external_nav_status_history)[-40:],
            "require_imu_status": require_imu_status,
            "send_position_setpoints": send_position_setpoints,
            "hover_drift": dict(hover_drift),
            "last_position": dict(last_position),
            "hold_position": dict(hold_position),
            "last_yaw_rad": last_yaw_rad,
            "hold_yaw_rad": hold_yaw_rad,
            "message_counts": dict(message_counts),
            "sent_commands": dict(sorted(sent_commands.items())),
            "accepted_command_ids": list(accepted_command_ids),
            "command_acks": list(command_acks)[-60:],
            "statustext": list(statustext)[-60:],
            "ekf_flags_seen": list(ekf_flags_seen),
            "gps_global_origin_seen": gps_global_origin_seen,
            "home_position_seen": home_position_seen,
            "land_command_accepted": landing_summary["land_command_accepted"],
            "touchdown_confirmed": landing_summary["touchdown_confirmed"],
            "disarmed": landing_summary["disarmed"],
            "motors_safe": landing_summary["motors_safe"],
            "landing": dict(landing_summary),
        }


class MissionSummaryWriter:
    """Atomically write final mission summary JSON."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def write(self, summary: Mapping[str, object]) -> None:
        """Write one mission summary with a temporary-file replace."""

        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        tmp_path.write_text(json.dumps(summary, allow_nan=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self._path)
