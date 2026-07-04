# Hover Mission Pipeline 重构设计与 TODO

## 背景

`navlab/sim/companion/nodes/hover_mission.py` 当前同时承担：

- ROS node / CLI 入口。
- MAVLink 基础命令、ACK、消息读取。
- runtime readiness、GUIDED、arm、takeoff。
- hover body 决策、hold setpoint、hover evidence。
- landing policy、descent、touchdown、disarm、landing summary。
- mission FSM、status payload、final summary。

这让 hover 看起来像所有 flight task 的 base，但实际依赖方向并不健康：`hover_mission.py` 现在从 `obstacle_mission.py` import `command_takeoff`、`command_arm`、`set_mode` 等通用 MAVLink 函数。具体任务节点之间互相 import 通用飞控 primitive，会让后续 navigation、exploration、scan robustness 的复用边界越来越乱。

用户期望的方向更接近 PyTorch `Sequential`：把任务拆成可组合 stage，用一个统一上下文串起来。

目标不是让其他任务 OOP 继承 hover，而是让 hover 成为最小 flight pipeline 模板：

```text
common prefix: runtime_ready -> guided -> arm -> takeoff
task body:     hover / exploration / navigation / scan_robustness
common suffix: landing -> summary
```

## 设计结论

推荐方案是：

```text
Functional Core
  + Stage Pipeline
  + MissionContext
  + explicit FSM
  + Imperative Shell
```

不要采用这些方案作为主设计：

| 方案 | 判断 | 原因 |
|---|---|---|
| 其他任务继承 `HoverMission` | 不推荐 | hover 是具体任务，会把 hover drift、hover evidence、hover summary 泄漏到 exploration/navigation |
| 纯 `Sequential` | 不够 | 无法清晰表达 wait、retry、timeout、abort、landing fallback |
| 纯 FSM | 过重 | 安全性好，但复用性差，容易回到一个巨大状态机文件 |
| Behavior Tree | 暂不需要 | 对当前 flight lifecycle 过重，后续复杂 navigation 可再评估 |
| companion 内部 DAG engine | 不推荐 | 飞控 loop 需要可预测、低复杂度；DAG 更适合 orchestration 层 |

最终采用“带状态返回的 Sequential”：

```python
pipeline = FlightPipeline([
    RuntimeReadyStage(),
    GuidedModeStage(),
    ArmStage(),
    TakeoffStage(),
    HoverHoldStage(),
    LandingStage(),
    SummaryStage(),
])

result = pipeline.tick(ctx)
```

每个 stage 不直接返回一个裸 bool，而是返回结构化结果：

```python
StageResult(
    status="running",          # running / complete / blocked / abort
    reason="waiting_for_slam",
    fsm_state="S1 wait_nav_ready",
    evidence={"external_nav_ready": False},
)
```

## 核心抽象

### MissionContext

`MissionContext` 是 stage 之间共享的运行状态。它类似 `nn.Sequential` 中在 layer 间流动的 tensor，但这里流动的是飞行任务状态。

建议结构：

```python
@dataclass
class MissionContext:
    config: MissionConfig
    clock: MissionClock
    state: MissionState
    evidence: MissionEvidence
    fsm: MissionPhaseRecorder
    io: MissionIO
```

`MissionState` 继续分层，避免 `ctx` 变成新的垃圾桶：

```python
@dataclass
class MissionState:
    fcu: FcuState
    nav: NavState
    pose: PoseState
    command: CommandState
    hover: HoverState
    landing: LandingState
```

边界原则：

- 纯逻辑函数不要吃整个 `ctx`，只吃小 dataclass。
- stage 可以读写 `ctx`。
- ROS / MAVLink node 负责把外部消息更新到 `ctx.state`。
- summary 从 `ctx.state` 和 `ctx.evidence` 生成。
- `ctx.io` 只放 shell 层能力，例如 publisher、MAVLink connection、logger；纯函数不得依赖它。

### Stage

每个 stage 只表达一个生命周期阶段：

```python
class Stage(Protocol):
    name: str

    def tick(self, ctx: MissionContext) -> StageResult:
        ...
```

stage 约束：

- `tick()` 必须幂等到足以被 timer loop 重复调用。
- `tick()` 不直接写 final summary。
- 需要发送命令时通过 `ctx.io` 或 command adapter，且必须记录 evidence。
- stage 只能推进自己的状态，不应偷偷重置其他阶段。
- stage 返回 `abort` 时，pipeline 必须进入 landing 或安全停止策略。

### StageResult

```python
@dataclass(frozen=True)
class StageResult:
    status: Literal["running", "complete", "blocked", "abort"]
    reason: str
    fsm_state: str | None = None
    evidence: dict[str, object] = field(default_factory=dict)
    blocker: str | None = None
```

语义：

- `running`: 当前 stage 还在等待或持续执行。
- `complete`: 当前 stage 完成，pipeline 可进入下一个 stage。
- `blocked`: 当前 stage 暂时无法推进，但还未触发 abort，例如等待 ExternalNav。
- `abort`: 当前任务主体失败，pipeline 应进入 safety path。

### FlightPipeline

`FlightPipeline` 负责顺序推进 stage，并统一写 FSM：

```python
class FlightPipeline:
    def tick(self, ctx: MissionContext) -> StageResult:
        stage = self.current_stage()
        result = stage.tick(ctx)
        ctx.fsm.transition(result.fsm_state, result.reason, blocker=result.blocker)
        if result.status == "complete":
            self.advance()
        elif result.status == "abort":
            self.enter_safety_path()
        return result
```

pipeline 负责：

- 当前 stage index。
- stage transition。
- abort 后进入 landing / stop / disarm 策略。
- FSM transition 的统一入口。
- phase counts / stage durations。

pipeline 不负责：

- 解析 MAVLink 消息。
- 直接发布 ROS topic。
- 拼 final summary 细节。

## 目标组合方式

公共前缀：

```python
COMMON_FLIGHT_PREFIX = [
    RuntimeReadyStage(),
    GuidedModeStage(),
    ArmStage(),
    TakeoffStage(),
]
```

公共后缀：

```python
COMMON_FLIGHT_SUFFIX = [
    LandingStage(),
    SummaryStage(),
]
```

任务组合：

```python
HOVER_PIPELINE = [
    *COMMON_FLIGHT_PREFIX,
    HoverHoldStage(),
    *COMMON_FLIGHT_SUFFIX,
]

EXPLORATION_PIPELINE = [
    *COMMON_FLIGHT_PREFIX,
    ExplorationStage(),
    ReturnHomeStage(),
    *COMMON_FLIGHT_SUFFIX,
]

NAVIGATION_PIPELINE = [
    *COMMON_FLIGHT_PREFIX,
    Nav2GoalStage(),
    *COMMON_FLIGHT_SUFFIX,
]

SCAN_ROBUSTNESS_PIPELINE = [
    *COMMON_FLIGHT_PREFIX,
    HoverHoldStage(),
    DisturbanceSweepStage(),
    *COMMON_FLIGHT_SUFFIX,
]
```

这样 hover 不是父类，但 hover 的结构成为最小 flight task 标准。

