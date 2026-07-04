# P4 FCU 状态机和唯一控制器 TODO

## 目标

在 P0/P1/P2/P3 已通过的基础上，验收 FCU 状态机、readiness gate 和唯一 setpoint owner。P4 完成后，只能说明控制权边界和飞控状态机具备进入 P6 hover gate 的基础；不能说明真实 SLAM hover 已完成，也不能说明探索任务已完成。

设计文档：

- `docs/scenarios/indoor/navlab_p4_fcu_state_machine_design.md`

前置条件：

- `docs/scenarios/indoor/todos/P0_official_baseline_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P1_official_maze_x2_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P2_rangefinder_imu_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P3_slam_backend_quality_todo.md` 已通过。

总 roadmap：

- `docs/scenarios/indoor/navlab_master_roadmap.md`

## P4.0 文档和边界

任务：

- [x] 新增 P4 设计文档。
- [x] 新增 P4 TODO 文档。
- [x] 在 `docs/README.md` 中加入 P4 design / TODO 入口。
- [x] 在 master roadmap 中把 P4 TODO 从“待建”改成具体文档。
- [x] 文档明确 P4 不代表 hover 完成。
- [x] 文档明确 P4 不代表 ExternalNav hover 完成。
- [x] 文档明确当前完成 route 是 `mavlink_bootstrap_plus_dds_cmd_vel`，不是纯 DDS service control。
- [x] 文档明确任务层不能直接向 FCU 发 movement setpoint。
- [x] 文档明确只能有一个 setpoint owner。
- [x] 文档明确 Gazebo truth 不能作为控制输入。

验收：

- [x] P4 文档中没有把 direct set pose 当作允许路径。
- [x] P4 文档中没有把 Gazebo truth 当作控制来源。
- [x] P4 文档中明确 `hover_claim=not_evaluated`。
- [x] P4 文档中明确 `exploration_claim=not_evaluated`。

## P4.1 FCU state watcher 配置

任务：

- [x] 新增 P4 controller/runtime 配置段。
- [x] 配置当前验收控制 route，默认 `mavlink_bootstrap_plus_dds_cmd_vel`。
- [x] 配置 MAVLink bootstrap endpoint/source system/source component。
- [x] 配置 required FCU topics/services。
- [x] 配置 FCU state watcher 输出 topic，默认 `/navlab/fcu/state`。
- [x] 配置 local position readiness topic，默认 `/ap/v1/pose/filtered`。
- [x] 配置 rangefinder readiness topic，默认 `/rangefinder/down/status`。
- [x] 配置 IMU readiness topic，默认 `/imu`。
- [x] 配置 readiness timeout。
- [x] summary 记录配置路径和 hash。

验收：

- [x] 配置可从 `orchestration/config.toml` 或 P4 runtime config 加载。
- [x] 缺 required topic/service 时 doctor blocked。
- [x] `control_route=mavlink_bootstrap_plus_dds_cmd_vel` 时不能被标为纯 `official_control_claim=true`。
- [x] summary 能解释每个 readiness 条件来自哪个 topic/service。

## P4.2 FCU 状态机

任务：

- [x] 实现或固化 FCU state watcher。
- [x] 实现或固化 controller 状态机。
- [x] 状态机包含 `wait_fcu_time`。
- [x] 状态机包含 `prearm_check`。
- [x] 状态机包含 `set_guided` / `wait_guided`。
- [x] 状态机包含 `arm` / `wait_armed`。
- [x] 状态机包含 `takeoff` / `wait_takeoff_ack`。
- [x] 状态机包含 `wait_local_position`。
- [x] 状态机包含 `hold_ready` / `final_hold`。
- [x] 每个状态转换记录 enter/exit time、reason、result。
- [x] 每个失败状态写入 blocker。

验收：

