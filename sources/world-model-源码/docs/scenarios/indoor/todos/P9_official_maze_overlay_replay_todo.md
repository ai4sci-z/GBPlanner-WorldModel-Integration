# P9 官方 maze 底图叠加与 Foxglove-lite 回放 TODO

## 目标

在 P8 官方 maze 探索任务已经通过后，生成一个更适合 Foxglove 查看和上传的 replay artifact：以官方 `maze.sdf` 的真实墙体作为 1:1 可视化底图，叠加 SLAM `/map`、`/scan`、轨迹和 exploration 状态，并输出轻量 `rosbag_foxglove/rosbag_foxglove_0.mcap`。

设计文档：

- `docs/scenarios/indoor/navlab_p9_official_maze_overlay_replay_design.md`

前置文档：

- `docs/scenarios/indoor/navlab_master_roadmap.md`
- `docs/scenarios/indoor/todos/P8_official_maze_exploration_todo.md` 已通过。

## P9.0 文档和边界

任务：

- [x] 新增 P9 设计文档。
- [x] 新增 P9 TODO 文档。
- [x] 在 `docs/README.md` 中加入 P9 design / TODO 入口。
- [x] 在 master roadmap 中把 P9 定义为官方 maze 底图叠加与 Foxglove-lite 回放。
- [x] 文档明确 P9 不缩放官方 maze 坐标。
- [x] 文档明确 P9 采用裁剪而不是物理缩小。
- [x] 文档明确官方底图是 visualization-only。
- [x] 文档明确官方底图不进入 SLAM、planning、ExternalNav 或控制输入。
- [x] 文档明确 P9 不代表 NavLab world/model 迁移完成。
- [x] 文档明确 P9 应优先使用 representative exploration replay run，而不是最小 P8 gate run。
- [x] 文档明确 replay profile 可以走快一点、走远一点，但不能放松 safety/truth/owner 边界。

验收：

- [x] P9 文档中没有把官方底图当作规划或控制输入。
- [x] P9 文档中没有要求缩小 Gazebo 物理 world。
- [x] P9 文档中明确 Foxglove-lite MCAP 和 raw acceptance MCAP 的区别。
- [x] P9 文档中明确 `p8_acceptance` 和 `p8_replay` 的区别。

## P9.1 官方 maze 解析器

任务：

- [x] 新增官方 `maze.sdf` 解析模块或脚本。
- [x] 支持从默认 `/home/nn/workspace/3588/ardupilot_gz/ardupilot_gz_gazebo/worlds/maze.sdf` 读取。
- [x] 支持通过 CLI 覆盖 maze path。
- [x] 解析 wall box 的 pose、size 和 yaw。
- [x] 计算官方 maze extent。
- [x] 记录 wall count 和 source hash。
- [x] 解析失败时给出明确 blocker。

验收：

- [x] 能解析官方 maze wall boxes。
- [x] extent 与当前官方 maze 约 `20.2m x 20.2m` 一致。
- [x] 解析结果不依赖 Gazebo runtime truth topic。

## P9.2 官方底图生成

任务：

- [x] 将 wall boxes 栅格化为 `nav_msgs/msg/OccupancyGrid`。
- [x] topic 固定为 `/navlab/official_maze/map`。
- [x] `header.frame_id` 固定为 `map`。
- [x] 默认 resolution 为 `0.05m` 或 `0.10m`。
- [x] wall cell 写为 `100`。
- [x] 非墙区域默认写为 `-1`，避免误标 free space。
- [x] 记录底图 origin、width、height、resolution 和 occupied cell count。
- [x] 可选生成 `/navlab/official_maze/walls` MarkerArray 明确延期；P9 使用 `/navlab/official_maze/map` OccupancyGrid 作为官方墙体底图，MarkerArray 不作为 P9 完成标准。

验收：

- [x] 生成的 official maze map 非空。
- [x] 底图 scale 为 `1.0`。
- [x] 底图坐标能与 SLAM `/map` 叠加。
- [x] 不需要 Gazebo mesh 才能看见官方墙体。

