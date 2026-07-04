# Real Hover Orchestration Gap TODO

日期：2026-06-26

## 来源

本文是 `docs/notes/real_hover_orchestration_gap_audit.md` 的执行 TODO 版本。

审计结论需要继续沿用：

```text
preflight / prepare / common-doctor / task-doctor / gate
  -> sim 和 real 的阶段形状一致
  -> evidence 来源不同
  -> Gazebo / SITL / 真实硬件 side effect 必须分包
```

## 目标

把 audit 中的设计判断转成可逐步执行的 phase：

- Go sim 显式补 `preflight`、`prepare`、`common-doctor`、默认 `task-doctor`。
- Rust real 使用同一套阶段形状，先让 `motor-debug` 成为最小真实任务闭环样板。
- `navlab.common` 只承接纯 FSM / evidence / summary / reason-code 逻辑。
- real hover 等 `motor-debug` pipeline 稳定后再推进。

## 工作规则

- [ ] 不在 `motor-debug` 闭环前直接实现 real hover live task。
- [ ] 不把 sim-only evidence 作为 real gate input。
- [ ] 不把真实硬件 side effect 放进 `navlab.common`。
- [ ] 每个 phase 必须产出可见 artifact、summary、schema 或测试。
- [ ] 没有 task-specific doctor 的 task 必须写显式 `not_applicable` artifact，不能静默缺失。

## Phase WF0：冻结 workflow 术语和 schema

目标：先统一 sim/real 对外层 DAG、内层 FSM、doctor result、artifact 的命名。

输出：`docs/general/orchestration_workflow_schema.md`

任务：

- [x] 定义最小 `WorkflowNode` 字段。
- [x] 定义最小 `NodeResult` 字段。
- [x] 定义最小 `NavLabFsmTransition` 字段。
- [x] 定义 common blocker / reason-code 命名规则。
- [x] 定义默认 task-doctor 的 `not_applicable` summary 语义。
- [x] 明确第一阶段不引入第三方 DAG 库。

验收：

- [x] Go sim 和 Rust real 能用同一套术语描述 workflow。
- [x] 每个 workflow node 的输出都能被 summary / artifact 引用。
- [x] `not_applicable` 能明确表示“检查后认为不需要”，不是“忘了检查”。

## Phase WF1：Go sim 补 preflight / prepare / common-doctor / default task-doctor

状态：完成。

目标：让 sim 侧不再把通用观察散在 task run、gate、helper 里。

进展：

- [x] 2026-06-26：Go sim dry-run/prepare 已在 `dag/` 下写出 `preflight_summary.json`、`prepare_summary.json`、`common_doctor_summary.json`、`task_doctor_summary.json`、`workflow_summary.json`、`doctor_result.json`。
- [x] 2026-06-26：第一版 sim prepare 采用 real prepare 的 service-plan/probe-plan/resource-provenance 形状，但只生成计划和 artifact，不启动 Gazebo/SITL/SLAM/companion/rosbag/probes。
- [x] 2026-06-26：补 `run --dry-run --live-preflight` 和 live run 前置 resource probe；只检查 Docker daemon/user permission、image existence、network readiness，不启动 runtime services。
- [x] 2026-06-26：run id 改为纳秒级 UTC，避免同一秒内多次 dry-run 覆盖同一个 DAG/artifact 目录。
- [x] 2026-06-26：补 hover / navigation / scan-robustness 第一版 task-specific static doctor；没有专属 doctor 的 task 继续显式 `not_applicable`。
- [x] 2026-06-26：补 live common-doctor artifact：live run 后写 `dag/common_doctor_live_summary.json`，从 runtime-execute 的 probe results、service handles、rosbag handles、runtime error 推导 topic freshness 和 blocker。

任务：

- [x] 增加 sim preflight：Docker daemon、用户权限、必要 images、image tag、host 命令、artifact root、task YAML、simulation profile、forbidden config、端口/网络、runtime mode。第一版静态 prepare 对 daemon/user/端口网络记录 `deferred_to_runtime`，不在 dry-run 里做 live probe。
- [x] 增加 sim prepare summary：记录 `prepare_claim`、`service_plan`、`probe_plan`、`rosbag_plan`、`resource_provenance`、`forbidden_input_audit`、`artifact_dir`、`container_log_dir`。
- [x] 增加 sim prepare runtime artifacts：artifact layout、runtime plan、runtime scripts、task request、SLAM config、Gazebo overlay、rosbag profile、Foxglove/review 配置。
- [x] 增加 sim prepare service-plan：SITL / MAVLink routing、sim companion / ExternalNav bridge、gazebo sensor / X2 emulator、Cartographer SLAM、sim rangefinder emulator / bridge。
- [x] 增加 sim prepare resource provenance：Docker daemon、Docker network、image ref/tag、workspace mount、container path、simulation source claim。
- [x] 增加 sim prepare forbidden-input audit：Gazebo truth、official overlay、seed map、diagnostic odometry 不能进入 SLAM / ExternalNav / controller / gate input。
- [x] 增加 sim common-doctor：runtime mode、source claims、no Gazebo truth input、official overlay review-only、`/scan`、`/tf`、`/tf_static`、`/slam/odom`、ExternalNav、MAVLink ExternalNav、FCU status、rosbag profile、artifact layout、runtime events、frame contract。prepare/static doctor 记录计划，live common-doctor 从 runtime-execute evidence 写 freshness artifact。
- [x] 增加 default task-doctor：task config、duration/deadline、simulation profile、artifact paths、runtime plan、required helpers。
- [x] 对没有 task-specific doctor 的 task 写 `not_applicable` artifact。
- [x] 后续再补 hover / navigation / scan-robustness 的 task-specific doctor。第一版为 static doctor：hover 检查 mainline profile、altitude/span/health/ExternalNav/landing policy；navigation 检查 Nav2/costmap/goals/adapter/no-truth；scan-robustness 检查 disturbance profiles/helpers/stabilization/no forbidden map input。

