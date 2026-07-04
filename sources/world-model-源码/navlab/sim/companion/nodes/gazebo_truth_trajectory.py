from __future__ import annotations

import argparse
import json
import math
import signal
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from navlab.sim.companion.nodes.gazebo_truth_odom import yaw_from_quaternion


@dataclass(frozen=True, slots=True)
class TrajectorySample:
    t_sec: float
    stamp_sec: float | None
    x_m: float
    y_m: float
    z_m: float
    yaw_rad: float
    vx_mps: float
    vy_mps: float
    vz_mps: float
    yaw_rate_radps: float


def _stamp_sec(stamp: object) -> float | None:
    sec = getattr(stamp, "sec", None)
    nanosec = getattr(stamp, "nanosec", None)
    if sec is None or nanosec is None:
        return None
    return float(sec) + (float(nanosec) / 1_000_000_000.0)


def sample_from_odom(msg: object, *, first_stamp_sec: float | None) -> TrajectorySample:
    stamp_sec = _stamp_sec(getattr(getattr(msg, "header", None), "stamp", None))
    if first_stamp_sec is None:
        t_sec = 0.0
    elif stamp_sec is None:
        t_sec = 0.0
    else:
        t_sec = max(0.0, stamp_sec - first_stamp_sec)
    pose = msg.pose.pose
    twist = msg.twist.twist
    orientation = pose.orientation
    return TrajectorySample(
        t_sec=t_sec,
        stamp_sec=stamp_sec,
        x_m=float(pose.position.x),
        y_m=float(pose.position.y),
        z_m=float(pose.position.z),
        yaw_rad=yaw_from_quaternion(
            x=float(orientation.x),
            y=float(orientation.y),
            z=float(orientation.z),
            w=float(orientation.w),
        ),
        vx_mps=float(twist.linear.x),
        vy_mps=float(twist.linear.y),
        vz_mps=float(twist.linear.z),
        yaw_rate_radps=float(twist.angular.z),
    )


def summarize_trajectory(samples: Sequence[TrajectorySample]) -> dict[str, object]:
    if not samples:
        return {
            "sample_count": 0,
            "duration_sec": 0.0,
            "horizontal_path_length_m": 0.0,
            "horizontal_displacement_m": 0.0,
        }
    path_length = 0.0
    for previous, current in zip(samples[:-1], samples[1:], strict=False):
        path_length += math.hypot(current.x_m - previous.x_m, current.y_m - previous.y_m)
    start = samples[0]
    end = samples[-1]
    xs = [sample.x_m for sample in samples]
    ys = [sample.y_m for sample in samples]
    zs = [sample.z_m for sample in samples]
    return {
        "sample_count": len(samples),
        "duration_sec": round(end.t_sec - start.t_sec, 6),
        "horizontal_path_length_m": round(path_length, 6),
        "horizontal_displacement_m": round(math.hypot(end.x_m - start.x_m, end.y_m - start.y_m), 6),
        "x_span_m": round(max(xs) - min(xs), 6),
        "y_span_m": round(max(ys) - min(ys), 6),
        "z_span_m": round(max(zs) - min(zs), 6),
        "min_z_m": round(min(zs), 6),
        "max_z_m": round(max(zs), 6),
        "start": asdict(start),
        "end": asdict(end),
    }


def write_trajectory_json(
    *,
    output_file: Path,
    topic: str,
    samples: Sequence[TrajectorySample],
) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "navlab.gazebo_truth_trajectory.v1",
        "source_topic": topic,
        "summary": summarize_trajectory(samples),
        "samples": [asdict(sample) for sample in samples],
    }
    output_file.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record Gazebo truth odom to a compact trajectory JSON.")
    parser.add_argument("--topic", default="/gazebo/truth/odom")
    parser.add_argument("--output-file", required=True, type=Path)
    parser.add_argument("--sample-rate-hz", type=float, default=10.0)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    min_period_sec = 0.0 if args.sample_rate_hz <= 0.0 else 1.0 / args.sample_rate_hz

    try:
        import rclpy
        from nav_msgs.msg import Odometry
        from rclpy.node import Node
    except ModuleNotFoundError as exc:
        raise SystemExit("gazebo_truth_trajectory requires ROS2 Python packages.") from exc

    class GazeboTruthTrajectoryRecorder(Node):
        def __init__(self) -> None:
            super().__init__("gazebo_truth_trajectory_recorder")
            self.samples: list[TrajectorySample] = []
            self._first_stamp_sec: float | None = None
            self._last_sample_stamp_sec: float | None = None
            self.create_subscription(Odometry, args.topic, self._handle_odom, 10)
            self.get_logger().info(f"recording {args.topic} to {args.output_file}")

        def _handle_odom(self, msg: object) -> None:
            stamp_sec = _stamp_sec(getattr(getattr(msg, "header", None), "stamp", None))
            if self._first_stamp_sec is None:
                self._first_stamp_sec = stamp_sec
            if (
                self._last_sample_stamp_sec is not None
                and stamp_sec is not None
                and stamp_sec - self._last_sample_stamp_sec < min_period_sec
            ):
                return
            sample = sample_from_odom(msg, first_stamp_sec=self._first_stamp_sec)
            self.samples.append(sample)
            self._last_sample_stamp_sec = stamp_sec

    rclpy.init(args=None)
    node = GazeboTruthTrajectoryRecorder()

    def _shutdown(_signum: int, _frame: object) -> None:
        if rclpy.ok():
            rclpy.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    try:
        rclpy.spin(node)
    finally:
        write_trajectory_json(output_file=args.output_file, topic=args.topic, samples=node.samples)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
