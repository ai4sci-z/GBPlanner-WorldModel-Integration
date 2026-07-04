# P5 Frame contract 自动验收 TODO

## 目标

在 P0/P1/P2/P3/P4 已通过的基础上，自动验收 ROS frame、MAVLink/ArduPilot frame、Gazebo truth 诊断、scan 方向和传感器安装 frame 是否一致。P5 完成后，只能说明 frame contract 足以进入 P6 真实 SLAM hover gate；不能说明 hover 已完成，也不能说明探索任务已完成。

设计文档：

- `docs/scenarios/indoor/navlab_p5_frame_contract_design.md`

前置条件：

- `docs/scenarios/indoor/todos/P0_official_baseline_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P1_official_maze_x2_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P2_rangefinder_imu_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P3_slam_backend_quality_todo.md` 已通过。
- `docs/scenarios/indoor/todos/P4_fcu_state_machine_todo.md` 已通过。

总 roadmap：

- `docs/scenarios/indoor/navlab_master_roadmap.md`

## P5.0 文档和边界

任务：

- [x] 新增 P5 设计文档。
- [x] 新增 P5 TODO 文档。
- [x] 在 `docs/README.md` 中加入 P5 design / TODO 入口。
- [x] 在 master roadmap 中把 P5 TODO 从“待建”改成具体文档。
- [x] 文档明确 P5 不代表 hover 完成。
- [x] 文档明确 P5 不代表 ExternalNav hover 完成。
- [x] 文档明确 P5 不代表探索完成。
- [x] 文档明确 Gazebo truth 只能作为诊断，不能作为控制或规划输入。
- [x] 文档明确 P5 不允许 direct set pose。
- [x] 文档明确 P5 不能绕过 P4 唯一 setpoint owner。

验收：

- [x] P5 文档中没有把 Gazebo truth 当作控制来源。
- [x] P5 文档中没有把 direct set pose 当作允许路径。
- [x] P5 文档中明确 `hover_claim=not_evaluated`。
- [x] P5 文档中明确 `exploration_claim=not_evaluated`。

## P5.1 Frame contract 配置

任务：

- [x] 新增 P5 frame contract 配置段。
- [x] 配置 required frames：
  - `map`
  - `odom`
  - `base_link`
  - `imu_link`
  - `base_scan` 或 `laser_frame`
  - `rangefinder_down_frame`
- [x] 配置 expected TF chain，默认 `map -> odom -> base_link`。
- [x] 配置 sensor child frames，默认挂在 `base_link` 下。
- [x] 配置 scan topic，默认 `/scan`。
- [x] 配置 IMU topic，默认 `/imu`。
- [x] 配置 rangefinder topic，默认 `/rangefinder/down/range`。
- [x] 配置 FCU pose topic，默认 `/ap/v1/pose/filtered`。
- [x] 配置 FCU twist topic，默认 `/ap/v1/twist/filtered`。
- [x] 配置 SLAM odom topic，默认 `/slam/odom`。
- [x] 配置 Gazebo truth diagnostic topic，默认 `/odometry` 或官方等价 topic。
- [x] 配置 TF age、scan valid ratio、rangefinder height error 和方向一致性阈值。
- [x] summary 记录配置路径和 hash。

验收：

- [x] 配置可从 `orchestration/config.toml` 或 P5 runtime config 加载。
- [x] 缺 required frame 或 required topic 时 doctor blocked。
- [x] summary 能解释每个 frame 条件来自哪个 topic/transform。

## P5.2 TF graph probe

任务：

- [x] 实现或固化 TF graph probe。
- [x] 订阅 `/tf` 和 `/tf_static`。
- [x] 构建 TF parent/child graph。
- [x] 检查 required frames 存在。
- [x] 检查 `map -> odom -> base_link` 连通。
- [x] 检查 `base_link -> imu_link` 连通。
- [x] 检查 `base_link -> base_scan` 或 `base_link -> laser_frame` 连通。
- [x] 检查 `base_link -> rangefinder_down_frame` 连通。
- [x] 检查每个 child frame 只有一个 parent。
- [x] 检查 TF graph 无循环。
- [x] 检查 dynamic transform 最新年龄小于阈值。
- [x] 检查 static transform quaternion norm 接近 1。
- [x] 输出 `/navlab/frame_contract/status`。

验收：

