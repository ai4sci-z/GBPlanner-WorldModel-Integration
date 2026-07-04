# P13 Nav2 室内导航与主动探索设计

## 1. 背景和目标

P8 已经证明 NavLab 可以在官方 maze 中完成可回放、受限的 exploration task。
P9/P10/P11/P12 进一步把 replay、scan integrity、2D scan stabilization 和 realistic
airframe disturbance envelope 做成了验收链路。

P13 的目标是在这些安全边界成立之后，把 P8 的轻量探索升级为 Nav2-backed
indoor navigation workflow：

```text
Cartographer /map + /slam/odom
  -> Nav2 global/local costmap
  -> Nav2 planner/controller/BT navigator
  -> NavLab navigation intent adapter
  -> single FCU controller
  -> ArduPilot /ap/v1/cmd_vel
```

P13 只回答：

> 在不让 Nav2 直接拥有 FCU 输出、不使用 Gazebo truth、不绕过 P10/P11/P12 scan
> contract 的前提下，Nav2 能否在官方 maze 中生成安全、可解释、可回放的 2D
> navigation / exploration intent，并通过 NavLab 单一 FCU owner 执行、返航和降落？

P13 通过后，操作者应该能判断：

- Nav2 是否能稳定消费 NavLab 的 `/map`、`/slam/odom`、TF 和 stabilized `/scan`。
- global/local costmap 是否正确更新 obstacle / inflation layer。
- Nav2 goal、path、recovery 和 failure 是否能被 mission summary 解释。
- Nav2 输出是否始终经过 NavLab intent adapter 和唯一 FCU controller。
- `ideal` 和 `realistic` simulation profile 下导航是否都能安全完成。

迁移前置条件：

- P13 不负责重新定义 SLAM/FCU 基础边界。Go sim 必须先满足
  `docs/general/orchestration_sim_python_parity_audit.md` 中的旧 Python
  orchestration parity。
- `/map` 和 `/slam/odom` 必须来自 Cartographer/SLAM backend。Nav2 seed map
  只能发布在 `/navlab/navigation/seed_map`，不能发布或冒充 `/map`。
- `/odometry`、Gazebo pose TF、seed map 和 official maze overlay 默认只能作为
  diagnostic/review artifact。除非能证明来源有真机等价传感器，否则不能作为
  Cartographer、Nav2、ExternalNav、controller 或 `/slam/odom` 的输入。
- `/navlab/official_maze/map` 只能用于 Foxglove review overlay，不能进入 Nav2
  costmap、planner、controller 或任务验收。

## 2. 参考来源

### 2.1 Navigation2 issue #3773

`ros-navigation/navigation2#3773` 说明 ArduPilot + Cartographer + Nav2 的组合存在实际参考价值：作者使用 ArduPilot ROS2 / AP_DDS、Cartographer 和 Nav2，在 remap
`/cmd_vel -> /ap/cmd_vel` 后能通过 Nav2 `/goal_pose` 驱动 copter。

这个 issue 对 P13 的启发不是“直接让 Nav2 控制 FCU”，而是：

- ArduPilot ROS2 / DDS 与 Nav2 的 topic 级集成是可行方向。
- `map -> odom -> base_link`、Cartographer output 和 Nav2 costmap 是关键风险点。
- 能发 goal 不等于导航完成；costmap obstacle layer、inflation、TF 和避障必须单独验收。

P13 因此把 costmap health 作为一等验收项，而不是只检查 NavigateToPose action 返回成功。

### 2.2 Altair-Silent

`/home/nn/workspace/3588/examples/Altair-Silent` 是室内 GPS-denied drone navigation
参考工程。它使用 2D LiDAR SLAM、Nav2 behavior-tree navigation、MAVROS/ArduPilot
和 staged mission workflow。可参考的结构包括：

