# Orchestration Config Precedence and Split 设计

## 背景

历史上的 `orchestration/config.toml` 同时承载了多类配置：

- runtime backend / mode。
- Docker/process runtime system config。
- real source contract。
- task 参数，例如 hover / P8 / P12 的 duration、profile、阈值和 landing。
- FCU controller、SLAM、sensor、rosbag profile、Foxglove 等阶段配置。

这会导致两个问题：

1. 真机/仿真边界不够显式。`runtime.mode` 如果来自某个 TOML 文件，操作者不看
   shell 命令就很难确认当前是不是 `real`。
2. task 参数和 system 参数混在一个大文件里。hover、P8、P12 后续都要有 Stage 1
   和 Stage 2，继续放在一个 `config.toml` 会越来越难审计。

因此需要把配置拆成两层：

```text
orchestration config: runtime/system/source boundary
task config: task behavior and acceptance parameters
```

同时把参数优先级固定下来，避免每个 CLI、环境变量和配置文件各走一套规则。

## 核心判断

最终规则应当是：

```text
runtime backend/mode:
  NAVLAB_RUNTIME_BACKEND / NAVLAB_RUNTIME_MODE > hard-code default

orchestration config path:
  CLI --orchestration-config > mode-derived default

task config path:
  CLI --task-config > orchestration/configs/<task-name>.toml

task invocation params:
  CLI arg/option > task config > hard-code default

system/task internals:
  task config or orchestration config > hard-code default
```

其中只有两个环境变量能影响 orchestration 行为：

```text
NAVLAB_RUNTIME_BACKEND
NAVLAB_RUNTIME_MODE
```

不再支持隐藏的配置路径环境变量，例如：

```text
NAVLAB_ORCHESTRATION_CONFIG
```

`RUN_ID`、`ARTIFACT_DIR` 这类 artifact/debug 变量可以后续独立清理；它们不应再被
视为配置优先级规则的一部分。

## 目标

配置重构完成后，用户能从命令和文件名直接看出当前运行边界：

```bash
NAVLAB_RUNTIME_BACKEND=docker NAVLAB_RUNTIME_MODE=simulation \
uv run --project orchestration python orchestration/main.py run hover \
  --task-config orchestration/configs/hover.toml
```

真机路径必须显式：

```bash
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real \
uv run --project orchestration python orchestration/main.py doctor \
  --task-config orchestration/configs/real_preflight.toml
```

默认 orchestration config 根据 mode 选择：

```text
simulation -> orchestration/config.simulation.toml
real       -> orchestration/config.real.toml
```

task 默认配置根据 task name 选择：

```text
hover                 -> orchestration/configs/hover.toml
exploration           -> orchestration/configs/exploration.toml
scan-robustness       -> orchestration/configs/scan_robustness.toml
doctor with process+real -> orchestration/configs/real_preflight.toml
```

## 文件结构

目标结构：

```text
orchestration/
  config.simulation.toml
  config.real.toml

configs/
  hover.toml
  exploration.toml
  scan_robustness.toml
  real_preflight.toml
```

可选后续拆分：

```text
configs/
  shared/
    fcu_controller.toml
    landing.toml
    slam.toml
```

但首轮不建议引入 include/merge 机制。先保持每个 task config 自包含，避免在现场
排障时还要追多层引用。

## Orchestration Config

`orchestration/config.{mode}.toml` 只放 system / runtime / source boundary。仿真配置可以包含
Docker image、SITL、Gazebo 等仿真系统默认值；真机配置不应携带这些仿真/image 默认值，
否则现场审计时会误以为真机路径还依赖 Docker 镜像。

`orchestration/config.simulation.toml` 可以包含：

```toml
[navlab.images]
tag_strategy = "latest"

[orchestration.runtime.docker]
workspace_container_path = "/workspace"
```

`orchestration/config.real.toml` 应保持最小：

```toml
[orchestration.runtime]
fail_on_missing_backend_config = true
fail_on_mode_violation = true

[orchestration.runtime.process]
workspace_host_path = "."
log_dir = "artifacts/runtime_logs"
require_explicit_services = false

[orchestration.runtime.real.sources]
scan_source_claim = "real_lidar_driver"
scan_source_topic = "/scan"
fcu_source_claim = "real_serial_mavlink_or_ardupilot_dds_bridge"
imu_source_claim = "real_fcu_or_sensor"
rangefinder_source_claim = "real_or_not_required"
slam_source_claim = "real_slam"
required_real_topics = ["/scan", "/tf", "/tf_static", "/slam/odom", "/ap/v1/status", "/ap/v1/pose/filtered"]
forbidden_simulation_input_topics = ["/gazebo/*", "/scan_ideal", "/sim/x2/status", "/rangefinder/down/scan_ideal"]
```

不再放：

```toml
[orchestration.runtime]
backend = "docker"
mode = "simulation"
```

