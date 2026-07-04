from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

CORRECTION_PHASES = frozenset({"hover_settle", "hover_hold"})


@dataclass(frozen=True, slots=True)
class ScanReferenceSample:
    ranges: tuple[float, ...]
    angle_min: float
    angle_increment: float
    range_min: float
    range_max: float
    stamp_sec: float = 0.0
    frame_id: str = ""


@dataclass(frozen=True, slots=True)
class ScanCorrectionEligibility:
    correction_allowed: bool
    allowed_mode: str
    allowed_axes: tuple[str, ...]
    stable_axes: tuple[str, ...]
    projection_x: float
    projection_y: float
    latest_velocity_mps: float
    direction_cosine_min: float | None
    stable_sample_count: int
    x_sign_flips: int
    y_sign_flips: int
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScanCorrectionIntent:
    shadow_only: bool
    active: bool
    mode: str
    axes: tuple[str, ...]
    correction_x_m: float
    correction_y_m: float
    correction_magnitude_m: float
    unit_x: float
    unit_y: float
    source_x_m: float
    source_y_m: float
    consecutive_allowed_samples: int
    required_consecutive_allowed_samples: int
    max_correction_m: float
    gain: float
    phase4b_consistency_ok: bool
    phase4b_consistency_source: str
    phase4b_consistency: dict[str, object]
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScanReferenceEstimate:
    x_m: float
    y_m: float
    valid_beams: int
    total_beams: int
    residual_rms_m: float
    max_abs_residual_m: float
    raw_residual_rms_m: float
    raw_max_abs_residual_m: float
    inlier_beams: int
    inlier_ratio: float
    horizontal_drift_m: float
    stamp_sec: float
    reference_stamp_sec: float
    ready: bool
    quality_good: bool
    blockers: tuple[str, ...]
    correction_eligibility: ScanCorrectionEligibility | None = None
    yaw_rad: float = 0.0


@dataclass(frozen=True, slots=True)
class ScanReferenceDriftConfig:
    min_valid_beams: int = 80
    max_residual_rms_m: float = 0.30
    max_range_delta_m: float = 3.0
    max_horizontal_drift_m: float = 5.0
    max_inlier_residual_m: float = 0.35
    min_inlier_ratio: float = 0.45
    robust_iterations: int = 3
    yaw_search_window_rad: float = 0.12
    yaw_search_steps: int = 13
    eligibility_window_samples: int = 8
    min_stable_samples: int = 5
    min_axis_drift_m: float = 0.05
    axis_deadband_m: float = 0.03
    max_axis_sign_flips: int = 0
    max_velocity_mps: float = 0.75
    min_direction_cosine: float = 0.70
    max_phase4b_saturation_ratio: float = 0.95
    correction_intent_shadow_enabled: bool = True
    min_correction_intent_consecutive_allowed_samples: int = 8
    max_correction_intent_m: float = 0.25
    correction_intent_gain: float = 1.0


def sample_from_scan_fields(
    *,
    ranges: Sequence[float],
    angle_min: float,
    angle_increment: float,
    range_min: float,
    range_max: float,
    stamp_sec: float = 0.0,
    frame_id: str = "",
) -> ScanReferenceSample:
    return ScanReferenceSample(
        ranges=tuple(float(v) for v in ranges),
        angle_min=float(angle_min),
        angle_increment=float(angle_increment),
        range_min=float(range_min),
        range_max=float(range_max),
        stamp_sec=float(stamp_sec),
        frame_id=frame_id,
    )


class ScanReferenceDriftEstimator:
    """Online range-residual drift estimator using only LaserScan beams."""

    def __init__(self, config: ScanReferenceDriftConfig | None = None) -> None:
        self.config = config or ScanReferenceDriftConfig()
        self.reference: ScanReferenceSample | None = None
        self.last_estimate: ScanReferenceEstimate | None = None
        self._history: deque[ScanReferenceEstimate] = deque(maxlen=max(2, self.config.eligibility_window_samples))

    def reset(self) -> None:
        self.reference = None
        self.last_estimate = None
        self._history.clear()

    def update(self, sample: ScanReferenceSample) -> ScanReferenceEstimate:
        if self.reference is None:
            self.reference = sample
            estimate = ScanReferenceEstimate(
                x_m=0.0,
                y_m=0.0,
                valid_beams=0,
                total_beams=len(sample.ranges),
                residual_rms_m=0.0,
                max_abs_residual_m=0.0,
                raw_residual_rms_m=0.0,
                raw_max_abs_residual_m=0.0,
                inlier_beams=0,
                inlier_ratio=0.0,
                horizontal_drift_m=0.0,
                stamp_sec=sample.stamp_sec,
                reference_stamp_sec=sample.stamp_sec,
                ready=False,
                quality_good=False,
                blockers=("scan_reference_waiting_for_second_scan",),
                yaw_rad=0.0,
            )
            self.last_estimate = estimate
            return estimate

        previous = self.last_estimate
        estimate = estimate_scan_reference_translation(self.reference, sample, self.config)
        self._history.append(estimate)
        estimate = _with_eligibility(
            estimate,
            evaluate_correction_eligibility(list(self._history), self.config, previous),
        )
        self.last_estimate = estimate
        self._history[-1] = estimate
        return estimate


