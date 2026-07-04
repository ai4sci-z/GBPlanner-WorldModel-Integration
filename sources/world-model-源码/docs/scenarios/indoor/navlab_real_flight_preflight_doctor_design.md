# NavLab 真机飞行前 Preflight Doctor 设计

## 1. 背景

当前 `hover`、`exploration` 和 `scan-robustness` built-in task 的主线仍是
Gazebo/SITL Stage 1 验收。它们会启动 official baseline、Gazebo/SITL、
gazebo-sensor、X2 virtual serial、SDF overlay 等仿真组件。

真机起飞前不能复用这些仿真入口来“顺便检查一下”。真实机器的对外入口必须是
统一 wrapper。wrapper 根据 `NAVLAB_RUNTIME_BACKEND` 和 `NAVLAB_RUNTIME_MODE`
选择 real 或 simulation 路径，不再通过 `--stage` 这类 CLI 参数切换阶段：

```text
run <task> with NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real
  -> real preflight doctor phase
  -> checks process + real runtime boundary
  -> checks real FCU serial device and selected fcu_bridge dependencies
  -> writes preflight summary
  -> real prepare / bringup phase
  -> task doctor phase
  -> companion / task run phase
  -> does not arm, take off, land, or publish movement setpoints
```

也就是说，真机飞行入口的顺序必须是：

```text
run <task> wrapper
     -> real preflight doctor phase passed
     -> real prepare / bringup phase passed
     -> task doctor phase passed
  -> operator safety confirmation
  -> real hover / P8 / P12 flight task
  -> landing summary
```

不能是：

```text
just navlab-hover
  -> use simulation hover result as real readiness
  -> fly the real machine
```

## 2. 目标

真机 preflight doctor 要回答一个问题：

> 当前系统是否真的处在 `process + real` 边界内，并且真实 FCU 串口 MAVLink
> 与真机基础依赖存在，足以允许 wrapper 进入 real prepare / bringup 阶段？

它的目标不是证明 hover 已经完成，也不是证明 landing 已经完成。它只证明：

- 当前 runtime backend 是 `process`。
- 当前 runtime mode 是 `real`。
- FCU 串口设备、权限和 baud 配置正确。
- `mavlink-router`、所选 `fcu_bridge_mode` 的 ROS package、SLAM、companion Python 入口等真机依赖存在。
- pymavlink 能在短窗口内从真实串口看到 autopilot HEARTBEAT 和 required MAVLink
  messages。
- summary 能作为后续 real prepare phase 的入口证据。

## 3. 不做什么

real preflight doctor 必须保持非执行性：

- 不 arm。
- 不 takeoff。
- 不 land。
- 不发布 `/ap/v1/cmd_vel`。
- 不发布 movement / landing intent。
- 不启动 Gazebo。
- 不启动 SITL。
- 不启动 official baseline。
- 不启动 gazebo-sensor。
- 不启动 `mavlink-router`、FCU ROS bridge、SLAM 或 companion；这些由 real prepare /
  task prepare 阶段负责。
- 不生成或加载 SDF / motor disturbance overlay。
- 不检查 `/scan`、`/slam/odom`、FCU bridge topic freshness 或 companion readiness。
- 不把仿真 Stage 1 artifact 当成真机数据源。
- 不把 TCP/UDP SITL endpoint 当成真实 FCU 证据。

doctor 通过只表示“允许进入下一层真机飞行入口检查”，不表示飞机已经可以无条件
自动起飞。

真机启动分层设计见
`docs/scenarios/indoor/navlab_real_prepare_and_task_doctor_design.md`。preflight
doctor 只做非执行性检查；real prepare 才启动辅助进程；task doctor 再检查
companion 和具体任务 readiness。这些都是 wrapper 内部 phase，不是单独的
operator CLI。

## 4. 入口关系

### 4.1 仿真 Stage 1 只作参考

Stage 1 仍由 Gazebo/SITL built-in task 负责，但它不是任何真机 wrapper 的必需 gate：

| task | Stage 1 command | 结果 |
|---|---|---|
| hover | `just navlab-run hover ... --simulation-profile ideal` 和 `realistic` | 证明仿真起飞、悬停、原地降落 |
| P8 exploration | `just navlab-run exploration ... --simulation-profile ideal` 和 `realistic` | 证明仿真移动、返航、降落 |
| P12 scan robustness | `just navlab-run scan-robustness ...` | 证明仿真扰动/scan 鲁棒性和原地降落 |

