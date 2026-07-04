# P10 机体固连 lidar 姿态补偿与 scan integrity gate 设计

## 1. 目标

P10 的目标是在 P9 官方 maze 可视化回放已经稳定之后，专门解决一个上真机前必须面对的问题：

```text
真实无人机没有 lidar 云台
  -> 2D lidar 固连在机体上
  -> 电机/桨叶/ESC 标定不完全一致会引入 roll/pitch
  -> lidar 扫描平面不再水平
  -> /scan 可能扫到地面、天花板或错误高度的墙面
  -> SLAM / exploration 可能把错误 scan 当作真实水平障碍
```

P10 要证明：即使机体有小幅姿态扰动，进入 SLAM 和 exploration 的 `/scan` 仍然是可解释、可验收、不会静默污染地图的 scan。

P10 只回答：

- `/scan` 是否来自真实 Gazebo lidar 或真机 lidar 链路，而不是 synthetic fallback。
- `/scan` 是否经过 attitude-aware integrity layer。
- 当 roll/pitch 处于安全范围内时，scan 能继续进入 SLAM。
- 当 roll/pitch 使 2D scan 明显偏离水平面时，系统能 clip/drop/warn，而不是把坏 scan 静默送进 SLAM。
- scan integrity 状态、drop ratio、tilt 统计和阻塞原因是否写入 summary。

P10 通过后，只说明“机体固连 2D lidar 在当前姿态扰动范围内不会静默污染 SLAM 输入”。它不说明无人机已经适合开放空间自由飞行，也不说明探索策略已经最优。

## 2. 为什么 P10 必须单独做

P8/P9 已经证明了官方 maze 中的探索链路和可视化链路，但它们默认 lidar 平面近似水平。这个假设在仿真里容易成立，在真机里不一定成立。

真实无人机常见情况：

- 四个电机静态标定值相同，例如都以 1500 为中值控制。
- 实际响应不完全一致，例如某些电机等效输出偏 1450，某些偏 1550。
- 飞控会闭环补偿姿态，但 hover / 低速移动时仍会出现 roll/pitch 微小偏差和瞬态摆动。
- 固连 2D lidar 会跟着机体一起倾斜；它不是世界坐标系里的水平扫描仪。

这个问题影响很大，因为 2D SLAM 通常隐含“scan 是某个固定高度附近的水平切片”。如果 scan 平面倾斜：

- 向下倾斜的 beam 可能先打到地面，形成假障碍弧线。
- 向上倾斜的 beam 可能越过低矮障碍或扫到错误墙高。
- roll 会造成左右两侧 beam 的高度不一致。
- pitch 会造成前后方向 beam 的高度不一致。
- 地图中可能出现真实 maze 不存在的边界、斜边、圆弧或局部堵塞。

因此 P10 不能和“探索更远、策略更聪明”混在一起做。先把 scan 输入契约做硬，再处理中等倾角下的 2D scan 稳定化；P12 先做 motor bias / ESC lag / vibration 鲁棒性仿真；更激进的探索策略优化进入 P13。

## 3. P10 范围

P10 包含：

- 在原始 X2/vendor scan 和 SLAM `/scan` 之间增加 scan integrity layer。
- 明确 `/scan` 的新语义：`/scan` 是 attitude-validated scan，不再是未经检查的 raw vendor scan。
- 保留 raw scan topic，便于诊断和回放对照。
- 使用 IMU/FCU/TF 中的姿态估计计算 lidar 扫描平面相对重力方向的倾角。
- 对每帧 scan 输出 accept / warn / clip / drop 状态。
- 对明显可能扫到地面/天花板的 beam 做裁剪或整帧 drop。
- 在 summary 中记录 attitude quality、drop ratio、time sync、source contract 和 blocker。
- 增加正常姿态和故障注入姿态两个 gate。
- 保持 P6/P7/P8 的唯一 setpoint owner、无 direct set_pose、无 Gazebo truth 输入规则。

P10 不包含：

