from __future__ import annotations

import copy
import json
import math
import time
from dataclasses import dataclass

from navlab.common.logging import configure_sim_logging, logger
from navlab.sim.gazebo_sensor.config import X2SensorRuntimeConfig

DEFAULT_STATUS_TOPIC = "/navlab/x2/scan_time_normalizer/status"
MAX_TIME_ANCHOR_AGE_SEC = 1.0
CARTOGRAPHER_TIME_TICK_NS = 100
MAX_RANGE_NO_RETURN_EPSILON_M = 0.05


def stamp_to_nanoseconds(stamp: object) -> int:
    return int(getattr(stamp, "sec", 0)) * 1_000_000_000 + int(getattr(stamp, "nanosec", 0))


@dataclass(frozen=True, slots=True)
class ScanStampDecision:
    stamp_ns: int
    source: str
    monotonic_adjusted: bool


def monotonic_scan_stamp_ns(
    *,
    preferred_ns: int,
    fallback_elapsed_sec: float,
    previous_ns: int | None,
    min_increment_ns: int = 1,
) -> int:
    fallback_ns = 1_000_000_000 + max(0, int(fallback_elapsed_sec * 1_000_000_000))
    candidate_ns = preferred_ns if preferred_ns > 0 else fallback_ns
    if previous_ns is None:
        return candidate_ns
    return max(candidate_ns, previous_ns + max(1, min_increment_ns))


def select_scan_stamp_ns(
    *,
    clock_ns: int,
    ideal_scan_ns: int,
    input_scan_ns: int,
    fallback_elapsed_sec: float,
    previous_ns: int | None,
    min_increment_ns: int = 1,
) -> ScanStampDecision:
    source = "wall_elapsed_fallback"
    preferred_ns = 0
    if ideal_scan_ns > 0:
        preferred_ns = ideal_scan_ns
        source = "ideal_scan_stamp"
    elif clock_ns > 0:
        preferred_ns = clock_ns
        source = "clock"
    elif input_scan_ns > 0:
        preferred_ns = input_scan_ns
        source = "input_scan_stamp"

    # Trusted ROS/Gazebo time anchors already encode elapsed sim time. Only force
    # strict monotonicity there; using scan_duration would create a faster clock.
    # Cartographer stores time in 100 ns ticks, so a 1 ns nudge is lost there.
    effective_min_increment_ns = min_increment_ns if preferred_ns <= 0 else CARTOGRAPHER_TIME_TICK_NS
    stamp_ns = monotonic_scan_stamp_ns(
        preferred_ns=preferred_ns,
        fallback_elapsed_sec=fallback_elapsed_sec,
        previous_ns=previous_ns,
        min_increment_ns=effective_min_increment_ns,
    )
    monotonic_adjusted = previous_ns is not None and stamp_ns != (preferred_ns if preferred_ns > 0 else stamp_ns)
    if previous_ns is not None and preferred_ns <= 0:
        fallback_ns = 1_000_000_000 + max(0, int(fallback_elapsed_sec * 1_000_000_000))
        monotonic_adjusted = stamp_ns != fallback_ns
    return ScanStampDecision(stamp_ns=stamp_ns, source=source, monotonic_adjusted=monotonic_adjusted)


def should_zero_scan_time_increment(stamp_source: str) -> bool:
    return stamp_source in {"ideal_scan_stamp", "clock", "input_scan_stamp"}


def normalize_no_return_ranges(
    ranges: list[float],
    *,
    range_max: float,
    epsilon_m: float = MAX_RANGE_NO_RETURN_EPSILON_M,
) -> list[float]:
    if not math.isfinite(range_max) or range_max <= 0:
        return ranges
    threshold = max(0.0, range_max - max(0.0, epsilon_m))
    return [float("inf") if math.isfinite(float(value)) and float(value) >= threshold else value for value in ranges]


