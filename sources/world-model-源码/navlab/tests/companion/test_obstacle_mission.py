from __future__ import annotations

import json
from math import isclose

from navlab.sim.companion.nodes.obstacle_mission import (
    DEFAULT_ORIGIN_ALT_M,
    DEFAULT_ORIGIN_LAT_DEG,
    DEFAULT_ORIGIN_LON_DEG,
    LOCAL_POSITION_YAW_TYPE_MASK,
    MissionConfig,
    MissionDecision,
    MissionInputs,
    ReactiveAvoidancePlanner,
    choose_scan_yaw,
    decide_obstacle_mission,
    encode_mission_status,
    position_target_from_velocity,
    send_gcs_heartbeat,
    send_local_position_yaw_setpoint,
    set_ekf_origin,
    set_home_position,
    set_mode,
    velocity_aligned_decision,
    yaw_for_velocity,
)


def _ready_inputs(**overrides) -> MissionInputs:
    values = {
        "current_x": 0.0,
        "current_y": 0.0,
        "current_z_ned": -0.8,
        "front_min": 5.0,
        "external_nav_ready": True,
        "imu_ready": True,
        "scan_fresh": True,
        "expected_mode_seen": True,
        "armed_seen": True,
        "airborne_seen": True,
        "airborne_elapsed_sec": 10.0,
    }
    values.update(overrides)
    return MissionInputs(**values)


def test_decision_waits_for_inputs_before_mode_or_arm() -> None:
    decision = decide_obstacle_mission(
        _ready_inputs(external_nav_ready=False),
        MissionConfig(),
    )

    assert decision.phase == "wait_ready"
    assert decision.should_set_guided is False
    assert decision.should_arm is False


def test_decision_sets_guided_then_arms_then_takeoff() -> None:
    config = MissionConfig()

    guided = decide_obstacle_mission(
        _ready_inputs(expected_mode_seen=False, armed_seen=False, airborne_seen=False),
        config,
    )
    arm = decide_obstacle_mission(_ready_inputs(armed_seen=False, airborne_seen=False), config)
    takeoff = decide_obstacle_mission(_ready_inputs(airborne_seen=False), config)

    assert guided.should_set_guided is True
    assert arm.should_arm is True
    assert takeoff.should_takeoff is True


def test_decision_moves_forward_when_clear() -> None:
    decision = decide_obstacle_mission(_ready_inputs(current_x=1.0, front_min=5.0), MissionConfig())

    assert decision.phase == "forward"
    assert decision.vx_mps > 0.0
    assert decision.vy_mps == 0.0


def test_decision_starts_yaw_scan_when_obstacle_seen() -> None:
    decision = decide_obstacle_mission(_ready_inputs(current_x=3.2, current_y=0.2, front_min=1.5), MissionConfig())

    assert decision.phase == "scan_left"
    assert decision.vx_mps == 0.0
    assert decision.vy_mps == 0.0
    assert decision.yaw_rad and decision.yaw_rad > 0.0


def test_decision_can_detect_visible_obstacle_without_early_avoid() -> None:
    config = MissionConfig(obstacle_detect_distance_m=5.2, obstacle_avoid_distance_m=2.0)

    decision = decide_obstacle_mission(_ready_inputs(current_x=1.0, current_y=0.0, front_min=5.0), config)

    assert decision.phase == "forward"
    assert 5.0 <= config.obstacle_detect_distance_m
    assert 5.0 > config.obstacle_avoid_distance_m


def test_reactive_planner_scans_left_and_right_then_selects_clearer_side() -> None:
    planner = ReactiveAvoidancePlanner(mode_started_monotonic=0.0)
    config = MissionConfig(scan_dwell_sec=1.0)

    left = planner.decide(_ready_inputs(current_x=3.2, front_min=1.5), config, now_monotonic=10.0)
    right = planner.decide(_ready_inputs(current_x=3.2, front_min=4.0), config, now_monotonic=11.1)
    avoid = planner.decide(_ready_inputs(current_x=3.2, front_min=2.5), config, now_monotonic=12.2)

    assert left.phase == "scan_left"
    assert left.yaw_rad and left.yaw_rad > 0.0
    assert right.phase == "scan_right"
    assert right.yaw_rad and right.yaw_rad < 0.0
    assert avoid.phase == "avoid"
    assert avoid.reason == "avoid_left"
    assert avoid.yaw_rad and avoid.yaw_rad > 0.0
    assert avoid.vx_mps > 0.0
    assert avoid.vy_mps > 0.0


def test_decision_completes_after_passing_and_returning_to_track() -> None:
    decision = decide_obstacle_mission(
        _ready_inputs(current_x=6.7, current_y=0.12, front_min=5.0, airborne_elapsed_sec=80.0),
        MissionConfig(return_y_m=0.15),
    )

    assert decision.phase == "complete"
    assert decision.terminal is True


def test_reactive_planner_returns_to_track_after_passing_obstacle() -> None:
    planner = ReactiveAvoidancePlanner(mode="avoid", selected_yaw_rad=0.78, selected_side="left")
    decision = planner.decide(
        _ready_inputs(current_x=6.7, current_y=2.0, front_min=5.0),
        MissionConfig(),
        now_monotonic=20.0,
    )

    assert decision.phase == "return_track"
    assert decision.vx_mps > 0.0
    assert decision.vy_mps < 0.0
    assert decision.yaw_rad and decision.yaw_rad < 0.0


