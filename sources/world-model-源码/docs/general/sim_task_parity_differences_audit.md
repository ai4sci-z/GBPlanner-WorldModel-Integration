# Sim Task Parity 差异审计：hover / exploration / scan-robustness

## 1. 结论

这份文档只记录差异，不声明修复完成。

当前 Go sim 的 `hover`、`exploration`、`scan-robustness` 不能按旧 Python orchestration
等价完成来认定。三者都存在不同层面的 parity gap：

| task | 当前结论 | 主要问题 |
|---|---|---|
| `hover` | 不等价，最近一次 `TASK_STATUS_OK` 是假通过 | Go runtime 用 FCU controller readiness 和低高度 takeoff threshold 代替旧 `hover_mission.py` 的完整 MAVLink hover mission |
| `exploration` | 不等价，缺少完整 live summary 证据 | Go workflow 是时间分段的 `frontier_lite` intent publisher，不是旧 obstacle/mission phase gate；当前 artifact 只有 probe，没有完整通过 summary |
| `scan-robustness` | 不等价，不能按完成算 | Go helper 仍标 `ported_partial`，live profile / profile sweep / P10-P11-P12 证据链没有完整 live summary 证明 |

硬原则：

- 不能用 ACK、topic count、setpoint count 或静态 SLAM pose 冒充任务完成。
- 不能用 Gazebo truth、seed map、official overlay 或 bridge odometry 顶替算法输入。
- 没有完整 live summary 的任务必须是 `not_verified`，不能写成 done。
- 文档、summary、Foxglove 上传都必须跟 task 真实状态一致。
- 汇报必须 evidence-first：没有可追踪 summary/artifact/test 证明时，不能说
  `done`、`passed`、`parity complete` 或“可以进入下一阶段”。
- Foxglove lite 只是 review artifact，不是验收证据；只有 task summary 已真实通过时，
  才能把上传结果作为辅助查看材料。
- 一旦发现之前的完成声明是 false pass，必须先把 artifact 和文档标成
  `false_pass_found` / `not_equivalent`，再继续功能开发。

## 2. 审计基线

Baseline commit：

```text
a3e0f7a feat(command): add unified CLI tool package
```

需要对照的旧 Python 入口：

| 区域 | baseline 文件 |
|---|---|
| hover acceptance | `navlab/companion/hover_acceptance.py` |
| hover mission body | `navlab/companion/nodes/hover_mission.py` |
| exploration / obstacle mission acceptance | `navlab/companion/acceptance.py` |
| exploration / obstacle mission body | `navlab/companion/nodes/obstacle_mission.py` |
| P8 exploration gate | `orchestration/src/tasks/exploration_gate.py` |
| P10 scan integrity gate | `orchestration/src/tasks/scan_integrity_gate.py` |
| P11 scan stabilization gate | `orchestration/src/tasks/scan_stabilization_gate.py` |

当前 Go 侧主要文件：

| 区域 | 当前文件 |
|---|---|
| task YAML | `orchestration/sim/configs/tasks/*.yaml` |
| execution plan | `orchestration/sim/internal/tasks/helpers/execution_plan.go` |
| runtime script generation | `orchestration/sim/internal/tasks/helpers/runtime_specs.go` |
| result gate | `orchestration/sim/internal/tasks/gate_evaluation.go` |
| helper registry | `orchestration/sim/internal/tasks/helpers/registry.go` |

当前仍残留的 Python runtime：

| 区域 | 当前文件 |
|---|---|
| hover mission | `navlab/sim/companion/nodes/hover_mission.py` |
| obstacle mission | `navlab/sim/companion/nodes/obstacle_mission.py` |
| hover acceptance | `navlab/sim/companion/runtime/hover_acceptance.py` |
| mission acceptance | `navlab/sim/companion/runtime/acceptance.py` |

## 3. Hover 差异

### 3.1 旧 Python 语义

旧 hover 不是普通 controller ready gate，而是完整 MAVLink hover mission：

```text
wait external nav / IMU / attitude
  -> set GUIDED
  -> arm
  -> MAV_CMD_NAV_TAKEOFF
  -> LOCAL_POSITION_NED confirms airborne
  -> continuously send SET_POSITION_TARGET_LOCAL_NED at target z
  -> wait until abs(current_z_ned + takeoff_alt_m) <= tolerance
  -> enter hover_hold
  -> hold duration and drift pass
  -> landing / completion
```

