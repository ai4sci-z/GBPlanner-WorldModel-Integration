from __future__ import annotations

import copy
import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from navlab.common.logging import configure_sim_logging, logger
from navlab.sim.gazebo_sensor.config import ScanStabilizationRuntimeConfig
from navlab.sim.gazebo_sensor.scan_integrity import quaternion_to_rpy_deg


@dataclass(frozen=True, slots=True)
class StabilizedScanQuality:
    state: str
    tilt_deg: float
    ranges: tuple[float, ...]
    retained_beam_ratio: float
    rejected_beam_ratio: float
    floor_hit_risk_beam_ratio: float
    max_vertical_projection_error_m: float
    mean_vertical_projection_error_m: float
    rejected_beam_count: int
    floor_hit_rejected_count: int
    blockers: tuple[str, ...]


def _level_point(*, range_m: float, angle_rad: float, roll_deg: float, pitch_deg: float) -> tuple[float, float, float]:
    x = range_m * math.cos(angle_rad)
    y = range_m * math.sin(angle_rad)
    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    z_roll = math.sin(roll) * y
    y_roll = math.cos(roll) * y
    x_level = math.cos(pitch) * x + math.sin(pitch) * z_roll
    z_level = -math.sin(pitch) * x + math.cos(pitch) * z_roll
    return x_level, y_roll, z_level


def scan_attitude_time_offset_ms(*, scan_stamp_sec: float, attitude_stamp_sec: float) -> float:
    if scan_stamp_sec <= 0.0 or attitude_stamp_sec <= 0.0:
        return 0.0
    return abs(scan_stamp_sec - attitude_stamp_sec) * 1000.0


def angle_to_scan_bin(*, angle_rad: float, angle_min: float, angle_increment: float, beam_count: int) -> int | None:
    if beam_count <= 0 or abs(angle_increment) <= 1e-9:
        return None
    raw_index = int(round((angle_rad - angle_min) / angle_increment))
    if 0 <= raw_index < beam_count:
        return raw_index
    scan_span = abs(angle_increment) * float(beam_count)
    if scan_span < (2.0 * math.pi - abs(angle_increment)):
        return None
    wrapped = (angle_rad - angle_min) % (2.0 * math.pi)
    wrapped_index = int(round(wrapped / abs(angle_increment))) % beam_count
    return wrapped_index


def validate_scan_stabilization_thresholds(
    *,
    passthrough_tilt_deg: float,
    compensation_tilt_deg: float,
    hard_drop_tilt_deg: float,
    max_vertical_projection_error_m: float,
    max_rejected_beam_ratio: float,
    min_retained_beam_ratio: float,
    max_floor_hit_risk_beam_ratio: float,
) -> list[str]:
    blockers: list[str] = []
    if not (0.0 <= passthrough_tilt_deg < compensation_tilt_deg < hard_drop_tilt_deg):
        blockers.append("scan_stabilization_config_invalid: tilt thresholds must be ordered")
    for name, value in (
        ("max_rejected_beam_ratio", max_rejected_beam_ratio),
        ("min_retained_beam_ratio", min_retained_beam_ratio),
        ("max_floor_hit_risk_beam_ratio", max_floor_hit_risk_beam_ratio),
    ):
        if not (0.0 <= value <= 1.0):
            blockers.append(f"scan_stabilization_config_invalid: {name} must be in [0, 1]")
    if max_vertical_projection_error_m <= 0.0:
        blockers.append("scan_stabilization_config_invalid: max_vertical_projection_error_m must be positive")
    return blockers


