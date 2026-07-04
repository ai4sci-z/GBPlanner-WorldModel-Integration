# P14 Benewake Rangefinder SITL Fidelity TODO

目标：让 SITL rangefinder 边界匹配真实机器，而不是把真实参数降级成 Gazebo/MAVLink 专用参数。

真实机器边界：

```text
Benewake TFmini -> UART -> FCU
```

SITL 目标边界：

```text
Gazebo range sensor -> Benewake serial emulator -> SITL serial port -> FCU
```

硬规则：

- `docker/profiles/navlab-sitl-external-nav.parm` 以真实机器为准。
- `RNGFND1_TYPE=20` 表示 Benewake TFmini serial backend，不允许为了让 SITL 通过而改成 `10`。
- `SERIAL7_PROTOCOL=9` 表示 FCU 从 Serial7 读取 Rangefinder，和 `docs/debug.param` / `docs/ori.param` 对齐。
- Gazebo 可以生成传感器观测，但不能作为 FCU/SLAM/ExternalNav 的 truth fallback。
- 如果 Benewake serial 没接通，任务必须 fail closed，并在 summary 中记录 blocker。

## Phase 0: Contract And Documentation

- [x] 记录硬件一致性原则。
- [x] 记录为什么 `RNGFND1_TYPE=10` 只能是旧临时桥接，不是最终方案。
- [x] 在 hover/exploration/scan-robustness 的验收文档中引用本原则。

## Phase 1: Profile And Artifact Consistency

- [x] `navlab-sitl-external-nav.parm` 显式携带 `SERIAL7_PROTOCOL=9`。
- [x] Python 参数测试断言 `RNGFND1_TYPE=20` 和 `SERIAL7_PROTOCOL=9`。
- [x] Go runtime artifact fixture 与真实 profile 一致。
- [x] 生成的 `gazebo-iris-rangefinder.parm` 不保留官方 Gazebo base 中的旧 `RNGFND1_TYPE=1` / `SIM_SONAR_SCALE` 混淆项。

## Phase 2: SITL Serial Transport

- [x] 确认 ArduPilot ROS2 `ardupilot_sitl.launch.py` 支持 `serial0` 到 `serial9` launch 参数，并会转成 `--serialN`。
- [x] 确认当前 Go `official_baseline` 服务没有消费 `[sitl].extra_args`；不能假设 `config.toml` 中的 `extra_args` 已经生效。
- [x] 确认顶层 `iris_maze.launch.py` 是否声明并透传 `serial7:=...`。Go sim 必须显式追加 Serial7 launch arg，不能依赖未生效的 `[sitl].extra_args`。
- [x] 记录 direct SITL backend 失败证据：2026-06-16 hover live 中 `serial7:=sim:benewake_tfmini` 让 official baseline 内的 ArduPilot `arducopter` 触发 floating point exception 并退出 `134`，该路径不得作为 NavLab 默认实现。
- [x] 将 official_baseline 启动配置改为 NavLab Benewake PTY emulator：`python3 -m navlab.sim.gazebo_sensor.benewake_tfmini_serial` 先创建 `/tmp/navlab_benewake_tfmini`，ArduPilot 用 `serial7:=uart:/tmp/navlab_benewake_tfmini:115200` 打开。
- [x] `navlab/config.toml` 和 Go 生成的 sensor runtime config 只保留 `virtual_serial_link` / `serial_baud`，不再写旧 `endpoint`、`source_system`、`source_component`、`sensor_id`、`mavlink_orientation`、`covariance_cm` MAVLink sender 字段。
- [x] 禁止使用 MAVLink `DISTANCE_SENSOR` 注入作为 hover/exploration/scan-robustness 的通过路径。

## Phase 3: Runtime Evidence Gates

- [x] summary 增加 `rangefinder_simulation_fidelity`。
- [x] 允许值只保留：
  - `benewake_serial_emulated`
  - `blocked_missing_benewake_serial`
- [x] hover mission 起飞前检查 FCU rangefinder 新鲜度，不用历史 count 顶替。当前 acceptance 要求 Benewake serial fidelity，旧 MAVLink sender status 会 block。
- [x] ExternalNav status 记录 height source、age、fresh、z/vz merge 状态。
- [x] hover 目标高度 gate 优先使用 FCU/EKF local position，不用下视 rangefinder 的近地读数替代目标高度。rangefinder 只作为 FCU 外设、height source 和 landing/touchdown 证据。
- [x] `MAV_CMD_NAV_TAKEOFF` ACK 缺失不再单独否定 hover；只有在缺少 `airborne_seen`、local position、高度误差等真实起飞证据时才 block。ACK 缺失仍保留在 summary 里作为诊断字段。

## Phase 4: Live Acceptance

- [x] 跑 hover live，要求真实起飞、hold、landing，且 rangefinder fidelity 为 `benewake_serial_emulated`。
  - 2026-06-16 `artifacts/sim/hover/20260616T100455Z/summary.json`: `status=TASK_STATUS_OK`。
  - hover mission: `ok=true`, `airborne_seen=true`, `hover_hold_duration_sec=17.999978`, `landing_ok=true`, `touchdown_confirmed=true`, `disarmed=true`, `motors_safe=true`。
  - ExternalNav: `ready=true`, `state=healthy`, `xy_yaw_source=/slam/odom`, `z_source=rangefinder_down_relative`, `vz_source=rangefinder_down_relative`。
  - MAVLink ExternalNav: `state=sending`, `sent_count=1004`, `fcu_local_position_ready=true`, `local_position_age_ms=0.622`。
  - SLAM: `ready=true`, `rejected_count=0`, `rejection_ratio=0`。
- [ ] 跑 exploration live，要求任务完成和 landing，不允许 Gazebo truth fallback。
- [ ] 跑 scan-robustness live，要求扰动 profile 下 scan/SLAM/FCU 链路仍满足 gate。
- [ ] 只上传 lite MCAP，且 lite topic 必须包含既定最小可视化 topic。

## Phase 5: Retire Temporary Paths

- [x] 删除或 diagnostic-only 标记 MAVLink rangefinder bridge。
- [x] CI 阻止 `RNGFND1_TYPE=10` 出现在 hardware-faithful SITL profile 和生成 artifact 中。
- [x] 文档标明 Altair-Silent 的 `RNGFND1_TYPE=1` 属于简化仿真，不作为 NavLab FCU 外设边界基线。
- [x] `sim:benewake_tfmini` 只允许作为审计记录/反例出现在文档中；运行路径必须使用 NavLab PTY emulator + `uart:`。