- [x] `tf.ok=true`。
- [x] `tf.missing_frames=[]`。
- [x] `tf.parent_conflicts=[]`。
- [x] `tf.cycles=[]`。
- [x] `tf.latest_dynamic_age_sec` 小于配置阈值。
- [x] frame probe 失败时写入明确 blocker。

## P5.3 NED/ENU 和 FRD/FLU 转换检查

任务：

- [x] P5 不做二次 MAVLink NED/FRD 转换，把 `/ap/v1/*` 视为 ArduPilot ROS2 官方输出。
- [x] 检查 `/ap/v1/pose/filtered`、`/ap/v1/twist/filtered` 被录入 rosbag 且与 P4 controller 链路共存。
- [x] 检查 `base_link`、sensor frames 和 FCU pose 处于同一 frame contract。
- [x] summary 记录动态运动方向为 `direction_motion_claim=not_evaluated`，避免把 P5 误判为 P6 hover/motion gate。

验收：

- [x] P5 不在 `/ap/v1/*` 上重复执行 NED/ENU 或 FRD/FLU 转换。
- [x] 如果后续 P6/P7 要验动态方向，必须打开 `require_motion_direction_check=true` 或进入对应 hover/navigation gate。
- [x] P5 summary 明确记录 `direction_motion_claim=not_evaluated`。

## P5.4 Scan frame 和方向检查

任务：

- [x] 读取 `/scan`。
- [x] 检查 `/scan.header.frame_id`。
- [x] 检查 scan frame 在 TF tree 中。
- [x] 检查 `angle_min < angle_max`。
- [x] 检查 `angle_increment` 与角度范围一致。
- [x] 检查有效 range 比例。
- [x] 检查 scan front angle 可用，并把前向约定绑定到 `base_link +X`。
- [x] 检查 scan 不需要手动旋转 180 度才能叠到场景。
- [x] summary 记录前向点、距离、有效点比例和 forward direction 判断。

验收：

- [x] `scan.ok=true`。
- [x] `scan.frame_id` 等于配置允许的 laser frame。
- [x] `scan.forward_matches_base_link_x=true`。
- [x] `scan.valid_range_ratio` 大于配置阈值。
- [x] scan 方向错误时写入 blocker：`scan forward direction does not match base_link +X`。

## P5.5 IMU 和 rangefinder frame 检查

任务：

- [x] 检查 `/imu.header.frame_id`。
- [x] 检查 IMU 输入存在并有非零 rosbag 计数。
- [x] 检查 `imu_link` 挂到 `base_link`。
- [x] 检查 `/rangefinder/down/range.header.frame_id`。
- [x] 检查 `rangefinder_down_frame` 挂到 `base_link`。
- [x] 检查 rangefinder 测距方向向下。
- [x] 对照 Gazebo truth diagnostic 计算 rangefinder height error。
- [x] summary 记录 IMU frame、rangefinder frame 和 height error。

验收：

- [x] `imu.ok=true`。
- [x] `imu.frame_id == imu_link` 或配置允许值。
- [x] `/imu` rosbag message count 大于 0。
- [x] `rangefinder.ok=true`。
- [x] `rangefinder.frame_id == rangefinder_down_frame`。
- [x] `rangefinder.height_error_m` 小于配置阈值。

## P5.6 方向一致性诊断

任务：

- [x] 使用 P4 controller 执行 P5 的短窗口控制链路，不绕过唯一 owner。
- [x] 不直接发布 `/ap/v1/cmd_vel` 绕过 controller。
- [x] 不使用 Gazebo truth 作为控制输入。
- [x] 采集动作窗口内 FCU pose 相对位移。
- [x] 采集动作窗口内 SLAM `/slam/odom` 相对位移。
- [x] 采集动作窗口内 Gazebo truth diagnostic 相对位移。
- [x] P5 不强制执行动态运动方向判断，summary 写 `direction_motion_claim=not_evaluated`。
- [ ] P6/P7 中再比较 FCU pose、SLAM odom、Gazebo truth 的动态方向一致性。
- [ ] P6/P7 中再比较 yaw 正方向、TF 方向和 scan 角度方向。

验收：

- [x] `direction_consistency.ok=true`。
- [x] `direction_motion_claim=not_evaluated`。
- [x] `uses_gazebo_truth_as_input=false`。
- [x] `set_pose_count==0`。
- [x] `owner.unique=true`。
- [ ] 动态方向 match 由 P6/P7 gate 验证。

