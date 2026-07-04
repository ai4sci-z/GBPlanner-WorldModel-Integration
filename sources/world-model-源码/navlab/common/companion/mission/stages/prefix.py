"""Reusable flight-prefix stages for ready, GUIDED, arm, and takeoff."""

from __future__ import annotations

import math
from dataclasses import dataclass

from navlab.common.companion.mission.command_adapter import request_mission_command
from navlab.common.companion.mission.context import MissionContext
from navlab.common.companion.mission.fsm import mission_phase_state_for_hover_phase
from navlab.common.companion.mission.pipeline import StageResult
from navlab.common.companion.mission.stages.hover import (
    HoverDecision,
    HoverInputs,
    HoverRequirements,
    decide_hover,
    hover_inputs_from_context,
    independent_takeoff_height_reached,
    should_fail_fast_wait_ready,
)


@dataclass(frozen=True, slots=True)
class FlightPrefixConfig:
    """Configuration shared by the reusable flight-prefix stages."""

    preflight_ready_sec: float = 5.0
    max_wait_ready_sec: float = 35.0
    external_nav_loss_grace_sec: float = 1.0
    require_external_nav: bool = True
    require_fcu_external_nav: bool = True
    require_imu_status: bool = True
    takeoff_alt_m: float = 0.45
    hover_altitude_tolerance_m: float = 0.18

    @property
    def hover_requirements(self) -> HoverRequirements:
        """Return the equivalent hover-decision requirements."""

        return HoverRequirements(
            require_external_nav=self.require_external_nav,
            require_fcu_external_nav=self.require_fcu_external_nav,
            require_imu_status=self.require_imu_status,
            external_nav_loss_grace_sec=self.external_nav_loss_grace_sec,
        )


def _prefix_decision(ctx: MissionContext, config: FlightPrefixConfig) -> tuple[HoverInputs, HoverDecision]:
    """Evaluate the shared hover decision using prefix-stage timing."""

    inputs = hover_inputs_from_context(ctx)
    decision = decide_hover(
        inputs,
        requirements=config.hover_requirements,
        preflight_ready_sec=config.preflight_ready_sec,
        hover_settle_sec=0.0,
        hover_hold_sec=math.inf,
        takeoff_alt_m=config.takeoff_alt_m,
        hover_altitude_tolerance_m=config.hover_altitude_tolerance_m,
    )
    return inputs, decision


class RuntimeReadyStage:
    """Wait for navigation, IMU, yaw, and preflight stability."""

    name = "runtime_ready"

    def __init__(self, config: FlightPrefixConfig) -> None:
        """Create a runtime readiness stage."""

        self._config = config

    def tick(self, ctx: MissionContext) -> StageResult:
        """Evaluate readiness and preflight timeout without side effects."""

        inputs, decision = _prefix_decision(ctx, self._config)
        if decision.phase != "wait_ready":
            return StageResult.complete(
                "runtime_ready",
                fsm_state=mission_phase_state_for_hover_phase("wait_ready"),
                evidence={"ready_elapsed_sec": inputs.ready_elapsed_sec},
            )
        if should_fail_fast_wait_ready(
            inputs,
            decision,
            mission_elapsed_sec=ctx.clock.elapsed_sec,
            max_wait_ready_sec=self._config.max_wait_ready_sec,
        ):
            return StageResult.abort(
                "preflight_timeout",
                fsm_state=mission_phase_state_for_hover_phase("wait_ready"),
                blocker=decision.reason,
                evidence={"ready_elapsed_sec": inputs.ready_elapsed_sec},
            )
        return StageResult.running(
            decision.reason,
            fsm_state=mission_phase_state_for_hover_phase("wait_ready"),
            evidence={"ready_elapsed_sec": inputs.ready_elapsed_sec},
        )


class GuidedModeStage:
    """Wait for GUIDED/custom mode confirmation."""

    name = "guided"

    def tick(self, ctx: MissionContext) -> StageResult:
        """Evaluate GUIDED mode state and request mode change when needed."""

        if ctx.state.fcu.airborne and not ctx.state.fcu.expected_mode_seen:
            return StageResult.abort(
                "guided_mode_lost_after_airborne",
                fsm_state="S_abort",
                blocker="guided_mode_lost_after_airborne",
            )
        if ctx.state.fcu.expected_mode_seen:
            return StageResult.complete(
                "guided_mode_confirmed",
                fsm_state=mission_phase_state_for_hover_phase("guided"),
            )
        command_sent = request_mission_command(ctx, "request_guided_mode")
        return StageResult.running(
            "setting_guided",
            fsm_state=mission_phase_state_for_hover_phase("guided"),
            evidence={"should_set_guided": True, "command_sent": command_sent},
        )


class ArmStage:
    """Wait for FCU armed confirmation."""

    name = "arm"

    def tick(self, ctx: MissionContext) -> StageResult:
        """Evaluate arming state and request arm when needed."""

        if ctx.state.fcu.armed:
            return StageResult.complete("armed", fsm_state=mission_phase_state_for_hover_phase("arm"))
        command_sent = request_mission_command(ctx, "request_arm")
        return StageResult.running(
            "arming_vehicle",
            fsm_state=mission_phase_state_for_hover_phase("arm"),
            evidence={"should_arm": True, "command_sent": command_sent},
        )


class TakeoffStage:
    """Wait for takeoff command effect and independent height evidence."""

    name = "takeoff"

    def __init__(self, config: FlightPrefixConfig) -> None:
        """Create a takeoff stage."""

        self._config = config

    def tick(self, ctx: MissionContext) -> StageResult:
        """Evaluate takeoff progress and request takeoff when needed."""

        inputs = hover_inputs_from_context(ctx)
        if not inputs.airborne_seen:
            command_sent = request_mission_command(ctx, "request_takeoff")
            return StageResult.running(
                "taking_off",
                fsm_state=mission_phase_state_for_hover_phase("takeoff"),
                evidence={
                    "should_takeoff": True,
                    "takeoff_ack_ok": inputs.takeoff_ack_ok,
                    "command_sent": command_sent,
                },
            )
        independent_height_ok = independent_takeoff_height_reached(
            inputs,
            takeoff_alt_m=self._config.takeoff_alt_m,
            hover_altitude_tolerance_m=self._config.hover_altitude_tolerance_m,
        )
        if not independent_height_ok:
            return StageResult.running(
                "waiting_for_independent_takeoff_height",
                fsm_state=mission_phase_state_for_hover_phase("takeoff"),
                evidence={
                    "takeoff_ack_ok": inputs.takeoff_ack_ok,
                    "external_nav_height_m": inputs.external_nav_height_m,
                    "rangefinder_relative_height_m": inputs.rangefinder_relative_height_m,
                },
            )
        reason = "takeoff_confirmed" if inputs.takeoff_ack_ok else "takeoff_height_confirmed_without_ack"
        return StageResult.complete(
            reason,
            fsm_state=mission_phase_state_for_hover_phase("takeoff"),
            evidence={
                "takeoff_ack_ok": inputs.takeoff_ack_ok,
                "external_nav_height_m": inputs.external_nav_height_m,
                "rangefinder_relative_height_m": inputs.rangefinder_relative_height_m,
            },
        )
