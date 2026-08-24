"""Pure planning-frame contract helpers used by the M5 ROS 2 relay."""

import math

WALL_EPOCH_MIN = 1e8
PLANNING_PARENT = "map"
PLANNING_CHILD = "base_link"
EXTERNAL_NAV_PARENT = "external_nav"


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
