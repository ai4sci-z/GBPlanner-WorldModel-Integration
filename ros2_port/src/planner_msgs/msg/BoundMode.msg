# Bound mode of the robot for collision checking, defined in Params/BoundModeType.
# ROS 2 requires UPPER_SNAKE_CASE constant names (ROS 1 was kExtendedBound, ...).
int32 K_EXTENDED_BOUND = 0
int32 K_RELAXED_BOUND = 1
int32 K_MIN_BOUND = 2
int32 K_EXACT_BOUND = 3
int32 K_NO_BOUND = 4

# Set one of above values.
int32 mode
