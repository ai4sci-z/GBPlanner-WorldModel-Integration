# P8 官方 maze 探索任务 TODO

## 目标

在 P0-P7 已通过的基础上，验收官方 `iris_maze` / Iris 场景中是否能完成一次
可回放、不碰撞、由 SLAM map/scan/TF/FCU state 驱动的 bounded exploration task。P8
完成后，只能说明官方 maze 的最小探索闭环已评价；不能说明 P9 Foxglove-lite replay、NavLab 8 字形 world/model
迁移、真机部署或完整生产级 Nav2 stack 已完成。

设计文档：

- `docs/scenarios/indoor/navlab_p8_official_maze_exploration_design.md`

前置文档：

- `docs/scenarios/indoor/navlab_master_roadmap.md`
- `docs/scenarios/indoor/todos/P6_slam_hover_gate_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P7_official_maze_motion_gate_todo.md` 已通过。

## P8.0 文档和边界

任务：

- [x] 新增 P8 设计文档。
- [x] 新增 P8 TODO 文档。
- [x] 在 `docs/README.md` 中加入 P8 design / TODO 入口。
- [x] 在 master roadmap 中把 P8 TODO 从“待建”改成具体文档。
- [x] 文档明确 P8 是官方 maze 探索 gate，不是 P9 Foxglove-lite replay。
- [x] 文档明确 P8 必须复用 P6 hover readiness。
- [x] 文档明确 P8 必须复用 P7 motion readiness。
- [x] 文档明确 P8 不允许 direct set pose。
- [x] 文档明确 P8 必须保持 P4/P6/P7 唯一 setpoint owner。
- [x] 文档明确 P8 不能把 Gazebo truth 当作探索输入。

验收：

- [x] P8 文档中没有把 Gazebo truth 当作控制、规划、SLAM 或 ExternalNav 来源。
- [x] P8 文档中没有把 direct set pose 当作允许路径。
- [x] P8 文档中明确 `exploration_claim=evaluated`。
- [x] P8 文档中明确 P8 不代表 P9 replay artifact 完成。

## P8.1 配置

任务：

- [x] 新增 P8 exploration 配置段。
- [x] 配置 strategy，例如 `frontier_lite`、`corridor_probe` 或 `scripted_bounded_exploration`。
- [x] 配置 exploration 总时长上限。
- [x] 配置每个 local goal 的 timeout。
- [x] 配置最小 accepted goal/action 数。
- [x] 配置最小 coverage 或 map-growth 阈值。
- [x] 配置最小 scan clearance 阈值。
- [x] 配置 stuck timeout 和 progress 阈值。
- [x] 配置 final stop / hover hold 时长和 drift 阈值。
- [x] 配置 P8 rosbag profile。
- [x] P8 runtime config 写入 artifact 并记录 hash。

验收：

- [x] 默认配置不读取 Gazebo truth 作为 planning/control/SLAM/ExternalNav 输入。
- [x] 默认配置不允许 direct set pose。
- [x] 默认配置要求 unique FCU controller owner。
- [x] 配置加载失败时，P8 doctor blocked。

## P8.2 Exploration intent 和唯一 controller gate

任务：

- [x] 新增或固化 P8 exploration intent/status schema。
- [x] exploration coordinator 只发布 `/navlab/fcu/setpoint/intent`。
- [x] exploration coordinator 不发布 `/ap/v1/cmd_vel`。
- [x] FCU controller 继续作为唯一 `/ap/v1/cmd_vel` owner。
- [x] owner monitor 记录 `owner.unique`、`set_pose_count`、`competing_publishers`。
- [x] summary 记录 `control_route=unique_fcu_controller`。

验收：

- [x] `owner.unique == true`。
- [x] `set_pose_count == 0`。
- [x] `competing_publishers == []`。
- [x] 发现第二个 `/ap/v1/cmd_vel` publisher 时，P8 blocked。
- [x] 发现 direct set pose 时，P8 blocked。
- [x] controller readiness 不满足时，P8 blocked。

## P8.3 P6/P7 前置 gate

任务：

- [x] P8 acceptance 先验证或复用 P6 hover readiness。
- [x] P8 acceptance 再验证或复用 P7 motion readiness。
- [x] P8 exploration coordinator 在前置 gate 未通过前不发 exploration intent。
- [x] summary 记录 `p6_hover_prerequisite`。
- [x] summary 记录 `p7_motion_prerequisite`。
- [x] summary 记录 `hover_claim=evaluated`。
- [x] summary 记录 `motion_claim=evaluated`。