## 目标目录

建议目标结构：

```text
navlab/sim/companion/mission/
  __init__.py
  context.py
  pipeline.py
  fsm.py
  mavlink_commands.py
  stages/
    __init__.py
    runtime_ready.py
    guided.py
    arm.py
    takeoff.py
    hover.py
    landing.py
    summary.py
  evidence/
    __init__.py
    hover.py
    landing.py
    summary.py

navlab/sim/companion/nodes/hover_mission.py
```

模块职责：

| 模块 | 职责 |
|---|---|
| `mission/context.py` | `MissionContext`、state dataclass、config dataclass |
| `mission/pipeline.py` | `Stage`、`StageResult`、`FlightPipeline` |
| `mission/fsm.py` | FSM state mapping、`MissionPhaseRecorder` |
| `mission/mavlink_commands.py` | 通用 MAVLink command、ACK、param read |
| `mission/stages/runtime_ready.py` | readiness fresh、preflight timeout、loss grace |
| `mission/stages/guided.py` | GUIDED mode request / confirmation |
| `mission/stages/arm.py` | arm request / confirmation |
| `mission/stages/takeoff.py` | takeoff request、高度确认、ACK fallback |
| `mission/stages/hover.py` | hover body decision、hold setpoint intent、hover completion |
| `mission/stages/landing.py` | landing policy、descent、touchdown、disarm |
| `mission/stages/summary.py` | final result stage |
| `mission/evidence/*` | hover / landing / summary evidence 纯函数 |
| `nodes/hover_mission.py` | CLI、ROS node wiring、MAVLink drain、pipeline 调度 |

## 不做什么

- 不把 navigation / exploration / scan robustness 改成继承 hover class。
- 不在第一阶段改 hover 阈值或放宽 readiness。
- 保留 `navlab.sim.companion.nodes.hover_mission.run` 作为 runtime entrypoint；不再保留 hover 对 obstacle/demo CLI 参数的兼容接收。
- 不为了拆文件删除 summary 字段、FSM 字段或 landing status 字段。
- 不把 Gazebo truth 作为控制输入。
- 不把 `MissionContext` 做成无限制全局字典。

## P0：冻结行为和建立迁移清单

目标：先把当前大文件按目标抽象归类，冻结回归边界。

### 任务

- [x] 列出 `hover_mission.py` 当前由测试直接 import 的函数和类。
- [x] 把这些函数归类到 `context`、`pipeline`、`fsm`、`mavlink_commands`、`stages`、`evidence`。
- [x] 保留 `hover_mission.py` 的 `run()` runtime entrypoint。
- [x] 固化 runtime template 仍 import `hover_mission.run`。
- [x] 记录明显机械清理项，例如重复 `return "pending"`，但不混入架构第一刀。

### P0 inventory

当前 `navlab/tests/companion/test_hover_mission.py` 直接从 `hover_mission.py` import 的符号分组如下。

目标 `mission/fsm.py`：

- `MissionPhaseRecorder`
- `mission_phase_state_for_hover_phase`
- `mission_phase_state_for_landing_state`

目标 `mission/mavlink_commands.py`：

- `_command_disarm`
- `_command_land`
- `_request_param_read`
- `append_bounded_command_ack`
- `command_ack_accepted`
- `command_ack_success`
- `mavlink_param_id_to_str`

目标 `mission/evidence/hover.py` 或 `mission/stages/hover.py`：

- `HoverInputs`
- `HoverRequirements`
- `capture_hold_anchor`
- `classify_hover_drift`
- `decide_hover`
- `height_reaches_target`
- `hold_axis_or_current`
- `hold_yaw_or_current`
- `hover_hold_setpoint_axes`
- `independent_takeoff_height_reached`
- `should_fail_fast_wait_ready`
- `should_send_position_hold_setpoint`
- `summarize_hover_altitude_crosscheck`
- `summarize_hover_drift`

目标 `mission/evidence/landing.py` 或 `mission/stages/landing.py`：

- `append_bounded_statustext`
- `fcu_land_params_report`
- `landing_acceptance_ok`
- `landing_controller_for_state`
- `landing_descent_evidence_height_and_source_m`
- `landing_descent_evidence_height_m`
- `landing_descent_height_m`
- `landing_descent_profile_enforced`
- `landing_descent_target_z_ned`
- `landing_effective_descent_rate_mps`
- `landing_policy_uses_ap_land_mode`
- `landing_touchdown_candidate`
- `should_command_land_this_tick`
- `should_send_disarm_after_touchdown`
- `should_use_guided_descent_before_land`
- `statustext_indicates_crash`
- `summarize_landing_descent_profile`

Runtime 入口：

- `navlab.sim.companion.nodes.hover_mission.run` 仍被 `navlab/sim/companion/runtime/hover_acceptance.py` 和 Go runtime template 生成脚本使用。
- 测试 helper facade 已在 P7.6 删除；`hover_mission.py` 不再承诺 re-export mission helper。

### P0 decisions

Decision: Phase1 先新增 `mission/context.py` 和 `mission/pipeline.py`，不迁移任何 hover 行为。

Basis: codebase research.

Reason: 先建立 `MissionContext` / `StageResult` / `FlightPipeline` 骨架，可以避免后续只是把 `hover_mission.py` 机械拆成多个无结构函数文件。

Decision: Phase1 pipeline 测试不得依赖 ROS2 或 pymavlink。

Basis: codebase research.

Reason: 当前 `hover_mission.py` 的 runtime 依赖重，pipeline 抽象应先作为 pure Python core 可测，后续 shell 再接 ROS / MAVLink。

### 验收

- [x] `just check-python` 通过。
- [x] `rg "from navlab.sim.companion.nodes.hover_mission import run"` 的入口仍存在。
- [x] 文档中能看到每个待迁移符号的目标模块。

## P1：建立 `MissionContext` / `StageResult` / `FlightPipeline` 骨架

目标：先把设计模式落成最小骨架，再迁移具体业务逻辑。

### 任务

- [x] 新增 `mission/context.py`。
- [x] 新增 `mission/pipeline.py`。
- [x] 定义 `StageResult.status` 枚举语义。
- [x] 定义 `MissionContext` 的最小字段，不一次性塞满所有状态。
- [x] 增加 pipeline 单测，覆盖 `running`、`complete`、`abort -> safety path`。

### 验收

- [x] pipeline 单测不依赖 ROS2 / pymavlink。
- [x] `FlightPipeline` 可以顺序推进 dummy stages。
- [x] abort path 不会跳过 landing policy 的位置预留。

## P2：抽 FSM 模块并接入 pipeline

目标：让 FSM transition 由 pipeline 统一记录，而不是散落在每个具体函数里。

### 候选迁移

- [x] `HOVER_PHASE_TO_MISSION_PHASE_STATE`
- [x] `LANDING_STATE_TO_MISSION_PHASE_STATE`
- [x] `mission_phase_state_for_hover_phase`
- [x] `mission_phase_state_for_landing_state`
- [x] `MissionPhaseRecorder`

### 目标文件

- `navlab/sim/companion/mission/fsm.py`

