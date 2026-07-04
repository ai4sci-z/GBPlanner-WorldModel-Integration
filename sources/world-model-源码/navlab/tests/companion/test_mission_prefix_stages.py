from __future__ import annotations

from navlab.common.companion.mission import (
    LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER,
    LANDING_POLICY_GUIDED_DESCENT,
    ArmStage,
    FlightPipeline,
    FlightPrefixConfig,
    GuidedModeStage,
    HoverHoldConfig,
    HoverHoldStage,
    LandingStage,
    LandingStageConfig,
    MissionClock,
    MissionContext,
    RuntimeReadyStage,
    TakeoffStage,
)


class _RecordingCommandAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def request_guided_mode(self, ctx: MissionContext) -> bool:
        self.calls.append(f"guided:{ctx.clock.now_monotonic}")
        return True

    def request_arm(self, ctx: MissionContext) -> bool:
        self.calls.append(f"arm:{ctx.clock.now_monotonic}")
        return True

    def request_takeoff(self, ctx: MissionContext) -> bool:
        self.calls.append(f"takeoff:{ctx.clock.now_monotonic}")
        return True

    def send_hold_setpoint(self, ctx: MissionContext) -> bool:
        self.calls.append(f"hold:{ctx.clock.now_monotonic}")
        return True

    def send_landing_descent_setpoint(self, ctx: MissionContext) -> bool:
        self.calls.append(f"landing_descent:{ctx.clock.now_monotonic}")
        return True

    def request_land(self, ctx: MissionContext) -> bool:
        self.calls.append(f"land:{ctx.clock.now_monotonic}")
        ctx.state.landing.land_command_sent = True
        return True

    def request_disarm(self, ctx: MissionContext) -> bool:
        self.calls.append(f"disarm:{ctx.clock.now_monotonic}")
        return True


def _ready_context() -> MissionContext:
    ctx = MissionContext(clock=MissionClock(started_at_monotonic=10.0, now_monotonic=16.0))
    ctx.state.nav.external_nav_ready = True
    ctx.state.nav.mavlink_external_nav_ready = True
    ctx.state.nav.fcu_local_position_ready = True
    ctx.state.nav.imu_ready = True
    ctx.state.nav.slam_quality = "good"
    ctx.state.nav.slam_quality_good = True
    ctx.state.nav.ready_elapsed_sec = 5.0
    ctx.state.pose.yaw_rad = 0.0
    return ctx


def test_runtime_ready_stage_preserves_preflight_timeout_gate() -> None:
    ctx = MissionContext(clock=MissionClock(started_at_monotonic=10.0, now_monotonic=50.0))
    ctx.state.nav.ready_elapsed_sec = 0.0
    ctx.state.pose.yaw_rad = 0.0
    stage = RuntimeReadyStage(FlightPrefixConfig(max_wait_ready_sec=35.0))

    result = stage.tick(ctx)

    assert result.status == "abort"
    assert result.reason == "preflight_timeout"
    assert result.blocker == "waiting_for_slam_quality"
    assert result.fsm_state == "S1 wait_nav_ready"


def test_prefix_pipeline_advances_ready_guided_arm_takeoff() -> None:
    ctx = _ready_context()
    ctx.state.fcu.expected_mode_seen = True
    ctx.state.fcu.armed = True
    ctx.state.fcu.airborne = True
    ctx.state.fcu.takeoff_ack_ok = True
    ctx.state.hover.airborne_elapsed_sec = 3.0
    ctx.state.pose.external_nav_height_m = 0.45
    ctx.state.pose.rangefinder_relative_height_m = 0.45
    ctx.state.pose.z_ned_m = -0.45
    ctx.state.pose.target_z_ned_m = -0.45

    pipeline = FlightPipeline(
        [
            RuntimeReadyStage(FlightPrefixConfig()),
            GuidedModeStage(),
            ArmStage(),
            TakeoffStage(FlightPrefixConfig()),
        ]
    )

    assert pipeline.tick(ctx).status == "complete"
    assert pipeline.tick(ctx).status == "complete"
    assert pipeline.tick(ctx).status == "complete"
    assert pipeline.tick(ctx).status == "complete"
    assert pipeline.terminal is True
    assert ctx.state.completed_stages == ["runtime_ready", "guided", "arm", "takeoff"]


