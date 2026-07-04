from __future__ import annotations

import math

import pytest

from navlab.common.perception.scan_reference_drift import (
    ScanReferenceDriftConfig,
    ScanReferenceDriftEstimator,
    estimate_scan_reference_translation,
    evaluate_correction_intent,
    sample_from_scan_fields,
)
from navlab.sim.companion.nodes.scan_reference_drift import should_reset_reference_on_phase


def _scan_for_translation(x: float, y: float, *, beams: int = 360) -> list[float]:
    ranges: list[float] = []
    angle_min = -math.pi
    angle_increment = 2.0 * math.pi / beams
    for idx in range(beams):
        theta = angle_min + idx * angle_increment
        ranges.append(5.0 - math.cos(theta) * x - math.sin(theta) * y)
    return ranges


def _sample(x: float, y: float, *, stamp: float = 0.0, beams: int = 360):
    return sample_from_scan_fields(
        ranges=_scan_for_translation(x, y, beams=beams),
        angle_min=-math.pi,
        angle_increment=2.0 * math.pi / beams,
        range_min=0.05,
        range_max=8.0,
        stamp_sec=stamp,
        frame_id="laser_frame",
    )


def _textured_range(theta: float) -> float:
    return 4.0 + 0.35 * math.cos(2.0 * theta) + 0.18 * math.sin(3.0 * theta)


def _yawed_sample(x: float, y: float, yaw: float, *, stamp: float = 0.0, beams: int = 360):
    angle_min = -math.pi
    angle_increment = 2.0 * math.pi / beams
    ranges = []
    for idx in range(beams):
        theta = angle_min + idx * angle_increment
        shifted = theta + yaw
        ranges.append(_textured_range(shifted) - math.cos(shifted) * x - math.sin(shifted) * y)
    return sample_from_scan_fields(
        ranges=ranges,
        angle_min=angle_min,
        angle_increment=angle_increment,
        range_min=0.05,
        range_max=8.0,
        stamp_sec=stamp,
        frame_id="laser_frame",
    )


def test_scan_reference_estimator_recovers_translation_from_ranges_only() -> None:
    estimator = ScanReferenceDriftEstimator(ScanReferenceDriftConfig(min_valid_beams=40))
    first = estimator.update(_sample(0.0, 0.0, stamp=1.0))
    assert not first.ready

    estimate = estimator.update(_sample(0.3, -0.2, stamp=2.0))

    assert estimate.quality_good
    assert estimate.valid_beams == 360
    assert estimate.x_m == pytest.approx(0.3, abs=1e-6)
    assert estimate.y_m == pytest.approx(-0.2, abs=1e-6)
    assert estimate.horizontal_drift_m == pytest.approx(math.hypot(0.3, -0.2), abs=1e-6)
    assert estimate.residual_rms_m < 1e-9


def test_scan_reference_estimator_recovers_translation_with_small_yaw() -> None:
    estimator = ScanReferenceDriftEstimator(
        ScanReferenceDriftConfig(
            min_valid_beams=40,
            yaw_search_window_rad=0.10,
            yaw_search_steps=11,
        )
    )
    estimator.update(_yawed_sample(0.0, 0.0, 0.0, stamp=1.0))

    estimate = estimator.update(_yawed_sample(0.22, -0.14, 0.04, stamp=2.0))

    assert estimate.quality_good
    assert estimate.x_m == pytest.approx(0.22, abs=0.02)
    assert estimate.y_m == pytest.approx(-0.14, abs=0.02)
    assert estimate.yaw_rad == pytest.approx(0.04, abs=0.02)
    assert estimate.residual_rms_m < 0.03


def test_scan_reference_quality_blocks_low_observability_samples() -> None:
    estimator = ScanReferenceDriftEstimator(ScanReferenceDriftConfig(min_valid_beams=40))
    estimator.update(_sample(0.0, 0.0, beams=8))

    estimate = estimator.update(_sample(0.1, 0.0, beams=8))

    assert not estimate.quality_good
    assert "scan_reference_valid_beams_low" in estimate.blockers


