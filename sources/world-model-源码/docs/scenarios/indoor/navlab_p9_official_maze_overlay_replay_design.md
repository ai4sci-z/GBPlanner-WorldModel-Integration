# P9 官方 maze 底图叠加与 Foxglove-lite 回放设计

## 1. 目标

P9 的目标是在 P8 官方 maze 探索任务已经通过后，把“能跑”和“能看懂”分开：

```text
P8 representative replay run
  -> raw MCAP + summary
  -> 解析官方 maze.sdf 真实墙体
  -> 生成 1:1 官方 2D 底图
  -> 裁剪到 SLAM/轨迹附近的局部窗口
  -> 叠加 SLAM /map、/scan、轨迹和探索状态
  -> 输出 Foxglove-lite MCAP
  -> 上传 Foxglove 作为可读、轻量、可对照的 replay artifact
```

P9 只回答：

> 能否用一段有代表性的 P8 exploration replay run，把官方 `maze.sdf` 的真实墙体作为只读可视化底图，与 SLAM map、scan、轨迹和任务状态叠加到同一 `map` frame 下，并生成比 raw acceptance bag 小得多的 Foxglove 回放包？

P9 通过后，操作者应该能在 Foxglove 里直接判断：

- 哪些黑墙是真实官方墙体。
- 哪些 SLAM `/map` 边界只是 free-space clearing 或 unknown boundary。
- 无人机实际探索了官方 maze 的哪一段，而不是只看最小 gate 的短距离移动。
- P8 exploration 的 goal/action/safety 发生在哪些真实墙体附近。

## 2. 为什么 P9 必须单独做

P8 已经证明官方 maze 中可以完成 bounded exploration task，但直接拿最小 P8 gate artifact 做展示有三个问题：

- **可读性问题**：单看 `/map` 容易把 SLAM free-space 边界误认为真实墙；看 Gazebo mesh 又太重、视角不稳定。
- **代表性问题**：最小 P8 gate 更关注安全闭环，默认速度和窗口保守，可能只移动不到 1m，叠到底图上不容易看出探索能力。
- **文件体积问题**：raw acceptance bag 为了验收会录 `/imu`、`/clock`、`/odometry` 等高频 topic，上传和远程回放成本很高。

最新 P8 示例中，raw MCAP 大约 608 MiB，主要消息量来自：

```text
/imu      > 1.5M messages
/clock    > 100k messages
/tf       > 10k messages
```

而用于 Foxglove 观看探索过程的核心信息其实是：

```text
/tf, /tf_static
/map
/scan
/slam/odom 或 /external_nav/odom
/navlab/exploration/*
/navlab/official_maze/map 或 /navlab/official_maze/walls
```

因此 P9 不应该把最小 P8 acceptance gate 改成很激进的长距离飞行，也不应该要求完整录完整个 maze。P9 应该引入一个单独的 representative replay profile：在保持 P8 安全边界的前提下，让飞机走得更远一点，然后再做可视化后处理和轻量回放包。

## 3. P9 范围

P9 包含：

- 解析官方 `ardupilot_gz_gazebo/worlds/maze.sdf` 的墙体几何。
- 生成 1:1 比例的官方 maze 2D 底图。
- 底图使用 `map` frame，不引入缩放坐标系。
- 支持按 SLAM known bbox、轨迹 bbox 或显式 bbox 裁剪官方底图。
- 生成 Foxglove 可显示的 `nav_msgs/OccupancyGrid` 底图 topic。
- 可选生成 `visualization_msgs/MarkerArray` 墙体轮廓 topic。
- 定义代表性 exploration replay profile，用于生成更有解释力的 P9 输入 run。
- 从 raw MCAP 生成 `rosbag_foxglove/rosbag_foxglove_0.mcap`。
- Foxglove-lite MCAP 只保留可视化和诊断必要 topic。
- Go sim `foxglove build-replay` 负责生成 lite MCAP；`foxglove upload` 只允许上传已经通过 topic 校验的 lite MCAP。
- 写出 `foxglove_replay_summary.json`，记录输入、输出、裁剪窗口、topic 和大小。

P9 不包含：

- 不把官方 maze 底图作为 SLAM、planning、ExternalNav 或控制输入。
- 不把 Gazebo truth 作为 exploration 策略输入。
- 不缩放物理 world，不改变 Gazebo maze 尺寸。
- 不替换 NavLab 8 字形 world/model。
- 不重新评价最小 P8 acceptance gate 是否通过。
- 不要求完整覆盖官方 maze。
- 不为了好看而放松 clearance、stop drift、owner 或 truth-input 安全约束。
- 不把 Foxglove-lite MCAP 当作 raw acceptance 证据的唯一来源。

