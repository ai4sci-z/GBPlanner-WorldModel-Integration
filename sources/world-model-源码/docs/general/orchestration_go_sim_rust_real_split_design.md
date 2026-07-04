# Orchestration Go Sim / Rust Real Split Design

## 1. 背景

当前 `orchestration` 是 Python 实现，主要服务前期快速开发：

- 统一 CLI。
- Docker/SITL/Gazebo 仿真验收。
- process backend 真机预检。
- doctor、artifact、summary、rosbag 等控制面流程。

这个 Python orchestration 不再作为长期主线。后续目标不是继续重构
Python package，而是直接把 orchestration 控制面拆成两个独立实现：

```text
simulation orchestration -> Go
real orchestration       -> Rust
```

`navlab` runtime 节点仍可以继续是 Python。这里要替换的是
`orchestration` 控制面，不是立即重写所有 ROS/MAVLink runtime 节点。

## 2. 核心决策

`orchestration` 按 sim 和 real 两条线拆分，不做 Python 级 shared
implementation。

```text
orchestration/sim   # 仿真控制面，Go 实现
orchestration/real  # 真机控制面，Rust 实现
```

当前仓库里的 Python `orchestration` 只作为迁移参考和旧流程兼容，不继续扩大
为长期框架。

### 不再采用的方向

不再把 Python orchestration 重构成：

```text
orchestration/src/common/
orchestration/src/sim/
orchestration/src/real/
```

原因：

- `common` 会制造实现级耦合，后续拆成两个仓库时还要再拆一次。
- Go sim 和 Rust real 不能依赖同一套 Python helper。
- 真机安全边界不应该被仿真 helper、Docker helper、Gazebo helper 间接污染。
- 两个未来仓库需要快速独立适配，而不是维护一个共享控制面抽象。

## 3. 目标边界

### Sim orchestration

Sim orchestration 由 Go 实现，面向仿真和可复现实验：

- Gazebo。
- SITL。
- Docker/compose 服务管理。
- official baseline。
- 仿真 lidar/rangefinder/IMU。
- SDF overlay。
- airframe disturbance / ESC lag / motor bias profile。
- P8/P9/P10/P11/P12 仿真验收。
- 仿真 rosbag 和 Foxglove replay 生成。

Sim orchestration 可以继续调用现有 Python runtime 节点，例如：

```text
navlab.sim.*
navlab.common.slam.*
```

但调用方式必须是进程边界、CLI、配置文件、ROS topic 或 artifact 文件，不依赖
Python import。

### Real orchestration

Real orchestration 由 Rust 实现，面向真实无人机和算力盒子：

- host process 管理。
- 真实 FCU 连接。
- 真实 lidar / IMU / rangefinder topic 检查。
- real preflight。
- real prepare。
- real common doctor。
- real task doctor。
- operator safety confirmation。
- 真机 artifact、日志和 summary。

Real orchestration 禁止包含：

- Gazebo。
- SITL。
- official baseline。
- SDF overlay。
- simulation profile。
- Gazebo truth。
- 仿真 sensor runtime。
- 仿真 topic 作为 gate 输入。

Real orchestration 可以继续调用现有 Python runtime 节点，例如：

```text
navlab.real.companion.nodes.*
navlab.real.common.*
```

但同样只能通过进程、CLI、配置、ROS topic 或 artifact 文件调用。

## 4. 保留 Task Registry Pattern

Task registry 是 orchestration 的扩展机制，必须保留。

保留的是 pattern，不是 Python implementation。Go sim 和 Rust real 各自实现
自己的 registry：

```text
orchestration-sim/
  internal/tasks/registry.go
  internal/tasks/exploration.go
  internal/tasks/scan_robustness.go

orchestration-real/
  src/tasks/registry.rs
  src/tasks/motor_debug.rs
  src/tasks/preflight.rs
```

registry 至少负责：

- task id 到 handler 的映射。
- task metadata。
- 参数 schema 或参数 contract。
- doctor / prepare / run / collect artifact 生命周期。
- task capability 和 required source 声明。
- summary producer 声明。

sim 和 real 的 registry 结构应保持同构，方便快速扩展和排查问题。但 registry
代码不跨语言共享，也不放进 Python `common`。

新增任务时的目标流程：

```text
新增 sim task:
  1. 写 Go task module
  2. 注册到 Go sim registry
  3. 绑定 config/proto contract
  4. 输出标准 artifact/summary

新增 real task:
  1. 写 Rust task module
  2. 注册到 Rust real registry
  3. 绑定 safety/doctor/proto contract
  4. 输出标准 artifact/summary
```

## 5. 共享内容只允许是 Contract

sim 和 real 不共享 implementation。允许共享的只有语言无关 contract。

推荐保留或新增：

```text
contracts/
  proto/
  schemas/
  cli/
  docs/
```

这些 contract 定义：

- task result schema。
- summary schema。
- artifact 目录和文件命名规则。
- exit code 语义。
- task id 命名。
- task registry metadata。
- runtime source claim 字段。
- ROS topic contract。
- safety confirmation 字段。

