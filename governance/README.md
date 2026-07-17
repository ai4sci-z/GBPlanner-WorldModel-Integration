# 治理清单与闭包协议(R003-S2-FIX · 2026-07-16)

> 本目录 = 三工作目录全量 tracked-path 五态清单、闭包协议、claim manifest 与治理决议。
> 生成器:`generate_manifest.py`(正反例测试 `test_generate_manifest.sh`,数量与分项以套件输出为准)。

## 1. 闭包协议与两个机器门(阶段 B 修订)

**两个独立机器门(GOV-03)**,由 `generate_manifest.py` 分立实现:

- `--verify-bound`(bound_commit_closure):对清单头部绑定 commit 校验——路径集合==该 commit
  的 git tree;逐行 review_commit==绑定 commit;逐行 lines==对应 blob 行数(gitlink=-1,
  symlink 跳过并计数);category==分类器重算;audit_status==登记来源重算;格式/枚举合法。
  退出码:0 过 / 4 集合违规 / 5 格式引用违规 / 6 行事实违规。
- `--verify-current`(current_worktree_closure):当前 HEAD tracked 集合相对清单的
  added/removed、untracked、tracked-but-missing、冲突、脏改动逐类列出,任一非零 → rc=7。

**audit_source 注册表**(audit_status 的机器可追溯来源,生成与校验共用同一注册表):
①`R003_CODE_STATUS` 种子表(30 条,来源=R003 CODE_REVIEW_MANIFEST 原判);②第三方规则
`third_party_audit`(本轮恒 UNVERIFIED,依据 §2 缺口清单);③其余第一方=默认 UNVERIFIED。
**verifier 能证明**:清单与绑定 commit 的路径集合/逐行行数/分类器输出一致,audit_status
与上述注册来源一致(来源存在且格式完整),当前工作树无漂移。
**verifier 不能证明**:audit_status 所代表的审查结论本身是否正确——那是人工审查产物,
机器只验证"未被篡改且可追溯到登记来源",不验证审查质量(GOV-04 诚实契约)。

## 1b. 闭包协议(解决"清单提交即过期")

采用**两提交零路径增量**方案:

1. 治理内容(生成器/测试/claim manifest/文档纠错)全部先行提交,最后一个此类提交记为
   **review commit(R)**——三份 manifest 头部 `HEAD=` 绑定 R。
2. 生成 manifest 后,以 `--verify` 对 **R 的 `git ls-tree`** 做集合相等判定(通过条件:
   missing=0 / extra=0 / duplicate=0;枚举与字段同步校验)。
3. 最终提交(C4)**只修改既有 tracked 文件**(三份 TSV + 计数刷新),不增删任何路径
   ⇒ `sets(C4) == sets(R)`,"绑定 R"与"覆盖当前 HEAD"同时成立且被 `--verify` 的
   `delta_vs_current` 行独立证明(added=0 / removed=0)。
4. 此后任何新增路径的提交都会使 `--verify` 的 delta 变为非零——**清单过期是可机器检测的**,
   每个阶段收口必须重跑 `--verify` 并报告 review_commit / current_head / delta。

每仓收口数字(review_commit、tracked、rows、missing/extra/duplicate、delta)见各 TSV 头部与
阶段收口报告;本 README 不复制易过期数值。

## 2. 第三方锁定判定(本轮 LOCKED = 0)

**判定规则**:`THIRD_PARTY_LOCKED` 要求组件记录五要素齐备且机器可解析——upstream、
commit/tag/digest、license(或明确"未声明"+风险标记)、build role、恢复方法。
任一缺失 → `THIRD_PARTY_UNVERIFIED`。

**本轮全部第三方为 UNVERIFIED,逐组件缺口**:

| 组件 | 已有 | 缺口(升级 LOCKED 的条件) |
|---|---|---|
| main `sources/world-model-源码/`(588 文件) | upstream、恢复方式(MANIFEST.yaml) | **快照未钉 commit;上游无 LICENSE**(需钉快照对应上游 SHA + license 风险标记) |
| main `sources/GBPlanner原始论文.pdf` | 出处 DOI | license 字段缺(出版物版权,需明确标注) |
| feat `sources/**`(592 项,含 2 个遗留损坏 gitlink) | — | **feat 分支无 MANIFEST.yaml**;需去重或补记录(依赖的 main commit 也须记录) |
| feat vendored voxblox(~370 文件) | 基底 pin d08e9d4(ros2_port/README) | per-component license 记录缺;第一方补丁边界未成文 |
| wm 8 个 gitlink | upstream+SHA(.gitmodules、pins_2026-07-14.yaml) | per-component license 与 build role 记录缺 |

注:main `sources/MANIFEST.yaml`、`sources/README.md`、mentor 任务文档为**第一方治理资产**
(ACTIVE_REFERENCE),不计第三方。

## 3. 构建不引用快照的核验(2026-07-16 重建,逐段 rc)

扫描目标:`sources/`、`/archive/` 是否进入 feat/wm 的构建、镜像、启动或运行输入。
每段独立捕获 grep 退出码(rc=1 即零命中;此前"管道取 head 退出码"的旧证据作废)。

