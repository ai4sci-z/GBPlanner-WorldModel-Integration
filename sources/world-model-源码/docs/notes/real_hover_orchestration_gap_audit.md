# Sim/Real 任务闭环与 Hover 观测迁移审计

日期：2026-06-25

## 目的

现在 `hover` 的 sim 主线已经把一套完整任务链路跑顺了：

```text
观测 -> gate -> FSM -> artifact -> summary/cohort
```

本文的目标不是立刻实现 real hover。当前更合理的目标是：参考 sim hover 已经沉淀出来的观测面、gate、artifact 和 FSM，把 Go sim 与 Rust real 的任务编排模型理顺，然后先用 real 侧已经存在的 `motor-debug` 做一个最小真实任务闭环。

短期主线应该是：

```text
real orchestration DAG
  -> preflight
  -> prepare
  -> common-doctor
  -> task-doctor
  -> motor-debug FSM
  -> task_result / summary / runtime events
```

不是直接跳到：

```text
real hover live flight
```

本文要回答：

- Go sim hover 里哪些观察/gate/artifact/FSM 思想应该保留。
- Rust real 的 `preflight`、`prepare`、`common-doctor`、`task-doctor` 应该如何承接这些观察。
- sim 侧 Go 是否也应该补 `preflight` / `prepare` / `common-doctor` / 默认 `task-doctor`。
- 整套编排应该抽象成 DAG 还是 FSM。
- DAG 是引入库还是先自己实现。
- `navlab.common` 可以迁哪些纯逻辑，哪些必须留在 `navlab.sim` / `navlab.real`。
- 当前 sim hover 在“无作弊/官方定义”上能怎么表述，哪些仍是后续收敛目标。

判断优先级：

```text
代码 > 测试/命令结果 > 文档 > 推断
```

## 证据快照

### 已检查命令

```bash
cd orchestration/real && cargo run --quiet -- list-tasks
cd orchestration/sim && go run ./cmd/navlab-sim task show hover --dry-run
```

观察结果：

- `navlab-real list-tasks` 当前只暴露 `motor-debug`。
- `navlab-sim task show hover --dry-run` 暴露 `hover`，默认 `simulation_profile=slam-direct-no-odom-prior`，`duration_sec=90`。

### 本地代码/文档依据

- `orchestration/sim/configs/tasks/hover.yaml`
- `orchestration/sim/internal/tasks/registry.go`
- `orchestration/sim/internal/tasks/simulation_profiles.go`
- `orchestration/sim/internal/tasks/runtime_runner.go`
- `orchestration/real/README.md`
- `orchestration/real/config.toml`
- `orchestration/real/src/tasks/registry.rs`
- `orchestration/real/src/workflows/{preflight,prepare,common_doctor,task_doctor,doctor_chain}.rs`
- `orchestration/real/src/tasks/motor_debug.rs`
- `navlab/sim/companion/nodes/hover_mission.py`
- `navlab/real/companion/nodes/{mavlink_bridge,external_nav,rangefinder_bridge,ydlidar_x2_scan}.py`
- `navlab/common/companion/mission/*`
- `docs/general/orchestration_runtime_mode_real_vs_sim_design.md`
- `docs/general/navlab_real_sim_package_boundary_design.md`
- `docs/general/sim_task_parity_differences_audit.md`
- `docs/decisions.md`

### 官方资料依据

- ArduPilot MAVLink 非 GPS 位置估计：`https://ardupilot.org/dev/docs/mavlink-nongps-position-estimation.html`
- ArduPilot Copter Guided 模式命令：`https://ardupilot.org/dev/docs/copter-commands-in-guided-mode.html`
- ArduPilot ROS 2 Interfaces：`https://ardupilot.org/dev/docs/ros2-interfaces.html`
- ArduPilot ROS 2 with SITL：`https://ardupilot.org/dev/docs/ros2-sitl.html`
- ArduPilot ROS 2 with Gazebo：`https://ardupilot.org/dev/docs/ros2-gazebo.html`
- ArduPilot ROS 2 总览 / Cartographer 入口：`https://ardupilot.org/dev/docs/ros2.html`

网络备注：本地代理环境会返回 `407 Proxy Authentication Required`，官方资料是取消代理环境变量后检查的。