def estimate_scan_reference_translation(
    reference: ScanReferenceSample,
    current: ScanReferenceSample,
    config: ScanReferenceDriftConfig | None = None,
) -> ScanReferenceEstimate:
    cfg = config or ScanReferenceDriftConfig()
    beam_count = min(len(reference.ranges), len(current.ranges))
    valid, x, y, degenerate, yaw_rad, raw_residual_rms, raw_max_abs_residual, inliers = _estimate_for_best_yaw(
        reference,
        current,
        cfg,
        beam_count,
    )

    blockers: list[str] = []
    if len(valid) < cfg.min_valid_beams:
        blockers.append("scan_reference_valid_beams_low")
    if degenerate:
        blockers.append("scan_reference_geometry_degenerate")

    residuals = _residuals(inliers, x, y)
    residual_rms = _rms(residuals)
    max_abs_residual = max((abs(r) for r in residuals), default=0.0)
    inlier_ratio = float(len(inliers)) / float(len(valid)) if valid else 0.0
    horizontal = math.hypot(x, y)
    if len(inliers) < cfg.min_valid_beams or inlier_ratio < cfg.min_inlier_ratio:
        blockers.append("scan_reference_inlier_ratio_low")
    if residual_rms > cfg.max_residual_rms_m:
        blockers.append("scan_reference_residual_high")
    if horizontal > cfg.max_horizontal_drift_m:
        blockers.append("scan_reference_horizontal_drift_implausible")

    ready = len(valid) > 0 and "scan_reference_geometry_degenerate" not in blockers
    return ScanReferenceEstimate(
        x_m=x,
        y_m=y,
        valid_beams=len(valid),
        total_beams=beam_count,
        residual_rms_m=residual_rms,
        max_abs_residual_m=max_abs_residual,
        raw_residual_rms_m=raw_residual_rms,
        raw_max_abs_residual_m=raw_max_abs_residual,
        inlier_beams=len(inliers),
        inlier_ratio=inlier_ratio,
        horizontal_drift_m=horizontal,
        stamp_sec=current.stamp_sec,
        reference_stamp_sec=reference.stamp_sec,
        ready=ready,
        quality_good=ready and not blockers,
        blockers=tuple(blockers),
        yaw_rad=yaw_rad,
    )


