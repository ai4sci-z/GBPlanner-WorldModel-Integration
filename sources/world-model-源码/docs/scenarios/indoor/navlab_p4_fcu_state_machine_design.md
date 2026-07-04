# P4 FCU 状态机和唯一控制器设计

## 1. 目标

P4 的目标是在 P0/P1/P2/P3 已经建立的官方 ArduPilot ROS2/Gazebo、X2 雷达、rangefinder/IMU、SLAM backend 质量基础上，单独验收 FCU 状态机和 setpoint 输出所有权。

P4 只回答：

> 当前系统是否能用一个唯一 controller 按真实飞控流程进入 GUIDED、arm、takeoff，并且所有 hover、yaw、local position target 都通过同一个 FCU setpoint 输出通道发送。

P4 不回答 SLAM ExternalNav hover 是否稳定完成。这属于 P6。P4 也不做 forward/avoid/exploration，这些属于 P7/P8。

## 2. 为什么 P4 必须单独做

P3 已经证明 SLAM backend 可以输出可诊断的 `/slam/odom`。但真实无人机能不能飞，不只取决于 SLAM topic 是否存在，还取决于飞控控制权是否清晰。

如果不单独做 P4，后续 hover 或探索失败时会混在一起：

- FCU 还没 ready 就开始发 setpoint；
- 多个节点同时向 FCU 发运动指令；
- GUIDED、arm、takeoff 的状态转换没有被确认；
- controller 使用 velocity setpoint、local position target、yaw command 的口径不一致；
- mission 任务层直接操作 MAVLink/ROS service，绕过统一 controller；
- 某个 fallback 节点仍在 direct set pose 或向 Gazebo 写位置；
- SLAM/ExternalNav 问题和飞控状态机问题混在同一个 gate 中。

P4 的意义是把“谁能控制飞控、什么时候能控制、用什么接口控制”固定下来。P4 通过后，P6 才能把真实 SLAM ExternalNav 接进 hover gate。

## 3. P4 范围

### 3.1 包含

P4 包含：

- 继续使用官方 `iris_maze` bringup 和官方 Iris 模型。
- 继续使用 P1 的 X2 `/scan` 链路。
- 继续使用 P2 的 down rangefinder 和 IMU 机制。
- 继续保留 P3 SLAM backend 作为可观测基础，但 P4 不判定 SLAM hover 成功。
- 新增或固化 FCU state watcher。
- 新增或固化唯一 setpoint owner。
- 新增或固化 mission intent 到 FCU command 的转换边界。
- 验证 FCU readiness：
  - `/ap/v1/time` 或等价 FCU heartbeat 可收到；
  - prearm 可检查；
  - mode 可切换到 GUIDED；
  - arm 成功；
  - takeoff command 成功；
  - local position / pose filtered 可观测；
  - rangefinder/IMU 状态可观测。
- 验证所有 movement intent 都只通过同一个 controller 输出。
- summary 记录 controller owner、状态机转换、setpoint 计数、拒绝原因和 direct set pose 计数。
- rosbag 记录 FCU 状态、controller 状态、setpoint intent、setpoint output 和关键诊断 topic。

### 3.2 不包含

P4 不包含：

- 不替换 NavLab 8 字形 world。
- 不替换 NavLab 自定义机体模型。
- 不完成 P6 SLAM hover gate。
- 不要求 hover drift 达到最终阈值。
- 不做 forward/back/yaw scan/avoid/exploration。
- 不允许 mission 任务层直接发飞控运动指令。
- 不允许多个节点同时向 FCU 发送 movement setpoint。
- 不允许 direct Gazebo set pose。
- 不允许 Gazebo truth 进入控制输入。

## 4. 目标架构

P4 目标架构是：

```text
official Gazebo/SITL baseline
  -> ArduPilot DDS /ap/v1/* state
  -> FCU state watcher
  -> controller readiness gate
  -> mission intent topic/service
  -> unique FCU controller
  -> MAVLink bootstrap for GUIDED/arm/takeoff
  -> ArduPilot DDS /ap/v1/cmd_vel setpoint output
  -> FCU local position / pose filtered diagnostic
  -> artifact summary + rosbag
```

其中 mission 任务层只表达意图：

```text
takeoff
hover
yaw_to / yaw_rate
local_position_target
hold
abort / land
```

任务层不能直接调用：

