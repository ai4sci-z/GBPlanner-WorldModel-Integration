# Orchestration Workflow Schema

日期：2026-06-26

## 目的

本文冻结 Go sim 和 Rust real 第一版共享 workflow 术语与最小 artifact schema。
它是 `docs/notes/real_hover_orchestration_gap_todo.md` 中 WF0 的产物。

目标不是立刻引入完整 DAG engine，也不是立刻新增 protobuf contract。当前目标
是让 sim 和 real 先使用同一套阶段名、node result 形状和 task FSM transition
语义；evidence 仍然由各自 safety domain 采集。

## 决策

Decision：WF0 先做文档级 schema，不直接新增 generated proto。

Basis：当前 `contracts/` 已经有 `doctor_result.json`、`runtime_plan` 和
task result 相关 contract，但还没有稳定的 `WorkflowNode`、`NodeResult`、
`NavLabFsmTransition` proto。

Reason：Go sim 和 Rust real 需要先在阶段名和 artifact 语义上收敛。等 WF1-WF3
证明字段稳定后，再把 schema 上升到 `contracts/proto`，否则会过早维护跨语言
生成代码。

## 术语

`workflow` 指外层 orchestration DAG：

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

`fsm` 指任务运行期内部状态机。`preflight`、`prepare`、
`common-doctor`、`task-doctor` 不能塞进 task FSM，它们是外层 workflow node。

`motor-debug` 的 task FSM 示例：

```text
runtime_ready
  -> guided
  -> armed
  -> motor_spin_hold
  -> disarmed
  -> completed
```

request、ACK、heartbeat、confirm 这类细节属于 transition evidence，不是顶层
task FSM state。

## WorkflowNode

最小字段：

```json
{
  "id": "prepare",
  "kind": "prepare",
  "deps": ["preflight"],
  "required": true,
  "mode": "dry_run",
  "domain": "sim",
  "side_effect_policy": "plan_only",
  "summary_path": "prepare_summary.json",
  "artifact_paths": ["runtime_plan.json"]
}
```

字段规则：

- `id`：workflow 内稳定唯一 node id，使用 kebab-case。
- `kind`：取值为 `load-config`、`preflight`、`prepare`、
  `common-doctor`、`task-doctor`、`runtime-execute`、`gate-evaluate`、
  `summary`。
- `deps`：运行前必须完成的 node id。
- `required`：为 true 时，依赖失败或本节点失败会阻塞后续 required node。
- `mode`：取值为 `dry_run`、`live`、`replay`。
- `domain`：取值为 `sim`、`real`、`common`。
- `side_effect_policy`：取值为 `none`、`plan_only`、
  `prepare_resource`、`runtime_start`、`hardware_command`。
- `summary_path`：node 级 summary artifact 路径，尽量相对 run artifact dir。
- `artifact_paths`：后续 node 可以引用的输出 artifact。

side effect 规则：

- `preflight` 应使用 `none`。
- dry-run `prepare` 应使用 `plan_only`。
- live `prepare` 可使用 `prepare_resource`。
- `runtime-execute` 使用 `runtime_start`。
- 会触碰真实硬件命令的 real task 使用 `hardware_command`。

## NodeResult

最小字段：

```json
{
  "id": "prepare",
  "kind": "prepare",
  "ok": true,
  "blocked": false,
  "skipped": false,
  "skip_reason": "",
  "blockers": [],
  "warnings": [],
  "artifacts": {
    "summary": "prepare_summary.json",
    "doctor_result": "doctor_result.json",
    "runtime_plan": "runtime_plan.json"
  },
  "evidence": {
    "service_plan_count": 6,
    "probe_plan_count": 4
  },
  "started_at": "2026-06-26T00:00:00Z",
  "finished_at": "2026-06-26T00:00:01Z"
}
```

字段规则：

