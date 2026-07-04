# 统一降落流程 TODO

## 目标

把 hover、P8 exploration、P12 scan robustness 的任务结束口径统一为“任务主体完成后必须安全降落、解除武装、motor safe，且 summary/rosbag 可验证”。

设计文档：

- `docs/scenarios/indoor/navlab_unified_landing_sequence_design.md`
- `docs/scenarios/indoor/navlab_real_flight_preflight_doctor_design.md`

适用 built-in flight task：

- `hover`: `land_in_place`
- `exploration` / P8: `return_home_then_land`
- `scan-robustness` / P12: `land_in_place`

## 前置原则

- [ ] 所有降落逻辑先在 Gazebo/SITL 里验收完成。
- [x] hover / P8 必须向 P12 已跑通的 runtime contract 对齐，不能为了早期 task 单独降级。
- [ ] 每个 built-in flight task 的 Gazebo/SITL Stage 1 必须包含 `ideal` 和 `realistic` 两种 profile。
- [ ] `ideal` 和 `realistic` 两种 profile 都通过后，才算对应 task 的 Stage 1 通过。
- [x] Gazebo/SITL Stage 1 通过后，才能进入真机 Stage 2 验收。
- [x] 真机未验收时必须标记 `real_landing_claim=not_evaluated`。
- [x] Stage 1 通过不等于 Stage 2 通过。
- [ ] 每次真机 Stage 2 flight task 进入 arm/takeoff 前，必须引用通过且未过期的 real preflight summary。
- [x] landing 失败时，任务主体即使成功，summary 也必须 `ok=false`。
- [x] P8 return home 失败但 emergency landing 成功时，summary 仍必须 `ok=false`。
- [x] 不允许 Gazebo reset / direct set pose / truth-control shortcut。

## L0：文档和边界

任务：

- [x] 新增统一降落流程设计文档。
- [x] 新增统一降落流程 TODO 文档。
- [x] 在 `docs/README.md` 中加入 design / TODO 入口。
- [x] 设计文档明确 hover、P8、P12 的 landing policy。
- [x] 设计文档明确 P12 runtime contract 是 hover/P8 前向迁移标准。
- [x] 设计文档明确两阶段验收：先 Gazebo/SITL，再真机。
- [x] 设计文档明确 Stage 1 至少覆盖 `ideal` 和 `realistic` 两种仿真 profile。
- [x] 设计文档明确 Gazebo truth 只能诊断，不能控制或作为唯一 touchdown 判据。

验收：

- [x] design 文档不承载 implementation checklist。
- [x] TODO 文档单独承载任务拆分和验收标准。
- [x] 后续实现 issue / task 应引用 design 和本 TODO。

## L1：配置和 summary schema

任务：

- [x] 新增统一 landing 配置段。
- [x] 支持 task-level landing policy override。
- [x] 配置 `land_in_place`。
- [x] 配置 `return_home_then_land`。
- [x] 配置 home pose source、home radius、pre-land hold。
- [x] 配置 landing timeout、descent rate、touchdown threshold。
- [x] 配置 require disarm / motors safe。
- [x] summary 新增 `landing_claim`。
- [x] summary 新增 `simulation_landing_claim`。
- [x] summary 新增 `real_landing_claim`。
- [x] summary 新增 `acceptance_stage`。
- [x] summary 新增统一 `landing` block。
- [x] summary 新增 `simulation_profile`，取值至少包含 `ideal` / `realistic`。
- [x] summary 新增 task-level Stage 1 profile matrix，记录每个 profile 的 artifact、`ok`、landing claim。

验收：

- [x] 默认配置不允许 Gazebo truth 作为 landing 控制输入。
- [x] task 未显式选择 policy 时使用安全默认值。
- [x] 真机未验收时 `real_landing_claim=not_evaluated`。
- [x] Stage 1 未通过时 Stage 2 summary blocked。
- [x] 任一 required simulation profile 未通过时，task-level Stage 1 summary blocked。

## L2：Landing state machine

任务：

