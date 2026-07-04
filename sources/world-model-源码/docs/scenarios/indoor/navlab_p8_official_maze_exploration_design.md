# P8 官方 maze 探索任务设计

## 1. 目标

P8 的目标是在 P0-P7 已经通过的基础上，证明 NavLab 的官方 `iris_maze`
场景可以完成一次可回放、可验收、不碰撞的探索任务：

```text
P6 hover ready
  -> P7 motion ready
  -> SLAM map / odom healthy
  -> exploration local goal
  -> FCU unique controller 执行动作
  -> safety monitor 持续约束
  -> coverage / progress 可度量
  -> final hover 或安全停止
```

P8 只回答：

> 当前官方 maze/Iris 场景中，在 P6 hover 和 P7 motion 都成立后，系统是否能只用
> SLAM map、scan、TF、FCU state 和任务状态完成一个 bounded exploration task，并能用
> rosbag/Foxglove 复现过程？

P8 通过后，才能说“官方 maze 中的最小探索闭环已评价”。P8 不回答 Foxglove-lite replay artifact、NavLab 8 字形
world/model 迁移、真机部署、长期鲁棒巡航或完整生产级 Nav2
navigation stack 是否完成。

## 2. 为什么 P8 必须单独做

P6 已经证明真实 SLAM feedback 可以支撑静止悬停。P7 已经证明官方 maze 中的
forward、back、yaw scan 和 stop hold 可以通过唯一 FCU controller 执行。但探索任务会
引入新的失败模式：

- local goal 选择可能把飞机推向死胡同、墙体或不可达区域。
- yaw scan、前进、停止之间可能出现状态机竞争。
- coverage 指标可能被 topic 存在误判为“已经探索”。
- safety monitor 可能只在单步 motion 中有效，无法覆盖长任务。
- SLAM map 增长、frontier/局部目标和 FCU 执行之间可能不同步。
- controller ownership 可能被 exploration coordinator 意外绕过。
- Gazebo truth 很容易被误用为“答案式地图”或规划输入。

因此 P8 需要把“可以做最小动作”推进到“可以执行受限探索任务”，但仍然把 replay artifact、world/model
迁移、真机实飞和完整长期 autonomy 放到后续阶段。

## 3. P8 范围

P8 包含：

- 继续使用官方 `iris_maze` world 和 Iris 机体。
- 继续使用 P1 X2 `/scan` 链路作为 SLAM 和避障输入。
- 继续使用 P2 rangefinder / IMU 链路。
- 继续使用 P3 SLAM backend 输出 `/slam/odom`、`/map` 和相关状态。
- 继续使用 P4 唯一 FCU controller，不新增第二个 `/ap/v1/cmd_vel` owner。
- 继续使用 P5 frame contract。
- 继续使用 P6 hover readiness 作为探索起点。
- 继续使用 P7 motion gate 作为动作能力前置条件。
- 新增 exploration coordinator，负责选择局部目标、触发 yaw scan、记录任务状态。
- 新增或固化 exploration intent/status/coverage topic。
- 新增 collision/stuck/progress/coverage gate。
- 生成 P8 summary、MCAP rosbag、Foxglove notes 和失败 blocker。

P8 不包含：

- 不替换 NavLab 8 字形 world。
- 不替换 NavLab 自定义机体模型。
- 不直接读取 Gazebo truth 作为地图、规划、控制、SLAM 或 ExternalNav 输入。
- 不允许 direct set pose。
- 不允许 exploration coordinator 直接发布 `/ap/v1/cmd_vel`。
- 不要求一次实现完整生产级 Nav2；可以先用 bounded frontier-lite / corridor probing
  策略验收探索闭环。
- 不要求覆盖 maze 的所有理论可达空间；P8 只要求达到文档化阈值并能解释未覆盖区域。
- 不做真机部署。

## 4. 目标架构

P8 目标架构是：

```text
Gazebo official iris_maze + Iris
  -> X2 /scan + IMU + rangefinder
  -> SLAM backend
  -> /slam/odom + /map + TF
  -> ExternalNav bridge
  -> ArduPilot EKF / local position
  -> P6 hover readiness
  -> P7 motion readiness
  -> P8 exploration coordinator
       -> local goal / yaw scan / stop intent
       -> /navlab/fcu/setpoint/intent
  -> unique navlab_fcu_controller
       -> /ap/v1/cmd_vel
  -> safety / stuck / coverage monitors
  -> P8 summary + MCAP + Foxglove notes
```

P8 的核心边界：

```text
exploration coordinator 只能发布任务意图或 FCU setpoint intent
唯一 FCU controller 才能发布 /ap/v1/cmd_vel
Gazebo truth 只能进入 diagnostic/summary 对照，不能进入策略输入
```

## 5. 服务职责

### 5.1 P8 orchestration / acceptance

负责：

- 提供 P8 doctor / acceptance task。
- 启动 P0-P7 已验证的 baseline、sensor、SLAM、ExternalNav bridge 和 FCU controller。
- 生成 P8 runtime config。
- 录制 P8 rosbag profile。
- 执行 P6 hover prerequisite。
- 执行或读取 P7 motion prerequisite。
- 启动 P8 exploration coordinator。
- 收集 coverage、collision、stuck、owner、truth usage 和 pipeline health。
- 写出 summary、Foxglove notes 和 blocker。

