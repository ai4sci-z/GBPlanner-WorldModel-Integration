# 治理清单(R003 动作八 / 验收门一 · 2026-07-16)

> 本目录 = 三工作目录全量 tracked-path 五态清单与治理决议记录。
> 生成器:`generate_manifest.py`(NUL-safe;R003 代码清单 30 文件审查状态已注种)。
> 再生成:`python3 generate_manifest.py <worktree> <main|feat|wm> <out.tsv>`

## 清单文件与分类计数

| worktree | HEAD(生成时) | 文件数 | CURRENT_AUTHORITY | ACTIVE_REFERENCE | FROZEN_EVIDENCE | ARCHIVE | THIRD_PARTY |
|---|---|---:|---:|---:|---:|---:|---:|
| GBPlanner-WorldModel-Integration(main) | 0aa9d55 | 990 | 1 | 243 | 69 | 85 | 592 |
| gbp-feat(feat/gbplanner-ros2-port) | 17db3ba | 1433 | 90 | 368 | 0 | 14 | 961 |
| world-model(fix/world-model-e2e-takeoff) | 288b486 | 609 | 403 | 197 | 0 | 0 | 9 |

audit_status 口径:第一方未逐行审查 = `UNVERIFIED`(不得写成通过);R003 代码清单 30 文件
按原判注种(VERIFIED_PASS×2 / VERIFIED_FAIL×6 / PARTIAL×18 / UNVERIFIED×4,见 manifest_wm.tsv);
第三方 = `THIRD_PARTY_LOCKED`(锁来源/SHA/边界,不做逐行人审)。

## 重复事实源判定(已量化)

1. **WorldModel 源码三重保存**:真仓 `/home/ai4s/projects/world-model`(权威)
   ∣ main `sources/`(592 文件快照)∣ feat `sources/`(同源快照,随分支携带)。
   **权威裁定:真仓唯一权威;两处 `sources/` 均为冻结快照(THIRD_PARTY),
   由 `sources/MANIFEST.yaml` 锁 upstream/commit/license。**
2. **构建参与核验(2026-07-16 实测)**:feat `ros2_port` 的 CMake/package.xml/脚本
   与 wm `orchestration` 的 Go 源码均无对 `sources/` 的引用——**快照不进入任何当前构建**(grep 零命中)。
3. **去重处置提案(未执行,待负责人批准后按"先证可恢复再动"执行)**:
   feat 分支的 `sources/` 与 main 同源冗余,候选处置 = 在 feat 分支删除、以 main 为唯一快照持有者
   (git 历史天然可恢复,另打 tag 兜底)。**本阶段只登记,不移动。**
4. **分支职责**:main = 治理/证据/状态入口;feat = ROS2 迁移施工(`ros2_port/` 90 个第一方文件);
   wm fix 分支 = 仿真与 B17–B22 实现。dev/archive 分支方案与基准 tag(Ubuntu 基线、ROS1 oracle)
   属验收门一余项,列阶段二遗留(见 CURRENT_STATUS)。

## 唯一入口决议(2026-07-16 负责人批准)

- **唯一当前状态入口 = `CURRENT_STATUS.md`**(main 分支)。
- **唯一问题台账 = `docs/world-model端到端Bug台账_给作者PR.md`**(B 编号 + OPEN 编号)。
- 其余(TASKS/接力棒/README/文档索引/HANDOVER)降为专项事实源或引用,不承载全局状态。
- 历史证据(runbooks evidence、archive)只读,只加指针不改数值。