## P9.3 自动裁剪窗口

任务：

- [x] 从 raw MCAP 读取 SLAM `/map` known cells bbox。
- [x] 从 `/slam/odom` 或 `/external_nav/odom` 读取 trajectory bbox。
- [x] 默认裁剪窗口为 SLAM bbox 与 trajectory bbox 的 union。
- [x] 默认 margin 配置为 `3m` 到 `5m`。
- [x] SLAM bbox 不可用时 fallback 到 start pose 周围固定窗口。
- [x] 支持 `--bbox xmin,ymin,xmax,ymax`。
- [x] 支持 `--full` 生成完整官方 maze 底图。
- [x] summary 记录 crop mode、margin 和 bbox。

验收：

- [x] 默认输出不是完整官方 maze，除非显式 `--full`。
- [x] 裁剪窗口覆盖无人机轨迹。
- [x] 裁剪窗口覆盖已知 SLAM map 区域。
- [x] 裁剪不会改变地图比例。

## P9.4 Representative exploration replay profile

任务：

- [x] 新增或固化 `p8_replay` / extended exploration 配置。
- [x] 保留 `p8_acceptance` 的保守 gate 参数，不把最小验收直接改成激进长距离飞行。
- [x] conservative replay 默认建议 `exploration_window_sec=50.0`。
- [x] conservative replay 默认建议 `forward_probe_window_sec=4.0`。
- [x] conservative replay 默认建议 `stop_hold_window_sec=2.5`。
- [x] conservative replay 默认建议 `motion_speed_mps=0.18`。
- [x] conservative replay 默认建议 `min_accepted_goals=5`。
- [x] conservative replay 默认建议 `min_path_length_m=2.5`。
- [x] 可选展示档支持 `motion_speed_mps=0.25`、`min_path_length_m=5.0`。
- [x] 默认不使用 `motion_speed_mps >= 0.35`。
- [x] replay run 仍然保持 `uses_gazebo_truth_as_input=false`。
- [x] replay run 仍然保持 `owner.unique=true`、`set_pose_count=0`。
- [x] replay run 仍然执行 clearance、stop drift、SLAM、ExternalNav 和 FCU health gate。
- [x] summary 记录 replay profile 名称和参数。

验收：

- [x] 代表性 replay run 的 `path_length_m >= 2.5m`。
- [x] 代表性 replay run 的 `accepted_goals >= 5`。
- [x] 代表性 replay run 的 coverage/map growth 有明确增长。
- [x] 代表性 replay run 不碰撞、不 stuck。
- [x] 代表性 replay run 的 stop drift 仍在 P8 阈值内。
- [x] 如果输入只是最小 P8 gate run，P9 summary 标记 `minimal_run` 或 `insufficient_path_length`。

## P9.5 Foxglove-lite MCAP 生成脚本

任务：

- [x] 新增 `scripts/build_foxglove_replay_mcap.py`。
- [x] CLI 支持可选 run id，默认使用最新 run。
- [x] 输入 raw `rosbag/rosbag_0.mcap`。
- [x] 输出 `rosbag_foxglove/rosbag_foxglove_0.mcap`。
- [x] 写入 `/navlab/official_maze/map`。
- [x] 保留 Foxglove-lite required topics。
- [x] 对可视化高频 topic 做 downsample。
- [x] 默认丢弃 `/imu` 高频全量数据。
- [x] 默认丢弃或低频采样 `/clock`。
- [x] 写出 `foxglove_replay_summary.json`。

验收：

- [x] 脚本可对最新 P8 run 执行。
- [x] 输出 MCAP 存在且非空。
- [x] 输出 MCAP 包含 `/navlab/official_maze/map`。
- [x] 输出 MCAP required topics 全部存在。
- [x] 输出 MCAP 明显小于 raw MCAP，或 summary 解释原因。

