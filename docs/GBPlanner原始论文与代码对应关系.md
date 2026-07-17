> **[技术参考 · 已逐行审计(R003-E0-CORRECT-2 补正,2026-07-18)]** 论文↔代码对应表为技术参考。
> 审计改动:①"真正的集成=桥接方案"结论标 SUPERSEDED(被 07-07 路线切换推翻,现=ROS2 原生迁移);
> ②`integration/…` 两处路径改指真实位置 `archive/integration_桥接线冻结/`;③源码路径/PDF/归档链接机械核验通过。
> 论文内容摘录(公式/Fig 编号)未逐页复核原 PDF,保持撰写时表述。
> 当前状态唯一权威 = [CURRENT_STATUS.md](../CURRENT_STATUS.md)。

> **[REFERENCE]** 论文↔代码对应(含 gbplanner_gain 失真标注)。当前状态以 [CURRENT_STATUS.md](../CURRENT_STATUS.md) 为准。

# GBPlanner 原始论文 ↔ 代码 对应关系(读原始论文后校准)

> ⚠️ **重要校准(2026-07-04)**:此前文档多引用 **arXiv:2201.07067**——那**不是** GBPlanner 原始论文,是它的一个**应用/扩展**(mentor 发的落地工作)。
> **原始论文** = Dang, Tranzatto, Khattak, Mascarich, Alexis, Hutter,
> *"Graph-based subterranean exploration path planning using aerial and legged robots"*, **Journal of Field Robotics (JFR) 2020**, DOI 10.1002/rob.21993(已归档 `sources/GBPlanner原始论文_JFR2020_Dang_et_al.pdf`,26 页)。
> 本文把原始论文的每个核心概念,精确对应到 `sources/gbplanner_ros-源码/` 的实现文件,并标出我们 `gbplanner_gain` 原型的**简化点与失真处**(要求13:不读原始论文做出来的东西是失真的)。

## 一、原始论文核心(JFR 2020,读后精确版)

GBPlanner 的贡献是一个 **bifurcated(二分)local + global 规划架构**(论文 Fig.2),面向**地下环境**(隧道网络、多分支拓扑、死胡同)、**同时支持飞行器与腿足机器人(ANYmal)**——不只无人机。

### 1. Local planner(局部,RRG + 体积增益)
- **RRG**(rapidly-exploring random graph):在机器人当前位姿周围的 local subspace 里随机撒点、碰撞检查后连边、在新顶点半径内 densify(论文 Fig.4 a→b→c)。
- **VolumetricGain(单顶点)** = 该顶点上机载测距传感器**期望能新感知到的累计未映射体积**(expected cumulative unmapped volume),经 **ray casting** 在**传感器视锥模型(sensor frustum)**内计算(Fig.3)。可扩展多传感器(如朝上测距建洞顶)。
- **ExplorationGain(整条路径)** = 论文公式(1):**路径上所有顶点 VolumetricGain 的加权累加**,乘距离衰减 `exp(-γ_S·d)`、减方向惩罚。用 **Dijkstra** 找最短路(顺带消除 zig-zag,因为绕远降增益)。
- 选 ExplorationGain 最大的 **admissible** 路径:collision-free + traversability(可通行)+ dynamic limits(动力学约束)。

### 2. Global planner(全局,frontier + 返航)
- 增量维护一张 **sparse global graph**;用 **DTW** 相似度聚类 high-gain 路径,每簇只留最长的"principal path"入图;其叶顶点标记为 **frontier**,周期性 re-evaluate 各 frontier 的体积增益。
- **触发时机**:local planner 找不到任何 informative path(局部无增益)→ 全局 reposition 到某 frontier。
- **GlobalExplorationGain** = 论文公式(2):`VolumetricGain(frontier)·exp(-γ_S·D)·exp(-γ_R·剩余时间)`,显式考虑 **time budget**——用剩余续航 RET 减去到达时间 ETA,保证"去一个 frontier 后还有电回家"(worst-case homing)。偏好"高增益 + 快到达"。
- **return-to-home**:在 global graph 上持续跑 Dijkstra 求回家路径;当"回家所需时间"逼近剩余续航即触发返航。

## 二、论文概念 ↔ gbplanner_ros 源码