- [x] 新增 landing helper / workflow state machine。
- [x] 支持 `task_body_complete -> pre_land_hold -> land_command_sent`。
- [x] 支持 descent monitoring。
- [x] 支持 touchdown candidate。
- [x] 支持 landed confirmed。
- [x] 支持 disarm requested / disarmed confirmed。
- [x] 支持 motors safe confirmed。
- [x] 支持 landing blockers。
- [x] 支持 emergency land-in-place fallback，但不能把任务标记通过。

验收：

- [x] `landing_complete` 必须包含 landed、disarmed、motors safe。
- [x] landing timeout 时 summary `ok=false`。
- [x] command rejected 时 summary `ok=false`。
- [x] touchdown 不确认时 summary `ok=false`。
- [x] disarm 失败时 summary `ok=false`。

## L3：FCU controller 接入

任务：

- [x] FCU controller 支持 landing intent。
- [x] FCU controller 支持 return-home intent。
- [x] FCU controller 支持 LAND / guided descent / official equivalent。
- [x] FCU controller 输出 landing status。
- [x] FCU controller 记录 land command accepted/rejected。
- [x] FCU controller 记录 armed、landed、motor output / motors safe。
- [x] 保持唯一 setpoint owner，不新增第二个 `/ap/v1/cmd_vel` publisher。
- [x] 对比 P12 已通过 artifact 的 FCU controller/runtime contract，列出 hover 当前缺失项。
- [x] hover 改为复用 P12/P8 的标准 FCU bootstrap，不单独降低 readiness gate。

验收：

- [x] `owner.unique == true`。
- [x] `set_pose_count == 0`。
- [x] `competing_publishers == []`。
- [x] landing helper 不直接抢占 FCU setpoint owner。

## L4：Home pose 和 P8 return-home

任务：

- [ ] 在 takeoff complete + hover settle 后采样 home pose。
- [x] home pose 来源优先使用 FCU filtered pose / official equivalent。
- [ ] 支持 SLAM odom home pose fallback。
- [x] Gazebo truth 只作为 diagnostic home pose 对照。
- [ ] P8 exploration complete 后停止 exploration intent。
- [x] P8 发起 return-home intent。
- [x] P8 在 home radius 内稳定 hold 后再 landing。
- [x] return-home fail 时允许 emergency land-in-place，但 P8 summary `ok=false`。

验收：

- [x] P8 `return_home.required == true`。
- [x] P8 return-home 使用非 truth home pose。
- [x] P8 distance-to-home 进入阈值后才允许正常 landing。
- [x] P8 return-home timeout 时 summary `ok=false`。

## L5：Task 接入

任务：

- [x] hover acceptance 接入 `land_in_place`。
- [x] P8 exploration acceptance 接入 `return_home_then_land`。
- [x] P12 scan robustness acceptance 接入 `land_in_place`。
- [x] task body 成功但 landing 失败时，顶层 summary `ok=false`。
- [ ] task body 失败时仍尽量执行 safe landing，并记录 emergency outcome。

验收：

- [x] hover acceptance 包含 takeoff -> hover -> land -> disarm。
- [x] P8 acceptance 包含 takeoff -> exploration -> return home -> land -> disarm。
- [ ] P12 acceptance 包含 robustness evaluation -> land -> disarm。
- [x] 三个 built-in flight task 都输出 landing summary。

## L6：Rosbag 和 replay

任务：

- [x] 更新 hover rosbag profile，加入 landing required topics。
- [x] 更新 P8 rosbag profile，加入 landing / return-home required topics。
- [x] 更新 P12 rosbag profile，加入 landing required topics。
- [ ] Foxglove notes 标出 takeoff、task body、return-home、landing、disarm 时间窗。
- [ ] simulation rosbag 允许记录 Gazebo truth diagnostic。
- [ ] real rosbag 不依赖 Gazebo diagnostic。

验收：

- [ ] rosbag 可回放完整起飞、任务、返航或原地降落、解除武装过程。
- [x] `/navlab/landing/status` 在 hover acceptance rosbag 中有数据。
- [ ] `/ap/v1/status`、`/ap/v1/pose/filtered`、rangefinder topic 有数据。

## L7：Stage 1 Gazebo/SITL 验收

任务：

