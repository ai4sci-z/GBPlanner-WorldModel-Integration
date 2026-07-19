# CURRENT_STATUS(唯一当前状态源;最后更新 2026-07-18)

> 问题事实源 = [docs/world-model端到端Bug台账_给作者PR.md](docs/world-model端到端Bug台账_给作者PR.md);
> 任务队列 = [TASKS.md](TASKS.md);交接 = [接力棒_当前值班.md](接力棒_当前值班.md);
> 执行纪律 = [工作铁律.md](工作铁律.md);审查主令 = `~/桌面/ClaudeCode_Reviews/`(R003 系列)。

## 一、目标与路线

把 GBPlanner(ROS1)无损迁移到 ROS2,作为独立、可配置选择、可切换、可回滚的探索算法接入
world-model,与 frontier_lite 等并列共存。固定路线(不跳步):

**P0 仓库/文档治理 → P1 长时间闭环稳定(WP303-WP308)→ P2 ROS1/ROS2 对齐 → P3 3D 无损 → P4 插件化接入。**
多层楼梯探索只做架构预留,不写功能代码。

## 二、当前位置(一句话)

**P0 治理收尾 + P1 前置(WP304)。** WP303 批生命周期已到实现停点;WP304 的离线证据链与
E1 观测方案已交付;**R003 状态闭环已经 Codex 独立复验 VERIFIED_PASS 关闭(2026-07-19;
复验基线=CLOSE-05 收口态,精确 HEAD 见 `governance/manifest_main.tsv` 头 `HEAD=`)**。分类:VERIFIED_CLOSED=R003-CLOSE-01..05/OPEN-2 环境复验/状态闭环;
CARRIED_OPEN=OPEN-1、WP303 真实链路、WP306-308、G4-G8;DEFERRED=dependencies 专用语义验收器。
**Codex 已复现:recover(telemetry_dir)=CORRUPT 但正式 evaluate_run_evidence() 仍使 evidence gate 得到 COMPLETE(段链漏验);且正式入口 sidecar 身份等待默认 5s 与 run_batch 120s 启动预算/300s watcher 不一致。E1L 状态 REOPENED/PARTIAL,A/A 不得放行。此为 E1 既有 required evidence 契约的失败,非冻结后新增范围**。当前令=R003-WP304-E1L-CORRECT(仅修此二缺陷;仍禁真实仿真/A/A)。

## 三、三仓基线

| 仓 | 分支@HEAD | 角色 | 本轮 |
|---|---|---|---|
| GBPlanner-WorldModel-Integration | main(HEAD 见 `governance/manifest_main.tsv` 头 `HEAD=`) | 治理/证据/状态入口 | 可改 |
| gbp-feat | feat/gbplanner-ros2-port@`17db3bae08d7` | ROS2 迁移代码(M1-M5) | 只读 |
| world-model | fix/world-model-e2e-takeoff@`750032a3aad8`(origin=SZ-surveying 上游,勿推;推 backup) | 仿真/运行链 | 授权修复已入(`faadb2a` B23 + `e569ecf` B22 接线 + `750032a` OPEN-2 解耦,fixture 级)并**重新冻结** |

## 四、已证事实(按证据等级)

- **B21 已验证**:external_nav 位置换系东轴取负(左手系反射喂入,BIN 帧审计 det≈−0.9);
  修复(wm `908a95a`)后 det≈+1,真值臂反事实 3/3 稳。
- **B22 候选(强支持)**:iris IMU roll-180 倒装致 SLAM 朝向反 180°;修复候选 wm `eab0cc6`
  (hover 族接线 `eab0cc6`;exploration/navigation 接线已补齐 `e569ecf`,fixture 级,真实仿真未验)。
- **默认主线分母(2026-07-15,wm eab0cc6)**:attempts 6 / airborne 3 / full-pass 3;
  诊断臂旁证 4/3/3。10/10 未开跑,禁写"稳定/FIXED/关门"。
- **OPEN-1 未定位**:同 commit 间歇性 bring-up 失败。已证伪"Accels inconsistent=判别器"
  (CRC 校验计数在成功与失败 run 均=20);no-BIN 类死因 UNKNOWN(SITL 控制台未落盘是主观测缺口)。
