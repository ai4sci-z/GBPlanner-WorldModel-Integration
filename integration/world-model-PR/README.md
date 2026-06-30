# world-model PR 物料包(给作者的有含金量 PR + Issue)

本目录是**准备提交给 `SZ-surveying/world-model` 作者**的完整材料。代码改动已在 WSL
`~/ws/world-model` 的分支 **`feat/gbplanner-gain-exploration-strategy`** 上 commit 完毕并验证通过。

## 这份 PR 做了两件事

1. **修真 bug**:exploration 工作流模板渲染出的 Python **无法编译**(`pattern[goal_index %% len(pattern)]`,
   `%%` 经 `text/template` 原样落盘 → `SyntaxError`)。改成单 `%`。
   —— 这很可能是之前 exploration 运行时起不来的根因之一。
2. **加真功能**:新增可选探索策略 `gbplanner_gain`,**读 SLAM 占据栅格、按体积增益选方向**
   (GBPlanner 核心思想,arXiv:2201.07067),替代只会循环 3 个写死动作、不看地图的 `frontier_lite`。
   加法式、可配置、不动默认行为。

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
