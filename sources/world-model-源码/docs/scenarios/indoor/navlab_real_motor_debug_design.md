# NavLab 真机 Motor Debug 设计

## 1. 背景

`motor-debug` 是无桨台架调试任务，用来验证真实 FCU 到电调/电机的输出链路。
它不是 ArduPilot 的飞行模式，也不是 hover、定高或 landing readiness 的替代验收。

2026-06-10 的真实运行暴露了一个关键边界：

```text
motor_debug_arm_rejected:MAV_RESULT_FAILED
motor_debug_arm_rejected_status:Arm: RC not found
motor_debug_arm_rejected_status:Arm: GPS 1: Bad fix
```

这说明 `MAV_CMD_COMPONENT_ARM_DISARM` 到达了 FCU，但 ArduPilot 的 arming
precheck 拒绝 arm。问题不在 `COMMAND_LONG` 格式，而在 FCU 当前还按 GPS/RC
pre-arm 条件判断；同时 `motor-debug` 当时没有完整复用 real prepare 的
Cartographer / ExternalNav 链路。

NavLab simulation 已经按 ArduPilot Cartographer SLAM 路线配置无 GPS
ExternalNav：

```text
GPS_TYPE 0
GPS1_TYPE 0
VISO_TYPE 1
EK3_SRC1_POSXY 6
EK3_SRC1_VELXY 6
EK3_SRC1_YAW 6
```

真机 `motor-debug` 应该复用同一套链路，只把输入源换成真实硬件。

VIO tracking camera 文档虽然使用视觉 odometry，但它对 NavLab lidar SLAM 同样有
参考价值：核心不是相机，而是“外部定位源 -> ROS bridge -> MAVLink ExternalNav
message -> ArduPilot EKF”的流程。NavLab 的传感器换成 `/scan + /imu ->
Cartographer -> /slam/odom`，但 FCU 侧仍然需要看到稳定的外部定位输入、正确
frame/坐标转换、合适频率、EKF origin/home，以及禁 GPS 或将 EKF source 切到
ExternalNav。

参考：

- ArduPilot Cartographer SLAM:
  `https://ardupilot.org/dev/docs/ros-cartographer-slam.html`
- ArduPilot ROS VIO tracking camera:
  `https://ardupilot.org/dev/docs/ros-vio-tracking-camera.html`
- GPS / Non-GPS Transitions:
  `https://ardupilot.org/copter/docs/common-non-gps-to-gps.html`
- ArduPilot Guided mode:
  `https://ardupilot.org/dev/docs/copter-commands-in-guided-mode.html`
- Arming / disarming MAVLink command:
  `https://ardupilot.org/dev/docs/mavlink-arming-and-disarming.html`
- MAVLink `COMMAND_LONG` and `MAV_CMD_COMPONENT_ARM_DISARM`:
  `https://mavlink.io/en/messages/common.html#COMMAND_LONG`
  `https://mavlink.io/en/messages/common.html#MAV_CMD_COMPONENT_ARM_DISARM`

## 2. 目标

`motor-debug` 的目标是：

- 只在 `NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real` 下可运行。
- 必须先通过 real preflight doctor。
- 必须启动 real prepare，使 MAVLink router、FCU bridge、真实 lidar、Cartographer
  和 ExternalNav 链路 ready。
- 必须在 operator safety 和 no-props 确认后才进入非 dry-run。
- 必须切到并确认 ArduPilot `GUIDED`。
- 只发送 arm / hold / disarm，不发送 takeoff setpoint，不进入任务控制器。
- 成功路径是 4 个电机按 FCU armed idle 逻辑一起转动约 5 秒，然后 disarm。
- artifact 必须记录 MAVLink ACK、STATUSTEXT、连接 endpoint、prepare 证据和日志路径。

## 3. 非目标

- 不执行 `MAV_CMD_DO_MOTOR_TEST` 逐个电机测试作为默认流程。
- 不起飞。
- 不降落。
- 不发送位置、速度、姿态或高度 setpoint。
- 不把 `motor-debug` 结果当作 hover readiness。
- 不在 simulation runtime 下执行；simulation 只通过普通任务和 SITL 回归验证
  arm / ExternalNav 机制。
