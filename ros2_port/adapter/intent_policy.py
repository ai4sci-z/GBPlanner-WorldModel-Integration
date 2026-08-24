"""Pure policy helpers for the GBPlanner trajectory adapter."""

import math

ALIGNMENT_UPDATE_MIN_M = 0.10
ALIGNMENT_FREEZE_MIN_M = 0.35
ALIGNMENT_SCALE_RATIO_MIN = 0.60
ALIGNMENT_SCALE_RATIO_MAX = 1.67
ACTIVE_TRAJECTORY_MAX_AGE_S = 120.0
FCU_YAW_MAX_AGE_S = 2.0


def normalize_angle(angle):
    return (float(angle) + math.pi) % (2.0 * math.pi) - math.pi


def quaternion_yaw(x, y, z, w):
    """Return normalized-quaternion yaw, or ``None`` for invalid input."""
    try:
        values = [float(value) for value in (x, y, z, w)]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    norm = math.sqrt(sum(value * value for value in values))
    if norm < 1e-9:
        return None
    x, y, z, w = (value / norm for value in values)
    return math.atan2(
        2.0 * (w * z + x * y),
        1.0 - 2.0 * (y * y + z * z),
    )


def valid_fcu_yaw(yaw_rad, age_s):
    try:
        yaw = float(yaw_rad)
        age = float(age_s)
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(yaw)
        and math.isfinite(age)
        and 0.0 <= age <= FCU_YAW_MAX_AGE_S
    )


def effective_fcu_yaw_age(pose_age_s, reported_attitude_age_s, status_age_s):
    """Return a conservative yaw age from pose and source-status evidence."""
    try:
        ages = [float(value) for value in (
            pose_age_s, reported_attitude_age_s, status_age_s)]
    except (TypeError, ValueError):
        return math.inf
    if not all(math.isfinite(age) and age >= 0.0 for age in ages):
        return math.inf
    pose_age, reported_age, status_age = ages
    return max(pose_age, reported_age + status_age)


def command_heading(map_to_ned_heading, fcu_yaw_ned):
    """Map-frame command heading expressed in the FCU body/FRD frame."""
    return normalize_angle(float(map_to_ned_heading) - float(fcu_yaw_ned))


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
    theta = normalize_angle(theta)
    freeze = map_distance >= ALIGNMENT_FREEZE_MIN_M
    return theta, map_distance, ned_distance, freeze
