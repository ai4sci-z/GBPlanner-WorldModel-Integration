# P7 官方 maze 小范围运动 gate TODO

## 目标

在 P0-P6 已通过的基础上，验收真实 SLAM `/slam/odom` 通过 ExternalNav 进入
ArduPilot EKF 后，FCU 是否能在官方 maze/Iris 场景中通过唯一 controller
执行 forward、back、yaw scan 和 stop hold。P7 完成后，只能说明最小 motion
gate 已通过；不能说明自主探索、Nav2、覆盖率或 NavLab 自定义 world/model
迁移已完成。

设计文档：

- `docs/scenarios/indoor/navlab_p7_official_maze_motion_gate_design.md`

前置条件：

- `docs/scenarios/indoor/todos/P0_official_baseline_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P1_official_maze_x2_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P2_rangefinder_imu_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P3_slam_backend_quality_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P4_fcu_state_machine_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P5_frame_contract_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P6_slam_hover_gate_todo.md` 已通过。

总 roadmap：

- `docs/scenarios/indoor/navlab_master_roadmap.md`

## P7.0 文档和边界

任务：

- [x] 新增 P7 设计文档。
- [x] 新增 P7 TODO 文档。
- [x] 在 `docs/README.md` 中加入 P7 design / TODO 入口。
- [x] 在 master roadmap 中把 P7 TODO 从“待建”改成具体文档。
- [x] 文档明确 P7 是小范围运动 gate，不是 P8 探索 gate。
- [x] 文档明确 P7 不替换 NavLab 8 字形 world/model。
- [x] 文档明确 Gazebo truth 只能作为诊断，不能作为 SLAM、ExternalNav、规划或控制输入。
- [x] 文档明确 P7 不允许 direct set pose。
- [x] 文档明确 P7 必须保持 P4/P6 唯一 setpoint owner。
- [x] 文档明确 P7 必须复用 P6 hover readiness。

验收：

- [x] P7 文档中没有把 Gazebo truth 当作控制来源。
- [x] P7 文档中没有把 direct set pose 当作允许路径。
- [x] P7 文档中明确 `motion_claim=evaluated`。
- [x] P7 文档中明确 `exploration_claim=not_evaluated`。

## P7.1 配置

任务：

- [x] 新增 P7 motion gate 配置段。
- [x] 配置 rosbag profile，默认 `docker/profiles/navlab-motion-gate-rosbag-topics.txt`。
- [x] 配置 SLAM odom topic，默认 `/slam/odom`。
- [x] 配置 SLAM status topic，默认 `/navlab/slam/status`。
- [x] 配置 ExternalNav status topic，默认 `/external_nav/status`。
- [x] 配置 FCU pose topic，默认 `/ap/v1/pose/filtered`。
- [x] 配置 FCU twist topic，默认 `/ap/v1/twist/filtered`。
- [x] 配置 FCU command topic，默认 `/ap/v1/cmd_vel`。
- [x] 配置 rangefinder topic，默认 `/rangefinder/down/range`。
- [x] 配置 IMU topic，默认 `/imu`。
- [x] 配置 Gazebo truth diagnostic topic，默认 `/odometry`。
- [x] 配置 hover status topic，默认 `/navlab/hover/status`。
- [x] 配置 motion status topic，默认 `/navlab/motion/status`。
- [x] 配置 forward/back distance、speed、yaw scan angle 和 yaw rate。
- [x] 配置 stop hold window、final hold window 和 action timeout。
- [x] 配置 displacement、lateral error、altitude error、yaw error、clearance、stop drift、rate 和 latest age 阈值。
- [x] 配置 `uses_gazebo_truth_as_input=false`。

验收：

- [x] 配置可从 `orchestration/config.toml` 加载。
- [x] P7 runtime config 写入 artifact 并记录 hash。
- [x] 配置中如果允许 Gazebo truth 作为输入，doctor blocked。
- [x] 配置中如果 motion setpoint 输出绕过唯一 FCU controller，doctor blocked。

