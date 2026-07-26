# CURRENT_STATUS(唯一当前状态源;最后更新 2026-07-22)

> 问题事实源 = [docs/world-model端到端Bug台账_给作者PR.md](docs/world-model端到端Bug台账_给作者PR.md);
> 任务队列 = [TASKS.md](TASKS.md);交接 = [接力棒_当前值班.md](接力棒_当前值班.md);
> 执行纪律 = [工作铁律.md](工作铁律.md);审查主令 = `~/桌面/ClaudeCode_Reviews/`(R003 系列)。

## 一、目标与路线

把 GBPlanner(ROS1)无损迁移到 ROS2,作为独立、可配置选择、可切换、可回滚的探索算法接入
world-model,与 frontier_lite 等并列共存。固定路线(不跳步):

**P0 仓库/文档治理 → P1 长时间闭环稳定(WP303-WP308)→ P2 ROS1/ROS2 对齐 → P3 3D 无损 → P4 插件化接入。**
多层楼梯探索只做架构预留,不写功能代码。

## 二、当前位置

**P1 前置 · WP304 · A/A 观测链。真实 AA003 已执行(负责人批准 exact SHA,2026-07-22)。**
approval 绑 frozen_plan_sha256=`3c41d8e…453144`(机器自校验 ok,P02.3 不可变全过),`--execute`
正式入口过门(producer_started=1/READY/refusal=[])。**aa-r1 OFF 失败即停(~3m44s,preflight_timeout,
`S1 wait_nav_ready`,armed_seen=false=从未 arm);aa-r3/aa-r2/aa-r4=NOT_STARTED_PRIOR_FAILURE(入分母)。**
- **A/A 无结论**:仅 1 OFF 跑完,ON 臂未跑,无 OFF/ON telemetry 扰动对比。
- **★OPEN-1 主线推进(BIN-EKF+rosbag 分析已做)**:①**首个失败样本+BIN**(LOG_DISARMED=1 生效,消除 no-BIN 盲区);
  ②BIN 证 FCU/EKF 侧早期健康(external nav 输入 66.9Hz 干净、EKF 3.3s 达完整解、origin 早设)→**CONTRADICTED
  "输入慢/EKF 融合慢/origin 慢"三子假设**;③rosbag 证 ROS 侧 external nav **全程新鲜**(odom_age≈1ms,RTF=0.30 实测,
  "sim-40s 硬停"是时钟误读=run 结束点);④**直接观测到 readiness 狂闪**:sender `ready` 每1-2s翻转而 odom 恒新鲜1ms
  →翻转项=local_position_fresh(FCU LP 输出反馈,推断),tlog 证 LP 输出 0.9Hz(511 限速)。判读见
  [AA003_BIN_EKF分析](runbooks/world-model-jazzy/l0_hover/open1/AA003_BIN_EKF分析_2026-07-22.md)+[AA003_result](runbooks/world-model-jazzy/l0_hover/open1/AA003_result_OPEN1判读_2026-07-22.md)。
- **OPEN-1 候选=STRONG_SUPPORT(经 2026-07-26 自检降级,不写"已定位")**:P01(aa-r1 rosbag 255帧)+P02 代码——
  **VERIFIED**:odom_fresh 255/255 恒 true→**外部导航输入侧排除**;readiness 失败全由 local_position not-fresh 解释,分两半——
  **FCU LOCAL_POSITION 迟起(msgid32 首帧 sim-boot 5.5s/wall+21s)24帧 + 迟起后仍慢/gappy(4.3Hz/12次>1000ms)20帧**;
  companion 墙钟1000ms阈值(external_nav.py:590)+零迟滞门(runtime_state.py:379)→迟+慢LP致readiness反复清零→timeout。
  **级别 STRONG_SUPPORT 非 DIRECT-已定位**("ready==fcu_local_position_ready 44/44"是代码同义反复,不作独立证据,已自检收回)。
  **UNKNOWN**:FCU LP 为何迟+慢(EKF-解到首输出延迟?511协商?RTF?均候选未验)。**推荐单变量 A(提率),OFF-only,待批**;
  B加迟滞/C阈值改sim域备选。判读=AA003_BIN_EKF分析 §8.1。
**A/A 启动资格已就此单次消费(负责人批准该 SHA);是否重跑 AA003 取 ON 臂+多样本待负责人裁决。
不等于 WorldModel 稳定/10-10/长稳/Review3 完成。**

分项现状:

- **A/A 机器门链**(preflight/aa_cli 四模式/aggregate 完整分母/授权防误触门/终态三轴
  语义门/观测条件门):已建成。经五轮 Codex 击穿-补正(占位符过门→测试孤岛→空分母+
  fixture 后门→复核缺口→`{}` 终态语义),五验包 Codex **VERIFIED_PASS(2026-07-21)**;
  已登记边界=ON 臂 sidecar 深层 evidence 的 A/A 级联动检查已加(B 包),five-layer 深检
  权威仍归 `run_registry.py aggregate`。击穿与补正全记录=
  [证据文档](governance/AA环境接线_companion镜像重建与preflight复核_2026-07-20.md) §5-§9。
