# P11 有界 2D lidar 姿态稳定化设计

## 1. 目标

P11 的目标是在 P10 scan integrity gate 已经证明“坏姿态 scan 不会静默污染 SLAM”之后，继续解决一个更接近实际飞行的问题：

```text
P9 representative replay 速度更高、路径更长
  -> 飞机可能出现比 P8/P10 慢速 gate 更明显的 roll/pitch
  -> P10 drop-only 策略会保护 SLAM，但也会减少有效 /scan 输入
  -> SLAM 可能因为 scan rate/coverage 不足而退化
  -> P11 在保守边界内尝试 2D lidar scan stabilization
```

P11 只考虑 2D lidar，不引入 3D lidar 或 PointCloud 路线。

P11 只回答：

> 能否在不使用 Gazebo truth、不把地面/天花板 hit 伪造成墙、不放松 P10 hard safety 的前提下，对中等倾角下的 2D LaserScan 做有界姿态稳定化，让 P9 representative replay 中 SLAM 获得更多有效 scan？

P11 通过后，操作者应该能判断：

- P10 drop-only baseline 在 P9 representative replay 下会丢多少 scan。
- P11 bounded 2D projection candidate 能否提高有效 scan availability。
- 补偿后的 `/scan` 是否仍由唯一 scan owner 发布。
- hard tilt、floor-hit risk、projection error 过大的 beam 是否仍被 reject/drop。
- SLAM map/odom 是否没有因为补偿引入明显假墙或退化。

## 2. 为什么 P11 必须单独做

P10 是安全门，不是补偿层。P10 的正确行为是：

```text
小倾角 scan -> accept
可疑 beam -> clip/drop
大倾角 scan -> drop
```

这个策略非常适合 hover 和慢速 motion，因为它优先保证 SLAM 输入不被污染。但如果后续飞得更快，例如前倾加速或更长距离 P9 representative replay，机体固连 2D lidar 会更频繁偏离水平面。此时 P10 继续 drop 是安全的，但可能带来：

- `/scan` 有效帧率下降。
- Cartographer scan matching 可用观测减少。
- `/map` 更新变慢或局部退化。
- P9 overlay 中轨迹增长了，但 SLAM map 增长不明显。

P11 不能直接把所有 tilted scan 投影成水平 scan，因为 2D lidar 不知道命中物体的真实 3D 表面。向下打到地面的点如果被简单投影回水平面，会变成假墙。P11 因此必须做“有界补偿”：只在倾角、垂直误差、floor-hit risk 和保留 beam 比例都满足门槛时补偿。

P11 也不能继续使用 P8 slow exploration profile 作为主验收，因为 P8 太保守，姿态扰动小，补偿层几乎不会被触发。P11 的主验收必须基于 P9 representative replay motion profile：速度更高、路径更长、覆盖更明显，但仍不放松 owner、truth、clearance、stop drift、SLAM、ExternalNav 和 FCU health gate。

## 3. P11 范围

P11 包含：

- 增加 2D lidar scan stabilization layer。
- 复用 P10 raw/normalized scan、attitude source、rangefinder height、TF 和 scan integrity 状态。
- 基于 IMU/TF 姿态，把 LaserScan endpoint 转到 gravity-aligned frame，再在安全边界内投影回水平平面。
- 增加 passthrough / compensate / drop 三段式策略。
- 所有补偿门槛参数化，不能 hardcode。
- 记录 projection error、retained/rejected beam ratio、compensated scan count、false-wall risk。
- 使用 P9 representative replay profile 作为主验收运动强度。
- 对比 P10 drop-only baseline 和 P11 bounded projection candidate。
- 保留 P10 hard tilt / floor-hit / no-truth / unique-owner 安全边界。

P11 不包含：

- 不引入 3D lidar 或 PointCloud pipeline。
- 不要求完整覆盖官方 maze。
- 不把官方 maze 底图作为 SLAM、planning、ExternalNav 或控制输入。
- 不使用 Gazebo truth pose/attitude 做 scan 补偿。
- 不把所有 tilted scan 都投影成水平障碍。
- 不放松 P10 hard tilt drop。
- 不改探索策略本身；P11 评估 scan 输入稳定化，不评估新的 frontier/Nav2 策略。
- 不建模 motor bias / ESC lag；这进入 P12 机体扰动鲁棒性 phase。

