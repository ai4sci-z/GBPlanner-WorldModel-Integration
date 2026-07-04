from __future__ import annotations

from math import isclose

from pymavlink.dialects.v20 import ardupilotmega as mavlink

from navlab.common.companion.mission.context import MissionClock, MissionContext
from navlab.common.companion.mission.evidence.hover import (
    classify_hover_drift,
    summarize_hover_altitude_crosscheck,
    summarize_hover_drift,
)
from navlab.common.companion.mission.evidence.landing import (
    landing_descent_evidence_height_and_source_m,
    landing_descent_evidence_height_m,
    landing_descent_height_m,
    landing_descent_target_z_ned,
    landing_effective_descent_rate_mps,
    landing_touchdown_candidate,
    summarize_landing_descent_profile,
)
from navlab.common.companion.mission.fsm import (
    MissionPhaseRecorder,
    mission_phase_state_for_hover_phase,
    mission_phase_state_for_landing_state,
)
from navlab.common.companion.mission.runtime_state import append_bounded_statustext, statustext_indicates_crash
from navlab.common.companion.mission.stages.hover import (
    HoverHealthGateConfig,
    HoverHoldConfig,
    HoverHoldStage,
    HoverInputs,
    HoverRequirements,
    capture_hold_anchor,
    decide_hover,
    height_reaches_target,
    hold_axis_or_current,
    hold_yaw_or_current,
    hover_hold_setpoint_axes,
    independent_takeoff_height_reached,
    should_fail_fast_wait_ready,
    should_send_position_hold_setpoint,
)
from navlab.common.companion.mission.stages.landing import (
    fcu_land_params_report,
    landing_acceptance_ok,
    landing_controller_for_state,
    landing_descent_profile_enforced,
    landing_policy_uses_ap_land_mode,
    should_command_land_this_tick,
    should_send_disarm_after_touchdown,
    should_use_guided_descent_before_land,
)
from navlab.sim.companion.mission.mavlink_commands import (
    append_bounded_command_ack,
    command_ack_accepted,
    command_ack_success,
    mavlink_param_id_to_str,
)
from navlab.sim.companion.mission.mavlink_commands import (
    command_disarm as _command_disarm,
)
from navlab.sim.companion.mission.mavlink_commands import (
    command_land as _command_land,
)
from navlab.sim.companion.mission.mavlink_commands import (
    request_param_read as _request_param_read,
)


class _FakeMav:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def command_long_send(self, *args: object) -> None:
        self.calls.append(args)

    def param_request_read_send(self, *args: object) -> None:
        self.calls.append(("param_request_read_send", *args))


class _FakeConnection:
    def __init__(self) -> None:
        self.mav = _FakeMav()


def _inputs(**overrides) -> HoverInputs:
    values = {
        "external_nav_ready": True,
        "mavlink_external_nav_ready": True,
        "fcu_local_position_ready": True,
        "imu_ready": True,
        "slam_quality_good": True,
        "slam_quality": "good",
        "ready_elapsed_sec": 5.0,
        "current_yaw_rad": 0.0,
        "expected_mode_seen": True,
        "armed_seen": True,
        "airborne_seen": True,
        "takeoff_ack_ok": True,
        "airborne_elapsed_sec": 10.0,
        "hover_elapsed_sec": 20.0,
        "current_x": 0.0,
        "current_y": 0.0,
        "current_z_ned": -0.45,
        "current_height_m": 0.45,
        "external_nav_height_m": 0.45,
        "rangefinder_relative_height_m": 0.45,
        "target_z_ned": -0.45,
        "slam_quality_loss_duration_sec": 0.0,
        "external_nav_loss_duration_sec": 0.0,
        "mavlink_external_nav_loss_duration_sec": 0.0,
        "fcu_local_position_loss_duration_sec": 0.0,
    }
    values.update(overrides)
    return HoverInputs(**values)


def _hover_context(inputs: HoverInputs, *, now: float = 10.0) -> MissionContext:
    ctx = MissionContext(clock=MissionClock(started_at_monotonic=0.0, now_monotonic=now))
    ctx.state.nav.external_nav_ready = inputs.external_nav_ready
    ctx.state.nav.mavlink_external_nav_ready = inputs.mavlink_external_nav_ready
    ctx.state.nav.fcu_local_position_ready = inputs.fcu_local_position_ready
    ctx.state.nav.imu_ready = inputs.imu_ready
    ctx.state.nav.slam_quality_good = inputs.slam_quality_good
    ctx.state.nav.slam_quality = inputs.slam_quality
    ctx.state.nav.ready_elapsed_sec = inputs.ready_elapsed_sec
    ctx.state.nav.slam_quality_loss_duration_sec = inputs.slam_quality_loss_duration_sec
    ctx.state.nav.external_nav_loss_duration_sec = inputs.external_nav_loss_duration_sec
    ctx.state.nav.mavlink_external_nav_loss_duration_sec = inputs.mavlink_external_nav_loss_duration_sec
    ctx.state.nav.fcu_local_position_loss_duration_sec = inputs.fcu_local_position_loss_duration_sec
    ctx.state.fcu.expected_mode_seen = inputs.expected_mode_seen
    ctx.state.fcu.armed = inputs.armed_seen
    ctx.state.fcu.airborne = inputs.airborne_seen
    ctx.state.fcu.takeoff_ack_ok = inputs.takeoff_ack_ok
    ctx.state.pose.yaw_rad = inputs.current_yaw_rad
    ctx.state.pose.x_m = inputs.current_x
    ctx.state.pose.y_m = inputs.current_y
    ctx.state.pose.z_ned_m = inputs.current_z_ned
    ctx.state.pose.height_m = inputs.current_height_m
    ctx.state.pose.external_nav_height_m = inputs.external_nav_height_m
    ctx.state.pose.rangefinder_relative_height_m = inputs.rangefinder_relative_height_m
    ctx.state.pose.target_z_ned_m = inputs.target_z_ned
    ctx.state.hover.airborne_elapsed_sec = inputs.airborne_elapsed_sec
    ctx.state.hover.hover_elapsed_sec = inputs.hover_elapsed_sec
    return ctx


def _hover_health_stage(
    *,
    min_observation_sec: float = 1.0,
    stable_required_sec: float = 1.0,
    max_wait_sec: float = 10.0,
    operator_confirm_required: bool = False,
    operator_confirm_timeout_sec: float = 10.0,
) -> HoverHoldStage:
    return HoverHoldStage(
        HoverHoldConfig(
            preflight_ready_sec=5.0,
            hover_settle_sec=2.0,
            hover_hold_sec=20.0,
            takeoff_alt_m=0.45,
            hover_altitude_tolerance_m=0.18,
            health_gate=HoverHealthGateConfig(
                min_observation_sec=min_observation_sec,
                stable_required_sec=stable_required_sec,
                max_wait_sec=max_wait_sec,
                operator_confirm_required=operator_confirm_required,
                operator_confirm_timeout_sec=operator_confirm_timeout_sec,
            ),
        )
    )