| Altair-Silent 组件 | P13 可借鉴点 | P13 调整 |
|---|---|---|
| `silent_bringup` | launch / system composition | 改为 NavLab sim runtime artifacts / ROS2 launch contract |
| `silent_nav2` | Nav2 params、BT、planner/controller/costmap config | 保留 Nav2 思路，不照搬 MAVROS remap |
| `silent_controllers` | 集中式 vehicle controller、velocity fusion | NavLab 仍保持 single FCU owner |
| `vehicle_state_watcher` | FCU ready 后激活 controller | 映射到 `/ap/v1/status`、GUIDED、armed、local position gate |
| `silent_explorer` | corner/frontier style exploration | 抽象为 bounded frontier / waypoint selector |
| `planner_node` | 多阶段 mission workflow | 抽象为 takeoff -> nav2 ready -> goals -> return-home -> land |
| `silent_msgs` | mission/service message boundary | 映射到 contracts/proto 或 NavLab task summary schema |

不能照搬：

- Altair-Silent 的主飞控接口是 MAVROS；NavLab P13 默认使用 ArduPilot official ROS2 / DDS `/ap/*` contract。
- Altair-Silent 的 window detection / window pass 是竞赛业务；P13 不做穿窗。
- Altair-Silent 的 Nav2 速度输出不能直接成为 NavLab FCU owner。

## 3. P13 范围

P13 包含：

- Nav2 bringup contract：planner server、controller server、BT navigator、lifecycle manager。
- Nav2 costmap contract：global/local costmap、obstacle layer、inflation layer、stale / empty / invalid detection。
- Nav2 action contract：NavigateToPose / waypoint sequence / recovery status / action result。
- NavLab navigation intent adapter：把 Nav2 `/cmd_vel` 或 controller output 转成 `/navlab/fcu/setpoint/intent`。
- Single FCU owner：仍由 NavLab FCU controller 输出 `/ap/v1/cmd_vel`。
- Bounded 2D drone adapter：固定高度、XY velocity limit、yaw rate limit、clearance gate、stop/hold。
- Mission workflow：takeoff、Nav2 ready、goal selection、navigation window、replan/recovery、return-home、land/disarm。
- Active exploration 首版：bounded frontier / waypoint selector，逐步扩大覆盖范围。
- Acceptance summary：记录 Nav2、costmap、SLAM、scan、FCU、owner、landing 和 artifact evidence。
- `ideal` + `realistic` simulation profile matrix。

P13 不包含：

- 不做 3D navigation / PointCloud pipeline。
- 不接 AirSim / PX4 / Unreal 教程路线。
- 不做穿窗任务。
- 不允许 Nav2 直接发布到 `/ap/v1/cmd_vel` 并绕过 FCU controller。
- 不使用 Gazebo truth、official maze overlay 或 SDF wall geometry 作为 planning input。
- 不降低 P10/P11/P12 scan / no-truth / owner / no-set-pose 安全边界。
- 不要求真机自由飞行；真机前仍需 P14 tethered indoor preflight。

## 4. 关键设计决定

### 4.1 Nav2 不能直接拥有 FCU 输出

P13 的最重要边界：

```text
Nav2 controller output
  -> navlab_navigation_adapter
  -> /navlab/fcu/setpoint/intent
  -> navlab_fcu_controller
  -> /ap/v1/cmd_vel
```

禁止：

```text
Nav2 /cmd_vel -> /ap/v1/cmd_vel
```

原因：

- NavLab 已经在 P4/P7/P8/P12 建立唯一 FCU owner contract。
- Landing、return-home、stop/hold、owner lease、mode window 和 no-set-pose gate 都在 NavLab controller / acceptance 层。
- Nav2 是 planner/controller source，不是飞控安全 owner。

如果 runtime plan 检测到 Nav2 或其它节点直接发布 `/ap/v1/cmd_vel`，P13 必须 blocked：

```text
nav2_direct_fcu_cmd_vel_detected
competing_cmd_vel_publishers
```

### 4.2 P13 是 2D Navigation，不是 3D Navigation

P13 继续使用 P10/P11/P12 验证过的 2D scan / SLAM contract：

```text
stabilized /scan
  -> Cartographer /map + /slam/odom
  -> Nav2 costmaps
  -> 2D path / velocity intent
```

高度策略：

- P13 首版固定任务高度。
- 高度保持由 FCU controller / rangefinder / existing hover gate 负责。
- Nav2 不输出 z control。
- Nav2 yaw/XY velocity 必须被 adapter 限幅。

