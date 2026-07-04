# 真机飞行前 Preflight Doctor TODO

## 目标

real preflight doctor 只做真机起飞前最基础的非执行性检查：

- 当前 wrapper 处在 `process + real` runtime 边界内。
- 真机 FCU 串口存在、可打开，并能通过 MAVLink 看到真实 autopilot HEARTBEAT。
- 真机运行所需的基础依赖存在，例如 `mavlink-router`、`ros2`、所选 `fcu_bridge_mode` 的 ROS packages、SLAM 和 companion Python 入口。

其他真机 bringup 和任务 readiness 职责归入
`docs/scenarios/indoor/todos/real_prepare_and_task_doctor_todo.md`。

设计文档：

- `docs/scenarios/indoor/navlab_real_flight_preflight_doctor_design.md`

相关 TODO：

- `docs/scenarios/indoor/todos/real_prepare_and_task_doctor_todo.md`

适用真机 wrapper task：

- `run hover` with `NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real`
- `run exploration` with `NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real`
- `run scan-robustness` with `NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real`

## RFD.0 文档和边界

任务：

- [x] 新增真机飞行前 preflight doctor 设计文档。
- [x] 新增真机飞行前 preflight doctor TODO 文档。
- [x] 在 `docs/README.md` 中加入 real preflight design / TODO 入口。
- [x] 文档明确 preflight doctor 是 `run <task>` wrapper 内部 phase，不是单独 operator CLI。
- [x] 文档明确 real preflight doctor 不 arm、不 takeoff、不 land、不发布 movement setpoint。
- [x] 文档明确 real preflight doctor 不启动 `mavlink-router`、FCU ROS bridge、SLAM、lidar driver 或 companion。
- [x] 文档明确 real preflight doctor 只检查串口 MAVLink 和依赖存在性。

验收：

- [x] design 文档只写边界和 contract，不承载 implementation checklist。
- [x] TODO 文档单独承载任务拆分和验收标准。
- [x] README 中能从室内主线导航到 design 和 TODO。
- [x] 后续真机 wrapper 实现引用本 TODO 时，只引用串口和依赖 preflight gate。

## RFD.1 Runtime mode 和 wrapper 边界

任务：

- [x] real preflight 归入 `run <task>` wrapper 内部 phase。
- [x] real preflight 要求 `NAVLAB_RUNTIME_BACKEND=process`。
- [x] real preflight 要求 `NAVLAB_RUNTIME_MODE=real`。
- [x] 新增或固化 `orchestration/config.real.toml` 示例。
- [x] 支持配置 real preflight summary 有效窗口，例如 `valid_for_sec`。
- [x] summary 记录 runtime backend/mode 来源。
- [x] 非 `process + real` 组合直接 blocked，不能 fallback 到 Docker。
- [x] 对外 CLI/justfile 收敛为 `run <task>` / `just navlab-run <task>`。

验收：

- [x] `NAVLAB_RUNTIME_BACKEND=docker NAVLAB_RUNTIME_MODE=simulation` 时 real preflight blocked。
- [x] `NAVLAB_RUNTIME_BACKEND=process` 但未设置 `NAVLAB_RUNTIME_MODE=real` 时 blocked。
- [x] `run hover` real mode 的第一个内部 phase 是 real preflight doctor。
- [x] `process + real` 下不会启动 Docker/Gazebo/SITL service。
- [x] summary 中有 `runtime_backend=process` 和 `runtime_mode=real`。

## RFD.2 依赖存在性检查

任务：

- [x] 配置 `[real_preflight.dependencies]`。
- [x] 检查 `mavlink-routerd` 或 `mavlink-router` 可执行文件存在。
- [x] 检查 `ros2` CLI 存在。
- [x] 依赖检查按 `fcu_bridge_mode` 注册器展开；`navlab_mavlink` 不要求 MAVROS / `mavros_msgs`。
- [x] `navlab_mavlink` 检查本地 ROS package，例如 `navlab_slam_bringup`、`navlab_external_nav_bridge`、`ydlidar_ros2_driver`。
- [x] 检查 SLAM 相关 package 存在，例如 `navlab_slam_bringup`。
- [x] 检查 companion Python 入口可 import。当前过渡入口是 `navlab.sim.companion.runtime.cli`，目标是 real/sim companion runtime 分包。
- [x] 检查 SLAM Python 入口可 import。当前过渡入口是 `navlab.common.slam.cli`，目标是 real/sim SLAM runtime 分包。
- [x] summary 记录 command、ROS package、Python module 三类依赖结果。
- [x] 依赖检查输出更清晰的 console table / panel。
- [x] 依赖 blocker 使用稳定字符串，例如 `required_command_missing`、`required_ros_package_missing`、`required_python_module_missing`。

