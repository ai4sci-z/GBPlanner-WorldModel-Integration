> **[历史设计任务书 · 已逐行审计(R003-E0-CORRECT-2 补正,2026-07-18)]** 路线切换后的迁移拆解(2026-07-08)。
> 审计改动:①§7 里程碑补真实进度(M0-M4 窄验收、M5 BLOCKED);②§8/§10/§11 标〔已执行〕(文档同步/分支目录/
> 首轮施工均已落地);③§12 启动提示词标 SUPERSEDED(现行指令体系=R003)。§2.1"已完成/已证明"为桥接期窄口径
> 判断;§5 工作量为当时估算。**本文非当前权威任务书**,当前状态唯一权威 = [CURRENT_STATUS.md](../CURRENT_STATUS.md)。

﻿# GBPlanner ROS2 原生迁移可行性与任务拆解

> 状态：导师最新指导后的路线切换文档  
> 日期：2026-07-08  
> 核心结论：停止继续扩展 ROS1-ROS2 桥接方案，转为 GBPlanner ROS2 原生迁移。

---

## 1. 路线切换结论

导师已经明确给出最高优先级指导：

> 一定要把 GBPlanner 算法迁移到 ROS2 系统，可以放弃桥接方案。ROS1 和 ROS2 同时跑过于笨重，后续应彻底抛弃桥接方案，开始 ROS2 原生迁移。

因此后续主线应从：

```text
ROS2 world-model
  -> ROS2/ROS1 bridge
  -> ROS1 GBPlanner
  -> bridge 回流
  -> ROS2 world-model 控制链
```

切换为：

```text
ROS2 world-model
  -> ROS2 GBPlanner 原生节点
  -> ROS2 trajectory / intent
  -> ROS2 world-model 控制链
```

这不是否定前期桥接工作。桥接工作的价值已经完成：

1. 证明 GBPlanner 接入 world-model 有探索增益；
2. 证明 3D lidar、voxblox、trajectory、intent 这一条链路概念上成立；
3. 暴露 ROS1+ROS2 双栈、TCP 薄桥、双时间域、双 TF 命名、probe 时序和 GUI 调试的长期维护负担；
4. 为 ROS2 迁移提供 oracle，也就是“原版 ROS1 GBPlanner 行为基准”。

后续桥接线应冻结为参考资产，不再作为最终系统继续演进。

---

## 2. 当前项目状态判断

### 2.1 已经坐实的部分

前期工作已经坐实：

| 项目 | 状态 | 意义 |
|---|---|---|
| world-model 原系统复现 | 已完成 | ROS2/Jazzy 仿真环境可跑 |
| GBPlanner ROS1 原版复现 | 已完成 | 原算法可作为 oracle |
| 3D lidar 数据进入 GBPlanner | 已证明 | 3D 输入链路成立 |
| voxblox 3D 建图 | 已证明 | GBPlanner 后端能消费点云 |
| trajectory 回流 | 已证明 | 规划输出可被转成执行意图 |
| Stage5b 3D 行为对照 | 已成立 | GBPlanner 行为受 3D 输入影响 |
| 公平对比 | 已有阶段性结论 | GBPlanner 支路优于 frontier_lite |
| 三 GUI 阶段演示 | 已初步搭建 | 可用于解释系统结构和迁移动机 |

这些结论可以作为 ROS2 迁移的动机与基线，而不是继续维护桥接方案的理由。

### 2.2 不建议继续投入的部分

以下内容不建议继续作为主线投入：

1. 继续修 thinbridge TCP 稳定性；
2. 继续追 Stage5c/final 的桥接全绿率；
3. 继续修 ROS1 RViz XMLRPC、ROS2 DDS 匹配、跨容器图形问题；
4. 继续围绕 ROS1/ROS2 双系统做 GUI 自动化；
5. 继续把桥接 probe 调到“看起来稳定”。

原因很简单：这些问题即使修好，也只是在维护一个导师已经明确要求放弃的过渡架构。

---

## 3. ROS2 迁移的正确目标

新的技术目标应定义为：

> 在 ROS2/Jazzy 下实现 GBPlanner 原生运行，使其直接订阅 world-model/Gazebo 的 ROS2 3D 点云、odom、TF，直接输出 ROS2 trajectory 或 exploration intent，并通过现有 world-model 控制链执行。

注意这里不是“重写一个像 GBPlanner 的新算法”，而是：

