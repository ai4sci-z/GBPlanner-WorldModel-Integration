from __future__ import annotations

import argparse
from math import nan

from navlab.common.perception.contract import DEFAULT_SCAN_CONTRACT
from navlab.common.perception.scan_features import compute_scan_features

DEFAULT_SCAN_FEATURES_TOPIC = "/scan_features"
DEFAULT_NEAREST_POINT_TOPIC = "/scan_nearest_point"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish X3-compatible scan feature summaries from /scan.")
    parser.add_argument(
        "--scan-topic",
        default=DEFAULT_SCAN_CONTRACT.topic_name,
        help="LaserScan input topic.",
    )
    parser.add_argument(
        "--features-topic",
        default=DEFAULT_SCAN_FEATURES_TOPIC,
        help="ScanFeatures output topic.",
    )
    parser.add_argument(
        "--nearest-point-topic",
        default=DEFAULT_NEAREST_POINT_TOPIC,
        help="Nearest PointStamped output topic.",
    )
    parser.add_argument(
        "--front-center-deg",
        type=float,
        default=0.0,
        help="Front sector center in LaserScan degrees.",
    )
    parser.add_argument(
        "--left-center-deg",
        type=float,
        default=90.0,
        help="Left sector center in LaserScan degrees.",
    )
    parser.add_argument(
        "--right-center-deg",
        type=float,
        default=-90.0,
        help="Right sector center in LaserScan degrees.",
    )
    parser.add_argument(
        "--rear-center-deg",
        type=float,
        default=180.0,
        help="Rear sector center in LaserScan degrees.",
    )
    parser.add_argument(
        "--front-half-width-deg",
        type=float,
        default=15.0,
        help="Half width of the front sector in degrees.",
    )
    parser.add_argument(
        "--side-half-width-deg",
        type=float,
        default=20.0,
        help="Half width of the left and right sectors in degrees.",
    )
    parser.add_argument(
        "--rear-half-width-deg",
        type=float,
        default=20.0,
        help="Half width of the rear sector in degrees.",
    )
    return parser


def _finite_or_nan(value: float | None) -> float:
    return nan if value is None else value


def run(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        import rclpy
        from geometry_msgs.msg import PointStamped
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import LaserScan
        from ydlidar_interfaces.msg import ScanFeatures
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "scan_features_publisher requires ROS2 Python packages and ydlidar_interfaces. "
            "Run it through the NavLab companion runtime or source the overlay first."
        ) from exc

    class ScanFeaturesPublisher(Node):
        def __init__(self) -> None:
            super().__init__("ydlidar_ros2_scan_features")
            self._features_publisher = self.create_publisher(
                ScanFeatures,
                args.features_topic,
                qos_profile_sensor_data,
            )
            self._nearest_point_publisher = self.create_publisher(
                PointStamped,
                args.nearest_point_topic,
                qos_profile_sensor_data,
            )
            self.create_subscription(
                LaserScan,
                args.scan_topic,
                self._handle_scan,
                qos_profile_sensor_data,
            )
            self.get_logger().info(
                f"subscribed to {args.scan_topic}, publishing {args.features_topic} and {args.nearest_point_topic}"
            )

        def _publish_report(self, *, header, report) -> None:
            features_message = ScanFeatures()
            features_message.header = header
            features_message.front_min = _finite_or_nan(report.front_min)
            features_message.left_min = _finite_or_nan(report.left_min)
            features_message.right_min = _finite_or_nan(report.right_min)
            features_message.rear_min = _finite_or_nan(report.rear_min)
            features_message.nearest_range = _finite_or_nan(report.nearest_range)
            features_message.nearest_angle_deg = report.nearest_angle_deg
            features_message.nearest_point.x = _finite_or_nan(report.nearest_x)
            features_message.nearest_point.y = _finite_or_nan(report.nearest_y)
            features_message.nearest_point.z = 0.0
            features_message.valid_count = report.valid_count
            features_message.total_count = report.total_count
            self._features_publisher.publish(features_message)

            if report.nearest_range is None:
                return

            nearest_point_message = PointStamped()
            nearest_point_message.header = header
            nearest_point_message.point.x = 0.0 if report.nearest_x is None else report.nearest_x
            nearest_point_message.point.y = 0.0 if report.nearest_y is None else report.nearest_y
            nearest_point_message.point.z = 0.0
            self._nearest_point_publisher.publish(nearest_point_message)

        def _handle_scan(self, message: LaserScan) -> None:
            report = compute_scan_features(
                list(message.ranges),
                contract=DEFAULT_SCAN_CONTRACT,
                angle_min=message.angle_min,
                angle_increment=message.angle_increment,
                range_min=message.range_min,
                range_max=message.range_max,
                front_center_deg=args.front_center_deg,
                left_center_deg=args.left_center_deg,
                right_center_deg=args.right_center_deg,
                rear_center_deg=args.rear_center_deg,
                front_half_width_deg=args.front_half_width_deg,
                side_half_width_deg=args.side_half_width_deg,
                rear_half_width_deg=args.rear_half_width_deg,
            )
            self._publish_report(header=message.header, report=report)

    rclpy.init(args=None)
    node = ScanFeaturesPublisher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