旧 `hover_mission.py` 的关键条件：

- `decide_hover()` 只有在 `takeoff_ack_ok` 和 `airborne_seen` 后才进入 hover settle。
- 只有 `current_z_ned` 接近 `-takeoff_alt_m` 才进入 `hover_hold`。
- `hover_hold` 阶段持续发送 `SET_POSITION_TARGET_LOCAL_NED`。
- summary 要求 `hover_hold` 出现、`LOCAL_POSITION_NED` 有样本、drift duration 达标。

旧 `hover_acceptance.py` 的关键条件：

- 必须运行 `hover_mission.py`。
- summary `ok` 要求 `guided_seen`、`armed_seen`、`airborne_seen`、`local_position_count > 0`。
- `hover_ok` 要求 `mission_summary.ok == true`、`"hover_hold" in phases_seen`、`hover_drift.ok == true`。
- ExternalNav 必须来自 SLAM，不允许 Gazebo truth 输入。
- MAVLink ExternalNav 反馈必须证明 FCU 仍在新鲜发布 `LOCAL_POSITION_NED`；
  `local_position_count > 0` 只能说明历史上见过位置，不能单独作为健康条件。

### 3.2 当前 Go 语义

当前 Go 通过 `FCUControllerRuntimeScript()` 生成一个通用 FCU controller runtime。
它的 takeoff readiness 逻辑是：

```text
target_min = max(takeoff_min_height_m, takeoff_alt_m * takeoff_min_height_ratio)
```

当前 `hover.yaml`：

```yaml
takeoff_alt_m: 0.5
takeoff_min_height_m: 0.15
takeoff_min_height_ratio: 0.35
```

因此只要高度达到 `0.175m`，runtime 就可能把 takeoff 判为 ready。

当前 Go controller status 又把 `controller_ready(state)` 映射成 `state = "hover_hold"`。
这不是旧 Python 的 `hover_hold`，因为它没有证明：

- MAVLink local position 已达到目标高度附近。
- 真实 hover hold duration 达标。
- `hover_mission.py` 的 phase state machine 完整跑过。
- `LOCAL_POSITION_NED` 的目标高度误差满足旧 tolerance。

### 3.3 已观察到的假通过证据

当前 artifact：

```text
artifacts/sim/hover/20260615T115355Z/summary.json
```

关键字段：

```json
{
  "status": "TASK_STATUS_OK",
  "takeoff_alt_m": 0.5,
  "height_m": 0.1899999976158142,
  "target_min_m": 0.175,
  "pose_source": "slam_odom",
  "setpoint_intent_samples": 0,
  "mavlink_setpoint_count": 152
}
```

这个结果不能证明 hover 成功：

- 请求高度是 `0.5m`，证据高度只有约 `0.19m`。
- `target_min_m=0.175` 是 readiness threshold，不是 hover acceptance threshold。
- `pose_source=slam_odom` 的 drift 为 0 不能证明 FCU 到达目标高度。
- `setpoint_intent_samples=0` 说明没有任务 intent 驱动；只有 hold setpoint 数量。
- 该 summary 被标 `TASK_STATUS_OK` 是错误的验收口径。

### 3.4 Hover 必须修复的差异

- Go hover 必须恢复旧 `hover_mission.py` 的 phase contract，而不是只复用 P4 controller。
- `hover_hold` 必须只来自真实 mission phase，不允许由 controller ready 命名生成。
- takeoff 完成必须要求接近 `takeoff_alt_m`，不能用 `takeoff_min_height_ratio` 当任务完成证据。
- summary 必须记录 `target_alt_m`、`local_position_z_ned`、`altitude_error_m`、`hover_hold_duration_sec`。
- gate 必须拒绝 `height_m < takeoff_alt_m - tolerance`。
- Foxglove artifact 只有在 hover gate 真实通过后才能上传为有效 hover。

### 3.5 Hover 修复 TODO 分阶段

这部分是执行 TODO，不是完成声明。每个 phase 都必须留下 summary/artifact/test
证据；没有证据时状态写 `not_verified` 或 `blocked`。

