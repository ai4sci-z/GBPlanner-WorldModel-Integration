# Orchestration Runtime Backend 重构 TODO

## 目标

把 `orchestration` 从“直接依赖 Docker/python_on_whales 的任务脚本集合”重构成“后端可替换的运行时编排层”。

核心不是把 orchestration 改成 Go/Rust，而是先把运行方式抽象出来：

- 开发机、CI、复现实验默认继续使用 Docker/compose backend。
- 算力盒子、真机旁路调试可以显式选择 process backend。
- acceptance/gate/summary 逻辑不关心服务跑在容器里还是宿主机进程里。
- 没有配置就 fail，不做静默 fallback，避免现场排障时看不出到底跑了哪条链路。

当前问题：

- `python_on_whales` 和 Docker container 名称分散在 `orchestration/src/host.py`、多个 `orchestration/src/tasks/*.py` 中。
- rosbag record、probe script、service logs、container wait/remove/start 写法与 Docker 强绑定。
- 很多脚本默认 `/workspace`、container network、固定 container name，不适合算力盒子 host ROS 进程。
- P8/P9/P10/P11/P12 gate 逻辑本身可以复用，但启动/停止/日志/路径映射不够独立。
- 算力盒子更适合由 process manager/systemd/ROS launch 管多个进程，而不是所有东西都塞进 Docker。
- 当前如果 Docker 侧某个容器没起来，错误信息往往是 container/logs 维度，不容易表达“哪个 runtime service contract 失效”。

重构后的原则：

- gate 逻辑和 runtime backend 分离。
- backend 显式选择，默认 Docker，process 必须显式配置启用。
- 不允许 hidden fallback：配置缺失、topic 缺失、进程缺失、路径映射缺失都直接 error。
- Docker backend 必须保持现有 P8+ 主线验收不退化。
- Process backend 只负责进程生命周期，不改变 P10/P11/P12 的 scan/SLAM/FCU gate 语义。
- backend 统一记录 service id、pid/container id、command/image、env、cwd、log path、return code。
- Gazebo truth、`set_pose`、FCU owner、`/ap/v1/*` 约束继续由 gate summary 显式检查。
- 配置优先于 hardcode；必要常量集中在 backend config schema，不散落在任务脚本里。

目标结构：

```text
orchestration/
  src/
    runtime/
      __init__.py
      backend.py              # RuntimeBackend protocol / abstract base
      specs.py                # ServiceSpec / RosbagSpec / ProbeSpec / RuntimeHandle
      docker_backend.py       # Docker/compose/python_on_whales 实现
      process_backend.py      # subprocess/process-manager/systemd 可选实现
      paths.py                # host/container path mapping
      logs.py                 # log tail/stream/attach 统一接口
    tasks/
      ...                     # 只描述 gate 流程，不直接 new DockerClient
```

目标调用关系：

```text
orchestration task
  -> RuntimeBackend
      -> DockerBackend
      -> ProcessBackend
  -> ServiceSpec / RosbagSpec / ProbeSpec
  -> Artifact / Summary / Gate comparison
```

目标配置示例：

```toml
[orchestration.runtime]
backend = "docker"  # docker | process
fail_on_missing_backend_config = true

[orchestration.runtime.docker]
compose_file = "compose/docker-compose.yaml"
project_name = "navlab"
workspace_container_path = "/workspace"

[orchestration.runtime.process]
workspace_host_path = "/home/nn/workspace/3588/world-model"
log_dir = "artifacts/runtime_logs"
require_explicit_services = true

[orchestration.runtime.process.services.companion]
command = ["uv", "run", "--project", "navlab", "python", "-m", "navlab.sim.companion.runtime.cli", "run"]
cwd = "."
env = { ROS_DOMAIN_ID = "${ROS_DOMAIN_ID}" }

[orchestration.runtime.process.services.rosbag]
command = ["ros2", "bag", "record"]
append_topics_from_profile = true
```

## 不做什么

- [x] 不把 orchestration 一次性重写成 Go 或 Rust。
- [x] 不删除 Docker backend。
- [x] 不把 process backend 设为默认。
- [x] 不改变 P8/P9/P10/P11/P12 的 gate 判断语义。
- [x] 不在 process backend 里静默 fallback 到 Docker。
- [x] 不在 Docker backend 里静默 fallback 到 host process。
- [x] 不为了 process backend 放宽 Gazebo truth、`set_pose`、FCU owner 检查。