## 4. 关键设计决定

### 4.1 P11 基于 P9 representative replay，而不是 P8 slow exploration

P8 acceptance 的目标是安全探索闭环，速度慢、移动短、保守。P11 的目标是验证中等倾角下 scan 输入是否还能稳定供给 SLAM，因此主验收必须使用 P9 representative replay motion profile。

建议 P11 gate 明确记录：

```json
{
  "motion_profile": "p9_representative_replay",
  "baseline_mode": "p10_drop_only",
  "candidate_mode": "bounded_2d_projection"
}
```

P11 不应该重新写一套探索策略，也不应该把 P8 最小 gate 当作补偿验收。P11 只复用 P9 的代表性运动强度，用来制造更真实的姿态扰动和 SLAM 观测压力。

### 4.2 P11 是 P10 后面的 stabilization layer，不替代 P10 safety

P10 之后的 scan 输入链路是：

```text
Gazebo lidar / real lidar
  -> X2 virtual serial / vendor driver
  -> /navlab/x2/scan_raw
  -> scan time normalizer
  -> /navlab/x2/scan_normalized
  -> P10 scan integrity filter
  -> /scan
```

P11 之后建议调整为：

```text
Gazebo lidar / real lidar
  -> X2 virtual serial / vendor driver
  -> /navlab/x2/scan_raw
  -> scan time normalizer
  -> /navlab/x2/scan_normalized
  -> P10/P11 shared scan quality input
  -> P11 bounded 2D scan stabilization
  -> /scan
  -> Cartographer / SLAM
```

可选中间 topic：

```text
/navlab/scan_integrity/scan_filtered
/navlab/scan_stabilization/scan_stabilized
/navlab/scan_stabilization/status
/navlab/scan_stabilization/events
```

但 `/scan` 的语义必须保持清楚：SLAM 唯一消费的 `/scan` 是已经通过 P10/P11 安全边界的 scan。不能同时让 raw scan 和 stabilized scan 都发布到 `/scan`。

### 4.3 三段式倾角策略

P11 不做无限制补偿，而是按倾角分区：

```text
tilt <= passthrough_tilt_deg:
  passthrough，不做投影补偿

passthrough_tilt_deg < tilt <= compensation_tilt_deg:
  尝试 bounded 2D projection
  对高风险 beam reject/clip
  满足保留比例后发布 stabilized scan

compensation_tilt_deg < tilt <= hard_drop_tilt_deg:
  默认 drop 或仅 debug 发布，不进入 /scan

tilt > hard_drop_tilt_deg:
  hard drop，不能补偿
```

推荐首版默认值：

```text
passthrough_tilt_deg = 3.0
compensation_tilt_deg = 8.0
hard_drop_tilt_deg = 10.0
```

这些数值只能是默认配置，不能写死在算法里。

### 4.4 2D projection 必须带垂直误差和 floor-hit gate

每个 LaserScan beam 可以先转成 lidar frame endpoint：

```text
p_scan = [range * cos(angle), range * sin(angle), 0]
```

再用 `base_link -> base_scan` 和当前 attitude，把 endpoint 转到 gravity-aligned frame：

```text
p_level = R_base_to_level * T_base_scan * p_scan
```

P11 只在以下条件满足时保留该 beam：

```text
abs(p_level.z) <= max_vertical_projection_error_m
floor_hit_risk == false
range_stabilized within [range_min, range_max]
```

保留后重新计算水平 endpoint：

```text
range_stabilized = hypot(p_level.x, p_level.y)
angle_stabilized = atan2(p_level.y, p_level.x)
```

然后重新栅格化回 LaserScan。多个原始 beam 落到同一输出 angle bin 时，选择更近的有效 range。

如果 rejected beam 太多，整帧 drop：

```text
rejected_beam_ratio > max_rejected_beam_ratio -> drop frame
retained_beam_ratio < min_retained_beam_ratio -> drop frame
floor_hit_risk_beam_ratio > max_floor_hit_risk_beam_ratio -> drop frame
```

### 4.5 所有门槛必须参数化

P11 gate 影响 SLAM 输入质量，不能把阈值 hardcode 到代码中。配置必须集中在 `orchestration/config.toml` 或项目配置，并写入 summary。