#### Phase H0：冻结 false pass 入口

- [x] 把 `artifacts/sim/hover/20260615T115355Z/summary.json` 记录为
  `false_pass_found` 的反例，不再作为 hover success evidence 引用。
- [x] Go gate 中禁止把 `controller_ready` 直接命名或解释成真实 `hover_hold`。
- [x] Go gate 中禁止把 `takeoff_min_height_ratio` 的 readiness threshold 当成 hover
  completion threshold。
- [x] hover summary 若只达到 readiness threshold，必须产生 blocker，例如
  `hover_takeoff_target_altitude_not_reached`。

验收证据：

- [x] 单元测试覆盖 `0.5m` 目标高度但只到 `0.19m` 时必须 fail。
- [x] 文档不再把该 artifact 写成通过；旧 artifact 本身保留原始错误状态作为
  false-pass 反例。

#### Phase H1：恢复旧 hover mission phase contract

- [x] 明确 Go hover 的任务执行入口：不能只复用 P4 `fcu-controller` readiness。
- [x] Go orchestration 生成并启动 Python `navlab.sim.companion.nodes.hover_mission`
  wrapper；runtime 仍由 Python mission 节点负责，不能改成 Go runtime。
- [x] hover task composition 移除 `fcu-controller` runtime；`fcu-controller` 暂时只保留给
  exploration/navigation 这类 setpoint workflow task。
- [x] mission runtime 必须显式发布/记录 phases：
  `wait_ready`、`guided`、`arm`、`takeoff`、`hover_settle`、`hover_hold`、`landing`、
  `complete`。
- [x] `hover_hold` 只能由 mission runtime 根据 MAVLink `LOCAL_POSITION_NED` 和
  hold duration 进入，不能由 probe 或 controller status 合成。
- [x] 保留 ExternalNav / IMU readiness 要求；如果缺失必须 block，不能绕过。

验收证据：

- [x] `mission_summary.json` 包含 `phases_seen`，且 `hover_hold` 不是 controller
  ready 的别名。
- [x] `mission_summary.json` 包含 `guided_seen=true`、`armed_seen=true`、
  `takeoff_ack_ok=true`、`airborne_seen=true`。

#### Phase H2：恢复 MAVLink 高度和 setpoint 语义

- [x] takeoff command 使用 `MAV_CMD_NAV_TAKEOFF`，目标高度来自 task YAML。
- [x] mission runtime 必须订阅/读取 `LOCAL_POSITION_NED`。
- [x] airborne 只能代表“离地”，不能代表“到达 hover 目标高度”。
- [x] `hover_settle` 必须等待
  `abs(current_z_ned + takeoff_alt_m) <= hover_altitude_tolerance_m`。
- [x] airborne 后必须持续发送 `SET_POSITION_TARGET_LOCAL_NED`，目标 `z_ned`
  为 `-takeoff_alt_m`。
- [x] summary 必须记录 `target_alt_m`、`current_z_ned`、`altitude_error_m`、
  `local_position_count`、`setpoints_sent_count`。

验收证据：

- [ ] live summary 证明 `altitude_error_m <= hover_altitude_tolerance_m` 后才进入
  `hover_hold`。
- [x] 如果 `LOCAL_POSITION_NED` 不可用，任务 blocked。
- [x] 如果只靠 `GLOBAL_POSITION_INT` 或 ACK，没有 local NED hold evidence，任务
  blocked 或 degraded，不允许通过。

#### Phase H3：恢复 hover hold / drift / landing 验收

- [x] `hover_hold` 必须持续达到 `hover_hold_sec - tolerance`。
- [x] drift 计算必须基于 hover hold window 内的 MAVLink local position sample，
  并记录 horizontal / z drift。
- [x] hover body 完成后才允许进入 landing。
- [x] landing 必须记录 `land_command_accepted`、`touchdown_confirmed`、
  `disarmed`、`motors_safe`。
- [x] landing 未完成时 hover 不能标记成功。

验收证据：

- [x] `mission_summary.json` schema/gate 要求 `hover_body_ok=true`。
- [x] `mission_summary.json` schema/gate 要求 `landing_ok=true`。
- [x] 顶层 `summary.json` 中 hover mission、SLAM/rosbag、landing 证据一致；
  hover 不再依赖 `fcu-controller` evidence。
