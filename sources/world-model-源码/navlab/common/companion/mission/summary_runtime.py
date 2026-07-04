"""Runtime summary adapters for the MAVLink hover mission shell."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from navlab.common.companion.mission.command_adapter import MissionCommandRuntime
from navlab.common.companion.mission.context import MissionContext
from navlab.common.companion.mission.evidence.hover import (
    HoverEvidenceRecorder,
    classify_hover_drift,
    json_safe_number,
    summarize_hover_altitude_crosscheck,
    summarize_hover_drift,
)
from navlab.common.companion.mission.evidence.landing import LandingEvidenceRecorder
from navlab.common.companion.mission.evidence.summary import (
    MissionSummaryBuilder,
    MissionSummaryWriter,
    build_landing_summary,
)
from navlab.common.companion.mission.fsm import MissionPhaseSnapshot
from navlab.common.companion.mission.mavlink_protocol import command_ack_accepted, mavlink
from navlab.common.companion.mission.runtime_state import (
    MavlinkRuntimeCollections,
    MavlinkRuntimeState,
    MissionRuntimeAdapterConfig,
    MissionRuntimeStateAdapter,
)


@dataclass(frozen=True, slots=True)
class HoverMissionSummaryConfig:
    """Static configuration needed to build hover mission summaries."""

    summary_file: str
    mode: str
    mode_number: int
    takeoff_alt_m: float
    hover_altitude_tolerance_m: float
    hover_hold_sec: float
    hover_health_min_observation_sec: float
    hover_health_stable_required_sec: float
    hover_health_max_wait_sec: float
    operator_confirm_required: bool
    operator_confirm_timeout_sec: float
    hover_duration_tolerance_sec: float
    max_horizontal_drift_m: float
    hover_span_target_m: float
    hover_span_hard_cap_m: float
    max_altitude_drift_m: float
    preflight_ready_sec: float
    max_wait_ready_sec: float
    hover_settle_sec: float
    require_external_nav: bool
    require_imu_status: bool
    send_position_setpoints: bool
    landing_policy: str
    require_disarm: bool
    require_motors_safe: bool
    touchdown_confirm_sec: float
    force_disarm_grace_sec: float
    force_disarm_after_touchdown: bool
    landing_setpoint_lookahead_sec: float
    landing_slowdown_altitude_m: float
    landing_near_ground_descent_rate_mps: float
    max_landing_descent_rate_mps: float
    touchdown_altitude_m: float


class HoverMissionSummaryRuntime:
    """Build landing and final summaries from mission state owners."""

    def __init__(self, config: HoverMissionSummaryConfig) -> None:
        """Create a summary runtime with static mission config."""

        self._config = config

    def landing_summary(
        self,
        *,
        now_monotonic: float,
        fsm_snapshot: MissionPhaseSnapshot,
        runtime: MavlinkRuntimeState,
        collections: MavlinkRuntimeCollections,
        landing_evidence: LandingEvidenceRecorder,
        started_at_monotonic: float,
    ) -> dict[str, object]:
        """Build the shared landing status/summary payload."""

        disarmed = not runtime.armed_seen
        motors_safe = disarmed if self._config.require_motors_safe else True
        return build_landing_summary(
            fsm_snapshot=fsm_snapshot,
            policy=self._config.landing_policy,
            state=landing_evidence.state,
            started=landing_evidence.started_at_monotonic is not None,
            frozen_hover_evidence=landing_evidence.frozen_hover_evidence,
            land_command_sent=landing_evidence.land_command_sent,
            land_command_sent_time_sec=None
            if landing_evidence.land_command_sent_time is None
            else max(0.0, landing_evidence.land_command_sent_time - started_at_monotonic),
            land_command_accepted=command_ack_accepted(
                collections.command_acks,
                mavlink.MAV_CMD_NAV_LAND,
                collections.accepted_command_ids,
            ),
            mode_before_land=landing_evidence.mode_before_land,
            mode_after_land=landing_evidence.mode_after_land,
            land_mode_seen=landing_evidence.land_mode_seen,
            land_mode_seen_elapsed_sec=landing_evidence.land_mode_seen_elapsed_sec,
            landed_state_timeline=runtime.landed_state_timeline,
            landing_duration_sec=None
            if landing_evidence.started_at_monotonic is None
            else max(0.0, now_monotonic - landing_evidence.started_at_monotonic),
            touchdown_confirmed=landing_evidence.touchdown_confirmed,
            touchdown_confirmed_time_sec=None
            if landing_evidence.touchdown_confirmed_time is None
            else max(0.0, landing_evidence.touchdown_confirmed_time - started_at_monotonic),
            disarmed=disarmed,
            motors_safe=motors_safe,
            require_disarm=self._config.require_disarm,
            require_motors_safe=self._config.require_motors_safe,
            touchdown_confirm_sec=self._config.touchdown_confirm_sec,
            force_disarm_grace_sec=self._config.force_disarm_grace_sec,
            force_disarm_after_touchdown=self._config.force_disarm_after_touchdown,
            force_disarm_used=landing_evidence.force_disarm_used,
            landing_setpoint_lookahead_sec=self._config.landing_setpoint_lookahead_sec,
            landing_slowdown_altitude_m=self._config.landing_slowdown_altitude_m,
            landing_near_ground_descent_rate_mps=self._config.landing_near_ground_descent_rate_mps,
            last_range_m=runtime.current_range_m,
            last_rangefinder_relative_height_m=self._rangefinder_relative_height_m(runtime),
            last_z_ned=runtime.current_z,
            last_vz_mps=runtime.current_vz,
            landed_state=runtime.landed_state,
            fcu_land_params=landing_evidence.fcu_land_params,
            descent_profile=landing_evidence.descent_profile(
                max_descent_rate_mps=self._config.max_landing_descent_rate_mps,
                touchdown_altitude_m=self._config.touchdown_altitude_m,
            ),
            landing_blockers=landing_evidence.blockers,
        )

    def build_final_summary(
        self,
        *,
        ok: bool,
        reason: str,
        landing_ok: bool,
        now_monotonic: float,
        started_at_monotonic: float,
        fsm_snapshot: MissionPhaseSnapshot,
        prefix_pipeline: Mapping[str, object],
        status_history: Sequence[Mapping[str, object]],
        ctx: MissionContext,
        runtime_adapter: MissionRuntimeStateAdapter,
        runtime_adapter_config: MissionRuntimeAdapterConfig,
        runtime: MavlinkRuntimeState,
        command_runtime: MissionCommandRuntime,
        collections: MavlinkRuntimeCollections,
        hover_evidence: HoverEvidenceRecorder,
        landing_evidence: LandingEvidenceRecorder,
    ) -> dict[str, object]:
        """Build the final mission summary payload from state owners."""

        hover_evidence.remember_segment()
        hover_window = hover_evidence.selected_window()
        hover_samples = hover_window.pose_samples
        altitude_samples = hover_window.altitude_samples
        drift = summarize_hover_drift(hover_samples)
        drift_quality = classify_hover_drift(drift, max_horizontal_drift_m=self._config.max_horizontal_drift_m)
        altitude_crosscheck = summarize_hover_altitude_crosscheck(
            altitude_samples,
            target_alt_m=self._config.takeoff_alt_m,
            tolerance_m=self._config.hover_altitude_tolerance_m,
        )
        target_z_ned = self._target_z_ned(runtime)
        hover_z_ned = hover_samples[-1][3] if hover_samples else runtime.current_z
        if hover_z_ned is not None:
            altitude_error_m = abs(float(hover_z_ned) - float(target_z_ned))
        elif runtime.current_range_m is not None:
            altitude_error_m = abs(float(runtime.current_range_m) - float(self._config.takeoff_alt_m))
        else:
            altitude_error_m = None
        readiness = runtime_adapter.readiness_summary(
            now_monotonic=now_monotonic,
            config=runtime_adapter_config,
        )
        landing_summary = self.landing_summary(
            now_monotonic=now_monotonic,
            fsm_snapshot=fsm_snapshot,
            runtime=runtime,
            collections=collections,
            landing_evidence=landing_evidence,
            started_at_monotonic=started_at_monotonic,
        )
        return MissionSummaryBuilder().build(
            ok=ok,
            reason=reason,
            fsm_snapshot=fsm_snapshot,
            hover_body_ok=ctx.state.hover.body_ok,
            landing_ok=landing_ok,
            phases_seen=sorted(ctx.state.hover.phase_counts),
            phase_counts=ctx.state.hover.phase_counts,
            prefix_pipeline=prefix_pipeline,
            status_history=status_history,
            mode=self._config.mode,
            mode_number=self._config.mode_number,
            guided_seen=runtime.guided_seen_ever
            or runtime.expected_mode_seen
            or runtime_adapter.external_expected_mode_seen,
            armed_seen=runtime.armed_seen_ever or runtime.armed_seen or runtime_adapter.external_armed_seen,
            airborne_seen=runtime.airborne_seen,
            takeoff_ack_ok=command_ack_accepted(
                collections.command_acks,
                mavlink.MAV_CMD_NAV_TAKEOFF,
                collections.accepted_command_ids,
            ),
            arm_ack_ok=command_ack_accepted(
                collections.command_acks,
                mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                collections.accepted_command_ids,
            ),
            crash_detected=runtime.crash_detected,
            setpoints_sent_count=command_runtime.setpoints_sent,
            local_position_count=runtime.message_counts.get("LOCAL_POSITION_NED", 0),
            rangefinder_count=self._rangefinder_count(runtime),
            target_alt_m=self._config.takeoff_alt_m,
            ground_z_ned=runtime.ground_z_ned,
            target_z_ned=target_z_ned,
            current_z_ned=hover_z_ned,
            current_height_m=runtime.current_range_m,
            altitude_error_m=altitude_error_m,
            hover_altitude_crosscheck=altitude_crosscheck,
            preflight_ready_sec=self._config.preflight_ready_sec,
            max_wait_ready_sec=self._config.max_wait_ready_sec,
            hover_settle_sec=self._config.hover_settle_sec,
            hover_altitude_tolerance_m=self._config.hover_altitude_tolerance_m,
            hover_hold_sec=self._config.hover_hold_sec,
            hover_span_target_m=self._config.hover_span_target_m,
            hover_span_hard_cap_m=self._config.hover_span_hard_cap_m,
            hover_health_min_observation_sec=self._config.hover_health_min_observation_sec,
            hover_health_stable_required_sec=self._config.hover_health_stable_required_sec,
            hover_health_max_wait_sec=self._config.hover_health_max_wait_sec,
            operator_confirm_required=self._config.operator_confirm_required,
            operator_confirm_timeout_sec=self._config.operator_confirm_timeout_sec,
            runtime_hover_health_final=self._runtime_hover_health_final(ctx, status_history),
            hover_hold_duration_sec=drift.duration_sec,
            hover_hold_segments_seen=hover_evidence.segment_count,
            require_external_nav=self._config.require_external_nav,
            external_nav_ready=readiness.external_nav_ready,
            external_nav_status_age_sec=readiness.external_nav_status_age_sec,
            external_nav_status_history=readiness.external_nav_status_history,
            mavlink_external_nav_ready=readiness.mavlink_external_nav_ready,
            fcu_local_position_ready=readiness.fcu_local_position_ready,
            mavlink_external_nav_status_age_sec=readiness.mavlink_external_nav_status_age_sec,
            mavlink_external_nav_status=readiness.mavlink_external_nav_status,
            mavlink_external_nav_status_history=readiness.mavlink_external_nav_status_history,
            require_imu_status=self._config.require_imu_status,
            send_position_setpoints=self._config.send_position_setpoints,
            hover_drift=self._hover_drift_payload(
                drift,
                drift_quality,
                slam_quality=runtime_adapter.external_nav_slam_quality,
                slam_quality_reason=runtime_adapter.external_nav_slam_quality_reason,
                slam_quality_loss_duration_sec=ctx.state.nav.slam_quality_loss_duration_sec,
                external_nav_loss_duration_sec=ctx.state.nav.external_nav_loss_duration_sec,
                mavlink_external_nav_loss_duration_sec=ctx.state.nav.mavlink_external_nav_loss_duration_sec,
                external_nav_status_payload=runtime_adapter.last_external_status_payload,
            ),
            last_position={"x": runtime.current_x, "y": runtime.current_y, "z_ned": runtime.current_z},
            hold_position={"x": ctx.state.hover.hold_x_m, "y": ctx.state.hover.hold_y_m},
            last_yaw_rad=runtime.current_yaw_rad,
            hold_yaw_rad=ctx.state.hover.hold_yaw_rad,
            message_counts=runtime.message_counts,
            sent_commands=command_runtime.sent_counts,
            accepted_command_ids=sorted(collections.accepted_command_ids),
            command_acks=collections.command_acks,
            statustext=collections.statustext,
            ekf_flags_seen=sorted(set(runtime.ekf_flags)),
            gps_global_origin_seen=runtime.gps_global_origin_seen,
            home_position_seen=runtime.home_position_seen,
            landing_summary=landing_summary,
        )

    def _runtime_hover_health_final(
        self,
        ctx: MissionContext,
        status_history: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        """Freeze the final runtime health gate state for mission-summary review."""

        latest_health: Mapping[str, object] = {}
        for row in reversed(status_history):
            candidate = row.get("hover_health")
            if isinstance(candidate, Mapping):
                latest_health = candidate
                break

        hover = ctx.state.hover
        phase = str(hover.health_phase or latest_health.get("phase") or "not_started")
        band = str(hover.health_band or latest_health.get("band") or "yellow")
        confirm_elapsed_sec = (
            None
            if hover.operator_confirm_started_at_monotonic is None
            else max(0.0, ctx.clock.now_monotonic - hover.operator_confirm_started_at_monotonic)
        )
        return {
            "schema": "navlab.runtime_hover_health.v1",
            "source": "python_runtime_fsm",
            "controls_task_proceed": True,
            "postrun_audit": False,
            "phase": phase,
            "band": band,
            "reason": str(hover.health_reason or latest_health.get("reason") or ""),
            "blockers": list(latest_health.get("blockers") or []),
            "mission_phase_state": "S6 hover_hold" if phase != "not_started" else None,
            "mission_phase_substate": phase,
            "runtime_phase_alias": latest_health.get("runtime_phase_alias", "hover_hold"),
            "observed_sec": hover.health_observed_sec,
            "stable_sec": hover.health_stable_sec,
            "operator_confirm_required": self._config.operator_confirm_required,
            "operator_confirm_allowed": hover.operator_confirm_allowed,
            "operator_confirm_received": hover.operator_confirm_received,
            "operator_confirm_elapsed_sec": confirm_elapsed_sec,
            "sim_auto_continue_allowed": (
                band == "green" and not self._config.operator_confirm_required and phase == "sim_auto_continue"
            ),
            "real_operator_confirm_allowed": hover.operator_confirm_allowed,
            "min_observation_sec": self._config.hover_health_min_observation_sec,
            "stable_required_sec": self._config.hover_health_stable_required_sec,
            "max_wait_sec": self._config.hover_health_max_wait_sec,
            "operator_confirm_timeout_sec": self._config.operator_confirm_timeout_sec,
        }

    def write_final_summary(self, *, summary_file: str, summary: Mapping[str, object]) -> None:
        """Write the final mission summary if a path is configured."""

        if summary_file:
            MissionSummaryWriter(summary_file).write(summary)

    def _hover_drift_payload(
        self,
        drift,
        drift_quality: str,
        *,
        slam_quality: str = "",
        slam_quality_reason: str = "",
        slam_quality_loss_duration_sec: float = 0.0,
        external_nav_loss_duration_sec: float = 0.0,
        mavlink_external_nav_loss_duration_sec: float = 0.0,
        external_nav_status_payload: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Build the legacy hover drift payload."""

        jump_report = _slam_quality_jump_report(external_nav_status_payload or {})
        jump_seen = slam_quality == "jump" or slam_quality_reason == "pose_or_yaw_jump"
        horizontal_span_tier = _hover_slo_tier(
            drift.horizontal_span_m,
            target_m=self._config.hover_span_target_m,
            hard_cap_m=self._config.hover_span_hard_cap_m,
        )
        horizontal_drift_tier = _hover_slo_tier(
            drift.horizontal_drift_m,
            target_m=self._config.hover_span_target_m,
            hard_cap_m=self._config.hover_span_hard_cap_m,
        )
        horizontal_span_ok = horizontal_span_tier in ("green", "yellow")
        horizontal_drift_ok = horizontal_drift_tier in ("green", "yellow")
        z_span_ok = drift.z_span_m <= self._config.max_altitude_drift_m
        duration_ok = drift.duration_sec >= self._config.hover_hold_sec - self._config.hover_duration_tolerance_sec
        no_slam_quality_loss_after_airborne = slam_quality_loss_duration_sec <= 0.0
        no_external_nav_loss_after_airborne = external_nav_loss_duration_sec <= 0.0
        no_mavlink_external_nav_loss_after_airborne = mavlink_external_nav_loss_duration_sec <= 0.0
        no_slam_quality_jump_in_hover_window = not jump_seen
        return {
            "sample_count": drift.sample_count,
            "duration_sec": drift.duration_sec,
            "horizontal_span_m": json_safe_number(drift.horizontal_span_m),
            "z_span_m": json_safe_number(drift.z_span_m),
            "horizontal_drift_m": json_safe_number(drift.horizontal_drift_m),
            "z_drift_m": json_safe_number(drift.z_drift_m),
            "max_horizontal_drift_m": self._config.max_horizontal_drift_m,
            "hover_span_target_m": self._config.hover_span_target_m,
            "hover_span_hard_cap_m": self._config.hover_span_hard_cap_m,
            "hover_slo_policy_source": "go_runtime_config",
            "max_altitude_drift_m": self._config.max_altitude_drift_m,
            "duration_tolerance_sec": self._config.hover_duration_tolerance_sec,
            "quality": drift_quality,
            "gps_like": drift_quality == "tight" and drift.horizontal_drift_m <= 0.05 and drift.z_span_m <= 0.05,
            "horizontal_span_ok": horizontal_span_ok,
            "horizontal_drift_ok": horizontal_drift_ok,
            "horizontal_span_target_ok": horizontal_span_tier == "green",
            "horizontal_drift_target_ok": horizontal_drift_tier == "green",
            "horizontal_span_hard_cap_ok": horizontal_span_ok,
            "horizontal_drift_hard_cap_ok": horizontal_drift_ok,
            "horizontal_span_tier": horizontal_span_tier,
            "horizontal_drift_tier": horizontal_drift_tier,
            "horizontal_span_warning": horizontal_span_tier == "yellow",
            "horizontal_drift_warning": horizontal_drift_tier == "yellow",
            "z_span_ok": z_span_ok,
            "duration_ok": duration_ok,
            "no_slam_quality_loss_after_airborne": no_slam_quality_loss_after_airborne,
            "no_external_nav_loss_after_airborne": no_external_nav_loss_after_airborne,
            "no_mavlink_external_nav_loss_after_airborne": no_mavlink_external_nav_loss_after_airborne,
            "no_slam_quality_jump_in_hover_window": no_slam_quality_jump_in_hover_window,
            "slam_quality": slam_quality,
            "slam_quality_reason": slam_quality_reason,
            "slam_quality_loss_duration_sec": slam_quality_loss_duration_sec,
            "external_nav_loss_duration_sec": external_nav_loss_duration_sec,
            "mavlink_external_nav_loss_duration_sec": mavlink_external_nav_loss_duration_sec,
            "jump_seen_in_hover_window": jump_seen,
            "max_observed_position_jump_m": jump_report["max_observed_position_jump_m"],
            "max_observed_yaw_jump_rad": jump_report["max_observed_yaw_jump_rad"],
            "ok": (
                drift.ok
                and duration_ok
                and horizontal_drift_ok
                and horizontal_span_ok
                and z_span_ok
                and no_slam_quality_loss_after_airborne
                and no_external_nav_loss_after_airborne
                and no_mavlink_external_nav_loss_after_airborne
                and no_slam_quality_jump_in_hover_window
            ),
        }

    def _target_z_ned(self, runtime: MavlinkRuntimeState) -> float:
        ground_z = runtime.ground_z_ned if runtime.ground_z_ned is not None else 0.0
        return ground_z - self._config.takeoff_alt_m

    @staticmethod
    def _rangefinder_relative_height_m(runtime: MavlinkRuntimeState) -> float | None:
        if runtime.current_range_m is None or runtime.ground_range_m is None:
            return None
        return max(0.0, float(runtime.current_range_m) - float(runtime.ground_range_m))

    @staticmethod
    def _rangefinder_count(runtime: MavlinkRuntimeState) -> int:
        return runtime.message_counts.get("DISTANCE_SENSOR", 0) + runtime.message_counts.get("RANGEFINDER", 0)


def _finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _hover_slo_tier(value: float, *, target_m: float, hard_cap_m: float) -> str:
    if target_m <= 0 or hard_cap_m <= 0 or target_m > hard_cap_m or not math.isfinite(value):
        return "unusable"
    if value <= target_m:
        return "green"
    if value <= hard_cap_m:
        return "yellow"
    return "red"


def _slam_quality_jump_report(payload: Mapping[str, object]) -> dict[str, float | None]:
    report = payload.get("slam_quality_report")
    if not isinstance(report, Mapping):
        return {"max_observed_position_jump_m": None, "max_observed_yaw_jump_rad": None}
    return {
        "max_observed_position_jump_m": _finite_number(report.get("max_observed_position_jump_m")),
        "max_observed_yaw_jump_rad": _finite_number(report.get("max_observed_yaw_jump_rad")),
    }