Stage 1 允许使用 Gazebo/SITL 生成可复现实验数据，但这些数据只能作为开发参考
和回归诊断。缺少 `ideal` 或 `realistic` artifact 时，不能因此 block
真机 preflight / prepare / task doctor；更不能把 Gazebo truth 作为控制、SLAM、
ExternalNav 或 landing 的输入。

### 4.2 Real Wrapper Entry

每一次真机飞行尝试都必须通过同一个 wrapper 入口运行。runtime backend/mode 从
环境变量读取：

```bash
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real \
just navlab-run hover
```

对应 orchestration 形态建议是：

```text
run hover
run exploration
run scan-robustness
```

不再暴露独立的 `doctor`、`prepare`、`hover doctor --stage real` 或
`hover run --stage real` operator 命令。wrapper 内部会写出 preflight summary，
并检查：

- `ok == true`
- `runtime_backend == "process"`
- `runtime_mode == "real"`
- required command / ROS package / Python module dependency checks 通过
- serial MAVLink probe 通过
- preflight summary 的时间没有超过配置的有效窗口

### 4.3 Real Prepare / Bringup Phase

preflight phase 通过后，wrapper 必须先进入 real prepare / bringup phase。
prepare 负责启动非 companion 的辅助进程，例如：

```text
mavlink-router
selected FCU ROS bridge
real lidar driver
SLAM runtime
optional rangefinder bridge
```

prepare 不能启动 Gazebo/SITL，也不能执行 arm/takeoff/land。它应写出 prepare
summary，记录启动了哪些 host process、mavlink-router 使用的串口、FCU bridge
mode、连接的本机 endpoint，以及 `/scan`、FCU topic、`/slam/odom` 是否开始可观测。

### 4.4 Task Doctor Phase

prepare phase 通过后，wrapper 必须运行 task doctor phase。task doctor 使用统一
helper 检查 companion 启动前置 topic：

```text
/scan
/tf
/tf_static
/navlab/mavlink/status
/navlab/fcu/local_position_pose
/mavlink_external_nav/status
/external_nav/status
/slam/odom
/navlab/slam/status
```

只有这些上游 topic ready 后，才能启动 companion 并进入 task run。

### 4.5 Real Flight Task Phase

后续 wrapper 应支持以下 task：

```text
hover
exploration
scan-robustness
```

task phase 只能在 real preflight、real prepare 和 task doctor 全部通过后执行。
它负责：

- 读取真机专用配置，例如 `takeoff_alt_m`。
- 获取 operator safety confirmation。
- 维护唯一 FCU owner。
- 执行 arm / takeoff / task body / landing。
- 输出 `acceptance_stage=real` 的 flight summary。

real flight task 不能重新启动仿真传感器，也不能 fallback 到 `just navlab-hover`
的 Docker/Gazebo 路径。

## 5. 真实数据源 contract

### 5.1 FCU 串口、MAVLink Router 和 fcu_bridge contract

真机 FCU 的 primary evidence 应来自真实串口 MAVLink，而不是 SITL endpoint。
运行时串口应由 `mavlink-router` 独占，再分发给所选 `fcu_bridge_mode`、
pymavlink probe、GCS 或日志工具。默认 real Stage 2 先实现
`fcu_bridge_mode = "navlab_mavlink"`，即使用 NavLab 自己的 MAVLink bridge，
不要求 MAVROS 或 `/ap/v1/*` DDS topic。

real preflight doctor 必须支持配置串口和依赖检查：

```toml
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
require_mode_observed = true
expected_autopilot = "ardupilotmega"
required_messages = ["HEARTBEAT", "SYS_STATUS", "ATTITUDE"]
optional_messages = ["LOCAL_POSITION_NED", "GLOBAL_POSITION_INT", "RANGEFINDER", "DISTANCE_SENSOR", "HIGHRES_IMU", "RAW_IMU", "SCALED_IMU"]

[real_preflight.dependencies]
required_command_groups = [
  ["mavlink-routerd", "mavlink-router"],
  ["ros2"]
]
required_ros_packages = [
  "navlab_slam_bringup",
  "navlab_cartographer_adapter",
  "navlab_external_nav_bridge",
  "navlab_slam_imu_bridge",
  "ydlidar_ros2_driver"
]
required_python_modules = ["navlab.sim.companion.runtime.cli", "navlab.common.slam.cli"]

[real_prepare]
fcu_bridge_mode = "navlab_mavlink"
```

