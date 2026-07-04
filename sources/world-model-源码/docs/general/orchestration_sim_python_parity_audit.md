# Go Sim 与旧 Python Orchestration Parity 审计

## 1. 目的

这份文档记录 Go sim 迁移时必须继承的旧 Python orchestration 行为边界。
它不是 Nav2 设计文档，也不是新功能清单；它是迁移审计基线，后续 real
迁移也要按这里的原则对照。

Baseline commit：

```text
cae4288 refactor(orchestration)!: narrow runtime tasks
```

主要旧实现证据：

| 旧 Python 位置 | 迁移含义 |
|---|---|
| `orchestration/src/tasks/legacy/slam_backend.py` | P3 SLAM backend、Cartographer 启动、SLAM doctor、truth diagnostic blocker |
| `orchestration/src/tasks/legacy/slam_hover.py` | P6 hover gate，ExternalNav 必须消费 `/slam/odom` |
| `orchestration/src/tasks/legacy/exploration_gate.py` | P8 exploration gate，`/map`、`/slam/odom`、coverage、owner、rosbag profile |
| `orchestration/config.toml` | P3/P6/P8 topic、frame、truth、owner 配置源；其中 truth/odometry 相关配置需要按本审计重新收紧 |
| `profiles/navlab-*-rosbag-topics.txt` | 旧 rosbag 必录 topic surface |
| `profiles/navlab-exploration-foxglove-lite-topics.txt` | 成熟 Foxglove-lite topic surface |

## 2. 不可破坏原则

### 2.1 Gazebo 只能是物理世界和传感器来源

允许：

- Gazebo/SITL 作为仿真世界、动力学、ray sensor、rangefinder sensor 来源。
- `/lidar` 作为 X2 virtual serial/vendor-driver 链路的上游仿真传感器输入。
- `/rangefinder/down/scan_ideal` 作为 down rangefinder sensor emulator 的内部输入。
- Gazebo/official bridge odometry、`/gazebo/tf` pose TF、seed map、official maze map 作为
  diagnostic-only artifact，用于离线误差分析和 Foxglove review。

禁止：

- 用 Gazebo truth、bridge odometry、seed map 或 SDF geometry 代替 `/slam/odom`。
- 用 Gazebo truth、seed map 或 official maze overlay 代替 `/map`。
- 用 Gazebo truth 或 direct pose 进入 ExternalNav、planning、navigation、hover、motion、exploration 或 control 验收。
- 用 `/navlab/official_maze/map` 进入 Nav2 costmap 或任务规划。这个 topic 只能用于 Foxglove review overlay。
- 把 Gazebo/official bridge `/odometry` remap 成 Cartographer 的正式 odometry
  input，除非该 odometry 来源在真机上有等价传感器并被明确记录。
- 从 Gazebo `/gazebo/tf` 或 bridge TF 中提取 `odom -> base_link` 再发布成
  `/slam/odom`。`/slam/odom` 必须是 SLAM backend 的输出，不是 Gazebo pose
  的换皮。

### 2.1.1 Gazebo truth boundary

这条边界是 sim 和 real 对齐的硬原则：

```text
Gazebo world / physics
  -> realistic sensors: lidar, IMU, rangefinder, camera
  -> same processing path as real machine
  -> SLAM / controller / navigation outputs
```

Gazebo 不能提供现实机器没有的“答案”给运行时算法：

| Gazebo artifact | 允许用途 | 禁止用途 |
|---|---|---|
| Gazebo ray sensor `/lidar` | 生成 X2/vendor-driver `/scan` | 直接替代 vendor-driver output contract |
| Gazebo down range sensor | 生成 rangefinder emulator，再进 MAVLink `DISTANCE_SENSOR` | companion 直接造高度控制或绕过 FCU rangefinder |
| Gazebo IMU bridge `/imu` | 仿真 IMU sensor input | 替代真机不存在的 perfect attitude/pose |
| Legacy diagnostic `/odometry` | diagnostic-only，对照漂移和 FCU/SITL 状态 | Cartographer/SLAM/ExternalNav/Nav2/control 的正式输入 |
| Gazebo model bridge `/gazebo/model/odometry` | diagnostic-only，明确标识来自 Gazebo model odometry bridge | Cartographer/SLAM/ExternalNav/Nav2/control 的正式输入 |
| Gazebo `/gazebo/tf` pose bridge | diagnostic-only，Foxglove 或调试可记录 | 生成 `/slam/odom`、`map -> odom`、导航 pose |
| `/navlab/official_maze/map` | Foxglove official map overlay | `/map`、Nav2 static layer、planner input、任务成功证据 |
| `/navlab/navigation/seed_map` | Nav2 static-layer bootstrap/debug，必须标注 seed | 冒充 Cartographer `/map` |

