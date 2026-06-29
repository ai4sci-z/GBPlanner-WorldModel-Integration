# 预研 A · 在本机完整复现并运行 world-model 仿真

> 目的:**完整复现并实际运行** world-model(不止构建),亲眼跑通 exploration 任务,**用证据论证** frontier_lite 探索的不足,为引入 GBPlanner 提供实据。
> 状态:🔵 进行中 —— 子模块已拉完;镜像构建待启动(重型,约 1–2h)。最后更新 2026-06-29。

## 一、目标(精细度要求)
1. 在本机把 world-model 仿真**完整跑起来**:Gazebo(无头)+ ArduPilot SITL + Cartographer SLAM + exploration 任务。
2. **实跑 frontier_lite**,做小 demo 暴露其局限(2D 平面、覆盖不充分、易停),**用数据+截图充分论证"需要改进"**(不空口)。
3. 为后续 GBPlanner vs frontier_lite 对比实验铺底。

## 二、当前进度
| 步骤 | 状态 |
|---|---|
| 克隆 world-model 仓库 | ✅ |
| 拉取子模块(ardupilot/Livox-SDK2/YDLidar-SDK 等) | ✅ exit 0 |
| 构建镜像集(navlab-sim build / docker) | ⬜ 待启动(需处理容器内 github 代理) |
| 运行 exploration 任务 | ⬜ |
| 截图 + 覆盖率/用时数据留痕 | ⬜ |
| 论证 frontier_lite 不足(小 demo) | ⬜ |

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
