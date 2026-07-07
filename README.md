> **[CURRENT] 入口页。状态细节以 [CURRENT_STATUS.md](CURRENT_STATUS.md) 为唯一事实源,本页不另行维护一套状态。**

# GBPlanner → World-Model 集成

把 **GBPlanner**(DARPA 地下赛冠军队 CERBERUS 的 3D 自主探索规划器,ROS1)接入 **world-model**(ROS2 jazzy 无人机仿真平台),替换其占位探索策略 `frontier_lite`,并用同口径数据证明升级价值。

## 一、这个项目到底做成了什么(2026-07-07)

**这不是"原始 GBPlanner 和原始 world-model 各跑各的对比实验",融合确实做了,主链已打通并有全程实证。** 准确定名:

> **GBPlanner-in-world-model 的桥接式融合**——ROS1 原版 GBPlanner 通过自写薄桥(B2.5)接入 ROS2 world-model,在 world-model 仿真里形成 3D 数据链、规划链、控制消费链、去混流运动归因、gate 机制通过与公平对比。**不是 ROS2 原生移植**(联网复核:官方无 ROS2 版 GBPlanner)。

融合链路(每一段都有证据文件,非方案想象):

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

**三大鸿沟逐项定性**(诚实边界,勿夸大):

| 鸿沟 | 状态 | 证据 | 不能夸大的边界 |
|---|---|---|---|
| ROS1 GBPlanner ↔ ROS2 world-model | **已打通** | B2.5 薄桥;odom/3D 点云/trajectory 全过桥(stage2~3.5) | 桥接式融合,**不是 ROS2 原生移植** |
| 2D 雷达平台 ↔ GBPlanner 需要 3D | **已做一版** | 独立 lidar3d 净增量;voxblox TSDF zspan 13.2m;5b FOV 对照证明行为随 3D 输入变化 | 3D 体现在感知/建图/规划行为,**尚未证明完整 z 方向飞行动作闭环** |
| trajectory ↔ FCU 控制接口 | **已适配并可归因** | 适配器消费 /gbp/trajectory;cmd_vel 签名;4c 去混流归因;5a gate 通过 | trajectory→intent 是工程适配,**不是无损轨迹执行**;控制仍是低速 XY/Yaw |

## 二、当前状态与核心数字

- **Stage2~5 主链全有实证**:transport→消费闭环→dry-run→3D 数据链→FCU 消费直证→**4c 去混流可归因 PASS**→**5a gate 机制 PASS(3 次重现)**→**5b 3D 行为对照成立**→**5c 首批 6 run 定档**;
- **runA = GBPlanner 策略下首个 TASK_STATUS_OK 完整全绿 run**(零探针失败);
- **🏆 公平对比定档(同 EKF 修复、同环境、同窗口口径)**:
  **GBPlanner gate 达标 3/6=50% vs frontier_lite 0/6=0%**——修复后基线 accepted 恒=2(零方差,窗口结构性失败);修复前基线的 2/6 全绿被证实是 EKF 跑飞"馈赠";且 GBPlanner 的 accepted=真实运动到达(预到达剔除),口径更严;
- 路上根治 **world-model 上游 EKF 参考系真 bug**(罗盘 yaw vs SLAM 位置差 δ→运动即发散跑飞;修复 3 件套入 clean 分支 99bcfa1,BIN 验尸全程留痕);
- **当前施工点 = GBPlanner v2 系统性批跑(v5/PD 适配器的全绿率)→ GUI 三演示 → PR 统一定稿**。

## 三、阶段表

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
| 适配器 v5(PD 阻尼,wp 捕获 0→9 直证) | ✅ 有效性直证 |
| **v2 系统性批跑(v5 后全绿率)** | 🔵 **当前** |
| GUI 三演示(①原版GBPlanner ②frontier_lite ③接入后)+ PR 定稿 | ⬜ |

## 四、不能宣称的结论

1. **不能说"稳定全绿"**——全绿率首批 1/6,v5(PD)后的全绿率待 v2 批跑定档;
2. **不能说"完整 3D 飞行动作闭环"**——已完成的是低速 XY/Yaw 控制链、gate 机制与 3D 输入行为对照;z 由飞控高度环保持;
3. **不能说"3D 障碍物级对照已做"**——5b 是传感 FOV 对照(动官方迷宫会伤基线可比性,列为增强项);
4. **不能说"v5/PD 已提升全绿率"**——目前只有 wp 捕获 0→9 的有效性直证;
5. RViz **绿线=planner 候选路径,粉线=执行轨迹**(`/rmf_obelix/command/trajectory`,发布者 PCI)——桥只接粉线,颜色不作证据;
6. **PR/Issue 暂缓提交**(等 v2 结果与文档口径收口后统一定稿);
7. 汇报必须区分三类实验:①原始 GBPlanner 复现(预研B)②原始 world-model/frontier_lite 基线(全绿复现+修复后 0/6)③**融合后 GBPlanner-in-world-model**(3D 链/消费链/归因/gate/公平对比)——不混写。

## 五、当前入口(新人只看这 5 个)

| 文件 | 作用 |
|---|---|
| [CURRENT_STATUS.md](CURRENT_STATUS.md) | **唯一事实源**:阶段/证据/卡点/纪律 |
| [TASKS.md](TASKS.md) | 任务表 |
| [接力棒_当前值班.md](接力棒_当前值班.md) | 值班交接 |
| [docs/桥接查证与执行计划_2026-07-06.md](docs/桥接查证与执行计划_2026-07-06.md) | 桥接技术主文档(架构/分阶段验收/ROS2 复核) |
| [文档索引.md](文档索引.md) | 全部文档带状态标签的索引 |

复现命令:`bash runbooks/world-model-jazzy/clean_repro.sh`(world-model 全绿)· `runbooks/world-model-jazzy/stage5c_run.sh <n>`(融合联跑一键)· `runbooks/gbplanner_ref/run_light.sh`(GBPlanner 单侧)· 证据全在 `runbooks/world-model-jazzy/*_evidence.txt`。

## 六、历史阶段(已完成,仅背景资料,入口见 [docs/archive/](docs/archive/))

- **预研 A**(world-model 复现与全绿):35 轮排障实录、humble 运行时记录、构建排错 → `docs/archive/`;Bug 修复链事实源 → [Bug 台账](docs/world-model端到端Bug台账_给作者PR.md)(B1~B16 + EKF 参考系修复,PR 素材)
- **预研 B**(GBPlanner 官方仿真复现):291.3m 自主探索+13 万体素建图实测 → [预研B_复现GBPlanner](docs/预研B_复现GBPlanner.md)
- **科普/参考**:[术语表·科研小白版](docs/术语表_科研小白版.md)、[论文↔代码对应](docs/GBPlanner原始论文与代码对应关系.md)、[体积增益与RViz详解](docs/体积增益与RViz界面详解.md)、[算法核心演示](docs/算法核心演示_体积增益选路.md)
- **旧方案(已判死/已取代)**:官方 ros1_bridge、zenoh 双桥、gbplanner_core 重写路线 → `docs/archive/OBSOLETE_*`
- 旧版全景蓝图 README(科普+名词表+历史叙事)→ [docs/archive/README_历史全景蓝图_2026-07-06.md](docs/archive/README_历史全景蓝图_2026-07-06.md)
