# P3 SLAM backend 质量验收 TODO

## 目标

在 P0/P1/P2 已通过的基础上，验收 SLAM backend 是否真正消费 `/scan + /imu + /odometry + TF`，并输出连续、可解释、可诊断的定位结果。

P3 完成后，只能说明 SLAM backend 质量具备进入 ExternalNav hover gate 的基础；不能说明 hover 已完成，也不能说明探索任务已完成。

设计文档：

- `docs/scenarios/indoor/navlab_p3_slam_backend_quality_design.md`

前置条件：

- `docs/scenarios/indoor/todos/P0_official_baseline_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P1_official_maze_x2_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P2_rangefinder_imu_todo.md` 已通过。

总 roadmap：

- `docs/scenarios/indoor/navlab_master_roadmap.md`

## P3.0 文档和边界

任务：

- [x] 新增 P3 设计文档。
- [x] 新增 P3 TODO 文档。
- [x] 在 `docs/README.md` 中加入 P3 design / TODO 入口。
- [x] 在 master roadmap 中把 P3 TODO 从“待建”改成具体文档。
- [x] 文档明确 P3 不代表 hover 完成。
- [x] 文档明确 P3 不代表 ExternalNav 回灌飞控完成。
- [x] 文档明确 Gazebo truth 只能作为诊断对照，不能作为 SLAM 输入。
- [x] 文档明确 Cartographer 是默认 backend，但 backend 必须可替换。

验收：

- [x] P3 文档中没有把 direct set pose 当作允许路径。
- [x] P3 文档中没有把 Gazebo truth 当作 SLAM 定位来源。
- [x] P3 文档中明确 `hover_claim=not_evaluated`。
- [x] P3 文档中明确 `external_nav_claim=not_evaluated`。

## P3.1 SLAM backend registry 和配置

任务：

- [x] 固化 P3 backend registry 使用方式。
- [x] 默认 backend 为 `cartographer`。
- [x] backend 注册项记录 name、image、launch command、input topics、output topics。
- [x] P3 配置支持通过 CLI 或 `orchestration/config.toml` 指定 backend。
- [x] P3 配置支持指定 backend config path。
- [x] P3 配置支持指定 canonical SLAM odom topic，例如 `/slam/odom`。
- [x] summary 记录 backend 名称、镜像、启动命令、配置路径和配置 hash。

验收：

- [x] 未知 backend 名称会给出明确 blocker。
- [x] backend 配置 hash 进入 artifact。
- [x] backend 不是 `cartographer` 时 summary 仍能解释输入/输出契约。
- [x] backend registry 不在 import 阶段实例化重 backend。

## P3.2 Cartographer 默认 backend 对齐

任务：

- [x] 使用 NavLab Cartographer wrapper 作为默认 Cartographer backend。
- [x] 记录 Cartographer Lua 配置路径。
- [x] 记录 Cartographer Lua 配置 hash。
- [x] 确认 Cartographer 消费 `/scan`。
- [x] 确认 Cartographer 消费 `/imu`。
- [x] 确认 Cartographer 消费 `/odometry` 或官方等价 odom input。
- [x] 确认 Cartographer 发布 `/map`。
- [x] 确认 Cartographer 发布 `/submap_list`。
- [x] 确认 Cartographer 发布 `/trajectory_node_list`。

验收：

- [x] `cartographer_node` 运行。
- [x] `cartographer_occupancy_grid_node` 运行。
- [x] `/scan` subscriber 包含 `cartographer_node`。
- [x] `/map` message count 大于 0。
- [x] `/submap_list` message count 大于 0。
- [x] `/trajectory_node_list` message count 大于 0。

## P3.3 输入契约验收

任务：

- [x] 复用或重跑 P1 X2 `/scan` gate。
- [x] 复用或重跑 P2 IMU gate。
- [x] 检查 `/scan` publisher 是 `ydlidar_ros2_driver_node` 或配置指定 X2 vendor-driver 输出。
- [x] 检查 `/scan.header.frame_id`。
- [x] 检查 `/imu.header.frame_id`。
- [x] 检查 `/odometry` message count、frame 和最新消息年龄。
- [x] 检查 `/tf`、`/tf_static` 可解释 `map/odom/base_link/imu_link/base_scan`。
- [x] 检查 Gazebo truth 没有被配置为 SLAM 输入。

验收：

- [x] `/scan` message count 大于 0。
- [x] `/scan` 不是 Gazebo ideal scan 直出。
- [x] `/imu` message count 大于 0。
- [x] `/imu` synthetic fallback 为 false。
- [x] `/odometry` message count 大于 0。
- [x] TF 无 loop、无同 child 多 parent。
- [x] 如果 Gazebo truth 被用作 SLAM 输入，P3 blocked。

