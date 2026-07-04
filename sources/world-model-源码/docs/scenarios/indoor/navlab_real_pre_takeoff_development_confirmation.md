# NavLab 真机起飞前开发确认文档

## 结论

完成 `docs/scenarios/indoor/todos/real_flight_preflight_doctor_todo.md` 只能说明
真机入口可以继续进入下一层检查，不能说明可以 `arm`、`takeoff` 或 `hover`。

真机起飞前必须把下面两份文档合并判断：

- `docs/scenarios/indoor/todos/real_flight_preflight_doctor_todo.md`
- `docs/scenarios/indoor/todos/real_prepare_and_task_doctor_todo.md`

当前开发结论是：

```text
preflight.ok=true
  -> 只允许进入 real prepare / task doctor
prepare.ok=true + task_doctor.ok=true + safety confirmed
  -> 才允许进入真实 arm/takeoff 前的最终人工确认
```

也就是说，preflight 是入口边界；prepare / task doctor 是起飞前开发 gate；operator
safety 是真正 arm/takeoff 前的最后 gate。

## 分层对比

| 层级 | Simulation hover 已证明 | Real preflight 后证明 | 起飞前还必须证明 |
|---|---|---|---|
| Runtime 边界 | Docker/Gazebo/SITL 环境可跑 | `process + real`，不会 fallback 到 simulation | wrapper 后续 phase 也保持 real mode |
| FCU | SITL autopilot 可通信 | `/dev/ttyUSB1` 真 FCU 串口可开，MAVLink HEARTBEAT 可见 | mavlink-router / FCU bridge 可持续运行且 topic 健康 |
| 依赖 | 仿真容器/包可用 | host 上 command、ROS package、Python 入口存在 | 依赖不只是存在，还要在 prepare 中实际启动健康 |
| 2D lidar / SLAM / yaw | Gazebo scan + IMU + Cartographer + ExternalNav 已跑通 | preflight 不启动这些 | real prepare 必须证明 `/scan`、`/imu`、`/slam/odom`、`/external_nav/status.ready=true` |
| Height / rangefinder | Gazebo down rangefinder -> `DISTANCE_SENSOR` -> `/rangefinder/down/*` | preflight 最多记录 MAVLink telemetry | real prepare/task doctor 必须证明 `/rangefinder/down/range`、`/rangefinder/down/status.ready=true` 和定高模式 |
| Hover 执行 | SITL 已实际 takeoff -> hover -> land/disarm | `flight_claim=not_evaluated` | 还没有 arm、takeoff、hover、landing |
| 安全与审计 | 仿真 artifact 只作参考 | preflight artifact 可复查串口/依赖 | 还缺 operator safety、flight rosbag、real landing summary |

## 统一真机起飞前开发流程

所有真机任务都必须走同一个 wrapper：

```bash
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real \
uv run --project orchestration python orchestration/main.py run hover --dry-run
```

完整开发 gate 顺序：

```text
real preflight doctor
  -> real prepare / bringup
  -> real task doctor
  -> dry-run summary review
  -> operator safety confirmation
  -> real task run arm/takeoff/hover/landing
  -> flight rosbag + landing summary review
```

Stage 1 simulation artifact 只能作为开发参考和回归诊断，不能作为真机 wrapper
的必需 blocker，也不能替代任何真实传感器、真实 FCU 或真实安全确认。

任何一层 blocked，都不能跳到下一层。

## Preflight 通过代表什么

`real_flight_preflight_doctor_todo.md` 的职责是非执行性检查：

- runtime 是 `process + real`。
- FCU 串口固定为 `/dev/ttyUSB1`，可打开并能看到真实 autopilot HEARTBEAT。
- required command / ROS package / Python module 存在。
- 所选 `fcu_bridge_mode` 的依赖存在。
- summary 标记 `preflight_claim=evaluated`。
- summary 标记 `flight_claim=not_evaluated`。
- summary 标记 `landing_claim=not_evaluated`。

preflight 明确不做：

- 不启动 `mavlink-router`。
- 不启动 FCU bridge。
- 不启动 lidar driver。
- 不启动 SLAM。
- 不启动 companion。
- 不 arm。
- 不 takeoff。
- 不 land。
- 不发布 movement setpoint。

因此 preflight 通过只允许进入 real prepare，不能作为真机 hover 放行依据。

## Prepare / Task Doctor 必须证明什么

`real_prepare_and_task_doctor_todo.md` 的职责是把真实辅助链路启动起来，并在 companion
或飞行执行前检查 readiness。

### FCU bridge

当前默认模式是：

```toml
[real_prepare]
fcu_bridge_mode = "navlab_mavlink"
```

该模式要求：

