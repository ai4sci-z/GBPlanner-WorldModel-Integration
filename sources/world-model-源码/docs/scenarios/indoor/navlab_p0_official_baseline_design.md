# P0 官方基线验收设计

## 1. 目标

P0 的目标是建立 NavLab 的真实闭环基准：先证明 ArduPilot 官方 ROS2 / Gazebo / Cartographer 路线能够被 NavLab 编排、观测、记录和验收。

P0 不要求完成 NavLab 自定义 world、X2 协议仿真、8 字形探索或最终 hover gate。它只回答：

> 当前系统是否已经具备官方 ArduPilot ROS2/Gazebo/Cartographer 基线能力，后续 NavLab 自定义模块是否可以可靠地接在这个基线上。

## 2. 为什么 P0 必须先做

当前 NavLab 已经有自定义链路：

```text
Cartographer /odom
  -> navlab_external_nav_bridge
  -> /external_nav/odom
  -> MAVLink ODOMETRY sender
  -> SITL
```

这条链路对诊断有价值，但它不是官方首选基线。真正要降低后续风险，必须先对齐官方路线：

```text
ardupilot_gz / ardupilot_ros
  -> ArduPilot SITL
  -> Micro-XRCE-DDS / ROS2
  -> /ap/v1/* DDS endpoints
  -> official Cartographer bringup
  -> ExternalNav / EKF
```

如果 P0 不做，后续即便 Foxglove 里能看到无人机、scan、odom，也无法判断：

- 是官方机制真的通了；
- 还是 NavLab 自定义 bridge 在绕过官方接口；
- 还是 Gazebo truth 或 fake odom 伪装成 SLAM feedback。

## 3. P0 范围

### 3.1 包含

P0 包含：

- 官方 ArduPilot ROS2/DDS 接口存在性检查。
- 官方 Gazebo/SITL bringup 结构调研和最小运行入口。
- 官方 Cartographer baseline 启动口径。
- EKF ExternalNav 参数与官方 baseline 对齐检查。
- NavLab orchestration 对官方 baseline 的 doctor/acceptance 支持。
- rosbag/Foxglove 对官方 baseline topic 的记录口径。
- summary 中明确区分 official baseline、自定义 bridge、diagnostic fallback。

### 3.2 不包含

P0 不包含：

- NavLab 8 字形 world。
- NavLab IQ quad 模型适配。
- X2 virtual serial + ydlidar driver 完整链路。
- 下视 rangefinder 定高最终验收。
- 真实 hover gate。
- forward/avoid/exploration。
- Nav2。

这些都属于 P1 之后。

## 4. 官方基线目标架构

P0 的目标架构是：

```text
orchestration
  -> official baseline task
  -> Gazebo + ArduPilot SITL + ROS2/DDS
  -> /ap/v1/time sample received
  -> /ap/v1/prearm_check service visible
  -> /ap/v1/* topics recordable
  -> Cartographer baseline launch visible/runnable
  -> artifact summary + rosbag profile
```

在 P0 中，NavLab 可以保留自定义 Docker 编排和 artifact 收集，但必须明确记录当前使用的是：

- `official_dds`：官方 DDS `/ap/*` 通道；
- `mavlink_fallback`：自定义 MAVLink fallback；
- `diagnostic_only`：只做诊断，不作为完成标准。

## 5. 服务职责

### 5.1 Orchestration

负责：

- 提供 P0 doctor / acceptance task。
- 启动或检查官方 baseline 所需服务。
- 收集 summary、rosbag profile、日志。
- 输出 artifact。

不负责：

- 发布 ROS topic。
- 修改 Cartographer 输出。
- 伪造 `/ap/*`。

### 5.2 ArduPilot SITL

负责：

- 以官方 DDS enabled 方式启动。
- 暴露 `/ap/v1/*` DDS endpoints。
- 输出官方状态 topic。

P0 中必须记录：

- `DDS_ENABLE`
- `DDS_DOMAIN_ID`
- `ROS_DOMAIN_ID`
- SITL model
- SITL profile/params
- 是否能收到 `/ap/v1/time`
- 是否能发现 `/ap/v1/prearm_check`
- ROS graph 中是否能看到 `/ap` 节点或 `_CREATED_BY_BARE_DDS_APP_` endpoint