### 历史迁移策略

- [x] Phase 迁移初期 `hover_mission.py` 曾 re-export 原 helper 名字。
- [x] 现有测试可以先不改 import 路径；P7.6 已迁到直接 import `mission.*`。

### P2 decisions

Decision: `FlightPipeline` 在 `ctx.fsm` 存在且 `StageResult.fsm_state` 非空时统一调用 recorder transition。

Basis: codebase research.

Reason: 这样后续 stage 不需要各自散落写 FSM；迁移初期保留 `hover_mission.py` helper re-export 以降低风险，P7.6 已删除测试 helper facade。

### 验收

- [x] FSM 相关测试通过。
- [x] `mission_phase_*` summary 字段不变。
- [x] pipeline 能通过 `StageResult.fsm_state` 记录 transition。

## P3：抽 MAVLink command 模块，修正依赖方向

目标：通用 MAVLink primitive 不再属于任何具体 mission node。

### 候选迁移

从 `obstacle_mission.py` 迁出：

- [x] `mode_number`
- [x] `send_gcs_heartbeat`
- [x] `send_local_position_yaw_setpoint`
- [x] `set_arming_check`
- [x] `set_ekf_origin`
- [x] `set_home_position`
- [x] `set_mode`
- [x] `command_arm`
- [x] `command_takeoff`

从 `hover_mission.py` 迁出或合并：

- [x] `_command_disarm`
- [x] `_command_land`
- [x] `_request_param_read`
- [x] `command_ack_success`
- [x] `command_ack_accepted`
- [x] `command_ack_rejected`
- [x] `append_bounded_command_ack`
- [x] `mavlink_param_id_to_str`

### 目标文件

- `navlab/sim/companion/mission/mavlink_commands.py`

### P3 decisions

Decision: move `DEFAULT_ORIGIN_*` and `LOCAL_POSITION_YAW_TYPE_MASK` with the command helpers.

Basis: codebase research.

Reason: `hover_mission.py` used those constants only because they lived in `obstacle_mission.py`; moving them removes the remaining concrete-node dependency while keeping `obstacle_mission.py` compatibility imports.

### 验收

- [x] hover and obstacle mission tests pass。
- [x] `hover_mission.py` 不再从 `obstacle_mission.py` import command primitive。
- [x] concrete mission node 之间不再互相 import 通用 MAVLink command。

## P4：抽 landing stage 和 landing evidence

目标：把最复杂、最应该跨任务复用的 landing 从 hover body 中独立出来。

### 候选迁移

- [x] landing policy 常量。
- [x] `landing_policy_uses_ap_land_mode`
- [x] `should_use_guided_descent_before_land`
- [x] `should_command_land_this_tick`
- [x] `should_send_disarm_after_touchdown`
- [x] `fcu_land_params_report`
- [x] `landing_controller_for_state`
- [x] `landing_descent_profile_enforced`
- [x] `landing_handoff_confirmed`
- [x] `landing_acceptance_ok`
- [x] `landing_descent_target_z_ned`
- [x] `landing_effective_descent_rate_mps`
- [x] `landing_descent_height_m`
- [x] `landing_descent_evidence_height_and_source_m`
- [x] `landing_descent_evidence_height_m`
- [x] `landing_touchdown_candidate`
- [x] `summarize_landing_descent_profile`

### 目标文件

- `mission/stages/landing.py`
- `mission/evidence/landing.py`

### 设计要求

- landing stage 读写 `ctx.state.landing`。
- landing evidence 纯函数不依赖 ROS / MAVLink。
- landing status schema 保持兼容。

### 验收

- [x] landing policy / touchdown / descent profile tests pass。
- [x] `/navlab/landing/status` schema 不变。
- [x] `mission_summary.json["landing"]` schema 不变。
- [x] no task acceptance relaxes landing requirements。

### P4 decisions

Decision: extract landing policy and evidence as pure helpers first, while leaving the runtime landing tick inside `hover_mission.py`.

Basis: codebase research and targeted tests.

Reason: the landing status and mission summary schemas are generated inside the current ROS node. Moving the pure helpers first makes them reusable without changing the execution path or relaxing landing acceptance. The future runner shrink can move the node state machine after P6/P7 stage scheduling is in place.

## P5：抽 hover body stage 和 hover evidence

目标：让 hover 成为一个普通 task body stage，而不是整个任务父类。

### 候选迁移

- [x] `HoverInputs`
- [x] `HoverRequirements`
- [x] `HoverDecision`
- [x] `HoverDriftSummary`
- [x] `decide_hover`
- [x] `should_fail_fast_wait_ready`
- [x] `summarize_hover_drift`
- [x] `summarize_hover_altitude_crosscheck`
- [x] `classify_hover_drift`
- [x] `height_reaches_target`
- [x] `independent_takeoff_height_reached`
- [x] `hold_axis_or_current`
- [x] `hover_hold_setpoint_axes`
- [x] `hold_yaw_or_current`
- [x] `capture_hold_anchor`
- [x] `should_send_position_hold_setpoint`

### 目标文件

- `mission/stages/hover.py`
- `mission/evidence/hover.py`

### 验收

- [x] hover decision tests pass。
- [x] hover drift and altitude crosscheck tests pass。
- [x] hover summary fields remain schema-compatible。

### P5 decisions

Decision: extract hover body decision and evidence helpers before introducing a concrete hover `Stage` class.

Basis: codebase research and targeted tests.

Reason: `hover_mission.py` still owns ROS IO, MAVLink drain, landing startup, and summary writing. Extracting `mission/stages/hover.py` and `mission/evidence/hover.py` first lets other tasks reuse the hover decision/evidence contract while preserving the current runtime schema.

## P6：抽 runtime ready / guided / arm / takeoff stages

目标：把公共 flight prefix 做成可复用 stage。

### 任务

- [x] `RuntimeReadyStage`: status freshness、preflight timeout、loss grace。
- [x] `GuidedModeStage`: mode request、mode confirmation。
- [x] `ArmStage`: arm request、armed confirmation。
- [x] `TakeoffStage`: takeoff command、ACK、高度确认、independent height fallback。

### 注意

takeoff 当前和 hover 高度确认强绑定。不要一开始把它抽成过度泛化的状态机；先抽 stage 壳和输入/输出，再逐步迁移纯函数。

### 验收

- [x] preflight timeout behavior unchanged。
- [x] airborne detection and takeoff ACK fallback unchanged。
- [x] no task bypasses standard readiness to make hover easier。

### P6 decisions

Decision: implement flight prefix stages as side-effect-free `Stage` classes over `MissionContext`.

Basis: codebase research and targeted tests.

Reason: GUIDED, arm, and takeoff still send commands from the ROS/MAVLink node. Keeping the new stages side-effect-free makes the prefix reusable and testable without changing command timing or bypassing the existing readiness, ACK, and independent-height gates.

## P7：收缩 `hover_mission.py` 为 shell + pipeline runner

目标：让 hover node 只负责外部 IO 和 pipeline 调度。

### 任务

