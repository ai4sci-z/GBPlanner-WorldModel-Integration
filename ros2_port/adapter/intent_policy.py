"""Pure policy helpers for the GBPlanner trajectory adapter."""

import math

ALIGNMENT_UPDATE_MIN_M = 0.10
ALIGNMENT_FREEZE_MIN_M = 0.35
ALIGNMENT_SCALE_RATIO_MIN = 0.60
ALIGNMENT_SCALE_RATIO_MAX = 1.67
ACTIVE_TRAJECTORY_MAX_AGE_S = 120.0


def estimate_alignment(map_anchor, ned_anchor, map_position, ned_position):
    """Estimate map-to-NED rotation from synchronized cumulative displacement.

    Returns ``(theta, map_distance, ned_distance, freeze)`` once the baseline
    has enough signal, otherwise ``None``. The estimate remains live until the
    longer freeze baseline is reached, so an initially poor fallback rotation
    cannot prevent calibration before the first waypoint.
    """
    dm = (
        float(map_position[0]) - float(map_anchor[0]),
        float(map_position[1]) - float(map_anchor[1]),
    )
    dn = (
        float(ned_position[0]) - float(ned_anchor[0]),
        float(ned_position[1]) - float(ned_anchor[1]),
    )
    map_distance = math.hypot(*dm)
    ned_distance = math.hypot(*dn)
    if map_distance < ALIGNMENT_UPDATE_MIN_M:
        return None
    scale_ratio = ned_distance / map_distance
    if not ALIGNMENT_SCALE_RATIO_MIN <= scale_ratio <= ALIGNMENT_SCALE_RATIO_MAX:
        return None
    theta = math.atan2(dn[1], dn[0]) - math.atan2(dm[1], dm[0])
    theta = (theta + math.pi) % (2.0 * math.pi) - math.pi
    freeze = map_distance >= ALIGNMENT_FREEZE_MIN_M
    return theta, map_distance, ned_distance, freeze
