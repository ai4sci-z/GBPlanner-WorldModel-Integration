# GBPlanner → World-Model 集成项目

> 把 **GBPlanner 自主探索算法** 加入 **world-model 仿真平台**,替换其占位探索策略。
> 本文 = 项目**蓝图 + 全景理解 + 集成方案 + 进展日志**,面向"看懂 + 做报告"。最后更新:2026-06-29。

---

# 第 0 部分 · 蓝图速览(一页看懂)

**我们在做什么:** 给一个无人机仿真平台(world-model)换上一个更聪明的"自主探索大脑"(GBPlanner)。

**为什么:** world-model 现在的探索功能是个**临时凑数的简易版**(代号 `frontier_lite`),只能在 2D 地图上凑几个目标点。GBPlanner 是学术界成熟的 **3D 体积增益探索算法**(来自 DARPA 地下挑战赛冠军队 CERBERUS),能真正"算出哪条路看见的未知空间最多"。

**怎么换(关键认知):** world-model 的探索模块,本质是"往几个固定 ROS 话题发目标点/路径"。**集成 = 写一个 GBPlanner 模块,产出目标点/路径,发到同一组话题,把简易版顶替掉。插口不变,只换大脑。**

**整体路线:**
| 阶段 | 名称 | 内容 | 状态 |
|---|---|---|---|
| P0-A | 复现 world-model | 跑通平台,看占位探索怎么工作 | 🔵 已读懂源码,待实跑 |
| P0-B | 复现 GBPlanner | 单独跑官方算法,看它怎么探索 | ⚪ 环境已备,待跑 |
| P1 | 抽核心库 | 把算法抽成不依赖框架的 C++ 核心 + 单测 | ⚪ 未开始 |
| P2 | ROS2 节点 | 把核心包成 ROS2 模块,接 world-model 数据 | ⚪ 未开始 |
| P3 | 编排集成 | 替换 frontier_lite,通过现有验收闸门 | ⚪ 未开始 |

**当前状态:** 全景调研完成;开发环境(WSL2+Docker+工具链)已搭好并验证;仓库已克隆;**尚未写集成代码**。

---

# 第 1 部分 · 全景理解(报告用)

## 1.1 world-model 是什么

⚠️ **先破除一个误会**:维护者本人说,"world-model" **不是**具身智能领域的"世界模型(world model)",只是他给这个任务随手起的名字,**没用到任何世界模型技术**。

它实际是:**一个面向室内、无 GPS 环境的无人机"仿真 + 编排"平台**。把它想象成一个"无人机实验台总控":

| 组成 | 技术 | 作用(大白话) |
|---|---|---|
| 仿真器 | **Gazebo**(headless) | 造一个虚拟世界,让虚拟无人机在里面飞 |
| 飞控 | **ArduPilot SITL** | 软件模拟的真实飞控,控制无人机姿态/油门 |
| 建图定位 | **Cartographer(2D)** | 无人机靠 2D 激光雷达边飞边画地图、算自己在哪 |
| 总调度 | **Go** 程序(`navlab-sim`) | 决定启动哪些容器、跑哪个任务、收集结果 |
| 通信契约 | **Protobuf** | 让 Go/Rust/Python 各模块用统一格式对话 |
| 打包 | **Docker** | 每个部件装进容器,一键复现 |
| 通信框架 | **ROS2**(Humble/Jazzy) | 机器人界的"消息总线",各模块发/收话题 |

它内置 **5 个仿真任务**:`exploration`(探索)、`hover`(悬停)、`navigation`(Nav2 导航)、`hover-slam-only`、`scan-robustness`。**我们只动 `exploration` 这一个。**

**exploration 现状(占位 frontier_lite):** 一个轻量 Python 工作流,用 Cartographer 的 **2D 地图**找边界(frontier),以 0.1 m/s、26 秒、凑 ≥3 个目标点的方式驱动无人机,只为证明"探索流水线通了"——**不是真正的探索算法**。这就是我们要替换的对象。

## 1.2 GBPlanner 是什么

**论文:** CERBERUS(arXiv:2201.07067),DARPA 地下挑战赛。**官方代码:** `ntnu-arl/gbplanner_ros`(分支 `gbplanner2`)。

