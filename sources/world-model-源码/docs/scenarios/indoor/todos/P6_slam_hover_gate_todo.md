# P6 真实 SLAM hover gate TODO

## 目标

在 P0-P5 已通过的基础上，验收真实 SLAM `/slam/odom` 通过 ExternalNav 进入 ArduPilot EKF 后，FCU 是否能在官方 maze/Iris 场景中稳定悬停。P6 完成后，只能说明真实 SLAM hover gate 已通过；不能说明小范围运动、避障、探索或 NavLab 自定义 world/model 迁移已完成。

设计文档：

- `docs/scenarios/indoor/navlab_p6_slam_hover_gate_design.md`

前置条件：

- `docs/scenarios/indoor/todos/P0_official_baseline_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P1_official_maze_x2_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P2_rangefinder_imu_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P3_slam_backend_quality_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P4_fcu_state_machine_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P5_frame_contract_todo.md` 已通过。

总 roadmap：

- `docs/scenarios/indoor/navlab_master_roadmap.md`

## P6.0 文档和边界

任务：

- [x] 新增 P6 设计文档。
- [x] 新增 P6 TODO 文档。
- [x] 在 `docs/README.md` 中加入 P6 design / TODO 入口。
- [x] 在 master roadmap 中把 P6 TODO 从“待建”改成具体文档。
- [x] 文档明确 P6 是 hover gate，不是 P7 小范围运动 gate。
- [x] 文档明确 P6 不是 P8 探索 gate。
- [x] 文档明确 P6 不替换 NavLab 8 字形 world/model。
- [x] 文档明确 Gazebo truth 只能作为诊断，不能作为 SLAM、ExternalNav、规划或控制输入。
- [x] 文档明确 P6 不允许 direct set pose。
- [x] 文档明确 P6 必须保持 P4 唯一 setpoint owner。

验收：

- [x] P6 文档中没有把 Gazebo truth 当作控制来源。
- [x] P6 文档中没有把 direct set pose 当作允许路径。
- [x] P6 文档中明确 `hover_claim=evaluated`。
- [x] P6 文档中明确 `exploration_claim=not_evaluated`。

## P6.1 配置

任务：

- [x] 新增 P6 SLAM hover 配置段。
- [x] 配置 rosbag profile，默认 `docker/profiles/navlab-slam-hover-rosbag-topics.txt`。
- [x] 配置 SLAM odom topic，默认 `/slam/odom`。
- [x] 配置 SLAM status topic，默认 `/navlab/slam/status`。
- [x] 配置 ExternalNav status topic，默认 `/external_nav/status`。
- [x] 配置 FCU pose topic，默认 `/ap/v1/pose/filtered`。
- [x] 配置 FCU twist topic，默认 `/ap/v1/twist/filtered`。
- [x] 配置 FCU status topic，默认 `/ap/v1/status`。
- [x] 配置 FCU command topic，默认 `/ap/v1/cmd_vel`。
- [x] 配置 rangefinder topic，默认 `/rangefinder/down/range`。
- [x] 配置 IMU topic，默认 `/imu`。
- [x] 配置 Gazebo truth diagnostic topic，默认 `/odometry`。
- [x] 配置 hover status topic，默认 `/navlab/hover/status`。
- [x] 配置 hover window、settle window 和 final hold window。
- [x] 配置 drift、altitude、yaw、rate 和 latest age 阈值。
- [x] 配置 `uses_gazebo_truth_as_input=false`。

验收：

- [x] 配置可从 `orchestration/config.toml` 加载。
- [x] P6 runtime config 写入 artifact 并记录 hash。
- [x] 配置中如果允许 Gazebo truth 作为输入，doctor blocked。
- [x] 配置中如果 SLAM odom topic 不是 `/slam/odom` 或等价 allowed topic，doctor blocked。

## P6.2 ExternalNav bridge gate

任务：

- [x] 固化 ExternalNav bridge 输入必须来自 `/slam/odom`。
- [x] ExternalNav bridge 记录 input count、sent count、rate、latest input age 和 latest sent age。
- [x] ExternalNav bridge 输出 `/external_nav/status`。
- [x] 检查 ExternalNav 不读取 `/odometry`。
- [x] 检查 ExternalNav 不读取 Gazebo truth diagnostic。
- [x] 检查 ExternalNav 不读取 FCU fused local position 作为输入。
- [x] 检查 ExternalNav 输出 route 是官方或支持的 ArduPilot EKF ExternalNav route。
- [x] 检查 ExternalNav 发送频率大于阈值。
- [x] 检查 ExternalNav 最新输入和最新发送年龄小于阈值。

验收：

- [x] `external_nav.ok=true`。
- [x] `external_nav.input_topic == "/slam/odom"`。
- [x] `external_nav.sent_count > 0`。
- [x] `external_nav.rate_hz >= min_external_nav_rate_hz`。
- [x] `external_nav.latest_sent_age_sec <= max_latest_age_sec`。
- [x] `external_nav.uses_gazebo_truth_as_input=false`。
- [x] ExternalNav 不 healthy 时，P6 blocked。

## P6.3 SLAM odom gate

任务：

- [x] 启动 P3 SLAM backend。
- [x] 检查 `/slam/odom` topic 存在。
- [x] 检查 `/slam/odom.header.frame_id` 和 `child_frame_id` 符合 P5 frame contract。
- [x] 检查 `/slam/odom` rate 大于阈值。
- [x] 检查 `/slam/odom` latest age 小于阈值。
- [x] 检查 stationary drift 小于阈值。
- [x] 检查 jump / yaw jump 小于阈值。
- [x] 检查 `/navlab/slam/status` healthy。
- [x] summary 记录 SLAM backend 名称、配置路径、config hash 和状态。

验收：

- [x] `slam_odom.ok=true`。
- [x] `slam_odom.topic == "/slam/odom"`。
- [x] `slam_odom.rate_hz >= min_slam_odom_rate_hz`。
- [x] `slam_odom.latest_age_sec <= max_latest_age_sec`。
- [x] `slam_odom.stationary_drift_m <= max_slam_stationary_drift_m`。
- [x] `/navlab/slam/status` message count 大于 0。
- [x] SLAM 不 healthy 时，P6 blocked。

