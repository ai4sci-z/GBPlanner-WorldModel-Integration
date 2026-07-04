from __future__ import annotations

import math

import pytest

from navlab.sim.gazebo_sensor.scan_stabilization import (
    angle_to_scan_bin,
    scan_attitude_time_offset_ms,
    stabilize_scan_ranges,
    validate_scan_stabilization_thresholds,
)


def _quality(*, roll: float = 0.0, pitch: float = 0.0, ranges: list[float] | None = None):
    return stabilize_scan_ranges(
        ranges=ranges or [1.0] * 36,
        angle_min=-math.pi,
        angle_increment=2.0 * math.pi / 36.0,
        range_min=0.1,
        range_max=8.0,
        roll_deg=roll,
        pitch_deg=pitch,
        lidar_height_m=0.5,
        passthrough_tilt_deg=3.0,
        compensation_tilt_deg=8.0,
        hard_drop_tilt_deg=10.0,
        max_vertical_projection_error_m=0.20,
        max_rejected_beam_ratio=0.8,
        min_retained_beam_ratio=0.1,
        max_floor_hit_risk_beam_ratio=0.8,
        floor_hit_guard_range_m=8.0,
        min_downward_ray_z=0.2,
    )


def test_stabilization_passthrough_for_small_tilt() -> None:
    quality = _quality(roll=1.0, pitch=0.5)

    assert quality.state == "passthrough"
    assert quality.retained_beam_ratio == 1.0
    assert quality.rejected_beam_ratio == 0.0


def test_stabilization_compensates_medium_tilt() -> None:
    quality = _quality(roll=4.0, pitch=0.0)

    assert quality.state == "compensate"
    assert quality.retained_beam_ratio > 0.0
    assert quality.max_vertical_projection_error_m > 0.0


def test_stabilization_drops_hard_tilt() -> None:
    quality = _quality(roll=11.0, pitch=0.0)

    assert quality.state == "drop"
    assert "hard_tilt_exceeded" in quality.blockers


def test_stabilization_rejects_floor_hit_risk() -> None:
    quality = stabilize_scan_ranges(
        ranges=[8.0] * 36,
        angle_min=-math.pi,
        angle_increment=2.0 * math.pi / 36.0,
        range_min=0.1,
        range_max=8.0,
        roll_deg=4.0,
        pitch_deg=4.0,
        lidar_height_m=0.3,
        passthrough_tilt_deg=3.0,
        compensation_tilt_deg=8.0,
        hard_drop_tilt_deg=10.0,
        max_vertical_projection_error_m=2.0,
        max_rejected_beam_ratio=1.0,
        min_retained_beam_ratio=0.0,
        max_floor_hit_risk_beam_ratio=1.0,
        floor_hit_guard_range_m=8.0,
        min_downward_ray_z=0.02,
    )

    assert quality.floor_hit_rejected_count > 0
    assert quality.floor_hit_risk_beam_ratio > 0.0


def test_stabilization_validates_threshold_order() -> None:
    blockers = validate_scan_stabilization_thresholds(
        passthrough_tilt_deg=8.0,
        compensation_tilt_deg=3.0,
        hard_drop_tilt_deg=10.0,
        max_vertical_projection_error_m=0.15,
        max_rejected_beam_ratio=0.5,
        min_retained_beam_ratio=0.5,
        max_floor_hit_risk_beam_ratio=0.1,
    )

    assert any("tilt thresholds" in blocker for blocker in blockers)


def test_stabilization_wraps_full_scan_angle_bins() -> None:
    assert (
        angle_to_scan_bin(angle_rad=math.pi, angle_min=-math.pi, angle_increment=2.0 * math.pi / 36.0, beam_count=36)
        == 0
    )
    assert (
        angle_to_scan_bin(angle_rad=-math.pi, angle_min=-math.pi, angle_increment=2.0 * math.pi / 36.0, beam_count=36)
        == 0
    )


def test_stabilization_reports_scan_attitude_time_offset_ms() -> None:
    assert scan_attitude_time_offset_ms(scan_stamp_sec=10.125, attitude_stamp_sec=10.100) == pytest.approx(25.0)
    assert scan_attitude_time_offset_ms(scan_stamp_sec=0.0, attitude_stamp_sec=10.100) == 0.0
