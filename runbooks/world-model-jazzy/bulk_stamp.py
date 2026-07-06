#!/usr/bin/env python3
# 给历史/进展类项目文档批量盖"状态戳"(幂等:已盖则跳过),指向当前事实源。
# 保留原文件换行风格,不动正文。只在文件最前面插入一段引用块。
import os

BASE = "/mnt/c/CCproject/GBPlanner-WorldModel-Integration"
MARK = "状态戳(2026-07-06)"

# (相对 BASE 的 posix 路径, 从该文件所在目录到仓库根的前缀)
TARGETS = [
    ("RESUME_恢复文档.md", ""),
    ("GBPlanner集成施工手册.md", ""),
    ("交接文档_给Codex接管.md", ""),
    ("文档索引.md", ""),
    ("接力棒_当前值班.md", ""),
    ("双Agent交替协作协议.md", ""),
    ("docs/jazzy全栈重建_施工指引.md", "../"),
    ("docs/预研A_构建排错记录.md", "../"),
    ("docs/预研A_复现worldmodel.md", "../"),
    ("docs/运行时排错记录_humble.md", "../"),
    ("docs/预研A排错战役实录_35轮实验全解.md", "../"),
    ("docs/镜像探索复盘.md", "../"),
    ("docs/集成机制与frontier_lite缺陷_核心发现.md", "../"),
    ("docs/对比实验与缺陷论证设计.md", "../"),
    ("docs/预研B_仿真实跑排错记录.md", "../"),
    ("docs/预研B_复现GBPlanner.md", "../"),
    ("docs/仓库导览_worldmodel与gbplanner.md", "../"),
    ("docs/WSL使用与复现.md", "../"),
    ("docs/操作手册_如何查看与演示.md", "../"),
    ("docs/实跑操作手册_图文版.md", "../"),
    ("docs/体积增益与RViz界面详解.md", "../"),
    ("docs/算法核心演示_体积增益选路.md", "../"),
    ("docs/GBPlanner原始论文与代码对应关系.md", "../"),
    ("docs/桥接接口规格.md", "../"),
    ("docs/手机Claude_RemoteControl.md", "../"),
    ("notes/环境就绪状态_2026-06-29.md", "../"),
    ("notes/进展_2026-06-29.md", "../"),
    ("notes/exploration集成接口_frontier_lite.md", "../"),
    ("integration/ros1_bridge/README_阶段4桥接设计.md", "../../"),
    ("code/gbplanner_core/README.md", "../../"),
    ("launchers/README.md", "../"),
]


def stamp_for(prefix):
    resume = prefix + "RESUME_新窗口接管_2026-07-06.md"
    ledger = prefix + "docs/world-model端到端Bug台账_给作者PR.md"
    return (
        "> 📌 **" + MARK + "**:本文含历史阶段内容。**当前权威状态**以 "
        "[RESUME_新窗口接管_2026-07-06.md](" + resume + ") + "
        "[Bug 台账](" + ledger + ") 为准。要点:jazzy 镜像 **9/9 已完成并开箱验真**;"
        "无 hack 配置**物理起飞已复现**(run 20260706T110405:SIM+0.76m/电机1950/DAlt0.655m);"
        "**端到端 exploration 尚未全绿**(剩 frame_contract_probe:/tf_static=QoS、"
        "/ap/v1/pose/filtered=时序非QoS、accepted_goals 2<3);**未提交 PR**。\n\n"
    )


done, skip, missing = [], [], []
for rel, prefix in TARGETS:
    path = os.path.join(BASE, rel)
    if not os.path.exists(path):
        missing.append(rel)
        continue
    data = open(path, encoding="utf-8", newline="").read()
    if MARK in data:
        skip.append(rel)
        continue
    nl = "\r\n" if "\r\n" in data else "\n"
    stamp = stamp_for(prefix).replace("\n", nl)
    open(path, "w", encoding="utf-8", newline="").write(stamp + data)
    done.append(rel)

print("STAMPED (%d):" % len(done))
for r in done:
    print("  +", r)
print("SKIPPED already-stamped (%d):" % len(skip), skip)
print("MISSING (%d):" % len(missing), missing)
