> **[CURRENT] 本文件是全项目唯一当前事实源。其他文档与本文冲突时,以本文为准。**
> 维护规则:每完成/失败一个阶段就更新本文;README 只引用本文,不另行维护状态。

# CURRENT_STATUS(最后更新:2026-07-07 下午)

## 一、当前一句话状态

> **Stage2~5 主链全部有实证**:4c 去混流可归因 PASS;5a gate 机制 PASS(run8)且已 3 次重现;
> **runA(`stage5b` 变体A)= GBPlanner 策略下首个 TASK_STATUS_OK 完整全绿 run**;
> **5b 3D 行为对照成立**(FOV ±30°→±5°:输入云 zspan 9.08→0.48,TSDF 点数 121k→54k,trajectory zspan 收缩一个量级);
> **5c 同口径 6 run 统计**:gate 达标率 3/6=50%(vs 基线 40%,且我方 accepted=真实运动到达),全绿 1/6=17%
> (失败=A类探索质量 3 次 + B类 frame_contract 波动,B类与 GBPlanner 无关);path 方差远小于基线(0.30 vs 3.4)。
> 上游 EKF 参考系真 bug 已根治(clean 99bcfa1);**ROS2 复核:未发现官方 ROS2 版 GBPlanner**(16 分支全 ROS1,0 tag),
> 短期维持 B2.5 薄桥路线(Review_017 判断一致)。当前施工点 = **成功率提升(A类波动)→ 基线修复后重跑 → GUI/PR 定稿**。

## 二、阶段表(全部有证据文件)

