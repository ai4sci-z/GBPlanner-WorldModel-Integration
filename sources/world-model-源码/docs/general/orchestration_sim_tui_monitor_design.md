# Go Sim TUI 监控设计

## 背景

`orchestration/sim` 已经迁移为 Go 控制面，负责 simulation task registry、
runtime plan、Docker/ROS runtime specs、probe、rosbag、summary 和 manifest。
现在 `navlab-sim run <task>` 的 live path 主要通过普通终端输出表达状态。

这个方式在短命令里够用，但对 hover、exploration、scan-robustness 这种需要同时
启动 Docker、SITL、Gazebo、SLAM、controller、probe、rosbag 的任务不够直观。
操作者真正需要的是快速看到：

- 当前 run 卡在哪个阶段。
- 哪个 service/probe/rosbag 失败。
- Docker/ROS/runtime 日志是否持续更新。
- 当前 blockers、warnings、metrics 是否已经出现。
- 最终 artifact 写到了哪里。

因此 Go sim 应该增加一个 TUI monitor，和 Rust real 的终端控制面目标保持一致：
运行时直接展示状态，而不是让操作者从线性日志里慢慢找结果。

## 目标

- `navlab-sim run <task> --tui` 进入 live monitor。
- `navlab-sim tui <artifact-dir>` 可以回看已有 run artifact。
- TUI 读取同一套 Go sim runtime state，不引入新的 orchestration 语义。
- TUI 使用 `runtime_plan.json`、`task_request.json`、`summary.json`、
  `manifest.json` 和 live event stream 作为状态来源。
- TUI 不替代 JSON artifact；artifact 仍然是 CI、回放、跨语言读取的稳定接口。
- TUI 必须支持非交互环境降级，CI 或无 TTY 时继续使用当前 plain output。

## 非目标

- 不把 sim 和 real 做成共享 TUI 代码库。
- 不把 Go sim TUI 迁移成 Python。
- 不要求 Docker/ROS runtime 逻辑为了 TUI 重写。
- 不在第一版做完整 mouse UI、复杂 dashboard 配置或远程 web UI。
- 不让 TUI 成为唯一可读结果；所有关键状态必须仍写入 artifact。

## 技术选择

Go sim 推荐使用：

```text
Bubble Tea   事件循环和 TUI app model
Lip Gloss    样式、布局、颜色
Bubbles      viewport/table/spinner/progress 等常用组件
Cobra        保持现有 CLI 结构
Viper        保持现有 config.toml / YAML loader
```

理由：

- Go sim 已经使用 Cobra、Viper、Lip Gloss。
- Bubble Tea 和 Lip Gloss 是同一生态，和当前 UI style 最容易衔接。
- TUI 可以通过 `tea.Cmd` 消费 runtime event channel，不需要把 runner 改成阻塞式
  callback。
- 后续如果 real Rust TUI 用 ratatui，二者也可以通过相同 contract/event shape
  对齐，而不是共享实现。

## CLI 形态

建议新增：

```bash
navlab-sim run hover --tui
navlab-sim run hover --tui --duration-sec 120
navlab-sim run hover --dry-run --tui
navlab-sim tui artifacts/sim/hover/20260612T170000Z
```

保留现有行为：

```bash
navlab-sim run hover
navlab-sim run hover --dry-run
```

降级规则：

- `--tui` 且 stdout/stderr 不是 TTY：直接失败并提示使用 plain output，除非后续添加
  `--tui=auto`。
- 未传 `--tui`：不改变当前输出。
- panic 或 terminal restore 失败必须避免破坏终端；TUI runner 要集中管理 restore。

## 包结构

建议新增：

```text
orchestration/sim/internal/tui/
  app.go              Bubble Tea app 入口
  model.go            顶层 model/update/view
  events.go           TUI event 类型和 channel adapter
  layout.go           dashboard 布局
  styles.go           Lip Gloss 样式
  log_view.go         service/probe/rosbag 日志 viewport
  task_view.go        task/run summary panel
  runtime_view.go     services/probes/rosbags table
  artifact_view.go    manifest/artifact panel
  replay.go           从 artifact-dir 回看
```

现有 CLI 只负责：

- 解析 `--tui`。
- 准备 `preparedTaskRun`。
- 将 runtime execution 交给 TUI runner 或 plain runner。

