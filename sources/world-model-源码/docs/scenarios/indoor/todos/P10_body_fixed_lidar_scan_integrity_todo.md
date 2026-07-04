# P10 机体固连 lidar 姿态补偿与 scan integrity gate TODO

## 目标

P10 要在进入真机试飞前，证明机体固连 2D lidar 在 roll/pitch 扰动下不会静默污染 SLAM 输入。

核心交付：

- `/scan` 从 unchecked vendor scan 改为 attitude-validated scan。
- raw scan 保留在 `/navlab/x2/scan_raw`。
- scan integrity filter 能根据姿态、静态 TF、时间同步和高度约束做 accept/warn/clip/drop。
- normal profile 和 tilt fault-injection profile 都能通过 gate。
- summary/MCAP/Foxglove 能解释为什么 scan 可信，或者为什么被阻塞。

## P10.0 文档和边界

- [x] 新增 P10 设计文档。
- [x] 新增 P10 TODO 文档。
- [x] 在 `docs/README.md` 中加入 P10 design / TODO 入口。
- [x] 在 master roadmap 中把 P10 定义为机体固连 lidar 姿态补偿与 scan integrity gate。
- [x] 文档明确 P11 先做 2D scan 稳定化，P12 做 motor bias / ESC lag / vibration 鲁棒性仿真，探索策略优化后移。
- [x] 文档明确 P10 不使用 Gazebo truth 作为 scan 修正输入。
- [x] 文档明确 P10 首版优先 filter/clip/drop，不做假水平投影补偿。

文档自检：

- [x] P10 文档中没有把官方 maze 底图当作规划或控制输入。
- [x] P10 文档中没有要求机械云台。
- [x] P10 文档中没有把缺失姿态源 fallback 到 raw `/scan`。
- [x] P10 文档中明确 normal profile 和 fault-injection profile 都是完成标准。

## P10.1 Topic contract 重构

- [x] 增加 raw scan topic：`/navlab/x2/scan_raw`。
- [x] 增加 normalized scan topic：`/navlab/x2/scan_normalized`。
- [x] 把 `/scan` 的 owner 改为 scan integrity filter。
- [x] 确保 SLAM/Cartographer 只订阅 `/scan`，不订阅 raw scan。
- [x] 确保 exploration 只订阅 `/scan` 或 SLAM map，不订阅 raw scan。
- [x] 更新 rosbag profile，记录 raw scan、validated scan、status、events、attitude、TF 和 rangefinder。
- [x] 增加 owner 检查：`/scan` 只能有 integrity filter 一个 publisher。
- [x] 如果 raw scan 缺失、validated scan 缺失或 `/scan` owner 不正确，gate 直接 fail。

验收：

- [x] 正常运行时 `/navlab/x2/scan_raw` 有数据。
- [x] 正常运行时 `/scan` 有数据且非静态。
- [x] `/scan` publisher 唯一。
- [x] SLAM input contract 报告 `validated_scan=true`。

## P10.2 姿态源 selector 和 no-fallback contract

- [x] 在配置中显式声明 scan integrity attitude source。
- [x] 支持 `/imu/data` 作为正式姿态源。
- [x] 支持 `/ap/v1/pose/filtered` 或当前 FCU filtered pose equivalent 作为正式姿态源。
- [x] 明确禁止 Gazebo truth pose/attitude 作为正式姿态源。
- [x] 增加姿态源 allowlist 检查。
- [x] 增加姿态源 rate 检查。
- [x] 增加 attitude timestamp freshness 检查。
- [x] 增加 `max_attitude_source_age_ms`，姿态源沉默超时 blocker 为 `attitude_source_age_too_high`。
- [x] 多个姿态源同时配置时必须 fail，不能自动猜。
- [x] 姿态源缺失时必须 fail，不能 fallback 到 unchecked `/scan`。

验收：

- [x] summary 记录 `attitude_source`。
- [x] summary 记录 `attitude_source_is_truth=false`。
- [x] attitude source 缺失时 gate fail，blocker 包含 `missing_attitude_source`。
- [x] truth source 被配置时 gate fail，blocker 包含 `attitude_source_is_truth`。

## P10.3 scan integrity filter

- [x] 实现 scan integrity filter 节点或组件。
- [x] 读取 `base_link -> base_scan` 静态 TF。
- [x] 读取 scan timestamp，并同步最近的 attitude sample。
- [x] 计算每帧 roll、pitch、tilt。
- [x] 实现 `soft_tilt_deg` warn 逻辑。
- [x] 实现 `hard_tilt_deg` drop 逻辑。
- [x] 实现 scan/attitude time offset gate。
- [x] 输出 `/navlab/scan_integrity/status`。
- [x] 输出 `/navlab/scan_integrity/events`。
- [x] 不允许 filter 未运行时继续发布 raw `/scan`。