## P3.4 canonical SLAM odom 输出

任务：

- [x] 定义 canonical SLAM odom topic，默认 `/slam/odom`。
- [x] 如果 backend 原生不发布 `/slam/odom`，实现 backend wrapper 从 SLAM TF / pose 输出生成。
- [x] wrapper 禁止消费 Gazebo truth。
- [x] wrapper 禁止消费 FCU fused local position。
- [x] summary 记录 `/slam/odom` publisher。
- [x] summary 记录 `/slam/odom` frame_id、child_frame_id。
- [x] summary 记录 `/slam/odom` count、rate、latest age。

验收：

- [x] `/slam/odom` message count 大于 0。
- [x] `/slam/odom` latest age 小于阈值。
- [x] `/slam/odom.header.frame_id` 符合 P3 配置。
- [x] `/slam/odom.child_frame_id` 符合 P3 配置。
- [x] `/slam/odom` publisher 不是 Gazebo truth relay。
- [x] `/slam/odom` publisher 不是 FCU local position relay。

## P3.5 SLAM 质量诊断

任务：

- [x] 采样 `/slam/odom` 短窗轨迹。
- [x] 计算 `slam_odom_rate_hz`。
- [x] 计算 `slam_odom_jump_max_m`。
- [x] 计算 `slam_odom_yaw_jump_max_rad`。
- [x] 计算静止窗口 `stationary_drift_m`。
- [x] 采样 Gazebo truth 诊断轨迹。
- [x] 计算 SLAM 与 Gazebo truth 的诊断误差 mean/p95/max。
- [x] summary 记录所有阈值和实测值。

验收：

- [x] `/slam/odom` rate 大于 P3 最小阈值。
- [x] `/slam/odom` latest age 小于阈值。
- [x] `slam_odom_jump_max_m` 小于阈值。
- [x] `slam_odom_yaw_jump_max_rad` 小于阈值。
- [x] `stationary_drift_m` 小于 P3 宽松阈值。
- [x] Gazebo truth 只出现在 diagnostic 字段，不出现在 SLAM input 字段。

## P3.6 Rosbag 和 Foxglove

任务：

- [x] 新增 P3 rosbag profile。
- [x] required topics 至少包含：
  - `/clock`
  - `/tf`
  - `/tf_static`
  - `/scan`
  - `/imu`
  - `/odometry`
  - `/map`
  - `/submap_list`
  - `/trajectory_node_list`
  - `/slam/odom`
  - `/sim/x2/status`
  - `/rangefinder/down/range`
  - `/rangefinder/down/status`
- [x] optional topics 包含：
  - `/ap/v1/time`
  - `/ap/v1/imu/experimental/data`
  - `/ap/v1/pose/filtered`
  - `/rangefinder/down/scan_ideal`
  - `/navlab/x2/scan_ideal`
  - `/scan_matched_points2`
  - `/constraint_list`
  - `/navlab/slam/status`
  - `/external_nav/status`
- [x] Foxglove notes 说明固定参考系、SLAM odom、map/submap 和 truth 诊断层。
- [x] summary 记录 MCAP 路径。

验收：

- [x] rosbag profile summary 中 required topics 全部存在且 message count 大于 0。
- [x] MCAP 可在 Foxglove 中回放 `/scan`、`/slam/odom`、map、submap、IMU 和 rangefinder。
- [x] P3 summary 记录 `rosbag_profile.ok=true`。

## P3.7 Acceptance task

任务：

- [x] 新增 `navlab-slam-backend-doctor` orchestration task。
- [x] 新增 `navlab-slam-backend-acceptance` orchestration task。
- [x] orchestration CLI 增加同名 task；历史 justfile 便捷入口已回收。
- [x] acceptance 先验证 P0 official DDS baseline。
- [x] acceptance 再验证 P1 X2 scan gate。
- [x] acceptance 再验证 P2 IMU/rangefinder gate。
- [x] acceptance 启动 SLAM backend。
- [x] acceptance 启动 SLAM output/quality probes。
- [x] summary 包含 `p3_slam_backend` section。
- [x] summary 包含 `slam_inputs` section。
- [x] summary 包含 `slam_outputs` section。
- [x] summary 包含 `slam_quality` section。
- [x] summary 包含 `hover_claim` 和 `external_nav_claim`。

验收：

