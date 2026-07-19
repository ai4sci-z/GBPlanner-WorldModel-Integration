#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1L-CORRECT-02 · 身份等待预算统一门。

expected 来源=launcher 预算语义:sidecar 身份等待窗口必须由 launcher 启动预算推导
(单一来源,dry-run 与正式同一代码),不得残留孤立 5s 默认;watcher 不得先于
sidecar 窗口终止;永久 PENDING 有界退出;TERM 不被长窗拖死;逐 attempt 独立窗口。
默认路径测试不设置 WP303_TELEMETRY_REGISTRY_WAIT(显式覆盖=fixture/test only)。"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BL = os.path.join(HERE, "..", "batch_lifecycle.py")
RID = "20260715T204428.255001623Z"
FAIL = 0


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def rr(*args):
    return subprocess.run([sys.executable, os.path.join(HERE, "run_registry.py"), *args],
                          capture_output=True, text=True, timeout=60)


def scene():
    base = tempfile.mkdtemp(prefix="bud_")
    wm = os.path.join(base, "wm")
    watch = os.path.join(wm, "artifacts", "sim", "hover")
    os.makedirs(watch)
    art = os.path.join(base, "art")
    os.makedirs(os.path.join(art, "runs"))
    fx = os.path.join(base, "fx.json")
    open(fx, "w").write(json.dumps({
        "proc": {"/proc/loadavg": ["0.5 0.6 0.7 1/1 1\n"],
                 "/proc/stat": ["cpu 100 0 100 800 0 0 0 0 0 0\n"],
                 "/proc/meminfo": ["MemTotal: 16 kB\nMemAvailable: 8 kB\n"],
                 "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": ["2400000\n"]},
        "docker": {"top": {"Processes": []}, "logs": "AP: x\n", "wait": 0},
        "ros": {"readiness": [{"ready": True}], "extnav": [{"state": "healthy"}]},
        "git": {"rev-parse HEAD": "x\n", "status --porcelain": ""},
        "image_refs": [], "config_hash": "c" * 32, "host_interval_sec": 0.05}))
    return base, wm, watch, art, fx


def make_producer(art, watch, resolve_at, alive_until):
    """producer:t=resolve_at 秒建 run 目录(经 begin+watch 的 bc 同构握手由测试驱动),
    存活到 alive_until 再退。"""
    p = os.path.join(art, "prod.sh")
    open(p, "w").write(f"""#!/usr/bin/env bash
AR="{art}"
python3 "{os.path.join(HERE, 'run_registry.py')}" begin --registry-dir "$AR/run_registry" \\
  --batch-id "$WP303_BATCH_ID" --run-index 1 --watch-dir "{watch}" >/dev/null 2>&1
python3 "{os.path.join(HERE, 'run_registry.py')}" watch --registry-dir "$AR/run_registry" \\
  --run-index 1 --timeout-sec "${{WP303_IDENTITY_WAIT_SEC:-300}}" --poll-sec 0.05 >/dev/null 2>&1 &
WPID=$!
sleep {resolve_at}
mkdir -p "{watch}/{RID}"
printf '{{"status":"TASK_STATUS_OK","ok":true,"blockers":[]}}' > "{watch}/{RID}/summary.json"
sleep {alive_until}
wait $WPID 2>/dev/null
python3 "{os.path.join(HERE, 'run_registry.py')}" finish --registry-dir "$AR/run_registry" \\
  --run-index 1 --rc 0 >/dev/null 2>&1
printf '{{"schema_version":1,"batch_id":"%s","run_index":1,"rc":0}}\\n' "$WP303_BATCH_ID" > "$AR/runs/run_1.json"
printf '{{"schema_version":1,"batch_id":"%s","final":"done"}}\\n' "$WP303_BATCH_ID" > "$AR/batch_final.json"
""")
    os.chmod(p, 0o755)
    return p


