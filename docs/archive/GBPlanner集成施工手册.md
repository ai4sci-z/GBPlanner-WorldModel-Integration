> **[HISTORICAL]** 早期施工总纲(含已取代的 gbplanner_core 重写路线)。当前状态以 [CURRENT_STATUS.md](../../CURRENT_STATUS.md) 为准。

# GBPlanner → world-model 集成施工手册 / 自提醒

> 本文合并自《WSL2_GBPlanner集成任务说明.docx》+《自主探索决策(GBPlanner算法).md》+ 2026-06-29 对两个仓库的源码级调研。
> 状态:**调研完成,尚未开工写代码**。开发机:ThinkBook 16p G6,Ultra 9 275HX(24核)/32G/RTX5060 8G/954G SSD,Win11 + WSL2。
> 环境决策:**WSL2 + Docker**,不装双系统。

---

## 0. 一句话任务定性

world-model 的 `exploration` 任务目前用占位级 **`frontier_lite`** 策略(0.1 m/s 在平面迷宫凑 3 个目标点的冒烟闸门)。
**本任务 = 用真正的 GBPlanner(图搜索 + 体积增益)替换掉这个占位策略。**
目标位置、验收闸门、编排框架都现成;难点是跨过**三道错配**:ROS1↔ROS2、voxblox 只有 ROS1、仿真无 3D 感知。

---

## 1. 两个系统事实速查(均有源码证据)

### 1.1 world-model(你的项目,目标宿主)
| 项 | 事实 | 证据文件 |
|---|---|---|
| 定位 | 室内 GPS-denied 无人机的**编排+契约平台**(非算法库) | Go/Rust/Python/Protobuf 多语言 |
| ROS | **ROS2 Humble(默认)/ Jazzy** | 所有包 `ament_cmake`+`rclcpp`+format3 |
| SLAM | **Cartographer 2D** → `/slam/odom` + `map→base_link` → external_nav → MAVLink → ArduPilot | `navlab_cartographer_2d_real.lua` |
| ROS2 SLAM 包 | navlab_slam_bringup / navlab_cartographer_adapter / navlab_external_nav_bridge / navlab_slam_imu_bridge / navlab_fake_odom | `navlab/common/slam/ros/` |
| 仿真无人机 | `navlab_iq_quad`:**仅 2D 雷达** `/scan_ideal`(gpu_lidar 361×1 平面)+ 朝下测距 `/rangefinder/down/scan_ideal` | `docker/navlab_models/navlab_iq_quad/model.sdf` |
| 3D 通路 | infra 有 **Fast-LIO(Livox 3D)** 镜像,但**未挂到无人机** | `docker/images/infra/fast-lio.Dockerfile` |
| 仿真世界 | empty_headless / iq_quad_figure8 / iq_quad_obstacle(平面 20×12,单箱 1×4×2m)/ uav_obstacle_5m → **全是平面单层** | `docker/worlds/` |
| 编排 | Go 显式注册表:`configs/tasks/*.yaml` + `internal/tasks/` 注册 + `docker/images/` 镜像 | `orchestration/sim/`(cmd/navlab-sim, internal/{config,tasks,runtime,images,artifacts,tui}) |
| 现 exploration | `strategy: frontier_lite`(占位),150s,needs gazebo/sitl/slam,0.1m/s,min_accepted_goals=3,return_home_then_land | `orchestration/sim/configs/tasks/exploration.yaml` |
| 契约 | Protobuf:navlab/{orchestration,runtime,safety,sensors}/v1;runtime/v1 = probe_spec/process_event/runtime_plan/service_spec/task_result;**无 pose/map/waypoint 规划契约** | `contracts/proto/` |
| 镜像 | base/ros-base;infra/{ardupilot-sitl,fast-lio,gazebo-headless,mavlink-router};runtime/{companion,gazebo-sensor,official-baseline(=ArduPilot 全栈),slam,sim-python} | `docker/images/` |
| 跑法 | 全 Docker,`navlab/*:humble-latest`,可用 `gazebo-headless` | `docker/compose/` |

