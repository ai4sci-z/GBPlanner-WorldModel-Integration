# P12 机体扰动下的 2D lidar / SLAM 水平复原鲁棒性设计

## 1. 背景和目标

P10/P11 已经把机体固连 2D lidar 的 scan 输入契约做起来了：

```text
P10: raw/normalized scan -> attitude-aware integrity gate
     -> 小角度 passthrough，中等倾角 warn/drop，坏 scan 不静默进 SLAM

P11: P9 representative replay -> bounded 2D projection stabilization
     -> 中等安全倾角下尝试水平复原，hard tilt / floor-hit 仍拒绝
```

但是这还没有回答真机前最关键的问题：

```text
真实飞机不会四个电机完全一致
  -> motor thrust bias / prop mismatch / ESC response lag
  -> roll/pitch 持续偏置、动态超调、振动和 IMU 噪声
  -> 机体固连 2D lidar 扫描平面不再水平
  -> SLAM map 可能出现假墙、墙体漂移、scan availability 下降
```

P12 的目标不是探索更远，也不是换 3D lidar，而是在仿真里显式制造更真实的机体扰动来源，并验证 P10/P11 的 scan integrity / stabilization 能否在这些扰动下保持安全、可解释和不污染 SLAM。

P12 只回答：

> 在不使用 Gazebo truth 作为 SLAM/补偿输入、不增加 3D lidar、不引入第二个 FCU owner 的前提下，当仿真模型存在 motor thrust bias、ESC lag、motor noise 和 IMU vibration/noise 时，P11 的 2D scan 水平复原链路是否仍能让 SLAM 输入安全可用，且不会把地面/倾斜 beam 投影成假墙？

P12 通过后，操作者应该能判断：

- 当前 P11 stabilization 在多大 motor bias / ESC lag / vibration 范围内仍可用。
- 哪些扰动会导致 passthrough、compensate、drop、floor-hit reject 或 gate fail。
- SLAM map 在扰动 profile 下是否明显退化。
- 真机前还需要收紧阈值、减小机动速度，还是需要机械减振/云台/3D 方案。

## 2. 为什么 P12 必须先做机体扰动，而不是探索策略

P8/P9 已经证明 maze 中可以做最小探索和 overlay replay。P10/P11 已经证明在现有 sim 姿态下 scan 输入可以被验证和有界复原。

但当前 sim 太理想：

- 四个 motor / prop / ESC 默认几乎同步。
- 没有显式 thrust multiplier mismatch。
- 没有 ESC response lag / asymmetry。
- IMU 没有足够接近真机的振动噪声。
- P11 live replay 经常停留在 passthrough zone，补偿不一定真实触发。

如果现在直接做 active frontier / 更激进探索，策略越主动，越会把未验证的姿态扰动风险放大：一旦 scan 水平复原不稳，探索策略会基于错误 map 做错误决策。

所以 P12 必须先把“飞机本体扰动导致的 lidar 水平复原问题”补上。探索策略优化后移到 P13 或之后。

## 3. P12 范围

P12 包含：

- 在仿真/launch/config 中加入可参数化的 motor thrust multiplier / motor bias profile。
- 加入可参数化的 ESC lag / first-order motor response delay / asymmetric lag profile。
- 加入可参数化的 motor noise / thrust noise / IMU angular noise / vibration profile。
- 保持 P9 representative replay motion profile 作为主验收运动强度。
- 复用 P10/P11 scan integrity / bounded 2D stabilization，不绕过它们。
- 对比 baseline `ideal` profile 和 disturbed profiles。
- 记录 roll/pitch/yaw-rate/attitude-rate、scan stabilization、drop/compensate/floor-hit、SLAM health、map risk 和 FCU health。
- 增加扰动扫参：mild / nominal-realistic / hard / invalid config。
- 在 summary 中给出 `airframe_disturbance_claim=evaluated` 和每个 profile 的 pass/fail/blocker。

P12 不包含：

- 不做 active frontier exploration strategy。
- 不追求完整 maze 覆盖率。
- 不引入 3D lidar / PointCloud pipeline。
- 不使用 Gazebo truth pose/attitude 作为 scan 补偿或 SLAM 输入。
- 不把官方 maze SDF / wall plot / overlay 作为 planning、SLAM 或补偿输入。
- 不放松 P10/P11 hard tilt、floor-hit、no-truth、unique-owner 安全边界。
- 不要求真机飞行；P12 是上真机前的仿真鲁棒性 gate。

