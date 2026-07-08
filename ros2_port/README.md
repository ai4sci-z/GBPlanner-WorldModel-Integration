# ros2_port — GBPlanner ROS 2 原生迁移(隔离工作区)

> 路线切换后新增(2026-07-08)。**桥接历史资产不动**,ROS 2 port 全部落在本目录隔离。
> 主线任务书:[../docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md](../docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md)。

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

本机 WSL 原生是 Ubuntu 22.04(Jammy),**无原生 Jazzy**;项目 Jazzy 只在 docker 镜像里。故 colcon build 在 jazzy 容器内进行,挂载本目录:

```bash
# 在 WSL:把 ros2_port 挂进 jazzy 容器构建
docker run --rm -v <ros2_port 绝对路径>:/ws -w /ws <jazzy镜像> \
  bash -lc "source /opt/ros/jazzy/setup.bash && colcon build && \
            source install/setup.bash && \
            ros2 interface show planner_msgs/srv/PlannerSrv"
```

验收(M1):`colcon build` 通过 + `ros2 interface show planner_msgs/srv/PlannerSrv` 可打印 + 无 ROS1/catkin/actionlib 依赖。构建证据见 [../runbooks/ros2_port/](../runbooks/ros2_port/)(若已生成)。

## M2:voxblox ROS 2 底座(进行中)

**vendored 来源**:[snt-arg/voxblox_ros2_minimal](https://github.com/snt-arg/voxblox_ros2_minimal) @ **d08e9d4**(2025-12-01,upstream HEAD),剥离 .git 整树收入 `src/voxblox_ros2_minimal/`(2.8MB,9 包:voxblox core / voxblox_ros / voxblox_msgs / voxblox_rviz_plugin / voxblox_skeleton + vendored eigen_checks / minkindr / minkindr_conversions / xmlrpcpp)。选型依据 [../docs/ros2迁移_voxblox选型_2026-07-07.md](../docs/ros2迁移_voxblox选型_2026-07-07.md);后续对底座的全部修改都在本仓以独立 commit 留痕(=我们的维护 fork)。

**切片计划与状态**(侦察依据 `docs/m2_scout_*.md`):

| 切片 | 内容 | 状态 |
|---|---|---|
| 1 | **纯净底座 Jazzy 全量构建**(零源码改动,复刻 Gabriele CI 口径) | ✅ 9/9 包 2min27s,COLCON_RC=0;6 executables;esdf_server 冒烟能跑(证据 [../runbooks/ros2_port/m2_build_evidence.txt](../runbooks/ros2_port/m2_build_evidence.txt)) |
| 2 | 维护补丁:删 voxblox_ros 幽灵依赖 voxblox_rviz_plugin;采纳 Gabriele b5c3911(rclcpp 先 init+auto-declare,修 gflags 吃 --ros-args,冒烟已实锤该 bug)并补齐其漏掉的 esdf/intensity server node | ✅ 最小集 7 包成立(rviz_plugin 不再被拖入);9/9 全量 rc=0;**参数管道 E2E 实证:`ros2 param get /voxblox world_frame`→`map`**,弃用警告消失(证据 [../runbooks/ros2_port/m2_build2_evidence.txt](../runbooks/ros2_port/m2_build2_evidence.txt)) |
| 3 | **行为等价补丁**:ntnu dev/noetic 的 tsdf_integrator 定制移植(3 新权重字段+删 sparsity+fast 提前终止)+ ros_params 对齐 + test_sdf_integrators 单测 | ⬜ |
| 4 | oracle 对拍:同点云 ROS1(ntnu dev/noetic)vs ROS2,save_map 层文件按体素查询比对(proto 字节级一致已证) | ⬜ |

**构建配方**(禁 rosdep——package.xml 有 ROS1 时代 key):deps 镜像 [../runbooks/ros2_port/m2_deps.Dockerfile](../runbooks/ros2_port/m2_deps.Dockerfile)(镜像名 `voxblox_ros2_deps:jazzy`,apt 清单源自 Gabriele Jazzy CI),构建脚本 [../runbooks/ros2_port/m2_build.sh](../runbooks/ros2_port/m2_build.sh)。

**已知陷阱**(详见侦察报告):GBPlanner yaml 的 `sparsity_compensation_factor=100` 在 ethz 血统底座上会激活 ×100 权重发散(ntnu 下是死参数)——切片 3 前禁止直接套 GBPlanner 配置;xmlrpcpp 是 ROS1 参数残留死路(仅 `use_tf_transforms=false` 分支),GBPlanner 用 True 不受影响,暂留后除。

## 后续

M3 算法核心 ROS-free 剥离(注意:GBPlanner 是**进程内实例化 TsdfServer**,构造签名 ROS1 `(nh,nh_private)`→ROS2 `(rclcpp::Node*)` 需适配)→ M4 planner 节点壳 → M5 world-model 直连联跑。见任务书。