backend/mode 必须来自环境变量或 hard-code default：

```text
backend default = docker
mode default = simulation
```

这意味着 `config.real.toml` 不能把一次运行变成 real。真正进入 real 必须由命令
环境显式声明：

```bash
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real ...
```

## Task Config

每个 built-in task 使用一个同名 task config。

### Hover

`orchestration/configs/hover.toml`：

```toml
[task]
duration_sec = 90.0
simulation_profile = "ideal"

[fcu_controller]
takeoff_alt_m = 0.5
readiness_timeout_sec = 45.0
hold_after_ready_sec = 8.0

[slam_hover]
settle_window_sec = 8.0
hover_window_sec = 18.0
final_hold_window_sec = 5.0
max_hover_horizontal_drift_m = 0.35
max_hover_altitude_error_m = 0.30

[landing]
hover_policy = "land_in_place"
pre_land_hold_sec = 2.0
max_landing_duration_sec = 35.0
touchdown_altitude_m = 0.12
require_disarm = true
require_motors_safe = true
```

### Exploration / P8

`orchestration/configs/exploration.toml`：

```toml
[task]
duration_sec = 150.0
simulation_profile = "ideal"

[exploration]
strategy = "frontier_lite"
exploration_window_sec = 26.0
motion_speed_mps = 0.10
min_accepted_goals = 3
min_path_length_m = 0.35

[landing]
exploration_policy = "return_home_then_land"
home_source = "post_takeoff_hover_pose"
home_radius_m = 0.35
max_return_home_duration_sec = 45.0
max_landing_duration_sec = 35.0
```

### Scan Robustness / P12

`orchestration/configs/scan_robustness.toml`：

```toml
[task]
duration_sec = 240.0
live = true
live_profiles = []

[airframe_disturbance]
profile = "nominal_realistic"
required_profiles = ["clean", "mild_bias", "nominal_realistic", "esc_lag", "vibration"]

[landing]
scan_robustness_policy = "land_in_place"
max_landing_duration_sec = 35.0
```

### Real Preflight

`orchestration/configs/real_preflight.toml`：

```toml
[task]
duration_sec = 45.0

[serial_mavlink]
enabled = true
port = "/dev/ttyACM0"
baud = 115200
connection_timeout_sec = 3.0
heartbeat_timeout_sec = 5.0
telemetry_window_sec = 8.0
require_autopilot_heartbeat = true
require_system_status = true
require_not_armed = true
required_messages = ["HEARTBEAT", "SYS_STATUS", "ATTITUDE"]

[landing]
default_policy = "land_in_place"
```

real preflight doctor 不执行 arm/takeoff/land，因此它的 task config 不能包含
movement 或 landing intent 参数。

## CLI Contract

CLI 入口应从：

```bash
uv run --project orchestration python orchestration/main.py run hover \
  --duration-sec 90 \
  --simulation-profile ideal \
  --orchestration-config orchestration/config.simulation.toml \
  --task-config orchestration/configs/hover.toml
```

迁移为：

```bash
uv run --project orchestration python orchestration/main.py run hover \
  --task-config orchestration/configs/hover.toml
```

可选覆盖 task invocation params：

```bash
uv run --project orchestration python orchestration/main.py run hover \
  --task-config orchestration/configs/hover.toml \
  --duration-sec 120 \
  --simulation-profile mild_disturbance
```

推荐 CLI 参数：

```text
--orchestration-config PATH
--task-config PATH
--duration-sec FLOAT
--simulation-profile ideal|mild_disturbance
```

其中：

- `--orchestration-config` 只选择 system config。
- `--task-config` 只选择 task config。
- task 参数 CLI 覆盖 task config。
- CLI 不再使用位置参数传 duration，避免 `just navlab-hover 90` 这种隐式参数在真机
  现场不够清楚。

工具型命令可以保留工具行为参数，例如：

```text
--dry-run
--force
--lite
--tag
```

这些不是 flight task behavior，不进入 task config 优先级规则。

## Precedence Schema

### Runtime backend/mode

```text
NAVLAB_RUNTIME_BACKEND > "docker"
NAVLAB_RUNTIME_MODE    > "simulation"
```

非法值直接 fail：

```text
NAVLAB_RUNTIME_BACKEND=unknown
NAVLAB_RUNTIME_MODE=unknown
```

非法组合直接 fail：

```text
docker + real
process + simulation
```

### Orchestration config path

```text
--orchestration-config > orchestration/config.{resolved_mode}.toml
```

如果没有显式 `--orchestration-config`：

```text
resolved_mode = NAVLAB_RUNTIME_MODE or "simulation"
default_path  = orchestration/config.<resolved_mode>.toml
```

### Task config path

```text
--task-config > orchestration/configs/<task-name>.toml
```

### Task invocation params

```text
CLI option > task config > hard-code default
```

例如 hover：