## 4. 关键设计决定

### 4.1 P12 验证扰动来源，不再只做 attitude bias 注入

P10 fault injection 可以直接给 attitude 加 bias，证明坏 scan 不会静默通过。这个测试仍然有价值，但不够真实。

P12 必须把扰动加到更靠近物理源头的位置：

```text
motor command
  -> thrust multiplier / response lag / noise
  -> vehicle dynamics roll/pitch/yaw-rate
  -> IMU / FCU attitude estimate
  -> P10/P11 scan integrity + stabilization
  -> SLAM /map and /slam/odom
```

当前实现采用 Gazebo / ArduPilot motor model 层扰动：

- 每个 motor 配置 `<multiplier>` thrust multiplier。
- 官方-baseline 构建时应用 `patches/ardupilot_gazebo_esc_lag.patch`，给 `ArduPilotPlugin` 增加 `<escTimeConstantMs>` first-order ESC response lag。
- 每个 motor 在 P12 SDF overlay 中写入独立 ESC time constant。
- IMU vibration/noise 由 NavLab sensor runtime 在 `/navlab/imu/raw -> /imu` 路径上注入，并发布 P12 status/events。
- 验证 FCU 是否能把这些扰动压住。

NavLab disturbance shim 只保留为未来备选；P12 当前不再用 `p_gain/frequencyCutoff` proxy 冒充 ESC lag。

P12 不接受只做 P10 attitude bias injection 然后宣称 motor bias 已验证。attitude bias 可以作为负例测试，但不能替代 motor/ESC 扰动 profile。

IMU vibration 注入点有明确局限：P12 runtime 注入在 `/navlab/imu/raw -> /imu`，因此只影响直接订阅 `/imu` 的 scan integrity/stabilization；如果后续 attitude source 改为 FCU EKF 输出 `/ap/v1/pose/filtered`，这条 vibration injection 不会经过 FCU EKF，也不会等价影响 EKF 姿态。

| attitude source | vibration injection 影响 | 解释 |
|---|---|---|
| `/imu` / `attitude_source_type=imu` | 直接影响 P10/P11 tilt 估计 | 当前 P12 live profile 使用该路径 |
| `/ap/v1/pose/filtered` / pose | 不直接影响 P10/P11 | FCU EKF 没消费 NavLab disturbed `/imu` |
| Gazebo truth / `/odometry` | 禁止 | no-truth contract 直接 fail |

因此 `imu_vibration_claim=evaluated` 的含义必须和 attitude source 一起解读；如果配置不是受影响路径，required vibration profile 应 blocked 或标记 `imu_vibration_profile_not_available`，不能用 `ideal` attitude path 冒充。

### 4.2 扰动 profile 必须参数化，不能 hardcode

推荐配置结构：

```toml
[airframe_disturbance]
enabled = true
profile = "realistic"
injection_layer = "gazebo_motor_model"
seed = 12012

motor_count = 4
thrust_multipliers = [0.97, 1.03, 1.00, 0.98]
max_abs_thrust_multiplier_delta = 0.06

esc_lag_ms = [20.0, 35.0, 25.0, 45.0]
esc_lag_model = "first_order"
max_esc_lag_ms = 60.0

thrust_noise_std = 0.015
thrust_noise_correlation_ms = 80.0
motor_jitter_hz = 35.0

imu_vibration_enabled = true
imu_input_topic = "/navlab/imu/raw"
imu_output_topic = "/imu"
imu_gyro_noise_std_dps = 0.8
imu_accel_noise_std_mps2 = 0.15
imu_vibration_freq_hz = 80.0
imu_vibration_roll_pitch_amp_deg = 0.4

[airframe_disturbance_gate]
profile_set = ["ideal", "realistic"]
required_profiles = ["ideal", "realistic"]
allow_hard_profile_fail = true
max_abs_roll_deg = 8.0
max_abs_pitch_deg = 8.0
max_rms_roll_deg = 3.0
max_rms_pitch_deg = 3.0
max_attitude_rate_dps = 120.0
max_scan_drop_ratio = 0.20
max_scan_compensated_ratio = 0.80
max_floor_hit_rejected_ratio = 0.05
min_stabilized_scan_rate_hz = 5.0
min_slam_odom_rate_hz = 10.0
max_map_artifact_score = 0.15
max_external_nav_dropout_ratio = 0.05
fcu_status_topic = "/ap/v1/status"
fcu_status_mode_field = "mode"
fcu_mode_window_topic = "/navlab/exploration/status"
required_fcu_mode_name = "GUIDED"
required_fcu_mode_number = 4
```