验收：

- [x] sim dry-run 能看到 `preflight`、`prepare`、`common-doctor`、`task-doctor` 节点结果。
- [x] sim prepare 能像 real prepare 一样产出 service/probe/resource plan，而不是只生成散落文件。
- [x] sim prepare 写出 `prepare_summary` 和 `doctor_result`。
- [x] 没有 task-specific doctor 的 task 不再静默缺检查。
- [x] 第一版 `prepare` 不启动 Gazebo / SITL / SLAM / companion / rosbag / probes；这些 side effect 留给 runtime-execute。
- [x] 后续 live prepare 若启用，只允许准备 Docker network、确认 image，或预拉起不执行任务主体的基础 service。当前实现只做 Docker daemon/image/network probe，不预拉起基础 service。

## Phase WF1.x：Go sim Docker SDK resource probe

状态：完成。

目标：把 WF1 的 Docker live resource probe 直接替换为 Docker SDK；shell `docker` CLI 不再作为 preflight/prepare 的资源证据来源。

进展：

- [x] 2026-06-26：`run --dry-run --live-preflight` 已切到 Docker SDK resource probe，不再依赖宿主机 `docker` CLI binary。
- [x] 2026-06-26：preflight/prepare artifact 记录 SDK provenance：Docker host、server/API version、OS、root dir、rootless claim、remote context evidence。
- [x] 2026-06-26：static dry-run 仍不触碰 Docker daemon；live-preflight 只做 daemon/image/network inspect，不启动 container。
- [x] 2026-06-26：缺失 daemon/image/network 仍写 `dag/preflight_summary.json` blocker，不中断 artifact 生成。

边界：

- 只替换 preflight / prepare resource evidence 采集。
- 不启动 Gazebo / SITL / SLAM / companion / rosbag / probes。
- 不在这一 phase 重写 `DockerBackend.StartService` / `RunProbe` / `StartRosbag`。
- 不保留 Docker CLI live resource probe fallback；runtime-execute 的 CLI backend 是 `WF-runtime` 的删除/断开目标。

任务：

- [x] 引入 Docker SDK client wrapper，封装 daemon ping / version / info。
- [x] 用 SDK 实现 image inspect：检查 runtime spec 中所有 image ref/tag 是否存在。
- [x] 用 SDK 实现 network inspect：检查非内置 Docker network 是否存在。
- [x] 记录 Docker host/socket/rootless/remote context 相关 provenance。
- [x] 将 `run --dry-run --live-preflight` 的 Docker checks 切到 SDK adapter。
- [x] 为 SDK adapter 增加 fake client 单元测试，不依赖本机 Docker daemon。
- [x] 失败时继续写同一类 blocker/reason-code 到 `preflight_summary.json`，但证据来源只来自 SDK probe。

验收：

- [x] `--dry-run --live-preflight` 不再依赖宿主机 `docker` CLI binary。
- [x] 缺失 daemon / image / network 时仍能写出 `dag/preflight_summary.json` 和 blocker。
- [x] static dry-run 仍不触碰 Docker daemon。
- [x] Docker SDK probe 不启动任何 container。

## Phase WF-runtime：Go sim Docker SDK runtime backend

状态：完成。

目标：直接 break 掉 Docker CLI runtime backend，在现有 `runtime.Backend` interface 后面实现 Docker SDK runtime backend，并把 rosbag graceful stop / finalize 作为 SDK runtime 生命周期的一部分。完成后 SDK backend 是唯一生产 runtime backend。

边界：

- 不改变 task plan、runtime spec、DAG artifact schema。
- 不把 SDK 类型泄漏到 `tasks` / `helpers` / config schema。
- 不保留 Docker CLI runtime fallback；CLI resource probe 已在 WF1.x 被 SDK probe 替代，runtime-execute 也应由 SDK backend 直接接管。
- 不做“先补 CLI 版本再迁 SDK”的过渡实现；涉及 container lifecycle 的新能力只落到 SDK backend。
- 允许保留纯 fake backend 测试，不保留 shell `docker` backend 作为运行路径。

任务：