## P9.6 Topic profile 和 downsample 策略

任务：

- [x] 新增 `docker/profiles/navlab-exploration-foxglove-lite-topics.txt`。
- [x] topic profile 使用显式 `overlay`、`required`、`optional`、`drop` 配置，不在脚本中硬编码 required/retained/downsample/drop 列表。
- [x] topic profile 缺失、格式错误或缺少 overlay/required/drop 时直接报错，不做静默 fallback。
- [x] required topics 包含 `/tf`、`/tf_static`。
- [x] required topics 包含 `/map`、`/scan`。
- [x] required topics 包含 `/slam/odom`；`/external_nav/odom` 作为 optional diagnostics，存在时保留。
- [x] required topics 包含 `/navlab/official_maze/map`。
- [x] required topics 包含 `/navlab/exploration/status`、`/navlab/exploration/goal`、`/navlab/exploration/coverage`。
- [x] required topics 包含 `/navlab/fcu/controller/status`、`/navlab/fcu/setpoint/intent`、`/navlab/fcu/setpoint/output`。
- [x] 定义 `/scan`、odom、map、status topic 的默认 downsample 频率。
- [x] 明确 `/imu`、`/clock`、`/odometry`、`/submap_list`、`/trajectory_node_list` 的默认处理策略。

验收：

- [x] profile 能被 replay 脚本读取。
- [x] profile 缺失时 replay 脚本不会使用内置 fallback。
- [x] profile 不把 raw acceptance required topics 全部照搬到 Foxglove-lite。
- [x] downsample 策略不破坏肉眼回放理解。

## P9.7 上传脚本集成

任务：

- [x] `scripts/upload_foxglove_mcap.py` 默认选择 raw/full `rosbag/rosbag_0.mcap`。
- [x] 上传附件包含 `summary.json`。
- [x] 上传附件包含 `foxglove_replay_summary.json`，如果存在。
- [x] `just foxglove-upload` 默认上传最新 run 的 raw/full MCAP；传 `--lite` 时上传 Foxglove-lite MCAP。
- [x] 如果传 `--lite` 且 Foxglove-lite MCAP 不存在，上传脚本 warn 并自动调用 P9 replay 生成命令。
- [x] dry-run 输出明确当前选择的是 `rosbag_foxglove` 还是 raw `rosbag`。

验收：

- [x] 只有传 `--lite` 时才选择 `rosbag_foxglove`，不传时保持 raw/full。
- [x] 传 `--lite` 但不存在 `rosbag_foxglove` 时会自动生成，生成失败才报错。
- [x] dry-run 能显示 MCAP source、summary attachment 和 replay summary attachment。

## P9.8 Summary 和 blocker

任务：

- [x] 写出 `foxglove_replay_summary.json`。
- [x] summary 记录 P8 prerequisite。
- [x] summary 记录 replay profile、path length、accepted goals 和 replay quality。
- [x] summary 记录 official maze source、hash、wall count 和 extent。
- [x] summary 记录 overlay topic、frame、resolution 和 scale。
- [x] summary 记录 crop mode、margin 和 bbox。
- [x] summary 记录 raw/output MCAP size 和 size reduction ratio。
- [x] summary 记录 retained、dropped、downsampled topics。
- [x] summary 记录 `uses_official_maze_as_input=false`。
- [x] summary 记录 `official_maze_layer_role=visualization_only`。
- [x] blocker 写入缺文件、解析失败、topic 缺失、bbox 非法和输出失败。

验收：

- [x] `ok=true` 时 summary 足够复现 replay 生成过程。
- [x] `blocked=true` 时 blockers 可直接定位原因。
- [x] summary 明确 P9 不重新声明 P8 exploration completion。
- [x] summary 能区分 `publishable` 和 `minimal_run` replay quality。

## P9.9 测试

任务：