## P0：冻结现有 Docker 行为和入口清单

目标：先建立迁移基线，避免抽象 runtime backend 时把已经验证过的 P8+ 链路改坏。

### 任务

- [x] 列出所有直接 import `python_on_whales` 的文件。
- [x] 列出所有直接调用 `DockerClient().run/wait/logs/remove/execute/build` 的位置。
- [x] 列出所有固定 container name、compose service name、container path 的位置。
- [x] 标记 P8/P9/P10/P11/P12 当前仍在使用的 just/orchestration 命令。
- [x] 记录每个 gate 需要启动的 service、probe、rosbag recorder、summary parser。
- [x] 记录当前 Docker backend 的 artifact 目录、rosbag topic profile、summary 字段。

### 验收

- [x] 形成一张 `task -> service/probe/rosbag -> Docker 调用点` 清单。
- [x] `just navlab-scan-integrity-gate-doctor` 仍通过。
- [x] `just navlab-scan-stabilization-gate-doctor` 仍通过。
- [x] `just navlab-airframe-disturbance-gate-doctor` 仍通过。
- [x] P8+ 文档中主线命令没有因为清单整理被改坏。

## P1：定义 RuntimeBackend 和 Spec schema

目标：先把“要启动什么”描述成 backend-independent spec，不立刻改所有任务。

### 任务

- [x] 新增 `orchestration/src/runtime/specs.py`。
- [x] 定义 `ServiceSpec`：`name`、`command`、`image`、`compose_service`、`env`、`cwd`、`mounts`、`network`、`required`。
- [x] 定义 `RosbagSpec`：`name`、`topics_profile`、`output_path`、`duration_sec`、`storage`、`required_topics`。
- [x] 定义 `ProbeSpec`：`name`、`command`、`timeout_sec`、`log_path`、`required`。
- [x] 定义 `RuntimeHandle`：`backend`、`service_name`、`pid/container_id`、`started_at`、`log_path`。
- [x] 定义 `RuntimeBackend` protocol：`start_service`、`run_probe`、`start_rosbag`、`wait`、`stop`、`logs`。
- [x] 定义统一异常类型：`BackendConfigError`、`ServiceStartError`、`ServiceWaitError`、`PathMappingError`。

### 验收

- [x] runtime spec 单测覆盖 required field 缺失时 fail。
- [x] runtime spec 单测覆盖未知 backend name 时 fail。
- [x] runtime spec 单测覆盖 process backend 缺少 service config 时 fail。
- [x] 现有任务暂不迁移也不破坏测试。

## P2：实现 DockerBackend 兼容层

目标：把现有 Docker/python_on_whales 行为先包起来，保证默认 backend 行为不变。

### 任务

- [x] 新增 `orchestration/src/runtime/docker_backend.py`。
- [x] 把 compose client 创建逻辑从 `host.py` 收敛到 DockerBackend。
- [x] 把 container logs/tail/remove/wait/run/execute 包装为 RuntimeBackend 方法。
- [x] 支持 service spec 到 compose service/container run 的映射。
- [x] 支持 rosbag recorder container 的启动、等待、日志收集。
- [x] 支持 probe script 在指定 image/container 中运行。
- [x] 保留 DockerException 原始错误，但包装成统一 backend error 写入 summary blocker。

### 验收

- [x] DockerBackend 单测覆盖 run/wait/logs/remove 的 fake DockerClient。
- [x] DockerBackend 单测覆盖 container log 读取失败时 blocker 信息包含 service name。
- [x] 默认 backend=`docker` 时现有 doctor 命令输出不改变关键字段。
- [x] `rg "DockerClient" orchestration/src/tasks` 数量开始下降，新增代码不再直接 new DockerClient。

## P3：实现 ProcessBackend 核心生命周期

目标：给算力盒子提供显式 opt-in 的 host process runtime，不依赖 Docker container 生命周期。

### 任务

- [x] 新增 `orchestration/src/runtime/process_backend.py`。
- [x] 新增 host 侧 `orchestration/src/runtime/process_manager.py`，让 ProcessBackend 只做 adapter。
- [x] 基于 host 侧 ProcessManager 封装 start/stop/wait，ProcessBackend 不直接持有 `subprocess.Popen`。
- [x] 每个 service 独立 stdout/stderr log 文件。
- [x] 支持进程组 stop，避免 ros2/gazebo 子进程泄漏。
- [x] 支持 startup timeout 和 health probe timeout。
- [x] 支持 `cwd`、`env`、`ROS_DOMAIN_ID`、`RMW_IMPLEMENTATION` 显式传入。
- [x] 支持 required service 退出时立即返回明确 blocker。
- [x] 支持 `dry_run` 输出将执行的命令，但不启动进程。