- [x] 保留 `_build_arg_parser()` 和 `run()`。
- [x] `MavlinkHoverMissionController` 负责 ROS publisher/subscriber、MAVLink drain、timer。
- [x] `_tick()` 接入 context sync 和 prefix pipeline tick：

```text
drain_mavlink
  -> update MissionContext
  -> pipeline.tick(ctx)
  -> existing decision side effects
  -> publish status
  -> write summary when terminal
```

- [x] summary assembly 迁到 `mission/evidence/summary.py`。
- [x] `hover_mission.py` 删除测试 helper facade，只保留 runtime `run()` / `main()`。
- [x] prefix pipeline directly owns command side effects through an adapter.
- [x] landing stage owns landing decisions through an adapter；node 仍保留 landing start/tick glue 和 evidence publishing。

### 验收

- [x] `hover_mission.py` 行数明显下降。
- [x] `run()` compatibility unchanged。
- [x] `just check-python` 通过。

### P7 decisions

Decision: connect hover runtime to `MissionContext` and the prefix `FlightPipeline`; command side effects are now issued through the command adapter used by prefix stages.

Basis: codebase research and targeted tests.

Reason: this keeps the real runner bridge (`drain_mavlink -> sync context -> pipeline.tick`) while moving GUIDED / arm / takeoff side effects behind a tested adapter instead of leaving them in hover body decision branches.

Decision: keep AP LAND mode descent profile as audit-only, and align hover's audit threshold with the unified landing default `0.60 m/s`.

Basis: codebase research and run `artifacts/sim/hover/20260623T043203Z`.

Reason: that run completed with `ok=true`, `mission_phase_state=S13 task_success`, and `landing.blockers=[]`, but `landing.descent_profile.ok=false` because hover still used a stale `0.25 m/s` audit threshold while AP LAND produced about `0.54 m/s`. For `ap_land_mode_after_hover`, tests and landing acceptance intentionally require LAND handoff, touchdown, disarm, and motors-safe evidence, while treating descent profile as diagnostic rather than a blocker. The audit threshold should match `orchestration/sim/config.toml` and the unified landing design default so a normal AP LAND descent is not reported as an apparent profile failure.

Verification: run `artifacts/sim/hover/20260623T044440Z` generated with `max_landing_descent_rate_mps=0.6` reached `mission_phase_state=S13 task_success`, `landing.ok=true`, `landing.descent_profile.ok=true`, `speed_ok=true`, and `max_downward_speed_mps=0.5430664420127869`. The top-level gate still blocked on `hover_xy_alignment_direction_mismatch` / `hover_xy_evidence_disagreement`, so the landing profile diagnostic is resolved but cross-task refactor should wait until the XY alignment gate is understood.

Decision: compare `/external_nav/odom_candidate`, `/external_nav/odom`, and `/slam/odom_corrected` as native ROS odometry XY in hover XY alignment gate.

Basis: codebase research and run `artifacts/sim/hover/20260623T044440Z`.

Reason: the blocked run showed `/external_nav/odom_candidate` and `/slam/odom_corrected` had identical raw XY vectors, but the gate flipped the ExternalNav vector as if the rosbag topic had already been projected into MAVLink `MAV_FRAME_LOCAL_FRD`. That projection happens inside the MAVLink sender when sending protocol fields; it should not be applied to ROS odometry topics during rosbag evidence comparison. Applying it in the gate produced false `hover_xy_alignment_direction_mismatch` blockers between pass-through topics.

Verification: run `artifacts/sim/hover/20260623T045927Z` reached `TASK_STATUS_OK`, `gate_evaluation.ok=true`, `blockers=[]`, `mission_phase_state=S13 task_success`, and `hover_xy_alignment.ok=true`.

Follow-up design note: live hover stability is tracked separately in `docs/notes/hover_xy_stability_design.md`. That note distinguishes replay/display TF fixes, gate projection fixes, and the remaining live XY drift / SLAM jump / FCU control stability work. Do not mix that repair into the current pipeline refactor unless the refactor itself changes runtime behavior.

## P7 剩余重构 TODO：把 `hover_mission.py` 收成 shell

P7 开始时 `navlab/sim/companion/nodes/hover_mission.py` 仍约 1467 行；P7.8 后已降到约 1054 行。P0-P7 已经把通用 MAVLink primitive、FSM、pipeline/context 骨架、prefix stage、hover decision/evidence、landing policy/evidence、runtime state owner、command runtime、landing evidence recorder、final summary builder/writer 抽出来；`hover_mission.py` 已基本收成 runtime shell。以下 TODO 是继续 P8 之前应该优先清掉的 hover 本体 debt。

2026-06-23 cleanup decision:

- hover runtime 不再接收 obstacle/demo 旧 CLI 参数：`--forward-speed-mps`、`--avoid-forward-speed-mps`、`--obstacle-detect-distance-m`、`--obstacle-avoid-distance-m`、`--scan-yaw-deg`、`--scan-dwell-sec`、`--pass-x-m`、`--return-y-m`、`--final-hold-sec`、`--scan-features-topic`、`--pose-topic`、`--scan-timeout-sec`、`--setpoint-lookahead-sec`。
- `MissionNodeConfig.argv()` 不再生成这些 hover 无用参数；这是 deliberate break，不做兼容。

### P7.1：prefix stage 拥有命令 side effect

当前状态：

- [x] `RuntimeReadyStage` / `GuidedModeStage` / `ArmStage` / `TakeoffStage` 已存在。
- [x] `_tick()` 已调用 `self._prefix_pipeline.tick(self._mission_context)`。
- [x] prefix pipeline 已通过 command adapter 执行 GUIDED / arm / takeoff side effect。
- [x] `set_mode` / `command_arm` / `command_takeoff` 已不再由 `_tick()` 的旧 `decide_hover()` 分支发送。

目标：

- [x] 增加 `MissionCommandAdapter` / `request_mission_command()`，封装 `set_mode`、`command_arm`、`command_takeoff`、command count、retry cadence。
- [x] `GuidedModeStage` 通过 adapter 请求 GUIDED。
- [x] `ArmStage` 通过 adapter 请求 arm。
- [x] `TakeoffStage` 通过 adapter 请求 takeoff。
- [x] `_tick()` 不再用 hover body decision 发送 prefix 命令。
- [x] 保持现有 command retry cadence、ACK fallback、independent height fallback 不变。

验收：

- [x] prefix stage 单测覆盖 command adapter 调用和 ACK / independent height fallback；retry cadence 保留在 node adapter 层。
- [x] `navlab/tests/companion/test_mission_prefix_stages.py` 不依赖 ROS / pymavlink。
- [x] `just check-python` 通过。
- [x] `just navlab-run hover` 曾通过到 `TASK_STATUS_OK` / `mission_phase_state=S13 task_success` / `gate_evaluation.ok=true`；后续代码改动仍需重跑。

### P7.2：hover body 变成 `HoverHoldStage`

当前状态：