## 当前 sim hover 基线

当前入口：

```bash
just navlab-run hover
```

控制面：

- Go CLI/package：`orchestration/sim`。
- task registry 里有 `hover`、`hover-slam-only`、`exploration`、`navigation`、`scan-robustness`。
- `hover.yaml` 设置 `family=sim`、`duration_sec=90`、`simulation_profile=slam-direct-no-odom-prior`。
- `duration_sec` 现在是 Go 拥有的任务 deadline，不应该再被理解为“必须录满 90 秒”。如果 FSM/probe 提前完成，只需要短暂 rosbag grace。

runtime 面：

- Python sim mission 入口是 `navlab.sim.companion.nodes.hover_mission`。
- Go 生成 runtime scripts/config/artifacts，然后启动 Docker/SITL/Gazebo/services/probes。
- 共享的 mission FSM 和 evidence 逻辑在 `navlab.common.companion.mission.*`。
- Go/Python 的交互边界是文件、artifact、CLI 参数、env、ROS topic、日志、JSON probe；real 也应该保持这个边界，不能做直接语言耦合。

当前主线数据路径：

```text
Gazebo 仿真 lidar/range/IMU source
  -> ROS /scan + /imu
  -> Cartographer /slam/odom
  -> ExternalNav bridge / MAVLink ODOMETRY
  -> SITL FCU EKF / LOCAL_POSITION_NED
  -> GUIDED takeoff / setpoint hover / landing FSM
```

当前无作弊意图：

- Gazebo truth/model odometry 可以录下来做 review/debug，但不能作为 SLAM、ExternalNav、controller、gate 的输入。
- `/navlab/official_maze/map` 只能是 overlay/review-only，不能替代 `/map`，也不能当 seed map 或控制输入。
- `slam-direct-no-odom-prior` 避免给 Cartographer 喂 odometry prior，防止把 scan/SLAM 的问题藏起来。
- hover span policy 已拆成 target/hard-cap：超过 target 是 SLO/统计观察，超过 hard-cap 才是 fail/block。

## 当前 real 基线

当前入口：

```bash
just navlab-real-run motor-debug ...
```

控制面：

- Rust CLI/package：`orchestration/real`。
- `orchestration/real/src/tasks/registry.rs` 目前只注册 `MotorDebugTask`。
- registry 测试明确断言 `registry.create("hover").is_none()`。
- `orchestration/real/configs/tasks/` 目前只有 `motor-debug.yaml`。

real mode contract 来自 `orchestration/real/config.toml`：

- `[runtime] mode="real", backend="process"`。
- real source claims 包括：
  - `scan_source_claim="ydlidar_x2"`，topic 是 `/scan`。
  - `fcu_source_claim="fcu_mavlink"`。
  - `imu_source_claim="fcu_mavlink"`。
  - `rangefinder_source_claim="fcu_distance_sensor"`。
  - `slam_source_claim="cartographer"`。
- required real topics 包括 `/scan`、`/tf`、`/tf_static`、`/slam/odom`、`/ap/v1/status`、`/ap/v1/pose/filtered`。
- forbidden simulation inputs 包括 `/gazebo/*`、`/scan_ideal`、`/sim/x2/status`、`/rangefinder/down/scan_ideal`。

real prepare chain 已经有可用积木：

- `mavlink_router`：真实串口 `/dev/ttyUSB1:115200` 到本地 MAVLink endpoint。
- `navlab_mavlink_bridge`：启动 real pose mirror 和 real ExternalNav sender。
- `lidar`：启动 `navlab.real.companion.nodes.ydlidar_x2_scan`。
- `slam`：启动 `navlab_slam_bringup`，参数是 `use_sim_time=false`、`navlab_cartographer_2d_real.lua`、`/scan`、`/imu/data`、`/slam/odom`。
- `rangefinder_bridge`：把真实 FCU 的 `DISTANCE_SENSOR` 转成 `/rangefinder/down/*`。

关键现状：real 侧不是没有基础设施，而是还没有把 Go sim 那套观察/gate/FSM/artifact 闭环系统性落到 `motor-debug` 和后续 real task 上。

## 总体设计结论

### 1. 外层编排是 DAG，任务执行是 FSM

最合理的抽象是：