不允许把这些东西做成 Python `common` helper 让两边 import。Go 和 Rust 都应
各自实现 contract 的读写、校验和错误处理。

## 6. 共享逻辑与分离逻辑

sim 和 real 应共享 orchestration 设计语言，但不共享实现代码。

应保持一致的逻辑：

- task registry pattern。
- task lifecycle。
- task id 命名。
- config precedence 规则。
- artifact 目录规则。
- summary 字段。
- exit code 语义。
- doctor result 格式。
- error/blocker/warning 分类。
- 日志和 trace 字段。

必须分开的逻辑：

- backend 管理。
- mode gate。
- runtime service 启动。
- safety boundary。
- source claim 校验。
- 真实硬件权限。
- 仿真环境生成。

Go sim 和 Rust real 应该看起来像同一套 orchestration 思路的两个实现，而不是
两个无关工具。但一致性来自 contract 和设计约束，不来自共享 Python helper。

## 7. Proto 与参数读取

大量跨语言边界应使用 proto 约束，尤其是 Go sim、Rust real、Python `navlab`
runtime 会同时存在的阶段。

推荐分层：

```text
人写配置:
  TOML/YAML

读取后规范化结构:
  Proto message

orchestration 与 runtime 边界:
  Proto JSON / binary protobuf / artifact file

运行结果:
  Proto result schema，再按需要落 JSON 或 pb
```

不要把所有人手编辑配置都改成 proto。TOML/YAML 仍适合放本机路径、设备名、
Docker image tag、profile sweep 和临时开发开关。proto 用来约束读取后的稳定
结构。

适合 proto 化的结构：

- `TaskMetadata`。
- `TaskRequest`。
- `RuntimePlan`。
- `DoctorRequest`。
- `DoctorResult`。
- `TaskResult`。
- `ArtifactManifest`。
- `SafetyConfirmation`。
- `RuntimeSourceClaims`。
- `ExitStatus`。

示例：

```proto
message TaskRequest {
  string task_id = 1;
  RuntimeMode runtime_mode = 2;
  double duration_sec = 3;
  string artifact_dir = 4;
  RuntimeSourceClaims source_claims = 5;
}

message RuntimeSourceClaims {
  string scan_source = 1;
  string imu_source = 2;
  string fcu_source = 3;
  string rangefinder_source = 4;
}

message TaskResult {
  string task_id = 1;
  RuntimeMode runtime_mode = 2;
  TaskStatus status = 3;
  repeated string blockers = 4;
  repeated Artifact artifacts = 5;
}
```

参数读取目标：

```text
TOML/YAML config
  -> Go/Rust 各自读取
  -> normalize / validate
  -> 转成 proto request 或 runtime plan
  -> 传给 Python navlab runtime 或写 artifact
  -> runtime 写 proto result
```

这样可以保留快速编辑配置的便利，同时让跨语言边界可测试、可版本化、可迁移。

## 8. 仓库拆分目标

长期目标是两个 orchestration 仓库，而不是一个多语言 monorepo 控制面。

```text
orchestration-sim/
  go.mod
  cmd/navlab-sim/
  internal/
    config/
    docker/
    gazebo/
    sitl/
    tasks/
    artifacts/

orchestration-real/
  Cargo.toml
  src/
    main.rs
    config/
    process/
    preflight/
    doctor/
    safety/
    artifacts/
```

当前 `world-model` 仓库可以先承载迁移过程，但目录设计应该按未来拆仓库来
推进，不再引入跨 sim/real 的 Python implementation。

## 9. 当前仓库过渡形态

当前仓库先采用并置结构，后续可以直接拆成两个仓库：

```text
orchestration/
  sim/
    go.mod
    config.toml
    cmd/navlab-sim/main.go
    configs/
      tasks/

  real/
    Cargo.toml
    config.toml
    src/main.rs
    configs/
      tasks/

  legacy-python/
    # 当前 Python orchestration 迁到这里，作为旧实现参考
```

或者在没有立即移动旧代码前，先约定：

```text
orchestration/src/
```

是 legacy Python orchestration，不再接受新的长期控制面抽象。新能力优先进入
`sim` 或 `real`。

## 10. CLI 目标

最终 CLI 应该分开：

```bash
navlab-sim doctor
navlab-sim run exploration
navlab-sim run scan-robustness
navlab-sim build images

navlab-real doctor
navlab-real prepare
navlab-real run motor-debug
navlab-real preflight
```

不再依赖一个 Python CLI 根据 `runtime.mode` dispatch。`runtime.mode` 可以保留
在 summary 和 config contract 中，但不应该继续作为一个混合 orchestration 的
核心架构。

## 11. 配置目标

sim 和 real 配置分离。项目级 `config.toml` 放在各自包根目录，`configs/`
只放 task 等分层配置。

```text
orchestration/sim/config.toml
orchestration/sim/configs/tasks/*.yaml

orchestration/real/config.toml
orchestration/real/configs/tasks/*.yaml
```

或者未来拆仓库后：

```text
orchestration-sim/config.toml
orchestration-real/config.toml
```

不要设计一个共享 Python config loader。重复少量字段解析是可以接受的，因为
两边语言、部署环境和安全约束不同。