def test_scan_reference_reset_uses_new_reference() -> None:
    estimator = ScanReferenceDriftEstimator(ScanReferenceDriftConfig(min_valid_beams=40))
    estimator.update(_sample(0.0, 0.0, stamp=1.0))
    estimator.update(_sample(0.4, 0.0, stamp=2.0))

    estimator.reset()
    first_after_reset = estimator.update(_sample(0.4, 0.0, stamp=3.0))
    after_reset = estimator.update(_sample(0.5, 0.0, stamp=4.0))

    assert not first_after_reset.ready
    assert after_reset.quality_good
    assert after_reset.x_m == pytest.approx(0.1, abs=1e-6)


def test_scan_reference_phase_reset_waits_for_first_hover_hold() -> None:
    reset, done = should_reset_reference_on_phase(
        reset_on_hover_hold=True,
        phase="hover_settle",
        hover_hold_reference_reset_done=False,
    )
    assert reset is False
    assert done is False

    reset, done = should_reset_reference_on_phase(
        reset_on_hover_hold=True,
        phase="hover_hold",
        hover_hold_reference_reset_done=done,
    )
    assert reset is True
    assert done is True

    reset, done = should_reset_reference_on_phase(
        reset_on_hover_hold=True,
        phase="hover_settle",
        hover_hold_reference_reset_done=done,
    )
    assert reset is False
    assert done is True

    reset, done = should_reset_reference_on_phase(
        reset_on_hover_hold=True,
        phase="hover_hold",
        hover_hold_reference_reset_done=done,
    )
    assert reset is False
    assert done is True


def test_scan_reference_phase_reset_rearms_outside_correction_phases() -> None:
    reset, done = should_reset_reference_on_phase(
        reset_on_hover_hold=True,
        phase="complete",
        hover_hold_reference_reset_done=True,
    )
    assert reset is False
    assert done is False


def test_correction_eligibility_allows_only_stable_axis_when_other_axis_flips() -> None:
    estimator = ScanReferenceDriftEstimator(
        ScanReferenceDriftConfig(min_valid_beams=40, min_stable_samples=4, eligibility_window_samples=5)
    )
    estimator.update(_sample(0.0, 0.0, stamp=1.0))

    estimate = None
    for idx, x in enumerate([0.08, -0.08, 0.07, -0.07, 0.06], start=2):
        estimate = estimator.update(_sample(x, 0.20 + idx * 0.02, stamp=float(idx)))

    assert estimate is not None
    eligibility = estimate.correction_eligibility
    assert eligibility is not None
    assert eligibility.correction_allowed
    assert eligibility.allowed_mode == "axis"
    assert eligibility.allowed_axes == ("y",)
    assert eligibility.x_sign_flips > 0
    assert eligibility.y_sign_flips == 0
    assert eligibility.projection_x == 0.0
    assert eligibility.projection_y == pytest.approx(1.0)


def test_correction_eligibility_blocks_when_velocity_is_implausible() -> None:
    estimator = ScanReferenceDriftEstimator(
        ScanReferenceDriftConfig(
            min_valid_beams=40,
            min_stable_samples=2,
            eligibility_window_samples=3,
            max_velocity_mps=0.2,
        )
    )
    estimator.update(_sample(0.0, 0.0, stamp=1.0))
    estimator.update(_sample(0.1, 0.0, stamp=2.0))
    estimate = estimator.update(_sample(1.0, 0.0, stamp=2.1))

    eligibility = estimate.correction_eligibility
    assert eligibility is not None
    assert not eligibility.correction_allowed
    assert eligibility.allowed_axes == ()
    assert "x" in eligibility.stable_axes
    assert "scan_reference_velocity_too_high" in eligibility.blockers


