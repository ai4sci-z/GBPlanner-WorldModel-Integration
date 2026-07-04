# NavLab 真机 Prepare 与 Task Doctor 设计

## 1. 背景

真机路径不是 Docker/compose 仿真路径，但也不是只让 companion 直接读
`/dev/ttyACM0`。真实系统应由 host process 管理多个辅助进程：

```text
FCU serial MAVLink
  -> mavlink-router
  -> local MAVLink endpoints
  -> selected FCU bridge mode
  -> ROS FCU topics

real 2D lidar driver
  -> /scan

2D lidar /scan + FCU IMU/pose evidence
  -> SLAM
  -> /slam/odom

height / rangefinder evidence
  -> FCU MAVLink DISTANCE_SENSOR, preferred
  -> FCU MAVLink RANGEFINDER, secondary/diagnostic
  -> /rangefinder/down/range
  -> /rangefinder/down/status

verified upstream topics
  -> companion
  -> task controller / mission / landing
```

因此真机入口对外只保留一个 wrapper：

```text
run <task>
  -> real preflight doctor
  -> real prepare / bringup
  -> real common doctor
  -> task doctor
  -> task run
```

## 2. 目标

本设计定义真机 Stage 2 的 host process 启动顺序和检查边界：

- `run <task>` 是唯一对外入口。
- `real preflight doctor`、`real prepare`、`task doctor` 都是 wrapper 内部阶段。
- `real common doctor` 是 wrapper 内部的 FCU / EKF / ExternalNav 共同状态检查阶段。
- `real preflight doctor` 只检查硬件、依赖、配置和禁止仿真输入。
- `real prepare` 在 preflight 通过后启动非 companion 的辅助进程。
- `real common doctor` 在 prepare 后检查 FCU / EKF / ExternalNav 共同状态。
- `task doctor` 使用统一 helper 检查 companion 启动前置 topic 和 task readiness。
- `task run` 才允许进入 arm / takeoff / mission / landing。
- 2D lidar 只作为水平 SLAM / yaw / obstacle evidence，不作为高度传感器。
- hover / landing 的高度 evidence 优先来自 FCU MAVLink `DISTANCE_SENSOR`
  下视测距；`RANGEFINDER` 可作为辅助/诊断，baro、EKF height 或明确配置的
  高度源可作为补充；不能由水平 2D `/scan` 推断。
- real hover / landing 还必须检查定高模式本身：task doctor 要记录
  `altitude_hold_mode`、当前 FCU mode、rangefinder 是否被该模式使用，以及该模式
  是否允许室内无 GPS 定高；不能只因为 rangefinder topic ready 就放行真实 hover。
- 如果 real path 有 ROS rangefinder bridge，它必须发布与 simulation 相同的
  `/rangefinder/down/range` 和 `/rangefinder/down/status` contract。

## 3. 非目标

本设计不把 doctor 变成飞行执行器：

- doctor 不 arm。
- doctor 不 takeoff。
- doctor 不 land。
- doctor 不发布 movement setpoint。
- doctor 不启动 Gazebo/SITL/gazebo-sensor。
- preflight doctor 不长期占用 FCU 串口。
- prepare 不启动 companion，不执行具体任务。
- common doctor 不启动或停止任何进程，只读取 prepare 后的状态。

## 4. 阶段定义

### 4.1 Real Preflight Doctor

`real preflight doctor` 是常规硬件和依赖检查。它回答：

> 当前 host 是否具备启动真机辅助链路的条件？

它检查：

- runtime 是 `process + real`。
- FCU serial path 存在，权限正确，例如 `/dev/ttyACM0` 或 udev symlink。
- `mavlink-routerd` 或 `mavlink-router` 可执行文件存在。
- `ros2` CLI 可用。
- 所选 `fcu_bridge_mode` 相关 package 存在。默认 `navlab_mavlink` 不要求 MAVROS。
- SLAM package 存在，例如 `navlab_slam_bringup`、`navlab_cartographer_adapter`。
- companion / SLAM Python 入口可 import。当前过渡入口仍可能是
  `navlab.sim.companion.runtime.cli`、`navlab.common.slam.cli`；目标边界是 real/sim runtime
  分别进入 `navlab.real.*` 和 `navlab.sim.*`，共享纯工具进入 `navlab.common`。
