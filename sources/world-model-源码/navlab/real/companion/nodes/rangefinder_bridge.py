from __future__ import annotations

import argparse
import json
import math
import signal
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

for site_packages in (Path(__file__).resolve().parents[3] / ".venv" / "lib").glob("python*/site-packages"):
    sys.path.insert(0, str(site_packages))

from pymavlink import mavutil  # noqa: E402
from pymavlink.dialects.v20 import ardupilotmega as mavlink  # noqa: E402


@dataclass(slots=True)
class DistanceSensorSample:
    current_m: float
    min_m: float
    max_m: float
    orientation: int
    quality: int
    sensor_id: int
    stamp_monotonic: float
    count: int


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish real FCU DISTANCE_SENSOR as NavLab down rangefinder topics.")
    parser.add_argument("--mavlink-endpoint", default="tcp:127.0.0.1:5760")
    parser.add_argument("--range-topic", default="/rangefinder/down/range")
    parser.add_argument("--status-topic", default="/rangefinder/down/status")
    parser.add_argument("--frame-id", default="rangefinder_down_frame")
    parser.add_argument("--accepted-orientation", type=int, action="append", default=[25])
    parser.add_argument("--source-label", default="real_fcu_distance_sensor")
    parser.add_argument("--rate-hz", type=float, default=20.0)
    parser.add_argument("--timeout-sec", type=float, default=1.0)
    return parser.parse_args(argv)


def _request_distance_sensor_stream(connection: Any, target_system: int, target_component: int, hz: float) -> None:
    connection.mav.command_long_send(
        target_system,
        target_component,
        mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0,
        mavlink.MAVLINK_MSG_ID_DISTANCE_SENSOR,
        int(1_000_000.0 / max(hz, 0.1)),
        0,
        0,
        0,
        0,
        0,
    )


def _orientation_name(value: int) -> str:
    enum = getattr(mavlink, "enums", {}).get("MAV_SENSOR_ORIENTATION", {})
    item = enum.get(value)
    if item is None:
        return str(value)
    return str(getattr(item, "name", value))


def _sample_from_distance_sensor(msg: Any, *, count: int) -> DistanceSensorSample:
    return DistanceSensorSample(
        current_m=float(getattr(msg, "current_distance", 0)) / 100.0,
        min_m=float(getattr(msg, "min_distance", 0)) / 100.0,
        max_m=float(getattr(msg, "max_distance", 0)) / 100.0,
        orientation=int(getattr(msg, "orientation", -1)),
        quality=int(getattr(msg, "quality", -1)),
        sensor_id=int(getattr(msg, "id", 0)),
        stamp_monotonic=time.monotonic(),
        count=count,
    )


def _sample_valid(sample: DistanceSensorSample, accepted_orientations: set[int]) -> tuple[bool, str]:
    if sample.orientation not in accepted_orientations:
        return False, "rangefinder_down_orientation_invalid"
    if not math.isfinite(sample.current_m) or sample.current_m <= 0.0:
        return False, "rangefinder_down_distance_invalid"
    if sample.min_m > 0.0 and sample.current_m < sample.min_m:
        return False, "rangefinder_down_distance_invalid"
    if sample.max_m > 0.0 and sample.current_m > sample.max_m:
        return False, "rangefinder_down_distance_invalid"
    return True, ""


