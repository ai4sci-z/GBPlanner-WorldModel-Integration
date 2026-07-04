from __future__ import annotations

import argparse
import copy
import json
import math
from collections import deque
from dataclasses import dataclass
from typing import Any

DEFAULT_SLAM_ODOM_TOPIC = "/slam/odom"
DEFAULT_SCAN_REFERENCE_STATUS_TOPIC = "/navlab/scan_reference_drift/status"
DEFAULT_HOVER_STATUS_TOPIC = "/navlab/hover/status"
DEFAULT_OUTPUT_ODOM_TOPIC = "/slam/odom_corrected"
DEFAULT_STATUS_TOPIC = "/navlab/scan_reference_correction/status"
CORRECTION_PHASES = frozenset({"hover_settle", "hover_hold"})


@dataclass(frozen=True, slots=True)
class CorrectionDecision:
    active: bool
    correction_applied: bool
    measurement_delta_x_m: float
    measurement_delta_y_m: float
    measurement_delta_magnitude_m: float
    source_intent_x_m: float
    source_intent_y_m: float
    source_intent_magnitude_m: float
    axes: tuple[str, ...]
    blocked_axes: tuple[str, ...]
    axis_blockers: dict[str, tuple[str, ...]]
    runtime_consistency_ok: bool
    phase4b_consistency_ok: bool
    phase4b_consistency_source: str
    blockers: tuple[str, ...]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply fail-closed scan-reference correction to SLAM odom.")
    parser.add_argument("--slam-odom-topic", default=DEFAULT_SLAM_ODOM_TOPIC)
    parser.add_argument("--scan-reference-status-topic", default=DEFAULT_SCAN_REFERENCE_STATUS_TOPIC)
    parser.add_argument("--hover-status-topic", default=DEFAULT_HOVER_STATUS_TOPIC)
    parser.add_argument("--output-odom-topic", default=DEFAULT_OUTPUT_ODOM_TOPIC)
    parser.add_argument("--status-topic", default=DEFAULT_STATUS_TOPIC)
    parser.add_argument("--expected-frame-id", default="map")
    parser.add_argument("--expected-child-frame-id", default="base_link")
    parser.add_argument("--max-status-age-ms", type=float, default=400.0)
    parser.add_argument("--max-correction-m", type=float, default=0.25)
    parser.add_argument("--max-measurement-delta-m", type=float, default=1.25)
    parser.add_argument("--max-correction-step-m", type=float, default=0.03)
    parser.add_argument("--min-runtime-consistency-samples", type=int, default=5)
    parser.add_argument("--min-direction-cosine", type=float, default=0.70)
    parser.add_argument("--max-axis-sign-flips", type=int, default=0)
    parser.add_argument("--max-saturation-ratio", type=float, default=0.95)
    parser.add_argument("--history-samples", type=int, default=8)
    parser.add_argument("--enable-correction", action="store_true", default=True)
    parser.add_argument("--disable-correction", dest="enable_correction", action="store_false")
    return parser


def _parse_json(data: str) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _phase_from_status(data: str) -> str:
    return str(_parse_json(data).get("phase") or "")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item))


def _clamp_vector(x: float, y: float, max_magnitude: float) -> tuple[float, float]:
    magnitude = math.hypot(x, y)
    limit = max(0.0, max_magnitude)
    if limit <= 0.0 or magnitude <= limit or magnitude <= 1e-9:
        return x, y
    scale = limit / magnitude
    return x * scale, y * scale


def _limit_step(target_x: float, target_y: float, last_x: float, last_y: float, max_step: float) -> tuple[float, float]:
    dx = target_x - last_x
    dy = target_y - last_y
    return_x, return_y = _clamp_vector(dx, dy, max_step)
    return last_x + return_x, last_y + return_y


def _deadband_sign(value: float, deadband: float = 0.02) -> int:
    if value > deadband:
        return 1
    if value < -deadband:
        return -1
    return 0


