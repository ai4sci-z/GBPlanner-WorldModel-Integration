# P0 官方基线验收 TODO

## 目标

建立 NavLab 的官方 ArduPilot ROS2/Gazebo/Cartographer 基线验收。P0 完成后，只能说明官方 baseline 已经可观测、可记录、可作为后续对齐标准；不能说明 NavLab 真实 SLAM hover 已完成。

设计文档：

- `docs/scenarios/indoor/navlab_p0_official_baseline_design.md`

总 roadmap：

- `docs/scenarios/indoor/navlab_master_roadmap.md`

## P0.0 文档和边界

- [x] 新增 master roadmap，明确官方路线是完成标准，四个仓库是工程参考。
- [x] 新增 P0 设计文档。
- [x] 新增 P0 TODO 文档。
- [x] 在 `docs/README.md` 中加入 master roadmap、P0 design、P0 todo 的入口。
- [x] 删除旧 hover 主线文档，避免其继续承担总 roadmap 职责。

验收：

- [x] 文档中明确 P0 不是 hover gate。
- [x] 文档中明确 MAVLink ODOMETRY sender 只能作为 fallback/diagnostic，不能作为 P0 官方完成标准。
- [x] 文档中明确 `/ap/*` DDS 是 P0 主验收对象。

## P0.1 官方依赖和镜像检查

任务：

- [x] 确认 SLAM 镜像中存在 `cartographer_ros`。
- [x] 确认 SLAM 镜像中存在 `cartographer_node`。
- [x] 确认 SLAM 镜像中存在 `cartographer_occupancy_grid_node`。
- [x] 确认 ArduPilot ROS2/DDS 相关依赖来源。
- [x] 确认 Micro-XRCE-DDS / micro-ROS-Agent 启动方式。
- [x] 记录官方 package 来源、版本、镜像 tag。

建议命令：

```bash
docker run --rm <slam-image> bash -lc \
  'source /opt/ros/jazzy/setup.bash && ros2 pkg prefix cartographer_ros'

docker run --rm <slam-image> bash -lc \
  'source /opt/ros/jazzy/setup.bash && ros2 pkg executables cartographer_ros'
```

验收：

- [x] doctor summary 记录 `cartographer_ros_present=true`。
- [x] doctor summary 记录 cartographer executables。
- [x] artifact 中记录 SLAM image 和 Cartographer 来源。

## P0.2 官方 DDS `/ap/*` 接口检查

任务：

- [x] 找到或实现官方 DDS enabled SITL 启动入口。
- [x] 配置 `DDS_ENABLE=1`。
- [x] 配置 `DDS_DOMAIN_ID` 与 `ROS_DOMAIN_ID` 对齐。
- [x] 启动后检查 ROS graph 中是否存在 `/ap` 节点或裸 DDS `/ap/v1/*` endpoint。
- [x] 记录 `/ap/*` topic 列表。
- [x] 记录 `/ap` node info。
- [x] 订阅 `/ap/v1/time` 并确认能收到真实 sample。
- [x] 检查 `/ap/v1/prearm_check` service 可发现。

建议命令：

```bash
ros2 topic echo --once /ap/v1/time builtin_interfaces/msg/Time
ros2 service list | grep '^/ap/v1/prearm_check$'
ros2 topic list | grep '^/ap/'
```

验收：

- [x] summary 记录 `official_baseline.official_dds_time_received=true`。
- [x] summary 记录 `official_baseline.official_dds_prearm_service_available=true`。
- [x] summary 记录 `official_baseline.ap_topics`。
- [x] summary 记录 `DDS_ENABLE`、`DDS_DOMAIN_ID`、`ROS_DOMAIN_ID`。
- [x] 如果 `/ap/v1/time` sample 收不到，summary 必须 `ok=false` 或 `blocked=true`，并写明 blocker。

## P0.3 官方 Gazebo/SITL bringup 对齐

任务：

