# P6 真实 SLAM hover gate 设计

## 1. 目标

P6 的目标是在 P0-P5 已经通过的基础上，真正证明 NavLab 的无 GPS 悬停闭环成立：

```text
Gazebo 物理无人机
  -> X2 /scan + IMU + down rangefinder
  -> SLAM backend 输出 /slam/odom
  -> ExternalNav bridge 把 /slam/odom 送入 ArduPilot EKF
  -> FCU 使用 EKF local position 和 rangefinder 定高
  -> 唯一 FCU controller 发送 hover setpoint
  -> 无 direct set pose、无 Gazebo truth 控制输入
```

P6 只回答：

> 当前官方 maze/Iris 场景中，真实 SLAM `/slam/odom` 是否能作为 ExternalNav 输入，让 ArduPilot SITL 在 GUIDED/armed/takeoff 后稳定悬停。

P6 通过后，才能进入 P7 小范围运动 gate。P6 不回答 forward/back/yaw scan 是否可靠，也不回答探索任务是否完成。

## 2. 为什么 P6 必须单独做

P0-P5 分别证明了不同前置条件：

- P0：官方 ArduPilot ROS2/Gazebo/DDS baseline 可观测、可记录。
- P1：官方 maze 中的 X2 雷达链路可输出 vendor `/scan`。
- P2：down rangefinder 和 IMU 机制可观测，并能进入飞控相关链路。
- P3：SLAM backend 能消费 `/scan + /imu` 和配置允许的非 truth 辅助输入，并输出 `/slam/odom`。
- P4：FCU state machine、GUIDED/arm/takeoff 和唯一 setpoint owner 成立。
- P5：TF、sensor frame、scan 前向、rangefinder/IMU frame 和 rosbag contract 成立。

但这些都没有证明“用真实 SLAM feedback 悬停”。如果不单独做 P6，后续失败会混在一起：

- SLAM `/slam/odom` 漂移导致 EKF 被带偏；
- ExternalNav 发送频率、时间戳或 frame 标识不被 EKF 接受；
- FCU local position 可观测，但没有真正用 SLAM ExternalNav；
- rangefinder 定高正常，但水平位置仍来自 fallback 或 fake odom；
- controller 看起来在 hover，实际 Gazebo truth 或 direct set pose 在兜底；
- rosbag 能看见 topic，但无法证明 hover drift 达标。

P6 的意义是把“真实 SLAM feedback 是否能支撑静止悬停”作为独立完成标准。

## 3. P6 范围

### 3.1 包含

P6 包含：

- 继续使用官方 `iris_maze` bringup 和官方 Iris 模型。
- 继续使用 P1 的 X2 `/scan` 链路。
- 继续使用 P2 的 down rangefinder 和 IMU 机制。
- 继续使用 P3 的 SLAM backend registry 和 Cartographer backend。
- 继续使用 P4 的唯一 FCU controller，不新增第二个控制者。
- 继续使用 P5 的 frame contract 检查结果。
- 新增或固化 SLAM ExternalNav hover gate。
- 把 `/slam/odom` 作为 ExternalNav 输入。
- 验证 ExternalNav bridge 输出状态、发送频率、最新输入年龄和拒绝原因。
- 验证 ArduPilot EKF/local position 持续输出。
- 验证 GUIDED、arm、takeoff、hover settle、hover hold 的完整状态机。
- 验证 hover 窗口内水平漂移、高度误差、yaw 漂移和 stop drift。
- 生成 P6 summary、MCAP rosbag、Foxglove notes 和失败 blocker。

### 3.2 不包含

P6 不包含：

- 不替换 NavLab 8 字形 world。
- 不替换 NavLab 自定义机体模型。
- 不做 forward/back/yaw scan 小范围运动。
- 不做避障或探索。
- 不要求 Nav2。
- 不允许 direct set pose。
- 不允许 Gazebo truth 进入 SLAM、ExternalNav、规划或控制输入。
- 不允许 fake odom、synthetic odom 或 FCU local position 反灌 SLAM。
- 不允许多个节点同时向 FCU 发送 movement setpoint。

## 4. 目标架构

P6 目标架构是：

```text
official Gazebo/SITL baseline
  -> X2 vendor /scan
  -> /imu
  -> /rangefinder/down/range
  -> SLAM backend
  -> /slam/odom
  -> ExternalNav bridge
  -> ArduPilot EKF ExternalNav input
  -> /ap/v1/pose/filtered + /ap/v1/twist/filtered
  -> FCU controller hover intent
  -> /ap/v1/cmd_vel
  -> artifact summary + MCAP rosbag
```

