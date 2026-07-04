# P13 Nav2 室内导航与主动探索 TODO

## 目标

P13 要在 P12 的 realistic airframe disturbance envelope 通过之后，把 P8 的 bounded
exploration 升级成 Nav2-backed indoor navigation workflow。P13 不做 3D navigation
或穿窗任务；它验证 Nav2 在 NavLab 的 stabilized 2D scan、Cartographer map/odom、
single FCU owner 和 return-home-then-land contract 下是否能安全工作。

对应设计文档：

- `docs/scenarios/indoor/navlab_p13_nav2_indoor_navigation_design.md`

## P13.0 文档和边界

- [x] 新增 P13 设计文档。
- [x] 新增 P13 TODO 文档。
- [x] 文档明确 P13 是 Nav2-backed indoor navigation，不是 3D navigation。
- [x] 文档明确 P13 不照搬 AirSim / PX4 / Unreal 教学流程。
- [x] 文档记录 Navigation2 issue #3773 的参考价值和 costmap 风险。
- [x] 文档记录 Altair-Silent 的 component / mission workflow 参考价值。
- [x] 文档明确 Nav2 不能直接拥有 FCU 输出。
- [x] 文档明确 P13 必须继承 P10/P11/P12 scan / no-truth / owner 安全边界。

验收：

- [x] P13 文档包含 Nav2 -> adapter -> FCU controller 的控制链路。
- [x] P13 文档包含 costmap、TF、scan、owner、landing acceptance。
- [x] P13 文档没有把 Gazebo truth / official maze overlay 作为 planning input。

## P13.1 配置和 no-hardcode contract

- [x] 增加 `[nav2]` 配置段。
- [x] 增加 `[nav2.costmap]` 配置段。
- [x] 增加 `[navigation_adapter]` 配置段。
- [x] 增加 `[navigation_mission]` 配置段。
- [x] 配置 global / odom / base frame。
- [x] 配置 scan / map / cmd_vel topic。
- [x] 配置 Nav2 BT XML 路径。
- [x] 配置 planner / controller plugin 名称。
- [x] 配置 costmap topics。
- [x] 配置 required costmap layers。
- [x] 配置 costmap stale / unknown ratio / obstacle cell 阈值。
- [x] 配置 adapter speed / yaw / accel limits。
- [x] 配置 fixed altitude。
- [x] 配置 mission window、goal radius、clearance、path length、goal count。
- [x] 配置 recovery count 和 return-home policy。
- [x] 所有 Nav2 topic、frame、limit、gate 阈值都从 config 读取。

验收：

- [x] 缺 `[nav2]` 时 doctor fail。
- [x] 缺 costmap layer 配置时 doctor fail。
- [x] adapter limit 不合法时 fail。
- [x] required frame/topic 为空时 fail。
- [x] config summary 写入 Nav2、costmap、adapter 和 mission 参数。

## P13.2 Nav2 runtime artifact generation

- [x] 生成 Nav2 params YAML。
- [x] 生成 Nav2 BT XML 或引用配置文件。
- [x] 生成 Nav2 launch/runtime plan。
- [x] 生成 navigation adapter runtime config。
- [x] 生成 navigation adapter script/node。
- [x] 生成 Nav2 lifecycle probe。
- [x] 生成 costmap health probe。
- [x] 生成 navigation status probe。
- [x] 生成 P13 rosbag profile。

验收：

- [x] dry-run 生成 Nav2 params artifact。
- [x] dry-run 生成 adapter runtime artifact。
- [x] dry-run runtime_plan 包含 Nav2 services/probes/rosbag。
- [x] 生成 artifact 不写死 workspace 绝对路径。

## P13.3 Nav2 bringup / lifecycle gate

- [x] 启动 planner server。
- [x] 启动 controller server。
- [x] 启动 BT navigator。
- [x] 启动 lifecycle manager。
- [x] Nav2 lifecycle 节点 active 状态可观测。
- [x] NavigateToPose action server ready 可观测。
- [x] Nav2 未 active 时 mission planner 不发送 goal。

验收：

- [x] `nav2_lifecycle_active=true` 写入 summary。
- [x] lifecycle inactive 时 blocker 包含 `nav2_lifecycle_inactive`。
- [x] action server unavailable 时 blocker 包含 `nav2_action_unavailable`。