- 配置中没有 Gazebo/SITL/X2 virtual serial/SDF overlay 作为 real source claim。

preflight doctor 可以短暂打开串口证明物理边界，但必须立即关闭。后续运行时串口
所有权应交给 `mavlink-router`。

### 4.2 Real Prepare / Bringup

`real prepare` 是有副作用的预处理工作。它只能在 preflight doctor 通过后运行。

它负责启动 companion 之前的辅助进程：

| 辅助进程 | 输入 | 输出 | 作用 |
|---|---|---|---|
| `mavlink-router` | FCU serial，例如 `/dev/ttyACM0:115200` | local TCP/UDP MAVLink endpoints | 独占串口并分发 MAVLink |
| selected FCU bridge | mavlink-router local endpoint | FCU bridge topics | 把 MAVLink / FCU evidence 转成 ROS graph 可读状态 |
| real 2D lidar driver | 真实 2D 雷达设备 | `/scan` | 提供水平 SLAM scan，不提供高度 |
| SLAM runtime | `/scan`、IMU/odom source | `/slam/odom`、`/navlab/slam/status` | 提供水平位姿和 yaw 的 ExternalNav 输入 |
| height / rangefinder bridge | FCU telemetry 中的下视 `DISTANCE_SENSOR`，辅助 `RANGEFINDER`、baro、EKF height 或明确配置的高度源 | `/rangefinder/down/range`、`/rangefinder/down/status`，或无 ROS bridge 时的 FCU telemetry evidence | 记录 hover / landing 高度 evidence |

`real prepare` 不启动 companion。原因是 companion 依赖上游 FCU、scan、SLAM topic
已经可观测；上游没准备好时启动 companion 会把问题混成 companion runtime 失败。

prepare summary 应记录：

```json
{
  "prepare_claim": "evaluated",
  "started_services": ["mavlink-router", "navlab_mavlink_bridge", "lidar", "slam"],
  "mavlink_router": {
    "serial": "/dev/ttyACM0",
    "baud": 115200,
    "local_endpoint": "tcp://127.0.0.1:5760"
  },
  "fcu_bridge_mode": {
    "name": "navlab_mavlink",
    "required_topics": [
      "/navlab/mavlink/status",
      "/navlab/fcu/local_position_pose",
      "/mavlink_external_nav/status",
      "/external_nav/status"
    ]
  },
  "blocked": false,
  "blockers": []
}
```

### 4.2.1 三链路 sensor contract

real Stage 2 必须和 simulation 一样把“水平定位”和“高度”分开，而不是把 2D lidar
误当成 rangefinder。完整 contract 是三条链：

```text
1. FCU MAVLink / bridge evidence:
   /dev/ttyUSB1
   -> mavlink-router
   -> selected fcu_bridge_mode
   -> /navlab/mavlink/status
   -> /navlab/fcu/local_position_pose

2. 2D lidar / SLAM / yaw evidence:
   /dev/ttyUSB0 2D lidar
   -> /scan
   -> /slam/odom
   -> /external_nav/status
   -> /mavlink_external_nav/status

3. height / rangefinder evidence:
   FCU MAVLink DISTANCE_SENSOR, orientation=PITCH_270, valid distance range
   optional RANGEFINDER / baro / EKF height diagnostic evidence
   -> /rangefinder/down/range
   -> /rangefinder/down/status
   -> hover altitude and landing readiness
```

如果第三条链通过 ROS bridge 暴露，就必须使用 simulation 已经采用的 topic 名：
`/rangefinder/down/range` 和 `/rangefinder/down/status`。如果真实 FCU 只在内部消费
baro / rangefinder，暂时没有 ROS bridge，prepare/task doctor summary 也必须记录
FCU telemetry evidence；但这只能作为“无 ROS bridge 的兼容 claim”，不能把水平
2D `/scan` 冒充高度 evidence。