- [x] 调研当前 `ardupilot_gz_bringup` 或等价官方 launch 的输入参数。
- [x] 确认官方 Gazebo bringup 如何启动 SITL、Gazebo、DDS、MAVLink GCS。
- [x] 在 orchestration 中预留 official baseline task。
- [x] official baseline task 和 NavLab custom acceptance 分开命名。
- [x] 启动后记录 Gazebo/SITL/GCS/DDS 进程状态。

验收：

- [x] summary 记录 `gazebo_bringup_mode`。
- [x] summary 区分 `official_gz_bringup` 和 `navlab_custom_bringup`。
- [x] summary 记录是否存在 direct set pose。
- [x] 如果 direct set pose 出现，P0 official baseline 不能通过。

## P0.4 官方 Cartographer baseline 对齐

任务：

- [x] 确认官方 Cartographer launch 的输入 topic。
- [x] 确认官方 Lua baseline 的 frame 配置。
- [x] 确认 `/odom -> /odometry` remap 是否符合官方口径。
- [x] 当前 `navlab_cartographer_2d.lua` 与官方 baseline 做差异记录。
- [x] artifact 记录本次使用的 Lua 配置内容或 hash。
- [x] doctor summary 记录 Cartographer backend 是否官方 baseline。

验收：

- [x] summary 记录 `cartographer_ros_present=true`。
- [x] summary 记录 `cartographer_config_path`。
- [x] summary 记录 `cartographer_config_hash`。
- [x] summary 记录 `cartographer_uses_odometry`。
- [x] summary 记录 `tracking_frame`、`published_frame`、`odom_frame`。

## P0.5 ExternalNav route 标注

任务：

- [x] summary 中新增或固化 `external_nav_route`。
- [x] route 至少支持：
  - `official_dds`
  - `mavlink_fallback`
  - `diagnostic_only`
  - `unknown`
- [x] 当前 MAVLink ODOMETRY sender 路线标注为 `mavlink_fallback`。
- [x] Gazebo truth relay 路线标注为 `diagnostic_only`。
- [x] P0 official baseline 只能接受 `official_dds` 或明确的官方等价 route。

验收：

- [x] 使用 MAVLink fallback 时，P0 official baseline 不通过。
- [x] 使用 Gazebo truth diagnostic 时，P0 official baseline 不通过。
- [x] summary 能一眼看出当前 ExternalNav 走的是哪条 route。

## P0.6 Rosbag 和 artifact

任务：

- [x] 为 P0 增加 rosbag profile。
- [x] P0 rosbag required topics 至少包含：
  - `/clock`
  - `/tf`
  - `/tf_static`
  - 官方 `/ap/*` 关键 topic
- [x] artifact 记录 `/ap` node info 输出。
- [x] artifact 记录 topic list。
- [x] artifact 记录 doctor summary。
- [x] artifact 记录 official baseline summary。

验收：

- [x] rosbag profile summary 中 required topics 全部存在。
- [x] P0 summary 中有 `official_baseline` section。
- [x] P0 summary 中有 `rosbag_profile` section。
- [x] Foxglove notes 明确 P0 只用于官方 baseline 观察，不代表 hover 完成。

## P0.7 Orchestration task

任务：

- [x] 在 orchestration task registry 中新增 P0 official baseline doctor。
- [x] 在 orchestration task registry 中新增 P0 official baseline acceptance。
- [x] CLI 命名避免使用旧 stage 口径。
- [x] orchestration CLI 增加 P0 doctor/acceptance task；历史 justfile 便捷入口已回收。
- [x] P0 task 不复用 hover acceptance 的完成判断。

建议命名：

```text
navlab-official-baseline-doctor
navlab-official-baseline-acceptance
```

验收：

- [x] `uv run --project orchestration python orchestration/main.py --help` 能看到 P0 official baseline task。
- [x] CLI help 能看到 P0 official baseline task。
- [x] P0 task 输出 artifact dir。
- [x] P0 task 失败时能给出 blocker，而不是沉默失败。

