#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1C · run 身份注册表:batch_id / run_index / world_model_run_id 三身份分离。

硬规则(E1C-03.1):run_index=批内序号,不是 run_id;world_model_run_id 必须等于
真实 run 目录基名;run_dir 必须位于受观察的 world-model artifact 根内;symlink/越界/
旧目录复用失败;同 batch 内 run_id 不重复;发现=attempt 窗口内**唯一**新增且结构合法
的目录——零个或多个候选一律 UNKNOWN/INCOMPLETE,禁止猜;不得裸取"最新目录"。
零 world-model 修改:纯目录集合差 + 有界观察。

CLI:begin / resolve / finish / read / aggregate(五层分母正式聚合入口)。
"""
import argparse
import json
import os
import re
import sys
import time

import telemetry_contract as C

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCHEMA_VERSION = "wp304.run_registry.v1"
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}\.\d{9}Z$")


class RegistryError(ValueError):
    pass


def _atomic_write(path, obj):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f".{os.path.basename(path)}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    dfd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _entry_path(registry_dir, run_index):
    return os.path.join(registry_dir, f"attempt_{int(run_index)}.json")


def _snapshot(watch_dir):
    try:
        return sorted(e for e in os.listdir(watch_dir))
    except OSError:
        return None   # watch 根不可读:登记为缺,resolve 只能 UNKNOWN


def _pid_starttime(pid):
    try:
        data = open(f"/proc/{pid}/stat").read()
    except OSError:
        return None
    f = data[data.rfind(")") + 2:].split()
    return f[19] if len(f) > 19 else None


def cmd_begin(a):
    snap = _snapshot(a.watch_dir)
    entry = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": a.batch_id,
        "run_index": int(a.run_index),
        "world_model_run_id": None,
        "world_model_run_dir": None,
        "producer_pid": a.producer_pid if a.producer_pid else os.getppid(),
        "producer_pid_starttime": (a.producer_starttime
                                   or _pid_starttime(a.producer_pid or os.getppid()) or "UNKNOWN"),
        "start_utc": time.time(),
        "start_monotonic": time.monotonic(),
        "end_utc": None,
        "rc": None,
        "identity_status": "PENDING",
        "discovery_method": "pre_set_freeze",
        "watch_dir": os.path.realpath(a.watch_dir),
        "pre_set": snap,
        "phase": "begin",
    }
    _atomic_write(_entry_path(a.registry_dir, a.run_index), entry)
    print(json.dumps({"begin": True, "run_index": entry["run_index"],
                      "pre_set_size": (len(snap) if snap is not None else None)}))
    return 0


def _load_entry(registry_dir, run_index):
    p = _entry_path(registry_dir, run_index)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise RegistryError(f"registry 条目不存在: {p}")
    except (OSError, ValueError) as e:
        raise RegistryError(f"registry 条目损坏(半写?): {p}: {e}")


def _valid_new_dir(watch_dir, name):
    """结构约束:名字符合 wm run_id 模式;真实目录;非 symlink;realpath 在 watch 根内。"""
    if not RUN_ID_RE.match(name):
        return False, f"目录名不符合 run_id 模式: {name}"
    p = os.path.join(watch_dir, name)
    if os.path.islink(p):
        return False, f"symlink 目录拒绝: {name}"
    if not os.path.isdir(p):
        return False, f"非目录: {name}"
    rp = os.path.realpath(p)
    if not rp.startswith(os.path.realpath(watch_dir) + os.sep):
        return False, f"目录 realpath 越出 watch 根: {name}"
    return True, ""


def cmd_resolve(a):
    entry = _load_entry(a.registry_dir, a.run_index)
    if entry.get("pre_set") is None:
        entry["identity_status"] = "UNKNOWN"
        entry["discovery_method"] = "watch_dir_unreadable"
        entry["phase"] = "resolved"
        _atomic_write(_entry_path(a.registry_dir, a.run_index), entry)
        print(json.dumps({"resolved": False, "identity_status": "UNKNOWN",
                          "reason": "watch 根不可读"}))
        return 0
    watch = entry["watch_dir"]
    pre = set(entry["pre_set"])
    deadline = time.monotonic() + float(a.timeout_sec)
    new_names = []
    reasons = []
    while True:
        cur = _snapshot(watch)
        if cur is not None:
            fresh = sorted(set(cur) - pre)   # 集合差:旧目录 mtime 变化不算新增
            new_names = fresh
            if fresh:
                break
        if time.monotonic() >= deadline:
            break
        time.sleep(float(a.poll_sec))
    valid = []
    for name in new_names:
        ok, why = _valid_new_dir(watch, name)
        if ok:
            valid.append(name)
        else:
            reasons.append(why)
    # 唯一性核验:必须恰一个合法新增;0 或 ≥2 → UNKNOWN,禁止猜
    if len(valid) == 1:
        run_id = valid[0]
        entry["world_model_run_id"] = run_id
        entry["world_model_run_dir"] = os.path.join(watch, run_id)
        entry["identity_status"] = "RESOLVED"
        entry["discovery_method"] = "unique_new_dir_in_window"
    else:
        entry["identity_status"] = "UNKNOWN"
        entry["discovery_method"] = (f"candidates={len(valid)} invalid={len(reasons)}"
                                     + ("; " + "; ".join(reasons) if reasons else ""))
    entry["phase"] = "resolved"
    _atomic_write(_entry_path(a.registry_dir, a.run_index), entry)
    print(json.dumps({"resolved": entry["identity_status"] == "RESOLVED",
                      "identity_status": entry["identity_status"],
                      "world_model_run_id": entry["world_model_run_id"],
                      "candidates": valid, "rejected": reasons}, ensure_ascii=False))
    return 0


def cmd_finish(a):
    entry = _load_entry(a.registry_dir, a.run_index)
    entry["end_utc"] = time.time()
    entry["end_monotonic"] = time.monotonic()
    entry["rc"] = int(a.rc)
    entry["phase"] = "finished"
    _atomic_write(_entry_path(a.registry_dir, a.run_index), entry)
    print(json.dumps({"finished": True, "run_index": entry["run_index"], "rc": entry["rc"]}))
    return 0


WATCHER_STATES = ("WAITING", "RESOLVED", "UNKNOWN_ZERO_CANDIDATE",
                  "UNKNOWN_MULTIPLE_CANDIDATES", "INVALID_CANDIDATE",
                  "TIMED_OUT", "CANCELLED", "CRASHED")


def cmd_watch(a):
    """独立 registry watcher(E1L-02):producer 运行期间并发观察目录集合差,
    唯一合法新目录一出现立即原子写 RESOLVED——不等 producer 结束。
    终态∈WATCHER_STATES,全程记录 candidates/rejected/双 monotonic/身份/reason。"""
    import hashlib as _h
    import signal as _sig
    entry = _load_entry(a.registry_dir, a.run_index)
    if entry.get("pre_set") is None:
        entry.update({"identity_status": "UNKNOWN", "watcher_state": "UNKNOWN_ZERO_CANDIDATE",
                      "watcher_reason": "watch 根不可读", "phase": "watched"})
        _atomic_write(_entry_path(a.registry_dir, a.run_index), entry)
        print(json.dumps({"watch": "UNKNOWN", "reason": "watch 根不可读"}))
        return 0
    watch = entry["watch_dir"]
    pre = set(entry["pre_set"])
    me_st = _pid_starttime(os.getpid()) or "UNKNOWN"
    entry.update({"phase": "watching", "watcher_state": "WAITING",
                  "watcher_pid": os.getpid(), "watcher_pid_starttime": me_st,
                  "watcher_start_monotonic": time.monotonic(),
                  "pre_set_sha256": _h.sha256("\n".join(sorted(pre)).encode()).hexdigest(),
                  "candidates": [], "rejected_candidates": [], "watcher_reason": None})
    _atomic_write(_entry_path(a.registry_dir, a.run_index), entry)
    cancelled = {"flag": False}

    def _on_term(_s, _f):
        cancelled["flag"] = True
    _sig.signal(_sig.SIGTERM, _on_term)
    _sig.signal(_sig.SIGINT, _on_term)

    def finalize(state, reason, run_id=None, run_dir=None, valid=(), rejected=()):
        entry["watcher_state"] = state
        entry["watcher_reason"] = reason
        entry["watcher_end_monotonic"] = time.monotonic()
        entry["candidates"] = list(valid)
        entry["rejected_candidates"] = list(rejected)
        if state == "RESOLVED":
            entry["identity_status"] = "RESOLVED"
            entry["world_model_run_id"] = run_id
            entry["world_model_run_dir"] = run_dir
            entry["resolved_monotonic"] = entry["watcher_end_monotonic"]
            entry["discovery_method"] = "concurrent_watcher_unique_new_dir"
            entry["phase"] = "resolved"
        else:
            entry["identity_status"] = "UNKNOWN"
            entry["discovery_method"] = f"watcher:{state}"
            entry["phase"] = "watched"
        _atomic_write(_entry_path(a.registry_dir, a.run_index), entry)
        print(json.dumps({"watch": state, "run_id": run_id, "reason": reason},
                         ensure_ascii=False))
        return 0

    deadline = time.monotonic() + float(a.timeout_sec)
    try:
        rejected_all = []
        while True:
            if cancelled["flag"]:
                return finalize("CANCELLED", "收到 TERM/INT")
            cur = _snapshot(watch)
            if cur is not None:
                fresh = sorted(set(cur) - pre)
                if fresh:
                    valid, rejected = [], []
                    for name in fresh:
                        ok, why = _valid_new_dir(watch, name)
                        (valid.append(name) if ok else rejected.append(why))
                    rejected_all = rejected
                    if len(valid) == 1:
                        return finalize("RESOLVED", "唯一合法新增", valid[0],
                                        os.path.join(watch, valid[0]), valid, rejected)
                    if len(valid) >= 2:
                        return finalize("UNKNOWN_MULTIPLE_CANDIDATES",
                                        f"同窗多候选={valid}", valid=valid, rejected=rejected)
                    # 只有非法候选:继续等到超时(可能合法目录稍后出现)
            if time.monotonic() >= deadline:
                if rejected_all:
                    return finalize("INVALID_CANDIDATE",
                                    f"窗口内仅非法候选: {rejected_all}", rejected=rejected_all)
                return finalize("TIMED_OUT", "窗口内零候选(UNKNOWN_ZERO_CANDIDATE)")
            time.sleep(float(a.poll_sec))
    except Exception as e:  # 崩溃也留终态
        try:
            finalize("CRASHED", f"{type(e).__name__}: {e}")
        except Exception:
            pass
        return 70


def load_registry(registry_dir, batch_id=None):
    """sidecar/聚合器消费入口:全量读取 + 失败关闭校验。
    返回 {"entries": [...], "errors": [...]};错误包括半写/batch 不符/重复 index/重复 run_id。"""
    entries, errors = [], []
    if not os.path.isdir(registry_dir):
        return {"entries": [], "errors": [f"registry 目录不存在: {registry_dir}"]}
    for name in sorted(os.listdir(registry_dir)):
        if not (name.startswith("attempt_") and name.endswith(".json")):
            continue
        p = os.path.join(registry_dir, name)
        try:
            with open(p, encoding="utf-8") as f:
                e = json.load(f)
        except (OSError, ValueError) as exc:
            errors.append(f"条目损坏(半写?): {name}: {exc}")
            continue
        if e.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"未知 schema: {name}: {e.get('schema_version')!r}")
            continue
        if batch_id is not None and e.get("batch_id") != batch_id:
            errors.append(f"batch_id 不符: {name}: {e.get('batch_id')!r} != {batch_id!r}")
            continue
        rid = e.get("world_model_run_id")
        rdir = e.get("world_model_run_dir")
        if rid is not None:
            if rdir is None or os.path.basename(os.path.normpath(rdir)) != rid:
                errors.append(f"run_id 与 run_dir 基名不一致: {name}")
                continue
        entries.append(e)
    idxs = [e["run_index"] for e in entries]
    if len(idxs) != len(set(idxs)):
        errors.append(f"run_index 重复: {sorted(idxs)}")
    rids = [e["world_model_run_id"] for e in entries if e.get("world_model_run_id")]
    if len(rids) != len(set(rids)):
        errors.append(f"world_model_run_id 重复: {sorted(rids)}")
    return {"entries": entries, "errors": errors}


def cmd_read(a):
    reg = load_registry(a.registry_dir, a.batch_id or None)
    print(json.dumps(reg, ensure_ascii=False, sort_keys=True, indent=1))
    return 0 if not reg["errors"] else 1


def _attempt_key(e):
    return e["world_model_run_id"] or f"attempt_{e['run_index']}_UNRESOLVED"


def cmd_aggregate(a):
    """五层分母正式聚合入口(E1C-05.3)。权威 launched = registry attempts
    (发起即入,永不消失),不扫描成功 summary。"""
    reg = load_registry(a.registry_dir, a.batch_id or None)
    if reg["errors"]:
        print(json.dumps({"aggregate": False, "errors": reg["errors"]}, ensure_ascii=False))
        return 1
    entries = reg["entries"]
    attempts = [_attempt_key(e) for e in entries]
    corrupt = set()
    layers = {name: {"count": 0, "run_ids": [], "exclusion_reasons": {}} for name in C.LAYERS}

    def put(name, rid):
        layers[name]["run_ids"].append(rid)

    def excl(name, rid, why):
        layers[name]["exclusion_reasons"][rid] = why

    for e in entries:
        rid = _attempt_key(e)
        put("launched", rid)
        if e.get("identity_status") != "RESOLVED" or e.get("rc") is None:
            excl("infrastructure_valid", rid,
                 f"identity_status={e.get('identity_status')} rc={e.get('rc')}")
            excl("causal_analysis_eligible", rid, "not infrastructure_valid")
            excl("airborne", rid, "not causal")
            excl("full_pass", rid, "not airborne")
            continue
        put("infrastructure_valid", rid)
        run_dir = e["world_model_run_dir"]
        fs_path = os.path.join(run_dir, "telemetry", "sidecar_final_status.json")
        ev_state = "UNKNOWN"
        try:
            fs = json.load(open(fs_path, encoding="utf-8"))
            ev_state = fs.get("evidence_state", "UNKNOWN")
        except (OSError, ValueError):
            ev_state = "UNKNOWN"
        if ev_state == "CORRUPT":
            corrupt.add(rid)
            excl("causal_analysis_eligible", rid, "telemetry evidence CORRUPT")
            excl("airborne", rid, "not causal")
            excl("full_pass", rid, "not airborne")
            continue
        if ev_state != "COMPLETE":
            excl("causal_analysis_eligible", rid, f"telemetry evidence {ev_state}(required 缺)")
            excl("airborne", rid, "not causal")
            excl("full_pass", rid, "not airborne")
            continue
        put("causal_analysis_eligible", rid)
        airborne = None
        ms_path = os.path.join(run_dir, "mission_summary.json")
        try:
            ms = json.load(open(ms_path, encoding="utf-8"))
            v = ms.get("airborne_seen")
            airborne = v if isinstance(v, bool) else None
        except (OSError, ValueError):
            airborne = None
        sem = C.airborne_semantics(airborne)
        if sem == "observed_airborne":
            put("airborne", rid)
        else:
            excl("airborne", rid, f"airborne={sem}(UNKNOWN 不压 false)")
            excl("full_pass", rid, "not airborne")
            continue
        if e.get("rc") == 0:
            put("full_pass", rid)
        else:
            excl("full_pass", rid, f"attempt rc={e.get('rc')}")
    for name in C.LAYERS:
        layers[name]["count"] = len(layers[name]["run_ids"])
    C.validate_five_layers(attempts, layers, corrupt_runs=corrupt)
    out = {"schema_version": SCHEMA_VERSION, "batch_id": a.batch_id,
           "attempts_authority": attempts, "corrupt_runs": sorted(corrupt),
           "layers": layers}
    if a.output:
        _atomic_write(a.output, out)
    print(json.dumps({"aggregate": True,
                      "counts": {k: layers[k]["count"] for k in C.LAYERS}}, ensure_ascii=False))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run_registry")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pb = sub.add_parser("begin")
    pb.add_argument("--registry-dir", required=True)
    pb.add_argument("--batch-id", required=True)
    pb.add_argument("--run-index", required=True, type=int)
    pb.add_argument("--watch-dir", required=True)
    pb.add_argument("--producer-pid", type=int, default=None)
    pb.add_argument("--producer-starttime", default=None)
    pr = sub.add_parser("resolve")
    pr.add_argument("--registry-dir", required=True)
    pr.add_argument("--run-index", required=True, type=int)
    pr.add_argument("--timeout-sec", default="2.0")
    pr.add_argument("--poll-sec", default="0.05")
    pw = sub.add_parser("watch")
    pw.add_argument("--registry-dir", required=True)
    pw.add_argument("--run-index", required=True, type=int)
    pw.add_argument("--timeout-sec", default="300")
    pw.add_argument("--poll-sec", default="0.05")
    pf = sub.add_parser("finish")
    pf.add_argument("--registry-dir", required=True)
    pf.add_argument("--run-index", required=True, type=int)
    pf.add_argument("--rc", required=True, type=int)
    pd = sub.add_parser("read")
    pd.add_argument("--registry-dir", required=True)
    pd.add_argument("--batch-id", default=None)
    pa = sub.add_parser("aggregate")
    pa.add_argument("--registry-dir", required=True)
    pa.add_argument("--batch-id", default=None)
    pa.add_argument("--output", default=None)
    a = ap.parse_args(argv)
    try:
        return {"begin": cmd_begin, "resolve": cmd_resolve, "finish": cmd_finish,
                "watch": cmd_watch, "read": cmd_read, "aggregate": cmd_aggregate}[a.cmd](a)
    except (RegistryError, C.ContractError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 5


if __name__ == "__main__":
    sys.exit(main())
