# P2 下视 Rangefinder 与 IMU 机制验收设计

## 1. 目标

P2 的目标是在 P0/P1 已经跑通的官方 ArduPilot ROS2/Gazebo/Cartographer baseline 上，单独验收两类飞行必需传感器机制：

- 下视 rangefinder：仿真中由 Gazebo 下视测距产生，作为飞控外设进入 ArduPilot。
- IMU：由 FCU/SITL 或官方 DDS/MAVLink telemetry 输出，作为 SLAM 和诊断的真实惯性输入。

P2 只回答：

> 当前仿真是否已经按照真实无人机机制提供“飞控可接收的下视测距”和“可供 SLAM 使用的真实 IMU 输入”。

P2 不回答 hover 是否完成，也不回答 SLAM `/odom` 质量是否已经足够。这些属于 P3/P6。

## 2. 为什么 P2 必须单独做

P1 已经证明：

```text
official iris_maze
  -> Gazebo /lidar
  -> X2 virtual serial
  -> ydlidar_ros2_driver
  -> /scan
  -> ardupilot_cartographer
```

但是无人机在无 GPS 室内真正能悬停，还需要两个额外机制稳定：

- 高度控制不能靠 companion 直接控制油门，也不能靠 Gazebo set pose。真实无人机已有下视测距外设，飞控可以用它参与定高或高度估计。
- SLAM 不能只靠 `/scan` topic 存在。Cartographer 或后续 SLAM backend 需要明确的 IMU 输入来源、frame、频率和时间戳口径。

如果 P2 不单独验收，后续 hover gate 失败时会混在一起：

- 是下视 rangefinder 没进 FCU；
- 是 FCU 没接收 `DISTANCE_SENSOR`；
- 是 IMU 不是 FCU 来源；
- 是 IMU frame 或时间戳错；
- 还是 SLAM 本身漂移。

P2 的意义就是把这些问题拆出来，先证明机制正确，再进入 P3/P6。

## 3. P2 范围

### 3.1 包含

P2 包含：

- 继续使用官方 `ardupilot_gz_bringup iris_maze.launch.py` 和官方 Iris 模型。
- 在 Gazebo/Iris 或等价官方模型上提供下视测距输入。
- `gazebo-sensor` 负责把下视测距转换为：
  - ROS `/rangefinder/down/range`
  - ROS `/rangefinder/down/status`
  - MAVLink `DISTANCE_SENSOR`
- 验证 `DISTANCE_SENSOR` 发送频率、方向、sensor id、最小/最大距离和最近测距值。
- 验证 FCU/SITL 或官方 DDS/MAVLink telemetry 中 IMU 输入来源、频率、frame 和最新消息年龄。
- 验证 rosbag/Foxglove 能回放 P2 required topics。
- summary 明确区分 rangefinder 机制、IMU 机制、P1 X2 scan 链路和后续 hover gate。

### 3.2 不包含

P2 不包含：

- 不替换 NavLab 8 字形 world。
- 不替换 NavLab 自定义机体模型。
- 不做 SLAM `/odom` 质量验收。
- 不做 ExternalNav 回灌飞控验收。
- 不做 hover drift 完成判断。
- 不做 forward/avoid/exploration。
- 不允许 direct Gazebo set pose。
- 不允许 companion 直接控制油门来证明高度稳定。

## 4. 目标架构

P2 目标架构分成两条传感器链。

### 4.1 下视 Rangefinder 链路

下视 rangefinder 是 FCU 外设，不是 companion 控制器：

```text
Gazebo down range sensor
  -> gazebo-sensor runtime
  -> /rangefinder/down/range
  -> /rangefinder/down/status
  -> MAVLink DISTANCE_SENSOR
  -> ArduPilot SITL rangefinder/EKF/altitude estimator
  -> FCU telemetry diagnostics
```

职责边界：