```text
orchestration workflow = DAG
task runtime/body       = FSM
```

DAG 管“要做哪些检查、生成、启动、采样、评估”；FSM 管“任务本身执行到哪一步”。

外层 DAG 示例：

```text
load-config
  -> preflight
  -> prepare
  -> common-doctor
  -> task-doctor
  -> runtime-execute
  -> gate-evaluate
  -> summary/cohort
```

它像 DAG 而不是单一 FSM，是因为：

- 有些节点可以并行，例如 image check、config validation、artifact root check。
- 有些节点可以 dry-run，也可以 live-run。
- 有些 evidence 可以来自 live topic，也可以来自 artifact/rosbag。
- doctor-chain 可以组合不同节点，而不必强行进入某个“全局状态”。

任务 body 更像 FSM，因为同一时刻任务只处于一个主要状态，状态转移有严格顺序。例如 `motor-debug` 的主状态应该保持粗粒度：

```text
runtime_ready
  -> guided
  -> armed
  -> motor_spin_hold
  -> disarmed
  -> completed
```

`guided_mode_request`、`guided_mode_confirm`、`arm_request`、`arm_confirm`、`disarm_request`、`disarm_confirm` 这类细节应该作为 transition evidence 记录，而不是提升为主状态。否则 FSM 会退化成命令日志，后续 hover、navigation、motor-debug 也难以共享同一套 task body 抽象。

hover 也是 FSM：

```text
runtime_ready
  -> guided
  -> arm
  -> takeoff
  -> hover_health_hold
  -> hover_hold
  -> landing
  -> disarm
  -> completed
```

所以原则是：

```text
DAG 管任务开始前/结束后的工作流。
FSM 管任务执行期的有序状态转移。
```

### 2. DAG 先自己实现，不引入库

当前不建议引入第三方 DAG 库。

原因：

- 现在的 DAG 很小，节点数量有限，主要是静态阶段：`preflight`、`prepare`、`common-doctor`、`task-doctor`、`runtime`、`gate`。
- Go sim 和 Rust real 都需要类似模型，引入某个语言库不能解决跨语言 contract 问题。
- 当前更重要的是统一 `NodeResult` / `evidence` / `blockers` / `artifact` schema，而不是复杂调度算法。
- 外部库会增加依赖和概念成本，后续重构会更难。
- Go/Rust 都可以很容易自己实现一个最小拓扑排序和节点执行器。

建议先实现项目内最小 DAG 模型：

```text
WorkflowNode:
  id
  deps
  required
  mode: dry_run | live
  run()
  outputs: artifacts/evidence/blockers
```

每个节点输出统一结构：

```text
NodeResult:
  id
  ok
  blocked
  blockers
  warnings
  artifacts
  evidence
  started_at
  finished_at
```

最小执行规则：

- 先做拓扑排序。
- dependency blocked 时，后续 required 节点跳过并标记 `blocked_by_dependency`。
- optional 节点失败只写 warning，不阻塞 required 主链。
- 每个节点都必须写 artifact 或 summary 片段。
- 最终 workflow summary 汇总所有 node result。

后续如果真的出现复杂动态调度，再考虑库：

- Rust 可以考虑 `petgraph`，但现在不需要。
- Go 可以考虑自己继续维护，因为标准库已经够用。

当前结论：

```text
第一阶段自己实现小 DAG，不引入库。
重点做 schema、artifact、blocker 语义统一。
```

### 3. preflight / prepare / doctor / gate 的形状应当 sim 和 real 一致

sim 和 real 的区别不是有没有这些阶段，而是 evidence source 不同。

```text
sim:
  Docker / image / Gazebo / SITL / sim services / no-cheat boundary

real:
  host process / serial / real FCU / real lidar / real services / operator safety
```

也就是说：

```text
preflight / prepare / common-doctor / task-doctor / gate 的形状一致。
evidence 的采集方式必须区分 sim/real。
side effect 必须按 safety domain 分包。
```

### 3.1 Go sim 侧的同构落地

Go sim 不应该把这些阶段揉成一个 `run`，而是显式保留和 real 一样的结构，只是检查对象换成仿真域资源。

sim 侧可以这样理解：

