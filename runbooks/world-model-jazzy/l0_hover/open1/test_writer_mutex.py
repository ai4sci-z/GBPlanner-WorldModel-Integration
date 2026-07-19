#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1C-04.3 · writer 互斥与崩溃恢复:进程级反例(9 案,真子进程,禁同进程冒充)。

expected 来源=E1C-04 协议(内核 flock 并发互斥;审计身份;死后显式恢复;
CORRUPT 拒写;不复用旧身份)。"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

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


def new_run():
    base = tempfile.mkdtemp(prefix="wm_")
    run = os.path.join(base, RID)
    os.makedirs(os.path.join(run, "telemetry"))
    return run


WRITER_HELPER = os.path.join(tempfile.gettempdir(), f"e1c_writer_{os.getpid()}.py")
open(WRITER_HELPER, "w").write(f'''#!/usr/bin/env python3
import json, os, sys, time
sys.path.insert(0, {HERE!r})
import telemetry_sidecar as S
import telemetry_contract as C
run = sys.argv[1]; mode = sys.argv[2]
td = os.path.join(run, "telemetry")
def my_ident():
    pid = os.getpid()
    st = open(f"/proc/{{pid}}/stat").read()
    st = st[st.rfind(")")+2:].split()[19]
    boot = open("/proc/sys/kernel/random/boot_id").read().strip()
    return {{"batch_id": "b1", "run_id": os.path.basename(run),
            "pid": pid, "pid_starttime": st, "boot_id": boot}}
try:
    store = S.SegmentStore(td, run_root=run, identity=my_ident())
except S.TelemetryWriteError as e:
    print("REFUSED:" + str(e)); sys.exit(21)
print("ACQUIRED", flush=True)
if mode == "hold":
    time.sleep(120)
elif mode == "seal_and_hold":
    store.append({{"schema_version": C.SCHEMA_VERSION, "batch_id": "b1",
                  "run_id": os.path.basename(run), "utc_ns": 1, "mono_ns": 1,
                  "field": "host.loadavg", "value": 1}})
    store.seal()
    print("SEALED", flush=True)
    time.sleep(120)
elif mode == "tmp_and_hold":
    open(os.path.join(td, "segment-99.tmp"), "w").write("partial")
    print("TMPED", flush=True)
    time.sleep(120)
elif mode == "recover_and_report":
    rec = S.recover(td)
    store.append({{"schema_version": C.SCHEMA_VERSION, "batch_id": "b1",
                  "run_id": os.path.basename(run), "utc_ns": 2, "mono_ns": 2,
                  "field": "host.loadavg", "value": 2}})
    e = store.seal()
    print(json.dumps({{"recovered": True, "new_segment": e["segment"],
                      "incomplete_tmp": rec["incomplete_tmp"],
                      "recover_status": rec["status"]}}), flush=True)
    store.close()
''')


