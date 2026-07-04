# navlab_external_nav_bridge

Converts SLAM odometry into the ROS topic consumed by the NavLab MAVLink
ExternalNav sender.

Contract:

- subscribe to `/odom` by default
- optionally require fresh `/imu/data`
- optionally require fresh height diagnostics
- publish `/external_nav/odom`
- publish structured health on `/external_nav/status`
- publish `/ap/tf` as a diagnostic ArduPilot-shaped TF stream
- report `slam_quality` as one of `good`, `uncertain`, `bad`, `stale`, or
  `jump`; `/external_nav/odom` is only published when the quality gate allows it

The companion MAVLink sender is responsible for converting `/external_nav/odom`
into MAVLink `ODOMETRY`; this package stays ROS-only.