```text
preflight
  检查 Docker / images / task config / profile / artifact root / ports
prepare
  生成 artifact / runtime artifacts / service plan / probe plan / rosbag plan
common-doctor
  检查 sim 共享语义：no-truth-input / source claims / frame / topic freshness
task-doctor
  检查任务特定语义：hover / navigation / scan-robustness 等
runtime-execute
  真正启动 Gazebo / SITL / SLAM / companion / rosbag / probes
gate
  汇总 evidence / blockers / warnings / summary
```

这里的关键不是名称，而是边界：

- `preflight` 只回答“有没有资格开始准备”。
- `prepare` 只回答“这次 run 的 service/probe/resource plan 是否成立，以及要生成哪些 runtime artifacts”。
- `common-doctor` 只检查所有 sim task 都共享的运行健康状态。
- `task-doctor` 只检查具体 task 的额外约束。
- `runtime-execute` 才允许产生真实副作用。

sim 的默认 task-doctor 不能静默缺失；如果某个 task 暂时没有特定检查，也要落一个显式 artifact：

```json
{
  "task_doctor_claim": "not_applicable",
  "ok": true,
  "reason": "task_has_no_specific_preflight_requirements"
}
```

这能保证后续看 summary/artifact 时，能分清楚“没有检查”还是“检查后确认不需要”。

### 4. Rust real 应该保留 Go sim 的观察能力

Go sim 里有很多观察面：runtime plan、source claim、topic freshness、ExternalNav 状态、hover health、mission summary、gate evaluation、cohort row、artifact 指针等。这些不是 sim 专属能力，而是任务闭环必须有的证据层。

迁移到 real 时，应该保留这些观察思想，但删除或替换 sim-only 部分：

- 保留：source claim、required topic freshness、FCU status、ExternalNav status、SLAM odom freshness、task FSM state、operator confirmation、timeout、summary/gate/cohort。
- 删除/降级：Gazebo truth、Gazebo model odometry、official maze overlay、Foxglove lite replay 这类仿真 review-only 证据。
- 替换：sim sensor status 替换成真实 lidar/rangefinder/IMU/FCU evidence。

所以 Rust real 不是要从零写一套更简单的任务系统，而是要把 Go sim 已经验证过的观测闭环，按 real 的安全边界重新落地。

## preflight / prepare / common-doctor / task-doctor 定义

### preflight

`preflight` 是不启动任务前就能做的基础资格检查。

sim preflight 检查：

- Docker daemon 是否可用。
- 必要 images 是否存在或可 build。
- task YAML 是否能 parse。
- simulation profile 是否存在。
- artifact root 是否可写。
- runtime mode 是否是 simulation。
- host 工具是否存在，例如 docker、rosbag/mcap/Foxglove 工具。
- 是否有明显端口/网络冲突。

real preflight 检查：

- runtime mode 是否是 real，backend 是否是 process。
- host 依赖是否存在，例如 `ros2`、`mavlink-routerd`。
- 真实串口是否存在、可打开。
- 基础 MAVLink heartbeat/status 是否可读。
- ROS package / Python module 是否存在。
- TCP/UDP endpoint 不能冒充真实串口证据。

### prepare

`prepare` 负责规划和生成任务需要的 runtime 环境，但不执行 task body。

sim prepare 可以负责：

- 生成 artifact layout。
- 生成 runtime artifacts，例如 runtime scripts、task request、SLAM config、Gazebo model overlay、rosbag profile、Foxglove/review 配置。
- 生成 service plan，例如 SITL / MAVLink routing、sim companion、ExternalNav bridge、gazebo sensor / X2 emulator、Cartographer SLAM、sim rangefinder emulator / bridge。
- 生成 probe plan 和 required topic plan。
- 生成 rosbag plan。
- 记录 Docker / image / source provenance。
- 审计 forbidden truth/control input，避免 Gazebo truth、official overlay、seed map 进入 runtime input。
- 可选检查或准备 Docker network/images，但第一版可以只做 plan/artifact，不启动 Gazebo/SITL。

real prepare 可以负责：

- 启动 `mavlink_router`。
- 启动 `navlab_mavlink_bridge`。
- 启动 lidar driver。
- 启动 SLAM。
- 启动 rangefinder bridge。
- 检查关键 topic 是否出现、是否 fresh、frame/source claim 是否合理。

建议把 prepare 拆清楚：