- [x] 增加 maze parser 单元测试。
- [x] 增加 rasterization 单元测试。
- [x] 增加 crop bbox 单元测试。
- [x] 增加 profile 加载测试。
- [x] 增加 upload selection 测试：默认选择 raw/full，传 `--lite` 时选择 `rosbag_foxglove`。
- [x] 增加 upload selection 测试：传 `--lite` 时会调用 replay builder 自动生成 lite。
- [x] 增加 summary schema 测试。
- [x] 增加 replay quality 测试：path length / accepted goals 不足时标记 minimal。
- [x] 增加 replay profile 测试：extended 参数不会放松 safety/truth/owner gate。
- [x] 增加 smoke test：对一个已有 P8 run dry-run 生成 summary。

验收：

- [x] P9 相关单元测试通过。
- [x] 不影响 P8 exploration gate 测试。
- [x] 不影响 upload 脚本 dry-run。

## P9.10 执行顺序

建议顺序：

1. P9.1 官方 maze 解析器。
2. P9.2 官方底图生成。
3. P9.3 自动裁剪窗口。
4. P9.4 Representative exploration replay profile。
5. P9.6 Topic profile 和 downsample 策略。
6. P9.5 Foxglove-lite MCAP 生成脚本。
7. P9.8 Summary 和 blocker。
8. P9.7 上传脚本集成。
9. P9.9 测试。
10. 跑一段 representative P8 replay，再生成 Foxglove-lite MCAP 并 dry-run 上传。

## P9 完成标准

P9 全部完成必须满足：

- [x] P9 replay 脚本可默认选择最新 P8 run。
- [x] P8 prerequisite `ok == true`。
- [x] 输入 run 满足 representative replay quality，或明确标记为 minimal/demo-only。
- [x] publishable replay artifact 满足 `path_length_m >= 2.5m`。
- [x] publishable replay artifact 满足 `accepted_goals >= 5`。
- [x] 官方 `maze.sdf` 解析成功。
- [x] `/navlab/official_maze/map` 生成成功。
- [x] official maze map 使用 `map` frame。
- [x] official maze map scale 为 `1.0`。
- [x] 默认使用自动裁剪窗口。
- [x] 输出 `rosbag_foxglove/rosbag_foxglove_0.mcap`。
- [x] Foxglove-lite required topics 全部存在。
- [x] 输出 MCAP 小于 raw acceptance MCAP，或有明确解释。
- [x] 上传脚本默认选择 raw/full MCAP，并支持 `--lite` 显式选择 Foxglove-lite MCAP。
- [x] `uses_official_maze_as_input == false`。
- [x] `uses_gazebo_truth_as_input == false`。
- [x] `official_maze_layer_role == visualization_only`。
- [x] Foxglove 中能直观看到官方墙体、SLAM `/map`、scan 和轨迹叠加。

## 验证记录

### 2026-06-07 P9 文档初始化

- 命令：未运行代码测试，纯文档初始化。
- 结果：新增 P9 设计文档和 TODO 文档，并把 P9 加入 README 和 master roadmap。
- blocker：representative replay profile 尚未实现为独立 P8 run 配置；source hash、MarkerArray、部分 fallback 测试仍待补。
- 备注：P9.0 文档和边界已完成；后续从 P9.1 官方 maze 解析器、P9.2 官方底图生成和 P9.4 representative replay profile 开始实现。


### 2026-06-07 P9 overlay/lite MCAP 第一版实现