验收：

- [x] P6 hover 前置不满足时，P8 blocked。
- [x] P7 motion 前置不满足时，P8 blocked。
- [x] P8 不能把 P6/P7 的 artifact 误标为 exploration completion。

## P8.4 Local goal / frontier-lite 策略

任务：

- [x] 实现或接入 bounded local goal selector。
- [x] selector 输入只允许 SLAM map、scan、TF、FCU state 和任务状态。
- [x] selector 输出 local goal、yaw scan 或 stop intent。
- [x] 每个 goal 记录选择原因、输入状态、target frame 和 timeout。
- [x] 拒绝不可达、clearance 不足或 stale map 的 goal。
- [x] 支持 dead-end 情况下的 yaw scan / backoff / stop 策略。

验收：

- [x] accepted goal 数达到配置阈值。
- [x] rejected goal 有明确原因。
- [x] Gazebo truth 不进入 selector 输入。
- [x] map stale 时不选择新 goal。
- [x] clearance 不足时不选择 forward goal。

## P8.5 Exploration action execution

任务：

- [x] 将 local goal 转换为 bounded forward/yaw/stop intent。
- [x] 每个 action 记录 start/end pose、duration、result 和 blocker。
- [x] 支持 forward probe。
- [x] 支持 yaw scan。
- [x] 支持 stop hold。
- [x] 支持 final hover 或 final stop。
- [x] action 执行期间持续记录 SLAM odom、FCU local position 和 scan clearance。

验收：

- [x] 至少完成配置中的最小 action 数。
- [x] 每个 accepted action 都有 FCU setpoint intent 和 controller output。
- [x] 每个 action 后 stop drift 在阈值内。
- [x] action timeout 时 P8 blocked 或进入安全停止并记录 blocker。

## P8.6 Safety：clearance、stop guard、collision、stuck

任务：

- [x] exploration window 内持续统计 scan clearance。
- [x] clearance 低于阈值时触发 stop 并 blocked。
- [x] 记录 stop drift 和 final drift。
- [x] 接入 collision diagnostic。
- [x] 接入 stuck detector。
- [x] stuck detector 同时考虑 intent、位移、yaw、map growth 和 timeout。
- [x] safety violation 写入 blocker。

验收：

- [x] `collision.detected == false`。
- [x] `stuck.blocked == false`。
- [x] `safety.min_scan_clearance_m >= threshold`。
- [x] stop drift 和 final drift 在阈值内。
- [x] collision diagnostic 表示发生碰撞时，P8 blocked。
- [x] stuck timeout 超阈值时，P8 blocked。

## P8.7 Coverage / progress metrics

任务：

- [x] 记录 exploration window 起止时间。
- [x] 记录 map known cell count 起止值。
- [x] 记录 known cell growth 或 explored area。
- [x] 记录 path length。
- [x] 记录 accepted/rejected goal 数。
- [x] 记录 yaw scan、forward probe、stop 数。
- [x] 记录 final task state。

验收：

- [x] coverage 或 map growth 达到配置阈值。
- [x] accepted goal/action 数达到配置阈值。
- [x] coverage 计算不依赖 Gazebo truth。
- [x] 未覆盖区域必须能在 summary 或 Foxglove notes 中解释。

## P8.8 SLAM、ExternalNav、FCU exploration health

任务：

- [x] exploration window 内统计 `/slam/odom` 频率和 max gap。
- [x] exploration window 内统计 `/map` 最新 age 和 known cell count。
- [x] exploration window 内统计 ExternalNav 频率和 stale 状态。
- [x] exploration window 内统计 FCU local position 频率和 stale 状态。
- [x] exploration window 内统计 scan、IMU、rangefinder health。
- [x] summary 记录所有 health 指标。

验收：

- [x] SLAM odom healthy。
- [x] map healthy。
- [x] ExternalNav healthy。
- [x] FCU local position healthy。
- [x] scan、IMU、rangefinder healthy。
- [x] 任一关键 pipeline stale 时，P8 blocked。

## P8.9 Rosbag 和 Foxglove

任务：