- [x] 定义 Docker SDK backend 的 constructor 和 client interface。
- [x] 用 SDK 实现 service container create/start/stop/logs/wait。
- [x] 用 SDK 实现 rosbag container start/graceful-stop/finalize/wait/logs。
- [x] 用 SDK 实现 probe container run/timeout/log capture。
- [x] 保持 volume/network/env/user/cwd/entry command 与 runtime spec 语义一致；旧 CLI backend 只作为读代码时的行为参考，不作为兼容目标。
- [x] 增加 backend contract tests：同一 `ServiceSpec` / `RosbagSpec` / `ProbeSpec` 生成预期 Docker SDK container config / host config。
- [x] 增加 runtime runner fake backend 测试，验证 timeout、cleanup、stop errors、required probe failure 语义不变。
- [x] 删除或断开 Docker CLI runtime backend 的生产入口，避免新旧 backend 分叉。

验收：

- [x] SDK backend 能跑通至少一个 probe smoke path。2026-06-27 live hover run 启动并完成 4 个 SDK probe container。
- [x] SDK backend 能跑通 `go run ./cmd/navlab-sim run hover`。验证 run：`artifacts/sim/hover/20260627T005913.764530118Z`，`TASK_STATUS_OK`。
- [x] SDK backend 写出的 summary/runtime events/manifest 继续满足现有 artifact schema。
- [x] 切换 backend 不改变 no-cheat boundary 和 DAG workflow artifact。

## Phase WF-runtime.rosbag-sdk：Go sim SDK rosbag graceful stop / finalize

状态：第一版完成；后续只剩 blocker reason-code taxonomy 细化。

背景：

- 2026-06-26 的 sim hover live run 暴露了 rosbag 收尾问题：任务本体和 live common-doctor 可以成功，但 `ros2 bag record -s mcap` 在 `timeout --signal=INT` + Docker cleanup 的组合下可能只留下 `hover_rosbag_0.mcap`，缺少 `metadata.yaml`。
- 现有 gate 已补 MCAP fallback：metadata 缺失时可 streaming 读取 MCAP required topic counts，且能容忍 footer/index 不完整但消息本体可读的情况。
- 这个 fallback 是 gate 的证据恢复路径，不是 runtime 生命周期的根治。更彻底的修法应该让 rosbag recorder 有明确 stop/finalize 阶段，尽量稳定产出 `metadata.yaml`、完整 MCAP footer/index 和可审计 finalize evidence。

目标：在 Docker SDK runtime backend 中，把 rosbag 从“靠 `timeout --signal=INT` 自然退出”升级为 runtime-owned lifecycle：

```text
start rosbag
  -> task/probes terminal
  -> post-task grace
  -> request graceful stop
  -> wait finalize
  -> verify metadata or readable MCAP counts
  -> capture finalize summary/logs
  -> cleanup
```

边界：

- 不改变 task plan / rosbag profile / required topic 语义。
- 不放宽 required topic gate；MCAP fallback 只能替代 metadata 作为证据来源，不能隐藏 topic 缺失。
- 不实现 CLI backend 版本；rosbag graceful stop / finalize 直接作为 SDK backend 的一部分落地。
- 不把 host `ros2` / `mcap` CLI 作为必需依赖；优先使用 container 内 recorder 和 Go MCAP reader。
- 不把 raw MCAP 内容搬进 SQLite 或 summary，只记录 counts、paths、finalize 状态和 blocker。

任务：

- [x] 为 `RuntimeHandle` 或 rosbag handle 增加 recorder lifecycle evidence：started、stop_requested、stop_signal、wait_exit_code、finalize_ok、metadata_path、mcap_paths、message_counts_source。
- [x] 把 `timeout --signal=INT <duration> ros2 bag record ...` 改为更明确的 wrapper：启动 recorder 后由 runtime runner 在 task terminal/post-task grace 后发送 graceful stop。
- [x] 为 Docker SDK backend 增加 rosbag-specific graceful stop：通过 SDK stop container with timeout 发送 SIGINT，并记录实际 signal/exit code。
- [x] 增加 finalize wait：停止 recorder 后等待 `metadata.yaml` 或 `.mcap/.mcap.zstd` 出现；required topic counts 仍由 gate evaluation 使用 metadata 或 Go MCAP reader 验证。
- [ ] 区分三类 blocker：
  - `rosbag_finalize_timeout`
  - `rosbag_metadata_missing_mcap_counts_ok`
  - `rosbag_required_topics_missing`
- [x] 在 `summary.json` / `gate_evaluation.rosbag_profiles[]` 中记录 finalize evidence，而不是只记录 metadata path。
- [x] 在 `dag/common_doctor_live_summary.json` 中把 rosbag live evidence 从 `rosbag_handles=1` 扩展为 finalize status。
- [x] 增加 fake backend 单元测试：
  - task 成功后 rosbag 收到 graceful stop。
  - metadata 正常写出 -> gate ok。
  - metadata 缺失但 MCAP readable 且 required topics present -> gate ok with fallback/source evidence。
  - MCAP readable 但 required topic missing -> gate blocked。
  - recorder stop/finalize timeout -> runtime blocked with explicit error。
- [x] 跑一次 SDK backend 的 `go run ./cmd/navlab-sim run hover`，确认 `TASK_STATUS_OK` 且 rosbag profile 使用 metadata 或 MCAP fallback 均有明确 evidence。

验收：

- [x] rosbag 停止不再只依赖 `timeout --signal=INT`。
- [x] 成功 hover run 的 rosbag summary 能说明 recorder 如何停止、是否完成 finalize、证据来自 metadata 还是 MCAP。
- [x] metadata 缺失时不再误判为 rosbag missing；required topic 缺失仍 fail closed。
- [x] live common-doctor 能看到 rosbag finalize status。
- [x] Docker SDK backend 是唯一生产 runtime backend；不保留 Docker CLI runtime fallback。