官方 SITL DDS 启动入口应以 `ardupilot_sitl` package 为准：

```bash
ros2 launch ardupilot_sitl sitl_dds_udp.launch.py
```

这个 launch 的职责不是只启动 `arducopter`，还包括：

- `micro_ros_agent.launch.py`
- `sitl.launch.py`
- `mavproxy.launch.py`

因此 P0 doctor 必须同时检查 `ardupilot_sitl`、`ardupilot_msgs`、
`micro_ros_agent`、`ardupilot_dds_tests` 和 Micro-XRCE-DDS agent 可执行文件。

### 5.3 Gazebo

P0 使用官方最小 Gazebo bringup 或与官方结构等价的入口。

P0 不要求接入 NavLab 8 字形 world，但要记录：

- Gazebo 是否启动；
- ArduPilot Gazebo plugin 是否参与；
- 是否有 Gazebo truth 诊断 topic；
- 是否有任何 direct set pose 行为。

官方 Gazebo bringup 入口应以 `ardupilot_gz_bringup` package 为准。当前 P0
baseline 使用下面的官方示例作为对齐目标：

```bash
ros2 launch ardupilot_gz_bringup iris_maze.launch.py
```

`iris_maze.launch.py` include `robots/iris_lidar.launch.py`，后者在
`use_dds_agent=true` 时通过 `robots/robot.launch.py` include
`ardupilot_sitl/launch/sitl_dds_udp.launch.py`。P0 可以保留 NavLab 自定义
world 作为后续替换对象，但 `gazebo_bringup_mode` 不能在仍是
`navlab_custom_bringup` 时判为 official baseline 通过。

当前 P0 dedicated runtime 实际使用：

```bash
ros2 launch ardupilot_gz_bringup iris_maze.launch.py \
  use_gz_sim_gui:=false \
  rviz:=false \
  use_dds_agent:=true \
  use_gz_sim_server:=true \
  spawn_robot:=true
```

运行时必须 source 官方 baseline workspace，并把 `ROS_DOMAIN_ID` 与 ArduPilot
`DDS_DOMAIN_ID` 对齐。当前通过的配置为：

