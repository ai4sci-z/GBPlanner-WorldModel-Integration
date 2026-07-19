#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1L-CORRECT-01 · required evidence gate 段链闭包门(Codex 反例 10 案)。

expected 来源=E1 required evidence 契约(D5-08/09)+ 原子段语义:入口指针文件、
index.json、段文件三者必须形成一致闭包;损坏→CORRUPT;required 零记录→INCOMPLETE;
业务成功/rc=0/full_pass 均不得覆盖证据失败。仓外同构 fixture,零仿真。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import telemetry_contract as C  # noqa: E402
import telemetry_sidecar as S  # noqa: E402

FAIL = 0
RID = "20260715T204428.255001623Z"


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def build_good_run():
    """经真实 CLI(fixture backend,post-run 模式)生成一棵合法证据树。"""
    base = tempfile.mkdtemp(prefix="evch_")
    wm = os.path.join(base, "wm")
    watch = os.path.join(wm, "artifacts", "sim", "hover")
    run_dir = os.path.join(watch, RID)
    os.makedirs(run_dir)
    open(os.path.join(run_dir, "summary.json"), "w").write(
        json.dumps({"status": "TASK_STATUS_OK", "ok": True, "blockers": []}))
    art = os.path.join(base, "art")
    reg = os.path.join(art, "run_registry")
    os.makedirs(reg)
    entry = {"schema_version": "wp304.run_registry.v1", "batch_id": "b1", "run_index": 1,
             "world_model_run_id": RID, "world_model_run_dir": run_dir,
             "producer_pid": 1, "producer_pid_starttime": "1", "start_utc": 1.0,
             "start_monotonic": 1.0, "end_utc": 9.0, "end_monotonic": 9.0, "rc": 0,
             "identity_status": "RESOLVED", "discovery_method": "unique_new_dir_in_window",
             "watch_dir": watch, "pre_set": [], "phase": "finished"}
    open(os.path.join(reg, "attempt_1.json"), "w").write(json.dumps(entry))
    fx = os.path.join(base, "fx.json")
    open(fx, "w").write(json.dumps({
        "proc": {"/proc/loadavg": ["0.5 0.6 0.7 1/1 1\n"],
                 "/proc/stat": ["cpu 100 0 100 800 0 0 0 0 0 0\n"],
                 "/proc/meminfo": ["MemTotal: 16 kB\nMemAvailable: 8 kB\n"],
                 "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": ["2400000\n"]},
        "docker": {"top": {"Processes": []}, "logs": "AP: x\n", "wait": 0},
        "ros": {"readiness": [{"ready": True}], "extnav": [{"state": "healthy"}]},
        "git": {"rev-parse HEAD": "x\n", "status --porcelain": ""},
        "image_refs": [], "config_hash": "c" * 32}))
    cp = subprocess.run([sys.executable, os.path.join(HERE, "telemetry_sidecar.py"),
                         "--artifact-root", art, "--batch-id", "b1", "--run-registry", reg,
                         "--world-model-root", wm, "--backend", "fixture",
                         "--fixture-input", fx, "--once", "--registry-wait-sec", "2"],
                        capture_output=True, text=True, timeout=60)
    assert cp.returncode == 0, cp.stderr
    return run_dir


def gate_of(run_dir):
    statuses, business_ok, _ = S.evaluate_run_evidence(run_dir)
    return C.evidence_gate(statuses, business_ok=business_ok)


def unlock(p):
    os.chmod(p, 0o644)
    return p


print("======== 基准:合法树必须 COMPLETE ========")
good = build_good_run()
g = gate_of(good)
ck("合法树 gate=COMPLETE", g["status"], "COMPLETE")
ck("合法树 recover=OK", S.recover(os.path.join(good, "telemetry"))["status"], "OK")
ck("合法树可验收", g["acceptance_eligible"], True)


def fresh():
    return build_good_run()


def seg_files(run_dir):
    td = os.path.join(run_dir, "telemetry")
    return sorted(f for f in os.listdir(td) if f.startswith("segment-") and f.endswith(".jsonl"))


