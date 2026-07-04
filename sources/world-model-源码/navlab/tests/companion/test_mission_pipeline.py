from __future__ import annotations

import pytest

from navlab.common.companion.mission import (
    FlightPipeline,
    MissionClock,
    MissionContext,
    MissionPhaseRecorder,
    StageResult,
)
from navlab.common.companion.mission.context import (
    CommandState,
    FcuState,
    HoverState,
    LandingRuntimeSnapshot,
    LandingState,
    MissionRuntimeSnapshot,
    NavState,
    PoseState,
    apply_landing_runtime_snapshot_to_context,
    apply_runtime_snapshot_to_context,
)


class _ScriptedStage:
    def __init__(self, name: str, *results: StageResult) -> None:
        self.name = name
        self._results = list(results)
        self.ticks = 0

    def tick(self, ctx: MissionContext) -> StageResult:
        self.ticks += 1
        index = min(self.ticks - 1, len(self._results) - 1)
        return self._results[index]


def test_pipeline_advances_complete_stages_and_marks_terminal() -> None:
    ctx = MissionContext()
    ready = _ScriptedStage("ready", StageResult.complete("ready_ok", fsm_state="S1 ready"))
    hover = _ScriptedStage("hover", StageResult.complete("hover_ok", fsm_state="S6 hover_hold"))
    pipeline = FlightPipeline([ready, hover])

    first = pipeline.tick(ctx)
    assert first.status == "complete"
    assert pipeline.active_stage.name == "hover"
    assert ctx.state.completed_stages == ["ready"]
    assert ctx.state.active_stage == "hover"
    assert ctx.state.terminal is False

    second = pipeline.tick(ctx)
    assert second.status == "complete"
    assert pipeline.terminal is True
    assert ctx.state.terminal is True
    assert ctx.state.completed_stages == ["ready", "hover"]
    assert ctx.evidence.latest["hover"]["fsm_state"] == "S6 hover_hold"


def test_pipeline_keeps_running_stage_active() -> None:
    ctx = MissionContext()
    stage = _ScriptedStage(
        "runtime_ready",
        StageResult.running("waiting_for_external_nav", fsm_state="S1 wait_nav_ready"),
        StageResult.complete("ready_ok", fsm_state="S1 wait_nav_ready"),
    )
    pipeline = FlightPipeline([stage])

    first = pipeline.tick(ctx)
    assert first.status == "running"
    assert pipeline.active_stage.name == "runtime_ready"
    assert ctx.state.phase_counts["runtime_ready"] == 1
    assert ctx.state.completed_stages == []

    second = pipeline.tick(ctx)
    assert second.status == "complete"
    assert stage.ticks == 2
    assert ctx.state.phase_counts["runtime_ready"] == 2
    assert ctx.state.completed_stages == ["runtime_ready"]


def test_pipeline_keeps_blocked_stage_active_and_records_blocker() -> None:
    ctx = MissionContext()
    stage = _ScriptedStage(
        "takeoff",
        StageResult.blocked(
            "waiting_for_height",
            fsm_state="S4 takeoff",
            evidence={"height_m": 0.1},
        ),
    )
    pipeline = FlightPipeline([stage])

    result = pipeline.tick(ctx)

    assert result.status == "blocked"
    assert pipeline.active_stage.name == "takeoff"
    assert ctx.state.completed_stages == []
    assert ctx.evidence.latest["takeoff"]["blocker"] == "waiting_for_height"
    assert ctx.evidence.latest["takeoff"]["evidence"] == {"height_m": 0.1}


def test_pipeline_records_fsm_transition_when_context_has_recorder() -> None:
    ctx = MissionContext(
        clock=MissionClock(started_at_monotonic=10.0, now_monotonic=12.5),
        fsm=MissionPhaseRecorder(started_at_monotonic=10.0),
    )
    stage = _ScriptedStage("takeoff", StageResult.running("taking_off", fsm_state="S4 takeoff"))
    pipeline = FlightPipeline([stage])

    result = pipeline.tick(ctx)
    snapshot = ctx.fsm.snapshot(now_monotonic=13.0)

    assert result.status == "running"
    assert snapshot.state == "S4 takeoff"
    assert snapshot.state_entered_at_sec == 2.5
    assert snapshot.last_transition_reason == "taking_off"
    assert snapshot.history[-1].guard == "takeoff"


