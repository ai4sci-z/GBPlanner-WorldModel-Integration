#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""表驱动:final_rc 优先级(cleanup 未完成 > evidence 缺失 > producer outcome)。
覆盖负责人指定 6 组 + 补充。任一不符退非零。"""
import importlib.util
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bl", os.path.join(here, "batch_lifecycle.py"))
bl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bl)

# (outcome, evidence, cleanup, 期望 rc)
TABLE = [
    ("SUCCEEDED", "COMPLETE",   "CLEAN",         0),   # 三轴全绿
    ("FAILED",    "COMPLETE",   "CLEAN",         10),
    ("CRASHED",   "COMPLETE",   "CLEAN",         20),
    ("TIMED_OUT", "COMPLETE",   "CLEAN",         30),
    ("CANCELLED", "COMPLETE",   "CLEAN",         40),
    ("SUCCEEDED", "INCOMPLETE", "CLEAN",         50),
    ("FAILED",    "INCOMPLETE", "CLEAN",         50),   # evidence 缺失不被 FAILED 隐藏
    ("CRASHED",   "INCOMPLETE", "CLEAN",         50),   # evidence 缺失不被 CRASHED 隐藏
    ("SUCCEEDED", "COMPLETE",   "NOT_ATTEMPTED", 60),   # cleanup 未完成不得返 0
    ("SUCCEEDED", "COMPLETE",   "REFUSED",       60),
    ("SUCCEEDED", "COMPLETE",   "RESIDUAL",      60),
    ("FAILED",    "COMPLETE",   "RESIDUAL",      60),   # cleanup 优先于 outcome
    ("SUCCEEDED", "INCOMPLETE", "RESIDUAL",      60),   # cleanup 优先于 evidence
]

bad = 0
for outcome, ev, cleanup, want in TABLE:
    got = bl.final_rc(outcome, ev, cleanup)
    tag = "OK" if got == want else "BAD"
    if got != want:
        bad += 1
    print(f"  {tag} final_rc({outcome},{ev},{cleanup}) = {got} (want {want})")
print(f"table rows={len(TABLE)} bad={bad}")
sys.exit(1 if bad else 0)
