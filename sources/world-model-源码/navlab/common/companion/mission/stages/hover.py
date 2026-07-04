"""Hover stage decision and setpoint helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from navlab.common.companion.mission.command_adapter import request_mission_command
from navlab.common.companion.mission.context import MissionContext
from navlab.common.companion.mission.fsm import mission_phase_state_for_hover_phase
from navlab.common.companion.mission.pipeline import StageResult


@dataclass(frozen=True, slots=True)
class HoverInputs:
    """Sensor and FCU inputs consumed by the hover decision stage."""

    external_nav_ready: bool
    mavlink_external_nav_ready: bool
    fcu_local_position_ready: bool
    imu_ready: bool
    slam_quality_good: bool
    slam_quality: str
    ready_elapsed_sec: float
    current_yaw_rad: float | None
    expected_mode_seen: bool
    armed_seen: bool
    airborne_seen: bool
    takeoff_ack_ok: bool
    airborne_elapsed_sec: float
    hover_elapsed_sec: float
    current_x: float | None
    current_y: float | None
    current_z_ned: float | None
    current_height_m: float | None
    external_nav_height_m: float | None
    rangefinder_relative_height_m: float | None
    target_z_ned: float | None
    slam_quality_loss_duration_sec: float = 0.0
    external_nav_loss_duration_sec: float = 0.0
    mavlink_external_nav_loss_duration_sec: float = 0.0
    fcu_local_position_loss_duration_sec: float = 0.0


@dataclass(frozen=True, slots=True)
class HoverRequirements:
    """Runtime gates that decide which readiness signals are mandatory."""

    require_external_nav: bool = True
    require_fcu_external_nav: bool = True
    require_imu_status: bool = True
    external_nav_loss_grace_sec: float = 1.0


@dataclass(frozen=True, slots=True)
class HoverHealthGateConfig:
    """Runtime proceed gate applied after the vehicle reaches hover hold."""

    min_observation_sec: float = 10.0
    stable_required_sec: float = 5.0
    max_wait_sec: float = 60.0
    operator_confirm_required: bool = False
    operator_confirm_timeout_sec: float = 60.0


@dataclass(frozen=True, slots=True)
class HoverHoldConfig:
    """Configuration for the executable hover-body stage."""

    preflight_ready_sec: float = 5.0
    hover_settle_sec: float = 2.0
    hover_hold_sec: float = 20.0
    takeoff_alt_m: float = 0.45
    hover_altitude_tolerance_m: float = 0.18
    send_position_setpoints: bool = True
    requirements: HoverRequirements = HoverRequirements()
    health_gate: HoverHealthGateConfig = HoverHealthGateConfig()


@dataclass(frozen=True, slots=True)
class HoverDecision:
    """Decision emitted by one hover stage evaluation."""

    phase: str
    reason: str
    should_set_guided: bool = False
    should_arm: bool = False
    should_takeoff: bool = False
    terminal: bool = False


@dataclass(frozen=True, slots=True)
class HoverHealthGateResult:
    """Typed result from the pre-task hover health gate."""

    decision: HoverDecision
    payload: dict[str, object]


def hover_inputs_from_context(ctx: MissionContext) -> HoverInputs:
    """Project shared mission context into the hover decision input contract."""

    return HoverInputs(
        external_nav_ready=ctx.state.nav.external_nav_ready,
        mavlink_external_nav_ready=ctx.state.nav.mavlink_external_nav_ready,
        fcu_local_position_ready=ctx.state.nav.fcu_local_position_ready,
        imu_ready=ctx.state.nav.imu_ready,
        slam_quality_good=ctx.state.nav.slam_quality_good,
        slam_quality=ctx.state.nav.slam_quality,
        ready_elapsed_sec=ctx.state.nav.ready_elapsed_sec,
        current_yaw_rad=ctx.state.pose.yaw_rad,
        expected_mode_seen=ctx.state.fcu.expected_mode_seen,
        armed_seen=ctx.state.fcu.armed,
        airborne_seen=ctx.state.fcu.airborne,
        takeoff_ack_ok=ctx.state.fcu.takeoff_ack_ok,
        airborne_elapsed_sec=ctx.state.hover.airborne_elapsed_sec,
        hover_elapsed_sec=ctx.state.hover.hover_elapsed_sec,
        current_x=ctx.state.pose.x_m,
        current_y=ctx.state.pose.y_m,
        current_z_ned=ctx.state.pose.z_ned_m,
        current_height_m=ctx.state.pose.height_m,
        external_nav_height_m=ctx.state.pose.external_nav_height_m,
        rangefinder_relative_height_m=ctx.state.pose.rangefinder_relative_height_m,
        target_z_ned=ctx.state.pose.target_z_ned_m,
        slam_quality_loss_duration_sec=ctx.state.nav.slam_quality_loss_duration_sec,
        external_nav_loss_duration_sec=ctx.state.nav.external_nav_loss_duration_sec,
        mavlink_external_nav_loss_duration_sec=ctx.state.nav.mavlink_external_nav_loss_duration_sec,
        fcu_local_position_loss_duration_sec=ctx.state.nav.fcu_local_position_loss_duration_sec,
    )


def decide_hover(
    inputs: HoverInputs,
    *,
    requirements: HoverRequirements | None = None,
    preflight_ready_sec: float,
    hover_settle_sec: float,
    hover_hold_sec: float,
    takeoff_alt_m: float,
    hover_altitude_tolerance_m: float,
) -> HoverDecision:
    """Evaluate the current hover phase and requested side effects."""

    requirements = requirements or HoverRequirements()
    if inputs.airborne_seen and not inputs.armed_seen:
        return HoverDecision("abort", "disarmed_after_airborne", terminal=True)
    loss_abort_ready = inputs.airborne_seen and (
        inputs.airborne_elapsed_sec >= hover_settle_sec or inputs.hover_elapsed_sec > 0.0
    )
    if (
        loss_abort_ready
        and requirements.require_external_nav
        and not inputs.slam_quality_good
        and inputs.slam_quality_loss_duration_sec >= requirements.external_nav_loss_grace_sec
    ):
        return HoverDecision("abort", "slam_quality_lost_after_airborne", terminal=True)
    if (
        loss_abort_ready
        and requirements.require_external_nav
        and not inputs.external_nav_ready
        and inputs.external_nav_loss_duration_sec >= requirements.external_nav_loss_grace_sec
    ):
        return HoverDecision("abort", "external_nav_lost_after_airborne", terminal=True)
    if loss_abort_ready and requirements.require_fcu_external_nav:
        if (
            not inputs.mavlink_external_nav_ready
            and inputs.mavlink_external_nav_loss_duration_sec >= requirements.external_nav_loss_grace_sec
        ):
            return HoverDecision("abort", "mavlink_external_nav_lost_after_airborne", terminal=True)
        if (
            not inputs.fcu_local_position_ready
            and inputs.fcu_local_position_loss_duration_sec >= requirements.external_nav_loss_grace_sec
        ):
            return HoverDecision("abort", "fcu_local_position_lost_after_airborne", terminal=True)
    if not inputs.airborne_seen and requirements.require_external_nav and not inputs.slam_quality_good:
        return HoverDecision("wait_ready", "waiting_for_slam_quality")
    if not inputs.airborne_seen and requirements.require_external_nav and not inputs.external_nav_ready:
        return HoverDecision("wait_ready", "waiting_for_external_nav_and_imu")
    if (
        not inputs.airborne_seen
        and requirements.require_fcu_external_nav
        and (not inputs.mavlink_external_nav_ready or not inputs.fcu_local_position_ready)
    ):
        return HoverDecision("wait_ready", "waiting_for_fcu_external_nav")
    if not inputs.airborne_seen and requirements.require_imu_status and not inputs.imu_ready:
        return HoverDecision("wait_ready", "waiting_for_external_nav_and_imu")
    if inputs.current_yaw_rad is None:
        return HoverDecision("wait_ready", "waiting_for_fcu_attitude")
    if not inputs.airborne_seen and inputs.ready_elapsed_sec < preflight_ready_sec:
        return HoverDecision("wait_ready", "waiting_for_stable_external_nav_and_imu")
    if inputs.airborne_seen and not inputs.expected_mode_seen:
        return HoverDecision("abort", "guided_mode_lost_after_airborne", terminal=True)
    if not inputs.expected_mode_seen:
        return HoverDecision("guided", "setting_guided", should_set_guided=True)
    if not inputs.armed_seen:
        return HoverDecision("arm", "arming_vehicle", should_arm=True)
    if not inputs.airborne_seen:
        return HoverDecision("takeoff", "taking_off", should_takeoff=True)
    if inputs.airborne_elapsed_sec < hover_settle_sec:
        return HoverDecision("hover_settle", "settling_before_position_hold")
    independent_height_ok = independent_takeoff_height_reached(
        inputs,
        takeoff_alt_m=takeoff_alt_m,
        hover_altitude_tolerance_m=hover_altitude_tolerance_m,
    )
    if not inputs.takeoff_ack_ok:
        if not independent_height_ok:
            return HoverDecision("hover_settle", "waiting_for_independent_takeoff_height")
        if inputs.hover_elapsed_sec < hover_hold_sec:
            return HoverDecision("hover_hold", "holding_position_with_independent_height")
        return HoverDecision("complete", "hover_complete", terminal=True)
    if not independent_height_ok:
        return HoverDecision("hover_settle", "waiting_for_independent_takeoff_height")
    if not hover_altitude_target_reached(
        inputs,
        takeoff_alt_m=takeoff_alt_m,
        hover_altitude_tolerance_m=hover_altitude_tolerance_m,
    ):
        return HoverDecision("hover_settle", "settling_until_target_altitude")
    if inputs.hover_elapsed_sec < hover_hold_sec:
        return HoverDecision("hover_hold", "holding_position")
    return HoverDecision("complete", "hover_complete", terminal=True)


def apply_hover_health_gate(
    ctx: MissionContext,
    inputs: HoverInputs,
    decision: HoverDecision,
    *,
    config: HoverHealthGateConfig,
    requirements: HoverRequirements,
) -> HoverHealthGateResult:
    """Apply the runtime hover-health proceed gate without shortening hover acceptance."""

    band, health_reason, blockers = classify_hover_health(inputs, decision, requirements=requirements)
    state = ctx.state.hover
    now = ctx.clock.now_monotonic
    gate_active = decision.phase in {"hover_hold", "complete"} or state.health_started_at_monotonic is not None

    if not gate_active:
        _update_hover_health_state(
            ctx,
            band=band,
            phase=decision.phase,
            reason=health_reason,
            operator_allowed=False,
            reset_green=True,
        )
        return HoverHealthGateResult(decision, hover_health_payload(ctx, config=config, blockers=blockers))

    if state.health_started_at_monotonic is None:
        state.health_started_at_monotonic = now

    if band == "green":
        if state.health_green_since_monotonic is None:
            state.health_green_since_monotonic = now
    else:
        state.health_green_since_monotonic = None
        state.operator_confirm_received = False
        state.operator_confirm_started_at_monotonic = None

    observed_sec = max(0.0, now - state.health_started_at_monotonic)
    stable_sec = (
        0.0 if state.health_green_since_monotonic is None else max(0.0, now - state.health_green_since_monotonic)
    )
    state.health_observed_sec = observed_sec
    state.health_stable_sec = stable_sec
    min_observation_sec = max(0.0, config.min_observation_sec)
    stable_required_sec = max(0.0, config.stable_required_sec)
    min_observation_met = observed_sec >= min_observation_sec
    stable_met = stable_sec >= stable_required_sec

    if band == "red":
        _update_hover_health_state(
            ctx,
            band=band,
            phase="hover_health_blocked",
            reason=health_reason,
            operator_allowed=False,
        )
        red_decision = HoverDecision("abort", health_reason, terminal=True)
        return HoverHealthGateResult(red_decision, hover_health_payload(ctx, config=config, blockers=blockers))

    if (
        config.max_wait_sec > 0.0
        and observed_sec >= config.max_wait_sec
        and not (band == "green" and min_observation_met and stable_met)
    ):
        reason = "hover_health_timeout"
        _update_hover_health_state(
            ctx,
            band="red",
            phase="hover_health_blocked",
            reason=reason,
            operator_allowed=False,
        )
        timeout_decision = HoverDecision("abort", reason, terminal=True)
        return HoverHealthGateResult(
            timeout_decision,
            hover_health_payload(ctx, config=config, blockers=[*blockers, reason]),
        )

    proceed_allowed = False
    operator_allowed = False
    if band != "green":
        health_phase = "hover_health_hold"
        reason = health_reason
    elif not min_observation_met:
        health_phase = "hover_health_hold"
        reason = "hover_health_waiting_min_observation"
        state.operator_confirm_received = False
    elif not stable_met:
        health_phase = "hover_health_hold"
        reason = "hover_health_waiting_stable_window"
        state.operator_confirm_received = False
    elif decision.phase != "complete":
        health_phase = "hover_health_hold"
        reason = "hover_health_waiting_hover_duration"
        state.operator_confirm_received = False
    elif config.operator_confirm_required:
        operator_allowed = True
        if state.operator_confirm_started_at_monotonic is None:
            state.operator_confirm_started_at_monotonic = now
        if state.operator_confirm_received:
            health_phase = "operator_confirmed"
            reason = "operator_confirmed"
            proceed_allowed = True
        elif (
            config.operator_confirm_timeout_sec > 0.0
            and now - state.operator_confirm_started_at_monotonic >= config.operator_confirm_timeout_sec
        ):
            reason = "operator_confirm_timeout"
            _update_hover_health_state(
                ctx,
                band="red",
                phase="hover_health_blocked",
                reason=reason,
                operator_allowed=False,
            )
            timeout_decision = HoverDecision("abort", reason, terminal=True)
            return HoverHealthGateResult(
                timeout_decision,
                hover_health_payload(ctx, config=config, blockers=[*blockers, reason]),
            )
        else:
            health_phase = "operator_confirm"
            reason = "waiting_for_operator_confirm"
    else:
        health_phase = "sim_auto_continue"
        reason = "hover_health_green_stable"
        proceed_allowed = True

    _update_hover_health_state(
        ctx,
        band=band,
        phase=health_phase,
        reason=reason,
        operator_allowed=operator_allowed,
    )

    if decision.phase == "complete" and not proceed_allowed:
        gated_decision = HoverDecision("hover_hold", reason)
        return HoverHealthGateResult(gated_decision, hover_health_payload(ctx, config=config, blockers=blockers))
    if decision.phase == "hover_hold" and health_phase in {"hover_health_hold", "operator_confirm"}:
        gated_decision = HoverDecision("hover_hold", reason)
        return HoverHealthGateResult(gated_decision, hover_health_payload(ctx, config=config, blockers=blockers))
    return HoverHealthGateResult(decision, hover_health_payload(ctx, config=config, blockers=blockers))


def classify_hover_health(
    inputs: HoverInputs,
    decision: HoverDecision,
    *,
    requirements: HoverRequirements,
) -> tuple[str, str, list[str]]:
    """Classify live hover readiness as green/yellow/red for proceed gating."""

    if decision.phase == "abort" or decision.terminal and decision.reason != "hover_complete":
        reason = decision.reason or "hover_health_red"
        return "red", reason, [reason]

    blockers: list[str] = []
    if not inputs.airborne_seen:
        blockers.append("not_airborne")
    if not inputs.armed_seen:
        blockers.append("not_armed")
    if not inputs.expected_mode_seen:
        blockers.append("guided_mode_not_confirmed")
    if requirements.require_external_nav:
        if not inputs.slam_quality_good:
            blockers.append("slam_quality_not_green")
        if not inputs.external_nav_ready:
            blockers.append("external_nav_not_ready")
    if requirements.require_fcu_external_nav:
        if not inputs.mavlink_external_nav_ready:
            blockers.append("mavlink_external_nav_not_ready")
        if not inputs.fcu_local_position_ready:
            blockers.append("fcu_local_position_not_ready")
    if requirements.require_imu_status and not inputs.imu_ready:
        blockers.append("imu_not_ready")

    if blockers:
        return "yellow", blockers[0], blockers
    return "green", "hover_health_green", []


def hover_health_payload(
    ctx: MissionContext,
    *,
    config: HoverHealthGateConfig,
    blockers: list[str] | None = None,
) -> dict[str, object]:
    """Build a status payload from the owned hover-health gate state."""

    state = ctx.state.hover
    confirm_elapsed_sec = (
        None
        if state.operator_confirm_started_at_monotonic is None
        else max(0.0, ctx.clock.now_monotonic - state.operator_confirm_started_at_monotonic)
    )
    return {
        "phase": state.health_phase,
        "runtime_phase_alias": (
            "hover_hold" if state.health_phase in {"hover_health_hold", "operator_confirm"} else state.health_phase
        ),
        "band": state.health_band,
        "reason": state.health_reason,
        "blockers": list(blockers or []),
        "observed_sec": state.health_observed_sec,
        "stable_sec": state.health_stable_sec,
        "operator_confirm_required": config.operator_confirm_required,
        "operator_confirm_allowed": state.operator_confirm_allowed,
        "operator_confirm_received": state.operator_confirm_received,
        "operator_confirm_elapsed_sec": confirm_elapsed_sec,
        "sim_auto_continue_allowed": state.health_band == "green"
        and not config.operator_confirm_required
        and state.health_phase == "sim_auto_continue",
        "real_operator_confirm_allowed": state.operator_confirm_allowed,
        "min_observation_sec": config.min_observation_sec,
        "stable_required_sec": config.stable_required_sec,
        "max_wait_sec": config.max_wait_sec,
        "operator_confirm_timeout_sec": config.operator_confirm_timeout_sec,
    }


def _update_hover_health_state(
    ctx: MissionContext,
    *,
    band: str,
    phase: str,
    reason: str,
    operator_allowed: bool,
    reset_green: bool = False,
) -> None:
    """Persist the latest gate classification in the shared hover state."""

    state = ctx.state.hover
    state.health_band = band
    state.health_phase = phase
    state.health_reason = reason
    state.operator_confirm_allowed = operator_allowed
    if reset_green:
        state.health_green_since_monotonic = None
        state.health_observed_sec = 0.0
        state.health_stable_sec = 0.0
        state.operator_confirm_started_at_monotonic = None


class HoverHoldStage:
    """Execute the hover body decision and request hold setpoints when needed."""

    name = "hover_hold"

    def __init__(self, config: HoverHoldConfig) -> None:
        """Create the hover-body stage."""

        self._config = config

    def tick(self, ctx: MissionContext) -> StageResult:
        """Evaluate hover progress and request a hold setpoint through the adapter."""

        inputs = hover_inputs_from_context(ctx)
        decision = decide_hover(
            inputs,
            requirements=self._config.requirements,
            preflight_ready_sec=self._config.preflight_ready_sec,
            hover_settle_sec=self._config.hover_settle_sec,
            hover_hold_sec=self._config.hover_hold_sec,
            takeoff_alt_m=self._config.takeoff_alt_m,
            hover_altitude_tolerance_m=self._config.hover_altitude_tolerance_m,
        )
        health_gate = apply_hover_health_gate(
            ctx,
            inputs,
            decision,
            config=self._config.health_gate,
            requirements=self._config.requirements,
        )
        decision = health_gate.decision
        should_send_hold_setpoint = should_send_position_hold_setpoint(
            send_position_setpoints=self._config.send_position_setpoints,
            inputs=inputs,
            decision=decision,
        )
        command_sent = False
        if should_send_hold_setpoint:
            command_sent = request_mission_command(ctx, "send_hold_setpoint")

        evidence = {
            "phase": decision.phase,
            "terminal": decision.terminal,
            "should_send_hold_setpoint": should_send_hold_setpoint,
            "command_sent": command_sent,
            "hover_health": health_gate.payload,
        }
        fsm_state = mission_phase_state_for_hover_phase(decision.phase)
        if decision.phase == "abort":
            return StageResult.abort(decision.reason, fsm_state=fsm_state, blocker=decision.reason, evidence=evidence)
        if decision.terminal:
            return StageResult.complete(decision.reason, fsm_state=fsm_state, evidence=evidence)
        return StageResult.running(decision.reason, fsm_state=fsm_state, evidence=evidence)


def should_fail_fast_wait_ready(
    inputs: HoverInputs,
    decision: HoverDecision,
    *,
    mission_elapsed_sec: float,
    max_wait_ready_sec: float,
) -> bool:
    """Return whether wait-ready has exceeded its fail-fast deadline."""

    return (
        max_wait_ready_sec > 0.0
        and decision.phase == "wait_ready"
        and not inputs.armed_seen
        and not inputs.airborne_seen
        and mission_elapsed_sec >= max_wait_ready_sec
    )


def hold_axis_or_current(hold_value: float | None, current_value: float | None) -> float:
    """Use a held axis value when available, otherwise fall back to current."""

    if hold_value is not None:
        return hold_value
    if current_value is not None:
        return current_value
    return 0.0


def hover_hold_setpoint_axes(
    *,
    hold_x: float | None,
    hold_y: float | None,
    current_x: float | None,
    current_y: float | None,
    current_z: float | None,
    target_z_ned: float | None,
) -> tuple[float, float, float]:
    """Build local-NED hold setpoint axes from anchors and current pose."""

    return (
        hold_axis_or_current(hold_x, current_x),
        hold_axis_or_current(hold_y, current_y),
        hold_axis_or_current(target_z_ned, current_z),
    )


def hold_yaw_or_current(hold_yaw_rad: float | None, current_yaw_rad: float | None) -> float:
    """Use held yaw when available, otherwise current yaw or zero."""

    if hold_yaw_rad is not None:
        return hold_yaw_rad
    return current_yaw_rad if current_yaw_rad is not None else 0.0


def capture_hold_anchor(
    hold_x: float | None,
    hold_y: float | None,
    hold_yaw_rad: float | None,
    current_x: float | None,
    current_y: float | None,
    current_yaw_rad: float | None,
    *,
    refresh_yaw: bool = False,
) -> tuple[float | None, float | None, float]:
    """Capture or retain the position/yaw anchor for a hold segment."""

    yaw_anchor = current_yaw_rad if refresh_yaw and current_yaw_rad is not None else hold_yaw_rad
    if hold_x is not None and hold_y is not None:
        return hold_x, hold_y, hold_yaw_or_current(yaw_anchor, current_yaw_rad)
    if current_x is None or current_y is None:
        return hold_x, hold_y, hold_yaw_or_current(yaw_anchor, current_yaw_rad)
    yaw = current_yaw_rad if current_yaw_rad is not None else hold_yaw_or_current(yaw_anchor, None)
    return current_x, current_y, yaw


def should_send_position_hold_setpoint(
    *,
    send_position_setpoints: bool,
    inputs: HoverInputs,
    decision: HoverDecision,
) -> bool:
    """Return whether a position-hold setpoint should be sent this tick."""

    return (
        send_position_setpoints
        and inputs.airborne_seen
        and inputs.armed_seen
        and decision.phase == "hover_hold"
        and not decision.terminal
    )


def height_reaches_target(value_m: float | None, *, target_alt_m: float, tolerance_m: float) -> bool:
    """Return whether a height sample is finite and within target tolerance."""

    if value_m is None:
        return False
    value = float(value_m)
    if not math.isfinite(value):
        return False
    return abs(value - target_alt_m) <= tolerance_m


def local_z_reaches_target(
    current_z_ned: float | None,
    *,
    target_z_ned: float | None,
    takeoff_alt_m: float,
    tolerance_m: float,
) -> bool:
    """Return whether local-NED z is within the configured target altitude."""

    if current_z_ned is None:
        return False
    value = float(current_z_ned)
    if not math.isfinite(value):
        return False
    target = float(target_z_ned) if target_z_ned is not None else -float(takeoff_alt_m)
    if not math.isfinite(target):
        return False
    return abs(value - target) <= tolerance_m


def hover_altitude_source_votes(
    inputs: HoverInputs,
    *,
    takeoff_alt_m: float,
    hover_altitude_tolerance_m: float,
) -> dict[str, bool]:
    """Return target-altitude agreement from the independent hover height sources."""

    return {
        "external_nav_height": height_reaches_target(
            inputs.external_nav_height_m,
            target_alt_m=takeoff_alt_m,
            tolerance_m=hover_altitude_tolerance_m,
        ),
        "rangefinder_relative_height": height_reaches_target(
            inputs.rangefinder_relative_height_m,
            target_alt_m=takeoff_alt_m,
            tolerance_m=hover_altitude_tolerance_m,
        ),
        "fcu_local_z": local_z_reaches_target(
            inputs.current_z_ned,
            target_z_ned=inputs.target_z_ned,
            takeoff_alt_m=takeoff_alt_m,
            tolerance_m=hover_altitude_tolerance_m,
        ),
    }


def hover_altitude_target_reached(
    inputs: HoverInputs,
    *,
    takeoff_alt_m: float,
    hover_altitude_tolerance_m: float,
) -> bool:
    """Require ExternalNav height plus one other altitude source at target."""

    votes = hover_altitude_source_votes(
        inputs,
        takeoff_alt_m=takeoff_alt_m,
        hover_altitude_tolerance_m=hover_altitude_tolerance_m,
    )
    return bool(votes["external_nav_height"] and (votes["rangefinder_relative_height"] or votes["fcu_local_z"]))


def independent_takeoff_height_reached(
    inputs: HoverInputs,
    *,
    takeoff_alt_m: float,
    hover_altitude_tolerance_m: float,
) -> bool:
    """Require ExternalNav height and a second height source to agree with target."""

    return hover_altitude_target_reached(
        inputs,
        takeoff_alt_m=takeoff_alt_m,
        hover_altitude_tolerance_m=hover_altitude_tolerance_m,
    )
