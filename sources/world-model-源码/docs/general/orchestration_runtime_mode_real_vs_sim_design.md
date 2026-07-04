# Orchestration Runtime Mode: Simulation vs Real 设计

## 背景

当前 `orchestration` 已经把运行方式抽象成 `RuntimeBackend`：

- `docker`：用 Docker/compose/python_on_whales 管服务。
- `process`：用 host-side ProcessManager 管本机进程。

但这还不够。`backend=process` 只说明“服务怎么被启动”，不说明“任务运行在仿真还是现实路径”。

真实无人机/算力盒子场景下，process backend 不应该再启动 Gazebo、SITL、official baseline、仿真 lidar、仿真 rangefinder、仿真 motor disturbance overlay。它应该只接入真实硬件/真实 ROS topic/真实 FCU 路径。

所以需要在 runtime backend 之外新增一层 runtime mode：

```text
runtime.mode = simulation | real
```

## 核心判断

你的判断是合理的：

- `docker + simulation` 是当前 P8/P9/P10/P11/P12 仿真验收主线。
- `process + real` 才是算力盒子/真实无人机主线。
- `process + simulation` 当前不支持，避免把 host process 调试误认为真机验收。
- `docker + real` 当前不支持，避免容器设备权限、udev、网络和真实 FCU 边界不清。

换句话说：

```text
backend = 进程/容器生命周期管理方式
mode    = 数据源和系统边界是真实还是仿真
```

不能只看 backend 来决定是否启动 Gazebo。

## 目标

新增 runtime mode 后，orchestration 必须能明确表达：

- 当前是否允许启动 Gazebo/SITL/official baseline。
- 当前是否允许使用 Gazebo truth 作为任何控制、SLAM、ExternalNav 输入。
- 当前 scan/IMU/rangefinder/FCU 数据来自仿真还是真实硬件。
- 当前是否允许生成 SDF overlay、motor bias overlay、ESC lag patch replay。
- 当前 summary 中能看出本次是 simulation 还是 real。

## 配置设计

建议在 `orchestration/config.toml` 增加：

```toml
[orchestration.runtime]
backend = "docker"      # docker | process
mode = "simulation"     # simulation | real
fail_on_missing_backend_config = true
fail_on_mode_violation = true

[orchestration.runtime.simulation]
allow_gazebo = true
allow_sitl = true
allow_official_baseline = true
allow_sdf_overlay = true
allow_simulated_lidar = true
allow_simulated_rangefinder = true
allow_simulated_imu = true
allow_airframe_disturbance_overlay = true

[orchestration.runtime.real]
allow_gazebo = false
allow_sitl = false
allow_official_baseline = false
allow_sdf_overlay = false
allow_simulated_lidar = false
allow_simulated_rangefinder = false
allow_simulated_imu = false
allow_airframe_disturbance_overlay = false
require_real_fcu = true
require_real_scan = true
require_real_imu = true
require_real_rangefinder = false
require_no_set_pose = true
require_no_gazebo_truth = true
```

环境变量覆盖：

```bash
NAVLAB_RUNTIME_BACKEND=process
NAVLAB_RUNTIME_MODE=real
```

无效组合必须 fail。

## 支持组合矩阵

当前只支持两种组合。其他组合不作为“以后默认可用”的隐含能力，而是直接视为非法配置。

| backend | mode | 状态 | 用途 |
|---|---|---|---|
| docker | simulation | 支持 | 当前 P8-P12 Docker/SITL/Gazebo 仿真验收 |
| process | real | 支持 | 算力盒子/真实无人机 |
| process | simulation | 不支持 | 避免 host process 调试路径和真机路径混淆 |
| docker | real | 不支持 | 避免容器化真机设备/权限/网络边界不清 |

推荐 gate：

```text
if mode == real:
  forbid_gazebo_services()
  forbid_sitl_services()
  forbid_official_baseline_services()
  forbid_sdf_overlay_generation()
  forbid_sim_sensor_runtime()
  require_real_topic_contract()
```

## Simulation mode 行为

`runtime.mode=simulation` 允许：

- 启动 Gazebo。
- 启动 SITL。
- 启动 official baseline container。
- 生成 SDF model overlay。
- 使用 Gazebo lidar topic 作为仿真 scan source。
- 使用仿真 rangefinder/IMU bridge。
- 使用 motor thrust multiplier / ESC lag / vibration simulation profile。
- 生成 official maze overlay 和 Foxglove-lite replay。

但 simulation mode 仍必须保持旧原则：