preflight doctor 负责证明物理串口和依赖边界：

Note: `navlab.sim.companion.runtime.cli` and `navlab.common.slam.cli` are transitional import
checks. The target package boundary is `navlab.real`, `navlab.sim`, and
`navlab.common`, with companion runtime split into real/sim packages.

- serial device path 存在，例如 `/dev/ttyACM0`、`/dev/ttyUSB0` 或 udev symlink。
- 当前用户有读写权限。
- baudrate 配置存在。
- `mavlink-routerd` 或 `mavlink-router` 可执行。
- `fcu_bridge_mode` 注册器中声明的 ROS packages 可用。
- SLAM 和 companion host runtime 入口可用。

preflight doctor 可以短暂打开串口或使用 pymavlink probe 验证 HEARTBEAT，但必须
立即关闭。长期运行的串口所有权属于 real prepare 启动的 `mavlink-router`。

prepare 通过后，FCU 证据应优先来自：

- `mavlink-router` process summary：真实 serial path、baud、本机 endpoint。
- `fcu_bridge_mode` 对应的 ROS bridge topics。
- pymavlink 通过本机 router endpoint 观察到的 HEARTBEAT。

这一步不能通过 SITL router endpoint 替代。`tcp://127.0.0.1:5760` 或
`udp://127.0.0.1:14550` 只有在 prepare summary 能追溯到真实串口时，才可作为
真机 MAVLink evidence。

### 5.2 ROS topic contract belongs to prepare / task doctor

real preflight doctor 不检查 ROS topic readiness。以下 topic contract 属于
`real prepare` 和 `task doctor`：

```text
/scan
/tf
/tf_static
/slam/odom
/navlab/mavlink/status
/navlab/fcu/local_position_pose
/mavlink_external_nav/status
/external_nav/status
/imu
/rangefinder/down/range
/rangefinder/down/status
/navlab/fcu/controller/status
/navlab/fcu/owner/status
/navlab/landing/status
```

注意：当前真机 2D 雷达发布的 `/scan` 是水平 SLAM 输入，不是高度输入。
它负责帮助 SLAM / ExternalNav 证明水平位姿和 yaw；它不能替代下视测距、baro
或 FCU EKF 的高度 evidence。`prepare_external_nav_yaw_not_ready` 这类 blocker
表示 `/scan + IMU/pose evidence -> SLAM -> ExternalNav` 的水平 yaw 链路未 ready，
不是因为 2D 雷达不能测高。

其中 `/rangefinder/down/range` 可以来自真实下视测距或 FCU telemetry bridge。
2026-06-10 桌面举高测试已经确认：`/dev/ttyUSB1 @ 115200` 的 ArduPilot MAVLink
里存在真实变化的 `DISTANCE_SENSOR` 和 `RANGEFINDER`。举高时
`DISTANCE_SENSOR.current_distance` 从 0 附近变化到约 `45 cm`，对应
`RANGEFINDER.distance` 约 `0.45 m`；`orientation=25`，即
`MAV_SENSOR_ROTATION_PITCH_270`。因此 real path 的首选高度证据是 FCU
MAVLink `DISTANCE_SENSOR`，不是 2D `/scan`。

有效下视高度证据规则：

```text
DISTANCE_SENSOR
  orientation == MAV_SENSOR_ROTATION_PITCH_270
  current_distance > 0
  current_distance >= min_distance
  current_distance <= max_distance
```

实测中 `RANGEFINDER.distance` 出现过单次跳点，而同一时刻
`DISTANCE_SENSOR.current_distance` 仍保持在约 `42 cm`。所以 bridge 和 flight
gate 应优先使用 `DISTANCE_SENSOR.current_distance`，`RANGEFINDER.distance`
只作为辅助/诊断，不应单独放行 hover / landing。

如果 real path 有 ROS rangefinder bridge，它必须和 simulation 一样发布：

