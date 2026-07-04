# P1 官方 maze + NavLab X2 雷达接入设计

## 1. 目标

P1 的目标是在 P0 已通过的官方 ArduPilot ROS2/Gazebo/Cartographer baseline 上，只替换雷达机制，不替换 world 和无人机模型。

P1 继续使用：

- 官方 `ardupilot_gz_bringup iris_maze.launch.py`
- 官方 maze world
- 官方 Iris / lidar 模型
- 官方 `ardupilot_cartographer` Cartographer baseline

P1 只引入 NavLab X2 链路：

```text
Gazebo lidar/ray source
  -> X2 virtual serial emulator
  -> ydlidar_ros2_driver
  -> /scan
  -> ardupilot_cartographer
```

这样做的原因是减少变量。P0 已经证明官方 DDS baseline 可观测；如果 P1 同时替换 world、模型和雷达，后续 `/scan`、TF、SLAM、飞控异常会很难归因。

## 2. 非目标

P1 不做：

- NavLab 8 字形 world。
- NavLab 自定义机体模型。
- 下视 rangefinder 定高最终验收。
- hover gate。
- exploration / avoid。
- direct Gazebo set pose。

NavLab world/model 后移到后续独立 migration phase，等官方 maze + X2 + SLAM + hover + motion + exploration 和 replay artifact 基础机制稳定后再作为可选迁移。

## 3. 目标架构

P1 目标链路：

```text
orchestration
  -> official baseline runtime image
  -> ardupilot_gz_bringup iris_maze.launch.py
  -> official Iris lidar sensor publishes Gazebo/ROS scan source
  -> NavLab gazebo-sensor X2 runtime consumes scan source
  -> X2 virtual serial packets
  -> ydlidar_ros2_driver
  -> /scan
  -> ardupilot_cartographer cartographer.launch.py
  -> Cartographer map / TF / occupancy grid
  -> rosbag MCAP + summary
```

P1 不要求 ExternalNav 回灌飞控已经完成。它只证明 `/scan` 的来源从普通 Gazebo LaserScan 收敛到 NavLab X2 厂商链路，并且 Cartographer 能消费这个 `/scan`。

## 4. 高度和 2D 雷达边界

2D 雷达只解决水平平面上的 scan matching。它不能负责定高，也不能单独证明无人机已经稳定 hover。

官方 Cartographer 示例的高度口径是：

```text
EK3_SRC1_POSXY = ExternalNav
EK3_SRC1_POSZ  = Baro
```

也就是说，官方示例默认把高度稳定交给 ArduPilot 的高度估计和高度控制，而不是交给 2D Cartographer。NavLab 后续会在 P2 接入下视 rangefinder，让仿真机制更接近真实无人机。

P1 因此只做 scan 链路和 Cartographer 输入验收：

- 可以验证 `/scan` 在官方 maze/Iris baseline 中可用。
- 可以验证 Cartographer 能消费 vendor driver 输出的 `/scan`。
- 不要求起飞、定高、hover drift 或 ExternalNav 回灌通过。
- 如果 P1 运行中需要让机体起飞，只能通过 ArduPilot 官方控制接口或 MAVProxy 触发，且高度稳定仍只能作为诊断，不作为 P1 完成标准。

## 5. Topic 合同

P1 required topics：

```text
/clock
/tf
/tf_static
/ap/v1/time
/scan
/sim/x2/status
```

P1 optional topics：

```text
/scan_ideal
/map
/submap_list
/trajectory_node_list
/navlab/slam/status
/ap/v1/imu/experimental/data
/ap/v1/pose/filtered
```

`/scan_ideal` 是 Gazebo 或桥接后的理想 ray scan，只能作为 X2 emulator 的输入和诊断对照。Cartographer 的主输入应是 vendor driver 输出的 `/scan`。

## 6. Summary 字段

P1 summary 至少包含：

```json
{
  "ok": false,
  "blocked": true,
  "blockers": [],
  "official_baseline": {
    "official_dds_time_received": false,
    "official_dds_prearm_service_available": false,
    "gazebo_bringup_mode": "official_gz_bringup"
  },
  "p1_maze_x2": {
    "world_source": "official_iris_maze",
    "vehicle_model_source": "official_iris_lidar",
    "lidar_route": "navlab_x2_vendor_driver",
    "altitude_control_claim": "not_evaluated",
    "hover_claim": "not_evaluated",
    "direct_set_pose": false,
    "scan_source_topic": "/scan_ideal",
    "scan_topic": "/scan",
    "x2_status_topic": "/sim/x2/status",
    "scan_count": 0,
    "x2_status_ok": false,
    "vendor_driver_running": false
  },
  "cartographer": {
    "launch_source": "ardupilot_cartographer",
    "configuration_hash": "",
    "uses_official_lua": true,
    "scan_input_topic": "/scan",
    "map_output_seen": false
  },
  "rosbag_profile": {
    "ok": false,
    "required_topics": [],
    "missing_required_topics": [],
    "zero_count_required_topics": []
  }
}
```

其中 `altitude_control_claim` 和 `hover_claim` 必须保持 `not_evaluated`。P1 不能把“scan 和 Cartographer 可用”写成“定高/悬停完成”。

## 7. 验收语义

P1 通过必须满足：

- official baseline doctor 仍通过。
- official bringup 仍是 `iris_maze.launch.py`。
- world/model 仍是官方 maze/Iris，不引入 NavLab 8 字形 world。
- `/scan` 来自 X2 virtual serial + `ydlidar_ros2_driver`，不是 synthetic fallback。
- `/sim/x2/status` 表明 emulator 和 driver 链路 healthy。
- `/scan` message count 大于 0。
- `/scan` frame、角度方向和官方 Cartographer frame 配置不冲突。
- summary 明确 `altitude_control_claim=not_evaluated`。
- summary 明确 `hover_claim=not_evaluated`。
- rosbag 能记录 required topics。

P1 不通过但有价值的情况：

- `/scan_ideal` 有数据但 `/scan` 没有：说明 X2 virtual serial 或 vendor driver 失败。
- `/scan` 有数据但 Cartographer 无输出：说明 TF、frame、scan 参数或 Cartographer 输入不匹配。
- `/scan` 方向反了：说明 X2 protocol remap 或 driver `reversion/inverted` 配置不正确。
- official DDS 重新失败：说明 P1 改动破坏了 P0 baseline。

## 8. 执行顺序

P1 推荐执行顺序：

```text
1. 复用 P0 official baseline doctor，确认官方 runtime 仍可用。
2. 启动 official iris_maze bringup。
3. 发现官方 lidar/Gazebo scan source，并记录 topic/type/frame。
4. 启动 X2 emulator，从官方 scan source 生成虚拟串口包。
5. 启动 ydlidar_ros2_driver，从虚拟串口输出 /scan。
6. 启动 ardupilot_cartographer，让 Cartographer 消费 /scan。
7. 录制 P1 rosbag profile。
8. 生成 summary.json 和 Foxglove notes。
```

## 9. 与后续 Phase 的关系

P1 完成后：

- P2 接 down rangefinder 和 IMU 机制。
- P3 验证 Cartographer `/odom` 质量。
- P6 做真实 SLAM hover gate。
- P7/P8 继续在官方 maze 中做小范围运动和探索。
- 后续 migration phase 再可选替换 NavLab 8 字形 world 和自定义机体。

如果 P1 没完成，不能进入 motion、exploration 或 NavLab world/model 迁移，因为雷达链路还没有被证明能在官方 baseline 中稳定工作。
