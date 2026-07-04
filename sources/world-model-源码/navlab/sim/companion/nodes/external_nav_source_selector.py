from __future__ import annotations

import argparse
import copy
import json
import math
from dataclasses import dataclass
from typing import Any

CORRECTION_PHASES = frozenset({"hover_settle", "hover_hold"})
SETTLE_BOOTSTRAP_PHASES = frozenset({"hover_settle"})
DEFAULT_SLAM_ODOM_TOPIC = "/slam/odom"
DEFAULT_SCAN_REFERENCE_ODOM_TOPIC = "/navlab/scan_reference_drift/odom"
DEFAULT_SCAN_REFERENCE_STATUS_TOPIC = "/navlab/scan_reference_drift/status"
DEFAULT_HOVER_STATUS_TOPIC = "/navlab/hover/status"
DEFAULT_OUTPUT_ODOM_TOPIC = "/external_nav/odom_candidate"
DEFAULT_STATUS_TOPIC = "/external_nav/source_selector/status"


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    frame_id: str
    child_frame_id: str
    x_m: float
    y_m: float
    z_m: float = 0.0
    yaw_rad: float = 0.0


@dataclass(frozen=True, slots=True)
class SourceDecision:
    source: str
    output_x_m: float
    output_y_m: float
    output_z_m: float
    output_yaw_rad: float
    output_frame_id: str
    output_child_frame_id: str
    blockers: tuple[str, ...]
    cartographer_scan_disagreement: bool
    ready: bool
    publish: bool
    degraded: bool = False
    uses_gazebo_truth_input: bool = False
    uses_known_map_input: bool = False
    hold_age_ms: float | None = None
    hold_reason: str | None = None
    reject_reason: str | None = None
    rejected_step_m: float | None = None
    rejected_yaw_step_rad: float | None = None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(v for v in values if v))


def _magnitude(x: float, y: float) -> float:
    return math.hypot(x, y)


def _angle_delta_rad(a: float, b: float) -> float:
    return abs(math.atan2(math.sin(a - b), math.cos(a - b)))


