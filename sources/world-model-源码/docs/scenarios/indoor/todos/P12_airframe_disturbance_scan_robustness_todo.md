# P12 机体扰动下的 2D lidar / SLAM 水平复原鲁棒性 TODO

## 目标

P12 要在 P10/P11 已完成 scan integrity 和 bounded 2D stabilization 后，补上真机前最重要的仿真 gap：motor thrust bias、ESC lag、thrust noise 和 IMU vibration/noise。P12 不做探索策略优化；它验证“飞机本体扰动导致 2D lidar 扫描平面倾斜时，P11 的水平复原和 P10 的安全 gate 是否仍然可靠”。

对应设计文档：

- `docs/scenarios/indoor/navlab_p12_airframe_disturbance_scan_robustness_design.md`

## P12.0 文档和边界

- [x] 新增 P12 设计文档。
- [x] 新增 P12 TODO 文档。
- [x] 文档明确 P12 是 airframe disturbance / scan robustness layer，不是 exploration strategy layer。
- [x] 文档明确 P12 解决 motor bias / ESC lag / thrust multiplier / vibration 仿真和验收。
- [x] 文档明确 P12 复用 P10/P11 scan integrity / stabilization，不重写 scan 算法。
- [x] 文档明确 P12 不引入 3D lidar / PointCloud。
- [x] 文档明确 P12 不使用 Gazebo truth pose/attitude 作为补偿、SLAM 或控制输入。
- [x] 文档明确 active frontier exploration strategy 后移到 P13 或之后。

验收：

- [x] P12 文档没有把 frontier/exploration strategy 作为当前目标。
- [x] P12 文档没有把 official maze overlay 作为算法输入。
- [x] P12 文档明确 P9 representative replay 是主运动 profile。
- [x] P12 文档明确 hard disturbance 可以 fail，但必须 fail 得清楚。

## P12.1 配置和 no-hardcode contract

- [x] 增加 `[airframe_disturbance]` 配置段。
- [x] 增加 `[airframe_disturbance_gate]` 配置段。
- [x] 配置 `enabled`。
- [x] 配置 `profile`。
- [x] 配置 `injection_layer`。
- [x] 配置 `seed`。
- [x] 配置 `motor_count`。
- [x] 配置 `thrust_multipliers`。
- [x] 配置 `max_abs_thrust_multiplier_delta`。
- [x] 配置 `esc_lag_ms`。
- [x] 配置 `esc_lag_model`。
- [x] 配置 `max_esc_lag_ms`。
- [x] 配置 `thrust_noise_std`。
- [x] 配置 `thrust_noise_correlation_ms`。
- [x] 配置 `motor_jitter_hz`。
- [x] 配置 `imu_vibration_enabled`。
- [x] 配置 `imu_input_topic`。
- [x] 配置 `imu_output_topic`。
- [x] 配置 `imu_gyro_noise_std_dps`。
- [x] 配置 `imu_accel_noise_std_mps2`。
- [x] 配置 `imu_vibration_freq_hz`。
- [x] 配置 `imu_vibration_roll_pitch_amp_deg`。
- [x] 配置 `profile_set`。
- [x] 配置 `required_profiles`。
- [x] 配置 `allow_hard_profile_fail`。
- [x] 配置 roll/pitch/RMS/attitude-rate 门槛。
- [x] 配置 scan drop / compensation / floor-hit / stabilized-rate 门槛。
- [x] 配置 SLAM/ExternalNav/FCU/map-artifact 门槛。
- [x] 配置 FCU mode gate：`fcu_status_topic`。
- [x] 配置 FCU mode gate：`fcu_status_mode_field`。
- [x] 配置 FCU mode gate：`fcu_mode_window_topic`。
- [x] 配置 FCU mode gate：`required_fcu_mode_name` / `required_fcu_mode_number`。
- [x] 所有 P12 profile 和阈值都从 config 读取，不写死在代码里。

验收：