P13 不解决：

- 3D 障碍物绕行。
- 垂直空间规划。
- 穿窗高度扫描。
- 复杂动态障碍建模。

### 4.3 Nav2 Costmap 是 P13 的核心风险点

参考 Navigation2 issue #3773，P13 不能只证明 goal_pose 能驱动飞机。必须单独验收：

```text
/global_costmap/costmap
/local_costmap/costmap
/global_costmap/published_footprint
/local_costmap/published_footprint
/plan
/cmd_vel or adapter input
```

Costmap gate 必须检查：

- costmap topic 有发布。
- resolution / frame / size 合理。
- obstacle layer 消费 stabilized `/scan`，不消费 raw scan。
- inflation layer 生效。
- local costmap 不 stale。
- obstacle cell count / lethal cell count 在合理范围内。
- costmap frame 与 `map -> odom -> base_link` TF 一致。
- official maze overlay 不作为 costmap input。

### 4.4 Nav2 Lifecycle 必须和 FCU Readiness 解耦

参考 Altair-Silent 的 StateWatcher 思路，P13 必须明确激活顺序：

```text
Gazebo/SITL ready
  -> SLAM ready
  -> FCU GUIDED / armed / local position healthy
  -> Nav2 lifecycle active
  -> adapter active
  -> mission goal allowed
```

如果 FCU 未 ready、SLAM stale、costmap stale 或 scan gate fail：

```text
adapter must hold
mission planner must not send new goal
Nav2 result cannot be accepted as task success
```

### 4.5 Mission Workflow 是多阶段状态机

P13 参考 Altair-Silent 的 mission workflow，但替换成 NavLab indoor navigation：

```text
1. Takeoff / Ready
2. Nav2 Activation
3. Initial Goal
4. Local Navigation
5. Exploration Step
6. Replan / Recovery
7. Return Home
8. Land / Disarm
```

每一阶段都必须写入 `/navlab/navigation/status` 和 summary，不能只看最后 action result。

## 5. P13 System Components

```text
navlab_bringup
  -> system integration & launch composition

navlab_nav2
  -> Nav2 params, BT, planner/controller/costmap config

navlab_navigation_adapter
  -> Nav2 cmd_vel/action output -> NavLab setpoint intent
  -> never directly owns FCU output

navlab_mission_planner
  -> task state machine
  -> maze-exit goal selection
  -> completion policy sequencing

navlab_explorer
  -> frontier / waypoint / coverage logic

navlab_slam
  -> Cartographer backend wrapper
  -> map / odom / TF health contract

navlab_controllers
  -> single FCU output owner
  -> altitude hold, yaw, velocity bounds, stop/hold

navlab_safety
  -> clearance, costmap, owner, no-truth, no-set-pose gates

navlab_msgs or contracts/proto
  -> navigation request/result
  -> mission stage events
  -> costmap health
  -> planner status

External:
  -> ArduPilot ROS2 / DDS
  -> Nav2
  -> Cartographer
  -> Gazebo
  -> ROS2
```

## 6. Topic / Frame Contract

Required input topics:

```text
/scan
/map
/slam/odom
/tf
/tf_static
/ap/v1/status
/ap/v1/pose/filtered
/navlab/fcu/controller/status
/navlab/fcu/owner/status
/navlab/scan_stabilization/status
```

Nav2 topics:

```text
/goal_pose or NavigateToPose action
/plan
/cmd_vel
/global_costmap/costmap
/local_costmap/costmap
/global_costmap/costmap_updates
/local_costmap/costmap_updates
/behavior_tree_log
/navigate_to_pose/_action/status
```

NavLab P13 topics:

```text
/navlab/navigation/status
/navlab/navigation/events
/navlab/navigation/goal
/navlab/navigation/path
/navlab/navigation/recovery
/navlab/navigation/costmap_health
/navlab/navigation/adapter/status
/navlab/exploration/frontiers
/navlab/exploration/coverage
```

Required frame chain:

```text
map -> odom -> base_link
base_link -> laser_frame
base_link -> imu_link
```

Frame rules:

- Nav2 global frame: `map`.
- Nav2 robot base frame: `base_link`.
- Nav2 odom frame: `odom` or Cartographer-compatible odom frame.
- `/scan` frame must match P10/P11 stabilized scan frame contract.
- No Gazebo truth frame can be used as Nav2 input.

## 7. Mission Workflow

### 7.1 Takeoff / Ready

Gate:

- FCU in GUIDED mode.
- armed and takeoff altitude reached.
- `/slam/odom` healthy.
- `/scan` stabilized and not stale.
- `/map` publishing.
- TF chain valid.
- no competing FCU owner.

### 7.2 Nav2 Activation

Gate:

- Nav2 lifecycle nodes active.
- planner / controller / BT navigator ready.
- global and local costmap publishing.
- obstacle layer has non-empty evidence.
- adapter is inactive until FCU and Nav2 are both ready.

### 7.3 Maze Exit Goal

Mission planner selects `exit_goal` as the real P13 endpoint:

- it represents the maze exit in the map frame.
- inside known or frontier-adjacent free space.
- within max radius from home.
- not behind an occupied / lethal costmap cell.
- yaw target bounded.

`bounded_goals` can still exist, but they are candidate/intermediate goals and
frontier-lite coverage evidence. They are not the semantic endpoint of P13. The
real task is:

```text
start pose -> Nav2 maze-exit goal -> completion policy -> landing gate
```

### 7.4 Local Navigation

During navigation:

- Nav2 produces path and velocity intent.
- adapter clamps XY velocity, yaw rate and acceleration.
- FCU controller remains only `/ap/v1/cmd_vel` publisher.
- clearance must stay above threshold.
- SLAM / map / costmap cannot go stale.

### 7.5 Exploration Step

P13 first exploration strategy:

```text
frontier_candidate
  -> costmap safety filter
  -> reachability / path length filter
  -> goal dispatch
  -> blacklist failed frontiers
  -> coverage update
```

Coverage metrics:

- known cell count growth.
- free cell count growth.
- frontier count.
- accepted goal count.
- rejected goal count with reasons.
- path length.
- goal success ratio.

### 7.6 Replan / Recovery

Allowed recovery:

- wait / hold.
- clear local costmap if configured and safe.
- choose alternate frontier.
- return home after repeated failure.

Not allowed:

- Gazebo set_pose.
- direct `/ap/v1/cmd_vel` bypass.
- ignoring stale SLAM/costmap and claiming success.

### 7.7 Completion Policy

Return-home and landing at the endpoint are two configurable completion
strategies, not separate task types.

- `land_in_place`: land at the current task endpoint. For P13 this means land at
  the maze exit.
- `return_home_then_land`: navigate back to `home_goal` with the same Nav2 +
  adapter + FCU owner path, then land.

Gate:

- completion policy recorded.
- home pose source recorded when return-home is required.
- path back to home exists or controlled hold/land fallback is used when
  `return_home_then_land` is configured.
- final stop drift below threshold.
- no collision / no floor-hit / no set_pose.

### 7.8 Land / Disarm

After navigation completes or aborts safely:

- stop navigation intent.
- apply configured completion policy.
- hold briefly before landing.
- land at endpoint or home depending on policy.
- disarm.
- write summary, rosbag and manifest artifacts.

The task-level time value is a deadline, not a required runtime. A task should
finish as soon as the mission goal and landing gate are satisfied. If the
deadline expires before completion, the task fails. After landing is confirmed,
orchestration keeps a short `completion_grace_sec` buffer for final status and
artifact flushing, then tears the runtime down instead of consuming the full
deadline.

## 8. Configuration Sketch

