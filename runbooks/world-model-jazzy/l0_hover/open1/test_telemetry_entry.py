#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1C-05 · WP303 正式入口 telemetry 接入 dry-run 门(20 案 + Codex 反例3/18)。

on 主路径 = 项目内正式 sidecar CLI(fixture backend,零外部假脚本);
崩溃/挂死/双写模拟 = WP303_TELEMETRY_CMD 覆盖(task record 显式标 fixture/test only)。
零 Docker daemon/ROS/仿真;身份断言 = PID+starttime。"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BL = os.path.join(HERE, "..", "batch_lifecycle.py")
RID = "20260715T204428.255001623Z"
FAIL = 0


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def mkroot():
    r = tempfile.mkdtemp(prefix="e1entry_")
    os.makedirs(os.path.join(r, "runs"))
    return r


def gen_prod(root, n=1, fail_run=0, final=True, post_sleep=0.0, pre_sleep=0.0):
    p = os.path.join(root, "prod.sh")
    lines = ["#!/usr/bin/env bash", f'AR="{root}"']
    if pre_sleep:
        lines.append(f"sleep {pre_sleep}")
    for i in range(1, n + 1):
        rc = 1 if i == fail_run else 0
        lines.append(
            'printf \'{"schema_version":1,"batch_id":"%s","run_index":%d,"rc":%d}\\n\' '
            f'"$WP303_BATCH_ID" {i} {rc} > "$AR/runs/run_{i}.json"')
    if final:
        lines.append('printf \'{"schema_version":1,"batch_id":"%s","final":"done"}\\n\' '
                     '"$WP303_BATCH_ID" > "$AR/batch_final.json"')
    if post_sleep:
        lines.append(f"sleep {post_sleep}")
    open(p, "w").write("\n".join(lines) + "\n")
    os.chmod(p, 0o755)
    return p


def gen_scene(root, batch_id):
    """结构真实 wm 场景 + RESOLVED registry + fixture 输入(供默认 CLI 消费)。"""
    wm = os.path.join(root, "wm")
    watch = os.path.join(wm, "artifacts", "sim", "hover")
    run_dir = os.path.join(watch, RID)
    os.makedirs(run_dir)
    open(os.path.join(run_dir, "summary.json"), "w").write(
        json.dumps({"status": "TASK_STATUS_OK", "ok": True, "blockers": []}))
    reg = os.path.join(root, "run_registry")
    os.makedirs(reg)
    entry = {"schema_version": "wp304.run_registry.v1", "batch_id": batch_id, "run_index": 1,
             "world_model_run_id": RID, "world_model_run_dir": run_dir,
             "producer_pid": 1, "producer_pid_starttime": "1", "start_utc": 1.0,
             "start_monotonic": 1.0, "end_utc": 9.0, "end_monotonic": 9.0, "rc": 0,
             "identity_status": "RESOLVED", "discovery_method": "unique_new_dir_in_window",
             "watch_dir": watch, "pre_set": [], "phase": "finished"}
    open(os.path.join(reg, "attempt_1.json"), "w").write(json.dumps(entry))
    fixture = {"proc": {"/proc/loadavg": ["0.5 0.6 0.7 1/100 42\n"],
                        "/proc/stat": ["cpu 100 0 100 800 0 0 0 0 0 0\n",
                                       "cpu 150 0 150 900 0 0 0 0 0 0\n"],
                        "/proc/meminfo": ["MemTotal: 16000000 kB\nMemAvailable: 8000000 kB\n"],
                        "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": ["2400000\n"]},
               "docker": {"inspect": {}, "top": {"Processes": []}, "logs": "AP: ready\n", "wait": 0},
               "ros": {"readiness": [{"ready": True}], "extnav": [{"state": "healthy"}]},
               "git": {"rev-parse HEAD": "750032a3aad8\n", "status --porcelain": ""},
               "image_refs": [], "config_hash": "cafe" * 8, "host_samples": 2}
    fx = os.path.join(root, "fixture.json")
    open(fx, "w").write(json.dumps(fixture))
    return wm, run_dir, reg, fx