print("======== 案1 index 引用段不存在 → CORRUPT ========")
rd = fresh(); td = os.path.join(rd, "telemetry")
os.unlink(unlock(os.path.join(td, seg_files(rd)[0])))
ck("案1 recover=CORRUPT", S.recover(td)["status"], "CORRUPT")
g = gate_of(rd)
ck("案1 gate=CORRUPT", g["status"], "CORRUPT")
ck("案1 acceptance=false", g["acceptance_eligible"], False)

print("======== 案2 段 SHA 与 index 不一致 → CORRUPT ========")
rd = fresh(); td = os.path.join(rd, "telemetry")
p = unlock(os.path.join(td, seg_files(rd)[0]))
with open(p, "ab") as f:
    f.write(b"TAMPER\n")
ck("案2 recover=CORRUPT", S.recover(td)["status"], "CORRUPT")
g = gate_of(rd)
ck("案2 gate=CORRUPT(Codex 核心反例)", g["status"], "CORRUPT")
ck("案2 acceptance=false", g["acceptance_eligible"], False)

print("======== 案3 未登记正式段 → CORRUPT ========")
rd = fresh(); td = os.path.join(rd, "telemetry")
open(os.path.join(td, "segment-99.jsonl"), "w").write("{}\n")
ck("案3 recover=CORRUPT", S.recover(td)["status"], "CORRUPT")
ck("案3 gate=CORRUPT", gate_of(rd)["status"], "CORRUPT")

print("======== 案4 重复段号 → CORRUPT ========")
rd = fresh(); td = os.path.join(rd, "telemetry")
ip = os.path.join(td, "index.json")
idx = json.load(open(ip))
idx["segments"].append(dict(idx["segments"][0]))
open(ip, "w").write(json.dumps(idx))
ck("案4 recover=CORRUPT", S.recover(td)["status"], "CORRUPT")
ck("案4 gate=CORRUPT", gate_of(rd)["status"], "CORRUPT")

print("======== 案5 入口声称存在但段内零条该字段 → INCOMPLETE ========")
rd = fresh(); td = os.path.join(rd, "telemetry")
# 把 readiness 记录从段里剥掉(重写段+index 保持结构一致,只失字段)
segs = seg_files(rd)
newlines = []
for sf in segs:
    p = unlock(os.path.join(td, sf))
    lines = [l for l in open(p) if json.loads(l)["field"] != "readiness"]
    open(p, "w").write("".join(lines))
    os.chmod(p, 0o444)
import hashlib
idx = json.load(open(os.path.join(td, "index.json")))
for e in idx["segments"]:
    data = open(os.path.join(td, e["file"]), "rb").read()
    e["sha256"] = hashlib.sha256(data).hexdigest()
    e["bytes"] = len(data)
    e["record_count"] = len(data.splitlines())
open(os.path.join(td, "index.json"), "w").write(json.dumps(idx))
# 指针同步(声称与段内一致,只剩"零记录"条件)→ 必须 INCOMPLETE(readiness required)
pp = os.path.join(rd, "telemetry", "readiness.jsonl")
os.chmod(pp, 0o644)
d = json.load(open(pp)); d["field_records"] = {}
open(pp, "w").write(json.dumps(d))
g = gate_of(rd)
ck("案5 readiness 零记录 → INCOMPLETE", g["status"], "INCOMPLETE")
ck("案5b failed_required 含 readiness", "readiness" in g["failed_required"], True)

print("======== 案6 入口 field_records 与段内计数不一致 → CORRUPT ========")
rd = fresh(); td = os.path.join(rd, "telemetry")
pp = os.path.join(rd, "telemetry", "host.jsonl")
d = json.load(open(pp))
d["field_records"]["host.loadavg"] = 999
os.chmod(pp, 0o644)
open(pp, "w").write(json.dumps(d))
g = gate_of(rd)
ck("案6 计数不一致 → CORRUPT", g["status"], "CORRUPT")

