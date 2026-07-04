from __future__ import annotations

import math

from navlab.real.companion.nodes.height_estimator import estimate_relative_height, parse_args


def test_height_estimator_defaults_publish_external_nav_height_contract() -> None:
    args = parse_args([])

    assert args.range_topic == "/rangefinder/down/range"
    assert args.height_topic == "/height/estimate"
    assert args.status_topic == "/height/status"
    assert args.source_type == "rangefinder_down_relative"
    assert args.covariance > 0
    assert args.max_vertical_speed_mps == 0.7
    assert args.max_vertical_velocity_output_mps == 0.0
    assert 0.0 < args.velocity_smoothing_alpha < 1.0
    assert args.max_filter_dt_sec == 0.1


def test_relative_height_estimator_clamps_spiky_rangefinder_velocity() -> None:
    height_m, vz_mps = estimate_relative_height(
        distance_m=0.80,
        ground_range_m=0.10,
        last_height_m=0.20,
        last_vz_mps=None,
        dt_sec=0.05,
        max_vertical_speed_mps=0.7,
        velocity_smoothing_alpha=0.35,
    )

    assert math.isclose(height_m, 0.235)
    assert math.isclose(vz_mps, 0.7)


def test_relative_height_estimator_rate_limits_spiky_height_position() -> None:
    height_m, vz_mps = estimate_relative_height(
        distance_m=4.70,
        ground_range_m=0.10,
        last_height_m=0.50,
        last_vz_mps=0.0,
        dt_sec=0.10,
        max_vertical_speed_mps=0.7,
        velocity_smoothing_alpha=0.35,
    )

    assert math.isclose(height_m, 0.57)
    assert math.isclose(vz_mps, 0.245)


def test_relative_height_estimator_smooths_clamped_velocity() -> None:
    _, vz_mps = estimate_relative_height(
        distance_m=0.80,
        ground_range_m=0.10,
        last_height_m=0.20,
        last_vz_mps=0.0,
        dt_sec=0.05,
        max_vertical_speed_mps=0.7,
        velocity_smoothing_alpha=0.35,
    )

    assert math.isclose(vz_mps, 0.245)


def test_relative_height_estimator_caps_filter_dt_after_sample_gap() -> None:
    height_m, vz_mps = estimate_relative_height(
        distance_m=2.00,
        ground_range_m=0.10,
        last_height_m=0.65,
        last_vz_mps=0.0,
        dt_sec=1.50,
        max_vertical_speed_mps=0.7,
        velocity_smoothing_alpha=0.35,
        max_filter_dt_sec=0.1,
    )

    assert math.isclose(height_m, 0.72)
    assert math.isclose(vz_mps, 0.245)


def test_relative_height_estimator_decouples_position_rate_from_vz_output() -> None:
    height_m, vz_mps = estimate_relative_height(
        distance_m=0.80,
        ground_range_m=0.10,
        last_height_m=0.20,
        last_vz_mps=None,
        dt_sec=0.10,
        max_vertical_speed_mps=0.5,
        max_vertical_velocity_output_mps=0.25,
        velocity_smoothing_alpha=0.35,
    )

    assert math.isclose(height_m, 0.25)
    assert math.isclose(vz_mps, 0.25)
