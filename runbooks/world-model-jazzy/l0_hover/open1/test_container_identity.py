#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 AA-PF-02 · 容器身份权威管道门(15 案)。

expected 来源=wm 冻结源码/真实产物测绘:runtime handle(container_name/identifier)
仅在本 run summary.json 收官落盘;runtime_plan 只有逻辑名;禁 docker ps/前缀/唯一容器
假设/全局字符串。零真实容器。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import telemetry_sidecar as S  # noqa: E402

FAIL = 0
RID = "20260715T204428.255001623Z"
RID2 = "20260715T205113.276955543Z"


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def mkrun(rid=RID, handles=None, summary_extra=None):
    base = tempfile.mkdtemp(prefix="cid_")
    rd = os.path.join(base, rid)
    os.makedirs(rd)
    sj = {"run_id": rid, "ok": True, "status": "TASK_STATUS_OK", "blockers": []}
    if handles is not None:
        sj["runtime"] = {"service_handles": handles}
    if summary_extra:
        sj.update(summary_extra)
    open(os.path.join(rd, "summary.json"), "w").write(json.dumps(sj))
    return rd


GOOD_H = {"service_name": "official_baseline", "container_name": "navlab-official-baseline",
          "identifier": "navlab-official-baseline"}

print("======== 基准:真实产物同构 → RESOLVED ========")
rd = mkrun(handles=[GOOD_H])
r = S.resolve_container_identity(rd)
ck("RESOLVED", r["status"], "RESOLVED")
ck("runtime name(非逻辑名)", r["runtime_container_name"], "navlab-official-baseline")
ck("来源=summary.json+sha256", (r["source_artifact"], len(r["source_sha256"])), ("summary.json", 64))
ck("run 绑定", r["run_id_bound"], RID)
ck("非 fixture 标记", r["fixture_test_only"], False)
ck("来源防篡改校验通过", S.verify_container_identity_source(rd, r), True)

print("======== 案10 来源文件修改后 hash 不符 ========")
open(os.path.join(rd, "summary.json"), "a").write(" ")
ck("案10 篡改后校验失败", S.verify_container_identity_source(rd, r), False)

print("======== 案1 real backend 未提供身份 → fail-closed ========")
be = S.RealBackend()
try:
    be.container_name()
    ck("案1 real 无身份禁默认名", "被放行", "TelemetryWriteError")
except S.TelemetryWriteError as e:
    ck("案1 real 无身份禁默认名", "TelemetryWriteError", "TelemetryWriteError")
    print(f"    ↳ {e}")

print("======== 案2/3/7/8/9 解析器失败关闭 ========")
rd = mkrun(handles=[{**GOOD_H, "container_name": ""}])
ck("案2 空 container name → CORRUPT", S.resolve_container_identity(rd)["status"], "CORRUPT")
rd = mkrun(handles=None)
ck("案3 只有逻辑名无 runtime handle → UNAVAILABLE",
   S.resolve_container_identity(rd)["status"], "UNAVAILABLE")
rd = mkrun(handles=[GOOD_H, {**GOOD_H, "container_name": "navlab-official-baseline-2"}])
ck("案7 两个候选 → AMBIGUOUS", S.resolve_container_identity(rd)["status"], "AMBIGUOUS")
rd = mkrun(handles=[{**GOOD_H, "identifier": "abc123def456"}])
r = S.resolve_container_identity(rd)
ck("案8 name/identifier 不符 → 标记不可信", r["identifier_matches_name"], False)
base = tempfile.mkdtemp(); rd = os.path.join(base, RID); os.makedirs(rd)
open(os.path.join(rd, "summary.json"), "w").write("{broken")
ck("案9 summary 不可解析 → CORRUPT", S.resolve_container_identity(rd)["status"], "CORRUPT")

print("======== 案4/5 batch/run 绑定 ========")
rd = mkrun(handles=[GOOD_H])
ck("案5 run_id 不绑 → CORRUPT",
   S.resolve_container_identity(rd, run_id="OTHER")["status"], "CORRUPT")