def gen_fake_sidecar(root, mode):
    """覆盖用假 sidecar(仅崩溃/挂死/双写模拟;record 标 fixture/test only)。"""
    p = os.path.join(root, "sidecar.py")
    open(p, "w").write(f'''#!/usr/bin/env python3
import json, os, sys, time
mode = {mode!r}
root = os.environ["BC_ROOT"]
td = os.path.join(root, "telemetry"); os.makedirs(td, exist_ok=True)
if mode == "ok_with_status":
    open(os.path.join(td, "sidecar_final_status.json"), "w").write(json.dumps(
        {{"evidence_state": "COMPLETE", "finalization_state": "WRITTEN"}}))
    sys.exit(0)
if mode == "crash":
    sys.exit(3)
if mode == "corrupt_status":
    open(os.path.join(td, "sidecar_final_status.json"), "w").write("{{broken")
    sys.exit(4)
if mode == "hang":
    time.sleep(600)
if mode == "doublewriter":
    sys.path.insert(0, {HERE!r})
    import subprocess
    import telemetry_sidecar as S
    run = root
    def ident():
        pid = os.getpid()
        st = open(f"/proc/{{pid}}/stat").read(); st = st[st.rfind(")")+2:].split()[19]
        boot = open("/proc/sys/kernel/random/boot_id").read().strip()
        return {{"batch_id": os.environ["WP303_BATCH_ID"], "run_id": os.path.basename(run),
                "pid": pid, "pid_starttime": st, "boot_id": boot}}
    S.SegmentStore(td, run_root=run, identity=ident())
    helper = os.path.join(td, "second_writer.py")
    open(helper, "w").write(
        "import os, sys\\n"
        "sys.path.insert(0, " + repr({HERE!r}) + ")\\n"
        "import telemetry_sidecar as S\\n"
        "td = " + repr(td) + "\\n"
        "run = " + repr(run) + "\\n"
        "ident = dict(batch_id=os.environ['WP303_BATCH_ID'], run_id=os.path.basename(run),\\n"
        "             pid=os.getpid(), pid_starttime='1', boot_id='b')\\n"
        "try:\\n"
        "    S.SegmentStore(td, run_root=run, identity=ident)\\n"
        "    sys.exit(0)\\n"
        "except S.TelemetryWriteError:\\n"
        "    sys.exit(21)\\n")
    code = subprocess.run([sys.executable, helper], env=os.environ).returncode
    open(os.path.join(td, "double_writer.json"), "w").write(json.dumps({{"second_rc": code}}))
    sys.exit(0)
sys.exit(0)
''')
    return p


def launch(root, env_extra=None, expected_runs=1, budget=None):
    env = dict(os.environ)
    for k in ("WP303_TELEMETRY", "WP303_TELEMETRY_CMD", "WP303_TELEMETRY_BACKEND",
              "WP303_TELEMETRY_FIXTURE_INPUT", "WM"):
        env.pop(k, None)
    env["WP303_POLL_SEC"] = "0.05"
    if env_extra:
        env.update(env_extra)
    b = budget or {}
    cp = subprocess.run(
        [sys.executable, BL, "launch", "--artifact-root", root, "--batch-id", "b_" + os.path.basename(root),
         "--expected-runs", str(expected_runs),
         "--startup-budget", b.get("startup", "1"), "--duration", b.get("duration", "0.5"),
         "--per-run-teardown", "0.1", "--inter-run-gap", "0.05",
         "--finalization-budget", b.get("final", "3"),
         "--", "bash", os.path.join(root, "prod.sh")],
        capture_output=True, text=True, env=env, timeout=90)
    return cp


def jload(root, name):
    p = os.path.join(root, name)
    return json.load(open(p)) if os.path.exists(p) else None


def alive(pid, starttime):
    try:
        data = open(f"/proc/{pid}/stat").read()
        f = data[data.rfind(")") + 2:].split()
        return f[19] == str(starttime) and f[0] != "Z"
    except OSError:
        return False


print("======== off 路径(案1/2/3;红案20)========")
r = mkroot(); gen_prod(r)
cp = launch(r)
ck("off:monitor rc=0", cp.returncode, 0)
rec = jload(r, "task_record.json")
ck("off:telemetry.enabled=False", rec["telemetry"]["enabled"], False)
ck("红案20 off 不产生 telemetry 目录", os.path.exists(os.path.join(r, "telemetry")), False)
BASE = {"runs", "prod.sh", "task_record.json", "batch_final.json",
        "monitor_status.json", ".monitor.lock", "batch.log"}
ck("案1 off artifact 集合零新增", sorted(set(os.listdir(r)) - BASE), [])
off_script = rec["script"]
off_deadline = rec["deadline_params"]
ms = jload(r, "monitor_status.json")
ck("off 三状态=OFF", (ms["telemetry_status"]["process_state"],
                      ms["telemetry_status"]["evidence_state"]), ("OFF", "OFF"))

print("======== on 主路径 = 项目内默认 CLI(Codex 反例3/18;案4/5/6/7)========")
r2 = mkroot(); gen_prod(r2, post_sleep=0.3)
wm, run_dir, reg, fx = gen_scene(r2, "b_" + os.path.basename(r2))
cp = launch(r2, env_extra={"WP303_TELEMETRY": "on", "WM": wm,
                           "WP303_TELEMETRY_BACKEND": "fixture",
                           "WP303_TELEMETRY_FIXTURE_INPUT": fx,
                           "WP303_TELEMETRY_REGISTRY_WAIT": "3"},
            budget={"duration": "2", "final": "5"})
