#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1C · 正式 sidecar CLI 门:参数反例 + fixture backend 真实主循环 +
required 闭包 + 三态并存 + 五层正式聚合(Codex 现场反例 1/2/13-17 的转绿证据)。

零 Docker daemon、零 ROS、零仿真;fixture backend 与 real 同一主循环。"""
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
SIDECAR = os.path.join(HERE, "telemetry_sidecar.py")
REGISTRY = os.path.join(HERE, "run_registry.py")


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def cli(*args, timeout=60):
    return subprocess.run([sys.executable, SIDECAR, *args],
                          capture_output=True, text=True, timeout=timeout)


def make_scene(with_summary_ok=None, omit_console=False, force_rc=None):
    """结构真实场景:fake wm 根 + 合法 run 目录 + RESOLVED registry + fixture 输入。"""
    base = tempfile.mkdtemp(prefix="cli_")
    wm = os.path.join(base, "wm")
    watch = os.path.join(wm, "artifacts", "sim", "hover")
    run_dir = os.path.join(watch, RID)
    os.makedirs(run_dir)
    art = os.path.join(base, "batchroot")
    reg = os.path.join(art, "run_registry")
    os.makedirs(reg)
    entry = {"schema_version": "wp304.run_registry.v1", "batch_id": "b1", "run_index": 1,
             "world_model_run_id": RID, "world_model_run_dir": run_dir,
             "producer_pid": 1, "producer_pid_starttime": "1", "start_utc": 1.0,
             "start_monotonic": 1.0, "end_utc": 9.0, "end_monotonic": 9.0, "rc": 0,
             "identity_status": "RESOLVED", "discovery_method": "unique_new_dir_in_window",
             "watch_dir": watch, "pre_set": [], "phase": "finished"}
    open(os.path.join(reg, "attempt_1.json"), "w").write(json.dumps(entry))
    if with_summary_ok is not None:
        open(os.path.join(run_dir, "summary.json"), "w").write(
            json.dumps({"status": "TASK_STATUS_OK" if with_summary_ok else "TASK_STATUS_ERROR",
                        "ok": with_summary_ok, "blockers": []}))
    fixture = {
        "proc": {"/proc/loadavg": ["0.5 0.6 0.7 1/100 42\n"],
                 "/proc/stat": ["cpu 100 0 100 800 0 0 0 0 0 0\n",
                                "cpu 150 0 150 900 0 0 0 0 0 0\n"],
                 "/proc/meminfo": ["MemTotal: 16000000 kB\nMemAvailable: 8000000 kB\n"],
                 "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": ["2400000\n"]},
        "docker": {"inspect": {"Image": "sha256:x"}, "top": {"Processes": [["1", "arducopter"]]},
                   "logs": "AP: hello\n", "wait": 0, "omit_console": omit_console},
        "ros": {"readiness": [{"ready": True}], "extnav": [{"state": "healthy"}]},
        "git": {"rev-parse HEAD": "750032a3aad8b62b0c8ef2b00f740ee125fdb382\n",
                "status --porcelain": ""},
        "image_refs": ["navlab/companion:jazzy-x"],
        "images_by_ref": {"navlab/companion:jazzy-x": {"tag": "jazzy-x", "digest": "sha256:d"}},
        "config_hash": "cafe" * 8, "container": "official_baseline", "host_samples": 2,
    }
    if force_rc is not None:
        fixture["force_rc"] = force_rc
    fx = os.path.join(base, "fixture.json")
    open(fx, "w").write(json.dumps(fixture))
    return base, wm, run_dir, art, reg, fx


def std_args(art, reg, wm, fx, extra=()):
    return ["--artifact-root", art, "--batch-id", "b1", "--run-registry", reg,
            "--world-model-root", wm, "--backend", "fixture", "--fixture-input", fx,
            "--once", "--registry-wait-sec", "0.2", *extra]


print("======== CLI 参数反例(Codex 反例1/2)========")
cp = cli("--help")
ck("反例1 --help 有正式 usage", cp.returncode == 0 and "usage" in cp.stdout, True)
cp = cli("--artifact-root", "/tmp", "--batch-id", "b")
ck("反例2 缺必需参数 → 失败关闭 rc=2", cp.returncode, 2)
cp = cli("--bogus-flag")
ck("未知参数 → rc=2", cp.returncode, 2)
base, wm, run_dir, art, reg, fx = make_scene()
cp = cli(*["--artifact-root", art, "--batch-id", "b1", "--run-registry", reg,
           "--world-model-root", wm, "--backend", "martian", "--once"])
ck("未知 backend → rc=2", cp.returncode, 2)
cp = cli("--artifact-root", art, "--batch-id", "b1", "--run-registry", reg,
         "--world-model-root", wm, "--backend", "fixture", "--once")
ck("fixture 缺 --fixture-input → rc=2", cp.returncode, 2)
# 空 registry:必须明确失败(非静默 0)
empty = tempfile.mkdtemp()
noreg = os.path.join(empty, "noreg")
cp = cli(*std_args(art, noreg, wm, fx))
ck("反例2b registry 不存在 → 有界等待后明确失败 rc=4(非静默 0/非秒退硬错)", cp.returncode, 4)
fs = json.load(open(os.path.join(art, "telemetry", "sidecar_final_status.json")))
ck("失败也产出 final status", fs["finalization_state"], "WRITTEN")
ck("失败原因在档(registry 目录未出现)",
   any("registry 目录不存在" in x for x in fs["failure_reasons"]), True)
# 空 registry 目录(存在但无 RESOLVED)→ rc=4
os.makedirs(noreg, exist_ok=True)
art2 = tempfile.mkdtemp()
cp = cli(*std_args(art2, noreg, wm, fx))
ck("反例2c 空 registry(无 RESOLVED)→ 明确失败 rc=4", cp.returncode, 4)
fs = json.load(open(os.path.join(art2, "telemetry", "sidecar_final_status.json")))
ck("失败原因=等待超时(仍 PENDING/无条目)", any("等待超时" in x for x in fs["failure_reasons"]), True)

print("======== fixture backend 走真实主循环(反例13/正式产物树)========")
base, wm, run_dir, art, reg, fx = make_scene(with_summary_ok=True)
cp = cli(*std_args(art, reg, wm, fx))
ck("完整 CLI 运行 rc=0", cp.returncode, 0)
td = os.path.join(run_dir, "telemetry")
for rel in S.REQUIRED_PROBE:
    ck(f"required 产物在: {rel}", os.path.exists(os.path.join(run_dir, rel)), True)
ck("段文件存在", any(f.startswith("segment-") and f.endswith(".jsonl") for f in os.listdir(td)), True)
ck("index 存在", os.path.exists(os.path.join(td, "index.json")), True)
fs = json.load(open(os.path.join(td, "sidecar_final_status.json")))
ck("反例13 evidence gate 由 CLI 实际调用", fs["evidence_gate"] is not None, True)
ck("evidence_state=COMPLETE", fs["evidence_state"], "COMPLETE")
ck("run_ids_processed=[真实 run_id]", fs["run_ids_processed"], [RID])
ck("business_outcome=OK", fs["business_outcome"], "OK")
ck("acceptance_eligible=True(业务∧证据)", fs["evidence_gate"]["acceptance_eligible"], True)
bat = json.load(open(os.path.join(art, "telemetry", "sidecar_final_status.json")))
ck("批级 final status 亦写", bat["evidence_state"], "COMPLETE")

print("======== 反例15:rc=0 但 required 缺 → 不得 OK ========")
base, wm, run_dir, art, reg, fx = make_scene(with_summary_ok=True, omit_console=True)
cp = cli(*std_args(art, reg, wm, fx))
ck("rc 仍=0(采集进程本身没失败)", cp.returncode, 0)
fs = json.load(open(os.path.join(run_dir, "telemetry", "sidecar_final_status.json")))
ck("反例15 evidence_state=INCOMPLETE(rc=0 不改判)", fs["evidence_state"], "INCOMPLETE")
ck("failed_required 含 console", "sitl.console" in fs["evidence_gate"]["failed_required"], True)
ck("acceptance_eligible=False", fs["evidence_gate"]["acceptance_eligible"], False)

print("======== 反例16:输出损坏 → CORRUPT(正式闭包函数)========")
base, wm, run_dir, art, reg, fx = make_scene(with_summary_ok=True)
cli(*std_args(art, reg, wm, fx))
fz = os.path.join(run_dir, "telemetry", "freeze.json")
os.chmod(fz, 0o644)
open(fz, "w").write("{broken json")
statuses, business_ok, biz = S.evaluate_run_evidence(run_dir)
ck("反例16 损坏 freeze → CORRUPT", statuses["freeze"], "CORRUPT")
import telemetry_contract as C
g = C.evidence_gate(statuses, business_ok=business_ok)
ck("反例16b gate=CORRUPT", g["status"], C.GATE_CORRUPT)

print("======== 反例17:进程失败与证据完整并存 ========")
base, wm, run_dir, art, reg, fx = make_scene(with_summary_ok=True, force_rc=8)
cp = cli(*std_args(art, reg, wm, fx))
ck("反例17 进程 rc=8", cp.returncode, 8)
fs = json.load(open(os.path.join(art, "telemetry", "sidecar_final_status.json")))
ck("反例17b 证据 COMPLETE 与进程失败并存(不压成一个字段)",
   (fs["process_rc"], fs["evidence_state"]), (8, "COMPLETE"))

print("======== --validate-only ========")
base, wm, run_dir, art, reg, fx = make_scene()
cp = cli(*std_args(art, reg, wm, fx, extra=("--validate-only",)))
ck("validate-only rc=0", cp.returncode, 0)
out = json.loads(cp.stdout)
ck("validate-only 报 registry", out["registry_entries"], 1)

print("======== TERM 封存(收信号不留脏摊子)========")
import signal
import time
base, wm, run_dir, art, reg, fx = make_scene(with_summary_ok=True)
# 无限模式(不 --once,长 registry-wait)启动后立即 TERM
p = subprocess.Popen([sys.executable, SIDECAR, "--artifact-root", art, "--batch-id", "b1",
                      "--run-registry", os.path.join(base, "empty_reg"), "--world-model-root", wm,
                      "--backend", "fixture", "--fixture-input", fx,
                      "--registry-wait-sec", "60", "--once"],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1.5)
p.send_signal(signal.SIGTERM)
rc = p.wait(timeout=30)
fs = json.load(open(os.path.join(art, "telemetry", "sidecar_final_status.json")))
ck("TERM 后 final status 落盘", fs["finalization_state"], "WRITTEN")

print("======== 反例14:五层分母正式聚合入口 ========")
base, wm, run_dir, art, reg, fx = make_scene(with_summary_ok=True)
cli(*std_args(art, reg, wm, fx))   # attempt_1 → COMPLETE
# attempt_2:producer 失败但 launched 保留;attempt_3:UNRESOLVED
watch = os.path.dirname(run_dir)
rid2 = "20260715T205113.276955543Z"
rd2 = os.path.join(watch, rid2)
os.makedirs(os.path.join(rd2, "telemetry"))
open(os.path.join(rd2, "telemetry", "sidecar_final_status.json"), "w").write(
    json.dumps({"evidence_state": "CORRUPT", "finalization_state": "WRITTEN"}))
e2 = {"schema_version": "wp304.run_registry.v1", "batch_id": "b1", "run_index": 2,
      "world_model_run_id": rid2, "world_model_run_dir": rd2,
      "producer_pid": 1, "producer_pid_starttime": "1", "start_utc": 2.0,
      "start_monotonic": 2.0, "end_utc": 3.0, "rc": 1,
      "identity_status": "RESOLVED", "discovery_method": "unique_new_dir_in_window",
      "watch_dir": watch, "pre_set": [], "phase": "finished"}
open(os.path.join(reg, "attempt_2.json"), "w").write(json.dumps(e2))
e3 = dict(e2); e3["run_index"] = 3; e3["world_model_run_id"] = None
e3["world_model_run_dir"] = None; e3["identity_status"] = "UNKNOWN"
open(os.path.join(reg, "attempt_3.json"), "w").write(json.dumps(e3))
# 给 attempt_1 补 finish rc=0 + mission airborne
os.makedirs(os.path.dirname(run_dir), exist_ok=True)
e1 = json.load(open(os.path.join(reg, "attempt_1.json")))
e1["rc"] = 0; e1["end_utc"] = 9.0; e1["phase"] = "finished"
open(os.path.join(reg, "attempt_1.json"), "w").write(json.dumps(e1))
open(os.path.join(run_dir, "mission_summary.json"), "w").write(json.dumps({"airborne_seen": True}))
out5 = os.path.join(art, "telemetry_denominators.json")
cp = subprocess.run([sys.executable, REGISTRY, "aggregate", "--registry-dir", reg,
                     "--batch-id", "b1", "--output", out5],
                    capture_output=True, text=True, timeout=30)
ck("反例14 聚合 CLI rc=0", cp.returncode, 0)
den = json.load(open(out5))
L = den["layers"]
ck("launched=3(失败/未解析 attempt 永不消失)", L["launched"]["count"], 3)
ck("infra=2(UNRESOLVED 排除+登记原因)", L["infrastructure_valid"]["count"], 2)
ck("causal=1(CORRUPT 排除)", L["causal_analysis_eligible"]["count"], 1)
ck("airborne=1", L["airborne"]["count"], 1)
ck("full_pass=1", L["full_pass"]["count"], 1)
ck("CORRUPT run 在册", den["corrupt_runs"], [rid2])
ck("排除原因逐 run 登记",
   rid2 in L["causal_analysis_eligible"]["exclusion_reasons"], True)

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
