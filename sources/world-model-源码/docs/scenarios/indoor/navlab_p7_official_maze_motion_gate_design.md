# P7 官方 maze 小范围运动 gate 设计

## 1. 目标

P7 的目标是在 P0-P6 已经通过的基础上，证明 NavLab 的真实 SLAM hover
闭环不只能够静止悬停，还能够在官方 maze/Iris 场景中执行可控的小范围水平
运动：

```text
Gazebo 物理无人机
  -> X2 /scan + IMU + down rangefinder
  -> SLAM backend 输出 /slam/odom
  -> ExternalNav bridge 把 /slam/odom 送入 ArduPilot EKF
  -> FCU 输出 local position
  -> 唯一 FCU controller 接收 motion intent
  -> /ap/v1/cmd_vel 输出 forward/back/yaw/stop setpoint
  -> 无 direct set pose、无 Gazebo truth 规划或控制输入
```

P7 只回答：

> 当前官方 maze/Iris 场景中，在 P6 hover 已经成立后，系统是否能通过唯一
> FCU controller 执行 forward、back、yaw scan 和 stop hold，并在每个动作后
> 保持 drift、scan clearance、SLAM/FCU/Gazebo 诊断对照可解释。

P7 通过后，才能进入 P8 探索任务。P7 不回答自主目标选择、覆盖率、全局路径
规划或 NavLab 8 字形 world/model 迁移是否完成。

## 2. 为什么 P7 必须单独做

P6 已经证明真实 SLAM feedback 可以支撑静止悬停，但小范围运动会暴露新的失败模式：

- forward/back setpoint 的 body/world frame 方向可能反了；
- `/ap/v1/cmd_vel` 速度、yaw rate 或停止指令可能没有被 FCU 稳定执行；
- motion 后 ExternalNav/EKF 可能漂移、跳变或短时间丢失；
- SLAM 在运动中可能跟踪失败，静止 hover 时看不出来；
- scan 前向方向和机头方向可能在 yaw 后才暴露问题；
- stop setpoint 后 drift 可能超阈值，导致后续探索不安全；
- motion gate 可能误用 Gazebo truth 做方向或距离答案；
- 多个任务节点可能绕过唯一 controller 直接发 setpoint。

P7 的意义是把“可以稳定悬停”推进到“可以安全做最小动作”，但仍然不把策略、
探索、覆盖率和 Nav2 引入同一个 gate。

## 3. P7 范围

### 3.1 包含

P7 包含：

- 继续使用官方 `iris_maze` bringup 和官方 Iris 模型。
- 继续使用 P1 的 X2 `/scan` 链路。
- 继续使用 P2 的 down rangefinder 和 IMU 机制。
- 继续使用 P3 的 SLAM backend registry 和 Cartographer backend。
- 继续使用 P4 的唯一 FCU controller，不新增第二个控制者。
- 继续使用 P5 的 frame contract 检查结果。
- 继续使用 P6 的 SLAM ExternalNav hover gate 作为前置状态。
- 新增或固化小范围 motion gate。
- 执行 forward、stop hold、back、stop hold、yaw scan、final stop hold。
- 验证每个动作的位移方向、位移幅度、yaw 方向、stop drift 和 clearance。
- 验证运动期间 SLAM odom、ExternalNav、FCU local position 和 scan 持续健康。
- 生成 P7 summary、MCAP rosbag、Foxglove notes 和失败 blocker。

### 3.2 不包含

P7 不包含：

- 不替换 NavLab 8 字形 world。
- 不替换 NavLab 自定义机体模型。
- 不做自主探索、覆盖率优化或 frontier selection。
- 不要求 Nav2。
- 不做复杂避障策略，只做最小 clearance 和 stop guard 检查。
- 不允许 direct set pose。
- 不允许 Gazebo truth 进入 SLAM、ExternalNav、规划或控制输入。
- 不允许 fake odom、synthetic odom 或 FCU local position 反灌 SLAM。
- 不允许 mission 层或 motion probe 绕过唯一 controller 直接发布 movement setpoint。

## 4. 目标架构

P7 目标架构是：

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
  -> P7 motion intent sequence
  -> unique FCU controller
  -> /ap/v1/cmd_vel
  -> /navlab/motion/status
  -> artifact summary + MCAP rosbag
