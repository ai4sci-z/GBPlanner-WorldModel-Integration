# NavLab 参考项目综合分析

## 1. 目的

这份文档综合四个参考项目的项目索引，提炼它们对 NavLab 室内无 GPS SLAM 悬停与后续探索任务的实际启发。重点不是判断哪个项目“最好”，而是识别哪些机制值得吸收，哪些做法会和 NavLab 的真实闭环目标冲突。

参考文档：

- `/home/nn/workspace/3588/examples/claudedrone/docs/project-map.md`
- `/home/nn/workspace/3588/examples/Altair-Silent/docs/project-map.md`
- `/home/nn/workspace/3588/examples/PX4-ROS2-SLAM-Control/docs/project-map.md`
- `/home/nn/workspace/3588/examples/Autonomous-Indoor-Drone-Navigation-ROS2/docs/project-map.md`

## 2. 总结论

四个项目没有任何一个可以直接照搬成 NavLab 当前方案，但它们各自提供了清晰的改进线索：

- `claudedrone` 值得借鉴的是 ArduPilot/MAVROS 起飞状态机、传感器健康监控、下视 rangefinder/optical-flow 的无 GPS 机制思路。
- `Altair-Silent` 值得借鉴的是系统分层、FCU ready 后再激活 controller、唯一 setpoint owner、Nav2 action 驱动任务。
- `PX4-ROS2-SLAM-Control` 值得借鉴的是 PX4 NED/FRD 到 ROS ENU/FLU 的独立 odom converter、SLAM backend 输入组织、持续 Offboard heartbeat。
- `Autonomous-Indoor-Drone-Navigation-ROS2` 值得借鉴的是 Gazebo ray sensor、`rf2o_laser_odometry -> /odom -> slam_toolbox` 的诊断链路。

它们共同指向一个原则：NavLab 不能再把“让 Foxglove 看起来会动”当成目标。当前阶段应该只验收真实机制：

```text
Gazebo 物理模型
  -> SITL/FCU 控制运动
  -> Gazebo sensor / X2 driver / rangefinder 产生传感器
  -> SLAM backend 输出 /odom
  -> ExternalNav 进入 FCU
  -> FCU local position 反映真实飞控状态
  -> rosbag/Foxglove 只观察，不参与控制
```

## 3. 四个项目对比

| 项目 | 最有价值的部分 | 不能照搬的部分 | 对 NavLab 的结论 |
|---|---|---|---|
| `claudedrone` | MAVROS 起飞 FSM、传感器健康监控、下视 rangefinder/optical-flow 思路、主动扫描状态机 | Cartographer/Nav2 没有完整代码闭环；MAVROS 不等于官方 ArduPilot ROS2 DDS；stop-scan 不是连续 SLAM | 可借鉴 FCU 状态确认和传感器职责，不作为 SLAM 主模板 |
| `Altair-Silent` | `VehicleController` 集中输出 setpoint；`StateWatcher` 按 FCU 状态激活 controller；Nav2 action 做任务层；Cartographer package 化 | Cartographer odom 配置有冲突；MAVROS 默认真机串口；穿窗 controller 不完整 | 最适合借鉴系统分层和控制权管理 |
| `PX4-ROS2-SLAM-Control` | PX4 odom converter；`/scan + /odom + TF` 给 SLAM Toolbox；RGB-D + RTAB-Map；Offboard setpoint heartbeat | PX4 topic 不能直接套给 ArduPilot；没看到 SLAM pose 回灌 EKF；路径 hardcode 多 | 最适合借鉴 frame 转换和 SLAM backend 接口 |
| `Autonomous-Indoor-Drone-Navigation-ROS2` | Gazebo ray lidar；`rf2o_laser_odometry`；`slam_toolbox` localization；已有地图模式 | 自写 PID 直接控制 Gazebo 电机；读 Gazebo truth；静态 `map -> scan` 可疑 | 只可作为传感器/激光里程计诊断参考，不能作为飞控闭环模板 |

## 4. 共同教训

### 4.1 飞控必须是运动控制边界

