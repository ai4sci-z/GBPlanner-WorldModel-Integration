#!/usr/bin/env python3
# 状态戳升级(Codex 第二轮 P1):把旧戳(未全绿口径)整段替换为当前权威口径。幂等。
import os, re

BASE = "/mnt/c/CCproject/GBPlanner-WorldModel-Integration"
OLD_MARK = "状态戳(2026-07-06)"
NEW_MARK = "状态戳(2026-07-06 晚·全绿后)"

def new_stamp(prefix):
    resume = prefix + "RESUME_新窗口接管_2026-07-06.md"
    ledger = prefix + "docs/world-model端到端Bug台账_给作者PR.md"
    return (
        "> 📌 **" + NEW_MARK + "**:本文含历史阶段内容。**当前权威状态**以 "
        "[RESUME_新窗口接管_2026-07-06.md](" + resume + ") + "
        "[Bug 台账](" + ledger + ") 为准。要点:jazzy 9/9 已验真;"
        "**run `20260706T130626` 已端到端全绿**(TASK_STATUS_OK/4探针全ok/3目标/SIM+0.72m,无hack,B15+B16 已修);"
        "但 frontier_lite 多跑基线**稳定性差**(6次全绿2/6,达标率40%,根因=启动耗时蚕食探索窗口);"
        "当前主线=**B2.5 自写薄桥接真 GBPlanner**(官方 ros1_bridge 与 zenoh 均已实验判死)→3D lidar(官方 lidar_3d 组件)→同口径对比;"
        "**PR 延后**(用户指示:等最终桥接跑通后统一定稿)。\n\n"
    )

count = 0
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d not in ("node_modules", "sources", ".git", "build")]
    for fn in files:
        if not fn.endswith(".md"):
            continue
        path = os.path.join(root, fn)
        data = open(path, encoding="utf-8", newline="").read()
        if OLD_MARK not in data or NEW_MARK in data:
            continue
        rel = os.path.relpath(root, BASE).replace("\\", "/")
        prefix = "" if rel == "." else "../" * (rel.count("/") + 1)
        nl = "\r\n" if "\r\n" in data else "\n"
        stamp = new_stamp(prefix).replace("\n", nl)
        # 旧戳=以 "> 📌 **状态戳(2026-07-06)**" 开头到首个空行的整段
        pattern = re.compile(r"> 📌 \*\*" + re.escape(OLD_MARK) + r"\*\*.*?(\r?\n){2}", re.S)
        newdata, n = pattern.subn(stamp, data, count=1)
        if n:
            open(path, "w", encoding="utf-8", newline="").write(newdata)
            count += 1
            print("RESTAMPED:", os.path.relpath(path, BASE))

print("total restamped:", count)