## P6.4 FCU readiness 和 EKF gate

任务：

- [x] 复用 P4 FCU controller readiness gate。
- [x] 检查 `/ap/v1/time` 可收到。
- [x] 检查 mode 可切到 GUIDED。
- [x] 检查 arm 成功。
- [x] 检查 takeoff 成功。
- [x] 检查 `/ap/v1/pose/filtered` 持续输出。
- [x] 检查 `/ap/v1/twist/filtered` 持续输出。
- [x] 检查 local position rate 大于阈值。
- [x] 检查 rangefinder 持续可用。
- [x] 检查 IMU 持续可用。
- [x] 检查 EKF 或等价状态能证明 ExternalNav 被接受。

验收：

- [x] `guided_ok=true`。
- [x] `arm_ok=true`。
- [x] `takeoff_ok=true`。
- [x] `fcu_local_position.ok=true`。
- [x] `fcu_local_position.rate_hz >= min_fcu_local_position_rate_hz`。
- [x] `rangefinder.ok=true`。
- [x] `imu.ok=true`。
- [x] EKF/ExternalNav 接收状态不满足时，P6 blocked。

## P6.5 Hover controller gate

任务：

- [x] 复用 P4 唯一 setpoint owner。
- [x] 支持 P6 hover intent。
- [x] controller 等待 SLAM odom ready。
- [x] controller 等待 ExternalNav healthy。
- [x] controller 等待 FCU local position ready。
- [x] controller 只通过 `/ap/v1/cmd_vel` 或配置允许的唯一输出通道发 hover setpoint。
- [x] controller 输出 `/navlab/hover/status`。
- [x] controller 输出 hover settle、hover hold、final hold 状态。
- [x] controller 未 ready 时拒绝 hover intent 并写明原因。
- [x] 不允许 mission 层直接发布 `/ap/v1/cmd_vel`。

验收：

- [x] `owner.unique=true`。
- [x] `owner.set_pose_count==0`。
- [x] `owner.competing_publishers=[]`。
- [x] `/navlab/fcu/controller/status` message count 大于 0。
- [x] `/navlab/fcu/setpoint/output` message count 大于 0。
- [x] `/navlab/hover/status` message count 大于 0。
- [x] controller readiness 不满足时，P6 blocked。

## P6.6 Hover drift 统计

任务：

- [x] 定义 settle window。
- [x] 定义 hover window。
- [x] 定义 final hold window。
- [x] 在 hover window 内统计 FCU local position 水平漂移。
- [x] 在 hover window 内统计 SLAM odom 水平漂移。
- [x] 在 hover window 内统计 Gazebo truth diagnostic 水平漂移。
- [x] 在 hover window 内统计高度误差。
- [x] 在 hover window 内统计 yaw 漂移。
- [x] 在 final hold window 内统计 stop drift。
- [x] summary 记录每个窗口的起止时间、样本数和误差。

验收：

- [x] `hover.ok=true`。
- [x] `hover.window_sec >= min_hover_window_sec`。
- [x] `hover.horizontal_drift_m <= max_hover_horizontal_drift_m`。
- [x] `hover.altitude_error_m <= max_hover_altitude_error_m`。
- [x] `hover.yaw_drift_rad <= max_hover_yaw_drift_rad`。
- [x] `hover.stop_drift_m <= max_stop_drift_m`。
- [x] hover drift 超阈值时，P6 blocked。

## P6.7 Rosbag 和 Foxglove

任务：

- [x] 新增 P6 rosbag profile。
- [x] required topics 至少包含：
  - `/clock`
  - `/tf`
  - `/tf_static`
  - `/scan`
  - `/imu`
  - `/rangefinder/down/range`
  - `/rangefinder/down/status`
  - `/slam/odom`
  - `/navlab/slam/status`
  - `/external_nav/status`
  - `/ap/v1/time`
  - `/ap/v1/pose/filtered`
  - `/ap/v1/twist/filtered`
  - `/ap/v1/status`
  - `/ap/v1/cmd_vel`
  - `/navlab/fcu/state`
  - `/navlab/fcu/controller/status`
  - `/navlab/fcu/setpoint/intent`
  - `/navlab/fcu/setpoint/output`
  - `/navlab/fcu/owner/status`
  - `/navlab/hover/status`
- [x] optional topics 至少包含：
  - `/map`
  - `/submap_list`
  - `/trajectory_node_list`
  - `/odometry`
  - `/navlab/frame_contract/status`
  - `/navlab/x2/vendor_scan`
  - `/navlab/x2/scan_ideal`
  - `/sim/x2/status`
  - `/rangefinder/down/scan_ideal`
- [x] Foxglove notes 说明 P6 固定参考系使用 `map`。
- [x] Foxglove notes 说明 `/odometry` 只用于诊断对照。
- [x] summary 记录 MCAP 路径。

验收：

- [x] rosbag profile summary 中 required topics 全部存在且 message count 大于 0。
- [x] MCAP 可回放 TF、scan、SLAM odom、FCU pose、rangefinder、ExternalNav status 和 hover status。
- [x] P6 summary 记录 `rosbag_profile.ok=true`。

## P6.8 Acceptance task

任务：

- [x] 新增 `navlab-slam-hover-doctor` orchestration task。
- [x] 新增 `navlab-slam-hover-acceptance` orchestration task。
- [x] orchestration CLI 增加同名 task；历史 justfile 便捷入口已回收。
- [x] acceptance 先验证 P0 official baseline。
- [x] acceptance 再验证 P1 X2 scan gate。
- [x] acceptance 再验证 P2 IMU/rangefinder gate。
- [x] acceptance 再验证 P3 SLAM backend gate。
- [x] acceptance 再验证 P4 FCU controller gate。
- [x] acceptance 再验证 P5 frame contract gate。
- [x] acceptance 启动 P6 hover probe/controller。
- [x] summary 包含 `p6_slam_hover` section。
- [x] summary 包含 `slam_odom` section。
- [x] summary 包含 `external_nav` section。
- [x] summary 包含 `fcu` section。
- [x] summary 包含 `hover` section。
- [x] summary 包含 `owner` section。
- [x] summary 包含 `hover_claim=evaluated`。
- [x] summary 包含 `exploration_claim=not_evaluated`。