```text
/rangefinder/down/range
/rangefinder/down/status
```

如果真实 FCU 已经内部消费下视测距，但 ROS 侧暂时没有直接 topic，prepare 或
task doctor summary 必须
明确写出：

```json
{
  "rangefinder_source_claim": "real_fcu_distance_sensor",
  "rangefinder_ros_topic_claim": "not_available",
  "rangefinder_fcu_receive_evidence": {
    "message": "DISTANCE_SENSOR",
    "orientation": "MAV_SENSOR_ROTATION_PITCH_270",
    "valid_distance": "required"
  }
}
```

不能因为 ROS topic 缺失就用仿真 `/rangefinder/down/scan_ideal` 代替。

real task 的传感器 contract 分成三条线：

```text
1. FCU MAVLink / bridge:
  /dev/ttyUSB1 -> mavlink-router -> selected fcu_bridge_mode
  -> /navlab/mavlink/status
  -> /navlab/fcu/local_position_pose

2. 2D lidar / SLAM / yaw:
  /scan -> /slam/odom -> /external_nav/status -> FCU ExternalNav

3. height / rangefinder:
  FCU MAVLink DISTANCE_SENSOR, orientation=PITCH_270, valid distance range
  optional RANGEFINDER / baro / EKF height diagnostic evidence
  -> /rangefinder/down/range
  -> /rangefinder/down/status
  -> hover altitude and landing gates
```

simulation 里这三条线经常同时存在，所以不会暴露“2D 雷达不能测高”的问题；
real prepare 不能因此把水平 `/scan` 当成高度 source，也不能因为目前只接了
FCU bridge 和 SLAM/yaw 链就省掉 rangefinder / height evidence 链。

如果 real path 使用 MAVROS，prepare 或 task doctor summary 应记录 topic alias，例如：

```json
{
  "fcu_ros_bridge": "mavros",
  "mavros_state_topic": "/mavros/state",
  "pose_topic": "/mavros/local_position/pose",
  "imu_topic": "/mavros/imu/data"
}
```

## 6. Forbidden Simulation Inputs

Forbidden simulation input gate 属于 prepare / task doctor / task run 阶段，不属于
real preflight doctor。real mode 下出现以下 topic 或 source claim 必须 block：

```text
/gazebo/*
/scan_ideal
/sim/x2/status
/rangefinder/down/scan_ideal
Gazebo lidar source claim
SITL FCU source claim
SDF overlay source claim
motor disturbance overlay source claim
official maze input claim
```

注意：真实 lidar driver 也可能使用 `/lidar` 作为原始 topic。因此 forbidden
规则不能只靠名字硬编码，必须结合 source claim 判断。推荐 prepare / task doctor
把 SLAM 唯一输入稳定在 `/scan`，并在 summary 里记录：

```json
{
  "source_claims": {
    "scan": "real_lidar_driver_or_real_scan_stabilization",
    "fcu": "real_serial_mavlink_or_ardupilot_dds_bridge",
    "imu": "real_fcu_or_sensor",
    "rangefinder": "real_down_rangefinder_or_fcu_internal",
    "slam": "real_slam"
  }
}
```

## 7. 高度设置边界

真机起飞高度属于 real flight task 配置，不属于 preflight doctor 配置。

当前统一配置字段是：

```toml
[fcu_controller]
takeoff_alt_m = 0.5
```

real preflight doctor 可以读取并记录计划高度，但不能执行起飞。后续真机 flight
task 应在 summary 中记录：

```json
{
  "planned_takeoff_alt_m": 0.5,
  "takeoff_alt_source": "config:fcu_controller.takeoff_alt_m"
}
```

首飞时高度应使用独立真机配置文件控制，例如：

```bash
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real \
uv run --project orchestration python orchestration/main.py run hover \
  --config orchestration/config.real.toml
```

`run hover` wrapper 只有在 real preflight、real prepare 和 task doctor phase 全部
通过后，才允许进入 arm/takeoff。

## 8. Summary Schema

real preflight doctor summary 建议包含：