```text
保留 GBPlanner 算法核心
替换 ROS1 外壳和运行时依赖
尽量保持行为和 ROS1 原版 oracle 对齐
```

这句话非常重要。否则工程会滑向“重新发明一个探索算法”，工作量和科研风险都会失控。

---

## 4. 总体迁移架构

推荐目标架构：

```text
Gazebo Sim / world-model ROS2
    |
    | /wm/cloud3d or /lidar3d/points
    | /slam/odom
    | TF: map -> base_link -> lidar3d_frame〔⚠️撰写时误写含 odom 中间层;理解(二)实证 cartographer 直发 map->base_link,无 map->odom〕
    v
GBPlanner ROS2 原生节点
    |
    | voxblox ROS2 / map manager
    | RRG / gain / raycast / collision checking
    v
/gbp/trajectory  (ROS2 MultiDOFJointTrajectory, frame=map)
    |
    v
trajectory_to_intent_stage4.py
    |
    v
/navlab/fcu/setpoint/intent
    |
    v
world-model / FCU / Gazebo
```

### 4.1 建议保留的资产

| 资产 | 是否保留 | 说明 |
|---|---|---|
| ROS2 world-model 仿真环境 | 保留 | 后续目标平台 |
| lidar3d 传感器配置 | 保留 | 3D 输入来源 |
| trajectory_to_intent_stage4.py | 暂时保留 | 作为 ROS2 trajectory 到 intent 的 fail-closed 执行适配器 |
| Stage5b / Stage5c evidence | 保留 | 作为迁移前 oracle 和汇报素材 |
| GBPlanner ROS1 原版容器 | 保留 | 只作为行为对照，不再作为运行主线 |
| GUI 演示脚本 | 保留但降级 | 用于解释，不作为最终稳定性目标 |

### 4.2 应冻结或归档的资产

| 资产 | 处理建议 | 原因 |
|---|---|---|
| thinbridge_ros1_side.py / thinbridge_ros2_side.py | HISTORICAL | 桥接路线废弃 |
| TCP:7601 协议 | HISTORICAL | ROS2 原生后不需要 |
| bridge_topics.yaml | HISTORICAL | topic 契约改由 ROS2 原生节点承担 |
| ROS1 wm_planner.launch | HISTORICAL | 后续用 ROS2 launch.py |
| Stage2/Stage3 桥接 runbook | REFERENCE | 可保留作历史证据，不再施工 |
| 桥接稳定性 probe 修复脚本 | REFERENCE | 不再作为主线继续修 |

---

## 5. 工作量判断

根据已有包清点，GBPlanner 迁移不是“小改几个 include”的级别。

大致工作量可以拆成几层：

| 层 | 内容 | 迁移动作 | 风险 |
|---|---|---|---|
| A 算法核心 | RRG、gain、采样、轨迹、几何 | 剥离 ROS1 日志、时间、TF 污染 | 中 |
| B 地图后端 | voxblox / TSDF / ESDF / raycast | 选择 ROS2 voxblox 路线并接回 MapManager | 高 |
| C ROS 外壳 | node、topic、service、param、TF、launch | ROS1 roscpp 改 ROS2 rclcpp | 中高 |
| D 消息定义 | planner_msgs、voxblox_msgs | msg/srv/action 改 ROS2 IDL | 中 |
| E 仿真专用 | rotors、smb、gazebo classic | 大部分丢弃 | 低 |
| F 支撑库 | minkindr、gflags、glog、protobuf 等 | 系统依赖或 vendored lib | 中 |

粗略判断：

```text
最小可编译 ROS2 GBPlanner 骨架：3-5 天
最小可运行 ROS2 GBPlanner 节点：1-2 周
接入 world-model 并跑出轨迹：2-3 周
形成稳定演示和对照实验：3-4 周
```

如果要求“行为严格对齐 ROS1 原版 + 文档齐 + 统计充分”，应按 4 周级别估计，而不是 1-2 天。

---

## 6. 最大技术风险：voxblox

ROS2 迁移最大风险不是 GBPlanner 的 RRG 核心，而是地图后端。

GBPlanner 依赖 voxblox 的两个能力：

1. **gain 计算**  
   从候选视点发射 ray，统计 unknown/free/occupied 体素，估计探索收益。

2. **碰撞检查**  
   查询 TSDF/ESDF 或占据状态，判断路径是否安全。

如果地图后端语义变化，GBPlanner 的行为会变化。也就是说：

