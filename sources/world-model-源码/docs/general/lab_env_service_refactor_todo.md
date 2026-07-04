# NavLab 服务边界重构 TODO

## 目标

把 Python 代码重构成“按运行位置和服务归属组织”的包，而不是按泛化类别组织。

当前问题：

- 旧 sim node 包太泛，里面很多节点实际由 NavLab companion runtime 启动。
- 旧 sim sensor/X2 包实际只属于 Gazebo/sensor 容器，不应该被 companion、SLAM、SITL 感知。
- 旧扫描桥独立 compose service 和 `gazebo-sensor` 职责重叠。
- `tests/` 平铺过多，测试归属不清晰。

重构后的原则：

- 代码归属等于服务归属。
- 配置归属等于启动方归属。
- 测试目录结构跟随代码目录结构。
- compose 只描述基础服务，服务内部进程由对应 Python runtime 管理。
- companion、SLAM、SITL 只消费最终 `/scan`，不感知 X2 协议和 `/tmp/navlab_x2`。

P8 之后的目标结构：

```text
orchestration/              # host 侧 Docker/acceptance/Foxglove 编排
navlab/
  companion/                # companion 容器内部 runtime 和节点
  slam/                     # 后续 SLAM runtime/doctor/config，当前可先占位
  gazebo_sensor/            # Gazebo/sensor 容器内部 runtime
  common/                   # 真正跨服务复用的纯工具
  sim/                      # 仿真 world/waypoint/status helper
```

目标测试结构：

```text
orchestration/
  tests/                    # host 编排测试

navlab/
  tests/                    # container runtime 测试
    companion/
    slam/
    gazebo_sensor/
      x2/
    common/
    sim/
```

## 设计判断：为什么 X2 仿真先用 Python

当前 X2 模拟使用 Python 是合理的，因为它处在“仿真协议和编排层”，不是 Gazebo
物理插件层：

- 现阶段重点是验证链路：`/scan_ideal -> X2 packets -> vendor driver -> /scan`。
- Python 更适合快速实现协议 encoder、PTY 虚拟串口、ROS topic glue、summary 和 smoke。
- 当前频率约 `3000 samples/sec`、`7 Hz`，Python 写串口包足够支撑验收。
- 代码和 NavLab acceptance、rosbag、Foxglove summary 都在 Python 体系里，调试成本低。
- 厂商 driver 本身仍然是 C++，最终 `/scan` 仍由 `ydlidar_ros2_driver_node` 发布。

后续需要 C++ 的条件：

- 要写 Gazebo RaySensor/System plugin，直接读取 Gazebo sensor 内部数据。
- Python emulator 成为性能瓶颈，出现稳定丢帧或串口写入抖动。
- 需要更接近硬件时序、中断、buffer overflow 或 SDK 命令流行为。
- 要把 X2 仿真作为独立高性能传感器插件长期维护。

因此当前策略是：

```text
P4/P5: Python runtime + vendor C++ driver
P6: Python 标定噪声/丢点/误差模型
P7+: 如有必要，再新增 C++ Gazebo plugin 或 C++ emulator
```

## P0：冻结当前行为和边界

目标：先把可用链路固定住，避免重构时行为漂移。

### 任务

- [x] 记录当前 staged/unstaged 变更的主要功能边界。
- [x] 确认当前 NavLab 入口只保留 `doctor`、`acceptance`、image build。
- [x] 确认 Stage 0/Stage 1 旧启动命令不再作为主线保留。
- [x] 确认 X2 链路当前入口为 `gazebo-sensor` 容器。
- [x] 确认 `/scan` publisher 是 `ydlidar_ros2_driver_node`。
- [x] 确认 `/scan_ideal` 只是 Gazebo ideal/debug topic。

### 验收

- [x] `ruff` 和现有相关 `pytest` 通过。
- [x] `docker compose config` 中 NavLab acceptance 不包含旧扫描桥 service。
- [x] 文档明确 companion、SLAM、SITL 不拥有 X2 vendor dependency。