- `mavlink-router` 独占 `/dev/ttyUSB1`。
- NavLab MAVLink bridge 连接 mavlink-router endpoint。
- 不要求 MAVROS。
- 不要求 `/ap/v1/*` DDS topics。
- 必须有 `/navlab/mavlink/status`。
- 必须有 `/navlab/fcu/local_position_pose`。
- 必须有 `/mavlink_external_nav/status`。

### 2D lidar / SLAM / yaw

雷达端口固定为 `/dev/ttyUSB0`。起飞前必须证明：

- `/scan` 来自真实 lidar，不是 `/scan_ideal`。
- `/imu/data` 来自真实 FCU MAVLink IMU evidence。
- `/imu` 是归一化后的 SLAM IMU topic。
- Cartographer 真正运行，不使用 placeholder odom。
- `/slam/odom` 存在、类型正确、数据新鲜。
- `/navlab/slam/status.ready=true`。
- `/external_nav/status.ready=true`。
- `/external_nav/status.odom.input_topic=/slam/odom`。
- `external_nav_yaw_ready` 或等价 ready field 被 task doctor 接受。

这层只证明水平 SLAM / yaw，不证明高度 readiness。

### Height / rangefinder / 定高模式

真机 hover 不能只靠 `/scan` 和 yaw。起飞前必须证明真实下视高度来源：

- FCU MAVLink `DISTANCE_SENSOR` 是首选高度 evidence。
- 下视 orientation 必须是 `25` / `MAV_SENSOR_ROTATION_PITCH_270`。
- `current_distance_m > 0`。
- `current_distance_m >= min_distance_m`。
- `current_distance_m <= max_distance_m`。
- `/rangefinder/down/range` 有真实 `sensor_msgs/msg/Range` 样本。
- `/rangefinder/down/status.ready=true`。
- status source 必须是 `real_fcu_distance_sensor`。
- `altitude_hold_mode` 必须是受支持模式，例如 `fcu_rangefinder_guided`。
- 当前 FCU mode 必须属于允许初始模式，例如 `STABILIZE`、`ALT_HOLD`、`GUIDED`。

如果 rangefinder 未 ready，task doctor 必须 blocked 为：

- `rangefinder_down_no_data`
- `rangefinder_down_not_ready`
- `rangefinder_down_orientation_invalid`
- `rangefinder_down_distance_invalid`
- `rangefinder_down_source_forbidden`
- `altitude_hold_mode_not_ready`

## 当前已知开发状态

截至 2026-06-10：

- real preflight 已通过：
  `artifacts/ros/navlab_real_preflight_doctor/20260610_080422/summary.json`
- RTD.5A real SLAM / yaw gate 已通过。
- RTD.5B real height / rangefinder 软件 gate 已实现。
- 之前桌面状态下 dry-run 被正确阻断：
  `artifacts/ros/navlab_real_prepare/20260610_081003/summary.json`，
  `current_distance_m=0.0`、`min_distance_m=0.1`，blocker 为
  `rangefinder_down_distance_invalid`。
- 举高到有效测距区间后，最新 dry-run 已通过 RTD.5B：
  - prepare summary: `artifacts/ros/navlab_real_prepare/20260610_082646/summary.json`
  - task doctor summary:
    `artifacts/ros/navlab_real_task_doctor/20260610_082733/hover/summary.json`
  - `/rangefinder/down/status.ready=true`
  - `source=real_fcu_distance_sensor`
  - `current_distance_m=0.14`
  - `min_distance_m=0.1`
  - `max_distance_m=12.0`
  - `orientation=25`
  - `real_height_rangefinder_contract.ok=true`
  - `altitude_hold.ok=true`

这说明 RTD.5B 的 height / rangefinder / altitude-hold dry-run gate 已经通过；
仍然不等于已经可以真实起飞，后续还要补 operator safety、companion/task run 边界、
real flight rosbag 和 landing summary。

## 起飞前开发确认 Checklist

### A. 入口边界

- [ ] 使用 `NAVLAB_RUNTIME_BACKEND=process`。
- [ ] 使用 `NAVLAB_RUNTIME_MODE=real`。
- [ ] FCU 串口是 `/dev/ttyUSB1`。
- [ ] 2D lidar 串口是 `/dev/ttyUSB0`。
- [ ] `just navlab-doctor` 或 wrapper 内 preflight 通过。
- [ ] preflight summary 中 `flight_claim=not_evaluated`。
- [ ] preflight summary 中 `landing_claim=not_evaluated`。

### B. Real prepare

