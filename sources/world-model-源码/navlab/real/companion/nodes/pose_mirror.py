from __future__ import annotations

import argparse
import json
import math
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass

from navlab.common.pose import PlanarPoseState, quaternion_from_yaw
from navlab.real.common.fcu_status import (
    FCU_STATUS_PARAMETER_NAMES,
    arducopter_mode_name,
    infer_external_nav_source_set,
    source_set_id,
)
from navlab.real.companion.nodes.imu_bridge import (
    GRAVITY_MPS2,
    ImuBridgeStatus,
    MavlinkImuSample,
    encode_imu_status,
    sample_from_highres_imu,
    sample_from_raw_imu,
    sample_from_scaled_imu,
    state_for_imu_status,
)


@dataclass(frozen=True, slots=True)
class NedPoseSample:
    x_north_m: float
    y_east_m: float
    z_down_m: float
    yaw_rad: float = 0.0


@dataclass(frozen=True, slots=True)
class PoseMirrorStatus:
    state: str
    local_position_present: bool
    local_position_age_ms: float
    set_pose_count: int
    last_gazebo_x: float | None
    last_gazebo_y: float | None
    last_gazebo_z: float | None
    last_yaw_rad: float | None
    reason: str


@dataclass(frozen=True, slots=True)
class MavlinkTelemetryStatus:
    state: str
    heartbeat_seen: bool
    target_system: int | None
    target_component: int | None
    armed: bool
    mode_number: int | None
    mode_name: str
    local_position_present: bool
    local_position_age_ms: float
    local_position_valid: bool
    active_source_set: str
    configured_external_nav_source_set: str
    observed_ekf_source_set: str
    observed_ekf_source_set_text: str
    external_nav_seen_by_fcu: bool | None
    ekf_source_set_switch: dict[str, bool | int | str | None]
    parameters: dict[str, int | float | str]
    ekf_flags: list[int]
    command_acks: list[dict[str, int]]
    statustext: list[dict[str, int | str]]
    message_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class ReplayStaticTransformSpec:
    parent_frame_id: str
    child_frame_id: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    yaw_rad: float = 0.0


def ned_to_gazebo_pose(
    sample: NedPoseSample,
    *,
    z_offset_m: float = 0.0,
    min_z_m: float = 0.1,
) -> PlanarPoseState:
    return PlanarPoseState(
        x=sample.x_north_m,
        y=sample.y_east_m,
        z=max(min_z_m, -sample.z_down_m + z_offset_m),
        yaw=sample.yaw_rad,
    )


def build_pose_stamped_fields(pose: PlanarPoseState) -> dict[str, float]:
    qx, qy, qz, qw = quaternion_from_yaw(pose.yaw)
    return {
        "x": pose.x,
        "y": pose.y,
        "z": pose.z,
        "qx": qx,
        "qy": qy,
        "qz": qz,
        "qw": qw,
    }


def sample_from_attitude(msg: object) -> MavlinkImuSample:
    return MavlinkImuSample(
        source_message="ATTITUDE",
        linear_acceleration_x=0.0,
        linear_acceleration_y=0.0,
        linear_acceleration_z=GRAVITY_MPS2,
        angular_velocity_x=float(getattr(msg, "rollspeed", 0.0)),
        angular_velocity_y=float(getattr(msg, "pitchspeed", 0.0)),
        angular_velocity_z=float(getattr(msg, "yawspeed", 0.0)),
    )


def build_replay_transform_fields(
    *,
    parent_frame_id: str,
    child_frame_id: str,
    pose: PlanarPoseState,
) -> dict[str, float | str]:
    fields = build_pose_stamped_fields(pose)
    return {
        "parent_frame_id": parent_frame_id,
        "child_frame_id": child_frame_id,
        **fields,
    }


def default_replay_static_transforms(
    *,
    root_frame_id: str,
    map_frame_id: str,
    odom_frame_id: str,
    sensor_base_frame_id: str,
    laser_frame_id: str,
    imu_frame_id: str,
    laser_x_m: float,
    laser_y_m: float,
    laser_z_m: float,
    laser_yaw_rad: float = 0.0,
) -> tuple[ReplayStaticTransformSpec, ...]:
    transforms = [
        ReplayStaticTransformSpec(parent_frame_id=root_frame_id, child_frame_id=map_frame_id),
    ]
    if odom_frame_id:
        transforms.append(ReplayStaticTransformSpec(parent_frame_id=map_frame_id, child_frame_id=odom_frame_id))
    transforms.append(
        ReplayStaticTransformSpec(
            parent_frame_id=sensor_base_frame_id,
            child_frame_id=laser_frame_id,
            x=laser_x_m,
            y=laser_y_m,
            z=laser_z_m,
            yaw_rad=laser_yaw_rad,
        )
    )
    if imu_frame_id != laser_frame_id:
        transforms.append(ReplayStaticTransformSpec(parent_frame_id=sensor_base_frame_id, child_frame_id=imu_frame_id))
    return tuple(transforms)


