# CURRENT_STATUS(唯一当前状态源;最后更新 2026-07-20)

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
**A/A 前置全部闭合(2026-07-20,四项裁决落地)**:方案A 宿主 ROS2 已装(pins 落档,
source /opt/ros/jazzy 激活;未 source 仍 fail-closed);readiness=/mavlink_external_nav/status;
wm 上游契约已实现(service.started 原子发布 service_handles.json 含真实 container_id,
wm@9a1ce95 推 backup);sidecar live 身份消费就绪;FUTURE_CANDIDATE=9a1ce95(显式推进)。
**A/A 环境接线=PARTIAL(2026-07-20,Codex 复验裁定)**:
①镜像接缝已闭合——companion 镜像 `jazzy-9a1ce95c56e2` 在盘(rc=0+docker images
真产物,Codex 独立确认;全层 CACHED=tag 绑定新 HEAD,非行为验证)。
②此前"preflight READY 18/18/接线闭合"被 Codex 击穿(占位符过 presence 门);
一次补正(hash/digest schema+物化独立重算)后,**Codex 三验再击穿(VERIFIED_FAIL)**:
aa_launch 库函数正确但**无 CLI、无生产调用方=测试孤岛**,真实入口 run_batch→
batch_lifecycle 完全绕过真实性门;且负责人停点只是文档规则非机器规则。
③二次补正(aa_cli 正式入口接 batch_lifecycle 链+授权机器门)后,**Codex 四验再击穿
(VERIFIED_FAIL)**:aggregate 空分母 rc=0(零次实验聚合成功=验收出口失真)+fixture
审批与测试覆盖 env(NAVLAB_SIM_CMD 等)可进生产 execute。
④三次补正令五包已施工(2026-07-20):aggregate 重写为**完整分母验收**(冻结计划
schema/launch_record 必在且 producer_started=1/恰好 4 attempt 与计划一一对应/
模式序 OFF,OFF,ON,ON/每 attempt 身份+task_record+monitor+final 终态齐+双向 hash
一致/禁 NOT_STARTED/rejected 必须空;输出 attempts_expected=4 等完整分母字段;
零/缺/多/乱序/失败均 rc=1);生产 execute **删除 --allow-fixture-approval 后门**
(fixture 审批一律拒)+启动前拒全部测试覆盖 env;新增独立 `--dry-run`(强制 fixture
审批,产物永久标 NON_ACCEPTANCE_FIXTURE,被正式 aggregate 永久拒,不是真实 A/A);
approval 增绑**整计划 frozen_plan_sha256**(validate 输出该 SHA 供负责人指令引用;
计划任何字节变化旧审批立即失效)——授权门性质=**具名计划的操作防误触门,非身份
认证,不抗恶意伪造**。树状令复核再补 4 缺口(先红后绿):telemetry 证据双源一致/
batch_final 损坏拒/run_rc_map 非零拒/dry-run 缺 stub 拒(防跑真仿真)。
测试 52(库层)+64(CLI)案全绿。
⑤**五验击穿(VERIFIED_FAIL)**:aggregate 对 monitor_status 只做 json.load,正例 fixture 用 `{}` 冒充终态并断言通过——"可解析"被误当"三轴语义有效"(撤回上轮 P01.5/P04.8/ROOT CLOSED)。**五验补正已施工**(红案冻结→实现→正例分层提交):monitor 三轴语义验证器进 aggregate 正式链(SUCCEEDED/COMPLETE/CLEAN 三轴齐才入分母,轴间不互覆盖,拒因到字段);{} 假正例删除,重建契约级+正式生命周期双正例(真实 batch_lifecycle 产物过 validator=生产者消费者同契约);20 红案(旧全 rc=0)先冻结后转绿;单变量判别全过。测试 52+90 案。**Codex 独立复验 VERIFIED_PASS(2026-07-21,仅本包:{} monitor 击穿已修,含套件外黑盒复验)**;边界=ON 臂 sidecar 深层 evidence(UNKNOWN/MISSING 可过 A/A 层)为已登记风险,权威归 run_registry aggregate、下一编号 Review;**不升级为启动资格/不升级为真实 telemetry 已验证**。真实 A/A 未启动,A/A 启动资格仍未授予。**裁决终态(§8.8 替代 §8.7):先 B 后 A,B 已完成,AA001 已执行未达标**(原裁决点:A=按当前边界放行一次受控 A/A(目标仅测旁路扰动)或 B=先补「ON 臂 sidecar deep evidence 联动检查」小前置包(证据须用于 OPEN-1 因果分析时)。
**当前事实:正式 A/A CLI 已接 batch_lifecycle;aggregate 空分母与测试覆盖隔离
被 Codex 击穿后已补正,验收出口尚未闭合(待 Codex 独立复验);A/A 不具备启动资格。**
击穿与补正记录=[governance/AA环境接线_companion镜像重建与preflight复核_2026-07-20.md](governance/AA环境接线_companion镜像重建与preflight复核_2026-07-20.md) §5-§7。
**AA001 受控 A/A 已执行(2026-07-21,首次真实全链)**:2 发起/1 过/1 败(aa-r3_OFF no-BIN+`waiting_for_fcu_external_nav`,OPEN-1 首次受控复现)/ON 臂未启动;§8.8 完成条件未达成,aggregate 裁定不合格(rc=1);样本保留。**aa-r3 定向分析已完成(2026-07-21,负责人指令)**:最强候选链=FCU LOCAL_POSITION_NED 慢启动爬升期(帧级判别:前 40s 0.8-2.6Hz vs 成功 1.75-5Hz,60s 后均收敛 5Hz)>等待预算(60s/连续5s)→ready 抖动→abort→未 arm→(LOG_DISARMED=0)no-BIN——一条链候选统一解释 no-BIN/间歇性/同 commit 并存;候选非 CONFIRMED,报告=[runbooks/…/open1/AA001_r3_定向分析_2026-07-21.md](runbooks/world-model-jazzy/l0_hover/open1/AA001_r3_定向分析_2026-07-21.md)。**AA002 建议=调整观测后再跑(LOG_DISARMED=1 进计划),待负责人裁决。**P2-OFFLINE-PREP 已获准并行(未开工,LIVE 冻结)。OPEN-1 未定位;G6 未关闭;WP307 未解锁。

## 三、三仓基线

| 仓 | 分支@HEAD | 角色 | 本轮 |
|---|---|---|---|
| GBPlanner-WorldModel-Integration | main(HEAD 见 `governance/manifest_main.tsv` 头 `HEAD=`) | 治理/证据/状态入口 | 可改 |
| gbp-feat | feat/gbplanner-ros2-port@`17db3bae08d7` | ROS2 迁移代码(M1-M5) | 只读 |
| world-model | fix/world-model-e2e-takeoff@`9a1ce95c56e2`(origin=SZ-surveying 上游,勿推;推 backup) | 仿真/运行链 | 授权链 `faadb2a`→`e569ecf`→`750032a`→`9a1ce95`(service_handles 上游契约,负责人批准);A/A 候选基线 |

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
| G6 WP304 因果链 | 🟡 环境接线 PARTIAL | 四裁决落地+镜像接缝闭合;旧 preflight READY 被 Codex 击穿(占位符过门);真实性补正已施工待 Codex 复验;A/A 不具备启动资格 |
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
