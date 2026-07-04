# P2 下视 Rangefinder 与 IMU 机制验收 TODO

## 目标

在 P0/P1 官方 baseline 和 X2 `/scan` 链路已通过的基础上，验收下视 rangefinder 和 IMU 是否按真实无人机机制接入。P2 完成后，只能说明 rangefinder/IMU 机制可观测、可记录、可作为后续 SLAM hover 的输入基础；不能说明 hover 已完成。

设计文档：

- `docs/scenarios/indoor/navlab_p2_rangefinder_imu_design.md`

前置条件：

- `docs/scenarios/indoor/todos/P0_official_baseline_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P1_official_maze_x2_todo.md` 已通过。

总 roadmap：

- `docs/scenarios/indoor/navlab_master_roadmap.md`

## P2.0 文档和边界

任务：

- [x] 新增 P2 设计文档。
- [x] 新增 P2 TODO 文档。
- [x] 在 `docs/README.md` 中加入 P2 design / TODO 入口。
- [x] 在 master roadmap 中把 P2 TODO 从“待建”改成具体文档。
- [x] 文档明确 P2 不代表 hover 完成。
- [x] 文档明确 P2 不代表 SLAM `/odom` 质量完成。
- [x] 文档明确 rangefinder 属于 `gazebo-sensor` FCU 外设机制，不属于 companion 控制高度。
- [x] 文档明确 IMU 必须来自 FCU/SITL 或官方 DDS/MAVLink telemetry，不允许 synthetic fallback 当完成标准。

验收：

- [x] P2 文档中没有把 direct set pose 当作允许路径。
- [x] P2 文档中没有把 companion 油门控制当作 rangefinder 定高验收。
- [x] P2 文档中明确 `altitude_control_claim=not_evaluated`。
- [x] P2 文档中明确 `hover_claim=not_evaluated`。

## P2.1 下视 Rangefinder Gazebo 传感器机制

任务：

- [x] 确认官方 Iris/maze P2 runtime 中有下视 Gazebo range sensor 或等价 ray sensor。
- [x] 如果官方模型没有下视 sensor，增加 P2 专用官方模型 overlay，不替换 world 和主机体控制机制。
- [x] 固化下视 sensor frame，例如 `rangefinder_down_frame`。
- [x] 固化安装位姿、更新频率、min/max range、噪声参数。
- [x] `gazebo-sensor` bridge 下视 scan/range 输入。
- [x] 发布 `/rangefinder/down/range`。
- [x] 发布 `/rangefinder/down/status`。
- [x] summary 记录 rangefinder config 和 hash。

验收：

- [x] `/rangefinder/down/range` message count 大于 0。
- [x] `/rangefinder/down/range.header.frame_id == "rangefinder_down_frame"` 或 P2 配置指定 frame。
- [x] `/rangefinder/down/status.state == "sending"` 或等价 healthy 状态。
- [x] `latest_distance_m` 在 min/max range 内。
- [x] `latest_input_age_sec` 小于阈值。
- [x] rangefinder 数据不是 static fallback。

## P2.2 MAVLink DISTANCE_SENSOR 进入 FCU

任务：

- [x] `gazebo-sensor` 发送 MAVLink `DISTANCE_SENSOR`。
- [x] `DISTANCE_SENSOR` 使用向下方向。
- [x] `DISTANCE_SENSOR` 记录 sensor id、source system、source component、min/max distance、covariance。
- [x] 配置 endpoint，使 `DISTANCE_SENSOR` 发往 ArduPilot SITL/FCU。
- [x] 配置或确认 ArduPilot rangefinder 参数。
- [x] 记录 `sent_count`、`latest_sent_age_sec`。
- [x] 从 SITL log、MAVLink telemetry 或官方 DDS 状态中提取 FCU 接收证据。
- [x] summary 记录 `rangefinder_fcu_received` 和 `rangefinder_fcu_receive_evidence`。

验收：

- [x] `rangefinder_mavlink_sent_count > 0`。
- [x] `latest_sent_age_sec` 小于阈值。
- [x] `mavlink_message == "DISTANCE_SENSOR"`。
- [x] `mavlink_orientation` 明确为下视方向。
- [x] FCU 接收证据存在时 full acceptance 可通过。
- [x] FCU 接收证据不存在时 full acceptance 必须 blocked，不能只靠 sender 通过。

## P2.3 IMU 来源、频率和 Frame

任务：

- [x] 确认 P2 canonical IMU source route：
  - 官方 DDS `/ap/v1/imu/experimental/data`；或
  - FCU MAVLink IMU telemetry bridge；或
  - 明确记录的官方等价 route。
- [x] 固化 IMU output topic，例如 `/imu` 或 `/imu/data`。
- [x] 发布 `/imu/status` 或等价 status。
- [x] summary 记录 `imu_source_route`。
- [x] summary 记录 `imu_source_topic`、`imu_output_topic`、`imu_status_topic`。
- [x] summary 记录 `imu_frame_id`。
- [x] summary 记录 IMU message count、rate、latest age。
- [x] 检查 IMU synthetic fallback 是否关闭。
- [x] 如果必须保留 fallback，只能标记为 diagnostic，不能作为 P2 完成标准。

验收：

- [x] IMU output topic message count 大于 0。
- [x] IMU rate 大于 P2 最小阈值。
- [x] IMU latest age 小于阈值。
- [x] `imu_frame_id == "imu_link"` 或 P2 配置指定 frame。
- [x] `synthetic_fallback_enabled == false`。
- [x] IMU source route 不是 `synthetic`。

## P2.4 TF 和安装关系

任务：