建议配置段：

```toml
[scan_stabilization_gate]
rosbag_profile = "docker/profiles/navlab-scan-stabilization-gate-rosbag-topics.txt"
motion_profile = "p9_representative_replay"
baseline_mode = "p10_drop_only"
candidate_mode = "bounded_2d_projection"
uses_gazebo_truth_as_input = false
scan_stabilization_claim = "evaluated"

[scan_stabilization]
enabled = true
mode = "bounded_2d_projection"
input_scan_topic = "/navlab/x2/scan_normalized"
output_scan_topic = "/scan"
status_topic = "/navlab/scan_stabilization/status"
events_topic = "/navlab/scan_stabilization/events"
debug_scan_topic = "/navlab/scan_stabilization/debug_scan"
attitude_source_topic = "/imu"
attitude_source_type = "imu"
range_topic = "/rangefinder/down/range"
base_frame_id = "base_link"
scan_frame_id = "base_scan"
passthrough_tilt_deg = 3.0
compensation_tilt_deg = 8.0
hard_drop_tilt_deg = 10.0
max_vertical_projection_error_m = 0.15
max_rejected_beam_ratio = 0.35
min_retained_beam_ratio = 0.55
max_floor_hit_risk_beam_ratio = 0.05
floor_hit_guard_range_m = 8.0
min_lidar_height_m = 0.25
min_downward_ray_z = 0.05
max_scan_attitude_time_offset_ms = 50.0
min_attitude_rate_hz = 20.0
min_stabilized_scan_rate_hz = 5.0
publish_debug_scan = false
```

配置校验必须覆盖：

```text
0 <= passthrough_tilt_deg < compensation_tilt_deg < hard_drop_tilt_deg
0 <= max_rejected_beam_ratio <= 1
0 <= min_retained_beam_ratio <= 1
0 <= max_floor_hit_risk_beam_ratio <= 1
max_vertical_projection_error_m > 0
uses_gazebo_truth_as_input=false
```

配置无效时 blocker 为 `scan_stabilization_config_invalid`，不能继续跑。

### 4.6 Baseline 与 candidate 必须可对比

P11 acceptance 至少需要两组结果：

```text
baseline:  P10 drop-only scan integrity
candidate: P11 bounded 2D projection stabilization
```

每组使用同一类 P9 representative replay motion profile，并记录：

```text
validated_scan_count
validated_scan_rate_hz
dropped_scan_count
dropped_scan_ratio
slam_odom_rate_hz
map_update_count
known_cell_growth
path_length_m
min_scan_clearance_m
owner.unique
set_pose_count
uses_gazebo_truth_as_input
```

Candidate 还必须记录：

```text
compensated_scan_count
passthrough_scan_count
rejected_beam_count
retained_beam_ratio
rejected_beam_ratio
max_vertical_projection_error_m
mean_vertical_projection_error_m
max_compensated_tilt_deg
floor_hit_rejected_count
false_wall_risk_ok
```

false-wall risk 的首版计算是保守布尔值：`false_wall_risk_ok = floor_hit_risk_beam_ratio <= max_floor_hit_risk_beam_ratio`，并结合 `floor_hit_rejected_count`、`hard_tilt_dropped`、`map_artifact_risk_ok` 和 SLAM health 做 gate。它不是完整 map artifact detector；如果后续 compensation 大量触发，应升级为 map/overlay 差分或连通分量分析。

P11 不是单纯追求“scan 越多越好”。如果补偿后出现假墙风险、floor-hit 被投影成障碍、SLAM odom 退化，即使 scan 数量增加也不能通过。

### 4.7 官方 maze overlay 只用于人工复核

P11 可以沿用 P9 Foxglove-lite overlay 作为可视化复核：

- 官方 wall map。
- SLAM `/map`。
- baseline `/scan` 或 candidate `/scan`。
- stabilized scan status。
- trajectory。
- scan availability time series。

但官方 maze 底图仍然是 visualization-only：

```text
used_as_slam_input = false
used_as_planning_input = false
used_as_control_input = false
```

P11 不允许用官方 maze SDF 来判断某个 beam 是否真实命中墙，也不允许用官方墙体作为补偿 ground truth。

## 5. 目标架构

