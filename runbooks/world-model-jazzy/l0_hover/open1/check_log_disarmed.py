#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AA003 P01.3 · LOG_DISARMED 观测条件静态机器检查(零仿真/零容器)。

用法: check_log_disarmed.py <parm 文件> [<parm 文件>…]
每个文件必须:恰好一行有效 LOG_DISARMED 且值==1(注释行忽略;缺失/值非1/重复
矛盾/文件不可读 → rc=1 并逐条打印原因)。解析口径=wm mergeExternalNavParamProfile
的 strings.Fields 语义(空白分隔,首 token 为 key)。"""
import sys


def check(path):
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError as e:
        return [f"{path}: 不可读: {e}"]
    hits = []
    for i, line in enumerate(lines, 1):
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        # 与 wm paramLineKey 同口径:整 token 匹配;逗号写法(LOG_DISARMED,1)会被
        # wm 视为另一个 key——按"矛盾写法"拒绝
        if fields[0] == "LOG_DISARMED":
            hits.append((i, fields[1] if len(fields) > 1 else None))
        elif fields[0].startswith("LOG_DISARMED"):
            return [f"{path}:L{i}: 非法写法 {fields[0]!r}(wm Fields 解析不识别为 LOG_DISARMED)"]
    if not hits:
        return [f"{path}: 缺失 LOG_DISARMED(观测条件未进 profile)"]
    if len(hits) > 1:
        return [f"{path}: LOG_DISARMED 重复 {len(hits)} 次(行 {[h[0] for h in hits]}),矛盾"]
    ln, val = hits[0]
    if val != "1":
        return [f"{path}:L{ln}: LOG_DISARMED={val!r}(必须为 1)"]
    return []


def main(argv):
    if len(argv) < 2:
        print("用法: check_log_disarmed.py <parm 文件>…", file=sys.stderr)
        return 2
    errs = []
    for p in argv[1:]:
        errs += check(p)
    for e in errs:
        print(f"FAIL: {e}")
    if not errs:
        print(f"PASS: {len(argv) - 1} 个文件 LOG_DISARMED=1 唯一有效")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