def stabilize_scan_ranges(
    *,
    ranges: Sequence[float],
    angle_min: float,
    angle_increment: float,
    range_min: float,
    range_max: float,
    roll_deg: float,
    pitch_deg: float,
    lidar_height_m: float,
    passthrough_tilt_deg: float,
    compensation_tilt_deg: float,
    hard_drop_tilt_deg: float,
    max_vertical_projection_error_m: float,
    max_rejected_beam_ratio: float,
    min_retained_beam_ratio: float,
    max_floor_hit_risk_beam_ratio: float,
    floor_hit_guard_range_m: float,
    min_downward_ray_z: float,
) -> StabilizedScanQuality:
    config_blockers = validate_scan_stabilization_thresholds(
        passthrough_tilt_deg=passthrough_tilt_deg,
        compensation_tilt_deg=compensation_tilt_deg,
        hard_drop_tilt_deg=hard_drop_tilt_deg,
        max_vertical_projection_error_m=max_vertical_projection_error_m,
        max_rejected_beam_ratio=max_rejected_beam_ratio,
        min_retained_beam_ratio=min_retained_beam_ratio,
        max_floor_hit_risk_beam_ratio=max_floor_hit_risk_beam_ratio,
    )
    if config_blockers:
        return StabilizedScanQuality(
            "blocked", 0.0, tuple(ranges), 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, tuple(config_blockers)
        )

    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    tilt_deg = math.degrees(math.hypot(roll, pitch))
    if lidar_height_m <= 0.0:
        return StabilizedScanQuality(
            "blocked", tilt_deg, tuple(ranges), 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, ("missing_lidar_height",)
        )
    if tilt_deg > hard_drop_tilt_deg:
        return StabilizedScanQuality(
            "drop", tilt_deg, tuple(ranges), 0.0, 1.0, 0.0, 0.0, 0.0, len(ranges), 0, ("hard_tilt_exceeded",)
        )
    if tilt_deg <= passthrough_tilt_deg:
        finite_count = sum(1 for value in ranges if math.isfinite(float(value)) and float(value) > 0.0)
        ratio = 1.0 if finite_count else 0.0
        return StabilizedScanQuality(
            "passthrough", tilt_deg, tuple(float(v) for v in ranges), ratio, 0.0, 0.0, 0.0, 0.0, 0, 0, ()
        )
    if tilt_deg > compensation_tilt_deg:
        return StabilizedScanQuality(
            "drop", tilt_deg, tuple(ranges), 0.0, 1.0, 0.0, 0.0, 0.0, len(ranges), 0, ("tilt_above_compensation_limit",)
        )

    output = [float("inf")] * len(ranges)
    finite_count = 0
    rejected_count = 0
    floor_hit_count = 0
    vertical_errors: list[float] = []
    guard_range = min(float(floor_hit_guard_range_m), float(range_max) if range_max > 0 else floor_hit_guard_range_m)
    for index, raw_range in enumerate(ranges):
        value = float(raw_range)
        if not math.isfinite(value) or value < range_min or value > range_max:
            continue
        finite_count += 1
        angle = angle_min + float(index) * angle_increment
        x_level, y_level, z_level = _level_point(range_m=value, angle_rad=angle, roll_deg=roll_deg, pitch_deg=pitch_deg)
        vertical_error = abs(z_level)
        vertical_errors.append(vertical_error)
        ray_z = z_level / max(value, 1e-6)
        floor_hit_risk = False
        if ray_z < -abs(min_downward_ray_z):
            floor_intersection = lidar_height_m / max(abs(ray_z), 1e-6)
            floor_hit_risk = floor_intersection <= guard_range and floor_intersection <= value
        if vertical_error > max_vertical_projection_error_m or floor_hit_risk:
            rejected_count += 1
            if floor_hit_risk:
                floor_hit_count += 1
            continue
        projected_range = math.hypot(x_level, y_level)
        if projected_range < range_min or projected_range > range_max:
            rejected_count += 1
            continue
        projected_angle = math.atan2(y_level, x_level)
        out_index = angle_to_scan_bin(
            angle_rad=projected_angle,
            angle_min=angle_min,
            angle_increment=angle_increment,
            beam_count=len(output),
        )
        if out_index is None:
            rejected_count += 1
            continue
        output[out_index] = min(output[out_index], projected_range)

    retained_count = sum(1 for value in output if math.isfinite(value))
    denom = max(finite_count, 1)
    retained_ratio = retained_count / denom
    rejected_ratio = rejected_count / denom
    floor_ratio = floor_hit_count / denom
    blockers: list[str] = []
    if rejected_ratio > max_rejected_beam_ratio:
        blockers.append("rejected_beam_ratio_too_high")
    if retained_ratio < min_retained_beam_ratio:
        blockers.append("retained_beam_ratio_too_low")
    if floor_ratio > max_floor_hit_risk_beam_ratio:
        blockers.append("floor_hit_risk_too_high")
    state = "drop" if blockers else "compensate"
    final_ranges = tuple((float(range_max) if value == float("inf") else value) for value in output)
    max_error = max(vertical_errors) if vertical_errors else 0.0
    mean_error = sum(vertical_errors) / len(vertical_errors) if vertical_errors else 0.0
    return StabilizedScanQuality(
        state,
        tilt_deg,
        final_ranges,
        retained_ratio,
        rejected_ratio,
        floor_ratio,
        max_error,
        mean_error,
        rejected_count,
        floor_hit_count,
        tuple(blockers),
    )


