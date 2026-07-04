from __future__ import annotations

from dataclasses import dataclass
from math import cos, degrees, fmod, isfinite, sin

from navlab.common.perception.contract import DEFAULT_SCAN_CONTRACT, ScanContract


@dataclass(frozen=True, slots=True)
class ScanFeaturesReport:
    front_min: float | None
    left_min: float | None
    right_min: float | None
    rear_min: float | None
    nearest_range: float | None
    nearest_angle_deg: float
    nearest_x: float | None
    nearest_y: float | None
    valid_count: int
    total_count: int


def _is_valid_range(value: float, *, range_min: float, range_max: float) -> bool:
    return isfinite(value) and range_min <= value <= range_max


def _angle_in_sector(angle_deg: float, center_deg: float, half_width_deg: float) -> bool:
    diff = fmod(angle_deg - center_deg + 540.0, 360.0) - 180.0
    return abs(diff) <= half_width_deg


def compute_scan_features(
    ranges: list[float],
    *,
    contract: ScanContract = DEFAULT_SCAN_CONTRACT,
    angle_min: float | None = None,
    angle_increment: float | None = None,
    range_min: float | None = None,
    range_max: float | None = None,
    front_center_deg: float = 0.0,
    left_center_deg: float = 90.0,
    right_center_deg: float = -90.0,
    rear_center_deg: float = 180.0,
    front_half_width_deg: float = 15.0,
    side_half_width_deg: float = 20.0,
    rear_half_width_deg: float = 20.0,
) -> ScanFeaturesReport:
    angle_min = contract.angle_min if angle_min is None else angle_min
    angle_increment = contract.angle_increment if angle_increment is None else angle_increment
    range_min = contract.range_min if range_min is None else range_min
    range_max = contract.range_max if range_max is None else range_max

    front_min: float | None = None
    left_min: float | None = None
    right_min: float | None = None
    rear_min: float | None = None
    nearest_range: float | None = None
    nearest_angle_deg = 0.0
    nearest_x: float | None = None
    nearest_y: float | None = None
    valid_count = 0

    for index, value in enumerate(ranges):
        if not _is_valid_range(value, range_min=range_min, range_max=range_max):
            continue

        valid_count += 1
        angle = angle_min + angle_increment * index
        angle_deg = degrees(angle)

        if _angle_in_sector(angle_deg, front_center_deg, front_half_width_deg):
            front_min = value if front_min is None else min(front_min, value)
        if _angle_in_sector(angle_deg, left_center_deg, side_half_width_deg):
            left_min = value if left_min is None else min(left_min, value)
        if _angle_in_sector(angle_deg, right_center_deg, side_half_width_deg):
            right_min = value if right_min is None else min(right_min, value)
        if _angle_in_sector(angle_deg, rear_center_deg, rear_half_width_deg):
            rear_min = value if rear_min is None else min(rear_min, value)

        if nearest_range is None or value < nearest_range:
            nearest_range = value
            nearest_angle_deg = angle_deg
            nearest_x = value * cos(angle)
            nearest_y = value * sin(angle)

    return ScanFeaturesReport(
        front_min=front_min,
        left_min=left_min,
        right_min=right_min,
        rear_min=rear_min,
        nearest_range=nearest_range,
        nearest_angle_deg=nearest_angle_deg,
        nearest_x=nearest_x,
        nearest_y=nearest_y,
        valid_count=valid_count,
        total_count=len(ranges),
    )