- 命令：`PYTHONPATH=orchestration uv run --project orchestration pytest orchestration/tests/test_p9_foxglove_replay.py -q`
- 结果：6 passed
- 命令：`uv run --project orchestration python scripts/build_foxglove_replay_mcap.py`
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260607_185314/rosbag_foxglove/rosbag_foxglove_0.mcap`
- 结果：生成 Foxglove-lite MCAP，包含 `/navlab/official_maze/map`，required topics 全部存在。
- 体积：raw MCAP 645,955,898 bytes；lite MCAP 1,647,374 bytes；size reduction ratio 392.1x。
- overlay：官方 maze wall_count=14，extent≈20.2m x 20.2m，crop bbox=`[-5.15,-5.14,10.1,10.1]`，resolution=0.1m，occupied_cells=1711。
- replay quality：当前输入 run 为 `minimal_run`，path_length=0.960m，accepted_goals=3，未达到 publishable replay 阈值；后续仍需跑 representative replay profile。
- upload dry-run：历史默认曾选择 `rosbag_foxglove/rosbag_foxglove_0.mcap`；当前上传脚本已改为默认 raw/full，`--lite` 才选择 lite。

### 2026-06-07 P9 representative replay 端到端验证

- representative replay 命令：`just navlab-exploration-replay 180`
- representative artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260607_193218`
- replay 结果：`ok=true`，`blocked=false`，`blockers=[]`，`replay_profile=conservative`。
- replay 质量：`path_length_m=3.026`，`accepted_goals=5`，`known_cell_growth=13430`，`estimated_explored_area_m2=70.783`。
- safety/truth/owner：`min_scan_clearance_m=0.894`，`stop_drift_m=0.100`，`uses_gazebo_truth_as_input=false`，`owner.unique=true`，`set_pose_count=0`。
- Foxglove-lite 生成命令：`just foxglove-replay 20260607_193218`
- Foxglove-lite artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260607_193218/rosbag_foxglove/rosbag_foxglove_0.mcap`
- Foxglove-lite summary：`ok=true`，`blocked=false`，`missing_topics=[]`，`publishable=true`。
- 体积：raw MCAP 776,370,879 bytes；lite MCAP 2,070,499 bytes；size reduction ratio 374.97x。
- overlay：`/navlab/official_maze/map`，frame=`map`，scale=`1.0`，resolution=`0.1m`，width=`154`，height=`153`，occupied_cells=`1713`。
- 官方 maze：wall_count=`14`，extent=`[-10.1,-10.1,10.1,10.1]`，sha256=`3c72f73aef4cce0bcde73b87beed09d58fc7078c30a9e0ca58f49d7994c67ce1`。
- topic 内容校验：lite MCAP 包含 `/tf`、`/tf_static`、`/map`、`/scan`、`/slam/odom`、`/navlab/official_maze/map`、`/navlab/exploration/*`、`/navlab/fcu/*`、`/navlab/motion/status`、`/rangefinder/down/range`。
- 默认 run 校验：`just foxglove-replay-dry-run` 与 `scripts/upload_foxglove_mcap.py --dry-run` 默认选择最新 run `20260607_193218`。
- upload dry-run：当前应使用 `scripts/upload_foxglove_mcap.py --dry-run --lite` 验证 lite 选择，并附带 `summary.json` 与 `foxglove_replay_summary.json`。
- 测试：`PYTHONPATH=orchestration uv run --project orchestration pytest orchestration/tests/test_config.py orchestration/tests/test_p9_foxglove_replay.py -q` -> 71 passed。
- diff 检查：`git diff --check` -> passed。
- blocker：无；真实 Foxglove 远端上传和人工视觉确认未在本次 CLI 验证中执行。

### 2026-06-07 P9 Foxglove-lite topic profile 完全配置化

- 变更：`docker/profiles/navlab-exploration-foxglove-lite-topics.txt` 改为显式 `overlay`、`required`、`optional`、`drop` profile。
- 变更：`scripts/build_foxglove_replay_mcap.py` 从 profile 读取 overlay topic、required topic、retained/downsample interval 和 explicit drop topic。
- 变更：移除静默 fallback；profile 缺失、格式错误、缺少 overlay/required/drop 会直接报错。
- 重新生成：`just foxglove-replay 20260607_193218` -> `ok=true`，`missing_topics=[]`。
- summary 新增：`topic_profile`、`retained_topics`、`configured_drop_topics`。
- dry-run：`just foxglove-replay-dry-run` -> latest run `20260607_193218` 通过。
- upload dry-run：`scripts/upload_foxglove_mcap.py --dry-run --lite` -> 选择 `rosbag_foxglove`，附件包含 replay summary；不带 `--lite` 时选择 raw/full。
- 测试：`PYTHONPATH=orchestration uv run --project orchestration pytest orchestration/tests/test_config.py orchestration/tests/test_p9_foxglove_replay.py -q` -> 73 passed。
- diff 检查：`git diff --check` -> passed。

### 2026-06-07 Foxglove upload raw/full 与 lite 显式选择

- 变更：`scripts/upload_foxglove_mcap.py` 从 argparse 改为 Typer CLI。
- 变更：不带 `--lite` 时默认上传 raw/full `rosbag/rosbag_0.mcap`。
- 变更：传 `--lite` 时上传 `rosbag_foxglove/rosbag_foxglove_0.mcap`；如果 lite 不存在，先 warn 并自动调用 `scripts/build_foxglove_replay_mcap.py <run_dir>` 生成。
- just：`just foxglove-upload --lite --dry-run` 可直接对 latest run 选择 lite；`just foxglove-upload <run_id> --lite` 可指定 run。
- dry-run full：`scripts/upload_foxglove_mcap.py 20260607_193218 --dry-run` -> source=`rosbag/rosbag_0.mcap`。
- dry-run lite：`scripts/upload_foxglove_mcap.py 20260607_193218 --dry-run --lite` -> source=`rosbag_foxglove/rosbag_foxglove_0.mcap`。

### 2026-06-07 P9 display replay profile

- 变更：新增 replay profile `display`，不替代 conservative replay。
- 参数：`exploration_window_sec=90.0`，`forward_probe_window_sec=5.0`，`stop_hold_window_sec=2.0`，`final_hold_window_sec=12.0`，`motion_speed_mps=0.25`，`min_accepted_goals=7`，`min_path_length_m=5.0`。
- 边界：仍沿用 P8 safety/truth/owner gate，不放松 `min_clearance_m`、`max_stop_drift_m`、`uses_gazebo_truth_as_input=false`、setpoint owner 和 claim。
- 命令：`just navlab-exploration-display-replay 240`。
- 测试：增加 display profile 配置测试，确认走得更远但不放松 safety/truth/owner contract。

### 2026-06-07 P9 display replay 实跑通过

- 备注：此记录来自 3D lidar / static fallback 问题修复前，只保留为历史记录；P9 最终验收以 2026-06-08 真实 Gazebo `/lidar` replay 记录为准。
- 命令：`just navlab-exploration-display-replay 240`
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260607_223132`
- 结果：`ok=true`，`blocked=false`，`blockers=[]`，`replay_profile=display`。
- replay 质量：`path_length_m=6.738`，`accepted_goals=6`，`known_cell_growth=21530`，`estimated_explored_area_m2=90.753`。
- safety/truth/owner：`min_scan_clearance_m=0.894`，`stop_drift_m=0.146`，`final_drift_m=0.021`，`uses_gazebo_truth_as_input=false`，`owner.unique=true`，`set_pose_count=0`。
- 管线健康：SLAM odom `50.5Hz`，ExternalNav `62.7Hz`，FCU local position `17.5Hz`。
- 说明：run 结束后的 `ros2 topic info` 对 `/navlab/exploration/*` 临时 topic 会打印 `Unknown topic`，但 rosbag 和 summary 中对应消息存在，且最终 rc 为 `0`。
- Foxglove-lite：`just foxglove-replay 20260607_223132` -> `ok=true`，`missing_topics=[]`，`replay_quality.profile=p8_replay_display`。
- 体积：raw MCAP 771,009,084 bytes；lite MCAP 2,291,392 bytes；size reduction ratio 336.48x。
- upload dry-run：`scripts/upload_foxglove_mcap.py 20260607_223132 --dry-run --lite` -> source=`rosbag_foxglove/rosbag_foxglove_0.mcap`。
- 测试：`PYTHONPATH=orchestration uv run --project orchestration pytest orchestration/tests/test_config.py orchestration/tests/test_p9_foxglove_replay.py -q` -> 79 passed。

### 2026-06-08 P9 真实 Gazebo lidar display replay 最终验收

- 修正：P9/P8 replay 不再允许 X2 `static_fallback` 圆形 scan 假通过；display replay 必须满足 `/sim/x2/status.scan_source=gazebo_ideal`，且 raw bag 必须录到 `/lidar`。
- 修正：P9/P8 overlay 将官方 `model://lidar_3d` 替换为 `model://lidar_2d` 作为 X2 LaserScan 输入源；官方 maze 底图仍为 visualization-only。
- 修正：P3/P5/P6/P7/P8 rosbag profile 统一将 `/lidar` 和 `/sim/x2/status` 纳入真实 X2 scan contract。
- display 参数：`exploration_window_sec=90.0`，`forward_probe_window_sec=5.0`，`stop_hold_window_sec=2.0`，`final_hold_window_sec=12.0`，`motion_speed_mps=0.25`，`min_accepted_goals=7`，`min_path_length_m=5.0`。
- 命令：`just navlab-exploration-display-replay 240`
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260608_080940`
- 结果：`ok=true`，`blocked=false`，`blockers=[]`，`replay_profile=display`。
- 真实 lidar：`/sim/x2/status.scan_source=gazebo_ideal`，`latest_scan_ideal_age_sec=0.106s`，`/lidar=1095`，`/scan=1258`，`/sim/x2/status=360`。
- replay 质量：`path_length_m=5.458`，`accepted_goals=7`，`known_cell_growth=19504`，`estimated_explored_area_m2=85.308`。
- safety/truth/owner：`min_scan_clearance_m=0.8945`，`stop_drift_m=0.146`，`final_drift_m=0.029`，`uses_gazebo_truth_as_input=false`，`owner.unique=true`，`set_pose_count=0`。
- 管线健康：SLAM odom `36.6Hz`，ExternalNav `68.1Hz`，FCU local position `11.1Hz`。
- rosbag：`ok=true`，`missing_required_topics=[]`，`zero_count_required_topics=[]`。
- 人工 Foxglove 截图确认：`docs/images/截屏2026-06-08 08.25.06.png` 与 `docs/images/截屏2026-06-08 08.25.30.png` 中红色 scan 点贴合官方 maze 墙体，不再是 1.5m static fallback 圆。
- 测试：`PYTHONPATH=orchestration uv run --project orchestration pytest orchestration/tests/test_config.py orchestration/tests/test_p9_foxglove_replay.py -q` -> 82 passed。
- diff 检查：`git diff --check` -> passed。

### 2026-06-14 Foxglove upload 迁入 Go sim

- 变更：Foxglove upload 不再由 `scripts/command foxglove upload` 负责，迁入 `orchestration/sim` 的 Go CLI。
- 新入口：`go run ./cmd/navlab-sim foxglove upload <run> --task <task> --force`。
- just：`just foxglove-upload <run> --task <task> --dry-run` 现在调用 Go sim。
- raw/full：Go sim 会按 task 选择主 MCAP，例如 P13 navigation 选择 `rosbag/navigation_rosbag/navigation_rosbag_0.mcap`。
- lite：传 `--lite` 时只选择已经存在的 `rosbag_foxglove/rosbag_foxglove_0.mcap`；缺文件直接失败，不再自动生成。
- 边界：Go sim upload 只认 `artifacts/sim/<task>/<run>` 和当前分层 rosbag 布局，不再兼容旧 `artifacts/ros/...` 或 `rosbag/rosbag_0.mcap`。
- 验证：`just foxglove-upload 20260614T093531Z --task navigation --dry-run` 选择 navigation MCAP。
- 验证：旧 `artifacts/ros/navlab_companion_sitl_gazebo/20260609_110400` 路径会被拒绝。