验收：

- [x] P0 official DDS 条件失败时，P6 blocked。
- [x] P1 X2 `/scan` 条件失败时，P6 blocked。
- [x] P2 IMU/rangefinder 条件失败时，P6 blocked。
- [x] P3 SLAM backend 条件失败时，P6 blocked。
- [x] P4 FCU controller 条件失败时，P6 blocked。
- [x] P5 frame contract 条件失败时，P6 blocked。
- [x] ExternalNav 条件失败时，P6 blocked。
- [x] hover drift 条件失败时，P6 blocked。
- [x] summary 把 P6 hover completion 和 P7/P8 分开。

## P6.9 测试

任务：

- [x] 增加 config 测试：P6 SLAM hover 配置可加载。
- [x] 增加 task registry 测试：P6 doctor/acceptance 已注册。
- [x] 增加 blocker 测试：ExternalNav input 不是 `/slam/odom` 不能通过。
- [x] 增加 blocker 测试：Gazebo truth 作为输入不能通过。
- [x] 增加 blocker 测试：direct set pose 不能通过。
- [x] 增加 blocker 测试：多个 setpoint owner 不能通过。
- [x] 增加 hover drift 测试：水平漂移超阈值不能通过。
- [x] 增加 hover drift 测试：高度误差超阈值不能通过。
- [x] 增加 rosbag profile 测试：P6 required topics 配置存在。

验收：

- [x] P6 相关单元测试通过。
- [x] 不影响 P0 official baseline 测试。
- [x] 不影响 P1 official maze X2 测试。
- [x] 不影响 P2 rangefinder/IMU 测试。
- [x] 不影响 P3 SLAM backend 测试。
- [x] 不影响 P4 FCU controller 测试。
- [x] 不影响 P5 frame contract 测试。

## P6.10 执行顺序

建议执行：

```text
1. uv run --project orchestration python orchestration/main.py official-baseline-acceptance 30
2. uv run --project orchestration python orchestration/main.py official-maze-x2-acceptance 45
3. uv run --project orchestration python orchestration/main.py rangefinder-imu-acceptance 60
4. uv run --project orchestration python orchestration/main.py slam-backend-acceptance 90
5. uv run --project orchestration python orchestration/main.py fcu-controller-acceptance 90
6. uv run --project orchestration python orchestration/main.py frame-contract-acceptance 90
7. uv run --project orchestration python orchestration/main.py slam-hover-doctor
8. uv run --project orchestration python orchestration/main.py slam-hover-acceptance 90
```

验收：

- [x] 每一步失败都能在 summary.blockers 中定位到具体层级。
- [x] 失败不会退回 synthetic TF、fake odom、direct set pose 或 Gazebo truth control 兜底。


## P6.11 终极闭环修复 TODO（2026-06-22 当前主线）

状态修正：2026-06-22 之后，P6 不能再按早期 `2026-06-06` 记录视为完成。当前真实 hover task 以 `orchestration/sim` 的顶层 `summary.ok=true` 为唯一完成标准；`mission_summary.ok=true` 只说明 FSM 局部完成，不能替代顶层通过。

当前已确认的具体失败原因：

- `artifacts/sim/hover/20260622T002530Z`：Cartographer 未产出 `/slam/odom`，`/slam/odom=0`、`/slam/odom_corrected=0`、`/external_nav/odom=0`，`/navlab/slam/status.state=waiting_for_cartographer_tf`，`slam_backend.runtime.log` 连续出现 `Queue waiting for data: (0, imu)`。这说明该轮不是 hover 飞坏，而是 SLAM preflight 未通过。
- `artifacts/sim/hover/20260622T001644Z` 与 `artifacts/sim/hover/20260622T002027Z`：runtime correction 链路已能进入 ExternalNav/FCU，mission FSM 可到 `S12 landing_complete`，但 Gazebo review-only drift 分别约 `0.546m` 和 `0.733m`，均超过 `0.35m` gate，不能宣称 hover 成功。
- `artifacts/sim/hover/20260622T002027Z`：correction intent review-only consistency 不稳定，`counter_drift_cosine.min=0.388` 且 `intent_y_sign_flips=1`，说明不能继续把完整 XY correction 送入 ExternalNav。

禁止事项：

- [ ] 不允许降低或删除 `hover_gazebo_model_horizontal_drift` gate。
- [ ] 不允许用 Gazebo truth、官方 maze map runtime localizer、fixed XY prior、Foxglove display TF 或全局 runtime `/tf map -> base_link` 绕过问题。
- [ ] 不允许再调 hover 高度门槛、landing 阈值来掩盖横漂。
- [ ] 不允许只跑单测就宣称 P6 成功；必须用真实 hover artifact 的顶层 `summary.ok=true`。

### P6.11.1 SLAM odom preflight：先阻断无效 hover run

目标：正式 arm/takeoff 前先证明 Cartographer 已经真正输出 SLAM pose，避免 `/slam/odom=0` 时还跑满 90 秒并产生一堆假 blocker。

任务：

- [ ] 在 hover task 的真实 run 前置 gate 中检查 `/navlab/slam/status.ready == true`。
- [x] 检查 `/navlab/slam/status.output.odom_count > 0`。已在 result gate 中通过 `slam_odom_preflight_missing` 阻断 `odom_count=0`。
- [ ] 检查 `/navlab/slam/status.tf.present == true` 且 `frame_id=map`、`child_frame_id=base_link`。
- [ ] 检查 `/slam/odom` 在 preflight 窗口内至少有 N 条样本，且 frame contract 为 `map -> base_link`。
- [x] 若 Cartographer log 出现持续 `Queue waiting for data: (0, imu)`，summary 必须给出专门 blocker：`slam_cartographer_waiting_for_imu_queue`。
- [x] 若 `/navlab/slam/status.state=waiting_for_cartographer_tf` 超过阈值，summary 必须给出 blocker：`slam_cartographer_tf_not_ready`。
- [x] preflight 失败时必须 fail-fast，不进入 GUIDED/arm/takeoff。`hover_mission.py` 已增加 pre-arm `wait_ready` 35 秒 fail-fast，summary reason 为 `preflight_timeout`。