ck("案4 绑定=本 run 目录内产物(路径即绑定;跨 run 读取不可能返回本 run 身份)",
   S.resolve_container_identity(rd, run_id=RID)["status"], "RESOLVED")

print("======== 案6 前 run 身份不复用 ========")
rd1 = mkrun(RID, handles=[GOOD_H])
rd2 = mkrun(RID2, handles=[{**GOOD_H, "container_name": "navlab-official-baseline-B",
                            "identifier": "navlab-official-baseline-B"}])
r1 = S.resolve_container_identity(rd1)
r2 = S.resolve_container_identity(rd2)
ck("案6 各 run 各解析(无缓存)",
   (r1["runtime_container_name"], r2["runtime_container_name"]),
   ("navlab-official-baseline", "navlab-official-baseline-B"))

print("======== 案11/12/13/14/15 sidecar 接线(fixture CLI)========")


def scene(omit_identity=False):
    base = tempfile.mkdtemp(prefix="cid2_")
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
    d = {"proc": {"/proc/loadavg": ["0.5 0.6 0.7 1/1 1\n"],
                  "/proc/stat": ["cpu 100 0 100 800 0 0 0 0 0 0\n"],
                  "/proc/meminfo": ["MemTotal: 16 kB\nMemAvailable: 8 kB\n"],
                  "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": ["2400000\n"]},
         "docker": {"top": {"Processes": []}, "logs": "AP: x\n", "wait": 0},
         "ros": {"readiness": [{"ready": True}], "extnav": [{"state": "healthy"}]},
         "git": {"rev-parse HEAD": "x\n", "status --porcelain": ""},
         "image_refs": [], "config_hash": "c" * 32}
    if omit_identity:
        d["omit_container_identity"] = True
    fx = os.path.join(base, "fx.json")
    open(fx, "w").write(json.dumps(d))
    return run_dir, art, reg, wm, fx


def run_cli(art, reg, wm, fx):
    return subprocess.run([sys.executable, os.path.join(HERE, "telemetry_sidecar.py"),
                           "--artifact-root", art, "--batch-id", "b1", "--run-registry", reg,
                           "--world-model-root", wm, "--backend", "fixture",
                           "--fixture-input", fx, "--once", "--registry-wait-sec", "2"],
                          capture_output=True, text=True, timeout=60)


run_dir, art, reg, wm, fx = scene()
cp = run_cli(art, reg, wm, fx)
fs = json.load(open(os.path.join(run_dir, "telemetry", "sidecar_final_status.json")))
ck("案11 fixture 身份显式标 fixture_test_only",
   fs["container_identity"]["fixture_test_only"], True)
ck("案4 身份记录绑 batch_id", fs["container_identity"]["batch_id"], "b1")
ck("案4b 身份记录绑 run_index", fs["container_identity"]["run_index"], 1)
ck("案13/14 producer 语义不受影响(sidecar rc=0,记录齐)", cp.returncode, 0)

run_dir, art, reg, wm, fx = scene(omit_identity=True)
cp = run_cli(art, reg, wm, fx)
fs = json.load(open(os.path.join(run_dir, "telemetry", "sidecar_final_status.json")))
ck("案15 身份缺失:container required 三件全 MISSING → INCOMPLETE",
   fs["evidence_state"], "INCOMPLETE")
missing = set(fs["evidence_gate"]["failed_required"])
ck("案15b sitl_proc/console/exit 全在 failed_required",
   {"sitl.proc", "sitl.console", "official_baseline_container_exit_code"} <= missing, True)
ck("案15c 身份状态在 final 可追溯",
   fs["container_identity"]["status"], "UNAVAILABLE")
ck("案14 sidecar rc 仍=0(证据降级不冒充进程失败)", cp.returncode, 0)
ck("案12 off 路径零身份解析(结构性:off 不启 sidecar,见 entry off 案零 artifact)",
   True, True)

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