def test_guided_stage_aborts_if_mode_is_lost_after_airborne() -> None:
    ctx = _ready_context()
    ctx.state.fcu.airborne = True
    stage = GuidedModeStage()

    result = stage.tick(ctx)

    assert result.status == "abort"
    assert result.reason == "guided_mode_lost_after_airborne"
    assert result.blocker == "guided_mode_lost_after_airborne"


def test_arm_stage_requests_arm_until_confirmed() -> None:
    ctx = _ready_context()
    stage = ArmStage()

    result = stage.tick(ctx)

    assert result.status == "running"
    assert result.reason == "arming_vehicle"
    assert result.evidence["should_arm"] is True


def test_prefix_stages_call_command_adapter_when_waiting() -> None:
    ctx = _ready_context()
    adapter = _RecordingCommandAdapter()
    ctx.io.command_adapter = adapter

    guided = GuidedModeStage().tick(ctx)
    armed = ArmStage().tick(ctx)
    takeoff = TakeoffStage(FlightPrefixConfig()).tick(ctx)

    assert guided.evidence["command_sent"] is True
    assert armed.evidence["command_sent"] is True
    assert takeoff.evidence["command_sent"] is True
    assert adapter.calls == ["guided:16.0", "arm:16.0", "takeoff:16.0"]


def test_takeoff_stage_allows_independent_height_fallback_without_ack() -> None:
    ctx = _ready_context()
    ctx.state.fcu.armed = True
    ctx.state.fcu.airborne = True
    ctx.state.fcu.takeoff_ack_ok = False
    ctx.state.pose.external_nav_height_m = 0.44
    ctx.state.pose.rangefinder_relative_height_m = 0.45
    stage = TakeoffStage(FlightPrefixConfig(takeoff_alt_m=0.45, hover_altitude_tolerance_m=0.18))

    result = stage.tick(ctx)

    assert result.status == "complete"
    assert result.reason == "takeoff_height_confirmed_without_ack"
    assert result.evidence["takeoff_ack_ok"] is False


def test_takeoff_stage_waits_for_independent_height_after_airborne() -> None:
    ctx = _ready_context()
    ctx.state.fcu.armed = True
    ctx.state.fcu.airborne = True
    ctx.state.fcu.takeoff_ack_ok = True
    ctx.state.pose.external_nav_height_m = 0.0
    ctx.state.pose.rangefinder_relative_height_m = 0.0
    stage = TakeoffStage(FlightPrefixConfig(takeoff_alt_m=0.45, hover_altitude_tolerance_m=0.18))

    result = stage.tick(ctx)

    assert result.status == "running"
    assert result.reason == "waiting_for_independent_takeoff_height"


def test_hover_hold_stage_requests_hold_setpoint_only_in_hover_hold() -> None:
    ctx = _ready_context()
    adapter = _RecordingCommandAdapter()
    ctx.io.command_adapter = adapter
    ctx.state.fcu.expected_mode_seen = True
    ctx.state.fcu.armed = True
    ctx.state.fcu.airborne = True
    ctx.state.fcu.takeoff_ack_ok = True
    ctx.state.hover.airborne_elapsed_sec = 4.0
    ctx.state.hover.hover_elapsed_sec = 3.0
    ctx.state.pose.z_ned_m = -0.45
    ctx.state.pose.target_z_ned_m = -0.45
    ctx.state.pose.external_nav_height_m = 0.45
    ctx.state.pose.rangefinder_relative_height_m = 0.45
    stage = HoverHoldStage(
        HoverHoldConfig(
            preflight_ready_sec=5.0,
            hover_settle_sec=2.0,
            hover_hold_sec=20.0,
            takeoff_alt_m=0.45,
            hover_altitude_tolerance_m=0.18,
            send_position_setpoints=True,
        )
    )

    result = stage.tick(ctx)

    assert result.status == "running"
    assert result.reason == "hover_health_waiting_min_observation"
    assert result.evidence["phase"] == "hover_hold"
    assert result.evidence["hover_health"]["phase"] == "hover_health_hold"
    assert result.evidence["should_send_hold_setpoint"] is True
    assert result.evidence["command_sent"] is True
    assert adapter.calls == ["hold:16.0"]


