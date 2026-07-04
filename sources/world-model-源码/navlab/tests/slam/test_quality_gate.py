from __future__ import annotations

from navlab.common.slam.quality_gate import SlamQualityInputs, evaluate_slam_quality


def test_slam_quality_accepts_healthy_odom_scan_imu() -> None:
    result = evaluate_slam_quality(SlamQualityInputs())

    assert result.quality == "good"
    assert result.reason == "healthy"
    assert result.good is True


def test_slam_quality_marks_stale_odom() -> None:
    result = evaluate_slam_quality(SlamQualityInputs(odom_fresh=False))

    assert result.quality == "stale"
    assert result.reason == "odom_stale"
    assert result.good is False


def test_slam_quality_rejects_low_odom_rate() -> None:
    result = evaluate_slam_quality(SlamQualityInputs(odom_rate_hz=1.0))

    assert result.quality == "bad"
    assert result.reason == "odom_rate_low"


def test_slam_quality_rejects_frame_mismatch() -> None:
    result = evaluate_slam_quality(SlamQualityInputs(frame_ok=False))

    assert result.quality == "bad"
    assert result.reason == "frame_mismatch"


def test_slam_quality_marks_pose_or_yaw_jump() -> None:
    result = evaluate_slam_quality(SlamQualityInputs(jump_active=True))

    assert result.quality == "jump"
    assert result.reason == "pose_or_yaw_jump"


def test_slam_quality_marks_low_observability_uncertain() -> None:
    result = evaluate_slam_quality(
        SlamQualityInputs(
            low_observability_mode=True,
            horizontal_span_m=0.02,
            scan_range_span_m=0.05,
            scan_range_stddev_m=0.01,
        )
    )

    assert result.quality == "uncertain"
    assert result.reason == "low_observability_horizontal_span"
    assert result.good is False


def test_slam_quality_accepts_low_motion_when_scan_geometry_is_observable() -> None:
    result = evaluate_slam_quality(
        SlamQualityInputs(
            low_observability_mode=True,
            horizontal_span_m=0.02,
            scan_valid_ratio=0.95,
            scan_hit_ratio=0.89,
            scan_range_span_m=7.0,
            scan_range_stddev_m=2.0,
            scan_observed_quadrants=4,
        )
    )

    assert result.quality == "good"
    assert result.reason == "healthy_scan_geometry"
    assert result.good is True


def test_slam_quality_rejects_single_wall_scan_geometry() -> None:
    result = evaluate_slam_quality(
        SlamQualityInputs(
            low_observability_mode=True,
            horizontal_span_m=0.02,
            scan_valid_ratio=0.95,
            scan_hit_ratio=0.80,
            scan_range_span_m=2.0,
            scan_range_stddev_m=0.5,
            scan_observed_quadrants=1,
        )
    )

    assert result.quality == "uncertain"
    assert result.reason == "low_observability_horizontal_span"


def test_slam_quality_rejects_missing_or_stale_scan_and_imu() -> None:
    assert evaluate_slam_quality(SlamQualityInputs(scan_present=False)).reason == "scan_missing"
    assert evaluate_slam_quality(SlamQualityInputs(scan_fresh=False)).quality == "stale"
    assert evaluate_slam_quality(SlamQualityInputs(imu_present=False)).reason == "imu_missing"
    assert evaluate_slam_quality(SlamQualityInputs(imu_fresh=False)).quality == "stale"