## P7.2 Motion intent 和 controller gate

任务：

- [x] 新增或固化 P7 motion intent schema。
- [x] motion intent 支持 `forward`、`back`、`yaw_scan`、`stop`、`final_hold`。
- [x] motion gate coordinator 只发布 motion intent，不直接发布 `/ap/v1/cmd_vel`。
- [x] FCU controller 把 motion intent 转换成唯一 setpoint output。
- [x] controller 未 ready 时拒绝 motion intent 并写明原因。
- [x] controller 输出 `/navlab/fcu/controller/status`。
- [x] controller 输出 `/navlab/fcu/setpoint/intent` 和 `/navlab/fcu/setpoint/output`。
- [x] owner status 输出 `/navlab/fcu/owner/status`。
- [x] 不允许 mission 或 probe 层直接发布 movement setpoint。

验收：

- [x] `owner.unique=true`。
- [x] `owner.set_pose_count==0`。
- [x] `owner.competing_publishers=[]`。
- [x] `/navlab/fcu/setpoint/intent` message count 大于 0。
- [x] `/navlab/fcu/setpoint/output` message count 大于 0。
- [x] `/navlab/motion/status` message count 大于 0。
- [x] controller readiness 不满足时，P7 blocked。

## P7.3 P6 hover 前置 gate

任务：

- [x] P7 acceptance 先验证或复用 P6 hover readiness。
- [x] 检查 GUIDED、arm、takeoff 成功。
- [x] 检查 `/slam/odom` healthy。
- [x] 检查 ExternalNav healthy。
- [x] 检查 `/ap/v1/pose/filtered` 和 `/ap/v1/twist/filtered` healthy。
- [x] 检查 rangefinder 和 IMU healthy。
- [x] 检查 hover settle 后 drift 在阈值内。
- [x] summary 记录 P6 hover prerequisite section。

验收：

- [x] `p6_hover_prerequisite.ok=true`。
- [x] `slam_odom.ok=true`。
- [x] `external_nav.ok=true`。
- [x] `fcu.local_position_ok=true`。
- [x] `rangefinder.ok=true`。
- [x] `imu.ok=true`。
- [x] P6 hover 前置不满足时，P7 blocked。

## P7.4 Forward/back motion gate

任务：

- [x] 执行 forward action。
- [x] forward action 后执行 stop hold。
- [x] 执行 back action。
- [x] back action 后执行 stop hold。
- [x] 用 FCU local position 统计 forward/back 主方向位移。
- [x] 用 SLAM odom 统计 forward/back 主方向位移。
- [x] 用 Gazebo truth diagnostic 记录对照位移，但不作为在线决策输入。
- [x] 统计 lateral error。
- [x] 统计高度误差。
- [x] 统计每个 stop hold 的 stop drift。
- [x] summary 记录 action start/end time、目标、实际位移、误差和 blocker。

验收：

- [x] `motion_actions.forward.ok=true`。
- [x] `motion_actions.forward.displacement_m >= min_forward_displacement_m`。
- [x] `motion_actions.forward.displacement_m <= max_forward_displacement_m`。
- [x] `motion_actions.forward.lateral_error_m <= max_lateral_error_m`。
- [x] `motion_actions.forward.stop_drift_m <= max_stop_drift_m`。
- [x] `motion_actions.back.ok=true`。
- [x] `motion_actions.back.displacement_m >= min_back_displacement_m`。
- [x] `motion_actions.back.displacement_m <= max_back_displacement_m`。
- [x] `motion_actions.back.lateral_error_m <= max_lateral_error_m`。
- [x] `motion_actions.back.stop_drift_m <= max_stop_drift_m`。
- [x] forward/back 方向错误或位移超阈值时，P7 blocked。

## P7.5 Yaw scan gate

任务：

