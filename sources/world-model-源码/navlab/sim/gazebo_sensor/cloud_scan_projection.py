from __future__ import annotations

import math
import time
from collections.abc import Iterable
from dataclasses import dataclass

from navlab.common.logging import configure_sim_logging, logger
from navlab.sim.gazebo_sensor.config import X2SensorRuntimeConfig

DEFAULT_INPUT_TOPIC = "cloud_in"
DEFAULT_FRAME_ID = "base_scan"
DEFAULT_BEAM_COUNT = 640
DEFAULT_SCAN_FREQUENCY_HZ = 10.0


@dataclass(frozen=True, slots=True)
class PointXYZ:
    x: float
    y: float
    z: float = 0.0


def project_points_to_ranges(
    points: Iterable[PointXYZ],
    *,
    beam_count: int = DEFAULT_BEAM_COUNT,
    angle_min_rad: float = -math.pi,
    angle_max_rad: float = math.pi,
    range_min_m: float = 0.1,
    range_max_m: float = 8.0,
) -> tuple[float, ...]:
    if beam_count <= 1:
        raise ValueError("beam_count must be greater than 1")
    if not math.isfinite(angle_min_rad) or not math.isfinite(angle_max_rad) or angle_max_rad <= angle_min_rad:
        raise ValueError("angle range must be finite and increasing")
    if range_min_m <= 0 or range_max_m <= range_min_m:
        raise ValueError("range limits must be positive and increasing")

    angle_increment = (angle_max_rad - angle_min_rad) / float(beam_count - 1)
    ranges = [math.nan] * beam_count
    for point in points:
        x = float(point.x)
        y = float(point.y)
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        distance = math.hypot(x, y)
        if distance < range_min_m or distance > range_max_m:
            continue
        angle = math.atan2(y, x)
        index = int(round((angle - angle_min_rad) / angle_increment))
        if index < 0 or index >= beam_count:
            continue
        previous = ranges[index]
        if not math.isfinite(previous) or distance < previous:
            ranges[index] = distance
    return tuple(ranges)


def _finite_range_count(ranges: tuple[float, ...]) -> int:
    return sum(1 for value in ranges if math.isfinite(value))


def run() -> int:
    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
        from rclpy.parameter import Parameter
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import LaserScan, PointCloud2
        from sensor_msgs_py import point_cloud2
    except ModuleNotFoundError as exc:
        raise SystemExit("cloud scan projection requires ROS2 Python packages.") from exc

    config = X2SensorRuntimeConfig.load()
    beam_count = DEFAULT_BEAM_COUNT
    angle_min = -math.pi
    angle_max = math.pi
    angle_increment = (angle_max - angle_min) / float(beam_count - 1)
    scan_time = 1.0 / max(0.001, DEFAULT_SCAN_FREQUENCY_HZ)
    time_increment = scan_time / float(beam_count)

    class CloudScanProjectionNode(Node):
        def __init__(self) -> None:
            super().__init__("navlab_lidar_cloud_scan_projection")
            self.set_parameters([Parameter("use_sim_time", Parameter.Type.BOOL, True)])
            self._publisher = self.create_publisher(LaserScan, config.scan_ideal_topic, qos_profile_sensor_data)
            self._count = 0
            self._published_count = 0
            self._started_at = time.monotonic()
            self.create_subscription(PointCloud2, DEFAULT_INPUT_TOPIC, self._handle_cloud, qos_profile_sensor_data)
            self.create_timer(2.0, self._log_status)
            logger.info(
                "projecting Gazebo lidar point cloud input={} output={} beams={}",
                DEFAULT_INPUT_TOPIC,
                config.scan_ideal_topic,
                beam_count,
            )

        def _handle_cloud(self, message: PointCloud2) -> None:
            self._count += 1
            raw_points = point_cloud2.read_points(message, field_names=("x", "y", "z"), skip_nans=True)
            points = (PointXYZ(float(row[0]), float(row[1]), float(row[2])) for row in raw_points)
            ranges = project_points_to_ranges(
                points,
                beam_count=beam_count,
                angle_min_rad=angle_min,
                angle_max_rad=angle_max,
                range_min_m=config.range_min_m,
                range_max_m=config.range_max_m,
            )
            if _finite_range_count(ranges) == 0:
                return
            scan = LaserScan()
            scan.header = message.header
            if not scan.header.frame_id:
                scan.header.frame_id = DEFAULT_FRAME_ID
            scan.angle_min = angle_min
            scan.angle_max = angle_max
            scan.angle_increment = angle_increment
            scan.time_increment = time_increment
            scan.scan_time = scan_time
            scan.range_min = config.range_min_m
            scan.range_max = config.range_max_m
            scan.ranges = list(ranges)
            self._publisher.publish(scan)
            self._published_count += 1

        def _log_status(self) -> None:
            elapsed = max(0.001, time.monotonic() - self._started_at)
            logger.info(
                "cloud scan projection input_count={} published_count={} publish_rate_hz={:.2f}",
                self._count,
                self._published_count,
                self._published_count / elapsed,
            )

    configure_sim_logging()
    rclpy.init(args=None)
    node = CloudScanProjectionNode()
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
