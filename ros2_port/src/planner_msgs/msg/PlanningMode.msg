# Planning mode for exploration, defined in Params/PlanningModeType.
# ROS 2 requires UPPER_SNAKE_CASE constant names (ROS 1 was kBasicExploration, ...).
int32 K_BASIC_EXPLORATION = 0
int32 K_NARROW_ENV_EXPLORATION = 1
int32 K_ADAPTIVE_EXPLORATION = 2

# Set one of above values.
int32 mode