- [x] 执行 yaw scan action。
- [x] yaw scan 后执行 stop hold。
- [x] 可选执行 yaw recenter 或反向 yaw scan。
- [x] 用 FCU pose 统计 yaw delta。
- [x] 用 SLAM odom 统计 yaw delta。
- [x] 用 `/scan` 检查 yaw 后 scan 方向和墙体几何仍可解释。
- [x] 统计 yaw stop drift。
- [x] summary 记录 yaw target、actual yaw delta、yaw direction 和 stop drift。

验收：

- [x] `motion_actions.yaw_scan.ok=true`。
- [x] `motion_actions.yaw_scan.yaw_delta_rad >= min_yaw_delta_rad`。
- [x] `motion_actions.yaw_scan.yaw_delta_rad <= max_yaw_delta_rad`。
- [x] `motion_actions.yaw_scan.stop_drift_m <= max_stop_drift_m`。
- [x] yaw 方向错误或 yaw delta 超阈值时，P7 blocked。

## P7.6 Clearance、stop guard 和碰撞诊断

任务：

- [x] motion window 中持续读取最终 vendor `/scan`。
- [x] 统计 front/side/rear clearance。
- [x] 统计有效 range 比例。
- [x] 检查 motion window 中 min clearance 大于阈值。
- [x] 检查 stop guard 状态可观测。
- [x] 检查 Gazebo 或 summary 中无碰撞诊断。
- [x] 如果碰撞 topic 不存在，summary 必须明确 collision evidence source。
- [x] 不允许用 `/scan_ideal` 代替 `/scan` 做 completion。

验收：

- [x] `clearance.ok=true`。
- [x] `clearance.min_scan_range_m >= min_clearance_m`。
- [x] `/scan` message count 大于 0。
- [x] `/scan` 来自 vendor driver 链路。
- [x] clearance 低于阈值时，P7 blocked。
- [x] collision diagnostic 表示发生碰撞时，P7 blocked。

## P7.7 SLAM、ExternalNav 和 FCU motion health

任务：

- [x] motion window 中检查 `/slam/odom` rate 和 latest age。
- [x] motion window 中检查 `/slam/odom` jump 和 yaw jump。
- [x] motion window 中检查 `/navlab/slam/status` healthy。
- [x] motion window 中检查 `/external_nav/status` healthy。
- [x] motion window 中检查 ExternalNav sent rate 和 latest sent age。
- [x] motion window 中检查 FCU local position rate 和 latest age。
- [x] motion window 中检查 rangefinder 和 IMU latest age。
- [x] summary 记录每个 action 内的 health slices。

验收：

- [x] `slam_odom.rate_hz >= min_slam_odom_rate_hz`。
- [x] `slam_odom.latest_age_sec <= max_latest_age_sec`。
- [x] `external_nav.rate_hz >= min_external_nav_rate_hz`。
- [x] `external_nav.latest_sent_age_sec <= max_latest_age_sec`。
- [x] `fcu.local_position_rate_hz >= min_fcu_local_position_rate_hz`。
- [x] SLAM、ExternalNav 或 FCU stale 时，P7 blocked。

## P7.8 Rosbag 和 Foxglove

任务：

- [x] 新增 P7 rosbag profile。
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
  - `/navlab/motion/status`
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
  - `/navlab/vehicle/markers`
- [x] Foxglove notes 说明 P7 固定参考系使用 `map`。
- [x] Foxglove notes 说明 `/odometry` 只用于诊断对照。
- [x] Foxglove notes 说明如何对照 motion status、setpoint output、FCU pose、SLAM odom 和 scan。
- [x] summary 记录 MCAP 路径。

验收：

- [x] rosbag profile summary 中 required topics 全部存在且 message count 大于 0。
- [x] MCAP 可回放 TF、scan、SLAM odom、FCU pose、ExternalNav status、hover status 和 motion status。
- [x] P7 summary 记录 `rosbag_profile.ok=true`。

## P7.9 Acceptance task

任务：

