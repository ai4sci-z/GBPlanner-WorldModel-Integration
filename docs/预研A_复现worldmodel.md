> 📌 **状态戳(2026-07-06)**:本文含历史阶段内容。**当前权威状态**以 [RESUME_新窗口接管_2026-07-06.md](../RESUME_新窗口接管_2026-07-06.md) + [Bug 台账](../docs/world-model端到端Bug台账_给作者PR.md) 为准。要点:jazzy 镜像 **9/9 已完成并开箱验真**;无 hack 配置**物理起飞已复现**(run 20260706T110405:SIM+0.76m/电机1950/DAlt0.655m);**端到端 exploration 尚未全绿**(剩 frame_contract_probe:/tf_static=QoS、/ap/v1/pose/filtered=时序非QoS、accepted_goals 2<3);**未提交 PR**。

# 预研 A · 在本机完整复现并运行 world-model 仿真

> 目的:**完整复现并实际运行** world-model(不止构建),亲眼跑通 exploration 任务,**用证据论证** frontier_lite 探索的不足,为引入 GBPlanner 提供实据。
> 状态:🔵 **~90%(2026-07-04)**:35轮实验修13坑;感知层全通→SLAM闭环(tight)→位姿回灌飞控(pose_samples=153);当前站 FCU bootstrap。战役全解见 [预研A排错战役实录_35轮实验全解.md](预研A排错战役实录_35轮实验全解.md)。最后更新 2026-07-04。

## 一、目标(精细度要求)
1. 在本机把 world-model 仿真**完整跑起来**:Gazebo(无头)+ ArduPilot SITL + Cartographer SLAM + exploration 任务。
2. **实跑 frontier_lite**,做小 demo 暴露其局限(2D 平面、覆盖不充分、易停),**用数据+截图充分论证"需要改进"**(不空口)。
3. 为后续 GBPlanner vs frontier_lite 对比实验铺底。

## 二、当前进度(2026-07-04)
| 步骤 | 状态 |
|---|---|
| 克隆仓库 + 子模块 | ✅ |
| **构建 9/9 镜像(humble)** | ✅ 全部实测存在(排掉 6 个 jazzy→humble 构建坑,见 [预研A_构建排错记录.md](预研A_构建排错记录.md)) |
| **运行时排坑(13 个,jazzy→humble 迁移遗留)** | 🔵 **35轮实验全实锤**:tomllib/空参/`%%`/venv悬空/setup.bash/rclpy版本/ydlidar+declare_parameter/QoS/**总根因sdformat_urdf-gpu_lidar-RSP**/CYCLONEDDS/SDF版本/**uid无passwd致gz分区错乱**/IMU自吞回声。全证据链:[运行时排错记录_humble.md](运行时排错记录_humble.md)、[战役实录](预研A排错战役实录_35轮实验全解.md) |
| 机器人生成链(spawn/传感器/SITL JSON) | ✅ 手动四连全绿 → **编排环境也全通**(感知层 /scan /tf /imu) |
| SLAM 闭环 | ✅ quality=tight,/slam/odom 真实流动(坑#13 IMU 自吞回声两针修复后) |
| 位姿回灌飞控 EKF | ✅ controller pose_samples=153,状态推进到 waiting_for_fcu_bootstrap |
| 编排环境端到端(exploration 全绿) | ◉ **当前站**:FCU bootstrap(坑#14候选:控制器请求 mode 15=AUTOTUNE 而 required=4=GUIDED;PreArm VisOdom) |
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