不要让 `cmd/navlab-sim/main.go` 直接持有复杂 TUI state。

## 事件模型

第一版建议定义 Go sim 内部事件，不直接依赖 generated protobuf：

```go
type RunEvent struct {
    Time        time.Time
    TaskID      string
    RunID       string
    Phase       string
    Component   string
    ComponentID string
    Level       string
    Message     string
    Artifact    string
    Payload     map[string]any
}
```

典型事件：

```text
run.started
artifact.written
service.starting
service.started
service.log
probe.running
probe.finished
rosbag.started
rosbag.finished
gate.evaluated
summary.written
run.blocked
run.completed
```

这些事件后续可以映射到 `contracts/proto/navlab/runtime/v1/process_event.proto`，
但第一版不强制 codegen。

## Runner 改造边界

当前 Go sim 主要有：

- `BuildRuntimeSpecs`
- `ExecuteRuntimeSpecs`
- `BuildLiveRunSummary`
- `AppendManifestArtifacts`
- Docker backend 的 start/probe/wait/stop/logs

建议最小改造：

```go
type RuntimeEventSink interface {
    Emit(event RunEvent)
}
```

runner option 增加：

```go
type RuntimeExecutionOptions struct {
    KeepRunning    bool
    WaitForRosbags bool
    EventSink      RuntimeEventSink
}
```

plain runner 使用 no-op sink。TUI runner 使用 channel sink。

这样 Docker/ROS 执行逻辑还是同一套，TUI 只是消费状态。

## 主界面布局

推荐第一版使用四区布局：

```text
+------------------------------------------------------------+
| NavLab Sim | hover | run_id | elapsed | status             |
+----------------------+----------------------+--------------+
| Runtime              | Gates / Blockers     | Artifacts    |
| services             | landing              | task_request |
| probes               | rosbag profile       | runtime_plan |
| rosbags              | slam quality         | summary      |
+----------------------+----------------------+--------------+
| Logs                                                       |
| selected component log tail                               |
+------------------------------------------------------------+
| q quit | tab switch | enter inspect | l logs | a artifacts |
+------------------------------------------------------------+
```

### Runtime panel

显示：

- `official_baseline`
- `gazebo_sensor`
- `slam`
- `fcu_controller`
- `rosbag`
- probes

状态：

```text
planned
starting
running
ok
blocked
failed
stopped
```

### Gates / Blockers panel

显示：

- 当前 blockers。
- landing acceptance。
- probe output。
- rosbag topic completeness。
- hover / exploration / scan robustness metrics。

### Artifacts panel

显示：

- `task_request.json`
- `runtime_plan.json`
- generated runtime configs/scripts
- `summary.json`
- `manifest.json`
- rosbag path

选中 artifact 后按 `enter` 展开 metadata 或路径。

### Logs panel

显示当前选中 service/probe 的 tail：

- Docker start logs。
- probe stdout/stderr。
- rosbag wait result。
- runtime summary 写入事件。

日志必须限量缓存，避免长时间 run 占用过多内存。

## 快捷键

```text
q / ctrl+c   退出 TUI
tab          切换 panel
up/down      移动选择
enter        展开当前项
l            切换 log view
a            切换 artifact view
b            跳到 blockers
r            刷新 artifact-dir replay
?            帮助
```

退出策略：

- dry-run TUI 退出只关闭界面。
- live run TUI 退出时默认不直接杀 runtime，先弹确认。
- 如果 run 已经完成，退出只 restore terminal。
- 如果 run blocked，退出后保留 artifact。

## Artifact Replay

`navlab-sim tui <artifact-dir>` 需要支持离线回看：

读取顺序：

1. `manifest.json`
2. `task_request.json`
3. `runtime_plan.json`
4. `summary.json` 或 `doctor_summary.json`
5. component log files

如果缺文件：

- TUI 显示 missing artifact。
- 不 panic。
- 允许用户继续查看已有 artifact。

这个能力对调试 CI artifact 和远程机器日志很重要。

## 和 contracts/proto 的关系

TUI 不是新的 contract owner。

TUI 读取和展示：

- `orchestration.v1.TaskRequest`
- `runtime.v1.RuntimePlan`
- `runtime.v1.ProcessEvent`
- `orchestration.v1.TaskResult`
- `orchestration.v1.ArtifactManifest`

