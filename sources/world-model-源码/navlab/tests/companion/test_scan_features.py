from __future__ import annotations

from math import isclose

from navlab.common.perception.contract import DEFAULT_SCAN_CONTRACT
from navlab.common.perception.scan_features import compute_scan_features


def _empty_ranges() -> list[float]:
    return [DEFAULT_SCAN_CONTRACT.invalid_range_value] * DEFAULT_SCAN_CONTRACT.beam_count


def test_scan_features_report_empty_scan_as_no_valid_points() -> None:
    report = compute_scan_features(_empty_ranges())

    assert report.front_min is None
    assert report.left_min is None
    assert report.right_min is None
    assert report.rear_min is None
    assert report.nearest_range is None
    assert report.nearest_angle_deg == 0.0
    assert report.nearest_x is None
    assert report.nearest_y is None
    assert report.valid_count == 0
    assert report.total_count == DEFAULT_SCAN_CONTRACT.beam_count


def test_scan_features_match_x3_sector_summary_layout() -> None:
    ranges = _empty_ranges()
    ranges[DEFAULT_SCAN_CONTRACT.beam_count // 2] = 5.0
    ranges[270] = 3.0
    ranges[90] = 4.0
    ranges[0] = 2.5

    report = compute_scan_features(ranges)

    assert report.front_min == 5.0
    assert report.left_min == 3.0
    assert report.right_min == 4.0
    assert report.rear_min == 2.5
    assert report.nearest_range == 2.5
    assert isclose(report.nearest_angle_deg, -180.0)
    assert isclose(report.nearest_x or 0.0, -2.5, abs_tol=1e-6)
    assert isclose(report.nearest_y or 0.0, 0.0, abs_tol=1e-6)
    assert report.valid_count == 4
    assert report.total_count == DEFAULT_SCAN_CONTRACT.beam_count


def test_scan_features_keeps_ros_front_at_zero_degrees() -> None:
    ranges = _empty_ranges()
    ranges[0] = 5.0
    ranges[DEFAULT_SCAN_CONTRACT.beam_count // 2] = 2.5

    report = compute_scan_features(ranges)

    assert report.front_min == 2.5
    assert report.rear_min == 5.0