- Gazebo 负责几何射线和物理世界。
- `gazebo-sensor` 负责 sensor runtime、ROS Range topic 和 MAVLink `DISTANCE_SENSOR`。
- ArduPilot SITL 负责接收 rangefinder 外设输入。
- companion 可以观察状态，但不能生成 rangefinder 数据，不能为了 P2 控制油门或移动 Gazebo。

### 4.2 IMU 链路

IMU 必须是 FCU/SITL 或官方 DDS/MAVLink telemetry 来源，不能是为了让 Cartographer 启动而临时 synthetic：

```text
ArduPilot SITL / FCU IMU state
  -> official DDS /ap/v1/imu/experimental/data
  -> 或 FCU MAVLink IMU telemetry bridge
  -> canonical ROS IMU topic
  -> /imu/status
  -> SLAM backend input contract
```

P2 不强制以后只能使用一个传输层。DDS 和 MAVLink 都可以作为 telemetry 通道，但 summary 必须记录：

- `imu_source_route`
- `imu_source_topic`
- `imu_output_topic`
- `imu_frame_id`
- `imu_rate_hz`
- `latest_imu_age_sec`
- 是否启用了 synthetic fallback

P2 通过时，synthetic fallback 不能作为完成标准。

### 4.3 与 P1 X2 链路的关系

P2 可以复用 P1 的 official maze + X2 `/scan` 链路，作为环境和 Cartographer 输入背景。但 P2 的完成标准不是 `/scan`，而是：

- 下视 rangefinder 机制健康；
- IMU 机制健康；
- 两者都能被 rosbag 记录和 summary 解释。

如果 P1 X2 链路回归失败，P2 应该 blocked，因为 P2 是在 P1 baseline 上继续加机制。

## 5. Topic 和 Frame 合同

P2 required topics：

```text
/clock
/tf
/tf_static
/ap/v1/time
/scan
/sim/x2/status
/rangefinder/down/range
/rangefinder/down/status
/imu
```

P2 optional topics：

```text
/ap/v1/imu/experimental/data
/imu/status
/odometry
/submap_list
/trajectory_node_list
/rangefinder/down/scan_ideal
/ap/v1/pose/filtered
```

Frame 要求：

```text
base_link
imu_link
base_scan
rangefinder_down_frame
```

验收语义：

- `/rangefinder/down/range.header.frame_id` 应为 `rangefinder_down_frame` 或 P2 配置指定 frame。
- `/imu.header.frame_id` 应为 `imu_link` 或 P2 配置指定 frame。
- `rangefinder_down_frame` 必须是下视安装语义，MAVLink orientation 必须记录为向下方向。
- `base_link -> imu_link` 和 `base_link -> rangefinder_down_frame` 的关系必须能在 TF 或 artifact 中解释。

## 6. FCU 接收语义

P2 必须证明 `DISTANCE_SENSOR` 不只是发出去了，还被飞控接收或至少能通过飞控侧状态间接证明。

优先证据：

- SITL log 中出现 rangefinder / distance sensor 接收相关证据。
- MAVLink telemetry 能看到对应 rangefinder status 或 distance sensor 回传。
- FCU altitude/local position 与 `/rangefinder/down/range` 在静态场景下数值趋势一致。

如果当前 ArduPilot 官方 DDS 不直接暴露 rangefinder topic，也不能直接降级为“只要 `/rangefinder/down/range` 有数据就通过”。summary 必须写清：

- `rangefinder_mavlink_sent_count`
- `rangefinder_fcu_received`
- `rangefinder_fcu_receive_evidence`
- `rangefinder_fcu_receive_claim`

当 FCU 接收证据不足时，P2 可以部分通过 sensor-side gate，但 full acceptance 必须 blocked。

## 7. Summary 字段

P2 summary 至少包含：