| 类别 | 范围与文件类型 | 结果 |
|---|---|---|
| 构建配置 | feat ros2_port + wm navlab/orchestration 的 CMakeLists/*.cmake/package.xml/setup.py | 零命中(rc=1)×2 |
| 脚本 | feat ros2_port+runbooks、wm navlab/orchestration/docker 的 *.sh/*.py/*.go | feat 命中 13 处,**全部在单文件 `runbooks/world-model-jazzy/bulk_label.py`**(文档标签工具的数据字符串,非构建/运行输入);wm 零命中(rc=1) |
| 镜像上下文 | wm docker + feat 全部 Dockerfile 的 sources/archive 引用 | 零命中(rc=1) |
| launch/YAML/TOML | feat ros2_port、wm navlab/orchestration | 零命中(rc=1) |
| CI 工作流 | wm .github/workflows(feat 无 .github) | 零命中(rc=1) |
| Makefile/justfile | 两仓根 | 文件不存在 |
| **运行时路径拼接** | 字符串拼接构造的路径无法静态穷尽 | **UNVERIFIED(声明盲区)** |

结论口径:**未发现静态直接引用、构建配置引用与镜像上下文引用**;运行时动态拼接为声明盲区,
不写"绝不参与任何构建"。

## 4. 唯一入口与重复事实源裁定(维持)

- 唯一当前状态入口 = `CURRENT_STATUS.md`;唯一问题台账 = `docs/world-model端到端Bug台账_给作者PR.md`
  (编号不携带状态,四维字段为准)。
- WorldModel 源码三重保存(真仓∣main sources/∣feat sources/):真仓唯一权威;
  **去重提案**(feat sources/ 删除,main 为唯一快照持有者,tag 兜底)已登记,**未执行,待负责人批准**。
- claim manifest = `claim_manifest.tsv`(活跃文档逐主张处置记录)。

## 5. 残留容器登记(§九,只登记不清理)

`zealous_curran` = ID `fdd310dee6d2…`,镜像 `navlab/official-baseline:jazzy-latest`,
Created 2026-07-15T19:00:11Z,Finished 19:02:14Z,Exit 0;
Cmd = 对 run `20260715T185957`(L1 孤儿批)执行 `slam_hover_probe.py`。
**与本项目相关**;其产物已在该 run 的 `probes/slam_hover_probe.json`。
**处置申请:建议清理(证据已落盘);未经负责人许可不删除。**
容器状态口径:运行中 0 / 已退出残留 1(禁止写"容器零")。

## 6. 冻结件登记

`49b111d` 的 `runbooks/.../wait_batch.sh` + `test_wait_batch.sh` = **历史冻结未验收草稿**
(当时 fixture timeout 失败);**已被 WP303 正式实现取代**:当前实现事实源 =
`runbooks/world-model-jazzy/l0_hover/batch_lifecycle.py` + `batch_common.sh` + `run_batch.sh`
+ `test_wait_batch.sh`(75/75)/`test_batch_common.sh`(12/12)/`test_final_rc.py`(13),
状态见 CURRENT_STATUS.md G5。本条仅作历史锚点,不再指导当前施工。

## 7. P0 余项方案停点(R003-S2-FIX-CLOSEOUT;**只方案,不执行**,执行动作全部待负责人批准)

1. **分支职责方案**:main = 治理/证据/状态唯一入口(维持现状);`feat/gbplanner-ros2-port` =
   ROS2 迁移唯一施工分支(worktree gbp-feat);archive 职责由 main 内 `docs/archive/` + `archive/`
   目录承担,**不新设 archive 分支**;dev 分支暂不设(单执行者+停点审查流下分支矩阵成本>收益,
   若并行开发出现再议——列为负责人决策项)。wm:`fix/world-model-e2e-takeoff` = 唯一施工分支,
   `backup` = 授权镜像,`origin` = 上游只读(远端更名 upstream/authorized 提案见补充令 §十三,待批)。
   无损实施:历史锚点一律 annotated tag(先批后打),不重写历史、不删分支。
2. **Ubuntu 基准 tag 候选**:名称 `baseline/ubuntu-native-20260713`;锚点 = wm `8df2690`
   (GATE-4 双死锁修复,当时 live 窄验收绿)+ 主仓 gate4_native_pass_evidence 时点 commit +
   `pins_2026-07-14.yaml`(9 镜像 ID/ArduPilot SHA);场景 = stage6/gate4 live 口径;
   **验收等级 = 历史窄验收(短窗),非稳定性宣称**(该绿后被 GATE-4b 重开)。待批动作:两仓打 tag。
3. **ROS1 oracle tag 候选**:名称 `oracle/ros1-gbplanner-7301b535`;锚点 = gbplanner-ref 镜像
   (10.7GB,`gbplanner_ros@7301b535`)+ 适配器冻结清单 `integration/ros1_bridge/ADAPTER_FREEZE.md`
   + 桥接期 stage1–5 证据;输入 = stage 证据 rosbag 与参数集;已知限制 = ROS1 noetic 容器、
   2D SLAM 语境、公平对比为窗口口径。待批动作:主仓打 tag + 镜像 digest 落 pins。
4. **机器可读依赖清单**:唯一位置候选 `governance/dependencies.yaml`
   (**新增路径将改变闭包 delta——创建必须与 manifest 再生成同批**);schema:
   `{component, kind: os|ros|docker-image|pip|go|submodule|vendor|snapshot, name, version_or_sha,
   digest, source_url, license, build_role, pinned_by, notes}`;初始条目来源 =
   pins_2026-07-14.yaml + wm .gitmodules + sources/MANIFEST.yaml + ros2_port vendor 记录。
5. **历史退出容器规则(交 WP303 方案纳入)**:批结束登记退出容器(ID/关联 run/退出码),
   证据确认后按保留期清理;现存 `zealous_curran` 保留至本次收口后由负责人裁决。
6. **本轮明确未执行**:打任何 tag / 建 dev 分支 / 远端更名 / 创建 dependencies.yaml /
   feat sources 去重 / 容器清理。