- [x] 新增 `navlab-motion-gate-doctor` orchestration task。
- [x] 新增 `navlab-motion-gate-acceptance` orchestration task。
- [x] orchestration CLI 增加同名 task；历史 justfile 便捷入口已回收。
- [x] acceptance 先验证 P0 official baseline。
- [x] acceptance 再验证 P1 X2 scan gate。
- [x] acceptance 再验证 P2 IMU/rangefinder gate。
- [x] acceptance 再验证 P3 SLAM backend gate。
- [x] acceptance 再验证 P4 FCU controller gate。
- [x] acceptance 再验证 P5 frame contract gate。
- [x] acceptance 再验证 P6 hover gate。
- [x] acceptance 启动 P7 motion gate coordinator。
- [x] summary 包含 `p7_motion_gate` section。
- [x] summary 包含 `p6_hover_prerequisite` section。
- [x] summary 包含 `motion_actions` section。
- [x] summary 包含 `clearance` section。
- [x] summary 包含 `slam_odom` section。
- [x] summary 包含 `external_nav` section。
- [x] summary 包含 `fcu` section。
- [x] summary 包含 `owner` section。
- [x] summary 包含 `motion_claim=evaluated`。
- [x] summary 包含 `exploration_claim=not_evaluated`。

验收：

- [x] P0 official DDS 条件失败时，P7 blocked。
- [x] P1 X2 `/scan` 条件失败时，P7 blocked。
- [x] P2 IMU/rangefinder 条件失败时，P7 blocked。
- [x] P3 SLAM backend 条件失败时，P7 blocked。
- [x] P4 FCU controller 条件失败时，P7 blocked。
- [x] P5 frame contract 条件失败时，P7 blocked。
- [x] P6 hover 条件失败时，P7 blocked。
- [x] forward/back/yaw/stop 条件失败时，P7 blocked。
- [x] summary 把 P7 motion completion 和 P8 exploration completion 分开。

## P7.10 测试

任务：

- [x] 增加 config 测试：P7 motion gate 配置可加载。
- [x] 增加 task registry 测试：P7 doctor/acceptance 已注册。
- [x] 增加 blocker 测试：P6 hover 前置失败不能通过。
- [x] 增加 blocker 测试：Gazebo truth 作为输入不能通过。
- [x] 增加 blocker 测试：direct set pose 不能通过。
- [x] 增加 blocker 测试：多个 setpoint owner 不能通过。
- [x] 增加 motion 测试：forward 位移方向错误不能通过。
- [x] 增加 motion 测试：back 位移方向错误不能通过。
- [x] 增加 motion 测试：yaw delta 超阈值不能通过。
- [x] 增加 stop drift 测试：stop drift 超阈值不能通过。
- [x] 增加 clearance 测试：min clearance 低于阈值不能通过。
- [x] 增加 rosbag profile 测试：P7 required topics 配置存在。

验收：

- [x] P7 相关单元测试通过。
- [x] 不影响 P0 official baseline 测试。
- [x] 不影响 P1 official maze X2 测试。
- [x] 不影响 P2 rangefinder/IMU 测试。
- [x] 不影响 P3 SLAM backend 测试。
- [x] 不影响 P4 FCU controller 测试。
- [x] 不影响 P5 frame contract 测试。
- [x] 不影响 P6 SLAM hover 测试。

## P7.11 执行顺序

建议执行：

```text
1. uv run --project orchestration python orchestration/main.py official-baseline-acceptance 30
2. uv run --project orchestration python orchestration/main.py official-maze-x2-acceptance 45
3. uv run --project orchestration python orchestration/main.py rangefinder-imu-acceptance 60
4. uv run --project orchestration python orchestration/main.py slam-backend-acceptance 90
5. uv run --project orchestration python orchestration/main.py fcu-controller-acceptance 90
6. uv run --project orchestration python orchestration/main.py frame-contract-acceptance 90
7. uv run --project orchestration python orchestration/main.py slam-hover-acceptance 90
8. uv run --project orchestration python orchestration/main.py motion-gate-doctor
9. uv run --project orchestration python orchestration/main.py motion-gate-acceptance 120
```

验收：

