# navlab_slam_bringup

Scenario-level launch package for the NavLab indoor SLAM feedback chain.

It assembles:

- `navlab_slam_imu_bridge`
- static body-to-sensor TF
- `navlab_cartographer_adapter`
- optional `navlab_fake_odom` for isolated smoke tests
- `navlab_external_nav_bridge`

Main runtime example:

```bash
ros2 launch navlab_slam_bringup navlab_slam_bringup.launch.py \
  launch_cartographer_backend:=true \
  launch_fake_odom:=false \
  external_nav_input_odom_topic:=/slam/odom \
  cartographer_tf_topic:=/navlab/slam/tf
```

The stable backend contract is `/scan + /imu + Cartographer-owned TF -> /map +
/slam/odom + /navlab/slam/status`. In the NavLab sim acceptance profile,
`/odometry` and global `/tf` are diagnostic-only and must not be used as
Cartographer, ExternalNav, controller, or task success inputs.