def test_correction_intent_is_fail_closed_until_hover_window_is_stable() -> None:
    estimator = ScanReferenceDriftEstimator(
        ScanReferenceDriftConfig(
            min_valid_beams=40,
            min_stable_samples=3,
            eligibility_window_samples=4,
            min_correction_intent_consecutive_allowed_samples=3,
            max_correction_intent_m=0.25,
        )
    )
    estimator.update(_sample(0.0, 0.0, stamp=1.0))
    estimate = None
    for idx in range(2, 6):
        estimate = estimator.update(_sample(0.2, 0.0, stamp=float(idx)))

    assert estimate is not None
    assert estimate.correction_eligibility is not None
    assert estimate.correction_eligibility.correction_allowed

    not_hover = evaluate_correction_intent(
        estimate,
        estimator.config,
        consecutive_allowed_samples=3,
        hover_phase="complete",
    )
    assert not not_hover.active
    assert not_hover.correction_magnitude_m == 0.0
    assert "scan_reference_correction_intent_not_hover_hold" in not_hover.blockers

    too_short = evaluate_correction_intent(
        estimate,
        estimator.config,
        consecutive_allowed_samples=2,
        hover_phase="hover_hold",
    )
    assert not too_short.active
    assert "scan_reference_correction_consecutive_window_short" in too_short.blockers

    active = evaluate_correction_intent(
        estimate,
        estimator.config,
        consecutive_allowed_samples=3,
        hover_phase="hover_hold",
    )
    assert active.shadow_only
    assert active.active
    assert active.axes == ("x",)
    assert active.phase4b_consistency_ok
    assert active.phase4b_consistency_source == "scan_reference_runtime_window"
    assert active.correction_x_m == pytest.approx(-0.2, abs=1e-6)
    assert active.correction_y_m == 0.0
    assert active.correction_magnitude_m == pytest.approx(0.2, abs=1e-6)
    assert active.source_x_m == pytest.approx(0.2, abs=1e-6)
    assert active.blockers == ()

    settle_active = evaluate_correction_intent(
        estimate,
        estimator.config,
        consecutive_allowed_samples=3,
        hover_phase="hover_settle",
    )
    assert settle_active.active
    assert settle_active.axes == ("x",)


def test_correction_intent_blocks_when_phase4b_runtime_window_is_saturated() -> None:
    estimator = ScanReferenceDriftEstimator(
        ScanReferenceDriftConfig(
            min_valid_beams=40,
            min_stable_samples=3,
            eligibility_window_samples=4,
            min_correction_intent_consecutive_allowed_samples=3,
            max_correction_intent_m=0.25,
        )
    )
    estimator.update(_sample(0.0, 0.0, stamp=1.0))
    estimate = None
    for idx in range(2, 6):
        estimate = estimator.update(_sample(0.4, 0.0, stamp=float(idx)))

    assert estimate is not None
    intent = evaluate_correction_intent(
        estimate,
        estimator.config,
        consecutive_allowed_samples=3,
        hover_phase="hover_hold",
    )

    assert not intent.active
    assert not intent.phase4b_consistency_ok
    assert "scan_reference_correction_phase4b_consistency_not_ok" in intent.blockers
    assert "scan_reference_phase4b_saturation_ratio_high" in intent.phase4b_consistency["blockers"]


def test_scan_reference_quality_keeps_good_estimate_with_sparse_outliers() -> None:
    reference = _sample(0.0, 0.0)
    current_ranges = _scan_for_translation(0.1, 0.0)
    current_ranges[0] += 1.0
    current_ranges[90] -= 1.0
    current = sample_from_scan_fields(
        ranges=current_ranges,
        angle_min=-math.pi,
        angle_increment=2.0 * math.pi / 360,
        range_min=0.05,
        range_max=8.0,
    )

    estimate = estimate_scan_reference_translation(
        reference,
        current,
        ScanReferenceDriftConfig(min_valid_beams=40, max_residual_rms_m=0.01),
    )

    assert estimate.quality_good
    assert estimate.x_m == pytest.approx(0.1, abs=1e-6)
    assert estimate.raw_residual_rms_m > estimate.residual_rms_m
    assert estimate.raw_max_abs_residual_m > estimate.max_abs_residual_m
    assert estimate.inlier_beams < estimate.valid_beams
    assert estimate.inlier_ratio > 0.95


def test_scan_reference_quality_blocks_when_outliers_dominate() -> None:
    reference = _sample(0.0, 0.0)
    current_ranges = _scan_for_translation(0.1, 0.0)
    for idx in range(220):
        current_ranges[idx] += 1.0 if idx % 2 == 0 else -1.0
    current = sample_from_scan_fields(
        ranges=current_ranges,
        angle_min=-math.pi,
        angle_increment=2.0 * math.pi / 360,
        range_min=0.05,
        range_max=8.0,
    )

    estimate = estimate_scan_reference_translation(
        reference,
        current,
        ScanReferenceDriftConfig(
            min_valid_beams=40,
            max_residual_rms_m=0.01,
            max_inlier_residual_m=0.35,
            min_inlier_ratio=0.45,
        ),
    )

    assert not estimate.quality_good
    assert "scan_reference_inlier_ratio_low" in estimate.blockers
    assert estimate.raw_residual_rms_m > estimate.residual_rms_m