- 不增加机械云台。
- 不把 Gazebo truth pose/attitude 作为 scan 修正输入。
- 不把官方 maze 底图作为 SLAM 或 planning 输入。
- 不尝试把坏 scan “几何投影”成看起来合理的水平 scan。
- 不重写探索策略，不追求更大覆盖率。
- 不解决所有电机动力学建模问题；电机/桨叶/ESC 偏置鲁棒性在 P12 单独做。
- 不替换 Cartographer 或引入 3D SLAM。

## 4. 关键设计决定

### 4.1 `/scan` 必须变成 validated scan

P10 之前的链路可以简化为：

```text
Gazebo lidar / real lidar
  -> X2 virtual serial / vendor driver
  -> /scan
  -> SLAM / exploration
```

P10 之后的链路必须变成：

```text
Gazebo lidar / real lidar
  -> X2 virtual serial / vendor driver
  -> /navlab/x2/scan_raw
  -> scan time normalizer
  -> /navlab/x2/scan_normalized
  -> scan attitude integrity filter
  -> /scan
  -> SLAM / exploration
```

其中：

- `/navlab/x2/scan_raw` 保留 vendor 原始输出，用于诊断。
- `/navlab/x2/scan_normalized` 保留 timestamp/frame/angle 归一化后的 scan，用于把 vendor 输出和 integrity filter 输入分开验收。
- `/scan` 是唯一允许 SLAM/Cartographer/exploration 消费的 LaserScan。
- 如果 integrity filter 没有运行，P10 gate 必须失败，而不是 fallback 到 raw `/scan`。

### 4.2 姿态来源必须显式配置，不做静默 fallback

P10 允许的姿态输入来源：

- `/imu/data` 或项目当前 IMU topic。
- `/ap/v1/pose/filtered` 或 FCU filtered attitude equivalent。
- `/tf` 中的 `map/odom -> base_link` 姿态，仅当该 TF 明确来自 SLAM/FCU 正式链路。

不允许：

- 用 `/gazebo/model_states`、Gazebo truth pose 或 simulation-only pose 作为正式修正输入。
- 姿态源缺失时继续发布 unchecked `/scan`。
- 多个姿态源冲突时自动猜一个。

配置里必须指定 attitude source。缺 topic、timestamp 过期、frame 不匹配、source 不在 allowlist、或者 source 被标记为 truth，都必须直接 fail。

### 4.3 P10 首版优先做 filter/clip，不做假补偿

对于固连 2D lidar，软件能做两类事：

1. 识别 scan 是否仍可作为近似水平切片使用。
2. 对明显会打到地面/天花板的 beam 做裁剪或丢弃。

P10 不做“把倾斜 scan 投影回水平面后继续当真”的强补偿。原因是 2D lidar 只知道 beam 方向和距离，不知道命中物体的真实 3D 面。如果直接把倾斜测距投影到水平面，可能把地面点、墙面高处点或噪声点伪造成水平障碍，反而污染 SLAM。

P10 的原则：

```text
可信的小倾角 scan -> 允许进入 /scan
可疑的 beam -> clip 为 range_max 或 NaN，按配置选择
可疑的整帧 scan -> drop，不发布到 /scan
无法判断 -> fail，不静默通过
```

### 4.4 用重力系计算 beam 是否可能扫到地面

scan integrity filter 需要知道：

- `base_link -> base_scan` 静态 TF。
- 当前 `base_link` 相对重力方向的 roll/pitch。
- lidar 离地高度，优先来自 rangefinder/FCU altitude 的正式链路。
- LaserScan 的 angle_min、angle_increment、ranges。

对每个 beam，计算它在 gravity/world-up 坐标下的竖直分量。如果 beam 明显向下，并且按当前高度计算的地面交点距离小于该 beam 的有效测距距离或小于配置阈值，则该 beam 有较高概率是 floor hit，应被 clip/drop。

简化判定：

```text
ray_z < -min_downward_ray_z
floor_intersection_range = lidar_height_m / abs(ray_z)
if floor_intersection_range < floor_hit_guard_range_m:
    mark beam unsafe
```

P10 不要求首版做完整 3D 点云投影，但必须把上述 floor-hit risk 作为可观测指标写入 status/summary。

### 4.5 阈值必须保守并可配置

推荐首版默认阈值：