- [x] live `summary.json` 证明以上字段全部来自真实 run。

#### Phase H4：rosbag / Foxglove-lite 只作为复核输出

- [x] hover rosbag/lite required 只包含可回放和任务状态硬证据：`/tf`、
  `/tf_static`、`/map`、`/scan`、`/slam/odom`、`/navlab/hover/status`、
  `/navlab/landing/status`、`/rangefinder/down/range`。IMU、FCU status、
  rangefinder status 必须由 runtime probe 或 mission summary 记录，但不能因为
  未进入 lite replay 而把已经完成的 hover 判失败。
- [x] hover lite profile 必须包含旧成熟 review topics 和
  `/navlab/official_maze/map` overlay；controller/setpoint topic 只作为 optional
  review topic。
- [x] upload 必须只允许 lite；raw 不能上传。
- [x] build-replay / upload 前必须读取 task summary；summary 未通过时不能上传为
  valid hover。

验收证据：

- [x] `foxglove_replay_summary.json` 标明 source task summary path。
- [x] task summary 未通过时，uploader 返回非零；默认不能上传。

#### Phase H5：真实 live 回归

- [x] 跑一轮 `hover` live。
- [x] 检查电机/arm/takeoff evidence：GUIDED/arm、`LOCAL_POSITION_NED`
  上升到目标高度附近、rangefinder MAVLink peer、setpoint stream。
  `NAV_TAKEOFF` ACK 只作为诊断字段记录，不能覆盖真实 airborne 证据。
- [x] 检查 `hover_hold` window 和 landing 完成。
- [x] 检查没有 Gazebo truth fallback：ExternalNav、SLAM、hover gate、landing gate
  都不能使用 Gazebo truth 作为输入。
- [x] 只有顶层 summary blockers 为空，才能写 `hover parity verified`。

验收证据：

- [x] 新 live artifact 的 `summary.json` 顶层 status 通过且 blockers 为空。
- [x] `mission_summary.json`、probe JSON、rosbag profile summary 和 landing evidence
  互相一致。
- [x] 文档更新引用新的有效 artifact，旧 `20260615T115355Z` 仍保留为 false pass
  反例。

当前 H5 live 证据：

- `artifacts/sim/hover/20260615T144150Z/summary.json` 仍为 `TASK_STATUS_ERROR`。
- `mission_summary.json` 显示 mission runtime 已启动并进入 `guided`/`arm`，
  但 `arm_ack_ok=false`、`takeoff_ack_ok=false`、`setpoints_sent_count=0`。
- ArduPilot STATUSTEXT 明确报 `Arm: Rangefinder 1: No Data`。
- `/rangefinder/down/range` ROS topic 存在，但 `/rangefinder/down/status` 显示
  `mavlink_peer_observed=false`、`sent_count=0`、`ready=false`，说明 FCU 没收到
  rangefinder MAVLink 数据。
- `artifacts/sim/hover/20260615T145759Z/summary.json` 在把 Go rangefinder endpoint
  临时改成 `udpin:0.0.0.0:14550` 后仍未通过；`gazebo_sensor_runtime.toml`
  确认 endpoint 已改，但 `/rangefinder/down/status` 仍是
  `mavlink_peer_observed=false`、`sent_count=0`。
- 对照 `a3e0f7a` 后确认旧 Python compose 栈确实有 `mavlink-router`，但当前
  Go official-baseline 不再是旧 compose 拓扑：official launch 已经拥有 SITL
  master `tcp:127.0.0.1:5760` 和 MAVProxy out `127.0.0.1:14550`。
- Go H5 中间方案启动额外 `mavlink_router` 抢了 `5760`，导致
  `20260615T153951Z`、`20260615T154958Z`、`20260615T155940Z` 都卡在
  `wait_ready`：mission 收不到 FCU heartbeat/local-position，`/ap/v1/pose/filtered`
  缺失，只有 rangefinder 流量。
- `20260615T162735Z` 去掉 router 后 mission 可以收到 heartbeat/local-position，
  但 rangefinder `mavlink_peer_observed=false`、`sent_count=0`，ArduPilot 仍报
  `Arm: Rangefinder 1: No Data`。这说明需要 multi-client UDP fan-out。