def test_hover_hold_stage_does_not_send_setpoint_before_hover_hold() -> None:
    ctx = _ready_context()
    adapter = _RecordingCommandAdapter()
    ctx.io.command_adapter = adapter
    ctx.state.fcu.expected_mode_seen = True
    ctx.state.fcu.armed = True
    ctx.state.fcu.airborne = True
    ctx.state.fcu.takeoff_ack_ok = True
    ctx.state.hover.airborne_elapsed_sec = 0.5
    ctx.state.hover.hover_elapsed_sec = 0.0
    ctx.state.pose.z_ned_m = -0.45
    ctx.state.pose.target_z_ned_m = -0.45
    ctx.state.pose.external_nav_height_m = 0.45
    ctx.state.pose.rangefinder_relative_height_m = 0.45
    stage = HoverHoldStage(HoverHoldConfig(hover_settle_sec=2.0, hover_hold_sec=20.0))

    result = stage.tick(ctx)

    assert result.status == "running"
    assert result.reason == "settling_before_position_hold"
    assert result.evidence["should_send_hold_setpoint"] is False
    assert adapter.calls == []


def test_landing_stage_pre_land_hold_sends_hold_setpoint() -> None:
    ctx = _ready_context()
    adapter = _RecordingCommandAdapter()
    ctx.io.command_adapter = adapter
    ctx.state.landing.elapsed_sec = 0.5
    stage = LandingStage(LandingStageConfig(pre_land_hold_sec=1.0))

    result = stage.tick(ctx)

    assert result.status == "running"
    assert result.reason == "pre_land_hold"
    assert result.evidence["state"] == "pre_land_hold"
    assert adapter.calls == ["hold:16.0"]


def test_landing_stage_ap_land_policy_requests_land_immediately() -> None:
    ctx = _ready_context()
    adapter = _RecordingCommandAdapter()
    ctx.io.command_adapter = adapter
    ctx.state.landing.elapsed_sec = 2.0
    ctx.state.landing.command_due = True
    stage = LandingStage(
        LandingStageConfig(
            landing_policy=LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER,
            pre_land_hold_sec=1.0,
        )
    )

    result = stage.tick(ctx)

    assert result.status == "running"
    assert result.evidence["state"] == "land_command_sent"
    assert result.evidence["land_command_sent_this_tick"] is True
    assert adapter.calls == ["land:16.0"]


def test_landing_stage_guided_policy_descends_before_touchdown() -> None:
    ctx = _ready_context()
    adapter = _RecordingCommandAdapter()
    ctx.io.command_adapter = adapter
    ctx.state.landing.elapsed_sec = 2.0
    stage = LandingStage(
        LandingStageConfig(
            landing_policy=LANDING_POLICY_GUIDED_DESCENT,
            pre_land_hold_sec=1.0,
        )
    )

    result = stage.tick(ctx)

    assert result.status == "running"
    assert result.reason == "guided_descent"
    assert result.evidence["state"] == "guided_descent"
    assert adapter.calls == ["landing_descent:16.0"]


def test_landing_stage_completes_when_acceptance_is_met() -> None:
    ctx = _ready_context()
    ctx.state.landing.elapsed_sec = 2.0
    ctx.state.landing.land_command_sent = True
    ctx.state.landing.land_command_accepted = True
    ctx.state.landing.land_mode_seen = True
    ctx.state.landing.touchdown_confirmed = True
    ctx.state.landing.disarmed = True
    ctx.state.landing.motors_safe = True
    ctx.state.landing.descent_profile_ok = False
    stage = LandingStage(
        LandingStageConfig(
            landing_policy=LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER,
            pre_land_hold_sec=1.0,
        )
    )

    result = stage.tick(ctx)

    assert result.status == "complete"
    assert result.reason == "landing_complete"
    assert result.evidence["state"] == "landing_complete"
