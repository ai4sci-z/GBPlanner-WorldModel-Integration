> **[CURRENT · 唯一当前状态入口]** 全项目状态只在本文维护(main 分支)。其他任何文档
> (TASKS/接力棒/README/HANDOVER/台账/runbook)均为专项事实源、引用或历史证据,与本文冲突时以本文为准。
> 唯一问题台账 = [docs/world-model端到端Bug台账_给作者PR.md](docs/world-model端到端Bug台账_给作者PR.md)。
> 2026-07-16 前的旧版全文 = [docs/archive/CURRENT_STATUS_历史快照_截至2026-07-16.md](docs/archive/CURRENT_STATUS_历史快照_截至2026-07-16.md)(SUPERSEDED,原始数值未改)。

# CURRENT_STATUS(最后更新:2026-07-16,R003 整改·第二阶段"仓库和文档治理")

## 一、当前阶段(唯一有效口径)

**项目处于 R003 审查整改中**(审查文件:`~/桌面/ClaudeCode_Reviews/Review_003_*_2026-07-16.md`,
两份等价,执行从严)。**不处于 M5 继续开发阶段。**

固定路线(R003 锁定,不得跳步):
**① 仓库/文档治理 → ② 长时间闭环稳定 → ③ ROS1/ROS2 前端对齐 → ④ 3D 无损验证 → ⑤ WorldModel 插件化接入**。
多层楼梯探索只做架构预留清单,禁止功能代码。

阶段状态:第一阶段有条件通过;**第二阶段首轮交付被 Codex 判"暂不放行"(2026-07-16)**,
三项阻塞 = 清单闭包不全(990≠实际 997)/文档正文旧主张残留/台账编号契约自相矛盾。
**阶段判定(负责人 2026-07-16 确认)**:
R003-S2-FIX:**收口通过**(CLOSEOUT@0f4a55c)
P0:**主体治理通过;tag/依赖/第三方锁定等执行项仍未关闭**(方案见 governance/README §7)
WP303:**仅方案设计已获放行,尚未批准编码**(方案=governance/WP303_monitor生命周期方案_2026-07-16.md)
49b111d:**冻结未验收草稿**
禁止表述:"P0 全部完成""WP303 进行实现"。
**历史段落(S2-FIX 放行令原文,留档)**:R003-S2-FIX(负责人 2026-07-16 有条件放行;非第二阶段验收通过):范围只限管理主仓
九类文件;wm/gbp-feat 只读;禁仿真/容器操作/tag/WP303+。执行依据 = Review_003 原版(913 行)+
纯中文等价版(551 行)+ 问题驱动工作包重构版(478 行)+ 阶段执行补充令(583 行),四份全文已逐行读取。
第三阶段预备件 wait_batch = `49b111d` **冻结未验收草稿(fixture-timeout 失败在案)**,本包内
禁改禁测、不计成果;WP303 正式开始时从方案停点重审。S2-FIX 收口即停点,等负责人再放行。

## 二、平台事实(GATE-4b 悬停战役,证据链见 runbooks)

**双帧缺陷已定位**(证据:`runbooks/world-model-jazzy/l0_hover/l15_frame_audit_evidence_2026-07-16.md`):

| 编号 | 内容 | 状态(严格口径) |
|---|---|---|
| B21 | external-nav 位置转换东轴取负 → 左手系反射喂入(det=−1 实测 3/3) | 缺陷判定**已验证**;修复 `wm 908a95a` 在 L1.5 真值臂反事实 3/3 稳 |
| B22 | iris IMU roll-180 倒装 → Cartographer 朝向反 180°(位置 cos=+1、yaw=真值−180° 实测) | **候选根因(当前配置下强证据)**;修复 `wm eab0cc6` 诊断臂反事实 4 攻 3 过全绿;**默认主线重复验收未闭合** |

**分母纪律(attempts / airborne / full-pass,失败不出分母)**:
默认主线(eab0cc6)当日 **6 / 3 / 3**;其中 R003 锚定的相邻两跑 = **2 / 1 / 1**(210849 失败:exit 20、
waiting_for_fcu_external_nav、BIN 见 Accels inconsistent;211927 成功:OK、18s 悬停、落地)。
诊断臂 imu-flu-correction **4 / 3 / 3**;L1.5 真值臂 3 / 3 / 3(诊断烙印 rc=1 属设计)。

**未关闭的门**:默认路径 10/10 短窗重复(验收门四)未开跑;长时间闭环稳定另设未开;
**OPEN-1 间歇性 bring-up 失败**(同 commit 一败一成,竞争假设矩阵未建,R003 发现五=致命级)。

**禁止表述**:"默认主线稳定"“GATE-4 恢复/关门”“hover FIXED”。合法表述 = "候选修复,诊断反事实通过,默认主线验收待完成"。