- Go H5 修复方向：official-baseline router 只监听 MAVProxy out `14550`，
  `ROUTER_TCP_PORT=0` 禁止抢 master `5760`，下游分发到 `14551/14552`；hover
  mission 默认监听 `udpin:0.0.0.0:14551`，down rangefinder 默认监听
  `udpin:0.0.0.0:14552`。禁止多个 runtime 直接竞争同一个 UDP listener，也禁止
  额外服务监听 official master 端口。
- `20260615T164659Z` 修通 rangefinder 后又暴露第二个 H5 差异：Go hover 把
  `takeoff_ack_ok` 作为 airborne 前置条件。对照 `a3e0f7a` 后确认旧
  `hover_mission.py` 也存在同类 ACK 依赖，只是旧 compose/MAVLink 拓扑中没有
  暴露；Go official-baseline 下 `NAV_TAKEOFF` ACK 可失败但真实飞机已经升空。
  修复后的原则是：只要 `LOCAL_POSITION_NED`/`GLOBAL_POSITION_INT` 显示已经
  airborne，就开始 setpoint hold；`NAV_TAKEOFF` ACK 失败只能作为诊断字段记录，
  不能覆盖真实 airborne 证据。否则飞机已经升空也会一直卡在 `takeoff`，导致
  setpoint/landing 永远不执行。
- `20260615T170341Z` 证明 hover body 已完成，但 landing 因
  `land_command_accepted=false` 被错误 block。H5 acceptance 现在统一为
  touchdown/disarm/motors-safe 证据优先，LAND ACK 仅作为诊断字段。
- `20260615T171440Z` 证明 hover 任务本体已完成：`mission_summary.ok=true`、
  `airborne_seen=true`、`hover_body_ok=true`、`landing_ok=true`、`disarmed=true`、
  `motors_safe=true`、`altitude_error_m=0`、`hover_hold_duration_sec=17.95`。
  剩余 blocker 是 Go hover rosbag profile 仍把 `/ap/v1/status`、`/imu`、
  `/rangefinder/down/status` 当 required；这些是 probe/summary 证据或高频诊断
  topic，不应作为 lite replay required。
- `20260615T172645Z` 是当前有效 H5 hover parity artifact：
  `summary.status=TASK_STATUS_OK`、`blocked=false`、`mission_summary.ok=true`、
  `airborne_seen=true`、`hover_body_ok=true`、`landing_ok=true`、
  `touchdown_confirmed=true`、`disarmed=true`、`motors_safe=true`、
  `altitude_error_m=0.01`、`hover_hold_duration_sec=17.95`、
  `rangefinder_count=1702`、`local_position_count=582`。rosbag profile 也通过，
  required topics 为 `/tf`、`/tf_static`、`/rangefinder/down/range`、
  `/navlab/hover/status`、`/slam/odom`、`/navlab/landing/status`、`/scan`、`/map`。
- 结论：H5 hover parity 已用 Go orchestration + Python runtime 跑通；继续
  exploration/scan-robustness 前仍禁止用 `force_arm`、Gazebo truth、topic count
  或 Foxglove artifact 伪装通过。

## 4. Exploration 差异

### 4.1 旧 Python 语义

旧 exploration / obstacle mission 不是简单 path length counter。
旧 `obstacle_mission.py` 的任务 phase 包含：

```text
wait_ready
  -> guided
  -> arm
  -> takeoff
  -> hover_settle
  -> forward
  -> scan_left / scan_right
  -> avoid / return_track
  -> final_hold
  -> complete
```

旧 `acceptance.py` summary 关注：

- mission phase 是否出现：`wait_ready`、`guided`、`arm`、`takeoff`、`hover_settle`、`forward`、`scan_left`、`scan_right`、`final_hold/complete`。
- `obstacle_detected`。
- `avoidance_setpoint_sent`。
- `vendor_scan_publisher_ok`。
- `x2_status_fresh`。
- `/scan`、`/scan_ideal`、`/sim/x2/status` 是否录到。
- ExternalNav 是否使用 SLAM odom，且不是 Gazebo truth。
- pose mirror 是否 observation-only。

旧 P8 `exploration_gate.py` 还会围绕 P3/P4/P5/P7 依赖做更完整检查：

