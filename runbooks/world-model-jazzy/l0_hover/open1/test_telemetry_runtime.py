#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1L · 运行期旁路链正式门(Codex 红案 R1-R15 + watcher 终态 + 全时序 dry-run)。

真实子进程 + 临时目录;禁止预填 RESOLVED 冒充运行期握手(活路径全部由并发
watcher 在 producer 存活期间 resolve)。零真实 Docker/ROS/仿真。"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import telemetry_sidecar as S  # noqa: E402

BL = os.path.join(HERE, "..", "batch_lifecycle.py")
BC = os.path.join(HERE, "..", "batch_common.sh")
RID = "20260715T204428.255001623Z"
RID2 = "20260715T205113.276955543Z"
FAIL = 0


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def rr(*args, **kw):
    return subprocess.run([sys.executable, os.path.join(HERE, "run_registry.py"), *args],
                          capture_output=True, text=True, timeout=60, **kw)


def scene():
    base = tempfile.mkdtemp(prefix="e1l_")
    wm = os.path.join(base, "wm")
    watch = os.path.join(wm, "artifacts", "sim", "hover")
    os.makedirs(watch)
    art = os.path.join(base, "art")
    reg = os.path.join(art, "run_registry")
    os.makedirs(reg)
    fx = os.path.join(base, "fx.json")
    open(fx, "w").write(json.dumps({
        "proc": {"/proc/loadavg": ["0.5 0.6 0.7 1/1 1\n"],
                 "/proc/stat": ["cpu 100 0 100 800 0 0 0 0 0 0\n",
                                "cpu 150 0 150 900 0 0 0 0 0 0\n"],
                 "/proc/meminfo": ["MemTotal: 16 kB\nMemAvailable: 8 kB\n"],
                 "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": ["2400000\n"]},
        "docker": {"top": {"Processes": []},
                   "logs_chunks": [{"delay": 0.05, "text": "AP: a\n"},
                                   {"delay": 0.1, "text": "AP: b\n"},
                                   {"delay": 0.1, "text": "AP: c\n"}],
                   "wait": 0, "wait_delay_sec": 2.0},
        "ros_stream": {"readiness": [{"delay": 0.05, "msg": {"ready": True}},
                                     {"delay": 0.1, "msg": {"ready": True}}],
                       "extnav": [{"delay": 0.05, "msg": {"state": "healthy"}}]},
        "git": {"rev-parse HEAD": "x\n", "status --porcelain": ""},
        "image_refs": [], "config_hash": "c" * 32, "host_interval_sec": 0.05}))
    return base, wm, watch, art, reg, fx


def sidecar_args(art, reg, wm, fx, extra=()):
    return [sys.executable, os.path.join(HERE, "telemetry_sidecar.py"),
            "--artifact-root", art, "--batch-id", "b1", "--run-registry", reg,
            "--world-model-root", wm, "--backend", "fixture", "--fixture-input", fx,
            "--flush-interval", "0.2", "--host-interval-sec", "0.05", *extra]


def mkrun(watch, rid):
    d = os.path.join(watch, rid)
    os.makedirs(d)
    open(os.path.join(d, "summary.json"), "w").write(
        json.dumps({"status": "TASK_STATUS_OK", "ok": True, "blockers": []}))
    return d


print("======== R1-R10:PENDING 等待→运行期 RESOLVE→连续采集→周期封存→finish ========")
base, wm, watch, art, reg, fx = scene()
rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", "1",
   "--watch-dir", watch)