```text
换地图后端，不只是换库；
很可能等于换了 gain 分布、碰撞安全边界和路径偏好。
```

### 6.1 推荐路线

优先路线：

```text
继续使用 voxblox core
采用或参考社区 ROS2 voxblox 移植
补齐 ntnu-arl/voxblox fork 与官方 voxblox 的差异
用 ROS1 原版 oracle 做 voxel/gain/collision 对拍
```

这样行为漂移最小。

### 6.2 不建议优先采用 nvblox

nvblox 很先进，也更现代，但不适合作为本轮迁移第一目标：

1. GPU 依赖增加；
2. 数据结构和积分语义与 voxblox 不同；
3. gain/raycast 接口需要重新设计；
4. 行为无法直接和 ROS1 GBPlanner oracle 对齐；
5. 工程会从“迁移 GBPlanner”变成“重构 GBPlanner 地图后端”。

nvblox 可以作为后续性能升级路线，不应作为 M1-M5 的首选。

### 6.3 OctoMap 只能作为保底

OctoMap ROS2 生态成熟，但语义和 voxblox 不同。它可作为 voxblox ROS2 迁移失败后的 fallback，不应作为第一选择。

---

## 7. 推荐里程碑(撰写时拆解;**真实进度以 CURRENT_STATUS 为准**:M0-M4 均为窄验收〔编译/单测/切片对拍,行为等价与 3D 无损未证〕,M5 被平台稳定门 BLOCKED)

### M0：侦察与冻结

目标：

1. 明确桥接路线冻结；
2. 明确 ROS2 迁移为唯一主线；
3. 完成包清单、依赖清单、voxblox 选型、直连架构契约；
4. 更新 README、CURRENT_STATUS、TASKS、文档索引，避免入口文档继续说“当前主线=桥接”。

验收标准：

```text
根 README 第一屏说明：当前主线是 ROS2 原生迁移
TASKS 有新的 ROS2 迁移任务表
文档索引中桥接计划标记为 HISTORICAL/REFERENCE
CURRENT_STATUS 与接力棒一致
```

当前观察：

```text
CURRENT_STATUS 和接力棒已经开始切换；
但 README、TASKS、文档索引仍有大量“当前主线=B2.5 薄桥”的旧口径。
```

这一点应优先修。否则新窗口接手会被入口文档带回桥接路线。

---

### M1：ROS2 工作区与消息层

目标：

1. 新建 `ros2_ws` 或 `ros2_port/`；
2. 建立 `planner_msgs` ROS2 包；
3. 迁移最小必要 msg/srv；
4. colcon 能编译通过。

最小消息集建议：

```text
planner_msgs/srv/planner_srv
planner_msgs/srv/planner_set_planning_mode
planner_msgs/srv/planner_homing   可选
planner_msgs/msg/PlanningMode     如 planner_srv 依赖
planner_msgs/msg/BoundMode        如 planner_srv 依赖
planner_msgs/msg/PlannerStatus    可选
```

注意不要一开始迁移 13 msg + 24 srv + 1 action 全家桶。先迁移最小闭环需要的定义。

验收标准：

```text
colcon build 通过
ROS2 能 ros2 interface show planner_msgs/srv/planner_srv
无 ROS1/catkin/actionlib 依赖
```

---

### M2：voxblox ROS2 后端落地

目标：

1. 选择 voxblox ROS2 底座；
2. 在 Jazzy 下编译；
3. 能订阅 PointCloud2；
4. 能生成 TSDF/ESDF；
5. 能在 RViz2 显示 mesh / pointcloud / occupied 信息；
6. 与 ROS1 oracle 做最小对拍。

建议对拍：

```text
同一段点云输入
ROS1 voxblox 输出统计
ROS2 voxblox 输出统计
比较：
- voxel 数量
- zspan
- occupied/free/unknown 分布
- ESDF 查询结果
- raycast 命中情况
```

验收标准：

```text
ROS2 voxblox 能在 world-model 场景下建图
map frame 明确为 map
lidar3d_frame -> map TF 可查
至少一组 voxel / ESDF 查询结果与 ROS1 oracle 在可解释误差内
```

---

### M3：算法核心剥离

目标：

把 GBPlanner 的核心算法从 ROS1 运行时中剥离出来。

重点文件：

```text
gbplanner/src/rrg.cpp
gbplanner/include/gbplanner/rrg.h
planner_common/src/*
planner_common/include/*
adaptive_obb
kdtree
```

需要处理：