- ArduPilot arm/mode/takeoff service；
- MAVLink `SET_POSITION_TARGET_*`；
- MAVLink `COMMAND_LONG`；
- ROS `/ap/v1/cmd_vel` 或等价 setpoint topic；
- Gazebo pose service。

所有实际控制输出必须经过唯一 controller。

## 5. 服务职责

### 5.1 Orchestration

负责：

- 提供 P4 doctor / acceptance task。
- 启动官方 baseline、gazebo sensor、SLAM backend 和 controller runtime。
- 生成 P4 runtime config。
- 收集 summary、rosbag profile、日志和 Foxglove notes。
- 验证 setpoint owner 唯一。

不负责：

- 发布飞控 movement setpoint。
- 直接调用 Gazebo set pose。
- 在 host 侧伪造 FCU state。

### 5.2 FCU state watcher

负责：

- 订阅或调用官方 ArduPilot DDS 状态接口。
- 维护 FCU 状态快照。
- 输出 controller 可以消费的 readiness status。

建议状态字段：

```json
{
  "time_received": true,
  "prearm_available": true,
  "prearm_ok": true,
  "mode": "GUIDED",
  "mode_ok": true,
  "armed": true,
  "arm_ok": true,
  "takeoff_requested": true,
  "takeoff_ok": true,
  "local_position_ready": true,
  "rangefinder_ready": true,
  "imu_ready": true,
  "external_nav_ready": false,
  "ready_for_setpoint": true
}
```

P4 中 `external_nav_ready=false` 不一定 blocked，因为 P4 不验收 P6 hover。但如果 P4 配置要求 ExternalNav，则必须把缺失写入 blocker。

### 5.3 FCU controller

负责：

- 持有唯一 setpoint ownership。
- 在 FCU 未 ready 时拒绝 movement intent。
- 顺序执行：
  - wait FCU time；
  - prearm check；
  - switch GUIDED；
  - arm；
  - takeoff；
  - hold；
  - optional yaw/local target smoke；
  - final hold 或 land/cleanup。
- 把 mission intent 转成统一 FCU setpoint output。
- 输出 `/navlab/fcu/controller/status`。
- 输出 `/navlab/fcu/setpoint/intent` 和 `/navlab/fcu/setpoint/output` 诊断。

不负责：

- 自己读取 Gazebo truth 做控制。
- 自己消费 `/slam/odom` 做导航规划。
- 绕过 readiness gate 发运动 setpoint。
- 与另一个 controller 共享 setpoint output。

### 5.4 Mission layer

负责：

- 发布任务意图。
- 记录任务阶段。
- 接收 controller ack/reject。

不负责：

- 直接控制 FCU。
- 直接控制 Gazebo。
- 直接把 SLAM/Gazebo truth 转成 setpoint。

### 5.5 SLAM backend

P4 中 SLAM backend 只提供观测基础和 P6 前置上下文。P4 可以启动 P3 backend 并记录 `/slam/odom` 状态，但 P4 不因为 `/slam/odom` 漂移而直接判定 hover 成功或失败。

P4 summary 必须明确：

```json
{
  "slam_hover_claim": "not_evaluated",
  "external_nav_hover_claim": "not_evaluated"
}
```

## 6. 状态机

P4 controller 状态机建议：

```text
init
  -> wait_fcu_time
  -> wait_prearm_service
  -> prearm_check
  -> set_guided
  -> wait_guided
  -> arm
  -> wait_armed
  -> takeoff
  -> wait_takeoff_ack
  -> wait_local_position
  -> hold_ready
  -> optional_setpoint_smoke
  -> final_hold
  -> complete
```

失败状态：

```text
blocked_prearm
blocked_guided
blocked_arm
blocked_takeoff
blocked_local_position
blocked_owner_conflict
blocked_setpoint_output
blocked_direct_set_pose
timeout
abort
```

每个状态转换必须写入 summary 和 rosbag 可回放 topic，至少包含：

- state name；
- enter time；
- exit time；
- reason；
- FCU observed state；
- command sent count；
- ack/result；
- blocker。

## 7. Setpoint ownership contract

P4 必须建立唯一 setpoint owner contract。

建议字段：