判定标准：

- 如果 real 机器上没有等价输入，sim 运行时算法不能依赖它。
- 如果一个 topic 是 truth/diagnostic，它可以被记录，但不能出现在
  SLAM/Nav2/ExternalNav/FCU controller 的 required input list。
- 如果 acceptance 因 diagnostic-only 输入而通过，结果必须判定为 blocked，
  不能标记为完成。

### 2.1.2 Fail closed / no truth fallback

所有 sim task 必须 fail closed：

- SLAM、Nav2、ExternalNav、FCU controller、landing 或 workflow 出问题时，只能记录
  blocker、summary metric、runtime log、rosbag evidence 和 artifact。
- 不允许为了让任务通过而把 Gazebo truth、Gazebo model odometry、Gazebo TF、seed
  map、official maze overlay 或 SDF geometry 顶替成 `/slam/odom`、`/map`、pose、
  navigation result、landing result 或 controller input。
- 如果 canonical input/output 缺失，结果应该是 failed、blocked 或 not evaluated；
  这不是需要绕过的问题，而是正确暴露的问题。
- Diagnostic-only topic 可以帮助解释失败，但不能修复失败，也不能改变 gate
  判定为通过。

### 2.2 SLAM canonical ownership

旧 Python P3/P6/P8 的主边界：

```text
/scan + /imu + SLAM-owned TF/state
  -> Cartographer backend
  -> /map
  -> /slam/odom
  -> /navlab/slam/status
  -> /external_nav/odom
  -> ArduPilot EKF
  -> /ap/v1/pose/filtered
```

`/map` 和 `/slam/odom` 必须由 SLAM backend 产生。FCU controller、Nav2 adapter、
mission script、Foxglove replay builder 都不能发布或伪造这两个 canonical
output。

`/odometry` 不是 canonical SLAM output。当前审计发现旧 Python/Go 迁移链路里
存在把 official/Gazebo bridge `/odometry` 当成 Cartographer input 的风险；这类
输入必须降级为 diagnostic-only，直到能证明它来自真机等价传感器。它可以被记录
和对照，但不能作为 `/slam/odom` 的替代成功条件，也不能作为 ExternalNav 输入。

Cartographer 的动态 TF 不能发布回全局 `/tf` 再由 adapter 混合读取。Gazebo
truth pose TF 必须隔离到 `/gazebo/tf` 和 `/gazebo/tf_static`，不能占用全局
`/tf`；Cartographer 运行时必须把 `map -> base_link` remap 到
`/navlab/slam/tf`，adapter 只从 `/navlab/slam/tf` 生成 `/slam/odom`。这样可以
避免同一个 `base_link` child 同时被 Gazebo/bridge `odom -> base_link` 和
Cartographer `map -> base_link` 驱动。

### 2.3 Frame 和 topic 必须继承旧 contract

| 语义 | Canonical value |
|---|---|
| map frame | `map` |
| odom frame | `odom` |
| body frame | `base_link` |
| lidar frame | `base_scan` |
| IMU frame | `imu_link` |
| down rangefinder frame | `rangefinder_down_frame` |
| stabilized scan | `/scan` |
| X2 upstream lidar | `/lidar` |
| X2 status | `/sim/x2/status` |
| rangefinder range | `/rangefinder/down/range` |
| rangefinder status | `/rangefinder/down/status` |
| FCU cmd_vel | `/ap/v1/cmd_vel` |
| FCU pose | `/ap/v1/pose/filtered` |
| FCU twist | `/ap/v1/twist/filtered` |
| SLAM odom | `/slam/odom` |
| SLAM map | `/map` |
| SLAM diagnostic odometry | `/odometry` |
| Gazebo model diagnostic odometry | `/gazebo/model/odometry` |
| Gazebo diagnostic TF | `/gazebo/tf`, `/gazebo/tf_static` |

Go helper defaults、project config defaults、generated runtime artifacts、
rosbag profiles、Foxglove-lite profiles 必须一致。

## 3. 当前 Go sim 对齐状态