- [x] 新增 P8 rosbag profile。
- [x] required topics 包含 `/clock`、`/tf`、`/tf_static`。
- [x] required topics 包含 `/scan`、`/imu`、`/rangefinder/down/range`、`/rangefinder/down/status`。
- [x] required topics 包含 `/slam/odom`、`/navlab/slam/status`、`/external_nav/status`。
- [x] required topics 包含 `/map`、`/submap_list`、`/trajectory_node_list`。
- [x] required topics 包含 `/ap/v1/time`、`/ap/v1/pose/filtered`、`/ap/v1/twist/filtered`、`/ap/v1/status`、`/ap/v1/cmd_vel`。
- [x] required topics 包含 `/navlab/fcu/state`、`/navlab/fcu/controller/status`、`/navlab/fcu/setpoint/intent`、`/navlab/fcu/setpoint/output`、`/navlab/fcu/owner/status`。
- [x] required topics 包含 `/navlab/hover/status`、`/navlab/motion/status`。
- [x] required topics 包含 `/navlab/exploration/status`、`/navlab/exploration/goal`、`/navlab/exploration/coverage`。
- [x] optional diagnostic topics 包含 Gazebo truth 或 markers 时，summary 明确 diagnostic-only。
- [x] Foxglove notes 说明固定参考系使用 `map`。
- [x] Foxglove notes 说明 exploration window、goal/action 窗口和 final stop 窗口。

验收：

- [x] rosbag 文件存在且非空。
- [x] required topics 全部存在。
- [x] required topics message count 全部大于 0。
- [x] required topics 频率或 max gap 满足阈值。
- [x] P8 summary 记录 `rosbag_profile.ok=true`。

## P8.10 Acceptance task

任务：

- [x] 新增 P8 doctor task。
- [x] 新增 P8 acceptance task。
- [x] acceptance 启动官方 maze/Iris baseline。
- [x] acceptance 启动 X2 `/scan`、rangefinder、IMU、SLAM、ExternalNav 和 FCU controller。
- [x] acceptance 验证 P6 hover gate。
- [x] acceptance 验证 P7 motion gate。
- [x] acceptance 启动 P8 exploration coordinator。
- [x] acceptance 运行 bounded exploration window。
- [x] acceptance 执行 final hover 或 final stop。
- [x] acceptance 写出 summary、rosbag、config、Foxglove notes 和 blocker。

验收：

- [x] P0 official DDS 条件失败时，P8 blocked。
- [x] P1 X2 `/scan` 条件失败时，P8 blocked。
- [x] P2 IMU/rangefinder 条件失败时，P8 blocked。
- [x] P3 SLAM backend 条件失败时，P8 blocked。
- [x] P4 FCU controller 条件失败时，P8 blocked。
- [x] P5 frame contract 条件失败时，P8 blocked。
- [x] P6 hover 条件失败时，P8 blocked。
- [x] P7 motion 条件失败时，P8 blocked。
- [x] exploration coverage/safety 条件失败时，P8 blocked。
- [x] summary 把 P8 exploration completion 和 P9 replay artifact 分开。

## P8.11 测试

任务：

- [x] 增加 config 测试：P8 exploration 配置可加载。
- [x] 增加 task registry 测试：P8 doctor/acceptance 已注册。
- [x] 增加 blocker 测试：P6 hover 前置失败不能通过。
- [x] 增加 blocker 测试：P7 motion 前置失败不能通过。
- [x] 增加 blocker 测试：Gazebo truth 作为 exploration input 时不能通过。
- [x] 增加 blocker 测试：owner conflict 时不能通过。
- [x] 增加 blocker 测试：coverage/map growth 不足时不能通过。
- [x] 增加 blocker 测试：collision/stuck 时不能通过。
- [x] 增加 rosbag profile 测试：P8 required topics 配置存在。
- [x] 增加 summary schema 测试：`exploration_claim=evaluated` 和 P6/P7 prerequisite 字段存在。
- [x] P8 相关单元测试通过。
- [x] 不影响 P6 SLAM hover 测试。
- [x] 不影响 P7 motion gate 测试。

验收：

- [x] 新增测试覆盖 P8 核心 blocker。
- [x] P6/P7 相关测试继续通过。
- [x] CI 或本地目标测试记录写入验证记录。

## P8.12 执行顺序

建议顺序：