def test_pipeline_enters_safety_path_after_abort() -> None:
    ctx = MissionContext()
    hover = _ScriptedStage("hover", StageResult.abort("hover_unstable", fsm_state="S_abort"))
    landing = _ScriptedStage("landing", StageResult.complete("landed", fsm_state="S12 landing_complete"))
    pipeline = FlightPipeline([hover], safety_stages=[landing])

    abort_result = pipeline.tick(ctx)
    assert abort_result.status == "abort"
    assert pipeline.in_safety_path is True
    assert pipeline.active_stage.name == "landing"
    assert ctx.state.aborted is True
    assert ctx.state.terminal is False

    landing_result = pipeline.tick(ctx)
    assert landing_result.status == "complete"
    assert pipeline.terminal is True
    assert ctx.state.terminal is True
    assert ctx.state.completed_stages == ["landing"]


def test_pipeline_abort_without_safety_path_is_terminal() -> None:
    ctx = MissionContext()
    stage = _ScriptedStage("ready", StageResult.abort("preflight_timeout", fsm_state="S_abort"))
    pipeline = FlightPipeline([stage])

    result = pipeline.tick(ctx)

    assert result.status == "abort"
    assert pipeline.terminal is True
    assert ctx.state.aborted is True
    assert ctx.state.terminal is True


def test_runtime_snapshot_refreshes_context_without_overwriting_hover_owner_fields() -> None:
    ctx = MissionContext()
    ctx.state.hover.hold_x_m = 1.0
    ctx.state.hover.body_ok = True
    snapshot = MissionRuntimeSnapshot(
        now_monotonic=12.0,
        nav=NavState(external_nav_ready=True, slam_quality="good", slam_quality_good=True),
        fcu=FcuState(armed=True, airborne=True, target_system=1, target_component=1),
        pose=PoseState(x_m=0.1, y_m=0.2, z_ned_m=-0.5, fcu_local_height_m=0.5),
        hover=HoverState(airborne_elapsed_sec=3.0, hover_elapsed_sec=2.0),
        command=CommandState(sent_counts={"arm": 1}, accepted_command_ids={22}, command_acks=[{"command": 22}]),
    )

    apply_runtime_snapshot_to_context(ctx, snapshot)

    assert ctx.clock.now_monotonic == 12.0
    assert ctx.state.nav.external_nav_ready is True
    assert ctx.state.fcu.target_system == 1
    assert ctx.state.pose.fcu_local_height_m == 0.5
    assert ctx.state.hover.airborne_elapsed_sec == 3.0
    assert ctx.state.hover.hold_x_m == 1.0
    assert ctx.state.hover.body_ok is True
    assert ctx.state.command.accepted_command_ids == {22}


def test_landing_runtime_snapshot_refreshes_landing_state() -> None:
    ctx = MissionContext()
    snapshot = LandingRuntimeSnapshot(
        now_monotonic=14.0,
        landing=LandingState(
            policy="guided_descent",
            state="guided_descent",
            elapsed_sec=3.0,
            touchdown_ready=True,
            descent_profile_ok=True,
        ),
    )

    apply_landing_runtime_snapshot_to_context(ctx, snapshot)

    assert ctx.clock.now_monotonic == 14.0
    assert ctx.state.landing.policy == "guided_descent"
    assert ctx.state.landing.state == "guided_descent"
    assert ctx.state.landing.elapsed_sec == 3.0
    assert ctx.state.landing.touchdown_ready is True
    assert ctx.state.landing.descent_profile_ok is True


def test_pipeline_rejects_empty_stage_list() -> None:
    with pytest.raises(ValueError, match="requires at least one stage"):
        FlightPipeline([])