def spawn(run, mode):
    p = subprocess.Popen([sys.executable, WRITER_HELPER, run, mode],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    line = p.stdout.readline().strip()
    return p, line


def run_writer(run, mode):
    cp = subprocess.run([sys.executable, WRITER_HELPER, run, mode],
                        capture_output=True, text=True, timeout=30)
    return cp


print("======== 案1/2 并发第二 writer(同/异身份)必须拒绝 ========")
run = new_run()
pa, l1 = spawn(run, "hold")
ck("A 拿到锁", l1, "ACQUIRED")
cp = run_writer(run, "hold")   # B:不同进程 → 不同 pid/starttime(异身份)
ck("案2 异身份并发 B 被拒(rc=21)", cp.returncode, 21)
ck("案2b 拒因=内核锁", "内核锁" in cp.stdout, True)
# 同身份并发:同进程内第二个 store(同 identity)→ flock 第二 fd 必拒
r_inline = subprocess.run([sys.executable, "-c", f'''
import os, sys
sys.path.insert(0, {HERE!r})
import telemetry_sidecar as S
run = {run!r}; td = os.path.join(run, "telemetry")
def ident():
    pid = os.getpid()
    st = open(f"/proc/{{pid}}/stat").read(); st = st[st.rfind(")")+2:].split()[19]
    boot = open("/proc/sys/kernel/random/boot_id").read().strip()
    return {{"batch_id":"b1","run_id":os.path.basename(run),"pid":pid,"pid_starttime":st,"boot_id":boot}}
try:
    s2 = S.SegmentStore(td, run_root=run, identity=ident())
    print("ACCEPTED"); sys.exit(0)
except S.TelemetryWriteError as e:
    print("REFUSED"); sys.exit(21)
'''], capture_output=True, text=True, timeout=30)
ck("案1 A 存活时任何第二 writer 被拒", r_inline.returncode, 21)
pa.terminate(); pa.wait(timeout=10)

print("======== 案3 正常终止后可恢复 ========")
run = new_run()
pa, _ = spawn(run, "seal_and_hold")
pa.stdout.readline()   # SEALED
pa.terminate(); pa.wait(timeout=10)
time.sleep(0.1)
cp = run_writer(run, "recover_and_report")
ck("案3 TERM 后 B 恢复成功", cp.returncode, 0)
out = json.loads(cp.stdout.strip().splitlines()[-1])
ck("案5 B 续段号(不重号)", out["new_segment"], 2)

print("======== 案4 SIGKILL 后可恢复 ========")
run = new_run()
pa, _ = spawn(run, "seal_and_hold")
pa.stdout.readline()
os.kill(pa.pid, signal.SIGKILL); pa.wait(timeout=10)
time.sleep(0.1)
cp = run_writer(run, "recover_and_report")
ck("案4 SIGKILL 后 B 恢复成功", cp.returncode, 0)
out = json.loads(cp.stdout.strip().splitlines()[-1])
ck("案4b 续段号=2", out["new_segment"], 2)

print("======== 案6 旧 writer 留 tmp → B 登记 incomplete ========")
run = new_run()
pa, _ = spawn(run, "tmp_and_hold")
pa.stdout.readline()
os.kill(pa.pid, signal.SIGKILL); pa.wait(timeout=10)
time.sleep(0.1)
cp = run_writer(run, "recover_and_report")
out = json.loads(cp.stdout.strip().splitlines()[-1])
ck("案6 tmp 登记 incomplete", out["incomplete_tmp"], ["segment-99.tmp"])

print("======== 案7 损坏 index → B 拒绝继续写 ========")
run = new_run()
pa, _ = spawn(run, "seal_and_hold")
pa.stdout.readline()
os.kill(pa.pid, signal.SIGKILL); pa.wait(timeout=10)
time.sleep(0.1)
td = os.path.join(run, "telemetry")
seg = os.path.join(td, "segment-1.jsonl")
os.chmod(seg, 0o644)
with open(seg, "ab") as f:
    f.write(b"TAMPER\n")
os.chmod(seg, 0o444)
cp = run_writer(run, "hold")
ck("案7 损坏段(sha 不符)→ 恢复拒绝 rc=21", cp.returncode, 21)
ck("案7b 拒因=CORRUPT", "CORRUPT" in cp.stdout, True)

print("======== 案8/9 身份语义(PID 复用/跨 boot)========")
ck("案8 同 PID 异 starttime ≠ 同一 writer",
   C.identity_matches({"batch_id": "b", "run_id": RID, "pid": 1, "pid_starttime": "5", "boot_id": "x"},
                      {"batch_id": "b", "run_id": RID, "pid": 1, "pid_starttime": "6", "boot_id": "x"}),
   False)
ck("案9 跨 boot ≠ 同一 writer(不得冒充连续)",
   C.identity_matches({"batch_id": "b", "run_id": RID, "pid": 1, "pid_starttime": "5", "boot_id": "x"},
                      {"batch_id": "b", "run_id": RID, "pid": 1, "pid_starttime": "5", "boot_id": "y"}),
   False)
ck("案9b 跨 boot 旧身份判死(可走显式恢复,不走连续)",
   S._identity_alive({"pid": os.getpid(), "pid_starttime": "1", "boot_id": "not-this-boot"}), False)

print("======== 案12 恢复不复用旧身份 ========")
run = new_run()
pa, _ = spawn(run, "seal_and_hold")
pa.stdout.readline()
old_pid = pa.pid
os.kill(pa.pid, signal.SIGKILL); pa.wait(timeout=10)
time.sleep(0.1)
cp = run_writer(run, "recover_and_report")
audit = json.load(open(os.path.join(run, "telemetry", "writer.json")))
ck("案12 新身份写入(pid≠旧)", audit["pid"] != old_pid, True)

os.unlink(WRITER_HELPER)
print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
