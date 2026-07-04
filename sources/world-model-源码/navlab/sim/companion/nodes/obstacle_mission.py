from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from navlab.sim.companion.mission.mavlink_commands import (
    DEFAULT_ORIGIN_ALT_M,
    DEFAULT_ORIGIN_LAT_DEG,
    DEFAULT_ORIGIN_LON_DEG,
    LOCAL_POSITION_YAW_TYPE_MASK,
    command_arm,
    command_takeoff,
    mode_number,
    send_gcs_heartbeat,
    send_local_position_yaw_setpoint,
    set_arming_check,
    set_ekf_origin,
    set_home_position,
    set_mode,
)
from navlab.sim.companion.runtime.status import DEFAULT_SIM_LOG_TOPIC, encode_sim_log

os.environ.setdefault("MAVLINK20", "1")


@dataclass(frozen=True, slots=True)
class MissionInputs:
    current_x: float | None
    current_y: float | None
    current_z_ned: float | None
    front_min: float | None
    external_nav_ready: bool
    imu_ready: bool
    scan_fresh: bool
    expected_mode_seen: bool
    armed_seen: bool
    airborne_seen: bool
    airborne_elapsed_sec: float | None


@dataclass(frozen=True, slots=True)
class MissionConfig:
    takeoff_alt_m: float = 0.8
    hover_settle_sec: float = 4.0
    forward_speed_mps: float = 0.15
    avoid_forward_speed_mps: float = 0.05
    obstacle_detect_distance_m: float = 5.2
    obstacle_avoid_distance_m: float = 2.0
    scan_yaw_rad: float = math.radians(45.0)
    scan_dwell_sec: float = 1.5
    pass_x_m: float = 6.5
    return_y_m: float = 0.1
    final_hold_sec: float = 5.0


@dataclass(frozen=True, slots=True)
class MissionDecision:
    phase: str
    mission_state: str
    reason: str
    vx_mps: float
    vy_mps: float
    yaw_rad: float | None = None
    should_set_guided: bool = False
    should_arm: bool = False
    should_takeoff: bool = False
    terminal: bool = False


@dataclass(slots=True)
class ReactiveAvoidancePlanner:
    mode: str = "track"
    mode_started_monotonic: float = 0.0
    left_clearance_m: float | None = None
    right_clearance_m: float | None = None
    selected_yaw_rad: float | None = None
    selected_side: str = ""

    def decide(self, inputs: MissionInputs, config: MissionConfig, *, now_monotonic: float) -> MissionDecision:
        base = decide_obstacle_mission(inputs, config)
        if base.phase in {"wait_ready", "guided", "arm", "takeoff", "hover_settle"}:
            return base
        if self.mode == "track" and base.phase in {"final_hold", "complete"}:
            return base

        x = inputs.current_x or 0.0
        y = inputs.current_y or 0.0
        front_min = inputs.front_min
        obstacle_close = front_min is not None and front_min <= config.obstacle_avoid_distance_m

        if self.mode == "track" and obstacle_close:
            self._switch("scan_left", now_monotonic)
            self.left_clearance_m = None
            self.right_clearance_m = None
            self.selected_yaw_rad = None
            self.selected_side = ""

        if self.mode == "scan_left":
            if now_monotonic - self.mode_started_monotonic < config.scan_dwell_sec:
                return MissionDecision("scan_left", "running", "scan_left_for_clearance", 0.0, 0.0, config.scan_yaw_rad)
            self.left_clearance_m = front_min
            self._switch("scan_right", now_monotonic)

        if self.mode == "scan_right":
            if now_monotonic - self.mode_started_monotonic < config.scan_dwell_sec:
                return MissionDecision(
                    "scan_right",
                    "running",
                    "scan_right_for_clearance",
                    0.0,
                    0.0,
                    -config.scan_yaw_rad,
                )
            self.right_clearance_m = front_min
            self.selected_yaw_rad = choose_scan_yaw(
                left_clearance_m=self.left_clearance_m,
                right_clearance_m=self.right_clearance_m,
                scan_yaw_rad=config.scan_yaw_rad,
            )
            self.selected_side = "left" if self.selected_yaw_rad >= 0.0 else "right"
            self._switch("avoid", now_monotonic)

        if self.mode == "avoid":
            yaw_rad = self.selected_yaw_rad if self.selected_yaw_rad is not None else config.scan_yaw_rad
            if x >= config.pass_x_m:
                self._switch("return_track", now_monotonic)
            else:
                return velocity_aligned_decision(
                    phase="avoid",
                    reason=f"avoid_{self.selected_side or 'selected'}",
                    speed_mps=config.avoid_forward_speed_mps,
                    yaw_rad=yaw_rad,
                )

        if self.mode == "return_track":
            if abs(y) <= config.return_y_m:
                self._switch("final", now_monotonic)
            else:
                yaw_rad = -config.scan_yaw_rad if y > 0.0 else config.scan_yaw_rad
                return velocity_aligned_decision(
                    phase="return_track",
                    reason="return_to_track",
                    speed_mps=config.avoid_forward_speed_mps,
                    yaw_rad=yaw_rad,
                )

        if self.mode == "final":
            return MissionDecision("complete", "complete", "mission_complete", 0.0, 0.0, terminal=True)

        return velocity_aligned_decision(
            phase="forward",
            reason="forward_progress",
            speed_mps=config.forward_speed_mps,
            yaw_rad=0.0,
        )

    def _switch(self, mode: str, now_monotonic: float) -> None:
        if self.mode != mode:
            self.mode = mode
            self.mode_started_monotonic = now_monotonic