2026-06-10 真机桌面举高测试确认：FCU 串口 `/dev/ttyUSB1 @ 115200` 会发布
`DISTANCE_SENSOR` 和 `RANGEFINDER`，并且举高时数值从 0 附近变化到约
`0.45 m`。其中 `DISTANCE_SENSOR.current_distance` 与实际举高过程稳定对应，
`orientation=25` 即 `MAV_SENSOR_ROTATION_PITCH_270`，应作为 real height bridge
的主输入。`RANGEFINDER.distance` 也会变化，但实测出现过一次跳点
`6.530 m`，因此只能作为辅助/诊断输入，不能单独作为飞行 gate 的强证据。

有效下视高度 evidence 的最小规则：

```text
DISTANCE_SENSOR
  orientation == MAV_SENSOR_ROTATION_PITCH_270
  current_distance > 0
  current_distance >= min_distance
  current_distance <= max_distance
```

real rangefinder ROS bridge 的转换规则：

```text
FCU MAVLink DISTANCE_SENSOR
  -> sensor_msgs/Range on /rangefinder/down/range
  -> std_msgs/String JSON status on /rangefinder/down/status
```

这样 real path 和 simulation path 使用相同 topic contract；区别只是 simulation
从 Gazebo `/rangefinder/down/scan_ideal` 生成高度，而 real 从 FCU telemetry
里的真实下视 `DISTANCE_SENSOR` 生成高度。

### 4.2.2 2D lidar、yaw 和高度边界

当前真机 2D 雷达是水平扫描传感器。它的职责是：

- 发布真实 `/scan`。
- 给 SLAM 提供水平几何约束。
- 通过 `/scan + IMU/pose evidence -> SLAM -> /slam/odom -> ExternalNav`
  证明室内水平位姿和 yaw readiness。

它不是高度传感器。不能把 2D `/scan` 当成下视测距，也不能从水平扫描里推断
hover 高度。simulation 里之所以没有暴露这个问题，是因为仿真链路同时有：

- Gazebo/SITL 中的 FCU altitude / EKF / baro / rangefinder 等高度 evidence。
- 由仿真世界提供的理想或受控 scan/IMU/pose 数据。
- Stage 1 中的 `/scan -> SLAM -> ExternalNav -> FCU` 仿真闭环只作设计参考和回归诊断，不作为真机 wrapper gate。

real prepare 的 `prepare_external_nav_yaw_not_ready` 表示第二条水平 SLAM/ExternalNav
yaw 链路没有 ready；它不是“缺高度”或“2D 雷达不能测高”的 blocker。

`hover`、`exploration`、`scan-robustness` 可以共享水平 SLAM/yaw gate；只有实际
arm/takeoff/landing 前的 task/flight gate 才需要把高度 evidence 升级成飞行安全条件。

### 4.2.3 SLAM yaw 链路必须对齐 simulation

simulation 中能通过 yaw gate，不是因为只看到 `/scan` topic 名存在，而是因为完整
SLAM runtime 被启动：

```text
Gazebo / official odometry + X2 scan + IMU evidence
  -> ydlidar_ros2_driver /scan
  -> cartographer_ros backend
  -> navlab_cartographer_adapter
  -> /slam/odom + /navlab/slam/status
  -> navlab_external_nav_bridge
  -> /external_nav/status
```

real prepare 也必须用同一条 contract，只把输入源换成真实设备：

```text
/dev/ttyUSB0 real lidar -> /scan
/dev/ttyUSB1 FCU MAVLink -> /imu/data and FCU pose evidence
cartographer_ros -> TF
navlab_cartographer_adapter -> /slam/odom
navlab_external_nav_bridge -> /external_nav/status
```

因此 real prepare 的 SLAM launch 必须显式设置：

```text
launch_cartographer_backend:=true
publish_placeholder_odom:=false
scan_topic:=/scan
imu_source_topic:=/imu/data
imu_topic:=/imu
cartographer_odometry_topic:=/odometry
odom_topic:=/slam/odom
external_nav_input_odom_topic:=/slam/odom
```

如果本机缺 `cartographer_ros`，doctor 应先把它作为缺失依赖警告并可安装；不能
因为少装 Cartographer 就让 adapter 或 FCU pose TF 假装成已通过 SLAM yaw gate。