| 阶段 | 状态 | 证据 |
|---|---|---|
| 前置·jazzy 9/9 镜像 | ✅ | docker images 验真 |
| 前置·exploration 端到端全绿(B1~B16 修复链,无 hack) | ✅ | run `20260706T130626`;clean 分支 5 commit(+99bcfa1 EKF 修复);净 diff 286 行+82 行 |
| Stage0 frontier_lite 基线定档 | ✅ | [基线定档](docs/基线定档_frontier_lite_2026-07-06.md):6 run,全绿 2/6,达标率 40%,根因=启动耗时蚕食 26s 窗口 |
| Stage1 GBPlanner ROS1 单侧复验 | ✅ | stage1_evidence:自主移动+trajectory+frames 实测 |
| Stage2 薄桥 transport 三段 | ✅ | stage2e/2j:odom✅ cloud✅ trajectory✅(rclpy 订阅口径) |
| Stage2.5 TCP 稳定性 | ✅ | stage2k:心跳后零断连;acceptor 线程死亡 bug 修复 |
| Stage2.6 纯 planner 栈消费 /wm/\* 闭环 | ✅ | stage26_evidence:订阅关系+voxblox 2.303Hz+19 条 trajectory。**边界:输入是 2D 冒烟(z=0),非 3D** |
| Stage3 trajectory dry-run(零发布) | ✅ | stage3_evidence:37 条 DRY 跟踪量数学自洽(首跑曾 FAIL=PCI 状态机挂起,fresh 时序后 PASS) |
| **Stage3.5 3D 数据链贯通** | ✅ **三判据过(stage35_evidence)** | lidar3d 净增量(点云源 z 跨度 3.3m)→ 薄桥 cloud3d 直通(base64/2Hz,3D 优先自动停 2D 冒烟)→ **史诗同框**:world-model 真栈(SITL 真 odom 604 条+真 3D 点云 115 帧)喂 GBPlanner → **voxblox 3D 体素地图 90,472 点 zspan=13.2m(判据②)**→ trajectory 回流(32wp,z 分量存在,判据③初步——大 z 机动待 Stage4 真飞) |
| **Stage4 低速 FCU intent(XY/Yaw)** | ✅ **4a/4b 消费直证 + 4c 去混流可归因全过** | 4a/4b:`/ap/v1/cmd_vel` GBP-SIGNATURE 逐位吻合+唯一性论证(frontier 值域不可能产生)。**4c(stage4c_external_evidence)**:external 策略下 frontier intent=0/status frontier=0(双零),GBP 运动 intent 61 条、签名 cmd_vel 14 条,**签名活跃窗口 odom path=0.99m≥0.10m**(环境漂移率 ~8 倍),takeoff_ok=True,渲染脚本 external 直证。适配器=fail-closed 全套(enable/kill/限速/超龄/frame 校验) |
| **Stage5cal 轴向校准+上游 EKF 真 bug 根治** | ✅ **根因链 BIN 验尸定案([stage5a_diagnosis](runbooks/world-model-jazzy/stage5a_diagnosis.md))** | ①坐标语义:intent(x,y) 不经旋转直进 NED;fcu 主路="胡萝卜"**位置目标**(目标=当前+v×2s),实际速度 ~0.3m/s 由 AP 增益决定与命令幅值无关;②**上游真 bug:EK3_SRC1_YAW=1(罗盘/世界系)与 POSXY=6(SLAM/map 系)参考系差 δ→运动即 stopped aiding→position lost→估计跑飞 34m**(=frontier_lite 基线 path 0.43~3.80m 方差的根因);③修复 3 件套(YAW→6、COMPASS_USE 全关、--no-align-yaw-to-fcu 显式传——argparse 默认 True=yaw 循环自证)已提交 **clean 分支 99bcfa1**,go test 全绿;④教训:parm 模板只是测试 fixture,真源头=docker/profiles/*.parm(只改模板 BIN 实测不生效) |
| **Stage5a gate/status 严格对齐** | ✅ **机制验收 PASS(run8 `20260707T041455`)**;全绿待 5c 统计 | **exploration gate 首次以 strategy=gbplanner 通过 exploration_probe**:适配器五条件闩锁(enable+无混流闩+controller_ready+accepted_goals≥3+path≥0.35+blockers 空)触发 GATE OK(wp_done=4 **全运动到达**,wp_prereached=4 另行剔除不计,path 0.80m);探针采样 ok=True rc=0,summary gate.exploration 收录 claim=evaluated。适配器最终形态:双坐标系(map vs /navlab/fcu/local_position_pose)**Procrustes 在线对齐**(实测旋转 −87° det=+1,396 对)+yaw_rate 恒 0(旋转致 2D SLAM 失锁)+slam_frozen blocker+近距比例减速(防胡萝卜越过 wp 的 0.5m 极限环)。**诚实边界**:run8 全绿被 frame_contract_probe 波动挡住(B16 同款,非 GBPlanner 链路);run9 accepted=1(探索质量 run 间波动,与基线 40% 同性质)→ 成功率统计归 5c |
| **Stage5b 3D 行为对照** | ✅ **成立([stage5b_evidence](runbooks/world-model-jazzy/stage5b_evidence.txt))** | 同参数只改 lidar3d 垂直 FOV(±30°→±5°):输入云 zspan 9.08→0.48(19×),TSDF 点数 121,479→54,129,trajectory zspan 0.434→0.001~0.166 且 1 条→6 条频繁重规划,gate 结果改变——**GBPlanner 行为确受 3D 输入影响**。诚实边界:是传感 FOV 对照而非障碍物对照(动官方迷宫伤基线可比性,列为增强项);TSDF zspan 含推断体素,点数+输入 zspan 才是主信号。**意外收获:变体 A(基线配置)= 首个 TASK_STATUS_OK 完整全绿 run** |
| **Stage5c 同口径多 run 对比** | ✅ **首批 6 样本定档([stage5c_summary](runbooks/world-model-jazzy/stage5c_summary_evidence.txt))** | run8/9/A/1/2/3(全部修复后同口径):**gate 达标率 3/6=50%**(vs 基线 40%,且我方 accepted=真实运动到达,基线是纯时间驱动)、全绿 1/6=17%、path 均值 0.90m 方差 0.30(基线跨 3.4m);失败分类:A类·探索质量 3 次 / B类·frame_contract 波动 3 次现身(2 次为唯一拦路,与 GBPlanner 无关)。**§7.3 失真补证表**:cmd_vel↔intent 方向差 0~14°(FCU 转发忠实);odom↔intent 差均值落在 map↔NED 固定旋转附近,段间散布来自换向瞬态(稳态段细化留增强)。⚠️公平性:基线跑于 EKF 修复前(path 含跑飞成分),严格对比需基线重跑 |
| **ROS2 路线复核(Review_017 §5)** | ✅ 已复核(2026-07-07 联网) | **未发现作者官方发布的 ROS2 版 GBPlanner**:ntnu-arl/gbplanner_ros 16 分支(master/gbplanner1/2/3/dev-noetic 等)全 ROS1 系,0 tag/release,无 ros2/humble/jazzy/foxy 关键词分支;NTNU unified_autonomy_stack 亦无明确 ROS2 GBPlanner 移植声明;第三方 fork 均为镜像非移植。**当前官方可复现路线仍是 ROS1/catkin;短期维持 B2.5 薄桥**(与 Review_017 判断一致) |
| 成功率提升(A类波动)+ 基线修复后重跑 + GUI 三演示 | ⬜ 下一步 | A类=GBPlanner 侧轨迹 wp 距离/窗口时长/触发时机可调;基线在 EKF 修复后重跑保公平;GUI 用户指示跑通后建 |

## 三、不能宣称的结论(汇报/文档纪律)

1. **不能说"完整 GBPlanner 已集成完成/稳定全绿"**——主链 4c/5a/5b/5c 全有实证且已出现完整全绿 run(runA),但**全绿率仅 1/6**,受 A类探索质量波动+B类探针波动影响;**不能说"GBPlanner 显著优于基线"**——gate 达标率 50% vs 40% 且计数口径更严,方向有利,但基线跑于 EKF 修复前(path 污染),严格结论需基线重跑;**不能说"3D 障碍物级行为对照已做"**(5b 是传感 FOV 对照);
2. **不能说"已完成 3D 探索闭环/完整 gate/FCU 闭环"**——可以说"**3D 数据链已贯通**,voxblox 3D 体素证据成立(90,472 点 zspan 13.2m)";Stage3.5 证明数据链,**不证明完整任务成功**(stage35 的 world-model run 本身 status=blocked=exploration_probe 波动+尚无 Stage4/5,见证据定性);
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
- **SITL 参数真源头=`docker/profiles/navlab-sitl-external-nav.parm`**,templates/parm/*.tmpl 只是测试 fixture(只改模板 BIN 实测不生效,5a 第四跑教训);
- **fcu MAVLink 主路是位置目标不是速度**("胡萝卜"=当前+v×2s):实际速度 ~0.3m/s 由 AP 增益决定,限速形同虚设;hold 滑行 0.5~1m;近距目标会越过 wp(须比例减速);
- **持续 yaw 旋转会把 X2 2D SLAM 干失锁**(odom 冻结/±1cm 抖动)→ 外部规划器驱动时 yaw_rate 恒 0(360° lidar 无需对头);
- `/navlab/fcu/local_position_pose` = AP LOCAL_POSITION_NED 的 xy 恒等回发(4Hz),可与 /slam/odom 组位移对做在线坐标对齐(Procrustes);EKF 混乱期该话题会冻结;
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
