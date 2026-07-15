# ros2_port — GBPlanner ROS 2 原生迁移(隔离工作区)

> 路线切换后新增(2026-07-08)。**桥接历史资产不动**,ROS 2 port 全部落在本目录隔离。
> 主线任务书:[../docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md](../docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md)。
>
> **当前状态(2026-07-15,事实源=main 分支 CURRENT_STATUS.md)**:
> M1 msgs ✅ / M2 voxblox ✅(五切片全过)/ M3 core 剥离 ✅(12k 行,单测 4/4;
> "3D 行为等价"未证,Review 002 判 NOT PROVEN)/ M4a 合成冒烟 ✅(M4b 真场景 open-loop 未测)/
> **M5 ⏸ BLOCKED_BY_PLATFORM_STABILITY**(GATE-4b 60s 悬停硬门重开;恢复前必须清
> Review 001 P0-1 单线程 executor、P0-4 readiness gate、P1-1~P1-8 等债务,见 main)。
> 下文 M1/M2 段落为历史施工记录,保留不动。

## 目录

```text
ros2_port/
  src/
    planner_msgs/            # M1:planner_msgs ROS 2 最小消息/服务包
    voxblox_ros2_minimal/    # M2:voxblox ROS 2 底座(vendored,见下方来源)
  docs/
    m2_scout_1_底座移植质量审计.md   # M2 侦察报告(3 并行审计,构建/移植前必读)
    m2_scout_2_ntnu定制diff审计.md   # 行为等价命门:ntnu tsdf_integrator 定制
    m2_scout_3_jazzy构建配方.md      # Jazzy 依赖清单与构建配方来源
  (build/ install/ log/ 由 colcon 生成,已 .gitignore)
```

## M1:planner_msgs 最小集

**只迁最小闭环**(不迁 13 msg + 24 srv + 1 action 全家桶)。当前集 = 核心规划服务 `PlannerSrv` + 它依赖的模式枚举:

| ROS 2 文件 | 迁自 ROS 1 | 说明 |
|---|---|---|
| `srv/PlannerSrv.srv` | `planner_srv.srv` | 核心:请求规划、返回 `geometry_msgs/Pose[]` 路径 |
| `srv/PlannerSetPlanningMode.srv` | `planner_set_planning_mode.srv` | 设置 manual/auto 规划模式 |
| `srv/PlannerHoming.srv` | `planner_homing.srv` | 请求回家最短路径 |
| `msg/PlanningMode.msg` | `PlanningMode.msg` | basic/narrow/adaptive 探索模式枚举 |
| `msg/BoundMode.msg` | `BoundMode.msg` | 碰撞检查 bound 模式枚举 |
| `msg/TriggerMode.msg` | `TriggerMode.msg` | PCI 触发模式枚举 |
| `msg/ExecutionPathMode.msg` | `ExecutionPathMode.msg` | 执行路径模式枚举 |
| `msg/PlannerStatus.msg` | `PlannerStatus.msg` | 规划器状态(聚合以上枚举) |

**依赖**:`std_msgs`(`Header`)、`geometry_msgs`(`Pose`/`Point`)。**不迁** `actionlib_msgs`(无 action)。

### ROS 1 → ROS 2 迁移记录(诚实标注)

- **文件名 PascalCase**:rosidl 要求接口文件 CamelCase,故 3 个服务由 snake_case 重命名(`planner_srv`→`PlannerSrv` 等)。**消息/服务字段内容逐字保持**,仅类型名大小写变化;桥接已废、无 ROS 1 互操作需求,采 ROS 2 惯用命名。
- **`Header` → `std_msgs/Header`**:ROS 2 不再隐式解析裸 `Header`。
- **同包引用用裸名**:`PlannerStatus.msg` 内 `TriggerMode trigger_mode` 等,rosidl 自动解析同包类型。
- **构建系统**:catkin `message_generation` → ament_cmake + `rosidl_default_generators`;`package.xml` format 2 → format 3。
- **常量改名 UPPER_SNAKE_CASE**:rosidl 强制常量命名 `[A-Z][A-Z0-9_]*`,ROS 1 的 `kManual/kAuto/kForward` 等 kCamelCase **直接报错拒编**(实测),全部改为 `K_MANUAL/K_AUTO/K_FORWARD` 等;**常量值逐字保持**,调用侧迁移时需同步改名(已在各 .msg 顶部注释标注)。