```

Gazebo truth diagnostic 仍然可以记录：

```text
/odometry
```

但它只能用于：

- 计算 motion 位移和漂移对照；
- 计算 SLAM odom 与物理真值误差；
- 检查碰撞、卡住或异常滑移的诊断证据；
- Foxglove 回放诊断；
- summary 失败定位。

Gazebo truth 不能进入：

- SLAM input；
- ExternalNav input；
- FCU controller setpoint；
- motion planner / action selector；
- forward/back/yaw 是否该执行的在线判断。

## 5. 服务职责

### 5.1 Orchestration

负责：

- 提供 P7 doctor / acceptance task。
- 启动 P0-P6 已验证的 baseline、sensor、SLAM、ExternalNav bridge 和 FCU controller。
- 生成 P7 runtime config。
- 录制 P7 rosbag profile。
- 收集 summary、topic info、node info、tail log、Foxglove notes。
- 在失败时生成明确 blocker。

不负责：

- 发布 movement setpoint。
- 修改 SLAM 输出。
- 用 Gazebo truth 修正 `/slam/odom` 或 motion result。
- 直接调用 Gazebo set pose。

### 5.2 P7 motion gate coordinator

负责：

- 等待 P6 hover 前置条件满足。
- 发布或调用 motion intent，而不是直接发布 `/ap/v1/cmd_vel`。
- 执行固定小范围动作序列：

```text
wait_p6_hover_ready
  -> forward_probe
  -> forward_stop_hold
  -> back_probe
  -> back_stop_hold
  -> yaw_scan_left
  -> yaw_stop_hold
  -> yaw_scan_right_or_recenter
  -> final_stop_hold
  -> complete
```

- 输出 `/navlab/motion/status`。
- 记录每个 action 的 start/end time、目标、实际位移、yaw 变化、stop drift 和拒绝原因。

不负责：

- 直接控制 Gazebo。
- 直接发布 FCU setpoint。
- 读取 Gazebo truth 做在线决策。
- 做探索目标选择或路径规划。

### 5.3 FCU controller

负责：

- 复用 P4/P6 唯一 setpoint owner。
- 在 readiness 满足前拒绝 motion intent。
- 把 motion intent 转换成唯一输出通道上的 velocity、yaw rate 或 stop setpoint。
- 输出 `/navlab/fcu/controller/status`、`/navlab/fcu/setpoint/intent`、
  `/navlab/fcu/setpoint/output` 和 `/navlab/fcu/owner/status`。

不负责：

- 读取 Gazebo truth 做控制。
- 与其他 controller 共享 `/ap/v1/cmd_vel`。
- 绕过 P6 hover readiness 执行动作。

### 5.4 SLAM backend 和 ExternalNav bridge

负责：

- 在 motion window 中持续输出 `/slam/odom` 和 `/navlab/slam/status`。
- ExternalNav bridge 持续把 `/slam/odom` 送入 ArduPilot EKF。
- 记录 motion 期间的 rate、latest age、jump、tracking 状态和拒绝原因。

不负责：

- 读取 Gazebo truth。
- 读取 FCU fused pose 作为 SLAM 答案。
- 发布 movement setpoint。

### 5.5 Scan / clearance monitor

负责：

- 读取最终 vendor `/scan`，不是 `/scan_ideal`。
- 在 forward/back/yaw 动作中记录 front/side/rear clearance。
- 检查最小 scan range、有效 range 比例和 stop guard 状态。
- 输出 summary 中的 clearance 诊断。

不负责：

- 直接决定探索目标。
- 用 Gazebo truth 替代 scan clearance。
- 直接控制 FCU。

## 6. Motion gate 判定

### 6.1 时间窗口

P7 acceptance 建议至少包含：

```text
startup window:        等待 Gazebo/SITL/DDS/sensor/SLAM ready
p6 hover window:       复用 P6 hover readiness 和 settle
forward window:        小距离前进动作
forward stop window:   前进后停止并观察 drift
back window:           小距离后退动作
back stop window:      后退后停止并观察 drift
yaw scan window:       小角度 yaw 或 yaw rate 扫描
final hold window:     全部动作后最终停止观察 drift
```

默认建议：

```text
duration_sec = 120
motion_distance_m = 0.40
yaw_scan_rad = 0.50
motion_speed_mps = 0.12
yaw_rate_radps = 0.20
yaw_window_sec = 4.0
stop_hold_window_sec >= 5
final_hold_window_sec >= 8
```

这些值是仿真 gate 初始值。真机或更窄 maze 中可以调小动作幅度，但机制不能改变。

### 6.2 通过条件

P7 通过必须满足：

- `p6_hover.ok=true` 或等价前置 hover readiness 成立。
- `guided_ok=true`、`arm_ok=true`、`takeoff_ok=true`。
- `slam_odom.ok=true`。
- `external_nav.ok=true`。
- `fcu_local_position.ok=true`。
- `owner.unique=true`。
- `set_pose_count==0`。
- `uses_gazebo_truth_as_input=false`。
- forward action 位移方向和幅度符合阈值。
- back action 位移方向和幅度符合阈值。
- yaw scan 方向和幅度符合阈值。
- 每个 stop window 的 drift 小于阈值。
- motion window 中 scan clearance 不低于安全阈值。
- motion window 中 SLAM、ExternalNav 和 FCU local position 未 stale。
- rosbag required topics 全部有数据。

建议默认阈值：

```text
min_forward_displacement_m = 0.20
max_forward_displacement_m = 0.80
min_back_displacement_m = 0.20
max_back_displacement_m = 0.80
min_yaw_delta_rad = 0.25
max_yaw_delta_rad = 0.90
max_lateral_error_m = 0.30
max_motion_altitude_error_m = 0.30
max_motion_yaw_error_rad = 0.25
max_stop_drift_m = 0.25
min_clearance_m = 0.35
min_slam_odom_rate_hz = 1.0
min_external_nav_rate_hz = 5.0
min_fcu_local_position_rate_hz = 1.5
max_latest_age_sec = 1.0
```

### 6.3 失败 blocker

P7 失败必须写入具体 blocker，例如：

```text
P6 hover prerequisite failed
Motion intent was rejected by controller
Forward displacement below threshold
Forward displacement direction is inconsistent
Back displacement below threshold
Back displacement direction is inconsistent
Yaw scan delta below threshold
Yaw scan direction is inconsistent
Stop drift exceeded threshold
Scan clearance below threshold
SLAM odom is stale during motion
ExternalNav is stale during motion
FCU local position is stale during motion
Multiple setpoint owners detected
Direct Gazebo set pose detected
Gazebo truth used as motion input
Rosbag required topic has zero count
```

## 7. Topic 和 rosbag 要求

P7 rosbag required topics 至少包含：

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
/navlab/motion/status
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
/navlab/vehicle/markers
```