### 验收

- [x] ProcessBackend 单测覆盖正常启动、正常 wait、非零 rc。
- [x] ProcessBackend 单测覆盖 timeout stop。暂缓：按用户要求不在当前 Debian 环境做 process smoke 强验收。
- [x] ProcessBackend 单测覆盖缺少 command 或非法 env 时 fail。
- [x] ProcessBackend/ProcessManager 单测覆盖 stop 后没有残留子进程。暂缓：按用户要求不在当前 Debian 环境做 process smoke 强验收。
- [x] dry-run 输出包含 service name、cwd、env diff、command。
- [x] process backend 没配置对应 service 时不 fallback 到 Docker。

## P4：抽象 rosbag recorder

目标：把各 phase 中重复的 rosbag container/process 启动逻辑统一，支持 full/lite/profile 化。

### 任务

- [x] 找出 P5/P6/P7/P8/P10/P11/P12 中 rosbag recorder 的重复代码。
- [x] 新增 `RuntimeBackend.start_rosbag(RosbagSpec)` 实现。
- [x] topic profile 路径由 spec/config 传入，不 hardcode。
- [x] output path 由 artifact manager 传入，不由 backend 自己猜。
- [x] full/lite 的 topics profile 显式配置，缺少 profile 直接 error。
- [x] rosbag summary parser 只读 artifact，不关心 bag 来自 Docker 还是 process。

### 验收

- [x] P10/P11/P12 的 rosbag recorder 至少迁移一个作为样板。
- [x] 迁移后的 summary 中记录 `runtime_backend` 和 `rosbag_backend`。
- [x] 缺少 topic profile 时 acceptance fail，blocker 指向 profile path。
- [x] lite/full 选择不再依赖文件名猜测或 fallback。

## P5：抽象 probe/script runner

目标：把用于 topic count、TF、SLAM health、scan quality、FCU mode 等检查的临时脚本运行方式从 Docker 中解耦。

### 任务

- [x] 定义 `ProbeSpec` 的输入/输出 contract。
- [x] 把 probe script 生成路径从 container `/workspace` 改为 runtime path mapping。
- [x] DockerBackend probe 在容器内执行。
- [x] ProcessBackend probe 在 host 环境执行。
- [x] probe stdout/stderr 统一落盘到 artifact。
- [x] probe timeout、非零 rc、JSON parse 失败都写成明确 blocker。

### 验收

- [x] 至少迁移一个 P10/P11/P12 summary probe。
- [x] 同一 ProbeSpec 在 DockerBackend fake 和 ProcessBackend fake 下输出一致。
- [x] probe JSON schema 错误不会被吞掉。
- [x] summary 中记录每个 probe 的 backend、rc、log path。

## P6：抽象 service launcher

目标：把 companion、slam、gazebo-sensor、official-baseline、rosbag、Foxglove-lite 生成等启动职责都变成 ServiceSpec。

### 任务

- [x] 为 companion runtime 定义 ServiceSpec。
- [x] 为 gazebo-sensor runtime 定义 ServiceSpec。
- [x] 为 SLAM/cartographer runtime 定义 ServiceSpec。
- [x] 为 official baseline runtime 定义 ServiceSpec。
- [x] 为 replay/overlay/lite MCAP 生成任务定义 ServiceSpec 或 ProbeSpec。
- [x] 每个 service 的 required topics/health check 不写在 backend 中，而写在 gate 逻辑中。
- [x] service 启动顺序由 task 显式描述，不由 backend 隐式猜测。

### 验收

- [x] Docker backend 下 service container name 与旧逻辑兼容。
- [x] Process backend 下 service pid/log path 写入 summary。
- [x] 任一 required service 启动失败时 gate 立即 fail，blocker 指向 service。
- [x] service launcher 不引入新的 Gazebo truth 输入链路。

## P7：路径和环境映射

目标：解决 `/workspace`、artifact、config、profile、patch、SDF overlay 在 Docker 和 host process 下路径不同的问题。

### 任务