验收：

- [x] 正常小倾角时 status state 为 `accept` 或低比例 `warn`。
- [x] 超过 hard tilt 时 status state 为 `drop` 或 `blocked`。
- [x] `/scan` 中不会出现 hard tilt 的 unchecked scan。
- [x] status JSON 可被 summary parser 稳定解析。

## P10.4 floor-hit / ceiling-hit 风险裁剪

- [x] 读取 lidar height，优先使用 rangefinder/FCU 正式链路。
- [x] 缺少 height 时 gate fail，不能 fallback 到 Gazebo truth height。
- [x] 对每个 beam 计算 gravity frame 下的竖直分量。
- [x] 计算 floor intersection range。
- [x] 对明显可能打到地面的 beam 做 clip 或 drop。
- [x] 记录 `floor_hit_risk_beam_ratio`。
- [x] 记录 `clipped_beam_ratio`。
- [x] 增加 `max_clipped_beam_ratio` gate。
- [x] 不把地面 hit 几何投影成水平障碍。

验收：

- [x] 正常姿态下 `floor_hit_risk_beam_ratio <= max_floor_hit_risk_beam_ratio`。
- [x] 下俯 fault injection 时 floor-hit risk 上升。
- [x] 下俯超过阈值时 scan 被 clip/drop，而不是静默进入 SLAM。
- [x] summary 包含 floor-hit risk 指标。

## P10.5 Normal integrity profile

- [x] 增加 P10 normal acceptance/replay 命令。
- [x] 复用 P6 hover prerequisite。
- [x] 复用 P7 小范围 motion prerequisite。
- [x] 启动 scan integrity filter。
- [x] 执行短 forward/back/yaw movement。
- [x] 记录 raw scan、validated scan、attitude、TF、SLAM、FCU、status。
- [x] summary 聚合 tilt、drop、clip、time sync、scan rate。
- [x] normal profile 失败时 P10 总 gate fail。

验收：

- [x] normal profile `ok=true`。
- [x] `dropped_scan_ratio <= max_dropped_scan_ratio`。
- [x] `max_scan_attitude_time_offset_ms <= 50`。
- [x] SLAM odom healthy。
- [x] ExternalNav healthy。
- [x] FCU local position healthy。

## P10.6 Tilt fault-injection profile

- [x] 增加 test-only attitude bias injection 配置。
- [x] 支持 mild roll/pitch bias case。
- [x] 支持 hard roll/pitch bias case。
- [x] mild case 应触发 accept/warn，不应崩溃。
- [x] mild case 的 `dropped_scan_ratio <= max_dropped_scan_ratio`。
- [x] hard case 应触发 drop/blocked。
- [x] fault injection 事件写入 summary。
- [x] 如果 fault injection 没运行，P10 blocker 包含 `fault_injection_not_run`。
- [x] 如果 hard tilt 没被拒绝，P10 blocker 包含 `hard_tilt_not_rejected`。
- [x] hard bias removed 后 state 在恢复窗口内回到 `accept`。

验收：

- [x] summary 记录 `fault_injection_mode`。
- [x] summary 记录 `fault_injection_ok=true`。
- [x] hard tilt case 没有 unchecked scan 进入 `/scan`。
- [x] fault-injection MCAP 或 replay evidence 可复查。
- [x] bias injected -> hard drop -> bias removed -> state returns to accept。

## P10.7 Summary 和 blocker

- [x] summary 增加 `scan_integrity_claim=evaluated`。
- [x] summary 增加 `scan_integrity` 对象。
- [x] summary 记录 scan owner、raw topic、validated topic。
- [x] summary 记录 attitude source 和 source truth 状态。
- [x] summary 记录 `base_scan_static_tf_ok`。
- [x] summary 记录 tilt max/rms/count。
- [x] summary 记录 accepted/warn/clipped/dropped scan count。
- [x] summary 记录 dropped scan ratio。
- [x] summary 记录 floor-hit risk 指标。
- [x] summary 记录 fault-injection 结果。
- [x] blocker 枚举覆盖 topic、TF、source、time sync、drop ratio、fault injection 和 truth input。

验收：

- [x] summary schema 单元测试通过。
- [x] 缺 topic / 缺姿态 / truth source / hard tilt 未拒绝都能产生明确 blocker。
- [x] P10 summary 不重新声明 P8/P9 exploration 或 replay claim。

## P10.7a / P10.1 小补强：姿态指标和 motor output 可观测性