def launch(art, prod, fx, wm, budgets, extra_env=None, timeout=120):
    env = dict(os.environ)
    for k in ("WP303_TELEMETRY", "WP303_TELEMETRY_CMD", "WP303_TELEMETRY_BACKEND",
              "WP303_TELEMETRY_FIXTURE_INPUT", "WP303_TELEMETRY_REGISTRY_WAIT", "WM"):
        env.pop(k, None)
    env.update({"WP303_POLL_SEC": "0.05", "WP303_TELEMETRY": "on", "WM": wm,
                "WP303_TELEMETRY_BACKEND": "fixture",
                "WP303_TELEMETRY_FIXTURE_INPUT": fx})
    if extra_env:
        env.update(extra_env)
    cp = subprocess.run(
        [sys.executable, BL, "launch", "--artifact-root", art, "--batch-id",
         "b_" + os.path.basename(art),
         "--expected-runs", "1",
         "--startup-budget", budgets["startup"], "--duration", budgets["duration"],
         "--per-run-teardown", budgets["teardown"], "--inter-run-gap", budgets["gap"],
         "--finalization-budget", budgets["final"],
         "--", "bash", prod],
        capture_output=True, text=True, env=env, timeout=timeout)
    return cp, env


print("======== 红案1/2/3:身份 6.5s 解析(>旧 5s 默认,<合法 startup 预算)========")
base, wm, watch, art, fx = scene()
prod = make_producer(art, watch, resolve_at=6.5, alive_until=1.0)
budgets = {"startup": "20", "duration": "5", "teardown": "0.5", "gap": "0.2", "final": "8"}
cp, _ = launch(art, prod, fx, wm, budgets)
rec = json.load(open(os.path.join(art, "task_record.json")))
argv = rec["telemetry"]["argv"]
wait_val = float(argv[argv.index("--registry-wait-sec") + 1])
ms = json.load(open(os.path.join(art, "monitor_status.json")))
ck("红案1 默认 argv 等待窗≠孤立 5s(由 launcher 预算推导)", wait_val > 5.0, True)
ck("红案2 sidecar 不在合法 startup 预算内 rc=4 秒退",
   ms["telemetry_status"]["sidecar_rc"], 0)
ck("红案3 身份在合法期限内解析 → ACTIVE 并完成采集",
   (ms["telemetry_status"]["process_state"], ms["telemetry_status"]["evidence_state"]),
   ("EXITED_ZERO", "COMPLETE"))
run_fs = json.load(open(os.path.join(watch, RID, "telemetry", "sidecar_final_status.json")))
ck("红案3b live_mode(运行期,非事后)", run_fs["live_mode"], True)
ck("预算推导可复核:wait == startup+duration+teardown+gap+margin",
   abs(wait_val - (20 + 5 + 0.5 + 0.2 + 10.0)) < 0.01, True)

print("======== 红案4:永久 PENDING → 有界退出(与 launcher 预算一致)========")
base, wm, watch, art, fx = scene()
prod = os.path.join(art, "prod.sh")
open(prod, "w").write(f"""#!/usr/bin/env bash
AR="{art}"
sleep 13
printf '{{"schema_version":1,"batch_id":"%s","run_index":1,"rc":0}}\\n' "$WP303_BATCH_ID" > "$AR/runs/run_1.json"
printf '{{"schema_version":1,"batch_id":"%s","final":"done"}}\\n' "$WP303_BATCH_ID" > "$AR/batch_final.json"
""")
os.chmod(prod, 0o755)
budgets = {"startup": "1", "duration": "13", "teardown": "0.1", "gap": "0.05", "final": "6"}
# 界=1+13+0.1+0.05+10=24.15?不:producer 活 13s > sidecar 界?——用小界:见下
budgets = {"startup": "0.5", "duration": "0.5", "teardown": "0.1", "gap": "0.05", "final": "16"}
t0 = time.monotonic()
cp, _ = launch(art, prod, fx, wm, budgets, timeout=180)
ms = json.load(open(os.path.join(art, "monitor_status.json")))
expect_bound = 0.5 + 0.5 + 0.1 + 0.05 + 10.0   # =11.15;producer 活 13s>界,sidecar 自身有界退出
ck("红案4 永久 PENDING:sidecar rc=4 有界退出", ms["telemetry_status"]["sidecar_rc"], 4)
bat = json.load(open(os.path.join(art, "telemetry", "sidecar_final_status.json")))
ck("红案4b INCOMPLETE 落档", bat["evidence_state"], "INCOMPLETE")
ck("红案4c 退出界=推导预算(monitor 收尾在 bound+finalization 内)",
   time.monotonic() - t0 < expect_bound + 14 + 8, True)