```text
soft_tilt_deg = 3.0
hard_tilt_deg = 6.0
max_dropped_scan_ratio = 0.05
max_clipped_beam_ratio = 0.20
max_scan_attitude_time_offset_ms = 50
max_attitude_source_age_ms = 250
min_scan_rate_hz = 5.0
min_attitude_rate_hz = 20.0
floor_hit_guard_range_m = 8.0
min_lidar_height_m = 0.25
```

判定语义：

- `tilt <= soft_tilt_deg`：正常发布。
- `soft_tilt_deg < tilt <= hard_tilt_deg`：发布但状态为 warn；如果 beam floor-hit risk 超阈值，则 clip 危险 beam。
- `tilt > hard_tilt_deg`：整帧 drop，不发布到 `/scan`。
- drop ratio 超阈值：P10 gate fail。
- attitude 与 scan 时间差超阈值：P10 gate fail。
- attitude source 最新样本 age 超过 `max_attitude_source_age_ms`：P10 gate fail，blocker 为 `attitude_source_age_too_high`。
- attitude source rate 低于阈值：P10 gate fail。

### 4.6 故障注入必须能证明坏 scan 不会静默通过

P10 不能只跑正常 hover/exploration，然后看到 ok 就结束。它还必须有一个故障注入 profile，模拟 roll/pitch 偏置或 scan plane tilt。

可接受的故障注入方式按优先级：

1. 在 scan integrity filter 前增加 test-only attitude bias 输入，模拟 IMU/FCU 姿态中出现 roll/pitch 偏置。
2. 在 replay/acceptance 中对 recorded attitude 做离线 bias 注入，验证同一段 scan 会被 warn/drop。
3. 如果 Gazebo/ArduPilot 方便配置，再增加 motor/thrust bias 级别的仿真扰动。

P10 首版可以先使用 1 或 2，但 summary 必须明确 `fault_injection_mode`。不能把“没有注入过坏姿态”的 normal run 当成完整 P10 完成。

### 4.7 P10.1 姿态指标和 motor output 可观测性补强

P10.1 不立刻做复杂姿态补偿；先证明飞行期间机体到底倾了多少，以及当前 ROS/MAVLink 链路能不能拿到 motor output。这样后续如果地图异常，可以先区分是 scan integrity 阈值问题、实际姿态抖动问题，还是 actuator 输出不可观测。

必须记录的 flight attitude metrics：

```text
max_abs_roll_deg
max_abs_pitch_deg
rms_roll_deg
rms_pitch_deg
yaw_rate_dps
max_attitude_rate_dps
```

必须记录的 scan attitude quality schema：

```text
scan_attitude_quality.ok
scan_attitude_quality.max_scan_tilt_deg
scan_attitude_quality.tilt_filtered_scan_count
scan_attitude_quality.tilt_warning_count
```

Motor output 只做 best effort，不允许假装有数据：

- 如果 ROS graph / `/ap/*` / MAVLink bridge 暴露了可解析的 motor、servo、actuator、ESC、RPM 或 PWM topic，summary 可以记录 `motor_pwm_*`、`motor_rpm_*` 和 `motor_thrust_bias_estimate`。
- 如果只发现候选 topic 但没有稳定解码出数值，summary 只能记录 `candidate_topics`，不能填假数。
- 如果当前 ROS graph 没有暴露 motor output topic，summary 必须明确 `motor_output_claim=not_available`，所有 PWM/RPM/spread/bias 字段为 `null`。

这个补强的完成口径是“可观测性清楚”，不是“电机偏置已经被补偿”。真正的 motor bias / ESC lag / thrust multiplier 鲁棒性仿真放到 P12。

## 5. 目标架构

P10 的目标运行结构：

```text
Gazebo official maze / real lidar
  -> lidar sensor source
  -> X2 virtual serial emulator
  -> ydlidar vendor driver
  -> /navlab/x2/scan_raw
  -> scan normalizer
  -> /navlab/x2/scan_normalized

IMU / FCU attitude / TF
  -> attitude source selector
  -> time synchronizer

/navlab/x2/scan_normalized + attitude + base_scan TF + rangefinder height
  -> scan integrity filter
  -> /scan
  -> Cartographer / SLAM
  -> ExternalNav
  -> FCU EKF
  -> P8/P9-style exploration/replay if needed
```

