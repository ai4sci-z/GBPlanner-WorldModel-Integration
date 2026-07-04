from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass

from navlab.common.pose import quaternion_from_yaw


@dataclass(frozen=True, slots=True)
class Pose2D:
    x: float
    y: float
    z: float
    yaw: float


@dataclass(frozen=True, slots=True)
class TruthOdomFields:
    x: float
    y: float
    z: float
    yaw: float
    vx: float
    vy: float
    vz: float
    yaw_rate: float


def yaw_from_quaternion(*, x: float, y: float, z: float, w: float) -> float:
    return math.atan2(2.0 * ((w * z) + (x * y)), 1.0 - (2.0 * ((y * y) + (z * z))))


def normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def relative_pose(*, pose: Pose2D, origin: Pose2D) -> Pose2D:
    dx = pose.x - origin.x
    dy = pose.y - origin.y
    cos_yaw = math.cos(-origin.yaw)
    sin_yaw = math.sin(-origin.yaw)
    return Pose2D(
        x=(dx * cos_yaw) - (dy * sin_yaw),
        y=(dx * sin_yaw) + (dy * cos_yaw),
        z=pose.z - origin.z,
        yaw=normalize_angle(pose.yaw - origin.yaw),
    )


def truth_odom_fields(
    *,
    pose: Pose2D,
    origin: Pose2D,
    previous_pose: Pose2D | None,
    previous_monotonic: float | None,
    now_monotonic: float,
) -> TruthOdomFields:
    current = relative_pose(pose=pose, origin=origin)
    vx = vy = vz = yaw_rate = 0.0
    if previous_pose is not None and previous_monotonic is not None:
        previous = relative_pose(pose=previous_pose, origin=origin)
        dt = now_monotonic - previous_monotonic
        if dt > 0.0:
            vx = (current.x - previous.x) / dt
            vy = (current.y - previous.y) / dt
            vz = (current.z - previous.z) / dt
            yaw_rate = normalize_angle(current.yaw - previous.yaw) / dt
    return TruthOdomFields(
        x=current.x,
        y=current.y,
        z=current.z,
        yaw=current.yaw,
        vx=vx,
        vy=vy,
        vz=vz,
        yaw_rate=yaw_rate,
    )


def pose_from_transform(transform: object) -> Pose2D:
    translation = transform.transform.translation
    rotation = transform.transform.rotation
    return Pose2D(
        x=float(translation.x),
        y=float(translation.y),
        z=float(translation.z),
        yaw=yaw_from_quaternion(
            x=float(rotation.x),
            y=float(rotation.y),
            z=float(rotation.z),
            w=float(rotation.w),
        ),
    )


def child_frame_matches(actual: str, expected: str) -> bool:
    if not expected:
        return False
    if actual == expected:
        return True
    if actual.startswith(f"{expected}::") or actual.startswith(f"{expected}/"):
        return True
    tokens = [token for token in actual.replace("/", "::").split("::") if token]
    return expected in tokens


def transform_frame_id(transform: object) -> str:
    header = getattr(transform, "header", None)
    return "" if header is None else getattr(header, "frame_id", "")


def transform_identity(transform: object) -> str:
    return getattr(transform, "child_frame_id", "") or transform_frame_id(transform)