- [x] `HoverInputs` / `HoverRequirements` / `HoverDecision` / `decide_hover()` 已移到 `mission/stages/hover.py`。
- [x] hover drift 和 altitude crosscheck evidence 已移到 `mission/evidence/hover.py`。
- [x] hover settle / hover hold 的采样、phase count、hold anchor 已下沉到 `MissionContext.state.hover` / `HoverEvidenceRecorder`；hold setpoint 发送已改为 stage intent + command adapter。
- [x] hover complete 后启动 landing 已由 `HoverMissionPipelineRunner.tick_hover()` 控制；node 只提供 landing start IO callback。

目标：

- [x] 新增 `HoverHoldStage`，负责 `hover_settle` / `hover_hold` / `complete` 的 stage 语义。
- [x] stage 只返回 hold setpoint intent，不直接依赖 ROS publisher。
- [x] node 通过 adapter 发布 setpoint intent，保持当前 `/navlab/hover/status` schema。
- [x] hover segment、altitude samples 写入 `HoverEvidenceRecorder.record_context(ctx, ...)`，phase count 写入 `ctx.state.hover.phase_counts`。
- [x] `_tick()` 不再负责 hover terminal 后启动 landing；`HoverMissionPipelineRunner` 将 hover `complete` / `abort` 统一切入 landing suffix/safety path。

验收：

- [x] hover decision/evidence tests 仍通过。
- [x] status history、phase counts、hover drift、altitude crosscheck summary schema 不变；2026-06-23 修复了 phase_counts 误混入 `runtime_ready` 的回归。
- [x] `mission_summary.json["hover_body_ok"]`、`hover_drift`、`hover_altitude_crosscheck` 保持兼容。
- [ ] `just navlab-run hover` 通过；20260623T114138Z runtime 完整执行且生成 `mission_summary.json`，但因 live hover drift / XY alignment gate blocked。

### P7.3：landing 变成真正的 `LandingStage`

当前状态：

- [x] landing policy helpers 已移到 `mission/stages/landing.py`。
- [x] landing descent evidence 已移到 `mission/evidence/landing.py`。
- [x] `_start_landing()` 已降为 runner 调用的 node-local IO callback：发布 landing intent，并把 landing start/frozen hover evidence 交给 `LandingEvidenceRecorder.start_with_hover_evidence()`。
- [x] `_tick_landing()` 不再控制 pre-land hold、guided descent、LAND command、touchdown、disarm、timeout；这些终端分支由 `HoverMissionPipelineRunner.tick_landing()` + `LandingStage` 解释。
- [x] `_send_landing_descent_setpoint()` 保留为 node-local MAVLink IO adapter method；何时发送由 `LandingStage` 经 command adapter 请求。
- [x] `_landing_summary()` 已调用 `build_landing_summary()`，landing schema assembly 不再直接散落在 node 中。

目标：

- [x] 新增 `LandingStage`，接管 pre-land hold、guided descent、LAND command、disarm、complete/abort 决策。
- [x] landing stage 通过 adapter 请求 hold setpoint、guided descent setpoint、LAND command、disarm。
- [x] landing stage 写 `ctx.state.landing`；`ctx.evidence.landing` 还未系统化。
- [x] node 主要负责发布 `/navlab/landing/status` 和 `/navlab/landing/intent`，但仍保留 touchdown/descent sample 采样。
- [x] descent sample source selection 下沉到 `LandingEvidenceRecorder.append_descent_sample_from_pose()`。
- [x] AP LAND mode 继续要求 LAND handoff、touchdown、disarm、motors safe；descent profile 仍按 policy 决定是否 hard gate。

验收：

- [x] landing policy/evidence tests 仍通过。
- [x] `/navlab/landing/status` schema 不变。
- [x] `mission_summary.json["landing"]` schema 不变。
- [x] AP LAND audit-only 语义不回退：`ap_land_mode_after_hover` 不因 descent profile alone block。
- [x] guided descent 仍 hard-enforces descent profile。
- [ ] `just navlab-run hover` 通过；20260623T114138Z landing ok 且 blockers=[]，但 hover drift / XY alignment 使 mission ok=false。


2026-06-23 runner split decision:

- `HoverMissionPipelineRunner` owns hover terminal -> landing suffix handoff so `_tick()` no longer decides when to call landing after hover `complete` / `abort`.
- `HoverMissionPipelineRunner.tick_landing()` owns landing stage result interpretation; node `_tick_landing()` now applies returned IO outcomes only (publish status, stop vehicle, write summary, shutdown).
- Node still owns ROS/MAVLink IO methods such as landing intent publish and local-position setpoint send; this follows the shell boundary rather than moving side effects into pure stages.

### P7.4：summary 迁出 node

当前状态：

- [x] `_publish_status()` 已调用 `build_hover_status_payload()`。
- [x] `_landing_summary()` 已调用 `build_landing_summary()`。
- [x] `write_summary()` 已调用 `MissionSummaryBuilder` 和 `MissionSummaryWriter`；最终 payload assembly 和原子 JSON 写入已迁出。
- [x] `mission_phase_summary_fields()` 已迁到 `mission/evidence/summary.py`。

目标：

- [x] 新增 `mission/evidence/summary.py`。
- [x] 已提供 `build_hover_status_payload()`、`build_landing_summary()`、`MissionSummaryBuilder.build()`。
- [x] summary builder 通过显式参数接收 runtime snapshot / config / evidence；后续可进一步收敛为 typed summary snapshot。
- [x] `hover_mission.py` 对 hover/landing status 只负责 `json.dumps()` 和 publish；最终 `mission_summary.json` payload 已由 builder 拼接。
- [x] 所有 schema 兼容字段保留，不能因为拆文件删字段。

验收：

- [x] 增加 summary builder 单测，覆盖 hover status、landing gate、preflight timeout 和 final mission summary payload。
- [x] `mission_summary.json` 关键字段和当前 artifact 兼容。
- [x] `just check-python` 通过。
- [x] `just navlab-run hover` 曾通过到 `TASK_STATUS_OK`；后续代码改动仍需重跑。

### P7.5：MAVLink drain 和 status parse 适配层

当前状态：

- [x] `_drain_mavlink()` 已通过 `mavlink_runtime_update()` 解析 heartbeat、local position、attitude、rangefinder、ACK、STATUSTEXT、PARAM_VALUE，node 只应用 update。
- [x] `_handle_external_nav_status()` / `_handle_mavlink_external_nav_status()` / `_handle_mavlink_status()` 已通过 typed snapshot 解析 status JSON。
- [x] `MissionContext` 通过 typed `MissionRuntimeSnapshot` 刷新，不再由 `_sync_mission_context()` 逐字段手工搬运。

目标：

- [x] 新增 `mission/runtime_state.py`，集中解析 MAVLink-derived update 和 status snapshots。
- [x] status topic parsing 返回 typed snapshot，不在 node 中散落 json key 读取。
- [x] `_tick()` 已直接使用 `MissionRuntimeStateAdapter.runtime_snapshot()` + `apply_runtime_snapshot_to_context(...)`，不再逐字段手工搬运。
- [x] node 仍拥有 ROS subscriptions 和 MAVLink connection，不把 IO 隐藏进 pure stage；status/MAVLink-derived state 已由 `MissionRuntimeStateAdapter` / `MavlinkRuntimeState` owner 管理。