- [x] FCU time 可收到。
- [ ] `/ap/v1/prearm_check` 可调用并返回 response。
- [x] prearm 通过或失败原因清晰。
- [x] GUIDED 切换成功。
- [x] arm 成功。
- [x] takeoff command 成功。
- [x] local position ready。
- [x] 状态机最终到达 `complete` 或明确 blocked state。

备注：2026-06-06 的 P4 acceptance 证明 `/ap/v1/prearm_check` service 可发现，但 Cyclone/Fast DDS 的 `ros2 service call` 和 P4 controller runtime 都无法收到 response。因此当前 P4 采用官方示例兼容路线：MAVLink bootstrap 完成 GUIDED/arm/takeoff，DDS `/ap/v1/*` 负责状态观测和 `/ap/v1/cmd_vel` movement output。纯 DDS service response 链路保留为后续 gap。

## P4.3 唯一 setpoint owner

任务：

- [x] 定义唯一 owner 名称，例如 `navlab_fcu_controller`。
- [x] 新增 owner status topic，默认 `/navlab/fcu/owner/status`。
- [x] 检查 movement output topic publisher 数量。
- [x] 检查 mission node 不能直接发布 movement output。
- [x] 检查 pose mirror / sim helper 不能 direct set pose。
- [x] 检查 controller 未 ready 前不会输出 movement setpoint。
- [x] summary 记录 owner、output route、publisher 列表和 competing publisher。

验收：

- [x] `owner.unique=true`。
- [x] `competing_publishers=[]`。
- [x] `set_pose_count==0`。
- [x] 未 ready movement intent 被 reject 或 queue。
- [x] mission layer 没有直接调用 FCU movement output。
- [x] 如果发现多个 owner，P4 blocked。

## P4.4 Mission intent 到 controller command

任务：

- [x] 定义 mission intent schema。
- [x] 定义 controller ack/reject schema。
- [x] 新增 `/navlab/fcu/setpoint/intent`。
- [x] 新增 `/navlab/fcu/setpoint/output`。
- [x] 支持 `takeoff` intent。
- [x] 支持 `hover` intent。
- [x] 支持 `yaw` intent。
- [x] 支持 `local_position_target` intent。
- [x] 支持 `hold` intent。
- [ ] 支持 `abort` 或 `land` intent。
- [x] 所有 intent 经过 readiness gate。
- [x] 所有 output 带 owner id 和 sequence id。

验收：

- [x] intent count 和 output count 进入 summary。
- [x] reject reason 进入 summary。
- [x] P4 hold/zero movement output 走同一 controller 输出通道 `/ap/v1/cmd_vel`。
- [ ] 完整 hover/yaw/local position target 语义在 P6/P7 中继续扩展并保持同一输出通道。
- [x] output 不直接读取 Gazebo truth。
- [x] output 不直接读取 `/slam/odom` 做规划。

## P4.5 官方 DDS 控制接口对齐

任务：

- [x] doctor 检查 `/ap/v1/prearm_check` service。
- [x] doctor 检查 `/ap/v1/mode_switch` service。
- [x] doctor 检查 `/ap/v1/arm_motors` service。
- [x] doctor 检查 `/ap/v1/experimental/takeoff` service。
- [x] doctor 检查 `/ap/v1/cmd_vel` 或官方等价 movement setpoint topic。
- [x] acceptance 记录每个 service call 的 request/result。
- [x] acceptance 记录 FCU observed state，而不是只记录 command sent。
- [x] acceptance 记录 MAVLink bootstrap 的 GUIDED/arm/takeoff ack。

验收：

- [x] 官方 DDS 控制接口存在。
- [x] controller 使用官方示例兼容 route：MAVLink bootstrap + DDS `/ap/v1/cmd_vel`。
- [x] bootstrap route 不会误标为纯 DDS official pass。
- [x] summary 记录 `official_control_claim=false`。
- [x] summary 记录 `mavlink_bootstrap_claim=true`。

## P4.6 Rosbag 和 Foxglove

任务：