## P1：合并 scan bridge 到 gazebo_sensor

目标：删除独立旧扫描桥服务，让 Gazebo/sensor runtime 独占 scan 输入链路。

### 任务

- [x] 删除 compose 中旧扫描桥 service。
- [x] 删除旧扫描桥 entrypoint。
- [x] 删除旧 ROS-Gazebo scan bridge 配置，或迁移为 runtime 内部配置。
- [x] 确保 `gazebo_sensor.runtime` 启动 `/scan_ideal` bridge。
- [x] 确保 `gazebo_sensor.runtime` 启动 X2 emulator。
- [x] 确保 `gazebo_sensor.runtime` 启动 `ydlidar_ros2_driver_node`。
- [x] 确保 orchestration 只启动 `gazebo-sensor`，不直接启动 X2 节点。

### 验收

- [x] `docker compose config` 不再出现旧扫描桥 service。
- [x] `gazebo-sensor` 日志能看到 bridge、emulator、vendor driver 三个进程。
- [x] `/scan_ideal`、`/sim/x2/status`、`/scan` 同时存在。
- [x] `/scan` publisher 是 `ydlidar_ros2_driver_node`。

## P2：迁移 X2 包到 gazebo_sensor

目标：让 X2 协议仿真代码只属于 Gazebo/sensor 服务。

### 任务

- [x] 创建 `navlab/sim/gazebo_sensor/` 包。
- [x] 移动旧 sim sensor/X2 包到 `navlab/sim/gazebo_sensor/x2/`。
- [x] 移动旧 X2 runtime 到 `navlab/sim/gazebo_sensor/runtime.py`。
- [x] 移动旧 X2 config 到 `navlab/sim/gazebo_sensor/config.py`。
- [x] 移动旧 X2 CLI 到 `navlab/sim/gazebo_sensor/cli.py`。
- [x] 更新 Docker entrypoint 调用 `python -m navlab.sim.gazebo_sensor.cli`。
- [x] 记录 X2 driver smoke 原始 docker compose 命令；历史 justfile 便捷入口已回收。
- [x] 更新所有 import。
- [x] 删除空的旧 sim sensor 包。

### 验收

- [x] repo 中不存在旧 sim sensor/X2 包。
- [x] X2 相关 import 全部指向 `navlab.sim.gazebo_sensor`。
- [x] `gazebo_sensor` 镜像仍可执行 driver smoke。
- [x] companion、SLAM、SITL 代码没有 import `gazebo_sensor.x2`。

## P3：迁移 companion 节点归属

目标：历史阶段先把由 companion runtime 启动的节点集中起来；当前结构已经继续按
real/sim 安全域拆到 `navlab.real.companion.nodes` 和
`navlab.sim.companion.nodes`。

### 任务

- [x] 历史阶段创建过 `navlab/companion/` 包；当前已拆到
  `navlab.sim.companion.runtime`、`navlab.sim.companion.nodes` 和
  `navlab.real.companion.nodes`。
- [x] 将 companion launcher/config/CLI/acceptance 归档到
  `navlab.sim.companion.runtime`。
- [x] 迁移 `world_marker_publisher` 到 `navlab.sim.companion.nodes.world_markers`。
- [x] 迁移 `scan_features_publisher` 到 `navlab.sim.companion.nodes.scan_features`。
- [x] 迁移 `mavlink_gazebo_pose_mirror` 到 `navlab.real.companion.nodes.pose_mirror`。
- [x] 迁移 `mavlink_imu_bridge` 到 `navlab.real.companion.nodes.imu_bridge`。
- [x] 迁移 `mavlink_external_nav_sender` 到 `navlab.real.companion.nodes.external_nav`。
- [x] 迁移 `mavlink_obstacle_mission_controller` 到 `navlab.sim.companion.nodes.obstacle_mission`。
- [x] 清理旧 sim node 包中已经不再通用的文件。

