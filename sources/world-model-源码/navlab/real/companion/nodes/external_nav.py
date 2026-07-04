from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections.abc import Sequence

os.environ.setdefault("MAVLINK20", "1")

try:
    import rclpy
    from geometry_msgs.msg import PoseStamped
    from nav_msgs.msg import Odometry
    from pymavlink import mavutil
    from pymavlink.dialects.v20 import ardupilotmega as mavlink
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from std_msgs.msg import String
except ModuleNotFoundError:
    rclpy = None
    PoseStamped = object
    Odometry = object
    mavutil = None
    mavlink = None
    ExternalShutdownException = KeyboardInterrupt
    Node = object
    String = object

from navlab.real.companion.nodes.pose_mirror import NedPoseSample, build_pose_stamped_fields, ned_to_gazebo_pose

MAVLINK_TIME_SOURCE = "sender_monotonic_clock_us"
MAVLINK_POSITION_FRAME = "MAV_FRAME_LOCAL_FRD"
MAVLINK_VELOCITY_FRAME = "MAV_FRAME_BODY_FRD"
MAVLINK_ESTIMATOR_TYPE = "MAV_ESTIMATOR_TYPE_VIO"
ROS_ODOM_SEMANTICS = "ROS ENU position with FLU body twist"


def _upper_triangular_covariance(covariance: Sequence[float]) -> list[float]:
    if len(covariance) != 36:
        return [0.0] * 21

    values: list[float] = []
    for row in range(6):
        for col in range(row, 6):
            value = covariance[(row * 6) + col]
            values.append(0.0 if math.isnan(value) else float(value))
    return values


def _ros_quat_to_frd(q: object) -> list[float]:
    # ROS odom is treated as ENU/FLU. MAVLink output is LOCAL_FRD/BODY_FRD.
    return [float(q.w), float(q.x), -float(q.y), -float(q.z)]


def _yaw_from_ros_quat_enu(q: object) -> float:
    x = float(q.x)
    y = float(q.y)
    z = float(q.z)
    w = float(q.w)
    return math.atan2(2.0 * ((w * z) + (x * y)), 1.0 - (2.0 * ((y * y) + (z * z))))


def ros_enu_position_to_mavlink_local_frd(
    *, x_enu_m: float, y_enu_m: float, z_enu_m: float
) -> tuple[float, float, float]:
    # ArduPilot's ODOMETRY handler requires MAV_FRAME_LOCAL_FRD. The runtime
    # ROS map contract is x=west, y=north for the hover world, so map x projects
    # to negative local-NED east.
    return y_enu_m, -x_enu_m, -z_enu_m


def ros_enu_yaw_to_mavlink_local_frd(yaw_enu_rad: float) -> float:
    return normalize_angle_rad((math.pi * 0.5) - yaw_enu_rad)


def _quat_from_roll_pitch_yaw_frd(*, roll_rad: float, pitch_rad: float, yaw_rad: float) -> list[float]:
    cr = math.cos(roll_rad * 0.5)
    sr = math.sin(roll_rad * 0.5)
    cp = math.cos(pitch_rad * 0.5)
    sp = math.sin(pitch_rad * 0.5)
    cy = math.cos(yaw_rad * 0.5)
    sy = math.sin(yaw_rad * 0.5)
    return [
        (cr * cp * cy) + (sr * sp * sy),
        (sr * cp * cy) - (cr * sp * sy),
        (cr * sp * cy) + (sr * cp * sy),
        (cr * cp * sy) - (sr * sp * cy),
    ]


def _send_message_interval(connection, target_system: int, target_component: int, message_id: int, hz: float) -> None:
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


