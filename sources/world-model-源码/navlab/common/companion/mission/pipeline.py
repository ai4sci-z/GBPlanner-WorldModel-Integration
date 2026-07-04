"""Composable stage pipeline for companion flight missions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from navlab.common.companion.mission.context import MissionContext

StageStatus = Literal["running", "complete", "blocked", "abort"]


@dataclass(frozen=True, slots=True)
class StageResult:
    """Outcome returned by a mission stage on each pipeline tick."""

    status: StageStatus
    reason: str
    fsm_state: str | None = None
    evidence: dict[str, object] = field(default_factory=dict)
    blocker: str | None = None

    @classmethod
    def running(
        cls,
        reason: str,
        *,
        fsm_state: str | None = None,
        evidence: dict[str, object] | None = None,
    ) -> StageResult:
        """Create a non-terminal result for a stage that is still active."""

        return cls("running", reason, fsm_state=fsm_state, evidence=dict(evidence or {}))

    @classmethod
    def complete(
        cls,
        reason: str,
        *,
        fsm_state: str | None = None,
        evidence: dict[str, object] | None = None,
    ) -> StageResult:
        """Create a result that advances the pipeline to the next stage."""

        return cls("complete", reason, fsm_state=fsm_state, evidence=dict(evidence or {}))

    @classmethod
    def blocked(
        cls,
        reason: str,
        *,
        fsm_state: str | None = None,
        evidence: dict[str, object] | None = None,
        blocker: str | None = None,
    ) -> StageResult:
        """Create a non-terminal blocked result with a blocker reason."""

        return cls("blocked", reason, fsm_state=fsm_state, evidence=dict(evidence or {}), blocker=blocker or reason)

    @classmethod
    def abort(
        cls,
        reason: str,
        *,
        fsm_state: str | None = None,
        evidence: dict[str, object] | None = None,
        blocker: str | None = None,
    ) -> StageResult:
        """Create a result that diverts to safety stages or terminates."""

        return cls("abort", reason, fsm_state=fsm_state, evidence=dict(evidence or {}), blocker=blocker or reason)


class Stage(Protocol):
    """Protocol implemented by one executable mission stage."""

    name: str

    def tick(self, ctx: MissionContext) -> StageResult:
        """Run one stage iteration using the shared mission context."""

        ...


class FlightPipeline:
    """Advance ordered mission stages and optional safety stages."""

    def __init__(self, stages: Sequence[Stage], *, safety_stages: Sequence[Stage] = ()) -> None:
        """Create a pipeline from primary stages and optional safety stages."""

        if not stages:
            raise ValueError("FlightPipeline requires at least one stage")
        self._primary_stages = tuple(stages)
        self._safety_stages = tuple(safety_stages)
        self._active_stages = self._primary_stages
        self._index = 0
        self._in_safety_path = False
        self._terminal_result: StageResult | None = None

    @property
    def active_stage(self) -> Stage:
        """Stage that will be ticked next."""

        return self._active_stages[self._index]

    @property
    def active_stage_index(self) -> int:
        """Index of the active stage within the current stage sequence."""

        return self._index

    @property
    def in_safety_path(self) -> bool:
        """Whether the pipeline is currently executing safety stages."""

        return self._in_safety_path

    @property
    def terminal(self) -> bool:
        """Whether the pipeline has reached a terminal result."""

        return self._terminal_result is not None

    def tick(self, ctx: MissionContext) -> StageResult:
        """Run one pipeline iteration and update mission context state."""

        if self._terminal_result is not None:
            return self._terminal_result

        stage = self.active_stage
        ctx.state.active_stage = stage.name
        ctx.state.active_stage_index = self._index
        ctx.state.phase_counts[stage.name] = ctx.state.phase_counts.get(stage.name, 0) + 1

        result = stage.tick(ctx)
        self._remember_result(ctx, stage, result)
        self._record_fsm(ctx, stage, result)

        if result.status == "complete":
            self._complete_stage(ctx, stage, result)
        elif result.status == "abort":
            self._enter_safety_path(ctx, result)

        return result

    def _remember_result(self, ctx: MissionContext, stage: Stage, result: StageResult) -> None:
        """Store the stage result in the shared evidence history."""

        ctx.evidence.remember_stage_result(
            stage=stage.name,
            status=result.status,
            reason=result.reason,
            fsm_state=result.fsm_state,
            blocker=result.blocker,
            evidence=result.evidence,
        )

    def _record_fsm(self, ctx: MissionContext, stage: Stage, result: StageResult) -> None:
        """Forward a stage FSM state to the context recorder when present."""

        if ctx.fsm is None or result.fsm_state is None:
            return
        transition = getattr(ctx.fsm, "transition", None)
        if not callable(transition):
            return
        transition(
            now_monotonic=ctx.clock.now_monotonic,
            state=result.fsm_state,
            reason=result.reason,
            guard=stage.name,
            blocker=result.blocker,
        )

    def _complete_stage(self, ctx: MissionContext, stage: Stage, result: StageResult) -> None:
        """Mark one stage complete and advance or terminate the pipeline."""

        ctx.state.completed_stages.append(stage.name)
        if self._index + 1 < len(self._active_stages):
            self._index += 1
            ctx.state.active_stage = self.active_stage.name
            ctx.state.active_stage_index = self._index
            return
        ctx.state.terminal = True
        self._terminal_result = result

    def _enter_safety_path(self, ctx: MissionContext, result: StageResult) -> None:
        """Switch to safety stages after abort, or terminate without them."""

        ctx.state.aborted = True
        if not self._safety_stages or self._in_safety_path:
            ctx.state.terminal = True
            self._terminal_result = result
            return
        self._active_stages = self._safety_stages
        self._index = 0
        self._in_safety_path = True
        ctx.state.active_stage = self.active_stage.name
        ctx.state.active_stage_index = self._index
