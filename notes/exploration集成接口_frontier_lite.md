> 📌 **状态戳(2026-07-06 晚·全绿后)**:本文含历史阶段内容。**当前权威状态**以 [RESUME_新窗口接管_2026-07-06.md](../RESUME_新窗口接管_2026-07-06.md) + [Bug 台账](../docs/world-model端到端Bug台账_给作者PR.md) 为准。要点:jazzy 9/9 已验真;**run `20260706T130626` 已端到端全绿**(TASK_STATUS_OK/4探针全ok/3目标/SIM+0.72m,无hack,B15+B16 已修);但 frontier_lite 多跑基线**稳定性差**(6次全绿2/6,达标率40%,根因=启动耗时蚕食探索窗口);当前主线=**B2.5 自写薄桥接真 GBPlanner**(官方 ros1_bridge 与 zenoh 均已实验判死)→3D lidar(官方 lidar_3d 组件)→同口径对比;**PR 延后**(用户指示:等最终桥接跑通后统一定稿)。

# exploration 基线 = frontier_lite 的真实接口契约(读源码所得,2026-06-29)

> 来源:`orchestration/sim/internal/tasks/helpers/runtime_specs.go`(ExplorationWorkflowSpec)、`internal/config/defaults.go`(defaultExplorationGate)、`gate_evaluation.go`。
> **这就是 GBPlanner 要对接/替换的精确接口面。**

## frontier_lite 是什么
exploration 任务的探索策略(navigation 任务用的是 `bounded_frontier`+Nav2)。本质是一个 **Python 运行时工作流**(模板 `exploration_workflow_runtime.py.tmpl`),基于 **Cartographer 2D `/map`** 做轻量 frontier 探索,驱动 ArduPilot 飞,Go 侧 `gate_evaluation.go` 只做**闸门评估**。

## 默认参数(DefaultExplorationWorkflowSpec)
| 参数 | 值 |
|---|---|
| strategy | `frontier_lite` |
| exploration_window_sec | 26.0 |
| motion_speed_mps | 0.10 |
| yaw_rate_radps | 0.18 |
| min_accepted_goals | 3 |
| min_path_length_m | 0.35 |
| probe_timeout_sec | 35.0 |

## 输入 topics(消费)
- `/slam/odom`(Cartographer 2D 里程计)
- `/scan`(2D 激光)、`/map`(OccupancyGrid)、`/submap_list`、`/trajectory_node_list`
- ArduPilot DDS:`/ap/v1/pose/filtered`、`/ap/v1/twist/filtered`、`/ap/v1/status`、`/ap/v1/cmd_vel`
- `/rangefinder/down/range`

## 输出 topics(发布)—— **GBPlanner 必须发到这同一组**
- `/navlab/exploration/status`(闸门读它判 accepted_goals/coverage)
- `/navlab/exploration/goal`、`/navlab/exploration/frontiers`、`/navlab/exploration/path`
- `/navlab/exploration/coverage`、`/navlab/exploration/markers`
- 控制:`/navlab/fcu/setpoint/intent` → `/navlab/fcu/setpoint/output` → `/navlab/fcu/controller/status`

## 闸门评估字段(gate_evaluation.go,必须满足)
**更正(2026-07-06 晚,gate_evaluation.go L224 源码复查)**:exploration gate 读的字段= `claim/strategy/accepted_goals/min_accepted_goals/path_length_m/min_path_length_m/motion_speed_mps`(+payload `ok/blockers` 驱动 task_completed);**`coverage_growth`/`goal_success_ratio` 属 navigation task(L232),不是 exploration gate 必需字段**。实测全绿 run `20260706T130626` 亦未依赖 coverage。

## GBPlanner 集成结论(据此精确化)
1. 在 exploration gate 加新 strategy(如 `gbplanner`),替换 `frontier_lite`。
2. GBPlanner 的 ROS2 节点产出 → **发到 `/navlab/exploration/{goal,path,frontiers,status,markers,coverage}`**,复用现有 setpoint→FCU 控制链(`/navlab/fcu/setpoint/intent`),**不引入 RotorS**。
3. 闸门指标(accepted_goals 等)不变,GBPlanner 只要驱动 ≥3 个目标、有覆盖增长即过闸。
4. **传感器线索(2026-07-06 晚已确认)**:`iris_with_lidar` = iris + **官方 `lidar_3d` 组件(gpu_lidar,360×60 线,垂直±30°,15Hz,topic=lidar)——真 3D**!且 world-model bridge 模板已预留 `/lidar/points`→`cloud_in`(PointCloud2)桥路。3D 方案=给 navlab_iq_quad include lidar_3d + 走预留桥路。
5. frontier_lite 当前基于 **2D `/map`**;GBPlanner 是 3D(voxblox),要补 3D 占据图前端(octomap_server2/nvblox),输入点云需 3D lidar。

## 跑通 exploration 的成本(已证实)
连 `--dry-run` 都要 `navlab/official-baseline:jazzy-latest` 镜像(从镜像读 `iris_with_lidar/model.sdf`)。完整跑通需:`ardupilot_gz` 已克隆(✅ 已放 ~/ws/ardupilot_gz)+ 拉超大子模块(ardupilot 等)+ `navlab-sim build all`(编译 ArduPilot SITL/cartographer…)→ **1–2 小时起**。