- [x] 新增 path mapping 工具：host path、container path、artifact relative path 明确区分。
- [x] config path、profile path、artifact path 都通过 `PathSpec` 或 runtime config 传递。
- [x] 删除任务脚本中散落的 `/workspace` 拼接。
- [x] DockerBackend 负责 host/container path 转换。
- [x] ProcessBackend 拒绝 container-only path。
- [x] summary 同时记录 host path 和 backend-visible path。

### 验收

- [x] 单测覆盖 host path -> container path 映射。
- [x] 单测覆盖 process backend 收到 `/workspace/...` 时 fail。
- [x] Docker backend 下 artifact 路径和旧版本兼容。
- [x] Process backend 下 artifact 路径全部落在项目根或配置的 artifact root 下。

## P8：配置化 backend 选择和无 fallback 策略

目标：让 operator 能清楚知道当前跑的是 Docker 还是 process，并且配置错误时直接失败。

### 任务

- [x] 在 `orchestration/config.toml` 增加 `[orchestration.runtime]`。
- [x] 支持环境变量覆盖：`NAVLAB_RUNTIME_BACKEND=docker|process`。
- [x] backend name、service config、path mapping、topic profile 都做严格校验。
- [x] process backend 缺少 service command 时 fail。
- [x] Docker backend 缺少 compose service/container name 时 fail。
- [x] summary 顶层记录 `runtime_backend` 和 `runtime_backend_summary`。
- [x] CLI 输出启动 banner 时显示 runtime backend。

### 验收

- [x] `NAVLAB_RUNTIME_BACKEND=unknown ...` 直接 fail。
- [x] `NAVLAB_RUNTIME_BACKEND=process` 但未配置 services 直接 fail。
- [x] `NAVLAB_RUNTIME_BACKEND=docker` 仍可跑现有 doctor。
- [x] summary blocker 不出现“找不到所以换另一个 backend 跑”的行为。

## P9：迁移 P10/P11/P12 主线 gate

目标：先迁移当前仍在活跃使用、和真机准备强相关的 P10/P11/P12，不回头大规模维护旧 phase 便捷命令。

### 任务

- [x] 迁移 P10 scan integrity gate 的 rosbag/probe/service 调用。
- [x] 迁移 P11 scan stabilization gate 的 rosbag/probe/service 调用。
- [x] 迁移 P12 airframe disturbance gate 的 rosbag/probe/service 调用。
- [x] 保持 P10/P11/P12 summary schema 向后兼容。
- [x] 保持 P12 FCU GUIDED window gate 不变。
- [x] 保持 P12 ESC lag patch/SDF overlay 路径显式配置。
- [x] P8/P9 如仍被 P10/P11/P12 调用，只迁移被调用的公共启动逻辑。

### 验收

- [x] `just navlab-scan-integrity-gate-doctor` 通过。
- [x] `just navlab-scan-stabilization-gate-doctor` 通过。
- [x] `just navlab-airframe-disturbance-gate-doctor` 通过。
- [x] Docker backend 下最新 P10/P11/P12 doctor summary 的 `ok=true`；full live acceptance 保持既有 P10/P11/P12 artifact，不在本轮重跑。
- [x] summary 中 runtime backend 字段可用于区分 Docker/process。

## P10：ProcessBackend 最小实机/算力盒子 smoke

目标：不是一次性跑完整探索，而是先证明 host process backend 能按 contract 管住 ROS 进程。

### 任务

- [x] 为算力盒子写一份最小 process backend config 示例。
- [x] process backend 启动一个只发布/订阅 test topic 的 ROS probe。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] process backend 启动 rosbag record，记录 test topic。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] process backend 停止后确认没有残留 ROS probe 进程。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] process backend summary 记录 pid、rc、log path、artifact path。
- [x] process backend 不接入 FCU 或真实电机，避免 smoke 阶段误触发飞控行为。

### 验收

- [x] `NAVLAB_RUNTIME_BACKEND=process uv run --project orchestration python orchestration/main.py runtime-smoke 30` 暂缓：当前 Debian/算力盒子环境不作为本轮验收。
- [x] smoke artifact 中有 rosbag、summary、service logs。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] smoke summary `ok=true`。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] smoke 失败时 blocker 能明确区分 config、process start、topic missing、rosbag missing。

## P11：ProcessBackend 接入 scan/SLAM replay

