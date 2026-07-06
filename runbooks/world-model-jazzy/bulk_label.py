#!/usr/bin/env python3
# 文档体系重整(Review_010/012):把旧"状态戳"段替换为简洁状态标签行。
# 标签体系:[CURRENT]/[ACTIVE]/[DRAFT]/[REFERENCE]/[HISTORICAL]/[OBSOLETE]
import os
import re

BASE = "/mnt/c/CCproject/GBPlanner-WorldModel-Integration"

# (相对路径, 标签, 一句说明)
PLAN = [
    # ACTIVE(当前仍在执行的技术文档)
    ("docs/桥接查证与执行计划_2026-07-06.md", "ACTIVE", "桥接技术主文档(B2.5 自写薄桥)。"),
    ("docs/对比实验与缺陷论证设计.md", "ACTIVE", "对比实验设计;基线对照组见 docs/基线定档_frontier_lite_2026-07-06.md。"),
    # REFERENCE(参考资料,非施工入口)
    ("docs/world-model端到端Bug台账_给作者PR.md", "REFERENCE", "B1~B16 修复链事实源(PR 素材)。"),
    ("docs/基线定档_frontier_lite_2026-07-06.md", "REFERENCE", "frontier_lite 基线对照组数据。"),
    ("docs/GBPlanner原始论文与代码对应关系.md", "REFERENCE", "论文↔代码对应(含 gbplanner_gain 失真标注)。"),
    ("docs/体积增益与RViz界面详解.md", "REFERENCE", "算法科普;注意:实际执行以粉线(command/trajectory)为准,绿线是 planner 候选路径。"),
    ("docs/算法核心演示_体积增益选路.md", "REFERENCE", "纯 C++ 体积增益演示。"),
    ("docs/预研B_复现GBPlanner.md", "REFERENCE", "GBPlanner 官方仿真单侧复现(不代表 world-model 集成完成)。"),
    ("docs/预研B_仿真实跑排错记录.md", "HISTORICAL", "预研B 排障过程。"),
    ("docs/仓库导览_worldmodel与gbplanner.md", "REFERENCE", "两仓库结构导览。"),
    ("docs/WSL使用与复现.md", "REFERENCE", "WSL/复现操作。"),
    ("docs/操作手册_如何查看与演示.md", "REFERENCE", "查看与演示手册(GUI 三演示建成后更新)。"),
    ("docs/实跑操作手册_图文版.md", "REFERENCE", "GBPlanner 官方仿真(预研B)演示手册,非 world-model 集成。"),
    ("docs/手机Claude_RemoteControl.md", "REFERENCE", "工具说明。"),
    ("docs/集成机制与frontier_lite缺陷_核心发现.md", "REFERENCE", "frontier_lite 缺陷论证(接大脑现行方案=B2.5 自写薄桥)。"),
    ("docs/桥接接口规格.md", "HISTORICAL", "旧接口规格(官方 ros1_bridge 语境);当前实现见 docs/桥接查证与执行计划_2026-07-06.md。"),
    ("docs/PR兼容性与jazzy评估.md", "REFERENCE", "PR 兼容性评估;PR 延后=等真 GBPlanner 集成跑通后统一定稿。"),
    ("docs/jazzy全栈重建_施工指引.md", "HISTORICAL", "镜像阶段已完成(9/9)。"),
    ("docs/镜像探索复盘.md", "HISTORICAL", "镜像阶段复盘。"),
    ("notes/exploration集成接口_frontier_lite.md", "REFERENCE", "exploration 接口契约(gate 字段以本文更正节为准)。"),
    ("code/gbplanner_core/README.md", "HISTORICAL", "gbplanner_core 重写路线=备选/理解材料,已被桥接方案取代。"),
    ("launchers/README.md", "REFERENCE", "启动器说明。"),
    ("交接文档_给Codex接管.md", "REFERENCE", "双 agent 协作边界说明(非技术状态源)。"),
    ("双Agent交替协作协议.md", "REFERENCE", "协作协议(非技术状态源)。"),
    # 归档目录(HISTORICAL/OBSOLETE 标签)
    ("docs/archive/RESUME_恢复文档.md", "HISTORICAL", "旧接管文档,已被 CURRENT_STATUS.md 取代。"),
    ("docs/archive/GBPlanner集成施工手册.md", "HISTORICAL", "早期施工总纲(含已取代的 gbplanner_core 重写路线)。"),
    ("docs/archive/预研A_复现worldmodel.md", "HISTORICAL", "预研A 过程记录(已全绿收官)。"),
    ("docs/archive/预研A_构建排错记录.md", "HISTORICAL", "预研A 构建排障。"),
    ("docs/archive/预研A排错战役实录_35轮实验全解.md", "HISTORICAL", "35 轮实验实录(方法论价值)。"),
    ("docs/archive/运行时排错记录_humble.md", "HISTORICAL", "humble 深水区排障(该线已停)。"),
    ("docs/archive/环境就绪状态_2026-06-29.md", "HISTORICAL", "环境快照。"),
    ("docs/archive/进展_2026-06-29.md", "HISTORICAL", "进展快照。"),
    ("docs/archive/01_环境搭建_WSL2_Docker_P0.md", "HISTORICAL", "环境搭建教程(环境已建成)。"),
    ("docs/archive/README_历史全景蓝图_2026-07-06.md", "HISTORICAL", "旧版主 README(全景蓝图/科普/名词表)。"),
    ("docs/archive/OBSOLETE_README_阶段4桥接设计.md", "OBSOLETE", "官方 ros1_bridge 路线已实验判死;现行=B2.5 自写薄桥(docs/桥接查证与执行计划)。禁止照做。"),
    ("docs/archive/OBSOLETE_PR_description.md", "OBSOLETE", "早期 PR 文案;现行草稿=integration/world-model-PR/PR_BODY.md(DRAFT,禁止提交)。"),
    ("docs/archive/OBSOLETE_ISSUE_frontier_lite_and_compile_bug.md", "OBSOLETE", "早期 Issue 文案;现行草稿=ISSUE_BODY.md(DRAFT,禁止提交)。"),
]

OLD_STAMP = re.compile(r"> 📌 \*\*状态戳\(2026-07-06[^\n]*\*\*.*?(\r?\n){2}", re.S)
OLD_OBS = re.compile(r"> 🗄️ \*\*早期作废版[^\n]*\n(>[^\n]*\n)*\r?\n", re.S)

count = 0
for rel, tag, note in PLAN:
    path = os.path.join(BASE, rel)
    if not os.path.exists(path):
        print("MISSING:", rel)
        continue
    data = open(path, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in data else "\n"
    depth = rel.count("/")
    prefix = "../" * depth
    label = ("> **[%s]** %s当前状态以 [CURRENT_STATUS.md](%sCURRENT_STATUS.md) 为准。" % (tag, note, prefix)) + nl + nl
    new = OLD_STAMP.sub("", data, count=1)
    new = OLD_OBS.sub("", new, count=1)
    if new.startswith("> **["):  # 已有标签,替换首段
        new = re.sub(r"^> \*\*\[[A-Z]+\]\*\*[^\n]*\r?\n\r?\n", label, new, count=1)
    else:
        new = label + new
    if new != data:
        open(path, "w", encoding="utf-8", newline="").write(new)
        count += 1
        print("LABELED[%s]: %s" % (tag, rel))

print("total labeled:", count)