def run(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Range
        from std_msgs.msg import String
    except ModuleNotFoundError as exc:
        raise SystemExit("fcu_distance_sensor_bridge requires ROS2 Python packages and pymavlink.") from exc

    stop_requested = False

    def _stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    accepted_orientations = {int(value) for value in args.accepted_orientation}

    rclpy.init(args=None)

    class FcuDistanceSensorBridge(Node):
        def __init__(self) -> None:
            super().__init__("navlab_real_rangefinder_bridge")
            self._range_pub = self.create_publisher(Range, args.range_topic, qos_profile_sensor_data)
            self._status_pub = self.create_publisher(String, args.status_topic, 10)
            self._connection = mavutil.mavlink_connection(args.mavlink_endpoint, dialect="ardupilotmega")
            self._target_system: int | None = None
            self._target_component: int | None = None
            self._next_request = 0.0
            self._sample: DistanceSensorSample | None = None
            self._last_observed: DistanceSensorSample | None = None
            self._count = 0
            self._rejected_count = 0
            self._last_reject_reason = ""
            self.create_timer(1.0 / max(args.rate_hz, 0.1), self._tick)
            self.get_logger().info(
                f"real rangefinder bridge endpoint={args.mavlink_endpoint} "
                f"range_topic={args.range_topic} status_topic={args.status_topic} "
                f"accepted_orientation={sorted(accepted_orientations)}"
            )

        def _tick(self) -> None:
            self._drain_mavlink()
            now = time.monotonic()
            if self._target_system is not None and self._target_component is not None and now >= self._next_request:
                _request_distance_sensor_stream(
                    self._connection, self._target_system, self._target_component, args.rate_hz
                )
                self._next_request = now + 2.0
            self._publish_status()

        def _drain_mavlink(self) -> None:
            while True:
                msg = self._connection.recv_match(blocking=False)
                if msg is None:
                    return
                msg_type = msg.get_type()
                if msg_type == "HEARTBEAT" and int(getattr(msg, "autopilot", 0)) != mavlink.MAV_AUTOPILOT_INVALID:
                    self._target_system = msg.get_srcSystem()
                    self._target_component = msg.get_srcComponent()
                elif msg_type == "DISTANCE_SENSOR":
                    self._count += 1
                    sample = _sample_from_distance_sensor(msg, count=self._count)
                    self._last_observed = sample
                    valid, reason = _sample_valid(sample, accepted_orientations)
                    if not valid:
                        self._rejected_count += 1
                        self._last_reject_reason = reason
                        continue
                    self._sample = sample
                    self._last_reject_reason = ""
                    self._publish_range(sample)

        def _publish_range(self, sample: DistanceSensorSample) -> None:
            message = Range()
            message.header.stamp = self.get_clock().now().to_msg()
            message.header.frame_id = args.frame_id
            message.radiation_type = Range.INFRARED
            message.field_of_view = 0.05
            message.min_range = sample.min_m
            message.max_range = sample.max_m
            message.range = sample.current_m
            self._range_pub.publish(message)

        def _publish_status(self) -> None:
            sample = self._sample
            observed = self._last_observed
            now = time.monotonic()
            age_ms = -1.0 if sample is None else (now - sample.stamp_monotonic) * 1000.0
            observed_age_ms = -1.0 if observed is None else (now - observed.stamp_monotonic) * 1000.0
            fresh = sample is not None and age_ms <= args.timeout_sec * 1000.0
            ready = bool(sample is not None and fresh)
            status = {
                "state": "ready" if ready else (self._last_reject_reason or "rangefinder_down_no_data"),
                "ready": ready,
                "source": args.source_label,
                "source_claim": args.source_label,
                "message": "DISTANCE_SENSOR",
                "range_topic": args.range_topic,
                "status_topic": args.status_topic,
                "frame_id": args.frame_id,
                "current_distance_m": None if observed is None else round(observed.current_m, 4),
                "min_distance_m": None if observed is None else round(observed.min_m, 4),
                "max_distance_m": None if observed is None else round(observed.max_m, 4),
                "orientation": None if observed is None else observed.orientation,
                "orientation_name": "" if observed is None else _orientation_name(observed.orientation),
                "quality": None if observed is None else observed.quality,
                "sensor_id": None if observed is None else observed.sensor_id,
                "count": self._count,
                "accepted_count": 0 if sample is None else sample.count,
                "rejected_count": self._rejected_count,
                "age_ms": round(age_ms, 3),
                "observed_age_ms": round(observed_age_ms, 3),
                "observed_fresh": observed is not None and observed_age_ms <= args.timeout_sec * 1000.0,
                "fresh": fresh,
                "blocker": "" if ready else (self._last_reject_reason or "rangefinder_down_no_data"),
            }
            message = String()
            message.data = json.dumps(status, separators=(",", ":"), sort_keys=True)
            self._status_pub.publish(message)

    node = FcuDistanceSensorBridge()
    try:
        while rclpy.ok() and not stop_requested:
            try:
                rclpy.spin_once(node, timeout_sec=0.2)
            except rclpy.executors.ExternalShutdownException:
                break
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