所有可借鉴项目里，真正接近真实飞行的路径都有一个共同点：上层只发 mode、arm、takeoff、setpoint，运动执行由飞控完成。

NavLab 必须坚持：

- 不直接 `set_pose`。
- 不由 companion 或 mission 直接移动 Gazebo。
- 不由 Python 直接控制 Gazebo motor joint。
- hover、forward、avoid 都必须通过 FCU 可接受的 setpoint 或官方接口完成。

`Autonomous-Indoor-Drone-Navigation-ROS2` 的自写 PID 对理解四旋翼动力学有帮助，但它本质上绕开了真实飞控，不能进入 NavLab 当前阶段。

### 4.2 传感器服务应该独立拥有传感器机制

`claudedrone` 和 `Autonomous-Indoor-Drone-Navigation-ROS2` 都说明一件事：传感器不应该只是随便发布一个同类型 ROS message。NavLab 的 X2 和下视 rangefinder 应继续由 `gazebo-sensor` 负责：

- Gazebo ray sensor 提供真实几何交互。
- X2 virtual serial 和厂商 driver 产生 `/scan`。
- 下视 range sensor 产生 `/rangefinder/down/range`。
- rangefinder 通过 MAVLink `DISTANCE_SENSOR` 或官方 DDS 外设路径进入 FCU。

companion 不应该控制高度，只能观察 FCU 状态和发送任务 setpoint。

### 4.3 SLAM backend 必须是可替换接口，不是单个脚本

四个项目分别使用 Cartographer、SLAM Toolbox、RTAB-Map、rf2o。它们证明 SLAM 算法会变化，但接口契约可以稳定。

NavLab 应固定下面这组契约：

```text
输入：
  /scan
  /imu/data
  /tf
  /tf_static
  可选 /odometry 或 /fcu/odom 诊断输入

输出：
  /odom
  /tf
  /navlab/slam/status
  可选 /map, /submap_list, /trajectory_node_list
```

Cartographer 只是当前 backend。后续可以增加：

- `slam_toolbox_mapping`
- `slam_toolbox_localization`
- `rf2o_diagnostic`
- `rtabmap_rgbd`
- 真机专用 Cartographer config

但所有 backend 都必须让 acceptance 能判断 `/odom` 质量，而不是只判断 topic 存在。

### 4.4 Frame 转换要成为一等公民

`PX4-ROS2-SLAM-Control` 最大价值是把 NED/FRD 到 ENU/FLU 的转换单独写出来。NavLab 的 ArduPilot MAVLink 也有同样问题：

- MAVLink/ArduPilot 常见 NED。
- ROS/Foxglove/SLAM 常见 ENU。
- 机体系可能是 FRD/FLU 差异。
- scan 角度方向、yaw 正方向、`laser_frame` 安装姿态都会影响结果。

因此 NavLab 应增加 frame contract 和验收：

- 单元测试 NED -> ENU、FRD -> FLU、yaw 转换。
- acceptance 检查 `navlab_world/map/odom/base_link/imu_link/laser_frame` 连通。
- rosbag summary 记录 TF 缺失、重复 parent、frame 跳变。
- `/scan` 正前方、左、右方向必须用固定场景验收。

如果 Foxglove 里墙体跟着无人机动、scan 和前进方向相反、无人机贴墙横移很诡异，优先查 frame，不要先调 SLAM 参数。

### 4.5 只能有一个 setpoint owner

`Altair-Silent` 的 `VehicleController` 思路很重要：系统可以有多个意图来源，但最终只能有一个节点向 FCU 发运动 setpoint。

NavLab 当前应该收敛为：

```text
mission / planner / diagnostics
  -> 控制意图
  -> navlab vehicle controller
  -> FCU setpoint sender
```

不要让 mission controller、hover controller、avoid controller、SLAM bridge 同时向飞控发运动命令。否则 rosbag 里很难判断到底是谁让飞机撞墙或漂移。

### 4.6 Acceptance 必须证明机制，而不是证明演示