配置校验必须覆盖：

```text
enabled profile requires explicit injection_layer
motor_count == len(thrust_multipliers) == len(esc_lag_ms)
0 < thrust_multiplier <= configured max range
0 <= esc_lag_ms <= max_esc_lag_ms
noise std >= 0
required_profiles subset of profile_set
uses_gazebo_truth_as_input=false
```

配置无效时 blocker 为 `airframe_disturbance_config_invalid`，不能 fallback 到 `ideal` profile。

### 4.3 Profile 和 Component 分层

Stage 1 simulation profile 只定义两类：

| profile | 目的 | 预期 |
|---|---|---|
| `ideal` | 无扰动基线 | P11 应稳定通过 |
| `realistic` | 真实机器扰动组合 | motor bias、ESC lag、thrust noise、IMU vibration/noise 同时开启，证明 P11/P12 在接近真实机器的扰动下仍安全 |

`realistic` 下面的扰动 component 必须显式配置和写入 summary：

| component | 目的 | 预期 |
|---|---|---|
| `motor_bias` | 小 motor mismatch / thrust multiplier | 大部分 passthrough，少量 warn/compensate |
| `esc_lag` | 响应时延/动态超调 | attitude rate 可观测，scan availability 不崩 |
| `thrust_noise` | 推力噪声和 motor jitter | 不应导致控制和 scan 大量抖动 |
| `imu_vibration` | IMU 噪声和虚高 tilt | 不应大量误 drop，summary 记录噪声影响 |

`hard_bias` 和 `invalid_config` 是 fault case，不是 Stage 1 required profile。它们的作用是证明 gate 会拒绝危险扰动或无效配置，而不是假装系统能承受所有情况。

### 4.4 P12 复用 P11 水平复原，而不是重写 scan 算法

P12 的 scan 链路必须保持：

```text
/lidar or vendor scan
  -> /navlab/x2/scan_raw
  -> /navlab/x2/scan_normalized
  -> P10 scan integrity
  -> P11 scan stabilization
  -> /scan
  -> SLAM
```

P12 不应该让 SLAM 直接消费 raw scan。扰动 profile 只改变机体/传感器输入条件，不改变 `/scan` ownership contract。

必须验证：

```text
/scan publisher unique
SLAM consumes /scan only
raw scan only for diagnostics / MCAP
set_pose_count = 0
uses_gazebo_truth_as_input = false
```

### 4.5 水平复原验收看 map 风险，不只看 topic rate

P12 不能只看 `/scan` 有数据。必须同时看 map 是否出现明显假墙/异常边界。

建议指标：

```text
scan_availability_ratio
scan_drop_ratio
scan_compensated_ratio
floor_hit_rejected_ratio
max_vertical_projection_error_m
false_wall_risk_score
map_artifact_score
known_cell_growth_delta_vs_ideal
slam_odom_rate_hz
external_nav_rate_hz
controller_ready_ratio
```

`map_artifact_score` 首版可以是可解释的启发式指标，例如：

- 相比 `ideal` baseline，障碍 cell 增长异常比例。
- 短时间内孤立 obstacle cluster 数量。
- 与 official maze overlay 的 review-only 对照差异分数。
- 斜向/弧形假墙段数量。

注意：official maze overlay 只能用于 offline review / summary artifact，不能作为 SLAM、scan stabilization 或 control 输入。

### 4.6 ESC lag 与 timestamp offset 是两回事

P10/P11 的 `max_scan_attitude_time_offset_ms` 只证明 scan message 和 attitude message 对齐。P12 的 ESC lag 是物理响应时延：电机收到命令后推力变化滞后，导致姿态动态超调。

P12 summary 必须分开记录：

```text
scan_attitude_time_offset_ms
esc_lag_ms_by_motor
estimated_attitude_response_lag_ms
max_attitude_rate_dps
attitude_overshoot_count
```

不能用 `scan_attitude_time_offset_ms <= 50` 代替 ESC lag 验证。

### 4.7 IMU vibration/noise 必须单独 profile

振动会造成两个风险：

1. 姿态估计虚高，导致 P10/P11 过度 warn/drop。
2. compensation 使用噪声姿态，导致投影后的 beam 抖动。

P12 需要 vibration profile，至少记录：