def test_hover_decision_waits_then_guided_arm_takeoff_hold_complete() -> None:
    assert decide_hover(
        _inputs(external_nav_ready=False, armed_seen=False, airborne_seen=False),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    ).phase == ("wait_ready")
    assert (
        decide_hover(
            _inputs(
                mavlink_external_nav_ready=False,
                fcu_local_position_ready=False,
                armed_seen=False,
                airborne_seen=False,
            ),
            preflight_ready_sec=5.0,
            hover_settle_sec=2.0,
            hover_hold_sec=20.0,
            takeoff_alt_m=0.45,
            hover_altitude_tolerance_m=0.18,
        ).reason
        == "waiting_for_fcu_external_nav"
    )
    assert (
        decide_hover(
            _inputs(ready_elapsed_sec=4.9, airborne_seen=False),
            preflight_ready_sec=5.0,
            hover_settle_sec=2.0,
            hover_hold_sec=20.0,
            takeoff_alt_m=0.45,
            hover_altitude_tolerance_m=0.18,
        ).reason
        == "waiting_for_stable_external_nav_and_imu"
    )
    assert (
        decide_hover(
            _inputs(slam_quality_good=False, slam_quality="uncertain", airborne_seen=False),
            preflight_ready_sec=5.0,
            hover_settle_sec=2.0,
            hover_hold_sec=20.0,
            takeoff_alt_m=0.45,
            hover_altitude_tolerance_m=0.18,
        ).reason
        == "waiting_for_slam_quality"
    )
    assert (
        decide_hover(
            _inputs(current_yaw_rad=None),
            preflight_ready_sec=5.0,
            hover_settle_sec=2.0,
            hover_hold_sec=20.0,
            takeoff_alt_m=0.45,
            hover_altitude_tolerance_m=0.18,
        ).reason
        == "waiting_for_fcu_attitude"
    )

    guided = decide_hover(
        _inputs(expected_mode_seen=False, armed_seen=False, airborne_seen=False),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    arm = decide_hover(
        _inputs(armed_seen=False, airborne_seen=False),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    takeoff = decide_hover(
        _inputs(airborne_seen=False),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    disarmed_after_airborne = decide_hover(
        _inputs(armed_seen=False, airborne_seen=True),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    hold_without_takeoff_ack_but_with_independent_height = decide_hover(
        _inputs(takeoff_ack_ok=False, hover_elapsed_sec=19.9, external_nav_height_m=0.44),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    settle = decide_hover(
        _inputs(airborne_elapsed_sec=1.9),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    altitude_settle = decide_hover(
        _inputs(
            current_z_ned=-0.2,
            current_height_m=0.2,
            external_nav_height_m=0.2,
            rangefinder_relative_height_m=0.2,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    hold = decide_hover(
        _inputs(hover_elapsed_sec=19.9),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    complete = decide_hover(
        _inputs(hover_elapsed_sec=20.0),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert guided.should_set_guided is True
    assert arm.should_arm is True
    assert takeoff.should_takeoff is True
    assert disarmed_after_airborne.phase == "abort"
    assert disarmed_after_airborne.reason == "disarmed_after_airborne"
    assert disarmed_after_airborne.terminal is True
    assert hold_without_takeoff_ack_but_with_independent_height.phase == "hover_hold"
    assert hold_without_takeoff_ack_but_with_independent_height.reason == "holding_position_with_independent_height"
    assert hold_without_takeoff_ack_but_with_independent_height.should_takeoff is False
    assert settle.phase == "hover_settle"
    assert altitude_settle.reason == "waiting_for_independent_takeoff_height"
    assert hold.phase == "hover_hold"
    assert complete.terminal is True


def test_hover_health_gate_delays_sim_completion_until_stable_window() -> None:
    stage = _hover_health_stage(min_observation_sec=1.0, stable_required_sec=1.0)
    ctx = _hover_context(_inputs(hover_elapsed_sec=20.0), now=10.0)

    waiting = stage.tick(ctx)
    ctx.clock.now_monotonic = 11.0
    complete = stage.tick(ctx)

    assert waiting.status == "running"
    assert waiting.evidence["phase"] == "hover_hold"
    assert waiting.evidence["hover_health"]["phase"] == "hover_health_hold"
    assert waiting.evidence["hover_health"]["reason"] == "hover_health_waiting_min_observation"
    assert complete.status == "complete"
    assert complete.evidence["hover_health"]["phase"] == "sim_auto_continue"
    assert complete.evidence["hover_health"]["sim_auto_continue_allowed"] is True


def test_hover_health_gate_does_not_shortcut_existing_hover_duration() -> None:
    stage = _hover_health_stage(min_observation_sec=0.0, stable_required_sec=0.0)
    ctx = _hover_context(_inputs(hover_elapsed_sec=19.0), now=10.0)

    waiting = stage.tick(ctx)

    assert waiting.status == "running"
    assert waiting.reason == "hover_health_waiting_hover_duration"
    assert waiting.evidence["hover_health"]["sim_auto_continue_allowed"] is False


def test_hover_health_gate_resets_stable_window_on_yellow_sample() -> None:
    stage = _hover_health_stage(min_observation_sec=0.0, stable_required_sec=1.0)
    ctx = _hover_context(_inputs(hover_elapsed_sec=20.0), now=10.0)

    assert stage.tick(ctx).status == "running"
    ctx.clock.now_monotonic = 10.5
    ctx.state.nav.slam_quality_good = False
    yellow = stage.tick(ctx)
    ctx.clock.now_monotonic = 11.5
    ctx.state.nav.slam_quality_good = True
    still_waiting = stage.tick(ctx)
    ctx.clock.now_monotonic = 12.5
    complete = stage.tick(ctx)

    assert yellow.evidence["hover_health"]["band"] == "yellow"
    assert yellow.evidence["hover_health"]["blockers"] == ["slam_quality_not_green"]
    assert still_waiting.status == "running"
    assert still_waiting.evidence["hover_health"]["stable_sec"] == 0.0
    assert complete.status == "complete"


def test_hover_health_gate_waits_for_operator_confirm_after_green() -> None:
    stage = _hover_health_stage(
        min_observation_sec=0.0,
        stable_required_sec=0.0,
        operator_confirm_required=True,
    )
    ctx = _hover_context(_inputs(hover_elapsed_sec=20.0), now=10.0)

    waiting = stage.tick(ctx)
    ctx.state.hover.operator_confirm_received = True
    ctx.clock.now_monotonic = 10.1
    complete = stage.tick(ctx)

    assert waiting.status == "running"
    assert waiting.reason == "waiting_for_operator_confirm"
    assert waiting.evidence["hover_health"]["phase"] == "operator_confirm"
    assert waiting.evidence["hover_health"]["real_operator_confirm_allowed"] is True
    assert complete.status == "complete"
    assert complete.evidence["hover_health"]["phase"] == "operator_confirmed"


def test_hover_health_gate_blocks_operator_confirm_when_red() -> None:
    stage = _hover_health_stage(
        min_observation_sec=0.0,
        stable_required_sec=0.0,
        operator_confirm_required=True,
    )
    ctx = _hover_context(_inputs(hover_elapsed_sec=20.0), now=10.0)

    waiting = stage.tick(ctx)
    ctx.clock.now_monotonic = 10.5
    ctx.state.nav.external_nav_ready = False
    ctx.state.nav.external_nav_loss_duration_sec = 1.0
    ctx.state.hover.operator_confirm_received = True
    blocked = stage.tick(ctx)

    assert waiting.evidence["hover_health"]["phase"] == "operator_confirm"
    assert blocked.status == "abort"
    assert blocked.reason == "external_nav_lost_after_airborne"
    assert blocked.evidence["hover_health"]["band"] == "red"
    assert blocked.evidence["hover_health"]["operator_confirm_allowed"] is False


def test_hover_phases_map_to_mission_phase_states() -> None:
    assert mission_phase_state_for_hover_phase("wait_ready") == "S1 wait_nav_ready"
    assert mission_phase_state_for_hover_phase("guided") == "S2 set_guided"
    assert mission_phase_state_for_hover_phase("arm") == "S3 arm"
    assert mission_phase_state_for_hover_phase("takeoff") == "S4 takeoff"
    assert mission_phase_state_for_hover_phase("hover_settle") == "S5 hover_settle"
    assert mission_phase_state_for_hover_phase("hover_hold") == "S6 hover_hold"
    assert mission_phase_state_for_hover_phase("complete") == "S7 pre_land_hold"
    assert mission_phase_state_for_hover_phase("abort") == "S_abort"
    assert mission_phase_state_for_hover_phase("unknown") == "S_abort"


def test_landing_states_map_to_mission_phase_states_without_promoting_guided_descent() -> None:
    assert mission_phase_state_for_landing_state("task_body_complete") == "S7 pre_land_hold"
    assert mission_phase_state_for_landing_state("pre_land_hold") == "S7 pre_land_hold"
    assert mission_phase_state_for_landing_state("guided_descent") == "legacy_guided_descent_diagnostic"
    assert mission_phase_state_for_landing_state("land_command_sent") == "S8 command_land"
    assert mission_phase_state_for_landing_state("descent_monitoring") == "S9 land_mode_monitor"
    assert mission_phase_state_for_landing_state("touchdown_candidate") == "S10 touchdown_monitor"
    assert mission_phase_state_for_landing_state("disarm_requested") == "S11 disarm_monitor"
    assert mission_phase_state_for_landing_state("landing_complete") == "S12 landing_complete"
    assert mission_phase_state_for_landing_state("bad_state") == "S_abort"
    assert landing_controller_for_state("guided_descent") == "guided_descent"
    assert landing_controller_for_state("descent_monitoring") == "guided_descent"
    assert (
        landing_controller_for_state(
            "descent_monitoring",
            landing_policy="ap_land_mode_after_hover",
        )
        == "ap_land_mode"
    )


def test_mission_phase_recorder_tracks_entry_exit_reason_and_blocker() -> None:
    recorder = MissionPhaseRecorder(started_at_monotonic=10.0)

    recorder.transition(now_monotonic=11.0, state="S1 wait_nav_ready", reason="waiting_for_slam_quality")
    recorder.transition(now_monotonic=13.5, state="S2 set_guided", reason="setting_guided", guard="guided")
    recorder.transition(
        now_monotonic=14.0,
        state="S_abort",
        reason="guided_mode_lost_after_airborne",
        guard="abort",
        blocker="guided_mode_lost_after_airborne",
    )

    snapshot = recorder.snapshot(now_monotonic=15.0)

    assert snapshot.state == "S_abort"
    assert snapshot.state_entered_at_sec == 4.0
    assert snapshot.last_transition_reason == "guided_mode_lost_after_airborne"
    assert snapshot.blocker == "guided_mode_lost_after_airborne"
    history = snapshot.history
    assert history[0].state == "S0 wait_runtime"
    assert history[0].exited_at_sec == 1.0
    assert history[1].state == "S1 wait_nav_ready"
    assert history[1].duration_sec == 2.5
    assert history[-1].state == "S_abort"
    assert history[-1].exited_at_sec is None


def test_ap_land_mode_policy_skips_guided_descent_and_commands_land_immediately() -> None:
    assert landing_policy_uses_ap_land_mode("ap_land_mode_after_hover")
    assert not should_use_guided_descent_before_land(
        landing_policy="ap_land_mode_after_hover",
        land_command_sent=False,
        touchdown_ready=False,
    )
    assert should_command_land_this_tick(
        landing_policy="ap_land_mode_after_hover",
        land_command_sent=False,
        touchdown_ready=False,
        command_due=False,
    )


def test_legacy_guided_descent_policy_still_waits_for_touchdown_before_land_command() -> None:
    assert should_use_guided_descent_before_land(
        landing_policy="guided_descent",
        land_command_sent=False,
        touchdown_ready=False,
    )
    assert not should_command_land_this_tick(
        landing_policy="guided_descent",
        land_command_sent=False,
        touchdown_ready=False,
        command_due=False,
    )
    assert should_command_land_this_tick(
        landing_policy="guided_descent",
        land_command_sent=False,
        touchdown_ready=True,
        command_due=False,
    )


def test_land_command_sends_mav_cmd_nav_land() -> None:
    conn = _FakeConnection()
    _command_land(conn, 1, 1)

    assert conn.mav.calls[0][2] == mavlink.MAV_CMD_NAV_LAND


def test_fcu_land_param_report_audits_land_speed_and_forbidden_rangefinder_z() -> None:
    report = fcu_land_params_report(
        {
            "LAND_SPD_MS": 0.5,
            "LAND_SPD_HIGH_MS": 0.0,
            "LAND_ALT_LOW_M": 10.0,
            "EK3_SRC1_POSZ": 10.0,
            "EK3_RNG_USE_HGT": 1.0,
        }
    )

    assert report["values"]["LAND_SPD_MS"] == 0.5
    assert report["values"]["LAND_ALT_LOW_M"] == 10.0
    assert report["ekf_posz_is_rangefinder"] is True
    assert report["ekf_rng_use_hgt_enabled"] is True
    assert "LAND_SPEED" in report["missing"]


def test_param_id_parsing_and_request_read_for_land_params() -> None:
    assert mavlink_param_id_to_str(b"LAND_SPD_MS\x00\x00") == "LAND_SPD_MS"
    assert mavlink_param_id_to_str("LAND_ALT_LOW_M\x00") == "LAND_ALT_LOW_M"

    conn = _FakeConnection()
    _request_param_read(conn, 1, 1, "LAND_SPD_MS")

    assert conn.mav.calls[0][0] == "param_request_read_send"
    assert conn.mav.calls[0][3] == b"LAND_SPD_MS"
    assert conn.mav.calls[0][4] == -1


def test_force_disarm_waits_for_touchdown_grace_window() -> None:
    assert not should_send_disarm_after_touchdown(
        touchdown_confirmed=False,
        disarmed=False,
        require_disarm=True,
        touchdown_confirmed_elapsed_sec=10.0,
        force_disarm_grace_sec=3.0,
    )
    assert not should_send_disarm_after_touchdown(
        touchdown_confirmed=True,
        disarmed=False,
        require_disarm=True,
        touchdown_confirmed_elapsed_sec=2.9,
        force_disarm_grace_sec=3.0,
    )
    assert should_send_disarm_after_touchdown(
        touchdown_confirmed=True,
        disarmed=False,
        require_disarm=True,
        touchdown_confirmed_elapsed_sec=3.0,
        force_disarm_grace_sec=3.0,
    )
    assert not should_send_disarm_after_touchdown(
        touchdown_confirmed=True,
        disarmed=True,
        require_disarm=True,
        touchdown_confirmed_elapsed_sec=3.0,
        force_disarm_grace_sec=3.0,
    )


def test_hover_decision_blocks_hold_when_only_fcu_local_z_suggests_airborne() -> None:
    decision = decide_hover(
        _inputs(
            takeoff_ack_ok=False,
            current_z_ned=-0.334,
            current_height_m=0.09,
            external_nav_height_m=0.0,
            rangefinder_relative_height_m=0.0,
            target_z_ned=-0.45,
            airborne_elapsed_sec=10.0,
            hover_elapsed_sec=19.9,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "hover_settle"
    assert decision.reason == "waiting_for_independent_takeoff_height"
    assert decision.terminal is False


def test_hover_decision_blocks_hold_with_takeoff_ack_when_independent_height_lags() -> None:
    decision = decide_hover(
        _inputs(
            takeoff_ack_ok=True,
            current_z_ned=-0.45,
            current_height_m=0.09,
            external_nav_height_m=0.0,
            rangefinder_relative_height_m=0.0,
            target_z_ned=-0.45,
            hover_elapsed_sec=19.9,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "hover_settle"
    assert decision.reason == "waiting_for_independent_takeoff_height"


def test_independent_takeoff_height_evidence_requires_external_nav_and_second_height_source() -> None:
    assert height_reaches_target(0.34, target_alt_m=0.45, tolerance_m=0.18)
    assert not height_reaches_target(0.70, target_alt_m=0.45, tolerance_m=0.18)
    assert not height_reaches_target(0.09, target_alt_m=0.45, tolerance_m=0.18)
    assert independent_takeoff_height_reached(
        _inputs(takeoff_ack_ok=False, external_nav_height_m=0.44, rangefinder_relative_height_m=0.44),
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    assert not independent_takeoff_height_reached(
        _inputs(takeoff_ack_ok=False, external_nav_height_m=0.70, rangefinder_relative_height_m=0.44),
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    assert independent_takeoff_height_reached(
        _inputs(
            takeoff_ack_ok=False,
            current_z_ned=-0.44,
            external_nav_height_m=0.44,
            rangefinder_relative_height_m=0.95,
            target_z_ned=-0.45,
        ),
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    assert not independent_takeoff_height_reached(
        _inputs(
            takeoff_ack_ok=False,
            current_z_ned=-0.44,
            external_nav_height_m=0.0,
            rangefinder_relative_height_m=0.44,
            target_z_ned=-0.45,
        ),
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )


def test_hover_decision_keeps_hold_when_rangefinder_has_single_high_outlier() -> None:
    decision = decide_hover(
        _inputs(
            takeoff_ack_ok=True,
            current_z_ned=-0.404,
            current_height_m=1.04,
            external_nav_height_m=0.411,
            rangefinder_relative_height_m=0.95,
            target_z_ned=-0.485,
            hover_elapsed_sec=0.25,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.5,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "hover_hold"
    assert decision.reason == "holding_position"


def test_hover_decision_still_settles_when_external_nav_height_does_not_support_target() -> None:
    decision = decide_hover(
        _inputs(
            takeoff_ack_ok=True,
            current_z_ned=-0.485,
            external_nav_height_m=0.0,
            rangefinder_relative_height_m=0.5,
            target_z_ned=-0.485,
            hover_elapsed_sec=0.25,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.5,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "hover_settle"
    assert decision.reason == "waiting_for_independent_takeoff_height"


def test_position_hold_setpoint_waits_for_true_hover_hold_phase() -> None:
    inputs = _inputs(hover_elapsed_sec=19.9)
    settle = decide_hover(
        _inputs(takeoff_ack_ok=True, external_nav_height_m=0.0, rangefinder_relative_height_m=0.0),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    hold = decide_hover(
        inputs,
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert settle.phase == "hover_settle"
    assert not should_send_position_hold_setpoint(
        send_position_setpoints=True,
        inputs=inputs,
        decision=settle,
    )
    assert should_send_position_hold_setpoint(
        send_position_setpoints=True,
        inputs=inputs,
        decision=hold,
    )


def test_hover_setpoint_yaw_holds_segment_anchor() -> None:
    assert hold_yaw_or_current(-1.1, 0.0) == -1.1
    assert hold_yaw_or_current(None, 0.3) == 0.3


def test_capture_hold_anchor_latches_first_airborne_position() -> None:
    captured = capture_hold_anchor(None, None, 0.0, 1.2, -0.4, 0.3)
    assert captured == (1.2, -0.4, 0.3)

    retained = capture_hold_anchor(captured[0], captured[1], captured[2], 2.5, 0.8, 1.1)
    assert retained == captured


def test_capture_hold_anchor_uses_current_yaw_when_no_anchor_exists() -> None:
    captured = capture_hold_anchor(None, None, None, 1.2, -0.4, 1.57)

    assert captured == (1.2, -0.4, 1.57)


def test_capture_hold_anchor_refreshes_yaw_for_new_hold_segment() -> None:
    refreshed = capture_hold_anchor(1.2, -0.4, 0.3, 2.5, 0.8, 1.1, refresh_yaw=True)

    assert refreshed == (1.2, -0.4, 1.1)


def test_capture_hold_anchor_waits_for_complete_xy() -> None:
    assert capture_hold_anchor(None, None, 0.2, None, -0.4, 0.3) == (None, None, 0.2)
    assert capture_hold_anchor(None, None, 0.2, 1.2, None, 0.3) == (None, None, 0.2)


def test_hover_decision_aborts_when_nav_source_is_lost_after_airborne() -> None:
    slam_quality_lost = decide_hover(
        _inputs(
            slam_quality_good=False,
            slam_quality="uncertain",
            armed_seen=True,
            airborne_seen=True,
            slam_quality_loss_duration_sec=1.1,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    external_lost = decide_hover(
        _inputs(external_nav_ready=False, armed_seen=True, airborne_seen=True, external_nav_loss_duration_sec=1.1),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    mavlink_lost = decide_hover(
        _inputs(
            mavlink_external_nav_ready=False,
            armed_seen=True,
            airborne_seen=True,
            mavlink_external_nav_loss_duration_sec=1.1,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )
    fcu_local_lost = decide_hover(
        _inputs(
            fcu_local_position_ready=False,
            armed_seen=True,
            airborne_seen=True,
            fcu_local_position_loss_duration_sec=1.1,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert slam_quality_lost.phase == "abort"
    assert slam_quality_lost.reason == "slam_quality_lost_after_airborne"
    assert slam_quality_lost.terminal is True
    assert external_lost.phase == "abort"
    assert external_lost.reason == "external_nav_lost_after_airborne"
    assert external_lost.terminal is True
    assert mavlink_lost.reason == "mavlink_external_nav_lost_after_airborne"
    assert mavlink_lost.terminal is True
    assert fcu_local_lost.reason == "fcu_local_position_lost_after_airborne"
    assert fcu_local_lost.terminal is True


def test_hover_decision_debounces_short_nav_quality_loss_after_airborne() -> None:
    decision = decide_hover(
        _inputs(
            slam_quality_good=False,
            slam_quality="stale",
            external_nav_ready=False,
            armed_seen=True,
            airborne_seen=True,
            slam_quality_loss_duration_sec=0.5,
            external_nav_loss_duration_sec=0.5,
            hover_elapsed_sec=10.0,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "hover_hold"
    assert decision.reason == "holding_position"
    assert decision.terminal is False


def test_hover_decision_defers_nav_loss_abort_during_initial_settle() -> None:
    decision = decide_hover(
        _inputs(
            slam_quality_good=False,
            slam_quality="stale",
            external_nav_ready=False,
            mavlink_external_nav_ready=False,
            armed_seen=True,
            airborne_seen=True,
            airborne_elapsed_sec=1.5,
            hover_elapsed_sec=0.0,
            slam_quality_loss_duration_sec=1.1,
            external_nav_loss_duration_sec=1.1,
            mavlink_external_nav_loss_duration_sec=1.1,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "hover_settle"
    assert decision.reason == "settling_before_position_hold"


def test_hover_decision_aborts_nav_loss_after_initial_settle_window() -> None:
    decision = decide_hover(
        _inputs(
            slam_quality_good=False,
            slam_quality="stale",
            external_nav_ready=False,
            armed_seen=True,
            airborne_seen=True,
            airborne_elapsed_sec=2.1,
            hover_elapsed_sec=0.0,
            slam_quality_loss_duration_sec=1.1,
            external_nav_loss_duration_sec=1.1,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "abort"
    assert decision.reason == "slam_quality_lost_after_airborne"


def test_hover_decision_does_not_reapply_preflight_stability_wait_after_airborne() -> None:
    decision = decide_hover(
        _inputs(
            ready_elapsed_sec=0.1,
            airborne_seen=True,
            airborne_elapsed_sec=10.0,
            hover_elapsed_sec=10.0,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "hover_hold"
    assert decision.reason == "holding_position"


def test_hover_decision_aborts_when_guided_mode_is_lost_after_airborne() -> None:
    decision = decide_hover(
        _inputs(expected_mode_seen=False, armed_seen=True, airborne_seen=True),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "abort"
    assert decision.reason == "guided_mode_lost_after_airborne"
    assert decision.terminal is True


def test_hover_decision_keeps_hold_when_fcu_local_z_is_single_outlier() -> None:
    decision = decide_hover(
        _inputs(current_height_m=0.46, current_z_ned=-0.8, hover_elapsed_sec=19.9),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "hover_hold"
    assert decision.reason == "holding_position"


def test_hover_decision_falls_back_to_rangefinder_without_local_position() -> None:
    decision = decide_hover(
        _inputs(current_height_m=0.46, current_z_ned=None),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.terminal is True


def test_hover_decision_can_skip_external_nav_for_rangefinder_diagnostic() -> None:
    decision = decide_hover(
        _inputs(
            external_nav_ready=False,
            imu_ready=False,
            expected_mode_seen=False,
            armed_seen=False,
            airborne_seen=False,
        ),
        requirements=HoverRequirements(
            require_external_nav=False,
            require_fcu_external_nav=False,
            require_imu_status=False,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert decision.phase == "guided"
    assert decision.should_set_guided is True


def test_wait_ready_fail_fast_only_before_arm_and_airborne() -> None:
    decision = decide_hover(
        _inputs(
            external_nav_ready=False,
            slam_quality_good=False,
            armed_seen=False,
            airborne_seen=False,
        ),
        preflight_ready_sec=5.0,
        hover_settle_sec=2.0,
        hover_hold_sec=20.0,
        takeoff_alt_m=0.45,
        hover_altitude_tolerance_m=0.18,
    )

    assert should_fail_fast_wait_ready(
        _inputs(armed_seen=False, airborne_seen=False),
        decision,
        mission_elapsed_sec=35.0,
        max_wait_ready_sec=35.0,
    )
    assert not should_fail_fast_wait_ready(
        _inputs(armed_seen=True, airborne_seen=False),
        decision,
        mission_elapsed_sec=35.0,
        max_wait_ready_sec=35.0,
    )


def test_hold_axis_uses_current_position_until_hover_anchor_exists() -> None:
    assert hold_axis_or_current(None, 12.5) == 12.5
    assert hold_axis_or_current(-0.25, 12.5) == -0.25
    assert hold_axis_or_current(None, None) == 0.0


def test_hover_hold_setpoint_axes_hold_anchor_and_target_altitude() -> None:
    assert hover_hold_setpoint_axes(
        hold_x=-0.25,
        hold_y=0.5,
        current_x=12.5,
        current_y=-9.0,
        current_z=-0.20,
        target_z_ned=-0.50,
    ) == (-0.25, 0.5, -0.50)


def test_hover_hold_setpoint_axes_fall_back_to_current_before_anchor_exists() -> None:
    assert hover_hold_setpoint_axes(
        hold_x=None,
        hold_y=None,
        current_x=12.5,
        current_y=-9.0,
        current_z=-0.20,
        target_z_ned=None,
    ) == (12.5, -9.0, -0.20)


def test_landing_descent_target_moves_slowly_toward_ground() -> None:
    assert isclose(
        landing_descent_target_z_ned(
            start_z_ned=-0.50,
            ground_z_ned=0.0,
            elapsed_sec=2.0,
            descent_rate_mps=0.12,
        ),
        -0.26,
    )
    assert (
        landing_descent_target_z_ned(
            start_z_ned=-0.50,
            ground_z_ned=0.0,
            elapsed_sec=10.0,
            descent_rate_mps=0.12,
        )
        == 0.0
    )
    assert isclose(
        landing_descent_target_z_ned(
            start_z_ned=-0.50,
            ground_z_ned=0.0,
            elapsed_sec=10.0,
            descent_rate_mps=0.12,
            current_z_ned=-0.24,
            setpoint_lookahead_sec=0.5,
        ),
        -0.18,
    )
    assert (
        landing_descent_target_z_ned(
            start_z_ned=-0.50,
            ground_z_ned=0.0,
            elapsed_sec=10.0,
            descent_rate_mps=0.12,
            current_z_ned=-0.03,
            setpoint_lookahead_sec=0.5,
        )
        == 0.0
    )


def test_landing_effective_descent_rate_slows_near_ground() -> None:
    assert (
        landing_effective_descent_rate_mps(
            nominal_descent_rate_mps=0.09,
            rangefinder_relative_height_m=0.50,
            slowdown_altitude_m=0.35,
            near_ground_descent_rate_mps=0.03,
        )
        == 0.09
    )
    assert (
        landing_effective_descent_rate_mps(
            nominal_descent_rate_mps=0.09,
            rangefinder_relative_height_m=0.31,
            slowdown_altitude_m=0.35,
            near_ground_descent_rate_mps=0.03,
        )
        == 0.03
    )
    assert (
        landing_effective_descent_rate_mps(
            nominal_descent_rate_mps=0.02,
            rangefinder_relative_height_m=0.31,
            slowdown_altitude_m=0.35,
            near_ground_descent_rate_mps=0.03,
        )
        == 0.02
    )


def test_landing_descent_evidence_height_prefers_rangefinder_relative_height() -> None:
    assert isclose(
        landing_descent_evidence_height_m(
            current_range_m=0.37,
            ground_range_m=0.09,
            current_z_ned=-3.60,
            ground_z_ned=0.0,
        ),
        0.28,
    )
    assert isclose(
        landing_descent_evidence_height_m(
            current_range_m=None,
            ground_range_m=0.09,
            current_z_ned=-0.30,
            ground_z_ned=0.0,
        ),
        0.30,
    )
    assert isclose(
        landing_descent_evidence_height_m(
            current_range_m=float("nan"),
            ground_range_m=0.09,
            current_z_ned=-0.24,
            ground_z_ned=0.0,
        ),
        0.24,
    )
    height, source = landing_descent_evidence_height_and_source_m(
        current_range_m=5.90,
        ground_range_m=0.09,
        current_z_ned=-0.10,
        ground_z_ned=0.0,
    )
    assert height == 0.10
    assert source == "fcu_local_z_after_rangefinder_high_outlier"


def test_landing_descent_profile_blocks_fast_drop_and_bounce() -> None:
    good = summarize_landing_descent_profile(
        [
            (0.0, landing_descent_height_m(-0.50, 0.0), 0.59, 0.00),
            (1.0, landing_descent_height_m(-0.39, 0.0), 0.48, 0.11),
            (2.0, landing_descent_height_m(-0.28, 0.0), 0.37, 0.11),
            (3.0, landing_descent_height_m(-0.12, 0.0), 0.21, 0.12),
            (4.0, landing_descent_height_m(-0.08, 0.0), 0.09, 0.04),
        ],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )
    assert good["ok"] is True

    fast = summarize_landing_descent_profile(
        [(0.0, 0.50, 0.59, 0.0), (1.0, 0.20, 0.29, 0.54), (2.0, 0.10, 0.09, 0.04)],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )
    assert fast["ok"] is False
    assert fast["speed_ok"] is False

    touchdown_transient = summarize_landing_descent_profile(
        [
            (0.0, 0.50, 0.59, 0.00),
            (1.0, 0.38, 0.47, 0.12),
            (2.0, 0.24, 0.33, 0.14),
            (3.0, 0.11, 0.10, 0.30),
            (4.0, 0.08, 0.09, 0.02),
        ],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )
    assert touchdown_transient["ok"] is True
    assert touchdown_transient["speed_ok"] is True
    assert touchdown_transient["max_touchdown_downward_speed_mps"] == 0.30

    bounce = summarize_landing_descent_profile(
        [(0.0, 0.50, 0.59, 0.0), (1.0, 0.10, 0.09, 0.10), (2.0, 0.18, 0.17, -0.08)],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )
    assert bounce["ok"] is False
    assert bounce["bounce_ok"] is False


def test_landing_descent_profile_filters_isolated_rangefinder_spike() -> None:
    profile = summarize_landing_descent_profile(
        [
            (0.0, 0.50, 0.59, 0.00),
            (1.0, 0.41, 0.50, 0.09),
            (2.0, 3.72, 5.88, 0.09),
            (2.1, 0.34, 0.43, 0.09),
            (3.0, 0.24, 0.33, 0.10),
            (4.0, 0.11, 0.20, 0.10),
        ],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )

    assert profile["ok"] is True
    assert profile["speed_ok"] is True
    assert profile["rangefinder_outlier_count"] == 1
    assert profile["raw_height_sample_count"] == 6
    assert profile["height_sample_count"] == 5
    assert profile["filtered_height_sample_count"] == 1
    assert profile["max_height_m"] == 0.50
    assert profile["max_downward_speed_mps"] < 0.25


def test_landing_descent_profile_uses_local_fallback_for_high_range_plateau() -> None:
    profile = summarize_landing_descent_profile(
        [
            (0.0, 0.50, 0.59, 0.00, "rangefinder_relative_height"),
            (1.0, 0.41, 0.50, 0.09, "rangefinder_relative_height"),
            (2.0, 0.20, 5.90, 0.04, "fcu_local_z_after_rangefinder_high_outlier"),
            (2.1, 0.18, 5.90, 0.04, "fcu_local_z_after_rangefinder_high_outlier"),
            (2.2, 0.16, 5.90, 0.04, "fcu_local_z_after_rangefinder_high_outlier"),
            (3.0, 0.08, 0.17, 0.02, "rangefinder_relative_height"),
        ],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )

    assert profile["ok"] is True
    assert profile["speed_ok"] is True
    assert profile["fallback_height_sample_count"] == 3
    assert profile["height_source_counts"]["fcu_local_z_after_rangefinder_high_outlier"] == 3
    assert profile["max_height_m"] == 0.50


def test_landing_descent_profile_filters_impossible_rangefinder_rate() -> None:
    profile = summarize_landing_descent_profile(
        [
            (0.0, 0.50, 0.59, 0.00, "rangefinder_relative_height"),
            (1.0, 0.72, 0.81, 0.08, "rangefinder_relative_height"),
            (2.0, 1.17, 1.26, 0.08, "rangefinder_relative_height"),
            (2.05, 0.47, 0.56, 0.08, "rangefinder_relative_height"),
            (3.0, 0.35, 0.44, 0.12, "rangefinder_relative_height"),
            (4.0, 0.24, 0.33, 0.11, "rangefinder_relative_height"),
        ],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )

    assert profile["ok"] is True
    assert profile["speed_ok"] is True
    assert profile["rangefinder_rate_outlier_count"] == 1
    assert profile["rangefinder_outlier_count"] == 1
    assert profile["max_height_m"] == 0.72


def test_landing_descent_profile_filters_impossible_post_touchdown_range_bounce() -> None:
    profile = summarize_landing_descent_profile(
        [
            (0.0, 0.18, 0.27, 0.08, "rangefinder_relative_height"),
            (1.0, 0.08, 0.17, 0.04, "rangefinder_relative_height"),
            (1.05, 0.50, 0.59, -0.02, "rangefinder_relative_height"),
            (2.0, 0.09, 0.18, 0.01, "rangefinder_relative_height"),
        ],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )

    assert profile["ok"] is True
    assert profile["bounce_ok"] is True
    assert profile["rangefinder_rate_outlier_count"] == 1


def test_landing_descent_profile_ignores_uncorroborated_vz_spike() -> None:
    profile = summarize_landing_descent_profile(
        [
            (0.0, 0.40, 0.49, 0.08, "rangefinder_relative_height"),
            (1.0, 0.34, 0.43, 1.20, "rangefinder_relative_height"),
            (2.0, 0.28, 0.37, 0.08, "rangefinder_relative_height"),
            (3.0, 0.22, 0.31, 0.08, "rangefinder_relative_height"),
        ],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )

    assert profile["ok"] is True
    assert profile["speed_ok"] is True
    assert profile["vertical_velocity_outlier_count"] == 1


def test_landing_descent_profile_still_blocks_real_fast_descent() -> None:
    profile = summarize_landing_descent_profile(
        [
            (0.0, 0.50, 0.59, 0.00),
            (0.5, 0.31, 0.40, 0.38),
            (1.0, 0.12, 0.21, 0.38),
            (1.5, 0.08, 0.17, 0.04),
        ],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )

    assert profile["ok"] is False
    assert profile["speed_ok"] is False
    assert profile["rangefinder_outlier_count"] == 0
    assert profile["max_downward_speed_mps"] > 0.25


def test_ap_land_mode_uses_descent_profile_as_audit_not_gate() -> None:
    fast_profile = summarize_landing_descent_profile(
        [
            (0.0, 0.50, 0.59, 0.00),
            (0.5, 0.31, 0.40, 0.38),
            (1.0, 0.12, 0.21, 0.38),
            (1.5, 0.08, 0.17, 0.04),
        ],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )

    assert fast_profile["ok"] is False
    assert fast_profile["speed_ok"] is False
    assert landing_descent_profile_enforced("ap_land_mode_after_hover") is False
    assert (
        landing_acceptance_ok(
            landing_policy="ap_land_mode_after_hover",
            land_command_sent=True,
            land_command_accepted=True,
            land_mode_seen=True,
            touchdown_confirmed=True,
            disarmed=True,
            motors_safe=True,
            require_disarm=True,
            require_motors_safe=True,
            descent_profile_ok=fast_profile["ok"] is True,
        )
        is True
    )


def test_guided_descent_still_enforces_project_descent_profile_gate() -> None:
    assert landing_descent_profile_enforced("guided_descent") is True
    assert (
        landing_acceptance_ok(
            landing_policy="guided_descent",
            land_command_sent=True,
            land_command_accepted=True,
            land_mode_seen=False,
            touchdown_confirmed=True,
            disarmed=True,
            motors_safe=True,
            require_disarm=True,
            require_motors_safe=True,
            descent_profile_ok=False,
        )
        is False
    )


def test_ap_land_mode_requires_official_handoff_evidence() -> None:
    assert (
        landing_acceptance_ok(
            landing_policy="ap_land_mode_after_hover",
            land_command_sent=True,
            land_command_accepted=False,
            land_mode_seen=True,
            touchdown_confirmed=True,
            disarmed=True,
            motors_safe=True,
            require_disarm=True,
            require_motors_safe=True,
            descent_profile_ok=False,
        )
        is True
    )
    assert (
        landing_acceptance_ok(
            landing_policy="ap_land_mode_after_hover",
            land_command_sent=True,
            land_command_accepted=False,
            land_mode_seen=False,
            touchdown_confirmed=True,
            disarmed=True,
            motors_safe=True,
            require_disarm=True,
            require_motors_safe=True,
            descent_profile_ok=True,
        )
        is False
    )


def test_landing_descent_profile_audits_local_z_fallback_samples() -> None:
    profile = summarize_landing_descent_profile(
        [
            (0.0, 0.40, None, 0.10),
            (1.0, 0.28, None, 0.12),
            (2.0, 0.16, None, 0.12),
        ],
        max_descent_rate_mps=0.25,
        touchdown_altitude_m=0.12,
    )

    assert profile["ok"] is True
    assert profile["fallback_height_sample_count"] == 3
    assert profile["rangefinder_raw_sample_count"] == 0


def test_disarm_command_uses_force_magic_only_after_touchdown() -> None:
    normal = _FakeConnection()
    _command_disarm(normal, 1, 1)

    forced = _FakeConnection()
    _command_disarm(forced, 1, 1, force=True)

    assert normal.mav.calls[0][2] == mavlink.MAV_CMD_COMPONENT_ARM_DISARM
    assert normal.mav.calls[0][5] == 0
    assert forced.mav.calls[0][2] == mavlink.MAV_CMD_COMPONENT_ARM_DISARM
    assert forced.mav.calls[0][5] == 21196


def test_touchdown_candidate_prefers_rangefinder_over_local_z() -> None:
    assert (
        landing_touchdown_candidate(
            landed_state_on_ground=False,
            current_range_m=0.35,
            current_z_ned=-0.07,
            current_vz_mps=0.02,
            touchdown_altitude_m=0.12,
            touchdown_vertical_speed_mps=0.08,
        )
        is False
    )
    assert (
        landing_touchdown_candidate(
            landed_state_on_ground=False,
            current_range_m=0.09,
            current_z_ned=-0.20,
            current_vz_mps=0.02,
            touchdown_altitude_m=0.12,
            touchdown_vertical_speed_mps=0.08,
        )
        is True
    )
    assert (
        landing_touchdown_candidate(
            landed_state_on_ground=False,
            current_range_m=None,
            current_z_ned=-0.07,
            current_vz_mps=0.02,
            touchdown_altitude_m=0.12,
            touchdown_vertical_speed_mps=0.08,
        )
        is True
    )


def test_hover_drift_summary_uses_span_and_endpoint_drift() -> None:
    summary = summarize_hover_drift(
        [
            (10.0, 0.0, 0.0, -0.45),
            (20.0, 0.1, -0.2, -0.43),
            (30.0, -0.1, 0.1, -0.47),
        ]
    )

    assert summary.sample_count == 3
    assert isclose(summary.duration_sec, 20.0)
    assert isclose(summary.horizontal_span_m, (0.2**2 + 0.3**2) ** 0.5)
    assert isclose(summary.z_span_m, 0.04)
    assert summary.ok is True


def test_hover_drift_quality_is_not_binary_pass_claim() -> None:
    drift = summarize_hover_drift([(0.0, 0.0, 0.0, -0.45), (20.0, 0.10, 0.0, -0.45)])

    assert classify_hover_drift(drift, max_horizontal_drift_m=0.35) == "nominal"


def test_hover_altitude_crosscheck_requires_fcu_external_nav_and_rangefinder() -> None:
    passing = summarize_hover_altitude_crosscheck(
        [
            {
                "fcu_local_z_ned": -0.42,
                "fcu_local_height_m": 0.42,
                "external_nav_height_m": 0.43,
                "rangefinder_range_m": 0.46,
                "rangefinder_relative_height_m": 0.42,
            },
            {
                "fcu_local_z_ned": -0.45,
                "fcu_local_height_m": 0.45,
                "external_nav_height_m": 0.44,
                "rangefinder_range_m": 0.50,
                "rangefinder_relative_height_m": 0.45,
            },
        ],
        target_alt_m=0.45,
        tolerance_m=0.08,
    )

    assert passing["ok"] is True
    assert passing["sources"]["fcu_local_z_ned"] == -0.45
    assert isclose(passing["diffs"]["fcu_vs_external_abs_m"], 0.01)

    failing = summarize_hover_altitude_crosscheck(
        [
            {
                "fcu_local_z_ned": -0.45,
                "fcu_local_height_m": 0.45,
                "external_nav_height_m": 0.44,
                "rangefinder_range_m": 0.20,
                "rangefinder_relative_height_m": 0.18,
            },
            {
                "fcu_local_z_ned": -0.45,
                "fcu_local_height_m": 0.45,
                "external_nav_height_m": 0.44,
                "rangefinder_range_m": 0.20,
                "rangefinder_relative_height_m": 0.18,
            },
        ],
        target_alt_m=0.45,
        tolerance_m=0.08,
    )

    assert failing["ok"] is False
    assert "fcu_vs_rangefinder_abs_m" in failing["over_tolerance"]
    assert "rangefinder_target_error_m" in failing["over_tolerance"]


def test_command_ack_success_checks_mavlink_command_and_result() -> None:
    assert command_ack_success(
        [
            {"command": mavlink.MAV_CMD_NAV_TAKEOFF, "result": 4},
            {"command": mavlink.MAV_CMD_NAV_TAKEOFF, "result": 0},
        ],
        mavlink.MAV_CMD_NAV_TAKEOFF,
    )
    assert not command_ack_success(
        [{"command": mavlink.MAV_CMD_NAV_TAKEOFF, "result": 4}],
        mavlink.MAV_CMD_NAV_TAKEOFF,
    )


def test_command_ack_buffer_keeps_recent_takeoff_ack_after_noisy_interval_acks() -> None:
    acks: list[dict[str, int]] = []
    for _ in range(8):
        append_bounded_command_ack(acks, {"command": mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, "result": 0}, max_count=4)
    append_bounded_command_ack(acks, {"command": mavlink.MAV_CMD_NAV_TAKEOFF, "result": 0}, max_count=4)

    assert len(acks) == 4
    assert command_ack_success(acks, mavlink.MAV_CMD_NAV_TAKEOFF)


def test_command_ack_accepted_keeps_success_after_recent_buffer_rolls_over() -> None:
    acks: list[dict[str, int]] = []
    accepted = {mavlink.MAV_CMD_NAV_TAKEOFF}
    for _ in range(8):
        append_bounded_command_ack(acks, {"command": mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, "result": 0}, max_count=4)

    assert not command_ack_success(acks, mavlink.MAV_CMD_NAV_TAKEOFF)
    assert command_ack_accepted(acks, mavlink.MAV_CMD_NAV_TAKEOFF, accepted)


def test_statustext_buffer_rolls_but_crash_text_is_detectable() -> None:
    statustext: list[dict[str, int | str]] = []
    for index in range(130):
        append_bounded_statustext(statustext, {"severity": 6, "text": f"noise {index}"}, max_count=4)
    append_bounded_statustext(statustext, {"severity": 0, "text": "Crash: Disarming: AngErr=42>30"}, max_count=4)

    assert len(statustext) == 4
    assert statustext_indicates_crash(str(statustext[-1]["text"]))
