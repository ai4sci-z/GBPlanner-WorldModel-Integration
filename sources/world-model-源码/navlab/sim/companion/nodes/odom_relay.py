from __future__ import annotations

import argparse
from collections.abc import Sequence


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Relay nav_msgs/Odometry between two ROS topics.")
    parser.add_argument("--input-topic", default="/gazebo/truth/odom")
    parser.add_argument("--output-topic", default="/external_nav/odom")
    parser.add_argument("--qos-depth", type=int, default=10)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        import rclpy
        from nav_msgs.msg import Odometry
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
    except ModuleNotFoundError as exc:
        raise SystemExit("odom_relay requires ROS2 Python packages.") from exc

    class OdomRelay(Node):
        def __init__(self) -> None:
            super().__init__("navlab_odom_relay")
            self._publisher = self.create_publisher(Odometry, args.output_topic, args.qos_depth)
            self.create_subscription(Odometry, args.input_topic, self._handle_odom, args.qos_depth)
            self.get_logger().info(f"relaying odometry {args.input_topic} -> {args.output_topic}")

        def _handle_odom(self, msg: Odometry) -> None:
            self._publisher.publish(msg)

    rclpy.init()
    node = OdomRelay()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