```text
prepare = 生成 runtime artifacts + service/probe/rosbag plan + resource provenance + 可选启动基础资源
runtime-execute = 真正启动任务 runtime / mission / probes
```

sim prepare 应参考 real prepare 的 service-plan 模型，而不是只理解成“生成文件”。对应关系是：

| real prepare | sim prepare |
|---|---|
| `mavlink_router` | SITL / MAVLink routing plan |
| `navlab_mavlink_bridge` | sim companion / ExternalNav bridge plan |
| lidar driver | gazebo sensor / X2 emulator plan |
| SLAM | Cartographer SLAM service plan |
| rangefinder bridge | sim rangefinder emulator / bridge plan |
| serial provenance | Docker / image / source provenance |
| forbidden sim token | forbidden truth/control input audit |
| topic readiness | sim topic readiness / required topic plan |
| process log dir | container / service log dir |
| health topics | probe specs / required topics |

第一阶段的 sim prepare 可以是 dry-run prepare：只写 `prepare_summary`、`doctor_result`、`runtime_plan`、`service_plan`、`probe_plan` 和 runtime artifacts。后续如果需要 live prepare，再允许创建 Docker network、确认 image，或预拉起不执行任务主体的基础 service。

### common-doctor

`common-doctor` 是所有任务都关心的通用语义检查。

sim common-doctor 可以检查：

- runtime mode 是 simulation。
- source claim 是否一致。
- Gazebo truth 是否没有进入 input。
- official maze overlay 是否只是 review-only。
- `/scan`、`/tf`、`/tf_static`、`/slam/odom` 是否有合理 evidence。
- ExternalNav、MAVLink ExternalNav、FCU status 是否有共同健康状态。
- rosbag profile required topics 是否合理。
- frame contract 是否基本成立。

real common-doctor 可以检查：

- FCU 状态是否可读。
- MAVLink bridge 是否健康。
- ExternalNav status 是否 fresh。
- SLAM odom 是否来自 real SLAM source。
- scan/IMU/rangefinder 是否来自 real source claims。
- forbidden simulation topics 是否未被用作输入。
- operator safety 之外的通用硬件状态是否可读。

### task-doctor

`task-doctor` 是具体任务自己的前置检查。

默认 task-doctor 应该所有 task 都有：

- task config 合法。
- duration/deadline 合法。
- profile 合法。
- required helpers/specs 存在。
- artifact paths 合法。
- 如果没有 task-specific 检查，也要写 `not_applicable` summary，不能静默缺失。

复杂任务再加 task-specific doctor：

- hover：altitude、hover health、span target/hard-cap、landing policy、ExternalNav requirement。
- navigation：Nav2 params、costmap topics、goals、official overlay 不能当 input。
- scan-robustness：disturbance profiles、scan stabilization config。
- motor-debug：motor_percent、motor_sec、motor_count、no-props、安全确认、GUIDED/arm/spin/disarm 前置规则。

task-doctor 的结论：

```text
结构可以 common。
证据来源和安全边界必须区分 sim/real。
```

推荐实现：

```text
common policy/check model
  + sim evidence adapter
  + real evidence adapter
```

## sim 和 real 差异矩阵

| 领域 | 当前 sim hover | 当前 real stack | 设计结论 |
|---|---|---|---|
| 控制面语言 | Go `navlab-sim` | Rust `navlab-real` | 控制面可不同，但 workflow schema 应统一。 |
| 当前主 task | `hover` 已跑通基本闭环 | `motor-debug` 是唯一 real task | 短期先让 `motor-debug` 成为 real 最小闭环样板。 |
| 外层模型 | 目前隐式混在 run/gate/helper 里 | 已有 preflight/prepare/doctor | 统一抽成小 DAG。 |
| task body | hover mission FSM | motor-debug 顺序逻辑偏多 | real `motor-debug` 需要显式 FSM。 |
| runtime mode | `docker + simulation` | `process + real` | 阶段形状一致，evidence source 不同。 |
| source evidence | Gazebo/SITL/sim sensors + no-cheat audit | serial/real FCU/real sensors | source claim schema 可共用，采集 adapter 分开。 |
| common-doctor | 很多观察散在 Go gate/helper 中 | 已有 `common-doctor` | sim 也应有 common-doctor；real 继续强化。 |
| task-doctor | 很多 task 没显式 task doctor | real 有 `task-doctor` 框架 | 所有 task 至少有 default/no-op doctor artifact。 |
| artifact | sim 已有较多 artifact/cohort | real summary 较少 | real 要补 runtime events、node results、FSM summary。 |
| sim-only review | Gazebo truth、official overlay、Foxglove lite | real 不应存在 | review-only 不能迁到 real，只保留抽象 observation schema。 |