def build_status_payload(
    *,
    input_topic: str,
    ideal_scan_topic: str,
    output_topic: str,
    status_topic: str,
    count: int,
    latest_clock_ns: int,
    latest_ideal_scan_ns: int,
    latest_input_scan_ns: int,
    latest_output_scan_ns: int,
    latest_stamp_source: str,
    source_counts: dict[str, int],
    monotonic_adjust_count: int,
    time_increment_zeroed_count: int,
    latest_clock_age_ms: float | None = None,
    latest_ideal_scan_age_ms: float | None = None,
) -> dict[str, object]:
    return {
        "state": "publishing" if count > 0 else "waiting_for_vendor_scan",
        "input_topic": input_topic,
        "ideal_scan_topic": ideal_scan_topic,
        "output_topic": output_topic,
        "status_topic": status_topic,
        "count": count,
        "clock_seen": latest_clock_ns > 0,
        "ideal_scan_seen": latest_ideal_scan_ns > 0,
        "latest_clock_stamp_sec": latest_clock_ns / 1_000_000_000 if latest_clock_ns > 0 else None,
        "latest_clock_age_ms": latest_clock_age_ms,
        "latest_ideal_scan_stamp_sec": latest_ideal_scan_ns / 1_000_000_000 if latest_ideal_scan_ns > 0 else None,
        "latest_ideal_scan_age_ms": latest_ideal_scan_age_ms,
        "latest_input_scan_stamp_sec": latest_input_scan_ns / 1_000_000_000 if latest_input_scan_ns > 0 else None,
        "latest_output_scan_stamp_sec": latest_output_scan_ns / 1_000_000_000 if latest_output_scan_ns > 0 else None,
        "latest_stamp_source": latest_stamp_source,
        "stamp_source_counts": dict(sorted(source_counts.items())),
        "wall_fallback_count": source_counts.get("wall_elapsed_fallback", 0),
        "monotonic_adjust_count": monotonic_adjust_count,
        "time_increment_zeroed_count": time_increment_zeroed_count,
    }