## Phase WF2：Rust real 用 motor-debug 做最小 workflow DAG

状态：完成。

目标：不是做 real hover，而是让 `motor-debug` 成为第一个完整 real task pipeline 样板。

进展：

- [x] 2026-06-26：`navlab-real run motor-debug` 已写 run-level `workflow_summary.json`，summary 内也带 `workflow.nodes`。
- [x] 2026-06-26：dry-run 已写 `task_request.json`、`task_plan.json`、`workflow_summary.json`、`summary.json`、`task_result.json`。
- [x] 2026-06-26：`--with-doctor-chain` 默认把 doctor-chain artifact 写到 run artifact dir；显式 `--doctor-artifact-dir` 仍可覆盖。
- [x] 2026-06-26：doctor-chain blocked 不再由 CLI 提前退出；motor-debug 会写 blocked run summary 后 fail closed。
- [x] 2026-06-26：operator safety blocked 也写可读 summary/task_result/workflow artifact，不只返回 CLI error。

任务：

- [x] 把 `preflight -> prepare -> common-doctor -> task-doctor -> run` 作为 real workflow DAG 显式记录。
- [x] `motor-debug` 挂接 upstream doctor artifact，不绕过 doctor-chain。
- [x] 为 `motor-debug` summary 增加 workflow node results。
- [x] blocked run 也写可读 summary，不只返回 CLI error。

验收：

- [x] dry-run 产出 request、plan、node results、summary。
- [x] blocked run 能定位到具体 blocked node 或 runtime state。
- [x] `motor-debug` 成为 real orchestration shape 的样板，而不是特殊任务。

## Phase WF3：给 motor-debug 增加显式 FSM

状态：完成。

目标：`motor-debug` 不再只是顺序执行 arm / spin / disarm，而是有可记录、可审计、可 fail-closed 的 FSM。主状态保持粗粒度，request / ACK / confirm 细节作为 transition evidence。

建议 FSM：

```text
runtime_ready
  -> guided
  -> armed
  -> motor_spin_hold
  -> disarmed
  -> completed
```

模板表达：

```text
runtime_ready
  -> guided
  -> arm
  -> task_body(motor_spin_hold)
  -> disarm
  -> completed
```

任务：

- [x] 在 Rust real `motor-debug` task 里记录 FSM transition。
- [x] 每个状态写 `state`、`entered_at`、`reason`、`evidence`。
- [x] guided / arm / disarm 的 request、ACK、heartbeat、mode、armed/disarmed evidence 绑定到对应 transition，不作为主状态。
- [x] 失败时写明确 blocker，不返回 generic error。

验收：

- [x] dry-run summary 能看到 planned FSM。
- [x] live summary 能看到 actual FSM transitions。
- [x] 任一 MAVLink step 失败时，summary 能定位到具体 failed state。

## Phase WF4：抽 common，但只抽纯逻辑

状态：完成第一版。

目标：让 sim hover、real motor-debug、未来 real hover 共享任务语义，不共享危险 side effect。

进展：

- [x] 2026-06-26：Python `navlab.common.companion.mission.fsm` 增加纯 task FSM summary/transition recorder，字段与 Rust real `fsm` artifact 对齐。
- [x] 2026-06-26：Rust real 把 `motor-debug` 的通用 FSM schema/transition 类型抽到 `workflows::fsm`，`motor_debug` 只保留任务特定状态推导。
- [x] 2026-06-26：Python `navlab.common.companion.mission.policy` 增加纯 operator confirmation、deadline、target/hard-cap、gate status、reason-code helper。
- [x] 2026-06-26：第一版不引入跨语言 runtime import；Rust real 和 Python sim/common 通过同一 JSON schema 对齐，后续再决定是否提升到 proto/generated common。

任务：

- [x] 梳理 `navlab.common.companion.mission` 中可复用 FSM / evidence / summary / reason-code。
- [x] 抽象 task FSM recorder，不绑定 hover。
- [x] 抽象 operator confirmation、deadline、target/hard-cap policy、gate status、reason-code。
- [x] 保持真实串口 / FCU / lidar / rangefinder 代码在 `navlab.real.*`。
- [x] 保持 Gazebo / SITL / sim sensor 代码在 `navlab.sim.*`。

验收：

- [x] `navlab.common` 里没有 Gazebo、SITL、真实串口 side effect。
- [x] sim wrapper 和 real wrapper 通过 common schema / language-local pure recorder 共享 FSM/evidence 语义，而不是互相 import。

## Phase WF5：基于闭环再设计 real hover

状态：完成第一版（dry-run design / live fail-closed），WF5B runtime FSM behind tests 已完成。

目标：等 `motor-debug` 最小闭环跑顺后，再把同一套 real task pipeline 扩展到 real hover。

进展：