- SLAM odom rate / frame / age。
- controller summary。
- owner uniqueness。
- rosbag profile。
- map / submap / trajectory topic。
- replay profile 对 `min_accepted_goals`、`min_path_length_m` 的要求。

### 4.2 当前 Go 语义

当前 Go `ExplorationWorkflowScript()` 是时间分段的 `frontier_lite` intent publisher：

```text
if controller_ready:
  goal_index = ready_elapsed / segment_sec
  accepted_goals = goal_index + 1
  publish intent pattern
```

当前 completion 条件主要是：

```text
controller_ready
odom_samples > 0
accepted_goals >= min_goals
path_length_m >= min_path_length_m
```

这个语义不等价：

- `accepted_goals` 是按时间段和 odom samples 推出来的，不一定代表真实 frontier candidate 被发现、验证、到达。
- 没有旧 obstacle mission 的 `scan_left / scan_right / avoid / return_track` phase contract。
- 没有严格证明 `obstacle_detected`、`avoidance_setpoint_sent`、`yaw_scan_ok`、`lateral_detour_ok`。
- 当前 `exploration.yaml` 的 `min_path_length_m=0.35` 很低，容易被微小漂移或短距离移动满足。
- 当前 Go workflow 与 Nav2/P13 frontier 不是一回事，不能拿它证明“走出迷宫”。

### 4.3 当前证据缺口

当前 artifacts 中可见：

```text
artifacts/sim/exploration/20260615T075519Z/exploration_probe.json
```

但没有对应完整：

```text
artifacts/sim/exploration/20260615T075519Z/summary.json
```

因此当前 exploration 不能被写成 live 成功。只有 probe 不能代替 task summary。

### 4.4 Exploration 必须修复的差异

- 先决定 exploration 的真实目标：旧 obstacle mission parity，还是新的 frontier-lite/P13 前置任务；两者不能混写。
- 如果目标是旧 parity，必须恢复 phase contract：`forward`、`scan_left/right`、`avoid`、`final_hold/complete`。
- 如果目标是 frontier-lite，必须把它标成新任务语义，不得说等价旧 Python exploration。
- `accepted_goals` 不能只由时间段推进，必须有 goal candidate / validation / reached 或明确的 bounded probe evidence。
- `path_length_m` 必须绑定到真实 SLAM odom 轨迹，并设置能排除抖动/漂移的阈值。
- summary 必须包含完整 task result，不允许只有 probe。
- gate 必须要求 landing policy 证据：`return_home_then_land` 或 `land_in_place`，并区分任务完成策略。

## 5. Scan-robustness 差异

### 5.1 旧 Python / 设计语义

`scan-robustness` 对应 P10/P11/P12 的组合，不是单个 status probe。

旧 P10 scan integrity 关注：

- raw / normalized / validated scan 链路。
- attitude-aware integrity gate。
- mild tilt、hard tilt、reset 的 fault injection。
- hard tilt 必须被 drop / blocked。
- attitude source 不能是 Gazebo truth 或 `/odometry`。

旧 P11 scan stabilization 关注：

- `bounded_2d_projection`。
- P9 representative replay motion profile。
- raw scan 不直接进入 SLAM。
- P11 output scan topic 必须匹配 SLAM scan topic。
- scan stabilization status / events / debug scan。
- retained / rejected / floor-hit / projection error 指标。

P12 设计语义关注：

- `ideal` 和 `realistic` 两个 required profile。
- `realistic` 是 motor bias、ESC lag、thrust noise、IMU vibration/noise 的组合，不是单个旧 `mild_disturbance` 标签。
- profile 不存在必须 fail fast，不能 fallback。
- summary 必须记录 profile sweep、per-profile pass/fail、drift/lag/noise/false-drop/SLAM health。
- 不允许用 Gazebo truth、official maze overlay 或 seed map 作为补偿、SLAM 或控制输入。

### 5.2 当前 Go 语义

当前 helper registry 仍标：

```text
scan-stabilization: ported_partial
scan-robustness-workflow: ported_partial
```

当前 execution plan 中 `scan-robustness-workflow` 主要生成：

- `scan_robustness_runtime.toml`
- `scan_robustness_gazebo_sensor_runtime.toml`
- `scan_robustness_bridge_override.yaml`
- `airframe_disturbance_probe.py`
- `scan_robustness_rosbag`
- `airframe_disturbance_gate`

