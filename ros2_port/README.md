# ros2_port — GBPlanner ROS 2 原生迁移(隔离工作区)

> 路线切换后新增(2026-07-08)。**桥接历史资产不动**,ROS 2 port 全部落在本目录隔离。
> 主线任务书:[../docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md](../docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md)。

## 目录

```text
ros2_port/
  src/
    planner_msgs/        # M1:planner_msgs ROS 2 最小消息/服务包
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
- **常量**:`int32 kForward = 0` 等常量语法 ROS 1/2 一致,原样保留。

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

## 后续(不在 M1 范围)

M2 voxblox ROS 2 后端 → M3 算法核心 ROS-free 剥离 → M4 planner 节点壳 → M5 world-model 直连联跑。见任务书。