- [x] 2026-06-26：Rust real registry 新增 `hover` task，`navlab-real run hover --dry-run` 产出 `task_request.json`、`task_plan.json`、`workflow_summary.json`、`summary.json`、`task_result.json`。
- [x] 2026-06-26：real hover dry-run summary 复用 WF2/WF3 的 workflow + task FSM artifact shape，FSM 为 `runtime_ready -> guided -> armed -> takeoff -> hover_health_hold -> hover_hold -> landing -> disarmed -> completed`。
- [x] 2026-06-26：real hover live path 当前明确 fail-closed，写 `real_hover_live_task_not_enabled` summary 后退出，不 arm、不 takeoff。
- [x] 2026-06-26：completion definition 固定为 `mavlink_external_nav_and_fcu_local_position` primary，official DDS pose 只作为 secondary/crosscheck，不作为唯一完成证据。
- [x] 2026-06-26：task-doctor 增加 hover evidence shape：SLAM odom、ExternalNav、MAVLink ExternalNav、rangefinder、FCU status。
- [x] 2026-06-26：real hover MAVLink runtime FSM 已在 Rust `runtime::mavlink` 中实现并由 fake MAVLink 单元测试覆盖；当前不接入 `run hover` live path。

任务：

- [x] 基于 `motor-debug` 的 workflow / FSM / artifact / gate 模板设计 real hover。
- [x] real hover 不直接运行或 import `navlab.sim.*`。
- [x] real hover 引入 hover-health stable window 和 operator confirmation。
- [x] real hover 补 SLAM / ExternalNav / landing / motor safety evidence plan。
- [x] 决定 real hover completion definition 是 MAVLink ExternalNav、官方 DDS，还是两者分层。

验收：

- [x] real hover 是已有 real task pipeline 的扩展，不是重新设计 orchestration。
- [x] real hover 没有新增 sim dependency。
- [x] real hover 的 completion definition 有明确 artifact 和 gate 证据。

后续 live runtime 子阶段：

- [x] WF5A：实现 operator safety final gate 和 props-installed / safe-area 语义，不复用 motor-debug 的 `no_props`。
  - [x] `navlab-real run hover` 缺少任一 final safety confirmation 时先写 `blocked_by_operator_safety`，不会进入 runtime。
  - [x] 新增 `--confirm-props-installed` 和 `NAVLAB_CONFIRM_PROPS_INSTALLED`；`--confirm-no-props` 继续只服务 motor-debug。
  - [x] real hover summary 记录 `props_policy=props_required_for_real_hover_no_no_props_shortcut`。
  - [x] 所有 hover safety confirmation 通过后，当前仍 fail-closed 到 `real_hover_live_task_not_enabled`。
- [x] WF5B：实现 real hover MAVLink runtime FSM：GUIDED、arm、takeoff、hover-health hold、hover hold、landing、disarm。
  - [x] 新增 `RealHoverRuntimeRequest` / `RealHoverRuntimeReport` 和 `run_real_hover_runtime` / `real_hover_runtime` runtime entrypoint。
  - [x] MAVLink runtime FSM 记录 `runtime_ready -> guided -> armed -> takeoff -> hover_health_hold -> hover_hold -> landing -> disarmed -> completed`。
  - [x] fake MAVLink 测试覆盖成功路径 command sequence：set guided、arm、takeoff、land、disarm。
  - [x] fake MAVLink 测试覆盖 takeoff ACK rejected：`failed_state=takeoff`，不继续 land/disarm。
  - [x] `run hover` live path 仍 fail-closed 到 `real_hover_live_task_not_enabled`，不调用 hover runtime。
- [ ] WF5C：接入真实 SLAM / ExternalNav / rangefinder / landing evidence 采集，生成 live `fsm` actual transitions。
- [ ] WF5D：增加 flight rosbag profile、landing summary、hover-health gate 和 cohort row。

## Phase WF-DAG：把 workflow summary 收敛成最小真实 DAG

状态：第一版完成（break 到新 DAG contract，不保留 root workflow / legacy node 字段兼容）。

背景：

- 当前 Go sim 已经在 `dag/` 下写出 preflight / prepare / common-doctor / task-doctor / workflow / doctor-result artifact，但 `runtime-execute` 和 `gate-evaluate` 还没有并入同一个 `workflow_summary.json` 主链。
- 当前 Rust real 已经能从 doctor-chain 和 task runtime 生成 `workflow_summary.json`，但 artifact 仍主要写在 run 根目录或 doctor-chain 目录，没有像 Go sim 一样统一放入 `dag/`。
- 两边现在都是“固定顺序 orchestration + node summary”，还不是按 `deps`、`required`、`skip_reason` 驱动的最小 DAG runner。

目标：不引入第三方 DAG 库，先用项目内最小 runner 和统一 artifact layout，把 sim/real 的 workflow 从“链式 summary”推进到可审计的 DAG contract。

进展：

- [x] 2026-06-27：Go sim / Rust real workflow node JSON 统一使用 `id/kind/deps/required/mode/domain/side_effect_policy/summary_path/artifact_paths` 和 `ok/blocked/skipped/skip_reason/blockers/warnings/artifacts/evidence/started_at/finished_at`；旧 `node_id/stage` artifact 字段已 break。
- [x] 2026-06-27：Go sim dry-run 和 Rust real dry-run 都写六节点 `dag/workflow_summary.json`：`preflight`、`prepare`、`common-doctor`、`task-doctor`、`runtime-execute`、`gate-evaluate`。
- [x] 2026-06-27：Go sim live path 会在 runtime 后重写 `dag/workflow_summary.json` / `dag/doctor_result.json`，把 `runtime-execute` 和 `gate-evaluate` 从 skipped node 覆盖为 live evidence node。
- [x] 2026-06-27：Rust real `motor-debug` / `real-hover` 直接写 `dag/workflow_summary.json`，不再写 root `workflow_summary.json` 兼容镜像。

