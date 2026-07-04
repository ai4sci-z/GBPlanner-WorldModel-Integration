from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass

os.environ.setdefault("MAVLINK20", "1")

GRAVITY_MPS2 = 9.80665


@dataclass(frozen=True, slots=True)
class MavlinkImuSample:
    source_message: str
    linear_acceleration_x: float
    linear_acceleration_y: float
    linear_acceleration_z: float
    angular_velocity_x: float
    angular_velocity_y: float
    angular_velocity_z: float
    raw_units: bool = False


@dataclass(frozen=True, slots=True)
class ImuBridgeStatus:
    state: str
    ready: bool
    source_label: str
    source_message: str | None
    input_present: bool
    input_fresh: bool
    input_age_ms: float
    input_rate_hz: float
    input_rate_ok: bool
    min_rate_hz: float
    output_topic: str
    output_frame_id: str
    count: int
    raw_fallback_count: int


def sample_from_highres_imu(msg: object) -> MavlinkImuSample:
    return MavlinkImuSample(
        source_message="HIGHRES_IMU",
        linear_acceleration_x=float(getattr(msg, "xacc")),
        linear_acceleration_y=float(getattr(msg, "yacc")),
        linear_acceleration_z=float(getattr(msg, "zacc")),
        angular_velocity_x=float(getattr(msg, "xgyro")),
        angular_velocity_y=float(getattr(msg, "ygyro")),
        angular_velocity_z=float(getattr(msg, "zgyro")),
    )


def sample_from_scaled_imu(msg: object) -> MavlinkImuSample:
    return MavlinkImuSample(
        source_message="SCALED_IMU",
        linear_acceleration_x=float(getattr(msg, "xacc")) * GRAVITY_MPS2 / 1000.0,
        linear_acceleration_y=float(getattr(msg, "yacc")) * GRAVITY_MPS2 / 1000.0,
        linear_acceleration_z=float(getattr(msg, "zacc")) * GRAVITY_MPS2 / 1000.0,
        angular_velocity_x=float(getattr(msg, "xgyro")) / 1000.0,
        angular_velocity_y=float(getattr(msg, "ygyro")) / 1000.0,
        angular_velocity_z=float(getattr(msg, "zgyro")) / 1000.0,
    )


def sample_from_raw_imu(msg: object) -> MavlinkImuSample:
    return MavlinkImuSample(
        source_message="RAW_IMU",
        linear_acceleration_x=float(getattr(msg, "xacc")),
        linear_acceleration_y=float(getattr(msg, "yacc")),
        linear_acceleration_z=float(getattr(msg, "zacc")),
        angular_velocity_x=float(getattr(msg, "xgyro")),
        angular_velocity_y=float(getattr(msg, "ygyro")),
        angular_velocity_z=float(getattr(msg, "zgyro")),
        raw_units=True,
    )


def state_for_imu_status(*, present: bool, fresh: bool, rate_ok: bool) -> str:
    if not present:
        return "waiting_for_fcu_imu_source"
    if not fresh:
        return "stale_fcu_imu_source"
    if not rate_ok:
        return "low_rate_fcu_imu_source"
    return "streaming_fcu_imu"