验收：

- [x] adapter 单测覆盖 ACK、mode、armed、landed_state、rangefinder、local position/status parsing。
- [x] `_drain_mavlink()` 行数显著下降。
- [x] `just check-python` 通过。
- [ ] `just navlab-run hover` 通过；20260623T120635Z generated `mission_summary.json`, no runtime exception, but blocked on live hover drift / XY alignment gates.

### P7.6：删除 compatibility facade

当前状态：

- [x] companion tests 已不再从 `hover_mission.py` import helper facade。
- [x] 只剩 runtime `run()` entrypoint 被 `hover_acceptance.py` 延迟导入。

目标：

- [x] 所有测试改为直接 import `mission.context`、`mission.fsm`、`mission.mavlink_commands`、`mission.stages.*`、`mission.evidence.*`、`mission.runtime_state`。
- [x] `hover_mission.py` 只保留 runtime `run()`、`main()`、arg parser 和 node-local helpers。
- [x] 删除不再属于 node 的 statustext helper aliases。

验收：

- [x] `rg "from navlab.sim.companion.nodes.hover_mission import" navlab/tests` 为 0。
- [x] `hover_mission.py` import section 不再承担 test/public helper facade。
- [x] `just check-python` 通过。

### P7.7：最终 shell 边界

当前状态：P7.1-P7.8 已把 command side effect、hover/landing stage 决策、runtime status/MAVLink parsing、test facade、final summary preparation、hover/landing evidence ownership 大部分迁出；`hover_mission.py` 保留 ROS/MAVLink IO、timer dispatch、publisher/subscriber wiring、telemetry/request cadence 和 shell callback。

最终 `hover_mission.py` 应只保留：

- [x] `_build_arg_parser()`
- [x] `run()`
- [x] `main()`
- [x] ROS publisher/subscriber wiring。
- [x] timer callback 调度 pipeline。
- [x] MAVLink connection lifecycle。
- [x] publish/write JSON 的 IO 动作。

最终 `hover_mission.py` 不应再直接包含：

- [x] flight prefix command decision。
- [x] hover body phase transition。
- [x] landing state machine。
- [x] summary schema assembly。
- [x] reusable MAVLink command primitive。
- [x] reusable evidence calculation。
- [x] concrete task-to-task shared base logic。

建议执行顺序：

1. P7.4 summary builder，风险最低，先减少 schema 拼接噪声。
2. P7.3 landing stage，因为 landing 是跨任务 suffix，复用价值最大。
3. P7.1 prefix command adapter，把 stage 从观察变成执行。
4. P7.2 hover body stage，最后收掉 `_tick()` 主体。
5. P7.5 runtime adapter，收敛状态同步和 MAVLink drain。
6. P7.6 删除 compatibility facade。

不要在这些重构里改变控制阈值、放宽 gate、引入 Gazebo truth 控制输入，或者把 navigation / exploration 改成继承 hover。

### P7.8：状态 ownership 类化，避免薄 wrapper

当前状态：`hover_mission.py` 已把部分决策、summary、MAVLink parse 拆出。P7.8 已继续把运行时 MAVLink 状态、command retry cadence、landing evidence、final summary 写入下放到 owner/builder class；node 仍保留 ROS I/O、timer、publisher/subscriber、mission context 同步和少量 orchestration glue。

目标：

- [x] 新增或完善 `MavlinkRuntimeStateAdapter` / `MissionRuntimeStateAdapter`，拥有 MAVLink-derived runtime state，而不是只返回临时 update；`MissionRuntimeStateAdapter` 现拥有 ROS status readiness、freshness/loss timers、external mode/arm mirrors，并与 `MavlinkRuntimeState` / `MavlinkRuntimeCollections` 共同输出 typed snapshots。
- [x] 将 `_target_system`、`_target_component`、`_current_custom_mode`、`_armed_seen`、`_current_x/y/z/vz`、`_current_range_m`、`_message_counts` 迁入 runtime state owner。
  - 2026-06-23：新增 `MavlinkRuntimeState`，`hover_mission.py` 通过 `self._runtime.apply_update()` 接收 MAVLink parser 输出；node 不再直接持有这些 runtime pose/mode/message_counts 字段。
- [x] 将 `_command_acks`、`_accepted_command_ids`、`_statustext` 迁入 `MavlinkRuntimeCollections` owner。
- [x] 将 `_next_mode_command`、`_next_arm_command`、`_next_takeoff_command`、`_next_setpoint`、`_next_land_command`、`_next_disarm_command`、`_sent_commands` 迁入 command adapter 或 dedicated command runtime state。
  - 2026-06-23：新增 `MissionCommandRuntime`，拥有 command retry deadlines、setpoint count、sent command counts。`_next_request/_next_heartbeat/_next_origin_command` 暂保留在 node，因为这是 telemetry/request cadence，不属于 mission command retry state。
- [x] 新增 `HoverEvidenceRecorder`，拥有 `_hover_samples`、`_hover_altitude_samples`、`_best_hover_samples`、`_hover_started`、`_hover_hold_segments_seen` 对应状态，并产出 selected hover evidence window。
- [x] 新增 `LandingEvidenceRecorder` 或扩展 `LandingStage` state owner，拥有 `_landing_descent_samples`、`_touchdown_confirmed`、`_touchdown_confirmed_time`、`_land_command_sent`、`_land_mode_seen`、`_fcu_land_params`、`_landing_blockers`。
  - 2026-06-23：新增 `LandingEvidenceRecorder`，拥有 landing start、descent samples、touchdown debounce、LAND command handoff、FCU land params、landing blockers、frozen hover evidence。
- [x] 新增 `MissionSummaryWriter` / `MissionSummaryBuilder`，把 final `write_summary()` 从 node 移出。
  - 2026-06-23：新增 `MissionSummaryBuilder` 和 `MissionSummaryWriter`；node 仍计算当前运行上下文，但最终 summary payload 和原子 JSON 写入已移出。
- [x] `hover_mission.py` 的 node class 只持有 ROS publishers/subscribers、MAVLink connection、pipeline/adapter/summary-runtime 实例、timer callback 所需的 coordination state；runtime/status/summary ownership 已下沉。

避免薄 wrapper 原则：

- [x] 只有“拥有状态 + 维护生命周期/不变量 + 提供可测试行为”的对象才建 class。
- [x] 纯输入输出计算保持 function，例如 `landing_acceptance_ok()`、`should_command_land_this_tick()`、`summarize_hover_drift()`、`build_landing_summary()`。
- [x] 不创建只包一两个 getter/setter、只转发到原 controller 字段、没有独立测试价值的 wrapper。
- [x] `HoverEvidenceRecorder` 已让 `hover_mission.py` 删除对应 hover sample/best/segment 私有属性，不只是多一层调用。
- [x] `HoverEvidenceRecorder` 已有 focused unit test 覆盖状态更新和 evidence 输出。
- [x] 后续新增 owner 仍必须删除 node 对应私有属性，并至少有一个 focused unit test；`MissionRuntimeStateAdapter` 和 `HoverMissionSummaryRuntime` 已有 focused tests。