## 三、代码事实源与候选实现状态

| 仓 | 分支@HEAD | 角色 | 关键状态 |
|---|---|---|---|
| `/home/ai4s/projects/world-model` | `fix/world-model-e2e-takeoff@288b486`(=backup;领先上游 origin 19,红线不推) | 仿真与 B17–B22 实现事实源 | `334c47d` 单包阈值(已被取代);**`288b486` 纪元契约 = 候选实现·Codex 独立复验失败**(navlab/.venv 2 failed/18 passed,节点级测试 mavlink=None,见台账 OPEN-2);**`77f0b67` GPU vendor 配置 = 候选实现·待完整复验** |
| `/home/ai4s/projects/gbp-feat` | `feat/gbplanner-ros2-port@17db3ba`(=origin 同名) | ROS2 迁移施工事实源 | M0–M5 统一证据分级(Codex 裁定口径):**M0**=窄验收证据(入口/探针,当时 live 全绿);**M1**=最小消息集构建通过(≠全接口迁移);**M2**=部分切片对拍通过(fast 积分器 2/34,506 失配未归因、3D Demo 查询未测);**M3**=编译+浅单测通过(**行为等价未证明**);**M4**=合成冒烟通过(**真场景长时 open-loop 未验证**);**M5**=仍被平台稳定门阻塞。R003 未逐行审查,manifest 全部 UNVERIFIED |
| 本仓 main | `governance/` 提交后最新 | 治理/证据/状态入口 | `sources/` 592 文件=冻结第三方快照,禁入构建(已实测零引用) |

companion 镜像 tag 陷阱仍有效:wm HEAD 变更后须 retag `jazzy-<HEAD12>`(当前已 retag 至 `eab0cc6f0d54`;
288b486 未 retag——**第六阶段跑批前必须 retag**)。

## 四、R003 验收门状态(纯中文版编号)

| 门 | 内容 | 状态 |
|---|---|---|
| 一 | 仓库和文档治理 | **S2-FIX 施工中**:清单闭包协议见 `governance/README.md` §1(数值以三份 manifest 头部与收口报告为准,本表不复制易过期计数);claim manifest 已建;第三方 LOCKED=0(缺口清单 §2);基准 tag/分支职责/依赖清单 = **方案停点已备**(governance/README §7,执行待负责人批准) |
| 二 | 后台监视生命周期(四态有界退出) | 阻塞(孤儿已清;存在**冻结未验收草稿** `49b111d`,fixture-timeout 失败在案;WP303 从方案停点重审,草稿去留由负责人裁定) |
| 三 | 时钟纪元反例矩阵 | 部分:契约+8 反例在 `288b486`,但独立复验失败+缺节点重启/来源生命周期反例(第四阶段修复) |
| 四 | 默认路径 10/10 短窗 | 阻塞(第六阶段;先过一~五) |
| 五 | 代码契约(covariance/枚举校验/审计豁免等) | 阻塞(第五阶段) |
| 六 | 文档一致性 | 施工中(本阶段) |
| 七 | 提交与远端收口 | 持续执行(origin=上游红线只读;backup=wm 授权镜像;本仓 origin=ai4sci-z 授权) |

## 五、下一步(严格按序)

1. **R003-S2-FIX 收口**:C1 生成器+27 测试 ✅ → C2 claim manifest+治理 README ✅ → C3 状态收口(本 commit)
   → 生成三仓 manifest(绑定 C3)+独立集合校验 → C4 仅提交 TSV(零路径增量,闭包在当前 HEAD 同时成立)
   → git diff --check → 推送核对 → **按补充令 §十六 模板交收口报告,停点**
2. 第三阶段:监视生命周期(helper+四类 fixture)
3. 第四阶段:时钟纪元修复(测试与 pymavlink 解耦+补反例;边界清晰提交)
4. 第五阶段:GPU 支持矩阵/IMU covariance(C'=RCRᵀ)+types.go 反注释/truth audit 混合匹配 fail-closed
5. 第六阶段:OPEN-1 时间线定位+竞争假设矩阵 → 固定条件默认路径 10/10 → 长稳门另设
6. 稳定门后:ROS1/ROS2 对齐 → 3D 无损 → 插件化接入(M5 恢复须负责人批准)

## 六、历史成果指针(只读,不再复述)

- 桥接线(冻结 oracle):公平对比 GBPlanner 50% vs 基线 0% 等全部结论见历史快照与 `docs/archive/`
- 原生迁移八门全过、M0–M4 收口、B1–B20 修复链:见历史快照、`runbooks/`、台账
- 组会/演示材料:`gui/`、`docs/`(阶段性口径,以本文为准)