当前 Go sim reader 已切换到 `contracts/gen/go` 的 generated Go 类型，并用
`protojson` 读取 proto-compatible JSON。旧 `doctor_summary.json` 仍作为 legacy
fallback 读取，直到 task doctor artifact 完整切到 `doctor_result.json`。

## 和 Rust real 的关系

sim 和 real 应保持一致的操作体验：

```text
run / doctor / task-doctor / artifact replay
status / blockers / logs / artifacts
```

但不要共享代码：

- Go sim 使用 Bubble Tea。
- Rust real 使用 ratatui/crossterm。
- 二者共享 contract schema 和 artifact semantics。

这样未来拆仓库时，sim 和 real 可以独立演进 UI，但输出和回看格式仍一致。

## TODO

### Phase 1: Replay-only TUI

- [x] 新增 `navlab-sim tui <artifact-dir>`。
- [x] 读取 manifest、task request、runtime plan、summary。
- [x] 如果 live summary 缺失，回退读取 `doctor_summary.json`。
- [x] 展示 runtime、artifacts、blockers、logs 的第一版 dashboard。
- [x] artifact 缺失时显示 missing，不 panic。
- [x] 不接 live runner，避免 Docker/ROS 副作用。
- [x] 为 artifact replay reader 和 view model 增加 Go 单元测试。

价值：没有运行副作用，最容易测试。

### Phase 2: Dry-run TUI

- [x] 支持 `navlab-sim run <task> --dry-run --tui`。
- [x] 使用现有 prepare path 生成 artifact。
- [x] 生成 artifact 后直接进入 replay view。
- [x] 无 TTY 时给出明确错误，不改变默认 plain output。

价值：验证 CLI 和 artifact 连接。

### Phase 3: Live event stream

- [x] 给 runtime runner 增加 `RuntimeEventSink`。
- [x] Docker service/probe/rosbag 执行时发送事件。
- [x] TUI 实时更新 service、probe、rosbag 状态。
- [x] summary 写入后把最终 task result 展示在 dashboard。

价值：真正解决“慢慢输出结果”的问题。

### Phase 4: Log tail and blocker focus

- [x] 支持 component log tail。
- [x] blocker 出现时自动高亮 Gates panel。
- [x] 支持按组件切换日志。
- [x] 日志缓存限量，避免长时间 run 占用过多内存。

### Phase 5: Real/sim UX alignment

- [x] 对齐 real TUI 的状态命名。
- [x] 对齐 real TUI 的核心快捷键。
- [x] 对齐 artifact replay 的读取语义。
- [x] 根据 shared contract 切换到 generated Go 类型。

## 测试策略

Go 单元测试：

- event reducer：输入 event，检查 model state。
- artifact replay reader：缺文件、坏 JSON、完整 artifact 三种路径。
- key binding：tab、enter、q、b 等。

CLI 测试：

- `navlab-sim tui <artifact-dir>` 对 golden artifact 可启动 replay model。
- `run --dry-run --tui` 在测试模式下生成 artifact 并构建 model。

非交互测试：

- 无 TTY 时 `--tui` 给出明确错误。
- plain output 行为不变。

人工验证：

- hover dry-run artifact replay。
- hover live run 观察 service/probe/rosbag 状态变化。
- 中断 TUI 后 terminal restore 正常。

## 风险和约束

- Bubble Tea 引入事件循环后，不能让 runtime execution 和 UI update 互相阻塞。
- Docker logs 可能很大，必须做 tail 缓存。
- TUI 退出时不能误杀仍需要 cleanup 的 Docker service。
- CI 默认不能进入 TUI。
- TUI 不应该吞掉原始错误；最终错误仍要写入 summary/task_result。

## 推荐结论

Go sim 应该做 TUI，但第一版应从 replay-only 开始，再接 dry-run，最后接 live event
stream。

原因：

- replay-only 可以快速验证布局和 artifact contract。
- dry-run TUI 可以复用现有 artifact writer。
- live TUI 最有价值，但需要 runner event sink，应该在前两个阶段稳定后再接。

最终目标是：

```text
plain CLI 适合 CI 和脚本
TUI 适合本地运行和现场调试
JSON/proto artifacts 适合回放、审计、跨语言读取
```