- [x] 检查 `base_link -> imu_link` 可解释。
- [x] 检查 `base_link -> rangefinder_down_frame` 可解释。
- [x] artifact 记录 TF tree 或 frame summary。
- [x] summary 记录 missing TF、duplicate parent、frame loop。
- [x] Foxglove notes 说明 rangefinder 和 IMU frame 如何显示。

验收：

- [x] `imu_link` 能连到 `base_link` 或 artifact 中有明确静态安装解释。
- [x] `rangefinder_down_frame` 能连到 `base_link` 或 artifact 中有明确静态安装解释。
- [x] 没有 TF loop。
- [x] 没有同一 child frame 多 parent。

## P2.5 Rosbag 和 Foxglove

任务：

- [x] 新增 P2 rosbag profile。
- [x] required topics 至少包含：
  - `/clock`
  - `/tf`
  - `/tf_static`
  - `/ap/v1/time`
  - `/scan`
  - `/sim/x2/status`
  - `/rangefinder/down/range`
  - `/rangefinder/down/status`
  - `/imu`
- [x] optional topics 包含：
  - `/ap/v1/imu/experimental/data`
  - `/imu/status`
  - `/odometry`
  - `/submap_list`
  - `/trajectory_node_list`
  - `/rangefinder/down/scan_ideal`
  - `/ap/v1/pose/filtered`
- [x] Foxglove notes 说明 rangefinder、IMU、scan、Cartographer topic 的显示方式。
- [x] summary 记录 MCAP 路径。

验收：

- [x] rosbag profile summary 中 required topics 全部存在且 message count 大于 0。
- [x] MCAP 可在 Foxglove 中回放 `/scan`、IMU、rangefinder 和官方 maze TF。
- [x] P2 summary 记录 `rosbag_profile.ok=true`。

## P2.6 Acceptance task

任务：

- [x] 新增 `navlab-rangefinder-imu-doctor` orchestration task。
- [x] 新增 `navlab-rangefinder-imu-acceptance` orchestration task。
- [x] orchestration CLI 增加同名 task；历史 justfile 便捷入口已回收。
- [x] acceptance 先跑或复用 P0 official DDS probe。
- [x] acceptance 再跑或复用 P1 X2 scan gate。
- [x] acceptance 启动 rangefinder/IMU probe。
- [x] summary 包含 `p2_rangefinder_imu` section。
- [x] summary 包含 `rangefinder` section。
- [x] summary 包含 `imu` section。
- [x] summary 包含 `altitude_control_claim` 和 `hover_claim`。

验收：

- [x] P0 official DDS 条件失败时，P2 blocked。
- [x] P1 X2 `/scan` 条件失败时，P2 blocked。
- [x] rangefinder sender 失败时，P2 blocked。
- [x] FCU 接收证据缺失时，P2 full acceptance blocked。
- [x] IMU synthetic fallback 被当成完成标准时，P2 blocked。
- [x] direct set pose 出现时，P2 blocked。
- [x] summary 把 P2 sensor mechanism 和 P6 hover completion 分开。

## P2.7 测试

任务：

- [x] 增加 config 测试：P2 rangefinder/IMU 配置可加载。
- [x] 增加 task registry 测试：P2 doctor/acceptance 已注册。
- [x] 增加 summary schema 测试：`p2_rangefinder_imu` 字段完整。
- [x] 增加 rosbag profile 测试：P2 required topics 配置存在。
- [x] 增加 rangefinder status parser 测试。
- [x] 增加 IMU status parser 测试。
- [x] 增加 blocker 测试：FCU 接收证据缺失不能 full pass。

验收：

- [x] P2 相关单元测试通过。
- [x] 不影响 P0 official baseline 测试。
- [x] 不影响 P1 official maze X2 acceptance 测试。

## P2.8 执行顺序

建议执行：

```text
1. uv run --project orchestration python orchestration/main.py official-baseline-acceptance 30
2. uv run --project orchestration python orchestration/main.py official-maze-x2-acceptance 45
3. uv run --project orchestration python orchestration/main.py rangefinder-imu-doctor
4. uv run --project orchestration python orchestration/main.py rangefinder-imu-acceptance 60
```

验收：

- [x] 每一步失败都能在 summary.blockers 中定位到具体层级。
- [x] 失败不会退回 synthetic rangefinder、synthetic IMU 或 fake odom 兜底。

## P2 完成标准

P2 全部完成必须满足：

- [x] 官方 `iris_maze` bringup 未被替换。
- [x] 官方 Iris 模型未被替换，或只使用明确记录的 P2 sensor overlay。
- [x] P1 X2 `/scan` 链路仍 healthy。
- [x] `/rangefinder/down/range` 持续发布。
- [x] `/rangefinder/down/status` 持续发布。
- [x] MAVLink `DISTANCE_SENSOR` 持续发送。
- [x] FCU 接收 rangefinder 的证据存在。
- [x] IMU canonical topic 持续发布。
- [x] IMU frame 和 rate 符合 P2 配置。
- [x] IMU source 不是 synthetic fallback。
- [x] rosbag required topics 全部有数据。
- [x] summary 明确标注 P2 不代表 hover 完成。
- [x] summary 明确标注 P2 不代表 SLAM `/odom` 质量完成。

## 验证记录

后续每次验证按下面格式记录：

```text
- 命令：`uv run --project orchestration python orchestration/main.py rangefinder-imu-acceptance 60`
- 时间：`2026-06-07`
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260607_001025/summary.json`
- 结果：`ok=true`
- blocker：`none`
- 备注：P2 config bug 已修复；`/lidar -> X2 -> /scan`、`/rangefinder/down/range`、`/imu`、`DISTANCE_SENSOR` 均通过；`hover` 和 `altitude_control` 仍然明确标记为 `not_evaluated`。
```