### 4.3 Real Common Doctor

`real common doctor` 是 prepare 后、task-specific 检查前的共同状态检查阶段。它回答：

> 辅助进程已经启动后，FCU / EKF / ExternalNav 是否处在与当前 real path 一致的状态？

这个阶段最适合输出 operator 需要直接看到的 FCU/EKF 面板，因为此时
`mavlink-router`、FCU bridge、SLAM、ExternalNav bridge 都已经运行，能够检查
ROS-ready 和 FCU-side evidence 是否一致。

RC input 只作为状态展示和后续 arm 诊断参考，不作为 common doctor 的共享硬前置。

common doctor 至少输出：

```text
FCU ExternalNav / EKF
  GPS_TYPE / GPS1_TYPE
  VISO_TYPE
  EK3_SRC1_POSXY / VELXY / YAW / POSZ
  EK3_SRC2_POSXY / VELXY / YAW / POSZ
  active source set: SRC1/SRC2/SRC3/unknown
  external nav ROS ready: true/false
  external nav seen by FCU: true/false/unknown
  local position valid: true/false/unknown
  EKF origin/home: set/missing/unknown
  RC input: present/missing/unknown
```

common doctor 的 blocker 应区分配置、链路和 pre-arm 条件：

| Blocker | 含义 |
|---|---|
| `ekf_source_requires_externalnav:SRC2` | 当前 active source set 要求 ExternalNav |
| `external_nav_not_seen_by_fcu` | ROS 侧 ready，但 FCU/EKF 侧没有 external nav evidence |
| `external_nav_or_gps_source_not_ready` | FCU 仍要求 GPS 或 EKF source 与室内 ExternalNav 不一致 |
| `ekf_origin_or_home_missing` | ExternalNav 路线需要的 origin/home evidence 缺失 |

如果 `active source = SRC2` 且 `SRC2` 配置为 ExternalNav，但 FCU 没看到 ExternalNav，
common doctor 必须 blocked，而不是让后续 task 再收到 opaque `MAV_RESULT_FAILED`。

### 4.4 Task Doctor

`task doctor` 是 companion 和具体任务前置检查。它回答：

> 当前上游 topic 是否足够让 companion 启动，并且当前 task 是否具备执行条件？

所有真机 task doctor 应复用统一 helper，例如：

```text
check_real_task_upstream_topics(task_name, config)
```

统一 helper 至少检查：

- `/scan` 存在、新鲜、frame 符合配置。
- `/tf`、`/tf_static` 存在。
- FCU ROS status / pose / velocity topic 存在。
- MAVROS state 或等价 FCU bridge state 存在。
- `/slam/odom` 存在、新鲜、frame 符合配置。
- `/navlab/slam/status` ready。
- hover / landing 需要高度 evidence 时，优先检查 FCU MAVLink `DISTANCE_SENSOR`
  下视测距是否有效；`RANGEFINDER`、baro、EKF height 或配置的 height source
  只能作为辅助/补充 evidence。
- 如果高度 evidence 通过 ROS bridge 暴露，必须检查 `/rangefinder/down/range`
  和 `/rangefinder/down/status`；水平 2D `/scan` 不能替代。
- hover / landing 还必须检查 real 定高模式 readiness：配置的
  `altitude_hold_mode` 与当前 FCU mode / EKF / rangefinder 使用状态一致，且无 GPS
  室内场景下不会退化成未验证的 baro-only 或 manual hold。
- 室内 SLAM 真机任务必须有 `external_nav_yaw_ready=true` 的 yaw source evidence；
  未校准磁罗盘本身不单独 blocked，但罗盘校准和 manual override 都不能替代
  ExternalNav/SLAM yaw readiness。
- 没有 forbidden simulation topic/source。

各 task 再追加自己的要求：

| task | 追加检查 |
|---|---|
| `hover` in real mode | hover 高度、landing policy、FCU mode/armed 初始状态 |
| `exploration` in real mode / P8 | return-home policy、home source、bounded movement limits |
| `scan-robustness` in real mode / P12 | scan stabilization / tilt robustness status |

