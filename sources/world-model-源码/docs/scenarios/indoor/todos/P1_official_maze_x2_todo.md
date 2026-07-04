# P1 官方 maze + NavLab X2 雷达 TODO

## 目标

在 P0 官方 baseline 已通过的基础上，继续使用官方 `iris_maze` world 和官方 Iris 模型，只把雷达链路替换为 NavLab X2 virtual serial + vendor driver 输出 `/scan`。

设计文档：

- `docs/scenarios/indoor/navlab_p1_official_maze_x2_design.md`

前置条件：

- `docs/scenarios/indoor/todos/P0_official_baseline_todo.md` 已通过。

## P1.0 边界固化

任务：

- [x] 确认 P1 launch 仍使用 `ardupilot_gz_bringup iris_maze.launch.py`。
- [x] 确认 P1 不加载 NavLab 8 字形 world。
- [x] 确认 P1 不加载 NavLab 自定义机体模型。
- [x] summary 记录 `world_source=official_iris_maze`。
- [x] summary 记录 `vehicle_model_source=official_iris_with_lidar`。
- [x] summary 记录 `lidar_route=navlab_x2_vendor_driver`。
- [x] summary 记录 `altitude_control_claim=not_evaluated`。
- [x] summary 记录 `hover_claim=not_evaluated`。

验收：

- [x] P1 summary 中没有 `navlab_iq_quad_figure8.sdf`。
- [x] P1 summary 中没有 direct set pose。
- [x] P1 summary 不声明定高完成。
- [x] P1 summary 不声明 hover 完成。

## P1.1 X2 输入源接入

任务：

- [x] 找到官方 Iris lidar 在 P0 bringup 中的 Gazebo/ROS scan source。
- [x] 明确 X2 emulator 输入 topic：官方 Gazebo `/lidar` 经 P1 bridge 输入到 ROS `/lidar`。
- [x] 确认输入 scan 的 frame、角度方向、range min/max。
- [x] X2 emulator 使用官方 scan source 生成虚拟串口原始包。
- [x] `/sim/x2/status` 记录 emulator link、scan rate、packet count。

验收：

- [x] `/scan_ideal` 或等价输入 topic message count 大于 0。
- [x] `/sim/x2/status` 显示 emulator healthy。
- [x] artifact 记录 X2 profile 路径和 hash。

## P1.2 Vendor driver 输出 `/scan`

任务：

- [x] 在 P1 runtime 中启动 `ydlidar_ros2_driver`。
- [x] driver 读取 X2 virtual serial，而不是真实串口。
- [x] driver 输出 `/scan`。
- [x] driver 参数来自 X2 profile，不使用临时 CLI 硬编码。
- [x] summary 记录 driver process/topic publisher 状态。

验收：

- [x] `/scan` message count 大于 0。
- [x] `/scan.header.frame_id` 为 `base_scan` 或 P1 配置指定 frame。
- [x] `/scan` angle convention 与 P0/P1 文档一致：0 度为机头前方。
- [x] `/scan` 不是 synthetic fallback。

## P1.3 Cartographer 消费 X2 `/scan`

任务：

- [x] 启动 `ardupilot_cartographer cartographer.launch.py` 或官方等价 Cartographer launch。
- [x] Cartographer 的 scan 输入绑定 vendor driver `/scan`。
- [x] Cartographer Lua 保持与官方 `cartographer.lua` 一致。
- [x] 保留 `/odom -> /odometry` remap。
- [x] artifact 记录 Cartographer config hash。

验收：

- [x] Cartographer process 正常运行。
- [x] `/map` 或 occupancy grid 相关 topic 有输出。
- [x] `/tf` 中 `map/odom/base_link/base_scan` 链路有录制证据。
- [x] 没有把 `/scan_ideal` 或 `/lidar` 直接作为 Cartographer 主输入。

## P1.4 高度边界和 2D 雷达前提

任务：

- [x] 文档和 summary 明确 P1 不验收定高。
- [x] 文档和 summary 明确 P1 不验收 hover drift。
- [x] 如果 P1 run 中触发起飞，只能通过 ArduPilot 官方控制接口或 MAVProxy，不允许 direct set pose。
- [x] 如果 P1 run 中触发起飞，记录高度来源为官方 baseline 诊断值，不作为 P1 completion。