def _yaw_from_quaternion(*, x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def _write_yaw_to_quaternion(orientation: Any, yaw_rad: float) -> None:
    orientation.x = 0.0
    orientation.y = 0.0
    orientation.z = math.sin(yaw_rad * 0.5)
    orientation.w = math.cos(yaw_rad * 0.5)


def _scan_reference_measurement_to_map_candidate(
    measurement: SourceCandidate,
    anchor: SourceCandidate | None,
) -> SourceCandidate:
    """Convert scan-reference measured displacement into a map-frame pose candidate.

    scan_reference reports measured drift from the reference scan. Its own
    correction intent uses the opposite sign, so the map pose candidate must
    apply that measurement as anchor - measurement.
    """
    if anchor is None:
        return measurement
    return SourceCandidate(
        frame_id=anchor.frame_id,
        child_frame_id=anchor.child_frame_id,
        x_m=anchor.x_m - measurement.x_m,
        y_m=anchor.y_m - measurement.y_m,
        z_m=anchor.z_m - measurement.z_m,
        yaw_rad=math.atan2(
            math.sin(anchor.yaw_rad - measurement.yaw_rad),
            math.cos(anchor.yaw_rad - measurement.yaw_rad),
        ),
    )


def _not_ready_decision(
    *,
    slam: SourceCandidate,
    blockers: tuple[str, ...],
    cartographer_scan_disagreement: bool,
    reject_reason: str | None = None,
    rejected_step_m: float | None = None,
    rejected_yaw_step_rad: float | None = None,
) -> SourceDecision:
    return SourceDecision(
        source="not_ready",
        output_x_m=slam.x_m,
        output_y_m=slam.y_m,
        output_z_m=slam.z_m,
        output_yaw_rad=slam.yaw_rad,
        output_frame_id=slam.frame_id,
        output_child_frame_id=slam.child_frame_id,
        blockers=blockers,
        cartographer_scan_disagreement=cartographer_scan_disagreement,
        ready=False,
        publish=False,
        reject_reason=reject_reason,
        rejected_step_m=rejected_step_m,
        rejected_yaw_step_rad=rejected_yaw_step_rad,
    )


def _hold_decision(
    *,
    slam: SourceCandidate,
    last_good_scan: SourceCandidate,
    blockers: tuple[str, ...],
    cartographer_scan_disagreement: bool,
    hold_age_ms: float,
    hold_reason: str,
    output_yaw_rad: float | None = None,
    reject_reason: str | None = None,
    rejected_step_m: float | None = None,
    rejected_yaw_step_rad: float | None = None,
) -> SourceDecision:
    return SourceDecision(
        source="scan_reference_hold",
        output_x_m=last_good_scan.x_m,
        output_y_m=last_good_scan.y_m,
        output_z_m=slam.z_m,
        output_yaw_rad=slam.yaw_rad if output_yaw_rad is None else output_yaw_rad,
        output_frame_id=slam.frame_id,
        output_child_frame_id=slam.child_frame_id,
        blockers=blockers,
        cartographer_scan_disagreement=cartographer_scan_disagreement,
        ready=True,
        publish=True,
        degraded=True,
        hold_age_ms=hold_age_ms,
        hold_reason=hold_reason,
        reject_reason=reject_reason,
        rejected_step_m=rejected_step_m,
        rejected_yaw_step_rad=rejected_yaw_step_rad,
    )


def _hold_or_not_ready(
    *,
    slam: SourceCandidate,
    blockers: tuple[str, ...],
    cartographer_scan_disagreement: bool,
    last_good_scan: SourceCandidate | None,
    last_good_scan_age_ms: float,
    max_hold_age_ms: float,
    hold_reason: str,
    output_yaw_rad: float | None = None,
    reject_reason: str | None = None,
    rejected_step_m: float | None = None,
    rejected_yaw_step_rad: float | None = None,
) -> SourceDecision:
    if last_good_scan is not None and 0.0 <= last_good_scan_age_ms <= max_hold_age_ms:
        return _hold_decision(
            slam=slam,
            last_good_scan=last_good_scan,
            blockers=blockers,
            cartographer_scan_disagreement=cartographer_scan_disagreement,
            hold_age_ms=last_good_scan_age_ms,
            hold_reason=hold_reason,
            output_yaw_rad=output_yaw_rad,
            reject_reason=reject_reason,
            rejected_step_m=rejected_step_m,
            rejected_yaw_step_rad=rejected_yaw_step_rad,
        )
    return _not_ready_decision(
        slam=slam,
        blockers=blockers,
        cartographer_scan_disagreement=cartographer_scan_disagreement,
        reject_reason=reject_reason,
        rejected_step_m=rejected_step_m,
        rejected_yaw_step_rad=rejected_yaw_step_rad,
    )


def _slam_settle_decision(
    *,
    slam: SourceCandidate,
    blockers: tuple[str, ...],
    cartographer_scan_disagreement: bool,
    hold_reason: str,
) -> SourceDecision:
    return SourceDecision(
        source="slam_settle",
        output_x_m=slam.x_m,
        output_y_m=slam.y_m,
        output_z_m=slam.z_m,
        output_yaw_rad=slam.yaw_rad,
        output_frame_id=slam.frame_id,
        output_child_frame_id=slam.child_frame_id,
        blockers=blockers,
        cartographer_scan_disagreement=cartographer_scan_disagreement,
        ready=True,
        publish=True,
        degraded=True,
        hold_reason=hold_reason,
    )


def _settle_hold_decision(
    *,
    slam: SourceCandidate,
    last_accepted_output: SourceCandidate,
    blockers: tuple[str, ...],
    cartographer_scan_disagreement: bool,
    hold_reason: str,
    rejected_step_m: float | None,
    rejected_yaw_step_rad: float | None,
) -> SourceDecision:
    return SourceDecision(
        source="hover_settle_hold",
        output_x_m=last_accepted_output.x_m,
        output_y_m=last_accepted_output.y_m,
        output_z_m=last_accepted_output.z_m,
        output_yaw_rad=last_accepted_output.yaw_rad,
        output_frame_id=slam.frame_id,
        output_child_frame_id=slam.child_frame_id,
        blockers=blockers,
        cartographer_scan_disagreement=cartographer_scan_disagreement,
        ready=True,
        publish=True,
        degraded=True,
        hold_reason=hold_reason,
        rejected_step_m=rejected_step_m,
        rejected_yaw_step_rad=rejected_yaw_step_rad,
    )


def _candidate_gate(
    *,
    decision: SourceDecision,
    last_accepted_output: SourceCandidate | None,
    max_candidate_step_m: float,
    max_candidate_yaw_step_rad: float,
) -> tuple[str | None, float | None, float | None]:
    if last_accepted_output is None:
        return None, None, None
    step_m = _magnitude(
        decision.output_x_m - last_accepted_output.x_m,
        decision.output_y_m - last_accepted_output.y_m,
    )
    yaw_step_rad = _angle_delta_rad(decision.output_yaw_rad, last_accepted_output.yaw_rad)
    if step_m > max_candidate_step_m:
        return "candidate_step_jump", step_m, yaw_step_rad
    if yaw_step_rad > max_candidate_yaw_step_rad:
        return "candidate_yaw_jump", step_m, yaw_step_rad
    return None, step_m, yaw_step_rad


def _slew_yaw_toward(current_yaw_rad: float, target_yaw_rad: float, max_step_rad: float) -> float:
    delta = math.atan2(math.sin(target_yaw_rad - current_yaw_rad), math.cos(target_yaw_rad - current_yaw_rad))
    if abs(delta) <= max_step_rad:
        return target_yaw_rad
    return current_yaw_rad + math.copysign(max_step_rad, delta)


def _slew_reacquire_decision(
    *,
    decision: SourceDecision,
    last_accepted_output: SourceCandidate | None,
    cartographer_scan_disagreement: bool,
    rejected_step_m: float | None,
    rejected_yaw_step_rad: float | None,
    max_candidate_step_m: float,
    max_candidate_yaw_step_rad: float,
    max_candidate_reacquire_step_m: float,
    max_candidate_reacquire_yaw_step_rad: float,
) -> SourceDecision | None:
    if last_accepted_output is None or rejected_step_m is None or rejected_yaw_step_rad is None:
        return None
    if rejected_step_m > max_candidate_reacquire_step_m:
        return None
    if rejected_yaw_step_rad > max_candidate_reacquire_yaw_step_rad:
        return None

    dx = decision.output_x_m - last_accepted_output.x_m
    dy = decision.output_y_m - last_accepted_output.y_m
    if rejected_step_m > max_candidate_step_m and rejected_step_m > 0.0:
        scale = max_candidate_step_m / rejected_step_m
        output_x = last_accepted_output.x_m + dx * scale
        output_y = last_accepted_output.y_m + dy * scale
    else:
        output_x = decision.output_x_m
        output_y = decision.output_y_m

    output_yaw = _slew_yaw_toward(
        last_accepted_output.yaw_rad,
        decision.output_yaw_rad,
        max_candidate_yaw_step_rad,
    )
    return SourceDecision(
        source="scan_reference_slew",
        output_x_m=output_x,
        output_y_m=output_y,
        output_z_m=decision.output_z_m,
        output_yaw_rad=output_yaw,
        output_frame_id=decision.output_frame_id,
        output_child_frame_id=decision.output_child_frame_id,
        blockers=("candidate_slew_reacquire",),
        cartographer_scan_disagreement=cartographer_scan_disagreement,
        ready=True,
        publish=True,
        degraded=True,
        hold_reason="candidate_slew_reacquire",
        rejected_step_m=rejected_step_m,
        rejected_yaw_step_rad=rejected_yaw_step_rad,
    )


def _slam_settle_or_not_ready(
    *,
    slam: SourceCandidate,
    blockers: tuple[str, ...],
    cartographer_scan_disagreement: bool,
    hover_phase: str,
    last_accepted_output: SourceCandidate | None,
    max_candidate_step_m: float,
    max_candidate_yaw_step_rad: float,
    hold_reason: str,
    reject_reason: str | None = None,
) -> SourceDecision:
    if hover_phase not in SETTLE_BOOTSTRAP_PHASES:
        return _not_ready_decision(
            slam=slam,
            blockers=blockers,
            cartographer_scan_disagreement=cartographer_scan_disagreement,
            reject_reason=reject_reason,
        )
    decision = _slam_settle_decision(
        slam=slam,
        blockers=blockers,
        cartographer_scan_disagreement=cartographer_scan_disagreement,
        hold_reason=hold_reason,
    )
    gate_reason, step_m, yaw_step_rad = _candidate_gate(
        decision=decision,
        last_accepted_output=last_accepted_output,
        max_candidate_step_m=max_candidate_step_m,
        max_candidate_yaw_step_rad=max_candidate_yaw_step_rad,
    )
    if gate_reason is not None:
        if last_accepted_output is not None:
            return _settle_hold_decision(
                slam=slam,
                last_accepted_output=last_accepted_output,
                blockers=(gate_reason,),
                cartographer_scan_disagreement=cartographer_scan_disagreement,
                hold_reason=f"hover_settle_last_accepted_hold_{gate_reason}",
                rejected_step_m=step_m,
                rejected_yaw_step_rad=yaw_step_rad,
            )
        return _not_ready_decision(
            slam=slam,
            blockers=(gate_reason,),
            cartographer_scan_disagreement=cartographer_scan_disagreement,
            reject_reason=gate_reason,
            rejected_step_m=step_m,
            rejected_yaw_step_rad=yaw_step_rad,
        )
    return decision


def _scan_is_eligible(
    status: dict[str, Any],
    *,
    hover_phase: str,
    scan_status_age_ms: float,
    max_status_age_ms: float,
    min_valid_beams: int,
    min_inlier_ratio: float,
    max_residual_rms_m: float,
    max_scan_reference_drift_m: float,
    min_direction_cosine: float,
    max_axis_sign_flips: int,
) -> tuple[bool, tuple[str, ...]]:
    blockers: list[str] = []
    if hover_phase not in CORRECTION_PHASES:
        blockers.append("not_hover_correction_phase")
    if scan_status_age_ms < 0.0 or scan_status_age_ms > max_status_age_ms:
        blockers.append("scan_reference_status_stale")
    if _bool(status.get("uses_gazebo_truth_input")):
        blockers.append("scan_reference_uses_gazebo_truth")
    if _bool(status.get("uses_known_map_input")):
        blockers.append("scan_reference_uses_known_map")
    if not _bool(status.get("ready")):
        blockers.append("scan_reference_not_ready")
    if not _bool(status.get("quality_good")):
        blockers.append("scan_reference_quality_not_good")
    if _float(status.get("valid_beams")) < float(min_valid_beams):
        blockers.append("scan_reference_valid_beams_low")
    if _float(status.get("inlier_ratio")) < min_inlier_ratio:
        blockers.append("scan_reference_inlier_ratio_low")
    if _float(status.get("residual_rms_m")) > max_residual_rms_m:
        blockers.append("scan_reference_residual_high")
    eligibility = status.get("correction_eligibility") if isinstance(status.get("correction_eligibility"), dict) else {}
    # Direction continuity and axis sign flips are correction-intent stability
    # signals. Cumulative horizontal drift is observed pose displacement; it is
    # surfaced as degraded evidence by the selector but does not by itself prove
    # a bad candidate. Candidate safety is enforced below by scan quality,
    # residual, Cartographer disagreement, and output step/yaw gates.
    _ = (max_scan_reference_drift_m, min_direction_cosine, max_axis_sign_flips, eligibility)
    return not blockers, _unique(blockers)


def _high_drift_tracking_blockers(
    status: dict[str, Any],
    *,
    min_direction_cosine: float,
    max_axis_sign_flips: int,
) -> tuple[str, ...]:
    eligibility = status.get("correction_eligibility") if isinstance(status.get("correction_eligibility"), dict) else {}
    intent = status.get("correction_intent") if isinstance(status.get("correction_intent"), dict) else {}
    blockers: list[str] = []
    if not _bool(eligibility.get("correction_allowed")):
        blockers.append("scan_reference_high_drift_tracking_not_allowed")
    allowed_axes = eligibility.get("allowed_axes")
    if not isinstance(allowed_axes, list) or not any(str(axis) for axis in allowed_axes):
        blockers.append("scan_reference_high_drift_tracking_axes_empty")
    if not _bool(intent.get("active")):
        blockers.append("scan_reference_high_drift_intent_not_active")
    intent_blockers = intent.get("blockers")
    if isinstance(intent_blockers, list) and any(str(blocker) for blocker in intent_blockers):
        blockers.append("scan_reference_high_drift_intent_has_blockers")
    direction_raw = eligibility.get("direction_cosine_min")
    if direction_raw is not None and _float(direction_raw, 1.0) < min_direction_cosine:
        blockers.append("scan_reference_high_drift_tracking_direction_unstable")
    if _float(eligibility.get("x_sign_flips")) > max_axis_sign_flips:
        blockers.append("scan_reference_high_drift_tracking_x_sign_flips")
    if _float(eligibility.get("y_sign_flips")) > max_axis_sign_flips:
        blockers.append("scan_reference_high_drift_tracking_y_sign_flips")
    return _unique(blockers)


def select_external_nav_source(
    *,
    slam: SourceCandidate,
    scan: SourceCandidate | None,
    scan_status: dict[str, Any],
    hover_phase: str,
    scan_status_age_ms: float,
    max_status_age_ms: float = 400.0,
    min_valid_beams: int = 80,
    min_inlier_ratio: float = 0.45,
    max_residual_rms_m: float = 0.30,
    max_scan_reference_drift_m: float = 0.25,
    min_direction_cosine: float = 0.70,
    max_axis_sign_flips: int = 0,
    cartographer_disagreement_m: float = 0.15,
    scan_reference_anchor: SourceCandidate | None = None,
    last_good_scan: SourceCandidate | None = None,
    last_good_scan_age_ms: float = -1.0,
    last_accepted_output: SourceCandidate | None = None,
    max_hold_age_ms: float = 750.0,
    max_hold_jump_m: float = 1.25,
    max_candidate_step_m: float = 0.12,
    max_candidate_yaw_step_rad: float = 0.35,
    max_candidate_reacquire_step_m: float = 0.35,
    max_candidate_reacquire_yaw_step_rad: float = 0.75,
) -> SourceDecision:
    if scan is None:
        if hover_phase in CORRECTION_PHASES:
            return _slam_settle_or_not_ready(
                slam=slam,
                blockers=("scan_reference_odom_missing",),
                cartographer_scan_disagreement=False,
                reject_reason="scan_reference_odom_missing",
                hover_phase=hover_phase,
                last_accepted_output=last_accepted_output,
                max_candidate_step_m=max_candidate_step_m,
                max_candidate_yaw_step_rad=max_candidate_yaw_step_rad,
                hold_reason="hover_settle_slam_continuity_scan_missing",
            )
        return SourceDecision(
            source="slam_bootstrap",
            output_x_m=slam.x_m,
            output_y_m=slam.y_m,
            output_z_m=slam.z_m,
            output_yaw_rad=slam.yaw_rad,
            output_frame_id=slam.frame_id,
            output_child_frame_id=slam.child_frame_id,
            blockers=("scan_reference_odom_missing",),
            cartographer_scan_disagreement=False,
            ready=True,
            publish=True,
        )

    scan_output = _scan_reference_measurement_to_map_candidate(scan, scan_reference_anchor)
    eligible, blockers = _scan_is_eligible(
        scan_status,
        hover_phase=hover_phase,
        scan_status_age_ms=scan_status_age_ms,
        max_status_age_ms=max_status_age_ms,
        min_valid_beams=min_valid_beams,
        min_inlier_ratio=min_inlier_ratio,
        max_residual_rms_m=max_residual_rms_m,
        max_scan_reference_drift_m=max_scan_reference_drift_m,
        min_direction_cosine=min_direction_cosine,
        max_axis_sign_flips=max_axis_sign_flips,
    )
    disagreement = _magnitude(scan_output.x_m - slam.x_m, scan_output.y_m - slam.y_m) > cartographer_disagreement_m
    scan_drift_high = _float(scan_status.get("horizontal_drift_m")) > max_scan_reference_drift_m
    scan_drift_blockers = ("scan_reference_horizontal_drift_high",) if scan_drift_high else ()
    if hover_phase not in CORRECTION_PHASES:
        return SourceDecision(
            source="slam_bootstrap",
            output_x_m=slam.x_m,
            output_y_m=slam.y_m,
            output_z_m=slam.z_m,
            output_yaw_rad=slam.yaw_rad,
            output_frame_id=slam.frame_id,
            output_child_frame_id=slam.child_frame_id,
            blockers=blockers,
            cartographer_scan_disagreement=disagreement,
            ready=True,
            publish=True,
        )
    if not eligible:
        hold_allowed = (
            last_good_scan is not None
            and 0.0 <= last_good_scan_age_ms <= max_hold_age_ms
            and 0.0 <= scan_status_age_ms <= max_status_age_ms
            and not _bool(scan_status.get("uses_gazebo_truth_input"))
            and not _bool(scan_status.get("uses_known_map_input"))
            and _magnitude(last_good_scan.x_m - slam.x_m, last_good_scan.y_m - slam.y_m) <= max_hold_jump_m
        )
        if hold_allowed:
            return _hold_decision(
                slam=slam,
                last_good_scan=last_good_scan,
                blockers=blockers,
                cartographer_scan_disagreement=disagreement,
                hold_reason="last_good_scan_reference_within_ttl",
                hold_age_ms=last_good_scan_age_ms,
                output_yaw_rad=last_accepted_output.yaw_rad if last_accepted_output is not None else slam.yaw_rad,
            )
        return _slam_settle_or_not_ready(
            slam=slam,
            blockers=blockers,
            cartographer_scan_disagreement=disagreement,
            hover_phase=hover_phase,
            last_accepted_output=last_accepted_output,
            max_candidate_step_m=max_candidate_step_m,
            max_candidate_yaw_step_rad=max_candidate_yaw_step_rad,
            hold_reason="hover_settle_slam_continuity_scan_not_eligible",
        )

    high_drift_tracking_blockers = (
        _high_drift_tracking_blockers(
            scan_status,
            min_direction_cosine=min_direction_cosine,
            max_axis_sign_flips=max_axis_sign_flips,
        )
        if scan_drift_high
        else ()
    )
    if high_drift_tracking_blockers:
        blockers = _unique([*scan_drift_blockers, *high_drift_tracking_blockers])
        return _hold_or_not_ready(
            slam=slam,
            blockers=blockers,
            cartographer_scan_disagreement=disagreement,
            last_good_scan=last_good_scan,
            last_good_scan_age_ms=last_good_scan_age_ms,
            max_hold_age_ms=max_hold_age_ms,
            hold_reason="scan_reference_high_drift_tracking_unstable",
            output_yaw_rad=last_accepted_output.yaw_rad if last_accepted_output is not None else slam.yaw_rad,
            reject_reason="scan_reference_high_drift_tracking_unstable",
        )

    if disagreement and last_accepted_output is None:
        hold_decision = _hold_or_not_ready(
            slam=slam,
            blockers=_unique(["cartographer_scan_disagreement", *scan_drift_blockers]),
            cartographer_scan_disagreement=disagreement,
            last_good_scan=last_good_scan,
            last_good_scan_age_ms=last_good_scan_age_ms,
            max_hold_age_ms=max_hold_age_ms,
            hold_reason="cartographer_scan_disagreement",
            output_yaw_rad=last_accepted_output.yaw_rad if last_accepted_output is not None else slam.yaw_rad,
            reject_reason="cartographer_scan_disagreement",
        )
        if hold_decision.publish or hover_phase not in SETTLE_BOOTSTRAP_PHASES:
            return hold_decision
        return _slam_settle_or_not_ready(
            slam=slam,
            blockers=_unique(["cartographer_scan_disagreement", *scan_drift_blockers]),
            cartographer_scan_disagreement=disagreement,
            hover_phase=hover_phase,
            last_accepted_output=last_accepted_output,
            max_candidate_step_m=max_candidate_step_m,
            max_candidate_yaw_step_rad=max_candidate_yaw_step_rad,
            hold_reason="hover_settle_slam_continuity_cartographer_scan_disagreement",
        )

    decision = SourceDecision(
        source="scan_reference",
        output_x_m=scan_output.x_m,
        output_y_m=scan_output.y_m,
        output_z_m=slam.z_m,
        output_yaw_rad=scan_output.yaw_rad,
        output_frame_id=slam.frame_id,
        output_child_frame_id=slam.child_frame_id,
        blockers=_unique(["cartographer_scan_disagreement" if disagreement else "", *scan_drift_blockers]),
        cartographer_scan_disagreement=disagreement,
        ready=True,
        publish=True,
        degraded=scan_drift_high,
    )
    gate_reason, step_m, yaw_step_rad = _candidate_gate(
        decision=decision,
        last_accepted_output=last_accepted_output,
        max_candidate_step_m=max_candidate_step_m,
        max_candidate_yaw_step_rad=max_candidate_yaw_step_rad,
    )
    if gate_reason == "candidate_step_jump":
        if hover_phase == "hover_hold":
            slew_decision = _slew_reacquire_decision(
                decision=decision,
                last_accepted_output=last_accepted_output,
                cartographer_scan_disagreement=disagreement,
                rejected_step_m=step_m,
                rejected_yaw_step_rad=yaw_step_rad,
                max_candidate_step_m=max_candidate_step_m,
                max_candidate_yaw_step_rad=max_candidate_yaw_step_rad,
                max_candidate_reacquire_step_m=max_candidate_reacquire_step_m,
                max_candidate_reacquire_yaw_step_rad=max_candidate_reacquire_yaw_step_rad,
            )
            if slew_decision is not None:
                return slew_decision
        if hover_phase in SETTLE_BOOTSTRAP_PHASES and (
            last_good_scan is None or last_good_scan_age_ms < 0.0 or last_good_scan_age_ms > max_hold_age_ms
        ):
            return _slam_settle_or_not_ready(
                slam=slam,
                blockers=_unique(["cartographer_scan_disagreement" if disagreement else "", "candidate_step_jump"]),
                cartographer_scan_disagreement=disagreement,
                hover_phase=hover_phase,
                last_accepted_output=last_accepted_output,
                max_candidate_step_m=max_candidate_step_m,
                max_candidate_yaw_step_rad=max_candidate_yaw_step_rad,
                hold_reason="hover_settle_slam_continuity_candidate_step_jump",
                reject_reason="candidate_step_jump",
            )
        return _hold_or_not_ready(
            slam=slam,
            blockers=("candidate_step_jump",),
            cartographer_scan_disagreement=disagreement,
            last_good_scan=last_good_scan,
            last_good_scan_age_ms=last_good_scan_age_ms,
            max_hold_age_ms=max_hold_age_ms,
            hold_reason="candidate_step_jump_hold",
            output_yaw_rad=last_accepted_output.yaw_rad,
            reject_reason="candidate_step_jump",
            rejected_step_m=step_m,
            rejected_yaw_step_rad=yaw_step_rad,
        )
    if gate_reason == "candidate_yaw_jump":
        if hover_phase == "hover_hold":
            slew_decision = _slew_reacquire_decision(
                decision=decision,
                last_accepted_output=last_accepted_output,
                cartographer_scan_disagreement=disagreement,
                rejected_step_m=step_m,
                rejected_yaw_step_rad=yaw_step_rad,
                max_candidate_step_m=max_candidate_step_m,
                max_candidate_yaw_step_rad=max_candidate_yaw_step_rad,
                max_candidate_reacquire_step_m=max_candidate_reacquire_step_m,
                max_candidate_reacquire_yaw_step_rad=max_candidate_reacquire_yaw_step_rad,
            )
            if slew_decision is not None:
                return slew_decision
        if hover_phase in SETTLE_BOOTSTRAP_PHASES and (
            last_good_scan is None or last_good_scan_age_ms < 0.0 or last_good_scan_age_ms > max_hold_age_ms
        ):
            return _slam_settle_or_not_ready(
                slam=slam,
                blockers=_unique(["cartographer_scan_disagreement" if disagreement else "", "candidate_yaw_jump"]),
                cartographer_scan_disagreement=disagreement,
                hover_phase=hover_phase,
                last_accepted_output=last_accepted_output,
                max_candidate_step_m=max_candidate_step_m,
                max_candidate_yaw_step_rad=max_candidate_yaw_step_rad,
                hold_reason="hover_settle_slam_continuity_candidate_yaw_jump",
                reject_reason="candidate_yaw_jump",
            )
        return _hold_or_not_ready(
            slam=slam,
            blockers=("candidate_yaw_jump",),
            cartographer_scan_disagreement=disagreement,
            last_good_scan=last_good_scan,
            last_good_scan_age_ms=last_good_scan_age_ms,
            max_hold_age_ms=max_hold_age_ms,
            hold_reason="candidate_yaw_jump_hold",
            output_yaw_rad=last_accepted_output.yaw_rad,
            reject_reason="candidate_yaw_jump",
            rejected_step_m=step_m,
            rejected_yaw_step_rad=yaw_step_rad,
        )
    return decision


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select a fail-closed ExternalNav odometry candidate for hover.")
    parser.add_argument("--slam-odom-topic", default=DEFAULT_SLAM_ODOM_TOPIC)
    parser.add_argument("--scan-reference-odom-topic", default=DEFAULT_SCAN_REFERENCE_ODOM_TOPIC)
    parser.add_argument("--scan-reference-status-topic", default=DEFAULT_SCAN_REFERENCE_STATUS_TOPIC)
    parser.add_argument("--hover-status-topic", default=DEFAULT_HOVER_STATUS_TOPIC)
    parser.add_argument("--output-odom-topic", default=DEFAULT_OUTPUT_ODOM_TOPIC)
    parser.add_argument("--status-topic", default=DEFAULT_STATUS_TOPIC)
    parser.add_argument("--max-status-age-ms", type=float, default=400.0)
    parser.add_argument("--max-scan-reference-drift-m", type=float, default=0.25)
    parser.add_argument("--max-hold-age-ms", type=float, default=750.0)
    parser.add_argument("--max-hold-jump-m", type=float, default=1.25)
    parser.add_argument("--max-candidate-step-m", type=float, default=0.12)
    parser.add_argument("--max-candidate-yaw-step-rad", type=float, default=0.35)
    parser.add_argument("--max-candidate-reacquire-step-m", type=float, default=0.35)
    parser.add_argument("--max-candidate-reacquire-yaw-step-rad", type=float, default=0.75)
    parser.add_argument("--cartographer-disagreement-m", type=float, default=0.15)
    return parser


def _parse_json(data: str) -> dict[str, Any]:
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _phase_from_status(data: str) -> str:
    return str(_parse_json(data).get("phase") or "")


def run(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        import rclpy
        from nav_msgs.msg import Odometry
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
        from std_msgs.msg import String
    except ModuleNotFoundError as exc:
        raise SystemExit("external_nav_source_selector requires ROS2 Python packages.") from exc

    class ExternalNavSourceSelectorNode(Node):
        def __init__(self) -> None:
            super().__init__("navlab_external_nav_source_selector")
            self._hover_phase = ""
            self._last_scan_odom: Odometry | None = None
            self._last_scan_status: dict[str, Any] = {}
            self._last_scan_status_wall = 0.0
            self._last_good_scan_candidate: SourceCandidate | None = None
            self._last_good_scan_wall = 0.0
            self._last_accepted_output: SourceCandidate | None = None
            self._last_accepted_wall = 0.0
            self._scan_reference_anchor: SourceCandidate | None = None
            self._scan_reference_anchor_stamp_sec = -1.0
            self._last_decision = SourceDecision(
                source="waiting",
                output_x_m=0.0,
                output_y_m=0.0,
                output_z_m=0.0,
                output_yaw_rad=0.0,
                output_frame_id="map",
                output_child_frame_id="base_link",
                blockers=("waiting_for_slam_odom",),
                cartographer_scan_disagreement=False,
                ready=False,
                publish=False,
            )
            output_qos = QoSProfile(depth=10)
            output_qos.reliability = ReliabilityPolicy.RELIABLE
            self._odom_pub = self.create_publisher(Odometry, args.output_odom_topic, output_qos)
            self._status_pub = self.create_publisher(String, args.status_topic, 10)
            self.create_subscription(Odometry, args.slam_odom_topic, self._handle_slam_odom, qos_profile_sensor_data)
            self.create_subscription(
                Odometry,
                args.scan_reference_odom_topic,
                self._handle_scan_odom,
                qos_profile_sensor_data,
            )
            self.create_subscription(String, args.scan_reference_status_topic, self._handle_scan_status, 10)
            self.create_subscription(String, args.hover_status_topic, self._handle_hover_status, 10)
            self.create_timer(0.5, self._publish_status)

        def _handle_hover_status(self, message: String) -> None:
            phase = _phase_from_status(message.data)
            if phase:
                self._hover_phase = phase

        def _handle_scan_status(self, message: String) -> None:
            self._last_scan_status = _parse_json(message.data)
            self._last_scan_status_wall = self.get_clock().now().nanoseconds / 1e9

        def _handle_scan_odom(self, message: Odometry) -> None:
            self._last_scan_odom = message

        def _candidate_from_odom(self, message: Odometry) -> SourceCandidate:
            orientation = message.pose.pose.orientation
            return SourceCandidate(
                frame_id=message.header.frame_id,
                child_frame_id=message.child_frame_id,
                x_m=float(message.pose.pose.position.x),
                y_m=float(message.pose.pose.position.y),
                z_m=float(message.pose.pose.position.z),
                yaw_rad=_yaw_from_quaternion(
                    x=float(orientation.x),
                    y=float(orientation.y),
                    z=float(orientation.z),
                    w=float(orientation.w),
                ),
            )

        def _handle_slam_odom(self, message: Odometry) -> None:
            now_sec = self.get_clock().now().nanoseconds / 1e9
            status_age_ms = (
                -1.0 if self._last_scan_status_wall <= 0.0 else (now_sec - self._last_scan_status_wall) * 1000.0
            )
            scan_candidate = (
                self._candidate_from_odom(self._last_scan_odom) if self._last_scan_odom is not None else None
            )
            slam_candidate = self._candidate_from_odom(message)
            reference_stamp_sec = _float(self._last_scan_status.get("reference_stamp_sec"), -1.0)
            if (
                scan_candidate is not None
                and reference_stamp_sec >= 0.0
                and not math.isclose(reference_stamp_sec, self._scan_reference_anchor_stamp_sec, abs_tol=1e-6)
            ):
                self._scan_reference_anchor = self._last_accepted_output or slam_candidate
                self._scan_reference_anchor_stamp_sec = reference_stamp_sec
            last_good_age_ms = (
                -1.0 if self._last_good_scan_wall <= 0.0 else (now_sec - self._last_good_scan_wall) * 1000.0
            )
            decision = select_external_nav_source(
                slam=slam_candidate,
                scan=scan_candidate,
                scan_status=self._last_scan_status,
                hover_phase=self._hover_phase,
                scan_status_age_ms=status_age_ms,
                max_status_age_ms=args.max_status_age_ms,
                max_scan_reference_drift_m=args.max_scan_reference_drift_m,
                cartographer_disagreement_m=args.cartographer_disagreement_m,
                scan_reference_anchor=self._scan_reference_anchor,
                last_good_scan=self._last_good_scan_candidate,
                last_good_scan_age_ms=last_good_age_ms,
                last_accepted_output=self._last_accepted_output,
                max_hold_age_ms=args.max_hold_age_ms,
                max_hold_jump_m=args.max_hold_jump_m,
                max_candidate_step_m=args.max_candidate_step_m,
                max_candidate_yaw_step_rad=args.max_candidate_yaw_step_rad,
                max_candidate_reacquire_step_m=args.max_candidate_reacquire_step_m,
                max_candidate_reacquire_yaw_step_rad=args.max_candidate_reacquire_yaw_step_rad,
            )
            if decision.source in {"scan_reference", "scan_reference_slew"} and scan_candidate is not None:
                self._last_good_scan_candidate = SourceCandidate(
                    frame_id=decision.output_frame_id,
                    child_frame_id=decision.output_child_frame_id,
                    x_m=decision.output_x_m,
                    y_m=decision.output_y_m,
                    z_m=decision.output_z_m,
                    yaw_rad=decision.output_yaw_rad,
                )
                self._last_good_scan_wall = now_sec
            self._last_decision = decision
            if not decision.publish:
                return
            out = copy.deepcopy(message)
            out.header.frame_id = decision.output_frame_id
            out.child_frame_id = decision.output_child_frame_id
            out.pose.pose.position.x = decision.output_x_m
            out.pose.pose.position.y = decision.output_y_m
            out.pose.pose.position.z = decision.output_z_m
            _write_yaw_to_quaternion(out.pose.pose.orientation, decision.output_yaw_rad)
            out.pose.covariance[0] = max(float(out.pose.covariance[0]), 0.04)
            out.pose.covariance[7] = max(float(out.pose.covariance[7]), 0.04)
            self._odom_pub.publish(out)
            self._last_accepted_output = SourceCandidate(
                frame_id=decision.output_frame_id,
                child_frame_id=decision.output_child_frame_id,
                x_m=decision.output_x_m,
                y_m=decision.output_y_m,
                z_m=decision.output_z_m,
                yaw_rad=decision.output_yaw_rad,
            )
            self._last_accepted_wall = now_sec

        def _publish_status(self) -> None:
            now_sec = self.get_clock().now().nanoseconds / 1e9
            last_accepted_age_ms = (
                None if self._last_accepted_wall <= 0.0 else (now_sec - self._last_accepted_wall) * 1000.0
            )
            payload = {
                "ready": self._last_decision.ready,
                "publish": self._last_decision.publish,
                "degraded": self._last_decision.degraded,
                "source": self._last_decision.source,
                "blockers": list(self._last_decision.blockers),
                "hover_phase": self._hover_phase,
                "output_odom_topic": args.output_odom_topic,
                "slam_odom_topic": args.slam_odom_topic,
                "scan_reference_odom_topic": args.scan_reference_odom_topic,
                "scan_reference_status_topic": args.scan_reference_status_topic,
                "cartographer_scan_disagreement": self._last_decision.cartographer_scan_disagreement,
                "uses_gazebo_truth_input": self._last_decision.uses_gazebo_truth_input,
                "uses_known_map_input": self._last_decision.uses_known_map_input,
                "output_frame_id": self._last_decision.output_frame_id,
                "output_child_frame_id": self._last_decision.output_child_frame_id,
                "hold_age_ms": self._last_decision.hold_age_ms,
                "hold_reason": self._last_decision.hold_reason,
                "reject_reason": self._last_decision.reject_reason,
                "rejected_step_m": self._last_decision.rejected_step_m,
                "rejected_yaw_step_rad": self._last_decision.rejected_yaw_step_rad,
                "last_accepted_age_ms": last_accepted_age_ms,
                "scan_reference_anchor_stamp_sec": self._scan_reference_anchor_stamp_sec,
                "scan_reference_anchor_x_m": None
                if self._scan_reference_anchor is None
                else self._scan_reference_anchor.x_m,
                "scan_reference_anchor_y_m": None
                if self._scan_reference_anchor is None
                else self._scan_reference_anchor.y_m,
            }
            msg = String()
            msg.data = json.dumps(payload, sort_keys=True)
            self._status_pub.publish(msg)

    rclpy.init(args=None)
    node = ExternalNavSourceSelectorNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