验收：

- [ ] 复现 `20260622T002530Z` 类问题时，run 在 preflight 阶段失败，blocker 指向 `slam_cartographer_waiting_for_imu_queue` 或 `slam_cartographer_tf_not_ready`，而不是 hover/takeoff/landing 一堆派生失败。
- [ ] preflight 通过时，`/slam/odom`、`/slam/odom_corrected`、`/external_nav/odom` 都有数据。
- [x] preflight 不读取 Gazebo truth，不改变 SLAM/ExternalNav/control 输入。

### P6.11.2 同窗口四源 XY 对齐：先判定到底是真漂还是坐标/映射错

目标：不要再只看单个漂移数字。必须在同一 hover window 中对齐四个位置源，确认 Gazebo review-only drift、FCU fused pose、ExternalNav 输入、corrected SLAM odom 的轴向、符号、尺度和时间窗是否一致。

任务：

- [x] 在 `summary.json` 增加 hover window 内四源 XY 对齐 section：`/gazebo/model/odometry`、`/ap/v1/pose/filtered`、`/external_nav/odom`、`/slam/odom_corrected`。
- [x] 对每个源记录 `sample_count`、`window_start/end`、`final_x/y`、`x_span/y_span`、`max_horizontal_drift_m`。
- [x] 计算四源两两方向余弦、尺度比、x/y sign、x/y swap 可疑度。
- [x] 检查 `/gazebo/model/odometry` 的 model/link 是否就是 ArduPilot 控制的 UAV 实体，而不是 sensor/link/其他 model。`20260622T013518Z` 证明 bridge 指向 `/model/{{ robot_name }}/odometry`，SDF model 为 `iris_with_lidar`，OdometryPublisher 与 ArduPilotPlugin 同在该 model，消息为 `odom -> base_link`。
- [x] 检查 MAVLink ExternalNav bridge 的 ENU/NED 与 x/y swap 映射是否和 `nav_msgs/Odometry` 官方语义一致。`hover_xy_alignment.gazebo_model_odometry_evidence.gazebo_xyz_to_ned_projection` 已按 SDF `gazeboXYZToNED=0 0 0 180 0 90` 输出 review-only 投影，确认方向问题主要来自 Gazebo XYZ/NED 比较方式，但幅度不一致仍存在。
- [x] 如果 Gazebo drift 与 FCU/ExternalNav drift 不一致，summary 必须输出 `hover_xy_evidence_disagreement`，不能继续直接调 correction。该 blocker 已提升到顶层 gate，但不删除 `hover_gazebo_model_horizontal_drift`。

验收：

- [x] 对 mission 完成但 Gazebo drift 超标的 run，summary 能明确显示是“真实模型漂移”还是“坐标/窗口/model 映射不一致”。`20260622T010115Z` 显示 Gazebo 与 FCU/ExternalNav/SLAM 方向相反且尺度不一致，因此当前先按证据不一致处理。
- [x] 若存在 x/y swap 或 ENU/NED 反号，必须给出具体 axis/sign blocker。当前 summary 已给出 raw pair direction mismatch，并给出 `projected_x=raw_y, projected_y=-raw_x` 投影后的方向/尺度对照。
- [ ] 若四源一致显示 Gazebo 模型真实漂移 >0.35m，才能进入 P6.11.3 correction 修复。


#### 2026-06-22 实测更新：`artifacts/sim/hover/20260622T010115Z`

- 顶层结果：`summary.ok=false`、`blocked=true`，不能宣称 hover 成功。
- mission/FSM 局部结果：`mission_summary.ok=true`、`takeoff_ack_ok=true`、`landing_ok=true`、hover body 通过，说明本轮不是 arm/takeoff/landing 主流程失败。
- SLAM preflight 结果：`/navlab/slam/status.ready=true`，`output.odom_count=964`，`slam_backend.runtime.log` 中 `cartographer_waiting_for_imu_queue_count=0`，说明本轮没有复现 `/slam/odom=0` 的 Cartographer 启动卡死。
- Gazebo review-only drift：`/gazebo/model/odometry` hover window `max_horizontal_drift_m=0.7169m`，超过 `0.35m`，所以原 `hover_gazebo_model_horizontal_drift` 仍保留。
- 四源 XY 对齐：`hover_xy_alignment.ok=false`，Gazebo final `(-0.429,-0.574)m`，FCU final `(-0.045,+0.189)m`，ExternalNav final `(-0.004,+0.059)m`，corrected SLAM final `(-0.004,+0.065)m`；Gazebo 与其他三源方向余弦为负，触发 `hover_xy_evidence_disagreement`。
- 结论：下一步不是继续调 hover 高度、landing、Gazebo drift 阈值或 correction 幅度；应先查 `/gazebo/model/odometry` 的 model/link/frame/window 是否代表同一个被 ArduPilot 控制的 UAV body。


#### 2026-06-22 实测更新：`artifacts/sim/hover/20260622T013518Z`

- 顶层结果：`summary.ok=false`、`blocked=true`，不能宣称 hover 成功。
- Gazebo evidence source：`hover_xy_alignment.gazebo_model_odometry_evidence.ok=true`，`bridge_gz_topic_name=/model/{{ robot_name }}/odometry`，预期展开为 `/model/iris_with_lidar/odometry`；SDF model `iris_with_lidar` 同时包含 `gz::sim::systems::OdometryPublisher` 与 `ArduPilotPlugin`，消息 frame 为 `odom -> base_link`。因此当前不能再把问题归因于 Gazebo odom 取了别的 model/link。
- ENU/NED/sign：SDF `gazeboXYZToNED=0 0 0 180 0 90` 的 review-only 投影公式为 `projected_x=raw_y, projected_y=-raw_x`。投影后 Gazebo 与 FCU/ExternalNav/SLAM 方向余弦约 `0.92-0.95`，说明 raw direction mismatch 主要是坐标系比较方式造成。
- 仍未解决的核心：投影不改变幅度。Gazebo projected magnitude `0.8436m`，ExternalNav `0.0377m`，corrected SLAM `0.0417m`，FCU `0.1891m`，尺度比只有约 `0.045/0.049/0.224`。因此四源仍不对齐，问题从“方向反号”收敛为“真实 Gazebo body 位移幅度没有被 ExternalNav/SLAM/FCU 反映”。
- correction 证据：`/external_nav/status.output.xy_yaw_source=/slam/odom_corrected`；`/slam/odom_corrected` hover drift `0.2417m`，而 scan-reference runtime drift `0.6765m`，且 intent consistency 有 x/y sign flip。下一步不能加大 correction 或放宽 gate，只能先让 correction fail-closed/稳定轴输出，不允许 corrected odom 掩盖 Gazebo body drift。