- [x] 用 P12 已通过 artifact 作为基准，记录 hover/P8/P12 的 runtime config diff。
- [x] 消除 hover 与 P12 标准 bootstrap 的不一致，而不是关闭 P12/official baseline 配置。
- [x] Stage 1 hover `ideal` landing acceptance 通过。
- [x] Stage 1 hover `realistic` landing acceptance 通过。
- [x] Stage 1 P8 `ideal` return-home landing acceptance 通过。
- [x] Stage 1 P8 `realistic` return-home landing acceptance 通过。
- [ ] Stage 1 P12 `ideal` in-place landing acceptance 通过。
- [ ] Stage 1 P12 `realistic` in-place landing acceptance 通过。
- [ ] Stage 1 P12 configured robustness profiles in-place landing acceptance 通过。
- [ ] 每个 task 的 `ideal` 与 `realistic` artifact 使用同一 P12/P8 runtime contract，差异只来自 disturbance profile。
- [x] Stage 1 profile matrix summary 汇总 hover/P8/P12 的 profile 结果。
- [ ] Stage 1 归档 summary、rosbag、Foxglove notes。
- [x] Hover Stage 1 `ideal` 归档 summary、rosbag、Foxglove notes：`artifacts/ros/navlab_companion_sitl_gazebo/20260609_120302/summary.json`。
- [x] Hover Stage 1 `ideal` summary 记录 `acceptance_stage=simulation`。
- [x] Hover Stage 1 `ideal` summary 记录 `simulation_profile=ideal`。
- [x] Hover Stage 1 `ideal` summary 记录 `simulation_landing_claim=evaluated`。
- [x] Hover Stage 1 `ideal` summary 记录 `real_landing_claim=not_evaluated`。
- [x] Hover Stage 1 `realistic` 归档 summary、rosbag、Foxglove notes：`artifacts/ros/navlab_companion_sitl_gazebo/20260609_115602/summary.json`。
- [x] Hover Stage 1 `realistic` summary 记录 `acceptance_stage=simulation`。
- [x] Hover Stage 1 `realistic` summary 记录 `simulation_profile=realistic`。
- [x] Hover Stage 1 `realistic` summary 记录 `simulation_landing_claim=evaluated`。
- [x] Hover Stage 1 `realistic` summary 记录 `real_landing_claim=not_evaluated`。
- [x] P8 Stage 1 `ideal` 归档 summary、rosbag、Foxglove notes：`artifacts/ros/navlab_companion_sitl_gazebo/20260609_122759/summary.json`。
- [x] P8 Stage 1 `ideal` summary 记录 `acceptance_stage=simulation`。
- [x] P8 Stage 1 `ideal` summary 记录 `simulation_profile=ideal`。
- [x] P8 Stage 1 `ideal` summary 记录 `simulation_landing_claim=evaluated`。
- [x] P8 Stage 1 `ideal` summary 记录 `real_landing_claim=not_evaluated`。
- [x] P8 Stage 1 `realistic` 归档 summary、rosbag、Foxglove notes：`artifacts/ros/navlab_companion_sitl_gazebo/20260609_125158/summary.json`。
- [x] P8 Stage 1 `realistic` summary 记录 `acceptance_stage=simulation`。
- [x] P8 Stage 1 `realistic` summary 记录 `simulation_profile=realistic`。
- [x] P8 Stage 1 `realistic` summary 记录 `simulation_landing_claim=evaluated`。
- [x] P8 Stage 1 `realistic` summary 记录 `real_landing_claim=not_evaluated`。

验收：

- [x] Gazebo/SITL hover `ideal` 降落并解除武装。
- [x] Gazebo/SITL hover `realistic` 降落并解除武装。
- [x] Gazebo/SITL P8 `ideal` 返回 home 后降落并解除武装。
- [x] Gazebo/SITL P8 `realistic` 返回 home 后降落并解除武装。
- [ ] Gazebo/SITL P12 `ideal` 原地降落并解除武装。
- [ ] Gazebo/SITL P12 `realistic` 原地降落并解除武装。
- [x] Hover Stage 1 `ideal` `uses_gazebo_truth_as_input=false`。
- [x] Hover Stage 1 `realistic` `uses_gazebo_truth_as_input=false`。
- [x] P8 Stage 1 `ideal` `uses_gazebo_truth_as_input=false`。
- [x] P8 Stage 1 `realistic` `uses_gazebo_truth_as_input=false`。
- [x] Hover Stage 1 `ideal` 未使用 Gazebo reset / set_pose 代替降落。
- [x] Hover Stage 1 `realistic` 未使用 Gazebo reset / set_pose 代替降落。
- [x] P8 Stage 1 `ideal` 未使用 Gazebo reset / set_pose 代替降落。
- [x] P8 Stage 1 `realistic` 未使用 Gazebo reset / set_pose 代替降落。