def run() -> int:
    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
        from rclpy.parameter import Parameter
        from rclpy.qos import qos_profile_sensor_data
        from rosgraph_msgs.msg import Clock
        from sensor_msgs.msg import LaserScan
        from std_msgs.msg import String
    except ModuleNotFoundError as exc:
        raise SystemExit("scan time normalizer requires ROS2 Python packages.") from exc

    config = X2SensorRuntimeConfig.load()
    if config.vendor_scan_topic == config.scan_topic:
        logger.error("vendor_scan_topic and scan_topic must be different: {}", config.scan_topic)
        return 22

    class ScanTimeNormalizerNode(Node):
        def __init__(self) -> None:
            super().__init__("navlab_x2_scan_time_normalizer")
            self.set_parameters([Parameter("use_sim_time", Parameter.Type.BOOL, True)])
            self._latest_clock: Clock | None = None
            self._latest_clock_wall_sec: float | None = None
            self._latest_ideal_scan_stamp_ns = 0
            self._latest_ideal_scan_wall_sec: float | None = None
            self._latest_input_scan_stamp_ns = 0
            self._latest_output_scan_stamp_ns = 0
            self._latest_stamp_source = "none"
            self._source_counts: dict[str, int] = {}
            self._monotonic_adjust_count = 0
            self._time_increment_zeroed_count = 0
            self._last_stamp_ns: int | None = None
            self._count = 0
            self._started_at = time.monotonic()
            self._publisher = self.create_publisher(LaserScan, config.scan_topic, qos_profile_sensor_data)
            self._status_publisher = self.create_publisher(String, DEFAULT_STATUS_TOPIC, 10)
            self.create_subscription(Clock, "/clock", self._handle_clock, 10)
            self.create_subscription(
                LaserScan,
                config.scan_ideal_topic,
                self._handle_ideal_scan,
                qos_profile_sensor_data,
            )
            self.create_subscription(LaserScan, config.vendor_scan_topic, self._handle_scan, qos_profile_sensor_data)
            self.create_timer(2.0, self._log_status)
            self.create_timer(0.5, self._publish_status)
            logger.info(
                "normalizing X2 scan timestamps input={} ideal_input={} output={} status={}",
                config.vendor_scan_topic,
                config.scan_ideal_topic,
                config.scan_topic,
                DEFAULT_STATUS_TOPIC,
            )

        def _handle_clock(self, message: Clock) -> None:
            self._latest_clock = message
            self._latest_clock_wall_sec = time.monotonic()

        def _handle_ideal_scan(self, message: LaserScan) -> None:
            self._latest_ideal_scan_stamp_ns = stamp_to_nanoseconds(message.header.stamp)
            self._latest_ideal_scan_wall_sec = time.monotonic()

        def _handle_scan(self, message: LaserScan) -> None:
            output = copy.deepcopy(message)
            now = time.monotonic()
            clock_fresh = (
                self._latest_clock is not None
                and self._latest_clock_wall_sec is not None
                and now - self._latest_clock_wall_sec <= MAX_TIME_ANCHOR_AGE_SEC
            )
            ideal_fresh = (
                self._latest_ideal_scan_stamp_ns > 0
                and self._latest_ideal_scan_wall_sec is not None
                and now - self._latest_ideal_scan_wall_sec <= MAX_TIME_ANCHOR_AGE_SEC
            )
            clock_ns = stamp_to_nanoseconds(self._latest_clock.clock) if clock_fresh else 0
            ideal_scan_ns = self._latest_ideal_scan_stamp_ns if ideal_fresh else 0
            self._latest_input_scan_stamp_ns = stamp_to_nanoseconds(message.header.stamp)
            scan_duration_sec = max(
                float(message.scan_time),
                float(message.time_increment) * len(message.ranges),
                0.0,
            )
            scan_duration_ns = int(scan_duration_sec * 1_000_000_000)
            decision = select_scan_stamp_ns(
                clock_ns=clock_ns,
                ideal_scan_ns=ideal_scan_ns,
                input_scan_ns=self._latest_input_scan_stamp_ns,
                fallback_elapsed_sec=now - self._started_at,
                previous_ns=self._last_stamp_ns,
                min_increment_ns=scan_duration_ns,
            )
            stamp_ns = decision.stamp_ns
            output.header.stamp.sec = int(stamp_ns // 1_000_000_000)
            output.header.stamp.nanosec = int(stamp_ns % 1_000_000_000)
            output.ranges = normalize_no_return_ranges(list(output.ranges), range_max=float(output.range_max))
            if should_zero_scan_time_increment(decision.source):
                output.time_increment = 0.0
                self._time_increment_zeroed_count += 1
            self._last_stamp_ns = stamp_ns
            self._latest_output_scan_stamp_ns = stamp_ns
            self._latest_stamp_source = decision.source
            self._source_counts[decision.source] = self._source_counts.get(decision.source, 0) + 1
            if decision.monotonic_adjusted:
                self._monotonic_adjust_count += 1
            self._publisher.publish(output)
            self._count += 1
            self._publish_status()

        def _log_status(self) -> None:
            elapsed = max(0.001, time.monotonic() - self._started_at)
            payload = self._status_payload()
            logger.info(
                "scan time normalizer count={} rate_hz={:.2f} clock_seen={} "
                "ideal_scan_seen={} stamp_source={} wall_fallback_count={} "
                "monotonic_adjust_count={} time_increment_zeroed_count={}",
                self._count,
                self._count / elapsed,
                payload["clock_seen"],
                payload["ideal_scan_seen"],
                payload["latest_stamp_source"],
                payload["wall_fallback_count"],
                payload["monotonic_adjust_count"],
                payload["time_increment_zeroed_count"],
            )

        def _status_payload(self) -> dict[str, object]:
            clock_ns = stamp_to_nanoseconds(self._latest_clock.clock) if self._latest_clock is not None else 0
            now = time.monotonic()
            clock_age_ms = (
                (now - self._latest_clock_wall_sec) * 1000.0 if self._latest_clock_wall_sec is not None else None
            )
            ideal_age_ms = (
                (now - self._latest_ideal_scan_wall_sec) * 1000.0
                if self._latest_ideal_scan_wall_sec is not None
                else None
            )
            return build_status_payload(
                input_topic=config.vendor_scan_topic,
                ideal_scan_topic=config.scan_ideal_topic,
                output_topic=config.scan_topic,
                status_topic=DEFAULT_STATUS_TOPIC,
                count=self._count,
                latest_clock_ns=clock_ns,
                latest_ideal_scan_ns=self._latest_ideal_scan_stamp_ns,
                latest_input_scan_ns=self._latest_input_scan_stamp_ns,
                latest_output_scan_ns=self._latest_output_scan_stamp_ns,
                latest_stamp_source=self._latest_stamp_source,
                source_counts=self._source_counts,
                monotonic_adjust_count=self._monotonic_adjust_count,
                time_increment_zeroed_count=self._time_increment_zeroed_count,
                latest_clock_age_ms=clock_age_ms,
                latest_ideal_scan_age_ms=ideal_age_ms,
            )

        def _publish_status(self) -> None:
            message = String()
            message.data = json.dumps(self._status_payload(), sort_keys=True)
            self._status_publisher.publish(message)

    configure_sim_logging()
    rclpy.init(args=None)
    node = ScanTimeNormalizerNode()
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