## navlab common 迁移边界

`navlab.common` 可以承接很多逻辑，但不能乱放安全域代码。

可以迁到 `navlab.common` 的是纯逻辑：

- FSM 状态模型和状态转移记录器。
- evidence recorder。
- summary builder。
- gate status / reason code。
- operator confirmation payload parser。
- deadline/timeout 语义。
- task config validation helper。
- artifact JSON schema helper。
- topic/status payload 解析。

不应该迁到 `navlab.common` 的是安全域 runtime：

- Gazebo/SITL/仿真 sensor bridge：留在 `navlab.sim.*`。
- 真实串口、真实 FCU、真实 lidar/rangefinder：留在 `navlab.real.*`。
- 直接 arm/disarm/takeoff/motor command 的 runtime adapter：按 real/sim 分 wrapper，公共部分只能是接口或纯协议数据结构。

推荐结构：

```text
navlab.common
  mission FSM / evidence / summary / schema / reason codes
navlab.sim
  SITL/Gazebo/MAVLink sim adapter + sim mission wrapper
navlab.real
  real FCU/lidar/rangefinder adapter + real task wrapper
orchestration.sim
  Go sim control plane: DAG nodes, sim scheduling, artifacts, gates
orchestration.real
  Rust real control plane: DAG nodes, preflight, prepare, doctor, run, artifacts
```

重点：

```text
common 放可复用语义。
sim/real 分别负责证据来源和副作用。
```

## 官方 / 无作弊定义审计

这里必须先拆清楚，“官方”至少有两个含义，不能混着说。

### 定义 A：ArduPilot 支持的 ExternalNav / Guided hover

这个定义问的是：任务是否使用了 ArduPilot 文档里支持的机制。

- ArduPilot 文档说明：可以通过 MAVLink External Navigation 把外部位置/速度估计发给 EKF，用于无 GPS 的位置估计和控制。
- ArduPilot 文档里 `ODOMETRY` 是推荐的 MAVLink 消息，其他 vision/mocap 消息也可以作为备选。
- ArduPilot 使用 ExternalNav 时需要配置 EKF source，例如 `EK3_SRC1_POSXY=6`、`EK3_SRC1_VELXY=6` 等。
- ArduPilot Guided Mode 支持 `SET_POSITION_TARGET_LOCAL_NED` 这类移动命令，也支持 takeoff/land 等 command-long 动作。

按定义 A 看当前 sim hover：

- **机制上基本合规，也不是作弊**：当前路径是 `/scan + /imu -> SLAM -> /slam/odom -> ExternalNav/MAVLink ODOMETRY -> FCU EKF -> GUIDED hover`，这是一条合理的 no-GPS estimation/control 路线。
- **审计路径里没有看到直接 truth 注入**：代码/文档/测试反复阻止 `uses_gazebo_truth_input=true`、diagnostic truth odometry 作为 ExternalNav、known-map input、official maze overlay 作为 runtime control input。
- **但还需要补强观测面**：FCU/controller/setpoint evidence、frame origin/sign convention、timestamp alignment、Gazebo review-only contract 还需要继续硬化；现在更适合说 case-study 可用，而不是说统计稳定性已经充分证明。

### 定义 B：ArduPilot 官方 ROS 2 / DDS / Gazebo / Cartographer 路线

这个定义问的是：任务是否完整走了 ArduPilot 官方 ROS 2/DDS 路线。

- ArduPilot ROS 2 Interfaces 文档里有 DDS 暴露的 topic，例如 `ap/pose/filtered`、`ap/twist/filtered`，也有 `/ap/arm_motors`、`/ap/mode_switch`、`/ap/experimental/takeoff` 等 service。
- ArduPilot ROS 2 with SITL/Gazebo 文档描述了 Micro-ROS/DDS、SITL、Gazebo、Cartographer 这条教程路线。