验收：

- [x] 缺 `mavlink-routerd` / `mavlink-router` 时 summary `ok=false`。
- [x] 缺 `ros2` 时 summary `ok=false`。
- [x] 缺 required ROS package 时 summary `ok=false`。
- [x] 缺 required Python module 时 summary `ok=false`。
- [x] 依赖检查不会启动任何辅助进程。
- [x] console 输出能直接看到缺哪个 command / package / module。

## RFD.3 真实串口 MAVLink 检查

任务：

- [x] 配置 `[serial_mavlink]`。
- [x] `orchestration` 增加 `pyserial` 依赖。
- [x] `orchestration` 增加 `pymavlink` 依赖。
- [x] 用 pyserial 检查串口 path 是否存在。
- [x] 用 pyserial 检查当前用户是否有读写权限。
- [x] 用 pyserial 按配置 baud 短暂打开串口。
- [x] 用 pymavlink 在 timeout 内等待 autopilot HEARTBEAT。
- [x] summary 记录 MAVLink system id、component id、autopilot、vehicle type、mode、armed。
- [x] 默认要求 preflight 时 FCU 未 armed。
- [x] 检查 required MAVLink messages，例如 HEARTBEAT、SYS_STATUS、ATTITUDE。
- [x] 可选记录 RANGEFINDER / DISTANCE_SENSOR 作为 telemetry evidence。
- [x] 检查完成后立即关闭串口，不长期占用。
- [x] 禁止用 SITL TCP/UDP endpoint 替代真实串口 evidence。
- [x] MAVLink blocker 使用稳定字符串，例如 `serial_port_missing`、`serial_port_permission_denied`、`serial_mavlink_heartbeat_missing`。

验收：

- [x] 串口不存在时 summary `ok=false`。
- [x] 串口权限不对时 summary `ok=false`。
- [x] baud 打不开时 summary `ok=false`。
- [x] 收不到真实 autopilot HEARTBEAT 时 summary `ok=false`。
- [x] MAVLink HEARTBEAT 来自 invalid autopilot 时 summary `ok=false`。
- [x] required MAVLink message 缺失时 summary `ok=false`。
- [x] preflight 时 FCU 已 armed 且未显式允许时 summary `ok=false`。
- [x] serial probe 不启动 `mavlink-router`，也不长期持有串口。

## RFD.4 Summary、artifact 和 console 输出

任务：

- [x] real preflight doctor 写出 artifact dir。
- [x] summary 新增或固化 `preflight_claim=evaluated`。
- [x] summary 新增或固化 `flight_claim=not_evaluated`。
- [x] summary 新增或固化 `landing_claim=not_evaluated`。
- [x] summary 记录 `checked_at` 和 `valid_for_sec`。
- [x] summary 记录 runtime backend/mode。
- [x] summary 记录 dependency checks。
- [x] summary 记录 `serial_mavlink` 检查结果。
- [x] console 使用 Rich panel / table 显示关键结论。
- [x] blocker 使用稳定字符串，例如 `runtime_backend_must_be_process`、`runtime_mode_must_be_real`、`required_command_missing`、`serial_mavlink_heartbeat_missing`。

验收：

- [x] `ok=true` 时 summary 足够证明依赖和串口 preflight 通过。
- [x] `blocked=true` 时 blockers 可直接定位缺依赖或串口 MAVLink 问题。
- [x] summary 不把 preflight doctor 误标为 `hover_claim=evaluated`。
- [x] summary 不把 preflight doctor 误标为 `real_landing_claim=evaluated`。

## RFD.5 测试

任务：

- [x] 增加配置测试：`process + real` real preflight 可加载。
- [x] 增加配置测试：非法 backend/mode 组合 blocked。
- [x] 增加 dependency probe 测试：缺 command blocked。
- [x] 增加 dependency probe 测试：缺 Python module blocked。
- [x] 增加 serial probe 测试：缺 port blocked。
- [x] 增加 serial probe 测试：网络 endpoint 被拒绝。
- [x] 增加 serial probe 测试：无 HEARTBEAT blocked。
- [x] 增加 summary schema 测试。
- [x] 增加 console table / panel 输出测试。

验收：

