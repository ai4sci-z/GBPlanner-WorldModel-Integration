from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass

from navlab.common.logging import configure_sim_logging, logger
from navlab.sim.gazebo_sensor.config import DownRangefinderRuntimeConfig


@dataclass(frozen=True, slots=True)
class RangefinderReading:
    distance_m: float
    stamp_monotonic: float


def select_down_range_m(ranges: Sequence[float], *, min_m: float, max_m: float) -> float | None:
    valid = [float(value) for value in ranges if min_m <= float(value) <= max_m and math.isfinite(float(value))]
    if not valid:
        return None
    return min(valid)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project Gazebo down rangefinder scans to NavLab ROS Range topics.")
    parser.add_argument("--log-file")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    configure_sim_logging(log_file=args.log_file)
    config = DownRangefinderRuntimeConfig.load()

    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
        from sensor_msgs.msg import LaserScan, Range
        from std_msgs.msg import String
    except ModuleNotFoundError as exc:
        raise SystemExit("down range projection runtime requires ROS2 packages.") from exc

    class DownRangeProjectionNode(Node):
        def __init__(self) -> None:
            super().__init__("down_rangefinder_projection")
            self._latest: RangefinderReading | None = None
            self._input_count = 0
            self._range_pub = self.create_publisher(Range, config.range_topic, 10)
            self._status_pub = self.create_publisher(String, config.status_topic, 10)
            self.create_subscription(LaserScan, config.scan_ideal_topic, self._handle_scan, 10)
            self.create_timer(0.5, self._publish_status)
            logger.info(
                "down range projection started scan_topic={} range_topic={}",
                config.scan_ideal_topic,
                config.range_topic,
            )

        def _handle_scan(self, msg: LaserScan) -> None:
            distance = select_down_range_m(msg.ranges, min_m=config.min_distance_m, max_m=config.max_distance_m)
            if distance is None:
                return
            self._input_count += 1
            now = time.monotonic()
            self._latest = RangefinderReading(distance_m=distance, stamp_monotonic=now)
            output = Range()
            output.header.stamp = self.get_clock().now().to_msg()
            output.header.frame_id = config.frame_id
            output.radiation_type = Range.INFRARED
            output.field_of_view = 0.0
            output.min_range = config.min_distance_m
            output.max_range = config.max_distance_m
            output.range = distance
            self._range_pub.publish(output)

        def _publish_status(self) -> None:
            now = time.monotonic()
            latest_age = None if self._latest is None else now - self._latest.stamp_monotonic
            ready = latest_age is not None and latest_age <= 1.0
            message = String()
            message.data = json.dumps(
                {
                    "state": "publishing" if ready else "waiting",
                    "ready": ready,
                    "source": "gazebo_down_range_projection",
                    "fcu_transport": "serial7_uart",
                    "fcu_rangefinder_source": "ardupilot_serial7_benewake_tfmini",
                    "rangefinder_simulation_fidelity": "benewake_serial_emulated",
                    "virtual_serial_link": str(config.virtual_serial_link),
                    "scan_ideal_topic": config.scan_ideal_topic,
                    "range_topic": config.range_topic,
                    "frame_id": config.frame_id,
                    "input_count": self._input_count,
                    "latest_distance_m": None if self._latest is None else self._latest.distance_m,
                    "latest_input_age_sec": latest_age,
                    "min_distance_m": config.min_distance_m,
                    "max_distance_m": config.max_distance_m,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
            self._status_pub.publish(message)

    rclpy.init(args=None)
    node = DownRangeProjectionNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