### P6.11.3 Correction 只能输出稳定轴/稳定投影，禁止完整 XY 硬修

目标：修正当前 intent y 方向反号/方向不稳定问题。只有通过 Phase 4A/4B 条件的稳定轴或稳定投影可以进入 runtime correction；4B consistency 不通过时 runtime 必须 fail-closed。

任务：

- [x] 将 runtime correction gate 与 4B consistency 规则绑定：`counter_drift_cosine`、`counter_drift_opposes_ratio`、`intent_direction_cosine`、`x/y sign flips`、`saturation_ratio` 未达标时不输出 correction。实现边界：runtime 不读取 Gazebo truth；若 `/navlab/scan_reference_drift/status` 没有明确给出 `phase4b_consistency_ok=true`，correction 必须 fail-closed。
- [x] 若某一轴出现 sign flip，只关闭该轴 correction，不因另一个稳定轴被误杀。
- [x] 若只有一个稳定轴，`/slam/odom_corrected` 只写该轴 measurement delta，另一个轴 passthrough。
- [x] 若双轴都稳定，才允许受限投影 correction，仍受 `max_correction_m` 和 `max_correction_step_m` 限幅。
- [x] correction status 必须记录 `allowed_axes`、`blocked_axes`、`axis_blockers`、`runtime_consistency_ok`、`phase4b_consistency_ok`。
- [x] 不允许通过增大 correction 幅度、降低 residual gate、关闭 low-observability gate 来压过不稳定 intent。本轮没有改 correction 幅度、residual gate、low-observability gate、hover 高度/landing 阈值或 Gazebo drift gate。

验收：

- [x] 构造 y sign flip 的单测，要求 y correction fail-closed、x 若稳定可继续输出：`test_runtime_correction_blocks_only_flipping_axis_when_other_axis_is_stable`。
- [x] 构造 counter-drift cosine 低的单测，要求 correction 全部 fail-closed：`TestSummarizeScanReferenceStatusHoverWindowBlocksWrongIntentDirection` 证明 4B intent consistency 会因反向一致性不足输出 blocker；runtime correction 侧缺失 `phase4b_consistency_ok=true` 时由 `test_runtime_correction_requires_phase4b_consistency_input` fail-closed。
- [x] 真实 hover 中若出现不稳定/缺失 4B consistency，summary 不得显示 correction 被应用。`20260622T015657Z` 中 `phase4b_consistency_ok=false`、`runtime_consistency_ok=false`、`blocked_axes=[x,y]`、`hover_window_correction_applied_count=0`、`corrected_count=0`。
- [ ] 若 correction 应用，summary 必须能证明 applied axis 与 review-only drift 反向一致。当前真实 run 仍 fail-closed，没有进入 correction applied；该项留到后续真正通过 4B 后再验收。

#### 2026-06-22 实测更新：`artifacts/sim/hover/20260622T015657Z`

- 顶层结果：`summary.ok=false`、`blocked=true`，不能宣称 hover 成功。顶层 blocker 为 `hover_gazebo_model_horizontal_drift`、三组 `hover_xy_alignment_direction_mismatch:*` 和 `hover_xy_evidence_disagreement`。
- mission/FSM 局部结果：`mission_summary.ok=true`、`takeoff_ack_ok=true`、`landing_ok=true`、ExternalNav/MAVLink 真实有数据；这只说明 arm/takeoff/hover/land 状态机局部跑通，不代表 P6 成功。
- correction fail-closed 证据：`scan_reference_correction.correction_status_sample_count=36`，`raw_correction_status_sample_count=179`，`correction_status_window_source=hover_status_phase_hover_hold`；summary 现在能从 rosbag hover window 直接读出 correction status，不再只看最后 probe。
- correction 未应用：`phase4b_consistency_ok=false`、`phase4b_consistency_source=missing_runtime_phase4b_consistency`、`runtime_consistency_ok=false`、`blocked_axes=[x,y]`、`axis_blockers.x/y=[scan_reference_runtime_saturation_ratio_high]`、`hover_window_correction_applied_count=0`、`corrected_count=0`、`passthrough_count=7049`。
- 安全边界证据：`uses_gazebo_truth_input=false`、`uses_known_map_input=false`、`writes_external_nav_odom=false`，`/slam/odom_corrected` 仍只是 SLAM-derived odom 输出，没有把 Gazebo truth 写进 ExternalNav。
- 仍未解决的问题：Gazebo review-only hover drift `max_horizontal_drift_m=0.7806m`，而 `/slam/odom_corrected` hover drift 约 `0.0249m`、ExternalNav 约 `0.0234m`、FCU pose 约 `0.0111m`；四源仍显示 Gazebo body 大漂而 FCU/EKF/SLAM 近零，P6 不能完成。

### P6.11.4 真实 hover 成功判据：一次完整闭环，不再用局部成功替代

目标：只有一个完整真实 hover artifact 同时满足 SLAM preflight、ExternalNav/FSM、四源 XY 对齐、correction consistency 和 Gazebo drift gate，P6 才能重新标记完成。

任务：

- [ ] 跑真实 hover：`cd orchestration/sim && env -u NAVLAB_SIM_OVERLAY_SOURCE_MODE NAVLAB_SIM_IMAGE_TAG=jazzy-latest GOCACHE=/tmp/go-cache timeout 900 go run ./cmd/navlab-sim run hover`。
- [ ] 检查顶层 `summary.ok == true`、`blocked == false`、`blockers == []`。
- [ ] 检查 `mission_summary.ok == true`、`takeoff_ack_ok == true`、FSM 到 `S12 landing_complete`。
- [ ] 检查 `/slam/odom > 0`、`/slam/odom_corrected > 0`、`/external_nav/odom > 0`、`/mavlink_external_nav/status.sent_count > 0`。
- [ ] 检查 Gazebo review-only hover drift `<= 0.10m`；`0.35m` 不再是可接受成功标准。
- [ ] 检查 correction status：若应用 correction，必须说明应用轴、限幅、方向一致性；若 fail-closed，必须说明原因。
- [ ] 检查 artifact 中明确 `uses_gazebo_truth_input=false`、`uses_known_map_input=false`、`writes_external_nav_odom=false`。