- 不用 force arm 掩盖 ExternalNav、GPS source 或 RC pre-arm 问题；force arm
  只能作为未来显式 bench-only override 设计，不能是默认行为。

## 4. Operator Flow

对外命令保持 wrapper 风格：

```text
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real \
just navlab-run motor-debug \
  --confirm-manual-takeover \
  --confirm-kill-switch \
  --confirm-safe-area \
  --confirm-no-props
```

内部流程：

```text
run motor-debug
  -> real preflight doctor
  -> real prepare for motor-debug
  -> real common doctor
  -> motor-debug task doctor / FCU link + ExternalNav + task config checks
  -> run startup parameter panel
  -> GUIDED gate: set GUIDED and confirm heartbeat mode
  -> MAV_CMD_COMPONENT_ARM_DISARM param1=1 param2=0
  -> hold 5 sec at FCU armed idle
  -> MAV_CMD_COMPONENT_ARM_DISARM param1=0 param2=0
  -> stop prepare services
```

`--dry-run` 只输出计划和配置来源，不 arm、不启动电机。

## 5. Prepare Contract

`motor-debug` 不能绕开 prepare 直接打开 `/dev/ttyUSB1`。真实串口只应由
`mavlink-router` 独占，任务本身连接 router 暴露的本机 endpoint。

目标链路：

```text
/dev/ttyUSB1 FCU MAVLink
  -> mavlink-router
  -> tcp:127.0.0.1:5760 / udpin:127.0.0.1:14550
  -> navlab_mavlink_bridge
  -> /navlab/mavlink/status
  -> /navlab/fcu/local_position_pose

/dev/ttyUSB0 real lidar + FCU IMU
  -> /scan + /imu
  -> Cartographer
  -> /slam/odom + /navlab/slam/status ready=true
  -> ExternalNav bridge
  -> /external_nav/status ready=true
  -> /mavlink_external_nav/status ready=true
```

对 `motor-debug` 来说，rangefinder/down height contract 不是必要 gate，因为它不
takeoff、不 hover、不 land。rangefinder 可以记录为上下文，但不能阻塞无桨台架
arm/idle/disarm 调试。

`motor-debug task doctor` 不要求进入时已经是 `GUIDED`。它记录
`required_mode=GUIDED`、当前 FCU mode 和 `guided_gate=run_stage`；真正的
`set_mode(GUIDED)`、heartbeat 确认和失败 blocker 属于 run 阶段，必须发生在
arm 之前。

## 6. FCU Parameter Contract

真机 FCU 参数必须和 simulation 的 ExternalNav profile 对齐，至少检查：

```text
GPS_TYPE == 0
GPS1_TYPE == 0
VISO_TYPE == 1
EK3_SRC1_POSXY == 6
EK3_SRC1_VELXY == 6
EK3_SRC1_YAW == 6
```

还必须检查 ExternalNav 数据不是只在 ROS 内 ready，而是真的进入 FCU/EKF：

```text
/slam/odom source == Cartographer / real lidar + real IMU
/external_nav/status.ready == true
/mavlink_external_nav/status.ready == true
FCU receives external navigation MAVLink messages
EKF origin / home position is set when required
FCU local position changes consistently during ground movement
```

这对应 VIO 文档里的地面测试口径：外部定位节点、MAVLink bridge 和 FCU 连接都要
先跑起来；FCU 侧要能看到外部定位消息；必要时设置 EKF origin/home；再拿起机体
移动，确认地面站或 ROS 中的位置变化和真实运动一致。

如果未来要支持室外 GPS 和室内 SLAM 之间切换，应参考 GPS / Non-GPS Transitions
文档，用 EKF source set 管理 GPS source 和 ExternalNav source。当前
`motor-debug` 不做 source 切换，但 arm 前应确认当前 active source 不再依赖 GPS。

`GPS 1: Bad fix` 出现在 arm rejected status 时，应被解释为：

```text
FCU is still using or requiring GPS for arming / EKF source.
```

这不是 motor command 问题，应优先检查 FCU 参数、ExternalNav 是否注入成功、
EKF source set 是否生效。

`Arm: RC not found` 是独立 pre-arm 条件。ExternalNav 不能解决 RC 缺失。该问题
需要通过真实 RC 输入、ArduPilot 参数策略，或未来显式 bench-only override 处理。