- [x] P0 official DDS 条件失败时，P3 blocked。
- [x] P1 X2 `/scan` 条件失败时，P3 blocked。
- [x] P2 IMU/rangefinder 条件失败时，P3 blocked。
- [x] SLAM backend 启动失败时，P3 blocked。
- [x] SLAM input contract 失败时，P3 blocked。
- [x] SLAM output contract 失败时，P3 blocked。
- [x] SLAM quality 超阈值时，P3 blocked。
- [x] summary 把 P3 SLAM backend 和 P6 hover completion 分开。

## P3.8 测试

任务：

- [x] 增加 config 测试：P3 backend 配置可加载。
- [x] 增加 task registry 测试：P3 doctor/acceptance 已注册。
- [x] 增加 backend registry 测试：默认 Cartographer backend 可创建。
- [x] 增加 rosbag profile 测试：P3 required topics 配置存在。
- [x] 增加 summary schema 测试：`p3_slam_backend` 字段完整。
- [x] 增加 blocker 测试：Gazebo truth 不能作为 SLAM input。
- [x] 增加 blocker 测试：缺 `/slam/odom` 不能 full pass。
- [x] 增加质量指标计算测试：跳变、漂移、latest age。

验收：

- [x] P3 相关单元测试通过。
- [x] 不影响 P0 official baseline 测试。
- [x] 不影响 P1 official maze X2 测试。
- [x] 不影响 P2 rangefinder/IMU 测试。

## P3.9 执行顺序

建议执行：

```text
1. uv run --project orchestration python orchestration/main.py official-baseline-acceptance 30
2. uv run --project orchestration python orchestration/main.py official-maze-x2-acceptance 45
3. uv run --project orchestration python orchestration/main.py rangefinder-imu-acceptance 60
4. uv run --project orchestration python orchestration/main.py slam-backend-doctor
5. uv run --project orchestration python orchestration/main.py slam-backend-acceptance 90
```

验收：

- [x] 每一步失败都能在 summary.blockers 中定位到具体层级。
- [x] 失败不会退回 synthetic IMU、synthetic odom、Gazebo truth SLAM input 或 fake odom 兜底。

## P3 完成标准

P3 全部完成必须满足：

- [x] 官方 `iris_maze` bringup 未被替换。
- [x] P1 X2 `/scan` 链路仍 healthy。
- [x] P2 IMU/rangefinder 机制仍 healthy。
- [x] SLAM backend 通过 registry 启动。
- [x] backend 名称、镜像、启动命令和配置 hash 进入 summary。
- [x] `/scan + /imu + /odometry + TF` 输入全部健康。
- [x] `/scan` 来自 X2 vendor-driver。
- [x] Gazebo truth 没有进入 SLAM 输入。
- [x] `/map` 持续发布。
- [x] `/submap_list` 持续发布。
- [x] `/trajectory_node_list` 持续发布。
- [x] `/slam/odom` 持续发布。
- [x] `/slam/odom` 最新消息年龄和频率符合阈值。
- [x] SLAM 输出没有明显跳变。
- [x] Gazebo truth 诊断误差被记录。
- [x] rosbag required topics 全部有数据。
- [x] summary 明确标注 P3 不代表 hover 完成。
- [x] summary 明确标注 P3 不代表 ExternalNav 回灌完成。

## 验证记录

后续每次验证按下面格式记录：

```text
- 命令：
- 时间：
- artifact：
- 结果：
- blocker：
- 备注：
```

```text
- 命令：uv run --project orchestration python orchestration/main.py slam-backend-doctor
- 时间：2026-06-06 12:02:42
- artifact：artifacts/ros/navlab_slam_backend_doctor/20260606_120242/summary.json
- 结果：通过
- blocker：无
- 备注：确认 P3 backend、runtime config、Cartographer command 可构建。
```

```text
- 命令：uv run --project orchestration python orchestration/main.py build slam
- 时间：2026-06-06
- artifact：navlab/slam-cartographer:latest
- 结果：通过
- blocker：无
- 备注：重建后包含 use_sim_time launch wiring 和 Cartographer adapter TF 过滤诊断。
```

```text
- 命令：uv run --project orchestration python orchestration/main.py slam-backend-acceptance 90
- 时间：2026-06-06 12:54:06
- artifact：artifacts/ros/navlab_companion_sitl_gazebo/20260606_125406/summary.json
- 结果：通过，summary.ok=true，rosbag_profile.ok=true。
- blocker：无
- 备注：/map=85，/submap_list=285，/trajectory_node_list=593，/scan=627，/navlab/x2/vendor_scan=627，/slam/odom=2963；/slam/odom rate=36.01Hz，max_jump_m=0.196m，max_yaw_jump_rad=0.0021rad，stationary_drift_m=0.196m；summary 已记录 slam_launch_command 和 runtime config hash。
```