```toml
[nav2]
enabled = true
profile = "indoor_2d"
global_frame = "map"
odom_frame = "odom"
base_frame = "base_link"
scan_topic = "/scan"
map_topic = "/map"
cmd_vel_topic = "/cmd_vel_nav"
bt_xml = "configs/nav2/navlab_indoor_bt.xml"
planner_plugin = "GridBased"
controller_plugin = "FollowPath"
use_sim_time = true

[nav2.costmap]
global_costmap_topic = "/global_costmap/costmap"
local_costmap_topic = "/local_costmap/costmap"
required_layers = ["static_layer", "obstacle_layer", "inflation_layer"]
max_costmap_age_sec = 1.5
min_obstacle_cells = 1
max_unknown_ratio = 0.85
inflation_radius_m = 0.35
footprint_radius_m = 0.22

[navigation_adapter]
source_cmd_vel_topic = "/cmd_vel_nav"
setpoint_intent_topic = "/navlab/fcu/setpoint/intent"
status_topic = "/navlab/navigation/adapter/status"
max_xy_speed_mps = 0.25
max_yaw_rate_dps = 35.0
max_accel_mps2 = 0.35
fixed_altitude_m = 0.8
stop_on_stale_costmap = true
stop_on_stale_slam = true

[navigation_mission]
strategy = "bounded_frontier"
completion_policy = "land_in_place"
navigation_window_sec = 240.0
max_goal_radius_m = 0.45
min_clearance_m = 0.35
min_coverage_growth = 0.50
min_path_length_m = 4.0
min_accepted_goals = 3
max_recovery_count = 2

[navigation_mission.exit_goal]
id = "maze_exit"
x_m = 1.5
y_m = -0.5
yaw_rad = 0.0

[landing]
navigation_policy = "land_in_place"
completion_grace_sec = 3.0
```

## 9. Summary Schema

P13 summary should include:

```json
{
  "navigation_claim": "evaluated",
  "nav2_claim": "evaluated",
  "costmap_claim": "evaluated",
  "adapter_claim": "evaluated",
  "simulation_profile": "realistic",
  "profiles": {
    "ideal": {"ok": true},
    "realistic": {"ok": true}
  },
  "nav2": {
    "lifecycle_active": true,
    "navigate_to_pose_goals": 4,
    "succeeded_goals": 3,
    "failed_goals": 1,
    "recovery_count": 1
  },
  "costmap": {
    "global_ok": true,
    "local_ok": true,
    "local_costmap_update_frequency_hz": 5.0,
    "obstacle_layer_ok": true,
    "inflation_layer_ok": true,
    "max_age_sec": 0.4,
    "unknown_ratio": 0.32
  },
  "frontier": {
    "frontier_claim": "evaluated",
    "frontier_candidates": [
      {"id": "p13_probe_1", "source": "bounded_goal_map_costmap_seed"}
    ],
    "accepted_frontiers": [{"id": "p13_probe_1"}],
    "rejected_frontiers": [
      {"id": "unreachable_probe", "reason": "unreachable_blacklisted"}
    ],
    "blacklisted_goals": ["unreachable_probe"],
    "coverage_growth": 0.5,
    "min_coverage_growth": 0.5,
    "uses_gazebo_truth_as_input": false
  },
  "completion": {
    "completion_policy": "land_in_place",
    "exit_goal": {"id": "maze_exit"},
    "deadline_sec": 180.0,
    "completion_grace_sec": 3.0
  },
  "adapter": {
    "direct_fcu_cmd_vel": false,
    "max_xy_speed_mps": 0.25,
    "max_yaw_rate_dps": 35.0,
    "clamped_command_count": 2
  },
  "owner": {
    "unique": true,
    "cmd_vel_publishers": ["navlab_fcu_controller"]
  },
  "truth_control": {
    "uses_gazebo_truth_as_input": false,
    "set_pose_count": 0
  },
  "landing": {
    "policy": "land_in_place",
    "ok": true,
    "disarmed": true
  }
}
```

## 9.1 Live Debug Evidence

The 2026-06-14 live debugging slice resolved the `/cmd_vel_nav` ambiguity:

- Mission goal dispatch works: `navigation_mission_runtime.py` sends
  `NavigateToPose` goals only after controller, SLAM, map and costmap readiness.
- Nav2 accepts bounded goals; action-result timeout or status `6` is recorded
  separately from the physical navigation gate.
- `/cmd_vel_nav` is produced and consumed by the navigation adapter.
- The adapter publishes bounded `/navlab/fcu/setpoint/intent`.
- The FCU controller remains the only publisher to `/ap/v1/cmd_vel`.
- FCU bootstrap uses MAVLink heartbeat, GUIDED mode, arm retry and takeoff retry,
  then records the ACK evidence in controller status.