## P0.8 测试

任务：

- [x] 增加 config 测试：P0 official baseline 配置可加载。
- [x] 增加 task registry 测试：P0 task 已注册。
- [x] 增加 summary schema 测试：`official_baseline` 字段完整。
- [x] 增加 route 判断测试：`mavlink_fallback` 不能通过 P0 official baseline。
- [x] 增加 rosbag profile 测试：P0 required topics 配置存在。

验收：

- [x] P0 相关单元测试通过。
- [x] 不影响现有 hover diagnostic 测试。

## P0.9 Official baseline runtime image

任务：

- [x] 新增 `navlab/official-baseline:latest` 镜像配置。
- [x] 新增 `docker/images/runtime/official-baseline.Dockerfile`。
- [x] 新增 `uv run --project orchestration python orchestration/main.py build official-baseline`。
- [x] P0 doctor 默认检查 dedicated official baseline runtime image，而不是 companion image。
- [x] 构建 `navlab/official-baseline:latest`。
- [x] 构建后重跑 `uv run --project orchestration python orchestration/main.py official-baseline-doctor`。
- [x] doctor summary 中 `official_runtime_image_available=true`。
- [x] doctor summary 中官方 ROS packages 全部 present。
- [x] doctor summary 中 `micro_ros_agent_available=true`。

验收：

- [x] `ros2 pkg prefix ardupilot_sitl` 在 official baseline image 内成功。
- [x] `ros2 pkg prefix ardupilot_gz_bringup` 在 official baseline image 内成功。
- [x] `ros2 pkg prefix ardupilot_cartographer` 在 official baseline image 内成功。
- [x] `command -v MicroXRCEAgent` 或 `command -v micro_ros_agent` 成功。
- [x] P0 acceptance 从 “runtime image missing” 推进到真正检查 `/ap/v1/*` DDS endpoint。

## P0 完成标准

P0 全部完成必须满足：

- [x] `/ap/v1/time` DDS sample 可收到。
- [x] `/ap/v1/prearm_check` service 可发现。
- [x] 关键 `/ap/*` topic 存在。
- [x] DDS domain 配置被 summary 记录。
- [x] official Gazebo/SITL bringup mode 被 summary 记录。
- [x] Cartographer 官方 baseline 依赖存在。
- [x] Cartographer 配置内容或 hash 进入 artifact。
- [x] ExternalNav route 被明确标注。
- [x] 自定义 MAVLink sender 不被当作 official completion。
- [x] Gazebo truth 不被当作 ExternalNav 正式输入。
- [x] rosbag profile 能记录 P0 required topics。
- [x] P0 doctor/acceptance 命令存在。

## 验证记录

当前 P0 official baseline doctor 和 acceptance 已通过。P0 acceptance 使用 dedicated official baseline runtime image 启动官方 Gazebo/SITL/DDS bringup，通过 Cyclone DDS 在 domain 0 收到 `/ap/v1/time` sample，发现 `/ap/v1/prearm_check` service，并录制 P0 required topics 到 MCAP。

- 命令：`uv run --project orchestration python orchestration/main.py official-baseline-doctor`
- 时间：2026-06-06 02:58:55
- artifact：`artifacts/ros/navlab_official_baseline_doctor/20260606_025855`
- 结果：通过
- blocker：无
- 备注：`official_runtime_image_available=true`；`cartographer_ros`、`cartographer_node`、`cartographer_occupancy_grid_node`、`ardupilot_sitl`、`ardupilot_gz_bringup`、`ardupilot_cartographer`、`micro_ros_agent` 均存在；RMW 为 `rmw_cyclonedds_cpp`，DDS domain 为 `0`。