## 7. MAVLink Command Contract

arm / disarm 只使用 `COMMAND_LONG`：

```text
command = MAV_CMD_COMPONENT_ARM_DISARM
confirmation = 0

arm:
  param1 = 1
  param2 = 0

disarm:
  param1 = 0
  param2 = 0
```

默认 `param2=0`，不使用 force magic value。收到非 accepted ACK 时，任务必须继续
采集 `STATUSTEXT`，并把 ACK result 与 status text 一起写入 blockers。

示例 blocker：

```text
motor_debug_arm_rejected:MAV_RESULT_FAILED
motor_debug_arm_rejected_status:Arm: GPS 1: Bad fix
motor_debug_arm_rejected_status:Arm: RC not found
```

## 8. Artifact Contract

summary 至少记录：

- `serial` 和 `connection_endpoint`。
- `target_system`、`target_component`。
- run startup parameter panel：router endpoint、serial、motor_count、hold
  seconds、`required_mode=GUIDED`、`guided_gate=run_stage`、arm/disarm command。
- `required_mode=GUIDED` 和 run 阶段 guided observed result。
- arm/disarm ACK，包含 `result_name`、`result_param2`、`status_text`。
- `spin_mode=armed_idle`、`motor_count=4`、`motor_sec=5.0`。
- prepare summary path 或 prepare artifact reference。
- process log path 和 entry count。
- shutdown claim。

所有日志应进入当前 run artifact，便于复查 prepare、ExternalNav、FCU pre-arm
状态和 MAVLink response。

## 9. FSM

`motor-debug` 也应按有限状态机推进，而不是依靠隐式 if/else。建议状态：

```text
PREPARE_READY
  -> COMMON_DOCTOR_OK
  -> TASK_DOCTOR_OK
  -> GUIDED_CONFIRMED
  -> ARM_ACCEPTED
  -> HOLDING
  -> DISARMED
  -> CLEANUP_DONE
```

任一阶段都可以转入 `BLOCKED(reason)`，但必须继续执行 cleanup。`HOLDING`
表示无桨 armed idle 5 秒，不是 takeoff 或 hover。

## 10. Failure Interpretation

| Blocker | 含义 | 优先排查 |
|---|---|---|
| `motor_debug_guided_mode_not_confirmed` | run 阶段没有切到/观察到 GUIDED | mode mapping、FCU mode、MAVLink link |
| `motor_debug_arm_rejected:MAV_RESULT_FAILED` | FCU pre-arm 拒绝 | status text |
| `...GPS 1: Bad fix` | FCU 仍要求 GPS 或 EKF source 未切到 ExternalNav | `GPS_TYPE/GPS1_TYPE`、`EK3_SRC1_*`、ExternalNav status |
| `...RC not found` | RC pre-arm 条件不满足 | RC receiver、ArduPilot arming check 策略 |
| `mavlink_router_endpoint_no_heartbeat` | prepare router endpoint 不通 | router process、serial ownership |
| `external_nav_status_not_ready` | SLAM -> ExternalNav 链路未 ready | `/slam/odom`、`/external_nav/status`、bridge logs |
| `external_nav_not_seen_by_fcu` | ROS 侧 ready 但 FCU 没收到外部定位 | MAVLink message stream、frame conversion、EKF origin/home |

## 11. 完成标准

- dry-run 输出显示 `GUIDED`、arm/disarm command、hold seconds、no-props
  requirement 和配置来源。
- 非 dry-run 缺任一 operator safety/no-props 确认时 blocked。
- 非 dry-run 必须先启动 prepare，再执行 motor-debug，最后关闭 prepare。
- motor-debug 使用 router endpoint，不直接抢真实 FCU serial。
- task doctor 不因为当前不是 `GUIDED` 阻塞；run 阶段必须先切到并确认
  `GUIDED`，然后才允许 arm。
- FCU 参数检查能在 arm 前指出 ExternalNav/GPS source mismatch。
- ground test 能证明 FCU 侧已经收到 ExternalNav，且移动机体时 local position
  与真实运动一致。
- arm rejected 时 blocker 包含 `MAV_RESULT_*` 和 `STATUSTEXT`。
- 真机无桨台架上成功完成 arm -> hold 5 sec -> disarm，summary `ok=true`。