配置读取可以保持同构：

```text
defaults
  -> config file
  -> env override
  -> CLI override
  -> normalized proto request
```

但 Go sim 和 Rust real 各自实现这套 precedence，不共享代码。

## 12. Artifact 目标

artifact contract 可以共享，但写入实现分开。

示例：

```text
artifacts/
  sim/
    exploration/
    scan_robustness/

  real/
    preflight/
    prepare/
    motor_debug/
```

summary 必须能直接看出来源：

```json
{
  "orchestration_family": "sim",
  "orchestration_implementation": "go",
  "runtime_mode": "simulation"
}
```

```json
{
  "orchestration_family": "real",
  "orchestration_implementation": "rust",
  "runtime_mode": "real"
}
```

## 13. 迁移顺序

推荐迁移顺序：

1. 固化 contract。
   - task result schema。
   - summary fields。
   - artifact path rules。
   - exit codes。
   - task registry metadata schema。
   - task request / doctor result proto。

2. 建 Go sim orchestration 最小入口。
   - `doctor`。
   - `run scan-robustness` 或当前最重要的仿真任务。
   - Docker/Gazebo/SITL 只进入 Go sim。

3. 建 Rust real orchestration 最小入口。
   - `doctor`。
   - `preflight`。
   - `prepare`。
   - `run motor-debug`。
   - 真机 safety gate 只进入 Rust real。

4. 把 Python orchestration 标记为 legacy。
   - 不再新增长期任务。
   - 只用于对照旧行为和迁移期间兜底。

5. 逐步删除 Python orchestration 入口。
   - `just` 命令切到 Go/Rust。
   - 文档切到 Go/Rust。
   - Python orchestration 只保留到迁移完成。

## 14. 新代码放置规则

从这个设计生效后：

- 新仿真 orchestration 能力进入 Go sim。
- 新真机 orchestration 能力进入 Rust real。
- 不新增 `orchestration/src/common`。
- 不新增跨 sim/real 的 Python helper。
- 不把 Gazebo/SITL/Docker helper 放进 real。
- 不把真机 safety/FCU 权限逻辑放进 sim。
- `navlab` Python runtime 可以继续存在，但 orchestration 只能通过进程边界调用。

## 15. 可优化点

后续迁移时可以优先优化这些地方。

### Contract versioning

proto 应带版本路径和版本字段：

```text
contracts/proto/navlab/orchestration/v1/
```

summary 中记录 contract version，避免 Go sim、Rust real、Python runtime 版本不
一致时静默误读。

### Task capability model

registry metadata 应显式声明 task 能力和需求：

```text
capabilities:
  needs_gazebo
  needs_sitl
  needs_real_fcu
  needs_real_scan
  writes_task_result
  records_rosbag
```

这样 doctor 可以从 task metadata 自动推导部分检查，而不是每个 task 手写重复
gate。

### Source claim validation

real 和 sim 都应输出 source claim，但语义不同：

- sim 证明数据来自 Gazebo/SITL 仿真链路，且 truth 没有进入控制输入。
- real 证明数据来自真实 FCU/真实 sensor/真实 SLAM 链路。

source claim 应进入 `TaskRequest` 和 `TaskResult`，并在 summary 中可见。

### Artifact manifest

每次 task 结束后写一个标准 manifest：

```text
manifest.json 或 manifest.pb
```

manifest 记录 artifact path、type、producer、sha256、created_at、contract
version。这样后续 replay、上传、对比实验不用猜文件名。

### Golden contract tests

为 proto JSON 准备 golden examples：

```text
contracts/examples/sim_task_request.json
contracts/examples/real_task_result.json
contracts/examples/doctor_result_blocked.json
```

Go、Rust、Python 都跑同一批 encode/decode 测试，防止跨语言字段漂移。

### Error taxonomy

统一 blocker/warning/error code：

```text
CONFIG_INVALID
SOURCE_MISSING
MODE_VIOLATION
SAFETY_CONFIRMATION_MISSING
RUNTIME_PROCESS_FAILED
ARTIFACT_MISSING
```

人看的 message 可以各实现不同，但机器读的 code 必须稳定。

### Legacy parity checklist

迁移 Python orchestration 时，每个 task 应有 parity checklist：

- CLI 参数是否覆盖。
- config precedence 是否一致。
- summary 字段是否一致。
- artifact 是否可被旧工具读取。
- exit code 是否一致。
- doctor blocker 是否一致或明确改变。

### Delete criteria

Python orchestration 不应无限期保留。每个 legacy task 应有删除条件：

- Go sim 或 Rust real 已覆盖主路径。
- contract examples 已补齐。
- 至少一个真实命令或仿真命令跑通。
- 文档和 `just` 入口已切换。

## 16. 和现有文档的关系

已有文档中的 `runtime.mode = simulation | real` 判断仍然有用，但它主要描述
旧 Python orchestration 内部如何避免混用仿真和真机。

本设计进一步明确：长期形态不是一个 Python orchestration 加 mode 分支，而是
两个独立 orchestration：

```text
sim  -> Go
real -> Rust
```

因此后续设计、todo 和实现应优先服务这个拆分目标。