```text
--duration-sec > orchestration/configs/hover.toml [task].duration_sec > 90.0
--simulation-profile > orchestration/configs/hover.toml [task].simulation_profile > ideal
```

### System config values

```text
orchestration/config.{mode}.toml > hard-code default
```

例如:

```text
[orchestration.runtime.process].log_dir > artifacts/runtime_logs
[orchestration.runtime.real.sources].required_real_topics > built-in required topics
```

## Summary Schema

所有 acceptance / doctor summary 顶层应记录配置来源：

```json
{
  "runtime_backend": "docker",
  "runtime_mode": "simulation",
  "config_sources": {
    "runtime_backend_source": "NAVLAB_RUNTIME_BACKEND|default",
    "runtime_mode_source": "NAVLAB_RUNTIME_MODE|default",
    "orchestration_config": "orchestration/config.simulation.toml",
    "orchestration_config_source": "cli|default",
    "task_config": "orchestration/configs/hover.toml",
    "task_config_source": "cli|default"
  },
  "task_parameters": {
    "duration_sec": {
      "value": 90.0,
      "source": "cli|task_config|default"
    },
    "simulation_profile": {
      "value": "ideal",
      "source": "cli|task_config|default"
    }
  }
}
```

这样 Foxglove artifact、rosbag、summary 能复现“这次到底用了哪个 mode、哪个
system config、哪个 task config，以及哪些参数是 CLI 覆盖的”。

## 迁移策略

### P0：冻结当前行为

- 记录当前 `orchestration/config.simulation.toml` 中所有 section 的归属。
- 标记哪些 section 应迁移到 `orchestration/config.simulation.toml`。
- 标记哪些 section 应迁移到 `orchestration/config.real.toml`。
- 标记哪些 section 应迁移到 `orchestration/configs/<task>.toml`。
- 保留现有 CLI 一轮，但 summary 加 warning。

### P1：新增 config resolver

- [x] 新增 runtime backend/mode resolver，只读 `NAVLAB_RUNTIME_BACKEND/MODE` 和 default。
- [x] 移除 backend/mode 从 TOML 读取。
- [x] 新增 orchestration config resolver：`--orchestration-config` 或
  `orchestration/config.{mode}.toml`。
- [x] 移除 `NAVLAB_ORCHESTRATION_CONFIG`。
- [x] 新增 task config resolver：`--task-config` 或 `orchestration/configs/<task>.toml`。

### P2：拆分文件

- [x] 生成 `orchestration/config.simulation.toml`。
- [x] 生成 `orchestration/config.real.toml`。
- [x] 生成 `orchestration/configs/hover.toml`。
- [x] 生成 `orchestration/configs/exploration.toml`。
- [x] 生成 `orchestration/configs/scan_robustness.toml`。
- [x] 生成 `orchestration/configs/real_preflight.toml`。
- [x] 删除旧 `orchestration/config.toml`，不再保留 legacy root config。

### P3：迁移 CLI

- [x] 将位置参数 `duration_sec` 改为 `--duration-sec`。
- [x] 保留 `--simulation-profile`，但它只覆盖 task config。
- [x] 新增 `--orchestration-config`。
- [x] 新增 `--task-config`。
- [x] 更新 justfile，默认依赖 task 默认路径。

### P4：迁移 summary 和测试

- [x] summary 记录 `config_sources`。
- [x] summary 记录 task 参数来源。
- [x] 单测覆盖 `env > default` 的 runtime 规则。
- [x] 单测覆盖 `CLI > task_config > default` 的 task 参数规则。
- [x] 单测覆盖不存在 `NAVLAB_ORCHESTRATION_CONFIG` 行为。

## 不做什么

- 不把 task config 和 orchestration config 重新合并。
- 不让 `config.real.toml` 自动切换到 real mode；real mode 必须来自
  `NAVLAB_RUNTIME_MODE=real`。
- 不通过隐藏环境变量选择 config path。
- 不在首轮实现复杂 include/extends 机制。
- 不把工具参数 `--dry-run`、`--force`、`--lite` 放入 task config。
- 不把真机 preflight doctor 变成 flight task；它仍然不 arm、不 takeoff、不 land。

## 完成标准

- 默认仿真运行使用 `orchestration/config.simulation.toml`。
- 显式真机运行使用 `NAVLAB_RUNTIME_MODE=real` 后默认选择
  `orchestration/config.real.toml`。
- runtime backend/mode 只来自 `NAVLAB_RUNTIME_BACKEND/MODE` 或 default。
- `NAVLAB_ORCHESTRATION_CONFIG` 不再影响 orchestration。
- hover/P8/P12/real-preflight 均有独立 `orchestration/configs/<task>.toml`。
- task 参数遵循 `CLI > task config > default`。
- system 参数遵循 `orchestration config > default`。
- summary 能记录 runtime、orchestration config、task config 和 task 参数来源。