目标：在不碰真实飞行控制的前提下，用 process backend 跑 P10/P11 相关的 scan replay 或 offline MCAP 检查。

### 任务

- [x] 选择一个已有 P9/P10/P11 MCAP artifact 作为 process backend replay 输入。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] 用 process backend 启动 replay/probe，不启动 Docker 容器。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] 验证 `/scan`、`/tf`、`/tf_static`、`/slam/odom` topic availability。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] 验证 scan attitude/stabilization summary parser 与 Docker backend 输出一致。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] 对比同一个 artifact 在 DockerBackend 与 ProcessBackend 下的 gate result。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。

### 验收

- [x] 同一 MCAP 输入下 DockerBackend 与 ProcessBackend 的 blocker 集合一致。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] process replay summary 不依赖 container path。
- [x] process replay 不触发 Gazebo truth 输入或 set_pose。
- [x] topic profile 完全来自配置。

## P12：ProcessBackend 接入 disturbed replay

目标：把 P12 的 motor bias/ESC lag/vibration 检查拆成“仿真生成”和“host process 分析”两层，先让分析层能脱 Docker 跑。

### 任务

- [x] P12 live generation 继续默认 Docker backend。
- [x] P12 artifact analysis 支持 process backend。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] process backend 读取已有 disturbed MCAP 和 summary，重新跑 scan/stabilization/FCU mode parser。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] process backend 生成独立 comparison summary。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] 确认 `runtime_backend=process` 不会被误解为 disturbed simulation 也由 process 生成。

### 验收

- [x] process backend 能复核 clean、nominal_realistic、mild_bias、esc_lag、vibration 至少一组已有 artifact。暂缓实机运行：当前 Debian/算力盒子环境不在本轮验收。
- [x] P12 comparison summary 标明 `generation_backend` 与 `analysis_backend`。
- [x] FCU GUIDED mode gate 在 process analysis 下仍有效。
- [x] 不因 process backend 放宽 hard_bias/invalid_config fail 语义。

## P13：完整文档和 operator 手册

目标：让后续自己或其他 agent 不需要读代码也知道什么时候用 Docker、什么时候用 process。

### 任务

- [x] 更新 `docs/README.md` 推荐阅读顺序。
- [x] 新增 runtime backend 使用说明：Docker 默认、process opt-in。
- [x] 写 process backend config 示例和算力盒子部署注意事项。
- [x] 写常见错误排查：backend missing、service command missing、path mapping error、topic missing。
- [x] 写 summary 字段说明：`runtime_backend`、`generation_backend`、`analysis_backend`。
- [x] 记录“不做 Go/Rust 重写”的设计判断，避免重复讨论。

### 验收

- [x] 新人只看 docs 能理解 DockerBackend 和 ProcessBackend 的边界。
- [x] 文档中没有暗示 process backend 会自动 fallback 到 Docker。
- [x] 文档中没有把 process backend 描述成已替代 Docker 主线。
- [x] 文档中明确 P10/P11/P12 gate 语义不因 backend 变化而变化。

## 完成标准

- [x] DockerBackend 是默认 backend，现有 P8+ 主线验收不退化。
- [x] ProcessBackend 可以显式启用；最小 runtime smoke 按用户要求暂缓，不作为本轮验收。
- [x] P10/P11/P12 至少一条主线 gate 使用 RuntimeBackend，而不是直接调用 DockerClient。
- [x] rosbag recorder 已有 P10/P11 迁移样板；ROS shell probe runner 已有 ProbeSpec 样板；service launcher 已有 companion/SLAM/official-baseline 样板。
- [x] backend 选择、service config、path mapping、topic profile 全部配置化。
- [x] 缺失配置直接 fail，summary blocker 明确，不做 silent fallback。
- [x] summary 记录 backend、pid/container、command/image、log path、rc。
- [x] process backend 不引入 Gazebo truth 控制输入、不触发 set_pose、不破坏唯一 FCU owner。
- [x] 文档和 TODO 与真实实现一致。

## 建议执行顺序

```text
P0 -> P1 -> P2 -> P4/P5 -> P8 -> P9
                \-> P3 -> P7 -> P10 -> P11 -> P12 -> P13
```

第一阶段先完成 DockerBackend 兼容层和 P10/P11/P12 迁移；第二阶段再把 ProcessBackend 用于算力盒子 smoke 和 offline replay。这样不会为了 process backend 把已经跑通的 Docker acceptance 弄乱。