- [x] 在 scan integrity status 中记录 `flight_attitude_metrics`。
- [x] 记录 `max_abs_roll_deg`。
- [x] 记录 `max_abs_pitch_deg`。
- [x] 记录 `rms_roll_deg`。
- [x] 记录 `rms_pitch_deg`。
- [x] 记录 `yaw_rate_dps`。
- [x] 记录 `max_attitude_rate_dps`。
- [x] 在 summary 顶层记录 `flight_attitude_metrics`。
- [x] 在 summary 顶层记录 `scan_attitude_quality.ok`。
- [x] 在 summary 顶层记录 `scan_attitude_quality.max_scan_tilt_deg`。
- [x] 在 summary 顶层记录 `scan_attitude_quality.tilt_filtered_scan_count`。
- [x] 在 summary 顶层记录 `scan_attitude_quality.tilt_warning_count`。
- [x] motor output 采用 best effort ROS graph 检测，不从不存在的 topic 伪造 PWM/RPM。
- [x] 如果没有 motor/servo/actuator/ESC output topic，summary 明确 `motor_output_claim=not_available`。
- [x] 如果只发现候选 topic 但暂不能解码数值，只记录 `candidate_topics`，所有 PWM/RPM/spread/bias 字段保持 `null`。

验收：

- [x] P10.1 summary schema 单元测试通过。
- [x] P10.1 acceptance artifact 包含 flight attitude metrics。
- [x] P10.1 acceptance artifact 包含 `scan_attitude_quality`。
- [x] P10.1 acceptance artifact 包含 `motor_output_claim`。
- [x] 当前 ROS graph 无 motor output topic 时，summary 为 `motor_output_claim=not_available`。

## P10.8 MCAP 和 Foxglove-lite 集成

- [x] 更新 raw acceptance rosbag profile。
- [x] P10 raw MCAP 包含 `/scan` 和 `/navlab/x2/scan_raw`。
- [x] P10 raw MCAP 包含 `/navlab/scan_integrity/status`。
- [x] P10 raw MCAP 包含 attitude source topic。
- [x] P10 raw MCAP 包含 `/tf_static` 中的 `base_link -> base_scan`。
- [x] P10 raw MCAP 不强制包含 official maze overlay；官方 maze 叠加继续由 P9 Foxglove-lite replay 负责。
- [x] 明确 P10 首版不扩展 P9 lite generator；P10 gate 以 raw MCAP 的 scan integrity 证据为准。
- [x] Foxglove 中能打开 raw scan、validated scan、SLAM map 和 integrity status；official maze 对照沿用 P9 lite replay。

验收：

- [x] MCAP required topics 全部有数据。
- [x] Foxglove 中 `/scan` 不报缺 TF。
- [x] raw scan 和 validated scan 可以分层显示。
- [x] lite profile 如开启，必须完全配置化，缺 topic 直接 fail。

## P10.9 测试

- [x] scan integrity filter 单元测试覆盖 accept/warn/drop。
- [x] floor-hit risk 单元测试覆盖水平、roll、pitch、下俯 hard case。
- [x] attitude time sync 单元测试覆盖 fresh/stale/out-of-order。
- [x] summary parser 单元测试覆盖 status JSON 聚合。
- [x] topic owner 检查测试覆盖 raw `/scan` 被错误发布的情况。
- [x] filter 未运行时，raw scan 不能错误发布到 `/scan`。
- [x] fault injection profile 测试覆盖 hard tilt 必须被拒绝。
- [x] docs 中的 P10 TODO 不含已经过期的 P8/P9 命令。

验收：

- [x] P10 相关单元测试通过。
- [x] `git diff --check` 通过。
- [x] P10 normal acceptance 本地跑通。
- [x] P10 fault-injection acceptance 本地跑通。

## P10.10 执行顺序

推荐执行顺序：

1. P10.1 Topic contract 重构。
2. P10.2 姿态源 selector 和 no-fallback contract。
3. P10.3 scan integrity filter。
4. P10.4 floor-hit / ceiling-hit 风险裁剪。
5. P10.7 Summary 和 blocker。
6. P10.7a / P10.1 姿态指标和 motor output 可观测性补强。
7. P10.5 Normal integrity profile。
8. P10.6 Tilt fault-injection profile。
9. P10.8 MCAP 和 Foxglove-lite 集成。
10. P10.9 测试。

## P10 完成标准

P10 全部完成必须满足：