但是当前计划本身没有证明完整 live parity：

- 没有在 artifacts 中看到可用的 `scan-robustness` live summary。
- `scan_robustness` YAML 里 `live_profiles: []`，实际 profile sweep 执行证据不明确。
- result gate 输入列了 `profile_sweep_summary.json`，但当前 artifact 证据缺失。
- 当前 `AirframeDisturbanceProbeScript` 是通用 ROS status probe，不等价完整 P12 profile sweep。
- P12 TODO 虽然大量项被勾选，但 artifacts 证据和 Go runtime 当前可见状态不足以证明这些都 live 通过。

### 5.3 Scan-robustness 必须修复的差异

- 必须跑出 `ideal` 和 `realistic` 两个 profile 的真实 live summary。
- `live_profiles` 不能空着导致只跑默认 profile；如果为空必须 fail 或由 required profile 明确展开。
- `profile_sweep_summary.json` 必须真实生成，并进入顶层 summary。
- 每个 profile 必须记录：
  - applied profile name
  - motor bias / thrust multipliers
  - ESC lag
  - thrust noise / motor jitter
  - IMU vibration / noise
  - attitude source
  - scan integrity result
  - scan stabilization result
  - SLAM health
  - FCU mode window
  - landing result
- `realistic` 必须是组合 profile，不是单独一个“扰动标签”。
- 不能把 P10 attitude bias injection 当成 P12 motor/ESC/vibration 验证。
- profile matrix 结果必须写入 summary 和 docs，不允许只在 test 里造 fake summary。

## 6. 跨任务共同差异

### 6.1 Task 成功语义被弱化

旧 Python task 多数是任务状态机 + runtime evidence + rosbag profile + summary gate。
当前 Go 多处变成：

```text
probe topic exists
status ok
setpoint count > 0
path length > small threshold
landing status ok
```

这会导致假通过。

### 6.2 Runtime script generation 过大且语义混杂

当前 `runtime_specs.go` 同时生成：

- FCU controller runtime
- exploration workflow
- Nav2 runtime
- scan stabilization
- scan robustness

这让 P4 controller readiness、P6 hover、P8 exploration、P12 robustness 的边界混在一起。
后续修复时必须拆清楚：

- controller readiness 不是 hover success。
- exploration workflow 不是 obstacle mission parity。
- scan robustness probe 不是 profile sweep。

### 6.3 文档与 artifact 状态不一致

`docs/general/orchestration_sim_python_parity_audit.md` 目前写过 hover/exploration
live parity 已通过，但当前 hover artifact 已证明该判断不可靠。

必须修正文档措辞：

- `hover` 改成 `not equivalent / false pass found`。
- `exploration` 改成 `not verified / missing summary`。
- `scan-robustness` 改成 `not verified / profile sweep evidence missing`。

### 6.4 Foxglove 上传不能作为验收

Foxglove lite 只证明 review artifact 可视化，不证明任务通过。

上传前必须满足：

- raw/lite topic surface 正确。
- `/navlab/official_maze/map` 只作为 overlay。
- task summary 真通过。
- hover/exploration/scan-robustness 的业务 gate 真通过。

当前 hover 上传过的 artifact 应视为无效 review artifact，不能作为 hover success evidence。

## 7. 修复顺序建议

必须按这个顺序修：

1. `hover`：恢复旧 `hover_mission.py` 的 MAVLink phase contract，先让真正 hover 起飞、到高、hold、landing。
2. `exploration`：基于修好的 hover/control，再决定旧 obstacle parity 还是新 frontier-lite；没有 hover 基础不能继续扩展。
3. `scan-robustness`：跑完整 `ideal` / `realistic` profile sweep，并把 profile evidence 固化进 summary。
4. 最后才继续 Nav2 / P13。

## 8. 当前不得再声称完成的事项

在以上差异修复并跑出 live evidence 前，不得声称：

- Go sim hover 已完成。
- Go sim exploration 已完成。
- Go sim scan-robustness 已完成。
- Python sim runtime 可以删除。
- P13 Nav2 可以建立在当前 hover/exploration 成功上。
- 已上传 Foxglove artifact 证明任务成功。