task doctor 可以检查 companion 是否已运行和 companion status topic 是否 ready，但不应自己
执行 arm/takeoff。若需要启动 companion，应由 wrapper 内部的 companion prepare/run
phase 完成。

### 4.5 Task Run

`task run` 才是真机飞行执行阶段。它必须引用：

- 可选记录 Stage 1 Gazebo/SITL summaries 作为诊断引用，但缺失时不能 block 真机 wrapper。
- 最新通过且未过期的 real preflight summary。
- 最新通过的 real prepare summary。
- 最新通过的 task doctor summary。
- operator safety confirmation。

## 5. 推荐命令结构

建议 CLI/justfile 逐步收敛到一个对外 wrapper：

```text
just navlab-run hover
just navlab-run exploration
just navlab-run scan-robustness
```

对应 orchestration 命令可以是：

```text
run hover
run exploration
run scan-robustness
```

wrapper 读取环境变量决定 backend/mode 和 real/simulation 路径，不使用 `--stage`：

```text
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real run hover
```

wrapper 内部仍应按顺序执行：

```text
preflight doctor -> real prepare -> real common doctor -> task doctor -> companion/task run
```

不能把 prepare 的副作用隐藏进 doctor，也不能把 `doctor` 或 `prepare`
暴露成单独的 operator 入口。它们是 wrapper 的内部 phase，只出现在日志、
summary 和调试 artifact 里。

## 6. MAVLink Router 和 FCU Bridge Contract

真机 FCU 串口推荐只由 `mavlink-router` 独占：

```text
mavlink-routerd -t 5760 -e 127.0.0.1:14550 /dev/ttyACM0:115200
```

FCU bridge 不直接抢 `/dev/ttyACM0`，而是连接 mavlink-router 暴露的本机 endpoint。
这样 pymavlink probe、NavLab MAVLink bridge、MAVROS、日志工具和 GCS 可以共享 MAVLink 流。

doctor 中允许的 MAVLink endpoint 必须能追溯到 real prepare summary 中的真实串口。
不能把 SITL endpoint 当成真实 FCU 证据。

手工串口桥，例如：

```text
socat -d -d /dev/ttyUSB1,b115200,raw,echo=0 /dev/ttyUSB2,b115200,raw,echo=0
```

只能用于孤立调试，不能和 real prepare / `mavlink-router` 同时运行。它会占用真实
串口并改变 MAVLink 拓扑，导致 serial provenance 和 endpoint probe 失真。进入
`just navlab-doctor` 或 `just navlab-run <task>` 前，必须先停止这类 tmux/socat/
stty/python 临时桥。

## 7. Wrapper FSM

真机 wrapper 应按有限状态机实现，而不是散落的 if/else。推荐状态：

```text
INIT
  -> PREFLIGHT_OK
  -> PREPARE_STARTING
  -> PREPARE_READY
  -> COMMON_DOCTOR_OK
  -> TASK_DOCTOR_OK
  -> GUIDED_CONFIRMED
  -> ARM_ACCEPTED
  -> HOLDING or TASK_RUNNING
  -> DISARMED
  -> CLEANUP_DONE
```

任一阶段都可以转入：

```text
BLOCKED(reason)
CLEANUP_REQUIRED
```

状态转换必须写入 summary，至少包含当前状态、上一状态、blocker、artifact
引用和是否需要 cleanup。`motor-debug` 的 `HOLDING` 是无桨 armed-idle hold；
hover/P8/P12 的 `TASK_RUNNING` 才允许进入 takeoff / movement / landing。

## 8. 完成标准

- preflight doctor 能在不启动进程的情况下定位缺依赖、缺硬件、错误 source claim。
- prepare 只在 preflight 通过后启动非 companion 辅助进程。
- common doctor 输出 FCU / EKF / ExternalNav / RC 的共同 readiness。
- task doctor 复用统一 upstream topic helper，并只追加 task-specific readiness。
- companion 只在 FCU、scan、SLAM 等上游 ready 后启动。
- task run 只在 preflight / prepare / common doctor / task doctor / operator safety 全部通过后进入 arm/takeoff。