- [x] real preflight 单元测试通过。
- [x] runtime mode / backend 现有测试仍通过。
- [x] CLI help 能看到 `run <task>`，但不把 preflight doctor 当作 operator 主入口。

## RFD.6 执行顺序

建议顺序：

1. RFD.0 文档和边界。
2. RFD.1 Runtime mode 和 wrapper 边界。
3. RFD.2 依赖存在性检查。
4. RFD.3 真实串口 MAVLink 检查。
5. RFD.4 Summary、artifact 和 console 输出。
6. RFD.5 测试。

## RFD 完成标准

RFD 全部完成必须满足：

- [x] real preflight 只检查 runtime boundary、依赖存在性和真实串口 MAVLink。
- [x] real preflight summary `ok=true`。
- [x] real preflight summary `runtime_backend=process`。
- [x] real preflight summary `runtime_mode=real`。
- [x] required command / ROS package / Python module 都存在。
- [x] 真实串口 MAVLink 可打开并收到 FCU HEARTBEAT。
- [x] summary 记录 MAVLink system/component id、mode、armed 和 message_counts。
- [x] doctor 不 arm、不 takeoff、不 land、不发布 movement setpoint。
- [x] doctor 不启动 `mavlink-router`、FCU ROS bridge、SLAM、lidar driver 或 companion。
- [x] doctor summary 标记 `flight_claim=not_evaluated`。
- [x] doctor summary 标记 `landing_claim=not_evaluated`。

## 验证记录

### 2026-06-09 RFD 文档初始化

- 命令：未运行代码测试，纯文档初始化。
- 结果：新增 real flight preflight doctor 设计文档和 TODO 文档，并把 TODO 加入 README 导航。
- blocker：真实串口 MAVLink 和依赖检查尚未实现。

### 2026-06-09 RFD serial MAVLink preflight implementation

- 命令：`uv run --project orchestration pytest orchestration/tests/test_runtime_backend.py -q`
- 结果：runtime/preflight 相关测试通过；preflight 已加载 `orchestration/configs/real_preflight.toml`，并检查真实 serial MAVLink port、HEARTBEAT、required MAVLink messages、armed/mode 和依赖存在性。
- blocker：稳定 blocker 字符串、console 输出细化、wrapper-only CLI 收敛仍未完成。

### 2026-06-09 RFD scope reduction

- 命令：未运行代码测试，纯 TODO 收敛。
- 结果：RFD TODO 已删掉超出串口和依赖检查范围的任务；后续真机 bringup 和任务 readiness 归入 prepare / task doctor TODO。
- blocker：代码中若仍把超出范围的检查放进 real preflight，需要后续按本文档继续清理。

### 2026-06-09 RFD wrapper and preflight cleanup

- 命令：`uv run --project orchestration pytest orchestration/tests/test_cli.py orchestration/tests/test_runtime_backend.py orchestration/tests/test_config.py -q`
- 结果：133 个 CLI / runtime / config 测试通过；CLI 只暴露 `build`、`doctor`、`run <task>`，public registry 不再暴露 per-task doctor，real preflight 不再采集或 gate ROS topic/source claim。
- blocker：真机 prepare、task doctor 和 real task flight wrapper 仍在 `real_prepare_and_task_doctor_todo.md` 中继续跟踪。


### 2026-06-09 RFD real hardware doctor pass

- 命令：`just navlab-doctor`
- 结果：real preflight doctor 在 `process+real`、`ros_distro=humble` 下通过；`Deps cmd=2/2, ros=6/6, py=2/2`，`/dev/ttyUSB1` 可打开并收到 ArduPilot HEARTBEAT，summary 记录 system/component、mode、armed 和 message_counts。
- blocker：无；后续真机 prepare、task doctor 和 flight wrapper 继续在 `real_prepare_and_task_doctor_todo.md` 跟踪。

### 2026-06-09 RFD fcu_bridge_mode registry

- 命令：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --project orchestration pytest orchestration/tests/test_real_prepare.py orchestration/tests/test_runtime_backend.py::test_real_preflight_loads_serial_mavlink_task_config orchestration/tests/test_runtime_backend.py::test_real_preflight_effective_dependencies_use_fcu_bridge_mode -q`
- 结果：新增 `fcu_bridge_mode = "navlab_mavlink"` 注册器；preflight 依赖和 prepare/task doctor required topics 按 mode 展开，默认不要求 MAVROS 或 `/ap/v1/*`。
- blocker：`navlab_mavlink` bridge 进程本身仍属于后续 real flight runner/companion bringup，不由 preflight doctor 启动。
