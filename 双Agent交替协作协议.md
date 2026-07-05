# 双 Agent 交替协作协议 · Claude Code ⇄ Codex(2026-07-05)

> 目的:项目重、token 5 小时封顶,让两个 AI agent **交替/并行**推进,不停摆。
> 但两个 agent 共用同一台机器、同一个 git 仓库、同一套 docker——**不设规则就会互相覆盖、git 冲突、容器打架**(本文写作时就有过:两窗口同改一仓库)。本协议就是防撞车 + 定接力。

## 0. 先认清:这不是对称接力,是"分工 + 交接"
两个 agent **能力不对等**:
- **Claude Code = 执行棒**:有 WSL/Docker/改代码/实跑能力 → **只有它能推 jazzy 全栈主线**(构建镜像、跑仿真、改 world-model)。
- **Codex = 文档/研究棒**:本 setup 下是只读旁路(它自己 README 写死"不改源码/不跑 docker")→ 做**不依赖本机环境**的活(论文、PR 文案、对比设计、汇报、review)。

→ 所以**不是**"同一件事你 5 小时我 5 小时",而是"**执行棒推主线 + 研究棒并行做支线**,谁上限了另一个继续自己那摊"。

## 1. 最高铁律:防撞车(违反必出乱子)
1. **同一时刻,`C:\CCproject` 这个 git 仓库只允许一个 agent `commit + push`。** 另一个此刻只读或只写自己独占区。
2. **同一时刻,只有一个 agent 跑 world-model 的 docker 容器**(它们抢 host 网络/容器名/资源,一起跑必崩)。
3. **谁都不 `git pull --force` / `checkout .` 覆盖工作区**(对方可能有未提交改动)。
4. 交接靠 `接力棒_当前值班.md`(第 3 节)当"锁",看它再动手。

## 2. 文件产权表(谁能改什么,绝不重叠)
| 区域 | 只能这个 agent 改 | 另一个 |
|---|---|---|
| WSL `~/ws/world-model` 分支、docker、jazzy 构建、`runbooks/world-model-jazzy/`、`runbooks/world-model-humble-fixes/` | **Claude Code(执行棒)** | 只读 |
| `Codex_GBPlanner_工作区/`(桌面) | **Codex** | 只读 |
| **PR 文案**:`integration/world-model-PR/PR_BODY.md`、`ISSUE_BODY.md`、`PR物料清单.md` | **Codex**(打磨文案)——但**执行棒改完代码后要通知**,Codex 据实更新 | 执行棒只提事实 |
| `docs/对比实验与缺陷论证设计.md`、`docs/GBPlanner原始论文与代码对应关系.md`、汇报材料 | **Codex** | 只读 |
| `README.md`、`RESUME_恢复文档.md`、`TASKS.md`、`docs/jazzy全栈重建_施工指引.md`、`docs/运行时排错记录_humble.md` | **仅当值执行棒**(避免两边同改主文档) | 只读 |
| `sources/`、源码 | 双方只读 | — |

## 3. 接力棒文件(锁 + 路由)——**每次动手前先读,收工时更新**
根目录维护 `接力棒_当前值班.md`,格式:
```
当前值班执行棒: Claude Code   (或 交回/空闲)
在干什么: <一句话,如"构建 jazzy gazebo-sensor 镜像">
锁定区(别人别碰): WSL world-model 分支 + docker + runbooks/world-model-jazzy/
Codex 现在可并行做(不冲突): 打磨 PR_BODY 到10项 / 对比设计加证据列
下一棒从哪继续: <指向 RESUME 进展块 / 施工指引第几节>
更新时间: <时间>
```
谁开工先读它;谁收工更新它。它就是"锁"。

## 4. 交接协议(每次收工 / token 快上限前,必做)
1. `cd C:\CCproject\... && git add <自己独占区> && git commit && git push`(状态固化进 git,别留未提交改动给对方踩)。
2. 更新 `RESUME_恢复文档.md` 的进展块(干到哪、下一步)+ `接力棒_当前值班.md`(交棒/空闲)。
3. docker:若起了 world-model 容器,收工**清掉**(`docker rm -f`),别占着资源/端口给对方。
4. 一句话写清"下一棒从哪读、从哪继续"。

## 5. 真正省 token 的用法(并行分工范例)
- **Claude Code 值班**:啃 jazzy 全栈(构建 4 镜像 → e2e → gbplanner_gain 替换 frontier_lite)。
- **同期 Codex 并行**(碰的全是自己独占区,零冲突):把 `PR_BODY/ISSUE_BODY` 补到 10 项修复、对比设计加"证据状态"列、写组会讲稿、深读原始论文补对应关系。
- **Claude Code 上限** → Codex 继续文档支线;**Codex 做完** → 等 Claude Code 恢复推主线。这样两条线都不空转。

## 6. 诚实边界(别指望不可能的事)
- **若 Codex 只读**:jazzy 主线在 Claude Code token 窗口耗尽时**推进不了**(Codex 没 docker/执行环境),那段时间只能 Codex 做文档。**双只读 agent 替不了执行棒。**
- **要真正"不停摆推 jazzy"**:要么给 Codex 配**同等执行环境**(WSL/docker/改文件),让它也能当执行棒——但**第 1 节铁律照守**(同一时刻只一个 agent 碰 git/docker,靠接力棒文件轮流);要么接受"**主线单线程、支线并行**"这个现实。
- 无论谁值班:**只信 `docker images` 真产物,不信退出码;不造假**(本项目最高纪律)。
