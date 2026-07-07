> **[CURRENT] 入口页。状态细节以 [CURRENT_STATUS.md](CURRENT_STATUS.md) 为唯一事实源,本页不另行维护一套状态。**

# GBPlanner → World-Model 集成

把 **GBPlanner**(DARPA 地下赛冠军队 CERBERUS 的 3D 自主探索规划器,ROS1)接入 **world-model**(ROS2 jazzy 无人机仿真平台),替换其占位探索策略 `frontier_lite`,并用同口径数据证明升级价值。

## 一、当前主线(2026-07-08):GBPlanner **ROS2 原生迁移**

> 🔄 **2026-07-07 晚·导师最高指示**:放弃 ROS1↔ROS2 桥接,把 GBPlanner **迁移到 ROS2 原生**(ROS1+ROS2 双栈过重)。
> 桥接线**冻结为 oracle 回归基准 + 科研叙事素材**(下方 §二 桥接期结论全部仍成立,不再演进);
> world-model 侧资产(EKF/探针修复、ROS2 适配器 `trajectory_to_intent`、lidar3d、评测口径)**全部直接复用**。
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

**迁移里程碑**(拆解与验收见任务书):

| 里程碑 | 内容 | 状态 |
|---|---|---|
| **M0** | 侦察 + 路线冻结 + 入口文档收口 | ✅(07-08 收口) |
| **M1** | `planner_msgs` ROS2 最小消息包(colcon build 通过) | ✅(07-08,分支 `feat/gbplanner-ros2-port`,证据 runbooks/ros2_port/) |
| M2 | voxblox ROS2 后端(与 ROS1 oracle 对拍 voxel/ESDF/gain) | ⬜ **当前** |
| M3 | 算法核心 ROS-free 剥离(rrg/planner_common) | ⬜ |
| M4 | ROS2 planner 节点壳(订 odom/cloud → 出 /gbp/trajectory,RViz2 可见) | ⬜ |
| M5 | world-model 直连联跑 + oracle 回归 + 同口径公平对比 | ⬜ |

> 最大技术风险 = **voxblox 地图后端**(gain/碰撞语义变则 GBPlanner 行为变):第一版沿用 voxblox core(snt-arg minimal 底座 + Jazzy 适配),**不用 nvblox**,用 ROS1 原版做逐体素对拍。

## 二、桥接阶段(已冻结,作为 oracle 与阶段性证据)

> 桥接阶段已完成使命:**证明 GBPlanner 接入 world-model 有探索增益,并暴露双 ROS 栈维护成本**;结论冻结为迁移 oracle,不再追桥接 final 批跑 / thinbridge 稳定性 / ROS1 RViz / 桥接 PR。以下为已坐实的桥接期成果(不夸大):

**桥接式融合**(B2.5 自写薄桥)—— ROS1 原版 GBPlanner 通过自写 TCP 薄桥接入 ROS2 world-model,链路每段都有证据文件:

```text
world-model 3D lidar(lidar3d 净增量)/ odom
        ↓  ROS2 → ROS1 自写 TCP 薄桥(官方 ros1_bridge 与 zenoh 均实验判死)
GBPlanner / voxblox 3D 建图 / trajectory 规划
        ↓  ROS1 → ROS2 薄桥回流(/gbp/trajectory,只接 PCI 执行轨迹)
trajectory_to_intent 适配器(fail-closed + Procrustes 坐标对齐 + PD + 诚实计数)
        ↓
world-model FCU intent / cmd_vel(GBP-SIGNATURE 逐位吻合)
        ↓
飞机实际 odom 运动(去混流可归因)+ exploration gate(以 strategy=gbplanner 通过)
```

**三大鸿沟逐项定性**(诚实边界,勿夸大)——这些正是 ROS2 迁移要从根上消除的:

| 鸿沟 | 桥接期状态 | 证据 | ROS2 迁移如何消除 |
|---|---|---|---|
| ROS1 GBPlanner ↔ ROS2 world-model | 桥接式打通 | B2.5 薄桥;odom/3D 点云/trajectory 全过桥(stage2~3.5) | **M1-M4 原生 ROS2 节点,无桥** |
| 2D 雷达平台 ↔ GBPlanner 需要 3D | 已做一版 | 独立 lidar3d 净增量;voxblox TSDF zspan 13.2m;5b FOV 对照证明行为随 3D 输入变化 | M2 voxblox ROS2 直接消费 /wm/cloud3d |
| trajectory ↔ FCU 控制接口 | 已适配并可归因 | 适配器消费 /gbp/trajectory;cmd_vel 签名;4c 去混流归因;5a gate 通过 | M5 沿用同一适配器(**此资产迁移后复用**) |

**桥接期已坐实的核心数字**(冻结为 oracle,汇报可引):

- **Stage2~5 主链全有实证**:transport→消费闭环→dry-run→3D 数据链→FCU 消费直证→4c 去混流可归因 PASS→5a gate 机制 PASS(3 次重现)→5b 3D 行为对照成立→5c 6 run 定档;
- **runA = GBPlanner 策略下首个 TASK_STATUS_OK 完整全绿 run**(零探针失败);
- **🏆 公平对比定档(同 EKF 修复、同环境、同窗口口径)**:GBPlanner gate 达标 **3/6=50% vs frontier_lite 0/6=0%**——基线 accepted 恒=2(窗口结构性失败),修复前 2/6 全绿实为 EKF 跑飞"馈赠";我方 accepted=真实运动到达,口径更严;
- 路上根治 **world-model 上游 EKF 参考系真 bug**(罗盘 yaw vs SLAM 位置差 δ→运动即发散跑飞;修复入 clean 分支 99bcfa1,BIN 验尸全程留痕)——此修复 world-model 侧**迁移后继续受益**。

## 三、桥接阶段表(已冻结,历史证据 / oracle)

| 阶段 | 状态 |
|---|---|
| jazzy 9/9 镜像 + exploration 全绿 + 基线定档 | ✅ |
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

> 桥接技术主文档 [docs/桥接查证与执行计划_2026-07-06.md](docs/桥接查证与执行计划_2026-07-06.md) 已降级为 **REFERENCE / HISTORICAL**(oracle 与历史证据,不再作为施工入口)。

复现命令:`bash runbooks/world-model-jazzy/clean_repro.sh`(world-model 全绿)· `runbooks/world-model-jazzy/stage5c_run.sh <n>`(融合联跑一键)· `runbooks/gbplanner_ref/run_light.sh`(GBPlanner 单侧)· 证据全在 `runbooks/world-model-jazzy/*_evidence.txt`。

## 六、历史阶段(已完成,仅背景资料,入口见 [docs/archive/](docs/archive/))

- **预研 A**(world-model 复现与全绿):35 轮排障实录、humble 运行时记录、构建排错 → `docs/archive/`;Bug 修复链事实源 → [Bug 台账](docs/world-model端到端Bug台账_给作者PR.md)(B1~B16 + EKF 参考系修复,PR 素材)
- **预研 B**(GBPlanner 官方仿真复现):291.3m 自主探索+13 万体素建图实测 → [预研B_复现GBPlanner](docs/预研B_复现GBPlanner.md)
- **科普/参考**:[术语表·科研小白版](docs/术语表_科研小白版.md)、[论文↔代码对应](docs/GBPlanner原始论文与代码对应关系.md)、[体积增益与RViz详解](docs/体积增益与RViz界面详解.md)、[算法核心演示](docs/算法核心演示_体积增益选路.md)
- **旧方案(已判死/已取代)**:官方 ros1_bridge、zenoh 双桥、gbplanner_core 重写路线 → `docs/archive/OBSOLETE_*`
- 旧版全景蓝图 README(科普+名词表+历史叙事)→ [docs/archive/README_历史全景蓝图_2026-07-06.md](docs/archive/README_历史全景蓝图_2026-07-06.md)