- **OPEN-2**:OPEN-2 的环境依赖复验失败观测已消除(wm `750032a`);WP305 反例矩阵与双环境
  独立复验通过(宿主 venv 22 passed + companion 容器真 pymavlink 2.4.49 ran=22 fails=0);
  真实仿真行为验收未执行,归 WP307。
- **M0-M4 = 窄验收**(编译/单测/切片对拍);行为等价与 3D 无损未证,归 P2/P3。
- **B23 runner 等 mission + B22 exploration/navigation IMU 接线补齐(wm `faadb2a`/`e569ecf`,2026-07-18)**:
  先红后绿 + 全模块 11 包测试 ok;状态词=**已编码+单测通过,真实仿真未验**,不改判任何门。

## 五、R003 九门

| 门 | 状态 | 依据 |
|---|---|---|
| G1/G2 manifest 闭包 | ✅ | 三仓 bound/current rc=0 |
| G3 生成器测试 | ✅ | 57/57 |
| G4 文档闭包 | 🟡 PARTIAL | 14 份逐行审计完成(8 全核/5 部分/1 归档),未核范围见 [审计记录](governance/P0_doc_audit_逐份审计_2026-07-18.md) |
| G5 WP303 生命周期 | 🟡 实现停点 | fixture 75/12/13 全绿;真实仿真未验 |
| G6 WP304 因果链 | 🔴 E1L-CORRECT PARTIAL | 缺陷一(段链漏验)已修:正式 gate 段链闭包 25P 红→绿;缺陷二(等待预算 5/120/300 不一致)施工中 |
| G7 默认 10/10 | ⛔ | 待 WP304-306 |
| G8 长稳 | ⛔ | 待 G7 |
| G9 六项收口 | 🔁 持续 | — |

## 六、推进思路(依赖链)

```
当前唯一施工点          下一停点                  解锁                    仍阻塞
──────────────────────────────────────────────────────────────────────────
E1 A/A 实验(OFF×2+ON×2)→  A/A 无扰动门(D6)   →  E1 pilot(≤3,另批) →  E2 负载对照
(待负责人另行放行;E1L 运行期                        ↳ OPEN-1 新数据
 旁路链已闭合:watcher 握手/状态机/周期封存/并发采集)
WP305 epoch 复验    →  已达成(双环境独立复验) →  真实仿真验收归 WP307 →  —
WP306 三单元        →  各单元反例测试绿         →  与 E1 无依赖,可并行  →  —
──────────────────────────────────────────────────────────────────────────
OPEN-1 定位 + WP305/306 完 → WP307 默认 10/10 → WP308 长稳 → P1 关门
P1 关门 → P2 ROS1/ROS2 对齐(oracle 冻结)→ P3 3D 无损 → P4 插件化接入
```

- E1 基线已裁决:`eab0cc6` 独立 detached worktree 复现历史(288b486 原地不动,其上样本=新基线);
  companion 镜像 `jazzy-eab0cc6f0d54` 已确认在盘(system docker daemon)。
- E1 前置雷:~~Docker 双 daemon~~(**已排除**:Desktop 于 07-18 卸载,单 system daemon);
  ~~runner 探针完即 SIGKILL mission~~(**已修 B23**,wm `faadb2a`,fixture 级;真实仿真未验);
  RTF≈0.08(单 run ≈25 分钟墙钟,批次预算按此排)。
- ⚠️ 基线注记:E1 历史复现基线仍=`eab0cc6` 独立 worktree(裁决不变);授权修复链在
  `288b486` 之上(`faadb2a`→`e569ecf`→`750032a`,当前材料),属**未来新基线材料**,
  不得混入 eab0cc6 历史统计。
- P2/P3 是论文核心交付(等价性证据);P1 稳定门未过前不启动,但 oracle 资产
  (gbplanner-ref 镜像、桥接期证据)已冻结待用。

## 七、环境备注

- Docker:单 daemon(system;Desktop 已卸载,config.json credsStore/context 残留已清)。
- 残留容器 `zealous_curran`(Exited)= 台账登记在案的验尸容器,保留待负责人裁决。
- P0 未执行遗留(tag/分支裁决/依赖清单等 7 项)登记于 [TASKS.md](TASKS.md),不擅自执行。