print("======== 红案6:TERM 不被长等待窗拖死 ========")
base, wm, watch, art, fx = scene()
reg = os.path.join(art, "run_registry"); os.makedirs(reg)
p = subprocess.Popen([sys.executable, os.path.join(HERE, "telemetry_sidecar.py"),
                      "--artifact-root", art, "--batch-id", "b1", "--run-registry", reg,
                      "--world-model-root", wm, "--backend", "fixture",
                      "--fixture-input", fx, "--once", "--registry-wait-sec", "300"],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1.5)
t0 = time.monotonic()
p.send_signal(signal.SIGTERM)
rc = p.wait(timeout=30)
ck("红案6 TERM 及时退出(<2s,300s 窗不拖死)", time.monotonic() - t0 < 2.0, True)
ck("红案6b final status 落盘", os.path.exists(
    os.path.join(art, "telemetry", "sidecar_final_status.json")), True)

print("======== 红案5:多 run 逐 attempt 独立等待窗口 ========")
# 直接以 CLI 驱动:窗口 W=2.5s;attempt1 于 1s 解析,attempt2 于其窗口内(全局 4s)解析。
# 共享窗口实现会在全局 2.5s 后拒 attempt2;逐 attempt 窗口必须成功。
base, wm, watch, art, fx = scene()
reg = os.path.join(art, "run_registry"); os.makedirs(reg)
side = subprocess.Popen([sys.executable, os.path.join(HERE, "telemetry_sidecar.py"),
                         "--artifact-root", art, "--batch-id", "b1", "--run-registry", reg,
                         "--world-model-root", wm, "--backend", "fixture",
                         "--fixture-input", fx, "--expected-runs", "2",
                         "--registry-wait-sec", "2.5",
                         "--flush-interval", "0.2", "--host-interval-sec", "0.05"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
RID2 = "20260715T205113.276955543Z"
for i, rid, delay in ((1, RID, 1.0), (2, RID2, 1.6)):
    time.sleep(delay)
    rr("begin", "--registry-dir", reg, "--batch-id", "b1", "--run-index", str(i),
       "--watch-dir", watch)
    w = subprocess.Popen([sys.executable, os.path.join(HERE, "run_registry.py"), "watch",
                          "--registry-dir", reg, "--run-index", str(i),
                          "--timeout-sec", "5", "--poll-sec", "0.02"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.1)
    d = os.path.join(watch, rid); os.makedirs(d)
    open(os.path.join(d, "summary.json"), "w").write(
        json.dumps({"status": "TASK_STATUS_OK", "ok": True, "blockers": []}))
    w.wait(timeout=15)
    time.sleep(0.3)
    rr("finish", "--registry-dir", reg, "--run-index", str(i), "--rc", "0")
rc = side.wait(timeout=60)
bat = json.load(open(os.path.join(art, "telemetry", "sidecar_final_status.json")))
ck("红案5 两 attempt 均在各自窗口内完成(共享窗会拒 attempt2)",
   (rc, [a["run_id"] for a in bat["attempts"]]), (0, [RID, RID2]))

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