验收：

- [ ] 只有顶层 `summary.ok=true` 才能把 P6 重新标为完成。
- [ ] 如果只满足 `mission_summary.ok=true`，必须记录为“FSM 局部成功，P6 未完成”。
- [ ] 如果失败，下一步 TODO 必须指向唯一主 blocker，不允许继续无目标跑 hover。

## P6 完成标准

状态说明：以下早期勾选项保留为历史基线记录；2026-06-22 后必须额外完成 P6.11，且以真实 hover 顶层 `summary.ok=true` 为准。

P6 全部完成必须满足：

- [x] 官方 `iris_maze` bringup 未被替换。
- [x] P1 X2 `/scan` 链路仍 healthy。
- [x] P2 IMU/rangefinder 机制仍 healthy。
- [x] P3 SLAM backend 仍 healthy。
- [x] P4 FCU controller 和唯一 owner 仍 healthy。
- [x] P5 frame contract 仍 healthy。
- [x] `/slam/odom` 是 ExternalNav 输入。
- [x] ExternalNav 不使用 Gazebo truth。
- [x] ExternalNav 持续 healthy。
- [x] EKF/FCU local position 持续输出。
- [x] GUIDED、arm、takeoff 全部成功。
- [x] hover window 达到最小时长。
- [x] hover horizontal drift 小于阈值。
- [x] hover altitude error 小于阈值。
- [x] hover yaw drift 小于阈值。
- [x] stop drift 小于阈值。
- [x] direct set pose 计数为 0。
- [x] Gazebo truth 没有进入控制、规划、SLAM 或 ExternalNav 输入。
- [x] rosbag required topics 全部有数据。
- [x] summary 明确标注 P6 已评价 hover。
- [x] summary 明确标注 P6 不代表探索完成。

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

### 2026-06-06 P6 文档初始化

- 命令：文档检查，未运行 acceptance
- 时间：2026-06-06
- artifact：无
- 结果：新增 P6 设计文档和 TODO 文档
- blocker：P6 orchestration task、ExternalNav hover gate、hover rosbag profile 和 acceptance 尚未实现
- 备注：P6.0 文档和边界已完成；后续从 P6.1 配置和 P6.2 ExternalNav bridge gate 开始实现。

### 2026-06-06 P6 实现和验收通过

- 命令：`python3 -m py_compile orchestration/src/config.py orchestration/src/tasks/slam_hover.py orchestration/src/tasks/fcu_controller.py orchestration/src/cli.py orchestration/src/tasks/registry.py`
- 时间：2026-06-06
- artifact：无
- 结果：通过
- blocker：无
- 备注：P6 orchestration、runtime config、rosbag profile 和 CLI 入口可静态加载。

- 命令：`uv run --project orchestration pytest orchestration/tests/test_config.py`
- 时间：2026-06-06
- artifact：无
- 结果：45 passed
- blocker：无
- 备注：覆盖 P6 配置、registry、rosbag profile、truth 输入禁用和 hover gate blocker；P4 owner/direct set pose blocker 继续作为 P6 前置 gate 复用。

- 命令：`uv run --project orchestration python orchestration/main.py slam-hover-doctor`
- 时间：2026-06-06
- artifact：`artifacts/ros/navlab_slam_hover_doctor/20260606_200908/summary.json`
- 结果：`ok=true`，`blocked=false`，`blockers=[]`
- blocker：无
- 备注：doctor 确认 P6 不允许 Gazebo truth 作为控制、规划、SLAM 或 ExternalNav 输入。