关键边界：

- scan integrity filter 是 `/scan` 的 owner。
- SLAM 不订阅 raw scan。
- exploration 不订阅 raw scan。
- Gazebo truth 只允许进入 diagnostic summary，不允许进入 filter 输入。
- rangefinder height 用于 floor-hit guard，因为它是真机存在的传感器机制；缺失时 gate 必须 fail，不能自动用 Gazebo truth height 顶替。

## 6. Topic 设计

### 6.1 输入 topic

| Topic | 类型 | 用途 | 要求 |
|---|---|---|---|
| `/navlab/x2/scan_raw` | `sensor_msgs/LaserScan` | vendor/raw scan 诊断 | 必须存在，不能被 SLAM 消费 |
| `/navlab/x2/scan_normalized` | `sensor_msgs/LaserScan` | timestamp/frame/angle 归一化后的 scan | 必须存在，不能省略 |
| `/imu/data` | `sensor_msgs/Imu` | 姿态/角速度输入 | 允许作为正式姿态源 |
| `/ap/v1/pose/filtered` | official pose equivalent | FCU filtered attitude 输入 | 允许作为正式姿态源 |
| `/tf_static` | `tf2_msgs/TFMessage` | `base_link -> base_scan` | 必须包含静态 lidar mount |
| `/tf` | `tf2_msgs/TFMessage` | 动态姿态链路 | 仅当 source contract 明确允许 |
| `/rangefinder/down/range` | range message | lidar height / floor guard | 推荐；缺失时按配置 fail 或禁用 floor guard |

### 6.2 输出 topic

| Topic | 类型 | 用途 | 要求 |
|---|---|---|---|
| `/scan` | `sensor_msgs/LaserScan` | validated scan，SLAM 唯一输入 | 必须由 integrity filter 发布 |
| `/navlab/scan_integrity/status` | `std_msgs/String` JSON | 当前 scan integrity 状态 | 必须录 bag |
| `/navlab/scan_integrity/events` | `std_msgs/String` JSON | warn/drop/clip 事件 | 推荐录 bag |
| `/navlab/scan_integrity/debug_scan_dropped` | `sensor_msgs/LaserScan` | 被 drop 的 scan 样本 | 可选，只在 debug profile 开启 |
| `/navlab/scan_integrity/debug_scan_clipped` | `sensor_msgs/LaserScan` | beam clip 后的 debug scan | 可选，只在 debug profile 开启 |

### 6.3 `/navlab/scan_integrity/status` schema

status 建议使用一行 JSON，便于 summary 聚合：

```json
{
  "ok": true,
  "state": "accept",
  "scan_source": "gazebo_ideal",
  "attitude_source": "/imu/data",
  "roll_deg": 0.7,
  "pitch_deg": -1.1,
  "tilt_deg": 1.3,
  "scan_attitude_time_offset_ms": 12.4,
  "input_scan_stamp": 1780842146.42,
  "attitude_stamp": 1780842146.41,
  "accepted_scan_count": 1255,
  "warn_scan_count": 4,
  "dropped_scan_count": 0,
  "clipped_beam_ratio": 0.003,
  "floor_hit_risk_beam_ratio": 0.001,
  "blockers": []
}
```

`state` 允许值：

- `accept`：正常发布。
- `warn`：发布，但倾角或 beam risk 接近阈值。
- `clip`：发布，但部分 beam 被裁剪。
- `drop`：本帧不发布到 `/scan`。
- `blocked`：contract 失败，gate 应失败。

## 7. Gate profile 设计

P10 至少需要两个 profile。

### 7.1 Normal integrity profile

目标：证明正常 hover / 小范围移动时，validated `/scan` 可以稳定进入 SLAM。

建议流程：

```text
P6 hover prerequisite
  -> P7 small motion prerequisite
  -> start scan integrity filter
  -> short forward/back/yaw movement
  -> record raw scan, validated scan, attitude, status, SLAM, FCU
  -> summarize drop/clip/tilt/time sync
```