def test_hover_pipeline_runner_starts_landing_on_terminal_hover() -> None:
    from navlab.common.companion.mission import HoverEvidenceRecorder, HoverInputs, LandingEvidenceRecorder
    from navlab.common.companion.mission.hover_landing import (
        HoverMissionPipelineRunner,
        HoverPipelineConfig,
        HoverTickRuntime,
    )

    ctx = MissionContext(clock=MissionClock(started_at_monotonic=10.0, now_monotonic=16.0))
    ctx.state.pose.x_m = 1.0
    ctx.state.pose.y_m = 2.0
    ctx.state.pose.yaw_rad = 0.5
    prefix = FlightPipeline([_ScriptedStage("takeoff", StageResult.complete("takeoff_ok"))])
    hover_stage = _ScriptedStage(
        "hover_hold",
        StageResult.complete("hover_complete", fsm_state="S8 hover_complete", evidence={"phase": "complete"}),
    )
    runner = HoverMissionPipelineRunner(
        prefix_pipeline=prefix,
        hover_stage=hover_stage,
        landing_stage=_ScriptedStage("landing", StageResult.running("pre_land_hold")),
        hover_evidence=HoverEvidenceRecorder(),
        landing_evidence=LandingEvidenceRecorder(),
        hover_config=HoverPipelineConfig(
            max_wait_ready_sec=35.0,
            takeoff_alt_m=0.45,
            hover_altitude_tolerance_m=0.18,
            hover_hold_sec=20.0,
            duration_tolerance_sec=0.25,
            max_horizontal_drift_m=0.3,
            hover_span_target_m=0.3,
            hover_span_hard_cap_m=0.3,
            max_altitude_drift_m=0.25,
        ),
    )
    fsm_events: list[tuple[str, str, str | None]] = []
    published: list[str] = []
    landing_starts: list[tuple[float, str]] = []

    def record_fsm(
        now: float, state: str, reason: str, *, guard: str | None = None, blocker: str | None = None
    ) -> None:
        fsm_events.append((state, reason, blocker))

    def publish_status(decision, inputs) -> None:
        published.append(decision.phase)

    def begin_landing(now: float, completion) -> None:
        landing_starts.append((now, completion.reason))

    runtime = HoverTickRuntime(
        now_monotonic=16.0,
        inputs=HoverInputs(
            external_nav_ready=True,
            mavlink_external_nav_ready=True,
            fcu_local_position_ready=True,
            imu_ready=True,
            slam_quality_good=True,
            slam_quality="good",
            ready_elapsed_sec=5.0,
            current_yaw_rad=0.5,
            expected_mode_seen=True,
            armed_seen=True,
            airborne_seen=True,
            takeoff_ack_ok=True,
            airborne_elapsed_sec=5.0,
            hover_elapsed_sec=20.0,
            current_x=1.0,
            current_y=2.0,
            current_z_ned=-0.45,
            current_height_m=0.45,
            external_nav_height_m=0.45,
            rangefinder_relative_height_m=0.45,
            target_z_ned=-0.45,
        ),
        local_position_count=1,
        crash_detected=False,
    )

    outcome = runner.tick_hover(
        ctx,
        runtime,
        record_fsm=record_fsm,
        publish_status=publish_status,
        begin_landing=begin_landing,
    )

    assert outcome.status == "landing_started"
    assert runner.landing_started is True
    assert published == ["complete"]
    assert landing_starts == [(16.0, "hover_samples_missing")]
    assert ctx.state.hover.body_ok is False
    assert ctx.state.hover.body_reason == "hover_samples_missing"
    assert fsm_events[-1] == ("S7 pre_land_hold", "hover_complete", None)


