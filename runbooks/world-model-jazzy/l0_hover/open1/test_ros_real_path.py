#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 AA-PF-01 · ROS real-path 失败关闭门(10 案)。

expected 来源=E1 required evidence 契约 + wm 冻结源码实证
(/external_nav/status=std_msgs/String,bridge cpp L89;readiness 连续 topic 无
发布者=未验证)。宿主实测=无 rclpy/std_msgs。零真实 ROS 图。"""
import json
import os
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


def rejects(name, fn, exc):
    global FAIL
    try:
        fn()
        print(f"FAIL: {name} expected={exc.__name__} actual=被放行")
        FAIL += 1
    except exc as e:
        print(f"PASS: {name} expected={exc.__name__} actual={exc.__name__}")
        print(f"    ↳ {e}")
    except Exception as e:
        print(f"FAIL: {name} expected={exc.__name__} actual={type(e).__name__}: {e}")
        FAIL += 1


def fake_factory():
    class N:
        def __init__(self):
            self.subs = []

        def create_subscription(self, t, topic, cb, d):
            self.subs.append((t, topic))
            return object()
    n = N()
    return lambda: (n, lambda t: None, lambda: None)


GOOD_TOPICS = {"readiness": "/mavlink_external_nav/status", "extnav": "/external_nav/status"}

print("======== 案1/2 宿主 rclpy/std_msgs 缺失(真实实测)========")
cp = subprocess.run([sys.executable, "-c", "import rclpy"], capture_output=True, text=True)
ck("案1 前提:宿主无 rclpy", cp.returncode != 0, True)
cp = subprocess.run([sys.executable, "-c", "from std_msgs.msg import String"],
                    capture_output=True, text=True)
ck("案2 前提:宿主无 std_msgs", cp.returncode != 0, True)
rejects("案1b default factory → RosAdapterUnavailable(明确原因,非崩)",
        lambda: S.ConcreteRosSubscribeAdapter(ros_domain_id="7", system_domain_id="7",
                                              topics=GOOD_TOPICS),
        S.RosAdapterUnavailable)

print("======== 案3 topic 消息类型权威校验 ========")
ck("权威登记:/external_nav/status=String(bridge cpp L89)",
   S.AUTHORITATIVE_TOPIC_TYPES["/external_nav/status"], "std_msgs/msg/String")
rejects("案3 类型不符拒绝(配置 Odometry vs 权威 String)",
        lambda: S.ConcreteRosSubscribeAdapter(ros_domain_id="7", system_domain_id="7",
                                              topics=GOOD_TOPICS,
                                              node_factory=fake_factory(),
                                              msg_type="nav_msgs/msg/Odometry"),
        S.RosWriteRefused)
rejects("案3b 未验证 topic 拒绝(wm 无发布者)",
        lambda: S.ConcreteRosSubscribeAdapter(ros_domain_id="7", system_domain_id="7",
                                              topics={"readiness": "/navlab/startup_readiness/status",
                                                      "extnav": "/external_nav/status"},
                                              node_factory=fake_factory()),
        S.RosAdapterUnavailable)
rejects("案3c readiness topic 显式置空 → 拒绝(fail-closed 保持)",
        lambda: S.ConcreteRosSubscribeAdapter(ros_domain_id="7", system_domain_id="7",
                                              topics={"readiness": None,
                                                      "extnav": "/external_nav/status"},
                                              node_factory=fake_factory()),
        S.RosAdapterUnavailable)
ck("案3d 默认 topics=负责人裁决值(§11.7)",
   S.ROS_SUBSCRIBE_TOPICS["readiness"], "/mavlink_external_nav/status")

print("======== 案4/5/6 双域独立来源 ========")
rejects("案4 sidecar domain 未配置 → fail-closed(禁静默 0)",
        lambda: S.ConcreteRosSubscribeAdapter(ros_domain_id=None, system_domain_id="7",
                                              topics=GOOD_TOPICS, node_factory=fake_factory()),
        S.RosAdapterUnavailable)
rejects("案5 system domain 未知 → fail-closed",
        lambda: S.ConcreteRosSubscribeAdapter(ros_domain_id="7", system_domain_id=None,
                                              topics=GOOD_TOPICS, node_factory=fake_factory()),
        S.RosAdapterUnavailable)
rejects("案6 两域不一致 → 拒绝",
        lambda: S.ConcreteRosSubscribeAdapter(ros_domain_id="7", system_domain_id="8",
                                              topics=GOOD_TOPICS, node_factory=fake_factory()),
        S.RosWriteRefused)
be = S.RealBackend(container="c", ros_domain_id=None, system_ros_domain_id=None,
                   ros_topics=GOOD_TOPICS)
rejects("案4b RealBackend 双域未配 → ros_stream fail-closed(非 env 双充)",
        lambda: next(be.ros_stream("extnav", lambda: False)),
        S.RosAdapterUnavailable)

print("======== 案7-10 sidecar 级失败关闭(fixture)========")


def scene(ros_fail=False, empty_ros=False, only_one=False):
    base = tempfile.mkdtemp(prefix="rrp_")
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
    ros = {"readiness": [{"ready": True}], "extnav": [{"state": "healthy"}]}
    if empty_ros:
        ros = {"readiness": [], "extnav": []}
    if only_one:
        ros = {"readiness": [], "extnav": [{"state": "healthy"}]}
    fx = os.path.join(base, "fx.json")
    d = {"proc": {"/proc/loadavg": ["0.5 0.6 0.7 1/1 1\n"],
                  "/proc/stat": ["cpu 100 0 100 800 0 0 0 0 0 0\n"],
                  "/proc/meminfo": ["MemTotal: 16 kB\nMemAvailable: 8 kB\n"],
                  "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": ["2400000\n"]},
         "docker": {"top": {"Processes": []}, "logs": "AP: x\n", "wait": 0},
         "ros": ros, "git": {"rev-parse HEAD": "x\n", "status --porcelain": ""},
         "image_refs": [], "config_hash": "c" * 32}
    if ros_fail:
        d["ros_raise"] = True
    open(fx, "w").write(json.dumps(d))
    return base, wm, run_dir, art, reg, fx


# fixture backend 注入 adapter 初始化异常
_orig = S.FixtureBackend.ros_stream


def _patched(self, key, should_stop):
    if self.data.get("ros_raise"):
        raise S.RosAdapterUnavailable("fixture: adapter 初始化异常")
    return _orig(self, key, should_stop)


S.FixtureBackend.ros_stream = _patched


def run_cli(art, reg, wm, fx):
    return subprocess.run([sys.executable, os.path.join(HERE, "telemetry_sidecar.py"),
                           "--artifact-root", art, "--batch-id", "b1", "--run-registry", reg,
                           "--world-model-root", wm, "--backend", "fixture",
                           "--fixture-input", fx, "--once", "--registry-wait-sec", "2"],
                          capture_output=True, text=True, timeout=60)


base, wm, run_dir, art, reg, fx = scene(ros_fail=True)
cp = run_cli(art, reg, wm, fx)
fs = json.load(open(os.path.join(run_dir, "telemetry", "sidecar_final_status.json")))
ck("案7 adapter 异常:producer rc 语义不被覆盖(sidecar 自 rc=0)", cp.returncode, 0)
ck("案7b evidence=INCOMPLETE", fs["evidence_state"], "INCOMPLETE")
ck("案7c 具体 error_state 在档",
   "初始化异常" in str(fs["collectors"]["readiness"]["error_state"] or "")
   or "初始化异常" in str(fs["collectors"]["extnav"]["error_state"] or ""), True)

base, wm, run_dir, art, reg, fx = scene(empty_ros=True)
cp = run_cli(art, reg, wm, fx)
fs = json.load(open(os.path.join(run_dir, "telemetry", "sidecar_final_status.json")))
ck("案8 required ROS 零记录 → INCOMPLETE(空 pointer 不伪装)",
   fs["evidence_state"], "INCOMPLETE")
ck("案8b failed_required 含 readiness+extnav",
   sorted(set(fs["evidence_gate"]["failed_required"]) & {"readiness", "extnav"}),
   ["extnav", "readiness"])

base, wm, run_dir, art, reg, fx = scene(only_one=True)
cp = run_cli(art, reg, wm, fx)
fs = json.load(open(os.path.join(run_dir, "telemetry", "sidecar_final_status.json")))
ck("案9 仅一个 ROS collector 成功 → 另一个 INCOMPLETE",
   ("readiness" in fs["evidence_gate"]["failed_required"],
    "extnav" in fs["evidence_gate"]["failed_required"]), (True, False))
ck("案10 producer 业务成功 + ROS required 缺 → acceptance=false",
   fs["evidence_gate"]["acceptance_eligible"], False)
# causal 排除(正式聚合)
cp = subprocess.run([sys.executable, os.path.join(HERE, "run_registry.py"), "aggregate",
                     "--registry-dir", reg, "--batch-id", "b1",
                     "--output", os.path.join(art, "den.json")],
                    capture_output=True, text=True, timeout=30)
den = json.load(open(os.path.join(art, "den.json")))
ck("案10b causal_analysis_eligible=0(排除原因在档)",
   den["layers"]["causal_analysis_eligible"]["count"], 0)
ck("案10c launched 保留", den["layers"]["launched"]["count"], 1)

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