边界：

- 不把 task runtime FSM、rosbag recorder FSM、MAVLink FSM 塞进 workflow DAG；它们仍属于 FSM phases。
- 不改变 sim/real evidence adapter 的边界：sim 采 Docker/SITL/Gazebo evidence，real 采 process/serial/FCU/operator safety evidence。
- 不要求本 phase 接入 `qmuntal/stateless` 或 `statig`；DAG runner 和 FSM adapter 分开推进。
- 不把 Gazebo/SITL 或真实硬件 side effect 放进 common/shared runner。

任务：

- [x] 统一 Go sim / Rust real 的 `WorkflowNode` 字段到 WF0 schema：`id/kind/deps/required/mode/domain/side_effect_policy/summary_path/artifact_paths`。
- [x] 统一 Go sim / Rust real 的 `NodeResult` 字段到 WF0 schema：`ok/blocked/skipped/skip_reason/blockers/warnings/artifacts/evidence/started_at/finished_at`。
- [x] 增加项目内最小 DAG runner 语义：拓扑排序、required dependency blocked 后跳过后续 required node、optional node 失败只转 warning。
- [x] 为 skipped node 显式写 `skip_reason=blocked_by_dependency:<node_id>`，不能只省略 node。
- [x] Go sim 把 `runtime-execute` 并入同一条 `dag/workflow_summary.json`，live run 后记录 runtime result、service/probe/rosbag handles、timeout/blocker。
- [x] Go sim 把 `gate-evaluate` 并入同一条 `dag/workflow_summary.json`，记录 gate ok/blocked、rosbag profile result、hover-health/cohort evidence reference。
- [x] Go sim dry-run / prepare 对 `runtime-execute` 和 `gate-evaluate` 写 planned/skipped node，而不是只缺失节点。
- [x] Rust real 新增 `dag/` artifact layout，并把 workflow 主 artifact 直接写到 `dag/workflow_summary.json`。
- [x] Rust real 的 `motor-debug` 和 `real-hover` run summary 直接 break 到 `dag/workflow_summary.json`；不再写 root `workflow_summary.json` 兼容镜像。
- [x] Rust real doctor-chain blocked / operator-safety blocked / runtime blocked 都写完整 DAG nodes，不因为提前 fail-closed 而缺 node。
- [x] Manifest 中给 DAG artifacts 使用稳定 artifact type：`workflow_summary`、`workflow_node_summary`、`doctor_result`。Go sim manifest 已使用稳定 DAG artifact type；Rust real 当前无 run manifest，DAG path 固定为 `dag/workflow_summary.json`。
- [x] 增加 Go/Rust schema snapshot 或 JSON fixture 测试，确保 sim/real node 字段同构。

验收：

- [x] Go sim live run 的 `dag/workflow_summary.json` 至少包含 `preflight`、`prepare`、`common-doctor`、`task-doctor`、`runtime-execute`、`gate-evaluate`。
- [x] Go sim dry-run 的 `dag/workflow_summary.json` 也显式包含未执行的 runtime/gate node，并带 `skipped` 或 planned evidence。
- [x] Rust real `motor-debug --dry-run` 和 blocked run 都写 `dag/workflow_summary.json`。
- [x] Rust real `real-hover --dry-run` 和 live fail-closed run 都写 `dag/workflow_summary.json`。
- [x] required dependency blocked 时，后续 required node 可定位到 blocking dependency。
- [x] sim/real 的 workflow node JSON 字段名和语义一致，差异只体现在 evidence adapter 内容。

## Phase FSM0：定义 navlab.fsm.v1 schema

状态：完成。

目标：把 sim / real / runtime sub-FSM 的对外 artifact contract 统一成 NavLab 自己的 schema，而不是暴露 Go/Rust 第三方 FSM 库内部类型。

边界：

- 不在 schema 中写入 `qmuntal/stateless` 或 `statig` 的内部状态结构。
- 不把 Docker/Gazebo/SITL 或真实硬件 side effect 放进 common schema。
- schema 只描述 FSM 名称、层级关系、当前状态、transition、guard、evidence、reason-code、blocker、artifact reference。

任务：

- [x] 新增 `docs/general/navlab_fsm_schema.md`。
- [x] 定义 `schema_version=navlab.fsm.v1`。
- [x] 定义 `fsm_name`、`parent_fsm`、`scope`、`task_id`、`run_id`、`state`。
- [x] 定义 `states` / `triggers` / `transitions` / `guards` / `evidence` / `reason_codes` / `blockers` 字段。
- [x] 定义 runtime sub-FSM 与 task FSM 的层级关系表达。
- [x] 定义失败态表达：`failed_state`、`failed_trigger`、`failure_reason_code`、`recoverable`。
- [x] 定义 graph/debug 输出是否 optional，例如 DOT graph 只作为 review artifact。

