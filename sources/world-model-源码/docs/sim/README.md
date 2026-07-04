# 仿真主线说明

这个目录现在只记录 NavLab 主线需要的仿真契约。旧 Stage 0 的 Python orchestration
入口已经退场；仿真控制面由 `orchestration/sim` 的 Go CLI 负责。

当前仿真链路收敛为：

```text
Gazebo world
  -> /scan_ideal
  -> gazebo_sensor runtime
  -> X2 virtual serial packets
  -> ydlidar_ros2_driver_node
  -> /scan
  -> NavLab companion runtime
  -> /scan_features, /navlab/mission/status, MAVLink setpoint
```

P13 之后，Nav2 导航链路也属于仿真主线：

```text
Gazebo/SITL + Cartographer
  -> /map, /slam/odom, /scan, TF
  -> Nav2 planner/controller/BT
  -> /cmd_vel_nav
  -> navigation adapter
  -> /navlab/fcu/setpoint/intent
  -> FCU controller
  -> /ap/v1/cmd_vel
```

## 当前服务边界

```text
orchestration/
  sim/
    cmd/navlab-sim
  real/

navlab/
  gazebo_sensor/
    x2/
  companion/
  slam/
  common/
  sim/
```

- `navlab.sim.gazebo_sensor` 只负责 Gazebo ideal scan 到厂商驱动 `/scan` 的传感器链路。
- 仿真 companion 节点放在 `navlab.sim.companion.nodes`；launcher/config/acceptance 放在 `navlab.sim.companion.runtime`。
- SLAM backend/config wrapper 放在 `navlab.common.slam`，因为当前 real/sim 共用同一套 backend registry 和 launch 参数契约。
- `common` 只放跨服务复用的纯工具，不拥有 ROS runtime 职责。

## 关键 topic

- `/scan_ideal`: Gazebo 直出的理想 LaserScan，只用于传感器仿真输入和 Foxglove 对照。
- `/sim/x2/status`: X2 虚拟串口仿真状态。
- `/scan`: 厂商 `ydlidar_ros2_driver_node` 发布的最终 LaserScan。
- `/scan_features`: companion 从最终 `/scan` 提取的扇区特征。
- `/sim/markers`: companion 发布的 UAV、路径和障碍物 marker。
- `/navlab/mission/status`: mission controller 发布的任务阶段和 setpoint 状态。
- `/cmd_vel_nav`: Nav2 controller 输出，不能直接接 FCU。
- `/navlab/fcu/setpoint/intent`: navigation adapter 输出的 bounded intent。
- `/navlab/navigation/status`: P13 mission status，记录 accepted goals、path length、coverage 和 blockers。
- `/navlab/navigation/adapter/status`: adapter active/hold/clamp 状态。
- `/navlab/landing/status`: completion policy 和 landing acceptance 的最终证据。

下游 SLAM、mission 和 rosbag 只应消费最终 `/scan`，不能依赖 X2 协议包或虚拟串口内部细节。

## 当前命令

主线入口放在 Go sim CLI：

```bash
cd orchestration/sim && go run ./cmd/navlab-sim build all
cd orchestration/sim && go run ./cmd/navlab-sim doctor
X2_MODE=driver-smoke X2_SMOKE_DURATION_SEC=8 X2_ARTIFACT_DIR=/artifacts/ros/x2_driver_smoke/manual docker compose --file compose/docker-compose.yaml --project-directory . --profile x2_sensor up --abort-on-container-exit --exit-code-from gazebo-sensor gazebo-sensor
cd orchestration/sim && go run ./cmd/navlab-sim run hover --duration-sec 90
cd orchestration/sim && NAVLAB_SIM_DISTRO=jazzy NAVLAB_SIM_IMAGE_TAG=jazzy-latest go run ./cmd/navlab-sim run navigation
cd orchestration/sim && go run ./cmd/navlab-sim foxglove upload 20260614T093531Z --task navigation --dry-run
```

`NAVLAB_SIM_DISTRO` and `NAVLAB_SIM_IMAGE_TAG` must describe the same ROS
distro. For Humble images, use a Humble tag such as `humble-latest`; otherwise
let the default tag policy resolve the tag from the selected distro.

NavLab acceptance 会启动 Gazebo、SITL、MAVLink router、gazebo sensor、companion、SLAM 和 Foxglove，
并生成 rosbag/MCAP、`summary.json`、`summary.md` 和 Foxglove 回放说明。

Foxglove 上传入口属于 Go sim CLI。默认上传当前 task raw MCAP；传 `--lite`
时只上传已经存在的 `rosbag_foxglove/rosbag_foxglove_0.mcap`。上传命令只认
`artifacts/sim/<task>/<run>` 和当前分层 rosbag 布局，不再兼容旧
`artifacts/ros/...` 或 `rosbag/rosbag_0.mcap` 布局。

P13 navigation 的当前通过样例为：

```text
artifacts/sim/navigation/20260614T062658Z/summary.json
```

它证明 mission goal 已发送，Nav2 bounded goals 被 accepted，`/cmd_vel_nav`
产生并进入 adapter，FCU controller 发布 `/ap/v1/cmd_vel`，最终 landing 和
rosbag profiles 均通过。

## Foxglove 回放

验收 rosbag 应至少包含：

- `/scan`
- `/scan_ideal`
- `/sim/x2/status`
- `/scan_features`
- `/sim/markers`
- `/navlab/mission/status`

3D 面板建议固定 frame 为 `map`。`/sim/markers` 用于显示 UAV、路径和障碍物；
`/scan` 与 `/scan_ideal` 用于对照最终厂商 scan 和 Gazebo ideal scan。

## 历史说明

`docs/sim/todo.md` 保留早期 Stage 0 仿真任务记录，只作为历史上下文。当前可执行主线以
NavLab 设计文档、X2 协议级仿真设计和 `docs/general/旧 Python 外壳_service_refactor_todo.md` 为准。
