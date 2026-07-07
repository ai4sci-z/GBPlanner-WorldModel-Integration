# Trigger mode of planner control interface, defined in PlannerTriggerModeType.
# ROS 2 requires UPPER_SNAKE_CASE constant names (ROS 1 was kManual/kAuto).
int32 K_MANUAL = 0
int32 K_AUTO = 1

# Set one of above values.
int32 mode