验收：

- [x] Go sim 和 Rust real 可以用同一份 JSON schema 表达 FSM artifact。
- [x] schema 能表达 task FSM、rosbag recorder FSM、MAVLink runtime FSM。
- [x] schema 不依赖任一第三方库的序列化格式。

## Phase FSM1：Go sim 引入 qmuntal/stateless，先包 rosbag_recorder FSM

状态：第一版完成。

目标：在 Go sim 侧引入 `qmuntal/stateless`，但通过 NavLab adapter 输出 `navlab.fsm.v1`，先把 rosbag recorder lifecycle 从普通 handle 字段升级为 runtime sub-FSM。

建议 FSM：

```text
idle
  -> starting
  -> recording
  -> post_task_grace
  -> stop_requested
  -> finalizing
  -> evidence_verified
  -> cleanup
  -> completed
```

失败态：

```text
start_failed
stop_failed
finalize_timeout
evidence_missing
required_topics_missing
cleanup_failed
```

任务：

- [x] 在 Go sim 新增 `internal/fsm` adapter，封装 `qmuntal/stateless`。
- [x] adapter 输出 `navlab.fsm.v1`，不暴露第三方库类型。
- [x] 为 rosbag recorder 定义 states / triggers / guards / transitions。
- [x] 把 `RuntimeHandle` 中已有 rosbag lifecycle evidence 映射成 FSM transitions。
- [x] 在 `summary.json` / `dag/common_doctor_live_summary.json` 中引用 rosbag recorder FSM artifact。
- [x] 为 metadata ready、MCAP readable、required topic missing、finalize timeout 增加 reason-code 统一映射。
- [x] 增加 DOT graph 或 transition table review artifact，作为 optional debug 输出。
- [x] 增加 fake backend / adapter 单元测试。

验收：

- [x] hover live run 的 rosbag recorder 有独立 FSM artifact。验证 run：`artifacts/sim/hover/20260627T025935.846660701Z/runtime/rosbag_hover_rosbag_fsm.json`。
- [x] rosbag finalize timeout / metadata missing / required topic missing 都能落到明确 failed state 和 reason-code。
- [x] 现有 `TASK_STATUS_OK` / blocked gate 语义不变。验证 run：`20260627T025935.846660701Z`，`status=ok`，summary 为 `TASK_STATUS_OK`。

## Phase FSM2：Go task/runtime FSM 逐步迁到 adapter

状态：完成第一版。

目标：把 Go sim 中已有 task/runtime FSM 记录逐步迁到同一 `internal/fsm` adapter，形成 task FSM + runtime sub-FSM 的统一 artifact 形状。

任务：

- [x] 盘点 Go sim 当前 hover / navigation / scan-robustness 的 mission/runtime state 输出。
- [x] 把 hover task body FSM 映射为 `navlab.fsm.v1`。粗粒度状态保持 `runtime_ready -> guided -> armed -> takeoff -> hover_health_hold -> hover_hold -> landing -> disarmed -> completed`，mission `S*` history 保留为 transition evidence。
- [x] 把 runtime services/probes/rosbag 的子 FSM 作为 parent task/runtime 的 sub-FSM 引用。第一版已接 rosbag recorder sub-FSM。
- [x] 保持 existing summary 字段兼容，新增 FSM artifact reference。
- [x] 为没有复杂 task FSM 的 task 生成显式 no-op/default FSM artifact。

验收：

- [x] Go sim 每个 task 至少有一个 task-level FSM artifact。
- [x] runtime sub-FSM 与 task FSM 的 parent/child 关系可追踪。
- [x] gate evaluation 能引用 FSM failed state / reason-code。验证 run：`artifacts/sim/hover/20260627T071510.747784322Z/summary.json` 中 `gate_evaluation.fsm_artifacts[]` 指向 task FSM 和 rosbag FSM。

## Phase FSM3：Rust real 引入 statig，先包 motor-debug FSM

状态：完成第一版。

目标：Rust real 侧引入 `statig` 作为 hierarchical state machine adapter，但输出仍保持 `navlab.fsm.v1`，先迁移 `motor-debug`。

边界：

- 不让 `statig` 内部类型进入 artifact schema。
- 不改变 `motor-debug` 的 operator safety / MAVLink evidence 语义。
- request / ACK / heartbeat / mode observation 仍作为 transition evidence，不升级为主状态。

任务：

- [x] 在 Rust real 新增 `workflows::fsm` adapter，封装 `statig`。
- [x] 定义 `navlab.fsm.v1` Rust 数据结构和 JSON writer。
- [x] 把 `motor-debug` FSM 迁到 adapter。第一版保留旧 `fsm` 内嵌字段，同时写独立 `runtime/task_motor_debug_fsm.json`。
- [x] 保留粗粒度状态：`runtime_ready -> guided -> armed -> motor_spin_hold -> disarmed -> completed`。
- [x] 将 ACK、heartbeat、mode、armed/disarmed evidence 挂到 transition evidence。
- [x] 增加 fake MAVLink / dry-run 测试，验证成功和 blocked summary。现有 fake MAVLink 覆盖旧 summary，新增 `workflows::fsm` 测试覆盖 `navlab.fsm.v1` 转换；dry-run 和 operator safety blocked CLI 已验证 artifact 写出。