四个项目多数缺少严格 acceptance，这正是 NavLab 应该补强的地方。

NavLab 的 summary 不应只写 `ok=true`，还要证明：

- `set_pose_count == 0`
- FCU 进入目标 mode
- arm 成功
- takeoff 成功
- `LOCAL_POSITION_NED` 连续输出
- `/scan` 和 `/imu/data` healthy
- SLAM `/odom` 连续且低跳变
- `/external_nav/odom` 来源是 SLAM，不是 Gazebo truth
- MAVLink/DDS ExternalNav 被 FCU 接收
- hover drift 在阈值内
- rosbag required topics 全部存在

## 5. NavLab 应该从哪里改进

### P0：先锁死真实闭环边界

目标：消灭“看起来能飞但实际是脚本移动”的路径。

要做：

- acceptance 统计并拒绝任何 Gazebo direct pose/motor control。
- summary 明确记录无人机运动来源：`fcu_controlled`、`gazebo_truth_only`、`synthetic`。
- companion 不允许消费 Gazebo truth 作为控制输入。
- `/gazebo/truth/odom` 只允许用于误差诊断和轨迹导出。

验收：

- `set_pose_count == 0`
- Gazebo truth 只出现在 diagnostics，不出现在 ExternalNav input。
- rosbag 能证明 FCU local position 与 Gazebo motion 同步。

### P1：补强 FCU 状态机和唯一 setpoint owner

目标：参考 `claudedrone` 和 `Altair-Silent`，把飞控状态确认和控制权管理做实。

要做：

- 建立 `FcuStateWatcher`：
  - heartbeat
  - mode
  - armed
  - takeoff ack
  - EKF status
  - local position count/rate
- 建立单一 `VehicleController` 或等价组件：
  - hover
  - yaw
  - local position target
  - later velocity target
- mission 只发任务状态和控制意图，不直接拥有 FCU 输出通道。

验收：

- 未 GUIDED/armed/takeoff 前，controller 不发运动 setpoint。
- 所有运动 setpoint 只来自一个 owner。
- summary 记录 setpoint owner、setpoint rate、last target。

### P2：把传感器链路做成可验收机制

目标：传感器仿真贴近真实机制，而不是只满足消息类型。

要做：

- 保持 X2 链路：

```text
Gazebo /scan_ideal
  -> X2 virtual serial
  -> ydlidar_ros2_driver
  -> /scan
```

- 保持下视测距链路：

```text
Gazebo down range sensor
  -> /rangefinder/down/range
  -> DISTANCE_SENSOR 或官方外设接口
  -> FCU
```

- 增加 scan 方向验收：
  - 正前墙
  - 左墙
  - 右墙
  - 背后空区
- 增加 rangefinder 对照：
  - Gazebo truth altitude
  - `/rangefinder/down/range`
  - FCU altitude/local position

验收：

- `/scan` 不使用 synthetic fallback。
- `/rangefinder/down/status` 证明 FCU 已接收测距。
- `/scan` frame 为 `laser_frame`，方向与机头一致。

### P3：SLAM backend 从“能发 odom”升级为“质量可诊断”

目标：参考四个项目的 SLAM 结构，但保持 NavLab backend registry。

要做：

- Cartographer backend 继续作为默认 backend。
- 增加 `rf2o_diagnostic` backend 或诊断链路，用来区分：
  - Cartographer scan matching 问题
  - 纯 laser odom 问题
  - frame/scan 方向问题
- 为每个 backend 声明：
  - required input topics
  - output odom topic
  - TF contract
  - health metrics
- adapter 只能导出 status 和 `/odom`，不能伪造定位。

验收：

- `/odom` rate、跳变、drift、与 Gazebo truth 的诊断误差进入 summary。
- hover-slam diagnostic 能区分“FCU 高度控制问题”和“SLAM 水平漂移问题”。
- backend 名称、配置文件、镜像 tag 进入 artifact。

### P4：建立 frame contract 和自动检查

目标：把 scan 反向、墙体跟随、无人机 yaw 异常这类问题前置发现。

要做：