- [x] 缺少 `[airframe_disturbance]` 时 doctor fail。
- [x] profile 未显式配置时 doctor fail。
- [x] motor_count 与 thrust/lag 数组长度不一致时 fail。
- [x] thrust multiplier 超范围时 fail。
- [x] ESC lag 超范围时 fail。
- [x] required profile 不在 profile_set 中时 fail。
- [x] invalid config 不 fallback 到 ideal。
- [x] config summary 写入所有扰动参数和阈值。

## P12.2 Motor thrust multiplier / bias 注入

- [x] 调研当前 Gazebo/ArduPilot motor model 是否支持 per-motor thrust multiplier。
- [x] 优先在 Gazebo/ArduPilot motor model 层实现 per-motor thrust multiplier。
- [ ] 如果官方插件短期不支持，增加 NavLab disturbance shim，并明确 `disturbance_injection_layer=shim`。
- [x] 支持 ideal profile：`[1.0, 1.0, 1.0, 1.0]`。
- [x] 支持 realistic profile。
- [x] realistic profile 支持 motor bias、ESC lag、thrust noise、IMU vibration/noise 组合。
- [x] 支持 hard_bias profile。
- [x] 发布 `/navlab/airframe_disturbance/status`。
- [x] 发布 `/navlab/airframe_disturbance/events`。
- [x] summary 记录每个 motor 的 thrust multiplier。
- [x] summary 记录实际应用的 injection layer。

验收：

- [x] ideal profile 不改变当前 P11 baseline 行为。
- [x] realistic profile 能造成可观测 roll/pitch 差异。
- [x] realistic profile 能在 P9 representative replay 中运行。
- [x] hard_bias profile 能触发 warn/drop/fail 或明确 blocker。
- [x] profile 未应用时 blocker 包含 `airframe_disturbance_profile_not_applied`。

## P12.3 ESC lag / response delay 注入

- [x] 支持 per-motor ESC lag 配置。
- [x] 支持 first-order response lag model。
- [x] 官方-baseline 插件补丁支持 `<escTimeConstantMs>`。
- [x] 记录 ArduPilot Gazebo patch 基线 commit：`cc0290d964dfa373531963a8fc39093a0836af0a`。
- [x] 文档记录 patch 失效时 Plan B：固定 ref 或显式 shim/blocker，不能静默 proxy fallback。
- [x] P12 SDF overlay 不再用 `p_gain/frequencyCutoff` proxy 冒充 ESC lag。
- [x] 支持 asymmetric lag profile。
- [x] summary 记录 `esc_lag_ms_by_motor`。
- [ ] summary 记录 `estimated_attitude_response_lag_ms`。
- [ ] summary 记录 `attitude_overshoot_count`。
- [x] 明确区分 ESC lag 和 scan/attitude timestamp offset。

验收：

- [x] esc_lag profile 可以运行 P9 representative replay。
- [x] `scan_attitude_time_offset_ms` 仍由 P10/P11 单独记录。
- [x] `esc_lag_ms_by_motor` 不被误写成 topic timestamp offset。
- [x] ESC lag 过大时 blocker 包含 `airframe_esc_lag_too_high` 或 profile fail 原因。

## P12.4 Thrust noise / motor jitter 注入

- [x] 支持 thrust noise std 配置。
- [x] 支持 thrust noise correlation window。
- [x] 支持 motor jitter frequency 配置。
- [x] summary 记录 thrust noise profile。
- [x] summary 记录扰动 seed。
- [x] 同 seed 运行可复现。
- [x] 不同 seed 可生成不同 noise realization。

验收：

- [x] thrust noise profile 不影响 no-truth 约束。
- [ ] 同 seed 的主要扰动参数可复现。
- [ ] noise 过大导致 scan/map 风险时 gate 明确 fail。

## P12.5 IMU vibration / noise profile