**它怎么工作(大白话):**
1. 无人机靠 3D 雷达边飞边建一张 **3D 占据地图**(每个小方块=已占据/空闲/**未知** 三选一)。
2. 在身边随机撒点,连成一张"候选路线图"(RRG 随机图)。
3. 对每条候选路线,用**光线投射**模拟"站在那能看见多少未知方块"——这就是**体积增益(VolumeGain)**。
4. 减去"绕远的距离惩罚 + 转向惩罚",**选增益最高且不撞墙的路**。
5. 身边都探完了,就去全局地图找没探的**边界(frontier)**。
6. 输出一串**目标航点**。

**技术事实(集成时要对接的):**
- 形态:**ROS1**(catkin/Noetic),地图库是 **voxblox**(3D 体素),输入 3D 点云 + 里程计,经 **PCI** 控制接口输出航点。

## 1.3 三道"错配"(集成的真正难点)

| # | 错配 | 通俗解释 | 对策 |
|---|---|---|---|
| 1 | **ROS1 ↔ ROS2** | 算法是老框架,项目是新框架,语言不通 | 把算法抽成"不依赖框架的核心",再用 ROS2 重新包一层 |
| 2 | **地图库 voxblox 只有 ROS1** | 算法自带的建图工具搬不到新框架 | 换成 ROS2 能用的建图(octomap_server2 或 GPU 版 nvblox) |
| 3 | **传感器/控制器不同** | 项目仿真无人机只有 2D 雷达;算法要 3D。算法原版用 RotorS 控制器,项目用 ArduPilot | 给仿真无人机加 3D 雷达;航点改走 ArduPilot |

> **这三点就是报告里"为什么这事不是简单复制粘贴"的核心论据。**

---

# 第 2 部分 · 集成方案蓝图

## 2.1 接口契约(已从源码精确提取)

frontier_lite(要替换的)发布到这组话题,GBPlanner **替换后发到同一组即可**:
- `/navlab/exploration/goal`(目标点)、`/path`(路径)、`/frontiers`(边界)、`/status`(状态,验收闸门读它)、`/coverage`、`/markers`
- 控制链:`/navlab/fcu/setpoint/intent` → `/output` → ArduPilot 飞控

**验收闸门**(Go 的 `gate_evaluation.go`)只看结果指标:accepted_goals≥3、path_length≥0.35m、coverage_growth 等。**GBPlanner 只要驱动 ≥3 个目标、有覆盖增长,就算通过。**

## 2.2 分层设计

```
[3D 雷达(需给仿真无人机加)] → [里程计+点云]
   → [ROS2 3D 建图: octomap_server2 / nvblox]   ← 替代 voxblox
      → gbplanner_core(纯 C++,无框架:RRG采样 / 光线投射 / 体积增益)
         → ROS2 节点:发 /navlab/exploration/*  → ArduPilot 飞
```
- **核心层 `gbplanner_core`**:纯算法,不绑定 ROS、不绑定 voxblox(靠抽象接口 `VoxelMapInterface`/`TraversabilityInterface`)。
- **适配层**:ROS2 节点,把核心接到 world-model 的数据和话题上。

## 2.3 交付物清单(最终要产出的)
gbplanner_core 库 + 抽象接口 + ROS2 节点 + 3D 建图前端 + 给仿真无人机加 3D 传感器 + Docker 镜像 + exploration.yaml 改 strategy + 离线 demo/单测 + 通过 exploration 闸门的集成测试。

---

# 第 3 部分 · 进展日志(每一步:做了什么 / 为什么 / 影响 / 报告怎么讲)

## 步骤 1 · 全景调研(源码级)
- **做了什么:** 深挖 world-model 与 GBPlanner 两个仓库的源码,确认技术栈、数据流、接口、三道错配。
- **为什么:** "看懂再动手"——不摸清就写代码必返工。
- **对项目影响:** 得到精确集成契约(见第 2 部分),把"无从下手"变成"有蓝图"。
- **报告怎么讲:** "我们先做了完整技术调研,确认 world-model 是 ROS2 仿真平台、GBPlanner 是 ROS1 算法,识别出三道集成鸿沟。"
- **产物:** [施工手册](GBPlanner集成施工手册.md)、[notes/exploration集成接口](notes/exploration集成接口_frontier_lite.md)。

## 步骤 2 · 开发环境搭建(已验证)
- **做了什么:** 在这台新电脑从零配好开发环境(下表),并克隆项目仓库。
- **为什么:** GBPlanner/ROS 必须 Linux;项目用 ROS2 Humble→对应 Ubuntu 22.04;全程 Docker。
- **对项目影响:** 具备了"能跑能编译"的底座。
- **报告怎么讲:** "搭建了 WSL2 + Docker + ROS2 工具链开发环境,并成功克隆与启动项目编排器。"

| 层 | 装了什么 | 验证 |
|---|---|---|
| Windows | Python3.12 / uv / Node / gh / pandoc + VS Code 扩展 | ✅ |
| WSL2 | Ubuntu 22.04.5(用户 ai4s) | ✅ |
| Docker | 29.6.1 + Compose(配了代理) | ✅ `Hello from Docker!` |
| 工具链 | gcc/g++11、cmake3.22、**Go 1.24** | ✅ |
| 仓库 | `~/ws/world-model` 已克隆 | ✅ |

**关键结果(可截图放报告):**
```
$ go run ./cmd/navlab-sim list-tasks
exploration   sim   Official-maze exploration gate over Gazebo/SITL.   ← 我们要改的
hover / hover-slam-only / navigation(Nav2) / scan-robustness
$ go run ./cmd/navlab-sim doctor
OK config loaded / OK task registry / backend=docker / task_count=5
```
- **遇到并解决的坑(报告加分项,体现工程能力):**
  1. Windows 自带的 python 是商店占位,装了真 Python 3.12。
  2. apt 的 Go 是 1.18 太老,项目要 1.24 → 手动装 Go 1.24。
  3. **Docker 守护进程不走 shell 代理** → 单独给 dockerd 配代理,才能拉镜像。
  4. WSL 代理未镜像 → 开 WSL 镜像网络模式。
- **产物:** [环境搭建 runbook](runbooks/01_环境搭建_WSL2_Docker_P0.md)、[环境就绪状态](notes/环境就绪状态_2026-06-29.md)。

## 步骤 3 · 读懂占位探索 frontier_lite
- **做了什么:** 读源码确认 frontier_lite 是 2D 简易探索 + 提取了 GBPlanner 接入的精确话题契约。
- **报告怎么讲:** "明确了被替换对象的行为与接口,得到 GBPlanner 的精确接入点。"
- **产物:** [exploration 集成接口](notes/exploration集成接口_frontier_lite.md)。

---

# 第 4 部分 · 预研 A / B(待执行,做完单独出 md)
- **预研 A = 复现 world-model**:构建镜像、实跑 exploration,亲眼看占位探索。⚠️ 成本大(1–2 小时构建),动手前会先征求你同意。完成后出 `docs/预研A_复现worldmodel.md`。
- **预研 B = 复现 GBPlanner**:用一键 Dockerfile 跑官方 rmf_sim,看算法行为。完成后出 `docs/预研B_复现gbplanner.md`。

---

# 第 5 部分 · 名词表(报告备查)
- **GBPlanner**:图搜索体积增益自主探索算法(CERBERUS/DARPA)。
- **world-model**:本项目的无人机仿真编排平台(名字与"世界模型"无关)。
- **frontier_lite**:world-model 现有的占位探索策略(被替换对象)。
- **ROS1/ROS2**:机器人操作系统(消息总线框架),两代不直接互通。
- **voxblox / octomap / nvblox**:把点云变成 3D 占据地图的建图库。
- **体积增益(VolumeGain)**:一条路能"看见"的未知空间体积,GBPlanner 选路依据。
- **frontier(边界)**:已知与未知区域的交界,全局探索目标。
- **SITL**:软件在环,纯软件模拟的飞控。
- **WSL2 / Docker**:Windows 上跑 Linux / 容器化打包,本项目开发底座。

---

## 目录结构
```
GBPlanner-WorldModel-Integration/   ← 项目根(git 仓库 → GitHub)
├─ README.md                         本文件:蓝图+全景+集成+进展(报告主材料)
├─ GBPlanner集成施工手册.md            技术施工手册(命令/接口/风险)
├─ docs/                             集成手册 docx + 预研 A/B 报告(后续)
├─ runbooks/                         环境搭建、GBPlanner 参考环境 Dockerfile
├─ notes/                            调研笔记(环境就绪、exploration 接口)
└─ images/                           截图(报告配图)
```
> Desktop 上有一份本文件的同步副本 `GBPlanner项目_蓝图与进展.md` 方便阅读。代码后续放 WSL `~/ws`。