- 新增 frame contract 文档或配置：
  - `navlab_world`
  - `map`
  - `odom`
  - `base_link`
  - `imu_link`
  - `laser_frame`
  - `rangefinder_down_frame`
- 增加 TF acceptance：
  - 连通性
  - parent 唯一性
  - 是否存在循环
  - 静态/动态 TF 角色是否正确
- 增加坐标转换单元测试：
  - MAVLink NED -> ROS ENU
  - body FRD -> FLU
  - yaw 正方向
  - covariance/frame_id 填写

验收：

- Foxglove 固定参考系用 `navlab_world` 或 `map` 时，墙体不跟随无人机。
- `/scan` 可正确叠在墙上。
- `/odom`、`/external_nav/odom`、FCU local position 不出现轴交换或符号反向。

### P5：从 hover 之后再接 Nav2/探索

目标：不要在 SLAM hover 未稳定前引入完整探索。

要做：

- 先只验收 hover：
  - FCU 定高
  - SLAM odom 稳定
  - ExternalNav healthy
- 再做小范围平移：
  - forward/back
  - yaw scan
  - stop drift
- 再接 Nav2：
  - mission 发 NavigateToPose action
  - local planner 输出速度/姿态意图
  - VehicleController 转成 FCU setpoint
- 最后做 8 字形世界探索：
  - 右环一圈
  - 中腰切换
  - 左环一圈
  - 必要时 scan_left/scan_right

验收：

- hover gate 先通过。
- slam-hover gate 再通过。
- local setpoint gate 再通过。
- navigation/exploration gate 最后通过。

## 6. 推荐改进路线

当前最合理路线不是马上做完整绕障，而是按下面顺序收敛：

1. **机制锁死**：确认无人机只能由 SITL/FCU/Gazebo plugin 驱动。
2. **FCU hover**：无 SLAM 水平控制，只证明 GUIDED、arm、takeoff、rangefinder 定高、local position。
3. **传感器验收**：X2 `/scan`、down rangefinder、IMU、TF 全部可诊断。
4. **SLAM hover**：Cartographer `/odom` 进入 ExternalNav，悬停不漂。
5. **Frame/坐标测试**：把 NED/ENU、FRD/FLU、scan 方向做成自动测试。
6. **唯一控制器**：建立 VehicleController，所有任务只输出意图。
7. **Nav2/探索**：在 hover 和 local setpoint 稳定后，再做 8 字形区域探索。

## 7. 当前不应该做的事

- 不应该把 `Autonomous-Indoor-Drone-Navigation-ROS2` 的自写 PID 移植进 NavLab 控制 Gazebo。
- 不应该用 Gazebo truth 作为 ExternalNav 正式输入。
- 不应该为了 Foxglove 好看让 marker 或模型跟随错误 frame。
- 不应该在 Cartographer 未稳定时直接上完整 Nav2 探索。
- 不应该同时保留多个节点向 FCU 发 setpoint。
- 不应该把 PX4 `/fmu/*` topic 名称直接混进 ArduPilot 主链路。

## 8. 最终判断

四个参考项目给出的最佳组合不是某个单一仓库，而是下面这套架构：

```text
claudedrone:
  FCU 状态确认 + 传感器健康

Altair-Silent:
  StateWatcher + VehicleController + Nav2 task layer

PX4-ROS2-SLAM-Control:
  frame converter + SLAM backend input contract + heartbeat setpoint

Autonomous-Indoor-Drone-Navigation-ROS2:
  Gazebo ray sensor + rf2o/slam_toolbox 诊断链

NavLab:
  ArduPilot SITL/Gazebo plugin + X2 driver chain + Cartographer backend
  + ExternalNav acceptance + rosbag/Foxglove artifact
```

因此 NavLab 的改进重点应该是工程边界和验收，而不是先换算法。只要 FCU 控制边界、传感器机制、frame contract、SLAM backend、唯一 setpoint owner 和 acceptance summary 都打牢，后续换 Cartographer/SLAM Toolbox/Nav2/探索策略才有意义。