```text
P9 representative replay profile
  higher speed / longer path than P8 acceptance
  still respects owner, truth, clearance, stop drift, SLAM, ExternalNav, FCU gates

P10 baseline mode
  /navlab/x2/scan_normalized
    -> P10 scan integrity filter
    -> /scan
    -> SLAM
  summary: drop-only availability and SLAM health

P11 candidate mode
  /navlab/x2/scan_normalized + attitude + TF + rangefinder height
    -> bounded 2D scan stabilization
    -> /scan
    -> SLAM
  summary: compensated availability, projection quality and SLAM health

P9 overlay postprocess
  raw MCAP + optional lite MCAP
    -> official maze overlay for visualization only
```

关键边界：

- `/scan` publisher 必须唯一。
- SLAM 不消费 `/navlab/x2/scan_raw` 或 unchecked scan。
- P11 不读取 Gazebo truth pose/attitude。
- P11 不读取 official maze as correction input。
- baseline/candidate 对比要写入同一个 summary 或可关联的两个 artifact summary。

## 6. Topic 设计

### 6.1 输入 topic

| Topic | 类型 | 用途 | 要求 |
|---|---|---|---|
| `/navlab/x2/scan_raw` | `sensor_msgs/LaserScan` | raw/vendor 诊断 | 必须录 bag，不进 SLAM |
| `/navlab/x2/scan_normalized` | `sensor_msgs/LaserScan` | P11 compensation 输入 | 必须存在 |
| `/imu` 或 `/imu/data` | `sensor_msgs/Imu` | 姿态输入 | 必须显式配置，非 truth |
| `/tf_static` | `tf2_msgs/TFMessage` | `base_link -> base_scan` | 必须包含 lidar mount |
| `/tf` | `tf2_msgs/TFMessage` | 动态 TF/回放对齐 | 必须录 bag |
| `/rangefinder/down/range` | range message | lidar height / floor guard | 推荐必需，缺失按配置 fail |
| `/slam/odom` | odometry | SLAM health | 必须用于健康评估 |
| `/map` | `nav_msgs/OccupancyGrid` | map growth | 必须用于 baseline/candidate 对比 |

### 6.2 输出 topic

| Topic | 类型 | 用途 | 要求 |
|---|---|---|---|
| `/scan` | `sensor_msgs/LaserScan` | SLAM 唯一输入 | 必须由 P11/P10 owner 发布 |
| `/navlab/scan_stabilization/status` | `std_msgs/String` JSON | 每帧状态 | 必须录 bag |
| `/navlab/scan_stabilization/events` | `std_msgs/String` JSON | warn/drop/project 事件 | 必须录 bag |
| `/navlab/scan_stabilization/debug_scan` | `sensor_msgs/LaserScan` | debug-only stabilized scan | 可选，不作为 SLAM 输入 |

### 6.3 Status schema

```json
{
  "ok": true,
  "state": "compensate",
  "mode": "bounded_2d_projection",
  "input_scan_topic": "/navlab/x2/scan_normalized",
  "output_scan_topic": "/scan",
  "roll_deg": 4.2,
  "pitch_deg": -2.1,
  "tilt_deg": 4.7,
  "scan_attitude_time_offset_ms": 12.0,
  "passthrough_scan_count": 820,
  "compensated_scan_count": 140,
  "dropped_scan_count": 25,
  "rejected_beam_ratio": 0.18,
  "retained_beam_ratio": 0.72,
  "max_vertical_projection_error_m": 0.12,
  "mean_vertical_projection_error_m": 0.03,
  "floor_hit_rejected_count": 34,
  "false_wall_risk_ok": true,
  "blockers": []
}
```

`state` 允许值：

- `passthrough`：小倾角，直接通过。
- `compensate`：中等倾角，已做 bounded 2D projection。
- `drop`：质量不足，本帧不发布到 `/scan`。
- `blocked`：contract 失败，gate 应失败。

## 7. Gate profile 设计

### 7.1 Baseline profile：P10 drop-only under P9 replay

目标：建立 P10 在更高速度 P9 representative replay 下的 scan availability 和 SLAM health baseline。

建议流程：

```text
P6 hover prerequisite
  -> P7 owner / motion safety prerequisite
  -> P9 representative replay motion profile
  -> P10 scan integrity drop-only mode
  -> record /scan, /map, /slam/odom, status, TF, attitude
  -> summarize scan drops and SLAM health
```