- 命令：`uv run --project orchestration python orchestration/main.py slam-hover-acceptance 90`
- 时间：2026-06-06
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260606_201653/summary.json`
- 结果：`ok=true`，`blocked=false`，`blockers=[]`
- blocker：无
- 备注：`/slam/odom -> /external_nav/status -> FCU local position -> hover` 真实 gate 通过；rosbag required topics 全部有数据；`uses_gazebo_truth_as_input=false`；`hover_claim=evaluated`；`exploration_claim=not_evaluated`。hover window 水平漂移约 0.014m，高度误差约 0.040m，yaw 漂移约 0.001rad，ExternalNav rate 约 70.8Hz，FCU local position rate 约 16.4Hz。

### 2026-06-16 P14 rangefinder 边界更新

- P6 后续验收必须引用 `docs/scenarios/indoor/todos/P14_benewake_rangefinder_sitl_todo.md`。
- FCU rangefinder 输入必须来自 `RNGFND1_TYPE=20` + `SERIAL7_PROTOCOL=9` + NavLab Benewake PTY emulator + `serial7:=uart:/tmp/navlab_benewake_tfmini:115200`，不能再由 Python/Gazebo sensor runtime 发送 MAVLink `DISTANCE_SENSOR`。`sim:benewake_tfmini` 在 2026-06-16 live 中触发 ArduPilot FPE，作为失败路径保留在 P14 审计中。
- `/rangefinder/down/range` 只作为 ROS observation/height-estimator/replay topic；P6 hover 通过条件必须记录 `rangefinder_simulation_fidelity=benewake_serial_emulated`。

### 2026-06-22 P6.11.5 有效 hover run 前置链路：down rangefinder scan bridge

背景：`artifacts/sim/hover/20260622T022825Z` 不是有效 hover/correction 结论。它在起飞前传感器链路断了：`/rangefinder/down/scan_ideal=0`，导致 `/rangefinder/down/range=0`、`/height/estimate=0`、`/external_nav/odom=0`，probe 被 kill。该 run 不能用于判断 hover 是否成功。

任务：

- [x] 确认 `model_overlay.sdf` 已生成 down-facing `gpu_lidar`，topic 为 `/rangefinder/down/scan_ideal`。
- [x] 确认 `gazebo_sensor_runtime.toml` 已启用 `down_rangefinder.enabled=true`，输入 topic 为 `/rangefinder/down/scan_ideal`。
- [x] 确认旧 `bridge_override.yaml` 没有 `/rangefinder/down/scan_ideal` bridge，导致 ROS 侧输入为 0。
- [x] 在 `WriteBridgeOverride` 中补 `rangefinder/down/scan_ideal` 的 `GZ_TO_ROS` LaserScan bridge。
- [x] 补 helper 测试，防止以后 bridge override 再漏掉 down rangefinder scan。
- [x] dry-run 检查新 artifact 的 `bridge_override.yaml` 确实包含该 bridge。`artifacts/sim/hover/20260622T024219Z` 已确认。
- [ ] 跑真实 hover，要求 `/rangefinder/down/range > 0`、`/height/estimate > 0`、`/external_nav/odom > 0`，否则仍视为无效 run。
- [ ] 若 run 有效，再回到 P6.11.4 顶层 `summary.ok=true` 判据；若仍失败，只记录唯一主 blocker，不把局部 mission 成功当 P6 成功。

边界：本项只修传感器 bridge 断链；不改 hover 高度门槛、landing 阈值、Gazebo drift gate、Foxglove display TF、全局 runtime TF、Gazebo truth 输入或官方 map runtime localizer。

### 2026-06-22 P6.11.6 Cartographer hover odometry input：只用 /scan 派生 prior，不绕过 SLAM

背景：`artifacts/sim/hover/20260622T024248Z` 已经恢复有效传感器链路，但顶层仍失败。按 hover_hold 窗口离线解析：`/trajectory_node_list` span 约 `0.074m`，`/slam/odom` span 约 `0.068m`，而 `/scan` estimator 约 `0.693m`、Gazebo review-only drift 约 `0.601m`。因此当前不是 ExternalNav 丢 Cartographer 输出，而是 Cartographer local SLAM 没估出 `/scan` 中可见横移。

任务：

- [x] 从有效 run 中确认 `/trajectory_node_list`、`/submap_list` 已记录，能做 Cartographer 内部诊断。
- [x] 按 hover_hold window 离线解析 Cartographer debug topic，确认 Cartographer 内部轨迹近零。
- [x] 查官方路径：Cartographer 支持 `use_odometry=true` + `/odom` `nav_msgs/Odometry` 输入。
- [x] 新增只由 `/scan` 生成的 Cartographer odometry prior：`/cartographer/odometry_input`，status `/navlab/scan_reference_cartographer_odom/status`。
- [x] 该 prior 禁止 hover_hold reset，避免 Cartographer odometry 输入跳变。
- [x] hover Cartographer lua 改为 `use_odometry=true`，并在注释中声明不是 Gazebo truth、不是 fixed XY prior、不是官方 maze-map localizer。
- [x] ExternalNav 仍只读 `/slam/odom_corrected`，不直接读 scan-reference prior。
- [x] 单测：hover lua、runtime artifact、execution plan、slam helper spec 全部通过。
- [x] dry-run：确认 `scan_reference_cartographer_odom_runtime.py`、runtime service、`/cartographer/odometry_input` required topic 全部落盘。`artifacts/sim/hover/20260622T025547Z` 已确认。
- [ ] 真实 hover：若 `/cartographer/odometry_input > 0` 且 Cartographer hover span 仍近零，则该路线失败，下一步只能继续查 Cartographer 对 odom input 的消费/时间戳/frame；不得改 drift gate 或加大 correction。

边界：本阶段不使用 Gazebo truth `/odometry`，不使用官方 maze map runtime localizer，不使用 fixed XY prior，不改 Foxglove/global TF，不放宽 `hover_gazebo_model_horizontal_drift`，不靠增大 correction 幅度硬压。

补充结果：`artifacts/sim/hover/20260622T025620Z` 证明 `/cartographer/odometry_input` 已发布并被 Cartographer 接收，但 hover window 中 Cartographer trajectory 仍近零。因此 P6.11.6 增加参数修复：开启 `POSE_GRAPH.optimize_every_n_nodes=30`，并设置 pose graph odometry/local_slam weights，让 `/scan` 派生 odom 不只作为 extrapolator hint，而是进入优化约束。下一次真实 run 必须检查 `/cartographer/odometry_input`、`/trajectory_node_list`、`/slam/odom` 三者在 hover window 的 span 是否拉齐。

### 2026-06-22 P6.11.7 当前根因收敛：correction fallback 不能绕过 cap

最新有效 run 证据：

- `artifacts/sim/hover/20260622T034353Z`：XY alignment 已通过，唯一 blocker 为 `hover_gazebo_model_horizontal_drift=0.3637m`，只超 `0.35m` 约 `0.0137m`；mission/takeoff/landing/rangefinder 均通过。
- `artifacts/sim/hover/20260622T034706Z`：把 correction 启动等待从 20 samples 降到 8 samples 后，correction 更早 active（`first_intent_active_offset_sec=5.66`），但 Gazebo drift 反而变成 `0.5043m`。
- 该 run 暴露真 bug：summary 里 `max_correction_m=0.25`，但 measurement fallback 输出 `measurement_delta_x_m=-0.5935`、`measurement_delta_y_m=0.2620`，幅度约 `0.65m`。这说明 fallback 路径绕过了 correction cap，不符合“不能加大 correction 硬压”的边界。

已修复：

- [x] `navlab/sim/companion/nodes/scan_reference_correction.py` 的 measurement fallback 也必须经过 `_clamp_vector(..., max_correction_m)`。
- [x] `navlab/tests/companion/test_scan_reference_correction.py` 增加/更新断言：即使 scan measurement 为 `0.42m`，fallback 输出也必须被限制到 `0.25m`。
- [x] 定向测试通过：`uv run --project navlab --directory /home/nn/workspace/3588/world-model pytest navlab/tests/companion/test_scan_reference_correction.py navlab/tests/companion/test_scan_reference_drift.py -q` -> `18 passed`。
- [x] Go gate/helper 测试通过：`cd orchestration/sim && GOCACHE=/tmp/go-cache go test ./internal/tasks ./internal/tasks/helpers -count=1`。

下一步只允许验证，不允许继续调门槛：

- [ ] 跑一次真实 hover，先检查 `/navlab/scan_reference_correction/status.measurement_delta_magnitude_m <= 0.25` 是否真实成立。
- [ ] 如果 cap 仍不成立，说明 runtime 没吃到新脚本/镜像/生成 artifact，先查 runtime artifact，不继续改算法。
- [ ] 如果 cap 成立但仍 `hover_gazebo_model_horizontal_drift`，再查 correction 符号链路和 ENU/NED 映射；不能改 hover 高度、landing、Gazebo drift gate、Foxglove TF、official map、truth input 或 fixed prior。

### 2026-06-22 P6.11.8 hover 顶层通过

旧 0.35m gate 链路闭合 run：`artifacts/sim/hover/20260622T035140Z`

- 顶层：`summary.ok=true`、`blocked=false`、`status=TASK_STATUS_OK`、`blockerCodes=null`。
- Gazebo review-only drift：`max_horizontal_drift_m=0.3396m`，按旧 `0.35m` gate 曾通过，但按当前 `0.10m` 标准不再通过。
- Mission/FSM：`takeoff_ack_ok=true`、`land_command_accepted=true`、`landing_ok=true`、`disarmed=true`。
- 高度证据：hover altitude crosscheck `ok=true`；external_nav height `0.497m`、FCU local height `0.4935m`、rangefinder relative height `0.49m`。
- Rangefinder：`rangefinder_probe.ok=true`，`/rangefinder/down/range` 与 `/rangefinder/down/status` 均采样成功。
- XY evidence：`hover_xy_alignment.ok=true`、`blockers=[]`。
- Correction 安全边界：`correction_applied=true`、`phase4b_consistency_ok=true`、`runtime_consistency_ok=true`、`hover_window_applied_without_phase4b_count=0`、`hover_window_applied_without_runtime_consistency_count=0`。
- Correction cap 验证：`measurement_delta_magnitude_m=0.25`，等于 `max_correction_m=0.25`，确认 P6.11.7 的 fallback cap 修复已在 runtime 生效。

结论更新：本轮只能证明链路闭合和 cap 生效，不能再算最终 hover task 通过；当前最终标准改为 Gazebo review-only drift `<=0.10m`。不得删除本节前面的失败记录；它们解释了为什么之前多轮 run 没有成功：probe DDS 假失败、XY evidence frame 未归一化、scan estimator 未考虑 yaw、以及 measurement fallback 绕过 cap。

### 2026-06-22 P6.11.9 最终 hover 横漂标准收紧到 0.10m

用户确认 `0.35m` 室内横漂不可接受，不能作为最终成功标准。当前修改：

- [x] `hover_gazebo_model_horizontal_drift` 顶层 gate 从 `0.35m` 改为 `0.10m`。
- [x] `orchestration/sim/configs/tasks/hover.yaml` 的 `max_hover_horizontal_drift_m` 从 `0.35` 改为 `0.10`。
- [x] `DefaultSlamHoverSpec()` 和 sim config default 的 hover 水平漂移默认值从 `0.35` 改为 `0.10`。
- [x] 新增测试要求 `0.3396m` drift 必须触发 `hover_gazebo_model_horizontal_drift`，`0.095m` 才能通过。

结论：`artifacts/sim/hover/20260622T035140Z` 不再是最终成功 run；它只证明链路闭合、rangefinder/takeoff/landing/XY/correction cap 正常。下一步必须继续把 Gazebo review-only hover drift 压到 `<=0.10m`。

### 2026-06-22 P6.11.10 预热 correction 后仍失败：FCU 稳不等于 Gazebo body 稳

验证 run：`artifacts/sim/hover/20260622T041059Z`

- 顶层：`summary.ok=false`、`status=TASK_STATUS_BLOCKED`。
- 新 `0.10m` 标准下 blockers：`hover_gazebo_model_horizontal_drift`、`hover_xy_evidence_disagreement` 及 Gazebo 与 ExternalNav/FCU/SLAM corrected 的方向 mismatch。
- Gazebo review-only drift：`0.6998m`，远超 `0.10m`。
- Mission/FCU drift：`hover_drift.horizontal_drift_m=0.0607m`，按 FCU/EKF 自身看已小于 `0.10m`。
- Correction 确实提前：`hover_window_first_correction_allowed_offset_sec=0.121s`、`first_correction_intent_active_offset_sec=0.839s`，说明 preheat/settle 生效。
- 关键结论：提前 correction 只让 FCU/ExternalNav 估计看起来稳定，没让 Gazebo body truth 稳定；这正是要禁止的“估计稳但机体漂”。不能把延长 settle/preheat 当最终修复。

下一步：必须查 FCU 控制输出到 Gazebo body 的闭环，而不是继续调 gate 或让 ExternalNav 更早/更强地修。重点对比 hover_hold 内：`/ap/v1/cmd_vel`、MAVLink setpoint、motor/servo output、`/gazebo/model/odometry` 速度、`/navlab/fcu/local_position_pose`。如果 FCU 估计稳定但 Gazebo body 仍漂，问题在控制/物理执行或 Gazebo evidence/source，而不是 SLAM gate。

### 2026-06-22 P6.11.11 执行纪律重置：先按根因文档做，不再先改代码

根因执行文档：`docs/notes/hover_external_nav_frame_root_cause_plan_20260622.md`

规则：

- [ ] TODO A：旧成功链路坐标合同表完成前，不改代码。
- [ ] TODO B：当前链路坐标合同表完成前，不改代码。
- [ ] TODO C：`20260622T041059Z` 同窗四源数值对齐完成前，不改代码。
- [ ] TODO D：最小修复方案评审完成前，不改代码。
- [ ] TODO E：实现时只改 TODO D 指定文件，并先写单测。
- [ ] TODO F：真实 hover 验证必须以 `<=0.10m` Gazebo drift 为最终标准。

当前禁止事项：继续调 hover 高度、landing、Gazebo drift gate、SLAM quality gate、Foxglove/global TF、Gazebo truth runtime input、official map runtime localizer、fixed prior、以及没有证据的 correction 参数。