| 区域 | 旧 Python baseline | Go sim 要求 | 状态 |
|---|---|---|---|
| SLAM backend command | source ROS + `/opt/navlab_ws/install/setup.bash` 后启动 Cartographer | `slam_backend` runtime service 必须 source 同样 workspace，并落盘 `slam_backend.runtime.log` | 已约束 |
| SLAM fake/placeholder | `launch_fake_odom=false`，`publish_placeholder_odom=false` | 写入 `slam_runtime.toml` 并测试 | 已约束 |
| `/map` owner | Cartographer occupancy grid | 禁止 seed map 发布到 `/map`；Nav2 seed map 只能用 `/navlab/navigation/seed_map` | 已约束 |
| `/slam/odom` owner | Cartographer adapter | FCU controller/mission/adapter 不发布 `/slam/odom` 或 SLAM status | 已约束 |
| `/odometry` | 旧链路存在 Cartographer input / diagnostic 混用风险 | 只能 diagnostic-only，不能作为 SLAM/ExternalNav/Nav2/control 输入；Cartographer odom input 默认改为 `/cartographer/odometry_input`，真机 odom 必须显式配置 | 已隔离 |
| `/gazebo/model/odometry` | Gazebo model bridge 原来可发布到裸 `/odometry` | 只能 review-only；bridge override 不能发布裸 `odometry` ROS topic | 已隔离 |
| Gazebo pose TF bridge | 旧 bridge 可发布 `odom -> base_link` 到全局 `/tf` | ROS 侧必须 remap 到 `/gazebo/tf`/`/gazebo/tf_static`；只能 diagnostic-only；不能生成 `/slam/odom` 或 `map -> odom` | 已隔离 |
| Cartographer dynamic TF | 旧链路曾混在全局 `/tf` | 必须 remap 到 `/navlab/slam/tf`，adapter 只读该 topic | 已约束 |
| FCU MAVLink bootstrap/router | 旧 Python compose 基础栈启动 `mavlink-router`，companion MAVLink clients 通过 router TCP/UDP surface 接入；新 official-baseline launch 自己拥有 SITL master `5760` 和 MAVProxy out `14550` | Go sim official-baseline router 只能做 UDP fan-out：监听 `14550`，`ROUTER_TCP_PORT=0`，下游 `14551/14552`；hover mission 默认 `udpin:14551`，down rangefinder 默认 `udpin:14552`；任何 heartbeat/rangefinder/ACK 缺失都必须 block，不能用 Gazebo truth 顶上 | H5 修复中 |
| FCU takeoff readiness | MAVLink bootstrap 后才进入 hover/exploration control | 起飞 ready 只能用 MAVLink `LOCAL_POSITION_NED` 或 `GLOBAL_POSITION_INT` 高度证据；阈值由 task config 显式配置 | 已约束 |
| FCU motion setpoint | Python P8 通过 MAVLink `SET_POSITION_TARGET_LOCAL_NED` 驱动 SITL | Go FCU runtime 必须把 workflow intent 转成 MAVLink local-position lookahead setpoint；DDS `/ap/v1/cmd_vel` 只保留为输出/记录 surface | 已迁移 |
| Diagnostic Cartographer odom profile | 旧 `navlab_cartographer_2d.lua` 可被误选中并启用 `use_odometry=true` | 重命名为 `navlab_cartographer_2d_diagnostic_odom.lua`，默认 runtime/real 配置只使用 `navlab_cartographer_2d_real.lua` | 已隔离 |
| X2 topics | `/lidar -> /scan`, `/sim/x2/status` | helper defaults 和 rosbag surface 保持旧值 | 已修正 |
| Rangefinder topics | `/rangefinder/down/*` | helper defaults 和 probe surface 保持旧值 | 已修正 |
| Frames | `base_scan`, `rangefinder_down_frame` | helper defaults 和 frame probe 保持旧值 | 已修正 |
| Foxglove overlay | `/navlab/official_maze/map` 只用于显示 | overlay 不缩放到 `/map` bbox，不作为 planning input | 已约束 |

## 3.1 Live parity evidence

| Task | Run | Result | Evidence |
|---|---|---|---|
| hover | `artifacts/sim/hover/20260615T024140Z/summary.json` | 通过 | `bootstrap_ready=true`、`pose_samples=141`、`mavlink_setpoint_count=154`、`mavlink_local_position_count=16`、`max_hover_horizontal_drift_m=0.7251`、`usesTruthAsControlInput=false` |
| exploration | `artifacts/sim/exploration/20260615T024623Z/summary.json` | 通过 | `accepted_goals=3`、`path_length_m=0.8409`、`mavlink_setpoint_count=443`、`mavlink_local_position_count=40`、`setpoint_intent_samples=125`、`usesTruthAsControlInput=false` |

