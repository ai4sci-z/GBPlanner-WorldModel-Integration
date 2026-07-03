# 预研 A · 在本机完整复现并运行 world-model 仿真

> 目的:**完整复现并实际运行** world-model(不止构建),亲眼跑通 exploration 任务,**用证据论证** frontier_lite 探索的不足,为引入 GBPlanner 提供实据。
> 状态:🔵 **~80%,运行时剥洋葱到最后几层**(9 坑修 8,总根因已破)。最后更新 2026-07-03。

## 一、目标(精细度要求)
1. 在本机把 world-model 仿真**完整跑起来**:Gazebo(无头)+ ArduPilot SITL + Cartographer SLAM + exploration 任务。
2. **实跑 frontier_lite**,做小 demo 暴露其局限(2D 平面、覆盖不充分、易停),**用数据+截图充分论证"需要改进"**(不空口)。
3. 为后续 GBPlanner vs frontier_lite 对比实验铺底。

## 二、当前进度(2026-07-03)
| 步骤 | 状态 |
|---|---|
| 克隆仓库 + 子模块 | ✅ |
| **构建 9/9 镜像(humble)** | ✅ 全部实测存在(排掉 6 个 jazzy→humble 构建坑,见 [预研A_构建排错记录.md](预研A_构建排错记录.md)) |
| **运行时排坑(9 个,jazzy→humble 迁移遗留)** | 🔵 **已修 8 个、全部实锤**:tomllib/空launch参数/模板`%%`/venv悬空/setup.bash缺失/rclpy版本/ydlidar驱动+declare_parameter/QoS/**总根因 sdformat_urdf-gpu_lidar→RSP崩→机器人从未生成**。全证据链:[运行时排错记录_humble.md](运行时排错记录_humble.md) |
| 机器人生成链(spawn/传感器/SITL JSON) | ✅ **手动常驻验证四连全绿**(RSP 活/iris 在 gz/激光出数据/JSON 接通) |
| 编排环境端到端(exploration 全绿) | ◉ **当前站**:baseline 话题对其他容器不可见(DDS 隔离嫌疑),探针已备 |
| frontier_lite 真实指标 + 截图留痕 | ⬜ 等上一步 |
| 论证 frontier_lite 不足(小 demo) | ⬜ 代码级铁证已有(脚本循环、不读图);量化等实跑 |

## 三、计划步骤 + 留痕清单
1. `cd ~/ws/world-model/orchestration/sim && go run ./cmd/navlab-sim ...` 构建/启动 exploration。
   - 📸 留痕:`navlab-sim list-tasks/doctor` 输出、镜像构建日志。
2. 起 Gazebo(headless)+ SITL + SLAM,跑 exploration(frontier_lite)。
   - 📸 留痕:RViz/Gazebo 截图、无人机轨迹、Cartographer 2D 地图、覆盖率随时间曲线、rosbag。
3. **论证缺陷的小 demo**:量化 frontier_lite 的覆盖率/用时/是否卡死/只在 2D 平面探索 → 出表+图,存 `images/预研A_*.png`。

## 四、为什么这一步重要(给报告)
组会要"充分论证",不能只说"frontier_lite 不行"。本预研产出**实跑证据**(截图+指标),证明其局限,再引出 GBPlanner 的价值——这是论证链的第一环。

## 五、风险/注意
- 镜像构建重(1–2h)、容器内拉 github 需代理(参照预研B 的 `--build-arg HTTPS_PROXY`)。
- WSL2 跑 Gazebo GUI 用 WSLg;吃力则用 headless + rosbag + 截图。

## 六、已验证(本机真实运行,留痕)2026-06-29
- **平台自检(真跑)**:`navlab-sim doctor` → OK config loaded / OK task registry configured / backend=docker / **task_count=5**(Go 1.24)。
- **任务清单(真跑)**:exploration / hover / hover-slam-only / navigation / scan-robustness(共 5)。
- **构建计划(dry-run)**:全套 **9 个镜像**,distro=**jazzy**:ros-base、ardupilot-sitl、mavlink-router、gazebo-headless、fast-lio、companion、slam(cartographer)、gazebo-sensor、official-baseline。
- **网络验证(留痕)**:构建容器默认 bridge 网络**直连 github = HTTP/2 200**(无需代理);host 网络经 127.0.0.1:7897 代理也通;Docker Hub 基础镜像由守护进程代理拉取。
- **Go 修正**:Go 1.24 在 `/usr/local/go/bin`,需置于 PATH 前(apt 旧 1.18 会盖住)。
- **构建已后台启动**:`navlab-sim build all`,日志 `~/navlab_build.log`;完成后回收结果、补截图。
- 📸 截图待补:`navlab-sim doctor/list-tasks` 终端、构建日志、后续 Gazebo/RViz 画面 → 存 `images/预研A_*.png`。