1. `ros/ros.h`；
2. `ROS_INFO/WARN/ERROR`；
3. `ros::Time` / `ros::Duration`；
4. ROS1 TF；
5. ROS1 参数读取；
6. ROS1 message 类型泄漏。

建议做法：

```text
先不要直接把 rrg.cpp 改成 rclcpp 节点。
先把它改成尽量 ROS-free 的 C++ library。
ROS2 节点外壳只负责喂数据、调服务、发结果。
```

验收标准：

```text
核心库可以在 ament_cmake 下编译
核心库不直接 include ros/ros.h
核心库可被一个简单单元测试调用
```

---

### M4：ROS2 planner 节点外壳

目标：

实现 `gbplanner_node` 的 ROS2 外壳。

最小职责：

1. 订阅 `/slam/odom`；
2. 订阅 `/wm/cloud3d` 或 `/lidar3d/points`；
3. 查询 TF；
4. 调用 voxblox / map manager；
5. 触发 RRG 规划；
6. 发布 `/gbp/trajectory`；
7. 发布 RViz2 marker；
8. 支持必要参数。

不建议一开始复刻完整 PCI。

PCI 可先替换为一个最小 trigger shell：

```text
每 N 秒触发一次规划
规划成功则发布 /gbp/trajectory
规划失败则保持静默或发布状态
```

原因：

原 PCI 包含大量 ROS1 服务、UI、homing、global、search、waypoint、geofence、action 等功能。第一阶段全部迁移会拖垮主线。

验收标准：

```text
ROS2 节点启动
能接收 odom / pointcloud
能构建地图
能触发一次规划
能发布 /gbp/trajectory
RViz2 能看到 trajectory 或 marker
```

---

### M5：world-model 直连联跑

目标：

把 ROS2 GBPlanner 接回 world-model。

输入：

```text
/slam/odom
/wm/cloud3d 或 /lidar3d/points
TF: map -> base_link -> lidar3d_frame〔⚠️同上,原文误含 odom 层〕
```

输出：

```text
/gbp/trajectory
```

沿用：

```text
trajectory_to_intent_stage4.py
/navlab/fcu/setpoint/intent
/navlab/exploration/status
stage5c probe 口径
```

验收标准分三层：

#### M5-a：可视化通过

```text
RViz2 中能看到点云/地图/trajectory
Gazebo 中 world-model 场景正常运行
无 ROS1 容器参与
```

#### M5-b：控制消费通过

```text
trajectory_to_intent 收到 /gbp/trajectory
intent 发布
FCU/controller 消费
odom 发生与 intent 方向相关的运动
```

#### M5-c：探索对比通过

```text
至少 3 run
记录 accepted_goals
记录 path_length
记录 TASK_STATUS
与桥接期 oracle 做行为对照
与 frontier_lite 做同口径对照
```

---

## 8. 文档体系必须同步调整(〔已执行〕本节点名的 README/TASKS/索引/接力棒 同步在后续轮次完成,且已被 R003 治理体系取代;本节留作历史)

当前最大非代码风险是：入口文档还可能把人带回旧路线。

需要立即同步：

| 文档 | 必须调整 |
|---|---|
| README.md | 第一屏写清：当前主线已转为 ROS2 原生迁移；桥接是已冻结阶段性验证 |
| CURRENT_STATUS.md | 已经基本转向，但要继续保持唯一事实源 |
| TASKS.md | 新增 ROS2 迁移任务表，旧 #9 B2.5 薄桥改为完成/冻结 |
| 文档索引.md | `桥接查证与执行计划` 从 ACTIVE 改 REFERENCE/HISTORICAL；新增 ROS2 迁移文档为 ACTIVE |
| 接力棒_当前值班.md | 当前值班任务改为 M0/M1，不再写 final 批跑/GUI/PR |
| 组会/PPT | 口径改为“桥接验证成功，因此转入 ROS2 原生迁移” |

强烈建议加一段统一口径：

```text
桥接线已经完成阶段性使命：证明 GBPlanner 接入 world-model 有价值，并暴露双 ROS 栈维护成本。
根据导师指导，后续不再追求桥接方案最终稳定化，而是以桥接结果作为 oracle 和阶段性证据，启动 GBPlanner ROS2 原生迁移。
```

---

## 9. 不建议现在做的事

