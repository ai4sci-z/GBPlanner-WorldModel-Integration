# CURRENT_STATUS(唯一当前状态源;最后更新 2026-07-17)

> 全局状态只在本文。问题事实源 = [docs/world-model端到端Bug台账_给作者PR.md](docs/world-model端到端Bug台账_给作者PR.md);
> 任务队列 = [TASKS.md](TASKS.md);交接 = [接力棒_当前值班.md](接力棒_当前值班.md)。
> 历史长过程见 git 历史与 [docs/archive/](docs/archive/),本文不复制审查过程。

## 一、当前阶段与唯一施工点

固定路线:**P0 文档与仓库收口 → WP303 monitor 生命周期 → WP304 OPEN-1 因果时间线 →
WP305 epoch → WP306 GPU/IMU/truth audit → WP307 默认路径 10/10 → WP308 长稳与 R003 收口
→ P2 ROS1/ROS2 对齐 → P3 3D 无损 → P4 WorldModel 独立可切换插件。**
GPS-denied 多层楼梯探索只做架构预留,不进入当前实现。

**当前唯一施工点已推进:WP303 monitor 生命周期已编码并通过 fixture(未做真实仿真);下一 = WP304 OPEN-1 因果时间线(方案停点)。**

## 二、三仓基线与角色

| 仓 | 分支@HEAD | 角色 | 本轮 |
|---|---|---|---|
| GBPlanner-WorldModel-Integration | main@9423a3a(=origin/main) | 治理/证据/状态入口 | 可改 |
| gbp-feat | feat/gbplanner-ros2-port@17db3ba(=upstream) | ROS2 迁移施工事实源(M1–M5) | 只读 |
| world-model | fix/world-model-e2e-takeoff@288b486(=backup;origin=SZ-surveying 上游红线勿推) | 仿真/B17–B22 实现事实源 | 只读 |

## 三、已证事实与问题保守状态

- **B21(wm `908a95a`)= 缺陷与修复已验证**:external_nav 位置转换东轴取负 → 左手系反射喂入
  (BIN 帧审计 det=−0.92/−0.95/−0.93 三样本);修复后 det≈+1.0,L1.5 真值臂反事实 3/3 稳。
- **B22(wm `eab0cc6`)= 候选根因**:iris IMU roll-180 倒装 → Cartographer 朝向反 180°;
  诊断臂反事实 4 攻 3 过全绿,默认主线 6 攻 3 过。**默认路径 10/10 未开跑,禁写 FIXED/稳定/关门。**
  ⚠️ 只转正了 hover 族;exploration/navigation 的 cartographer 仍读原始 `/imu`,M5 前必须补。
- **OPEN-1 = 间歇性 bring-up 失败(未定位)**:同 commit 同配置一败一成(Accels inconsistent /
  waiting_for_fcu_external_nav / SITL 无 BIN);致命级,封 GATE-4b 稳定性宣称,归 WP304。
- **OPEN-2 = 时钟纪元候选实现(wm `288b486`)独立复验失败**:节点级测试 mavlink=None 炸,
  测试须环境无关;归 WP305。
- 分母纪律:attempts / airborne / full-pass 并列,失败不出分母。

## 四、R003 九门当前状态

| 门 | 内容 | 状态 |
|---|---|---|
| G1 | manifest bound 闭包 | ✅ 三仓 rc=0 |
| G2 | manifest current 闭包 | ✅ 三仓 rc=0 |
| G3 | generate_manifest 测试 | ✅ 57/57;工具安全模型不再扩展,仅三固定输出 |
| G4 | 文档闭包(链接/登记/路径/生命周期/语义) | 🟡 P0 收口中 |
| G5 | WP303 monitor 生命周期实现 | 🟡 **已编码+正式入口 e2e dry-run 通过**(test_wait_batch 54/54 + test_batch_common 12/12 + test_final_rc 13/13;正式入口 run_batch.sh 自动 launch→record→monitor→传播 rc;deadline 跨重启不重置;三轴退出码);**未做真实仿真验收** |
| G6 | WP304 OPEN-1 因果时间线 | ⛔ 阻塞(待 WP303) |
| G7 | WP307 默认路径 10/10 | ⛔ 阻塞 |
| G8 | WP308 长稳 | ⛔ 阻塞 |
| G9 | 六项收口纪律 | 🔁 持续 |

## 五、唯一下一动作

**WP304 OPEN-1 因果时间线(方案停点)**:对失败/成功 run 逐层建启动+readiness 时间线,
形成竞争假设矩阵,单变量可证伪实验须负责人放行后才跑。WP303 已编码通过 fixture(未做真实仿真验收),
契约实体见 batch_lifecycle.py/batch_common.sh;原方案见
[governance/WP303_monitor生命周期方案_2026-07-16.md](governance/WP303_monitor生命周期方案_2026-07-16.md)
(原方案含已知缺陷,实施以当前工作包修订契约为准)。

Docker 容器归属本轮无法独立核验,一律记 UNVERIFIED,不写"零容器"为事实。