def test_encode_mission_status_is_foxglove_friendly_json() -> None:
    decision = MissionDecision("avoid", "running", "avoid_left", 0.05, 0.15, yaw_rad=1.249)
    payload = encode_mission_status(
        decision=decision,
        inputs=_ready_inputs(current_x=3.0, current_y=0.5, front_min=1.4),
        setpoints_sent_count=12,
        obstacle_detected=True,
    )

    data = json.loads(payload)
    assert data["phase"] == "avoid"
    assert data["mission_state"] == "running"
    assert data["cmd"]["vy_mps"] == 0.15
    assert data["cmd"]["yaw_rad"] == 1.249
    assert data["obstacle_detected"] is True
    assert data["position"]["x"] == 3.0


def test_yaw_for_velocity_faces_current_motion_direction() -> None:
    assert isclose(yaw_for_velocity(0.15, 0.0, 0.7), 0.0)
    assert yaw_for_velocity(0.05, 0.15, 0.0) > 0.0
    assert isclose(yaw_for_velocity(0.0, 0.0, 0.7), 0.7)


def test_velocity_aligned_decision_keeps_heading_and_motion_together() -> None:
    decision = velocity_aligned_decision(phase="avoid", reason="avoid_left", speed_mps=0.2, yaw_rad=0.5)

    assert isclose(decision.yaw_rad or 0.0, 0.5)
    assert isclose(math_atan2(decision.vy_mps, decision.vx_mps), 0.5)


def test_position_target_from_velocity_looks_ahead_from_current_local_position() -> None:
    x, y = position_target_from_velocity(
        current_x=1.0,
        current_y=-0.2,
        vx_mps=0.3,
        vy_mps=0.1,
        lookahead_sec=2.0,
    )

    assert isclose(x, 1.6)
    assert isclose(y, 0.0)


def test_choose_scan_yaw_prefers_clearer_front_scan() -> None:
    assert choose_scan_yaw(left_clearance_m=4.0, right_clearance_m=1.0, scan_yaw_rad=0.7) == 0.7
    assert choose_scan_yaw(left_clearance_m=1.0, right_clearance_m=4.0, scan_yaw_rad=0.7) == -0.7


def math_atan2(y: float, x: float) -> float:
    from math import atan2

    return atan2(y, x)


class _FakeMav:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def heartbeat_send(self, *args: object) -> None:
        self.calls.append(("heartbeat_send", args))

    def set_gps_global_origin_send(self, *args: object) -> None:
        self.calls.append(("set_gps_global_origin_send", args))

    def set_mode_send(self, *args: object) -> None:
        self.calls.append(("set_mode_send", args))

    def command_long_send(self, *args: object) -> None:
        self.calls.append(("command_long_send", args))

    def set_position_target_local_ned_send(self, *args: object) -> None:
        self.calls.append(("set_position_target_local_ned_send", args))


class _FakeConnection:
    def __init__(self) -> None:
        self.mav = _FakeMav()


def test_fcu_initialization_sends_gcs_heartbeat_origin_and_home() -> None:
    connection = _FakeConnection()

    send_gcs_heartbeat(connection)
    set_ekf_origin(connection, 1, DEFAULT_ORIGIN_LAT_DEG, DEFAULT_ORIGIN_LON_DEG, DEFAULT_ORIGIN_ALT_M)
    set_home_position(connection, 1, 1, DEFAULT_ORIGIN_LAT_DEG, DEFAULT_ORIGIN_LON_DEG, DEFAULT_ORIGIN_ALT_M)

    heartbeat = connection.mav.calls[0]
    origin = connection.mav.calls[1]
    home = connection.mav.calls[2]
    assert heartbeat[0] == "heartbeat_send"
    assert origin[0] == "set_gps_global_origin_send"
    assert origin[1][0] == 1
    assert origin[1][1] == int(DEFAULT_ORIGIN_LAT_DEG * 1e7)
    assert origin[1][2] == int(DEFAULT_ORIGIN_LON_DEG * 1e7)
    assert origin[1][3] == int(DEFAULT_ORIGIN_ALT_M * 1000.0)
    assert home[0] == "command_long_send"


def test_local_position_yaw_setpoint_uses_position_fields_and_ignores_velocity() -> None:
    connection = _FakeConnection()

    send_local_position_yaw_setpoint(
        connection,
        target_system=1,
        target_component=1,
        x_ned_m=1.2,
        y_ned_m=0.4,
        z_ned_m=-0.45,
        yaw_rad=0.7,
    )

    name, args = connection.mav.calls[0]
    assert name == "set_position_target_local_ned_send"
    assert args[4] == LOCAL_POSITION_YAW_TYPE_MASK
    assert args[5] == 1.2
    assert args[6] == 0.4
    assert args[7] == -0.45
    assert args[8] == 0.0
    assert args[9] == 0.0
    assert args[14] == 0.7


def test_set_mode_uses_arducopter_set_mode_and_ackable_command() -> None:
    connection = _FakeConnection()

    set_mode(connection, 1, 4)

    assert connection.mav.calls[0][0] == "set_mode_send"
    assert connection.mav.calls[1][0] == "command_long_send"