按定义 B 看当前 sim hover：

- **还不能说完全合规**：当前 sim hover 的完成路径仍然主要是 NavLab 自己的 MAVLink ExternalNav bridge 和 Go 生成的 runtime scripts，不是纯官方 ROS 2/DDS task body。
- 这不代表它作弊；它代表当前任务是一个 NavLab no-cheat ExternalNav hover baseline，而 full official DDS conformance 是另一个收敛目标。
- 所以对外表述时不要说“已经完整符合官方 ArduPilot ROS 2 hover task”，除非后续 phase 证明 `/ap` DDS 路线端到端拥有 arm/takeoff/mode/setpoint/pose evidence。

## 可执行 phase

### Phase WF0：冻结统一 workflow 术语和 schema

目标：先统一 sim/real 对外层 DAG、内层 FSM、doctor result、artifact 的命名。

任务：

- [ ] 定义 `WorkflowNode` / `NodeResult` 最小字段。
- [ ] 定义 `NavLabFsmTransition` 最小字段。
- [ ] 定义 common blocker/reason code 命名规则。
- [ ] 定义 `not_applicable` task-doctor summary 语义。
- [ ] 文档明确：第一阶段不引入 DAG 第三方库。

验收：

- Go sim 和 Rust real 能用同一套术语讨论 workflow。
- 每个阶段输出都能被 summary/cohort 引用。

### Phase WF1：Go sim 补 preflight/prepare/common-doctor/default task-doctor 形状

目标：让 sim 侧不再把所有观察散在 task run/gate/helper 里。

任务：

- [ ] 增加 sim preflight：Docker、image、task config、profile、artifact root。
- [ ] 增加 sim prepare：prepare summary、doctor_result、runtime artifacts、service/probe/rosbag plan、Docker/image/source provenance、forbidden-input audit。
- [ ] 增加 sim common-doctor：source claim、no-truth-input、frame/SLAM/ExternalNav/FCU common evidence。
- [ ] 增加 default task-doctor：没有 task-specific 检查时写 `not_applicable` artifact。
- [ ] hover/navigation/scan-robustness 再逐步补 task-specific doctor。

验收：

- `just navlab-run hover --dry-run` 能看到 preflight/prepare/doctor 节点结果。
- 没有 task-specific doctor 的 task 不再“静默缺检查”。

### Phase WF2：Rust real 用 motor-debug 做最小闭环

目标：不是做 real hover，而是让 `motor-debug` 成为第一个完整 real task pipeline 样板。

任务：

- [ ] 把 `preflight -> prepare -> common-doctor -> task-doctor -> run` 作为 real workflow DAG 显式记录。
- [ ] `run motor-debug --with-doctor-chain` 挂接 upstream doctor artifact。
- [ ] 为 `motor-debug` summary 增加 `workflow_nodes`、`fsm`、`deadline`、`operator_confirmations`、`mavlink_evidence`。
- [ ] blocked run 也要写可读 summary，不只返回 CLI error。

验收：

- 一次 dry-run 产出 request/plan/node results/summary。
- 一次 blocked run 能定位到具体 blocked node 或 FSM state。

### Phase WF3：给 motor-debug 增加显式 FSM

目标：`motor-debug` 不再只是顺序执行 arm/spin/disarm，而是有可记录、可审计、可 fail-closed 的 FSM。主状态保持和 flight task 模板对齐，request / ACK / confirm 作为 transition evidence。

建议 FSM：

```text
runtime_ready
  -> guided
  -> armed
  -> motor_spin_hold
  -> disarmed
  -> completed
```

等价地，也可以把它写成模板形式：

```text
runtime_ready
  -> guided
  -> arm
  -> task_body(motor_spin_hold)
  -> disarm
  -> completed
```

失败状态：

```text
blocked_operator_confirm
blocked_guided_mode
blocked_arm
blocked_motor_spin
blocked_disarm
runtime_timeout
aborted
```

任务：

- [ ] 在 Rust real `motor-debug` task 里记录 FSM transition。
- [ ] 每个状态写 `state`、`entered_at`、`reason`、`evidence`。
- [ ] guided / arm / disarm 的 request、ACK、heartbeat、mode、armed/disarmed evidence 绑定到对应 transition，不作为主状态。
- [ ] 失败时写明确 blocker，不要只返回 generic error。