完成标准：

- baseline artifact 存在。
- baseline 不使用 Gazebo truth input。
- baseline owner unique。
- baseline 记录 P10 drop-only scan availability。
- baseline SLAM/ExternalNav/FCU health 可评价。

### 7.2 Candidate profile：bounded 2D projection under P9 replay

目标：验证 P11 candidate 在同类 P9 representative replay 下提高 scan availability，同时不引入假墙风险。

建议流程：

```text
P6 hover prerequisite
  -> P7 owner / motion safety prerequisite
  -> P9 representative replay motion profile
  -> P11 bounded 2D projection enabled
  -> record /scan, /map, /slam/odom, status, TF, attitude
  -> summarize compensation quality and SLAM health
```

完成标准：

- `scan_stabilization_claim=evaluated`。
- `validated_scan_count >= baseline.validated_scan_count` 或 summary 解释没有触发补偿的原因。
- `validated_scan_rate_hz >= min_stabilized_scan_rate_hz`。
- `compensated_scan_count > 0`，除非 replay tilt 分布证明没有进入 compensation zone。
- `false_wall_risk_ok=true`。
- hard tilt 仍然 drop。
- floor-hit beam 不会投影成墙。
- SLAM odom、ExternalNav、FCU health 不退化。

### 7.3 Fault profile：bad projection rejection

P11 还需要一个 fault/injection profile，证明 projection 不是万能放行：

```text
inject medium tilt with safe geometry -> compensate or passthrough
inject floor-hit risk -> reject beam / drop frame
inject hard tilt -> drop frame
inject stale attitude -> blocked
```

如果 fault profile 没跑，P11 blocker 包含：

```text
scan_stabilization_fault_profile_not_run
```

如果 hard tilt 被补偿通过，P11 blocker 包含：

```text
hard_tilt_compensated
```

## 8. MCAP 和 Foxglove 回放口径

P11 raw MCAP 必须包含：

```text
/tf
/tf_static
/map
/scan
/navlab/x2/scan_raw
/navlab/x2/scan_normalized
/navlab/scan_stabilization/status
/navlab/scan_stabilization/events
/navlab/scan_integrity/status
/navlab/scan_integrity/events
/imu
/rangefinder/down/range
/slam/odom
/navlab/slam/status
/navlab/fcu/owner/status
/navlab/fcu/controller/status
/navlab/motion/status
```

P11 可以生成 Foxglove-lite artifact，但其用途是人工复核，不替代 raw acceptance evidence。Foxglove-lite 建议保留：

```text
/navlab/official_maze/map
/map
/scan
/slam/odom
/tf
/tf_static
/navlab/scan_stabilization/status
/navlab/scan_stabilization/events
/navlab/exploration/* 或 representative replay status
```

P11 summary 必须记录：

```text
official_maze_layer_role = visualization_only
uses_official_maze_as_input = false
uses_gazebo_truth_as_input = false
```

## 9. Gate 判定

P11 `ok=true` 必须满足：

- `scan_stabilization_claim=evaluated`。
- motion profile 是 `p9_representative_replay`，不是 P8 slow acceptance。
- baseline/candidate 都有 summary，或 summary 明确 candidate-only 的原因。
- P11 所有补偿门槛来自配置并写入 summary。
- `/scan` owner unique。
- SLAM 不消费 raw scan。
- `uses_gazebo_truth_as_input=false`。
- `uses_official_maze_as_input=false`。
- `set_pose_count=0`。
- attitude source 明确、非 truth、fresh/rate/time sync 通过。
- hard tilt 仍 drop。
- floor-hit risk 不被投影成障碍。
- compensated scan 不导致 SLAM/ExternalNav/FCU health 退化。
- raw MCAP 和 summary 存在。

P11 blocker 示例：

```text
scan_stabilization_config_invalid
motion_profile_not_p9_representative_replay
missing_baseline_summary
missing_candidate_summary
scan_owner_not_unique
slam_consumes_raw_scan
missing_attitude_source
attitude_source_is_truth
scan_attitude_time_offset_too_high
hard_tilt_compensated
floor_hit_projected_as_wall
projection_error_too_high
rejected_beam_ratio_too_high
retained_beam_ratio_too_low
stabilized_scan_rate_too_low
slam_health_regressed
external_nav_health_regressed
fcu_health_regressed
uses_gazebo_truth_as_input
uses_official_maze_as_input
set_pose_detected
```

