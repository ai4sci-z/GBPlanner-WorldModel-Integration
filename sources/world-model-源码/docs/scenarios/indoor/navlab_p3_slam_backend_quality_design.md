# P3 SLAM backend 质量验收设计

## 1. 目标

P3 的目标是在 P0/P1/P2 已通过的官方 ArduPilot ROS2/Gazebo baseline 上，单独验收 SLAM backend 的输入契约、输出契约和定位质量。

P3 只回答：

> 当前 SLAM backend 是否真正消费 Gazebo/FCU 机制产生的 `/scan + /imu + /odometry + TF`，并输出连续、可解释、可诊断的定位结果。

P3 不回答无人机是否已经能 hover，也不回答 ExternalNav 是否已经回灌飞控。这些属于 P6。P3 也不做 forward/avoid/exploration，这些属于 P7/P8。

## 2. 为什么 P3 必须单独做

P2 已经证明：

```text
official iris_maze
  -> NavLab X2 Gazebo scan input
  -> X2 virtual serial
  -> ydlidar_ros2_driver
  -> /scan

Gazebo down rangefinder
  -> /rangefinder/down/range
  -> MAVLink DISTANCE_SENSOR
  -> ArduPilot SITL telemetry evidence

official Gazebo IMU bridge
  -> /imu
```

但这些只能证明传感器机制存在。真实无 GPS 悬停还需要 SLAM 输出足够稳定的定位。如果不单独做 P3，后续 hover 失败时会混在一起：

- SLAM 没有真的消费 `/scan`；
- SLAM 使用了 synthetic IMU 或错误 frame；
- SLAM 只发 topic，但时间戳不连续；
- SLAM `/odom` 有跳变、漂移或坐标方向错误；
- ExternalNav sender 把错误 SLAM 输出送进 FCU；
- FCU/EKF 参数或 setpoint 控制有问题。

P3 的意义是把“SLAM backend 质量”从 FCU hover gate 中拆出来。P3 通过后，P6 才能把 SLAM 输出接入 ExternalNav。

## 3. P3 范围

### 3.1 包含

P3 包含：

- 继续使用官方 `ardupilot_gz_bringup iris_maze.launch.py` 和官方 Iris 模型。
- 继续使用 P1 的 X2 vendor-driver `/scan` 链路。
- 继续使用 P2 的 IMU 和 rangefinder 机制作为环境基础。
- 以 Cartographer 作为默认真实 SLAM backend。
- 固化 SLAM backend 输入契约：
  - `/scan`
  - `/imu`
  - `/odometry`
  - `/tf`
  - `/tf_static`
- 固化 SLAM backend 输出契约：
  - `/map`
  - `/submap_list`
  - `/trajectory_node_list`
  - `map -> odom` 或等价 SLAM localization TF
  - canonical SLAM odometry topic，例如 `/slam/odom`
- 使用 Gazebo truth 只做诊断对照，不作为 SLAM 输入。
- 记录 backend 名称、配置路径、配置 hash、镜像、版本和启动命令。
- 记录 SLAM 输出频率、最新消息年龄、跳变、短窗漂移、与 Gazebo truth 的诊断误差。
- 输出 rosbag 和 summary，方便 Foxglove 回放和数值复核。

### 3.2 不包含

P3 不包含：

- 不替换 NavLab 8 字形 world。
- 不替换 NavLab 自定义机体模型。
- 不向 FCU 发送 ExternalNav。
- 不 arm/takeoff/hover。
- 不下发运动 setpoint。
- 不做导航规划或探索。
- 不允许 Gazebo truth 进入 SLAM 输入链路。
- 不允许 direct Gazebo set pose 被当成定位质量。

## 4. 目标架构

P3 目标架构是：

```text
official Gazebo/SITL baseline
  -> /scan        # P1 X2 vendor-driver output
  -> /imu         # P2 official Gazebo/FCU equivalent IMU
  -> /odometry    # official Gazebo odometry / motion prior
  -> /tf, /tf_static
  -> SLAM backend container
  -> Cartographer or registered backend
  -> /map, /submap_list, /trajectory_node_list
  -> map -> odom TF
  -> /slam/odom canonical localization output
  -> artifact diagnostics
```

