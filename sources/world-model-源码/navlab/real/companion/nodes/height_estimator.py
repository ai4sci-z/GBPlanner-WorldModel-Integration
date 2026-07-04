from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Sequence

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from sensor_msgs.msg import Range
    from std_msgs.msg import String
except ModuleNotFoundError:
    rclpy = None
    ExternalShutdownException = KeyboardInterrupt
    Node = object
    Range = object
    String = object


class DownRangeHeightEstimator(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("down_range_height_estimator")
        self._range_topic = args.range_topic
        self._height_topic = args.height_topic
        self._status_topic = args.status_topic
        self._max_age_ms = args.max_age_ms
        self._covariance = args.covariance
        self._source_type = args.source_type
        self._max_vertical_speed_mps = args.max_vertical_speed_mps
        self._max_vertical_velocity_output_mps = args.max_vertical_velocity_output_mps
        self._velocity_smoothing_alpha = args.velocity_smoothing_alpha
        self._max_filter_dt_sec = args.max_filter_dt_sec
        self._ground_range_m: float | None = None
        self._last_height_m: float | None = None
        self._last_vz_mps: float | None = None
        self._last_rx_monotonic = 0.0
        self._last_publish_monotonic = 0.0
        self._input_count = 0
        self._output_count = 0
        self._height_pub = self.create_publisher(String, self._height_topic, 10)
        self._status_pub = self.create_publisher(String, self._status_topic, 10)
        self.create_subscription(Range, self._range_topic, self._handle_range, 10)
        self.create_timer(0.5, self._publish_status)
        self.get_logger().info(
            f"down range height estimator started range_topic={self._range_topic} height_topic={self._height_topic}"
        )

    def _handle_range(self, msg: Range) -> None:
        distance_m = float(msg.range)
        if not math.isfinite(distance_m):
            return
        if distance_m < float(msg.min_range) or distance_m > float(msg.max_range):
            return

        now = time.monotonic()
        if self._ground_range_m is None:
            self._ground_range_m = distance_m

        dt = now - self._last_publish_monotonic if self._last_publish_monotonic > 0.0 else 0.0
        z_m, vz_mps = estimate_relative_height(
            distance_m=distance_m,
            ground_range_m=self._ground_range_m,
            last_height_m=self._last_height_m,
            last_vz_mps=self._last_vz_mps,
            dt_sec=dt,
            max_vertical_speed_mps=self._max_vertical_speed_mps,
            max_vertical_velocity_output_mps=self._max_vertical_velocity_output_mps,
            velocity_smoothing_alpha=self._velocity_smoothing_alpha,
            max_filter_dt_sec=self._max_filter_dt_sec,
        )

        self._input_count += 1
        self._last_rx_monotonic = now
        self._last_publish_monotonic = now
        self._last_height_m = z_m
        self._last_vz_mps = vz_mps
        payload = {
            "z": z_m,
            "vz": vz_mps,
            "covariance": self._covariance,
            "source_type": self._source_type,
            "range_m": distance_m,
            "ground_range_m": self._ground_range_m,
        }
        message = String()
        message.data = json.dumps(payload, separators=(",", ":"))
        self._height_pub.publish(message)
        self._output_count += 1

    def _publish_status(self) -> None:
        age_ms = -1.0
        if self._last_rx_monotonic > 0.0:
            age_ms = (time.monotonic() - self._last_rx_monotonic) * 1000.0
        ready = self._output_count > 0 and 0.0 <= age_ms <= self._max_age_ms
        payload = {
            "state": "publishing" if ready else "waiting_for_range",
            "ready": ready,
            "range_topic": self._range_topic,
            "height_topic": self._height_topic,
            "input_count": self._input_count,
            "output_count": self._output_count,
            "age_ms": round(age_ms, 3),
            "max_age_ms": self._max_age_ms,
            "source_type": self._source_type,
            "ground_range_m": self._ground_range_m,
            "last_height_m": self._last_height_m,
            "last_vz_mps": self._last_vz_mps,
            "max_vertical_speed_mps": self._max_vertical_speed_mps,
            "max_vertical_velocity_output_mps": self._max_vertical_velocity_output_mps,
            "velocity_smoothing_alpha": self._velocity_smoothing_alpha,
            "max_filter_dt_sec": self._max_filter_dt_sec,
        }
        message = String()
        message.data = json.dumps(payload, separators=(",", ":"))
        self._status_pub.publish(message)


def estimate_relative_height(
    *,
    distance_m: float,
    ground_range_m: float,
    last_height_m: float | None,
    last_vz_mps: float | None,
    dt_sec: float,
    max_vertical_speed_mps: float,
    velocity_smoothing_alpha: float,
    max_vertical_velocity_output_mps: float | None = None,
    max_filter_dt_sec: float = 0.1,
) -> tuple[float, float]:
    raw_z_m = max(0.0, distance_m - ground_range_m)
    effective_dt_sec = dt_sec
    if max_filter_dt_sec > 0.0:
        effective_dt_sec = min(effective_dt_sec, max_filter_dt_sec)
    z_m = raw_z_m
    if effective_dt_sec > 0.0 and last_height_m is not None:
        max_delta_m = max(0.0, max_vertical_speed_mps) * effective_dt_sec
        z_m = clamp(raw_z_m, last_height_m - max_delta_m, last_height_m + max_delta_m)
        z_m = max(0.0, z_m)
    if effective_dt_sec > 0.0 and last_height_m is not None:
        raw_vz_mps = (z_m - last_height_m) / effective_dt_sec
    else:
        raw_vz_mps = 0.0
    max_vz_output_mps = max_vertical_speed_mps
    if max_vertical_velocity_output_mps is not None and max_vertical_velocity_output_mps > 0.0:
        max_vz_output_mps = max_vertical_velocity_output_mps
    vz_mps = clamp(raw_vz_mps, -max_vz_output_mps, max_vz_output_mps)
    if last_vz_mps is not None:
        alpha = clamp(velocity_smoothing_alpha, 0.0, 1.0)
        vz_mps = (alpha * vz_mps) + ((1.0 - alpha) * last_vz_mps)
    return z_m, clamp(vz_mps, -max_vz_output_mps, max_vz_output_mps)


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish relative height estimates from a down rangefinder.")
    parser.add_argument("--range-topic", default="/rangefinder/down/range")
    parser.add_argument("--height-topic", default="/height/estimate")
    parser.add_argument("--status-topic", default="/height/status")
    parser.add_argument("--max-age-ms", type=float, default=1000.0)
    parser.add_argument("--covariance", type=float, default=0.04)
    parser.add_argument("--source-type", default="rangefinder_down_relative")
    parser.add_argument("--max-vertical-speed-mps", type=float, default=0.7)
    parser.add_argument("--max-vertical-velocity-output-mps", type=float, default=0.0)
    parser.add_argument("--velocity-smoothing-alpha", type=float, default=0.35)
    parser.add_argument("--max-filter-dt-sec", type=float, default=0.1)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if rclpy is None:
        raise SystemExit("height_estimator requires ROS2 Python packages.")
    rclpy.init(args=None)
    node = DownRangeHeightEstimator(args)
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
