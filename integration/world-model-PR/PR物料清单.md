# PR 物料清单(2026-07-06 更新)——要提交给 world-model 作者的东西 + jazzy 兼容诚实标注

> 🚧 **阻断(2026-07-06 晚更新):禁止提交 PR/Issue**。阻断原因**不再是"未全绿"**(run `20260706T130626` 已端到端全绿,B16 已修),而是:①**用户指示:等真 GBPlanner 桥接集成跑通后统一定稿提交**;②PR_BODY/ISSUE_BODY 需吸收 B16+基线定档数据后定稿;③frontier_lite 基线稳定性差(达标率 40%)应作为对比叙事写入。
>
> ⚠️ **重要纠偏**:本清单(07-05)把 **humble 期特性分支** 的一堆 fix(tomllib / CYCLONEDDS / gazebo-sensor COPY / mode-switch)和 **jazzy clean 分支** 混在了一起。**真正经 jazzy 实跑验证的净变更集** = clean 分支 `fix/world-model-e2e-takeoff` 的 `CLEAN_REPRO_takeoff_fixes.diff`(**仅** B1 `%%` / B3 空launch参数 / B6-7 IMU回声 / B14 RNGFND改名 / B15 死锁,**无 hack**)。tomllib 是 humble 专用(jazzy 原生有),不在 clean diff 内。以 [Bug 台账](../../docs/world-model端到端Bug台账_给作者PR.md) 为准。

## ⚠️ 一句诚实前提(2026-07-06 订正)
07-05 版说"没在 jazzy 上实际跑过"**已过时**:现已在 jazzy 干净复现并**物理起飞**(run `20260706T110405`:SIM+0.760m/电机1950/DAlt0.655m)。
**端到端 exploration 已全绿**(run `20260706T130626`,B16 后)。PR 暂停原因=用户要求等真 GBPlanner 集成跑通统一定稿 + PR_BODY/ISSUE_BODY 未定稿;frontier_lite 基线稳定性(达标率 40%)将作为对比叙事写入。

## 一、代码物料(10 个文件,全在上游代码树内)

建议**拆成两个 PR**(bug fix 与 feature 分开,作者更容易接受、也更好判断):

### PR-A:通用 / humble 兼容 bug fix(8 处改动,作者友好、兼容性最强)

| 文件 | 改了什么 | 性质 | jazzy 兼容性(诚实) |
|---|---|---|---|
| `navlab/common/toml_values.py` | `import tomllib` 加 `except ModuleNotFoundError: import tomli` | 向后兼容 | ✅ jazzy(Py3.12)有 tomllib,except 分支**不执行**,零影响。**需**在 pyproject 把 tomli 声明为 `python_version<"3.11"` 条件依赖 |
| `navlab/sim/companion/runtime/config.py` | 同上 | 向后兼容 | ✅ 同上 |
| `exploration_workflow_runtime.py.tmpl`(其中 `%%`→`%` 那一处) | 修模板渲染 bug | 纯 bug | ✅ `text/template` 不处理 `%`,jazzy 渲染也一样坏;与版本无关 |
| `navlab/common/slam/backends.py` | 跳过空值 launch 参数 | 向后兼容 | ✅ 空参本就无意义,humble/jazzy 都安全 |
| `orchestration/.../config/defaults.go` + `helpers/slam.go` | IMU 净化桥输出 topic 从 `/imu` 改 `/navlab/slam/imu`(修自吞回声) | 纯 bug | ✅ 逻辑 bug(桥订阅自己输出),与版本无关;jazzy 同样崩 |
| `orchestration/.../tasks/runtime_specs.go` | official_baseline 补 `CYCLONEDDS_URI` + gz 服务显式 `GZ_PARTITION` | 纯 bug/稳健化 | ✅ Go 疏漏 + 容器 uid/gz-transport 问题,与 ROS 版本无关 |
| `docker/images/runtime/gazebo-sensor.Dockerfile`(+4 行) | 补 `COPY` uv 托管的 Python(修悬空软链) | 纯 bug | ✅ 上游 COPY venv 不 COPY 其解释器=悬空,不论 python 版本都是 bug;jazzy 构建同样需要 |
| `fcu_controller_runtime.py.tmpl`(+6 行) | mode 优先信 config 的 GUIDED 号,不信 pymavlink 车型猜测 | 通用改进 | ✅ config 明确值(Copter=4)总是对;jazzy/任何 SITL 握手时机都更稳 |