| 论文概念 | 源码位置(`sources/gbplanner_ros-源码/`) |
|---|---|
| Local RRG 采样/连边/densify | `gbplanner/src/rrg.cpp`(RRG 主体) |
| VolumetricGain / ray casting / frustum | `rrg.cpp` 内 gain 计算 + `planner_common`(体素地图查询,voxblox) |
| ExplorationGain 路径打分(公式1) | `rrg.cpp` 路径评估;`gbplanner/src/gbplanner.cpp`(planner 主循环) |
| Dijkstra 最短路 | `planner_common`(图搜索工具)、`kdtree`(近邻) |
| Global graph / frontier / DTW 聚类 | `gbplanner.cpp` 全局层;`planner_msgs/Graph.msg`、`Vertex.msg`(带 num_unknown/occupied/free_voxels) |
| GlobalExplorationGain(公式2,time budget) | `gbplanner.cpp` 全局 gain;config `time_budget_limit`(实测 480s) |
| 3D 占据地图(occ/free/unknown) | **voxblox**(编译进 gbplanner,`planner_common` 封装) |
| 规划触发 / 航点下发 | `planner_control_interface`(PCI)+ `pci_general`(`pci_general.cpp`:发 `command/trajectory`) |
| 传感器 FOV / 增益权重 / 采样参数 | `gbplanner/config/<robot>/gbplanner_config.yaml`(`unknown_voxel_gain=60` 等) |
| RViz 可视化(红球/紫球/绿线) | `gbplanner/src/gbplanner_rviz.cpp`(配色见 [体积增益与RViz界面详解.md](archive/体积增益与RViz界面详解.md)(历史归档)) |

## 三、我们 `gbplanner_gain` 原型 vs 原始论文(诚实标注失真)

`archive/integration_桥接线冻结/navlab_gbplanner_strategy.py`(桥接期接进 world-model 的 ROS2 决策层原型,**现已随桥接线冻结入 archive**)相对原始论文是**大幅简化**的,必须如实说明:

| 维度 | 原始 GBPlanner(JFR 2020) | 我们的 gbplanner_gain 原型 | 失真/差距 |
|---|---|---|---|
| 地图维度 | **3D** 体素(voxblox occ/free/unknown) | **2D** 占据栅格(OccupancyGrid) | ⚠️ 降维;真集成走桥接方案接原版 3D |
| 规划结构 | RRG 图 + 路径级 ExplorationGain | **单步 24 方向**贪心选向 | ⚠️ 无图搜索、无路径累加,是"局部单步近似" |
| 增益定义 | 视锥内 ray casting 期望体积(公式1) | 沿方向数未知栅格 × 单元面积 | 思想一致,但非视锥模型、非路径加权 |
| 全局层 | frontier + DTW + time budget 返航 | **无** | ⚠️ 只有局部,无全局 reposition/返航 |
| 传感器 | 3D 雷达(OS0-64,360°×90°) | 依赖 SLAM 的 2D `/map` | ⚠️ 2D |

**结论(要求13 的正解)**:`gbplanner_gain` 只是"把 world-model 的脚本决策换成读图选向"的**决策层第一步原型**,借用了体积增益的**思想**,但**不是** GBPlanner 算法本身。
〔**SUPERSEDED(2026-07-07 路线切换)**:下句为撰写当时(桥接期)结论——"真正忠于原始论文的集成 = 桥接方案(ros1_bridge):让原版 ROS1 GBPlanner 原样运行,只在 ROS2 侧做数据搬运(见 [桥接接口规格.md](archive/桥接接口规格.md)(历史归档)、`archive/integration_桥接线冻结/ros1_bridge/`)"。**该结论已被推翻**:桥接线已冻结为 oracle 回归基准,当前路线 = **ROS2 原生迁移**(gbp-feat `feat/gbplanner-ros2-port`),"不失真"由 M2/M3 的 oracle 数值对拍与 P3 三维无损验收承担,见 [路线切换_ROS2迁移_2026-07-07.md](路线切换_ROS2迁移_2026-07-07.md) 与 CURRENT_STATUS。〕

## 四、mentor 论文(arXiv:2201.07067)的定位
是 GBPlanner 的**应用/扩展**(落地工作),不是原始算法。它是很好的落地参考(告诉我们"怎么用/怎么部署"),但**算法原理必须以 JFR 2020 为准**。后续文档统一:**原理引 JFR 2020;落地/应用引 2201.07067**。
