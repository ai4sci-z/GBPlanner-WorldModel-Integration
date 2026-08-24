"""Pure policy helpers for the GBPlanner trajectory adapter."""

import math

ACTIVE_TRAJECTORY_MAX_AGE_S = 120.0
FCU_YAW_MAX_AGE_S = 2.0
ODOM_FRAME_ID = "map"
ODOM_CHILD_FRAME_ID = "base_link"


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


def valid_odom_frames(frame_id, child_frame_id):
    """Require the exact pose transform consumed by the body-frame mapping."""
    return frame_id == ODOM_FRAME_ID and child_frame_id == ODOM_CHILD_FRAME_ID


def map_velocity_to_body_frd(vx_map, vy_map, map_yaw):
    """Express a ROS map vector as body forward/right (FRD) components."""
    try:
        vx, vy, yaw = (float(value) for value in (vx_map, vy_map, map_yaw))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (vx, vy, yaw)):
        return None
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    return (
        cos_yaw * vx + sin_yaw * vy,
        sin_yaw * vx - cos_yaw * vy,
    )