### PR-B:新功能(我们的集成产物,2 处改动,**诚实定性为 2D 原型**)

| 文件 | 改了什么 | jazzy 兼容性 |
|---|---|---|
| `exploration_workflow_runtime.py.tmpl`(gbplanner_gain 那 ~108 行) | 新增可选策略 `gbplanner_gain`(读 OccupancyGrid、体积增益选向) | ✅ 纯 ROS2 rclpy/nav_msgs 代码,humble/jazzy API 一致;additive、默认策略不变 |
| `orchestration/.../helpers/runtime_specs.go`(+5 行) | `ExplorationWorkflowSpec` 加 `MapTopic` 透传 | ✅ additive 字段,无版本相关 |

> **PR-B 必须在描述里诚实写明**:这是 **2D 占据栅格单步原型**,**不是**完整 GBPlanner(无 RRG 图搜索、无 3D voxblox、无全局 frontier 层);真正忠于原文的集成走 ros1_bridge 桥接原版(见项目 `integration/ros1_bridge/`)。不要说"已完整集成 GBPlanner"。

## 二、md 物料(在 `integration/world-model-PR/`)

| 文件 | 用途 | 是否进 PR |
|---|---|---|
| `PR_BODY.md` / `ISSUE_BODY.md` | PR/Issue 纯正文(gh --body-file 直接用) | ✅ 提交时用 |
| `PR_description.md` / `ISSUE_frontier_lite_and_compile_bug.md` | 带说明的完整版 | 参考 |
| `手动提交PR与Issue指南.md` | 教你 fork+push+开PR 的分步操作 | 操作用 |
| `gbplanner_gain.patch` | 改动补丁备份 | 附证据 |
| `rendered_*.py` | 渲染脚本证据(两策略都 py_compile 过) | 附证据 |
| **本清单 + `docs/PR兼容性与jazzy评估.md`** | jazzy 兼容论证 | PR 描述引用 |

> 🚧 **阻断项(2026-07-06)**:`PR_BODY.md` / `ISSUE_BODY.md` 已从"tomllib+%%+gbplanner_gain"旧版**重写为当前草稿**(顶部有 DRAFT 横幅、覆盖 B1/B3/B6/B14/B15),但**仍是草稿、禁止提交**,须等 exploration 端到端全绿 + frontier_lite 真实指标(对照组)后定稿。`PR_description.md` / `ISSUE_frontier_lite_and_compile_bug.md` = 早期作废版,勿用。

## 三、humble 专用物料——**明确不进 PR**(避免污染作者 jazzy 环境)

这些在**我们项目仓的独立目录**,是"如何在 humble 复现"的附录,**不提交给作者**:
- `runbooks/world-model-humble-fixes/`(gazebo-sensor 改系统 Py3.10 venv、ydlidar declare_parameter 补丁、robot.launch.py 薄层补丁、build 脚本)
- 本机 tomli vendor、keepalive 等环境操作

## 四、提交前 checklist(达"做好"标准后执行)
- [x] exploration 端到端跑通(run `20260706T130626` 全绿);frontier_lite 基线已定档(达标率 40%,docs/基线定档)
- [ ] **真 GBPlanner 桥接集成跑通(用户要求的统一定稿前置)**
- [ ] world-model 分支 rebase 到最新 origin/main(已确认=09a5aa4,无更新)
- [ ] pyproject 把 tomli 设为 `<3.11` 条件依赖
- [ ] PR_BODY 补齐到 8 项 bug fix；PR-B 诚实标注 2D 原型
- [ ] (可选,若要 100% 确证)重建 jazzy 实跑验证兼容性
- [ ] 用 ai4sci-z fork + 提交(照手动提交指南)