- [x] 每一步失败都能在 summary.blockers 中定位到具体层级。
- [x] 失败不会退回 synthetic TF、fake odom、direct set pose 或 Gazebo truth control 兜底。

## P7 完成标准

P7 全部完成必须满足：

- [x] 官方 `iris_maze` bringup 未被替换。
- [x] P1 X2 `/scan` 链路仍 healthy。
- [x] P2 IMU/rangefinder 机制仍 healthy。
- [x] P3 SLAM backend 仍 healthy。
- [x] P4 FCU controller 和唯一 owner 仍 healthy。
- [x] P5 frame contract 仍 healthy。
- [x] P6 SLAM hover gate 仍 healthy。
- [x] `/slam/odom` 是 ExternalNav 输入。
- [x] ExternalNav 不使用 Gazebo truth。
- [x] forward action 位移方向和幅度符合阈值。
- [x] back action 位移方向和幅度符合阈值。
- [x] yaw scan 方向和幅度符合阈值。
- [x] 每个 stop hold 的 stop drift 小于阈值。
- [x] motion window 中 scan clearance 大于阈值。
- [x] motion window 中 SLAM、ExternalNav 和 FCU local position 持续 healthy。
- [x] direct set pose 计数为 0。
- [x] Gazebo truth 没有进入控制、规划、SLAM 或 ExternalNav 输入。
- [x] rosbag required topics 全部有数据。
- [x] summary 明确标注 P7 已评价小范围 motion。
- [x] summary 明确标注 P7 不代表探索完成。

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

### 2026-06-07 P7 文档初始化

- 命令：文档检查，未运行 acceptance
- 时间：2026-06-07
- artifact：无
- 结果：新增 P7 设计文档和 TODO 文档
- blocker：P7 orchestration task、motion gate coordinator、motion rosbag profile 和 acceptance 尚未实现
- 备注：P7.0 文档和边界已完成；后续从 P7.1 配置和 P7.2 motion intent/controller gate 开始实现。


### 2026-06-07 P7 motion gate acceptance 通过

- 命令：`timeout 420 uv run --project orchestration python orchestration/main.py motion-gate-acceptance 120`
- 时间：2026-06-07
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260607_115010/summary.json`
- 结果：通过，`ok=true`，`blockers=[]`，`motion_claim=evaluated`，`exploration_claim=not_evaluated`
- blocker：无
- 备注：rangefinder preflight 和正式 probe 均收到数据；rosbag profile `ok=true`，required topics 无缺失且无 zero-count；关键计数包括 `/ap/v1/cmd_vel=766`、`/rangefinder/down/range=1666`、`/rangefinder/down/scan_ideal=1666`、`/navlab/motion/status=80`、`/slam/odom=4978`；motion gate 中 forward/back/yaw 均 `ok=true`，最小 scan clearance `0.892m >= 0.35m`，FCU local position rate `1.93Hz >= 1.5Hz`。

### 2026-06-07 P7 coordinator/controller split 后验收通过

- 命令：`timeout 480 uv run --project orchestration python orchestration/main.py motion-gate-acceptance 120`
- 时间：2026-06-07
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260607_121115/summary.json`
- 结果：通过，`ok=true`，`blockers=[]`，`motion_claim=evaluated`，`exploration_claim=not_evaluated`
- blocker：无
- 备注：P7 coordinator 只发布 `/navlab/fcu/setpoint/intent` 和 `/navlab/motion/status`，`/ap/v1/cmd_vel` 由 `navlab_fcu_controller` 发布；rosbag profile `ok=true`，required topics 无缺失且无 zero-count；关键计数包括 `/ap/v1/cmd_vel=528`、`/navlab/fcu/setpoint/intent=1069`、`/navlab/fcu/setpoint/output=531`、`/navlab/hover/status=296`、`/navlab/motion/status=77`、`/slam/odom=4807`；forward/back/yaw 均 `ok=true`，yaw delta `0.450rad`，最小 scan clearance `0.887m >= 0.35m`。