```json
{
  "ok": true,
  "blocked": false,
  "blockers": [],
  "runtime_backend": "process",
  "runtime_mode": "real",
  "preflight_claim": "evaluated",
  "flight_claim": "not_evaluated",
  "landing_claim": "not_evaluated",
  "checked_at": "2026-06-09T00:00:00Z",
  "valid_for_sec": 120,
  "real_preflight": {
    "dependencies": {
      "required_command_groups": [
        {
          "candidates": ["mavlink-routerd", "mavlink-router"],
          "found": true,
          "selected": "mavlink-routerd"
        },
        {
          "candidates": ["ros2"],
          "found": true,
          "selected": "ros2"
        }
      ],
      "required_ros_packages": {
        "navlab_slam_bringup": {"present": true},
        "navlab_external_nav_bridge": {"present": true},
        "ydlidar_ros2_driver": {"present": true}
      },
      "required_python_modules": {
        "navlab.sim.companion.runtime.cli": true,
        "navlab.common.slam.cli": true
      }
    },
    "serial_mavlink": {
      "enabled": true,
      "port": "/dev/ttyACM0",
      "baud": 115200,
      "serial_open_ok": true,
      "heartbeat_seen": true,
      "system_id": 1,
      "component_id": 1,
      "autopilot": "ardupilotmega",
      "vehicle_type": "quadrotor",
      "armed": false,
      "mode": "STABILIZE",
      "message_counts": {
        "HEARTBEAT": 3,
        "SYS_STATUS": 2,
        "ATTITUDE": 20,
        "DISTANCE_SENSOR": 8
      }
    }
  }
}
```

控制台输出不能只给 summary path。每次运行必须用显著的 panel/table 输出操作者
最需要立即判断的信息：

- `Status`: `OK` 或 `BLOCKED`。
- `Runtime`: backend + mode。
- `Serial MAVLink`: port、baud、serial open、heartbeat。
- `Deps`: `mavlink-router`、`ros2`、所选 FCU bridge、SLAM、companion 依赖概览。
- `FCU`: system/component id、autopilot、mode、armed。
- `Blockers`: 前若干个稳定 blocker 字符串。
- `Summary`: 完整 JSON artifact path。

real flight summary 应引用 preflight summary：

```json
{
  "acceptance_stage": "real",
  "real_preflight": {
    "ok": true,
    "artifact": "artifacts/ros/navlab_real_preflight_doctor/<run_id>/summary.json",
    "age_sec_at_takeoff": 42.0
  },
  "real_prepare": {
    "ok": true,
    "artifact": "artifacts/ros/navlab_real_prepare/<run_id>/summary.json"
  },
  "task_doctor": {
    "ok": true,
    "artifact": "artifacts/ros/navlab_hover_real_doctor/<run_id>/summary.json"
  },
  "real_landing_claim": "evaluated"
}
```

## 9. Blocker Rules

后续真机 flight task 入口必须在以下情况 blocked：

```text
real_preflight_missing
real_preflight_failed
real_preflight_expired
runtime_backend_must_be_process:<actual>
runtime_mode_must_be_real:<actual>
serial_port_missing:<path>
serial_port_permission_denied:<path>
serial_open_failed:<reason>
serial_mavlink_heartbeat_missing
serial_mavlink_autopilot_invalid
serial_mavlink_required_message_missing:<message>
serial_mavlink_unexpected_armed
required_command_missing:<command-or-group>
required_ros_package_missing:<package>
required_python_module_missing:<module>
real_prepare_missing
real_prepare_failed
task_doctor_missing
task_doctor_failed
simulation_stage_not_passed
manual_takeover_not_confirmed
kill_switch_not_confirmed
takeoff_altitude_not_configured
```

这些 blocker 应在 arm/takeoff 之前产生。只要出现 blocker，就不能进入飞行状态机。

## 10. 完成标准

本设计完成后，系统边界应当清楚：

- `just navlab-hover` 只代表 Gazebo/SITL Stage 1 hover，不代表真机 hover。
- 每次真机飞行前必须先跑 `NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real ... doctor`。
- wrapper 内部必须在 preflight 通过后进入 real prepare / bringup，再进入 task doctor。
- real preflight doctor 不触发电机或飞行动作。
- 真机 flight task 必须引用最新通过的 preflight、prepare 和 task doctor summary。
- real mode 下不能使用模拟串口、Gazebo lidar、SITL、SDF overlay 或仿真 rangefinder。
- 起飞高度由真机 flight task 的配置读取，不由 doctor 执行。