```text
ROS_DOMAIN_ID=0
DDS_DOMAIN_ID=0
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

### 5.4 Cartographer

P0 只要求官方 Cartographer baseline 可用或可被 doctor 证明依赖存在。

必须记录：

- `cartographer_ros` 是否安装。
- `cartographer_node` 是否存在。
- `cartographer_occupancy_grid_node` 是否存在。
- 使用的 Lua 配置路径或官方配置来源。
- 是否使用 `/scan`、`/imu`、`/odometry`。

官方 Cartographer 入口应以 `ardupilot_cartographer` package 为准：

```bash
ros2 launch ardupilot_cartographer cartographer.launch.py
```

官方 launch 会启动 `cartographer_ros cartographer_node` 和
`cartographer_ros cartographer_occupancy_grid_node`，并执行 `/odom -> /odometry`
remap。NavLab 当前 `navlab_cartographer_2d.lua` 已按官方 frame / odometry 口径
收敛，但 P0 doctor 仍必须区分：

- `cartographer_ros` 依赖存在；
- 官方 `ardupilot_cartographer` package 存在；
- NavLab 自定义 adapter 是否仍在改变完成标准。

### 5.5 MAVLink

P0 不禁止 MAVLink，但 MAVLink 只能作为：

- GCS/调试/日志通道；
- fallback；
- 对照诊断。

P0 不能把自定义 MAVLink ODOMETRY sender 作为官方基线完成标准。

## 6. Topic 和接口要求

P0 至少检查：

```text
/ap/v1/time
/ap/v1/prearm_check
/tf
/tf_static
/clock
```

具体 `/ap/*` topic 以后按官方运行结果固化到配置，不在设计文档里硬编码完整列表。P0 acceptance 应记录实际发现的 `/ap/*` topic，并判断关键 topic 是否存在。

注意：ArduPilot DDS endpoint 可能表现为裸 DDS writer。ROS graph 中未必稳定出现一个名为 `/ap` 的 ROS node，节点信息也可能显示 `_CREATED_BY_BARE_DDS_APP_`。因此 P0 的硬验收不应该是 `ros2 node list` 里必须有 `/ap`，而应该是：

- `/ap/v1/time` 能收到 sample；
- `/ap/v1/prearm_check` service 可发现；
- required `/ap/v1/*` topic 能被 rosbag 记录。

Jazzy 环境下当前 P0 使用 `rmw_cyclonedds_cpp`。本地调试发现 `rmw_fastrtps_cpp` 能发现部分 ArduPilot bare DDS endpoint，但 `/ap/v1/time` echo 长时间收不到 sample；Cyclone DDS 能收到 sample 并写入 MCAP。Cyclone 运行时可能打印 type hash 相关 warning，但不影响 P0 的 sample 接收和 rosbag 记录。

建议 summary 字段：

```json
{
  "official_baseline": {
    "ok": false,
    "dds_enabled": null,
    "dds_domain_id": null,
    "official_ros_domain_id": null,
    "navlab_ros_domain_id": null,
    "rmw_implementation": null,
    "ap_node_present": false,
    "official_dds_time_received": false,
    "official_dds_prearm_service_available": false,
    "ap_topics": [],
    "probe_confirmed_ap_topics": [],
    "cartographer_ros_present": false,
    "gazebo_bringup_mode": "unknown",
    "external_nav_route": "unknown",
    "rosbag_profile": {
      "ok": false,
      "required_topics": [],
      "missing_required_topics": [],
      "zero_count_required_topics": []
    }
  }
}
```

## 7. Acceptance 语义

P0 通过不等于 NavLab hover 完成。P0 只表示官方 baseline 条件成立。

P0 通过条件：

- `/ap/v1/time` sample 可收到。
- `/ap/v1/prearm_check` service 可发现。
- 关键 `/ap/v1/*` topic 可见且 required topics 可被 rosbag 记录。
- DDS domain 与 ROS domain 记录清楚。
- 官方或官方等价 Gazebo/SITL bringup 可启动或 doctor 可证明依赖齐全。
- Cartographer 官方 baseline 依赖可用。
- summary 明确标注 ExternalNav route。
- rosbag profile 包含官方 baseline topic 检查结果。

P0 失败但有价值的情况：

- `/ap/v1/time` sample 收不到：说明还没有进入可用的官方 DDS 主通道，或者 RMW/domain 不匹配。
- `/ap/v1/prearm_check` service 不可见：说明官方 SITL/DDS 服务面没有完整暴露。
- Cartographer 依赖不存在：说明 SLAM backend 仍只是壳或 fallback。
- ExternalNav route 是 `mavlink_fallback`：说明可诊断，但不能作为官方完成标准。
- Gazebo direct set pose 出现：说明运动控制边界不干净。

## 8. 与后续 Phase 的关系

P0 完成后：

- P1 先保留官方 `iris_maze` world 和官方 Iris 模型，只把 X2 雷达链路接入官方结构。
- P2 再接下视 rangefinder 和 IMU 机制验收。
- P3 才能把 Cartographer backend 质量验收和官方 baseline 对齐。
- P6 才能把真实 SLAM hover 作为完成标准。

如果 P0 没完成，后续 phase 可以继续做诊断，但不能宣称“真实闭环完成”。

## 9. 风险

主要风险：

- 官方 DDS `/ap/*` 接口和当前 Docker/SITL 启动方式不兼容。
- 当前 mavlink-router 主链路和官方 DDS bringup 同时存在，容易混淆完成标准。
- Cartographer 可以启动但没有真实消费 `/scan + /imu + /odometry`。
- P0 acceptance 只检查 topic 存在，误判为机制完成。

对应策略：

- summary 必须记录 route，而不是只记录 topic。
- official baseline 和 NavLab custom route 分开验收。
- P0 不做 hover 通过判断，只做官方机制存在性和最小连通性判断。