1. P8.1 配置。
2. P8.2 Exploration intent 和唯一 controller gate。
3. P8.3 P6/P7 前置 gate。
4. P8.4 Local goal / frontier-lite 策略。
5. P8.5 Exploration action execution。
6. P8.6 Safety gate。
7. P8.7 Coverage / progress metrics。
8. P8.8 Pipeline health。
9. P8.9 Rosbag 和 Foxglove。
10. P8.10 Acceptance task。
11. P8.11 测试。
12. 真实运行 P8 acceptance，补验证记录。

## P8 完成标准

P8 全部完成必须满足：

- [x] P8 doctor 通过。
- [x] P8 acceptance 通过。
- [x] `ok == true`。
- [x] `blocked == false`。
- [x] `blockers == []`。
- [x] `hover_claim == evaluated`。
- [x] `motion_claim == evaluated`。
- [x] `exploration_claim == evaluated`。
- [x] P6 hover prerequisite `ok == true`。
- [x] P7 motion prerequisite `ok == true`。
- [x] 官方 maze/Iris 中完成 bounded exploration task。
- [x] coverage 或 map growth 达到阈值。
- [x] accepted goal/action 数达到阈值。
- [x] 不碰撞。
- [x] 不 stuck。
- [x] final hover 或 final stop 稳定。
- [x] `uses_gazebo_truth_as_input == false`。
- [x] `owner.unique == true`。
- [x] `set_pose_count == 0`。
- [x] `competing_publishers == []`。
- [x] rosbag profile `ok == true`。
- [x] required topics 全部有数据。
- [x] Foxglove 可回放完整探索任务。
- [x] summary 明确标注 P8 已评价探索。
- [x] summary 明确标注 P8 不代表 P9 Foxglove-lite replay 完成。

## 验证记录

### 2026-06-07 P8 文档初始化

- 命令：未运行代码测试，纯文档初始化。
- 结果：新增 P8 设计文档和 TODO 文档，并把 P8 加入 README 和 master roadmap。
- blocker：P8 配置、exploration coordinator、coverage/safety gate、rosbag profile 和 acceptance 尚未实现。
- 备注：P8.0 文档和边界已完成；后续从 P8.1 配置和 P8.2 exploration intent/controller gate 开始实现。


### 2026-06-07 P8 实现、测试和 acceptance 通过

- 命令：`PYTHONPATH=orchestration uv run --project orchestration pytest orchestration/tests/test_config.py -q`
- 结果：61 passed
- 命令：`PYTHONPATH=orchestration uv run --project orchestration python orchestration/main.py exploration-gate-doctor`
- 结果：doctor `ok=true`，`blocked=false`，`blockers=[]`
- 命令：`PYTHONPATH=orchestration uv run --project orchestration python orchestration/main.py exploration-gate-acceptance 150`
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260607_144800/summary.json`
- 结果：`ok=true`，`blocked=false`，`blockers=[]`
- 关键指标：`exploration_claim=evaluated`，`hover_claim=evaluated`，`motion_claim=evaluated`，`uses_gazebo_truth_as_input=false`
- 探索结果：`strategy=frontier_lite`，`accepted_goals=3`，`forward_probe=3`，`yaw_scan=0`，`final_task_state=final_hover`
- coverage：known cell 从 2948 增至 3388，growth=440；path_length=0.930m；estimated_explored_area=8.47m2
- safety：min_scan_clearance=1.5m，stop_drift=0.0556m，final_drift=0.0182m，collision=false，stuck=false
- pipeline：SLAM odom 50.1Hz，ExternalNav 120.6Hz，FCU local position 17.2Hz
- owner：`unique=true`，`set_pose_count=0`，`competing_publishers=[]`
- rosbag：profile `ok=true`，required topics 全部非零；MCAP `artifacts/ros/navlab_companion_sitl_gazebo/20260607_144800/rosbag/rosbag_0.mcap`
- 备注：第一次 acceptance 尝试暴露了 P8 probe 生成脚本的 newline 转义问题；修复后重新运行 acceptance 通过。

### 2026-06-16 P14 rangefinder 边界更新

- P8 后续 live acceptance 必须引用 `docs/scenarios/indoor/todos/P14_benewake_rangefinder_sitl_todo.md`。
- exploration 任务不能依赖 Python 发送 MAVLink `DISTANCE_SENSOR` 作为 FCU rangefinder 输入。
- FCU rangefinder 输入必须是 Benewake serial emulation；summary 必须记录 `rangefinder_simulation_fidelity=benewake_serial_emulated`，否则 blocked。