### 1.2 GBPlanner(待集成算法,ntnu-arl/gbplanner_ros @ `gbplanner2`)
| 项 | 事实 | 证据 |
|---|---|---|
| 形态 | **ROS1 catkin**(Noetic/Ubuntu20.04;或 Melodic/18.04) | `gbplanner/package.xml`:`catkin`+`catkin_simple` |
| 地图库 | **voxblox_ros**(TSDF/ESDF,occ/free/unknown),**编译进 gbplanner,非独立节点** | `gbplanner/package.xml` depend `voxblox_ros` |
| 包组 | gbplanner / planner_common / planner_msgs / planner_semantic_msgs / kdtree / **planner_control_interface**(pci_manager.h, planner_control_interface.h) / planner_gazebo_sim / gbplanner_ui | repo 根 |
| 核心源码 | `gbplanner.cpp`+`rrg.cpp`(RRG 采样+光线投射+VolumeGain);`gbplanner_ros_node.cpp`;`gbplanner_rviz.cpp` | `gbplanner/src/` |
| 依赖拉取 | `packages_https.rosinstall`(voxblox、eigen_catkin、catkin_simple、gflags/glog、minkindr、mav_comm 等) | repo 根 |
| **输入** | 点云 `/pointcloud` ← `/<robot>/velodyne_points`(**3D Velodyne**);里程计 `odometry` ← `/<robot>/ground_truth/odometry_throttled`;TF `world→navigation` | `gbplanner/launch/rmf/rmf_sim.launch` |
| **输出** | 经 **PCI**(`pci_general_ros_node`)下发轨迹/航点给控制器 | 同上 |
| 参考控制器 | **RotorS `lee_position_controller`**(spawn_mav) | 同上 |
| 配置 | `config/<robot>/gbplanner_config.yaml`、`voxblox_sim_config.yaml`、`planner_control_interface_sim_config.yaml` | 同上 |

---

## 2. 三道错配 & 对策(核心架构决策)

| # | 错配 | 对策(必须早定) |
|---|---|---|
| 1 | **ROS1(GBPlanner)↔ ROS2(world-model)** | ~~抽 ROS-agnostic 核心库 `gbplanner_core` + 写 rclcpp 节点;ros1_bridge 不进最终方案~~ **⚠️ 旧路线,已被用户拍板的桥接方案取代(2026-07-05)**:保留原版 ROS1 GBPlanner,标准消息过桥(实测选型=**B2.5 自写薄桥**,官方 ros1_bridge 与 zenoh 均实验判死);`gbplanner_core` 降为备选/理解材料 |
| 2 | **voxblox 仅 ROS1** | ROS2 侧换 3D 建图前端:**octomap_server2**(原生 occ/free/unknown,最稳)或 **nvblox**(NVIDIA GPU,用上 RTX5060)。靠 `VoxelMapInterface` 抽象,核心库不绑定具体实现 |
| 3 | **仿真无 3D 感知 + 控制器不同** | (a) 给 `navlab_iq_quad/model.sdf` 加 **3D LiDAR/深度相机**(发 velodyne 式点云);(b) PCI 输出**重定向到 MAVLink/ArduPilot**(复用现有 fcu_controller/external_nav),不要 RotorS Lee 控制器 |

**分层设计:**
- **核心层 `gbplanner_core`(纯 C++,无 ROS,无 voxblox):** planner(RRG)/ gain evaluator / ray caster / `VoxelMapInterface`(occ/free/unknown + 分辨率)/ `TraversabilityInterface`(点可通行 + 路径碰撞)/ waypoint 输出。
- **适配层(ROS2):** rclcpp 节点(仿 `external_nav_bridge` 范式)订阅点云+里程计 → 建图前端实现 `VoxelMapInterface` → 调核心 → 发布航点 + status;再把航点转 MAVLink。