验收：

- dry-run summary 能看到 planned FSM。
- live summary 能看到 actual FSM transitions。
- 任一 MAVLink step 失败时，summary 能定位到具体 failed state。

### Phase WF4：抽 common，但只抽纯逻辑

目标：让 sim hover、real motor-debug、未来 real hover 共享任务语义，不共享危险 side effect。

任务：

- [ ] 梳理 `navlab.common.companion.mission` 中可复用 FSM/evidence/summary。
- [ ] 抽象 task FSM recorder，不绑定 hover。
- [ ] 抽象 reason code / gate status / operator confirmation payload parser。
- [ ] 保持 real 串口/FCU/lidar 代码在 `navlab.real.*`。
- [ ] 保持 Gazebo/SITL 代码在 `navlab.sim.*`。

验收：

- common 里没有 Gazebo、SITL、真实串口 side effect。
- real wrapper 和 sim wrapper 通过 common 共享 FSM/evidence 语义，而不是互相 import。

### Phase WF5：再基于闭环讨论 real hover

目标：等 `motor-debug` 最小闭环跑顺后，再把同一套 real task pipeline 扩展到 real hover。

任务：

- [ ] 基于 `motor-debug` 的 workflow/FSM/artifact/gate 模板设计 real hover。
- [ ] real hover 不直接运行 `navlab.sim.*`。
- [ ] real hover 引入 hover-health stable window + operator confirm。
- [ ] real hover 再补 SLAM/ExternalNav/landing/motors-safe evidence。
- [ ] 决定 real hover completion definition 是 MAVLink ExternalNav 还是官方 DDS。

验收：

- real hover 的新增工作是在已有 real task pipeline 上扩展 mission FSM，而不是重做 orchestration。

## 立即建议

建议按这个顺序做：

1. 先不要做 real hover live task，先把 workflow DAG / task FSM 的术语和 artifact schema 定下来。
2. Go sim 补 `preflight`、`prepare`、`common-doctor`、default `task-doctor` 形状。
3. Rust real 保留 Go sim 的观察/gate/artifact 思想，但去掉 Gazebo/SITL/review-only 部分。
4. 用 `motor-debug` 做 real 最小闭环，补显式 FSM 和 runtime events。
5. 把纯 FSM/evidence/summary/reason-code 逻辑抽到 common；real/sim side effect 保持分包。
6. 等 `motor-debug` 闭环稳定后，再把同一套 pipeline 扩展成 real hover。

## 硬规则

- [ ] 外层 workflow 用 DAG，任务 body 用 FSM，不要混成一个巨型状态机。
- [ ] 第一阶段不引入 DAG 第三方库，先做项目内最小 DAG runner/schema。
- [ ] sim/real 的阶段形状可以一致，但 evidence adapter 必须分开。
- [ ] common 只能放纯逻辑，不能放 Gazebo/SITL/真实串口 side effect。
- [ ] real task body 不能放在或直接运行 `navlab.sim.*`。
- [ ] real mode 不能使用 Gazebo/SITL/official maze/seed-map/known-map input。
- [ ] 没有 DDS 路线证据前，不能声称 full official ROS 2/DDS compliance。

## 待确认问题

- `WorkflowNode` / `NodeResult` 是否先放在 orchestration 各自实现，还是上升到 `contracts`。
- sim preflight 是否只检查本地资源，还是允许触发 image build。
- sim live prepare 是否允许创建 Docker network、确认 image，或预拉起不执行任务主体的基础 service；第一版 dry-run prepare 只写 plan/artifact/summary。
- `motor-debug` 的最小 FSM 是否使用 `armed/disarmed` 状态名，还是使用 `arm/disarm` 阶段名；preflight/prepare/doctor 仍应作为外层 workflow node 写入 summary，而不是塞进 task FSM。
- Rust real 的 runtime events 用 `jsonl`，还是 summary 内嵌数组。
- 哪些 Go sim gate 字段应该做成语言无关 contract，哪些直接在 Rust real 重新实现。
- 下一阶段 real hover 的 completion definition 是 MAVLink ExternalNav，还是必须官方 DDS。
