from __future__ import annotations

import argparse
import json
import time

from navlab.common.perception.scan_reference_drift import (
    CORRECTION_PHASES,
    ScanReferenceDriftConfig,
    ScanReferenceDriftEstimator,
    ScanReferenceEstimate,
    evaluate_correction_intent,
    sample_from_scan_fields,
)

DEFAULT_ODOM_TOPIC = "/navlab/scan_reference_drift/odom"
DEFAULT_STATUS_TOPIC = "/navlab/scan_reference_drift/status"
DEFAULT_HOVER_STATUS_TOPIC = "/navlab/hover/status"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish diagnostic-only scan-to-reference drift from LaserScan.")
    parser.add_argument("--scan-topic", default="/scan")
    parser.add_argument("--odom-topic", default=DEFAULT_ODOM_TOPIC)
    parser.add_argument("--status-topic", default=DEFAULT_STATUS_TOPIC)
    parser.add_argument("--hover-status-topic", default=DEFAULT_HOVER_STATUS_TOPIC)
    parser.add_argument("--frame-id", default="scan_reference")
    parser.add_argument("--child-frame-id", default="base_link")
    parser.add_argument("--min-valid-beams", type=int, default=80)
    parser.add_argument("--max-residual-rms-m", type=float, default=0.30)
    parser.add_argument("--max-range-delta-m", type=float, default=3.0)
    parser.add_argument("--max-horizontal-drift-m", type=float, default=5.0)
    parser.add_argument("--max-inlier-residual-m", type=float, default=0.35)
    parser.add_argument("--min-inlier-ratio", type=float, default=0.45)
    parser.add_argument("--robust-iterations", type=int, default=3)
    parser.add_argument("--yaw-search-window-rad", type=float, default=0.12)
    parser.add_argument("--yaw-search-steps", type=int, default=13)
    parser.add_argument("--eligibility-window-samples", type=int, default=8)
    parser.add_argument("--min-stable-samples", type=int, default=5)
    parser.add_argument("--min-axis-drift-m", type=float, default=0.03)
    parser.add_argument("--axis-deadband-m", type=float, default=0.03)
    parser.add_argument("--max-axis-sign-flips", type=int, default=0)
    parser.add_argument("--max-velocity-mps", type=float, default=0.75)
    parser.add_argument("--min-direction-cosine", type=float, default=0.70)
    parser.add_argument("--max-phase4b-saturation-ratio", type=float, default=0.95)
    parser.add_argument("--min-correction-intent-consecutive-allowed-samples", type=int, default=20)
    parser.add_argument("--max-correction-intent-m", type=float, default=0.25)
    parser.add_argument("--correction-intent-gain", type=float, default=1.0)
    parser.add_argument("--reset-on-hover-hold", action="store_true", default=True)
    parser.add_argument("--no-reset-on-hover-hold", dest="reset_on_hover_hold", action="store_false")
    return parser


def _stamp_to_float(stamp) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def _parse_phase(data: str) -> str:
    try:
        value = json.loads(data)
    except json.JSONDecodeError:
        return ""
    return str(value.get("phase") or "") if isinstance(value, dict) else ""


def should_reset_reference_on_phase(
    *,
    reset_on_hover_hold: bool,
    phase: str,
    hover_hold_reference_reset_done: bool,
) -> tuple[bool, bool]:
    if not reset_on_hover_hold or not phase:
        return False, hover_hold_reference_reset_done
    if phase == "hover_hold" and not hover_hold_reference_reset_done:
        return True, True
    if phase not in CORRECTION_PHASES:
        return False, False
    return False, hover_hold_reference_reset_done


def _intent_payload(intent) -> dict[str, object]:
    return {
        "shadow_only": intent.shadow_only,
        "active": intent.active,
        "mode": intent.mode,
        "axes": list(intent.axes),
        "correction_x_m": intent.correction_x_m,
        "correction_y_m": intent.correction_y_m,
        "correction_magnitude_m": intent.correction_magnitude_m,
        "unit_x": intent.unit_x,
        "unit_y": intent.unit_y,
        "source_x_m": intent.source_x_m,
        "source_y_m": intent.source_y_m,
        "consecutive_allowed_samples": intent.consecutive_allowed_samples,
        "required_consecutive_allowed_samples": intent.required_consecutive_allowed_samples,
        "max_correction_m": intent.max_correction_m,
        "gain": intent.gain,
        "phase4b_consistency_ok": intent.phase4b_consistency_ok,
        "phase4b_consistency_source": intent.phase4b_consistency_source,
        "phase4b_consistency": intent.phase4b_consistency,
        "blockers": list(intent.blockers),
    }