---

## 3. 目标数据流

```
3D LiDAR/深度相机(需新加到 navlab_iq_quad)
  → Fast-LIO 或仿真 ground-truth (odom + 3D 点云)
    → [ROS2 3D 建图: octomap_server2 / nvblox]      ← 替代 ROS1 voxblox
       → VoxelMapInterface (occ/free/unknown)
          → gbplanner_core: RRG 采样 → ray casting 算 VolumeGain
             → 距离/转向/风险惩罚评分 → 选路;局部无增益 → global frontier
                → 航点 → ROS2 node 发布 + protobuf 规划契约
                   → fcu_controller / external_nav → MAVLink → ArduPilot SITL → 无人机
```

---

## 4. 环境搭建清单(WSL2 + Docker · 待执行,先不装)

> 原则:源码与编译目录放 **Linux 文件系统**(`~/ws/...`),**绝不在 `/mnt/c` 下编译**。硬盘按 **954G 实际容量**规划,不照搬 docx 的 1T/1T/1T。

```bash
# ── Windows PowerShell(管理员)──
wsl --install -d Ubuntu-22.04        # ROS2 Humble 对应 Ubuntu 22.04
wsl --update                          # 确保 WSLg(GUI)与 GPU 直通

# ── WSL2 Ubuntu 内 ──
# Docker(推荐 Docker Desktop 开 WSL2 集成,或 WSL 内装 docker engine)
# NVIDIA 容器(给 Gazebo/nvblox 用 GPU):
#   装 nvidia-container-toolkit;Win 侧装好 NVIDIA 驱动即可,WSL2 自动透传 CUDA

mkdir -p ~/ws && cd ~/ws
git clone https://github.com/SZ-surveying/world-model.git
# 跑通基线(全 Docker,无需本机装 ROS):
cd world-model/docker/compose
docker compose pull        # 拉 navlab/*:humble-latest
# 用 Go 编排起 exploration 基线任务(确认现有 frontier_lite 能跑):
cd ../../orchestration/sim && go run ./cmd/navlab-sim --help
```

**P0 参考环境(独立,仅供学习原版 GBPlanner):**
```bash
# ROS1 Noetic 容器跑官方 sim(Ubuntu20.04)
docker run -it --gpus all --net host ros:noetic-robot bash
# 容器内:装 catkin-tools/glog/octomap-ros → clone gbplanner_ros -b gbplanner2
#   → wstool/rosinstall 拉 voxblox 等 → catkin config -DCMAKE_BUILD_TYPE=Release → catkin build
#   → roslaunch gbplanner rmf_sim.launch   (看 RViz 里 velodyne 点云 + 探索图 + 航点)
```

---

## 5. 阶段路线图(P0–P4)

| 阶段 | 目标 | 关键动作 | 验收 | 产出 |
|---|---|---|---|---|
| **P0** | 看懂原版算法 | ROS1 Docker 跑通 `rmf_sim.launch`,录下 I/O、参数、行为 | RViz 看到探索图+航点 | 算法认知笔记 |
| **P1** | 离线核心 | 抽 `gbplanner_core`(剥 ROS/voxblox)+ 合成 voxel map demo + 单测 | 单测全绿 | 可独立验证的核心库 |
| **P2** | ROS2 落地 | rclcpp 节点 + octomap_server2/nvblox 建图,接 world-model odom/点云 | ROS2 里出航点 | ROS2 planner 节点 |
| **P3** | 编排集成 | 给 iq_quad 加 3D 传感器;`exploration.yaml` 改 `strategy: gbplanner`;Go 注册;补 planning.proto;航点→MAVLink | 过现有 exploration 闸门 | 集成可跑 |
| **P4**(可选) | 闭环/UE | 航点→MAVLink 完整闭环;UE 联动 | 演示 | 真机/UE demo |