验收：

- [x] `altitude_control_claim == "not_evaluated"`。
- [x] `hover_claim == "not_evaluated"`。
- [x] `set_pose_count == 0` 或等价 direct set pose 检查为 0。

## P1.5 Rosbag 和 Foxglove

任务：

- [x] 新增 P1 rosbag profile。
- [x] required topics 至少包含：
  - `/clock`
  - `/tf`
  - `/tf_static`
  - `/ap/v1/time`
  - `/scan`
  - `/sim/x2/status`
- [x] optional topics 包含：
  - `/lidar`
  - `/map`
  - `/submap_list`
  - `/trajectory_node_list`
  - `/scan_matched_points2`
- [x] Foxglove notes 说明固定参考系、scan 层和 raw status topic。

验收：

- [x] rosbag profile summary 中 required topics 全部存在且 message count 大于 0。
- [x] MCAP 包含 maze replay 所需 TF、scan 和 Cartographer topic。
- [x] `/lidar` 与 `/scan` 可对照，但 completion 使用 `/scan`。

## P1.6 Acceptance task

任务：

- [x] 新增 `navlab-official-maze-x2-acceptance` orchestration task。
- [x] orchestration CLI 增加同名 task；历史 justfile 便捷入口已回收。
- [x] acceptance 先跑 P0 official DDS probe，再跑 X2 scan gate。
- [x] summary 合并 P0 official section、X2 section、Cartographer section、rosbag section。
- [x] summary 包含 `p1_maze_x2` section。
- [x] summary 包含 `cartographer` section。
- [x] summary 包含 `altitude_control_claim` 和 `hover_claim`。

验收：

- [x] P0 official DDS 条件失败时，P1 直接 blocked。
- [x] X2 driver `/scan` 失败时，P1 blocked。
- [x] Cartographer 未消费 `/scan` 时，P1 blocked。
- [x] direct set pose 出现时，P1 blocked。
- [x] summary 把 P1 completion 和 hover completion 分开。

## P1.7 执行顺序

建议执行：

```text
1. uv run --project orchestration python orchestration/main.py official-baseline-doctor
2. 启动 official iris_maze bringup。
3. 发现官方 lidar/Gazebo scan source。
4. 启动 X2 emulator。
5. 启动 ydlidar_ros2_driver。
6. 启动 ardupilot_cartographer。
7. 录制 P1 rosbag profile。
8. 生成 summary.json。
```

验收：

- [x] 每一步失败都能在 summary.blockers 中定位到具体层级。
- [x] 失败不会退回 synthetic scan 或 fake odom 兜底。

## P1 完成标准

P1 全部完成必须满足：

- [x] 官方 `iris_maze` bringup 未被替换。
- [x] 官方 Iris 模型未被替换。
- [x] `/ap/v1/time` sample 可收到。
- [x] `/ap/v1/prearm_check` service 可发现。
- [x] X2 virtual serial emulator healthy。
- [x] `ydlidar_ros2_driver` 输出 `/scan`。
- [x] Cartographer 消费 vendor `/scan`。
- [x] rosbag required topics 全部有数据。
- [x] summary 明确标注 P1 不代表 hover 完成。
- [x] summary 明确标注 P1 不代表定高完成。

## 验证记录

后续每次验证按下面格式记录：

```text
- 命令：uv run --project orchestration python orchestration/main.py official-maze-x2-acceptance 45
- 时间：2026-06-06 09:56:22 Asia/Hong_Kong
- artifact：artifacts/ros/navlab_companion_sitl_gazebo/20260606_095622
- 结果：通过，summary.ok=true，blockers=[]
- blocker：无
- 备注：/scan publisher=ydlidar_ros2_driver_node，subscriber=cartographer_node；/scan frame_id=base_scan；
  /lidar=215、/scan=103、/sim/x2/status=29、/submap_list=49；altitude/hover claim 均为 not_evaluated。
```