## 4. 关键设计决定

### 4.1 官方底图保持 1:1，不做比例缩小

官方 maze 真实范围约为：

```text
x: -10.1m ~ 10.1m
y: -10.1m ~ 10.1m
size: 20.2m x 20.2m
```

无人机移动速度慢时，完整 maze 看起来会显得很大。但不能通过缩放底图解决，因为：

- SLAM `/map`、TF、轨迹和 scan 都使用真实米制坐标。
- OccupancyGrid 和 TF 没有“只缩放显示、不缩放坐标”的安全语义。
- 缩小官方底图会导致真实墙体与 SLAM map 错位，反而误导调试。

P9 采用：

```text
保持真实比例 + 自动裁剪局部窗口 + Foxglove 视图配置
```

### 4.2 裁剪优先于缩放

默认裁剪窗口来自：

```text
bbox = union(SLAM known cells bbox, odom/trajectory bbox) + margin
```

建议默认 margin：

```text
3m ~ 5m
```

如果 SLAM map 太小或 bbox 不可用，则 fallback 到：

```text
start pose 周围 10m x 10m
```

允许显式 override：

```text
--bbox xmin,ymin,xmax,ymax
--margin 4.0
--full
```

但默认上传应该使用 auto crop，避免 Foxglove 里出现“巨大官方 maze + 小小一段飞行”的阅读负担。

### 4.3 官方底图是 diagnostic-only visualization

P9 生成的官方底图必须满足：

```text
source = official_maze_sdf
role = visualization_only
used_as_slam_input = false
used_as_planning_input = false
used_as_control_input = false
```

P9 summary 必须显式记录：

```json
{
  "uses_official_maze_as_input": false,
  "uses_gazebo_truth_as_input": false,
  "official_maze_layer_role": "visualization_only"
}
```

### 4.4 P9 使用 representative replay run，而不是最小 gate run

P8 acceptance profile 和 P9 replay profile 的目标不同：

```text
p8_acceptance:
  short, conservative, gate-focused
  目标是证明 hover + motion + exploration 闭环安全成立

p8_replay:
  longer, moderately faster, visualization-focused
  目标是在不放松安全边界的前提下覆盖更多局部 maze
```

P9 默认应该优先使用 `p8_replay` artifact。如果只输入最小 P8 gate artifact，脚本仍可生成 overlay，但 summary 必须标记 replay quality 为 `minimal_run` 或 `insufficient_path_length`，避免把一小段移动包装成“充分探索”。

建议先使用保守增强档：

```toml
exploration_window_sec = 50.0
forward_probe_window_sec = 4.0
stop_hold_window_sec = 2.5
final_hold_window_sec = 6.0
motion_speed_mps = 0.18
min_accepted_goals = 5
min_path_length_m = 2.5
```

如果保守增强档通过，再使用展示档：

```toml
exploration_window_sec = 90.0
forward_probe_window_sec = 5.0
stop_hold_window_sec = 2.0
final_hold_window_sec = 12.0
motion_speed_mps = 0.25
min_accepted_goals = 7
min_path_length_m = 5.0
```

对应命令：

```bash
just navlab-exploration-display-replay 240
```

展示档只用于生成更适合截图和 Foxglove demo 的 replay artifact，不替代 P8 acceptance，也不放松 truth、owner、clearance、stop drift、SLAM、ExternalNav 或 FCU health gate。

暂不建议默认超过：

```text
motion_speed_mps >= 0.35
```

原因是官方 maze 走廊宽度有限，速度过快会同时放大 SLAM 滞后、ExternalNav 延迟、刹车漂移和 scan clearance 触发延迟。P9 的代表性 replay 应该优先追求“更大局部覆盖 + 可解释安全余量”，而不是一次冲完整个 maze。

P9 replay quality 推荐阈值：

```text
path_length_m >= 2.5m   # conservative publishable
accepted_goals >= 5
known_cell_growth > 0 或 estimated_explored_area_m2 增长明确
min_scan_clearance_m >= P8 threshold
stop_drift_m <= P8 threshold
```

这些阈值只决定 replay artifact 是否适合发布/上传，不替代 P8 acceptance 的通过条件。

## 5. 目标架构