**P1 单测必须覆盖:** unknown 体素统计 / 射线遇 occupied 停止 / 距离惩罚 / 转向惩罚 / 障碍碰撞检查 / 局部无增益时转 global frontier。

---

## 6. 关键接口规格

### 6.1 GBPlanner 原生 I/O(P0 对照用)
- 输入点云 topic:`/pointcloud`(remap 自 `/<robot>/velodyne_points`,**3D**)
- 输入里程计:`odometry`(remap 自 `.../ground_truth/odometry_throttled`)
- TF:`world → navigation` 静态变换;voxblox 在此坐标系建图
- 输出:`pci_general_ros_node`(PCI)下发轨迹/航点;触发规划走 service/action
- 配置三件套:`gbplanner_config.yaml`(增益/采样/传感器FOV)、`voxblox_sim_config.yaml`(分辨率/截断)、`planner_control_interface_sim_config.yaml`

### 6.2 world-model 接入点
- **任务**:`orchestration/sim/configs/tasks/exploration.yaml` → `exploration_gate.strategy: gbplanner`
- **注册**:`orchestration/sim/internal/tasks/`(Go 显式注册)
- **镜像**:新增 `docker/images/runtime/gbplanner.Dockerfile`(base `ros-base`,ROS2 Humble)
- **契约**:新增 `contracts/proto/navlab/runtime/v1/planning.proto`(航点/规划状态),供 Go/Rust/Python 共用
- **控制**:航点 → 复用 `navlab_external_nav_bridge` 同侧的 fcu_controller → MAVLink → ArduPilot SITL
- **建图前端**:仿 `navlab_cartographer_adapter`,做一个 `navlab_gbplanner_bridge` ROS2 包

### 6.3 传感器改造(P3 前置)
`navlab_iq_quad/model.sdf` 增加 3D 传感器:
- 选项 A:Livox(配 `fast-lio.Dockerfile`,出 `/<robot>/livox/points` → Fast-LIO 出 odom + 去畸变点云)
- 选项 B:`gpu_lidar` 多垂直线(如 16/32 线,模拟 Velodyne,直发 `/<robot>/velodyne_points`)→ 最贴近 GBPlanner 原生
- 选项 C:深度相机(室内近距更稳)

---

## 7. 风险登记册

| # | 风险 | 严重度 | 规避 |
|---|---|---|---|
| 1 | ROS1↔ROS2 不通 | 高 | ~~核心库无 ROS + ROS2 节点;ros1_bridge 仅原型~~ **旧对策,已改桥接方案(B2.5 自写薄桥,transport 三段已实测通)** |
| 2 | voxblox 仅 ROS1(隐藏成本最大) | 高 | 早抽 VoxelMapInterface;ROS2 用 octomap_server2/nvblox |
| 3 | 仿真无 3D 感知 | 高 | 先改 iq_quad 加 3D 传感器,否则 GBPlanner 无 unknown 体积可探 |
| 4 | 世界全是平面单层 | 中 | 垂直探索需 3D 结构世界;先用平面验证 2.5D,再换隧道世界 |
| 5 | 控制器错配(RotorS≠ArduPilot) | 中 | 丢弃 PCI 的 Lee 控制路径,航点转 MAVLink setpoint |
| 6 | WSL2 Gazebo GPU 渲染坑 | 中 | 用 `gazebo-headless` + rosbag/RViz,绕 GUI |
| 7 | TF/坐标系不一致 | 中 | 对齐 `map→base_link`(Cartographer)或 Fast-LIO odom 到 `world→navigation` |
| 8 | 范围蔓延 | 中 | 严守 exploration 闸门(min_accepted_goals/min_path_length),增量替换,不搞整套 CERBERUS |

---

## 8. UE ↔ Linux 联动(现实澄清 + 选型)

