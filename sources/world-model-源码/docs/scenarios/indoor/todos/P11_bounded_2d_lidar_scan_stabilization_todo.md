# P11 有界 2D lidar 姿态稳定化 TODO

## 目标

P11 要在 P10 scan integrity gate 已完成后，基于 P9 representative replay motion profile，验证 2D lidar 在中等机体倾角下能否通过有界姿态稳定化提高有效 `/scan` 输入，同时不把地面/天花板/坏姿态 scan 投影成假墙。

设计文档：

- `docs/scenarios/indoor/navlab_p11_bounded_2d_lidar_scan_stabilization_design.md`

前置条件：

- P9 representative replay profile 已存在，并能提供比 P8 slow acceptance 更高速度、更长路径的回放强度。
- P10 scan integrity gate 已通过，`/scan` 已是 attitude-validated scan，raw/normalized scan、attitude、TF、rangefinder 和 status 均可观测。

## P11.0 文档和边界

任务：

- [x] 新增 P11 设计文档。
- [x] 新增 P11 TODO 文档。
- [x] 在 `docs/README.md` 中加入 P11 design / TODO 入口。
- [x] 在 master roadmap 中把 P11 定义为有界 2D lidar 姿态稳定化 gate。
- [x] 文档明确 P11 只考虑 2D lidar，不引入 3D lidar / PointCloud。
- [x] 文档明确 P11 主验收基于 P9 representative replay，不使用 P8 slow exploration 作为主要验收。
- [x] 文档明确 P11 是 P10 后面的 stabilization layer，不替代 P10 hard safety。
- [x] 文档明确官方 maze overlay 仅用于可视化复核，不进入补偿、SLAM、planning 或控制输入。
- [x] 文档明确所有 pass/compensate/drop 门槛必须参数化，不能 hardcode。

验收：

- [x] P11 文档中没有把 Gazebo truth 作为 scan 补偿输入。
- [x] P11 文档中没有把官方 maze 底图作为补偿或规划输入。
- [x] P11 文档中没有要求上 3D lidar。
- [x] P11 文档中明确 baseline 是 P10 drop-only，candidate 是 bounded 2D projection。

## P11.1 配置和 no-hardcode contract

任务：

- [x] 新增 `[scan_stabilization]` 配置段。
- [x] 新增 `[scan_stabilization_gate]` 配置段。
- [x] 配置 `mode=bounded_2d_projection`。
- [x] 配置 `motion_profile=p9_representative_replay`。
- [x] 配置 `baseline_mode=p10_drop_only`。
- [x] 配置 `candidate_mode=bounded_2d_projection`。
- [x] 配置 `passthrough_tilt_deg`。
- [x] 配置 `compensation_tilt_deg`。
- [x] 配置 `hard_drop_tilt_deg`。
- [x] 配置 `max_vertical_projection_error_m`。
- [x] 配置 `max_rejected_beam_ratio`。
- [x] 配置 `min_retained_beam_ratio`。
- [x] 配置 `max_floor_hit_risk_beam_ratio`。
- [x] 配置 scan/attitude time sync、attitude rate 和 stabilized scan rate 门槛。
- [x] 配置 input/output/status/events/debug topic。
- [x] summary 记录所有实际使用的配置值。
- [x] gate 检查配置来自显式配置，不能使用算法内部神秘默认值。

验收：

- [x] `0 <= passthrough_tilt_deg < compensation_tilt_deg < hard_drop_tilt_deg`。
- [x] ratio 类参数都在 `[0, 1]`。
- [x] projection error、height、time sync、rate 参数为正。
- [x] 配置无效时 blocker 包含 `scan_stabilization_config_invalid`。
- [x] 缺关键配置时 fail，不做静默 fallback。

## P11.2 bounded 2D projection 算法

任务：

- [x] 实现 LaserScan endpoint 到 lidar frame point 的转换。
- [x] 读取 `base_link -> base_scan` 静态 TF。
- [x] 读取 attitude source，并与 `/scan.header.stamp` 对齐。
- [x] 把 endpoint 转到 gravity-aligned frame。
- [x] 计算 `vertical_projection_error_m`。
- [x] 计算 floor-hit risk。
- [x] 实现 passthrough / compensate / drop 状态机。
- [x] 对超过 `max_vertical_projection_error_m` 的 beam reject。
- [x] 对 floor-hit risk beam reject。
- [x] 对保留的 beam 重新计算水平 range/angle。
- [x] 将补偿后的点重新栅格化为 LaserScan。
- [x] 同一输出 angle bin 多个点时保留最近有效 range。
- [x] range 不在 `[range_min, range_max]` 内时 reject。
- [x] 不把 rejected beam 投影成障碍。

