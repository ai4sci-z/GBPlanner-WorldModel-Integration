from __future__ import annotations

import math

from navlab.sim.gazebo_sensor.scan_integrity import evaluate_scan_quality, quaternion_to_rpy_deg


def test_quaternion_to_rpy_deg_identity() -> None:
    roll, pitch, yaw = quaternion_to_rpy_deg(0.0, 0.0, 0.0, 1.0)

    assert roll == 0.0
    assert pitch == 0.0
    assert yaw == 0.0


def test_scan_quality_accepts_level_scan() -> None:
    quality = evaluate_scan_quality(
        ranges=[2.0] * 360,
        angle_min=-math.pi,
        angle_increment=2.0 * math.pi / 360.0,
        range_max=8.0,
        roll_deg=0.5,
        pitch_deg=0.5,
        lidar_height_m=0.5,
        soft_tilt_deg=3.0,
        hard_tilt_deg=6.0,
        max_clipped_beam_ratio=0.2,
        floor_hit_guard_range_m=8.0,
        min_downward_ray_z=0.05,
    )

    assert quality.state == "accept"
    assert quality.unsafe_indices == ()


def test_scan_quality_warns_on_soft_tilt() -> None:
    quality = evaluate_scan_quality(
        ranges=[1.0] * 36,
        angle_min=-math.pi,
        angle_increment=2.0 * math.pi / 36.0,
        range_max=8.0,
        roll_deg=3.2,
        pitch_deg=0.0,
        lidar_height_m=0.5,
        soft_tilt_deg=3.0,
        hard_tilt_deg=6.0,
        max_clipped_beam_ratio=0.9,
        floor_hit_guard_range_m=8.0,
        min_downward_ray_z=0.2,
    )

    assert quality.state == "warn"


def test_scan_quality_drops_on_hard_tilt() -> None:
    quality = evaluate_scan_quality(
        ranges=[2.0] * 360,
        angle_min=-math.pi,
        angle_increment=2.0 * math.pi / 360.0,
        range_max=8.0,
        roll_deg=0.0,
        pitch_deg=7.0,
        lidar_height_m=0.5,
        soft_tilt_deg=3.0,
        hard_tilt_deg=6.0,
        max_clipped_beam_ratio=0.2,
        floor_hit_guard_range_m=8.0,
        min_downward_ray_z=0.05,
    )

    assert quality.state == "drop"
    assert "hard_tilt_exceeded" in quality.blockers


def test_scan_quality_clips_floor_risk() -> None:
    quality = evaluate_scan_quality(
        ranges=[8.0] * 360,
        angle_min=-math.pi,
        angle_increment=2.0 * math.pi / 360.0,
        range_max=8.0,
        roll_deg=2.0,
        pitch_deg=2.0,
        lidar_height_m=0.3,
        soft_tilt_deg=3.0,
        hard_tilt_deg=6.0,
        max_clipped_beam_ratio=0.8,
        floor_hit_guard_range_m=8.0,
        min_downward_ray_z=0.02,
    )

    assert quality.state == "clip"
    assert quality.floor_hit_risk_beam_ratio > 0.0