```json
{
  "owner": "navlab_fcu_controller",
  "owner_id": "navlab-p4-fcu-controller",
  "output_route": "mavlink_bootstrap_plus_dds_cmd_vel",
  "movement_output_topics": [
    "/ap/v1/cmd_vel"
  ],
  "movement_output_services": [
    "/ap/v1/mode_switch",
    "/ap/v1/arm_motors",
    "/ap/v1/experimental/takeoff"
  ],
  "competing_publishers": [],
  "set_pose_count": 0
}
```

blocked 条件：

- movement output topic 有多个非 rosbag publisher。
- mission node 直接发布 movement output。
- pose mirror 或 simulation helper 仍在写 Gazebo pose。
- controller 未 ready 时发送 movement setpoint。
- setpoint output route 不是配置允许的官方 DDS 或明确等价 route。

## 8. 控制接口口径

P4 当前采用 `mavlink_bootstrap_plus_dds_cmd_vel` route：

- GUIDED、arm、takeoff 使用 MAVLink bootstrap。
- FCU 状态观测使用官方 ArduPilot ROS2/DDS `/ap/v1/*` topics。
- 运动 setpoint 输出使用官方 DDS topic `/ap/v1/cmd_vel`。
- summary 必须明确 `official_control_claim=false`，`mavlink_bootstrap_claim=true`。

这个 route 的原因是：官方 `ardupilot_cartographer` README 的 Nav2 示例中，起飞步骤也是通过 MAVProxy/MAVLink 完成：

```text
mode guided
arm throttle
takeoff 2.5
```

随后 Nav2 通过 `/cmd_vel -> /ap/cmd_vel` 继续发送运动速度指令。因此 P4 的验收口径不是“纯 DDS service 已完整可用”，而是“官方示例兼容的 MAVLink 起飞 bootstrap + DDS 状态/运动 topic 面”。

P4 仍然保留纯 DDS route 的配置和 doctor 检查：

```text
/ap/v1/prearm_check
/ap/v1/mode_switch
/ap/v1/arm_motors
/ap/v1/experimental/takeoff
/ap/v1/cmd_vel 或官方等价 setpoint topic
/ap/v1/pose/filtered
/ap/v1/twist/filtered
/ap/v1/status
```

但纯 DDS route 只有在 service request 和 response 都可用时，才能标记为：

```json
{
  "control_route": "official_dds",
  "official_control_claim": true
}
```

### 8.1 当前官方示例和 P4 验收差异

P4 需要区分两件事：

- 官方 ROS2/DDS topic 面可用：`/ap/v1/time`、`/ap/v1/pose/filtered`、`/ap/v1/twist/filtered`、`/ap/v1/status` 等可以作为 FCU 状态观测。
- 官方 ROS2/DDS service 面真实可调用：`/ap/v1/prearm_check`、`/ap/v1/mode_switch`、`/ap/v1/arm_motors`、`/ap/v1/experimental/takeoff` 不只要可发现，还必须返回 response。

2026-06-06 的 P4 验证中，service replier 可发现，但 `ros2 service call` 和 P4 controller runtime 都收不到 response。因此当前 P4 不声明纯 DDS control pass；它声明的是官方示例兼容 route：

```json
{
  "control_route": "mavlink_bootstrap_plus_dds_cmd_vel",
  "official_control_claim": false,
  "mavlink_bootstrap_claim": true
}
```

纯 DDS service response 链路是后续改进项，不能混入当前 P4 已完成结论。

## 9. Topic 和接口要求

P4 required input topics：

```text
/tf
/tf_static
/ap/v1/time
/ap/v1/pose/filtered
/ap/v1/twist/filtered
/ap/v1/status
/ap/v1/cmd_vel
/rangefinder/down/range
/rangefinder/down/status
/imu
```

`/clock` 是 optional replay topic。P4 仍会探测 `/ap/v1/prearm_check`、`/ap/v1/mode_switch`、`/ap/v1/arm_motors`、`/ap/v1/experimental/takeoff`，但在 `mavlink_bootstrap_plus_dds_cmd_vel` route 下不要求 DDS service response 作为通过条件。

P4 controller topics：

```text
/navlab/fcu/state
/navlab/fcu/controller/status
/navlab/fcu/setpoint/intent
/navlab/fcu/setpoint/output
/navlab/fcu/owner/status
```

P4 optional diagnostic topics：

```text
/scan
/slam/odom
/navlab/slam/status
/external_nav/status
/odometry
```

## 10. Summary 字段

P4 summary 建议：

