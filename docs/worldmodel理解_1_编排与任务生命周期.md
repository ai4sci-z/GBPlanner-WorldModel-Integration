# worldmodel 理解(一):Go 编排层与任务生命周期

> 状态:CURRENT(2026-08-24)
> 读者:准备把 GBPlanner 移植成 ROS2 原生节点并接进 world-model 的人。
> 依据:精读 `orchestration/sim/`(cmd/navlab-sim、internal/tasks/、internal/tasks/helpers/、internal/runtime/)。
>
> **⚠️ 行号基准**:本文行号最初以 **WSL `~/ws-clean/world-model`、分支 `fix/world-model-e2e-takeoff` @ `e7ca9fc`** 为准;2026-08-24 已按本机当前分支复核 exploration 完成、返航、降落和 deadline 语义。精确行号可能继续漂移,以符号名和当前源码为准。
> Windows 镜像 `sources\world-model-源码\` 有 **3 个文件是旧版**(不含 45→90/35→90/容器150 与 QoS 内省):
> `orchestration/sim/internal/tasks/runtime_specs.go`、`internal/tasks/helpers/runtime_specs.go`、`internal/tasks/helpers/templates/python/ros_probe.py.tmpl`。其余本文引用的文件(runtime_runner.go、gate_evaluation.go、live_summary.go、helpers/execution_plan.go、cmd/navlab-sim/main.go)两处内容一致。
> 下文路径均相对仓库根 `world-model/orchestration/sim/`。

---

## 0. 这一层是什么

world-model 的仿真编排层是一个 **Go 写的控制平面**(单一二进制 `navlab-sim`,cobra CLI,`cmd/navlab-sim/main.go:53-89`)。它本身**不是 ROS 节点、不参与任何实时控制**;它做四件事:

1. **规划**:把任务 YAML + helper 注册表展开成一份声明式执行计划(services / probes / rosbags / result gates);
2. **渲染**:用 Go template 生成所有运行期产物 —— Python 运行脚本、TOML/YAML 配置、SDF 模型覆盖、ArduPilot 参数;
3. **执行**:用 Docker SDK 起一组容器(Gazebo/SITL、SLAM、控制器、工作流、探针、rosbag 录制),带全局 deadline;
4. **裁决**:从探针 JSON、rosbag 元数据、运行日志离线评估 gate,写出 `summary.json` 定 run 的生死。

一个关键设计:**真正跑在 ROS 里的全部是渲染出来的 Python 脚本**(`runtime/scripts/*.py`、`probes/*.py`),Go 层只通过"文件产物"与它们交互(计划注释原文:"Generated runtime scripts may execute Python inside ROS containers … but orchestration no longer depends on Python helpers",`internal/tasks/helpers/execution_plan.go:93`)。对移植 GBPlanner 的含义:**你的 ROS2 planner 不需要动 Go 层任何执行逻辑,只需要满足它的 topic/JSON 契约**(见 §5)。

---

## 1. `navlab-sim run exploration` 完整生命周期时间线

入口:`newRunCommand`(`cmd/navlab-sim/main.go:154-193`,flags:`--dry-run/--tui/--duration-sec/--simulation-profile`)→ `runTask`(main.go:876-950)。非 dry-run 路径分两大步:`prepareTaskRun`(规划+渲染)→ `runLiveTask`(执行+裁决)。

### 阶段 A:规划(prepareTaskRun,main.go:988-1102)

| 步 | 动作 | 源码 |
|---|---|---|
| A1 | 读 `config.toml`(项目)+ `configs/tasks/exploration.yaml`(任务) | main.go:998-1007 |
| A2 | 任务注册表解析:exploration → 11 个 helper(artifacts, navlab-models, official-stack, sensors, slam, fcu-controller, frame-contract, motion, landing, rosbag-profiles, exploration-workflow) | `internal/tasks/registry.go:63-87` |
| A3 | `BuildExecutionPlan`:各 helper 往计划里追加 服务/探针/rosbag/gate 声明 | `internal/tasks/helpers/execution_plan.go:75-149` |
| A4 | 构建运行期配置(YAML 段覆盖默认值)+ 仿真 profile + hover SLO 策略 | main.go:1017-1028 |
| A5 | **创建 run 目录并写 task_plan.json/manifest.json**。run 目录 = `<artifact_root>/<task_id>/<run_id>`,artifact_root=`../../artifacts/sim`(config.toml:28),run_id 格式 `20060102T150405.000000000Z`(`internal/artifacts/writer.go:67-69,77-78`) | main.go:1038-1041 |
| A6 | `GenerateRuntimeArtifacts`:**渲染全部模板产物**(见下表) | main.go:1042-1045;`internal/tasks/runtime_artifacts.go:27-381` |
| A7 | `BuildRuntimeSpecs`:把计划落成可执行的 Docker 规格(镜像解析、卷挂载、容器命令、探针超时),写 `runtime_plan.json` | main.go:1049-1060;`internal/tasks/runtime_specs.go:23-219` |
| A8 | 写 planned FSM、workflow DAG、preflight/prepare/doctor 摘要(`dag/*.json`) | main.go:1066-1091 |
| A9 | **doctor 拦截**:doctor 有 blocker 时拒绝进入执行 | main.go:896-898 |

### 阶段 B:渲染产物(哪些模板 → 哪些文件)

run 目录固定骨架(`internal/artifacts/layout/layout.go:8-39`):`audits/ dag/ probes/ runtime/{scripts,config,logs} profiles/ rosbag/ sitl/`,根文件 `manifest.json summary.json mission_summary.json task_plan.json task_request.json runtime_plan.json` 等(layout.go:21-30)。

exploration 一次 run 渲染的产物(`runtime_artifacts.go`,模板都在 `internal/tasks/helpers/templates/`):

| helper | 产物(run 目录内) | 模板/来源 | 源码 |
|---|---|---|---|
| official-stack | `runtime/scripts/official_maze_overlay_runtime.py` | 读官方 `maze.sdf` 生成占据栅格发布脚本 | runtime_artifacts.go:40-51 |
| navlab-models | `runtime/config/bridge_override.yaml`(gz↔ROS 桥配置,含 `/lidar/points→cloud` 3D 预留)、`vendor_profile.yaml` | `templates/yaml/…` | runtime_artifacts.go:52-63 |
| sensors | `runtime/config/model_overlay.sdf`(iris+lidar 模型覆盖)、`gazebo-iris-rangefinder.parm`(**与 ExternalNav 参数 profile 合并**,RNGFND 参数归 NavLab 管)、`gazebo_sensor_runtime.toml`;`probes/rangefinder_probe.py`、`probes/imu_probe.py` | 模型/参数源默认**从 docker 镜像里 `cat` 出来**(officialOverlaySource,runtime_artifacts.go:507-532 — 渲染阶段就要求 Docker 可用) | runtime_artifacts.go:64-110、447-462 |
| slam | `runtime/config/slam_runtime.toml`、`external_nav_bridge_params.yaml` | | runtime_artifacts.go:111-156 |
| fcu-controller | `runtime/config/fcu_controller_runtime.toml`、`runtime/scripts/fcu_controller_runtime.py`。**exploration 特例**:把 MotionSpeedMPS/MinAcceptedGoals/MinPathLengthM 注入控制器,并把 `TaskCompletionStatusTopic=/navlab/exploration/status` —— 控制器靠探索状态判断任务完成、触发降落 | `fcu_controller_runtime.py.tmpl` | runtime_artifacts.go:157-200(注入在 162-168) |
| frame-contract | `runtime/config/frame_contract_runtime.toml`、`probes/frame_contract_probe.py` | `ros_probe.py.tmpl` | runtime_artifacts.go:202-215 |
| exploration-workflow | `runtime/config/exploration_runtime.toml`、`runtime/scripts/exploration_workflow_runtime.py`、`probes/exploration_probe.py` | `exploration_workflow_runtime.py.tmpl` / `ros_probe.py.tmpl` | runtime_artifacts.go:279-298 |
| rosbag | `profiles/exploration_rosbag.txt`(topic 清单一行一个) | runtime_specs.go:709-718(Windows 行号一致) | |

### 阶段 C:执行(runLiveTask → ExecuteRuntimeSpecs)

`runLiveTask` 以如下选项调 `ExecuteRuntimeSpecs`:`WaitForRosbags=true`、`RosbagPostTaskGraceSec=5`,exploration 的 Go watchdog 由 `RuntimeTaskDeadlineSec` 取 `max(plan.DurationSec, exploration_probe脚本预算+10s)`。默认配置为 **178s**,不再被 YAML 的 150s 在返航/降落证据完成前抢先清理;其他任务仍沿用配置 duration。

`ExecuteRuntimeSpecs`(runtime_runner.go:74-234)的时间线:

```
t0  run.started
    ├─ 逐个顺序启动 Services(runtime_runner.go:101-117):
    │    mavlink_router → official_baseline → official_maze_overlay
    │    → gazebo_sensor → slam_backend → fcu_controller → exploration_workflow
    │    → mavlink_external_nav → height_estimator
    │    (顺序 = BuildRuntimeSpecs 的追加顺序:官方栈三件套先行 runtime_specs.go:46-73,
    │     再按 helper 顺序 75-117,最后 external-nav/height 118-135;
    │     任一 Start 失败 → 立即 cleanup + run.failed)
    ├─ startup-readiness 监视器:仅 hover 任务启用(runtime_runner.go:321-327),exploration 跳过
    ├─ 启动 Rosbags(runtime_runner.go:145-158):exploration_rosbag 开始录制
t1  ├─ runProbes:4 个探针【并发】各起一个一次性容器(runtime_runner.go:160,242-284;
    │    每个探针一个 goroutine,L249-256),与任务窗口同时在线观测
    │    ……(此期间任务本体在容器里跑:起飞→探索窗口→降落)……
    ├─ 探针结果聚合(runtime_runner.go:164-209):
    │    required 探针 err 或 rc≠0 → 仍等 rosbag 收尾(保全证据)→ run.blocked,返回 error
t2  ├─ 任务结束:等 5s 后停录制(waitPostTaskRosbagGrace L596-607)
    │    → finalizeRosbags:SIGINT 停 ros2 bag record、校验 metadata/mcap(L609-637)
    ├─ cleanup:逆序 stop 全部容器(L84-90,711-724)
t3  run.completed / run.blocked
全程:每个阶段前检查配置派生 deadline(exploration 默认178s);超时 → 写兜底 mission_summary.json
     (reason=task_runtime_timeout,L658-683)+ 抓容器日志 + cleanup(L91-98)
```

### 阶段 D:裁决与落盘(main.go:1163-1259)

1. `BuildLiveRunSummary`(`internal/tasks/live_summary.go:104-187`)内部调 `EvaluateResultGates`(见 §4),blockers 为空 ⇔ `ok=true`;
2. 状态/退出码:`TASK_STATUS_OK`(exit 0)/ `TASK_STATUS_ERROR`(executionErr≠nil,exit 1)/ `TASK_STATUS_BLOCKED`(gate 拦下,exit 20)(live_summary.go:189-207);
3. 写 FSM 产物(rosbag recorder FSM + task FSM,main.go:1164-1172)→ **`summary.json`**(main.go:1175-1180)→ `dag/common_doctor_live_summary.json`、live workflow/doctor(main.go:1188-1213)→ `FinalizeRunArtifacts`(summary.md 等,main.go:1220-1224)→ manifest 收口。

---

## 2. 容器/服务全景表(exploration 任务,9 服务 + 1 rosbag + 4 探针)

镜像引用解析:`resolveImageRef`,其中 `images.runtime` 别名到 `official_baseline` 镜像(runtime_specs.go:303-310,WSL 行号;镜像定义 config.toml:31-95)。所有容器 `--network host`、挂载整个 workspace 到 `/workspace`。

| # | 服务名(容器名) | 镜像 | 干什么 | 关键 topic(出/入) | 源码 |
|---|---|---|---|---|---|
| 1 | mavlink_router(navlab-mavlink-router) | navlab/mavlink-router | MAVLink UDP 路由:listen 0.0.0.0:14550 → 下游 14551/14552/14553 | (非 ROS) | runtime_specs.go:401-445 |
| 2 | official_baseline(navlab-official-baseline) | navlab/official-baseline | 主容器:`ros2 launch ardupilot_gz_bringup iris_maze.launch.py … use_dds_agent:=true`,即 Gazebo 迷宫 + ArduPilot SITL + micro-ROS agent;附带 benewake TFmini 虚拟串口(serial7)、AHRS set-origin lua;挂载 model_overlay.sdf / .parm / bridge_override.yaml 覆盖 | 出:`/clock` `/imu` `/lidar`(gz 桥)`/odometry`(真值诊断);micro-ROS:`/ap/v1/pose/filtered` `/ap/v1/twist/filtered` `/ap/v1/status`;入:`/ap/v1/cmd_vel` | runtime_specs.go:544-641(串口参数注入 636-641) |
| 3 | official_maze_overlay(navlab-official-maze-overlay) | images.runtime | 把官方 maze.sdf 栅格化后周期发布(GUI/Foxglove 审查用,不参与控制) | 出:overlay occupancy topic | runtime_specs.go:643-679 |
| 4 | gazebo_sensor(见 GazeboSensorContainer) | navlab/gazebo-sensor | 传感器管线:X2 激光虚拟串口仿真,`/lidar` → **`/scan`**;测距计 range/status | 入:`/lidar`;出:`/scan` `/sim/x2/status` `/rangefinder/down/range` `/rangefinder/down/status`(默认值 helpers/runtime_specs.go:102-127) | execution_plan.go:198-215 |
| 5 | slam_backend(SlamBackendContainer) | navlab/slam-cartographer | Cartographer SLAM | 入:`/scan` `/navlab/slam/imu`;出:**`/slam/odom`** `/navlab/slam/status`(默认 helpers/slam.go:87-97) | execution_plan.go:219-243 |
| 6 | fcu_controller(FCUControllerContainer) | images.runtime | 起飞/控制闭环:消费 **`/navlab/fcu/setpoint/intent`**(JSON String)→ 仅走 MAVLink LOCAL_NED 位置目标;严格复核 `/navlab/exploration/status` 的本地 goal/path 下限,随后实测返航并执行 LAND/touchdown/disarm 闭环 | 入:intent、`/slam/odom`、rangefinder、MAVLink FCU 状态;出:`/navlab/fcu/controller/status` `/navlab/fcu/setpoint/output` `/navlab/fcu/owner/status` `/navlab/landing/status` | execution_plan.go;runtime_artifacts.go;`fcu_controller_runtime.py.tmpl` |
| 7 | exploration_workflow(navlab-exploration-workflow) | images.runtime | 探索策略本体(frontier_lite 内建;`strategy=external` 时整体让位,见 §5) | 出:`/navlab/fcu/setpoint/intent`、**`/navlab/exploration/status`** 及 goal/coverage/frontiers/path/markers 审查族;入:`/navlab/fcu/controller/status` `/slam/odom` | execution_plan.go:489-540 |
| 8 | mavlink_external_nav(MAVLinkExternalNavContainer) | images.runtime | `/external_nav/odom` → MAVLink 视觉/外部导航注入 SITL(udpin:14553);现状 `--no-align-yaw-to-fcu`(EKF yaw 源修复,commit 99bcfa1) | 入:`/external_nav/odom` `/navlab/fcu/local_position_pose`;出:`/mavlink_external_nav/status` | runtime_specs.go:447-495(参数 458-472) |
| 9 | height_estimator(navlab-height-estimator) | images.runtime | 测距计 → 高度估计 | 入:`/rangefinder/down/range`;出:`/height/estimate` `/height/status` | runtime_specs.go:497-542 |
| R | exploration_rosbag | images.runtime | `ros2 bag record -s mcap --compression-format zstd -o … --topics <清单>`;由编排层 SIGINT 收尾(非定时自杀) | 录制清单=ExplorationTaskReviewTopics | `internal/runtime/docker_backend.go:363-398`;runtime_specs.go:184-217 |

> 服务启动顺序即上表顺序(§1 阶段 C)。exploration 没有"延后启动"的服务;hover 任务才有 `hover_mission` 延后到 startup-readiness 通过之后(runtime_runner.go:321-327)。

---

## 3. 探针体系(现状口径,含我们调过的预算)

### 3.1 机制:一份模板生成所有探针

所有 `*_probe.py` 都由 `ros_probe.py.tmpl` 渲染(`internal/tasks/helpers/templates/python/ros_probe.py.tmpl`)。行为:

- **两条采样通路**:以 `/status /output /intent /goal /coverage /frontiers /path /markers` 结尾的 topic 视为 JSON-String,走**批量订阅**(一个 rclpy 节点同时订全部,tmpl:16,286-344);其余(Odometry/Range/Imu/TF)逐个走 **message 采样**(tmpl:137-250),失败再退化到 `ros2 topic echo --once` 重试(tmpl:79-135,瞬态错误白名单 271-284)。⚠️ 经验教训:jazzy 下 CLI echo 对 rclpy 发布者可能收不到,**验收以 rclpy 订阅为准**(所以 rclpy 优先、CLI 只是兜底)。
- **类型发现用全预算**(B16 修复):等 topic 类型出现在 graph 里的窗口从 2s 改为整个 `PROBE_TIMEOUT_SEC`(tmpl:151-166,注释注明 micro-ROS 话题实测 ~29s 才可见);
- **QoS 内省**(B16 修复):订阅前查发布者 QoS 并镜像其 reliability/durability(≤10s 或预算 1/3,tmpl:173-204);查不到且 topic 名以 `tf_static` 结尾 → 默认 TRANSIENT_LOCAL(tmpl:189-195),解决 latched `/tf_static` 用 volatile 订阅永远收不到的问题;
- **消息等待也用全预算**(tmpl:206-214,注释:类型已发现说明发布者存在,DDS endpoint 匹配对 micro-ROS agent 实测 ~30s,匹配后数据立刻到);
- **slam odom 证据兜底**:`SlamOdomTopic` 采样失败时,若 `/navlab/slam/status` 的 `output.odom_count>0` 等字段成立则视为通过(tmpl:58-77)—— 这就是 "slam.ready=False 不一定挡 gate" 的机制之一;
- 输出:单个 JSON(`ok/samples/blockers/optional_blockers`),**ok=false 时进程退出码 20**(tmpl:30-44)。

### 3.2 预算是两级的(容器级必须 > 脚本级)

- **容器级**:`ProbeSpec.TimeoutSec` → docker context deadline,超时容器直接被杀("context deadline exceeded",`internal/runtime/docker_backend.go:174-179`)。取值:`probeTimeoutSec`(`internal/tasks/runtime_specs.go:270-301`)。
- **脚本级**:`PROBE_TIMEOUT_SEC = SPEC.ProbeTimeoutSec`(tmpl:10),即 per-topic 观测预算;String 批采样整体等待 `STRING_READY_TIMEOUT_SEC = max(batch, PROBE_TIMEOUT_SEC)`(tmpl:13)。

### 3.3 exploration 的 4 个探针(全部 required)

`probeRequiredForRuntime`:除 `slam_hover_probe` 外全为 required(runtime_specs.go:266-268)。

| 探针 | 验什么(topic 清单) | 容器超时 | 脚本内预算 | 源码 |
|---|---|---|---|---|
| rangefinder_probe | `/rangefinder/down/range` `/rangefinder/down/status` 有数据 | 30s(默认,runtime_specs.go:300) | 8s(spec 无 ProbeTimeoutSec 字段,tmpl:10 默认) | helpers/runtime_specs.go:176-183 |
| imu_probe | `/imu` 有数据 | 30s | 8s | execution_plan.go:214 |
| frame_contract_probe | **8 个 topic**:`/tf` `/tf_static` `/scan` `/imu` `/rangefinder/down/range` `/ap/v1/pose/filtered` `/slam/odom` `/navlab/slam/status`(即"frame_contract 8/8 话题") | **150s**(runtime_specs.go:277-281,注释:90s per-topic 预算 + 慢的 micro-ROS 话题的余量) | **90s**(was 45;FrameContractSpec.ProbeTimeoutSec,helpers/runtime_specs.go:439-443 字段注释、475-477 取值注释:单独实测 ~29s、满载 48.96s,45s 偶发不够) | helpers/runtime_specs.go:488-493 |
| exploration_probe | `/navlab/fcu/controller/status` `/navlab/fcu/setpoint/output` **`/navlab/exploration/status`** `/slam/odom` `/navlab/landing/status`(5 个,无 optional) | 默认 **180s**(`max(150,duration+30)`) | 默认 **168s**=`15 DDS余量 + 45 FCU readiness + 26 exploration + 2 pre-land hold + 45 return + 35 landing`;由运行配置动态派生 | `explorationSpec`;`probeTimeoutSec`;`RuntimeTaskDeadlineSec` |

其他任务参考:`navigation_status_probe = max(duration,90)`、`slam_hover_probe = max(duration+30,120)`(runtime_specs.go:271-276,294-299)。⚠️ 小瑕疵:`probeTimeoutSec` 里 L288-293 还有第二个 `frame_contract_probe` 分支(返回 90),被 L277 的分支遮蔽,是死代码,读代码时别被绕进去。

### 3.4 探针失败如何决定 run 结局(双通道)

1. **运行层**(runtime_runner.go:164-209):required 探针 err 或 rc≠0 → 先等 rosbag 收尾保全证据,再 `run.blocked` 并让 `ExecuteRuntimeSpecs` 返回 error → summary 记 `runtime_execution_failed`、状态 `TASK_STATUS_ERROR`(live_summary.go:117-120,189-197);
2. **gate 层**(gate_evaluation.go:112-136):即使容器 rc≠0,只要 JSON 输出已写出,gate 仍解析它:`probe_failed:<name>:rc=…`、输出缺失/为空/`ok=false` 分别记 `probe_output_missing/empty/not_ok`,并**透传** payload 顶层 `blockers` 与各 sample `parsed.blockers`(probeBlockers,gate_evaluation.go:3117-3145;landing/scan_reference/source_selector 的 status 样本豁免透传)。gate 读探针文件时会等文件"稳定成合法 JSON"最多 ~5s(readEventuallyStableProbeOutput,gate_evaluation.go:3298-3323)。

---

## 4. gate 评估:exploration 判据从哪来、怎么判

总入口 `EvaluateResultGates`(gate_evaluation.go:92-189),`OK = len(blockers)==0`(L178-188)。blockers 来源按序:

1. **静态 taskChecks**(gate_evaluation.go:3483-3487):`exploration_window_positive`(ExplorationWindowSec>0)、`exploration_min_goals_positive`(MinAcceptedGoals>0)、`exploration_landing_policy_valid`、`exploration_claim_evaluated`(claim 必须是 "evaluated")。配置默认:window 26s、min_goals 3、min_path 0.35m、speed 0.10m/s(`configs/tasks/exploration.yaml:19-24`;缺省值 helpers/runtime_specs.go:1121-1136)。
2. **executionErr**(runtime 层失败,L109-111)与 **探针 rc / 输出**(§3.4)。
3. **rosbag required topics**(evaluateRosbagProfiles,gate_evaluation.go:3325-3376):读 `rosbag/exploration_rosbag/metadata.yaml`(缺失则直接流式数 mcap 消息,L3338-3352),required 集缺 topic 或计数为 0 → `rosbag_profile_failed:exploration_rosbag`。required 集(`helpers/rosbag_topic_sets.go:84-99`):`/tf /tf_static /ap/v1/pose/filtered /ap/v1/twist/filtered /rangefinder/down/range /navlab/fcu/controller/status /navlab/fcu/setpoint/intent /navlab/fcu/setpoint/output /navlab/exploration/status /slam/odom /scan /map`。
4. **landing acceptance**(gate_evaluation.go:149-161):证据取自探针样本里的 `/navlab/landing/status`(landingFromProbeOutputs,L3199-3241),按 exploration 策略 `return_home_then_land`(exploration.yaml:26;landingConfig L3589-3622)评估,landing.Blockers 全部并入。
5. **slam 运行日志 blockers**(L162,全任务通用)。

### 4.1 accepted_goals / path 的真正判定点在工作流脚本里

gate 对 exploration 指标**只是复读**:`metricSummaryFromEvidence` 从探针样本 `/navlab/exploration/status` 的 parsed JSON 摘 `claim/strategy/accepted_goals/min_accepted_goals/path_length_m/min_path_length_m`(gate_evaluation.go:223-226)进 `summary.metrics.gate.exploration`;判 ok/不 ok 的逻辑在 `exploration_workflow_runtime.py.tmpl` 里:

- **status 的 ok**:blockers 为空,blockers 由 `controller_not_ready / slam_odom_missing / accepted_goals_below_min / path_length_below_min` 组成(tmpl:187-219)。status.ok=false → 探针里该 sample 的 `parsed.ok=false` → 探针 `effective_sample_ok` 判失败(ros_probe.py.tmpl:58-64)→ 探针 ok=false、rc=20 → gate blockers。
- **accepted_goals 是纯时间驱动的**(基线判据的已知根因):controller ready 后按 `ready_elapsed/segment_sec` 递进 goal_index,`segment_sec = max(2, window/min_goals)`(≈8.67s/个),只要有 odom 样本就计数(tmpl:117-121,79-81)——不是真实 frontier 接受计数。
- **path_length_m 从 `/slam/odom` 积分**,单步 >1m 的跳变丢弃(tmpl:50-65);controller 首次 ready 时全部清零重计(tmpl:38-48)。
- **完成后**:发 stop intent、保持 5s,广播最终 status(tmpl:107-115,129-134)。

另外注意**双重消费**:fcu_controller 也被注入同一组阈值并订阅 `/navlab/exploration/status`。现在只有 JSON 布尔 `ok=true`、本地配置的 goal/path 下限、上报下限以及空 blockers 同时满足才触发 `return_home_then_land`;外部 status 不能通过把自己的 minimum 调低来提前收工。status 造假/缺失会保持 fail-closed,并最终形成 landing/timeout blocker。

---

## 5. 对"GBPlanner→ROS2 原生移植"的直接落点

1. **让位机制已内建**:`exploration_gate.strategy: external`(改 `configs/tasks/exploration.yaml:20`)时,`exploration_workflow_runtime.py` 全程只 spin 不发任何 intent/status(tmpl:86-96,注释点名 "e.g. a bridged GBPlanner"),把 `/navlab/fcu/setpoint/intent` 和 `/navlab/exploration/status` 的所有权让给进程外 planner。这正是 Stage4c/5a 走通的路径。
2. **你的 ROS2 GBPlanner(或其适配器)必须满足的契约**:
   - 发 `/navlab/fcu/setpoint/intent`(std_msgs/String,JSON:`ok/linear_x_mps/linear_y_mps/yaw_rate_radps/source/goal_id…`,字段样例见 tmpl:153-185);
   - 发 `/navlab/exploration/status`(JSON,**必须含** `ok/claim/strategy/accepted_goals/min_accepted_goals/path_length_m/min_path_length_m/blockers`,gate 摘取字段见 gate_evaluation.go:224,ok 判定见 ros_probe.py.tmpl:58-64);claim 需为 `evaluated`;
   - 保证 rosbag required 集里的 topic 有流量(尤其 `/navlab/exploration/status`、`/navlab/fcu/setpoint/intent`,§4 第 3 条)—— 只要满足这三条,**gate、探针、rosbag、summary 全链路零改动复用**。
3. **原生接入(替代薄桥)时的新服务位**:照 `execution_plan.go:502-512` 的样式给计划加一个 RuntimeServicePlan(镜像可用 `images.runtime` 或自建 jazzy+gbplanner 镜像),即可被编排层自动纳入启动/停止/日志/deadline 管理;探针照 `ExplorationProbeScript` 的写法加 topic 即可。
4. **预算经验直接复用**:micro-ROS/晚加入订阅的 DDS 发现 ~30-50s 是常态,新探针一律用"类型发现全预算 + QoS 内省 + 容器超时 > 脚本预算 + Go watchdog 再外包一层"的现行模式(§3),且必须把任务体后的返航/降落计入,别退回 8s/30s 旧默认。

---

## 附:文中未展开但相邻的文件

- `internal/tasks/runtime_fsm.go` — task/rosbag FSM 产物;`internal/tasks/workflow_summaries.go` — DAG/doctor 摘要;`internal/tasks/simulation_profiles.go` — ideal/realistic profile 对 runtimeConfig 的覆写;`internal/runtime/docker_backend.go` — Docker SDK 后端(host 网络、日志尾抓取、rosbag SIGINT finalize)。
- 佐证材料(以源码为准):`CURRENT_STATUS.md`、`docs/桥接查证与执行计划_2026-07-06.md`、`runbooks/world-model-jazzy/stage5a_diagnosis.md`。