## 10. Summary schema

P11 summary 建议写入：

```json
{
  "ok": true,
  "blocked": false,
  "blockers": [],
  "scan_stabilization_claim": "evaluated",
  "motion_profile": "p9_representative_replay",
  "uses_gazebo_truth_as_input": false,
  "uses_official_maze_as_input": false,
  "official_maze_layer_role": "visualization_only",
  "scan_stabilization": {
    "mode": "bounded_2d_projection",
    "input_scan_topic": "/navlab/x2/scan_normalized",
    "output_scan_topic": "/scan",
    "status_topic": "/navlab/scan_stabilization/status",
    "runtime_config": {
      "passthrough_tilt_deg": 3.0,
      "compensation_tilt_deg": 8.0,
      "hard_drop_tilt_deg": 10.0,
      "max_vertical_projection_error_m": 0.15,
      "max_rejected_beam_ratio": 0.35,
      "min_retained_beam_ratio": 0.55,
      "max_floor_hit_risk_beam_ratio": 0.05
    },
    "passthrough_scan_count": 820,
    "compensated_scan_count": 140,
    "dropped_scan_count": 25,
    "rejected_beam_count": 1200,
    "retained_beam_ratio": 0.72,
    "rejected_beam_ratio": 0.18,
    "max_vertical_projection_error_m": 0.12,
    "mean_vertical_projection_error_m": 0.03,
    "max_compensated_tilt_deg": 7.8,
    "floor_hit_rejected_count": 300,
    "false_wall_risk_ok": true,
    "hard_tilt_dropped": true
  },
  "baseline_comparison": {
    "baseline_mode": "p10_drop_only",
    "candidate_mode": "bounded_2d_projection",
    "baseline_validated_scan_count": 900,
    "candidate_validated_scan_count": 960,
    "baseline_validated_scan_rate_hz": 6.1,
    "candidate_validated_scan_rate_hz": 7.4,
    "scan_availability_improved": true,
    "slam_health_regressed": false
  },
  "slam": {
    "odom_healthy": true,
    "map_growth_ok": true
  },
  "owner": {
    "unique": true,
    "competing_publishers": []
  },
  "truth_control": {
    "set_pose_count": 0,
    "gazebo_truth_as_input": false
  }
}
```

## 11. 和后续阶段的关系

P11 通过后只能说明：

- 2D lidar 在中等倾角下有一个可控、可解释、可回放的 stabilization 方案。
- P9 representative replay 强度下，P11 candidate 没有比 P10 drop-only baseline 更差。
- P11 没有把 hard tilt 或 floor-hit risk 强行投影成墙。

P11 不说明：

- 2D projection 在所有真实环境都物理正确。
- 飞机可以频繁大角度高速机动。
- 电机/ESC/桨叶偏置已经建模。
- 主动 frontier 探索策略已经最优或能覆盖完整 maze。
- 3D 障碍、透明/反光材质、动态物体已经解决。

后续建议：

- P12：motor bias / ESC lag / thrust multiplier / vibration 鲁棒性仿真，验证更真实的姿态扰动来源下 P11 水平复原仍安全。
- P13：恢复 active frontier exploration strategy 优化，让探索走得更远、更稳。
- P14：真机 tethered indoor preflight，先在保护/限位下验证 hover + scan integrity + stabilization，再考虑 active frontier。

## Runtime Mode 分流

- `docker + simulation`：保持当前 P11 bounded 2D compensation + P9 representative replay 验收路径。
- `process + real`：只允许真实 `/scan` 和真实 attitude source 进入 stabilization 检查，不启动 P9 replay、official maze overlay、Gazebo/SITL 或 gazebo-sensor。
- real mode 下如果代码路径试图使用 simulation-only replay/source/overlay，必须以 `runtime_mode_violation:*` blocker 失败。
- P11 real mode 不再用官方 maze 作为任何输入；official maze 只能留在 simulation/Foxglove review 语义里。
- P11 首版 real mode 的目标是边界隔离和真实 source claim 审计；完整真实 flight stabilization gate 后续基于 real-preflight topic contract 扩展。