def yaw_from_pose_orientation(orientation: object) -> float:
    x = float(orientation.x)
    y = float(orientation.y)
    z = float(orientation.z)
    w = float(orientation.w)
    return math.atan2(2.0 * ((w * z) + (x * y)), 1.0 - (2.0 * ((y * y) + (z * z))))


def stamp_fields_to_nanoseconds(sec: int, nanosec: int) -> int:
    return int(sec) * 1_000_000_000 + int(nanosec)


def anchored_sim_stamp_nanoseconds(
    *,
    anchor_stamp_ns: int,
    anchor_monotonic: float,
    now_monotonic: float,
) -> int:
    elapsed_ns = max(0, int((now_monotonic - anchor_monotonic) * 1_000_000_000))
    return anchor_stamp_ns + elapsed_ns


def next_monotonic_stamp_nanoseconds(candidate_ns: int, previous_ns: int | None) -> int:
    if previous_ns is None:
        return candidate_ns
    return max(candidate_ns, previous_ns + 1)


def next_imu_output_stamp_nanoseconds(
    *,
    stamp_source_ns: int | None,
    stamp_source_monotonic: float,
    now_monotonic: float,
    node_clock_ns: int,
    previous_output_ns: int | None,
) -> int:
    if stamp_source_ns is None:
        candidate_ns = node_clock_ns
    else:
        candidate_ns = anchored_sim_stamp_nanoseconds(
            anchor_stamp_ns=stamp_source_ns,
            anchor_monotonic=stamp_source_monotonic,
            now_monotonic=now_monotonic,
        )
    return next_monotonic_stamp_nanoseconds(candidate_ns, previous_output_ns)


def marker_has_displayable_geometry(marker: object) -> bool:
    action = int(getattr(marker, "action", 0))
    if action in {2, 3}:  # DELETE, DELETEALL
        return True

    marker_type = int(getattr(marker, "type", -1))
    points = list(getattr(marker, "points", []))
    if marker_type == 4:  # LINE_STRIP
        return len(points) >= 2
    if marker_type == 5:  # LINE_LIST
        return len(points) >= 2 and len(points) % 2 == 0
    if marker_type in {6, 7, 8}:  # CUBE_LIST, SPHERE_LIST, POINTS
        return len(points) >= 1
    return True


def filter_displayable_markers(markers: Sequence[object]) -> list[object]:
    return [marker for marker in markers if marker_has_displayable_geometry(marker)]


def encode_pose_mirror_status(status: PoseMirrorStatus) -> str:
    return json.dumps(
        {
            "state": status.state,
            "local_position": {
                "present": status.local_position_present,
                "age_ms": round(status.local_position_age_ms, 3),
            },
            "set_pose_count": status.set_pose_count,
            "last_gazebo_pose": {
                "x": status.last_gazebo_x,
                "y": status.last_gazebo_y,
                "z": status.last_gazebo_z,
                "yaw_rad": status.last_yaw_rad,
            },
            "reason": status.reason,
        },
        separators=(",", ":"),
    )


