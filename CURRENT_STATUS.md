> **[CURRENT] 本文件是全项目唯一当前事实源。其他文档与本文冲突时,以本文为准。**
> 维护规则:每完成/失败一个阶段就更新本文;README 只引用本文,不另行维护状态。

# CURRENT_STATUS(最后更新:2026-07-06 深夜)

## 一、当前一句话状态

> world-model jazzy exploration 已端到端全绿;frontier_lite 基线已定档(达标率 40%);
> B2.5 自写薄桥 transport 三段通;纯 planner 栈消费 /wm/\* 闭环已打通(2D 冒烟输入);
> Stage3 trajectory dry-run 已 PASS(零发布,跟踪量自洽);
> **当前施工点 = 3D lidar 接入**(lidar3d 净增量补丁已应用,z 分布实证进行中);
> 3D 对照、低速 FCU(Stage4)、exploration gate 对齐(Stage5)尚未完成。

## 二、阶段表(全部有证据文件)

| 阶段 | 状态 | 证据 |
|---|---|---|
| 前置·jazzy 9/9 镜像 | ✅ | docker images 验真 |
| 前置·exploration 端到端全绿(B1~B16 修复链,无 hack) | ✅ | run `20260706T130626`;clean 分支 4 commit;净 diff 286 行 |
| Stage0 frontier_lite 基线定档 | ✅ | [基线定档](docs/基线定档_frontier_lite_2026-07-06.md):6 run,全绿 2/6,达标率 40%,根因=启动耗时蚕食 26s 窗口 |
| Stage1 GBPlanner ROS1 单侧复验 | ✅ | stage1_evidence:自主移动+trajectory+frames 实测 |
| Stage2 薄桥 transport 三段 | ✅ | stage2e/2j:odom✅ cloud✅ trajectory✅(rclpy 订阅口径) |
| Stage2.5 TCP 稳定性 | ✅ | stage2k:心跳后零断连;acceptor 线程死亡 bug 修复 |
| Stage2.6 纯 planner 栈消费 /wm/\* 闭环 | ✅ | stage26_evidence:订阅关系+voxblox 2.303Hz+19 条 trajectory。**边界:输入是 2D 冒烟(z=0),非 3D** |
| Stage3 trajectory dry-run(零发布) | ✅ | stage3_evidence:37 条 DRY 跟踪量数学自洽(首跑曾 FAIL=PCI 状态机挂起,fresh 时序后 PASS) |
| **Stage3.5 3D lidar 接入(当前)** | 🔵 **点云源已实证 3D** | lidar3d 净增量补丁(overlay+bridge,SLAM 链零触碰);实证:`/wm/cloud3d` **10800 点(360×30),z∈[-0.334,+2.969] 跨度 3.3m,zstd=0.593 → 3D**(stage3d_evidence)。剩:薄桥 PointCloud2 直通 → GBPlanner 联跑(voxblox 3D 体素+trajectory z 变化+随输入变化对照) |
| Stage4 低速 FCU intent(限速/kill/hold) | ⬜ | — |
| Stage5 gate 对齐 + 3D 同口径对比 | ⬜ | — |
| GUI 三演示 | ⬜(用户指示:跑通后建) | — |

## 三、不能宣称的结论(汇报/文档纪律)

1. **不能说"完整 GBPlanner 已集成完成"**——当前=transport+纯 planner 栈消费闭环,Stage4/5 未做;
2. **不能说"已实现 3D 探索"**——Stage2.6 输入是 z=0 冒烟;3D 实证进行中;
3. **不能把 Stage2.6 说成完整 world-model 闭环**——那是"纯 planner 栈+手工输入";stage2k 证据是反例(完整原仿真栈里 GBPlanner 吃原生 topic,/wm/\* 无订阅者);
4. **RViz 绿线(best planning path)≠执行轨迹**——执行轨迹=粉线=`/rmf_obelix/command/trajectory`(发布者 PCI,已实证),桥只接它,绝不接 `/vis/*`;
5. **PR/Issue 禁止提交**——用户指示:等真 GBPlanner 集成跑通后统一定稿(物料全部 DRAFT);
6. exploration gate **不需要 coverage_growth**(那是 navigation task 的,gate_evaluation.go L224 实证)。

## 四、关键技术事实(踩坑记录,新窗口必读)

- **jazzy `ros2 topic echo` CLI 对 rclpy 发布者收不到**(stage2i 矩阵:rclpy→rclpy 60/60,rclpy→CLI 0)→ 验收一律 rclpy 订阅;
- world-model 生成器把 iris 的 lidar_3d **故意降为 lidar_2d**(navlab_models.go L35)→ 3D 方案=净增量加 lidar3d 传感器(独立 topic,SLAM 链零触碰);
- PCI 规划循环靠"轨迹被执行"驱动,静止 odom 会挂起循环 → 持续探索需 Stage4 FCU 闭环;
- micro-ROS agent 的 DDS 端点对后加入订阅者要 ~29s 才匹配(B16 实测)→ 探针预算 45s/容器 90s;
- 薄桥消息在 ROS1 端重打 `rospy.Time.now()` 戳,ROS1 侧统一 wall clock,与 world-model sim time 解耦;
- WSL/工具纪律:搜 Grep/读 Read/改 Edit/git 用 PowerShell;WSL 只跑脚本文件;docker exec 不过 entrypoint 须显式 source。

## 五、当前入口(新窗口只看这些)

| 文件 | 作用 |
|---|---|
| [CURRENT_STATUS.md](CURRENT_STATUS.md) | 本文,唯一事实源 |
| [TASKS.md](TASKS.md) | 任务表 |
| [接力棒_当前值班.md](接力棒_当前值班.md) | 双 agent 锁 |
| [docs/桥接查证与执行计划_2026-07-06.md](docs/桥接查证与执行计划_2026-07-06.md) | 桥接技术主文档(ACTIVE) |
| [docs/world-model端到端Bug台账_给作者PR.md](docs/world-model端到端Bug台账_给作者PR.md) | PR 事实源(REFERENCE) |
| runbooks/world-model-jazzy/stage\*_evidence.txt | 各阶段实测证据 |

历史资料(预研A/B、35轮排障、旧方案、旧 PR 文案)一律在 [docs/archive/](docs/archive/) 与 [文档索引](文档索引.md),不作为施工入口。
