from __future__ import annotations

from dataclasses import dataclass
from math import pi


@dataclass(frozen=True, slots=True)
class ScanContract:
    topic_name: str = "/scan"
    frame_id: str = "laser_frame"
    angle_min: float = -pi
    angle_max: float = pi
    range_min: float = 0.1
    range_max: float = 12.0
    frequency_hz: float = 10.0
    beam_count: int = 361
    invalid_range_value: float = 0.0
    intensity_value: float = 0.0

    @property
    def angle_increment(self) -> float:
        return (self.angle_max - self.angle_min) / (self.beam_count - 1)

    @property
    def scan_time(self) -> float:
        return 1.0 / self.frequency_hz

    @property
    def time_increment(self) -> float:
        return self.scan_time / max(self.beam_count, 1)


DEFAULT_SCAN_CONTRACT = ScanContract()