side = subprocess.Popen(sidecar_args(art, reg, wm, fx, ("--once", "--registry-wait-sec", "5")),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
t0 = time.monotonic()
time.sleep(0.4)                                   # sidecar 在 PENDING 上等待(R1/R2)
w = subprocess.Popen([sys.executable, os.path.join(HERE, "run_registry.py"), "watch",
                      "--registry-dir", reg, "--run-index", "1",
                      "--timeout-sec", "5", "--poll-sec", "0.02"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(0.1)
run_dir = mkrun(watch, RID)                       # producer 运行期间目录出现
w.wait(timeout=15)
time.sleep(0.5)                                   # ACTIVE 采集窗口,producer 仍"存活"
final_path = os.path.join(run_dir, "telemetry", "sidecar_final_status.json")
ck("R9 run 结束前不得写最终 COMPLETE", os.path.exists(final_path), False)
idx_path = os.path.join(run_dir, "telemetry", "index.json")
mid_has_segment = os.path.exists(idx_path) and \
    len(json.load(open(idx_path))["segments"]) >= 1
ck("周期封存:run 存活期已有正式段", mid_has_segment, True)
rr("finish", "--registry-dir", reg, "--run-index", "1", "--rc", "0")
rc = side.wait(timeout=30)
dt = time.monotonic() - t0
ck("R1 不秒退(旧 0.028s rc=4)", (rc, dt > 0.9), (0, True))
ent = json.load(open(os.path.join(reg, "attempt_1.json")))
fs = json.load(open(final_path))
ck("R3 --once=完整处理一个 attempt", fs["run_ids_processed"], [RID])
ck("R4 resolve 发生在 producer 存活期(start<resolved<end)",
   ent["start_monotonic"] < ent["resolved_monotonic"] < ent["end_monotonic"], True)
hc = fs["collectors"]["host"]
ck("R5 首条 host 在 attempt end 前", hc["first_sample_mono_ns"] / 1e9 < ent["end_monotonic"], True)
ck("R6 首条 readiness 在 end 前",
   fs["collectors"]["readiness"]["first_sample_mono_ns"] / 1e9 < ent["end_monotonic"], True)
ck("R6b 首条 extnav 在 end 前",
   fs["collectors"]["extnav"]["first_sample_mono_ns"] / 1e9 < ent["end_monotonic"], True)
ck("R7 连续采集跨≥2 个 monotonic 点",
   hc["records"] >= 2 and hc["first_sample_mono_ns"] != hc["last_sample_mono_ns"], True)
segs = json.load(open(idx_path))["segments"]
ck("R8 Docker wait(2s)不阻塞其他采集(总时长<等待+采集应有值)", dt < 4.5, True)
ck("R8b wait 阻塞期间 host 多条", hc["records"] >= 4, True)
ck("R8c logs 三段全收", fs["collectors"]["sitl_console"]["records"], 3)
ck("R10 finish 后封存末段+final", fs["finalization_state"], "WRITTEN")
ck("R10b 首段密封时刻 < attempt end(非一次性尾部封存)",
   segs[0]["sealed_monotonic_ns"] / 1e9 < ent["end_monotonic"], True)
ck("live_mode=True", fs["live_mode"], True)
ck("evidence COMPLETE", fs["evidence_state"], "COMPLETE")

print("======== R11/R12:永远 PENDING / UNKNOWN ========")
base, wm, watch, art, reg, fx = scene()
rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", "1",
   "--watch-dir", watch)
t0 = time.monotonic()
cp = subprocess.run(sidecar_args(art, reg, wm, fx, ("--once", "--registry-wait-sec", "0.6")),
                    capture_output=True, text=True, timeout=30)
dt = time.monotonic() - t0
ck("R11 永远 PENDING → 有界超时(≥wait 窗口)", (cp.returncode, dt >= 0.6), (4, True))
bat = json.load(open(os.path.join(art, "telemetry", "sidecar_final_status.json")))
ck("R11b INCOMPLETE 落档", bat["evidence_state"], "INCOMPLETE")
base, wm, watch, art, reg, fx = scene()
rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", "1",
   "--watch-dir", watch)
rr("watch", "--registry-dir", reg, "--run-index", "1", "--timeout-sec", "0.2",
   "--poll-sec", "0.02")   # 零候选 → TIMED_OUT/UNKNOWN
cp = subprocess.run(sidecar_args(art, reg, wm, fx, ("--once", "--registry-wait-sec", "2")),
                    capture_output=True, text=True, timeout=30)
bat = json.load(open(os.path.join(art, "telemetry", "sidecar_final_status.json")))
ck("R12 UNKNOWN 身份:不启动 per-run writer(INCOMPLETE 登记)",
   (bat["attempts"][0]["state"], "writer" in str(bat["failure_reasons"])),
   ("INCOMPLETE", True))
ck("R12b 无 run 目录/writer 产物", os.listdir(watch), [])

print("======== watcher 终态(E1L-02.2)========")
base, wm, watch, art, reg, fx = scene()
rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", "1", "--watch-dir", watch)
rr("watch", "--registry-dir", reg, "--run-index", "1", "--timeout-sec", "0.2", "--poll-sec", "0.02")
e = json.load(open(os.path.join(reg, "attempt_1.json")))
ck("零候选 → TIMED_OUT", e["watcher_state"], "TIMED_OUT")
for k in ("watcher_pid", "watcher_pid_starttime", "watcher_start_monotonic",
          "watcher_end_monotonic", "pre_set_sha256", "candidates",
          "rejected_candidates", "watcher_reason"):
    ck(f"watcher 字段在档: {k}", k in e, True)
base, wm, watch, art, reg, fx = scene()
rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", "1", "--watch-dir", watch)
os.makedirs(os.path.join(watch, RID)); os.makedirs(os.path.join(watch, RID2))
rr("watch", "--registry-dir", reg, "--run-index", "1", "--timeout-sec", "1", "--poll-sec", "0.02")
e = json.load(open(os.path.join(reg, "attempt_1.json")))
ck("双候选 → UNKNOWN_MULTIPLE_CANDIDATES", e["watcher_state"], "UNKNOWN_MULTIPLE_CANDIDATES")
base, wm, watch, art, reg, fx = scene()
rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", "1", "--watch-dir", watch)
os.makedirs(os.path.join(watch, "not-a-run-id"))
rr("watch", "--registry-dir", reg, "--run-index", "1", "--timeout-sec", "0.3", "--poll-sec", "0.02")
e = json.load(open(os.path.join(reg, "attempt_1.json")))
ck("仅非法候选 → INVALID_CANDIDATE", e["watcher_state"], "INVALID_CANDIDATE")
base, wm, watch, art, reg, fx = scene()
rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", "1", "--watch-dir", watch)
os.symlink(tempfile.mkdtemp(), os.path.join(watch, RID))
rr("watch", "--registry-dir", reg, "--run-index", "1", "--timeout-sec", "0.3", "--poll-sec", "0.02")
e = json.load(open(os.path.join(reg, "attempt_1.json")))
ck("symlink 候选拒绝(INVALID)", e["watcher_state"], "INVALID_CANDIDATE")
ck("symlink 拒因在档", any("symlink" in x for x in e["rejected_candidates"]), True)
base, wm, watch, art, reg, fx = scene()
rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", "1", "--watch-dir", watch)
wp = subprocess.Popen([sys.executable, os.path.join(HERE, "run_registry.py"), "watch",
                       "--registry-dir", reg, "--run-index", "1",
                       "--timeout-sec", "30", "--poll-sec", "0.02"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(0.3)
wp.send_signal(signal.SIGTERM)
wp.wait(timeout=15)
e = json.load(open(os.path.join(reg, "attempt_1.json")))
ck("TERM → CANCELLED", e["watcher_state"], "CANCELLED")

print("======== R13/R14:多 run 隔离(--expected-runs 2 活路径)========")
base, wm, watch, art, reg, fx = scene()
side = subprocess.Popen(sidecar_args(art, reg, wm, fx,
                                     ("--expected-runs", "2", "--registry-wait-sec", "8")),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
run_dirs = []
for i, rid in ((1, RID), (2, RID2)):
    rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", str(i),
       "--watch-dir", watch)
    w = subprocess.Popen([sys.executable, os.path.join(HERE, "run_registry.py"), "watch",
                          "--registry-dir", reg, "--run-index", str(i),
                          "--timeout-sec", "5", "--poll-sec", "0.02"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.1)
    run_dirs.append(mkrun(watch, rid))
    w.wait(timeout=15)
    time.sleep(0.4)
    rr("finish", "--registry-dir", reg, "--run-index", str(i), "--rc", "0")
    time.sleep(0.2)
rc = side.wait(timeout=60)
ck("双 run rc=0", rc, 0)
bat = json.load(open(os.path.join(art, "telemetry", "sidecar_final_status.json")))
ck("R13 两 attempt 分别处理", [a["run_id"] for a in bat["attempts"]], [RID, RID2])
w1 = json.load(open(os.path.join(run_dirs[0], "telemetry", "writer.json")))
w2 = json.load(open(os.path.join(run_dirs[1], "telemetry", "writer.json")))
ck("R14 run2 独立 writer(run_id 各绑各)", (w1["run_id"], w2["run_id"]), (RID, RID2))
i1 = json.load(open(os.path.join(run_dirs[0], "telemetry", "index.json")))["segments"]
i2 = json.load(open(os.path.join(run_dirs[1], "telemetry", "index.json")))["segments"]
ck("R14b 段互不复用(各 run 独立 index/目录)",
   (len(i1) >= 1, len(i2) >= 1), (True, True))
r1_ids = {json.loads(l)["run_id"] for seg in i1
          for l in open(os.path.join(run_dirs[0], "telemetry", seg["file"]))}
r2_ids = {json.loads(l)["run_id"] for seg in i2
          for l in open(os.path.join(run_dirs[1], "telemetry", seg["file"]))}
ck("R14c run1 段只含 run1 记录", r1_ids, {RID})
ck("R14d run2 段只含 run2 记录", r2_ids, {RID2})

print("======== SIGKILL sidecar → 段可恢复(E1L-03.3)========")
base, wm, watch, art, reg, fx = scene()
rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", "1", "--watch-dir", watch)
side = subprocess.Popen(sidecar_args(art, reg, wm, fx, ("--once", "--registry-wait-sec", "8")),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
w = subprocess.Popen([sys.executable, os.path.join(HERE, "run_registry.py"), "watch",
                      "--registry-dir", reg, "--run-index", "1",
                      "--timeout-sec", "5", "--poll-sec", "0.02"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(0.1)
run_dir = mkrun(watch, RID)
w.wait(timeout=15)
time.sleep(0.6)   # 让至少一段封存
side.send_signal(signal.SIGKILL)
side.wait(timeout=15)
r = S.recover(os.path.join(run_dir, "telemetry"))
ck("SIGKILL 后已封存段完好", (r["status"], len(r["segments"]) >= 1), ("OK", True))
n_before = len(r["segments"])
rr("finish", "--registry-dir", reg, "--run-index", "1", "--rc", "0")
cp = subprocess.run(sidecar_args(art, reg, wm, fx, ("--once", "--registry-wait-sec", "2")),
                    capture_output=True, text=True, timeout=60)
ck("恢复 writer(post-run 补处理)rc=0", cp.returncode, 0)
r2 = S.recover(os.path.join(run_dir, "telemetry"))
ck("续段号不重号", len(r2["segments"]) > n_before, True)
ck("恢复后 index 可解析", r2["status"], "OK")

print("======== 局部 collector 失败(E1L-04.2)========")
base, wm, watch, art, reg, fx = scene()
d = json.load(open(fx)); d["docker"]["omit_console"] = True
open(fx, "w").write(json.dumps(d))
rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", "1", "--watch-dir", watch)
side = subprocess.Popen(sidecar_args(art, reg, wm, fx, ("--once", "--registry-wait-sec", "8")),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
w = subprocess.Popen([sys.executable, os.path.join(HERE, "run_registry.py"), "watch",
                      "--registry-dir", reg, "--run-index", "1",
                      "--timeout-sec", "5", "--poll-sec", "0.02"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(0.1)
run_dir = mkrun(watch, RID)
w.wait(timeout=15)
time.sleep(0.5)
rr("finish", "--registry-dir", reg, "--run-index", "1", "--rc", "0")
rc = side.wait(timeout=30)
fs = json.load(open(os.path.join(run_dir, "telemetry", "sidecar_final_status.json")))
ck("console 失败 → evidence INCOMPLETE", fs["evidence_state"], "INCOMPLETE")
ck("其他 required 继续采集(host 有样本)", fs["collectors"]["host"]["records"] >= 2, True)
ck("console error_state 在档", fs["collectors"]["sitl_console"]["error_state"] is not None, True)

print("======== E1L-06:正式入口全时序 dry-run(bc_run+watcher+真实 CLI)========")
base = tempfile.mkdtemp(prefix="e1l6_")
wm = os.path.join(base, "wm")
watch = os.path.join(wm, "artifacts", "sim", "hover")
os.makedirs(watch)
art = os.path.join(base, "batchroot")
os.makedirs(os.path.join(art, "runs"))
fx = os.path.join(base, "fx.json")
open(fx, "w").write(json.dumps({
    "proc": {"/proc/loadavg": ["0.5 0.6 0.7 1/1 1\n"],
             "/proc/stat": ["cpu 100 0 100 800 0 0 0 0 0 0\n",
                            "cpu 150 0 150 900 0 0 0 0 0 0\n"],
             "/proc/meminfo": ["MemTotal: 16 kB\nMemAvailable: 8 kB\n"],
             "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": ["2400000\n"]},
    "docker": {"top": {"Processes": []}, "logs": "AP: x\n", "wait": 0},
    "ros_stream": {"readiness": [{"delay": 0.05, "msg": {"ready": True}}],
                   "extnav": [{"delay": 0.05, "msg": {"state": "healthy"}}]},
    "git": {"rev-parse HEAD": "x\n", "status --porcelain": ""},
    "image_refs": [], "config_hash": "c" * 32, "host_interval_sec": 0.05}))
prod = os.path.join(art, "prod.sh")
open(prod, "w").write(f"""#!/usr/bin/env bash
source "{BC}"
BC_ROOT="{art}"
run_cmd() {{
  sleep 0.4
  mkdir -p "{watch}/{RID}"
  printf '{{"status":"TASK_STATUS_OK","ok":true,"blockers":[]}}' > "{watch}/{RID}/summary.json"
  sleep 1.2
}}
bc_init t >/dev/null; BC_ROOT="{art}"
bc_run 1 run_cmd || true
bc_finalize
""")
os.chmod(prod, 0o755)
env = dict(os.environ)
env.update({"WP303_POLL_SEC": "0.05", "WP303_TELEMETRY": "on", "WM": wm,
            "WP303_TELEMETRY_BACKEND": "fixture", "WP303_TELEMETRY_FIXTURE_INPUT": fx,
            "WP303_TELEMETRY_REGISTRY_WAIT": "8", "BC_WATCH_DIR": watch,
            "BC_REGISTRY_WATCH_SEC": "10"})
cp = subprocess.run(
    [sys.executable, BL, "launch", "--artifact-root", art, "--batch-id", "b_e1l6",
     "--expected-runs", "1", "--startup-budget", "5", "--duration", "5",
     "--per-run-teardown", "1", "--inter-run-gap", "0.5", "--finalization-budget", "6",
     "--", "bash", prod],
    capture_output=True, text=True, env=env, timeout=120)
ck("正式入口 rc=0", cp.returncode, 0)
ent = json.load(open(os.path.join(art, "run_registry", "attempt_1.json")))
run_dir = os.path.join(watch, RID)
fs = json.load(open(os.path.join(run_dir, "telemetry", "sidecar_final_status.json")))
segs = json.load(open(os.path.join(run_dir, "telemetry", "index.json")))["segments"]
hc = fs["collectors"]["host"]
t_start = ent["start_monotonic"]
t_res = ent["resolved_monotonic"]
t_first = hc["first_sample_mono_ns"] / 1e9
t_seal1 = segs[0]["sealed_monotonic_ns"] / 1e9
t_end = ent["end_monotonic"]
t_final = fs["finalized_monotonic_ns"] / 1e9
ck("全时序 producer_start < resolved", t_start < t_res, True)
ck("全时序 resolved < first_sample", t_res < t_first, True)
ck("全时序 first_sample < first_seal", t_first < t_seal1, True)
ck("全时序 first_seal < producer_end", t_seal1 < t_end, True)
ck("全时序 producer_end < evidence_final", t_end < t_final, True)
ck("live_mode(运行期采集,非事后)", fs["live_mode"], True)
ms = json.load(open(os.path.join(art, "monitor_status.json")))
ck("monitor 三态:EXITED_ZERO/COMPLETE/WRITTEN",
   (ms["telemetry_status"]["process_state"], ms["telemetry_status"]["evidence_state"],
    ms["telemetry_status"]["finalization_state"]), ("EXITED_ZERO", "COMPLETE", "WRITTEN"))
# R15:watcher 已被 bc_run 回收(entry 记录 watcher pid 已死)
wpid = ent.get("watcher_pid")
alive = os.path.exists(f"/proc/{wpid}") and open(f"/proc/{wpid}/stat").read().split(") ")[1][0] != "Z"
ck("R15 watcher 已回收", alive, False)
# 聚合(五层)也走一遍正式入口
cp = subprocess.run([sys.executable, os.path.join(HERE, "run_registry.py"), "aggregate",
                     "--registry-dir", os.path.join(art, "run_registry"),
                     "--batch-id", "b_e1l6",
                     "--output", os.path.join(art, "telemetry_denominators.json")],
                    capture_output=True, text=True, timeout=30)
ck("五层聚合 rc=0", cp.returncode, 0)
den = json.load(open(os.path.join(art, "telemetry_denominators.json")))
ck("launched=causal=full=1", (den["layers"]["launched"]["count"],
                              den["layers"]["causal_analysis_eligible"]["count"]), (1, 1))

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