```json
{
  "ok": false,
  "blocked": true,
  "blockers": [],
  "p2_rangefinder_imu": {
    "world_source": "official_iris_maze",
    "vehicle_model_source": "official_iris_with_lidar",
    "altitude_control_claim": "not_evaluated",
    "hover_claim": "not_evaluated",
    "direct_set_pose": false,
    "rangefinder": {
      "source_owner": "gazebo_sensor",
      "range_topic": "/rangefinder/down/range",
      "status_topic": "/rangefinder/down/status",
      "frame_id": "rangefinder_down_frame",
      "mavlink_message": "DISTANCE_SENSOR",
      "mavlink_orientation": "MAV_SENSOR_ROTATION_PITCH_270",
      "input_count": 0,
      "sent_count": 0,
      "latest_distance_m": null,
      "latest_input_age_sec": null,
      "latest_sent_age_sec": null,
      "fcu_received": false,
      "fcu_receive_evidence": ""
    },
    "imu": {
      "source_route": "official_dds_or_fcu_telemetry",
      "source_topic": "",
      "output_topic": "/imu",
      "status_topic": "/imu/status",
      "frame_id": "imu_link",
      "message_count": 0,
      "rate_hz": 0.0,
      "latest_age_sec": null,
      "synthetic_fallback_enabled": false
    }
  },
  "rosbag_profile": {
    "ok": false,
    "required_topics": [],
    "missing_required_topics": [],
    "zero_count_required_topics": []
  }
}
```

`altitude_control_claim` 和 `hover_claim` 必须保持 `not_evaluated`。P2 证明传感器机制，不证明 hover。

## 8. 验收语义

P2 通过必须满足：

- P0 official DDS baseline 仍能收到 `/ap/v1/time`。
- P1 X2 `/scan` 链路没有被破坏。
- 下视 rangefinder 数据由 `gazebo-sensor` 发布，不由 companion 伪造。
- `/rangefinder/down/range` 有持续数据，frame、量程、频率符合配置。
- `/rangefinder/down/status` 显示 input_count 和 sent_count 增长。
- MAVLink `DISTANCE_SENSOR` 方向、sensor id、min/max distance 被 summary 记录。
- 有 FCU 接收证据；如果没有，full acceptance blocked。
- IMU topic 有持续数据，frame 和频率符合配置。
- IMU source 不是 synthetic fallback。
- rosbag required topics 全部存在且 message count 大于 0。
- summary 明确 P2 不代表 hover 完成，不代表 SLAM `/odom` 质量完成。

P2 不通过但有价值的情况：

- `/rangefinder/down/range` 有数据但 `sent_count=0`：说明 MAVLink sender 或 endpoint 失败。
- `sent_count>0` 但 FCU 接收证据缺失：说明 FCU rangefinder 参数、telemetry 或验收探针不足。
- IMU 有 topic 但 frame 错：说明 SLAM frame contract 不能进入 P3。
- IMU 来源是 synthetic fallback：说明只能作为启动临时手段，不能进入真实验收。

## 9. 执行顺序

P2 推荐执行顺序：

```text
1. 复跑 P0 official baseline doctor/acceptance。
2. 复跑 P1 official maze + X2 acceptance。
3. 启动 official iris_maze bringup。
4. 启动 gazebo-sensor，下视 rangefinder enabled。
5. 确认 /rangefinder/down/range 和 /rangefinder/down/status。
6. 确认 MAVLink DISTANCE_SENSOR sent_count。
7. 检查 FCU 接收证据或 SITL log。
8. 启动或检查 IMU bridge / official DDS IMU。
9. 记录 P2 rosbag profile。
10. 生成 summary.json 和 Foxglove notes。
```

## 10. 与后续 Phase 的关系

P2 完成后：

- P3 验证 Cartographer `/odom` 质量，开始把 `/scan + /imu + /odometry + TF` 作为 SLAM 输入质量合同。
- P4 做 FCU 状态机和唯一 setpoint owner。
- P6 才能做真实 SLAM hover gate。

如果 P2 没完成，不应该进入 P6。否则 hover gate 失败时无法区分是高度传感器、IMU、SLAM 还是 FCU setpoint 问题。