Gazebo truth diagnostic 仍然可以记录：

```text
/odometry
```

但它只能用于：

- 计算 hover drift 对照；
- 计算 SLAM odom 与物理真值误差；
- Foxglove 回放诊断；
- summary 失败定位。

Gazebo truth 不能进入：

- SLAM input；
- ExternalNav input；
- FCU controller setpoint；
- 任务规划；
- hover 判定的唯一来源。

## 5. 服务职责

### 5.1 Orchestration

负责：

- 提供 P6 doctor / acceptance task。
- 启动 P0-P5 已验证的 baseline、sensor、SLAM、ExternalNav bridge 和 FCU controller。
- 生成 P6 runtime config。
- 录制 P6 rosbag profile。
- 收集 summary、topic info、node info、tail log、Foxglove notes。
- 在失败时生成明确 blocker。

不负责：

- 发布 hover setpoint。
- 修改 SLAM 输出。
- 用 Gazebo truth 修正 `/slam/odom`。
- 直接调用 Gazebo set pose。

### 5.2 SLAM backend

负责：

- 消费 `/scan`、`/imu` 和配置允许的非 truth 辅助输入。
- 输出 `/slam/odom`。
- 输出 `/navlab/slam/status`。
- 保持 P5 frame contract。
- 报告 odom rate、latest age、jump、stationary drift 和 tracking 状态。

不负责：

- 读取 Gazebo truth。
- 读取 FCU fused pose 作为定位答案。
- 直接发送 MAVLink 或 FCU setpoint。

### 5.3 ExternalNav bridge

负责：

- 订阅 `/slam/odom`。
- 把 SLAM odom 转换为 ArduPilot EKF 可接受的 ExternalNav 输入。
- 维护发送频率、最新输入年龄、最新发送年龄、发送计数和拒绝原因。
- 输出 `/external_nav/status`。

P6 必须记录：

```json
{
  "input_topic": "/slam/odom",
  "output_route": "official_dds_or_supported_external_nav",
  "input_count": 0,
  "sent_count": 0,
  "input_rate_hz": 0.0,
  "latest_input_age_sec": null,
  "latest_sent_age_sec": null,
  "state": "unknown",
  "uses_gazebo_truth_as_input": false
}
```

### 5.4 ArduPilot EKF / FCU

负责：

- 接收 ExternalNav。
- 输出 `/ap/v1/pose/filtered` 和 `/ap/v1/twist/filtered`。
- 使用 rangefinder 支撑定高。
- 在 GUIDED + armed + takeoff 后响应 hover setpoint。

P6 必须记录：

- mode 是否 GUIDED；
- arm 是否成功；
- takeoff 是否成功；
- local position 是否持续输出；
- local position rate；
- EKF/ExternalNav 接收状态；
- rangefinder 接收状态；
- 是否出现 failsafe 或 prearm/arming blocker。

### 5.5 FCU controller

负责：

- 复用 P4 唯一 setpoint owner。
- 在 readiness 满足前拒绝 hover intent。
- 执行：

```text
wait_fcu_time
  -> wait_rangefinder
  -> wait_imu
  -> wait_slam_odom
  -> wait_external_nav_healthy
  -> set_guided
  -> arm
  -> takeoff
  -> hover_settle
  -> hover_hold
  -> final_hold
  -> complete
```

不负责：

- 读取 Gazebo truth 做控制。
- 绕过 ExternalNav 使用 fake local position。
- 与其他 controller 共享 `/ap/v1/cmd_vel`。

## 6. Hover gate 判定

### 6.1 时间窗口

P6 acceptance 建议至少包含：

```text
startup window:      等待 Gazebo/SITL/DDS/sensor/SLAM ready
takeoff window:      GUIDED + arm + takeoff
settle window:       起飞后等待高度和 local position 稳定
hover window:        正式统计 hover drift
final hold window:   停止控制后短时间观察 drift
```

默认建议：

```text
duration_sec = 90
hover_window_sec >= 20
settle_window_sec >= 10
```

### 6.2 通过条件

P6 通过必须满足：

- `guided_ok=true`
- `arm_ok=true`
- `takeoff_ok=true`
- `rangefinder.ok=true`
- `imu.ok=true`
- `slam_odom.ok=true`
- `external_nav.ok=true`
- `fcu_local_position.ok=true`
- `owner.unique=true`
- `set_pose_count==0`
- `uses_gazebo_truth_as_input=false`
- hover window 内水平漂移小于阈值。
- hover window 内高度误差小于阈值。
- hover window 内 yaw 漂移小于阈值。
- stop drift 小于阈值。
- rosbag required topics 全部有数据。