验收：

- [x] 小倾角时 state 为 `passthrough`。
- [x] 中等倾角且 vertical error 低时 state 为 `compensate`。
- [x] hard tilt 时 state 为 `drop`。
- [x] floor-hit risk 高时 beam 被 reject 或整帧 drop。
- [x] rejected beam 不会出现在输出 `/scan` 中。

## P11.3 stabilization runtime node

任务：

- [x] 新增 scan stabilization runtime 节点或组件。
- [x] 输入 `/navlab/x2/scan_normalized`。
- [x] 输出 validated/stabilized `/scan`。
- [x] 输出 `/navlab/scan_stabilization/status`。
- [x] 输出 `/navlab/scan_stabilization/events`。
- [x] 可选输出 `/navlab/scan_stabilization/debug_scan`，且不被 SLAM 消费。
- [x] 确保 `/scan` publisher 唯一。
- [x] 确保 SLAM/Cartographer 不订阅 raw scan。
- [x] 姿态源缺失、TF 缺失、height 缺失、time sync 失败时 fail，不 fallback 到 unchecked scan。

验收：

- [x] `/scan` publisher 只有 stabilization owner。
- [x] `/navlab/x2/scan_raw` 有数据但不被 SLAM 消费。
- [x] `/navlab/x2/scan_normalized` 有数据。
- [x] status JSON 可被 summary parser 稳定解析。
- [x] debug topic 即使开启也不会进入 SLAM input contract。

## P11.4 P9 representative replay baseline

任务：

- [x] 新增或复用 P9 representative replay motion profile。
- [x] P11 acceptance 不使用 P8 slow exploration profile 作为主要验收。
- [x] baseline 使用 P10 drop-only scan integrity。
- [x] baseline 记录 validated scan count/rate。
- [x] baseline 记录 dropped scan count/ratio。
- [x] baseline 记录 SLAM odom rate、map update、known cell growth。
- [x] baseline 记录 path length、accepted goals 或 representative replay progress。
- [x] baseline 仍保持 `uses_gazebo_truth_as_input=false`。
- [x] baseline 仍保持 `owner.unique=true`、`set_pose_count=0`。

验收：

- [x] summary 记录 `motion_profile=p9_representative_replay`。
- [x] summary 记录 `baseline_mode=p10_drop_only`。
- [x] baseline same-run drop-only estimate artifact 存在。
- [x] 文档说明 same-run estimate 不是独立 A/B，baseline availability 可能被低估。
- [x] baseline SLAM/ExternalNav/FCU health 可评价。
- [x] 如果误用 P8 slow profile，blocker 包含 `motion_profile_not_p9_representative_replay`。

## P11.5 P11 candidate replay

任务：

- [x] candidate 使用同类 P9 representative replay motion profile。
- [x] candidate 启用 bounded 2D projection。
- [x] candidate 记录 passthrough scan count。
- [x] candidate 记录 compensated scan count。
- [x] candidate 记录 dropped scan count。
- [x] candidate 记录 rejected beam count。
- [x] candidate 记录 retained/rejected beam ratio。
- [x] candidate 记录 max/mean vertical projection error。
- [x] candidate 记录 max compensated tilt。
- [x] candidate 记录 floor-hit rejected count。
- [x] candidate 记录 false-wall risk。

验收：

- [x] `scan_stabilization_claim=evaluated`。
- [x] candidate artifact 存在。
- [x] candidate `/scan` rate 满足 `min_stabilized_scan_rate_hz`。
- [x] 如果 live tilt 分布进入 compensation zone，`compensated_scan_count > 0`；否则 P11.7 fault injection 必须证明 compensation path 可触发。
- [x] 如果未进入 compensation zone，summary 明确 `compensation_not_triggered_reason`。
- [x] `false_wall_risk_ok=true`。
- [x] 定义 `false_wall_risk_ok` 首版计算：`floor_hit_risk_beam_ratio <= max_floor_hit_risk_beam_ratio`，并结合 floor-hit/hard-tilt/SLAM health。
- [x] SLAM/ExternalNav/FCU health 不退化。