- `ok=true` 表示该 node 完成了自己的 contract。
- `blocked=true` 表示 workflow 不应继续执行后续 required node。
- `skipped=true` 时必须写 `skip_reason`。
- `blockers` 是机器稳定 blocker；新代码优先使用含 `code`、`message`、
  `source` 的对象。
- `warnings` 自身不阻塞后续 required node。
- `artifacts` 是 artifact role 到路径的映射。
- `evidence` 是结构化 JSON，sim 和 real 可以不同。
- 时间戳使用 RFC3339 UTC。

依赖规则：

- required dependency blocked 时，后续 required node 跳过，并写
  `skip_reason=blocked_by_dependency:<node_id>`。
- optional node 失败只记录 warning evidence，不阻塞 required 主链。
- 每个被执行的 node 都必须写 summary artifact 或 `doctor_result`。

## NavLabFsmTransition

最小字段：

```json
{
  "task_id": "motor-debug",
  "run_id": "20260626T000000Z",
  "fsm_name": "motor-debug",
  "from_state": "guided",
  "to_state": "armed",
  "event": "arm_confirmed",
  "reason_code": "arm_ack_accepted",
  "ok": true,
  "blocked": false,
  "blocker": null,
  "evidence": {
    "arm_request_sent": true,
    "arm_ack_result": "ACCEPTED",
    "armed_confirmed": true
  },
  "at": "2026-06-26T00:00:05Z"
}
```

字段规则：

- `from_state` 和 `to_state` 是粗粒度 task state，不是命令日志步骤。
- `event` 表示触发状态转移的事件。
- `reason_code` 遵守下方 reason-code 规则。
- `evidence` 记录 command request、ACK、heartbeat、topic 或 summary 证据。
- 失败 transition 设置 `blocked=true`，并写 `blocker`。

## Reason Code

Reason code 是稳定机器字符串。人类可读细节放在 `message` 或 `evidence`，不要塞进
code。

规则：

- 使用 lowercase snake_case。
- 优先使用 `phase_subject_condition` 顺序。
- 不把路径、端口、时间戳、topic 名等动态值直接放进 code。
- 动态值放到 `source`、`message` 或 `evidence`。
- 策略相同的 sim/real blocker 使用同一个 code。
- evidence 来源不同且语义不同的场景使用 domain-specific code。

示例：

```text
prepare_service_start_failed
prepare_required_service_missing
preflight_runtime_mode_mismatch
common_doctor_topic_stale
task_doctor_not_applicable
task_has_no_specific_preflight_requirements
runtime_timeout
blocked_by_dependency
```

## Default Task Doctor

每个 task 都必须产出 task-doctor 结果。如果某个 task 没有 task-specific 检查，
必须显式写成：

```json
{
  "task_id": "example-task",
  "ok": true,
  "blocked": false,
  "task_doctor_claim": "not_applicable",
  "reason_code": "task_has_no_specific_preflight_requirements",
  "reason": "task_has_no_specific_preflight_requirements",
  "checks": [
    {
      "name": "task_specific_doctor",
      "status": "ok",
      "message": "No task-specific preflight requirements are defined."
    }
  ]
}
```

这个结果表示“已经检查过，当前 task 没有额外 task-specific preflight
requirements”。它不能用于跳过 common config、profile、helper、artifact 或
deadline validation。

配套 `doctor_result.json` 应包含一个 OK check，名称为
`task_specific_doctor_not_applicable`。

## 第一版 Runner 规则

WF0 不引入第三方 DAG 库。

第一版实现应使用项目内最小 runner：

- 对静态 node 做拓扑排序。
- 按依赖顺序运行 node。
- required dependency blocked 时跳过后续 required node。
- optional node 失败时记录 warning evidence。
- 写出每个 `NodeResult`。
- 汇总 node result 到 workflow summary。

等 sim 和 real 都有真实 node result 后，如果静态 runner 明确不够用，再重新评估
是否引入 DAG 库。