不负责：

- 不直接选择每个 motion setpoint。
- 不绕过 FCU controller。
- 不把 rosbag topic 存在当作 exploration 完成。

### 5.2 P8 exploration coordinator

负责：

- 等待 P6 hover readiness 和 P7 motion readiness。
- 读取 SLAM map、scan、TF、FCU state、motion status 和任务状态。
- 选择 bounded local goal 或 yaw scan 行为。
- 只发布 exploration status、goal、coverage 和 FCU setpoint intent。
- 在 clearance 不足、progress 不足或 controller 不 ready 时触发 stop intent。
- 记录每个 accepted goal/action 的原因、结果和耗时。

必须记录：

- `strategy`: `frontier_lite`、`corridor_probe`、`scripted_bounded_exploration` 等。
- `goal_source`: `slam_map`、`scan_clearance`、`task_state`。
- `accepted_goals` / `rejected_goals`。
- `yaw_scan_count`。
- `forward_probe_count`。
- `stop_count`。
- `final_task_state`。

禁止：

- 直接发布 `/ap/v1/cmd_vel`。
- 直接调用 Gazebo pose reset 或 set pose。
- 读取 Gazebo truth 作为 target、frontier、costmap 或 coverage 输入。
- 在 P6/P7 前置 gate 未满足时执行探索动作。

### 5.3 Unique FCU controller

负责：

- 复用 P4/P6/P7 唯一 setpoint owner。
- 接收 P8 exploration coordinator 的 setpoint intent。
- 把 intent 转换为 `/ap/v1/cmd_vel` 或等价官方控制输出。
- 输出 `/navlab/fcu/controller/status`、`/navlab/fcu/setpoint/output` 和 owner 状态。
- 在 stale、owner conflict、FCU not ready 或 stop guard 触发时拒绝 intent。

P8 必须保持：

```text
owner.unique == true
set_pose_count == 0
competing_publishers == []
```

### 5.4 SLAM / map / localization health monitor

负责：

- 监控 `/slam/odom` 频率、stale、jump 和 frame。
- 监控 `/map` 是否持续可用且不是空地图。
- 监控 map growth 或 explored cell growth。
- 监控 ExternalNav 和 FCU local position 是否持续 healthy。
- 把 Gazebo truth 只作为 diagnostic 对照，不允许进入 SLAM 或 planning 输入。

P8 必须记录：

- `slam_odom.hz`。
- `slam_odom.max_gap_sec`。
- `map.hz` 或最新 map age。
- `map.known_cell_count`。
- `map.known_cell_growth`。
- `external_nav.hz`。
- `fcu.local_position_hz`。

### 5.5 Safety / collision / stuck monitor

负责：

- 监控 scan clearance。
- 监控 stop drift。
- 监控 collision diagnostic。
- 监控 stuck：有 intent 但位移、yaw 或 map growth 长时间不足。
- 在 safety violation 时触发 stop，并把 P8 标为 blocked。

P8 safety 不依赖 Gazebo truth 做规划，但可以把 Gazebo truth collision/contact 作为诊断证据。
如果 Gazebo truth diagnostic 与 scan/FCU 状态冲突，summary 必须记录冲突而不是静默通过。

### 5.6 Coverage / replay monitor

负责：

- 记录探索窗口内的已知地图 cell、可通行 cell 或探索面积变化。
- 记录路径长度、动作数、goal 数、yaw scan 数和 stop 数。
- 记录 final hover / final stop 状态。
- 生成 Foxglove replay notes：固定参考系、关键 topic、起止时间和判定窗口。

Coverage 不能只用 Gazebo truth 计算。允许使用 Gazebo truth 作为 diagnostic 对照，例如估计真实路径长度或碰撞位置，但正式 coverage claim 必须来自 SLAM map / scan / task state。

## 6. Gate 判定

P8 acceptance 建议至少包含：

```text
bootstrap window:       P0-P5 baseline health
hover window:           P6 hover readiness
motion window:          P7 motion readiness
exploration window:     goal selection + action execution + safety + coverage
final window:           stop / hover hold + summary
```

### 6.1 P8 通过条件

P8 通过必须满足：

- `ok == true`。
- `blocked == false`。
- `blockers == []`。
- `hover_claim == evaluated`。
- `motion_claim == evaluated`。
- `exploration_claim == evaluated`。
- P6 hover prerequisite `ok == true`。
- P7 motion prerequisite `ok == true`。
- `uses_gazebo_truth_as_input == false`。
- `owner.unique == true`。
- `set_pose_count == 0`。
- `competing_publishers == []`。
- exploration 至少完成配置中的最小 goal/action 数。
- coverage 或 map growth 达到配置阈值。
- `collision.detected == false`。
- `stuck.blocked == false`。
- final stop / hover drift 在阈值内。
- SLAM、ExternalNav、FCU local position、scan、IMU、rangefinder 在 exploration window 内 healthy。
- rosbag profile `ok == true`，required topics 全部非零。