```text
imu_noise_profile
imu_vibration_freq_hz
imu_vibration_amp_deg
attitude_noise_rms_deg
tilt_warning_count
tilt_filtered_scan_count
compensation_jitter_score
false_drop_ratio
```

如果当前仿真不能真实模拟 IMU vibration，也必须在 summary 中明确：

```text
imu_vibration_claim = "not_available"
```

不能把 `ideal` IMU run 当成 vibration 验收。

## 5. 目标架构

P12 的目标运行结构：

```text
P12 disturbance profile config
  -> Gazebo/ArduPilot motor disturbance injection
  -> FCU closed-loop flight under P9 representative replay
  -> IMU / rangefinder / X2 scan
  -> P10 scan integrity
  -> P11 scan stabilization
  -> SLAM / ExternalNav / FCU
  -> P12 profile summary + comparison
```

建议组件：

```text
navlab_airframe_disturbance_profile
  - loads configured motor/ESC/noise profile
  - applies profile through Gazebo/ArduPilot plugin params or shim
  - publishes /navlab/airframe_disturbance/status
  - publishes /navlab/airframe_disturbance/events

navlab_airframe_disturbance_gate
  - runs ideal and disturbed profiles
  - parses P10/P11 summaries
  - compares scan/SLAM/FCU/map risk
  - writes P12 summary
```

## 6. Topic 和 artifact contract

P12 raw MCAP 至少包含：

| topic | 用途 |
|---|---|
| `/scan` | P11 stabilized scan，SLAM 输入 |
| `/navlab/x2/scan_raw` | 诊断 raw scan |
| `/navlab/x2/scan_normalized` | 诊断 normalized scan |
| `/navlab/scan_integrity/status` | P10 scan integrity 状态 |
| `/navlab/scan_integrity/events` | P10 事件 |
| `/navlab/scan_stabilization/status` | P11 stabilization 状态 |
| `/navlab/scan_stabilization/events` | P11 事件 |
| `/navlab/airframe_disturbance/status` | P12 扰动 profile 状态 |
| `/navlab/airframe_disturbance/events` | P12 扰动事件 |
| `/imu` 或配置姿态 topic | 姿态/角速度输入 |
| `/rangefinder/down/range` | floor-hit / height guard |
| `/tf`, `/tf_static` | frame contract |
| `/map` | SLAM map 输出 |
| `/slam/odom` | SLAM odom |
| `/ap/v1/*` | FCU 状态和 command owner 检查 |
| `/navlab/fcu/*` | controller/status/summary |
| `/navlab/official_maze/map` | review-only overlay |

Lite MCAP 可以保留：

```text
/tf, /tf_static, /map, /scan, /slam/odom,
/navlab/official_maze/map,
/navlab/scan_integrity/status,
/navlab/scan_stabilization/status,
/navlab/airframe_disturbance/status,
/navlab/fcu/*,
/rangefinder/down/range
```

## 7. Acceptance 设计

P12 acceptance 建议分四段：

### 7.1 Doctor

验证：

- P10/P11 前置 gate 已完成。
- P12 disturbance config 全部显式配置。
- motor/ESC/noise profile 能被 runtime 读取。
- no-truth / unique-owner / no-set-pose 规则仍生效。
- rosbag profile 包含 P12 status/events 和 P10/P11 状态。

### 7.2 Ideal baseline

运行 P9 representative replay + `ideal` profile，记录：

```text
profile = ideal
scan_contract = p11_stabilized_scan
slam_health
external_nav_health
fcu_health
map_artifact_score
```

`ideal` baseline 必须 ok，否则 P12 不继续宣称 disturbed profile 结果。

### 7.3 Realistic Disturbance Components

至少运行 `realistic` profile，并确认以下 component 都被配置、启用并写入 summary：

```text
realistic
esc_lag
motor_bias
thrust_noise
vibration
```

`realistic` profile 记录：

```text
max_abs_roll_deg
max_abs_pitch_deg
rms_roll_deg
rms_pitch_deg
max_attitude_rate_dps
yaw_rate_dps
scan_drop_ratio
scan_compensated_ratio
floor_hit_rejected_ratio
stabilized_scan_rate_hz
slam_odom_rate_hz
external_nav_rate_hz
map_artifact_score_optional
false_wall_risk_ok
```