Hover 和 exploration 的基础 live parity 已经跑通：controller ready、SLAM odom、
workflow、MAVLink setpoint、landing/probe gate 均能形成通过 summary。Go runtime
仍必须保持 `usesTruthAsControlInput=false`，不能用 Nav2、seed map、Gazebo
odometry 或 bridge TF 绕过。

FCU bootstrap 的 takeoff readiness 是“允许 controller 开始控制”的门槛，不是
任务完成条件。默认配置为 `takeoff_min_height_m=0.15` 与
`takeoff_min_height_ratio=0.35`，实际阈值取二者和目标高度比例的较大值；hover、
exploration 后续仍由 SLAM odom、path/goal、landing status 等 gate 判定。

当前剩余风险不再是 Go task 未迁移，而是 Cartographer 稳定性：`20260615T023414Z`
曾在任务通过后出现 `rejected odom TF`、大量 `Dropped earlier points`，并触发
Cartographer `std::length_error`；adapter 拒绝异常 TF，cleanup 也因此暴露
Docker stop warning。该风险必须作为 SLAM drift/stability 问题继续跟踪，不能用
Gazebo truth 修补。

## 4. 后续 real 迁移对照

real 迁移时不需要继承 Gazebo 组件，但必须继承语义边界：

- `/slam/odom` 必须来自 real SLAM/localization backend，不是 FCU local position 复制。
- `/map` 必须来自 real SLAM/localization backend，不是人工 seed map。
- truth/diagnostic topic 可以存在，但必须显式标成 diagnostic，不能进入 planning/control input。
- sim 中任何使用 Gazebo `/odometry` 或 Gazebo pose TF 的链路，迁移到 real 前必须
  被替换成真实传感器、真实 SLAM 输出，或被删除。
- FCU controller 仍是唯一 `/ap/v1/cmd_vel` owner。
- frame contract 仍使用 `map -> odom -> base_link -> base_scan`。
- task doctor 必须检查 canonical topic distinctness：
  - `slam_odom_topic != truth_diagnostic_topic`
  - `slam_odom_topic != cartographer_odometry_topic`
  - `map_topic != official_overlay_topic`

## 5. 验收检查

代码层必须保留以下检查：

- Go helper default parity test：阻止 topic/frame 默认值漂移。
- SLAM runtime config test：阻止 fake odom、placeholder odom、truth input 回流。
- FCU controller script test：阻止 FCU controller 发布 `/map`、`/slam/odom`、SLAM TF。
- FCU takeoff readiness test：阻止 MAVLink 起飞高度阈值回退成 runtime script
  内部硬编码；task YAML 必须能显式配置 `takeoff_min_height_m` 和
  `takeoff_min_height_ratio`。
- Navigation adapter config test：seed map 只能发布到 `/navlab/navigation/seed_map`。
- Foxglove replay test：official overlay 只按 SDF/crop identity 显示，不拟合到 `/map`。
- Live run 验收：raw rosbag 中 `/map` 和 `/slam/odom` 都要有消息；没有 `/map` 时不能上传为“已修复”的 navigation lite artifact。
- Truth boundary test：阻止 `/odometry`、Gazebo `/gazebo/tf`、official maze overlay、
  seed map 出现在 SLAM/Nav2/ExternalNav/controller 的 required inputs 中。
- TF isolation test：Cartographer dynamic `/tf` 必须 remap 到
  `/navlab/slam/tf`，adapter 的 `tf_topic` 必须指向同一 topic。

## 6. 当前优先级

在继续扩展 P13 Nav2 前，优先完成：

1. 把 Cartographer drift/stability 指标固化到 summary：rejected TF count、dropped point warnings、max accepted odom step、adapter reject reason。
2. 确认 `/map`、`/slam/odom`、`/submap_list`、`/trajectory_node_list` 来自 Cartographer，并在 raw rosbag/golden 中保持可查。
3. 清理 official/Gazebo `/odometry` 和 `/tf` pose bridge：保留 diagnostic-only
   记录，禁止进入 Cartographer adapter、ExternalNav、Nav2 或 controller 输入。
4. hover 和 exploration 已通过后，再继续 Nav2 planner/controller/frontier 的功能调试，但 Nav2 验收必须继承同一 truth boundary。