def choose_scan_yaw(*, left_clearance_m: float | None, right_clearance_m: float | None, scan_yaw_rad: float) -> float:
    left = -math.inf if left_clearance_m is None else left_clearance_m
    right = -math.inf if right_clearance_m is None else right_clearance_m
    return scan_yaw_rad if left >= right else -scan_yaw_rad


def velocity_aligned_decision(*, phase: str, reason: str, speed_mps: float, yaw_rad: float) -> MissionDecision:
    return MissionDecision(
        phase,
        "running",
        reason,
        speed_mps * math.cos(yaw_rad),
        speed_mps * math.sin(yaw_rad),
        yaw_rad=yaw_rad,
    )


def decide_obstacle_mission(inputs: MissionInputs, config: MissionConfig) -> MissionDecision:
    ready = inputs.external_nav_ready and inputs.imu_ready and inputs.scan_fresh
    if not ready:
        return MissionDecision("wait_ready", "ready", "waiting_for_inputs", 0.0, 0.0)
    if not inputs.expected_mode_seen:
        return MissionDecision("guided", "arming", "setting_guided", 0.0, 0.0, should_set_guided=True)
    if not inputs.armed_seen:
        return MissionDecision("arm", "arming", "arming_vehicle", 0.0, 0.0, should_arm=True)
    if not inputs.airborne_seen:
        return MissionDecision("takeoff", "takeoff", "taking_off", 0.0, 0.0, should_takeoff=True)
    if inputs.airborne_elapsed_sec is None or inputs.airborne_elapsed_sec < config.hover_settle_sec:
        return MissionDecision("hover_settle", "running", "hover_settle", 0.0, 0.0)

    x = inputs.current_x or 0.0
    front_min = inputs.front_min
    obstacle_close = front_min is not None and front_min <= config.obstacle_avoid_distance_m

    if x >= config.pass_x_m:
        if inputs.airborne_elapsed_sec < config.hover_settle_sec + config.final_hold_sec:
            return MissionDecision("final_hold", "running", "final_hold", 0.0, 0.0)
        return MissionDecision("complete", "complete", "mission_complete", 0.0, 0.0, terminal=True)
    if obstacle_close:
        return MissionDecision("scan_left", "running", "scan_left_for_clearance", 0.0, 0.0, config.scan_yaw_rad)
    if x < config.pass_x_m:
        return velocity_aligned_decision(
            phase="forward",
            reason="forward_progress",
            speed_mps=config.forward_speed_mps,
            yaw_rad=0.0,
        )
    return MissionDecision("complete", "complete", "mission_complete", 0.0, 0.0, terminal=True)


