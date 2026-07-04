from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SlamQualityInputs:
    odom_present: bool = True
    odom_fresh: bool = True
    odom_rate_hz: float = 10.0
    min_odom_rate_hz: float = 4.0
    frame_ok: bool = True
    imu_present: bool = True
    imu_fresh: bool = True
    imu_rate_hz: float = 100.0
    min_imu_rate_hz: float = 4.0
    scan_present: bool = True
    scan_fresh: bool = True
    scan_rate_hz: float = 7.0
    min_scan_rate_hz: float = 2.0
    require_imu_for_quality: bool = True
    require_scan_for_quality: bool = True
    jump_active: bool = False
    low_observability_mode: bool = False
    horizontal_span_m: float = 1.0
    min_observable_horizontal_span_m: float = 0.10
    scan_valid_ratio: float = 0.95
    min_scan_valid_ratio_for_quality: float = 0.50
    scan_hit_ratio: float = 0.85
    min_scan_hit_ratio_for_quality: float = 0.25
    scan_range_span_m: float = 2.0
    min_scan_range_span_m_for_quality: float = 1.0
    scan_range_stddev_m: float = 0.5
    min_scan_range_stddev_m_for_quality: float = 0.20
    scan_observed_quadrants: int = 4
    min_scan_observed_quadrants_for_quality: int = 3


@dataclass(frozen=True, slots=True)
class SlamQualityResult:
    quality: str
    reason: str
    good: bool


def evaluate_slam_quality(inputs: SlamQualityInputs) -> SlamQualityResult:
    if not inputs.odom_present:
        return SlamQualityResult("bad", "odom_missing", False)
    if not inputs.odom_fresh:
        return SlamQualityResult("stale", "odom_stale", False)
    if not inputs.frame_ok:
        return SlamQualityResult("bad", "frame_mismatch", False)
    if inputs.odom_rate_hz < inputs.min_odom_rate_hz:
        return SlamQualityResult("bad", "odom_rate_low", False)
    if inputs.jump_active:
        return SlamQualityResult("jump", "pose_or_yaw_jump", False)
    if inputs.require_imu_for_quality:
        if not inputs.imu_present:
            return SlamQualityResult("bad", "imu_missing", False)
        if not inputs.imu_fresh:
            return SlamQualityResult("stale", "imu_stale", False)
        if inputs.imu_rate_hz < inputs.min_imu_rate_hz:
            return SlamQualityResult("bad", "imu_rate_low", False)
    if inputs.require_scan_for_quality:
        if not inputs.scan_present:
            return SlamQualityResult("bad", "scan_missing", False)
        if not inputs.scan_fresh:
            return SlamQualityResult("stale", "scan_stale", False)
        if inputs.scan_rate_hz < inputs.min_scan_rate_hz:
            return SlamQualityResult("bad", "scan_rate_low", False)
    scan_geometry_observable = (
        inputs.scan_valid_ratio >= inputs.min_scan_valid_ratio_for_quality
        and inputs.scan_hit_ratio >= inputs.min_scan_hit_ratio_for_quality
        and inputs.scan_range_span_m >= inputs.min_scan_range_span_m_for_quality
        and inputs.scan_range_stddev_m >= inputs.min_scan_range_stddev_m_for_quality
        and inputs.scan_observed_quadrants >= inputs.min_scan_observed_quadrants_for_quality
    )
    if (
        inputs.low_observability_mode
        and inputs.horizontal_span_m < inputs.min_observable_horizontal_span_m
        and not scan_geometry_observable
    ):
        return SlamQualityResult("uncertain", "low_observability_horizontal_span", False)
    if inputs.low_observability_mode and inputs.horizontal_span_m < inputs.min_observable_horizontal_span_m:
        return SlamQualityResult("good", "healthy_scan_geometry", True)
    return SlamQualityResult("good", "healthy", True)
