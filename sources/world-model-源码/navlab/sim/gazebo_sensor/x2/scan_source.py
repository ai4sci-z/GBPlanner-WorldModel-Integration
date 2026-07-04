from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from navlab.sim.gazebo_sensor.x2.protocol import X2Sample


@dataclass(frozen=True, slots=True)
class IdealLaserScan:
    ranges: tuple[float, ...]
    angle_min_rad: float
    angle_increment_rad: float


def resample_ideal_scan_to_x2_samples(
    scan: IdealLaserScan,
    *,
    sample_count: int,
    range_min_m: float,
    range_max_m: float,
    noise_stddev_m: float = 0.0,
    noise_stddev_per_m: float = 0.0,
    dropout_rate: float = 0.0,
    random_seed: int | None = None,
) -> tuple[X2Sample, ...]:
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    if not scan.ranges:
        return ()
    if not math.isfinite(scan.angle_increment_rad) or scan.angle_increment_rad == 0:
        raise ValueError("angle_increment_rad must be finite and non-zero")
    if noise_stddev_m < 0:
        raise ValueError("noise_stddev_m must be non-negative")
    if noise_stddev_per_m < 0:
        raise ValueError("noise_stddev_per_m must be non-negative")
    if not 0 <= dropout_rate <= 1:
        raise ValueError("dropout_rate must be in [0, 1]")

    rng = random.Random(random_seed) if random_seed is not None else random
    angle_step_deg = 360.0 / sample_count
    samples: list[X2Sample] = []
    for index in range(sample_count):
        angle_deg = index * angle_step_deg
        source_value = _nearest_range_for_angle(
            ranges=scan.ranges,
            angle_min_rad=scan.angle_min_rad,
            angle_increment_rad=scan.angle_increment_rad,
            target_angle_rad=_x2_angle_deg_to_ros_rad(angle_deg),
        )
        range_m = _normalize_range(
            source_value,
            range_min_m=range_min_m,
            range_max_m=range_max_m,
            rng=rng,
            noise_stddev_m=noise_stddev_m,
            noise_stddev_per_m=noise_stddev_per_m,
            dropout_rate=dropout_rate,
        )
        samples.append(X2Sample(angle_deg=angle_deg, range_m=range_m))
    return tuple(samples)


def _x2_angle_deg_to_ros_rad(angle_deg: float) -> float:
    angle_rad = math.radians(angle_deg % 360.0)
    if angle_rad >= math.pi:
        angle_rad -= 2.0 * math.pi
    return angle_rad


def _nearest_range_for_angle(
    *,
    ranges: Sequence[float],
    angle_min_rad: float,
    angle_increment_rad: float,
    target_angle_rad: float,
) -> float:
    source_index = round((target_angle_rad - angle_min_rad) / angle_increment_rad)
    if source_index < 0 or source_index >= len(ranges):
        return math.nan
    return float(ranges[source_index])


def _normalize_range(
    value: float,
    *,
    range_min_m: float,
    range_max_m: float,
    rng: Any,
    noise_stddev_m: float,
    noise_stddev_per_m: float,
    dropout_rate: float,
) -> float:
    if dropout_rate > 0 and rng.random() < dropout_rate:
        return math.nan
    if not math.isfinite(value):
        return math.nan
    value = max(range_min_m, min(range_max_m, value))
    noise_stddev = noise_stddev_m + abs(value) * noise_stddev_per_m
    if noise_stddev > 0:
        value += rng.gauss(0.0, noise_stddev)
        value = max(range_min_m, min(range_max_m, value))
    return value
