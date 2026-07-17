# CURRENT_STATUS(唯一当前状态源;最后更新 2026-07-17)

> 全局状态只在本文。问题事实源 = [docs/world-model端到端Bug台账_给作者PR.md](docs/world-model端到端Bug台账_给作者PR.md);
> 任务队列 = [TASKS.md](TASKS.md);交接 = [接力棒_当前值班.md](接力棒_当前值班.md)。
> 历史长过程见 git 历史与 [docs/archive/](docs/archive/),本文不复制审查过程。

## 一、当前阶段与唯一施工点

固定路线:**P0 文档与仓库收口 → WP303 monitor 生命周期 → WP304 OPEN-1 因果时间线 →
WP305 epoch → WP306 GPU/IMU/truth audit → WP307 默认路径 10/10 → WP308 长稳与 R003 收口
→ P2 ROS1/ROS2 对齐 → P3 3D 无损 → P4 WorldModel 独立可切换插件。**
GPS-denied 多层楼梯探索只做架构预留,不进入当前实现。

**当前唯一施工点已推进:WP303 生命周期补正完成(75/12/13 全绿);WP304 OPEN-1 E0 完成
(埋点+fixture,确定性证伪 accel 判别器假说,no-BIN 收窄为 boot 完成后零 arm 尝试)。下一 = 待放行 E1 静默 pilot。**

## 二、三仓基线与角色

| 仓 | 分支@HEAD | 角色 | 本轮 |
|---|---|---|---|
| GBPlanner-WorldModel-Integration | main@WP303 实现基线(随补正推进,当前 origin/main;**非最终发布 HEAD**) | 治理/证据/状态入口 | 可改 |
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
| G5 | WP303 monitor 生命周期实现 | 🟡 **PARTIAL(实现停点,未发布)**:已编码+正式入口 e2e dry-run 通过(test_wait_batch **75/75**〔1-23 生命周期 + 24-33 串批/身份/路径边界反例〕+ test_batch_common 12/12 + test_final_rc 13/13);batch_id 端到端绑定(纳秒+UUID 强唯一,producer 经 WP303_BATCH_ID 盖章,monitor 只认本批 run/final);正式入口拒绝旧现场(不删旧证据);required 路径边界拒绝绝对/../symlink 越界;deadline 跨重启不重置;三轴退出码。**未做真实仿真验收** |
| G6 | WP304 OPEN-1 因果时间线 | 🟡 **E0 停点**(埋点实现+fixture 完成,未启动仿真):自包含 tlog 解码器确定性证伪"accel=失因"(成功/BIN-失败 accel 恒=20);no-BIN=boot 完成却零 arm 尝试(异源,根因 UNKNOWN)。方案+E0 结果见 [governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md](governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md) §9 + [runbooks/…/open1/](runbooks/world-model-jazzy/l0_hover/open1/);申请下一动作=放行 E1 静默 pilot(≤3) |
| G7 | WP307 默认路径 10/10 | ⛔ 阻塞 |
| G8 | WP308 长稳 | ⛔ 阻塞 |
| G9 | 六项收口纪律 | 🔁 持续 |

## 五、唯一下一动作

**放行 WP304 E1 静默 pilot(≤3)**:E0 已完成(埋点实现+环境无关 fixture,未启动仿真)——
自包含 tlog 解码器确定性结论(accel 计数成功/失败恒=20 → 非判别器;no-BIN=boot 完成却零 arm 尝试,
异源、根因 UNKNOWN)、样本分层、F1-F5、H1-H5 见
[governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md](governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md) §9
+ [runbooks/…/open1/](runbooks/world-model-jazzy/l0_hover/open1/)。
E1 前须先裁决**运行时缺口**(宿主负载/SITL 控制台/EKF 残差/arm 时刻)如何捕获:若需改 world-model,**先申请扩权**。
基线红线:历史属 wm `eab0cc6`,禁 checkout/reset 当前 `288b486`;不放行 E1/E2 前不启动仿真。

Docker 容器归属本轮无法独立核验,一律记 UNVERIFIED,不写"零容器"为事实。