## 构建(必须在 ROS 2 Jazzy 环境)

> ⚠️ 历史记录(WSL 期)。2026-07-13 已迁移到原生 Ubuntu 24.04;容器构建方式仍有效。

本机 WSL 原生是 Ubuntu 22.04(Jammy),**无原生 Jazzy**;项目 Jazzy 只在 docker 镜像里。故 colcon build 在 jazzy 容器内进行,挂载本目录:

```bash
# 在 WSL:把 ros2_port 挂进 jazzy 容器构建
docker run --rm -v <ros2_port 绝对路径>:/ws -w /ws <jazzy镜像> \
  bash -lc "source /opt/ros/jazzy/setup.bash && colcon build && \
            source install/setup.bash && \
            ros2 interface show planner_msgs/srv/PlannerSrv"
```

验收(M1):`colcon build` 通过 + `ros2 interface show planner_msgs/srv/PlannerSrv` 可打印 + 无 ROS1/catkin/actionlib 依赖。构建证据见 [../runbooks/ros2_port/](../runbooks/ros2_port/)(若已生成)。

## M2:voxblox ROS 2 底座(✅ 已收口 2026-07-14)

**vendored 来源**:[snt-arg/voxblox_ros2_minimal](https://github.com/snt-arg/voxblox_ros2_minimal) @ **d08e9d4**(2025-12-01,upstream HEAD),剥离 .git 整树收入 `src/voxblox_ros2_minimal/`(2.8MB,9 包:voxblox core / voxblox_ros / voxblox_msgs / voxblox_rviz_plugin / voxblox_skeleton + vendored eigen_checks / minkindr / minkindr_conversions / xmlrpcpp)。选型依据 [../docs/ros2迁移_voxblox选型_2026-07-07.md](../docs/ros2迁移_voxblox选型_2026-07-07.md);后续对底座的全部修改都在本仓以独立 commit 留痕(=我们的维护 fork)。

**切片计划与状态**(侦察依据 `docs/m2_scout_*.md`):

| 切片 | 内容 | 状态 |
|---|---|---|
| 1 | **纯净底座 Jazzy 全量构建**(零源码改动,复刻 Gabriele CI 口径) | ✅ 9/9 包 2min27s,COLCON_RC=0;6 executables;esdf_server 冒烟能跑(证据 [../runbooks/ros2_port/m2_build_evidence.txt](../runbooks/ros2_port/m2_build_evidence.txt)) |
| 2 | 维护补丁:删 voxblox_ros 幽灵依赖 voxblox_rviz_plugin;采纳 Gabriele b5c3911(rclcpp 先 init+auto-declare,修 gflags 吃 --ros-args,冒烟已实锤该 bug)并补齐其漏掉的 esdf/intensity server node | ✅ 最小集 7 包成立(rviz_plugin 不再被拖入);9/9 全量 rc=0;**参数管道 E2E 实证:`ros2 param get /voxblox world_frame`→`map`**,弃用警告消失(证据 [../runbooks/ros2_port/m2_build2_evidence.txt](../runbooks/ros2_port/m2_build2_evidence.txt)) |
| 3 | **行为等价补丁**:ntnu dev/noetic 的 tsdf_integrator 定制移植(3 新权重字段+删 sparsity+fast 提前终止)+ ros_params 对齐 + test_sdf_integrators 单测 | ✅ 补丁=`git diff 8d1b843 dev-noetic`(原件 [../runbooks/ros2_port/ntnu_tsdf_integrator.patch](../runbooks/ros2_port/ntnu_tsdf_integrator.patch),19/20 hunk 干净套上+1 个 header hunk 手补虚函数声明);ros_params 三参数换血(clearing_ray_weight_factor/weight_ray_by_range/use_symmetric_weight_dropoff 进,sparsity 两参数出);**gtest 10/10 PASSED**+sparsity 符号零残留(证据 [../runbooks/ros2_port/m2_build3_evidence.txt](../runbooks/ros2_port/m2_build3_evidence.txt)) |
| 4 | oracle 对拍:同点云 ROS1(ntnu dev/noetic)vs ROS2,save_map 层文件按体素查询比对 | ✅ **TSDF 双积分器全 PASS**(harness=[oracle_cmp/](oracle_cmp/),输入逐字节一致 SHA 互证):**simple=46/46 块、35,323/35,323 观测体素零差、距离场 RMS 1e-4**;fast(GBPlanner 实际用)=mismatch 2/34,506(0.0058%,竞态噪声)。路上抓到并修掉真移植 bug:min_time 节流 1s 无操作(from_seconds 静态工厂误用)+ 实测纠正订阅名为私有名 `/voxblox_node/pointcloud`。证据 [../runbooks/ros2_port/m2_oracle_cmp_evidence.txt](../runbooks/ros2_port/m2_oracle_cmp_evidence.txt) |
| 5 | M2 收尾:ESDF 对拍 + world-model 场景建图(订 /wm/cloud3d 或 lidar3d)+ RViz2 可见 | ✅ ESDF oracle 对拍 PASS(RMS 2.5e-05)+ 场景建图 3.0MB/18,202 体素 + RViz2 截图(feat `404ac67`/`8fba00a`) |

**构建配方**(禁 rosdep——package.xml 有 ROS1 时代 key):deps 镜像 [../runbooks/ros2_port/m2_deps.Dockerfile](../runbooks/ros2_port/m2_deps.Dockerfile)(镜像名 `voxblox_ros2_deps:jazzy`,apt 清单源自 Gabriele Jazzy CI),构建脚本 [../runbooks/ros2_port/m2_build.sh](../runbooks/ros2_port/m2_build.sh)。

**已知陷阱**(详见侦察报告):GBPlanner yaml 的 `sparsity_compensation_factor=100` 在 ethz 血统底座上会激活 ×100 权重发散(ntnu 下是死参数)——切片 3 前禁止直接套 GBPlanner 配置;xmlrpcpp 是 ROS1 参数残留死路(仅 `use_tf_transforms=false` 分支),GBPlanner 用 True 不受影响,暂留后除。

## M3-M5(状态见顶部横幅与 main CURRENT_STATUS)

- **M3 ✅(feat `e61052d`)**:核心 12,143 行剥离为 ament 库(`src/gbplanner_core/`),零 `ros/ros.h`,单测 4/4。
  口径纪律(Review 001 P1-6):只能说 **ROS1-free / node-wrapper-free**,不能说 "ROS-free"
  (接口仍依赖 ROS2 消息/tf2/voxblox_ros);"3D 算法行为等价"未证,需 ROS1 oracle 3D fixture 对拍。
- **M4a ✅(feat `be7d6e0`)**:节点壳 `src/gbplanner_node/` + 最小 PCI 触发,合成场景 RRG 出 12wp 轨迹。
  PCI 替身只是 smoke 工具(Review 002 §13.1),恢复 M5 前须另做 planning coordinator。
- **M5 ⏸ BLOCKED**:数据链已证通(真 odom/点云进、轨迹/intent 出,run 20260714T095739),
  飞行闭环 FAIL;当前 adapter 丢弃 z,只能算 XY 诊断切片,最终口径必须含 z 闭环(多层 Demo 硬要求)。