诊断对照链路是：

```text
Gazebo truth / official odometry diagnostic
  -> diagnostic sampler
  -> compare with /slam/odom
  -> summary quality metrics
```

Gazebo truth 只能用于误差分析，不能进入：

- SLAM backend 输入；
- ExternalNav 输入；
- FCU setpoint 控制；
- P3 完成标准中的“定位来源”。

## 5. Backend 注册和接口合同

P3 必须把 SLAM backend 当成可替换模块，而不是把 Cartographer 逻辑写死在 orchestration 中。

推荐接口：

```text
backend name
backend image
backend launch command
input topics
output topics
required frames
config path
config hash
health probe
quality probe
```

默认 backend：

```text
name: cartographer
source: official ardupilot_cartographer / cartographer_ros
launch: ros2 launch ardupilot_cartographer cartographer.launch.py
```

后续 backend 可以是：

- `cartographer`
- `slam_toolbox`
- `rf2o_diagnostic`
- 自研 C++/Rust SLAM

但所有 backend 必须遵守同一输出契约。否则 P6 ExternalNav gate 会被 backend 差异污染。

## 6. 输入契约

P3 required input topics：

```text
/clock
/tf
/tf_static
/scan
/imu
/odometry
```

输入要求：

- `/scan` publisher 必须是 `ydlidar_ros2_driver_node` 或 P3 配置指定的 X2 vendor-driver 输出。
- `/scan` 不能直接来自 Gazebo bridge 的 raw ideal scan。
- `/scan.header.frame_id` 必须是 `base_scan` 或 P3 配置指定 laser frame。
- `/imu.header.frame_id` 必须是 `imu_link` 或 P3 配置指定 IMU frame。
- `/imu` synthetic fallback 必须关闭。
- `/odometry` 可以作为 SLAM motion prior，但必须记录来源。
- `/tf` 和 `/tf_static` 必须能解释 `map/odom/base_link/imu_link/base_scan` 的关系。

P3 blocked 条件：

- `/scan` 未收到。
- `/scan` 不是 X2 vendor-driver 输出。
- `/imu` 未收到。
- `/imu` 是 synthetic fallback。
- `/odometry` 未收到。
- TF 链不连通或 frame 方向无法解释。
- Gazebo truth 被配置为 SLAM 输入。

## 7. 输出契约

P3 required output topics / transforms：

```text
/map
/submap_list
/trajectory_node_list
map -> odom
/slam/odom
```

其中：

- `/map`、`/submap_list`、`/trajectory_node_list` 证明 Cartographer 或等价 backend 在运行。
- `map -> odom` 证明 backend 输出 localization transform。
- `/slam/odom` 是 NavLab 后续 P6 ExternalNav 使用的 canonical SLAM odometry 输出。

如果 backend 原生不发布 `/slam/odom`，允许一个 backend wrapper 从 backend TF / pose 输出生成 `/slam/odom`。但 wrapper 必须只消费 SLAM 输出和 TF，不能消费 Gazebo truth 或 FCU fused local position。

## 8. 质量指标

P3 不要求达到最终 hover 阈值，但必须从“topic 存在”推进到“质量可诊断”。

建议指标：

```text
slam_odom_count
slam_odom_rate_hz
latest_slam_odom_age_sec
slam_odom_jump_max_m
slam_odom_yaw_jump_max_rad
slam_truth_error_mean_m
slam_truth_error_p95_m
slam_truth_error_max_m
slam_stationary_drift_m
map_count
submap_list_count
trajectory_node_list_count
```

P3 通过阈值建议：

- `/slam/odom` 持续发布。
- latest age 小于 1 秒。
- 短窗内没有明显跳变。
- 静止窗口 drift 不超过 P3 配置阈值。
- 与 Gazebo truth 的诊断误差在 P3 宽松阈值内。
- summary 必须记录阈值和实测值。

注意：Gazebo truth 误差只是诊断指标。P3 可以用它判断 backend 是否明显失真，但不能把 truth 当成正式定位来源。

