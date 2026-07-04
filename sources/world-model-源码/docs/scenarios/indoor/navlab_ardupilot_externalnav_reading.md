# ArduPilot ExternalNav / Non-GPS 文档阅读

## 1. 阅读范围

这份阅读笔记服务于 NavLab 真机 `motor-debug`、real prepare、hover/P8/P12 的
ExternalNav 链路设计。关注点不是照抄某一种传感器，而是抽取 ArduPilot 侧对
非 GPS 定位、EKF source、GUIDED 和 arm/disarm 的共同要求。

官方文档：

- Cartographer SLAM for Non-GPS Navigation:
  `https://ardupilot.org/dev/docs/ros-cartographer-slam.html`
- ROS and VIO tracking camera for non-GPS Navigation:
  `https://ardupilot.org/dev/docs/ros-vio-tracking-camera.html`
- GPS / Non-GPS Transitions:
  `https://ardupilot.org/copter/docs/common-non-gps-to-gps.html`
- Copter Commands in Guided Mode:
  `https://ardupilot.org/dev/docs/copter-commands-in-guided-mode.html`
- Arming and Disarming:
  `https://ardupilot.org/dev/docs/mavlink-arming-and-disarming.html`
- MAVLink `COMMAND_LONG` / `MAV_CMD_COMPONENT_ARM_DISARM`:
  `https://mavlink.io/en/messages/common.html#COMMAND_LONG`
  `https://mavlink.io/en/messages/common.html#MAV_CMD_COMPONENT_ARM_DISARM`

## 2. Cartographer SLAM 文档给 NavLab 的结论

Cartographer 文档证明了“2D lidar -> ROS SLAM -> MAVLink vision / ExternalNav
-> ArduPilot EKF”是 ArduPilot 支持的非 GPS 路线。文档中的传感器是 RPLidarA2，
NavLab 使用的是真实 YDLidar X2，但 FCU 侧关心的是外部位姿消息和 EKF source，
不是激光雷达品牌。

可迁移到 NavLab 的点：

- 真实 lidar 接 companion，发布 `/scan`。
- Cartographer 消费 scan，并输出本地位姿。
- ROS / bridge 把 SLAM 位姿送入 FCU 的 ExternalNav / vision input。
- ArduPilot 参数需要切到 EKF3，并把水平位置、水平速度和 yaw source 设为
  ExternalNav。
- GPS 应禁用或不能作为室内 arm / EKF 的必要 source。
- 参数变更后需要重启 FCU。
- FCU 侧必须看到 external nav 被 EKF 使用，而不是只看 ROS topic ready。

对当前代码的含义：

```text
/dev/ttyUSB0 real lidar
  -> /scan
  -> Cartographer
  -> /slam/odom
  -> ExternalNav bridge
  -> FCU EKF ExternalNav source
```

因此 `motor-debug` 如果出现 `GPS 1: Bad fix`，优先怀疑：

- FCU 参数仍在要求 GPS。
- EKF source 没切到 ExternalNav。
- ExternalNav ROS topic ready 但没有真正进入 FCU。
- EKF origin/home 未设置或 EKF 未开始融合 external nav。

## 3. VIO Tracking Camera 文档给 NavLab 的结论

VIO 文档虽然使用 tracking camera，但流程和 lidar SLAM 本质一致：

```text
external pose source
  -> ROS transform / odometry node
  -> MAVLink vision / ExternalNav message
  -> ArduPilot EKF
```

NavLab 不使用 VIO camera，但必须继承它的地面测试纪律：

- 启动所有 ROS node 和 FCU bridge。
- 确认 FCU 正在收到 external nav / vision position 消息。
- 必要时设置 `SET_GPS_GLOBAL_ORIGIN` 和 `SET_HOME_POSITION`，或者用 GCS 设置
  EKF origin。
- 拿起机体走一个小范围轨迹，确认 GCS / ROS 显示的位置变化和真实运动一致。
- 地面确认通过后，再考虑 arm / flight。

对 NavLab 的直接要求：

- `real prepare` 不能只检查 `/external_nav/status.ready=true`。
- 还应增加 FCU-side evidence：FCU 是否收到 external nav message、local position
  是否随地面移动合理变化、EKF origin/home 是否已设置。
- `motor-debug` arm 前应把这些 evidence 写入 summary。

## 4. GPS / Non-GPS Transitions 文档给 NavLab 的结论

这个文档说明 ArduPilot 支持 GPS 和非 GPS source set 的切换。关键点：

- 使用 EKF3。
- 可以配置多组 EKF source set。
- GPS 环境通常作为 source set 1。
- 非 GPS 环境可以作为 source set 2，例如 ExternalNav。
- 可以用 RC auxiliary switch 配置 `EKF Pos Source` 手动切换 source set。
- 切换后应观察 GCS 消息，等待 EKF 保持 healthy。
- 日志里会记录 source set 切换事件，`XKFS.SS` 可看当前 active source。

