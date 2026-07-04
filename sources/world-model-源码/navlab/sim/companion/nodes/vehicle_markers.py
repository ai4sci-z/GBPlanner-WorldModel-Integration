from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import atan2, cos, sin

DEFAULT_TOPIC = "/navlab/vehicle/markers"
DEFAULT_POSE_TOPIC = "/ap/v1/pose/filtered"
DEFAULT_FRAME_ID = "map"
DEFAULT_RATE_HZ = 10.0


@dataclass(frozen=True, slots=True)
class VehicleMarkerPart:
    marker_id: int
    namespace: str
    shape: str
    dx: float
    dy: float
    dz: float
    yaw: float
    scale_x: float
    scale_y: float
    scale_z: float
    color_r: float
    color_g: float
    color_b: float
    color_a: float


def vehicle_marker_parts() -> tuple[VehicleMarkerPart, ...]:
    rotor_offsets = (
        (0.24, 0.24),
        (0.24, -0.24),
        (-0.24, 0.24),
        (-0.24, -0.24),
    )
    parts = [
        VehicleMarkerPart(
            0, "navlab_vehicle_body", "sphere", 0.0, 0.0, 0.0, 0.0, 0.34, 0.22, 0.12, 0.08, 0.15, 0.22, 1.0
        ),
        VehicleMarkerPart(
            1, "navlab_vehicle_nose", "arrow", 0.18, 0.0, 0.0, 0.0, 0.24, 0.055, 0.055, 1.0, 0.78, 0.16, 1.0
        ),
        VehicleMarkerPart(
            2,
            "navlab_vehicle_arm_a",
            "cube",
            0.0,
            0.0,
            0.005,
            0.7853981633974483,
            0.68,
            0.035,
            0.035,
            0.12,
            0.20,
            0.28,
            1.0,
        ),
        VehicleMarkerPart(
            3,
            "navlab_vehicle_arm_b",
            "cube",
            0.0,
            0.0,
            0.005,
            -0.7853981633974483,
            0.68,
            0.035,
            0.035,
            0.12,
            0.20,
            0.28,
            1.0,
        ),
        VehicleMarkerPart(
            4, "navlab_vehicle_x2_lidar", "cylinder", 0.10, 0.0, -0.09, 0.0, 0.08, 0.08, 0.055, 0.08, 0.65, 1.0, 1.0
        ),
    ]
    for index, (dx, dy) in enumerate(rotor_offsets):
        parts.append(
            VehicleMarkerPart(
                marker_id=10 + index,
                namespace=f"navlab_vehicle_rotor_{index}_disc",
                shape="cylinder",
                dx=dx,
                dy=dy,
                dz=0.035,
                yaw=0.0,
                scale_x=0.18,
                scale_y=0.18,
                scale_z=0.018,
                color_r=0.86,
                color_g=0.89,
                color_b=0.92,
                color_a=0.82,
            )
        )
        parts.append(
            VehicleMarkerPart(
                marker_id=20 + index,
                namespace=f"navlab_vehicle_rotor_{index}_motor",
                shape="cylinder",
                dx=dx,
                dy=dy,
                dz=0.0,
                yaw=0.0,
                scale_x=0.06,
                scale_y=0.06,
                scale_z=0.065,
                color_r=0.03,
                color_g=0.04,
                color_b=0.05,
                color_a=1.0,
            )
        )
    return tuple(parts)


def quaternion_from_yaw(yaw: float) -> tuple[float, float, float, float]:
    return 0.0, 0.0, sin(yaw * 0.5), cos(yaw * 0.5)


def yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return atan2(siny_cosp, cosy_cosp)


def rotate_planar(x: float, y: float, yaw: float) -> tuple[float, float]:
    return x * cos(yaw) - y * sin(yaw), x * sin(yaw) + y * cos(yaw)


def marker_type(shape: str, marker_cls: type) -> int:
    if shape == "arrow":
        return marker_cls.ARROW
    if shape == "cube":
        return marker_cls.CUBE
    if shape == "sphere":
        return marker_cls.SPHERE
    if shape == "cylinder":
        return marker_cls.CYLINDER
    raise ValueError(f"unsupported vehicle marker shape: {shape}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish a portable primitive UAV shell for Foxglove replay.")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="MarkerArray output topic.")
    parser.add_argument("--pose-topic", default=DEFAULT_POSE_TOPIC, help="PoseStamped topic used to place the UAV.")
    parser.add_argument("--frame-id", default="", help="Override marker frame. Empty uses pose frame, then map.")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE_HZ, help="Publish rate in Hz.")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    parts = vehicle_marker_parts()

    try:
        import rclpy
        from geometry_msgs.msg import PoseStamped
        from rclpy.duration import Duration
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
        from visualization_msgs.msg import Marker, MarkerArray
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "vehicle_marker_publisher requires ROS2 Python packages. "
            "Source your ROS environment before running this command."
        ) from exc

    class VehicleMarkerPublisher(Node):
        def __init__(self) -> None:
            super().__init__("navlab_vehicle_marker_publisher")
            self._pose: PoseStamped | None = None
            qos = QoSProfile(depth=1)
            qos.reliability = ReliabilityPolicy.RELIABLE
            qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
            self._publisher = self.create_publisher(MarkerArray, args.topic, qos)
            self.create_subscription(PoseStamped, args.pose_topic, self._handle_pose, qos_profile_sensor_data)
            self.create_timer(1.0 / max(args.rate, 0.1), self._publish_markers)
            self.get_logger().info(
                f"publishing {len(parts)} primitive vehicle markers on {args.topic} from {args.pose_topic}"
            )

        def _handle_pose(self, message: PoseStamped) -> None:
            self._pose = message

        def _publish_markers(self) -> None:
            message = MarkerArray()
            now = self.get_clock().now().to_msg()
            pose = self._pose
            frame_id = args.frame_id or (pose.header.frame_id if pose is not None else "") or DEFAULT_FRAME_ID
            px = pose.pose.position.x if pose is not None else 0.0
            py = pose.pose.position.y if pose is not None else 0.0
            pz = pose.pose.position.z if pose is not None else 0.0
            if pose is not None:
                q = pose.pose.orientation
                yaw = yaw_from_quaternion(q.x, q.y, q.z, q.w)
            else:
                yaw = 0.0
            for part in parts:
                marker = Marker()
                marker.header.stamp = now
                marker.header.frame_id = frame_id
                marker.ns = part.namespace
                marker.id = part.marker_id
                marker.type = marker_type(part.shape, Marker)
                marker.action = Marker.ADD
                dx, dy = rotate_planar(part.dx, part.dy, yaw)
                marker.pose.position.x = px + dx
                marker.pose.position.y = py + dy
                marker.pose.position.z = pz + part.dz
                qx, qy, qz, qw = quaternion_from_yaw(yaw + part.yaw)
                marker.pose.orientation.x = qx
                marker.pose.orientation.y = qy
                marker.pose.orientation.z = qz
                marker.pose.orientation.w = qw
                marker.scale.x = part.scale_x
                marker.scale.y = part.scale_y
                marker.scale.z = part.scale_z
                marker.color.r = part.color_r
                marker.color.g = part.color_g
                marker.color.b = part.color_b
                marker.color.a = part.color_a
                marker.lifetime = Duration(seconds=0).to_msg()
                message.markers.append(marker)
            self._publisher.publish(message)

    rclpy.init()
    node = VehicleMarkerPublisher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