## 9. Rosbag 和 Foxglove

P3 rosbag required topics：

```text
/clock
/tf
/tf_static
/scan
/imu
/odometry
/map
/submap_list
/trajectory_node_list
/slam/odom
/sim/x2/status
/rangefinder/down/range
/rangefinder/down/status
```

P3 optional topics：

```text
/ap/v1/time
/ap/v1/imu/experimental/data
/ap/v1/pose/filtered
/rangefinder/down/scan_ideal
/navlab/x2/scan_ideal
/scan_matched_points2
/constraint_list
/slam/status
/slam/diagnostics
```

Foxglove notes 必须说明：

- 固定参考系优先选 `map`。
- 用 `/slam/odom` 查看 SLAM localization。
- 用 `/map`、`/submap_list`、`/trajectory_node_list` 查看 Cartographer 建图状态。
- 用 `/scan` 叠加墙体和轨迹。
- Gazebo truth 只能作为诊断对照层。

## 10. Summary 字段

P3 summary 至少包含：

```json
{
  "ok": false,
  "blocked": true,
  "blockers": [],
  "p3_slam_backend": {
    "backend": "cartographer",
    "backend_image": "navlab/slam-cartographer:latest",
    "backend_source": "official_cartographer",
    "launch_command": "ros2 launch ardupilot_cartographer cartographer.launch.py",
    "config_path": null,
    "config_hash": null,
    "world_source": "official_iris_maze",
    "vehicle_model_source": "official_iris_with_lidar",
    "external_nav_claim": "not_evaluated",
    "hover_claim": "not_evaluated",
    "direct_set_pose": false
  },
  "slam_inputs": {
    "scan_topic": "/scan",
    "scan_publisher": "ydlidar_ros2_driver_node",
    "imu_topic": "/imu",
    "imu_frame_id": "imu_link",
    "odometry_topic": "/odometry",
    "uses_gazebo_truth_as_input": false
  },
  "slam_outputs": {
    "slam_odom_topic": "/slam/odom",
    "slam_odom_count": 0,
    "slam_odom_rate_hz": 0.0,
    "latest_slam_odom_age_sec": null,
    "map_count": 0,
    "submap_list_count": 0,
    "trajectory_node_list_count": 0,
    "map_to_odom_present": false
  },
  "slam_quality": {
    "slam_odom_jump_max_m": null,
    "slam_odom_yaw_jump_max_rad": null,
    "slam_truth_error_mean_m": null,
    "slam_truth_error_p95_m": null,
    "slam_truth_error_max_m": null,
    "stationary_drift_m": null,
    "thresholds": {}
  },
  "rosbag_profile": {
    "ok": false,
    "message_counts": {}
  }
}
```

## 11. P3 完成标准

P3 通过必须满足：

- 官方 `iris_maze` bringup 未被替换。
- P1 X2 `/scan` 链路仍 healthy。
- P2 IMU/rangefinder 机制仍 healthy。
- SLAM backend 通过 registry 启动，backend 名称和配置 hash 被记录。
- `/scan + /imu + /odometry + TF` 输入全部健康。
- `/scan` 来自 X2 vendor-driver，不是 Gazebo ideal scan。
- `/slam/odom` 或配置指定 canonical SLAM odom 持续发布。
- `/map`、`/submap_list`、`/trajectory_node_list` 有数据。
- `map -> odom` 或等价 localization transform 存在。
- SLAM 输出没有明显跳变。
- Gazebo truth 只用于诊断对照，没有进入 SLAM 输入。
- rosbag profile 通过。
- summary 明确 `hover_claim=not_evaluated`。
- summary 明确 `external_nav_claim=not_evaluated`。

## 12. 与后续 Phase 的关系

P3 通过后，才能进入：

- P4：FCU 状态机和唯一 setpoint owner。
- P5：Frame contract 自动验收。
- P6：真实 SLAM ExternalNav hover gate。

P3 失败时，不能通过调宽 P6 hover 阈值绕过。应该先修 SLAM 输入、frame、backend 配置或 wrapper 输出。