⚠️ **world-model 当前不用 UE,用的是 Gazebo(headless)+ ArduPilot SITL。** UE 是 docx 里的设想,需新设计一层。联动选型:
- **AirSim / Colosseum(UE 插件)**:Win 跑 UE+AirSim 渲染与传感器仿真 → 经 AirSim ROS bridge 把点云/里程计喂给 WSL2 的 ROS2。最贴合"UE 出传感器"。
- **ROS-TCP-Connector(Unity)/ 自定义 socket**:若不用 AirSim,可自写 TCP 桥把 UE 传感器/位姿序列化给 ROS2。
- **MAVLink 直连**:UE 侧只做渲染,飞控仍走 ArduPilot SITL,UE 通过 MAVLink 取位姿做可视化。
- **Pixel Streaming**:仅做远程可视化,不参与算法回路。
- **建议**:先做**不依赖 UE 的最小 planner**(P1–P3 走 Gazebo),UE 放 P4。若要 UE 出 3D 传感器,优先 AirSim 路线。

---

## 9. 交付物清单

1. `gbplanner_core/` — 无 ROS C++ 库 + CMake(RRG/raycast/gain/frontier)
2. 抽象接口:`VoxelMapInterface`、`TraversabilityInterface`
3. ROS2 节点包 `navlab_gbplanner_bridge`(rclcpp)
4. ROS2 3D 建图前端接入(octomap_server2 或 nvblox)实现 VoxelMapInterface
5. `navlab_iq_quad` 加 3D 传感器(model.sdf 改造)
6. `docker/images/runtime/gbplanner.Dockerfile`
7. `exploration.yaml`(strategy: gbplanner)+ Go 注册 + `planning.proto` 契约
8. 航点 → MAVLink 转换(复用 fcu_controller/external_nav)
9. 离线 demo + 单测(§5 六项)
10. 集成测试(过 exploration 闸门)
11. 本手册持续更新

---

## 10. 开工前待确认 / 待调参(施工期解决,非阻塞)

- [ ] `gbplanner_config.yaml` 实际参数值(增益权重/采样数/传感器 FOV)— P0 跑通后抄
- [ ] PCI 输出的精确 message 类型(`planner_msgs`)— 读 planner_control_interface.h
- [ ] octomap_server2 vs nvblox 最终取舍(是否用 GPU)
- [ ] frontier_lite 在 Go 编排中的确切位置与调用方式(`internal/tasks/`)
- [ ] 3D 传感器选型(Livox+FastLIO vs 多线 gpu_lidar vs 深度相机)
- [ ] 是否需要 3D 结构的隧道世界来测垂直探索

---

## 11. 给 AI / Codex 的标准提示词

> 我在 Windows + WSL2 Ubuntu 22.04 + Docker 下开发 https://github.com/SZ-surveying/world-model(ROS2 Humble 编排平台,SLAM=Cartographer 2D,仿真无人机 navlab_iq_quad 仅 2D 雷达,exploration 任务现用占位 frontier_lite)。
> 目标:把 ntnu-arl/gbplanner_ros(gbplanner2,ROS1 catkin,地图库 voxblox_ros)的 GBPlanner 集成进来替换 frontier_lite,用于基于 3D occ/free/unknown 占据栅格的自主探索。
> 约束:GBPlanner 是 ROS1、项目是 ROS2 → 必须抽 ROS-agnostic 核心库 gbplanner_core(VoxelMapInterface/TraversabilityInterface)+ ROS2 rclcpp 节点;voxblox 仅 ROS1 → ROS2 侧用 octomap_server2 或 nvblox;仿真需先给 iq_quad 加 3D 传感器;航点输出重定向到 MAVLink/ArduPilot(非 RotorS)。
> 请先按 P0→P4 路线给出当前阶段的具体实现,不要跨阶段;先离线核心+单测,再 ROS2,再编排集成。
```
```
```

---

*最后更新:2026-06-29 · 调研阶段完成,未写项目代码。*
