> **[CURRENT] 入口页。状态细节以 [CURRENT_STATUS.md](CURRENT_STATUS.md) 为唯一事实源,本页不另行维护一套状态。**

# GBPlanner → World-Model 集成

把 **GBPlanner**(DARPA 地下赛冠军队 CERBERUS 的 3D 自主探索规划器,ROS1)接入 **world-model**(ROS2 jazzy 无人机仿真平台),替换其占位探索策略 `frontier_lite`,并用同口径数据证明升级价值。

## 一、当前状态(2026-07-06 深夜)

- world-model jazzy **exploration 已端到端全绿**(run `20260706T130626`,无参数 hack,B1~B16 修复链);
- **frontier_lite 基线已定档**:6 run 达标率 40%,path 方差 0.43~3.80m——占位策略缺陷的量化铁证;
- **B2.5 自写薄桥**(官方 ros1_bridge 与 zenoh 均实验判死)transport 三段通;
- **纯 planner 栈消费 /wm/\* 闭环已打通**(GBPlanner/voxblox 真消费过桥输入并出轨迹);
- **Stage3 dry-run 已 PASS**(轨迹→速度意图跟踪量自洽,零发布);
- **Stage3.5 3D 数据链已贯通**(world-model 真 odom+真 3D 点云 → voxblox 3D 体素地图 90,472 点 zspan=13.2m → trajectory 回流);
- **当前施工点 = Stage4 低速 FCU intent**(限速/kill/hold/status);
- 未完成:Stage4、Stage5 gate 对齐+同口径对比(含 3D 对照强化)、GUI 三演示。

## 二、阶段表

| 阶段 | 状态 |
|---|---|
| jazzy 9/9 镜像 + exploration 全绿 + 基线定档 | ✅ |
| Stage1 GBPlanner ROS1 单侧复验 | ✅ |
| Stage2/2.5 薄桥 transport + TCP 稳定性 | ✅ |
| Stage2.6 纯 planner 栈消费 /wm/\* 闭环(2D 冒烟输入) | ✅ |
| Stage3 trajectory dry-run(零发布) | ✅ |
| Stage3.5 3D 数据链贯通(voxblox 3D 体素 zspan 13.2m) | ✅ |
| **Stage4 低速 FCU intent(限速/kill/hold/status)** | 🔵 **当前** |
| Stage5 exploration gate 对齐 + 同口径对比(含 3D 对照强化) | ⬜ |
| GUI 三演示(①原版GBPlanner ②frontier_lite ③接入后) | ⬜ |

## 三、不能宣称的结论

1. 不能说"完整 GBPlanner 已集成完成"(Stage4/5 未做);
2. 不能说"已实现 3D 探索"(3D 对照未完成;Stage2.6 输入是 z=0 冒烟);
3. RViz **绿线=planner 候选路径,粉线=执行轨迹**(`/rmf_obelix/command/trajectory`,发布者 PCI)——桥只接粉线;
4. **PR/Issue 禁止提交**(用户指示:等真 GBPlanner 集成跑通后统一定稿);
5. exploration gate 不需要 coverage_growth(源码实证)。

## 四、当前入口(新人只看这 5 个)

| 文件 | 作用 |
|---|---|
| [CURRENT_STATUS.md](CURRENT_STATUS.md) | **唯一事实源**:阶段/证据/卡点/纪律 |
| [TASKS.md](TASKS.md) | 任务表 |
| [接力棒_当前值班.md](接力棒_当前值班.md) | 双 agent 协作锁 |
| [docs/桥接查证与执行计划_2026-07-06.md](docs/桥接查证与执行计划_2026-07-06.md) | 桥接技术主文档(查证/架构/分阶段验收) |
| [文档索引.md](文档索引.md) | 全部文档带状态标签的索引 |

复现命令:`bash runbooks/world-model-jazzy/clean_repro.sh`(world-model 全绿)· `runbooks/gbplanner_ref/run_light.sh`(GBPlanner 单侧)· 证据全在 `runbooks/world-model-jazzy/stage*_evidence.txt`。

## 五、历史阶段(已完成,仅背景资料,入口见 [docs/archive/](docs/archive/))

- **预研 A**(world-model 复现与全绿):35 轮排障实录、humble 运行时记录、构建排错 → `docs/archive/`;Bug 修复链事实源 → [Bug 台账](docs/world-model端到端Bug台账_给作者PR.md)(B1~B16,PR 素材)
- **预研 B**(GBPlanner 官方仿真复现):291.3m 自主探索+13 万体素建图实测 → [预研B_复现GBPlanner](docs/预研B_复现GBPlanner.md)
- **科普/参考**:[术语表·科研小白版](docs/术语表_科研小白版.md)、[论文↔代码对应](docs/GBPlanner原始论文与代码对应关系.md)、[体积增益与RViz详解](docs/体积增益与RViz界面详解.md)、[算法核心演示](docs/算法核心演示_体积增益选路.md)
- **旧方案(已判死/已取代)**:官方 ros1_bridge、zenoh 双桥、gbplanner_core 重写路线 → `docs/archive/OBSOLETE_*`
- 旧版全景蓝图 README(科普+名词表+历史叙事)→ [docs/archive/README_历史全景蓝图_2026-07-06.md](docs/archive/README_历史全景蓝图_2026-07-06.md)
