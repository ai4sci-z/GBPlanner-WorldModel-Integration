> **[OBSOLETE]** 官方 ros1_bridge 路线已实验判死;现行=B2.5 自写薄桥(docs/桥接查证与执行计划)。禁止照做。当前状态以 [CURRENT_STATUS.md](../../CURRENT_STATUS.md) 为准。

# 阶段4:ros1_bridge 接真版 GBPlanner —— 设计与进度

> 锁定方案:桥接(ros1_bridge),接 **ROS1 原版 GBPlanner**(非 2D 重写)。本目录是阶段4 的实现工件。
> 全部 I/O 契约**已从镜像 `gbplanner-ref` 的真实源码逐条证实**(见下"证据"),非臆造。最后更新 2026-06-30。

## 1. 源码证实的 I/O 契约(去风险关键)

GBPlanner 启动文件 `gbplanner/launch/rmf/rmf_sim.launch` + `pci_general.cpp` 证实:

| 方向 | 话题(remap 后) | 消息类型 | 跨桥 |
|---|---|---|---|
| 进 GBPlanner | `/pointcloud` ← `/<robot>/velodyne_points` | `sensor_msgs/PointCloud2`(3D) | ✅ 标准,ros1_bridge 开箱 |
| 进 GBPlanner | `odometry` ← `/<robot>/ground_truth/odometry_throttled` | `nav_msgs/Odometry` | ✅ 标准 |
| 进 GBPlanner | TF `world → navigation`(静态) | `tf2_msgs/TFMessage` | ✅ 标准 |
| 出 GBPlanner | `<robot>/command/trajectory`(PCI 发布) | `trajectory_msgs/MultiDOFJointTrajectory` | ✅ 标准 |
| 规划触发 | `pci_trigger` 等(`planner_msgs/*` srv) | 自定义 | ⛔ **留 ROS1 内部,不跨桥** |

**结论(把 ros1_bridge 最大的坑绕开)**:GBPlanner + PCI 原样在 ROS1 侧跑,那一堆自定义
`planner_msgs`/srv(13 msg + 24 srv)只在 ROS1 内部用;**跨桥的只有 4 类标准消息** → 不必给 ros1_bridge
移植/重编自定义类型,直接用 `parameter_bridge` 或 `dynamic_bridge` 即可。

> PCI 配置 `planner_control_interface_sim_config.yaml`:`output_type: kTopic`、`trigger_mode: kManual`、
> `v_max:1.0, yaw_rate_max:0.15`。kManual = 原版靠 RViz 按钮/service 触发规划;桥接部署时改自动触发或在 ROS1 侧发 `pci_trigger`。

## 2. 目标数据流

```
world-model(ROS2)                         │ ros1_bridge │      GBPlanner(ROS1, gbplanner-ref 镜像)
─────────────────────────────────────────┼─────────────┼──────────────────────────────────────────
[iq_quad +3D雷达] → /pointcloud(PC2) ─────┼──── → ─────┼─→ /pointcloud → voxblox 3D建图(occ/free/unknown)
/slam/odom → (中继) /gbplanner/odometry ──┼──── → ─────┼─→ odometry  → gbplanner_node: RRG+光线投射+体积增益
                                          │             │     → planner_srv 返回 best path → PCI
trajectory_to_intent.py ←─ command/traj ──┼──── ← ─────┼─← <robot>/command/trajectory(MultiDOFJointTrajectory)
   → /navlab/fcu/setpoint/intent(替换脚本决策)→ fcu_controller → MAVLink → ArduPilot
```

## 3. 本目录工件(已产出)

| 文件 | 作用 | 状态 |
|---|---|---|
| `bridge_topics.yaml` | ros1_bridge `parameter_bridge` 话题映射(4 类标准消息) | ✅ 已写 |
| `trajectory_to_intent.py` | ROS2 出口适配器:`MultiDOFJointTrajectory` + `/slam/odom` → `/navlab/fcu/setpoint/intent`(strategy=gbplanner) | ✅ 已写,`py_compile` 通过 |
| 本 README | 源码证实的契约 + 数据流 + 剩余步骤 | ✅ |

## 4. 剩余步骤(端到端还没通,诚实清单)

- [ ] **步骤①·3D 眼睛**:给 `navlab_iq_quad/model.sdf` 加 3D 雷达(对齐 Velodyne/OS064),产出 `/pointcloud`。world-model 现仅 2D `/scan`。
- [ ] **步骤②·建桥**:在一个同时有 ROS1 noetic + ROS2 humble 的环境编译 `ros1_bridge`,用 `bridge_topics.yaml` 起桥。
- [ ] **步骤③·跑 ROS1 侧**:`gbplanner-ref` 容器内起 `gbplanner_node` + `pci_general_ros_node`(喂桥来的点云/里程计),触发规划。
- [ ] **步骤④·接 ROS2 侧**:跑 `trajectory_to_intent.py`,把航点意图发给 world-model 的 `fcu_controller`。
- [ ] **前置依赖**:world-model 运行时当前**起不来**(SLAM 崩于 `tomllib`,Python3.10 无此库;另有 exploration 脚本 `%%` 编译 bug)。端到端验证前需先修这两个(见 `docs/` 与 world-model-PR)。

## 5. 诚实状态

**已完成**:阶段4 的"接口契约(源码证实)+ ROS2 出口适配器代码 + ros1_bridge 映射配置"。
**未完成**:3D 雷达、ros1_bridge 实际编译起桥、ROS1/ROS2 两侧同时运行、端到端验证。
**即:Stage4 的设计与 ROS2 侧胶水已落地且语法验证;真正的端到端跑通是后续重活,且受 world-model 运行时阻塞。**
