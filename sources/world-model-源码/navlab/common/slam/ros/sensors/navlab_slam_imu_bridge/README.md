# navlab_slam_imu_bridge

Normalizes the FCU-side IMU stream for SLAM.

Contract:

- subscribe to an upstream `sensor_msgs/msg/Imu` topic
- publish normalized IMU on `/imu` by default
- publish structured health on `/imu/status`
- keep FCU/MAVLink/MAVROS-specific details outside the SLAM backend

Example:

```bash
ros2 run navlab_slam_imu_bridge navlab_slam_imu_bridge_node \
  --ros-args \
  -p source_topic:=/ap/imu/experimental/data \
  -p source_label:=fcu_mavlink_navlab
```