- Gazebo truth 不能进 SLAM/ExternalNav/control。
- 禁止 direct `set_pose` 移动无人机。
- FCU owner 仍必须唯一。
- summary 必须记录 `uses_gazebo_truth_as_input=false`。

## Real mode 行为

`runtime.mode=real` 禁止：

- 启动 Gazebo。
- 启动 SITL。
- 启动 official baseline。
- 生成或加载 SDF overlay。
- 启动 gazebo-sensor runtime。
- 使用 `/lidar`、`/scan_ideal`、`/gazebo/*` 等仿真 topic。
- 使用 motor bias / ESC lag / SDF thrust multiplier overlay。
- 使用 official maze 作为任何输入。
- 使用 Gazebo truth diagnostic 作为 gate 通过条件。

`runtime.mode=real` 要求：

- FCU 来源是真实 `/ap/v1/*` 或明确配置的真实飞控接口。
- `/scan` 来自真实 lidar 驱动或真实 scan stabilization pipeline。
- `/imu` 来自真实 IMU/FCU/传感器融合链路。
- `/tf`、`/tf_static` 来自真实 robot description/static publisher。
- `/slam/odom` 来自真实 SLAM。
- rosbag 只记录真实任务窗口 topic。
- summary 记录 `runtime_mode=real` 和所有 real source claims。

## Real mode topic contract

建议 real mode 至少检查：

```text
required_real_topics:
  /scan
  /tf
  /tf_static
  /slam/odom
  /ap/v1/status
  /ap/v1/pose/filtered 或真实配置的 FCU pose topic
  /ap/v1/twist/filtered 或真实配置的 FCU twist topic

forbidden_sim_topics:
  /gazebo/*
  /scan_ideal
  /lidar                 # 如果这是 Gazebo lidar topic
  /sim/x2/status
  /rangefinder/down/scan_ideal
  /navlab/official_maze/* 作为输入
```

注意：真实 lidar 驱动也可能发布 `/lidar`，所以 forbidden topic 不应只按名字硬判。应该配置 source claim：

```toml
[orchestration.runtime.real.sources]
scan_source_claim = "real_lidar_driver"
scan_source_topic = "/scan"
imu_source_claim = "real_fcu_or_sensor"
fcu_source_claim = "real_serial_mavlink_or_ardupilot_dds_bridge"
```

## Gate 分层设计

### Simulation gate

继续服务当前 P8-P12：

- official maze exploration
- official maze overlay replay
- scan integrity
- scan stabilization
- airframe disturbance robustness

这些 gate 可以使用 Gazebo/SITL 生成可复现实验数据，但不能把 truth 输入控制/SLAM。

### Real preflight gate

新增或后续迁移：

```text
real-preflight-doctor
```

检查：

- backend 必须是 `process`。
- mode 必须是 `real`。
- Gazebo/SITL/official baseline service 没有启动。
- real required topics 存在。
- forbidden simulation topics 不作为输入。
- FCU mode/status 可读。
- scan attitude quality 可读。
- no set_pose path。

### Real scan integrity gate

复用 P10/P11 逻辑，但数据源是真实 topic：

- 不启动 Gazebo。
- 不生成 SDF。
- 不启动 simulated X2/gazebo-sensor。
- 只检查真实 `/scan` 是否经过 attitude validation/stabilization。
- 如果姿态超阈值，按 P10/P11 规则 warn/drop/compensate。

### Real flight gate

后续真实试飞才启用：

- 严格 FCU owner。
- 严格 GUIDED/任务模式窗口。
- 严格 no Gazebo/no SITL/no set_pose。
- rosbag profile 使用 real-flight profile。
- summary 不允许出现 simulation-only source claim。

## Summary schema

所有 summary 顶层新增或保留：

```json
{
  "runtime_backend": "process",
  "runtime_mode": "real",
  "runtime_backend_summary": {
    "backend": "process",
    "mode": "real",
    "backend_source": "NAVLAB_RUNTIME_BACKEND",
    "mode_source": "NAVLAB_RUNTIME_MODE",
    "backend_config_path": "orchestration/config.toml",
    "fail_on_missing_backend_config": true,
    "fail_on_mode_violation": true
  },
  "source_claims": {
    "fcu": "real_serial_mavlink_or_ardupilot_dds_bridge",
    "scan": "real_lidar_driver",
    "imu": "real_fcu_or_sensor",
    "rangefinder": "real_or_not_required",
    "slam": "real_slam"
  },
  "simulation_sources": {
    "gazebo_started": false,
    "sitl_started": false,
    "official_baseline_started": false,
    "sdf_overlay_used": false,
    "gazebo_truth_as_input": false,
    "set_pose_count": 0
  }
}
```

## Mode violation blockers