ck("案4 on(默认命令)monitor rc=0", cp.returncode, 0)
rec2 = jload(r2, "task_record.json")
tinfo = rec2["telemetry"]
ck("反例3 默认命令=版本库内 sidecar", tinfo["argv"][1].endswith("open1/telemetry_sidecar.py"), True)
ck("反例18 无外部假脚本(非覆盖)", tinfo["cmd_override_fixture_test_only"], False)
argv = tinfo["argv"]
ck("argv 含 artifact_root", r2 in argv, True)
ck("argv 含 batch_id", "b_" + os.path.basename(r2) in argv, True)
ck("argv 含 run-registry", os.path.join(r2, "run_registry") in argv, True)
ck("argv 含 backend", "fixture" in argv, True)
ck("案2 producer argv 不变(on/off 同构)", rec2["script"], off_script.replace(r, r2))
ck("案3 deadline 参数集不受 telemetry 影响",
   sorted(rec2["deadline_params"].keys()), sorted(off_deadline.keys()))
# 三身份一致(E1C-03.3):sidecar 记录 == registry == run 目录基名
fs = json.load(open(os.path.join(run_dir, "telemetry", "sidecar_final_status.json")))
regv = json.load(open(os.path.join(reg, "attempt_1.json")))
ck("案6 三者相等:sidecar==registry==目录基名",
   (fs["run_ids_processed"], regv["world_model_run_id"], os.path.basename(run_dir)),
   ([RID], RID, RID))
ck("案5 batch_id 贯通(sidecar final)", fs["batch_id"], "b_" + os.path.basename(r2))
ms = jload(r2, "monitor_status.json")
ck("案7 三状态并存:process=EXITED_ZERO", ms["telemetry_status"]["process_state"], "EXITED_ZERO")
ck("案7b evidence_state=COMPLETE(来自产物,非 rc 推断)",
   ms["telemetry_status"]["evidence_state"], "COMPLETE")
ck("案7c finalization=WRITTEN", ms["telemetry_status"]["finalization_state"], "WRITTEN")
ck("案15 身份含 pid+starttime", str(tinfo.get("pid_starttime", "")).isdigit(), True)

print("======== 失败语义(案8-12/19;红案21;反例15 monitor 侧)========")
r3 = mkroot(); gen_prod(r3); gen_fake_sidecar(r3, "crash")
cp = launch(r3, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r3,'sidecar.py')}"})
ms = jload(r3, "monitor_status.json")
ck("红案21/案8 sidecar 崩溃不覆盖 producer rc", cp.returncode, 0)
ck("案8b process=EXITED_NONZERO + rc=3",
   (ms["telemetry_status"]["process_state"], ms["telemetry_status"]["sidecar_rc"]),
   ("EXITED_NONZERO", 3))
ck("案8c 覆盖命令显式标 fixture/test only",
   jload(r3, "task_record.json")["telemetry"]["cmd_override_fixture_test_only"], True)
ck("反例15 无 final status → evidence=UNKNOWN/finalization=MISSING(不写 OK)",
   (ms["telemetry_status"]["evidence_state"], ms["telemetry_status"]["finalization_state"]),
   ("UNKNOWN", "MISSING"))

r3b = mkroot(); gen_prod(r3b); gen_fake_sidecar(r3b, "ok_with_status")
cp = launch(r3b, env_extra={"WP303_TELEMETRY": "on",
                            "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r3b,'sidecar.py')}"})
ms = jload(r3b, "monitor_status.json")
ck("rc=0+有 status → EXITED_ZERO/COMPLETE/WRITTEN 并存",
   (ms["telemetry_status"]["process_state"], ms["telemetry_status"]["evidence_state"],
    ms["telemetry_status"]["finalization_state"]), ("EXITED_ZERO", "COMPLETE", "WRITTEN"))

r3c = mkroot(); gen_prod(r3c); gen_fake_sidecar(r3c, "corrupt_status")
cp = launch(r3c, env_extra={"WP303_TELEMETRY": "on",
                            "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r3c,'sidecar.py')}"})
ms = jload(r3c, "monitor_status.json")
ck("案10 进程失败+status 损坏 → EXITED_NONZERO/CORRUPT 并存(不压一个字段)",
   (ms["telemetry_status"]["process_state"], ms["telemetry_status"]["evidence_state"]),
   ("EXITED_NONZERO", "CORRUPT"))
ck("案10b producer 不受影响", (cp.returncode, ms["producer_outcome"]), (0, "SUCCEEDED"))