对 NavLab 的解释：

- 如果 NavLab 当前是纯室内无 GPS流程，`EK3_SRC1_* = ExternalNav` 是直接路线。
- 如果未来要做室内/室外切换，应采用 source set 设计，例如：

```text
SRC1 = GPS
SRC2 = ExternalNav
RCx_OPTION = 90  # EKF Pos Source
```

- 当前 `motor-debug` 不需要做 GPS/Non-GPS 切换，但可以借用这个文档的验证方法：
  arm 前确认 active source 真的已经是 ExternalNav，而不是 GPS source。
- `RC not found` 不是 ExternalNav 问题，也不属于 common doctor 的共享 blocker；
  它留给 arm / task 阶段作为独立 pre-arm 诊断。

## 5. Guided Mode 文档给 NavLab 的结论

Guided 文档把 movement command 限定在 Guided 语义下。对 NavLab 的规则是：

- 所有盒子主动控制都必须基于 ArduPilot `GUIDED`。
- `motor-debug` 必须先切到并观察到 `GUIDED`。
- `motor-debug` 不发送 `SET_POSITION_TARGET_*`、`SET_ATTITUDE_TARGET` 或 takeoff
  command；它只用 arm/hold/disarm 验证电机 idle 输出链路。
- hover/P8/P12 之后如果要发送 movement setpoint，才进入 Guided movement
  command contract。

## 6. Arming / Disarming 与 MAVLink 文档给 NavLab 的结论

arm/disarm 的正确 MAVLink contract 是：

```text
message = COMMAND_LONG
command = MAV_CMD_COMPONENT_ARM_DISARM
confirmation = 0

arm:
  param1 = 1
  param2 = 0

disarm:
  param1 = 0
  param2 = 0
```

`param2=0` 表示遵守 safety checks。`param2=21196` 是 force arm/disarm，能尝试
绕过 arming checks。NavLab 默认不应该用 force arm 掩盖配置问题。

对当前 blocker 的解释：

```text
MAV_RESULT_FAILED + STATUSTEXT
```

表示 FCU 收到了命令，但 pre-arm 条件失败。它不是 `COMMAND_LONG` 格式错误。
因此系统必须收集 `COMMAND_ACK` 和随后的 `STATUSTEXT`，把失败原因明确分类。

## 7. 当前 Motor Debug 的正确判断

最近真实 blocker：

```text
motor_debug_arm_rejected:MAV_RESULT_FAILED
motor_debug_arm_rejected_status:Arm: RC not found
motor_debug_arm_rejected_status:Arm: GPS 1: Bad fix
```

阅读后的判断：

- `GPS 1: Bad fix`：FCU 仍然在 arming / EKF source 上要求 GPS，或者 ExternalNav
  没有真正进入 FCU/EKF。应检查 GPS 参数、EKF source、ExternalNav message、
  EKF origin/home 和 active source。
- `RC not found`：独立 RC/pre-arm 条件。ExternalNav 不能解决。需要真实 RC 输入、
  参数策略，或未来明确 bench-only override 设计。
- 不应该先上 force arm。先把 ExternalNav 和 RC/pre-arm 条件拆清楚。

## 8. 建议落到代码里的检查

arm 前增加 `motor-debug task doctor`：

- 参数读取：
  - `AHRS_EKF_TYPE`
  - `EK3_ENABLE`
  - `EK2_ENABLE`
  - `GPS_TYPE`
  - `GPS1_TYPE`
  - `VISO_TYPE`
  - `EK3_SRC1_POSXY`
  - `EK3_SRC1_VELXY`
  - `EK3_SRC1_YAW`
- ROS readiness：
  - `/scan` fresh
  - `/imu` fresh
  - `/slam/odom` fresh
  - `/navlab/slam/status.ready=true`
  - `/external_nav/status.ready=true`
  - `/mavlink_external_nav/status.ready=true`
- FCU-side readiness：
  - external nav MAVLink messages observed or bridge status proves FCU send success
  - local position valid
  - EKF origin/home set if required
  - active EKF source is ExternalNav when available in telemetry/logs
- Arm rejection classification:
  - `GPS 1: Bad fix` -> `external_nav_or_gps_source_not_ready`
  - `RC not found` -> 独立 RC/pre-arm 诊断，不是 common doctor 的 shared blocker
  - other `STATUSTEXT` -> preserve raw text in summary

## 9. 结论

NavLab 的 lidar SLAM 和官方 VIO camera route 是同一种 ArduPilot ExternalNav
问题：传感器不同，FCU/EKF contract 相同。`motor-debug` 要跑通，优先级应是：

```text
real prepare starts router + lidar + SLAM + ExternalNav
FCU parameters match ExternalNav route
FCU confirms external nav / local position
GUIDED confirmed
operator + no-props confirmed
arm -> hold -> disarm
```

只有这条链路跑通，`motor-debug` 才能说明真实盒子链路和电机 idle 输出链路是可信的。