## L8：Stage 2 真机验收

任务：

- [ ] Stage 2 入口检查对应 Stage 1 summary `ok=true`。
- [ ] Stage 2 入口检查对应 task 的 Stage 1 `ideal` 和 `realistic` profile 都 `ok=true`。
- [ ] Stage 2 入口检查 Stage 1 artifact 已归档。
- [x] P8 Stage 2 入口所需 Stage 1 `ideal` / `realistic` artifacts 已归档。
- [ ] Stage 2 入口检查 real preflight doctor summary `ok=true`。
- [ ] Stage 2 入口检查 real preflight doctor summary 未超过有效窗口。
- [ ] Stage 2 入口记录 real preflight artifact path。
- [ ] Stage 2 入口检查 manual takeover / kill switch 已确认。
- [ ] 真机 hover landing acceptance。
- [ ] 真机 P8 return-home landing acceptance。
- [ ] 真机 P12 in-place landing acceptance。
- [ ] Stage 2 summary 记录 `acceptance_stage=real`。
- [ ] Stage 2 summary 记录 `real_landing_claim=evaluated`。

验收：

- [x] Stage 1 未通过时 Stage 2 必须 blocked。
- [ ] 真机 hover 降落并解除武装。
- [ ] 真机 P8 返回 home 后降落并解除武装。
- [ ] 真机 P12 原地降落并解除武装。
- [ ] 真机 landing 失败时 summary `ok=false`。

## L9：测试和回归

任务：

- [x] 增加配置测试：landing 默认配置可加载。
- [x] 增加配置测试：P8 policy 为 `return_home_then_land`。
- [x] 增加配置测试：P12 policy 为 `land_in_place`。
- [x] 增加 blocker 测试：landing fail 导致 summary fail。
- [x] 增加 blocker 测试：P8 return-home fail + emergency landing success 仍 fail。
- [x] 增加 blocker 测试：Stage 1 未通过时 Stage 2 blocked。
- [x] 增加 blocker 测试：Gazebo truth 不能作为 landing 控制输入。
- [x] 增加 profile matrix 测试：缺少 `ideal` 或 `realistic` 时 task-level Stage 1 blocked。
- [ ] 增加 profile matrix 测试：hover/P8/P12 两种 required simulation profile 都通过后，Stage 1 才允许通过。
- [ ] 增加 Stage 2 入口测试：对应 task 的 `ideal` 和 `realistic` 未全部通过时 blocked。
- [x] 增加 CLI/just smoke。

验收：

- [x] orchestration 单测通过。
- [x] CLI help 仍只列 built-in task。
- [x] just list 仍只暴露 built-in flight task 和 command tools。

## 最终完成标准

- [x] hover Stage 1 Gazebo/SITL landing 通过：`ideal` 和 `realistic` 都通过。
- [x] hover Stage 1 Gazebo/SITL `ideal` landing 通过。
- [x] hover Stage 1 Gazebo/SITL `realistic` landing 通过。
- [x] P8 Stage 1 Gazebo/SITL return-home landing 通过：`ideal` 和 `realistic` 都通过。
- [ ] P12 Stage 1 Gazebo/SITL in-place landing 通过：`ideal`、`realistic` 和 configured robustness profiles 都通过。
- [ ] hover Stage 2 real landing 通过。
- [ ] P8 Stage 2 real return-home landing 通过。
- [ ] P12 Stage 2 real in-place landing 通过。
- [ ] 所有 flight task summary 包含 `landing_claim=evaluated`。
- [ ] 所有 flight task summary 区分 `simulation_landing_claim` 和 `real_landing_claim`。
- [ ] landing 失败时 summary `ok=false`。
- [ ] rosbag 可回放完整起飞、任务、返航或原地降落、解除武装过程。