def encode_mission_status(
    *,
    decision: MissionDecision,
    inputs: MissionInputs,
    setpoints_sent_count: int,
    obstacle_detected: bool,
) -> str:
    return json.dumps(
        {
            "phase": decision.phase,
            "mission_state": decision.mission_state,
            "reason": decision.reason,
            "cmd": {
                "vx_mps": decision.vx_mps,
                "vy_mps": decision.vy_mps,
                "yaw_rad": decision.yaw_rad,
            },
            "position": {
                "x": inputs.current_x,
                "y": inputs.current_y,
                "z_ned": inputs.current_z_ned,
            },
            "front_min": inputs.front_min,
            "external_nav_ready": inputs.external_nav_ready,
            "imu_ready": inputs.imu_ready,
            "scan_fresh": inputs.scan_fresh,
            "expected_mode_seen": inputs.expected_mode_seen,
            "armed_seen": inputs.armed_seen,
            "airborne_seen": inputs.airborne_seen,
            "setpoints_sent_count": setpoints_sent_count,
            "obstacle_detected": obstacle_detected,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run NavLab hover/forward/avoid mission via MAVLink setpoints.")
    parser.add_argument("--endpoint", default="tcp:sitl:5765")
    parser.add_argument("--duration-sec", type=float, default=90.0)
    parser.add_argument("--summary-file", default="")
    parser.add_argument("--mode", default="GUIDED")
    parser.add_argument("--takeoff-alt-m", type=float, default=0.8)
    parser.add_argument("--min-airborne-alt-m", type=float, default=0.25)
    parser.add_argument("--hover-settle-sec", type=float, default=4.0)
    parser.add_argument("--forward-speed-mps", type=float, default=0.15)
    parser.add_argument("--avoid-forward-speed-mps", type=float, default=0.05)
    parser.add_argument("--obstacle-detect-distance-m", type=float, default=5.2)
    parser.add_argument("--obstacle-avoid-distance-m", type=float, default=2.0)
    parser.add_argument("--scan-yaw-deg", type=float, default=45.0)
    parser.add_argument("--scan-dwell-sec", type=float, default=1.5)
    parser.add_argument("--pass-x-m", type=float, default=6.5)
    parser.add_argument("--return-y-m", type=float, default=0.1)
    parser.add_argument("--final-hold-sec", type=float, default=5.0)
    parser.add_argument("--origin-lat-deg", type=float, default=DEFAULT_ORIGIN_LAT_DEG)
    parser.add_argument("--origin-lon-deg", type=float, default=DEFAULT_ORIGIN_LON_DEG)
    parser.add_argument("--origin-alt-m", type=float, default=DEFAULT_ORIGIN_ALT_M)
    parser.add_argument("--source-system", type=int, default=255)
    parser.add_argument("--source-component", type=int, default=190)
    parser.add_argument("--status-topic", default="/navlab/mission/status")
    parser.add_argument("--sim-log-topic", default=DEFAULT_SIM_LOG_TOPIC)
    parser.add_argument("--scan-features-topic", default="/scan_features")
    parser.add_argument("--external-nav-status-topic", default="/external_nav/status")
    parser.add_argument("--imu-status-topic", default="/imu/status")
    parser.add_argument("--pose-topic", default="/sim/uav_pose")
    parser.add_argument("--mavlink-status-topic", default="/navlab/mavlink/status")
    parser.add_argument("--scan-timeout-sec", type=float, default=1.0)
    parser.add_argument("--status-timeout-sec", type=float, default=1.0)
    parser.add_argument("--setpoint-rate-hz", type=float, default=5.0)
    parser.add_argument("--setpoint-lookahead-sec", type=float, default=2.0)
    parser.add_argument("--disable-arming-checks", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force-arm", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--simulate-mode-arm", action=argparse.BooleanOptionalAction, default=False)
    return parser


def _send_message_interval(connection, target_system: int, target_component: int, message_id: int, hz: float) -> None:
    from pymavlink.dialects.v20 import ardupilotmega as mavlink

    connection.mav.command_long_send(
        target_system,
        target_component,
        mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0,
        message_id,
        int(1_000_000.0 / hz),
        0,
        0,
        0,
        0,
        0,
    )


def _request_streams(connection, target_system: int, target_component: int) -> None:
    from pymavlink.dialects.v20 import ardupilotmega as mavlink

    for message_id, hz in (
        (mavlink.MAVLINK_MSG_ID_HEARTBEAT, 2.0),
        (mavlink.MAVLINK_MSG_ID_LOCAL_POSITION_NED, 10.0),
        (mavlink.MAVLINK_MSG_ID_EKF_STATUS_REPORT, 4.0),
        (mavlink.MAVLINK_MSG_ID_EXTENDED_SYS_STATE, 4.0),
        (mavlink.MAVLINK_MSG_ID_GPS_GLOBAL_ORIGIN, 1.0),
        (mavlink.MAVLINK_MSG_ID_HOME_POSITION, 1.0),
        (mavlink.MAVLINK_MSG_ID_STATUSTEXT, 2.0),
    ):
        _send_message_interval(connection, target_system, target_component, message_id, hz)


def position_target_from_velocity(
    *,
    current_x: float | None,
    current_y: float | None,
    vx_mps: float,
    vy_mps: float,
    lookahead_sec: float,
) -> tuple[float, float]:
    x = 0.0 if current_x is None else current_x
    y = 0.0 if current_y is None else current_y
    return x + vx_mps * lookahead_sec, y + vy_mps * lookahead_sec


def yaw_for_velocity(vx_mps: float, vy_mps: float, fallback_yaw_rad: float) -> float:
    if math.hypot(vx_mps, vy_mps) < 0.02:
        return fallback_yaw_rad
    return math.atan2(vy_mps, vx_mps)


def run(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        import rclpy
        from geometry_msgs.msg import PoseStamped
        from pymavlink import mavutil
        from pymavlink.dialects.v20 import ardupilotmega as mavlink
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from std_msgs.msg import String
        from ydlidar_interfaces.msg import ScanFeatures
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "mavlink_obstacle_mission_controller requires ROS2, ydlidar_interfaces, and pymavlink. "
            "Run it from the NavLab companion image."
        ) from exc

    class MavlinkObstacleMissionController(Node):
        def __init__(self) -> None:
            super().__init__("mavlink_obstacle_mission_controller")
            self._connection = mavutil.mavlink_connection(
                args.endpoint,
                source_system=args.source_system,
                source_component=args.source_component,
                dialect="ardupilotmega",
            )
            self._status_pub = self.create_publisher(String, args.status_topic, 10)
            self._sim_log_pub = self.create_publisher(String, args.sim_log_topic, 10)
            self.create_subscription(
                ScanFeatures,
                args.scan_features_topic,
                self._handle_scan_features,
                qos_profile_sensor_data,
            )
            self.create_subscription(String, args.external_nav_status_topic, self._handle_external_nav_status, 10)
            self.create_subscription(String, args.imu_status_topic, self._handle_imu_status, 10)
            self.create_subscription(PoseStamped, args.pose_topic, self._handle_pose, 10)
            self.create_subscription(String, args.mavlink_status_topic, self._handle_mavlink_status, 10)
            self.mode_number = mode_number(args.mode)
            self._target_system: int | None = None
            self._target_component: int | None = None
            self._front_min: float | None = None
            self._last_scan_monotonic = 0.0
            self._external_nav_ready = False
            self._last_external_status_monotonic = 0.0
            self._imu_ready = False
            self._last_imu_status_monotonic = 0.0
            self._current_x: float | None = None
            self._current_y: float | None = None
            self._current_z: float | None = None
            self._expected_mode_seen = False
            self._armed_seen = False
            self._external_expected_mode_seen = False
            self._external_armed_seen = False
            self._airborne_seen = False
            self._airborne_started: float | None = None
            self._next_request = 0.0
            self._next_heartbeat = 0.0
            self._next_origin_command = 0.0
            self._next_mode_command = 0.0
            self._next_arm_command = 0.0
            self._next_takeoff_command = 0.0
            self._next_setpoint = 0.0
            self._last_setpoint_yaw_rad = 0.0
            self._setpoints_sent = 0
            self._obstacle_detected = False
            self._avoidance_setpoint_sent = False
            self._scan_left_seen = False
            self._scan_right_seen = False
            self._phases_seen: set[str] = set()
            self._message_counts: dict[str, int] = {}
            self._command_acks: list[dict[str, int]] = []
            self._statustext: list[dict[str, object]] = []
            self._sent_commands: dict[str, int] = {}
            self._ekf_flags: list[int] = []
            self._gps_global_origin_seen = False
            self._home_position_seen = False
            self._started = time.monotonic()
            self._config = MissionConfig(
                takeoff_alt_m=args.takeoff_alt_m,
                hover_settle_sec=args.hover_settle_sec,
                forward_speed_mps=args.forward_speed_mps,
                avoid_forward_speed_mps=args.avoid_forward_speed_mps,
                obstacle_detect_distance_m=args.obstacle_detect_distance_m,
                obstacle_avoid_distance_m=args.obstacle_avoid_distance_m,
                scan_yaw_rad=math.radians(args.scan_yaw_deg),
                scan_dwell_sec=args.scan_dwell_sec,
                pass_x_m=args.pass_x_m,
                return_y_m=args.return_y_m,
                final_hold_sec=args.final_hold_sec,
            )
            self._planner = ReactiveAvoidancePlanner(mode_started_monotonic=time.monotonic())
            self.create_timer(0.05, self._tick)
            self.get_logger().info(f"stage1.5 obstacle mission controller started endpoint={args.endpoint}")

        def _handle_scan_features(self, msg) -> None:
            value = float(msg.front_min)
            self._front_min = value if math.isfinite(value) else None
            self._last_scan_monotonic = time.monotonic()

        def _handle_external_nav_status(self, msg: String) -> None:
            self._external_nav_ready = self._status_ready(msg.data)
            self._last_external_status_monotonic = time.monotonic()

        def _handle_imu_status(self, msg: String) -> None:
            self._imu_ready = self._status_ready(msg.data)
            self._last_imu_status_monotonic = time.monotonic()

        def _handle_pose(self, msg) -> None:
            self._current_x = float(msg.pose.position.x)
            self._current_y = float(msg.pose.position.y)
            self._current_z = -float(msg.pose.position.z)
            if msg.pose.position.z >= args.min_airborne_alt_m:
                self._airborne_seen = True
                if self._airborne_started is None:
                    self._airborne_started = time.monotonic()

        def _handle_mavlink_status(self, msg: String) -> None:
            try:
                payload = json.loads(msg.data)
            except json.JSONDecodeError:
                return
            mode_number = payload.get("mode_number")
            self._external_expected_mode_seen = mode_number == self.mode_number
            self._external_armed_seen = payload.get("armed") is True

        @staticmethod
        def _status_ready(data: str) -> bool:
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                return False
            return payload.get("ready") is True

        def _tick(self) -> None:
            now = time.monotonic()
            if now - self._started >= args.duration_sec:
                self.write_summary(ok=False, reason="duration_timeout")
                rclpy.try_shutdown()
                return
            self._drain_mavlink()
            if now >= self._next_heartbeat:
                send_gcs_heartbeat(self._connection)
                self._next_heartbeat = now + 1.0
            if self._target_system is not None and self._target_component is not None and now >= self._next_request:
                _request_streams(self._connection, self._target_system, self._target_component)
                if args.disable_arming_checks:
                    set_arming_check(self._connection, self._target_system, self._target_component, 0)
                self._next_request = now + 2.0
            target_known = self._target_system is not None and self._target_component is not None
            if target_known and now >= self._next_origin_command:
                if not self._gps_global_origin_seen:
                    set_ekf_origin(
                        self._connection,
                        self._target_system,
                        args.origin_lat_deg,
                        args.origin_lon_deg,
                        args.origin_alt_m,
                    )
                    self._count_sent_command("set_gps_global_origin")
                if not self._home_position_seen:
                    set_home_position(
                        self._connection,
                        self._target_system,
                        self._target_component,
                        args.origin_lat_deg,
                        args.origin_lon_deg,
                        args.origin_alt_m,
                    )
                    self._count_sent_command("set_home_position")
                self._next_origin_command = now + 2.0

            inputs = self._build_inputs(now)
            decision = self._planner.decide(inputs, self._config, now_monotonic=now)
            self._phases_seen.add(decision.phase)
            if decision.phase == "scan_left":
                self._scan_left_seen = True
            if decision.phase == "scan_right":
                self._scan_right_seen = True
            if inputs.front_min is not None and inputs.front_min <= self._config.obstacle_detect_distance_m:
                self._obstacle_detected = True

            if self._target_system is not None and self._target_component is not None:
                if decision.should_set_guided and now >= self._next_mode_command:
                    set_mode(self._connection, self._target_system, self.mode_number)
                    self._count_sent_command("set_mode_guided")
                    self._next_mode_command = now + 1.0
                if decision.should_arm and now >= self._next_arm_command:
                    command_arm(self._connection, self._target_system, self._target_component, args.force_arm)
                    self._count_sent_command("arm")
                    self._next_arm_command = now + 2.0
                if decision.should_takeoff and now >= self._next_takeoff_command:
                    command_takeoff(self._connection, self._target_system, self._target_component, args.takeoff_alt_m)
                    self._count_sent_command("takeoff")
                    self._next_takeoff_command = now + 2.0
                if inputs.airborne_seen and now >= self._next_setpoint:
                    yaw_rad = decision.yaw_rad
                    if yaw_rad is None:
                        yaw_rad = yaw_for_velocity(decision.vx_mps, decision.vy_mps, self._last_setpoint_yaw_rad)
                    self._last_setpoint_yaw_rad = yaw_rad
                    decision = MissionDecision(
                        phase=decision.phase,
                        mission_state=decision.mission_state,
                        reason=decision.reason,
                        vx_mps=decision.vx_mps,
                        vy_mps=decision.vy_mps,
                        yaw_rad=yaw_rad,
                        should_set_guided=decision.should_set_guided,
                        should_arm=decision.should_arm,
                        should_takeoff=decision.should_takeoff,
                        terminal=decision.terminal,
                    )
                    target_x, target_y = position_target_from_velocity(
                        current_x=inputs.current_x,
                        current_y=inputs.current_y,
                        vx_mps=decision.vx_mps,
                        vy_mps=decision.vy_mps,
                        lookahead_sec=args.setpoint_lookahead_sec,
                    )
                    send_local_position_yaw_setpoint(
                        self._connection,
                        self._target_system,
                        self._target_component,
                        target_x,
                        target_y,
                        -args.takeoff_alt_m,
                        decision.yaw_rad,
                    )
                    self._setpoints_sent += 1
                    self._count_sent_command("local_position_setpoint")
                    if decision.phase in {"avoid", "scan_left", "scan_right"}:
                        self._avoidance_setpoint_sent = True
                    self._next_setpoint = now + (1.0 / args.setpoint_rate_hz)

            self._publish_status(decision, inputs)
            if decision.terminal:
                self.write_summary(ok=True, reason=decision.reason)
                rclpy.try_shutdown()

        def _drain_mavlink(self) -> None:
            while True:
                msg = self._connection.recv_match(blocking=False)
                if msg is None:
                    return
                msg_type = msg.get_type()
                self._message_counts[msg_type] = self._message_counts.get(msg_type, 0) + 1
                if msg_type == "HEARTBEAT" and int(msg.autopilot) != mavlink.MAV_AUTOPILOT_INVALID:
                    self._target_system = msg.get_srcSystem()
                    self._target_component = msg.get_srcComponent()
                    self._expected_mode_seen = int(msg.custom_mode) == self.mode_number
                    self._armed_seen = bool(int(msg.base_mode) & mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                elif msg_type == "COMMAND_ACK":
                    if len(self._command_acks) < 80:
                        self._command_acks.append({"command": int(msg.command), "result": int(msg.result)})
                elif msg_type == "STATUSTEXT":
                    if len(self._statustext) < 80:
                        self._statustext.append({"severity": int(msg.severity), "text": str(msg.text)})
                elif msg_type == "LOCAL_POSITION_NED":
                    self._current_x = float(msg.x)
                    self._current_y = float(msg.y)
                    self._current_z = float(msg.z)
                    if self._current_z <= -args.min_airborne_alt_m:
                        self._airborne_seen = True
                elif msg_type == "GLOBAL_POSITION_INT":
                    if float(msg.relative_alt) / 1000.0 >= args.min_airborne_alt_m:
                        self._airborne_seen = True
                elif msg_type == "EXTENDED_SYS_STATE":
                    if int(msg.landed_state) in (mavlink.MAV_LANDED_STATE_TAKEOFF, mavlink.MAV_LANDED_STATE_IN_AIR):
                        self._airborne_seen = True
                elif msg_type == "EKF_STATUS_REPORT":
                    self._ekf_flags.append(int(msg.flags))
                elif msg_type == "GPS_GLOBAL_ORIGIN":
                    self._gps_global_origin_seen = True
                elif msg_type == "HOME_POSITION":
                    self._home_position_seen = True
                if self._airborne_seen and self._airborne_started is None:
                    self._airborne_started = time.monotonic()

        def _build_inputs(self, now: float) -> MissionInputs:
            scan_fresh = self._last_scan_monotonic > 0.0 and now - self._last_scan_monotonic <= args.scan_timeout_sec
            external_nav_fresh = (
                self._last_external_status_monotonic > 0.0
                and now - self._last_external_status_monotonic <= args.status_timeout_sec
            )
            imu_fresh = (
                self._last_imu_status_monotonic > 0.0
                and now - self._last_imu_status_monotonic <= args.status_timeout_sec
            )
            airborne_elapsed = None if self._airborne_started is None else now - self._airborne_started
            return MissionInputs(
                current_x=self._current_x,
                current_y=self._current_y,
                current_z_ned=self._current_z,
                front_min=self._front_min,
                external_nav_ready=self._external_nav_ready and external_nav_fresh,
                imu_ready=self._imu_ready and imu_fresh,
                scan_fresh=scan_fresh,
                expected_mode_seen=(
                    args.simulate_mode_arm or self._expected_mode_seen or self._external_expected_mode_seen
                ),
                armed_seen=args.simulate_mode_arm or self._armed_seen or self._external_armed_seen,
                airborne_seen=self._airborne_seen,
                airborne_elapsed_sec=airborne_elapsed,
            )

        def _publish_status(self, decision: MissionDecision, inputs: MissionInputs) -> None:
            msg = String()
            msg.data = encode_mission_status(
                decision=decision,
                inputs=inputs,
                setpoints_sent_count=self._setpoints_sent,
                obstacle_detected=self._obstacle_detected,
            )
            self._status_pub.publish(msg)
            sim_log = String()
            sim_log.data = encode_sim_log(
                source="mavlink_obstacle_mission_controller",
                event=decision.reason,
                mission_state=decision.mission_state,
                phase=decision.phase,
                current_x=inputs.current_x,
                current_y=inputs.current_y,
                current_z_ned=inputs.current_z_ned,
                front_min=inputs.front_min,
                cmd_vx_mps=decision.vx_mps,
                cmd_vy_mps=decision.vy_mps,
                yaw_rad=decision.yaw_rad,
                obstacle_detected=self._obstacle_detected,
                setpoints_sent_count=self._setpoints_sent,
            )
            self._sim_log_pub.publish(sim_log)

        def _count_sent_command(self, name: str) -> None:
            self._sent_commands[name] = self._sent_commands.get(name, 0) + 1

        def write_summary(self, *, ok: bool, reason: str) -> None:
            if not args.summary_file:
                return
            summary = {
                "ok": ok,
                "reason": reason,
                "setpoints_sent_count": self._setpoints_sent,
                "obstacle_detected": self._obstacle_detected,
                "avoidance_setpoint_sent": self._avoidance_setpoint_sent,
                "scan_left_seen": self._scan_left_seen,
                "scan_right_seen": self._scan_right_seen,
                "selected_avoidance_side": self._planner.selected_side,
                "selected_avoidance_yaw_rad": self._planner.selected_yaw_rad,
                "phases_seen": sorted(self._phases_seen),
                "last_position": {"x": self._current_x, "y": self._current_y, "z_ned": self._current_z},
                "message_counts": self._message_counts,
                "sent_commands": dict(sorted(self._sent_commands.items())),
                "command_acks": self._command_acks[-40:],
                "statustext": self._statustext[-40:],
                "ekf_flags_seen": sorted(set(self._ekf_flags)),
                "gps_global_origin_seen": self._gps_global_origin_seen,
                "home_position_seen": self._home_position_seen,
            }
            path = Path(args.summary_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    rclpy.init(args=None)
    node = MavlinkObstacleMissionController()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