def rate_limit_xy(
    *,
    target_x: float,
    target_y: float,
    last_x: float | None,
    last_y: float | None,
    dt_sec: float,
    max_speed_mps: float,
) -> tuple[float, float]:
    if last_x is None or last_y is None or dt_sec <= 0.0 or max_speed_mps <= 0.0:
        return target_x, target_y
    dx = target_x - last_x
    dy = target_y - last_y
    distance = math.hypot(dx, dy)
    max_distance = max_speed_mps * dt_sec
    if distance <= max_distance or distance <= 0.0:
        return target_x, target_y
    scale = max_distance / distance
    return last_x + (dx * scale), last_y + (dy * scale)


def normalize_angle_rad(angle_rad: float) -> float:
    return (angle_rad + math.pi) % (2.0 * math.pi) - math.pi


def shortest_angle_delta_rad(target_rad: float, current_rad: float) -> float:
    return normalize_angle_rad(target_rad - current_rad)


def rate_limit_yaw(
    *,
    target_yaw_rad: float,
    last_yaw_rad: float | None,
    dt_sec: float,
    max_yaw_rate_radps: float,
) -> float:
    if last_yaw_rad is None or dt_sec <= 0.0 or max_yaw_rate_radps <= 0.0:
        return normalize_angle_rad(target_yaw_rad)
    max_delta = max_yaw_rate_radps * dt_sec
    delta = shortest_angle_delta_rad(target_yaw_rad, last_yaw_rad)
    if abs(delta) <= max_delta:
        return normalize_angle_rad(target_yaw_rad)
    return normalize_angle_rad(last_yaw_rad + math.copysign(max_delta, delta))


def _odometry_mapping_status(
    *,
    input_topic: str,
    quality: int,
    reset_counter: int,
    rate_hz: float,
    source_system: int,
    use_fcu_roll_pitch: bool,
    align_yaw_to_fcu: bool,
) -> dict[str, object]:
    return {
        "input": {
            "topic": input_topic,
            "message": "nav_msgs/msg/Odometry",
            "semantics": ROS_ODOM_SEMANTICS,
        },
        "output": {
            "message": "MAVLink v2 ODOMETRY",
            "position_frame": MAVLINK_POSITION_FRAME,
            "velocity_frame": MAVLINK_VELOCITY_FRAME,
            "estimator_type": MAVLINK_ESTIMATOR_TYPE,
            "component": "MAV_COMP_ID_VISUAL_INERTIAL_ODOMETRY",
            "source_system": source_system,
            "rate_hz": rate_hz,
            "quality": quality,
            "reset_counter": reset_counter,
            "time_usec_source": MAVLINK_TIME_SOURCE,
            "roll_pitch_source": "level roll/pitch" if use_fcu_roll_pitch else "ROS odom quaternion",
            "yaw_source": "SLAM odom yaw, initial-aligned to FCU ATTITUDE" if align_yaw_to_fcu else "SLAM odom yaw",
        },
        "field_map": {
            "time_usec": MAVLINK_TIME_SOURCE,
            "x": "odom.pose.pose.position.y",
            "y": "-odom.pose.pose.position.x",
            "z": "-odom.pose.pose.position.z",
            "q": (
                "level roll/pitch + converted odom yaw"
                if use_fcu_roll_pitch
                else "[w, x, -y, -z] from odom.pose.pose.orientation"
            ),
            "vx": "odom.twist.twist.linear.x",
            "vy": "-odom.twist.twist.linear.y",
            "vz": "-odom.twist.twist.linear.z",
            "rollspeed": "0.0 (roll source is FCU ATTITUDE)" if use_fcu_roll_pitch else "odom.twist.twist.angular.x",
            "pitchspeed": "0.0 (pitch source is FCU ATTITUDE)" if use_fcu_roll_pitch else "-odom.twist.twist.angular.y",
            "yawspeed": "-odom.twist.twist.angular.z",
            "pose_covariance": "upper triangular odom.pose.covariance",
            "velocity_covariance": "upper triangular odom.twist.covariance",
        },
    }