def encode_mavlink_telemetry_status(status: MavlinkTelemetryStatus) -> str:
    return json.dumps(
        {
            "state": status.state,
            "heartbeat_seen": status.heartbeat_seen,
            "target_system": status.target_system,
            "target_component": status.target_component,
            "armed": status.armed,
            "mode_number": status.mode_number,
            "mode_name": status.mode_name,
            "mode": status.mode_name,
            "local_position": {
                "present": status.local_position_present,
                "age_ms": round(status.local_position_age_ms, 3),
            },
            "local_position_valid": status.local_position_valid,
            "active_source_set": status.active_source_set,
            "configured_external_nav_source_set": status.configured_external_nav_source_set,
            "observed_ekf_source_set": status.observed_ekf_source_set,
            "observed_ekf_source_set_text": status.observed_ekf_source_set_text,
            "external_nav_seen_by_fcu": status.external_nav_seen_by_fcu,
            "ekf_source_set_switch": status.ekf_source_set_switch,
            "parameters": status.parameters,
            "ekf": {
                "flags_seen": status.ekf_flags,
            },
            "command_acks": status.command_acks,
            "statustext": status.statustext,
            "message_counts": status.message_counts,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def normalize_mavlink_param_value(value: object) -> int | float | str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").rstrip("\x00")
    if isinstance(value, str):
        return value.rstrip("\x00")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isfinite(number) and number.is_integer():
        return int(number)
    return number


def parse_ekf_source_set_from_statustext(text: str) -> str | None:
    """Extract ArduPilot's EKF source set observation from STATUSTEXT, when present."""
    clean = text.rstrip("\x00").strip()
    if not re.search(r"\bekf\w*\b", clean, flags=re.IGNORECASE):
        return None
    match = re.search(r"\bsource\s*set\b\D*([123])\b", clean, flags=re.IGNORECASE)
    if match is None:
        return None
    return f"SRC{match.group(1)}"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Observe ArduPilot local NED position and publish replay pose topics.")
    parser.add_argument("--endpoint", default="tcp:sitl:5763")
    parser.add_argument("--pose-topic", default="/sim/uav_pose")
    parser.add_argument("--pose-frame-id", default="navlab_world")
    parser.add_argument("--map-frame-id", default="map")
    parser.add_argument("--odom-frame-id", default="odom")
    parser.add_argument("--sensor-base-frame-id", default="base_link")
    parser.add_argument("--replay-base-frame-id", default="")
    parser.add_argument("--replay-base-parent-frame-id", default="")
    parser.add_argument("--disable-replay-static-tf", action="store_true")
    parser.add_argument("--laser-frame-id", default="laser_frame")
    parser.add_argument("--replay-imu-frame-id", default="")
    parser.add_argument("--laser-x-m", type=float, default=0.05)
    parser.add_argument("--laser-y-m", type=float, default=0.0)
    parser.add_argument("--laser-z-m", type=float, default=0.13)
    parser.add_argument("--laser-yaw-rad", type=float, default=0.0)
    parser.add_argument("--constraint-list-topic", default="/constraint_list")
    parser.add_argument("--replay-constraints-topic", default="/navlab/replay/constraint_markers")
    parser.add_argument("--status-topic", default="/navlab/pose_mirror/status")
    parser.add_argument("--mavlink-status-topic", default="/navlab/mavlink/status")
    parser.add_argument("--fallback-pose-topic", default="")
    parser.add_argument("--imu-topic", default="/imu/data")
    parser.add_argument("--imu-status-topic", default="/imu/status")
    parser.add_argument("--imu-frame-id", default="fcu_imu")
    parser.add_argument("--imu-source-label", default="fcu_mavlink_navlab")
    parser.add_argument(
        "--imu-stamp-source-topic",
        default="/scan",
        help="Topic whose header stamp anchors FCU IMU output into Gazebo sim time; set empty to use node clock.",
    )
    parser.add_argument("--imu-min-rate-hz", type=float, default=4.0)
    parser.add_argument("--allow-raw-imu", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--synthetic-imu-when-mavlink-missing", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--rate-hz", type=float, default=10.0)
    parser.add_argument("--stream-rate-hz", type=float, default=10.0)
    parser.add_argument("--auto-ekf-source-set", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--ekf-source-set-retry-sec", type=float, default=2.0)
    parser.add_argument("--timeout-sec", type=float, default=1.0)
    parser.add_argument("--reconnect-sec", type=float, default=2.0)
    parser.add_argument("--stale-reconnect-sec", type=float, default=5.0)
    parser.add_argument("--z-offset-m", type=float, default=0.0)
    parser.add_argument("--min-z-m", type=float, default=0.1)
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


def _request_streams(connection, target_system: int, target_component: int, hz: float) -> None:
    from pymavlink.dialects.v20 import ardupilotmega as mavlink

    for message_id in (
        mavlink.MAVLINK_MSG_ID_LOCAL_POSITION_NED,
        mavlink.MAVLINK_MSG_ID_ATTITUDE,
        mavlink.MAVLINK_MSG_ID_HEARTBEAT,
        mavlink.MAVLINK_MSG_ID_EKF_STATUS_REPORT,
        mavlink.MAVLINK_MSG_ID_STATUSTEXT,
        mavlink.MAVLINK_MSG_ID_HIGHRES_IMU,
        mavlink.MAVLINK_MSG_ID_SCALED_IMU,
        mavlink.MAVLINK_MSG_ID_RAW_IMU,
    ):
        _send_message_interval(connection, target_system, target_component, message_id, hz)


def run(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        import rclpy
        from geometry_msgs.msg import PoseStamped, TransformStamped
        from pymavlink import mavutil
        from pymavlink.dialects.v20 import ardupilotmega as mavlink
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
        from sensor_msgs.msg import Imu, LaserScan
        from std_msgs.msg import String
        from tf2_msgs.msg import TFMessage
        from visualization_msgs.msg import MarkerArray
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "mavlink_gazebo_pose_mirror requires ROS2 Python packages and pymavlink. "
            "Run it from the NavLab companion/sim runtime image."
        ) from exc

    class MavlinkGazeboPoseMirror(Node):
        def __init__(self) -> None:
            super().__init__("navlab_mavlink_pose_mirror")
            self._connection = None
            self._pose_pub = self.create_publisher(PoseStamped, args.pose_topic, 10)
            self._tf_pub = self.create_publisher(TFMessage, "/tf", 10)
            static_tf_qos = QoSProfile(depth=1)
            static_tf_qos.reliability = ReliabilityPolicy.RELIABLE
            static_tf_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
            self._tf_static_pub = self.create_publisher(TFMessage, "/tf_static", static_tf_qos)
            self._replay_constraints_pub = self.create_publisher(MarkerArray, args.replay_constraints_topic, 10)
            self._imu_pub = self.create_publisher(Imu, args.imu_topic, 10)
            self._imu_status_pub = self.create_publisher(String, args.imu_status_topic, 10)
            self._status_pub = self.create_publisher(String, args.status_topic, 10)
            self._mavlink_status_pub = self.create_publisher(String, args.mavlink_status_topic, 10)
            self._target_system: int | None = None
            self._target_component: int | None = None
            self._heartbeat_seen = False
            self._armed = False
            self.mode_number: int | None = None
            self._last_sample: NedPoseSample | None = None
            self._last_imu_sample: MavlinkImuSample | None = None
            self._last_imu_sample_monotonic = 0.0
            self._last_imu_stamp_source_ns: int | None = None
            self._last_imu_stamp_source_monotonic = 0.0
            self._last_imu_output_stamp_ns: int | None = None
            self._imu_input_rate_hz = 0.0
            self._imu_count = 0
            self._raw_imu_count = 0
            self._last_sample_monotonic = 0.0
            self._last_yaw_rad = 0.0
            self._last_pose: PlanarPoseState | None = None
            self._fallback_pose: PlanarPoseState | None = None
            self._fallback_pose_monotonic = 0.0
            self._fallback_pose_count = 0
            self._set_pose_count = 0
            self._message_counts: dict[str, int] = {}
            self._command_acks: list[dict[str, int]] = []
            self._statustext: list[dict[str, int | str]] = []
            self._ekf_flags: list[int] = []
            self._parameters: dict[str, int | float | str] = {}
            self._observed_ekf_source_set = ""
            self._observed_ekf_source_set_text = ""
            self._ekf_source_set_switch_sent_source = ""
            self._ekf_source_set_switch_sent_count = 0
            self._ekf_source_set_switch_last_send = 0.0
            self._ekf_source_set_switch_ack_result: int | None = None
            self._next_parameter_request = 0.0
            self._parameter_request_index = 0
            self._next_stream_request = 0.0
            self._next_reconnect_monotonic = 0.0
            self._last_mavlink_message_monotonic = 0.0
            self._connect_mavlink()
            if args.imu_stamp_source_topic:
                self.create_subscription(
                    LaserScan,
                    args.imu_stamp_source_topic,
                    self._handle_imu_stamp_source,
                    qos_profile_sensor_data,
                )
            if args.fallback_pose_topic:
                self.create_subscription(
                    PoseStamped,
                    args.fallback_pose_topic,
                    self._handle_fallback_pose,
                    10,
                )
            if args.constraint_list_topic:
                self.create_subscription(
                    MarkerArray,
                    args.constraint_list_topic,
                    self._handle_constraint_list,
                    10,
                )
            self._static_transform_specs = (
                ()
                if args.disable_replay_static_tf
                else default_replay_static_transforms(
                    root_frame_id=args.pose_frame_id,
                    map_frame_id=args.map_frame_id,
                    odom_frame_id=args.odom_frame_id,
                    sensor_base_frame_id=args.sensor_base_frame_id,
                    laser_frame_id=args.laser_frame_id,
                    imu_frame_id=args.replay_imu_frame_id or args.imu_frame_id,
                    laser_x_m=args.laser_x_m,
                    laser_y_m=args.laser_y_m,
                    laser_z_m=args.laser_z_m,
                    laser_yaw_rad=args.laser_yaw_rad,
                )
            )
            if self._static_transform_specs:
                self._publish_static_replay_tf()
            self.create_timer(1.0 / args.rate_hz, self._tick)
            self.create_timer(2.0, self._publish_static_replay_tf)
            replay_base_parent = args.replay_base_parent_frame_id or args.pose_frame_id
            replay_base = args.replay_base_frame_id or "<disabled>"
            self.get_logger().info(
                f"pose observer started endpoint={args.endpoint} "
                f"imu_stamp_source={args.imu_stamp_source_topic or 'node_clock'} "
                f"fallback_pose_topic={args.fallback_pose_topic or '<disabled>'} "
                f"replay_tf={args.pose_frame_id}->{args.map_frame_id}, "
                f"{args.map_frame_id}->{args.odom_frame_id}, "
                f"{replay_base_parent}->{replay_base}, "
                f"{args.sensor_base_frame_id}->{args.laser_frame_id}"
            )

        def _connect_mavlink(self) -> None:
            now = time.monotonic()
            if now < self._next_reconnect_monotonic:
                return
            self._next_reconnect_monotonic = now + args.reconnect_sec
            old_connection = self._connection
            if old_connection is not None:
                try:
                    old_connection.close()
                except Exception:
                    pass
            try:
                self._connection = mavutil.mavlink_connection(args.endpoint, dialect="ardupilotmega")
                self._last_mavlink_message_monotonic = now
            except Exception as exc:
                self._connection = None
                self.get_logger().warn(f"mavlink reconnect failed endpoint={args.endpoint}: {exc}")

        def _reconnect_if_stale(self, now: float) -> None:
            if self._connection is None:
                self._connect_mavlink()
                return
            if self._last_mavlink_message_monotonic <= 0.0:
                return
            if now - self._last_mavlink_message_monotonic >= args.stale_reconnect_sec:
                self.get_logger().warn(
                    f"mavlink stream stale for {now - self._last_mavlink_message_monotonic:.1f}s; reconnecting"
                )
                self._connect_mavlink()

        def _tick(self) -> None:
            self._drain_mavlink()
            now = time.monotonic()
            self._reconnect_if_stale(now)
            self._publish_synthetic_imu_if_needed(now)
            if (
                self._connection is not None
                and self._target_system is not None
                and self._target_component is not None
                and now >= self._next_stream_request
            ):
                _request_streams(self._connection, self._target_system, self._target_component, args.stream_rate_hz)
                self._next_stream_request = now + 2.0
            self._request_status_parameter_if_needed(now)
            self._switch_ekf_source_set_if_needed(now)

            age_sec = now - self._last_sample_monotonic if self._last_sample is not None else math.inf
            if self._last_sample is None:
                if self._publish_fallback_pose_if_fresh(now):
                    return
                self._publish_status("waiting_for_local_position", age_sec, "waiting_for_LOCAL_POSITION_NED")
                self._publish_mavlink_status()
                self._publish_imu_status()
                return
            if age_sec > args.timeout_sec:
                if self._publish_fallback_pose_if_fresh(now):
                    return
                self._publish_status("timeout", age_sec, "local_position_timeout")
                self._publish_mavlink_status()
                self._publish_imu_status()
                return

            pose = ned_to_gazebo_pose(self._last_sample, z_offset_m=args.z_offset_m, min_z_m=args.min_z_m)
            self._last_pose = pose
            self._publish_pose(pose)
            self._publish_status("mirroring", age_sec, "mavlink_local_position_observed")
            self._publish_mavlink_status()
            self._publish_imu_status()

        def _drain_mavlink(self) -> None:
            if self._connection is None:
                return
            while True:
                try:
                    msg = self._connection.recv_match(blocking=False)
                except Exception as exc:
                    self.get_logger().warn(f"mavlink receive failed endpoint={args.endpoint}: {exc}")
                    self._connection = None
                    return
                if msg is None:
                    return
                msg_type = msg.get_type()
                self._last_mavlink_message_monotonic = time.monotonic()
                self._message_counts[msg_type] = self._message_counts.get(msg_type, 0) + 1
                if msg_type == "HEARTBEAT" and int(msg.autopilot) != mavlink.MAV_AUTOPILOT_INVALID:
                    self._heartbeat_seen = True
                    self._target_system = msg.get_srcSystem()
                    self._target_component = msg.get_srcComponent()
                    self._armed = bool(int(msg.base_mode) & mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    self.mode_number = int(msg.custom_mode)
                elif msg_type == "ATTITUDE":
                    self._last_yaw_rad = float(msg.yaw)
                    self._handle_imu_sample(sample_from_attitude(msg))
                elif msg_type == "LOCAL_POSITION_NED":
                    self._last_sample = NedPoseSample(
                        x_north_m=float(msg.x),
                        y_east_m=float(msg.y),
                        z_down_m=float(msg.z),
                        yaw_rad=self._last_yaw_rad,
                    )
                    self._last_sample_monotonic = time.monotonic()
                elif msg_type == "COMMAND_ACK":
                    if len(self._command_acks) < 80:
                        self._command_acks.append({"command": int(msg.command), "result": int(msg.result)})
                    if int(msg.command) == int(mavlink.MAV_CMD_SET_EKF_SOURCE_SET):
                        self._ekf_source_set_switch_ack_result = int(msg.result)
                elif msg_type == "STATUSTEXT":
                    text = getattr(msg, "text", "")
                    if isinstance(text, bytes):
                        text = text.decode("utf-8", errors="replace")
                    text_clean = str(text).rstrip("\x00")
                    observed_source_set = parse_ekf_source_set_from_statustext(text_clean)
                    if observed_source_set is not None:
                        self._observed_ekf_source_set = observed_source_set
                        self._observed_ekf_source_set_text = text_clean
                    if len(self._statustext) < 80:
                        self._statustext.append({"severity": int(msg.severity), "text": text_clean})
                elif msg_type == "EKF_STATUS_REPORT":
                    self._ekf_flags.append(int(msg.flags))
                elif msg_type == "PARAM_VALUE":
                    self._handle_param_value(msg)
                elif msg_type == "HIGHRES_IMU":
                    self._handle_imu_sample(sample_from_highres_imu(msg))
                elif msg_type == "SCALED_IMU":
                    self._handle_imu_sample(sample_from_scaled_imu(msg))
                elif msg_type == "RAW_IMU" and args.allow_raw_imu:
                    self._raw_imu_count += 1
                    self._handle_imu_sample(sample_from_raw_imu(msg))

        def _handle_param_value(self, msg: object) -> None:
            param_id = getattr(msg, "param_id", "")
            if isinstance(param_id, bytes):
                param_name = param_id.decode("utf-8", errors="replace").rstrip("\x00")
            else:
                param_name = str(param_id).rstrip("\x00")
            if param_name in FCU_STATUS_PARAMETER_NAMES:
                self._parameters[param_name] = normalize_mavlink_param_value(getattr(msg, "param_value", ""))

        def _switch_ekf_source_set_if_needed(self, now: float) -> None:
            if not args.auto_ekf_source_set:
                return
            if self._connection is None or self._target_system is None or self._target_component is None:
                return
            target_source = infer_external_nav_source_set(self._parameters)
            target_source_id = source_set_id(target_source)
            if target_source_id is None:
                return
            if (
                self._ekf_source_set_switch_sent_source == target_source
                and self._ekf_source_set_switch_ack_result == int(mavlink.MAV_RESULT_ACCEPTED)
            ):
                return
            if (
                self._ekf_source_set_switch_sent_source == target_source
                and now - self._ekf_source_set_switch_last_send < args.ekf_source_set_retry_sec
            ):
                return
            try:
                self._connection.mav.command_long_send(
                    self._target_system,
                    self._target_component,
                    mavlink.MAV_CMD_SET_EKF_SOURCE_SET,
                    0,
                    float(target_source_id),
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                )
            except Exception as exc:
                self.get_logger().warn(f"ekf source set switch failed target={target_source}: {exc}")
                self._ekf_source_set_switch_last_send = now
                return
            self._ekf_source_set_switch_sent_source = target_source
            self._ekf_source_set_switch_sent_count += 1
            self._ekf_source_set_switch_last_send = now
            self._ekf_source_set_switch_ack_result = None
            self.get_logger().info(f"requested EKF source set {target_source} for ExternalNav")

        def _request_status_parameter_if_needed(self, now: float) -> None:
            if self._connection is None or self._target_system is None or self._target_component is None:
                return
            if not FCU_STATUS_PARAMETER_NAMES or now < self._next_parameter_request:
                return
            param_name = FCU_STATUS_PARAMETER_NAMES[self._parameter_request_index]
            try:
                self._connection.mav.param_request_read_send(
                    self._target_system,
                    self._target_component,
                    param_name.encode("ascii"),
                    -1,
                )
            except Exception as exc:
                self.get_logger().warn(f"mavlink parameter request failed param={param_name}: {exc}")
                self._next_parameter_request = now + 2.0
                return
            self._parameter_request_index = (self._parameter_request_index + 1) % len(FCU_STATUS_PARAMETER_NAMES)
            self._next_parameter_request = now + (10.0 if self._parameter_request_index == 0 else 0.1)

        def _handle_constraint_list(self, msg: MarkerArray) -> None:
            filtered = MarkerArray()
            filtered.markers = filter_displayable_markers(msg.markers)
            self._replay_constraints_pub.publish(filtered)

        def _handle_fallback_pose(self, msg: PoseStamped) -> None:
            self._fallback_pose = PlanarPoseState(
                x=float(msg.pose.position.x),
                y=float(msg.pose.position.y),
                z=float(msg.pose.position.z),
                yaw=yaw_from_pose_orientation(msg.pose.orientation),
            )
            self._fallback_pose_monotonic = time.monotonic()
            self._fallback_pose_count += 1

        def _publish_fallback_pose_if_fresh(self, now: float) -> bool:
            if self._fallback_pose is None:
                return False
            age_sec = now - self._fallback_pose_monotonic
            if age_sec > args.timeout_sec:
                return False
            self._last_pose = self._fallback_pose
            self._publish_pose(self._fallback_pose)
            self._publish_status("mirroring", age_sec, "fallback_local_position_pose_observed")
            self._publish_mavlink_status()
            self._publish_imu_status()
            return True

        def _publish_pose(self, pose: PlanarPoseState) -> None:
            fields = build_pose_stamped_fields(pose)
            message = PoseStamped()
            stamp = self.get_clock().now().to_msg()
            message.header.stamp = stamp
            message.header.frame_id = args.pose_frame_id
            message.pose.position.x = fields["x"]
            message.pose.position.y = fields["y"]
            message.pose.position.z = fields["z"]
            message.pose.orientation.x = fields["qx"]
            message.pose.orientation.y = fields["qy"]
            message.pose.orientation.z = fields["qz"]
            message.pose.orientation.w = fields["qw"]
            self._pose_pub.publish(message)
            if not args.replay_base_frame_id:
                return
            transform = self._transform_from_fields(
                build_replay_transform_fields(
                    parent_frame_id=args.replay_base_parent_frame_id or args.pose_frame_id,
                    child_frame_id=args.replay_base_frame_id,
                    pose=pose,
                ),
                stamp=stamp,
            )
            self._tf_pub.publish(TFMessage(transforms=[transform]))

        def _publish_static_replay_tf(self) -> None:
            if not self._static_transform_specs:
                return
            stamp = self.get_clock().now().to_msg()
            transforms = [
                self._transform_from_fields(
                    build_replay_transform_fields(
                        parent_frame_id=spec.parent_frame_id,
                        child_frame_id=spec.child_frame_id,
                        pose=PlanarPoseState(x=spec.x, y=spec.y, z=spec.z, yaw=spec.yaw_rad),
                    ),
                    stamp=stamp,
                )
                for spec in self._static_transform_specs
            ]
            self._tf_static_pub.publish(TFMessage(transforms=transforms))

        def _transform_from_fields(self, fields: dict[str, float | str], *, stamp) -> TransformStamped:
            transform = TransformStamped()
            transform.header.stamp = stamp
            transform.header.frame_id = str(fields["parent_frame_id"])
            transform.child_frame_id = str(fields["child_frame_id"])
            transform.transform.translation.x = float(fields["x"])
            transform.transform.translation.y = float(fields["y"])
            transform.transform.translation.z = float(fields["z"])
            transform.transform.rotation.x = float(fields["qx"])
            transform.transform.rotation.y = float(fields["qy"])
            transform.transform.rotation.z = float(fields["qz"])
            transform.transform.rotation.w = float(fields["qw"])
            return transform

        def _handle_imu_stamp_source(self, message: LaserScan) -> None:
            stamp = message.header.stamp
            stamp_ns = stamp_fields_to_nanoseconds(stamp.sec, stamp.nanosec)
            if stamp_ns <= 0:
                return
            self._last_imu_stamp_source_ns = stamp_ns
            self._last_imu_stamp_source_monotonic = time.monotonic()

        def _handle_imu_sample(self, sample: MavlinkImuSample) -> None:
            now = time.monotonic()
            if self._last_imu_sample is not None:
                delta = now - self._last_imu_sample_monotonic
                if delta > 0.0:
                    current_rate = 1.0 / delta
                    self._imu_input_rate_hz = (
                        current_rate
                        if self._imu_input_rate_hz <= 0.0
                        else (0.8 * self._imu_input_rate_hz + 0.2 * current_rate)
                    )
            self._last_imu_sample = sample
            self._last_imu_sample_monotonic = now
            self._imu_count += 1
            self._publish_imu(sample)

        def _publish_synthetic_imu_if_needed(self, now: float) -> None:
            if not args.synthetic_imu_when_mavlink_missing:
                return
            if (
                self._last_imu_sample is not None
                and self._last_imu_sample.source_message != "SIM_GAZEBO_FALLBACK"
                and now - self._last_imu_sample_monotonic <= args.timeout_sec
            ):
                return
            self._handle_imu_sample(
                MavlinkImuSample(
                    source_message="SIM_GAZEBO_FALLBACK",
                    linear_acceleration_x=0.0,
                    linear_acceleration_y=0.0,
                    linear_acceleration_z=GRAVITY_MPS2,
                    angular_velocity_x=0.0,
                    angular_velocity_y=0.0,
                    angular_velocity_z=0.0,
                )
            )

        def _imu_stamp(self):
            stamp = self.get_clock().now().to_msg()
            stamp_ns = next_imu_output_stamp_nanoseconds(
                stamp_source_ns=self._last_imu_stamp_source_ns,
                stamp_source_monotonic=self._last_imu_stamp_source_monotonic,
                now_monotonic=time.monotonic(),
                node_clock_ns=stamp_fields_to_nanoseconds(stamp.sec, stamp.nanosec),
                previous_output_ns=self._last_imu_output_stamp_ns,
            )
            self._last_imu_output_stamp_ns = stamp_ns
            stamp.sec = int(stamp_ns // 1_000_000_000)
            stamp.nanosec = int(stamp_ns % 1_000_000_000)
            return stamp

        def _publish_imu(self, sample: MavlinkImuSample) -> None:
            imu = Imu()
            imu.header.stamp = self._imu_stamp()
            imu.header.frame_id = args.imu_frame_id
            imu.orientation.w = 1.0
            imu.orientation_covariance[0] = -1.0
            imu.angular_velocity.x = sample.angular_velocity_x
            imu.angular_velocity.y = sample.angular_velocity_y
            imu.angular_velocity.z = sample.angular_velocity_z
            imu.linear_acceleration.x = sample.linear_acceleration_x
            imu.linear_acceleration.y = sample.linear_acceleration_y
            imu.linear_acceleration.z = sample.linear_acceleration_z
            self._imu_pub.publish(imu)

        def _publish_status(self, state: str, age_sec: float, reason: str) -> None:
            pose = self._last_pose
            status = PoseMirrorStatus(
                state=state,
                local_position_present=self._last_sample is not None or self._fallback_pose is not None,
                local_position_age_ms=-1.0 if math.isinf(age_sec) else age_sec * 1000.0,
                set_pose_count=self._set_pose_count,
                last_gazebo_x=None if pose is None else pose.x,
                last_gazebo_y=None if pose is None else pose.y,
                last_gazebo_z=None if pose is None else pose.z,
                last_yaw_rad=None if pose is None else pose.yaw,
                reason=reason,
            )
            message = String()
            message.data = encode_pose_mirror_status(status)
            self._status_pub.publish(message)

        def _publish_mavlink_status(self) -> None:
            if self._last_sample is not None:
                state = "streaming"
            elif self._heartbeat_seen:
                state = "waiting_for_local_position"
            else:
                state = "waiting_for_heartbeat"
            local_position_age_ms = (
                -1.0
                if self._last_sample is None
                else max(0.0, (time.monotonic() - self._last_sample_monotonic) * 1000.0)
            )
            local_position_valid = self._last_sample is not None and local_position_age_ms <= args.timeout_sec * 1000.0
            configured_external_nav_source_set = infer_external_nav_source_set(self._parameters)
            observed_ekf_source_set = self._observed_ekf_source_set or "not_observed"
            external_nav_seen = (
                True if local_position_valid and configured_external_nav_source_set in {"SRC1", "SRC2"} else None
            )
            message = String()
            message.data = encode_mavlink_telemetry_status(
                MavlinkTelemetryStatus(
                    state=state,
                    heartbeat_seen=self._heartbeat_seen,
                    target_system=self._target_system,
                    target_component=self._target_component,
                    armed=self._armed,
                    mode_number=self.mode_number,
                    mode_name=arducopter_mode_name(self.mode_number),
                    local_position_present=self._last_sample is not None,
                    local_position_age_ms=local_position_age_ms,
                    local_position_valid=local_position_valid,
                    active_source_set=observed_ekf_source_set,
                    configured_external_nav_source_set=configured_external_nav_source_set,
                    observed_ekf_source_set=observed_ekf_source_set,
                    observed_ekf_source_set_text=self._observed_ekf_source_set_text,
                    external_nav_seen_by_fcu=external_nav_seen,
                    ekf_source_set_switch=self._ekf_source_set_switch_status(configured_external_nav_source_set),
                    parameters=dict(self._parameters),
                    ekf_flags=sorted(set(self._ekf_flags)),
                    command_acks=self._command_acks[-20:],
                    statustext=self._statustext[-20:],
                    message_counts=dict(self._message_counts),
                )
            )
            self._mavlink_status_pub.publish(message)

        def _ekf_source_set_switch_status(self, target_source: str) -> dict[str, bool | int | str | None]:
            target_source_id = source_set_id(target_source)
            return {
                "enabled": bool(args.auto_ekf_source_set),
                "target_source_set": target_source,
                "target_source_set_id": target_source_id,
                "sent": self._ekf_source_set_switch_sent_count > 0,
                "sent_count": self._ekf_source_set_switch_sent_count,
                "ack_result": self._ekf_source_set_switch_ack_result,
            }

        def _publish_imu_status(self) -> None:
            now = time.monotonic()
            present = self._last_imu_sample is not None
            age_sec = now - self._last_imu_sample_monotonic if present else math.inf
            fresh = present and age_sec <= args.timeout_sec
            rate_ok = self._imu_input_rate_hz >= args.imu_min_rate_hz
            status = ImuBridgeStatus(
                state=state_for_imu_status(present=present, fresh=fresh, rate_ok=rate_ok),
                ready=present and fresh and rate_ok,
                source_label=args.imu_source_label,
                source_message=None if self._last_imu_sample is None else self._last_imu_sample.source_message,
                input_present=present,
                input_fresh=fresh,
                input_age_ms=-1.0 if math.isinf(age_sec) else age_sec * 1000.0,
                input_rate_hz=self._imu_input_rate_hz,
                input_rate_ok=rate_ok,
                min_rate_hz=args.imu_min_rate_hz,
                output_topic=args.imu_topic,
                output_frame_id=args.imu_frame_id,
                count=self._imu_count,
                raw_fallback_count=self._raw_imu_count,
            )
            message = String()
            message.data = encode_imu_status(status)
            self._imu_status_pub.publish(message)

    rclpy.init(args=None)
    node = MavlinkGazeboPoseMirror()
    try:
        rclpy.spin(node)
    except Exception as exc:
        if rclpy.ok():
            raise
        node.get_logger().info(f"pose observer shutting down: {exc}")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
