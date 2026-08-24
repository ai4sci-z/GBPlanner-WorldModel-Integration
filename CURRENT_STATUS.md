# CURRENT_STATUS（唯一当前状态源；最后更新 2026-08-24）

> 任务队列见 [TASKS.md](TASKS.md)，现场交接见
> [接力棒_当前值班.md](接力棒_当前值班.md)，执行纪律见
> [工作铁律.md](工作铁律.md)。历史结论保留在 `docs/archive/`，不得回填为当前事实。

## 一、项目章程与固定顺序

目标：将 GBPlanner 从 ROS 1 无损迁移到 ROS 2，作为独立、可配置、可切换、可回滚的
探索算法接入 world-model，并与 `frontier_lite` 并列。

固定路线不得跳步：

1. P0：清理并治理仓库与文档。
2. P1：证明长时间闭环稳定。
3. P2：完成 ROS 1 / ROS 2 像素、参数、消息、I/O 与时序对齐。
4. P3：证明 3D 行为无损。
5. P4：把真 GBPlanner 作为独立、可切换 WorldModel 探索算法正式集成。

GPS-denied 多层楼梯探索只做架构研究，不进入当前实现排期。

## 二、当前三仓基线

| 仓库 | 当前基线 | 角色与远端口径 |
|---|---|---|
| `/home/ai4s/projects/GBPlanner-WorldModel-Integration` | `main` | 治理、状态与证据入口；`origin/main` 是授权远端 |
| `/home/ai4s/projects/gbp-feat` | `feat/gbplanner-ros2-port@f9c20f296fe629817176cfdbaabc6fc6a31bdb27` | 真 GBPlanner ROS 2 迁移代码；与授权 `origin` 完全一致 |
| `/home/ai4s/projects/world-model` | `fix/world-model-e2e-takeoff@8649ae553e0b433b867c301b05ca780d49cd2530` | 仿真与运行链；与授权 `backup` 完全一致；禁止向只读平台上游推送 |

GitHub 来源已于 2026-08-24 直接核验：

- 原始平台仓是 `https://github.com/SZ-surveying/world-model`。它是 GitHub Organization
  下的原生仓库，`fork=false`、`parent=null`，根提交 `c73dfd4` 无父提交；公开上游只有
  `main` 分支，最后推送于 2026-06-27。
- 授权修复镜像是 `https://github.com/ai4sci-z/world-model`，包含
  `fix/world-model-e2e-takeoff@8649ae5`；本轮修复只推送到该镜像。
- 两仓均无 Tag 和 Release；2026-08-24 未发现遗漏的线上更新。
- `ntnu-arl/gbplanner_ros` 是 GBPlanner 算法来源，不是 world-model 平台仓。

## 三、NVIDIA 与容器环境

2026-08-24 宿主与容器实测：

- GPU：NVIDIA GeForce RTX 5060 Laptop GPU，8151 MiB VRAM。
- 驱动：595.84；驱动报告 CUDA 13.2。
- 宿主 `nvidia-smi` 正常；`nvidia-container-cli info` 正常；Docker 已注册 NVIDIA runtime。
- `docker run --rm --gpus all navlab/official-baseline:jazzy-latest nvidia-smi` 通过，容器内
  NVML 和设备映射正常。
- 本轮没有重启。先前沙箱内看不到 `/dev/nvidia*` 是隔离表现，不能据此宣称宿主驱动损坏。

2026-07-31 的 `NVML: Driver Not Loaded` 当前已不复现，但只说明 GPU 环境门已恢复，不能把
旧任务结果改判为 PASS。

## 四、ROS 2 构建与测试事实

2026-08-24 在固定镜像 `voxblox_ros2_deps:jazzy`（镜像 ID
`sha256:5f4a1875...`）中把 `gbp-feat@ef4f96f` 源码只读挂载、复制到容器原生文件系统后验证：

- `colcon build --merge-install --executor sequential --packages-up-to gbplanner_node`：
  11 个依赖包全部完成，`gbplanner_core` 与 `gbplanner_node` 均成功链接。
- `gbplanner_core` gtest：4/4 通过。
- M4 真 RRG 合成场景：`TRAJ_POINTS=13`，`pci_trigger_node` 发布 13 个航点。
- Python：`test_intent_z.py` 与 `test_enable_lease.py` 共 17/17 通过。
- world-model：`go test ./...` 全模块通过；回归测试固定
  `exploration_probe=required`、`slam_hover_probe=optional`、
  `frame_contract_probe=required`、`exploration_workflow=mission`。