建议默认阈值：

```text
max_hover_horizontal_drift_m = 0.10
max_hover_altitude_error_m = 0.25
max_hover_yaw_drift_rad = 0.35
max_stop_drift_m = 0.20
min_slam_odom_rate_hz = 1.0
min_external_nav_rate_hz = 5.0
min_fcu_local_position_rate_hz = 2.0
max_latest_age_sec = 1.0
```

这些阈值是仿真 gate 初始值。真机调参时可以根据传感器噪声、飞控参数、雷达安装误差和室内环境调整，但机制不能改变。

### 6.3 失败 blocker

P6 失败必须写入具体 blocker，例如：

```text
SLAM odom is stale
ExternalNav is not healthy
ExternalNav input is not /slam/odom
ExternalNav uses Gazebo truth as input
FCU local position is missing
GUIDED mode failed
Arm failed
Takeoff failed
Hover horizontal drift exceeded threshold
Rangefinder height error exceeded threshold
Multiple setpoint owners detected
Direct Gazebo set pose detected
Rosbag required topic has zero count
```

## 7. Topic 和 rosbag 要求

P6 rosbag required topics 至少包含：

```text
/clock
/tf
/tf_static
/scan
/imu
/rangefinder/down/range
/rangefinder/down/status
/slam/odom
/navlab/slam/status
/external_nav/status
/ap/v1/time
/ap/v1/pose/filtered
/ap/v1/twist/filtered
/ap/v1/status
/ap/v1/cmd_vel
/navlab/fcu/state
/navlab/fcu/controller/status
/navlab/fcu/setpoint/intent
/navlab/fcu/setpoint/output
/navlab/fcu/owner/status
/navlab/hover/status
```

optional topics 建议包含：

```text
/map
/submap_list
/trajectory_node_list
/odometry
/navlab/frame_contract/status
/navlab/x2/vendor_scan
/navlab/x2/scan_ideal
/sim/x2/status
/rangefinder/down/scan_ideal
```

Foxglove 回放重点：

- 固定参考系：`map`。
- 观察 `map -> odom -> base_link`。
- 观察 `/scan` 是否随机体方向正确叠加。
- 观察 `/slam/odom`、`/ap/v1/pose/filtered` 和 `/odometry` 的漂移对照。
- 不把 `/odometry` 当作控制或 SLAM 输入。

## 8. Summary schema

P6 summary 顶层建议：

```json
{
  "ok": false,
  "blocked": false,
  "blockers": [],
  "p6_slam_hover": {
    "ok": false,
    "hover_claim": "evaluated",
    "exploration_claim": "not_evaluated",
    "control_route": "unique_fcu_controller",
    "external_nav_input_topic": "/slam/odom",
    "uses_gazebo_truth_as_input": false
  },
  "fcu": {
    "guided_ok": false,
    "arm_ok": false,
    "takeoff_ok": false,
    "local_position_ok": false,
    "local_position_count": 0,
    "local_position_rate_hz": 0.0
  },
  "slam_odom": {
    "ok": false,
    "topic": "/slam/odom",
    "count": 0,
    "rate_hz": 0.0,
    "latest_age_sec": null,
    "stationary_drift_m": null
  },
  "external_nav": {
    "ok": false,
    "state": "unknown",
    "input_topic": "/slam/odom",
    "sent_count": 0,
    "rate_hz": 0.0,
    "latest_sent_age_sec": null
  },
  "hover": {
    "ok": false,
    "window_sec": 0.0,
    "horizontal_drift_m": null,
    "altitude_error_m": null,
    "yaw_drift_rad": null,
    "stop_drift_m": null
  },
  "owner": {
    "unique": false,
    "owner": null,
    "set_pose_count": 0,
    "competing_publishers": []
  },
  "rosbag_profile": {
    "ok": false,
    "missing_required_topics": [],
    "zero_count_required_topics": []
  }
}
```

## 9. 和后续阶段的关系

P6 通过后只能说明：

- 官方 maze/Iris 场景中真实 SLAM ExternalNav 可以支撑静止悬停；
- FCU 定高、SLAM odom、ExternalNav、EKF local position 和唯一 controller 的机制成立；
- rosbag/Foxglove 可以复现 hover gate。

P6 不说明：

- forward/back/yaw scan 运动可靠；
- 避障可靠；
- 探索可靠；
- NavLab 8 字形 world/model 已经迁移完成；
- 真机参数已经最终调好。

这些分别进入 P7、P8 和后续 world/model migration。