Foxglove 回放重点：

- 固定参考系：`map`。
- 观察 `map -> odom -> base_link`。
- 观察 `/scan` 是否随机体方向正确叠加。
- 观察 `/slam/odom`、`/ap/v1/pose/filtered` 和 `/odometry` 的运动方向对照。
- 观察 `/navlab/fcu/setpoint/output` 与 `/navlab/motion/status` 的 action 时间段是否一致。
- 观察 forward/back/yaw 后 stop drift 是否可见且在阈值内。
- 不把 `/odometry` 当作规划、控制或 SLAM 输入。

## 8. Summary schema

P7 summary 顶层建议：

```json
{
  "ok": false,
  "blocked": false,
  "blockers": [],
  "p7_motion_gate": {
    "ok": false,
    "hover_claim": "evaluated",
    "motion_claim": "evaluated",
    "exploration_claim": "not_evaluated",
    "control_route": "unique_fcu_controller",
    "external_nav_input_topic": "/slam/odom",
    "uses_gazebo_truth_as_input": false
  },
  "p6_hover_prerequisite": {
    "ok": false,
    "hover_window_sec": 0.0,
    "horizontal_drift_m": null
  },
  "motion_actions": {
    "forward": {
      "ok": false,
      "target_distance_m": 0.4,
      "displacement_m": null,
      "lateral_error_m": null,
      "stop_drift_m": null
    },
    "back": {
      "ok": false,
      "target_distance_m": 0.4,
      "displacement_m": null,
      "lateral_error_m": null,
      "stop_drift_m": null
    },
    "yaw_scan": {
      "ok": false,
      "target_yaw_delta_rad": 0.5,
      "yaw_delta_rad": null,
      "stop_drift_m": null
    }
  },
  "clearance": {
    "ok": false,
    "min_scan_range_m": null,
    "min_clearance_m": 0.35
  },
  "fcu": {
    "guided_ok": false,
    "arm_ok": false,
    "takeoff_ok": false,
    "local_position_ok": false,
    "local_position_rate_hz": 0.0
  },
  "slam_odom": {
    "ok": false,
    "topic": "/slam/odom",
    "rate_hz": 0.0,
    "latest_age_sec": null,
    "max_jump_m": null
  },
  "external_nav": {
    "ok": false,
    "input_topic": "/slam/odom",
    "rate_hz": 0.0,
    "latest_sent_age_sec": null
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

P7 通过后只能说明：

- 官方 maze/Iris 场景中真实 SLAM ExternalNav 可以支撑最小水平运动；
- forward、back、yaw scan 和 stop hold 的 FCU setpoint 链路成立；
- motion 后 drift、clearance、SLAM/FCU/Gazebo 诊断对照可回放；
- 唯一 controller 的 movement intent 边界可以支撑 P8。

P7 不说明：

- 自主探索策略可靠；
- coverage 或 frontier selection 已完成；
- Nav2 已接入；
- NavLab 8 字形 world/model 已迁移完成；
- 真机参数已经最终调好。

这些分别进入 P8、后续 world/model migration 和真机迁移记录。