- [x] 新增 P4 rosbag profile。
- [x] required topics 至少包含：
  - `/tf`
  - `/tf_static`
  - `/ap/v1/time`
  - `/ap/v1/pose/filtered`
  - `/ap/v1/twist/filtered`
  - `/ap/v1/status`
  - `/ap/v1/cmd_vel`
  - `/rangefinder/down/range`
  - `/rangefinder/down/status`
  - `/imu`
  - `/navlab/fcu/state`
  - `/navlab/fcu/controller/status`
  - `/navlab/fcu/setpoint/intent`
  - `/navlab/fcu/setpoint/output`
  - `/navlab/fcu/owner/status`
- [x] optional topics 包含：
  - `/clock`
  - `/scan`
  - `/slam/odom`
  - `/navlab/slam/status`
  - `/external_nav/status`
  - `/odometry`
  - `/map`
  - `/submap_list`
  - `/trajectory_node_list`
- [x] Foxglove notes 说明 P4 只看 FCU 状态机和 setpoint owner。
- [x] summary 记录 MCAP 路径。

验收：

- [x] rosbag profile summary 中 required topics 全部存在且 message count 大于 0。
- [x] MCAP 可回放 controller state、owner status、setpoint intent/output 和 FCU pose。
- [x] P4 summary 记录 `rosbag_profile.ok=true`。

## P4.7 Acceptance task

任务：

- [x] 新增 `navlab-fcu-controller-doctor` orchestration task。
- [x] 新增 `navlab-fcu-controller-acceptance` orchestration task。
- [x] orchestration CLI 增加同名 task；历史 justfile 便捷入口已回收。
- [x] acceptance 先验证 P0 official DDS baseline。
- [x] acceptance 再验证 P1 X2 scan gate。
- [x] acceptance 再验证 P2 IMU/rangefinder gate。
- [x] acceptance 可选验证 P3 SLAM backend 未被破坏。
- [x] acceptance 启动 FCU controller runtime。
- [x] acceptance 启动 owner/quality probes。
- [x] summary 包含 `p4_fcu_controller` section。
- [x] summary 包含 `fcu_state` section。
- [x] summary 包含 `setpoint_owner` section。
- [x] summary 包含 `setpoint_flow` section。
- [x] summary 包含 `hover_claim` 和 `exploration_claim`。

验收：

- [x] P0 official DDS 条件失败时，P4 blocked。
- [x] P1 X2 `/scan` 条件失败时，P4 blocked。
- [x] P2 IMU/rangefinder 条件失败时，P4 blocked。
- [x] FCU readiness 失败时，P4 blocked。
- [x] GUIDED/arm/takeoff 任一失败时，P4 blocked。
- [x] setpoint owner 不唯一时，P4 blocked。
- [x] direct set pose 出现时，P4 blocked。
- [x] summary 把 P4 controller readiness 和 P6 hover completion 分开。

## P4.8 测试

任务：

- [x] 增加 config 测试：P4 controller 配置可加载。
- [x] 增加 task registry 测试：P4 doctor/acceptance 已注册。
- [x] 增加 summary schema 测试：`p4_fcu_controller` 字段完整。
- [x] 增加 blocker 测试：多个 setpoint owner 不能通过。
- [x] 增加 blocker 测试：未 ready 时输出 movement setpoint 不能通过。
- [x] 增加 blocker 测试：direct set pose 不能通过。
- [x] 增加 route 判断测试：`mavlink_bootstrap_plus_dds_cmd_vel` 不能被标为纯 DDS official pass。
- [x] 增加 rosbag profile 测试：P4 required topics 配置存在。

验收：

- [x] P4 相关单元测试通过。
- [x] 不影响 P0 official baseline 测试。
- [x] 不影响 P1 official maze X2 测试。
- [x] 不影响 P2 rangefinder/IMU 测试。
- [x] 不影响 P3 SLAM backend 测试。