- 命令：`uv run --project orchestration python orchestration/main.py official-baseline-acceptance 30`
- 时间：2026-06-06 03:01:57
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260606_030157`
- 结果：通过
- blocker：无
- 备注：`official_dds_time_received=true`，`official_dds_prearm_service_available=true`，`external_nav_route=official_dds`，`gazebo_bringup_mode=official_gz_bringup`。rosbag profile 通过，MCAP 位于 `artifacts/ros/navlab_companion_sitl_gazebo/20260606_030157/rosbag/rosbag_0.mcap`；计数包含 `/clock=7466`、`/tf=523`、`/tf_static=1`、`/ap/v1/time=207`、`/ap/v1/imu/experimental/data=276`、`/ap/v1/pose/filtered=114`、`/ap/v1/navsat=32`。

历史失败记录保留如下，用于说明 P0 gate 如何从 custom fallback 收敛到 official DDS baseline。

- 命令：`uv run --project orchestration python orchestration/main.py official-baseline-doctor`
- 时间：2026-06-05 23:45:42
- artifact：`artifacts/ros/navlab_official_baseline_doctor/20260605_234542`
- 结果：通过
- blocker：无
- 备注：`cartographer_ros`、`cartographer_node`、`cartographer_occupancy_grid_node` 均存在；Lua config hash 已记录。

- 命令：`uv run --project orchestration python orchestration/main.py official-baseline-acceptance 5`
- 时间：2026-06-05 23:45:59
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260605_234559`
- 结果：未通过，符合当前 P0 预期
- blocker：缺 `/ap` 节点、缺 `/ap/tf`、`external_nav_route=mavlink_fallback`、`gazebo_bringup_mode=navlab_custom_bringup`
- 备注：P0 gate 已能阻止把自定义 MAVLink fallback 误判为官方 baseline 完成。

- 命令：`uv run --project orchestration python orchestration/main.py official-baseline-doctor`
- 时间：2026-06-06 00:04:14
- artifact：`artifacts/ros/navlab_official_baseline_doctor/20260606_000414`
- 结果：未通过，符合当前 P0 预期
- blocker：缺 `ardupilot_sitl`、`ardupilot_msgs`、`ardupilot_dds_tests`、`micro_ros_agent`、`ardupilot_gz_bringup`、`ardupilot_gz_application`、`ardupilot_gazebo`、`ardupilot_gz_gazebo`、`ardupilot_sitl_models`、`ardupilot_cartographer`，且缺 Micro-XRCE-DDS / micro-ROS-Agent 可执行文件
- 备注：doctor 已记录官方来源、启动入口、Cartographer 配置和当前 runtime image。

- 命令：`uv run --project orchestration python orchestration/main.py official-baseline-acceptance 5`
- 时间：2026-06-06 00:05:19
- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260606_000519`
- 结果：未通过，符合当前 P0 预期
- blocker：缺官方 ROS2/DDS package、缺 Micro-XRCE-DDS / micro-ROS-Agent、缺 `/ap` 节点、缺 `/ap/tf`、`external_nav_route=mavlink_fallback`、`gazebo_bringup_mode=navlab_custom_bringup`
- 备注：summary 已记录 Gazebo/SITL/router/gazebo-sensor compose 服务状态。

- 命令：`uv run --project orchestration python orchestration/main.py official-baseline-doctor`
- 时间：2026-06-06 00:20:10
- artifact：`artifacts/ros/navlab_official_baseline_doctor/20260606_002010`
- 结果：未通过，符合当前 P0 预期
- blocker：`navlab/official-baseline:latest` 尚未构建或不可运行，官方 ROS2/DDS package 和 Micro-XRCE-DDS / micro-ROS-Agent 仍缺失
- 备注：P0 doctor 已改为检查 dedicated official baseline runtime image；下一步是执行 `uv run --project orchestration python orchestration/main.py build official-baseline`。

后续每次验证按下面格式记录：

```text
- 命令：
- 时间：
- artifact：
- 结果：
- blocker：
- 备注：
```