def evaluate_correction_eligibility(
    history: Sequence[ScanReferenceEstimate],
    config: ScanReferenceDriftConfig | None = None,
    previous: ScanReferenceEstimate | None = None,
) -> ScanCorrectionEligibility:
    cfg = config or ScanReferenceDriftConfig()
    samples = list(history)[-max(2, cfg.eligibility_window_samples) :]
    latest = samples[-1] if samples else None
    blockers: list[str] = []
    if latest is None:
        return _eligibility(False, "none", (), (), 0.0, 0.0, 0.0, None, 0, 0, 0, ("scan_reference_no_estimate",))
    if not latest.quality_good:
        blockers.append("scan_reference_quality_not_good")
    if len(samples) < cfg.min_stable_samples:
        blockers.append("scan_reference_stable_window_short")

    velocity = _estimate_velocity(latest, previous)
    if velocity > cfg.max_velocity_mps:
        blockers.append("scan_reference_velocity_too_high")

    direction_cosine_min = _min_direction_cosine(samples, cfg.axis_deadband_m)
    if direction_cosine_min is not None and direction_cosine_min < cfg.min_direction_cosine:
        blockers.append("scan_reference_direction_not_continuous")

    x_signs = _axis_signs(samples, "x", cfg.axis_deadband_m)
    y_signs = _axis_signs(samples, "y", cfg.axis_deadband_m)
    x_flips = _sign_flips(x_signs)
    y_flips = _sign_flips(y_signs)
    allowed_axes: list[str] = []
    if _axis_stable(samples, "x", cfg, x_flips):
        allowed_axes.append("x")
    if _axis_stable(samples, "y", cfg, y_flips):
        allowed_axes.append("y")
    if not allowed_axes:
        blockers.append("scan_reference_no_stable_axis")

    stable_axes = tuple(allowed_axes)
    correction_allowed = not blockers and bool(stable_axes)
    allowed_axes_tuple = stable_axes if correction_allowed else ()
    mode = "xy" if correction_allowed and len(allowed_axes_tuple) == 2 else "axis" if correction_allowed else "none"
    projection_x = latest.x_m if "x" in allowed_axes_tuple else 0.0
    projection_y = latest.y_m if "y" in allowed_axes_tuple else 0.0
    norm = math.hypot(projection_x, projection_y)
    if norm > 1e-9:
        projection_x /= norm
        projection_y /= norm
    else:
        projection_x = projection_y = 0.0
    return _eligibility(
        correction_allowed,
        mode,
        allowed_axes_tuple,
        stable_axes,
        projection_x,
        projection_y,
        velocity,
        direction_cosine_min,
        len(samples),
        x_flips,
        y_flips,
        tuple(dict.fromkeys(blockers)),
    )


