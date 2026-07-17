> **[CURRENT] 入口页。状态细节以 [CURRENT_STATUS.md](CURRENT_STATUS.md) 为唯一事实源,本页不另行维护一套状态。**

> **[R003 治理标记 · 2026-07-16]** 本页只作项目入口;一切状态以 [CURRENT_STATUS.md](CURRENT_STATUS.md)
> 为准(唯一入口),问题以 [台账](docs/world-model端到端Bug台账_给作者PR.md) 为准。本页下文中任何
> "已完成/全绿/资产全部直接复用"等表述若与 CURRENT_STATUS 冲突,一律以 CURRENT_STATUS 为准。

# GBPlanner → World-Model 集成

把 **GBPlanner**(DARPA 地下赛冠军队 CERBERUS 的 3D 自主探索规划器,ROS1)接入 **world-model**(ROS2 jazzy 无人机仿真平台),替换其占位探索策略 `frontier_lite`,并用同口径数据证明升级价值。

## 一、当前主线(2026-07-08):GBPlanner **ROS2 原生迁移**

> 🔄 **2026-07-07 晚·导师最高指示**:放弃 ROS1↔ROS2 桥接,把 GBPlanner **迁移到 ROS2 原生**(ROS1+ROS2 双栈过重)。
> 桥接线**冻结为 oracle 回归基准 + 科研叙事素材**(下方 §二 桥接期结论全部仍成立,不再演进);
> world-model 侧资产(EKF/探针修复、ROS2 适配器 `trajectory_to_intent`、lidar3d、评测口径)**规划为复用**(桥接期产物;在 ROS2 直连主线上逐项验证后方可称"已复用")。
> 权威蓝图:[docs/路线切换_ROS2迁移_2026-07-07.md](docs/路线切换_ROS2迁移_2026-07-07.md) + [docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md](docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md)。

目标架构(从"双栈过桥"改为"ROS2 直连"):

```text
Gazebo / world-model ROS2(/wm/cloud3d、/slam/odom、TF)
        ↓  (无桥,ROS2 原生订阅)
GBPlanner ROS2 原生节点(voxblox ROS2 + RRG/gain/collision)
        ↓  /gbp/trajectory(ROS2 MultiDOFJointTrajectory,frame=map)
trajectory_to_intent 适配器(桥接期资产,直接复用)
        ↓  /navlab/fcu/setpoint/intent
world-model FCU 控制链 / Gazebo
```

**迁移里程碑 M0–M5**:当前状态、证据等级、阻塞项**一律以 [CURRENT_STATUS.md](CURRENT_STATUS.md) §三为准**,
本页不复制里程碑进度(避免双事实源)。任务拆解与验收门见
[任务书](docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md)。

## 三、桥接阶段表(已冻结,历史证据 / oracle)

| 阶段 | 状态 |
|---|---|
| jazzy 9/9 镜像 + exploration 历史窄验收绿(07-06)+ 基线定档 | ✅(历史证据) |
| Stage1 GBPlanner ROS1 单侧复验 | ✅ |
| Stage2/2.5/2.6 薄桥 transport + 稳定性 + 消费闭环 | ✅ |
| Stage3/3.5 dry-run + 3D 数据链贯通 | ✅ |
| Stage4a/4b/4c FCU 消费直证 + 去混流可归因 | ✅ |
| Stage5a gate 机制(strategy=gbplanner 通过 exploration_probe) | ✅ |
| Stage5b 3D 行为对照(FOV ±30°→±5° 三层变化) | ✅ |
| Stage5c 首批 6 run + **基线修复后复档(公平对比 50% vs 0%)** | ✅ |
| v2 批跑(v5/kp0.45 证伪)+ 成功率战役:C/B 类探针预算根因全修 + 适配器 v6b | ✅ |
| **final2 = 修复链后再次 TASK_STATUS_OK 完整全绿**(最终口径批仅 3 样本,统计未定档) | ✅/🔵 |
| **GUI 三演示(阶段性可视化口径)**:gui_demo_master.sh + results_panel.html + 演示手册 | ✅ |
| ~~组会后:最终口径 full 批 + 基线复跑 + 桥接 PR~~ | ⛔ **已冻结**(路线切换,桥接不再演进) |
| **ROS2 原生迁移 M0-M5**(见 §一) | 🔵 **当前主线**,详见 [TASKS.md](TASKS.md) |

