from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import atan2, cos, sin
from pathlib import Path

from navlab.sim.companion.runtime.world_markers import (
    MarkerPose,
    MarkerSpec,
    load_world_marker_specs,
    load_world_model_pose,
)

DEFAULT_WORLD_FILE = Path("/workspace/docker/worlds/navlab_iq_quad_figure8.sdf")
DEFAULT_TOPIC = "/sim/markers"
DEFAULT_POSE_TOPIC = "/sim/uav_pose"
DEFAULT_ROOT_MODEL_NAME = "navlab_iq_quad"
DEFAULT_REPLAY_FRAME_ID = "navlab_world"


@dataclass(frozen=True, slots=True)
class _LocalMarkerOffset:
    marker_id: int
    namespace: str
    shape: str
    dx: float
    dy: float
    dz: float
    droll: float
    dpitch: float
    dyaw: float
    scale_x: float
    scale_y: float
    scale_z: float
    color_r: float
    color_g: float
    color_b: float
    color_a: float
    frame_id: str


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish MarkerArray from the current world SDF.")
    parser.add_argument(
        "--world-file",
        default=str(DEFAULT_WORLD_FILE),
        help="Path to the SDF world file.",
    )
    parser.add_argument(
        "--topic",
        default=DEFAULT_TOPIC,
        help="MarkerArray output topic.",
    )
    parser.add_argument(
        "--pose-topic",
        default=DEFAULT_POSE_TOPIC,
        help="PoseStamped topic used to place the UAV markers.",
    )
    parser.add_argument(
        "--frame-id",
        default=DEFAULT_REPLAY_FRAME_ID,
        help="Stable replay frame used for all scene markers.",
    )
    parser.add_argument(
        "--root-model-name",
        default=DEFAULT_ROOT_MODEL_NAME,
        help="World model/include name whose pose anchors UAV marker offsets.",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="Republish rate in Hz.",
    )
    return parser


def _marker_type(marker_spec: MarkerSpec, marker_cls: type) -> int:
    if marker_spec.shape == "arrow":
        return marker_cls.ARROW
    if marker_spec.shape == "cube":
        return marker_cls.CUBE
    if marker_spec.shape == "sphere":
        return marker_cls.SPHERE
    if marker_spec.shape == "cylinder":
        return marker_cls.CYLINDER
    raise ValueError(f"unsupported marker shape: {marker_spec.shape}")


def _quaternion_from_rpy(roll: float, pitch: float, yaw: float) -> tuple[float, float, float, float]:
    cy = cos(yaw * 0.5)
    sy = sin(yaw * 0.5)
    cp = cos(pitch * 0.5)
    sp = sin(pitch * 0.5)
    cr = cos(roll * 0.5)
    sr = sin(roll * 0.5)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def _rotate_planar(x: float, y: float, yaw: float) -> tuple[float, float]:
    return (x * cos(yaw) - y * sin(yaw), x * sin(yaw) + y * cos(yaw))


def build_local_marker_offsets(specs: list[MarkerSpec], *, root_pose: MarkerPose) -> dict[int, _LocalMarkerOffset]:
    offsets: dict[int, _LocalMarkerOffset] = {}
    for spec in specs:
        if not spec.namespace.startswith("navlab_iq_quad_"):
            continue
        dx_world = spec.pose.x - root_pose.x
        dy_world = spec.pose.y - root_pose.y
        dx_local, dy_local = _rotate_planar(dx_world, dy_world, -root_pose.yaw)
        offsets[spec.marker_id] = _LocalMarkerOffset(
            marker_id=spec.marker_id,
            namespace=spec.namespace,
            shape=spec.shape,
            dx=dx_local,
            dy=dy_local,
            dz=spec.pose.z - root_pose.z,
            droll=spec.pose.roll - root_pose.roll,
            dpitch=spec.pose.pitch - root_pose.pitch,
            dyaw=spec.pose.yaw - root_pose.yaw,
            scale_x=spec.scale.x,
            scale_y=spec.scale.y,
            scale_z=spec.scale.z,
            color_r=spec.color.r,
            color_g=spec.color.g,
            color_b=spec.color.b,
            color_a=spec.color.a,
            frame_id=spec.frame_id,
        )
    return offsets