P12 首版不把 `map_artifact_score` 作为硬 gate 的唯一依据。当前 hard gate 使用 `scan_drop_ratio`、`false_wall_risk_ok`、`slam_health_regressed`、ExternalNav/FCU health 和 no-truth/owner 约束；`map_artifact_score` 保留为 optional/future 指标，后续可升级为 OccupancyGrid 连通分量、official maze overlay 差分或假墙段检测。

### 7.4 Fault profiles

至少运行：

```text
hard_bias
invalid_config
```

预期：

- `hard_bias` 可以 fail，但必须 fail 在明确 blocker 上，例如 `airframe_disturbance_hard_tilt_rejected`、`scan_drop_ratio_too_high`、`floor_hit_risk_too_high` 或 `slam_health_regressed`。
- hard fail 期间 `set_pose_count` 必须仍为 0，不能靠 Gazebo pose reset 兜底。
- disturbance window 内 FCU mode 必须持续为配置的 `required_fcu_mode_number=4` / `required_fcu_mode_name=GUIDED`；当前 window 由 `fcu_mode_window_topic=/navlab/exploration/status` 首尾样本定义，排除 pre-replay bootstrap 阶段。
- FCU mode 不能意外进入 RTL/LAND/failsafe 后还被当作 successful disturbance profile；如果 `/ap/v1/status` 缺失、schema 缺配置字段 `mode` 或 window 内出现非 GUIDED，必须给出明确 blocker。
- 如果 SLAM map 出现假障碍，应作为污染风险 fail，而不是把“能继续发布 scan”当成功。
- `invalid_config` 必须 blocked，不能 fallback 到 `ideal`。

## 8. P12 ok 判定

P12 `ok=true` 必须满足：

- `airframe_disturbance_claim=evaluated`。
- required profiles 全部运行：ideal、realistic。
- ideal baseline ok。
- realistic profile 的 motor bias、ESC lag、thrust noise、IMU vibration/noise components 全部启用并写入 summary。
- realistic profile 的 scan/SLAM/ExternalNav/FCU health 不低于阈值。
- hard profile 的危险行为被 gate 明确拦截。
- invalid config 被明确 blocked。
- required live disturbed profiles 的 `fcu_mode_gate.ok=true`，且 `non_guided_count=0`。
- `/scan` publisher 唯一，SLAM 不消费 raw scan。
- `uses_gazebo_truth_as_input=false`。
- `uses_official_maze_as_input=false`。
- `set_pose_count=0`。
- 所有扰动参数、阈值、profile 列表来自配置并写入 summary。

P12 blocker 示例：

```text
airframe_disturbance_config_invalid
airframe_disturbance_profile_not_applied
required_disturbance_profile_missing
ideal_baseline_failed
scan_contract_not_p11_stabilized
scan_drop_ratio_too_high
stabilized_scan_rate_too_low
slam_health_regressed
external_nav_health_regressed
fcu_health_regressed
map_artifact_risk_too_high_optional
false_wall_risk_failed
hard_tilt_not_rejected
imu_vibration_profile_not_available
esc_lag_profile_not_available
uses_gazebo_truth_as_input
competing_cmd_vel_publishers
set_pose_detected
```

## 9. Summary schema

P12 summary 建议写入：

```json
{
  "ok": true,
  "blockers": [],
  "airframe_disturbance_claim": "evaluated",
  "scan_contract": "p11_stabilized_scan",
  "motion_profile": "p9_representative_replay",
  "uses_gazebo_truth_as_input": false,
  "uses_official_maze_as_input": false,
  "owner": {
    "unique": true,
    "cmd_vel_publishers": ["navlab_fcu_controller"]
  },
  "disturbance_config": {
    "injection_layer": "gazebo_motor_model",
    "seed": 12012,
    "required_profiles": ["ideal", "realistic"]
  },
  "profiles": {
    "realistic": {
      "ok": true,
      "blockers": [],
      "components": {
        "motor_bias": true,
        "esc_lag": true,
        "thrust_noise": true,
        "imu_vibration": true
      },
      "motor": {
        "thrust_multipliers": [0.97, 1.03, 1.0, 0.98],
        "esc_lag_ms": [20.0, 35.0, 25.0, 45.0],
        "thrust_noise_std": 0.015
      },
      "imu_vibration": {
        "enabled": true,
        "freq_hz": 80.0,
        "amp_deg": 0.4,
        "attitude_noise_rms_deg": 0.22
      },
      "flight_attitude_metrics": {
        "max_abs_roll_deg": 4.2,
        "max_abs_pitch_deg": 4.8,
        "rms_roll_deg": 1.4,
        "rms_pitch_deg": 1.7,
        "yaw_rate_dps": 12.0,
        "max_attitude_rate_dps": 86.0
      },
      "scan_stabilization": {
        "passthrough_scan_count": 800,
        "compensated_scan_count": 220,
        "dropped_scan_count": 18,
        "scan_drop_ratio": 0.017,
        "floor_hit_rejected_ratio": 0.004,
        "stabilized_scan_rate_hz": 8.5
      },
      "slam": {
        "odom_rate_hz": 42.0,
        "map_artifact_score": 0.08,
        "false_wall_risk_ok": true
      },
      "fcu_mode_gate": {
        "ok": true,
        "status_topic": "/ap/v1/status",
        "window_topic": "/navlab/exploration/status",
        "required_mode_name": "GUIDED",
        "required_mode_number": 4,
        "status_count": 120,
        "guided_count": 120,
        "non_guided_count": 0
      }
    }
  },
  "comparison": {
    "disturbed_vs_clean_slam_health_regressed": false,
    "disturbed_vs_clean_map_artifact_delta": 0.03,
    "scan_availability_ok": true,
    "horizontal_recovery_claim": "evaluated"
  }
}
```