## 四、不能宣称的结论(桥接期诚实边界,仍适用于 oracle 引用)

1. **不能说"稳定全绿"**——全绿率首批 1/6,v5(PD)后的全绿率待 v2 批跑定档;
2. **不能说"完整 3D 飞行动作闭环"**——已完成的是低速 XY/Yaw 控制链、gate 机制与 3D 输入行为对照;z 由飞控高度环保持;
3. **不能说"3D 障碍物级对照已做"**——5b 是传感 FOV 对照(动官方迷宫会伤基线可比性,列为增强项);
4. **不能说"v5/PD 已提升全绿率"**——目前只有 wp 捕获 0→9 的有效性直证;
5. RViz **绿线=planner 候选路径,粉线=执行轨迹**(`/rmf_obelix/command/trajectory`,发布者 PCI)——桥只接粉线,颜色不作证据;
6. **不再追桥接 final 批跑 / 桥接 PR**——路线已切换,桥接冻结为 oracle;world-model 侧修复(EKF/探针)的 PR 物料等 ROS2 迁移联跑后再统一定稿;
7. 汇报必须区分三类实验:①原始 GBPlanner 复现(预研B)②原始 world-model/frontier_lite 基线(全绿复现+修复后 0/6)③**融合后 GBPlanner-in-world-model**(3D 链/消费链/归因/gate/公平对比)——不混写。

## 五、当前入口(新窗口只看这 5 个)

| 文件 | 作用 |
|---|---|
| [CURRENT_STATUS.md](CURRENT_STATUS.md) | **唯一事实源**:阶段/证据/卡点/纪律 |
| [TASKS.md](TASKS.md) | 任务表(ROS2 迁移 M0-M5) |
| [接力棒_当前值班.md](接力棒_当前值班.md) | 值班交接 |
| [docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md](docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md) | **当前主线任务书**(M0-M5 拆解/voxblox 风险/验收) |
| [文档索引.md](文档索引.md) | 全部文档带状态标签的索引 |

> 桥接技术主文档 [docs/桥接查证与执行计划_2026-07-06.md](docs/archive/桥接查证与执行计划_2026-07-06.md) 已降级为 **REFERENCE / HISTORICAL**(oracle 与历史证据,不再作为施工入口)。

复现命令:`bash runbooks/world-model-jazzy/clean_repro.sh`(**历史基线复现**:重现 07-06 桥接期窄验收绿,非当前平台稳定结论)· `runbooks/world-model-jazzy/stage5c_run.sh <n>`(融合联跑一键)· `runbooks/gbplanner_ref/run_light.sh`(GBPlanner 单侧)· 证据全在 `runbooks/world-model-jazzy/*_evidence.txt`。

## 六、历史阶段(已完成,仅背景资料,入口见 [docs/archive/](docs/archive/))

- **预研 A**(world-model 复现与全绿):35 轮排障实录、humble 运行时记录、构建排错 → `docs/archive/`;Bug 修复链事实源 → [Bug 台账](docs/world-model端到端Bug台账_给作者PR.md)(B1~B16 + EKF 参考系修复,PR 素材)
- **预研 B**(GBPlanner 官方仿真复现):291.3m 自主探索+13 万体素建图实测 → [预研B_复现GBPlanner](docs/archive/预研B_复现GBPlanner.md)
- **科普/参考**:[术语表·科研小白版](docs/术语表_科研小白版.md)、[论文↔代码对应](docs/GBPlanner原始论文与代码对应关系.md)、[体积增益与RViz详解](docs/archive/体积增益与RViz界面详解.md)、[算法核心演示](docs/archive/算法核心演示_体积增益选路.md)
- **旧方案(已判死/已取代)**:官方 ros1_bridge、zenoh 双桥、gbplanner_core 重写路线 → `docs/archive/OBSOLETE_*`
- 旧版全景蓝图 README(科普+名词表+历史叙事)→ [docs/archive/README_历史全景蓝图_2026-07-06.md](docs/archive/README_历史全景蓝图_2026-07-06.md)