## P4.9 执行顺序

建议执行：

```text
1. uv run --project orchestration python orchestration/main.py official-baseline-acceptance 30
2. uv run --project orchestration python orchestration/main.py official-maze-x2-acceptance 45
3. uv run --project orchestration python orchestration/main.py rangefinder-imu-acceptance 60
4. uv run --project orchestration python orchestration/main.py slam-backend-acceptance 90
5. uv run --project orchestration python orchestration/main.py fcu-controller-doctor
6. uv run --project orchestration python orchestration/main.py fcu-controller-acceptance 90
```

验收：

- [x] 每一步失败都能在 summary.blockers 中定位到具体层级。
- [x] 失败不会退回 synthetic FCU state、synthetic setpoint ack、Gazebo truth control 或 fake odom 兜底。

## P4 完成标准

P4 全部完成必须满足：

- [x] 官方 `iris_maze` bringup 未被替换。
- [x] P1 X2 `/scan` 链路仍 healthy。
- [x] P2 IMU/rangefinder 机制仍 healthy。
- [x] P3 SLAM backend 不被破坏。
- [x] FCU state watcher 能观测 `/ap/v1/*` 状态。
- [x] GUIDED 切换成功。
- [x] arm 成功。
- [x] takeoff command 成功。
- [x] local position ready。
- [x] 只有一个 setpoint owner。
- [x] P4 hold/zero movement output 走同一个 controller 输出通道。
- [ ] 完整 hover/yaw/local position target 语义在 P6/P7 中继续扩展。
- [x] 未 ready 前不会输出 movement setpoint。
- [x] direct set pose 计数为 0。
- [x] Gazebo truth 没有进入控制输入。
- [x] rosbag required topics 全部有数据。
- [x] summary 明确标注 P4 不代表 hover 完成。
- [x] summary 明确标注 P4 不代表探索完成。

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

### 2026-06-06 P4 实现验证

- 命令：`uv run --project orchestration pytest orchestration/tests/test_config.py`
- 时间：2026-06-06 17:00 前后
- artifact：无
- 结果：通过，37 passed
- blocker：无
- 备注：覆盖 P4 config、task registry、runtime config、owner blocker、route blocker、MAVLink bootstrap 配置和 rosbag profile。

- 命令：`uv run --project orchestration python orchestration/main.py fcu-controller-doctor`
- 时间：2026-06-06 16:32:43
- artifact：`artifacts/ros/navlab_fcu_controller_doctor/20260606_163243/summary.json`
- 结果：通过
- blocker：无
- 备注：doctor 验证 P4 runtime 配置、MAVLink bootstrap route、ROS interface、`pymavlink` 和 rosbag profile 前置条件。

- 命令：`uv run --project orchestration python orchestration/main.py rangefinder-imu-acceptance 45`
- 时间：2026-06-06 16:40:26
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260606_164026/summary.json`
- 结果：通过，`ok=true`
- blocker：无
- 备注：独立确认 P2 rangefinder/IMU 链路健康，rangefinder input_count 1191，range rosbag count 126。

- 命令：`uv run --project orchestration python orchestration/main.py fcu-controller-acceptance 90`
- 时间：2026-06-06 17:00:39
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260606_170039/summary.json`
- 结果：通过，`ok=true`
- blocker：无
- 备注：`control_route=mavlink_bootstrap_plus_dds_cmd_vel`；`guided_ok=true`、`arm_ok=true`、`takeoff_ok=true`、`local_position_ready=true`、`rangefinder_ready=true`、`imu_ready=true`；`official_control_claim=false`、`mavlink_bootstrap_claim=true`；唯一 setpoint owner 为 `navlab_fcu_controller`；`/ap/v1/cmd_vel` rosbag count 19，`/rangefinder/down/range` count 1610，`/navlab/fcu/setpoint/output` count 22；`hover_claim=not_evaluated`，`exploration_claim=not_evaluated`。
