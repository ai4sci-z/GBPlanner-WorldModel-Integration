# world-model PR 物料包(给作者的有含金量 PR + Issue)

> 🚧 **阻断:当前禁止提交 PR/Issue(2026-07-06)**。前置未满足:exploration 端到端未全绿(剩 `frame_contract_probe`:`/tf_static` QoS + `/ap/v1/pose/filtered` 时序;`accepted_goals` 2<3)。
>
> **事实源不是本目录正文,而是** [`docs/world-model端到端Bug台账_给作者PR.md`](../../docs/world-model端到端Bug台账_给作者PR.md)。`PR_BODY.md` / `ISSUE_BODY.md` 已重写为**当前草稿(顶部有 DRAFT 横幅)**;`PR_description.md` / `ISSUE_frontier_lite_and_compile_bug.md` 为**早期作废版**,勿用。

本目录是准备提交给 `SZ-surveying/world-model` 作者的材料。clean 验证分支在 WSL
`~/ws-clean/world-model` 的 **`fix/world-model-e2e-takeoff`**(提交链 `79643b9` 真bug+死锁 → `77d951a` 撤 3 参数 hack);净变更集 = `CLEAN_REPRO_takeoff_fixes.diff`(无 hack,153 行)。原 `feat/gbplanner-gain-exploration-strategy` 分支承载 `gbplanner_gain` 特性。

## 真实变更链(以净 diff 为准,非旧 tomllib 叙事)

1. **B1 `%%`→`%`**(exploration 生成脚本 `text/template` 原样落盘 → SyntaxError)。
2. **B3 跳过空 launch 参数**(ROS2 humble/jazzy 拒绝空 `name:=`)。
3. **B6/B7 SLAM IMU 自吞回声**(桥 output 默认 `/imu` = source → cartographer Non-sorted abort;改 `/navlab/slam/imu`)。
4. **B14 测距仪参数名漂移**(`RNGFND1_MIN_CM`→4.5 新名 `RNGFND1_MIN`,旧名被固件静默无视 → 高度源死)。
5. **B15 起飞死锁(关键)**(起飞完成前不转发探索 intent,否则 hold 覆盖 GUIDED 爬升 → 死锁;加 `bootstrap_ready` 门)。
6. **feat `gbplanner_gain`**:可选、读占据栅格按 2D 体积增益选向。诚实:**2D 原型,非完整 GBPlanner**。
7. **不进 PR(已撤并提交)**:3 个参数 hack(`DISARM_DELAY 0`/`EK3_SRC1_POSZ 1`/`readiness 90`)——不符合物理实际、起飞不需要。

> ⚠️ 历史订正:早期把头号根因说成 tomllib 是 humble 语境;作者仓库是 jazzy,tomllib 原生存在。jazzy 上的真实端到端 blocker 是上面 B1/B3/B6/B14/B15。

## 文件清单

| 文件 | 用途 |
|---|---|
| `手动提交PR与Issue指南.md` | **先看这个** —— 教你逐步把 Issue + PR 亲手提交上去(gh 命令 / 网页两条路) |
| `ISSUE_frontier_lite_and_compile_bug.md` | Issue 全文(含说明) |
| `PR_description.md` | PR 全文(含说明) |
| `ISSUE_BODY.md` / `PR_BODY.md` | 纯正文版,供 `gh ... --body-file` 直接引用 |
| `gbplanner_gain.patch` | 改动补丁备份(`git diff main...feat/...`) |
| `rendered_frontier_lite.py` / `rendered_gbplanner_gain.py` | 渲染后的脚本,两者均 `py_compile` 通过(证据) |

## 改动文件(在 world-model 仓库里)

- `orchestration/sim/internal/tasks/helpers/runtime_specs.go`(+5):`ExplorationWorkflowSpec` 加 `MapTopic`,透传 `map_topic`
- `orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl`(+108/-3):bugfix + gbplanner_gain 决策

## 验证结论(已实测)

- `go build ./...` / `go vet` / `go test ./internal/tasks/helpers/` 全过
- 两种策略渲染出的脚本 `python3 -m py_compile` 均通过
- `config.toml`(本机 humble 改动)**未**进入 PR 的两个 commit

## 怎么算"任务真完成"

按 mentor 要求,终点是**作者收到一个有含金量、可用的 PR + Issue**。等你照 `手动提交PR与Issue指南.md`
提交后,把 **Issue 链接 + PR 链接**发我,我把链接存进 `TASKS.md` / `README.md`,任务即闭环。