### 验收

- [x] companion runtime 不再从旧的未分域 companion node 包启动节点；节点入口已分到
  `navlab.real.companion.nodes` 和 `navlab.sim.companion.nodes`。
- [x] mission status 仍发布 `/navlab/mission/status`。
- [x] scan features 仍消费最终 `/scan`，发布 `/scan_features`。
- [x] pose mirror、IMU bridge、ExternalNav sender 行为不变。

## P4：建立 common 工具包

目标：只把真正跨服务复用的无业务工具放到 `common`。

### 任务

- [x] 创建 `navlab/common/` 包。
- [x] 迁移 `旧 Python 外壳/logging_utils.py` 到 `navlab/common/logging.py`。
- [x] 迁移 `navlab/runtime/process_manager.py` 到 `navlab/common/process_manager.py`。
- [x] 迁移 `sim/rosbag.py` 到 `navlab/common/rosbag.py`。
- [x] 审核 `sim/perception` 是否应归属 companion，避免留泛目录。
- [x] 保留 `旧 Python 外壳/config.py` 作为全局 host/project config，或拆出服务配置读取。

审计结论：`sim/perception` 是纯 LaserScan/stop-guard 算法工具，迁移到
`navlab/common/perception`，由 companion 和 legacy sim 共同复用。

### 验收

- [x] `common` 不 import `navlab`、`gazebo_sensor` 或具体服务节点。
- [x] 服务包可以 import `common`。
- [x] 没有服务包之间的反向依赖。

## P5：重排 tests 目录

目标：先把原来平铺的测试按服务边界分组。P10 后，测试进一步跟随 project
边界迁移到 `orchestration/tests/` 和 `navlab/tests/`。

### 任务

- [x] 创建中间测试分组目录。
- [x] 迁移 `test_navlab_config.py` 中 orchestration 相关测试。
- [x] 迁移 companion runtime、acceptance、artifact 测试。
- [x] 迁移 X2 protocol、emulator、scan source、driver smoke 测试。
- [x] 迁移 rosbag、process manager、logging 测试。
- [x] 更新 `pytest` 收集路径和任何脚本里的测试路径。

### 验收

- [x] 每个服务的测试都先进入对应分组。
- [x] 中间状态 `pytest` 通过。

## P6：更新 CLI 和镜像入口

目标：外部命令仍简单，但内部路径符合新服务结构。

### 任务

- [x] `orchestration/main.py` 只引用 `orchestration/src/cli.py` 的 Typer app。
- [x] companion 容器 entrypoint 调用 `navlab.sim.companion.runtime.cli`。
- [x] gazebo-sensor 容器 entrypoint 调用 `gazebo_sensor.cli`。
- [x] orchestration 原始 image build 命令保持可用。
- [x] smoke/acceptance 原始命令更新到新模块路径。
- [x] Dockerfile 中 Python dependency group 仍按镜像边界安装。

### 验收

- [x] `just --list` 不出现旧 Stage 0/Stage 1 启动命令。
- [x] `uv run --project orchestration python orchestration/main.py build gazebo-sensor` 可构建目标镜像。
- [x] `X2_MODE=driver-smoke X2_SMOKE_DURATION_SEC=8 X2_ARTIFACT_DIR=/artifacts/ros/x2_driver_smoke/manual docker compose --file compose/docker-compose.yaml --project-directory . --profile x2_sensor up --abort-on-container-exit --exit-code-from gazebo-sensor gazebo-sensor` 通过。
- [x] `uv run --project orchestration python orchestration/main.py doctor` 通过。

## P7：完整 acceptance 和 rosbag 回放

目标：确认重构没有改变真实验收链路。

### 任务