- **AA001(2026-07-21,首次真实全链 A/A)**:2 发起/1 过/1 败/ON 臂未启动;无 A/A 扰动
  结论;**产出 OPEN-1 首个受控复现样本**(aa-r3_OFF:no-BIN+
  `hover_mission_abort:waiting_for_fcu_external_nav`)。样本=`~/aa_runs/AA001-20260721`。
- **aa-r3 定向分析(2026-07-21,Codex 接受为阶段证据)**:最强候选链=FCU
  LOCAL_POSITION_NED 慢启动爬升期 ×(墙钟 1000ms 阈值/RTF)有效收紧 → ready 抖动
  攒不足连续 5s → 60s 预算耗尽 → abort → 未 arm →(LOG_DISARMED=0)no-BIN。
  一条链候选统一解释 no-BIN/间歇性/同 commit 并存;**候选,未 CONFIRMED**;帧级判别
  与 RTF 实测(恒 0.30)见[分析报告](runbooks/world-model-jazzy/l0_hover/open1/AA001_r3_定向分析_2026-07-21.md)。
- **AA002(2026-07-21)=INVALID_OBSERVATION**:LOG_DISARMED 经 --config 注入无效
  (真实参数链=wm 代码硬编码常量),三 run 实测 mav.parm=0;OFF×2 全过(再证间歇性),
  ON 臂主动取消;无扰动结论、无失败臂内部证据;样本保留(证据文档 §8.10)。
- **AA003 前置(2026-07-22,负责人 B1 裁决,已完成;核心技术 Codex 复验通过)**:
  wm@`6d412a11`(仅 `LOG_DISARMED 1`,观测条件改动,**不是飞行稳定修复**)推 backup;
  FUTURE_CANDIDATE 前移;companion `jazzy-6d412a11f152` 在盘;观测条件门(失败关闭:
  计划声称必须有真实生成链产物证据)进 aa_cli 正式链;validate-only READY。
  真实 AA003 未启动(无 attempts/无 approval)。
- R003 状态闭环已于 2026-07-19 经 Codex VERIFIED_PASS 关闭(CLOSE-01..05);
  CARRIED_OPEN=OPEN-1、WP303 真实链路、WP306-308、G4-G8;DEFERRED 与下一编号 Review
  积压项见 TASKS。
- P2-OFFLINE-PREP 已获准并行,未开工(LIVE 冻结)。

## 三、三仓基线

| 仓 | 分支@HEAD | 角色 | 本轮 |
|---|---|---|---|
| GBPlanner-WorldModel-Integration | main(HEAD 见 `governance/manifest_main.tsv` 头 `HEAD=`) | 治理/证据/状态入口 | 可改 |
| gbp-feat | feat/gbplanner-ros2-port@`17db3bae08d7` | ROS2 迁移代码(M1-M5) | 只读 |
| world-model | fix/world-model-e2e-takeoff@`6d412a11f152`(origin=SZ-surveying 上游,勿推;推 backup) | 仿真/运行链 | 授权链 `faadb2a`→`e569ecf`→`750032a`→`9a1ce95`→`6d412a11`(LOG_DISARMED 观测,负责人 B1 裁决);A/A 候选基线 |

## 四、已证事实(按证据等级)

- **B21 已验证**:external_nav 位置换系东轴取负(左手系反射喂入,BIN 帧审计 det≈−0.9);
  修复(wm `908a95a`)后 det≈+1,真值臂反事实 3/3 稳。
- **B22 候选(强支持)**:iris IMU roll-180 倒装致 SLAM 朝向反 180°;修复候选 wm `eab0cc6`
  (hover 族接线 `eab0cc6`;exploration/navigation 接线已补齐 `e569ecf`,fixture 级,真实仿真未验)。
- **历史默认主线分母(2026-07-15,wm eab0cc6)**:attempts 6 / airborne 3 / full-pass 3;
  诊断臂旁证 4/3/3。10/10 未开跑,禁写"稳定/FIXED/关门"。
- **A/A 系列分母(2026-07-21,wm 9a1ce95;与 eab0cc6 历史分母分开统计,不混)**:
  AA001 OFF 臂 2 攻 1 过;AA002 OFF 臂 2 攻 2 过(观测无效实验,行为数据仍真);
  合计 OFF 臂 4 攻 3 过——与历史间歇率同量级,再证 OPEN-1 与 commit 无关。
