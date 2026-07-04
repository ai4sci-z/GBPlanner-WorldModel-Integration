# navlab_cartographer_adapter

ROS 2 wiring for the current NavLab Cartographer backend.

Contract:

- consume `sensor_msgs/msg/LaserScan` from `/scan`
- consume normalized `sensor_msgs/msg/Imu` from `/imu`
- launch `cartographer_ros` when `launch_cartographer_backend:=true`
- convert Cartographer-owned `map -> base_link` TF into `nav_msgs/msg/Odometry`
  on `/slam/odom`
- optionally republish accepted SLAM `map -> base_link` transforms to global
  `/tf` for frame consumers and replay visualization
- publish structured backend health on `/navlab/slam/status`

Cartographer dynamic TF is isolated from global `/tf`: the launch file remaps
Cartographer `/tf` to `/navlab/slam/tf`, and the adapter reads that topic via
`tf_topic`. Global `/tf` may contain AP/Gazebo diagnostic frames, but it is not
an input to `/slam/odom` in the NavLab sim acceptance profile. In sim runtime,
`publish_global_tf:=true` publishes only transforms that passed the adapter's
SLAM stability checks, so Foxglove can resolve `map -> base_link -> base_scan`
without consuming Gazebo truth.

This package is an adapter, not a standalone SLAM implementation. Real scan
matching is performed by `cartographer_ros`; this node validates inputs and
turns backend TF into the odometry topic consumed by `navlab_external_nav_bridge`.

`config/navlab_cartographer_2d_diagnostic_odom.lua` remains the official
ArduPilot baseline comparison file. It uses odometry input and must not be used
as the default sim acceptance profile because `/odometry` is diagnostic-only in
NavLab sim. Runtime configs that intentionally use odometry must bind
`cartographer_odometry_topic` to an explicitly provisioned real odometry source
such as `/cartographer/odometry_input`, never to Gazebo truth `/odometry`.

`config/navlab_cartographer_2d_real.lua` is the default NavLab sim runtime
profile. It disables odometry input (`use_odometry=false`), so Cartographer is
not seeded by Gazebo or bridge odometry. It also disables Cartographer's odom
frame (`provide_odom_frame=false`); the adapter reads the SLAM-owned
`map -> base_link` TF and emits `/slam/odom` for downstream tasks. Before flying
on hardware, retune at least LiDAR/IMU extrinsics, range limits, scan matcher
windows, motion filter, pose graph behavior, timestamp handling, and whether
Cartographer should use IMU data directly.

Example:

```bash
ros2 launch navlab_cartographer_adapter navlab_cartographer_adapter.launch.py \
  launch_cartographer_backend:=true \
  publish_placeholder_odom:=false \
  cartographer_tf_topic:=/navlab/slam/tf
```