- [x] 构建 companion、SLAM、gazebo-sensor 镜像。
- [x] 跑 `uv run --project orchestration python orchestration/main.py acceptance 90`。
- [x] 检查 summary 中 `scan_source = "x2_virtual_serial_vendor_driver"`。
- [x] 检查 rosbag 包含 `/scan`、`/scan_ideal`、`/sim/x2/status`、`/scan_features`。
- [x] 检查 `/scan_features` message count 非零。
- [x] 在 Foxglove 回放中确认能看到 ideal scan 和最终 vendor scan。

### 验收

- [x] summary.json 中 `ok=true`。
- [x] summary.md 写出 X2 sensor 和 `/scan` publisher。
- [x] rosbag MCAP 可以用于 Foxglove 回放完整任务。
- [x] companion、SLAM、SITL 镜像没有 X2 vendor dependency。

## P8：删除遗留目录和文档修正

目标：完成结构收敛，避免后续继续使用旧路径。

### 任务

- [x] 删除空的旧 sim node 包。
- [x] 删除空的旧 sim sensor 包。
- [x] 删除或迁移 `navlab/sim/runtime.py`。
- [x] 更新 `docs/README.md` 推荐阅读顺序。
- [x] 更新 X2 设计文档中的模块路径。
- [x] 更新 NavLab 设计文档中的服务结构图。
- [x] 更新 commit message 或 PR 描述，说明这是包结构重构。

### 验收

- [x] 旧 sim node/sensor Python import 不再命中主线代码。
- [x] 旧扫描桥 service 名不再命中 compose 和主线文档。
- [x] `ruff` 和 `pytest` 通过。
- [x] 关键 smoke 通过。

## P9：拆成 host orchestration 和 container navlab 顶层包

目标：让包结构直接反映运行位置。宿主机本地执行的 Docker/build/acceptance/Foxglove
编排代码放到根目录 `orchestration/`；容器内部 runtime 代码放到根目录 `navlab/`。

### 任务

- [x] 创建根目录 `orchestration/`，迁移 host 侧 `cli.py`、`host.py`、`config.py`、`artifacts.py`；Foxglove 上传改由外部脚本负责。
- [x] 创建根目录 `navlab/`，迁移 `companion/`、`gazebo_sensor/`、`common/`、`sim/`。
- [x] 删除旧 Python 包外壳。
- [x] 历史 justfile 便捷入口已回收，文档改为记录 `python orchestration/main.py ...` 原始命令。
- [x] 更新 Docker entrypoint，直接调用 `navlab.sim.companion.runtime...` / `navlab.sim.gazebo_sensor...`。
- [x] 更新 Dockerfile/uv project 路径，避免再依赖旧包外壳下的 pyproject。
- [x] 更新测试 import 和测试目录路径。
- [x] 更新文档中的主线路径。

### 验收

- [x] 旧包外壳的 Python import 和 module entrypoint 不再命中主线代码。
- [x] `python orchestration/main.py --help` 可运行。
- [x] `python -m navlab.sim.companion.runtime.cli --help` 可运行。
- [x] `python -m navlab.sim.gazebo_sensor.cli --help` 可运行。
- [x] `ruff` 和 `pytest` 通过。
- [x] `just --list` 保持干净；历史 build/doctor/acceptance 改回 orchestration 原始命令记录。

## P10：测试也跟随 project 边界拆分

目标：根目录不再保留混合测试；host 编排测试属于 `orchestration` project，容器 runtime
测试属于 `navlab` project。

### 任务

- [x] 移动 host 编排测试到 `orchestration/tests/`。
- [x] 移动 companion、gazebo_sensor、common、sim 测试到 `navlab/tests/`。
- [x] 删除根目录 `tests/`。
- [x] 为两个 project 分别保留 `conftest.py`。

### 验收

- [x] `pytest orchestration/tests -q` 通过。
- [x] `pytest navlab/tests -q` 通过。
- [x] `rg "^tests/"` 不再命中主线测试路径。
