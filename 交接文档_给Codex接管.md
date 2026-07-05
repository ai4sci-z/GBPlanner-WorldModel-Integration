# 交接文档 · 把本项目转给 Codex 接管(2026-07-05)

> 由 Claude Code 撰写,交给 Codex(或任何接手 agent)。**先读本文第 1 节做环境自检,再决定能接哪一档任务——不要跳过。**

## 0. 先读这四份(顺序别乱)
1. 本文(判断你能接哪一档)
2. `RESUME_恢复文档.md` 顶部 `AGENT DIRECTIVES` + `CURRENT_TOP_PRIORITY_2026_07_05`
3. `docs/jazzy全栈重建_施工指引.md`(当前主线的完整方案)
4. `README.md`(全景)+ `项目简洁汇报.md`(一页看懂)

## 1. ⚠️ 环境前提自检(接手前必跑,决定你能干哪一档)
主线任务(jazzy 全栈)**重度依赖本机状态**,大量东西**不在 git 里**。先跑这 6 条,确认你能访问:
```bash
# ① 你能操作这台机器的 WSL 吗?
wsl -d Ubuntu-22.04 bash -c "whoami; lsb_release -a 2>/dev/null | grep Release"   # 应为 ai4s / 22.04
# ② docker 可用、且能看到已构建的镜像吗?(关键!这些不在 git)
wsl -d Ubuntu-22.04 bash -c "docker images | grep -cE 'navlab.*(humble|jazzy)'"     # 应 ≥ 13(9 humble + 5 jazzy)
# ③ world-model 本地仓库+我们的修复分支在吗?
wsl -d Ubuntu-22.04 bash -c "cd ~/ws/world-model && git branch --show-current && git log --oneline -3"
# ④ 能改文件吗?(不是只读)
ls -la /c/CCproject/GBPlanner-WorldModel-Integration/README.md
# ⑤ 能跑长后台任务吗?(镜像构建几小时)
# ⑥ 有网络/代理拉镜像吗?(clash 127.0.0.1:7897)
wsl -d Ubuntu-22.04 bash -c "curl -s -o /dev/null -w '%{http_code}' -m 8 https://github.com"   # 200 或经代理 200
```

**判断规则:**
- **6 条全绿** → 你有完整执行环境,可接**主线(jazzy 全栈重建)**。跳到第 2 节。
- **②③ 不绿**(看不到镜像/仓库,或在别的机器/云沙箱)→ **你接不了主线**:那些镜像和本地分支是本机状态,你从零重建要几小时且重解所有坑。→ 跳到第 3 节(降级为你擅长的文档/review 工作)。
- **④ 不绿**(只读,不能改文件)→ 同上,做第 3 节。

## 2. 若环境完整:主线 = jazzy 全栈重建(照施工指引干)
目标:**在 jazzy 上把 exploration + gbplanner_gain 跑通**(作者环境=jazzy 铁证,PR 必须 jazzy 兼容否则白干)。
- 完整方案、缺哪 4 个 jazzy 镜像、每个的已知坑+修法、构建命令、脚本铁律 → **全在 `docs/jazzy全栈重建_施工指引.md`**,照它逐步干。
- **铁律**:只信 jazzy 实跑 + `docker images` 真镜像,不信退出码(已抓多次假成功);改文件脚本用绝对路径 + `git checkout` 恢复(Claude 栽过 3 次 cwd bug);WSL 跑容器前挂 keepalive(空闲关机杀 docker);变量在 `wsl bash -c` 里常被吞→写脚本文件执行。
- **血泪教训**:代码级"论证兼容"不可靠——Claude 论证 `d8ff119` 兼容,jazzy 实测直接 `COPY failed`。必须实跑。

## 3. 若环境受限(只读/别的机器):做你擅长且不依赖本机的活
这些**只需读 git 里的文档/源码**,是 Codex 已经在做的强项,直接接:
- **打磨 PR/Issue 文案**:`integration/world-model-PR/PR_BODY.md`、`ISSUE_BODY.md` 补齐到 10 项修复、诚实定性 gbplanner_gain 为 2D 原型(现在还停在早期 3 项)。
- **对比实验设计**:`docs/对比实验与缺陷论证设计.md` 加"证据状态"列(已实测/源码推断/待实测)。
- **论文↔代码**:`docs/GBPlanner原始论文与代码对应关系.md` 可继续深化(原始论文 `sources/GBPlanner原始论文_JFR2020_Dang_et_al.pdf`)。
- **汇报材料**:组会讲稿、答辩问答(你 04_汇报材料 已有基础)。
- ⚠️ **不要碰的**:jazzy/humble 全栈实跑、改 world-model 代码/Dockerfile、跑 docker——没本机环境做不了,别假装做了(项目铁律:绝不造假)。

## 4. 关键本机状态清单(不在 git,最容易被忽略)
| 状态 | 位置 | 说明 |
|---|---|---|
| world-model 本地分支 | WSL `~/ws/world-model` 分支 `feat/gbplanner-gain-exploration-strategy` | 含 10 个修复提交,基于上游 `09a5aa4` |
| 未提交本地改动 | 同上 | `config.toml`(distro=humble 本机跑用)、`navlab/sim/gazebo_sensor/cli.py`(坑#7 QoS,PR前要补交)、`tomli/` vendor |
| 已构建镜像 | 本机 docker | 9 个 `navlab/*:humble-latest` + 5 个 `*:jazzy-latest`(**重建要几小时**) |
| 环境配置 | 本机 | clash 代理 7897、docker daemon 代理、WSL keepalive、Go 1.24 在 `/usr/local/go/bin` |

## 5. 当前进度一句话(交接锚点)
预研B ✅完整(GBPlanner 官方仿真自主探索+量化);预研A humble 端 FCU 已过 GUIDED+arm(坑#14修好),卡 takeoff(EKF/VisOdom 深水区,疑 humble 特有);**主线已转向 jazzy 全栈重建**(作者环境=jazzy,PR 必须 jazzy 兼容)。gbplanner_gain 是 2D 单步原型(非完整 GBPlanner);真集成走 ros1_bridge 桥接原版(地基已落 `integration/ros1_bridge/`)。