## P5.7 Rosbag 和 Foxglove

任务：

- [x] 新增 P5 rosbag profile。
- [x] required topics 至少包含：
  - `/tf`
  - `/tf_static`
  - `/ap/v1/time`
  - `/ap/v1/pose/filtered`
  - `/ap/v1/twist/filtered`
  - `/ap/v1/status`
  - `/ap/v1/cmd_vel`
  - `/scan`
  - `/imu`
  - `/rangefinder/down/range`
  - `/rangefinder/down/status`
  - `/slam/odom`
  - `/navlab/slam/status`
  - `/navlab/fcu/state`
  - `/navlab/fcu/controller/status`
  - `/navlab/fcu/setpoint/output`
  - `/navlab/fcu/owner/status`
  - `/navlab/frame_contract/status`
- [x] optional topics 包含：
  - `/clock`
  - `/map`
  - `/submap_list`
  - `/trajectory_node_list`
  - `/odometry`
  - `/external_nav/status`
  - `/navlab/x2/vendor_scan`
  - `/sim/x2/status`
- [x] Foxglove notes 说明 P5 只看 frame contract。
- [x] summary 记录 MCAP 路径。

验收：

- [x] rosbag profile summary 中 required topics 全部存在且 message count 大于 0。
- [x] MCAP 可回放 TF、scan、FCU pose、SLAM odom、rangefinder 和 frame status。
- [x] P5 summary 记录 `rosbag_profile.ok=true`。

## P5.8 Acceptance task

任务：

- [x] 新增 `navlab-frame-contract-doctor` orchestration task。
- [x] 新增 `navlab-frame-contract-acceptance` orchestration task。
- [x] orchestration CLI 增加同名 task；历史 justfile 便捷入口已回收。
- [x] acceptance 先验证 P0 official baseline。
- [x] acceptance 再验证 P1 X2 scan gate。
- [x] acceptance 再验证 P2 IMU/rangefinder gate。
- [x] acceptance 再验证 P3 SLAM backend gate。
- [x] acceptance 再验证 P4 FCU controller gate。
- [x] acceptance 启动 P5 frame probe。
- [x] summary 包含 `p5_frame_contract` section。
- [x] summary 包含 `tf` section。
- [x] summary 包含 `scan` section。
- [x] summary 包含 `imu` section。
- [x] summary 包含 `rangefinder` section。
- [x] summary 包含 `direction_consistency` section。
- [x] summary 包含 `hover_claim` 和 `exploration_claim`。

验收：

- [x] P0 official DDS 条件失败时，P5 blocked。
- [x] P1 X2 `/scan` 条件失败时，P5 blocked。
- [x] P2 IMU/rangefinder 条件失败时，P5 blocked。
- [x] P3 SLAM backend 条件失败时，P5 blocked。
- [x] P4 FCU controller 条件失败时，P5 blocked。
- [x] TF contract 失败时，P5 blocked。
- [x] scan direction 失败时，P5 blocked。
- [x] direction consistency 失败时，P5 blocked；当前 P5 默认不要求动态 motion match。
- [x] summary 把 P5 frame contract 和 P6 hover completion 分开。

## P5.9 测试

任务：

- [x] 增加 config 测试：P5 frame contract 配置可加载。
- [x] 增加 task registry 测试：P5 doctor/acceptance 已注册。
- [x] 增加 TF graph 测试：缺 required frame 不能通过。
- [x] 增加 TF graph 测试：parent conflict 不能通过。
- [x] 增加 TF graph 测试：cycle 不能通过。
- [x] 增加 scan 测试：frame 缺失不能通过。
- [x] 增加 scan 测试：forward 方向反了不能通过。
- [x] 增加 rangefinder 测试：frame 不向下不能通过。
- [x] 增加 blocker 测试：direct set pose 不能通过。
- [x] 增加 blocker 测试：Gazebo truth 作为输入不能通过。
- [x] 增加 rosbag profile 测试：P5 required topics 配置存在。

验收：

- [x] P5 相关单元测试通过。
- [x] 不影响 P0 official baseline 测试。
- [x] 不影响 P1 official maze X2 测试。
- [x] 不影响 P2 rangefinder/IMU 测试。
- [x] 不影响 P3 SLAM backend 测试。
- [x] 不影响 P4 FCU controller 测试。