- **OPEN-1 未定位(有最强候选链)**:同 commit 间歇性 bring-up 失败。已证伪
  "Accels inconsistent=判别器";**已获受控复现+候选链**(见 §二 aa-r3 定向分析),
  no-BIN 的候选统一解释=从未 arm(LOG_DISARMED=0 不落盘);上游原因(FCU 慢启动为何)
  仍 UNKNOWN,待 AA003 失败臂 BIN 证据检验。
- **OPEN-2**:环境依赖复验失败观测已消除(wm `750032a`);WP305 反例矩阵与双环境
  独立复验通过(宿主 venv 22 passed + companion 容器真 pymavlink 2.4.49 ran=22 fails=0);
  真实仿真行为验收未执行,归 WP307。
- **M0-M4 = 窄验收**(编译/单测/切片对拍);行为等价与 3D 无损未证,归 P2/P3。
- **B23 runner 等 mission + B22 exploration/navigation IMU 接线补齐(wm `faadb2a`/`e569ecf`)**:
  先红后绿+全模块 11 包测试 ok;**真实仿真中 B23 修复已实际生效**(AA001/AA002 五个
  attempt 的 runner 均等待 mission 完成),但 10/10 级验收仍归 WP307。

## 五、R003 九门

| 门 | 状态 | 依据 |
|---|---|---|
| G1/G2 manifest 闭包 | ✅ | 三仓 bound/current rc=0 |
| G3 生成器测试 | ✅ | 57/57 |
| G4 文档闭包 | 🟡 PARTIAL | 14 份逐行审计完成(8 全核/5 部分/1 归档),未核范围见 [审计记录](governance/P0_doc_audit_逐份审计_2026-07-18.md) |
| G5 WP303 生命周期 | 🟡 实现停点 | fixture 75/12/13 全绿;真实仿真级验证:A/A 五 attempt 经 batch_lifecycle 正式链跑通(monitor 三轴/CANCEL/终态产物全真实产出),10/10 级验收归 WP307 |
| G6 WP304 因果链 | 🟡 进行中 | 机器门链五验 PASS;AA001 受控复现+候选链;AA003 前置就绪;**停点=负责人批准 AA003**;OPEN-1 上游原因未定 |
| G7 默认 10/10 | ⛔ | 待 WP304-306 |
| G8 长稳 | ⛔ | 待 G7 |
| G9 六项收口 | 🔁 持续 | — |

## 六、推进思路(依赖链)

```
当前停点                 解锁                          之后
──────────────────────────────────────────────────────────────────────────
负责人批准 AA003     →  真实 A/A(OFF×2+ON×2):        →  ①A/A 扰动结论(D6 门)
(approval 绑 plan SHA)   失败臂带 BIN/EKF 内部时序        ②OPEN-1 候选链检验
WP306 三单元         →  各单元反例测试绿(可并行,未开工) →  —
──────────────────────────────────────────────────────────────────────────
OPEN-1 定位 + WP305/306 完 → WP307 默认 10/10 → WP308 长稳 → P1 关门
P1 关门 → P2 ROS1/ROS2 对齐(oracle 冻结)→ P3 3D 无损 → P4 插件化接入
```

- **A/A 现行基线=FUTURE_CANDIDATE(wm `6d412a11`+companion `jazzy-6d412a11f152`)**,
  由负责人裁决链显式推进(§三授权链);历史复现基线 `eab0cc6`(独立 worktree+镜像
  `jazzy-eab0cc6f0d54` 在盘)仍冻结可用,两类样本不混统计。
- 实测运行参数(AA001 帧级,取代早期估计):**RTF≈0.30 恒定**,hover 单 attempt 墙钟
  3-4 分钟(成功/失败均短,历史"25 分钟/RTF0.08"为旧栈时代数据,已过时)。
- E1 前置雷已清:Docker 单 daemon;B23 已修并在真实 run 生效;companion tag 绑 HEAD
  机制正常(§三)。
- P2/P3 是论文核心交付(等价性证据);P1 稳定门未过前不启动,但 oracle 资产
  (gbplanner-ref 镜像、桥接期证据)已冻结待用。

## 七、环境备注

- Docker:单 daemon(system);运行中容器=0;exited 容器 17 个保留未删(AA001/002 各
  attempt 收尾产物+历史验尸容器 `zealous_curran`),删除待负责人裁决。
- 宿主 ROS2 jazzy 按方案A pins([pins](governance/ros2_host_env_pins_2026-07-20.md));
  A/A 操作须 `source /opt/ros/jazzy/setup.bash`。
- A/A 样本目录:`~/aa_runs/AA001-20260721`(2 attempt)、`AA002-20260721`(3 attempt)、
  `AA003-20260722`(仅 plan/inputs,无 attempts)——均永久保留,重跑不覆盖。
- P0 未执行遗留(tag/分支裁决/依赖清单等 7 项)登记于 [TASKS.md](TASKS.md),不擅自执行。