- [x] `/scan` 是 attitude-validated scan，不是 raw vendor scan。
- [x] `/navlab/x2/scan_raw` 保留并录入 MCAP。
- [x] scan integrity filter 是 `/scan` 唯一 publisher。
- [x] SLAM/Cartographer 不消费 raw scan。
- [x] `base_link -> base_scan` 静态 TF 存在。
- [x] attitude source 明确、非 truth、rate/freshness/time sync 通过。
- [x] normal integrity profile 通过。
- [x] tilt fault-injection profile 通过。
- [x] hard tilt 不会把 unchecked scan 发布到 `/scan`。
- [x] floor-hit risk 被计算并写入 summary。
- [x] summary 记录 flight attitude metrics。
- [x] summary 记录 `scan_attitude_quality`。
- [x] summary 明确记录 `motor_output_claim`，当前无 motor output topic 时为 `not_available`。
- [x] summary 记录 `scan_integrity_claim=evaluated`。
- [x] `uses_gazebo_truth_as_input=false`。
- [x] `set_pose_count=0`。
- [x] `owner.unique=true`。
- [x] raw MCAP、summary 和验证记录存在。
- [x] Foxglove 可对照 raw scan、validated scan 和 SLAM map；official maze 对照沿用 P9 lite replay。

## 验证记录

### 2026-06-08 P10 文档初始化

- 范围：新增 P10 设计文档和 TODO 文档，更新 README 与 master roadmap。
- 结果：P10 被定义为机体固连 lidar 姿态补偿与 scan integrity gate；P11 先做 2D scan 稳定化，P12 做 motor bias / ESC lag / vibration 鲁棒性仿真。
- 验证：已运行 `rg` 检查 P10/P0-P10 索引关键字；已运行 `git diff --check`，通过。
- 备注：P10.0 文档和边界已完成；后续从 P10.1 topic contract、P10.2 姿态源 selector 和 P10.3 scan integrity filter 开始实现。

### 2026-06-08 P10 scan integrity gate 首次端到端验收通过

- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260608_095523`。
- 结果：`ok=true`，`blocked=false`，`blockers=[]`。
- scan contract：`/navlab/x2/scan_raw=977`，`/navlab/x2/scan_normalized=977`，`/scan=864`，`/navlab/scan_integrity/status=977`，`/navlab/scan_integrity/events=156`。
- owner：`/scan` publisher 唯一，为 `navlab_scan_integrity_filter`；raw scan subscriber 只有 `navlab_x2_scan_time_normalizer`。
- normal profile：P10 复用 P7 small-motion probe，通过 validated `/scan` 后 SLAM/ExternalNav/FCU 均健康。
- fault injection：runtime attitude bias 注入通过；baseline/mild/reset 均回到 `accept`，hard tilt 进入 `drop`，证明坏姿态 scan 不会静默进入 `/scan`。
- 约束：`uses_gazebo_truth_as_input=false`，`set_pose_count=0`，`owner.unique=true`，`base_scan_static_tf_ok=true`。
- 验证：`just navlab-scan-integrity-gate-doctor` 通过；`just navlab-scan-integrity-gate-acceptance 140` 通过；`uv run --project orchestration pytest navlab/tests/gazebo_sensor/test_scan_integrity.py navlab/tests/gazebo_sensor/x2/test_sensor_runtime.py orchestration/tests/test_config.py -q` 通过，81 passed；`git diff --check` 通过。
- 备注：全仓库裸 `pytest` 仍会收集 third_party/YDLidar 示例和缺失 `pymavlink` 的 companion 测试，不作为 P10 本次验收口径。

### 2026-06-08 P10.1 姿态指标和 motor output 可观测性补强验收通过

- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260608_103819`。
- 结果：`ok=true`，`blocked=false`，`blockers=[]`。
- flight attitude metrics：`max_abs_roll_deg=0.376`，`max_abs_pitch_deg=1.293`，`rms_roll_deg=0.192`，`rms_pitch_deg=0.212`，`yaw_rate_dps=-0.028`，`max_attitude_rate_dps=38.024`。
- scan attitude quality：`ok=true`，`max_scan_tilt_deg=8.341`，`tilt_filtered_scan_count=315`，`tilt_warning_count=0`；其中 hard tilt/drop 来自 P10 fault injection 证明坏 scan 被过滤。
- motor output：当前 ROS graph 没有暴露 motor/servo/actuator/ESC output topic，summary 明确 `motor_output_claim=not_available`，PWM/RPM/spread/bias 字段为 `null`。
- 验证：`just navlab-scan-integrity-gate-acceptance 140` 通过；`uv run --project orchestration pytest navlab/tests/gazebo_sensor/test_scan_integrity.py navlab/tests/gazebo_sensor/x2/test_sensor_runtime.py orchestration/tests/test_config.py -q` 通过，85 passed。