- [ ] `mavlink-router` 已启动并可从真实 serial 追溯到 `/dev/ttyUSB1`。
- [ ] `navlab_mavlink_bridge` 已启动。
- [ ] `lidar` 已启动并发布真实 `/scan`。
- [ ] `slam` 已启动并发布 `/slam/odom` 和 `/navlab/slam/status`。
- [ ] `rangefinder_bridge` 已启动并发布 `/rangefinder/down/range` 和 `/rangefinder/down/status`。
- [ ] prepare summary 中没有 `/scan_ideal`、`/sim/x2/status`、Gazebo、SITL 或 fake odom 作为 real evidence。

### C. Task doctor

- [ ] `real_slam_yaw_contract.ok=true`。
- [ ] `/scan` 有真实样本。
- [ ] `/imu/data` 有真实样本。
- [ ] `/imu` 有真实样本。
- [ ] `/slam/odom` fresh。
- [ ] `/navlab/slam/status.ready=true`。
- [ ] `/external_nav/status.ready=true`。
- [ ] `real_height_rangefinder_contract.ok=true`。
- [ ] `/rangefinder/down/range` 有真实样本。
- [ ] `/rangefinder/down/status.ready=true`。
- [ ] `current_distance_m` 在 `[min_distance_m, max_distance_m]` 内。
- [ ] `orientation=25`。
- [ ] `altitude_hold.ok=true`。
- [ ] `task_doctor.ok=true`。
- [ ] task doctor 通过时仍未启动 companion，未 arm，未 takeoff。

### D. Operator safety

Stage 1 simulation artifact 不作为真机起飞 gate；这一层只检查真实操作安全。

- [ ] manual takeover 已确认，并在真实非 dry-run 命令中传
  `--confirm-manual-takeover`。
- [ ] kill switch 已确认，并在真实非 dry-run 命令中传 `--confirm-kill-switch`。
- [ ] 安全场地、保护措施和人员站位已确认。
- [ ] 电池、电机、桨叶、固定件和安全距离已确认。
- [ ] 真实非 dry-run 命令中传 `--confirm-safe-area`。

### E. 真机执行前最终条件

只有同时满足以下条件，才允许进入真实 arm/takeoff/hover：

```text
preflight.ok=true
prepare.ok=true
task_doctor.ok=true
real_slam_yaw_contract.ok=true
real_height_rangefinder_contract.ok=true
altitude_hold.ok=true
operator_safety_confirmed=true
```

否则必须停在 dry-run / doctor 阶段。

真实非 dry-run 执行前的安全确认方式固定为 wrapper 参数：

```bash
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real \
uv run --project orchestration python orchestration/main.py run hover \
  --confirm-manual-takeover \
  --confirm-kill-switch \
  --confirm-safe-area
```

任一 flag 缺失都会在 arm/takeoff 前 blocked。`--dry-run` 不要求这些 flag，因为
dry-run 不会启动 companion、arm 或 takeoff。

## 推荐下一步

1. 把飞机举高到 rangefinder 有效距离区间。
2. 重跑：

```bash
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real \
uv run --project orchestration python orchestration/main.py run hover --dry-run
```

3. 确认 summary 同时满足：
   - `prepare.ok=true`
   - `task_doctor.ok=true`
   - `real_slam_yaw_contract.ok=true`
   - `real_height_rangefinder_contract.ok=true`
   - `altitude_hold.ok=true`
4. dry-run 通过后，再补 operator safety 和 real flight rosbag / landing summary gate。

## 无桨 Motor Debug

如果当前没有挂桨叶，只想确认电机链路，可以使用 `motor-debug`，不要用 `hover`。
这个 task 不起飞、不做 landing 验收，只做低油门短时电机测试并在结束后发送
disarm 关闭电机。

先 dry-run 看计划，不会转电机：

```bash
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real \
uv run --project orchestration python orchestration/main.py run motor-debug --dry-run
```

确认无桨、可人工接管、kill switch 和场地安全后，才允许真实转电机：

```bash
NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real \
uv run --project orchestration python orchestration/main.py run motor-debug \
  --confirm-no-props \
  --confirm-manual-takeover \
  --confirm-kill-switch \
  --confirm-safe-area
```

可选调小参数，例如：

```bash
--motor-percent 5 --motor-sec 1.5 --motor-count 4
```

`motor-debug` 只证明电机输出链路；不能证明 hover、height hold、SLAM yaw 或
landing readiness。

## 禁止绕过

- 禁止用 preflight 通过直接解释为可以起飞。
- 禁止用 `/scan` 或 SLAM yaw ready 替代 height ready。
- 禁止用 `/rangefinder/down/scan_ideal`、Gazebo、SITL、fake height 作为 real evidence。
- 禁止在 prepare/task doctor blocked 时启动 companion 或进入 arm/takeoff。
- 禁止在没有 operator safety confirmation 时执行真实飞行。
