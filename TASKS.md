# TASKS(未完成工作包队列;状态以 CURRENT_STATUS 为准)

> 本文只维护**未完成**任务:优先级、依赖、验收门、解锁条件。
> 已完成历史见 git 历史,不在此堆日志。当前分母/状态不在此复制,见 CURRENT_STATUS。

## 当前队列(严格按序,不并行扩张)

| WP | 任务 | 依赖 | 验收门 | 状态 |
|---|---|---|---|---|
| **WP303** | monitor 生命周期实现:launcher + task record + 三轴状态 + fixture;batch_id 端到端绑定+拒绝旧现场(stale-evidence 补正);只跑 fixture 不跑真实仿真 | P0 收口 | 正式入口 run_batch.sh e2e dry-run + test_wait_batch **75/75** + test_batch_common 12/12 + test_final_rc 13/13,残留=0 | 🟡 **PARTIAL 实现停点未发布:dry-run 通过,真实仿真未做** |
| **WP304** | OPEN-1 因果时间线:样本分层 + F1-F5 + H1-H5 + E0/E1/E2;**E0 已收口**(open1/ 离线提取器 + CRC 校验协议解码器 + 观测 schema 草案 + 环境无关 fixture;证伪"accel=判别器";arm/no-BIN 死因=UNKNOWN;运行时埋点未实现;**E0-CORRECT 补正:逐输入 schema 门(UNSUPPORTED_SCHEMA)+ 标注冻结验收门(RAN=5/PASS=5/SKIP=0 + provenance 实绑)+ claim 语义时效门**) | WP303 | 逐阶段放行;E0+证据门/标注补正 done,E1 方案 done,**E1 组件库与 fake dry-run 已实现;Codex 发现真实 sidecar CLI、真实 run_id、writer 恢复和正式证据门调用链未闭合,E1 实现停点 REOPENED**,当前=E1-CORRECT 施工 | 🔴 **E1 实现停点 REOPENED(Codex VERIFIED_FAIL)** |
| WP305 | 时钟纪元契约修复(OPEN-2):测试与 pymavlink 环境解耦,补节点重启/来源生命周期反例 | WP303 | 反例矩阵全绿,独立复验通过 | 🟢 **代码/环境独立复验完成**(wm `750032a`,双环境:venv 22P + 容器 ran=22 fails=0);真实仿真验收归 WP307 |
| WP306 | 三独立单元:GPU 支持矩阵 / IMU covariance(C'=RCRᵀ)+types.go 反注释 / truth audit 混合匹配 fail-closed | WP303 | 各单元反例测试通过 | ⛔ 阻塞 |
| WP307 | 默认路径连续 10/10:固定 commit/镜像/场景,全 attempts 入分母 | WP304–306 | 10/10 发起/起飞/full-pass,产物完整无残留 | ⛔ 阻塞 |
| WP308 | 长稳门 + R003 收口:固定时长/漂移/断链/崩溃阈值 | WP307 | 负责人批准的长稳指标全满足 | ⛔ 阻塞 |

## 下游阻塞任务(P0/P1 未关闭前禁止进入)

- **P2 ROS1/ROS2 前端对齐**:冻结 ROS1 oracle,像素/体素/参数/消息/时序逐项 diff。⛔
- **P3 3D 无损验证**:路径 z / 体积增益 / 立体避障 / 空间探索,与 oracle 同表比较。⛔
- **P4 WorldModel 插件化接入**:GBPlanner 与 frontier_lite 等并列注册、配置选择、运行切换、独立验收。⛔
- **架构预留**:GPS-denied 多层楼梯探索只输出接口/数据结构/模块边界清单,禁止功能代码。

## 相邻技术债(并入对应 WP,不单列)

- ~~exploration/navigation cartographer 读原始 `/imu`~~ / ~~runner 探针完即 SIGKILL mission~~:
  **已修(wm `e569ecf`/`faadb2a`,2026-07-18,先红后绿 fixture 级)**;真实仿真验收并入 WP307 默认 10/10。

## P0 未执行遗留队列(登记,不擅自执行;每项列前置/决策点/验收/最迟门)

| 遗留项 | 当前状态 | 前置条件 | 负责人决策点 | 验收标准 | 最迟须在此 R003 门前完成 |
|---|---|---|---|---|---|
| 分支职责最终裁决 | 提案在 governance/README §7,未定 | 无 | 是否设 dev 分支/archive 分支职责 | 三仓分支职责成文且机械可核 | R003-门二(事实源治理) |
| Ubuntu 基准 annotated tag | 候选 `baseline/ubuntu-native-20260713`,未打 | 锚点 commit + pins 确认 | 批准打 tag | 两仓 tag 存在+说明+pins digest | R003-门八(长稳收口)前 |
| ROS1 oracle annotated tag | 候选 `oracle/ros1-gbplanner-7301b535`,未打 | 镜像 digest 落 pins | 批准打 tag | tag+ADAPTER_FREEZE+镜像 digest | P2 对齐启动前 |
| ~~governance/dependencies.yaml~~ | **已创建(2026-07-18,队列放行)**:已创建并可解析;17 个组件、LOCKED 13/UNVERIFIED 4 和八个 gitlink SHA/URL 可复核;许可信息按逐组件证据等级记录,不宣称全部 license 已验证;四项 UNVERIFIED 及升级条件见 governance/README §2 | — | — | 可解析+计数/SHA/URL 可复核(无专用 schema 验收器,归下一编号 Review) | 已关闭 |
| feat sources/ 去重 | 提案已登记,未执行 | main 为唯一快照持有者确认 | 批准删除 feat sources/ | feat 去重后闭包 delta 干净+tag 兜底 | P2 前 |
| world-model origin 只读机械保护 | 未实施(仅文档红线) | pre-push 钩子方案 | 批准增 pre-push 防护 | 可测试 pre-push 拒推 SZ-surveying | R003-门七(远端收口) |
| 回滚锚点与恢复验证 | 未建立 | Ubuntu/ROS1 tag 就绪 | 批准建锚点 | 锚点 tag + 恢复演练证据 | R003-门八 |
| runbooks/world-model-jazzy 物理重组(208 平铺→分子目录) | 已建导览 README,物理重组未做 | 全量引用清点 | 批准重组(大量 rename+manifest churn) | 引用零断链+闭包 delta 干净 | P2 前 |
| ~~Docker context 统一~~ | **已解决(2026-07-18)**:负责人批准卸载 Docker Desktop;单 system daemon,舰队 47GB 完整,config 残留已清 | — | — | 裸 docker 命令直达舰队 ✓ | 已关闭 |
| 下一编号 Review:为 dependencies.yaml 增加专用 schema/字段/枚举/状态一致性反例验收 | R003 冻结后新发现,仅登记不实现(R003-CLOSE 硬冻结规则 5) | 下一编号 Review 开启 | 负责人排期 | 专用验收器 + 反例矩阵全绿 | 下一编号 Review |