- 可复核证据目录：`/home/ai4s/aa_runs/gbplanner_verify/20260824T031820Z`，其中
  `result.txt` 为 `VERIFY_RC=0`。
- `f9c20f2` 新增 M5 同 run 结构化验收器并把运行时 Python 回归扩为 20/20；未改 C++，
  上述 `ef4f96f` 全量构建证据仍是其直接父提交的有效构建基线。

历史 `voxblox_eval.cc` 缺 `pcl_ros/transforms.hpp` 的根因是用错镜像：

- `voxblox_ros2_deps:jazzy` 中该头文件存在，当前全链构建成功。
- `navlab/official-baseline:jazzy-latest` 是运行镜像，不安装 `ros-jazzy-pcl-ros`，在其中编译
  voxblox 必然失败。
- 正确修复是固定构建入口与镜像职责，不是改掉源码中正确的 include，也不默认膨胀运行镜像。

统一重建入口：`/home/ai4s/projects/gbp-feat/runbooks/ros2_port/verify_current_ros2.sh`。

## 五、真实运行证据与边界

- 真 GBPlanner ROS 2 核心位于 `gbp-feat/ros2_port/`；M4 合成场景已证活，但不等于
  world-model 正式闭环通过。
- P1-2 首次固定 SHA run：
  `world-model/artifacts/sim/exploration/20260824T033655.765292080Z`。最终
  `ok=false`、`TASK_STATUS_ERROR`、required `exploration_probe` rc=20，诚实判 FAIL。
  FCU/controller、起飞和 setpoint 链正常；GBPlanner RRG 每轮只有 1 顶点/0 边且无轨迹。
  直接根因是 M5 仍把 voxblox 接到旧 2D `/cloud_in`（frame=`base_scan`），自由体素只出现在
  低位，规划高度保持 Unknown。`f9c20f2` 已改接 `/wm/cloud3d`、补
  `base_link -> lidar3d_frame` 固定外参，并要求同 run 五类证据，等待复跑验证。
- 2026-07-28 的真 M5 现场曾观察到 RRG 175 顶点、624 边、15 前沿和 PCI 航点输出；当时
  执行闭环失败，不能算验收。
- 2026-07-30 长跑证据目录：
  `world-model/artifacts/sim/exploration/20260730T033541.154997958Z`。rosbag 约 9578.844 秒、
  8,524,637 条消息；早期探针看到起飞、controller ready、8 goals、1.8245 m 路径，但没有
  最终 summary，状态仍 `ok=false`，必须判未完成/未验收。
- 最新正式失败目录：
  `world-model/artifacts/sim/exploration/20260731T065059.411462422Z`，失败于当时的 NVML 门。
- `/home/ai4s/aa_runs/gbplanner_strategy_v4.py` 是 2D OccupancyGrid 增益代理，不是真
  GBPlanner/RRG。桌面入口已在 2026-08-24 将“真 GBPlanner”和“2D 增益代理演示”分轨。

## 六、阶段门状态

| 阶段 | 状态 | 当前判定 |
|---|---|---|
| P0 仓库/文档治理 | 本轮闭包完成 | 当前事实源、claim 清单和机器闭包规则已统一；三仓 manifest 按双提交协议绑定 |
| P1 长时间闭环稳定 | 进行中 | P1-1 正式 required probe 已恢复并有回归测试；当前停点是固定 SHA 的真 GBPlanner 短闭环 |
| P2 ROS1/ROS2 对齐 | 阻塞 | 等 P1；只允许离线准备，不做通过声明 |
| P3 3D 无损 | 阻塞 | 等 P2；M4 和单次航点输出不足以证明 3D 等价 |
| P4 插件化接入 | 阻塞 | 桌面分轨只是入口治理，不等于正式插件化验收 |

## 七、当前唯一推进顺序

1. 执行 P1-2：在固定三仓 SHA 和固定镜像下跑短时真 GBPlanner 闭环，要求正常收尾、summary 完整、
   `ok=true`、真 RRG/voxblox/adapter 证据同时存在。
2. 短跑通过后跑正式 10/10；所有 attempts 入分母，禁止挑样本。
3. 10/10 通过后才运行长稳门。
4. P1 关闭后按 P2 -> P3 -> P4 推进。