def evaluate_correction_intent(
    estimate: ScanReferenceEstimate,
    config: ScanReferenceDriftConfig | None = None,
    *,
    consecutive_allowed_samples: int,
    hover_phase: str,
) -> ScanCorrectionIntent:
    cfg = config or ScanReferenceDriftConfig()
    eligibility = estimate.correction_eligibility
    blockers: list[str] = []
    if not cfg.correction_intent_shadow_enabled:
        blockers.append("scan_reference_correction_intent_shadow_disabled")
    if hover_phase not in CORRECTION_PHASES:
        blockers.append("scan_reference_correction_intent_not_hover_hold")
    if eligibility is None:
        blockers.append("scan_reference_correction_eligibility_missing")
    elif not eligibility.correction_allowed:
        blockers.append("scan_reference_correction_not_allowed")
    required = max(1, cfg.min_correction_intent_consecutive_allowed_samples)
    if consecutive_allowed_samples < required:
        blockers.append("scan_reference_correction_consecutive_window_short")
    phase4b_consistency = evaluate_runtime_phase4b_consistency(estimate, cfg)
    phase4b_consistency_ok = bool(phase4b_consistency["ok"])
    if not phase4b_consistency_ok:
        blockers.append("scan_reference_correction_phase4b_consistency_not_ok")

    axes = () if eligibility is None else eligibility.allowed_axes
    mode = "none" if eligibility is None else eligibility.allowed_mode
    source_x = estimate.x_m if "x" in axes else 0.0
    source_y = estimate.y_m if "y" in axes else 0.0
    correction_x = -source_x * cfg.correction_intent_gain
    correction_y = -source_y * cfg.correction_intent_gain
    correction_x, correction_y = _clamp_vector(correction_x, correction_y, cfg.max_correction_intent_m)
    magnitude = math.hypot(correction_x, correction_y)
    unit_x = correction_x / magnitude if magnitude > 1e-9 else 0.0
    unit_y = correction_y / magnitude if magnitude > 1e-9 else 0.0
    active = not blockers and magnitude > 0.0
    if not active:
        correction_x = correction_y = magnitude = unit_x = unit_y = 0.0
        mode = "none"
        axes = ()

    return ScanCorrectionIntent(
        shadow_only=True,
        active=active,
        mode=mode,
        axes=axes,
        correction_x_m=correction_x,
        correction_y_m=correction_y,
        correction_magnitude_m=magnitude,
        unit_x=unit_x,
        unit_y=unit_y,
        source_x_m=source_x,
        source_y_m=source_y,
        consecutive_allowed_samples=consecutive_allowed_samples,
        required_consecutive_allowed_samples=required,
        max_correction_m=cfg.max_correction_intent_m,
        gain=cfg.correction_intent_gain,
        phase4b_consistency_ok=phase4b_consistency_ok,
        phase4b_consistency_source="scan_reference_runtime_window",
        phase4b_consistency=phase4b_consistency,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def evaluate_runtime_phase4b_consistency(
    estimate: ScanReferenceEstimate,
    config: ScanReferenceDriftConfig | None = None,
) -> dict[str, object]:
    cfg = config or ScanReferenceDriftConfig()
    eligibility = estimate.correction_eligibility
    blockers: list[str] = []
    if eligibility is None:
        blockers.append("scan_reference_phase4b_eligibility_missing")
    elif not eligibility.correction_allowed:
        blockers.append("scan_reference_phase4b_eligibility_not_allowed")
    if not estimate.quality_good:
        blockers.append("scan_reference_phase4b_quality_not_good")

    direction_cosine_min = None if eligibility is None else eligibility.direction_cosine_min
    if direction_cosine_min is not None and direction_cosine_min < cfg.min_direction_cosine:
        blockers.append("scan_reference_phase4b_direction_not_continuous")

    x_flips = 0 if eligibility is None else eligibility.x_sign_flips
    y_flips = 0 if eligibility is None else eligibility.y_sign_flips
    if x_flips > cfg.max_axis_sign_flips:
        blockers.append("scan_reference_phase4b_x_sign_flips")
    if y_flips > cfg.max_axis_sign_flips:
        blockers.append("scan_reference_phase4b_y_sign_flips")

    allowed_axes = () if eligibility is None else eligibility.allowed_axes
    source_x = estimate.x_m if "x" in allowed_axes else 0.0
    source_y = estimate.y_m if "y" in allowed_axes else 0.0
    raw_correction_magnitude = math.hypot(source_x * cfg.correction_intent_gain, source_y * cfg.correction_intent_gain)
    saturated = cfg.max_correction_intent_m > 0.0 and raw_correction_magnitude >= cfg.max_correction_intent_m * 0.98
    saturation_ratio = 1.0 if saturated else 0.0
    if saturation_ratio > cfg.max_phase4b_saturation_ratio:
        blockers.append("scan_reference_phase4b_saturation_ratio_high")

    return {
        "ok": len(blockers) == 0,
        "source": "scan_reference_runtime_window",
        "blockers": tuple(dict.fromkeys(blockers)),
        "allowed_axes": allowed_axes,
        "stable_axes": () if eligibility is None else eligibility.stable_axes,
        "direction_cosine_min": direction_cosine_min,
        "x_sign_flips": x_flips,
        "y_sign_flips": y_flips,
        "saturation_ratio": saturation_ratio,
        "max_allowed_saturation_ratio": cfg.max_phase4b_saturation_ratio,
        "raw_correction_magnitude_m": raw_correction_magnitude,
        "max_correction_m": cfg.max_correction_intent_m,
        "uses_gazebo_truth_input": False,
        "uses_known_map_input": False,
    }


def _with_eligibility(estimate: ScanReferenceEstimate, eligibility: ScanCorrectionEligibility) -> ScanReferenceEstimate:
    return ScanReferenceEstimate(
        x_m=estimate.x_m,
        y_m=estimate.y_m,
        valid_beams=estimate.valid_beams,
        total_beams=estimate.total_beams,
        residual_rms_m=estimate.residual_rms_m,
        max_abs_residual_m=estimate.max_abs_residual_m,
        raw_residual_rms_m=estimate.raw_residual_rms_m,
        raw_max_abs_residual_m=estimate.raw_max_abs_residual_m,
        inlier_beams=estimate.inlier_beams,
        inlier_ratio=estimate.inlier_ratio,
        horizontal_drift_m=estimate.horizontal_drift_m,
        stamp_sec=estimate.stamp_sec,
        reference_stamp_sec=estimate.reference_stamp_sec,
        ready=estimate.ready,
        quality_good=estimate.quality_good,
        blockers=estimate.blockers,
        correction_eligibility=eligibility,
        yaw_rad=estimate.yaw_rad,
    )


def _eligibility(
    correction_allowed: bool,
    allowed_mode: str,
    allowed_axes: tuple[str, ...],
    stable_axes: tuple[str, ...],
    projection_x: float,
    projection_y: float,
    latest_velocity_mps: float,
    direction_cosine_min: float | None,
    stable_sample_count: int,
    x_sign_flips: int,
    y_sign_flips: int,
    blockers: tuple[str, ...],
) -> ScanCorrectionEligibility:
    return ScanCorrectionEligibility(
        correction_allowed=correction_allowed,
        allowed_mode=allowed_mode,
        allowed_axes=allowed_axes,
        stable_axes=stable_axes,
        projection_x=projection_x,
        projection_y=projection_y,
        latest_velocity_mps=latest_velocity_mps,
        direction_cosine_min=direction_cosine_min,
        stable_sample_count=stable_sample_count,
        x_sign_flips=x_sign_flips,
        y_sign_flips=y_sign_flips,
        blockers=blockers,
    )


def _estimate_velocity(latest: ScanReferenceEstimate, previous: ScanReferenceEstimate | None) -> float:
    if previous is None:
        return 0.0
    dt = latest.stamp_sec - previous.stamp_sec
    if dt <= 1e-6:
        return 0.0
    return math.hypot(latest.x_m - previous.x_m, latest.y_m - previous.y_m) / dt


def _axis_signs(samples: Sequence[ScanReferenceEstimate], axis: str, deadband: float) -> list[int]:
    signs: list[int] = []
    for sample in samples:
        value = sample.x_m if axis == "x" else sample.y_m
        if abs(value) <= deadband:
            continue
        signs.append(1 if value > 0 else -1)
    return signs


def _sign_flips(signs: Sequence[int]) -> int:
    return sum(1 for left, right in zip(signs, signs[1:]) if left != right)


def _axis_stable(
    samples: Sequence[ScanReferenceEstimate],
    axis: str,
    cfg: ScanReferenceDriftConfig,
    flips: int,
) -> bool:
    if len(samples) < cfg.min_stable_samples or flips > cfg.max_axis_sign_flips:
        return False
    signs = _axis_signs(samples, axis, cfg.axis_deadband_m)
    if len(signs) < cfg.min_stable_samples:
        return False
    latest = samples[-1].x_m if axis == "x" else samples[-1].y_m
    return abs(latest) >= cfg.min_axis_drift_m


def _min_direction_cosine(samples: Sequence[ScanReferenceEstimate], deadband: float) -> float | None:
    vectors = [(s.x_m, s.y_m) for s in samples if math.hypot(s.x_m, s.y_m) > deadband]
    if len(vectors) < 3:
        return None
    values: list[float] = []
    for left, right in zip(vectors, vectors[1:]):
        left_norm = math.hypot(*left)
        right_norm = math.hypot(*right)
        if left_norm <= 1e-9 or right_norm <= 1e-9:
            continue
        values.append((left[0] * right[0] + left[1] * right[1]) / (left_norm * right_norm))
    return min(values) if values else None


def _solve_translation(samples: Sequence[tuple[float, float, float]]) -> tuple[float, float, bool]:
    a00 = a01 = a11 = 0.0
    b0 = b1 = 0.0
    for delta_range, ux, uy in samples:
        a00 += ux * ux
        a01 += ux * uy
        a11 += uy * uy
        b0 += -ux * delta_range
        b1 += -uy * delta_range
    determinant = a00 * a11 - a01 * a01
    if abs(determinant) < 1e-9:
        return 0.0, 0.0, True
    x = (b0 * a11 - b1 * a01) / determinant
    y = (a00 * b1 - a01 * b0) / determinant
    return x, y, False


def _estimate_for_best_yaw(
    reference: ScanReferenceSample,
    current: ScanReferenceSample,
    cfg: ScanReferenceDriftConfig,
    beam_count: int,
) -> tuple[list[tuple[float, float, float]], float, float, bool, float, float, float, list[tuple[float, float, float]]]:
    best: (
        tuple[
            float,
            float,
            int,
            list[tuple[float, float, float]],
            float,
            float,
            bool,
            float,
            float,
            float,
            list[tuple[float, float, float]],
        ]
        | None
    ) = None
    for yaw_rad in _yaw_candidates(cfg):
        valid = _valid_correspondences_for_yaw(reference, current, cfg, beam_count, yaw_rad)
        x, y, degenerate = _solve_translation(valid)
        raw_residuals = _residuals(valid, x, y)
        raw_residual_rms = _rms(raw_residuals)
        raw_max_abs_residual = max((abs(r) for r in raw_residuals), default=0.0)
        inliers = valid
        for _ in range(max(1, cfg.robust_iterations)):
            residuals_for_filter = _residuals(inliers, x, y)
            filtered = [
                item
                for item, residual in zip(inliers, residuals_for_filter)
                if abs(residual) <= cfg.max_inlier_residual_m
            ]
            if len(filtered) < 3 or len(filtered) == len(inliers):
                break
            candidate_x, candidate_y, candidate_degenerate = _solve_translation(filtered)
            if candidate_degenerate:
                break
            inliers = filtered
            x, y = candidate_x, candidate_y
        residual_rms = _rms(_residuals(inliers, x, y))
        # Prefer lower residuals, then more inliers, then smaller yaw. This keeps
        # the estimator fail-closed without turning yaw into an unbounded prior.
        score = residual_rms + (0.05 if degenerate else 0.0) + 0.001 * abs(yaw_rad)
        candidate = (
            score,
            abs(yaw_rad),
            len(inliers),
            valid,
            x,
            y,
            degenerate,
            yaw_rad,
            raw_residual_rms,
            raw_max_abs_residual,
            inliers,
        )
        if (
            best is None
            or candidate[0] < best[0]
            or (
                math.isclose(candidate[0], best[0], abs_tol=1e-9)
                and (candidate[2], -candidate[1]) > (best[2], -best[1])
            )
        ):
            best = candidate
    if best is None:
        return [], 0.0, 0.0, True, 0.0, 0.0, 0.0, []
    return best[3], best[4], best[5], best[6], best[7], best[8], best[9], best[10]


def _yaw_candidates(cfg: ScanReferenceDriftConfig) -> tuple[float, ...]:
    window = max(0.0, float(cfg.yaw_search_window_rad))
    steps = max(1, int(cfg.yaw_search_steps))
    if window <= 0.0 or steps <= 1:
        return (0.0,)
    if steps % 2 == 0:
        steps += 1
    center = steps // 2
    step = window / float(center)
    return tuple((idx - center) * step for idx in range(steps))


def _valid_correspondences_for_yaw(
    reference: ScanReferenceSample,
    current: ScanReferenceSample,
    cfg: ScanReferenceDriftConfig,
    beam_count: int,
    yaw_rad: float,
) -> list[tuple[float, float, float]]:
    valid: list[tuple[float, float, float]] = []
    for idx in range(beam_count):
        cur_range = current.ranges[idx]
        if not _range_valid(cur_range, current.range_min, current.range_max):
            continue
        theta = current.angle_min + float(idx) * current.angle_increment + yaw_rad
        ref_range = _interpolate_reference_range(reference, theta)
        if ref_range is None:
            continue
        delta_range = cur_range - ref_range
        if abs(delta_range) > cfg.max_range_delta_m:
            continue
        ux = math.cos(theta)
        uy = math.sin(theta)
        valid.append((delta_range, ux, uy))
    return valid


def _interpolate_reference_range(reference: ScanReferenceSample, theta: float) -> float | None:
    if not reference.ranges or abs(reference.angle_increment) <= 1e-12:
        return None
    beam_count = len(reference.ranges)
    span = abs(reference.angle_increment) * float(max(0, beam_count - 1))
    start = reference.angle_min
    rel = theta - start
    if span >= (2.0 * math.pi - 2.5 * abs(reference.angle_increment)):
        period = abs(reference.angle_increment) * float(beam_count)
        rel = rel % period
    idx_float = rel / reference.angle_increment
    if idx_float < 0.0 or idx_float > float(beam_count - 1):
        return None
    lower = int(math.floor(idx_float))
    upper = min(beam_count - 1, lower + 1)
    lower_range = reference.ranges[lower]
    upper_range = reference.ranges[upper]
    if not _range_valid(lower_range, reference.range_min, reference.range_max):
        return None
    if upper == lower or not _range_valid(upper_range, reference.range_min, reference.range_max):
        return lower_range
    weight = idx_float - float(lower)
    return lower_range * (1.0 - weight) + upper_range * weight


def _residuals(samples: Sequence[tuple[float, float, float]], x: float, y: float) -> list[float]:
    return [delta + ux * x + uy * y for delta, ux, uy in samples]


def _rms(values: Sequence[float]) -> float:
    return math.sqrt(sum(v * v for v in values) / len(values)) if values else 0.0


def _clamp_vector(x: float, y: float, max_magnitude: float) -> tuple[float, float]:
    limit = max(0.0, max_magnitude)
    magnitude = math.hypot(x, y)
    if limit <= 0.0 or magnitude <= limit or magnitude <= 1e-9:
        return x, y
    scale = limit / magnitude
    return x * scale, y * scale


def _range_valid(value: float, range_min: float, range_max: float) -> bool:
    return not math.isnan(value) and not math.isinf(value) and range_min <= value <= range_max