def _sign_flips(values: list[int]) -> int:
    return sum(1 for left, right in zip(values, values[1:]) if left != right)


def _cosine(left: tuple[float, float], right: tuple[float, float]) -> float:
    left_norm = math.hypot(*left)
    right_norm = math.hypot(*right)
    if left_norm <= 1e-9 or right_norm <= 1e-9:
        return 0.0
    return ((left[0] * right[0]) + (left[1] * right[1])) / (left_norm * right_norm)


def _min_direction_cosine(vectors: list[tuple[float, float]]) -> float | None:
    if len(vectors) < 2:
        return None
    values = [_cosine(left, right) for left, right in zip(vectors, vectors[1:])]
    return min(values) if values else None


def _unique(items: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _empty_decision(
    *,
    source_intent_x_m: float = 0.0,
    source_intent_y_m: float = 0.0,
    source_intent_magnitude_m: float = 0.0,
    blocked_axes: tuple[str, ...] = (),
    axis_blockers: dict[str, tuple[str, ...]] | None = None,
    runtime_consistency_ok: bool = False,
    phase4b_consistency_ok: bool = False,
    phase4b_consistency_source: str = "scan_reference_status",
    blockers: tuple[str, ...] = (),
) -> CorrectionDecision:
    return CorrectionDecision(
        active=False,
        correction_applied=False,
        measurement_delta_x_m=0.0,
        measurement_delta_y_m=0.0,
        measurement_delta_magnitude_m=0.0,
        source_intent_x_m=source_intent_x_m,
        source_intent_y_m=source_intent_y_m,
        source_intent_magnitude_m=source_intent_magnitude_m,
        axes=(),
        blocked_axes=blocked_axes,
        axis_blockers=axis_blockers or {},
        runtime_consistency_ok=runtime_consistency_ok,
        phase4b_consistency_ok=phase4b_consistency_ok,
        phase4b_consistency_source=phase4b_consistency_source,
        blockers=_unique(blockers),
    )


def _runtime_consistency(
    history: list[tuple[float, float, float]],
    *,
    requested_axes: tuple[str, ...],
    min_samples: int,
    min_direction_cosine: float,
    max_axis_sign_flips: int,
    max_saturation_ratio: float,
    check_saturation: bool = True,
) -> tuple[bool, tuple[str, ...], tuple[str, ...], dict[str, tuple[str, ...]]]:
    blockers: list[str] = []
    axis_blockers: dict[str, list[str]] = {axis: [] for axis in requested_axes}
    if len(history) < max(1, min_samples):
        blockers.append("scan_reference_runtime_consistency_window_short")
        return False, (), requested_axes, {axis: tuple(blockers) for axis in requested_axes}
    x_flips = _sign_flips([sign for sign in (_deadband_sign(x) for x, _, _ in history) if sign != 0])
    y_flips = _sign_flips([sign for sign in (_deadband_sign(y) for _, y, _ in history) if sign != 0])
    if "x" in axis_blockers and x_flips > max_axis_sign_flips:
        axis_blockers["x"].append("scan_reference_runtime_x_sign_flips")
    if "y" in axis_blockers and y_flips > max_axis_sign_flips:
        axis_blockers["y"].append("scan_reference_runtime_y_sign_flips")
    candidate_axes = tuple(axis for axis in requested_axes if not axis_blockers.get(axis))
    if len(candidate_axes) >= 2:
        vectors = [
            (
                x if "x" in candidate_axes else 0.0,
                y if "y" in candidate_axes else 0.0,
            )
            for x, y, _ in history
        ]
        direction_cosine = _min_direction_cosine(vectors)
        if direction_cosine is not None and direction_cosine < min_direction_cosine:
            blockers.append("scan_reference_runtime_direction_unstable")
    if check_saturation:
        saturated = sum(1 for x, y, limit in history if limit > 0.0 and math.hypot(x, y) >= limit * 0.98)
        saturation_ratio = saturated / float(len(history))
        if saturation_ratio > max_saturation_ratio:
            blockers.append("scan_reference_runtime_saturation_ratio_high")
    if blockers:
        return (
            False,
            (),
            requested_axes,
            {axis: _unique(tuple(axis_blockers.get(axis, ())) + tuple(blockers)) for axis in requested_axes},
        )
    allowed_axes = candidate_axes
    blocked_axes = tuple(axis for axis in requested_axes if axis not in allowed_axes)
    return (
        bool(allowed_axes),
        allowed_axes,
        blocked_axes,
        {axis: _unique(tuple(values)) for axis, values in axis_blockers.items() if values},
    )


def _measurement_decision(
    status: dict[str, Any],
    *,
    hover_phase: str,
    status_age_ms: float,
    max_status_age_ms: float,
    runtime_history: list[tuple[float, float, float]],
    min_runtime_consistency_samples: int,
    min_direction_cosine: float,
    max_axis_sign_flips: int,
    max_saturation_ratio: float,
    max_correction_m: float,
    max_measurement_delta_m: float,
    correction_enabled: bool,
) -> CorrectionDecision | None:
    """Use scan-reference pose as a measured odometry delta when intent capping blocks.

    This path is still fail-closed: it requires the scan-only estimator quality
    and stability gates. It deliberately does not use Gazebo truth, known maps,
    fixed priors, or a larger correction cap.
    """
    blockers: list[str] = []
    if not correction_enabled:
        blockers.append("scan_reference_runtime_correction_disabled")
    if hover_phase not in CORRECTION_PHASES:
        blockers.append("scan_reference_runtime_not_hover_hold")
    if status_age_ms < 0.0 or status_age_ms > max_status_age_ms:
        blockers.append("scan_reference_status_stale")
    if not _bool(status.get("quality_good")):
        blockers.append("scan_reference_runtime_quality_not_good")

    eligibility = status.get("correction_eligibility") if isinstance(status.get("correction_eligibility"), dict) else {}
    if not _bool(eligibility.get("correction_allowed")):
        blockers.append("scan_reference_runtime_eligibility_not_allowed")
    axes = _string_list(eligibility.get("allowed_axes"))
    if not axes:
        blockers.append("scan_reference_runtime_axes_empty")

    source_x = _float(status.get("x_m")) if "x" in axes else 0.0
    source_y = _float(status.get("y_m")) if "y" in axes else 0.0
    if math.hypot(source_x, source_y) <= 1e-9:
        blockers.append("scan_reference_runtime_measurement_zero")

    runtime_consistency_ok, runtime_allowed_axes, runtime_blocked_axes, axis_blockers = _runtime_consistency(
        runtime_history,
        requested_axes=axes,
        min_samples=min_runtime_consistency_samples,
        min_direction_cosine=min_direction_cosine,
        max_axis_sign_flips=max_axis_sign_flips,
        max_saturation_ratio=max_saturation_ratio,
        check_saturation=False,
    )
    axes = tuple(axis for axis in axes if axis in runtime_allowed_axes)
    if not axes:
        for values in axis_blockers.values():
            blockers.extend(values)
        blockers.append("scan_reference_runtime_no_stable_axis")
    if "x" not in axes:
        source_x = 0.0
    if "y" not in axes:
        source_y = 0.0
    source_x, source_y = _clamp_vector(source_x, source_y, max_measurement_delta_m)
    source_magnitude = math.hypot(source_x, source_y)
    if source_magnitude <= 1e-9:
        blockers.append("scan_reference_runtime_measurement_zero")

    if blockers:
        return None

    return CorrectionDecision(
        active=True,
        correction_applied=True,
        measurement_delta_x_m=source_x,
        measurement_delta_y_m=source_y,
        measurement_delta_magnitude_m=source_magnitude,
        source_intent_x_m=-source_x,
        source_intent_y_m=-source_y,
        source_intent_magnitude_m=source_magnitude,
        axes=axes,
        blocked_axes=runtime_blocked_axes,
        axis_blockers=axis_blockers,
        runtime_consistency_ok=runtime_consistency_ok,
        phase4b_consistency_ok=True,
        phase4b_consistency_source="scan_reference_runtime_measurement_window",
        blockers=(),
    )


def decide_correction(
    status: dict[str, Any],
    *,
    hover_phase: str,
    status_age_ms: float,
    max_status_age_ms: float,
    max_correction_m: float,
    runtime_history: list[tuple[float, float, float]],
    min_runtime_consistency_samples: int,
    min_direction_cosine: float,
    max_axis_sign_flips: int,
    max_saturation_ratio: float,
    correction_enabled: bool = True,
    max_measurement_delta_m: float | None = None,
) -> CorrectionDecision:
    if max_measurement_delta_m is None:
        max_measurement_delta_m = max_correction_m
    blockers: list[str] = []
    if not correction_enabled:
        blockers.append("scan_reference_runtime_correction_disabled")
    if hover_phase not in CORRECTION_PHASES:
        blockers.append("scan_reference_runtime_not_hover_hold")
    if status_age_ms < 0.0 or status_age_ms > max_status_age_ms:
        blockers.append("scan_reference_status_stale")
    eligibility = status.get("correction_eligibility") if isinstance(status.get("correction_eligibility"), dict) else {}
    intent = status.get("correction_intent") if isinstance(status.get("correction_intent"), dict) else {}
    if not _bool(eligibility.get("correction_allowed")):
        blockers.append("scan_reference_runtime_eligibility_not_allowed")
    if not _bool(intent.get("active")):
        blockers.append("scan_reference_runtime_intent_not_active")
    if _string_list(intent.get("blockers")):
        blockers.append("scan_reference_runtime_intent_has_blockers")
    consecutive = _float(intent.get("consecutive_allowed_samples"))
    required = max(1.0, _float(intent.get("required_consecutive_allowed_samples"), 1.0))
    if consecutive < required:
        blockers.append("scan_reference_runtime_consecutive_window_short")
    axes = _string_list(intent.get("axes"))
    if not axes:
        blockers.append("scan_reference_runtime_axes_empty")
    eligibility_axes = _string_list(eligibility.get("allowed_axes"))
    if eligibility_axes:
        axes = tuple(axis for axis in axes if axis in eligibility_axes)
    if not axes:
        blockers.append("scan_reference_runtime_axes_not_eligible")
    requested_axes = axes

    phase4b_consistency_ok = _bool(intent.get("phase4b_consistency_ok")) or _bool(status.get("phase4b_consistency_ok"))
    phase4b_consistency_source = str(
        intent.get("phase4b_consistency_source")
        or status.get("phase4b_consistency_source")
        or "missing_runtime_phase4b_consistency"
    )
    if not phase4b_consistency_ok:
        blockers.append("scan_reference_runtime_phase4b_consistency_missing")

    intent_x = _float(intent.get("correction_x_m")) if "x" in axes else 0.0
    intent_y = _float(intent.get("correction_y_m")) if "y" in axes else 0.0
    intent_x, intent_y = _clamp_vector(intent_x, intent_y, max_correction_m)
    intent_magnitude = math.hypot(intent_x, intent_y)
    if intent_magnitude <= 1e-9:
        blockers.append("scan_reference_runtime_intent_zero")

    runtime_consistency_ok, runtime_allowed_axes, runtime_blocked_axes, axis_blockers = _runtime_consistency(
        runtime_history,
        requested_axes=axes,
        min_samples=min_runtime_consistency_samples,
        min_direction_cosine=min_direction_cosine,
        max_axis_sign_flips=max_axis_sign_flips,
        max_saturation_ratio=max_saturation_ratio,
    )
    axes = tuple(axis for axis in axes if axis in runtime_allowed_axes)
    if not axes:
        for values in axis_blockers.values():
            blockers.extend(values)
        blockers.append("scan_reference_runtime_no_stable_axis")
    if "x" not in axes:
        intent_x = 0.0
    if "y" not in axes:
        intent_y = 0.0
    intent_x, intent_y = _clamp_vector(intent_x, intent_y, max_correction_m)
    intent_magnitude = math.hypot(intent_x, intent_y)

    active = len(blockers) == 0
    if not active:
        measurement_decision = _measurement_decision(
            status,
            hover_phase=hover_phase,
            status_age_ms=status_age_ms,
            max_status_age_ms=max_status_age_ms,
            runtime_history=runtime_history,
            min_runtime_consistency_samples=min_runtime_consistency_samples,
            min_direction_cosine=min_direction_cosine,
            max_axis_sign_flips=max_axis_sign_flips,
            max_saturation_ratio=max_saturation_ratio,
            max_correction_m=max_correction_m,
            max_measurement_delta_m=max_measurement_delta_m,
            correction_enabled=correction_enabled,
        )
        if measurement_decision is not None:
            return measurement_decision
        return _empty_decision(
            source_intent_x_m=intent_x,
            source_intent_y_m=intent_y,
            source_intent_magnitude_m=intent_magnitude,
            blocked_axes=_unique(runtime_blocked_axes or requested_axes),
            axis_blockers=axis_blockers,
            runtime_consistency_ok=runtime_consistency_ok,
            phase4b_consistency_ok=phase4b_consistency_ok,
            phase4b_consistency_source=phase4b_consistency_source,
            blockers=tuple(blockers),
        )

    # The intent is the motion needed to counter drift. ExternalNav odometry must
    # instead report the observed drift, so the measurement delta has opposite sign.
    measurement_x, measurement_y = _clamp_vector(-intent_x, -intent_y, max_correction_m)
    return CorrectionDecision(
        active=True,
        correction_applied=True,
        measurement_delta_x_m=measurement_x,
        measurement_delta_y_m=measurement_y,
        measurement_delta_magnitude_m=math.hypot(measurement_x, measurement_y),
        source_intent_x_m=intent_x,
        source_intent_y_m=intent_y,
        source_intent_magnitude_m=intent_magnitude,
        axes=axes,
        blocked_axes=runtime_blocked_axes,
        axis_blockers=axis_blockers,
        runtime_consistency_ok=runtime_consistency_ok,
        phase4b_consistency_ok=phase4b_consistency_ok,
        phase4b_consistency_source=phase4b_consistency_source,
        blockers=(),
    )


def run(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        import rclpy
        from nav_msgs.msg import Odometry
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
        from std_msgs.msg import String
    except ModuleNotFoundError as exc:
        raise SystemExit("scan_reference_correction requires ROS2 Python packages.") from exc

    class ScanReferenceCorrectionNode(Node):
        def __init__(self) -> None:
            super().__init__("navlab_scan_reference_correction")
            self._hover_phase = ""
            self._last_status: dict[str, Any] = {}
            self._last_status_wall = 0.0
            self._history: deque[tuple[float, float, float]] = deque(maxlen=max(2, args.history_samples))
            self._last_applied_x = 0.0
            self._last_applied_y = 0.0
            self._last_decision = _empty_decision(blockers=("scan_reference_runtime_waiting_for_status",))
            self._published_count = 0
            self._corrected_count = 0
            self._passthrough_count = 0
            # ExternalNav bridge subscribes with the default reliable QoS; publish
            # corrected odom reliably while still ingesting raw SLAM odom as sensor data.
            corrected_odom_qos = QoSProfile(depth=10)
            corrected_odom_qos.reliability = ReliabilityPolicy.RELIABLE
            self._odom_pub = self.create_publisher(Odometry, args.output_odom_topic, corrected_odom_qos)
            self._status_pub = self.create_publisher(String, args.status_topic, 10)
            self.create_subscription(Odometry, args.slam_odom_topic, self._handle_odom, qos_profile_sensor_data)
            self.create_subscription(String, args.scan_reference_status_topic, self._handle_scan_reference_status, 10)
            self.create_subscription(String, args.hover_status_topic, self._handle_hover_status, 10)
            self.create_timer(0.5, self._publish_status)
            self.get_logger().info(
                f"scan_reference_correction subscribed to {args.slam_odom_topic}; "
                f"publishing {args.output_odom_topic}; fail-closed"
            )

        def _handle_hover_status(self, message: String) -> None:
            phase = _phase_from_status(message.data)
            if phase:
                self._hover_phase = phase
            if phase not in CORRECTION_PHASES:
                self._history.clear()

        def _handle_scan_reference_status(self, message: String) -> None:
            status = _parse_json(message.data)
            self._last_status = status
            self._last_status_wall = self.get_clock().now().nanoseconds / 1e9
            status.get("correction_intent") if isinstance(status.get("correction_intent"), dict) else {}
            eligibility = (
                status.get("correction_eligibility") if isinstance(status.get("correction_eligibility"), dict) else {}
            )
            if _bool(eligibility.get("correction_allowed")) and self._hover_phase in CORRECTION_PHASES:
                self._history.append(
                    (
                        _float(status.get("x_m")),
                        _float(status.get("y_m")),
                        0.0,
                    )
                )
            else:
                self._history.clear()

        def _handle_odom(self, message: Odometry) -> None:
            now_sec = self.get_clock().now().nanoseconds / 1e9
            status_age_ms = -1.0 if self._last_status_wall <= 0.0 else (now_sec - self._last_status_wall) * 1000.0
            frame_blockers: list[str] = []
            if message.header.frame_id != args.expected_frame_id:
                frame_blockers.append("scan_reference_correction_frame_id_mismatch")
            if message.child_frame_id != args.expected_child_frame_id:
                frame_blockers.append("scan_reference_correction_child_frame_id_mismatch")
            decision = decide_correction(
                self._last_status,
                hover_phase=self._hover_phase,
                status_age_ms=status_age_ms,
                max_status_age_ms=args.max_status_age_ms,
                max_correction_m=args.max_correction_m,
                max_measurement_delta_m=args.max_measurement_delta_m,
                runtime_history=list(self._history),
                min_runtime_consistency_samples=args.min_runtime_consistency_samples,
                min_direction_cosine=args.min_direction_cosine,
                max_axis_sign_flips=args.max_axis_sign_flips,
                max_saturation_ratio=args.max_saturation_ratio,
                correction_enabled=args.enable_correction,
            )
            if frame_blockers:
                decision = _empty_decision(
                    source_intent_x_m=decision.source_intent_x_m,
                    source_intent_y_m=decision.source_intent_y_m,
                    source_intent_magnitude_m=decision.source_intent_magnitude_m,
                    blocked_axes=decision.blocked_axes or decision.axes,
                    axis_blockers=decision.axis_blockers,
                    runtime_consistency_ok=decision.runtime_consistency_ok,
                    phase4b_consistency_ok=decision.phase4b_consistency_ok,
                    phase4b_consistency_source=decision.phase4b_consistency_source,
                    blockers=tuple(dict.fromkeys((*decision.blockers, *frame_blockers))),
                )
            target_x = decision.measurement_delta_x_m
            target_y = decision.measurement_delta_y_m
            applied_x, applied_y = _limit_step(
                target_x,
                target_y,
                self._last_applied_x,
                self._last_applied_y,
                args.max_correction_step_m,
            )
            if not decision.correction_applied:
                applied_x = applied_y = 0.0
            out = copy.deepcopy(message)
            out.header.frame_id = args.expected_frame_id
            out.child_frame_id = args.expected_child_frame_id
            out.pose.pose.position.x += applied_x
            out.pose.pose.position.y += applied_y
            out.pose.covariance[0] = max(float(out.pose.covariance[0]), 0.04)
            out.pose.covariance[7] = max(float(out.pose.covariance[7]), 0.04)
            self._odom_pub.publish(out)
            self._published_count += 1
            if decision.correction_applied:
                self._corrected_count += 1
            else:
                self._passthrough_count += 1
            self._last_applied_x = applied_x
            self._last_applied_y = applied_y
            self._last_decision = CorrectionDecision(
                active=decision.active,
                correction_applied=decision.correction_applied,
                measurement_delta_x_m=applied_x,
                measurement_delta_y_m=applied_y,
                measurement_delta_magnitude_m=math.hypot(applied_x, applied_y),
                source_intent_x_m=decision.source_intent_x_m,
                source_intent_y_m=decision.source_intent_y_m,
                source_intent_magnitude_m=decision.source_intent_magnitude_m,
                axes=decision.axes,
                blocked_axes=decision.blocked_axes,
                axis_blockers=decision.axis_blockers,
                runtime_consistency_ok=decision.runtime_consistency_ok,
                phase4b_consistency_ok=decision.phase4b_consistency_ok,
                phase4b_consistency_source=decision.phase4b_consistency_source,
                blockers=decision.blockers,
            )

        def _publish_status(self) -> None:
            status_age_ms = -1.0
            if self._last_status_wall > 0.0:
                status_age_ms = ((self.get_clock().now().nanoseconds / 1e9) - self._last_status_wall) * 1000.0
            payload = {
                "ready": self._published_count > 0,
                "state": "correcting" if self._last_decision.correction_applied else "passthrough",
                "correction_enabled": bool(args.enable_correction),
                "correction_applied": self._last_decision.correction_applied,
                "fail_closed": True,
                "blockers": list(self._last_decision.blockers),
                "hover_phase": self._hover_phase,
                "input_odom_topic": args.slam_odom_topic,
                "scan_reference_status_topic": args.scan_reference_status_topic,
                "output_odom_topic": args.output_odom_topic,
                "input_odom_qos_reliability": "sensor_data",
                "output_odom_qos_reliability": "reliable",
                "status_age_ms": status_age_ms,
                "published_count": self._published_count,
                "corrected_count": self._corrected_count,
                "passthrough_count": self._passthrough_count,
                "runtime_consistency_sample_count": len(self._history),
                "measurement_delta_x_m": self._last_decision.measurement_delta_x_m,
                "measurement_delta_y_m": self._last_decision.measurement_delta_y_m,
                "measurement_delta_magnitude_m": self._last_decision.measurement_delta_magnitude_m,
                "source_intent_x_m": self._last_decision.source_intent_x_m,
                "source_intent_y_m": self._last_decision.source_intent_y_m,
                "source_intent_magnitude_m": self._last_decision.source_intent_magnitude_m,
                "axes": list(self._last_decision.axes),
                "allowed_axes": list(self._last_decision.axes),
                "blocked_axes": list(self._last_decision.blocked_axes),
                "axis_blockers": {axis: list(values) for axis, values in self._last_decision.axis_blockers.items()},
                "runtime_consistency_ok": self._last_decision.runtime_consistency_ok,
                "phase4b_consistency_ok": self._last_decision.phase4b_consistency_ok,
                "phase4b_consistency_source": self._last_decision.phase4b_consistency_source,
                "max_correction_m": args.max_correction_m,
                "max_measurement_delta_m": args.max_measurement_delta_m,
                "max_correction_step_m": args.max_correction_step_m,
                "uses_gazebo_truth_input": False,
                "uses_known_map_input": False,
                "writes_external_nav_odom": False,
                "external_nav_input_topic": args.output_odom_topic,
            }
            msg = String()
            msg.data = json.dumps(payload, sort_keys=True)
            self._status_pub.publish(msg)

    rclpy.init(args=None)
    node = ScanReferenceCorrectionNode()
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