## P11.6 baseline vs candidate 对比

任务：

- [x] 汇总 baseline 和 candidate 的 scan availability。
- [x] 汇总 baseline 和 candidate 的 SLAM odom health。
- [x] 汇总 baseline 和 candidate 的 map growth。
- [x] 汇总 baseline 和 candidate 的 path length / replay progress。
- [x] 计算 `scan_availability_improved`。
- [x] 计算 `slam_health_regressed`。
- [x] 计算 `map_artifact_risk_ok`。
- [x] 文档说明 `map_artifact_risk_ok` 首版是 false-wall/floor-hit/SLAM health 代理，不是完整 map 差分。
- [x] 如果 scan 数量增加但假墙风险上升，gate fail。
- [x] 如果 candidate 比 baseline 退化，gate fail 或明确 blocker。

验收：

- [x] candidate validated scan count 不低于 baseline，或 summary 解释未触发补偿。
- [x] candidate SLAM odom 不低于 baseline health。
- [x] candidate map growth 不出现明显异常退化。
- [x] P9 official maze overlay 可用于人工检查，但不是控制输入。

## P11.7 fault injection 和负例

任务：

- [x] 增加 medium safe tilt 注入，验证可 passthrough/compensate。
- [x] 增加 floor-hit risk 注入，验证 beam reject 或 frame drop。
- [x] 增加 hard tilt 注入，验证 hard drop。
- [x] 增加 stale attitude 注入，验证 blocked。
- [x] 增加 invalid config 注入，验证 config blocker。
- [x] fault profile 结果写入 summary。
- [x] 如果 fault profile 没跑，P11 blocker 包含 `scan_stabilization_fault_profile_not_run`。

验收：

- [x] hard tilt 不会被 compensation 发布到 `/scan`。
- [x] floor-hit risk 不会被投影成墙。
- [x] stale attitude 不会 fallback 到 unchecked scan。
- [x] invalid config 不会继续运行。

## P11.8 Summary、MCAP 和 Foxglove-lite

任务：

- [x] summary 增加 `scan_stabilization_claim=evaluated`。
- [x] summary 增加 `scan_stabilization` 对象。
- [x] summary 增加 `baseline_comparison` 对象。
- [x] summary 记录 `motion_profile=p9_representative_replay`。
- [x] summary 记录 runtime config。
- [x] summary 记录 topic owner、truth control、official maze role。
- [x] 新增 P11 raw rosbag topic profile。
- [x] raw MCAP 包含 raw scan、normalized scan、stabilized `/scan`、status/events、TF、attitude、rangefinder、SLAM、FCU。
- [ ] 可选 Foxglove-lite artifact 包含 official maze overlay、SLAM map、trajectory、scan stabilization status。
- [x] Foxglove-lite 缺 topic 时 fail，不做静默 fallback。

验收：

- [x] raw MCAP required topics 全部有数据。
- [ ] Foxglove 中可分层查看 official wall、SLAM map、validated scan 和 status。
- [x] summary 明确 `uses_official_maze_as_input=false`。
- [x] summary 明确 `uses_gazebo_truth_as_input=false`。

## P11.9 测试

任务：

- [x] 单元测试覆盖 LaserScan endpoint projection。
- [x] 单元测试覆盖 yaw wrap 和 attitude time sync。
- [x] 单元测试覆盖 passthrough / compensate / drop。
- [x] 单元测试覆盖 floor-hit rejection。
- [x] 单元测试覆盖 bin re-rasterization。
- [x] 单元测试覆盖 config validation。
- [x] summary parser 测试覆盖 P11 schema。
- [x] gate 测试覆盖 baseline/candidate comparison。
- [x] docs 中的 P11 TODO 不含过期 P8 slow acceptance 作为主验收。

验收：

- [x] P11 相关单元测试通过。
- [x] `git diff --check` 通过。
- [x] P11 doctor 本地跑通。
- [x] P11 acceptance 本地跑通。

## P11.10 执行顺序

推荐执行顺序：