## P13.4 TF / map / scan contract

- [x] 验证 `map -> odom -> base_link`。
- [x] 验证 `base_link -> laser_frame`。
- [x] 验证 `/map` 发布频率和最新 age。
- [x] 验证 `/slam/odom` 健康。
- [x] 验证 Nav2 只消费 stabilized `/scan`。
- [x] 验证 Nav2 不消费 raw scan。
- [x] 验证 official maze overlay 不作为 Nav2 input。

验收：

- [x] TF invalid 时 blocker 包含 `nav2_tf_invalid`。
- [x] map stale 时 blocker 包含 `navigation_map_stale`。
- [x] scan source 不是 stabilized `/scan` 时 fail。
- [x] Gazebo truth / overlay 进入 Nav2 input 时 fail。

## P13.5 Costmap gate

- [x] global costmap topic 发布。
- [x] local costmap topic 发布。
- [x] obstacle layer enabled。
- [x] inflation layer enabled。
- [x] costmap frame 与 TF chain 一致。
- [x] 统计 costmap max age。
- [x] 统计 unknown ratio。
- [x] 统计 obstacle / lethal cell count。
- [x] 统计 local costmap update frequency。

验收：

- [x] global/local costmap 缺失时 fail。
- [x] obstacle layer 缺失时 blocker 包含 `nav2_obstacle_layer_missing`。
- [x] inflation layer 缺失时 blocker 包含 `nav2_inflation_layer_missing`。
- [x] costmap stale 时 blocker 包含 `nav2_costmap_stale`。
- [x] unknown ratio 过高时 blocker 包含 `navigation_costmap_unknown_ratio_too_high`。

## P13.6 Navigation adapter / single owner

- [x] adapter 订阅 Nav2 `/cmd_vel`。
- [x] adapter 发布 `/navlab/fcu/setpoint/intent`。
- [x] adapter 不发布 `/ap/v1/cmd_vel`。
- [x] adapter 限制 XY velocity。
- [x] adapter 限制 yaw rate。
- [x] adapter 限制 acceleration。
- [x] adapter 在 SLAM/costmap stale 时 hold。
- [x] adapter status 发布 clamp / hold / stale 原因。
- [x] FCU controller 保持唯一 `/ap/v1/cmd_vel` publisher。

验收：

- [x] direct Nav2 `/ap/v1/cmd_vel` publisher 时 fail。
- [x] competing cmd_vel publisher 时 fail。
- [x] velocity 超限时 clamp 并记录。
- [x] adapter inactive 时 blocker 包含 `navigation_adapter_not_active`。

## P13.7 NavigateToPose / waypoint mode

- [x] mission planner 发送 NavigateToPose goal。
- [x] 记录 goal pose、frame、yaw。
- [x] 记录 Nav2 action status。
- [x] action goal accepted 与 action result success 分开记录。
- [x] 记录 path length。
- [x] 记录 goal success / failure。
- [x] unreachable goal 加入 blacklist。
- [x] repeated failure 后 return-home。
- [x] mission 等 controller、SLAM、map、costmap ready 后再发 goal。
- [x] mission 在等待 action result 时持续发布 `/navlab/navigation/status`。

验收：

- [x] 至少 3 个 bounded NavigateToPose goal accepted。
- [x] odom path length 达到配置阈值。
- [x] unreachable goal 不应被误标成功。
- [x] recovery 超限时 blocker 包含 `nav2_recovery_limit_exceeded`。

## P13.8 Active exploration / frontier-lite upgrade

- [x] 实现 bounded frontier candidate schema。
- [x] 从 map/costmap 中选择 frontier 或 waypoint。
- [x] frontier 经过 clearance filter。
- [x] frontier 经过 path reachability filter。
- [x] 记录 accepted / rejected frontier。
- [x] 记录 coverage growth。
- [x] 记录 path length。
- [x] 记录 goal success ratio。

验收：

- [x] accepted goal count >= 配置阈值。
- [x] coverage growth >= 配置阈值。
- [x] rejected frontier 带 reason。
- [x] exploration 不读取 Gazebo truth。

## P13.9 Completion policy / landing

