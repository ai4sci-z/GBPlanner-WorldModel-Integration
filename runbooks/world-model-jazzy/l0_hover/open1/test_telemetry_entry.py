#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1-05 · WP303 正式入口 telemetry 接入 dry-run 门(20 案 + 红案20/21)。

全 fake producer/fake sidecar,零 Docker/ROS/仿真。断言对象 = task_record.json /
monitor_status.json / artifact 集合 / 进程存活(身份=PID+starttime,不用名字模糊匹配)。
"""
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BL = os.path.join(HERE, "..", "batch_lifecycle.py")
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
    if fail_run:
        lines.append("exit 0")
    if post_sleep:
        lines.append(f"sleep {post_sleep}")
    open(p, "w").write("\n".join(lines) + "\n")
    os.chmod(p, 0o755)
    return p


def gen_sidecar(root, mode="ok"):
    """fake sidecar:把身份贯通证据写进 telemetry/sidecar_ran.json。
    mode: ok / crash(rc=3) / corrupt(写标记后 rc=4) / hang(挂死) / doublewriter"""
    p = os.path.join(root, "sidecar.py")
    open(p, "w").write(f'''#!/usr/bin/env python3
import json, os, sys, time
mode = {mode!r}
root = os.environ["BC_ROOT"]
td = os.path.join(root, "telemetry")
os.makedirs(td, exist_ok=True)
# run_id 贯通:只从真实 producer run 记录取,不另造第二套
run_rec = None
deadline = time.monotonic() + 2.0
while time.monotonic() < deadline:
    p1 = os.path.join(root, "runs", "run_1.json")
    if os.path.exists(p1):
        run_rec = json.load(open(p1)); break
    time.sleep(0.02)
out = {{"batch_id_env": os.environ.get("WP303_BATCH_ID"),
       "run_index_from_producer_record": (run_rec or {{}}).get("run_index"),
       "producer_batch_id_in_record": (run_rec or {{}}).get("batch_id"),
       "pid": os.getpid(), "mode": mode}}
open(os.path.join(td, "sidecar_ran.json"), "w").write(json.dumps(out))
if mode == "doublewriter":
    sys.path.insert(0, {HERE!r})
    import telemetry_sidecar as S
    ident = {{"batch_id": os.environ["WP303_BATCH_ID"], "run_id": os.path.basename(root),
             "pid": os.getpid(), "pid_starttime": "1", "boot_id": "b"}}
    S.SegmentStore(td, run_root=root, identity=ident)
    try:
        S.SegmentStore(td, run_root=root,
                       identity={{**ident, "pid": os.getpid()+1, "pid_starttime": "2"}})
        refused = False
    except S.TelemetryWriteError:
        refused = True
    open(os.path.join(td, "double_writer.json"), "w").write(json.dumps({{"refused": refused}}))
if mode == "crash":
    sys.exit(3)
if mode == "corrupt":
    open(os.path.join(td, "CORRUPT_MARK"), "w").write("x")
    sys.exit(4)
if mode == "hang":
    time.sleep(600)
sys.exit(0)
''')
    return p


def launch(root, env_extra=None, expected_runs=1):
    env = dict(os.environ)
    env.pop("WP303_TELEMETRY", None)
    env.pop("WP303_TELEMETRY_CMD", None)
    env["WP303_POLL_SEC"] = "0.05"
    if env_extra:
        env.update(env_extra)
    cp = subprocess.run(
        [sys.executable, BL, "launch", "--artifact-root", root, "--batch-id", "b_" + os.path.basename(root),
         "--expected-runs", str(expected_runs), "--startup-budget", "1", "--duration", "0.5",
         "--per-run-teardown", "0.1", "--inter-run-gap", "0.05", "--finalization-budget", "1",
         "--", "bash", os.path.join(root, "prod.sh")],
        capture_output=True, text=True, env=env, timeout=60)
    return cp


def jload(root, name):
    p = os.path.join(root, name)
    return json.load(open(p)) if os.path.exists(p) else None


def alive(pid, starttime):
    try:
        data = open(f"/proc/{pid}/stat").read()
        f = data[data.rfind(")") + 2:].split()
        return f[19 - 17] is not None and f[17] == str(starttime) if False else \
            (data[data.rfind(")") + 2:].split()[19] == str(starttime)
             and data[data.rfind(")") + 2:].split()[0] != "Z")
    except OSError:
        return False


BASE_ARTIFACTS = {"runs", "prod.sh", "sidecar.py", "task_record.json",
                  "batch_final.json", "monitor_status.json", ".monitor.lock", "batch.log"}

print("======== off 路径(案1/2/3;红案20)========")
r = mkroot(); gen_prod(r); gen_sidecar(r)
cp = launch(r)
ck("off:monitor rc=0", cp.returncode, 0)
rec = jload(r, "task_record.json")
ck("off:record.telemetry.enabled=False", rec["telemetry"]["enabled"], False)
ck("红案20 off 不产生 telemetry 目录", os.path.exists(os.path.join(r, "telemetry")), False)
got = set(os.listdir(r))
ck("案1 off artifact 集合不变(无新增)", sorted(got - BASE_ARTIFACTS), [])
off_script = rec["script"]
off_deadline = rec["deadline_params"]
ck("案2 off producer argv 不变", off_script.endswith("prod.sh") and "telemetry" not in off_script, True)

r2 = mkroot(); gen_prod(r2); gen_sidecar(r2)
cp = launch(r2, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r2,'sidecar.py')}"})
rec2 = jload(r2, "task_record.json")
ck("案2b on/off producer argv 完全一致", rec2["script"], off_script.replace(r, r2))
ck("案3 on/off deadline 参数一致", rec2["deadline_params"], off_deadline)

print("======== on 路径(案4/5/6/7;案15 身份)========")
ck("案4 on 启动 fake sidecar(产物在)",
   os.path.exists(os.path.join(r2, "telemetry", "sidecar_ran.json")), True)
ck("案4b monitor rc 仍=0", cp.returncode, 0)
side = jload(r2, "telemetry/sidecar_ran.json")
ck("案5 batch_id 贯通(env→sidecar)", side["batch_id_env"], "b_" + os.path.basename(r2))
ck("案5b producer 记录同 batch_id", side["producer_batch_id_in_record"], "b_" + os.path.basename(r2))
ck("案6 run_id 贯通(取自 producer run 记录,非第二套)",
   side["run_index_from_producer_record"], 1)
ms = jload(r2, "monitor_status.json")
ck("案7 telemetry_status 独立记录", ms["telemetry_status"]["state"], "OK")
ck("案7b sidecar rc 记录", ms["telemetry_status"]["sidecar_rc"], 0)
ck("producer_outcome 键分离", ms["producer_outcome"], "SUCCEEDED")
tinfo = rec2["telemetry"]
ck("案15 telemetry 身份含 pid", isinstance(tinfo.get("pid"), int), True)
ck("案15b telemetry 身份含 pid_starttime(PID 复用可判)",
   str(tinfo.get("pid_starttime", "")).isdigit(), True)

print("======== 失败语义(案8/9/10/11/12/19;红案21)========")
r3 = mkroot(); gen_prod(r3); gen_sidecar(r3, mode="crash")
cp = launch(r3, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r3,'sidecar.py')}"})
ms = jload(r3, "monitor_status.json")
ck("红案21/案8 sidecar 崩溃不覆盖 producer rc(monitor=0)", cp.returncode, 0)
ck("案8b telemetry_status=CRASHED", ms["telemetry_status"]["state"], "CRASHED")
ck("案8c sidecar_rc=3 留档", ms["telemetry_status"]["sidecar_rc"], 3)

r4 = mkroot(); gen_prod(r4); gen_sidecar(r4, mode="hang")
cp = launch(r4, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r4,'sidecar.py')}"})
ms = jload(r4, "monitor_status.json")
ck("案9 sidecar 挂死被 cleanup 收(KILLED)", ms["telemetry_status"]["state"], "KILLED")
ck("案9b monitor rc 仍=0", cp.returncode, 0)
t4 = jload(r4, "task_record.json")["telemetry"]
time.sleep(0.2)
ck("案18 cleanup 后无 sidecar 孤儿", alive(t4["pid"], t4["pid_starttime"]), False)

r5 = mkroot(); gen_prod(r5); gen_sidecar(r5, mode="corrupt")
cp = launch(r5, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r5,'sidecar.py')}"})
ms = jload(r5, "monitor_status.json")
ck("案10 producer 成功+telemetry CORRUPT:monitor rc=0", cp.returncode, 0)
ck("案10b telemetry_status=CRASHED(rc=4)", ms["telemetry_status"]["sidecar_rc"], 4)
ck("案10c producer_outcome 不被改写", ms["producer_outcome"], "SUCCEEDED")

r6 = mkroot(); gen_prod(r6, n=2, fail_run=2); gen_sidecar(r6)
cp = launch(r6, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r6,'sidecar.py')}"},
            expected_runs=2)
ms = jload(r6, "monitor_status.json")
ck("案11/19 producer 失败+telemetry 完整:rc=10(保真)", cp.returncode, 10)
ck("案11b telemetry_status=OK", ms["telemetry_status"]["state"], "OK")
ck("案20 launched 分母不删除失败 attempt(run_2 rc=1 在 run_rc_map)",
   ms["run_rc_map"].get("2"), 1)

r7 = mkroot(); gen_prod(r7, n=2, fail_run=1); gen_sidecar(r7, mode="crash")
cp = launch(r7, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r7,'sidecar.py')}"},
            expected_runs=2)
ms = jload(r7, "monitor_status.json")
ck("案12 双失败:producer rc=10 主导", cp.returncode, 10)
ck("案12b telemetry_status=CRASHED 并存", ms["telemetry_status"]["state"], "CRASHED")

print("======== 案13/14/16/17 ========")
r8 = mkroot(); gen_prod(r8, pre_sleep=5); gen_sidecar(r8)
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
proc.wait(timeout=30)
ms = jload(r8, "monitor_status.json")
ck("案13 cancel:outcome=CANCELLED rc=40", (ms["producer_outcome"], proc.returncode),
   ("CANCELLED", 40))
ck("案13b cancel 后 telemetry 已回收", ms["telemetry_status"]["state"] in ("OK", "KILLED"), True)

r9 = mkroot(); gen_prod(r9); gen_sidecar(r9)
open(os.path.join(r9, "monitor_status.json"), "w").write("{}")   # stale 现场
cp = launch(r9, env_extra={"WP303_TELEMETRY": "on",
                           "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r9,'sidecar.py')}"})
ck("案14 stale artifact 拒绝启动 rc=5", cp.returncode, 5)
ck("案14b stale 时不启动 sidecar", os.path.exists(os.path.join(r9, "telemetry")), False)

r10 = mkroot(); gen_prod(r10, pre_sleep=3); gen_sidecar(r10)
env10 = dict(env); env10["WP303_TELEMETRY_CMD"] = f"{sys.executable} {os.path.join(r10,'sidecar.py')}"
proc = subprocess.Popen(
    [sys.executable, BL, "launch", "--artifact-root", r10, "--batch-id", "b_" + os.path.basename(r10),
     "--expected-runs", "1", "--startup-budget", "5", "--duration", "5",
     "--per-run-teardown", "1", "--inter-run-gap", "1", "--finalization-budget", "5",
     "--", "bash", os.path.join(r10, "prod.sh")],
    env=env10, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(0.8)
cp2 = subprocess.run([sys.executable, BL, "monitor", "--artifact-root", r10],
                     capture_output=True, text=True, timeout=30)
ck("案16 第二 monitor 让位 rc=75", cp2.returncode, 75)
open(os.path.join(r10, "CANCEL"), "w").write("1")
proc.wait(timeout=30)

r11 = mkroot(); gen_prod(r11); gen_sidecar(r11, mode="doublewriter")
cp = launch(r11, env_extra={"WP303_TELEMETRY": "on",
                            "WP303_TELEMETRY_CMD": f"{sys.executable} {os.path.join(r11,'sidecar.py')}"})
dw = jload(r11, "telemetry/double_writer.json")
ck("案17 第二 writer 被拒(经真实 SegmentStore)", dw and dw["refused"], True)

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
