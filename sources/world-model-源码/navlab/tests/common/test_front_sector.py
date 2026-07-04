from __future__ import annotations

from navlab.common.perception.contract import DEFAULT_SCAN_CONTRACT
from navlab.common.perception.front_sector import (
    ForwardStopStateMachine,
    classify_front_min,
    classify_front_sector,
    compute_front_min,
)


def _ranges_with_front_obstacle(distance: float) -> list[float]:
    ranges = [DEFAULT_SCAN_CONTRACT.invalid_range_value] * DEFAULT_SCAN_CONTRACT.beam_count
    center = DEFAULT_SCAN_CONTRACT.beam_count // 2
    for offset in range(-5, 6):
        ranges[center + offset] = distance
    return ranges


def test_front_min_is_none_for_empty_scan() -> None:
    ranges = [DEFAULT_SCAN_CONTRACT.invalid_range_value] * DEFAULT_SCAN_CONTRACT.beam_count
    assert compute_front_min(ranges) is None
    assert classify_front_sector(ranges).state == "clear"


def test_front_obstacle_is_reported() -> None:
    ranges = _ranges_with_front_obstacle(5.0)
    assert compute_front_min(ranges) == 5.0
    assert classify_front_sector(ranges).state == "obstacle_seen"


def test_close_obstacle_triggers_avoid_required() -> None:
    ranges = _ranges_with_front_obstacle(0.5)
    report = classify_front_sector(ranges)
    assert report.front_min == 0.5
    assert report.state == "avoid_required"


def test_classify_front_min_supports_scan_features_path() -> None:
    report = classify_front_min(5.0, valid_points=45)
    assert report.front_min == 5.0
    assert report.valid_points == 45
    assert report.state == "obstacle_seen"


def test_forward_stop_state_machine_stops_inside_threshold() -> None:
    machine = ForwardStopStateMachine(forward_speed=0.2, stop_distance=0.5)

    first = machine.update(5.0)
    assert first.motion_state == "forward"
    assert first.linear_x == 0.2
    assert first.reason == "path_clear"
    assert first.transitioned is False

    second = machine.update(0.4)
    assert second.motion_state == "stop"
    assert second.linear_x == 0.0
    assert second.reason == "stop_distance_reached"
    assert second.transitioned is True


def test_forward_stop_state_machine_stops_at_threshold_with_small_sensor_jitter() -> None:
    machine = ForwardStopStateMachine(forward_speed=0.2, stop_distance=0.5)

    decision = machine.update(0.50003)

    assert decision.motion_state == "stop"
    assert decision.linear_x == 0.0
    assert decision.reason == "stop_distance_reached"


def test_forward_stop_state_machine_stops_without_front_observation() -> None:
    machine = ForwardStopStateMachine(forward_speed=0.2, stop_distance=0.5)

    decision = machine.update(None)
    assert decision.motion_state == "stop"
    assert decision.linear_x == 0.0
    assert decision.reason == "no_front_observation"
    assert decision.transitioned is True