完成标准：

- `/scan` publisher 只有 integrity filter。
- `/navlab/x2/scan_raw` 有数据。
- `/scan` 有数据且非静态。
- SLAM odom 健康。
- ExternalNav 健康。
- FCU local position 健康。
- `max_abs_roll_deg <= soft_tilt_deg` 或 warn ratio 在阈值内。
- `dropped_scan_ratio <= max_dropped_scan_ratio`。
- `max_scan_attitude_time_offset_ms <= 50`。

### 7.2 Tilt fault-injection profile

目标：证明坏姿态不会静默通过。

建议流程：

```text
reuse normal run input or start controlled short run
  -> inject roll/pitch bias below soft threshold
  -> verify state remains accept/warn
  -> inject roll/pitch bias above hard threshold
  -> verify state becomes drop/blocked
  -> remove bias
  -> verify state returns to accept within N scans
  -> verify summary reports expected blockers or expected_fault_response=true
```

完成标准：

- mild tilt case 不导致系统崩溃。
- hard tilt case 不能继续把 unchecked scan 发布到 `/scan`。
- drop/warn/clip 事件被记录。
- gate 能区分 expected fault response 和真实 failure。
- 如果 fault injection 没跑，P10 不能标记完成。

## 8. MCAP 和 Foxglove 回放口径

P10 raw acceptance MCAP 必须包含：

```text
/tf
/tf_static
/scan
/navlab/x2/scan_raw
/navlab/x2/scan_normalized
/navlab/scan_integrity/status
/navlab/scan_integrity/events
/imu/data
/ap/v1/pose/filtered
/slam/odom
/navlab/slam/status
/navlab/fcu/owner/status
/navlab/fcu/controller/status
/rangefinder/down/range
```

P10 可以继续沿用 P9 的 Foxglove-lite replay 思路，但 P10 的核心验收不是上传体积，也不是重新生成官方 maze 底图，而是 scan integrity 证据完整。官方 maze 对照继续使用 P9 lite replay；P10 raw MCAP 必须优先保留 raw scan、normalized scan、validated `/scan`、status/events、SLAM map/odom、TF 和必要 FCU 状态。

Foxglove 中应该能看到：

- raw P10 MCAP 中的 scan integrity 证据。
- SLAM `/map`。
- validated `/scan`。
- raw scan 对照层。
- scan integrity status/time series。
- roll/pitch/tilt 曲线。

如果需要把这些证据和官方 maze 墙体叠加，使用 P9 Foxglove-lite overlay/replay 流程生成 visualization artifact；P10 不把官方底图作为 gate 输入。

## 9. Gate 判定

P10 `ok=true` 必须满足：

- `scan_integrity_claim=evaluated`。
- `motion_claim` 至少继承 P7/P8 prerequisite 结果，不能未知。
- `/scan` owner 是 scan integrity filter。
- SLAM 不订阅 raw scan。
- `uses_gazebo_truth_as_input=false`。
- `set_pose_count=0`。
- `owner.unique=true`。
- `base_link -> base_scan` 静态 TF 存在。
- attitude source 明确且非 truth。
- scan/attitude 时间同步满足阈值。
- normal profile 通过。
- tilt fault-injection profile 通过。
- raw MCAP 和 summary 都存在。

P10 阻塞条件示例：

```text
missing_raw_scan
missing_validated_scan
scan_owner_not_integrity_filter
slam_consumes_raw_scan
missing_base_scan_static_tf
missing_attitude_source
attitude_source_is_truth
scan_attitude_time_offset_too_high
scan_rate_too_low
dropped_scan_ratio_too_high
floor_hit_risk_too_high
fault_injection_not_run
hard_tilt_not_rejected
uses_gazebo_truth_as_input
set_pose_detected
owner_not_unique
```

## 10. Summary schema

P10.1 后 summary 需要同时表达 scan integrity 结论、flight attitude 统计，以及 motor output 是否可观测；缺 motor output 时必须显式写 `motor_output_claim=not_available`。

P10 summary 建议写入：