1. 不要继续追桥接 final 成功率；
2. 不要继续修 ROS1 RViz 面板；
3. 不要把 nvblox 作为第一版后端；
4. 不要一口气迁移全部 planner_msgs；
5. 不要一开始复刻完整 PCI；
6. 不要把 ROS2 迁移说成“很快就能做完”；
7. 不要删除桥接证据，它是迁移 oracle；
8. 不要在主分支上混杂桥接收尾和 ROS2 port 大改。

---

## 10. 推荐分支与目录策略(〔已执行〕分支 `feat/gbplanner-ros2-port` 与 `ros2_port/` 目录均已按本节落地,见 gbp-feat worktree)

建议开新分支：

```text
feat/gbplanner-ros2-port
```

建议目录：

```text
ros2_port/
  src/
    planner_msgs/
    voxblox/
    voxblox_ros/
    gbplanner_core/
    gbplanner_ros2/
  docs/
    migration_notes.md
    oracle_comparison.md
```

或者如果计划未来独立成仓：

```text
gbplanner_ros2_ws/
```

原则：

```text
桥接历史资产不删
ROS2 port 新目录隔离
每个 M 阶段单独 commit
每个 M 阶段有 evidence
```

---

## 11. 第一轮施工建议(〔已执行〕M0 收口与 M1 骨架在后续轮次完成)

下一轮不应该立刻大规模改代码，应先做 M0 收口和 M1 骨架。

建议执行顺序：

1. 更新 README / TASKS / 文档索引，把路线切换写到所有入口；
2. 创建 ROS2 迁移任务表；
3. 新建 `feat/gbplanner-ros2-port` 分支；
4. 新建最小 ROS2 workspace；
5. 迁移最小 `planner_msgs`；
6. 验证 `colcon build`；
7. 再开始 voxblox ROS2 底座验证。

第一轮验收不要超过这个范围。否则很容易同时碰 messages、voxblox、rrg、params、TF、RViz2，最后无法定位错误。

---

## 12. 给 Claude Code 的直接提示词(〔SUPERSEDED〕当时的启动提示词,内容已全部执行;**现行工作指令体系 = R003 系列审查/补充令,本节不再作为提示词使用**)

```text
当前路线已经根据导师最高指导切换：停止继续扩展 ROS1-ROS2 桥接方案，主线改为 GBPlanner ROS2 原生迁移。

请先不要继续修 bridge final 批跑、v6/kp0.35、stage5c probe、ROS1 RViz、thinbridge TCP 或三 GUI 稳定性。这些作为桥接期证据冻结即可。

下一步请按 M0 -> M1 推进：

1. 先同步所有入口文档：
   - README.md 第一屏写清当前主线是 ROS2 原生迁移；
   - TASKS.md 新增 ROS2 迁移任务表；
   - 文档索引.md 把桥接计划从 ACTIVE 改为 REFERENCE/HISTORICAL；
   - CURRENT_STATUS.md 和接力棒保持一致；
   - 明确桥接线是 oracle 和科研叙事素材，不再演进。

2. 新建 ROS2 port 工作区或分支：
   - 建议分支 feat/gbplanner-ros2-port；
   - 新目录建议 ros2_port/ 或 gbplanner_ros2_ws/；
   - 不要污染桥接历史成果。

3. 第一阶段只做 M1：
   - 建立 planner_msgs ROS2 包；
   - 只迁移最小必要 srv/msg；
   - colcon build 通过；
   - 能 ros2 interface show 对应接口。

4. 第二阶段再做 M2：
   - 验证 voxblox ROS2 底座；
   - 优先沿用 voxblox core，不要第一版换 nvblox；
   - 与 ROS1 oracle 做 voxel / ESDF / gain 对拍。

验收纪律：
- 每个阶段都要有 evidence；
- 不要因为能编译就宣称迁移成功；
- 行为等价要靠 ROS1 oracle 对照；
- 第一版目标是“ROS2 原生最小闭环”，不是完整复刻所有 GBPlanner UI/PCI 功能。
```

---

## 13. 一句话汇报口径

可以这样向老师汇报：

> 前期桥接方案已经证明 GBPlanner 接入 world-model 有价值，也暴露了 ROS1+ROS2 双栈过重的问题。根据最新指导，后续不再继续维护桥接路线，而是把桥接结果冻结为 oracle 和阶段性证据，正式启动 GBPlanner ROS2 原生迁移。迁移将优先保留算法核心和 voxblox 行为语义，先完成最小 ROS2 消息层、地图层和 planner 节点闭环，再回到 world-model 做直连联跑和对照实验。
