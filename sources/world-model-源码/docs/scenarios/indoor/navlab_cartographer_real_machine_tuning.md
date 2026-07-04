# NavLab Cartographer 真机调参记录模板

这份模板用于记录每一次真机 Cartographer bringup。仿真中的
`navlab_cartographer_2d.lua` 只能作为初始参考，真机必须记录实际外参、传感器、
飞控和 Cartographer 参数，避免后续无法复现。

## 1. 基本信息

- 日期：
- 机器编号：
- 计算盒子型号：
- FCU 型号和固件版本：
- X2 雷达型号和固件版本：
- 使用的 rosbag：
- 使用的 Cartographer 配置文件：
- 配置文件 hash：
- 使用的 ArduPilot 参数文件：
- 操作人：

## 2. 传感器和坐标系

### X2 雷达

- ROS topic：`/scan`
- `frame_id`：
- 安装位置，`base_link -> laser_frame` xyz：
- 安装姿态，`base_link -> laser_frame` rpy：
- 0 度是否朝机头：
- 正角方向是否朝左：
- 真实扫描频率：
- 有效最小距离：
- 有效最大距离：
- 是否存在固定角度遮挡：
- 是否需要驱动层 `inverted` / `reversion` / 等价参数：

### FCU IMU

- ROS topic：`/imu/data`
- `frame_id`：
- 安装位置，`base_link -> imu_link` xyz：
- 安装姿态，`base_link -> imu_link` rpy：
- 输出频率：
- 时间戳来源：
- 是否和雷达时间同步：
- 静止时加速度方向是否正确：
- 静止时角速度 bias：

## 3. Cartographer 配置

记录以下 Lua 配置项的实际值和调整原因。

- `map_frame`：
- `tracking_frame`：
- `published_frame`：
- `odom_frame`：
- `provide_odom_frame`：
- `publish_frame_projected_to_2d`：
- `TRAJECTORY_BUILDER_2D.use_imu_data`：
- `TRAJECTORY_BUILDER_2D.min_range`：
- `TRAJECTORY_BUILDER_2D.max_range`：
- `TRAJECTORY_BUILDER_2D.missing_data_ray_length`：
- `TRAJECTORY_BUILDER_2D.num_accumulated_range_data`：
- `TRAJECTORY_BUILDER_2D.use_online_correlative_scan_matching`：
- `real_time_correlative_scan_matcher.linear_search_window`：
- `real_time_correlative_scan_matcher.angular_search_window`：
- `motion_filter.max_distance_meters`：
- `motion_filter.max_angle_radians`：
- `POSE_GRAPH.optimize_every_n_nodes`：

## 4. ExternalNav 和飞控

- MAVLink ODOMETRY 发送频率：
- ODOMETRY frame 约定：
- covariance 设置：
- FCU 是否接受 ExternalNav：
- EKF source / lane 配置：
- `LOCAL_POSITION_NED` 输出频率：
- rangefinder topic：
- MAVLink `DISTANCE_SENSOR` 发送频率：
- rangefinder 最小/最大距离：
- 定高模式相关参数：

## 5. 验收记录

### 静止采集

- `/scan` 是否稳定：
- `/imu/data` 是否稳定：
- TF 链是否闭合：
- Cartographer 是否启动 trajectory：
- `/odom` 是否静止不跳：

### 手持或地面慢速移动

- `/map` 是否出现明显重影：
- `/odom` 是否连续：
- 回到原点误差：
- 最大瞬时跳变：

### 悬停观察，不回灌飞控

- `/odom` 漂移：
- `/navlab/slam/status`：
- CPU 占用：
- 是否丢 scan：

### ExternalNav 悬停

- 是否进入 GUIDED：
- 是否 arm：
- 是否 takeoff：
- `LOCAL_POSITION_NED` 是否持续：
- 水平漂移：
- 高度漂移：
- 是否发生碰撞或触墙：

## 6. 调整结论

- 本次可保留的参数：
- 下次必须继续调整的参数：
- 是否允许进入下一阶段：
- 不允许进入下一阶段的原因：