def select_transform(transforms: Sequence[object], *, child_frame_id: str, transform_index: int) -> object | None:
    if child_frame_id:
        for transform in transforms:
            if child_frame_matches(getattr(transform, "child_frame_id", ""), child_frame_id) or child_frame_matches(
                transform_frame_id(transform),
                child_frame_id,
            ):
                return transform
        return None
    if 0 <= transform_index < len(transforms):
        return transforms[transform_index]
    return None


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish Gazebo physical model pose as nav_msgs/Odometry.")
    parser.add_argument("--input-topic", default="/gazebo/tf")
    parser.add_argument("--odom-topic", default="/gazebo/truth/odom")
    parser.add_argument("--status-topic", default="/gazebo/truth/status")
    parser.add_argument("--frame-id", default="odom")
    parser.add_argument("--child-frame-id", default="base_link")
    parser.add_argument("--gazebo-child-frame-id", default="")
    parser.add_argument("--transform-index", type=int, default=0)
    parser.add_argument("--timeout-sec", type=float, default=1.0)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        import rclpy
        from nav_msgs.msg import Odometry
        from rclpy.node import Node
        from std_msgs.msg import String
        from tf2_msgs.msg import TFMessage
    except ModuleNotFoundError as exc:
        raise SystemExit("gazebo_truth_odom requires ROS2 Python packages.") from exc

    class GazeboTruthOdomNode(Node):
        def __init__(self) -> None:
            super().__init__("gazebo_truth_odom")
            self._origin: Pose2D | None = None
            self._previous_pose: Pose2D | None = None
            self._previous_monotonic: float | None = None
            self._last_fields: TruthOdomFields | None = None
            self._last_message_monotonic = 0.0
            self._message_count = 0
            self._selected_count = 0
            self._selected_child_frame_id = ""
            self._seen_child_frame_ids: list[str] = []
            self._seen_frame_ids: list[str] = []
            self._odom_pub = self.create_publisher(Odometry, args.odom_topic, 10)
            self._status_pub = self.create_publisher(String, args.status_topic, 10)
            self.create_subscription(TFMessage, args.input_topic, self._handle_tf, 10)
            self.create_timer(0.5, self._publish_status)
            self.get_logger().info(
                f"gazebo_truth_odom started input={args.input_topic} odom={args.odom_topic} "
                f"index={args.transform_index} gazebo_child_frame={args.gazebo_child_frame_id or '<index>'}"
            )

        def _handle_tf(self, msg: object) -> None:
            self._message_count += 1
            self._remember_child_frame_ids(msg.transforms)
            transform = select_transform(
                list(msg.transforms),
                child_frame_id=args.gazebo_child_frame_id,
                transform_index=args.transform_index,
            )
            if transform is None:
                return
            self._selected_count += 1
            self._selected_child_frame_id = transform_identity(transform)
            now_monotonic = time.monotonic()
            pose = pose_from_transform(transform)
            if self._origin is None:
                self._origin = pose
            fields = truth_odom_fields(
                pose=pose,
                origin=self._origin,
                previous_pose=self._previous_pose,
                previous_monotonic=self._previous_monotonic,
                now_monotonic=now_monotonic,
            )
            self._previous_pose = pose
            self._previous_monotonic = now_monotonic
            self._last_fields = fields
            self._last_message_monotonic = now_monotonic
            self._publish_odom(fields)

        def _publish_odom(self, fields: TruthOdomFields) -> None:
            qx, qy, qz, qw = quaternion_from_yaw(fields.yaw)
            odom = Odometry()
            odom.header.stamp = self.get_clock().now().to_msg()
            odom.header.frame_id = args.frame_id
            odom.child_frame_id = args.child_frame_id
            odom.pose.pose.position.x = fields.x
            odom.pose.pose.position.y = fields.y
            odom.pose.pose.position.z = fields.z
            odom.pose.pose.orientation.x = qx
            odom.pose.pose.orientation.y = qy
            odom.pose.pose.orientation.z = qz
            odom.pose.pose.orientation.w = qw
            odom.twist.twist.linear.x = fields.vx
            odom.twist.twist.linear.y = fields.vy
            odom.twist.twist.linear.z = fields.vz
            odom.twist.twist.angular.z = fields.yaw_rate
            odom.pose.covariance[0] = 0.0025
            odom.pose.covariance[7] = 0.0025
            odom.pose.covariance[14] = 0.0025
            odom.pose.covariance[35] = 0.01
            odom.twist.covariance[0] = 0.01
            odom.twist.covariance[7] = 0.01
            odom.twist.covariance[14] = 0.01
            odom.twist.covariance[35] = 0.02
            self._odom_pub.publish(odom)

        def _publish_status(self) -> None:
            age_sec = time.monotonic() - self._last_message_monotonic if self._last_message_monotonic else math.inf
            fields = self._last_fields
            ready = fields is not None and age_sec <= args.timeout_sec
            status = {
                "state": "publishing" if ready else "waiting_for_gazebo_pose",
                "ready": ready,
                "input_topic": args.input_topic,
                "odom_topic": args.odom_topic,
                "transform_index": args.transform_index,
                "gazebo_child_frame_id": args.gazebo_child_frame_id,
                "selected_child_frame_id": self._selected_child_frame_id,
                "seen_child_frame_ids": self._seen_child_frame_ids[:40],
                "seen_frame_ids": self._seen_frame_ids[:40],
                "message_count": self._message_count,
                "selected_count": self._selected_count,
                "age_ms": None if math.isinf(age_sec) else round(age_sec * 1000.0, 3),
                "pose": None
                if fields is None
                else {
                    "x": round(fields.x, 3),
                    "y": round(fields.y, 3),
                    "z": round(fields.z, 3),
                    "yaw": round(fields.yaw, 3),
                },
            }
            message = String()
            message.data = json.dumps(status, separators=(",", ":"), sort_keys=True)
            self._status_pub.publish(message)

        def _remember_child_frame_ids(self, transforms: object) -> None:
            seen = set(self._seen_child_frame_ids)
            seen_frames = set(self._seen_frame_ids)
            for transform in transforms:
                child_frame_id = getattr(transform, "child_frame_id", "")
                if child_frame_id and child_frame_id not in seen:
                    self._seen_child_frame_ids.append(child_frame_id)
                    seen.add(child_frame_id)
                frame_id = transform_frame_id(transform)
                if frame_id and frame_id not in seen_frames:
                    self._seen_frame_ids.append(frame_id)
                    seen_frames.add(frame_id)
                if len(self._seen_child_frame_ids) >= 40 and len(self._seen_frame_ids) >= 40:
                    return

    rclpy.init(args=None)
    node = GazeboTruthOdomNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