def _estimate_payload(
    estimate: ScanReferenceEstimate,
    *,
    scan_topic: str,
    config: ScanReferenceDriftConfig,
    consecutive_allowed_samples: int,
    hover_phase: str,
) -> dict[str, object]:
    eligibility = estimate.correction_eligibility
    intent = evaluate_correction_intent(
        estimate,
        config,
        consecutive_allowed_samples=consecutive_allowed_samples,
        hover_phase=hover_phase,
    )
    return {
        "ready": estimate.ready,
        "quality_good": estimate.quality_good,
        "blockers": list(estimate.blockers),
        "source_topic": scan_topic,
        "reference_source": "first_hover_hold_scan_or_first_runtime_scan",
        "estimator": "range_residual_least_squares",
        "x_m": estimate.x_m,
        "y_m": estimate.y_m,
        "horizontal_drift_m": estimate.horizontal_drift_m,
        "yaw_rad": estimate.yaw_rad,
        "valid_beams": estimate.valid_beams,
        "total_beams": estimate.total_beams,
        "residual_rms_m": estimate.residual_rms_m,
        "max_abs_residual_m": estimate.max_abs_residual_m,
        "raw_residual_rms_m": estimate.raw_residual_rms_m,
        "raw_max_abs_residual_m": estimate.raw_max_abs_residual_m,
        "inlier_beams": estimate.inlier_beams,
        "inlier_ratio": estimate.inlier_ratio,
        "stamp_sec": estimate.stamp_sec,
        "reference_stamp_sec": estimate.reference_stamp_sec,
        "uses_gazebo_truth_input": False,
        "uses_known_map_input": False,
        "correction_output_enabled": False,
        "phase4b_consistency_ok": intent.phase4b_consistency_ok,
        "phase4b_consistency_source": intent.phase4b_consistency_source,
        "phase4b_consistency": intent.phase4b_consistency,
        "correction_intent": _intent_payload(intent),
        "correction_eligibility": {
            "correction_allowed": False if eligibility is None else eligibility.correction_allowed,
            "allowed_mode": "none" if eligibility is None else eligibility.allowed_mode,
            "allowed_axes": [] if eligibility is None else list(eligibility.allowed_axes),
            "stable_axes": [] if eligibility is None else list(eligibility.stable_axes),
            "projection_x": 0.0 if eligibility is None else eligibility.projection_x,
            "projection_y": 0.0 if eligibility is None else eligibility.projection_y,
            "latest_velocity_mps": 0.0 if eligibility is None else eligibility.latest_velocity_mps,
            "direction_cosine_min": None if eligibility is None else eligibility.direction_cosine_min,
            "stable_sample_count": 0 if eligibility is None else eligibility.stable_sample_count,
            "x_sign_flips": 0 if eligibility is None else eligibility.x_sign_flips,
            "y_sign_flips": 0 if eligibility is None else eligibility.y_sign_flips,
            "blockers": ["scan_reference_eligibility_not_ready"] if eligibility is None else list(eligibility.blockers),
        },
    }