- Navigation task completion is evaluated from accepted goals, odom path length,
  coverage growth, recovery count and no-truth evidence; it does not require
  every Nav2 action result to return success.
- Landing evidence is evaluated from the final `/navlab/landing/status` sample.
  Earlier hover-probe landing blockers are diagnostic only and must not override
  a later navigation landing completion sample.

The current accepted live artifact is:

```text
artifacts/sim/navigation/20260614T062658Z/summary.json
```

It passed with `TASK_STATUS_OK`, empty blockers, `accepted_goals=3`,
`path_length_m=4.2269`, `coverage_growth=0.75`, adapter `intent_count=2928`,
controller `ready=true`, landing `ok=true`, and all required rosbag profiles
`ok=true`.

## 10. Acceptance

P13 `ok=true` requires:

- Nav2 lifecycle nodes active.
- `map -> odom -> base_link` TF valid for the navigation window.
- global/local costmap publishing and not stale.
- obstacle and inflation layers enabled and evidenced.
- Nav2 path / goal / recovery status recorded.
- `navigation_status_probe` samples navigation, adapter, controller and final
  landing status before returning success.
- adapter output bounded and converted to NavLab setpoint intent.
- NavLab FCU controller is the only `/ap/v1/cmd_vel` publisher.
- no Gazebo truth, no set_pose, no official maze overlay as planning input.
- `/scan` comes from stabilized P10/P11/P12 contract.
- SLAM, ExternalNav and FCU health do not regress.
- configured completion policy completes: `land_in_place` at maze exit or `return_home_then_land` via `home_goal`.
- `ideal` and `realistic` Stage 1 profile matrix passes.

Blocker examples:

```text
nav2_lifecycle_inactive
nav2_costmap_stale
nav2_obstacle_layer_missing
nav2_inflation_layer_missing
nav2_tf_invalid
nav2_goal_unreachable
nav2_recovery_limit_exceeded
nav2_direct_fcu_cmd_vel_detected
navigation_adapter_not_active
navigation_velocity_limit_exceeded
navigation_clearance_too_low
navigation_slam_stale
navigation_costmap_unknown_ratio_too_high
navigation_return_home_failed
navigation_landing_required
uses_gazebo_truth_as_input
set_pose_detected
competing_cmd_vel_publishers
```

## 11. 与 P8/P9/P10/P11/P12/P14 的关系

P8：证明可回放 bounded exploration task，不要求完整 Nav2 stack。

P9：提供 official maze overlay / Foxglove-lite review artifact，但 overlay 不能作为 P13 planning input。

P10/P11：提供 stabilized `/scan` 与 scan integrity / horizontal recovery contract。

P12：提供 `realistic` airframe disturbance envelope；P13 必须在该 envelope 下通过。

P13：把 P8 的探索升级为 Nav2-backed mission workflow，强化 costmap、action、adapter 和 recovery 语义。

P14：真机 tethered indoor preflight。P13 通过不等于可以无保护真机自由探索。

## 12. 完成后能说明什么

P13 通过后可以说明：

- Nav2 能在 NavLab 2D indoor contract 下工作。
- Nav2 costmap、path、action、recovery 和 mission summary 可解释。
- Nav2 没有绕过 NavLab single FCU owner。
- `ideal` 和 `realistic` profiles 下，Nav2 navigation 都能安全返航并降落。

P13 不说明：

- 3D obstacle navigation 已解决。
- 穿窗任务已完成。
- active frontier strategy 已经覆盖所有真实室内环境。
- 真机可以无保护自由飞行。

## Runtime Mode 分流

- `docker + simulation`：允许 Nav2、Gazebo/SITL、Cartographer、stabilized scan、official maze review artifacts。
- `process + real`：Nav2 real mode 必须只消费真实 `/scan`、真实 SLAM/map/TF、真实 FCU status；禁止 Gazebo/SITL、official maze overlay 和 sim-only costmap sources。
- real mode 下如果 Nav2 使用 simulation-only source，必须以 `runtime_mode_violation:*` blocker 失败。
- P13 real mode 首版目标是 topic/source/owner/costmap gate，不是无保护自由探索。
