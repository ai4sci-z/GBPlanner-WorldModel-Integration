"""Pure planning-frame contract helpers used by the M5 ROS 2 relay."""

import math

WALL_EPOCH_MIN = 1e8
PLANNING_PARENT = "map"
PLANNING_CHILD = "base_link"
EXTERNAL_NAV_PARENT = "external_nav"
PLANNING_HEIGHT_MIN_M = 0.05
PLANNING_HEIGHT_MAX_M = 3.0
PLANNING_HEIGHT_MAX_AGE_S = 1.0


def should_forward_tf(stamp_sec, parent_frame, child_frame):
    if stamp_sec >= WALL_EPOCH_MIN:
        return False
    return not (
        parent_frame == PLANNING_PARENT and child_frame == PLANNING_CHILD
    )


def valid_external_nav_odom(parent_frame, child_frame, position, orientation):
    if parent_frame != EXTERNAL_NAV_PARENT or child_frame != PLANNING_CHILD:
        return False
    values = tuple(position) + tuple(orientation)
    return len(values) == 7 and all(math.isfinite(float(value)) for value in values)


def valid_planning_height(height_m, age_s):
    try:
        height = float(height_m)
        age = float(age_s)
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(height)
        and math.isfinite(age)
        and PLANNING_HEIGHT_MIN_M < height <= PLANNING_HEIGHT_MAX_M
        and 0.0 <= age <= PLANNING_HEIGHT_MAX_AGE_S
    )


def planning_height_rejection(height_m):
    """Classify unsafe FCU heights without treating ground as divergence."""
    try:
        height = float(height_m)
    except (TypeError, ValueError):
        return "nonfinite"
    if not math.isfinite(height):
        return "nonfinite"
    if height <= PLANNING_HEIGHT_MIN_M:
        return "low"
    if height > PLANNING_HEIGHT_MAX_M:
        return "overheight"
    return None
