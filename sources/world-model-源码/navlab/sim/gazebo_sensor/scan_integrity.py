from __future__ import annotations

import copy
import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from navlab.common.logging import configure_sim_logging, logger
from navlab.sim.gazebo_sensor.config import ScanIntegrityRuntimeConfig


@dataclass(frozen=True, slots=True)
class TiltQuality:
    state: str
    tilt_deg: float
    clipped_beam_ratio: float
    floor_hit_risk_beam_ratio: float
    unsafe_indices: tuple[int, ...]
    blockers: tuple[str, ...]


def angle_delta_deg(end: float, start: float) -> float:
    return math.degrees(math.atan2(math.sin(math.radians(end - start)), math.cos(math.radians(end - start))))


def quaternion_to_rpy_deg(x: float, y: float, z: float, w: float) -> tuple[float, float, float]:
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 1e-9:
        raise ValueError("invalid zero quaternion")
    x /= norm
    y /= norm
    z /= norm
    w /= norm
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)
    sinp = 2.0 * (w * y - z * x)
    pitch = math.copysign(math.pi / 2.0, sinp) if abs(sinp) >= 1.0 else math.asin(sinp)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def evaluate_scan_quality(
    *,
    ranges: Sequence[float],
    angle_min: float,
    angle_increment: float,
    range_max: float,
    roll_deg: float,
    pitch_deg: float,
    lidar_height_m: float,
    soft_tilt_deg: float,
    hard_tilt_deg: float,
    max_clipped_beam_ratio: float,
    floor_hit_guard_range_m: float,
    min_downward_ray_z: float,
) -> TiltQuality:
    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    tilt_deg = math.degrees(math.hypot(roll, pitch))
    blockers: list[str] = []
    if lidar_height_m <= 0.0:
        blockers.append("missing_lidar_height")
    if tilt_deg > hard_tilt_deg:
        return TiltQuality("drop", tilt_deg, 0.0, 0.0, (), tuple([*blockers, "hard_tilt_exceeded"]))

    unsafe: list[int] = []
    finite_count = 0
    for index, raw_range in enumerate(ranges):
        value = float(raw_range)
        if not math.isfinite(value) or value <= 0.0:
            continue
        finite_count += 1
        angle = angle_min + float(index) * angle_increment
        ray_z = -math.sin(pitch) * math.cos(angle) + math.cos(pitch) * math.sin(roll) * math.sin(angle)
        if ray_z >= -abs(min_downward_ray_z):
            continue
        floor_intersection = lidar_height_m / max(abs(ray_z), 1e-6)
        guard_range = min(
            float(floor_hit_guard_range_m), float(range_max) if range_max > 0 else floor_hit_guard_range_m
        )
        if floor_intersection <= guard_range and floor_intersection <= value:
            unsafe.append(index)

    denom = max(finite_count, 1)
    clipped_ratio = len(unsafe) / denom
    state = "accept"
    if clipped_ratio > max_clipped_beam_ratio:
        state = "drop"
        blockers.append("clipped_beam_ratio_too_high")
    elif unsafe:
        state = "clip"
    elif tilt_deg > soft_tilt_deg:
        state = "warn"
    return TiltQuality(state, tilt_deg, clipped_ratio, clipped_ratio, tuple(unsafe), tuple(blockers))


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
        raise SystemExit("scan integrity filter requires ROS2 Python packages.") from exc

    config = ScanIntegrityRuntimeConfig.load()
    if not config.enabled:
        logger.error("scan integrity filter was launched while disabled")
        return 22
    if config.input_scan_topic == config.output_scan_topic:
        logger.error("input_scan_topic and output_scan_topic must differ: {}", config.output_scan_topic)
        return 22
    if config.attitude_source_topic.startswith("/gazebo") or config.attitude_source_topic == "/odometry":
        logger.error("attitude source must not be Gazebo truth: {}", config.attitude_source_topic)
        return 22
    if config.attitude_source_type not in {"imu", "pose"}:
        logger.error("unsupported attitude_source_type={}", config.attitude_source_type)
        return 22

    class ScanIntegrityFilter(Node):
        def __init__(self) -> None:
            super().__init__("navlab_scan_integrity_filter")
            self.set_parameters([Parameter("use_sim_time", Parameter.Type.BOOL, True)])
            self._publisher = self.create_publisher(LaserScan, config.output_scan_topic, qos_profile_sensor_data)
            self._status_publisher = self.create_publisher(String, config.status_topic, 10)
            self._event_publisher = self.create_publisher(String, config.events_topic, 10)
            self._attitude: dict[str, Any] | None = None
            self._range_height_m: float | None = None
            self._base_scan_tf_ok = False
            self._count = 0
            self._accepted = 0
            self._warned = 0
            self._clipped = 0
            self._dropped = 0
            self._hard_tilt = 0
            self._max_scan_tilt_deg = 0.0
            self._started = time.monotonic()
            self._attitude_times: list[float] = []
            self._last_attitude_sample: dict[str, float] | None = None
            self._attitude_sample_count = 0
            self._roll_sq_sum = 0.0
            self._pitch_sq_sum = 0.0
            self._max_abs_roll_deg = 0.0
            self._max_abs_pitch_deg = 0.0
            self._latest_yaw_rate_dps = 0.0
            self._max_attitude_rate_dps = 0.0
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
            logger.info(
                "scan integrity filter input={} output={} attitude={} type={}",
                config.input_scan_topic,
                config.output_scan_topic,
                config.attitude_source_topic,
                config.attitude_source_type,
            )

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
            if self._last_attitude_sample is not None:
                dt = max(stamp_sec - float(self._last_attitude_sample["stamp_sec"]), 0.0)
                if dt > 1e-6:
                    roll_rate = (roll_deg - float(self._last_attitude_sample["roll_deg"])) / dt
                    pitch_rate = (pitch_deg - float(self._last_attitude_sample["pitch_deg"])) / dt
                    yaw_rate = angle_delta_deg(yaw_deg, float(self._last_attitude_sample["yaw_deg"])) / dt
                    self._latest_yaw_rate_dps = yaw_rate
                    attitude_rate = math.sqrt(roll_rate * roll_rate + pitch_rate * pitch_rate + yaw_rate * yaw_rate)
                    self._max_attitude_rate_dps = max(self._max_attitude_rate_dps, attitude_rate)
            self._last_attitude_sample = {
                "roll_deg": roll_deg,
                "pitch_deg": pitch_deg,
                "yaw_deg": yaw_deg,
                "stamp_sec": stamp_sec,
            }
            self._attitude_sample_count += 1
            self._roll_sq_sum += roll_deg * roll_deg
            self._pitch_sq_sum += pitch_deg * pitch_deg
            self._max_abs_roll_deg = max(self._max_abs_roll_deg, abs(roll_deg))
            self._max_abs_pitch_deg = max(self._max_abs_pitch_deg, abs(pitch_deg))
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

        def _flight_attitude_metrics(self) -> dict[str, float | int]:
            count = max(self._attitude_sample_count, 1)
            return {
                "sample_count": self._attitude_sample_count,
                "max_abs_roll_deg": self._max_abs_roll_deg,
                "max_abs_pitch_deg": self._max_abs_pitch_deg,
                "rms_roll_deg": math.sqrt(self._roll_sq_sum / count),
                "rms_pitch_deg": math.sqrt(self._pitch_sq_sum / count),
                "yaw_rate_dps": self._latest_yaw_rate_dps,
                "max_attitude_rate_dps": self._max_attitude_rate_dps,
            }

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
            if payload.get("state") in {"warn", "clip", "drop", "blocked"}:
                self._event_publisher.publish(self._json_msg(payload))

        def _blocked(self, message: LaserScan, blockers: list[str]) -> None:
            self._count += 1
            self._dropped += 1
            payload = self._status_payload(message, "blocked", blockers=blockers)
            self._publish_status(payload)

        def _status_payload(
            self,
            message: LaserScan,
            state: str,
            *,
            quality: TiltQuality | None = None,
            blockers: Sequence[str] = (),
            time_offset_ms: float | None = None,
        ) -> dict[str, Any]:
            attitude = self._attitude or {}
            roll = float(attitude.get("roll_deg") or 0.0) + (
                self._fault["roll_bias_deg"] if self._fault["enabled"] else 0.0
            )
            pitch = float(attitude.get("pitch_deg") or 0.0) + (
                self._fault["pitch_bias_deg"] if self._fault["enabled"] else 0.0
            )
            tilt = quality.tilt_deg if quality else math.hypot(roll, pitch)
            dropped_ratio = self._dropped / max(self._count, 1)
            all_blockers = list(blockers)
            if dropped_ratio > config.max_dropped_scan_ratio:
                all_blockers.append("dropped_scan_ratio_too_high")
            return {
                "ok": not all_blockers,
                "state": state,
                "scan_source": "gazebo_ideal",
                "attitude_source": config.attitude_source_topic,
                "attitude_source_type": config.attitude_source_type,
                "attitude_source_is_truth": False,
                "input_scan_topic": config.input_scan_topic,
                "output_scan_topic": config.output_scan_topic,
                "roll_deg": roll,
                "pitch_deg": pitch,
                "tilt_deg": tilt,
                "scan_attitude_time_offset_ms": time_offset_ms,
                "attitude_source_age_ms": self._attitude_source_age_ms(),
                "input_scan_stamp": self._stamp_sec(message.header.stamp),
                "attitude_stamp": attitude.get("stamp_sec"),
                "base_scan_static_tf_ok": self._base_scan_tf_ok,
                "lidar_height_m": self._range_height_m,
                "accepted_scan_count": self._accepted,
                "warn_scan_count": self._warned,
                "clipped_scan_count": self._clipped,
                "dropped_scan_count": self._dropped,
                "dropped_scan_ratio": dropped_ratio,
                "clipped_beam_ratio": quality.clipped_beam_ratio if quality else 0.0,
                "floor_hit_risk_beam_ratio": quality.floor_hit_risk_beam_ratio if quality else 0.0,
                "attitude_rate_hz": self._attitude_rate(),
                "fault_injection": self._fault,
                "hard_tilt_count": self._hard_tilt,
                "max_scan_tilt_deg": self._max_scan_tilt_deg,
                "tilt_filtered_scan_count": self._dropped + self._clipped,
                "tilt_warning_count": self._warned,
                "flight_attitude_metrics": self._flight_attitude_metrics(),
                "blockers": all_blockers,
            }

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
            time_offset_ms = abs(scan_stamp - attitude_stamp) * 1000.0 if scan_stamp and attitude_stamp else 0.0
            if time_offset_ms > config.max_scan_attitude_time_offset_ms:
                self._blocked(message, ["scan_attitude_time_offset_too_high"])
                return

            roll = float(attitude["roll_deg"]) + (self._fault["roll_bias_deg"] if self._fault["enabled"] else 0.0)
            pitch = float(attitude["pitch_deg"]) + (self._fault["pitch_bias_deg"] if self._fault["enabled"] else 0.0)
            quality = evaluate_scan_quality(
                ranges=message.ranges,
                angle_min=float(message.angle_min),
                angle_increment=float(message.angle_increment),
                range_max=float(message.range_max),
                roll_deg=roll,
                pitch_deg=pitch,
                lidar_height_m=float(self._range_height_m or 0.0),
                soft_tilt_deg=config.soft_tilt_deg,
                hard_tilt_deg=config.hard_tilt_deg,
                max_clipped_beam_ratio=config.max_clipped_beam_ratio,
                floor_hit_guard_range_m=config.floor_hit_guard_range_m,
                min_downward_ray_z=config.min_downward_ray_z,
            )
            self._count += 1
            self._max_scan_tilt_deg = max(self._max_scan_tilt_deg, quality.tilt_deg)
            if "hard_tilt_exceeded" in quality.blockers:
                self._hard_tilt += 1
            if quality.state == "drop":
                self._dropped += 1
                self._publish_status(
                    self._status_payload(
                        message, "drop", quality=quality, blockers=quality.blockers, time_offset_ms=time_offset_ms
                    )
                )
                return

            output = copy.deepcopy(message)
            output.header.frame_id = config.scan_frame_id
            if quality.unsafe_indices:
                ranges = list(output.ranges)
                replacement = float(output.range_max) if math.isfinite(float(output.range_max)) else 0.0
                for index in quality.unsafe_indices:
                    ranges[index] = replacement
                output.ranges = ranges
                self._clipped += 1
            elif quality.state == "warn":
                self._warned += 1
            self._accepted += 1
            self._publisher.publish(output)
            self._publish_status(
                self._status_payload(output, quality.state, quality=quality, time_offset_ms=time_offset_ms)
            )

        def _log_status(self) -> None:
            elapsed = max(time.monotonic() - self._started, 0.001)
            logger.info(
                "scan integrity count={} accepted={} dropped={} rate_hz={:.2f} tf_ok={} attitude_seen={} height={}",
                self._count,
                self._accepted,
                self._dropped,
                self._count / elapsed,
                self._base_scan_tf_ok,
                self._attitude is not None,
                self._range_height_m,
            )

    configure_sim_logging()
    rclpy.init(args=None)
    node = ScanIntegrityFilter()
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