- [x] 记录 home pose source。
- [x] 支持 `land_in_place` 在当前任务终点原地降落。
- [x] 支持 `return_home_then_land` 使用 Nav2 + adapter + FCU controller 路径返回 home 后降落。
- [x] return-home 失败时进入 hold/land fallback。
- [x] final stop drift 低于阈值。
- [x] navigation intent 停止后再 land。
- [x] land 后 disarm。
- [x] summary 写入 completion policy、landing policy 和 disarm 状态。
- [x] task timeout 作为失败 deadline，不作为必须跑满的任务时长。
- [x] navigation task body 成功后由最终 `/navlab/landing/status` 决定 landing acceptance。
- [x] 早期 hover probe 的 landing blocker 不覆盖后续 navigation landing completion。

验收：

- [x] 配置的 completion policy 成功。
- [x] landing ok。
- [x] disarmed true。
- [x] 未使用 Gazebo set_pose。

## P13.10 Summary / rosbag / Foxglove-lite

- [x] summary 写入 `navigation_claim`。
- [x] summary 写入 `nav2_claim`。
- [x] summary 写入 `costmap_claim`。
- [x] summary 写入 `adapter_claim`。
- [x] summary 写入 Nav2 lifecycle/action/recovery metrics。
- [x] summary 写入 costmap health。
- [x] summary 写入 adapter clamp/hold metrics。
- [x] summary 写入 owner/no-truth/no-set-pose。
- [x] rosbag 记录 Nav2、costmap、SLAM、scan、FCU、navigation status topics。
- [x] Foxglove-lite profile 包含 map、path、costmap、scan、trajectory、goals、events。
- [x] `navigation_status_probe` 同时采样 navigation、adapter、controller、landing status。
- [x] summary evaluator 从所有 landing samples 中优先选择 `ok=true` 的最终 sample。
- [x] landing sample blockers 只进入 landing acceptance，不作为早期 probe 的全局 blocker 重复计算。

验收：

- [x] P13 summary schema 单元测试通过。
- [x] rosbag profile required topics 存在。
- [x] Foxglove-lite artifact 可复核 goal/path/costmap。

## P13.11 Ideal / realistic profile matrix

- [x] `ideal` profile 下 P13 navigation 通过。
- [x] `realistic` profile 下 P13 navigation 通过。
- [x] Stage 1 profile matrix 包含 `ideal` 和 `realistic`。
- [x] `realistic` profile 不降低 P12 scan/SLAM safety gate。

验收：

- [x] `ideal` summary `ok=true`。
- [x] `realistic` summary `ok=true`。
- [x] profile matrix `ok=true`。

## P13.12 Tests

- [x] 配置 loader 测试覆盖 `[nav2]`。
- [x] 配置 loader 测试覆盖 `[nav2.costmap]`。
- [x] 配置 loader 测试覆盖 `[navigation_adapter]`。
- [x] 配置 loader 测试覆盖 `[navigation_mission]`。
- [x] doctor 测试覆盖缺 topic/frame。
- [x] doctor 测试覆盖 direct FCU cmd_vel publisher。
- [x] summary parser 测试覆盖 Nav2 / costmap / adapter metrics。
- [x] costmap gate 单元测试覆盖 stale / missing layer / unknown ratio。
- [x] adapter 单元测试覆盖 velocity clamp / stale hold。
- [x] stage1 matrix 测试覆盖 ideal/realistic。

验收：

- [x] Go sim tests 通过。
- [x] contract/golden summary examples 更新。
- [x] CI 运行 P13 doctor 测试。

## P13.13 完成标准

- [x] Nav2 lifecycle active。
- [x] NavigateToPose action server ready。
- [x] global/local costmap healthy。
- [x] obstacle/inflation layer healthy。
- [x] Nav2 只消费 stabilized `/scan`。
- [x] Nav2 不直接控制 FCU。
- [x] adapter 输出 bounded intent。
- [x] single FCU owner 成立。
- [x] 至少一个 bounded goal 成功。
- [x] active exploration goal selection 有 coverage/path 证据。
- [x] configured completion policy + land/disarm 成功。
- [x] `ideal` + `realistic` profile matrix 通过。
- [x] no Gazebo truth input。
- [x] no set_pose。
- [x] summary / rosbag / Foxglove-lite artifact 可复核。
- [x] Live run `artifacts/sim/navigation/20260614T062658Z/summary.json` 通过：
  `TASK_STATUS_OK`、blockers 空、landing ok、rosbag profiles ok。
