"""Hover mission pipeline runner that owns body-to-landing handoff."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from navlab.common.companion.mission.context import (
    LandingRuntimeSnapshot,
    MissionContext,
    apply_landing_runtime_snapshot_to_context,
)
from navlab.common.companion.mission.evidence.hover import HoverCompletionEvaluation, HoverEvidenceRecorder
from navlab.common.companion.mission.evidence.landing import LandingEvidenceRecorder
from navlab.common.companion.mission.fsm import (
    mission_phase_state_for_hover_phase,
    mission_phase_state_for_landing_state,
)
from navlab.common.companion.mission.pipeline import FlightPipeline, Stage, StageResult
from navlab.common.companion.mission.stages.hover import (
    HoverDecision,
    HoverInputs,
    capture_hold_anchor,
    should_fail_fast_wait_ready,
)

HoverTickStatus = Literal["running", "preflight_timeout", "landing_started"]
LandingTickStatus = Literal["running", "abort", "complete"]


class MissionPhaseRecorderCallback(Protocol):
    """Callback used by the runner to record mission FSM transitions."""

    def __call__(
        self,
        now: float,
        state: str,
        reason: str,
        *,
        guard: str | None = None,
        blocker: str | None = None,
    ) -> None:
        """Record one transition."""

        ...


@dataclass(frozen=True, slots=True)
class HoverPipelineConfig:
    """Acceptance thresholds needed when the hover body reaches a terminal state."""

    max_wait_ready_sec: float
    takeoff_alt_m: float
    hover_altitude_tolerance_m: float
    hover_hold_sec: float
    duration_tolerance_sec: float
    max_horizontal_drift_m: float
    hover_span_target_m: float
    hover_span_hard_cap_m: float
    max_altitude_drift_m: float


@dataclass(frozen=True, slots=True)
class HoverTickRuntime:
    """Runtime-only hover inputs for one pipeline runner tick."""

    now_monotonic: float
    inputs: HoverInputs
    local_position_count: int
    crash_detected: bool


@dataclass(frozen=True, slots=True)
class HoverTickOutcome:
    """Result of one hover body pipeline tick."""

    status: HoverTickStatus
    decision: HoverDecision
    hover_completion: HoverCompletionEvaluation | None = None


@dataclass(frozen=True, slots=True)
class LandingTickPreparation:
    """Runtime landing snapshot prepared by the imperative shell."""

    target_available: bool
    snapshot: LandingRuntimeSnapshot | None = None


@dataclass(frozen=True, slots=True)
class LandingTickOutcome:
    """Result of one landing suffix pipeline tick."""

    status: LandingTickStatus
    reason: str
    stage_result: StageResult | None = None
    publish_status: bool = True
    stop_vehicle: bool = False
    shutdown: bool = False
    summary_ok: bool = False
    summary_landing_ok: bool = False
    record_task_success: bool = False


class HoverMissionPipelineRunner:
    """Coordinate prefix, hover body, and landing suffix stages.

    The runner owns the transition from a terminal hover body result into the
    landing suffix. The ROS/MAVLink node still supplies IO callbacks, but it no
    longer decides when the hover body should hand off to landing or how landing
    stage terminal results are interpreted.
    """

    def __init__(
        self,
        *,
        prefix_pipeline: FlightPipeline,
        hover_stage: Stage,
        landing_stage: Stage,
        hover_evidence: HoverEvidenceRecorder,
        landing_evidence: LandingEvidenceRecorder,
        hover_config: HoverPipelineConfig,
    ) -> None:
        """Create a runner from reusable stages and state owners."""

        self._prefix_pipeline = prefix_pipeline
        self._hover_stage = hover_stage
        self._landing_stage = landing_stage
        self._hover_evidence = hover_evidence
        self._landing_evidence = landing_evidence
        self._hover_config = hover_config
        self._landing_started = False

    @property
    def landing_started(self) -> bool:
        """Return whether the runner has entered the landing suffix."""

        return self._landing_started

    def mark_landing_started(self) -> None:
        """Mark landing as active when an external safety path starts it."""

        self._landing_started = True

    def prefix_pipeline_status(self, ctx: MissionContext) -> dict[str, object]:
        """Return a compact status payload for the shared prefix pipeline."""

        active_stage = self._prefix_pipeline.active_stage.name
        return {
            "active_stage": active_stage,
            "active_stage_index": self._prefix_pipeline.active_stage_index,
            "completed_stages": list(ctx.state.completed_stages),
            "terminal": self._prefix_pipeline.terminal,
            "latest": dict(ctx.evidence.latest.get(active_stage, {})),
        }

    def tick_hover(
        self,
        ctx: MissionContext,
        runtime: HoverTickRuntime,
        *,
        record_fsm: MissionPhaseRecorderCallback,
        publish_status: Callable[[HoverDecision, HoverInputs], None],
        begin_landing: Callable[[float, HoverCompletionEvaluation], None],
    ) -> HoverTickOutcome:
        """Tick prefix and hover body stages, entering landing on hover terminal."""

        self._prefix_pipeline.tick(ctx)
        hover_body_result = self._hover_stage.tick(ctx)
        decision = self._hover_decision_from_stage_result(hover_body_result)
        phase_counts = ctx.state.hover.phase_counts
        phase_counts[decision.phase] = phase_counts.get(decision.phase, 0) + 1
        record_fsm(
            runtime.now_monotonic,
            mission_phase_state_for_hover_phase(decision.phase),
            decision.reason,
            guard=decision.phase,
            blocker=decision.reason if decision.phase == "abort" else None,
        )
        if should_fail_fast_wait_ready(
            runtime.inputs,
            decision,
            mission_elapsed_sec=ctx.clock.elapsed_sec,
            max_wait_ready_sec=self._hover_config.max_wait_ready_sec,
        ):
            record_fsm(
                runtime.now_monotonic,
                mission_phase_state_for_hover_phase(decision.phase),
                "preflight_timeout",
                guard=decision.phase,
                blocker=decision.reason,
            )
            ctx.state.hover.body_ok = False
            ctx.state.hover.body_reason = "preflight_timeout"
            return HoverTickOutcome("preflight_timeout", decision)

        hover_segment_started = self._hover_evidence.record_context(
            ctx,
            phase=decision.phase,
            terminal=decision.terminal,
        )
        if hover_segment_started:
            hover = ctx.state.hover
            pose = ctx.state.pose
            hover.hold_x_m, hover.hold_y_m, hover.hold_yaw_rad = capture_hold_anchor(
                hover.hold_x_m,
                hover.hold_y_m,
                hover.hold_yaw_rad,
                pose.x_m,
                pose.y_m,
                pose.yaw_rad,
                refresh_yaw=True,
            )

        publish_status(decision, runtime.inputs)
        if not decision.terminal:
            return HoverTickOutcome("running", decision)

        hover_completion = self._hover_evidence.evaluate_completion(
            target_alt_m=self._hover_config.takeoff_alt_m,
            altitude_tolerance_m=self._hover_config.hover_altitude_tolerance_m,
            hold_sec=self._hover_config.hover_hold_sec,
            duration_tolerance_sec=self._hover_config.duration_tolerance_sec,
            max_horizontal_drift_m=self._hover_config.max_horizontal_drift_m,
            hover_span_target_m=self._hover_config.hover_span_target_m,
            hover_span_hard_cap_m=self._hover_config.hover_span_hard_cap_m,
            max_altitude_drift_m=self._hover_config.max_altitude_drift_m,
            local_position_count=runtime.local_position_count,
            crash_detected=runtime.crash_detected,
            slam_quality=ctx.state.nav.slam_quality,
            slam_quality_reason=ctx.state.nav.slam_quality_reason,
            slam_quality_loss_duration_sec=ctx.state.nav.slam_quality_loss_duration_sec,
            external_nav_loss_duration_sec=ctx.state.nav.external_nav_loss_duration_sec,
            mavlink_external_nav_loss_duration_sec=ctx.state.nav.mavlink_external_nav_loss_duration_sec,
        )
        ctx.state.hover.body_ok = hover_completion.ok
        ctx.state.hover.body_reason = hover_completion.reason
        self._landing_started = True
        begin_landing(runtime.now_monotonic, hover_completion)
        return HoverTickOutcome("landing_started", decision, hover_completion)

    def tick_landing(
        self,
        ctx: MissionContext,
        *,
        now_monotonic: float,
        prepare_landing_tick: Callable[[float], LandingTickPreparation],
        record_fsm: MissionPhaseRecorderCallback,
    ) -> LandingTickOutcome:
        """Tick the landing suffix and interpret its terminal result."""

        preparation = prepare_landing_tick(now_monotonic)
        if not preparation.target_available or preparation.snapshot is None:
            reason = "landing_target_system_missing"
            self._landing_evidence.blockers.append(reason)
            record_fsm(
                now_monotonic,
                "S_abort",
                reason,
                guard=self._landing_evidence.state,
                blocker=reason,
            )
            return LandingTickOutcome(
                "abort",
                reason,
                publish_status=False,
                shutdown=True,
                summary_ok=False,
                summary_landing_ok=False,
            )

        apply_landing_runtime_snapshot_to_context(ctx, preparation.snapshot)
        landing_result = self._landing_stage.tick(ctx)
        self._landing_evidence.state = str(landing_result.evidence.get("state") or ctx.state.landing.state)
        if landing_result.status == "abort":
            self._landing_evidence.blockers.append(landing_result.reason)
            record_fsm(
                now_monotonic,
                "S_abort",
                landing_result.reason,
                guard=self._landing_evidence.state,
                blocker=landing_result.reason,
            )
            return LandingTickOutcome(
                "abort",
                landing_result.reason,
                stage_result=landing_result,
                publish_status=True,
                stop_vehicle=landing_result.reason == "landing_timeout",
                shutdown=True,
                summary_ok=False,
                summary_landing_ok=False,
            )
        if landing_result.status == "complete":
            record_fsm(
                now_monotonic,
                mission_phase_state_for_landing_state(self._landing_evidence.state),
                landing_result.reason,
                guard=self._landing_evidence.state,
            )
            final_ok = ctx.state.hover.body_ok
            return LandingTickOutcome(
                "complete",
                ctx.state.hover.body_reason,
                stage_result=landing_result,
                publish_status=True,
                shutdown=True,
                summary_ok=final_ok,
                summary_landing_ok=True,
                record_task_success=final_ok,
            )
        return LandingTickOutcome("running", landing_result.reason, stage_result=landing_result, publish_status=True)

    @staticmethod
    def _hover_decision_from_stage_result(result: StageResult) -> HoverDecision:
        """Convert a hover stage result into the legacy status decision shape."""

        return HoverDecision(
            phase=str(result.evidence.get("phase") or "abort"),
            reason=result.reason,
            terminal=result.status in {"abort", "complete"},
        )