Real mode 下出现以下情况必须 fail：

```text
runtime_mode_violation:gazebo_service_requested
runtime_mode_violation:sitl_service_requested
runtime_mode_violation:official_baseline_requested
runtime_mode_violation:sdf_overlay_requested
runtime_mode_violation:simulated_sensor_runtime_requested
runtime_mode_violation:gazebo_truth_input_claimed
runtime_mode_violation:set_pose_path_available
runtime_mode_violation:scan_source_not_real
runtime_mode_violation:fcu_source_not_real
runtime_mode_violation:required_real_topic_missing:<topic>
```

Simulation mode 下出现以下情况必须 fail：

```text
runtime_mode_violation:simulation_disabled_but_sim_service_requested
runtime_mode_violation:gazebo_truth_used_as_input
runtime_mode_violation:set_pose_count_nonzero
```

## 对当前 P10/P11/P12 的影响

### P10 scan integrity

Simulation mode：保持当前 Docker/SITL/Gazebo 验收。

Real mode：只保留 scan attitude quality / drop / warn / summary 逻辑，不启动任何仿真服务。

### P11 scan stabilization

Simulation mode：保持 bounded 2D compensation + P9 representative replay。

Real mode：只在真实 `/scan` 和真实 attitude source 上运行 stabilization gate；不做 P9 replay，不生成 official maze overlay。

### P12 airframe disturbance

Simulation mode：继续使用 motor thrust multiplier / ESC lag / vibration simulation profile。

Real mode：不再“注入”motor bias/ESC lag。只能观测真实飞行期间的 attitude/motor/scan metrics：

- roll/pitch RMS
- max tilt
- scan drop ratio
- compensation ratio
- FCU mode continuity
- motor output best-effort

P12 real mode 的目标不是制造扰动，而是证明真实扰动没有破坏 scan/SLAM contract。

## 实施 TODO

### P0：新增 runtime mode 配置

- [x] 在 project config 中增加 `runtime.mode`。
- [x] 支持 `NAVLAB_RUNTIME_MODE=simulation|real`。
- [x] 默认 `mode=simulation`，保持现有 Docker 主线不变。
- [x] 非法 mode 直接 fail。
- [x] 非法 backend/mode 组合直接 fail：只允许 `docker+simulation` 和 `process+real`。
- [x] summary 顶层记录 `runtime_mode`。

### P1：mode policy

- [x] 新增 `RuntimeModePolicy`。
- [x] 定义 simulation/real 允许和禁止的 service/source/overlay。
- [x] real mode 禁止 Gazebo/SITL/official baseline/gazebo-sensor/SDF overlay。
- [x] mode violation 输出明确 blocker。

### P2：service launcher guard

- [x] `ServiceSpec` 增加 `service_role` 或 `source_role`。
- [x] Gazebo/SITL/official-baseline/gazebo-sensor 标记为 simulation-only。
- [x] real mode 下 simulation-only service start 直接 fail。
- [x] Docker/process backend 不自行猜 mode，由 task/runtime policy 传入。

### P3：real source contract

- [x] 配置 real scan source claim。
- [x] 配置 real FCU source claim。
- [x] 配置 real IMU source claim。
- [x] 配置 forbidden simulation input topics。
- [x] real preflight doctor 检查 required real topics。

### P4：P10/P11/P12 mode 分流

- [ ] P10 real mode 不启动仿真，只跑真实 scan integrity 检查。
- [ ] P11 real mode 不启动 P9 replay，只跑真实 scan stabilization 检查。
- [ ] P12 real mode 不注入扰动，只记录真实 disturbance metrics。
- [x] P10/P11/P12 simulation mode 维持当前 Docker/SITL/Gazebo 路径。

### P5：文档和验收

- [x] 更新 runtime backend guide。
- [x] 更新 P10/P11/P12 设计文档，说明 simulation vs real 分流。
- [x] 增加 real-preflight-doctor 命令设计。
- [x] 增加 summary schema 测试。
- [x] 增加 mode violation 单测。

## 完成标准

- [x] `backend` 和 `mode` 在 config/summary 中都可见。
- [x] `process + real` 不会启动 Gazebo/SITL/official baseline。
- [x] `docker + simulation` 保持当前 P10/P11/P12 doctor 通过。
- [x] real mode 下 simulation-only service 直接 fail，blocker 清楚。
- [x] P10/P11/P12 real mode 不使用 official maze replay/SDF overlay/仿真 sensor。
- [x] 文档明确：当前只支持 `docker+simulation` 和 `process+real` 两条主线。
- [x] 文档明确：process backend 不是自动真机，real mode 才是真机路径。