```text
P8 representative replay run artifact
  artifacts/ros/navlab_companion_sitl_gazebo/<run_id>/
    rosbag/rosbag_0.mcap
    summary.json
    p8_slam_runtime.toml
    p8_exploration_gate_runtime.toml

P8 replay profile
  p8_acceptance remains conservative
  p8_replay increases duration/speed/goals within safety bounds

Official maze source
  /home/nn/workspace/3588/ardupilot_gz/.../worlds/maze.sdf

P9 postprocess
  navlab-sim foxglove build-replay <run_id> --task <task>
    -> read raw MCAP metadata/topics with Foxglove's Go MCAP library
    -> require the runtime-published /navlab/official_maze/map topic
    -> filter/downsample replay topics
    -> write rosbag_foxglove/rosbag_foxglove_0.mcap
    -> write foxglove_replay_summary.json

Foxglove upload
  navlab-sim foxglove upload <run_id> --task <task> --force
    -> upload an existing rosbag_foxglove/rosbag_foxglove_0.mcap
    -> attach summary.json and foxglove_replay_summary.json
    -> fail if overlay + required topics are missing
```

## 6. Topic 设计

### 6.1 官方底图 topic

首选 topic：

```text
/navlab/official_maze/map
```

消息类型：

```text
nav_msgs/msg/OccupancyGrid
```

字段约定：

```text
header.frame_id = "map"
info.resolution = 0.05 或 0.10
occupied wall cell = 100
unknown / non-wall cell = -1
```

说明：底图不负责表达 free space，只负责表达官方墙体。非墙区域用 unknown 可以避免操作者误以为官方底图给出了可通行空间答案。

### 6.2 可选墙体轮廓 topic

可选 topic：

```text
/navlab/official_maze/walls
```

消息类型：

```text
visualization_msgs/msg/MarkerArray
```

用途：

- 显示墙体中心线或 box outline。
- 与 OccupancyGrid 底图互相校验。
- 便于截图和文档说明。

第一版可以只实现 OccupancyGrid，MarkerArray 作为后续增强。

### 6.3 Foxglove-lite required topics

Foxglove-lite MCAP 的 topic contract 来自：

```text
docker/profiles/navlab-exploration-foxglove-lite-topics.txt
```

profile 必须显式声明：

```text
overlay /navlab/official_maze/map
required /tf interval=0.05
optional /external_nav/odom interval=0.05
drop /imu
```

缺少 profile、格式错误、缺少 `overlay`、没有 required topic 或没有 explicit drop topic 都是 fatal error；P9 replay 脚本不使用静默 fallback，避免 topic contract 配错后还生成看似成功的 artifact。

当前 Foxglove-lite MCAP required topics：

```text
/tf
/tf_static
/map
/scan
/slam/odom
/navlab/official_maze/map
/navlab/exploration/status
/navlab/exploration/goal
/navlab/exploration/coverage
/navlab/fcu/controller/status
/navlab/fcu/setpoint/intent
/navlab/fcu/setpoint/output
/navlab/motion/status
/rangefinder/down/range
```

Foxglove-lite optional topics：

```text
/navlab/official_maze/walls
/navlab/exploration/frontiers
/navlab/exploration/path
/navlab/exploration/markers
/navlab/frame_contract/status
/navlab/slam/status
/external_nav/odom
/external_nav/status
/ap/v1/pose/filtered
/ap/v1/twist/filtered
```

默认不保留：

```text
/imu
/clock 高频全量
/odometry 高频全量
/submap_list 高频全量
/trajectory_node_list 高频全量
/ap/v1/time 高频全量
```

如果 Foxglove 回放需要 `/clock`，P9 可以保留低频采样后的 `/clock`，但不能继续全量保留。

## 7. MCAP 体积策略

P9 的目标不是让 raw acceptance bag 变小，而是新增一个上传友好的 replay bag。

建议策略：

- raw acceptance MCAP 保留，用于 gate 证据。
- Foxglove-lite MCAP 只保留观看和诊断需要的 topic。
- 对高频 topic 采用 drop 或 downsample。
- 对 `/map` 保留关键帧，例如 1Hz 或变化时。
- 对 `/scan` 保留 5-10Hz 足够观看。
- 对 odom/trajectory 保留 10-20Hz 足够观看。
- 官方底图只写一次或低频 latched equivalent。

P9 summary 必须记录：