class MavlinkExternalNavSender(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("mavlink_external_nav_sender")
        self._endpoint = args.endpoint
        self._rate_hz = args.rate_hz
        self._quality = args.quality
        self._reset_counter = args.reset_counter
        self._source_system = args.source_system
        self._use_fcu_roll_pitch = args.use_fcu_roll_pitch
        self._align_yaw_to_fcu = args.align_yaw_to_fcu
        self._odom_topic = args.odom_topic
        self._max_odom_age_ms = args.max_odom_age_ms
        self._max_local_position_age_ms = args.max_local_position_age_ms
        self._max_horizontal_speed_mps = args.max_horizontal_speed_mps
        self._max_yaw_rate_radps = args.max_yaw_rate_radps
        self._local_position_pose_topic = args.local_position_pose_topic
        self._connection = mavutil.mavlink_connection(
            self._endpoint,
            source_system=self._source_system,
            source_component=mavlink.MAV_COMP_ID_VISUAL_INERTIAL_ODOMETRY,
            dialect="ardupilotmega",
        )
        self._last_odom: Odometry | None = None
        self._last_odom_rx_monotonic = 0.0
        self._sent_count = 0
        self._last_heartbeat_monotonic = 0.0
        self._target_system: int | None = None
        self._target_component: int | None = None
        self._next_stream_request_monotonic = 0.0
        self._fcu_roll_rad: float | None = None
        self._fcu_pitch_rad: float | None = None
        self._fcu_yaw_rad: float = 0.0
        self._fcu_rollspeed_radps: float | None = None
        self._fcu_pitchspeed_radps: float | None = None
        self._last_fcu_attitude_monotonic = 0.0
        self._yaw_alignment_offset_rad: float | None = None
        self._local_position_count = 0
        self._last_local_position_monotonic = 0.0
        self._last_sent_x: float | None = None
        self._last_sent_y: float | None = None
        self._last_limited_odom_x: float | None = None
        self._last_limited_odom_y: float | None = None
        self._last_sent_xy_monotonic = 0.0
        self._last_sent_yaw_rad: float | None = None
        self._last_sent_yaw_monotonic = 0.0

        self.create_subscription(Odometry, args.odom_topic, self._handle_odom, 10)
        self._status_pub = self.create_publisher(String, args.status_topic, 10)
        self._local_position_pose_pub = (
            self.create_publisher(PoseStamped, args.local_position_pose_topic, 10)
            if args.local_position_pose_topic
            else None
        )
        self.create_timer(1.0 / self._rate_hz, self._send_tick)
        self.create_timer(0.5, self._publish_status)

        self.get_logger().info(
            "mavlink_external_nav_sender started "
            f"endpoint={self._endpoint} odom_topic={args.odom_topic} rate={self._rate_hz:.3f}Hz "
            f"quality={self._quality} reset_counter={self._reset_counter} "
            f"use_fcu_roll_pitch={self._use_fcu_roll_pitch} "
            f"align_yaw_to_fcu={self._align_yaw_to_fcu} "
            f"local_position_pose_topic={args.local_position_pose_topic or '<disabled>'}"
        )

    def _handle_odom(self, msg: Odometry) -> None:
        self._last_odom = msg
        self._last_odom_rx_monotonic = time.monotonic()

    def _send_tick(self) -> None:
        now_monotonic = time.monotonic()
        self._drain_mavlink(now_monotonic)
        self._request_fcu_attitude_if_needed(now_monotonic)
        if now_monotonic - self._last_heartbeat_monotonic >= 1.0:
            self._connection.mav.heartbeat_send(
                mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                mavlink.MAV_AUTOPILOT_INVALID,
                0,
                0,
                mavlink.MAV_STATE_ACTIVE,
            )
            self._last_heartbeat_monotonic = now_monotonic

        if self._last_odom is None:
            return

        odom = self._last_odom
        pose = odom.pose.pose
        twist = odom.twist.twist
        time_usec = int(time.monotonic() * 1000000)
        xy_dt_sec = now_monotonic - self._last_sent_xy_monotonic if self._last_sent_xy_monotonic > 0.0 else 0.0
        odom_x_m, odom_y_m = rate_limit_xy(
            target_x=float(pose.position.x),
            target_y=float(pose.position.y),
            last_x=self._last_limited_odom_x,
            last_y=self._last_limited_odom_y,
            dt_sec=xy_dt_sec,
            max_speed_mps=self._max_horizontal_speed_mps,
        )
        self._last_limited_odom_x = odom_x_m
        self._last_limited_odom_y = odom_y_m
        x_m, y_m, z_m = ros_enu_position_to_mavlink_local_frd(
            x_enu_m=odom_x_m,
            y_enu_m=odom_y_m,
            z_enu_m=float(pose.position.z),
        )
        self._last_sent_x = x_m
        self._last_sent_y = y_m
        self._last_sent_xy_monotonic = now_monotonic

        q = self._odometry_quaternion(pose, now_monotonic=now_monotonic)
        rollspeed_radps, pitchspeed_radps = self._roll_pitch_speeds(twist, now_monotonic=now_monotonic)
        yawspeed_radps = self._limit_yawspeed(float(twist.angular.z))

        self._connection.mav.odometry_send(
            int(time_usec),
            mavlink.MAV_FRAME_LOCAL_FRD,
            mavlink.MAV_FRAME_BODY_FRD,
            x_m,
            y_m,
            z_m,
            q,
            float(twist.linear.x),
            -float(twist.linear.y),
            -float(twist.linear.z),
            rollspeed_radps,
            pitchspeed_radps,
            -yawspeed_radps,
            _upper_triangular_covariance(odom.pose.covariance),
            _upper_triangular_covariance(odom.twist.covariance),
            int(self._reset_counter),
            mavlink.MAV_ESTIMATOR_TYPE_VIO,
            int(self._quality),
        )
        self._sent_count += 1

    def _drain_mavlink(self, now_monotonic: float) -> None:
        while True:
            msg = self._connection.recv_match(blocking=False)
            if msg is None:
                return
            msg_type = msg.get_type()
            if msg_type == "HEARTBEAT" and int(msg.autopilot) != mavlink.MAV_AUTOPILOT_INVALID:
                self._target_system = msg.get_srcSystem()
                self._target_component = msg.get_srcComponent()
            elif msg_type == "ATTITUDE":
                self._fcu_roll_rad = float(msg.roll)
                self._fcu_pitch_rad = float(msg.pitch)
                self._fcu_yaw_rad = float(msg.yaw)
                self._fcu_rollspeed_radps = float(msg.rollspeed)
                self._fcu_pitchspeed_radps = float(msg.pitchspeed)
                self._last_fcu_attitude_monotonic = now_monotonic
            elif msg_type == "LOCAL_POSITION_NED":
                self._local_position_count += 1
                self._last_local_position_monotonic = now_monotonic
                self._publish_local_position_pose(msg)

    def _request_fcu_attitude_if_needed(self, now_monotonic: float) -> None:
        if not self._use_fcu_roll_pitch and not self._local_position_pose_pub:
            return
        if self._target_system is None or self._target_component is None:
            return
        if now_monotonic < self._next_stream_request_monotonic:
            return
        for message_id, hz in (
            (mavlink.MAVLINK_MSG_ID_HEARTBEAT, 2.0),
            (mavlink.MAVLINK_MSG_ID_ATTITUDE, 20.0),
            (mavlink.MAVLINK_MSG_ID_LOCAL_POSITION_NED, 20.0),
        ):
            _send_message_interval(self._connection, self._target_system, self._target_component, message_id, hz)
        self._next_stream_request_monotonic = now_monotonic + 2.0

    def _publish_local_position_pose(self, msg: object) -> None:
        if self._local_position_pose_pub is None:
            return
        pose = ned_to_gazebo_pose(
            NedPoseSample(
                x_north_m=float(msg.x),
                y_east_m=float(msg.y),
                z_down_m=float(msg.z),
                yaw_rad=self._fcu_yaw_rad,
            ),
            min_z_m=0.0,
        )
        fields = build_pose_stamped_fields(pose)
        message = PoseStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "map"
        message.pose.position.x = fields["x"]
        message.pose.position.y = fields["y"]
        message.pose.position.z = fields["z"]
        message.pose.orientation.x = fields["qx"]
        message.pose.orientation.y = fields["qy"]
        message.pose.orientation.z = fields["qz"]
        message.pose.orientation.w = fields["qw"]
        self._local_position_pose_pub.publish(message)

    def _odometry_quaternion(self, pose: object, *, now_monotonic: float | None = None) -> list[float]:
        if now_monotonic is None:
            now_monotonic = time.monotonic()
        if self._use_fcu_roll_pitch and self._fcu_roll_rad is not None and self._fcu_pitch_rad is not None:
            if self._fcu_attitude_fresh(now_monotonic):
                yaw_ned_rad = ros_enu_yaw_to_mavlink_local_frd(_yaw_from_ros_quat_enu(pose.orientation))
                if self._align_yaw_to_fcu:
                    if self._yaw_alignment_offset_rad is None:
                        self._yaw_alignment_offset_rad = self._fcu_yaw_rad - yaw_ned_rad
                    yaw_ned_rad += self._yaw_alignment_offset_rad
                yaw_ned_rad = self._limit_yaw(yaw_ned_rad, now_monotonic=now_monotonic)
                return _quat_from_roll_pitch_yaw_frd(
                    roll_rad=0.0,
                    pitch_rad=0.0,
                    yaw_rad=yaw_ned_rad,
                )
        return _ros_quat_to_frd(pose.orientation)

    def _fcu_attitude_fresh(self, now_monotonic: float) -> bool:
        return now_monotonic - self._last_fcu_attitude_monotonic <= 1.0

    def _roll_pitch_speeds(self, twist: object, *, now_monotonic: float) -> tuple[float, float]:
        if (
            self._use_fcu_roll_pitch
            and self._fcu_rollspeed_radps is not None
            and self._fcu_pitchspeed_radps is not None
            and self._fcu_attitude_fresh(now_monotonic)
        ):
            return 0.0, 0.0
        return float(twist.angular.x), -float(twist.angular.y)

    def _limit_yaw(self, target_yaw_rad: float, *, now_monotonic: float) -> float:
        yaw_dt_sec = now_monotonic - self._last_sent_yaw_monotonic if self._last_sent_yaw_monotonic > 0.0 else 0.0
        yaw_rad = rate_limit_yaw(
            target_yaw_rad=target_yaw_rad,
            last_yaw_rad=self._last_sent_yaw_rad,
            dt_sec=yaw_dt_sec,
            max_yaw_rate_radps=self._max_yaw_rate_radps,
        )
        self._last_sent_yaw_rad = yaw_rad
        self._last_sent_yaw_monotonic = now_monotonic
        return yaw_rad

    def _limit_yawspeed(self, target_yawspeed_radps: float) -> float:
        if self._max_yaw_rate_radps <= 0.0:
            return target_yawspeed_radps
        return max(-self._max_yaw_rate_radps, min(self._max_yaw_rate_radps, target_yawspeed_radps))

    def _publish_status(self) -> None:
        age_ms = -1.0
        if self._last_odom is not None:
            age_ms = (time.monotonic() - self._last_odom_rx_monotonic) * 1000.0
        attitude_age_ms = -1.0
        if self._last_fcu_attitude_monotonic > 0.0:
            attitude_age_ms = (time.monotonic() - self._last_fcu_attitude_monotonic) * 1000.0
        local_position_age_ms = -1.0
        if self._last_local_position_monotonic > 0.0:
            local_position_age_ms = (time.monotonic() - self._last_local_position_monotonic) * 1000.0

        odom_fresh = self._last_odom is not None and 0.0 <= age_ms <= self._max_odom_age_ms
        local_position_fresh = (
            self._local_position_count > 0 and 0.0 <= local_position_age_ms <= self._max_local_position_age_ms
        )
        state = "sending" if self._last_odom is not None else "waiting_for_external_nav_odom"
        ready = state == "sending" and self._sent_count > 0 and odom_fresh and local_position_fresh

        status = {
            "state": state,
            "ready": ready,
            "endpoint": self._endpoint,
            "input_topic": self._odom_topic,
            "sent_count": self._sent_count,
            "rate_hz": self._rate_hz,
            "odom_age_ms": round(age_ms, 3),
            "max_odom_age_ms": self._max_odom_age_ms,
            "max_horizontal_speed_mps": self._max_horizontal_speed_mps,
            "max_yaw_rate_radps": self._max_yaw_rate_radps,
            "last_sent_x": self._last_sent_x,
            "last_sent_y": self._last_sent_y,
            "last_sent_yaw_rad": self._last_sent_yaw_rad,
            "odom_fresh": odom_fresh,
            "frame_id": self._last_odom.header.frame_id if self._last_odom else "",
            "child_frame_id": self._last_odom.child_frame_id if self._last_odom else "",
            "mav_frame_id": MAVLINK_POSITION_FRAME,
            "mav_child_frame_id": MAVLINK_VELOCITY_FRAME,
            "quality": self._quality,
            "reset_counter": self._reset_counter,
            "estimator_type": MAVLINK_ESTIMATOR_TYPE,
            "time_usec_source": MAVLINK_TIME_SOURCE,
            "use_fcu_roll_pitch": self._use_fcu_roll_pitch,
            "align_yaw_to_fcu": self._align_yaw_to_fcu,
            "yaw_alignment_offset_rad": self._yaw_alignment_offset_rad,
            "fcu_attitude_age_ms": round(attitude_age_ms, 3),
            "local_position_pose_topic": self._local_position_pose_topic,
            "local_position_count": self._local_position_count,
            "local_position_age_ms": round(local_position_age_ms, 3),
            "max_local_position_age_ms": self._max_local_position_age_ms,
            "fcu_local_position_ready": local_position_fresh,
            "mapping": _odometry_mapping_status(
                input_topic=self._odom_topic,
                quality=self._quality,
                reset_counter=self._reset_counter,
                rate_hz=self._rate_hz,
                source_system=self._source_system,
                use_fcu_roll_pitch=self._use_fcu_roll_pitch,
                align_yaw_to_fcu=self._align_yaw_to_fcu,
            ),
        }
        msg = String()
        msg.data = json.dumps(status, separators=(",", ":"))
        self._status_pub.publish(msg)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send ROS ExternalNav odom as MAVLink ODOMETRY.")
    parser.add_argument("--endpoint", default="udpout:mavlink-router:14550")
    parser.add_argument("--odom-topic", default="/external_nav/odom")
    parser.add_argument("--status-topic", default="/mavlink_external_nav/status")
    parser.add_argument("--rate-hz", type=float, default=20.0)
    parser.add_argument("--quality", type=int, default=100)
    parser.add_argument("--reset-counter", type=int, default=0)
    parser.add_argument("--source-system", type=int, default=191)
    parser.add_argument("--use-fcu-roll-pitch", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--align-yaw-to-fcu", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--local-position-pose-topic", default="")
    parser.add_argument("--max-odom-age-ms", type=float, default=1000.0)
    parser.add_argument("--max-local-position-age-ms", type=float, default=1000.0)
    parser.add_argument("--max-horizontal-speed-mps", type=float, default=0.0)
    parser.add_argument("--max-yaw-rate-radps", type=float, default=0.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if rclpy is None or mavutil is None or mavlink is None:
        raise SystemExit(
            "mavlink_external_nav_sender requires ROS2 Python packages and pymavlink. "
            "Run it with the ROS Python environment."
        )
    rclpy.init(args=None)
    node = MavlinkExternalNavSender(args)
    try:
        rclpy.spin(node)
    except (ExternalShutdownException, KeyboardInterrupt):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