```json
{
  "ok": true,
  "blocked": false,
  "blockers": [],
  "scan_integrity_claim": "evaluated",
  "exploration_claim": "not_evaluated",
  "uses_gazebo_truth_as_input": false,
  "scan_integrity": {
    "scan_owner": "navlab_scan_integrity_filter",
    "raw_scan_topic": "/navlab/x2/scan_raw",
    "normalized_scan_topic": "/navlab/x2/scan_normalized",
    "validated_scan_topic": "/scan",
    "attitude_source": "/imu",
    "base_scan_static_tf_ok": true,
    "scan_source": "gazebo_ideal",
    "normal_profile_ok": true,
    "fault_injection_ok": true,
    "fault_injection_mode": "attitude_bias_runtime"
  },
  "flight_attitude_metrics": {
    "sample_count": 213407,
    "max_abs_roll_deg": 0.38,
    "max_abs_pitch_deg": 1.29,
    "rms_roll_deg": 0.19,
    "rms_pitch_deg": 0.21,
    "yaw_rate_dps": -0.03,
    "max_attitude_rate_dps": 38.02
  },
  "scan_attitude_quality": {
    "ok": true,
    "max_scan_tilt_deg": 8.34,
    "tilt_filtered_scan_count": 315,
    "tilt_warning_count": 0,
    "dropped_scan_count": 315,
    "clipped_scan_count": 0,
    "hard_tilt_count": 32,
    "dropped_scan_ratio": 0.386,
    "max_clipped_beam_ratio": 0.0,
    "max_floor_hit_risk_beam_ratio": 0.0
  },
  "motor_output": {
    "motor_output_claim": "not_available",
    "available": false,
    "candidate_topics": [],
    "motor_pwm_min": null,
    "motor_pwm_max": null,
    "motor_pwm_spread": null,
    "motor_rpm_min": null,
    "motor_rpm_max": null,
    "motor_rpm_spread": null,
    "motor_thrust_bias_estimate": null
  },
  "truth_control": {
    "set_pose_count": 0,
    "gazebo_truth_as_input": false
  },
  "owner": {
    "unique": true,
    "competing_publishers": []
  }
}
```

## 11. 和后续阶段的关系

P10 通过后只能说明：

- 机体固连 lidar 的 scan 输入契约已经比 P8/P9 更接近真机。
- 小姿态扰动下 `/scan` 不会无检查地污染 SLAM。
- 大姿态扰动会被 warn/drop/block，而不是静默通过。
- 真机前的 lidar 姿态风险已经有可观测 gate。

P10 不说明：

- 电机、桨叶、ESC 的真实动力学偏差已经完整建模。
- 无人机可以在真实室内环境中无保护高速探索。
- 探索策略已经足够覆盖完整 maze。
- 3D 障碍、玻璃、反光、动态人/物体已经解决。

后续建议：

- P11：有界 2D lidar 姿态稳定化，在 P9 representative replay 强度下减少中等倾角造成的 scan drop。
- P12：电机/桨叶/ESC 偏置鲁棒性仿真，加入 motor bias / ESC lag / thrust multiplier / vibration profile，验证 P11 水平复原在真实扰动来源下仍安全。
- P13：主动 frontier 探索策略优化，必须以 P12 扰动 envelope 通过为前置条件。
- P14：真机 tethered indoor preflight，先做限位/保护下的 hover + scan integrity + stabilization 验收。

## Runtime Mode 分流

- `docker + simulation`：保持当前 P10 验收路径，允许 Gazebo/SITL/official baseline/gazebo-sensor/SDF overlay 生成可复现实验数据。
- `process + real`：只允许真实 `/scan`、真实 attitude source、真实 FCU/SLAM topic 进入 scan integrity 检查。
- real mode 禁止启动 Gazebo/SITL/official baseline/gazebo-sensor，也禁止生成 SDF/param overlay。
- real mode 下如果当前 P10 acceptance 代码路径试图进入 simulation-only service/source/overlay，必须以 `runtime_mode_violation:*` blocker 失败，而不是 fallback 到 Docker。
- P10 首版 real mode 的目标是保护边界：不把仿真 scan/IMU/rangefinder 当真机数据；完整真实 flight scan integrity gate 后续再按 real-preflight contract 扩展。