def encode_imu_status(status: ImuBridgeStatus) -> str:
    return json.dumps(
        {
            "state": status.state,
            "ready": status.ready,
            "source": {
                "mode": "mavlink",
                "label": status.source_label,
                "message": status.source_message or "",
            },
            "input": {
                "present": status.input_present,
                "fresh": status.input_fresh,
                "age_ms": round(status.input_age_ms, 3),
                "rate_hz": round(status.input_rate_hz, 3),
                "rate_ok": status.input_rate_ok,
                "min_rate_hz": status.min_rate_hz,
                "count": status.count,
                "raw_fallback_count": status.raw_fallback_count,
            },
            "output": {
                "topic": status.output_topic,
                "frame_id": status.output_frame_id,
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge FCU MAVLink IMU messages into ROS /imu/data.")
    parser.add_argument("--endpoint", default="tcp:sitl:5764")
    parser.add_argument("--imu-topic", default="/imu/data")
    parser.add_argument("--status-topic", default="/imu/status")
    parser.add_argument("--frame-id", default="fcu_imu")
    parser.add_argument("--source-label", default="fcu_mavlink")
    parser.add_argument("--rate-hz", type=float, default=50.0)
    parser.add_argument("--stream-rate-hz", type=float, default=50.0)
    parser.add_argument("--timeout-sec", type=float, default=0.5)
    parser.add_argument("--min-rate-hz", type=float, default=4.0)
    parser.add_argument("--allow-raw-imu", action=argparse.BooleanOptionalAction, default=False)
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


def _request_imu_streams(
    connection,
    target_system: int,
    target_component: int,
    hz: float,
    *,
    include_raw: bool,
) -> None:
    from pymavlink.dialects.v20 import ardupilotmega as mavlink

    message_ids = [
        mavlink.MAVLINK_MSG_ID_HIGHRES_IMU,
        mavlink.MAVLINK_MSG_ID_SCALED_IMU,
    ]
    if include_raw:
        message_ids.append(mavlink.MAVLINK_MSG_ID_RAW_IMU)
    for message_id in message_ids:
        _send_message_interval(connection, target_system, target_component, message_id, hz)


def run(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        import rclpy
        from pymavlink import mavutil
        from pymavlink.dialects.v20 import ardupilotmega as mavlink
        from rclpy.node import Node
        from sensor_msgs.msg import Imu
        from std_msgs.msg import String
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "mavlink_imu_bridge requires ROS2 Python packages and pymavlink. Run it from the NavLab companion image."
        ) from exc

    class MavlinkImuBridge(Node):
        def __init__(self) -> None:
            super().__init__("mavlink_imu_bridge")
            self._connection = mavutil.mavlink_connection(args.endpoint, dialect="ardupilotmega")
            self._imu_pub = self.create_publisher(Imu, args.imu_topic, 10)
            self._status_pub = self.create_publisher(String, args.status_topic, 10)
            self._target_system: int | None = None
            self._target_component: int | None = None
            self._last_sample: MavlinkImuSample | None = None
            self._last_sample_monotonic = 0.0
            self._last_status_monotonic = 0.0
            self._input_rate_hz = 0.0
            self._count = 0
            self._raw_fallback_count = 0
            self._next_stream_request = 0.0
            self.create_timer(1.0 / args.rate_hz, self._tick)
            self.get_logger().info(f"mavlink_imu_bridge started endpoint={args.endpoint}")

        def _tick(self) -> None:
            self._drain_mavlink()
            now = time.monotonic()
            if (
                self._target_system is not None
                and self._target_component is not None
                and now >= self._next_stream_request
            ):
                _request_imu_streams(
                    self._connection,
                    self._target_system,
                    self._target_component,
                    args.stream_rate_hz,
                    include_raw=args.allow_raw_imu,
                )
                self._next_stream_request = now + 2.0
            self._publish_status()

        def _drain_mavlink(self) -> None:
            while True:
                msg = self._connection.recv_match(blocking=False)
                if msg is None:
                    return
                msg_type = msg.get_type()
                if msg_type == "HEARTBEAT" and int(msg.autopilot) != mavlink.MAV_AUTOPILOT_INVALID:
                    self._target_system = msg.get_srcSystem()
                    self._target_component = msg.get_srcComponent()
                elif msg_type == "HIGHRES_IMU":
                    self._handle_sample(sample_from_highres_imu(msg))
                elif msg_type == "SCALED_IMU":
                    self._handle_sample(sample_from_scaled_imu(msg))
                elif msg_type == "RAW_IMU" and args.allow_raw_imu:
                    self._raw_fallback_count += 1
                    self._handle_sample(sample_from_raw_imu(msg))

        def _handle_sample(self, sample: MavlinkImuSample) -> None:
            now = time.monotonic()
            if self._last_sample is not None:
                delta = now - self._last_sample_monotonic
                if delta > 0.0:
                    current_rate = 1.0 / delta
                    self._input_rate_hz = (
                        current_rate if self._input_rate_hz <= 0.0 else (0.8 * self._input_rate_hz + 0.2 * current_rate)
                    )
            self._last_sample = sample
            self._last_sample_monotonic = now
            self._count += 1
            self._publish_imu(sample)

        def _publish_imu(self, sample: MavlinkImuSample) -> None:
            imu = Imu()
            imu.header.stamp = self.get_clock().now().to_msg()
            imu.header.frame_id = args.frame_id
            imu.orientation.w = 1.0
            imu.orientation_covariance[0] = -1.0
            imu.angular_velocity.x = sample.angular_velocity_x
            imu.angular_velocity.y = sample.angular_velocity_y
            imu.angular_velocity.z = sample.angular_velocity_z
            imu.linear_acceleration.x = sample.linear_acceleration_x
            imu.linear_acceleration.y = sample.linear_acceleration_y
            imu.linear_acceleration.z = sample.linear_acceleration_z
            self._imu_pub.publish(imu)

        def _publish_status(self) -> None:
            now = time.monotonic()
            if now - self._last_status_monotonic < 0.5:
                return
            self._last_status_monotonic = now
            present = self._last_sample is not None
            age_sec = now - self._last_sample_monotonic if present else math.inf
            fresh = present and age_sec <= args.timeout_sec
            rate_ok = self._input_rate_hz >= args.min_rate_hz
            state = state_for_imu_status(present=present, fresh=fresh, rate_ok=rate_ok)
            status = ImuBridgeStatus(
                state=state,
                ready=present and fresh and rate_ok,
                source_label=args.source_label,
                source_message=None if self._last_sample is None else self._last_sample.source_message,
                input_present=present,
                input_fresh=fresh,
                input_age_ms=-1.0 if math.isinf(age_sec) else age_sec * 1000.0,
                input_rate_hz=self._input_rate_hz,
                input_rate_ok=rate_ok,
                min_rate_hz=args.min_rate_hz,
                output_topic=args.imu_topic,
                output_frame_id=args.frame_id,
                count=self._count,
                raw_fallback_count=self._raw_fallback_count,
            )
            msg = String()
            msg.data = encode_imu_status(status)
            self._status_pub.publish(msg)

    rclpy.init(args=None)
    node = MavlinkImuBridge()
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