def apply_uav_pose(
    spec: MarkerSpec,
    *,
    current_pose: MarkerPose,
    local_offsets: dict[int, _LocalMarkerOffset],
) -> MarkerSpec:
    offset = local_offsets.get(spec.marker_id)
    if offset is None:
        return spec
    dx_world, dy_world = _rotate_planar(offset.dx, offset.dy, current_pose.yaw)
    return MarkerSpec(
        marker_id=spec.marker_id,
        namespace=spec.namespace,
        shape=spec.shape,
        pose=MarkerPose(
            x=current_pose.x + dx_world,
            y=current_pose.y + dy_world,
            z=current_pose.z + offset.dz,
            roll=current_pose.roll + offset.droll,
            pitch=current_pose.pitch + offset.dpitch,
            yaw=current_pose.yaw + offset.dyaw,
        ),
        scale=spec.scale,
        color=spec.color,
        frame_id=spec.frame_id,
    )


def run(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    specs = load_world_marker_specs(args.world_file)
    uav_root_pose = load_world_model_pose(args.world_file, args.root_model_name)
    local_offsets = build_local_marker_offsets(specs, root_pose=uav_root_pose)

    try:
        import rclpy
        from geometry_msgs.msg import PoseStamped
        from rclpy.duration import Duration
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from visualization_msgs.msg import Marker, MarkerArray
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "world_marker_publisher requires ROS2 Python packages. "
            "Source your ROS environment before running this command."
        ) from exc

    class WorldMarkerPublisher(Node):
        def __init__(self) -> None:
            super().__init__("world_marker_publisher")
            self._current_pose = uav_root_pose
            qos = QoSProfile(depth=1)
            qos.reliability = ReliabilityPolicy.RELIABLE
            qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
            self._publisher = self.create_publisher(MarkerArray, args.topic, qos)
            self.create_subscription(PoseStamped, args.pose_topic, self._handle_pose, 10)
            self._timer = self.create_timer(1.0 / args.rate, self._publish_markers)
            self.get_logger().info(f"publishing {len(specs)} markers on {args.topic}")

        def _handle_pose(self, message: PoseStamped) -> None:
            q = message.pose.orientation
            yaw = 2.0 * atan2(q.z, q.w)
            self._current_pose = MarkerPose(
                x=message.pose.position.x,
                y=message.pose.position.y,
                z=message.pose.position.z,
                yaw=yaw,
            )

        def _publish_markers(self) -> None:
            message = MarkerArray()
            now = self.get_clock().now().to_msg()
            for spec in specs:
                resolved_spec = apply_uav_pose(spec, current_pose=self._current_pose, local_offsets=local_offsets)
                marker = Marker()
                marker.header.stamp = now
                marker.header.frame_id = args.frame_id
                marker.ns = resolved_spec.namespace
                marker.id = resolved_spec.marker_id
                marker.type = _marker_type(resolved_spec, Marker)
                marker.action = Marker.ADD
                marker.pose.position.x = resolved_spec.pose.x
                marker.pose.position.y = resolved_spec.pose.y
                marker.pose.position.z = resolved_spec.pose.z
                orientation = _quaternion_from_rpy(
                    resolved_spec.pose.roll,
                    resolved_spec.pose.pitch,
                    resolved_spec.pose.yaw,
                )
                marker.pose.orientation.x = orientation[0]
                marker.pose.orientation.y = orientation[1]
                marker.pose.orientation.z = orientation[2]
                marker.pose.orientation.w = orientation[3]
                marker.scale.x = resolved_spec.scale.x
                marker.scale.y = resolved_spec.scale.y
                marker.scale.z = resolved_spec.scale.z
                marker.color.r = resolved_spec.color.r
                marker.color.g = resolved_spec.color.g
                marker.color.b = resolved_spec.color.b
                marker.color.a = resolved_spec.color.a
                marker.lifetime = Duration(seconds=0.0).to_msg()
                message.markers.append(marker)
            self._publisher.publish(message)

    rclpy.init(args=None)
    node = WorldMarkerPublisher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0