- [x] 支持 IMU gyro noise std 配置。
- [x] 支持 IMU accel noise std 配置。
- [x] 支持 vibration frequency 配置。
- [x] 支持 roll/pitch vibration amplitude 配置。
- [x] summary 记录 `imu_vibration_claim`。
- [ ] summary 记录 `attitude_noise_rms_deg`。
- [ ] summary 记录 `false_drop_ratio`。
- [ ] summary 记录 `compensation_jitter_score`。
- [x] 如果当前仿真无法注入 IMU vibration，summary 明确 `imu_vibration_claim=not_available` 并让 required vibration profile blocked。

验收：

- [x] vibration profile 不能用 ideal IMU run 冒充。
- [x] 文档说明 `attitude_source=/imu` 时 vibration 注入有效，`/ap/v1/pose/filtered` 时不等价影响 FCU EKF。
- [x] vibration profile 下 P10/P11 不应大量误 drop，或必须明确 fail。
- [ ] compensation jitter 超阈值时 blocker 包含 `compensation_jitter_too_high`。

## P12.6 P11 scan stabilization 集成

- [x] P12 runtime 复用 P11 `/scan` 输出。
- [x] SLAM 只消费 P11 stabilized `/scan`。
- [x] raw scan 只进入诊断、MCAP 和 summary。
- [x] P12 summary 记录 `scan_contract=p11_stabilized_scan`。
- [x] P12 summary 记录 P10 scan integrity 指标。
- [x] P12 summary 记录 P11 scan stabilization 指标。
- [x] P12 summary 记录 `horizontal_recovery_claim=evaluated`。

验收：

- [x] `/scan` publisher unique。
- [x] 没有节点绕过 P11 直接把 raw scan 送进 SLAM。
- [x] hard tilt 仍 drop。
- [x] floor-hit risk 不被投影成墙。
- [x] scan availability 和 drop ratio 写入 profile summary。

## P12.7 Ideal baseline

- [x] 运行 P9 representative replay + ideal disturbance profile。
- [x] 记录 ideal scan/SLAM/ExternalNav/FCU health。
- [x] 记录 ideal map artifact score。
- [x] ideal baseline summary 写入 P12 summary。
- [x] ideal baseline fail 时停止 required disturbed success 判定。

验收：

- [x] ideal baseline `ok=true`。
- [x] ideal baseline `uses_gazebo_truth_as_input=false`。
- [x] ideal baseline `owner.unique=true`。
- [x] ideal baseline `set_pose_count=0`。

## P12.8 Disturbed profile acceptance

- [x] 运行 `realistic` profile。
- [x] realistic profile 启用 ESC lag component。
- [x] realistic profile 启用 vibration component。
- [x] realistic profile 记录 flight attitude metrics。
- [x] realistic profile 记录 scan drop/compensate/floor-hit 指标。
- [x] 每个 profile 记录 SLAM/ExternalNav/FCU health。
- [x] 每个 profile 记录 optional map artifact score；P12 首版 hard gate 不依赖该 soft score。
- [x] 每个 profile 记录 false wall risk。
- [x] profile-sweep summary 记录 disturbed-vs-ideal aggregate comparison。

验收：

- [x] required profiles 全部运行。
- [x] required profiles 没有静默 fallback 到 ideal。
- [x] required profiles 的 scan availability 达标。
- [x] required profiles 的 SLAM health 不退化或退化原因明确。
- [x] required profiles 的 false-wall/SLAM health 不超阈值；map artifact score 降为 optional/future。
- [x] required profiles 的 ExternalNav/FCU health 不退化。

## P12.9 Fault profile 和负例

- [x] 运行 `hard_bias` profile。
- [x] 运行 `invalid_config` profile。
- [x] hard_bias 可 fail，但必须产生明确 blocker。
- [x] hard_bias 不允许把危险 scan 静默送进 SLAM。
- [x] hard_bias/required disturbed profiles 检查 `set_pose_count=0`，不能用 truth reset 兜底。
- [x] required disturbed profiles 期间显式检查 FCU mode stays GUIDED，不能意外 RTL/LAND/failsafe 后仍算 pass。
- [x] FCU mode gate 使用 `/navlab/exploration/status` 首尾样本作为 disturbance window，排除 pre-replay bootstrap 阶段。
- [x] FCU mode gate 对 `/ap/v1/status` 缺失、`mode_number` schema 无效、window 内非 GUIDED 给出明确 blocker。
- [x] invalid_config 必须 blocked。
- [x] invalid_config 不允许 fallback 到 ideal。