r4 = mkroot(); gen_prod(r4); gen_fake_sidecar(r4, "hang")
cp = launch(r4, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r4,'sidecar.py')}"})
ms = jload(r4, "monitor_status.json")
ck("案9 挂死被 cleanup 收:process=KILLED", ms["telemetry_status"]["process_state"], "KILLED")
ck("案9b monitor rc 仍=0", cp.returncode, 0)
t4 = jload(r4, "task_record.json")["telemetry"]
time.sleep(0.2)
ck("案18 cleanup 后无 sidecar 孤儿", alive(t4["pid"], t4["pid_starttime"]), False)

r6 = mkroot(); gen_prod(r6, n=2, fail_run=2); gen_fake_sidecar(r6, "ok_with_status")
cp = launch(r6, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r6,'sidecar.py')}"},
            expected_runs=2)
ms = jload(r6, "monitor_status.json")
ck("案11/19 producer 失败+telemetry 完整:rc=10 保真", cp.returncode, 10)
ck("案11b evidence=COMPLETE 并存", ms["telemetry_status"]["evidence_state"], "COMPLETE")
ck("案20 launched 不删失败 attempt(run_2 rc=1 在册)", ms["run_rc_map"].get("2"), 1)

r7 = mkroot(); gen_prod(r7, n=2, fail_run=1); gen_fake_sidecar(r7, "crash")
cp = launch(r7, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r7,'sidecar.py')}"},
            expected_runs=2)
ms = jload(r7, "monitor_status.json")
ck("案12 双失败:producer rc=10 主导 + telemetry EXITED_NONZERO 并存",
   (cp.returncode, ms["telemetry_status"]["process_state"]), (10, "EXITED_NONZERO"))

print("======== 案13/14/16/17 ========")
r8 = mkroot(); gen_prod(r8, pre_sleep=5); gen_fake_sidecar(r8, "hang")
env = dict(os.environ); env["WP303_POLL_SEC"] = "0.05"
env["WP303_TELEMETRY"] = "on"
env["WP303_TELEMETRY_CMD"] = f"{sys.executable} {os.path.join(r8,'sidecar.py')}"
proc = subprocess.Popen(
    [sys.executable, BL, "launch", "--artifact-root", r8, "--batch-id", "b_" + os.path.basename(r8),
     "--expected-runs", "1", "--startup-budget", "5", "--duration", "5",
     "--per-run-teardown", "1", "--inter-run-gap", "1", "--finalization-budget", "5",
     "--", "bash", os.path.join(r8, "prod.sh")],
    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(0.6)
open(os.path.join(r8, "CANCEL"), "w").write("1")
proc.wait(timeout=45)
ms = jload(r8, "monitor_status.json")
ck("案13 cancel:CANCELLED rc=40", (ms["producer_outcome"], proc.returncode), ("CANCELLED", 40))
ck("案13b cancel 后 sidecar 已回收",
   ms["telemetry_status"]["process_state"] in ("EXITED_ZERO", "KILLED"), True)

r9 = mkroot(); gen_prod(r9); gen_fake_sidecar(r9, "ok_with_status")
open(os.path.join(r9, "monitor_status.json"), "w").write("{}")
cp = launch(r9, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r9,'sidecar.py')}"})
ck("案14 stale 现场拒启 rc=5", cp.returncode, 5)
ck("案14b stale 时不启 sidecar", os.path.exists(os.path.join(r9, "telemetry")), False)

r10 = mkroot(); gen_prod(r10, pre_sleep=3); gen_fake_sidecar(r10, "ok_with_status")
env10 = dict(env); env10["WP303_TELEMETRY_CMD"] = f"{sys.executable} {os.path.join(r10,'sidecar.py')}"
proc = subprocess.Popen(
    [sys.executable, BL, "launch", "--artifact-root", r10, "--batch-id", "b_" + os.path.basename(r10),
     "--expected-runs", "1", "--startup-budget", "5", "--duration", "5",
     "--per-run-teardown", "1", "--inter-run-gap", "1", "--finalization-budget", "5",
     "--", "bash", os.path.join(r10, "prod.sh")],
    env=env10, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(0.8)
cp2 = subprocess.run([sys.executable, BL, "monitor", "--artifact-root", r10],
                     capture_output=True, text=True, timeout=45)
ck("案16 第二 monitor 让位 rc=75", cp2.returncode, 75)
open(os.path.join(r10, "CANCEL"), "w").write("1")
proc.wait(timeout=45)

r11 = mkroot(); gen_prod(r11); gen_fake_sidecar(r11, "doublewriter")
cp = launch(r11, env_extra={"WP303_TELEMETRY": "on",
                            "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r11,'sidecar.py')}"})
dw = jload(r11, "telemetry/double_writer.json")
ck("案17 第二 writer(真子进程)被拒 rc=21", dw and dw["second_rc"], 21)

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