def test_landing_pipeline_runner_interprets_stage_complete_and_task_success() -> None:
    from navlab.common.companion.mission import HoverEvidenceRecorder, LandingEvidenceRecorder
    from navlab.common.companion.mission.hover_landing import (
        HoverMissionPipelineRunner,
        HoverPipelineConfig,
        LandingTickPreparation,
    )

    ctx = MissionContext(clock=MissionClock(started_at_monotonic=10.0, now_monotonic=20.0))
    ctx.state.hover.body_ok = True
    ctx.state.hover.body_reason = "hover_complete"
    landing_evidence = LandingEvidenceRecorder()
    landing_evidence.start(20.0, state="touchdown_candidate")
    landing_stage = _ScriptedStage(
        "landing",
        StageResult.complete(
            "landing_complete", fsm_state="S12 landing_complete", evidence={"state": "landing_complete"}
        ),
    )
    runner = HoverMissionPipelineRunner(
        prefix_pipeline=FlightPipeline([_ScriptedStage("prefix", StageResult.complete("ok"))]),
        hover_stage=_ScriptedStage("hover", StageResult.running("holding")),
        landing_stage=landing_stage,
        hover_evidence=HoverEvidenceRecorder(),
        landing_evidence=landing_evidence,
        hover_config=HoverPipelineConfig(
            max_wait_ready_sec=35.0,
            takeoff_alt_m=0.45,
            hover_altitude_tolerance_m=0.18,
            hover_hold_sec=20.0,
            duration_tolerance_sec=0.25,
            max_horizontal_drift_m=0.3,
            hover_span_target_m=0.3,
            hover_span_hard_cap_m=0.3,
            max_altitude_drift_m=0.25,
        ),
    )
    fsm_events: list[tuple[str, str, str | None]] = []

    def record_fsm(
        now: float, state: str, reason: str, *, guard: str | None = None, blocker: str | None = None
    ) -> None:
        fsm_events.append((state, reason, guard))

    def prepare(now: float) -> LandingTickPreparation:
        return LandingTickPreparation(
            target_available=True,
            snapshot=LandingRuntimeSnapshot(now_monotonic=now, landing=LandingState(state="touchdown_candidate")),
        )

    outcome = runner.tick_landing(ctx, now_monotonic=21.0, prepare_landing_tick=prepare, record_fsm=record_fsm)

    assert outcome.status == "complete"
    assert outcome.summary_ok is True
    assert outcome.summary_landing_ok is True
    assert outcome.shutdown is True
    assert outcome.record_task_success is True
    assert landing_evidence.state == "landing_complete"
    assert fsm_events == [("S12 landing_complete", "landing_complete", "landing_complete")]


def test_landing_pipeline_runner_handles_missing_target_as_abort() -> None:
    from navlab.common.companion.mission import HoverEvidenceRecorder, LandingEvidenceRecorder
    from navlab.common.companion.mission.hover_landing import (
        HoverMissionPipelineRunner,
        HoverPipelineConfig,
        LandingTickPreparation,
    )

    ctx = MissionContext()
    landing_evidence = LandingEvidenceRecorder()
    runner = HoverMissionPipelineRunner(
        prefix_pipeline=FlightPipeline([_ScriptedStage("prefix", StageResult.complete("ok"))]),
        hover_stage=_ScriptedStage("hover", StageResult.running("holding")),
        landing_stage=_ScriptedStage("landing", StageResult.running("pre_land_hold")),
        hover_evidence=HoverEvidenceRecorder(),
        landing_evidence=landing_evidence,
        hover_config=HoverPipelineConfig(
            max_wait_ready_sec=35.0,
            takeoff_alt_m=0.45,
            hover_altitude_tolerance_m=0.18,
            hover_hold_sec=20.0,
            duration_tolerance_sec=0.25,
            max_horizontal_drift_m=0.3,
            hover_span_target_m=0.3,
            hover_span_hard_cap_m=0.3,
            max_altitude_drift_m=0.25,
        ),
    )
    fsm_events: list[tuple[str, str, str | None]] = []

    def record_fsm(
        now: float, state: str, reason: str, *, guard: str | None = None, blocker: str | None = None
    ) -> None:
        fsm_events.append((state, reason, blocker))

    outcome = runner.tick_landing(
        ctx,
        now_monotonic=22.0,
        prepare_landing_tick=lambda now: LandingTickPreparation(target_available=False),
        record_fsm=record_fsm,
    )

    assert outcome.status == "abort"
    assert outcome.reason == "landing_target_system_missing"
    assert outcome.publish_status is False
    assert outcome.shutdown is True
    assert landing_evidence.blockers == ["landing_target_system_missing"]
    assert fsm_events == [("S_abort", "landing_target_system_missing", "landing_target_system_missing")]