```json
{
  "ok": true,
  "blocked": false,
  "blockers": [],
  "p4_fcu_controller": {
    "official_bringup": true,
    "control_route": "mavlink_bootstrap_plus_dds_cmd_vel",
    "official_control_claim": false,
    "mavlink_bootstrap_claim": true,
    "state_machine": {
      "state": "complete",
      "visited": [],
      "transitions": [],
      "timeouts": []
    },
    "fcu_state": {
      "time_received": true,
      "prearm_service_available": true,
      "prearm_ok": true,
      "guided_ok": true,
      "arm_ok": true,
      "takeoff_ok": true,
      "local_position_ready": true
    },
    "owner": {
      "owner": "navlab_fcu_controller",
      "unique": true,
      "competing_publishers": [],
      "set_pose_count": 0
    },
    "setpoints": {
      "intent_count": 0,
      "output_count": 0,
      "rejected_before_ready": 0,
      "hover_setpoint_count": 0,
      "yaw_setpoint_count": 0,
      "local_position_target_count": 0
    },
    "claims": {
      "hover_claim": "not_evaluated",
      "slam_hover_claim": "not_evaluated",
      "exploration_claim": "not_evaluated"
    }
  },
  "rosbag_profile": {}
}
```

## 11. Rosbag 和 Foxglove

P4 rosbag required topics：

```text
/clock
/tf
/tf_static
/ap/v1/time
/ap/v1/pose/filtered
/ap/v1/twist/filtered
/ap/v1/status
/rangefinder/down/range
/rangefinder/down/status
/imu
/navlab/fcu/state
/navlab/fcu/controller/status
/navlab/fcu/setpoint/intent
/navlab/fcu/setpoint/output
/navlab/fcu/owner/status
```

P4 optional topics：

```text
/clock
/scan
/slam/odom
/navlab/slam/status
/external_nav/status
/odometry
/map
/submap_list
/trajectory_node_list
```

Foxglove 回放口径：

- 固定参考系优先使用 `map`；如果 P4 未启动 SLAM，可以使用 `odom`。
- 3D 面板只看 TF、FCU pose、必要的 scan/map 诊断。
- Raw Messages 面板查看 controller status、owner status、setpoint intent/output。
- Plot 面板查看 state transitions、local position z、rangefinder distance、setpoint output count。
- P4 bag 不能被解释为 hover 完成 bag。

## 12. Acceptance 语义

P4 acceptance 必须通过以下条件：

- P0 official DDS baseline healthy。
- P1 X2 scan gate 不被破坏。
- P2 rangefinder/IMU gate 不被破坏。
- P3 SLAM backend 可选启动时不被破坏。
- FCU state watcher 能观测 `/ap/v1/*` 状态。
- controller 能通过配置 route 完成 GUIDED、arm、takeoff、local position ready。
- 当前已验收 route 为 `mavlink_bootstrap_plus_dds_cmd_vel`。
- 所有 movement setpoint 都来自唯一 owner。
- 未 ready 前的 movement intent 被拒绝或排队，不会直接输出。
- summary 中 `set_pose_count == 0`。
- summary 中 `hover_claim=not_evaluated`。

P4 blocked 条件：

- FCU time 收不到。
- 当前 route 需要的 MAVLink bootstrap 不可用。
- GUIDED 切换失败。
- arm 失败。
- takeoff 失败。
- local position 长时间不可用。
- movement output 有竞争 publisher。
- direct set pose 出现。
- mission 绕过 controller 直接发 movement setpoint。
- rosbag required topics 缺失。

## 13. 推荐命令

建议命名：

```text
uv run --project orchestration python orchestration/main.py fcu-controller-doctor
uv run --project orchestration python orchestration/main.py fcu-controller-acceptance 90
```

doctor 只检查：

- 依赖和配置；
- 官方 DDS 控制接口是否存在；
- controller output route 是否可构建；
- setpoint owner 配置是否唯一。

acceptance 才启动完整运行链路并输出 rosbag/summary。

## 14. P4 完成后才能进入什么

P4 完成后，可以进入：

- P5 frame contract 自动验收；
- P6 真实 SLAM hover gate。

P4 未完成时，不应进入：

- P6 hover completion；
- P7 小范围运动；
- P8 探索任务。

原因是后续所有任务都依赖“只有一个 controller 能向 FCU 发运动指令”这个前提。