1. P11.1 配置和 no-hardcode contract。
2. P11.2 bounded 2D projection 算法。
3. P11.3 stabilization runtime node。
4. P11.4 P9 representative replay baseline。
5. P11.5 P11 candidate replay。
6. P11.6 baseline vs candidate 对比。
7. P11.7 fault injection 和负例。
8. P11.8 Summary、MCAP 和 Foxglove-lite。
9. P11.9 测试。

## P11 完成标准

P11 全部完成必须满足：

- [x] P11 主验收使用 P9 representative replay profile。
- [x] baseline 是 P10 drop-only scan integrity。
- [x] candidate 是 bounded 2D projection stabilization。
- [x] 所有 pass/compensate/drop 门槛都来自配置。
- [x] `/scan` publisher 唯一。
- [x] SLAM 不消费 raw scan。
- [x] hard tilt 仍然 drop。
- [x] floor-hit risk 不会被投影成墙。
- [x] candidate scan availability 不低于 baseline，或 summary 明确未触发补偿原因。
- [x] candidate SLAM/ExternalNav/FCU health 不退化。
- [x] summary 记录 `scan_stabilization_claim=evaluated`。
- [x] summary 记录 `uses_gazebo_truth_as_input=false`。
- [x] summary 记录 `uses_official_maze_as_input=false`。
- [x] `set_pose_count=0`。
- [x] `owner.unique=true`。
- [x] raw MCAP、summary 和验证记录存在。
- [ ] Foxglove 可复核 official maze overlay、SLAM map、trajectory 和 stabilization status。

## 验证记录

### 2026-06-08 P11 文档初始化

- 范围：新增 P11 设计文档和 TODO 文档，更新 README、master roadmap 与 P10 后续关系。
- 结果：P11 被定义为基于 P9 representative replay 的有界 2D lidar 姿态稳定化 gate；P11 不引入 3D lidar，不使用 P8 slow exploration 作为主要验收。
- 验证：已运行 `rg` 文档索引/边界检查和 `git diff --check`，通过。
- 备注：P11.0 文档和边界完成；实现从配置/no-hardcode contract、bounded 2D projection 算法和 stabilization runtime 开始。

### 2026-06-08 P11 implementation acceptance

- 范围：实现 P11 scan stabilization config、runtime node、P9 representative replay acceptance、raw MCAP profile、fault profile 和 summary schema。
- 验证：`just navlab-scan-stabilization-gate-doctor` 通过，summary 为 `artifacts/ros/navlab_scan_stabilization_gate_doctor/20260608_141436/summary.json`。
- 验证：`just navlab-scan-stabilization-gate-acceptance 240` 通过，summary 为 `artifacts/ros/navlab_companion_sitl_gazebo/20260608_141444/summary.json`，`ok=true`、`blockers=[]`。
- MCAP：required topics 全部有数据，关键计数 `/lidar=1480`、`/navlab/x2/scan_raw=1678`、`/navlab/x2/scan_normalized=1678`、`/scan=1588`、`/navlab/scan_stabilization/status=1678`、`/rangefinder/down/range=2958`、`/slam/odom=8966`、`/map=460`。
- Fault profile：medium safe tilt、floor-hit risk、hard tilt、stale attitude、invalid config 全部通过。
- 备注：本次 P9 replay 姿态未超过 passthrough zone，live compensation 未触发；summary 已记录 `compensation_not_triggered_reason=tilt_never_exceeded_passthrough_tilt_deg`。
- 测试：targeted pytest `98 passed`；`git diff --check` 通过。

### 2026-06-08 P11 replay robustness follow-up

- 范围：根据失败 artifact `artifacts/ros/navlab_companion_sitl_gazebo/20260608_135843/summary.json`，修复 P8 representative replay 在 P11 240s window 内偶发 readiness timeout 和 controller summary 采集竞态。
- 改动：P11 gate 新增显式配置 `replay_readiness_timeout_sec=90.0` 与 `controller_summary_timeout_sec=45.0`；P11 acceptance 在 rosbag finish 后再采集 controller summary，避免 controller 仍在 hold-ready 时被误判 missing。
- 补测：P11.9 新增 yaw wrap / scan-attitude time offset、summary schema parser、baseline/candidate blocker 对比测试。
- 验证：`just navlab-scan-stabilization-gate-acceptance 240` 通过，summary 为 `artifacts/ros/navlab_companion_sitl_gazebo/20260608_141444/summary.json`，`ok=true`、`blockers=[]`、P8 replay `ok=true`。
