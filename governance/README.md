# 治理清单与闭包协议(R003-S2-FIX · 2026-07-16)

> 本目录 = 三工作目录全量 tracked-path 五态清单、闭包协议、claim manifest 与治理决议。
> 生成器:`generate_manifest.py`(27 项正反例测试 `test_generate_manifest.sh`)。

## 1. 闭包协议(解决"清单提交即过期")

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

`49b111d` 的 `runbooks/.../wait_batch.sh` + `test_wait_batch.sh` = **WP303 的冻结未验收草稿,
fixture(timeout)存在失败**;不计入 R003-S2-FIX 成果;WP303 正式开始时从方案停点重审,
负责人可要求保留/重做/废弃。