print("======== 案7 段内记录不可解析 → CORRUPT ========")
rd = fresh(); td = os.path.join(rd, "telemetry")
sf = unlock(os.path.join(td, seg_files(rd)[0]))
data = open(sf, "rb").read()
open(sf, "wb").write(b"NOT JSON\n" + data[9:])   # 等长破坏(避开 sha 检查的捷径依赖)
idx = json.load(open(os.path.join(td, "index.json")))
for e in idx["segments"]:
    if e["file"] == os.path.basename(sf):
        e["sha256"] = hashlib.sha256(open(sf, "rb").read()).hexdigest()
open(os.path.join(td, "index.json"), "w").write(json.dumps(idx))
g = gate_of(rd)
ck("案7 段行不可解析 → CORRUPT", g["status"], "CORRUPT")

print("======== 案8 段内 run_id 与 run 目录身份不一致 → CORRUPT ========")
rd = fresh(); td = os.path.join(rd, "telemetry")
sf = unlock(os.path.join(td, seg_files(rd)[0]))
lines = []
for l in open(sf):
    r = json.loads(l)
    r["run_id"] = "20260715T999999.000000000Z"
    lines.append(json.dumps(r, sort_keys=True) + "\n")
open(sf, "w").write("".join(lines))
idx = json.load(open(os.path.join(td, "index.json")))
for e in idx["segments"]:
    if e["file"] == os.path.basename(sf):
        data = open(sf, "rb").read()
        e["sha256"] = hashlib.sha256(data).hexdigest()
        e["bytes"] = len(data)
open(os.path.join(td, "index.json"), "w").write(json.dumps(idx))
g = gate_of(rd)
ck("案8 run_id 串写 → CORRUPT", g["status"], "CORRUPT")

print("======== 案9 required collector 静默零记录且无 error_state → INCOMPLETE ========")
# 案5 已构造"零记录"физически;本案断言语义:零记录不因'无 error_state'而洗白
rd = fresh(); td = os.path.join(rd, "telemetry")
for sf in seg_files(rd):
    p = unlock(os.path.join(td, sf))
    lines = [l for l in open(p) if json.loads(l)["field"] != "extnav"]
    open(p, "w").write("".join(lines))
idx = json.load(open(os.path.join(td, "index.json")))
for e in idx["segments"]:
    data = open(os.path.join(td, e["file"]), "rb").read()
    e["sha256"] = hashlib.sha256(data).hexdigest()
    e["bytes"] = len(data)
    e["record_count"] = len(data.splitlines())
open(os.path.join(td, "index.json"), "w").write(json.dumps(idx))
pp = os.path.join(rd, "telemetry", "extnav.jsonl")
os.chmod(pp, 0o644)
d = json.load(open(pp)); d["field_records"] = {}
open(pp, "w").write(json.dumps(d))
fs = json.load(open(os.path.join(td, "sidecar_final_status.json")))
ck("案9 前提:final 里 extnav 无 error_state",
   fs["collectors"]["extnav"].get("error_state"), None)
g = gate_of(rd)
ck("案9 静默零记录 → INCOMPLETE", g["status"], "INCOMPLETE")
ck("案9b failed_required 含 extnav", "extnav" in g["failed_required"], True)

print("======== 案10 业务成功不得覆盖证据失败 ========")
rd = fresh(); td = os.path.join(rd, "telemetry")
sf = unlock(os.path.join(td, seg_files(rd)[0]))
with open(sf, "ab") as f:
    f.write(b"TAMPER\n")
sj = json.load(open(os.path.join(rd, "summary.json")))
ck("案10 前提:business ok=True", sj["ok"], True)
g = gate_of(rd)
ck("案10 gate=CORRUPT", g["status"], "CORRUPT")
ck("案10b acceptance_eligible=false(业务成功被证据失败压制)",
   g["acceptance_eligible"], False)
g2 = C.evidence_gate({"host.loadavg": "CORRUPT"}, business_ok=True, full_pass=True)
ck("案10c full_pass=True 亦不得开门", g2["acceptance_eligible"], False)

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
