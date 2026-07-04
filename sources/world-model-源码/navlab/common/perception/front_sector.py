from __future__ import annotations

from dataclasses import dataclass

from navlab.common.perception.contract import DEFAULT_SCAN_CONTRACT, ScanContract
from navlab.common.perception.scan_features import compute_scan_features


@dataclass(frozen=True, slots=True)
class FrontSectorReport:
    front_min: float | None
    state: str
    valid_points: int


@dataclass(frozen=True, slots=True)
class ForwardStopDecision:
    motion_state: str
    linear_x: float
    reason: str
    transitioned: bool


class ForwardStopStateMachine:
    def __init__(
        self,
        *,
        forward_speed: float = 0.2,
        stop_distance: float = 0.5,
        initial_state: str = "forward",
        stop_distance_tolerance: float = 1e-3,
    ) -> None:
        self._forward_speed = forward_speed
        self._stop_distance = stop_distance
        self._stop_distance_tolerance = stop_distance_tolerance
        self._state = initial_state

    @property
    def state(self) -> str:
        return self._state

    def update(self, front_min: float | None) -> ForwardStopDecision:
        if front_min is None:
            next_state = "stop"
            reason = "no_front_observation"
        elif front_min <= self._stop_distance + self._stop_distance_tolerance:
            next_state = "stop"
            reason = "stop_distance_reached"
        else:
            next_state = "forward"
            reason = "path_clear"

        transitioned = next_state != self._state
        self._state = next_state
        linear_x = self._forward_speed if next_state == "forward" else 0.0
        return ForwardStopDecision(
            motion_state=next_state,
            linear_x=linear_x,
            reason=reason,
            transitioned=transitioned,
        )


def classify_front_min(
    front_min: float | None,
    *,
    valid_points: int,
    obstacle_seen_distance: float = 6.0,
    avoid_distance: float = 1.0,
) -> FrontSectorReport:
    if front_min is None:
        return FrontSectorReport(front_min=None, state="clear", valid_points=valid_points)
    if front_min < avoid_distance:
        return FrontSectorReport(front_min=front_min, state="avoid_required", valid_points=valid_points)
    if front_min < obstacle_seen_distance:
        return FrontSectorReport(front_min=front_min, state="obstacle_seen", valid_points=valid_points)
    return FrontSectorReport(front_min=front_min, state="clear", valid_points=valid_points)


def compute_front_min(
    ranges: list[float],
    *,
    contract: ScanContract = DEFAULT_SCAN_CONTRACT,
    front_half_width_deg: float = 15.0,
) -> float | None:
    return compute_scan_features(
        ranges,
        contract=contract,
        front_half_width_deg=front_half_width_deg,
    ).front_min


def classify_front_sector(
    ranges: list[float],
    *,
    contract: ScanContract = DEFAULT_SCAN_CONTRACT,
    front_half_width_deg: float = 15.0,
    obstacle_seen_distance: float = 6.0,
    avoid_distance: float = 1.0,
) -> FrontSectorReport:
    feature_report = compute_scan_features(
        ranges,
        contract=contract,
        front_half_width_deg=front_half_width_deg,
    )
    return classify_front_min(
        feature_report.front_min,
        valid_points=feature_report.valid_count,
        obstacle_seen_distance=obstacle_seen_distance,
        avoid_distance=avoid_distance,
    )
