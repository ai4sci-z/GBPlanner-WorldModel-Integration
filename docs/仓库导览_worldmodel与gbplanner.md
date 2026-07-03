# 仓库导览:world-model 与 gbplanner 的文件夹都是干嘛的

> 📌 **2026-07-03 校核**:本文内容仍有效。项目最新全景与"你在这里"路线图见 [README](../README.md);运行时排坑最新进展见 [运行时排错记录_humble.md](运行时排错记录_humble.md)。

> 桌面已放两份源码供你浏览:`world-model源码浏览/`、`gbplanner源码浏览/`。
> 本文逐个文件夹说明:**是什么 / 在我们任务里的角色 / 我们怎么处理**。最后更新 2026-06-29。

---

# 一、world-model(你的项目宿主,ROS2 仿真编排平台)

| 文件夹/文件 | 是什么 | 在我们任务里的角色 | 我们怎么处理 |
|---|---|---|---|
| `README.md`、`justfile` | 项目说明 / 命令快捷方式(build、run 等) | 入门、跑命令靠它 | 只读;用 justfile 的命令 |
| `navlab/` | **Python 运行时**:ROS 节点、SLAM 适配、传感器仿真 | 平台运行时大脑(Python 侧) | 主要只读;了解 SLAM/传感器接口 |
| `navlab/common/slam/` | Cartographer(2D)SLAM 适配 + ROS2 桥接包 | 提供里程计/地图——GBPlanner 要用 | **重点参考**:桥接要从这里取 odom/点云 |
| `orchestration/sim/` | **Go 仿真编排**:任务注册、镜像构建、Docker 调度 | 决定跑哪个任务、构建镜像 | **要改**:加 GBPlanner 镜像、改 exploration 任务 |
| `orchestration/sim/configs/tasks/` | 各任务 YAML(含 `exploration.yaml`) | exploration 用 `frontier_lite` 占位 | **要改**:把 strategy 换成 GBPlanner |
| `orchestration/real/` | Rust 真机编排 | 真机流程(暂不涉及) | 暂不动 |
| `contracts/` | **Protobuf 契约**(跨语言数据格式) | 各模块通信约定 | 可能加"航点/规划"契约 |
| `docker/` | **镜像定义 + 仿真世界 + 无人机模型** | 仿真的"积木" | **要改**:加 3D 雷达到无人机模型;加 GBPlanner 镜像 |
| `docker/images/{base,infra,runtime}/` | 各镜像 Dockerfile(ros-base/ardupilot-sitl/gazebo/slam 等) | 我们构建的 9 个镜像来源 | 参考;新增 gbplanner 镜像 |
| `docker/worlds/` | Gazebo 世界(迷宫/障碍,平面单层) | 仿真场景 | 可能加 3D 结构世界测垂直探索 |
| `docker/navlab_models/navlab_iq_quad/` | **仿真无人机模型**(目前只有 2D 雷达) | GBPlanner 需要 3D 点云 | **要改**:给它加 3D 雷达 |
| `compose/` | docker-compose 编排文件 | 一键起多容器 | 参考/复用 |
| `scripts/` | 质量检查、命令工具 | 辅助 | 只读 |
| `third_party/` | 子模块:ardupilot、Livox-SDK2、YDLidar-SDK | 飞控/雷达驱动源码 | 构建依赖,不手改 |
| `artifacts/` | 仿真运行的输出(日志/rosbag/回放) | **看仿真结果的地方** | 跑完看这里 + Foxglove |

**一句话**:world-model 我们主要改 3 处 —— `orchestration/sim`(加任务/镜像)、`docker`(加 3D 雷达/GBPlanner 镜像)、`navlab/common/slam`(取数据接桥)。

---

# 二、gbplanner_ros(要集成的算法,ROS1)

| 文件夹 | 是什么 | 在我们任务里的角色 | 我们怎么处理 |
|---|---|---|---|
| `gbplanner/` | **核心规划器**(src: `gbplanner.cpp` 主逻辑、`rrg.cpp` 随机图);config/launch | 算法主体 | **桥接方案下原样跑**(不改);参数参考 |
| `gbplanner/launch/rmf/` | 无人机(aerial)仿真启动文件 `rmf_sim.launch` | 预研B 跑的就是它 | 跑它看效果;参考它的话题接线 |
| `gbplanner/config/rmf/` | 参数:增益权重、采样数、voxblox 分辨率、传感器 FOV | 调参依据 | 抄参数 |
| `planner_common/` | 公共库(地图、几何工具) | 被核心依赖 | 不改 |
| `planner_msgs/` `planner_semantic_msgs/` | 自定义消息类型 | 话题数据结构 | 桥接时 ros1_bridge 要映射它们 |
| `planner_control_interface/` | **PCI**:把规划结果(航点)下发给控制器 | 输出航点的出口 | **桥接重点**:从这里取航点回流 ROS2 |
| `kdtree/` | KD 树(近邻搜索) | 采样/查询加速 | 不改 |
| `planner_gazebo_sim/` | 仿真辅助 | 预研B 仿真用 | 跑仿真用 |
| `gbplanner_ui/` | RViz 交互面板 | 可视化/触发规划 | 看仿真用 |
| `packages_https.rosinstall` | 依赖清单(voxblox、catkin_simple、rotors 等) | 构建时拉依赖 | 预研B 镜像已据此装好 |

**一句话**:桥接方案下,gbplanner_ros **基本原样在 ROS1 容器里跑**;我们重点对接的是它的**输入**(点云/里程计话题)和**输出**(PCI 的航点),用 ros1_bridge 接到 world-model。

---

# 三、两者如何拼起来(回顾)
```
world-model(ROS2):提供 点云+里程计 ──ros1_bridge──► gbplanner_ros(ROS1):算探索航点
                    ◄──ros1_bridge── 航点(经 PCI)──► 发到 /navlab/exploration/* ──► 无人机飞
```