### 6.2 P8 阻塞条件

P8 失败必须写入具体 blocker，例如：

```text
P6 hover prerequisite failed
P7 motion prerequisite failed
exploration coordinator published /ap/v1/cmd_vel directly
Gazebo truth used as exploration input
owner conflict detected
set_pose_count > 0
no accepted exploration goals
coverage growth below threshold
scan clearance below threshold
collision diagnostic triggered
stuck timeout exceeded
SLAM map stale during exploration
ExternalNav stale during exploration
FCU local position stale during exploration
rosbag required topic missing
```

## 7. Topic 和 rosbag 要求

P8 rosbag required topics 至少包含：

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
/map
/submap_list
/trajectory_node_list

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
/navlab/exploration/status
/navlab/exploration/goal
/navlab/exploration/coverage
```

P8 optional diagnostic topics：

```text
/odometry
/navlab/frame_contract/status
/navlab/x2/vendor_scan
/navlab/x2/scan_ideal
/sim/x2/status
/rangefinder/down/scan_ideal
/navlab/vehicle/markers
/navlab/exploration/frontiers
/navlab/exploration/path
/navlab/exploration/markers
```

Rosbag profile 必须记录：

- required topic 是否存在。
- required topic message count。
- required topic 频率或 max gap。
- exploration window 起止时间。
- 每个 accepted goal/action 的起止时间。
- final stop / hover window。

## 8. Summary schema

P8 summary 顶层建议：

```json
{
  "ok": true,
  "blocked": false,
  "blockers": [],
  "hover_claim": "evaluated",
  "motion_claim": "evaluated",
  "exploration_claim": "evaluated",
  "uses_gazebo_truth_as_input": false,
  "p6_hover_prerequisite": {
    "ok": true,
    "artifact": "artifacts/.../summary.json"
  },
  "p7_motion_prerequisite": {
    "ok": true,
    "artifact": "artifacts/.../summary.json"
  },
  "p8_exploration": {
    "ok": true,
    "strategy": "frontier_lite",
    "control_route": "unique_fcu_controller",
    "accepted_goals": 0,
    "rejected_goals": 0,
    "actions": {
      "forward_probe": 0,
      "yaw_scan": 0,
      "stop": 0
    },
    "final_task_state": "final_hover"
  },
  "coverage": {
    "ok": true,
    "known_cell_count_start": 0,
    "known_cell_count_end": 0,
    "known_cell_growth": 0,
    "estimated_explored_area_m2": 0.0,
    "path_length_m": 0.0,
    "thresholds": {
      "min_known_cell_growth": 0,
      "min_accepted_goals": 0,
      "min_path_length_m": 0.0
    }
  },
  "safety": {
    "ok": true,
    "min_scan_clearance_m": 0.0,
    "stop_drift_m": 0.0,
    "final_drift_m": 0.0
  },
  "collision": {
    "detected": false,
    "source": "scan_and_diagnostic"
  },
  "stuck": {
    "blocked": false,
    "events": []
  },
  "slam_odom": {
    "healthy": true,
    "hz": 0.0,
    "max_gap_sec": 0.0
  },
  "map": {
    "healthy": true,
    "known_cell_growth": 0,
    "latest_age_sec": 0.0
  },
  "external_nav": {
    "healthy": true,
    "hz": 0.0
  },
  "fcu": {
    "local_position_healthy": true,
    "local_position_hz": 0.0,
    "final_state": "GUIDED"
  },
  "owner": {
    "unique": true,
    "set_pose_count": 0,
    "competing_publishers": []
  },
  "rosbag_profile": {
    "ok": true,
    "required_topics": {},
    "missing_topics": [],
    "zero_count_topics": []
  }
}
```

字段语义：

- `exploration_claim=evaluated`：P8 已真实评价探索任务。
- `hover_claim=evaluated`：P8 复用并确认 P6 hover 前置条件。
- `motion_claim=evaluated`：P8 复用并确认 P7 motion 前置条件。
- `uses_gazebo_truth_as_input=false`：Gazebo truth 没有进入 SLAM、ExternalNav、planning 或控制输入。
- `control_route=unique_fcu_controller`：探索动作没有绕过唯一 controller。
- `coverage.ok=true`：coverage 或 map growth 达到 P8 配置阈值。

## 9. 和后续阶段的关系

P8 通过后只能说明：

- 官方 `iris_maze` 中可以完成 bounded exploration task。
- 探索策略使用 SLAM map、scan、TF、FCU state 和任务状态。
- P6 hover、P7 motion 和 P8 exploration 的 claim 已分开评价。
- 唯一 controller 边界在探索任务中仍然成立。
- rosbag/Foxglove 可以复现完整探索过程。

P8 不说明：

- P9 Foxglove-lite replay artifact 已经生成。
- NavLab 8 字形 world/model 已经迁移。
- 真机部署已经完成。
- 所有 maze 空间都已完整覆盖。
- 生产级 Nav2 stack 已完成。
- 长时间自主巡航已经可靠。

这些分别进入 P9、后续 world/model migration、真机迁移记录和 navigation hardening。