参数传递原则：

- [x] stage / recorder / adapter 之间传运行时状态时优先使用 `MissionContext`，不要继续扩散 10+ 参数的函数签名。
- [x] 固定任务配置不塞进 `MissionContext`，用 config dataclass 注入，例如 `HoverHoldConfig`、`LandingStageConfig`、`MissionRuntimeAdapterConfig`、`HoverMissionSummaryConfig`。
- [x] 外部副作用不塞进 `MissionContext.state`，通过 `ctx.io.*` adapter 或 constructor 注入的 IO adapter 暴露 intent，例如 MAVLink command、ROS publish、summary file write。
- [x] `MissionContext` 只放每 tick 会变化、需要跨 stage 共享或需要进入 evidence 的 runtime state；禁止把它变成无边界全局 dict。
- [x] summary builder 不直接吃 controller 私有字段；`HoverMissionSummaryRuntime` 从 runtime/recorder/context owners 构建 summary snapshot 并调用 builder。
- [x] 纯 helper 如果参数少且含义稳定，可以继续显式参数；如果参数膨胀到 8-10 个以上，应引入 typed input dataclass/snapshot，而不是改成读取全局 controller。
- [x] 推荐形态：`Stage(config).tick(ctx)`、`Recorder.record(ctx)` / `Recorder.snapshot()`、`SummaryBuilder.build(snapshot, config)`、pure helper 使用小而显式的参数。

验收：

- [x] `hover_mission.py` 私有属性数量显著下降，剩余私有属性能归类为 ROS wiring、MAVLink connection lifecycle、pipeline scheduling、status/summary runtime owners 或 publisher/file IO；文件降到约 1054 行。
- [x] `MissionContext` 不退化成全局 dict；状态 owner 输出 typed snapshot 或明确 dataclass。
- [x] `HoverEvidenceRecorder` 单测已覆盖 sample append、segment lifecycle、selected evidence 输出；`LandingEvidenceRecorder` 已新增并有 focused test。
  - 2026-06-23：新增 `test_mission_state_owners.py` 覆盖 `LandingEvidenceRecorder` sample append、touchdown debounce、LAND handoff。
- [x] runtime state owner 单测覆盖 ACK、mode/armed、local pose、rangefinder、landed state、statustext；ACK collections 已由 `MavlinkRuntimeCollections` 测试覆盖。
  - 2026-06-23：`test_mission_runtime_state.py` 覆盖 `MavlinkRuntimeState.apply_update()` 对 pose/mode/counts/landed timeline 的 ownership；`test_mission_state_owners.py` 覆盖 `MissionCommandRuntime` 和 `MissionSummaryWriter`。
  - Verification：`just check-python` 通过，360 passed。
- [x] `just check-python` 通过。
- [ ] `just navlab-run hover` 通过，`mission_phase_state=S13 task_success`，`landing.blockers=[]`，gate blockers 为空；20260623T120635Z reached `landing_ok=true`, `landing.blockers=[]`, and stopped at `S12 landing_complete` because hover drift / XY alignment exceeded threshold.


2026-06-23 shell boundary decision:

- `MissionRuntimeStateAdapter` owns ROS status readiness/freshness/loss-duration state and builds `HoverInputs` / `MissionRuntimeSnapshot`; `hover_mission.py` no longer owns external-nav, MAVLink-external-nav, IMU, or external mode/arm mirror fields.
- `HoverMissionSummaryRuntime` owns landing/final mission summary preparation from state owners; `hover_mission.py` only publishes/writes JSON.
- `hover_mission.py` remains the imperative shell for ROS publishers/subscribers, MAVLink connection lifecycle, telemetry/request cadence, timer dispatch, and IO adapter methods.

### P7.9：抽出 `navlab.common.companion.mission`，给 sim / real 共用 functional core

当前判断：P7.7 / P7.8 已经把 hover node 收成可接受的 shell；继续在
`hover_mission.py` 内部挤小 helper 的收益开始下降。更值得做的下一步是把已经证明
不依赖 Gazebo / SITL / ROS shell 的 mission functional core 移到
`navlab/common/companion/mission/`，让后续 real companion task 也能复用同一套
context、stage、FSM、evidence 和 summary 语义。

边界决策：

- `navlab.common.companion.mission` 只放 sim / real 完全一致的纯 mission 逻辑和 typed contract。
- sim / real 的 orchestration 控制面仍不共享 Python helper；P7.9 只处理 `navlab` runtime 内部可共用的 companion mission core。
- 不把 Gazebo truth、SITL 默认原点、Docker/runtime artifact、real operator safety confirmation、真实串口/硬件 ownership 放进 common。
- 不因为迁移到 common 放宽 hover / landing gate，也不引入 Gazebo truth 作为 runtime control input。

建议目标结构：

```text
navlab/common/companion/mission/
  __init__.py
  context.py
  pipeline.py
  fsm.py
  command_adapter.py
  hover_landing.py
  runtime_state.py              # only if it stays mode/topic agnostic
  summary_runtime.py            # JSON/schema builder, no sim artifact policy
  evidence/
    hover.py
    landing.py
    summary.py
  stages/
    prefix.py
    hover.py
    landing.py

navlab/sim/companion/mission/
  __init__.py                   # temporary compatibility re-export only
  mavlink_commands.py           # keep concrete SITL-safe command sender here first

navlab/real/companion/mission/
  command_adapter.py            # real safety/transport adapter, optional future step
```

可迁移候选：

- [x] `context.py`、`pipeline.py`、`fsm.py`：pure dataclass / stage protocol / FSM mapping，优先迁。
- [x] `command_adapter.py`：只包含 `MissionCommandAdapter` protocol、command retry runtime、`request_mission_command()`，可以迁；真实发送策略不放这里。
- [x] `stages/prefix.py`、`stages/hover.py`、`stages/landing.py`：如果保持“只请求 adapter、不直接 import MAVLink/ROS/Gazebo”，可迁到 common。
- [x] `evidence/hover.py`、`evidence/landing.py`、`evidence/summary.py`：纯 evidence / schema builder 可迁。
- [x] `hover_landing.py`：runner 只协调 stage / recorder / callback，可迁；IO callback 仍由 sim/real shell 注入。
- [x] `summary_runtime.py`：若只依赖 common state owners 和 explicit path 参数，可迁；artifact 目录选择仍由 orchestration/shell 负责。
- [x] `runtime_state.py`：拆成 common typed runtime snapshot / status parser 与 sim-specific MAVLink drain adapter；能不 import sim、Gazebo、rclpy 的部分才迁。
  - 2026-06-23：新增 `mavlink_protocol.py` 承载 ACK/status parser 所需的 MAVLink constants / normalization；concrete command sender 仍留在 sim `mavlink_commands.py`。

暂不直接迁到 common 的内容：