验收：

- [x] hard tilt 被 P10/P11 拒绝。
- [x] floor-hit risk 被拒绝或 clip，不生成假墙。
- [x] invalid motor_count/array length fail。
- [x] invalid thrust multiplier fail。
- [x] invalid ESC lag fail。
- [x] missing required profile fail。

## P12.10 Summary、MCAP 和 Foxglove-lite

- [x] summary 顶层记录 `airframe_disturbance_claim=evaluated`。
- [x] summary 顶层记录 `scan_contract=p11_stabilized_scan`。
- [x] summary 顶层记录 `motion_profile=p9_representative_replay`。
- [x] summary 顶层记录 `uses_gazebo_truth_as_input=false`。
- [x] summary 顶层记录 `uses_official_maze_as_input=false`。
- [x] summary 记录 `disturbance_config`。
- [x] summary 记录 per-profile results。
- [x] summary 记录 disturbed-vs-ideal comparison。
- [x] 文档明确 `map_artifact_score` 首版降级为 optional/future，hard gate 使用 scan_drop/false_wall/slam_health。
- [x] 新增 P12 raw rosbag topic profile。
- [x] raw MCAP 包含 P11/P12 status/events、scan、map、SLAM、FCU、IMU raw/stabilized、rangefinder、TF。
- [x] raw MCAP 必须包含 `/ap/v1/status` 和 `/navlab/exploration/status`，用于 FCU GUIDED mode disturbance-window gate。
- [x] Foxglove-lite artifact 包含 official maze overlay、SLAM map、trajectory、stabilized scan、P11/P12 status。

验收：

- [x] summary parser 测试覆盖 P12 schema。
- [x] Lite MCAP 生成不依赖 hardcoded topic list。
- [x] Foxglove overlay 仅作为 review-only artifact。

## P12.11 测试

- [x] 单元测试覆盖 airframe disturbance config parser。
- [x] 单元测试覆盖 invalid motor_count / array length。
- [x] 单元测试覆盖 thrust multiplier range validation。
- [x] 单元测试覆盖 ESC lag range validation。
- [x] 单元测试覆盖 required profile validation。
- [x] 单元测试覆盖 summary schema parser。
- [x] 单元测试覆盖 disturbed-vs-ideal comparison。
- [x] 单元测试覆盖 hard profile fail semantics。
- [x] 单元测试覆盖 FCU GUIDED mode gate 的 pass / non-GUIDED fail / schema invalid fail。
- [x] 集成测试覆盖 ideal profile doctor。
- [x] 集成测试覆盖 realistic profile doctor。
- [x] 集成测试覆盖 invalid_config blocker。
- [x] docs 测试确保 P12 不再定义为 active frontier exploration strategy。

验收：

- [x] P12 相关单元测试通过。
- [x] P12 doctor 本地跑通。
- [x] P12 acceptance 本地跑通。
- [x] P12 fault profile 本地跑通。

## P12.12 Full live replay / Foxglove 复核

- [x] `realistic` profile 跑 full live P9 replay。
- [x] realistic summary 记录 ESC lag component。
- [x] realistic summary 记录 vibration component。
- [x] live replay summary 记录 `/navlab/airframe_disturbance/status/events` 消息。
- [x] live replay raw MCAP 记录 `/navlab/imu/raw` 和 disturbed `/imu`。
- [x] 对通过的 live artifact 生成 Foxglove-lite MCAP。
- [x] Foxglove-lite summary `ok=true`，overlay 仅作为 review-only。

验收：

