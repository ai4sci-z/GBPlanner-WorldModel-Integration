# CURRENT_STATUS(唯一当前状态源;最后更新 2026-07-17)

> 全局状态只在本文。问题事实源 = [docs/world-model端到端Bug台账_给作者PR.md](docs/world-model端到端Bug台账_给作者PR.md);
> 任务队列 = [TASKS.md](TASKS.md);交接 = [接力棒_当前值班.md](接力棒_当前值班.md)。
> 历史长过程见 git 历史与 [docs/archive/](docs/archive/),本文不复制审查过程。

## 一、当前阶段与唯一施工点

固定路线:**P0 文档与仓库收口 → WP303 monitor 生命周期 → WP304 OPEN-1 因果时间线 →
WP305 epoch → WP306 GPU/IMU/truth audit → WP307 默认路径 10/10 → WP308 长稳与 R003 收口
→ P2 ROS1/ROS2 对齐 → P3 3D 无损 → P4 WorldModel 独立可切换插件。**
GPS-denied 多层楼梯探索只做架构预留,不进入当前实现。

**当前唯一施工点已推进:WP303 生命周期补正完成(75/12/13 全绿);WP304 OPEN-1 E0 收口
(离线提取器+CRC 校验协议解码器+观测 schema 草案;证伪"accel=失败判别器";arm 时序/no-BIN 死因=UNKNOWN;
运行时埋点未实现);证据门/独立标注补正收口(R003-E0-EVIDENCE-GATE 包A/B:evidence_gate+acceptance_eligible,可复现标注 v2);E1 可执行方案已交付(WP304 §10)。下一 = 待放行 E1 最小旁路观测补丁**实现停点**(实现+fixture,不跑仿真)。**

## 二、三仓基线与角色

| 仓 | 分支@HEAD | 角色 | 本轮 |
|---|---|---|---|
| GBPlanner-WorldModel-Integration | main@**当前 HEAD 见 governance/manifest_main.tsv 头 `HEAD=`**(每次 manifest 刷新提交同步为最终 review commit;此处不写易过期的内嵌 SHA) | 治理/证据/状态入口 | 可改 |
| gbp-feat | feat/gbplanner-ros2-port@17db3bae08d7(=upstream) | ROS2 迁移施工事实源(M1–M5) | 只读 |
| world-model | fix/world-model-e2e-takeoff@288b48630237(=backup;origin=SZ-surveying 上游红线勿推) | 仿真/B17–B22 实现事实源 | 只读 |

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
| G4 | 文档闭包(链接/登记/路径/生命周期/语义) | 🟡 **PARTIAL**:14 份活跃文档逐行事实审计完成(8 REFERENCE_VERIFIED / 5 REFERENCE_PARTIAL / 1 ARCHIVE,逐份读取范围+重放核验+未核实范围见 [governance/P0_doc_audit_逐份审计_2026-07-18.md](governance/P0_doc_audit_逐份审计_2026-07-18.md));5 份 PARTIAL 的未核实范围(外部仓现状/镜像复测/次级行号重放)关闭前 G4 不改通过;doc_closure rc=0 只证机械门,不替代人工逐主张审计 |
| G5 | WP303 monitor 生命周期实现 | 🟡 **PARTIAL(实现停点,未发布)**:已编码+正式入口 e2e dry-run 通过(test_wait_batch **75/75**〔1-23 生命周期 + 24-33 串批/身份/路径边界反例〕+ test_batch_common 12/12 + test_final_rc 13/13);batch_id 端到端绑定(纳秒+UUID 强唯一,producer 经 WP303_BATCH_ID 盖章,monitor 只认本批 run/final);正式入口拒绝旧现场(不删旧证据);required 路径边界拒绝绝对/../symlink 越界;deadline 跨重启不重置;三轴退出码。**未做真实仿真验收** |
| G6 | WP304 OPEN-1 因果时间线 | 🟡 **E0 收口停点**(离线提取器+协议解码器+schema 草案,未启动仿真、未实现运行时埋点):CRC 校验协议解析证伪"accel=失败判别器"(成功与 BIN-失败 accel 均=20、no-BIN=0);airborne 取 mission_summary 正证据;**arm 时序/no-BIN 死因/是否同源 = UNKNOWN**。见 [governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md](governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md) §9 + [runbooks/…/open1/](runbooks/world-model-jazzy/l0_hover/open1/);包A/B 证据门+独立标注收口、包D E1 可执行方案(§10)已交付;申请下一动作=放行 E1 **实现停点** |
| G7 | WP307 默认路径 10/10 | ⛔ 阻塞 |
| G8 | WP308 长稳 | ⛔ 阻塞 |
| G9 | 六项收口纪律 | 🔁 持续 |

## 五、唯一下一动作

**放行 R003-WP304-E1 最小旁路观测补丁实现停点**(实现+fixture,不跑真实仿真):E0 已收口+证据门/独立标注补正收口(包A/B),E1 可执行方案已交付(WP304 §10:基线裁决=eab0cc6 独立 worktree、20 项真实调用链 file:line、26 观测字段契约、纯旁路/A-A 门/WP303 联合门/STOP 条件;sidecar 方案默认零 wm 改动)。E0 收口
(离线提取器 + CRC 校验协议解码器 + 观测 schema 草案,未启动仿真、未实现运行时埋点)。
最强事实(绑证据):CRC 校验后 accel 文本在成功与 BIN-失败均=20、no-BIN=0 → **非成败判别器**;
airborne 取 mission_summary 正证据;**arm 时序 / no-BIN 直接死因 / 两类是否同源 = UNKNOWN**。见
[governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md](governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md) §9
+ [runbooks/…/open1/](runbooks/world-model-jazzy/l0_hover/open1/)。
基线已裁决(WP304 §10.1):**推荐 eab0cc6 独立 detached worktree 复现历史**;288b486 原地不动,
其上样本=新基线不并入历史 6/3/3(eab0cc6..288b486 三提交动 external_nav+GPU,因果污染实证)。
运行时缺口捕获=sidecar 旁路方案(§10.3-10.4),**默认零 wm 改动**;须改 wm 即触发 STOP 申请扩权。
基线红线:禁 checkout/reset 当前 `288b486`;E1 实现停点只写代码+fixture,不启动仿真。

Docker 本轮可读:`docker ps -a` 为空(无运行/退出残留容器)。历史容器由谁删除**不作推断**;
容器归属的历史链仍记 UNVERIFIED,但不再写"无法独立核验 Docker"。