- [x] `mavlink_commands.py` 中 `command_arm()`、`command_takeoff()`、`command_land()`、`set_mode()` 这类会直接触发车辆行为的 sender。它们可以先留在 sim，real 侧通过自己的 safety adapter 实现同一 `MissionCommandAdapter`。
- [x] `DEFAULT_ORIGIN_LAT_DEG` / `DEFAULT_ORIGIN_LON_DEG` / `DEFAULT_ORIGIN_ALT_M` 这类 SITL 默认值留在 sim。
- [x] `set_arming_check()`、force-arm / force-disarm magic、EKF origin/home setup：如果未来要共享，只能先拆成 `navlab.common.companion.mavlink_protocol` 的低层编码 helper；真实安全策略必须在 `navlab.real.*` adapter 显式包一层。
- [x] ROS publisher/subscriber、MAVLink connection lifecycle、timer、telemetry/request cadence、artifact directory policy 继续留在 concrete shell。

迁移顺序：

1. 新建 `navlab/common/companion/mission/`，先迁 leaf modules：`fsm.py`、`context.py`、`pipeline.py`、`command_adapter.py`。
2. 迁 `evidence/*` 和 `stages/*`，同步改内部 import；保持所有 stage 只通过 adapter 表达 side effect。
3. 拆 `runtime_state.py` / `mavlink_commands.py`：ACK/status normalization 等无安全副作用的 parser 可以 common，具体 command sender 先留 sim/real。
4. 迁 `hover_landing.py` 和 `summary_runtime.py`，让 sim shell 只 import common runner + sim command sender。
5. 在 `navlab/sim/companion/mission/*` 保留一轮 compatibility re-export，先把 tests 改到 common import，再删除 shim。

real 复用目标：

- [x] real hover/preflight task 可以 import `MissionContext`、`FlightPipeline`、`LandingStage`、`HoverEvidenceRecorder`、summary builder，而不会 import `navlab.sim`、Gazebo、SITL default 或 Docker runtime。
- [x] real 侧通过 `MissionCommandAdapter` 注入安全确认、真实 MAVLink transport、arm/takeoff/land 策略；common stage 不知道自己运行在 sim 还是真机。
- [x] `/navlab/landing/status`、mission FSM、landing evidence、summary schema 在 sim / real 保持同一 contract。

验收：

- [x] `rg "navlab\\.sim|gazebo|sitl|docker" navlab/common/companion/mission --glob '*.py'` 没有 runtime import / assumption 命中；允许 `uses_gazebo_truth_as_input` 这个历史 summary schema field。
- [x] `rg "navlab\\.sim\\.companion\\.mission" navlab/real --glob '*.py'` 为 0。
- [x] `python - <<'PY'` 能只 import common mission core：`MissionContext`、`FlightPipeline`、`LandingStage`、`HoverEvidenceRecorder`、`MissionSummaryBuilder`。
- [x] companion mission tests 改为优先 import `navlab.common.companion.mission.*`，sim compatibility shim 只覆盖旧路径。
- [x] `just check-python` 通过。
- [x] `just check-go` 通过。
- [x] `just navlab-run hover` 能完整跑到 summary；若仍 block，只允许是 hover drift / XY alignment 等已知运行时 gate，而不是 import/package boundary 回归。
  - 2026-06-23：run `artifacts/sim/hover/20260623T123111Z` generated summary without import/package errors; `mission_summary.ok=true`, `mission_phase_state=S13 task_success`, `landing.ok=true`, `landing.blockers=[]`; top-level gate still blocked on hover XY alignment evidence disagreement.

2026-06-23 common companion decision:

- Basis: `docs/general/navlab_real_sim_package_boundary_design.md` 允许 `navlab.common.*` 放 sim / real 完全一致的纯 runtime utilities，但要求 direct hardware / SITL / Gazebo assumptions 留在对应 safety domain。
- Reason: P7.8 后 hover shell 已经主要剩 IO wiring；继续 refactor 的最大复用点不是再拆 shell，而是把 common mission functional core 提前移出 `navlab.sim`，避免 real companion 未来反向 import sim mission。
- Verification: focused companion mission tests passed (`102 passed`), `just check-python` passed (`360 passed`), `just check-go` passed, and `just navlab-run hover` reached mission success before the existing XY alignment gate block.

## P8：跨任务复用

目标：在 hover 拆稳后，再让其他 flight task 组合公共 prefix/suffix。

### 任务

- [x] `obstacle_mission.py` 改用 `mission/mavlink_commands.py`。
- [ ] exploration / navigation / scan robustness 继续通过 orchestration workflow 组合，不继承 hover。
- [ ] 为 future flight tasks 提供 `COMMON_FLIGHT_PREFIX` 和 `COMMON_FLIGHT_SUFFIX`。
- [ ] 评估 `fcu_controller_runtime.py.tmpl` 中 takeoff / landing 逻辑是否需要下沉到 companion mission module。
- [x] 移除 `hover_mission.py` 临时 helper re-export；runtime 只保留 `run()` entrypoint。

### 验收

- [x] no concrete mission node imports common command logic from another concrete mission node。
- [ ] `/navlab/landing/status` schema remains shared。
- [ ] hover, exploration, navigation, scan-robustness task plans still generate expected runtime scripts。
- [x] relevant sim task dry-run passes。

## 建议执行顺序

1. P0 baseline inventory。
2. P1 context / pipeline 骨架。
3. P2 FSM。
4. P3 MAVLink commands。
5. P4 landing。
6. P5 hover body。
7. P6 runtime ready / guided / arm / takeoff。
8. P7 hover runner 收缩。
9. P7.9 common companion mission package。
10. P8 cross-task reuse。

原因：

- 先建 `MissionContext` / `StageResult`，避免只是把大文件拆成多个无结构函数文件。
- FSM 早接入 pipeline，后面 stage 都能统一记录。
- MAVLink command 先抽，解决依赖方向错误。
- landing 和 hover body 都是纯逻辑较多的 stage，适合先迁移。
- takeoff / preflight 风险更高，放在有 pipeline 和测试保护之后。
- P7.9 先建立 sim / real 可共享的 runtime functional core package，避免 P8 扩到其他任务时继续把 common 逻辑留在 `navlab.sim`。

## 每阶段通用验收

每个 phase 至少跑：

```bash
just check-python
```

涉及 Go runtime template 或 task artifact 生成时加跑：

```bash
just check-go
```

涉及 hover runtime argv 或生成脚本时加跑：

```bash
cd orchestration/sim && go test ./internal/tasks/helpers ./internal/tasks ./cmd/navlab-sim -count=1
```

涉及真实 hover 行为时再跑：

```bash
just navlab-run hover
```

## 最终验收

- [ ] `hover_mission.py` 只保留 node wiring、argument parsing、MAVLink drain、pipeline scheduling、runtime entrypoint。
- [ ] common MAVLink command logic 不属于任何具体 mission node。
- [ ] `MissionContext` 有明确分层，没有退化成全局字典。
- [ ] `FlightPipeline` 能组合 hover / exploration / navigation / scan robustness 的公共 prefix/suffix。
- [ ] landing logic 可被 hover 以外的 flight task 复用。
- [ ] hover mission summary schema 不破坏历史 artifact 消费者。
- [ ] `just check-python` 和 `just check-go` 通过。
- [ ] hover task dry-run 和至少一次 full run 通过。