- [x] `just navlab-airframe-disturbance-gate-acceptance 240 --live-profiles realistic` 通过。
- [x] realistic live profile 的 P11 nested summary `ok=true`。
- [x] realistic live profile 的 rosbag profile `ok=true`。
- [x] P12 parent summary `live_replay_claim=evaluated`。

## P12.13 执行顺序

建议顺序：

1. P12.1 配置和 no-hardcode contract。
2. P12.2 motor thrust multiplier / bias 注入。
3. P12.3 ESC lag 注入。
4. P12.4 thrust noise / motor jitter 注入。
5. P12.5 IMU vibration / noise profile。
6. P12.6 P11 scan stabilization 集成。
7. P12.7 ideal baseline。
8. P12.8 disturbed profile acceptance。
9. P12.9 fault profile 和负例。
10. P12.10 summary / MCAP / Foxglove-lite。
11. P12.11 测试。

## P12 完成标准

P12 全部完成必须满足：

- [x] P12 主验收使用 P9 representative replay motion profile。
- [x] P12 主验收使用 P11 stabilized `/scan` contract。
- [x] motor thrust multiplier / bias profile 已实现并验收。
- [x] ESC lag / response delay profile 已实现并验收。
- [x] thrust noise / motor jitter profile 已实现并验收。
- [x] IMU vibration / noise profile 已实现并验收，或 required profile 明确 blocked 不假通过。
- [x] ideal baseline ok。
- [x] ideal / realistic required profiles 全部 evaluated。
- [x] hard_bias / invalid_config fault profiles 全部 evaluated。
- [x] 所有扰动参数、阈值和 profile 列表都来自配置。
- [x] `/scan` publisher unique，SLAM 不消费 raw scan。
- [x] `owner.unique=true`。
- [x] `set_pose_count=0`。
- [x] required live disturbed profiles 的 `fcu_mode_gate.ok=true`，且 `non_guided_count=0`。
- [x] `uses_gazebo_truth_as_input=false`。
- [x] `uses_official_maze_as_input=false`。
- [x] P10/P11 hard tilt / floor-hit safety 没被放松。
- [x] summary 明确 `airframe_disturbance_claim=evaluated`。
- [x] summary 明确 `horizontal_recovery_claim=evaluated`。
- [x] summary 无 blockers。
- [x] raw MCAP 和 lite MCAP 可复核扰动、scan、SLAM 和 map 风险。

## 执行记录

### 2026-06-08 P12 文档重定向

- 范围：把 P12 从错误的 active frontier exploration strategy 改回 airframe disturbance / scan robustness gate。
- 结果：P12 被定义为 motor bias / ESC lag / thrust multiplier / vibration 仿真和 P11 水平复原鲁棒性验收；探索策略优化后移到 P13 或之后。


### 2026-06-08 P12 profile/model-level implementation

- 范围：新增 P12 airframe disturbance config、profile library、ArduPilotPlugin control multiplier overlay、ESC lag 初版 proxy、profile-sweep summary、doctor/acceptance task、just 命令和单元测试。
- 验证：`just navlab-airframe-disturbance-gate-doctor` 通过；`just navlab-airframe-disturbance-gate-acceptance 240` 通过，summary 位于 `artifacts/ros/navlab_companion_sitl_gazebo/20260608_154034/summary.json`。
- 边界：这是历史初版记录，已被后续 `escTimeConstantMs` first-order patch 和 live replay artifacts 取代；当前 P12 不再用 `p_gain/frequencyCutoff` proxy 冒充 ESC lag。


### 2026-06-08 P12 live disturbed replay 验收通过