def run() -> int:
    try:
        import rclpy
        from geometry_msgs.msg import PoseStamped
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
        from rclpy.parameter import Parameter
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
        from sensor_msgs.msg import Imu, LaserScan, Range
        from std_msgs.msg import String
        from tf2_msgs.msg import TFMessage
    except ModuleNotFoundError as exc:
        raise SystemExit("scan stabilization filter requires ROS2 Python packages.") from exc

    config = ScanStabilizationRuntimeConfig.load()
    blockers = config.validate()
    if blockers:
        logger.error("invalid scan stabilization config: {}", blockers)
        return 22
    if not config.enabled:
        logger.error("scan stabilization filter was launched while disabled")
        return 22
    if config.attitude_source_topic.startswith("/gazebo") or config.attitude_source_topic == "/odometry":
        logger.error("attitude source must not be Gazebo truth: {}", config.attitude_source_topic)
        return 22

    class ScanStabilizationFilter(Node):
        def __init__(self) -> None:
            super().__init__("navlab_scan_stabilization_filter")
            self.set_parameters([Parameter("use_sim_time", Parameter.Type.BOOL, True)])
            self._publisher = self.create_publisher(LaserScan, config.output_scan_topic, qos_profile_sensor_data)
            self._status_publisher = self.create_publisher(String, config.status_topic, 10)
            self._event_publisher = self.create_publisher(String, config.events_topic, 10)
            self._debug_publisher = (
                self.create_publisher(LaserScan, config.debug_scan_topic, qos_profile_sensor_data)
                if config.publish_debug_scan
                else None
            )
            self._attitude: dict[str, Any] | None = None
            self._range_height_m: float | None = None
            self._base_scan_tf_ok = False
            self._started = time.monotonic()
            self._count = 0
            self._passthrough = 0
            self._compensated = 0
            self._dropped = 0
            self._blocked_count = 0
            self._hard_tilt_dropped_count = 0
            self._rejected_beam_count = 0
            self._floor_hit_rejected_count = 0
            self._max_vertical_projection_error_m = 0.0
            self._max_observed_tilt_deg = 0.0
            self._max_compensated_tilt_deg = 0.0
            self._attitude_times: list[float] = []
            self._fault = {"enabled": False, "roll_bias_deg": 0.0, "pitch_bias_deg": 0.0}
            static_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
            )
            self.create_subscription(TFMessage, "/tf_static", self._tf_static_cb, static_qos)
            self.create_subscription(Range, config.range_topic, self._range_cb, qos_profile_sensor_data)
            self.create_subscription(String, config.fault_injection_topic, self._fault_cb, 10)
            self.create_subscription(LaserScan, config.input_scan_topic, self._scan_cb, qos_profile_sensor_data)
            if config.attitude_source_type == "imu":
                self.create_subscription(Imu, config.attitude_source_topic, self._imu_cb, qos_profile_sensor_data)
            else:
                self.create_subscription(PoseStamped, config.attitude_source_topic, self._pose_cb, 10)
            self.create_timer(2.0, self._log_status)

        def _stamp_sec(self, stamp: Any) -> float:
            return float(stamp.sec) + float(stamp.nanosec) * 1e-9

        def _json_msg(self, payload: dict[str, Any]) -> Any:
            msg = String()
            msg.data = json.dumps(payload, sort_keys=True)
            return msg

        def _tf_static_cb(self, message: TFMessage) -> None:
            for transform in message.transforms:
                if (
                    transform.header.frame_id == config.base_frame_id
                    and transform.child_frame_id == config.scan_frame_id
                ):
                    self._base_scan_tf_ok = True

        def _range_cb(self, message: Range) -> None:
            value = float(message.range)
            if math.isfinite(value) and value >= config.min_lidar_height_m:
                self._range_height_m = value

        def _fault_cb(self, message: String) -> None:
            try:
                payload = json.loads(message.data)
            except json.JSONDecodeError:
                payload = {}
            self._fault = {
                "enabled": bool(payload.get("enabled")),
                "roll_bias_deg": float(payload.get("roll_bias_deg") or 0.0),
                "pitch_bias_deg": float(payload.get("pitch_bias_deg") or 0.0),
            }
            self._event_publisher.publish(self._json_msg({"event": "fault_injection_update", **self._fault}))

        def _record_attitude(self, *, roll_deg: float, pitch_deg: float, yaw_deg: float, stamp_sec: float) -> None:
            now = time.monotonic()
            self._attitude = {
                "roll_deg": roll_deg,
                "pitch_deg": pitch_deg,
                "yaw_deg": yaw_deg,
                "stamp_sec": stamp_sec,
                "monotonic": now,
            }
            self._attitude_times.append(now)
            cutoff = now - 5.0
            self._attitude_times = [item for item in self._attitude_times if item >= cutoff]

        def _imu_cb(self, message: Imu) -> None:
            q = message.orientation
            try:
                roll, pitch, yaw = quaternion_to_rpy_deg(float(q.x), float(q.y), float(q.z), float(q.w))
            except ValueError:
                return
            self._record_attitude(
                roll_deg=roll, pitch_deg=pitch, yaw_deg=yaw, stamp_sec=self._stamp_sec(message.header.stamp)
            )

        def _pose_cb(self, message: PoseStamped) -> None:
            q = message.pose.orientation
            try:
                roll, pitch, yaw = quaternion_to_rpy_deg(float(q.x), float(q.y), float(q.z), float(q.w))
            except ValueError:
                return
            self._record_attitude(
                roll_deg=roll, pitch_deg=pitch, yaw_deg=yaw, stamp_sec=self._stamp_sec(message.header.stamp)
            )

        def _attitude_rate(self) -> float:
            now = time.monotonic()
            cutoff = now - 5.0
            self._attitude_times = [item for item in self._attitude_times if item >= cutoff]
            if len(self._attitude_times) < 2:
                return 0.0
            return (len(self._attitude_times) - 1) / max(self._attitude_times[-1] - self._attitude_times[0], 0.001)

        def _attitude_source_age_ms(self) -> float | None:
            if self._attitude is None:
                return None
            return max(0.0, (time.monotonic() - float(self._attitude.get("monotonic") or 0.0)) * 1000.0)

        def _publish_status(self, payload: dict[str, Any]) -> None:
            self._status_publisher.publish(self._json_msg(payload))
            if payload.get("state") in {"compensate", "drop", "blocked"}:
                self._event_publisher.publish(self._json_msg(payload))

        def _status_payload(
            self,
            message: LaserScan,
            quality: StabilizedScanQuality,
            *,
            blockers: Sequence[str] = (),
            time_offset_ms: float | None = None,
        ) -> dict[str, Any]:
            attitude = self._attitude or {}
            all_blockers = [*quality.blockers, *blockers]
            candidate_count = self._passthrough + self._compensated
            baseline_count = self._passthrough
            return {
                "ok": not all_blockers,
                "state": quality.state,
                "mode": config.mode,
                "input_scan_topic": config.input_scan_topic,
                "output_scan_topic": config.output_scan_topic,
                "attitude_source": config.attitude_source_topic,
                "attitude_source_type": config.attitude_source_type,
                "attitude_source_is_truth": False,
                "roll_deg": float(attitude.get("roll_deg") or 0.0)
                + (self._fault["roll_bias_deg"] if self._fault["enabled"] else 0.0),
                "pitch_deg": float(attitude.get("pitch_deg") or 0.0)
                + (self._fault["pitch_bias_deg"] if self._fault["enabled"] else 0.0),
                "tilt_deg": quality.tilt_deg,
                "scan_attitude_time_offset_ms": time_offset_ms,
                "attitude_source_age_ms": self._attitude_source_age_ms(),
                "input_scan_stamp": self._stamp_sec(message.header.stamp),
                "attitude_stamp": attitude.get("stamp_sec"),
                "base_scan_static_tf_ok": self._base_scan_tf_ok,
                "lidar_height_m": self._range_height_m,
                "passthrough_scan_count": self._passthrough,
                "compensated_scan_count": self._compensated,
                "dropped_scan_count": self._dropped,
                "blocked_scan_count": self._blocked_count,
                "candidate_validated_scan_count": candidate_count,
                "baseline_drop_only_validated_scan_count": baseline_count,
                "scan_availability_improved": candidate_count >= baseline_count,
                "retained_beam_ratio": quality.retained_beam_ratio,
                "rejected_beam_ratio": quality.rejected_beam_ratio,
                "floor_hit_risk_beam_ratio": quality.floor_hit_risk_beam_ratio,
                "rejected_beam_count": self._rejected_beam_count,
                "floor_hit_rejected_count": self._floor_hit_rejected_count,
                "max_vertical_projection_error_m": self._max_vertical_projection_error_m,
                "mean_vertical_projection_error_m": quality.mean_vertical_projection_error_m,
                "max_observed_tilt_deg": self._max_observed_tilt_deg,
                "max_compensated_tilt_deg": self._max_compensated_tilt_deg,
                "hard_tilt_dropped": self._hard_tilt_dropped_count > 0,
                "hard_tilt_dropped_count": self._hard_tilt_dropped_count,
                "false_wall_risk_ok": quality.floor_hit_risk_beam_ratio <= config.max_floor_hit_risk_beam_ratio,
                "fault_injection": self._fault,
                "runtime_config": config.to_summary(),
                "blockers": all_blockers,
            }

        def _blocked(self, message: LaserScan, blockers: Sequence[str]) -> None:
            self._count += 1
            self._blocked_count += 1
            quality = StabilizedScanQuality(
                "blocked", 0.0, tuple(message.ranges), 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, tuple(blockers)
            )
            self._publish_status(self._status_payload(message, quality))

        def _scan_cb(self, message: LaserScan) -> None:
            blockers: list[str] = []
            if not self._base_scan_tf_ok:
                blockers.append("missing_base_scan_static_tf")
            if self._attitude is None:
                blockers.append("missing_attitude_source")
            if self._range_height_m is None:
                blockers.append("missing_lidar_height")
            attitude_age_ms = self._attitude_source_age_ms()
            if attitude_age_ms is not None and attitude_age_ms > config.max_attitude_source_age_ms:
                blockers.append("attitude_source_age_too_high")
            if self._attitude_rate() < config.min_attitude_rate_hz and self._count > 5:
                blockers.append("attitude_rate_too_low")
            if blockers:
                self._blocked(message, blockers)
                return
            attitude = self._attitude or {}
            scan_stamp = self._stamp_sec(message.header.stamp)
            attitude_stamp = float(attitude.get("stamp_sec") or 0.0)
            time_offset_ms = scan_attitude_time_offset_ms(
                scan_stamp_sec=scan_stamp,
                attitude_stamp_sec=attitude_stamp,
            )
            if time_offset_ms > config.max_scan_attitude_time_offset_ms:
                self._blocked(message, ["scan_attitude_time_offset_too_high"])
                return
            roll = float(attitude["roll_deg"]) + (self._fault["roll_bias_deg"] if self._fault["enabled"] else 0.0)
            pitch = float(attitude["pitch_deg"]) + (self._fault["pitch_bias_deg"] if self._fault["enabled"] else 0.0)
            quality = stabilize_scan_ranges(
                ranges=message.ranges,
                angle_min=float(message.angle_min),
                angle_increment=float(message.angle_increment),
                range_min=float(message.range_min),
                range_max=float(message.range_max),
                roll_deg=roll,
                pitch_deg=pitch,
                lidar_height_m=float(self._range_height_m or 0.0),
                passthrough_tilt_deg=config.passthrough_tilt_deg,
                compensation_tilt_deg=config.compensation_tilt_deg,
                hard_drop_tilt_deg=config.hard_drop_tilt_deg,
                max_vertical_projection_error_m=config.max_vertical_projection_error_m,
                max_rejected_beam_ratio=config.max_rejected_beam_ratio,
                min_retained_beam_ratio=config.min_retained_beam_ratio,
                max_floor_hit_risk_beam_ratio=config.max_floor_hit_risk_beam_ratio,
                floor_hit_guard_range_m=config.floor_hit_guard_range_m,
                min_downward_ray_z=config.min_downward_ray_z,
            )
            self._count += 1
            self._rejected_beam_count += quality.rejected_beam_count
            self._floor_hit_rejected_count += quality.floor_hit_rejected_count
            self._max_observed_tilt_deg = max(self._max_observed_tilt_deg, quality.tilt_deg)
            self._max_vertical_projection_error_m = max(
                self._max_vertical_projection_error_m, quality.max_vertical_projection_error_m
            )
            if quality.state == "drop":
                self._dropped += 1
                if "hard_tilt_exceeded" in quality.blockers:
                    self._hard_tilt_dropped_count += 1
                self._publish_status(self._status_payload(message, quality, time_offset_ms=time_offset_ms))
                return
            if quality.state == "blocked":
                self._blocked_count += 1
                self._publish_status(self._status_payload(message, quality, time_offset_ms=time_offset_ms))
                return
            output = copy.deepcopy(message)
            output.header.frame_id = config.scan_frame_id
            output.ranges = list(quality.ranges)
            if quality.state == "compensate":
                self._compensated += 1
                self._max_compensated_tilt_deg = max(self._max_compensated_tilt_deg, quality.tilt_deg)
            else:
                self._passthrough += 1
            self._publisher.publish(output)
            if self._debug_publisher is not None:
                self._debug_publisher.publish(output)
            self._publish_status(self._status_payload(output, quality, time_offset_ms=time_offset_ms))

        def _log_status(self) -> None:
            elapsed = max(time.monotonic() - self._started, 0.001)
            logger.info(
                "scan stabilization count={} pass={} comp={} drop={} rate_hz={:.2f} "
                "tf_ok={} attitude_seen={} height={}",
                self._count,
                self._passthrough,
                self._compensated,
                self._dropped,
                self._count / elapsed,
                self._base_scan_tf_ok,
                self._attitude is not None,
                self._range_height_m,
            )

    configure_sim_logging()
    rclpy.init(args=None)
    node = ScanStabilizationFilter()
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
