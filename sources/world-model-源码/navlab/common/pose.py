from __future__ import annotations

from dataclasses import dataclass
from math import cos, sin


@dataclass(slots=True)
class PlanarPoseState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    yaw: float = 0.0


def quaternion_from_yaw(yaw: float) -> tuple[float, float, float, float]:
    half_yaw = yaw * 0.5
    return (0.0, 0.0, sin(half_yaw), cos(half_yaw))