- 命令：`just navlab-airframe-disturbance-gate-acceptance 240 --live`。
- 结果：P12 summary `ok=true`、`blockers=[]`，artifact 位于 `artifacts/ros/navlab_companion_sitl_gazebo/20260608_154641/summary.json`。
- live replay：嵌套 P11 disturbed replay `ok=true`、`blockers=[]`，summary 位于 `artifacts/ros/navlab_companion_sitl_gazebo/20260608_154641/p12_live_disturbed_replay/summary.json`。
- 扰动确认：`disturbance_injection_layer=gazebo_motor_model`，四个 ArduPilotPlugin control multiplier 分别应用 `0.97/1.03/1.00/0.98`。该历史 artifact 的 ESC lag 仍是旧 proxy 路径，已由后续 first-order patch live artifact 取代。
- scan 结果：`passthrough_scan_count=605`，`compensated_scan_count=0`，`dropped_scan_count=0`，`max_observed_tilt_deg=2.877`，`false_wall_risk_ok=true`。补偿未触发原因是 `tilt_never_exceeded_passthrough_tilt_deg`，说明该 realistic live run 仍被 FCU 压在 passthrough 区。
- owner/truth：`owner.unique=true`，`competing_publishers=[]`，`set_pose_count=0`，`uses_gazebo_truth_as_input=false`，`uses_official_maze_as_input=false`。
- 边界：live 只跑了当前 realistic 配置 profile；ESC lag / vibration 作为 realistic components 已在 gate 中 evaluated。

### 2026-06-08 P12 FCU GUIDED mode gate follow-up

- 范围：新增 P12 live disturbed replay 的 FCU mode gate，使用配置化 `fcu_status_topic=/ap/v1/status`、`fcu_status_mode_field=mode`、`fcu_mode_window_topic=/navlab/exploration/status`、`required_fcu_mode_number=4`。
- 验证：`PYTHONPATH=orchestration uv run --project orchestration pytest orchestration/tests/test_airframe_disturbance_gate.py orchestration/tests/test_config.py -q` 通过；`just navlab-airframe-disturbance-gate-doctor` 通过；`just navlab-airframe-disturbance-gate-acceptance 240 --live-profiles realistic` 通过。
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260608_191029/summary.json`，P12 `ok=true`、`blockers=[]`。
- FCU mode gate：realistic profile 72/72 GUIDED，ESC lag / vibration components 的 `non_guided_count=0`、`schema_invalid_count=0`。

### 2026-06-08 P12 first-order ESC lag + ideal/realistic live closure

- 范围：复核 P12 ESC lag 实现与设计一致性，并补跑 `ideal` / `realistic` live replay。
- ESC lag 证据：当前 SDF overlay 写入 `<escTimeConstantMs>`，`model_overlay.airframe_disturbance.applied_controls[*].esc_lag_model=plugin_first_order`，`esc_lag_claim=first_order`；`artifacts/ros/navlab_companion_sitl_gazebo/20260608_195430/summary.json` 对应 replay SDF 中 `escTimeConstantMs` 出现 8 次，未出现 `frequencyCutoff` proxy。
- ideal artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260608_200320/summary.json`，P12 `ok=true`、`blockers=[]`；`ideal` live `passthrough=606`、`compensated=0`、`dropped=0`、`max_observed_tilt_deg=2.991`、FCU 71/71 GUIDED。
- realistic artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260608_195430/summary.json`，P12 `ok=true`、`blockers=[]`；historical artifact path 保留旧目录名，当前语义归并为 `realistic` live：`passthrough=550`、`compensated=40`、`dropped=20`、`max_observed_tilt_deg=5.793`、`false_wall_risk_ok=true`、FCU 73/73 GUIDED。
- Foxglove-lite：已为 `ideal` 和 `realistic` 的最新 live replay 生成 P12 lite MCAP，`foxglove_replay_summary.json` 均为 `ok=true`。

### 2026-06-16 P14 rangefinder 边界更新

- P12 后续 scan-robustness live acceptance 必须引用 `docs/scenarios/indoor/todos/P14_benewake_rangefinder_sitl_todo.md`。
- realistic 扰动下也不能回退到 Python/Gazebo sensor runtime 发送 MAVLink `DISTANCE_SENSOR`。
- FCU rangefinder 输入必须是 Benewake serial emulation；summary 必须记录 `rangefinder_simulation_fidelity=benewake_serial_emulated`，否则 blocked。