```json
{
  "raw_mcap_size_bytes": 0,
  "foxglove_mcap_size_bytes": 0,
  "size_reduction_ratio": 0.0,
  "dropped_topics": [],
  "downsampled_topics": {},
  "required_topics_present": true
}
```

## 8. Gate 判定

P9 通过必须满足：

- `ok == true`。
- `blocked == false`。
- `blockers == []`。
- 输入 P8 summary 存在且 `ok == true`。
- 输入 run 满足 representative replay quality，或 summary 明确标记为 minimal/demo-only。
- P9 publishable artifact 至少满足 `path_length_m >= 2.5m` 和 `accepted_goals >= 5`。
- 官方 `maze.sdf` 解析成功。
- 官方底图 frame 为 `map`。
- 官方底图与 SLAM `/map` 使用同一米制坐标，不做缩放。
- 裁剪 bbox 有记录且合法。
- `rosbag_foxglove/rosbag_foxglove_0.mcap` 存在且非空。
- Foxglove-lite required topics 全部存在。
- `/navlab/official_maze/map` 存在且非空。
- `uses_official_maze_as_input == false`。
- `uses_gazebo_truth_as_input == false`。
- 输出 MCAP 小于 raw MCAP，或 summary 明确解释无法缩小的原因。
- Go sim upload command 拒绝 raw/full MCAP；只能上传已经存在且通过 `overlay + required` topic 校验的 Foxglove-lite MCAP。

P9 阻塞条件示例：

```text
P8 summary missing or failed
representative replay quality below threshold
official maze.sdf missing
official maze parse failed
crop bbox invalid
official maze map missing in foxglove mcap
required replay topic missing
official maze layer used as planning input
foxglove mcap not generated
upload script selected lite unexpectedly without --lite, or failed to generate lite when --lite was requested
```

## 9. Summary schema

P9 summary 建议写入：

```json
{
  "ok": true,
  "blocked": false,
  "blockers": [],
  "run_id": "20260607_174705",
  "p8_prerequisite": {
    "ok": true,
    "summary": "artifacts/.../summary.json"
  },
  "replay_quality": {
    "profile": "p8_replay_conservative",
    "publishable": true,
    "path_length_m": 2.5,
    "accepted_goals": 5,
    "known_cell_growth": 0,
    "estimated_explored_area_m2": 0.0,
    "min_scan_clearance_m": 0.0,
    "stop_drift_m": 0.0,
    "warnings": []
  },
  "official_maze": {
    "source": "/home/nn/workspace/3588/ardupilot_gz/.../maze.sdf",
    "wall_count": 14,
    "extent_m": {
      "xmin": -10.1,
      "xmax": 10.1,
      "ymin": -10.1,
      "ymax": 10.1
    }
  },
  "overlay": {
    "topic": "/navlab/official_maze/map",
    "frame_id": "map",
    "resolution_m": 0.05,
    "scale": 1.0,
    "role": "visualization_only"
  },
  "crop": {
    "mode": "auto_slam_and_trajectory_bbox",
    "margin_m": 4.0,
    "bbox_m": {
      "xmin": 0.0,
      "xmax": 0.0,
      "ymin": 0.0,
      "ymax": 0.0
    }
  },
  "replay_mcap": {
    "path": "artifacts/.../rosbag_foxglove/rosbag_foxglove_0.mcap",
    "raw_mcap_size_bytes": 0,
    "foxglove_mcap_size_bytes": 0,
    "size_reduction_ratio": 0.0,
    "required_topics": [],
    "missing_topics": [],
    "dropped_topics": [],
    "downsampled_topics": {}
  },
  "truth_boundary": {
    "uses_official_maze_as_input": false,
    "uses_gazebo_truth_as_input": false,
    "official_maze_layer_role": "visualization_only"
  }
}
```

## 10. 和后续阶段的关系

P9 通过后只能说明：

- 一段有代表性的 P8 exploration replay 能用官方真实墙体底图解释。
- Foxglove 回放包比 raw acceptance bag 更适合上传和分享。
- 官方 maze 底图没有进入 SLAM、planning、ExternalNav 或控制输入。
- 操作者可以区分真实墙体、SLAM 占用栅格和 free-space 边界。

P9 不说明：

- NavLab 8 字形 world/model 已迁移。
- 物理 maze 被缩小或替换。
- P8/P9 replay 覆盖了完整官方 maze。
- 真机部署已经完成。

NavLab world/model 迁移应作为后续 phase 或独立 migration 任务处理。P9 的职责是 replay/visualization artifact，不是改变实验世界。