def run(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        import rclpy
        from nav_msgs.msg import Odometry
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import LaserScan
        from std_msgs.msg import String
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "scan_reference_drift requires ROS2 Python packages. "
            "Run it through the NavLab runtime container after sourcing ROS."
        ) from exc

    class ScanReferenceDriftNode(Node):
        def __init__(self) -> None:
            super().__init__("navlab_scan_reference_drift")
            self._estimator = ScanReferenceDriftEstimator(
                ScanReferenceDriftConfig(
                    min_valid_beams=args.min_valid_beams,
                    max_residual_rms_m=args.max_residual_rms_m,
                    max_range_delta_m=args.max_range_delta_m,
                    max_horizontal_drift_m=args.max_horizontal_drift_m,
                    max_inlier_residual_m=args.max_inlier_residual_m,
                    min_inlier_ratio=args.min_inlier_ratio,
                    robust_iterations=args.robust_iterations,
                    yaw_search_window_rad=args.yaw_search_window_rad,
                    yaw_search_steps=args.yaw_search_steps,
                    eligibility_window_samples=args.eligibility_window_samples,
                    min_stable_samples=args.min_stable_samples,
                    min_axis_drift_m=args.min_axis_drift_m,
                    axis_deadband_m=args.axis_deadband_m,
                    max_axis_sign_flips=args.max_axis_sign_flips,
                    max_velocity_mps=args.max_velocity_mps,
                    min_direction_cosine=args.min_direction_cosine,
                    max_phase4b_saturation_ratio=args.max_phase4b_saturation_ratio,
                    min_correction_intent_consecutive_allowed_samples=args.min_correction_intent_consecutive_allowed_samples,
                    max_correction_intent_m=args.max_correction_intent_m,
                    correction_intent_gain=args.correction_intent_gain,
                )
            )
            self._config = self._estimator.config
            self._last_phase = ""
            self._reset_pending = False
            self._hover_hold_reference_reset_done = False
            self._last_estimate: ScanReferenceEstimate | None = None
            self._consecutive_allowed_samples = 0
            self._last_publish_wall = time.monotonic()
            self._odom_pub = self.create_publisher(Odometry, args.odom_topic, qos_profile_sensor_data)
            self._status_pub = self.create_publisher(String, args.status_topic, 10)
            self.create_subscription(LaserScan, args.scan_topic, self._handle_scan, qos_profile_sensor_data)
            self.create_subscription(String, args.hover_status_topic, self._handle_hover_status, 10)
            self.get_logger().info(
                f"scan_reference_drift diagnostic subscribed to {args.scan_topic}; "
                f"publishing {args.odom_topic} and {args.status_topic}; correction disabled"
            )

        def _handle_hover_status(self, message: String) -> None:
            phase = _parse_phase(message.data)
            reset_now, self._hover_hold_reference_reset_done = should_reset_reference_on_phase(
                reset_on_hover_hold=args.reset_on_hover_hold,
                phase=phase,
                hover_hold_reference_reset_done=self._hover_hold_reference_reset_done,
            )
            if reset_now:
                self._reset_pending = True
            if phase:
                self._last_phase = phase

        def _handle_scan(self, message: LaserScan) -> None:
            if self._reset_pending:
                self._estimator.reset()
                self._consecutive_allowed_samples = 0
                self._reset_pending = False
            sample = sample_from_scan_fields(
                ranges=list(message.ranges),
                angle_min=message.angle_min,
                angle_increment=message.angle_increment,
                range_min=message.range_min,
                range_max=message.range_max,
                stamp_sec=_stamp_to_float(message.header.stamp),
                frame_id=message.header.frame_id,
            )
            estimate = self._estimator.update(sample)
            eligibility = estimate.correction_eligibility
            if self._last_phase in CORRECTION_PHASES and eligibility is not None and eligibility.correction_allowed:
                self._consecutive_allowed_samples += 1
            else:
                self._consecutive_allowed_samples = 0
            previous = self._last_estimate
            self._publish_odom(message, estimate, previous)
            self._publish_status(estimate)
            self._last_estimate = estimate

        def _publish_odom(
            self,
            scan: LaserScan,
            estimate: ScanReferenceEstimate,
            previous: ScanReferenceEstimate | None,
        ) -> None:
            msg = Odometry()
            msg.header.stamp = scan.header.stamp
            msg.header.frame_id = args.frame_id
            msg.child_frame_id = args.child_frame_id
            msg.pose.pose.position.x = estimate.x_m
            msg.pose.pose.position.y = estimate.y_m
            msg.pose.pose.position.z = 0.0
            msg.pose.pose.orientation.w = 1.0
            msg.pose.covariance[0] = max(estimate.residual_rms_m, 1e-3) ** 2
            msg.pose.covariance[7] = max(estimate.residual_rms_m, 1e-3) ** 2
            msg.pose.covariance[14] = 999.0
            msg.pose.covariance[21] = 999.0
            msg.pose.covariance[28] = 999.0
            msg.pose.covariance[35] = 999.0
            if previous is not None:
                dt = estimate.stamp_sec - previous.stamp_sec
                if dt > 1e-3:
                    msg.twist.twist.linear.x = (estimate.x_m - previous.x_m) / dt
                    msg.twist.twist.linear.y = (estimate.y_m - previous.y_m) / dt
            self._odom_pub.publish(msg)

        def _publish_status(self, estimate: ScanReferenceEstimate) -> None:
            payload = _estimate_payload(
                estimate,
                scan_topic=args.scan_topic,
                config=self._config,
                consecutive_allowed_samples=self._consecutive_allowed_samples,
                hover_phase=self._last_phase,
            )
            payload["hover_phase"] = self._last_phase
            msg = String()
            msg.data = json.dumps(payload, sort_keys=True)
            self._status_pub.publish(msg)

    rclpy.init(args=None)
    node = ScanReferenceDriftNode()
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
