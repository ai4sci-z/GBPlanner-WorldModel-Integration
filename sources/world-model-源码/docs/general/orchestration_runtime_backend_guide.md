# Orchestration Runtime Backend Guide

## 目标

`orchestration` 负责 host 侧编排：启动服务、运行 probe、录制 rosbag、收集日志、写 summary。Runtime backend 把这些动作和具体运行方式解耦。

当前支持两种 backend：

- `docker`：默认 backend，用 Docker/compose/python_on_whales 跑现有 NavLab 仿真和验收主线。
- `process`：显式 opt-in 的 host process backend，用于后续算力盒子/真机旁路调试；当前只完成基础 manager 和 adapter，不作为默认验收路径。

注意：backend 只表示生命周期管理方式。真实/仿真边界由 `runtime.mode` 表达。当前只支持两条主线：

- `docker + simulation`：built-in hover、P8 exploration 和 scan robustness 仿真验收。
- `process + real`：算力盒子/真实无人机路径。

`process + simulation` 和 `docker + real` 当前都直接视为非法配置。

## 选择规则

默认：

```bash
uv run --project orchestration python orchestration/main.py run scan-robustness
```

等价于：

```bash
NAVLAB_RUNTIME_BACKEND=docker NAVLAB_RUNTIME_MODE=simulation \
uv run --project orchestration python orchestration/main.py run scan-robustness
```

显式 process real：

```bash
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real uv run --project orchestration python orchestration/main.py doctor
```

process backend 要求 `[orchestration.runtime.process.services]` 显式配置服务命令。没有配置时必须 fail，不允许自动 fallback 到 Docker。

## 配置位置

主配置按 runtime mode 拆分：

```toml
[orchestration.runtime]
backend = "docker"
mode = "simulation"
fail_on_missing_backend_config = true
fail_on_mode_violation = true

[orchestration.runtime.docker]
workspace_container_path = "/workspace"

[orchestration.runtime.process]
workspace_host_path = "."
log_dir = "artifacts/runtime_logs"
require_explicit_services = true
```

环境变量 `NAVLAB_RUNTIME_BACKEND` 和 `NAVLAB_RUNTIME_MODE` 优先级高于配置文件。

## DockerBackend 边界

DockerBackend 负责：

- compose up/stop/logs/ps
- service container start/wait/stop/logs
- one-shot probe container
- Docker remove/execute
- Docker exception 包装为 backend error

DockerBackend 不负责：

- 判断 SLAM 是否健康
- 判断 FCU owner 是否唯一
- 判断 scan 是否安全
- 修改 built-in scan robustness gate 语义

这些仍属于 task/gate 层。

## ProcessBackend 边界

ProcessBackend 只做 `ServiceSpec/ProbeSpec/RosbagSpec -> ProcessManager` 的适配。

`orchestration/src/runtime/process_manager.py` 是 host 侧 process manager，负责：

- `subprocess.Popen`
- `cwd/env/log_path/start_new_session`
- process group terminate/kill
- wait 和 log tail
- captured one-shot probe

ProcessBackend 不直接持有 `subprocess.Popen`。这样后续要换成 systemd、supervisord 或 ROS launch wrapper 时，可以优先替换 manager 层，不改 gate contract。

## Summary 字段

P10/P11/P12 doctor/acceptance summary 顶层记录：

```json
{
  "runtime_backend": "docker",
  "runtime_mode": "simulation",
  "runtime_backend_summary": {
    "backend": "docker",
    "mode": "simulation",
    "backend_source": "config.toml",
    "mode_source": "config.toml",
    "backend_config_path": "orchestration/config.toml",
    "fail_on_missing_backend_config": true,
    "fail_on_mode_violation": true
  }
}
```

P10/P11/P12 rosbag profile summary 记录：

```json
{
  "rosbag_backend": "docker",
  "runtime_mode": "simulation"
}
```

后续如果 disturbed replay 采用“Docker 生成 + process 分析”，应继续区分：

- `generation_backend`
- `analysis_backend`

避免把 `runtime_backend=process` 误解成仿真生成也由 process backend 完成。

## 常见错误

### unknown backend

现象：`NAVLAB_RUNTIME_BACKEND=unknown` 直接 fail。

原因：backend 名称只能是 `docker` 或 `process`。

处理：修正环境变量或删除环境变量使用默认 Docker。

### invalid backend/mode combination

现象：`NAVLAB_RUNTIME_BACKEND=process` 但没有设置 `NAVLAB_RUNTIME_MODE=real`，或配置了 `docker + real`，直接 fail。

原因：当前只支持 `docker+simulation` 和 `process+real`，避免把 host process 调试路径误判成真机，或把容器化路径误判成真实硬件路径。

处理：仿真验收使用 `docker + simulation`；算力盒子/真机使用 `process + real`。

### process backend missing services

现象：`NAVLAB_RUNTIME_BACKEND=process` 直接 fail。

原因：`require_explicit_services=true`，但没有配置 process services。

处理：在 `[orchestration.runtime.process.services.<name>]` 中写明确命令；不要期待 fallback 到 Docker。

### path mapping error

现象：process backend 拒绝 `/workspace/...`。

原因：`/workspace` 是 container-only path，process backend 必须使用 host path。

处理：通过 runtime path mapping 或 host absolute path 传入。

### topic missing

现象：backend 启动成功，但 gate blocker 报 required topic missing。

原因：backend 只负责进程/容器生命周期，topic 健康仍由 gate 层判断。

处理：检查对应 service log、rosbag profile 和 summary blocker。

## 当前完成状态

已完成：

- RuntimeBackend / ServiceSpec / ProbeSpec / RosbagSpec 基础 schema
- DockerBackend 基础封装
- ProcessManager + ProcessBackend 基础封装
- P10/P11 rosbag recorder 迁移样板
- ROS shell probe 迁移样板
- companion / SLAM / official baseline service launcher 迁移样板
- P10/P11/P12 summary runtime backend 字段
- runtime mode 配置、summary 字段和 mode violation 单测
- `docker+simulation` / `process+real` 两条主线组合校验
- real mode 下 simulation-only service/source/overlay guard

暂缓：

- Debian/算力盒子 process backend smoke
- ProcessBackend offline MCAP replay
- P12 Docker generation + process analysis split

暂缓原因：当前执行环境不是目标算力盒子；不能把未跑过的 process smoke 标成真机可用。