验收：

- [x] `navlab-real run motor-debug --dry-run` 写出 `navlab.fsm.v1` planned FSM。验证 artifact：`artifacts/real/motor-debug/20260627T071342Z/runtime/task_motor_debug_fsm.json`。
- [x] live/fake runtime 写出 actual FSM transitions。actual runtime path 会从 `MotorDebugRuntimeReport.fsm` 转写为 `navlab.fsm.v1`；本 phase 未启动真实硬件 runtime。
- [x] blocked run 能定位到 failed state、trigger、reason-code。验证 artifact：`artifacts/real/motor-debug/20260627T071848Z/runtime/task_motor_debug_fsm.json`。

## Phase FSM4：real hover runtime FSM 迁到 statig adapter

状态：部分完成；live runtime 深迁移仍等待 WF5C/WF5D。

目标：把 Rust real hover MAVLink runtime FSM 迁到 `statig` adapter，让 real hover 与 motor-debug 使用同一套 `navlab.fsm.v1` artifact contract。

任务：

- [x] 把 real hover runtime states 映射到 `statig` hierarchical FSM。第一版通过 `workflows::fsm` adapter 从 planned/blocked `fsm` 转写 `navlab.fsm.v1`。
- [x] 保留状态：`runtime_ready -> guided -> armed -> takeoff -> hover_health_hold -> hover_hold -> landing -> disarmed -> completed`。
- [x] 把 hover-health stable window、landing evidence、ExternalNav evidence、FCU local position evidence 写入 transition evidence / guard evidence。planned artifact 已记录目标策略；live evidence 仍等待 WF5C/WF5D。
- [x] 将 operator safety blocked 与 runtime FSM blocked 分层表达。
- [ ] 增加 fake MAVLink 测试：成功路径、takeoff rejected、hover-health timeout、landing failed。
- [x] 在 live path 真正启用前继续 fail-closed，除非 WF5C/WF5D evidence gate 满足。

验收：

- [x] real hover planned/blocked FSM 都是 `navlab.fsm.v1`。actual live FSM 等 WF5C/WF5D。
- [x] real hover blocked summary 能区分 safety gate blocked、runtime guard blocked、MAVLink command failed。当前已验证 operator safety blocked；MAVLink command failed 仍随 live runtime enable 推进。
- [x] real hover FSM 与 Go sim hover FSM 在 schema 和 reason-code 上可比。

## 依赖关系

- [x] WF0 必须先于 WF1 / WF2 / WF3。
- [x] WF1 应先于“把 sim hover 作为 real 迁移样板”的后续工作。
- [x] WF1.x 可以在 WF2/WF3 前后独立推进，但只能替换 Docker resource evidence adapter。
- [x] WF-runtime 依赖 WF1.x 的 SDK client wrapper 稳定，但不阻塞 WF2/WF3。
- [x] WF-runtime.rosbag-sdk 与 WF-runtime 合并推进；不在 CLI backend 上补 graceful stop/finalize，也不保留 CLI fallback，直接以 SDK backend 作为唯一生产实现。
- [x] WF2 / WF3 应先于任何 real hover live task。
- [ ] WF4 可以和 WF2 / WF3 并行推进，但 common 只能收纯逻辑。
- [ ] WF5 依赖 WF2 / WF3 稳定，以及 WF4 中相关 common 语义可用。
- [x] WF-DAG 依赖 WF0 / WF1 / WF2；Go sim runtime/gate 节点依赖 WF-runtime 和 WF-runtime.rosbag-sdk 第一版完成。
- [x] WF-DAG 应先于把 workflow schema 上升到 `contracts/proto`，否则 proto 会固化当前链式字段缺口。
- [x] FSM0 必须先于 FSM1 / FSM2 / FSM3 / FSM4。
- [x] FSM1 依赖 WF-runtime.rosbag-sdk 第一版完成。
- [x] FSM2 依赖 FSM1 的 Go adapter 稳定。
- [x] FSM3 依赖 FSM0 和 WF3。
- [ ] FSM4 依赖 FSM3 和 WF5B；真正接入 real hover live path 仍依赖 WF5C/WF5D。

## 完成标准

- [x] Go sim 和 Rust real 都暴露同构 orchestration stage。
- [x] Go sim 和 Rust real 都把 workflow DAG 主 artifact 写入 `dag/workflow_summary.json`。
- [x] `runtime-execute` 和 `gate-evaluate` 在 Go sim workflow summary 中有明确 node result。
- [x] Real `motor-debug` 写出 workflow、FSM、summary artifact。
- [ ] `navlab.common` 只包含纯 FSM / evidence / summary / reason-code 语义。
- [x] real hover 不再是验证 orchestration 设计的第一个任务。
- [x] Go sim Docker SDK runtime 有明确 rosbag graceful stop / finalize evidence；`timeout --signal=INT` 和 Docker CLI backend 不再是生产收尾语义。
- [x] Go sim 和 Rust real 都通过 `navlab.fsm.v1` 输出 task FSM / runtime sub-FSM artifact。
- [x] Go `qmuntal/stateless` 和 Rust `statig` 只存在于 language-local adapter 内，不泄漏到 artifact schema。