## 10. MCAP / Foxglove 复核

P12 应复用 P9 official maze overlay 作为 review-only 可视化：

- official wall layer：只做人眼对照，不参与算法。
- SLAM map layer：观察扰动 profile 下假墙/漂移。
- trajectory layer：观察 roll/pitch 变化时路径是否异常。
- scan layer：观察 stabilized `/scan` 是否明显抖动或断流。
- status layer：观察 P11/P12 status 与事件。

P12 使用独立 topic profile：

```text
docker/profiles/navlab-airframe-disturbance-foxglove-lite-topics.txt
```

该 profile 保留 `/navlab/airframe_disturbance/status/events`、`/navlab/scan_stabilization/status/events`、raw `/navlab/imu/raw`、disturbed `/imu`、stabilized `/scan`、SLAM `/map`/`/slam/odom` 和 official maze overlay。topic list 由 profile 文件提供，不写死在 replay builder 里。

Foxglove-lite artifact 应能复核每个 disturbed live replay，但不要求上传 full raw MCAP。

## 11. 与 P10/P11/P13 的关系

P10：证明坏姿态 scan 不会静默进入 SLAM，记录姿态质量和 motor output 可观测性。

P11：在中等安全倾角下做有界 2D 水平投影复原，保留 hard tilt / floor-hit 拒绝。

P12：把真实扰动来源加入仿真，验证 P10/P11 在 motor bias / ESC lag / thrust noise / IMU vibration 下是否仍然安全有效。

P13 才考虑主动 frontier 探索策略优化。P13 必须以 P12 通过后的 disturbance envelope 为前置条件，不能在 scan/SLAM 水平复原还没抗扰验证前加大探索强度。

## 12. 完成后能说明什么

P12 通过后可以说明：

- 当前仿真已经不是完全理想电机/ESC/IMU。
- P10/P11 scan 链路在配置的 realistic disturbance envelope 内没有明显污染 SLAM。
- 超出 envelope 的 hard disturbance 会被 gate 明确 fail，而不是产生假 ok。
- 真机前已有一套可复现的 motor/ESC/vibration 扰动验收标准。

P12 不说明：

- 所有真实电机/桨叶/ESC 缺陷都已覆盖。
- 2D lidar 在任意大角度机动下都可靠。
- 不需要机械减振、标定或云台。
- active frontier exploration 已经最优。
- 真机可以无保护自由飞行。

## Runtime Mode 分流

- `docker + simulation`：保持当前 motor thrust multiplier / ESC lag proxy / vibration profile / disturbed P9 replay 验收路径。
- `process + real`：不注入 motor bias、ESC lag、SDF thrust multiplier 或 Gazebo vibration；只观测真实 flight window 内 attitude、motor output best-effort、scan drop/compensation、SLAM health 和 FCU mode continuity。
- real mode 禁止 P12 disturbed SDF overlay、gazebo-sensor runtime 和 official baseline replay。
- real mode 下如果 P12 试图制造仿真扰动，必须以 `runtime_mode_violation:*` blocker 失败。
- P12 real mode 的目标不是“制造扰动”，而是证明真实无人机自身扰动没有破坏 scan/SLAM contract。