## P5.10 执行顺序

建议执行：

```text
1. uv run --project orchestration python orchestration/main.py official-baseline-acceptance 30
2. uv run --project orchestration python orchestration/main.py official-maze-x2-acceptance 45
3. uv run --project orchestration python orchestration/main.py rangefinder-imu-acceptance 60
4. uv run --project orchestration python orchestration/main.py slam-backend-acceptance 90
5. uv run --project orchestration python orchestration/main.py fcu-controller-acceptance 90
6. uv run --project orchestration python orchestration/main.py frame-contract-doctor
7. uv run --project orchestration python orchestration/main.py frame-contract-acceptance 90
```

验收：

- [x] 每一步失败都能在 summary.blockers 中定位到具体层级。
- [x] 失败不会退回 synthetic TF、fake odom、direct set pose 或 Gazebo truth control 兜底。

## P5 完成标准

P5 全部完成必须满足：

- [x] 官方 `iris_maze` bringup 未被替换。
- [x] P1 X2 `/scan` 链路仍 healthy。
- [x] P2 IMU/rangefinder 机制仍 healthy。
- [x] P3 SLAM backend 仍 healthy。
- [x] P4 FCU controller 和唯一 owner 仍 healthy。
- [x] `map -> odom -> base_link` 连通。
- [x] `base_link -> imu_link` 连通。
- [x] `base_link -> base_scan` 或 `base_link -> laser_frame` 连通。
- [x] `base_link -> rangefinder_down_frame` 连通。
- [x] TF graph 无循环。
- [x] child frame parent 唯一。
- [x] dynamic TF 最新年龄在阈值内。
- [x] `/scan` frame 正确。
- [x] `/scan` 前向方向匹配 `base_link +X`。
- [x] IMU frame 正确。
- [x] rangefinder frame 正确且测距方向向下。
- [ ] FCU pose、SLAM odom、Gazebo truth 诊断动态方向一致，由 P6/P7 验证。
- [x] direct set pose 计数为 0。
- [x] Gazebo truth 没有进入控制、规划或 ExternalNav 输入。
- [x] rosbag required topics 全部有数据。
- [x] summary 明确标注 P5 不代表 hover 完成。
- [x] summary 明确标注 P5 不代表探索完成。

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

### 2026-06-06 P5 文档初始化

- 命令：文档检查，未运行 acceptance
- 时间：2026-06-06
- artifact：无
- 结果：新增 P5 设计文档和 TODO 文档
- blocker：P5 orchestration task、frame probe、rosbag profile 和 acceptance 尚未实现
- 备注：P5.0 文档和边界已完成；后续从 P5.1 配置和 P5.2 TF graph probe 开始实现。

### 2026-06-06 P5 自动验收完成

- 命令：`python3 -m py_compile orchestration/src/config.py orchestration/src/tasks/frame_contract.py orchestration/src/cli.py orchestration/src/tasks/registry.py`
- 时间：2026-06-06
- artifact：无
- 结果：通过
- blocker：无
- 备注：P5 task、CLI、registry 和配置模块语法检查通过。

- 命令：`uv run --project orchestration pytest orchestration/tests/test_config.py`
- 时间：2026-06-06
- artifact：无
- 结果：`41 passed`
- blocker：无
- 备注：覆盖 P5 配置、registry、rosbag profile 和 blocker 单元测试。

- 命令：`uv run --project orchestration python orchestration/main.py frame-contract-doctor`
- 时间：2026-06-06
- artifact：`artifacts/ros/navlab_frame_contract_doctor/20260606_175333/summary.json`
- 结果：通过，`ok=true`
- blocker：无
- 备注：P5 doctor 确认 frame contract 配置和 truth/control claim 没有违反边界。

- 命令：`uv run --project orchestration python orchestration/main.py frame-contract-acceptance 90`
- 时间：2026-06-06
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260606_180445/summary.json`
- 结果：通过，`ok=true`，`blocked=false`，`rosbag_profile.ok=true`
- blocker：无
- 备注：`tf.ok=true`，`scan.ok=true`，`imu.ok=true`，`rangefinder.ok=true`，`direction_consistency.ok=true`；`direction_motion_claim=not_evaluated`，动态 hover/motion 方向留给 P6/P7。
