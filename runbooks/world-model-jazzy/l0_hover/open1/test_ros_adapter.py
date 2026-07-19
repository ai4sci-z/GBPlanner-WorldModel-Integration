#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1L-05 · concrete ROS 只订不发适配层结构门(recording node factory)。

针对 ConcreteRosSubscribeAdapter 本体(非包装类):recording node 实录全部
create_* 调用,断言只出现 create_subscription。不启动真实 ROS 图。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import telemetry_sidecar as S  # noqa: E402

FAIL = 0


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


class RecordingNode:
    """实录 node:任何属性访问都被记账;create_subscription 返回句柄并存 callback。"""

    def __init__(self):
        self.calls = []
        self.subs = {}

    def create_subscription(self, msg_type, topic, callback, depth):
        self.calls.append(("create_subscription", msg_type, topic, depth))
        self.subs[topic] = callback
        return object()

    def create_publisher(self, *a, **k):
        self.calls.append(("create_publisher",) + a)
        return object()

    def create_service(self, *a, **k):
        self.calls.append(("create_service",) + a)
        return object()

    def create_client(self, *a, **k):
        self.calls.append(("create_client",) + a)
        return object()

    def declare_parameter(self, *a, **k):
        self.calls.append(("declare_parameter",) + a)

    def set_parameters(self, *a, **k):
        self.calls.append(("set_parameters",) + a)


class Msg:
    def __init__(self, data):
        self.data = data


def make_factory():
    node = RecordingNode()
    spins = {"n": 0}
    shutdowns = {"n": 0}

    def spin_once(timeout_sec):
        spins["n"] += 1

    def shutdown():
        shutdowns["n"] += 1
    return node, spins, shutdowns, (lambda: (node, spin_once, shutdown))


print("======== 只订不发(concrete adapter 本体)========")
GOOD_TOPICS = {"readiness": "/mavlink_external_nav/status", "extnav": "/external_nav/status"}
node, spins, shutdowns, factory = make_factory()
ad = S.ConcreteRosSubscribeAdapter(ros_domain_id="7", system_domain_id="7",
                                   topics=GOOD_TOPICS, node_factory=factory)
kinds = sorted({c[0] for c in node.calls})
ck("实际只出现 create_subscription", kinds, ["create_subscription"])
ck("恰两个订阅", len([c for c in node.calls if c[0] == "create_subscription"]), 2)
topics = sorted(c[2] for c in node.calls if c[0] == "create_subscription")
ck("订阅 topic 与契约一致", topics, sorted(GOOD_TOPICS.values()))
ck("publisher/service/client/参数方法零调用",
   [c for c in node.calls if c[0] != "create_subscription"], [])

print("======== domain / callback / shutdown 语义 ========")
try:
    S.ConcreteRosSubscribeAdapter(ros_domain_id="7", system_domain_id="8",
                                  topics=GOOD_TOPICS, node_factory=factory)
    ck("domain 不一致拒绝", "被放行", "RosWriteRefused")
except S.RosWriteRefused:
    ck("domain 不一致拒绝", "RosWriteRefused", "RosWriteRefused")
# callback 只写内部队列
cb = node.subs[GOOD_TOPICS["extnav"]]
cb(Msg({"state": "healthy"}))
out = ad.drain()
ck("callback 只写 sidecar 内部队列", (len(out), out[0][0], out[0][1]),
   (1, "extnav", {"state": "healthy"}))
ck("记录带双时戳", (out[0][2] > 0, out[0][3] > 0), (True, True))
# callback 闭包不保留可写 raw node(cell 内只有队列/shut 标志)
free = cb.__code__.co_freevars
ck("callback 闭包无 node 引用", "node" not in free and "_node" not in free, True)
# 有界 spin
ad.spin_bounded(0.05, lambda: False)
ck("有界 spin 执行过", spins["n"] >= 1, True)
# shutdown 幂等 + 关后不再接收
ad.shutdown()
ad.shutdown()
ck("shutdown 幂等(只关一次)", shutdowns["n"], 1)
cb(Msg({"state": "late"}))
ck("shutdown 后不再接收", ad.drain(), [])

print("======== rclpy 不可用语义(default factory;剥离环境子进程历史反例)========")
# 2026-07-20 补正:裁决后 sourced 宿主已有 rclpy——在本进程直接构造 default factory
# 会 rclpy.init() 建真实 node(违反"不启动真实 ROS 图")。改为剥离 ROS 环境的
# 子进程复现"无 rclpy"历史状态,环境无关。
import subprocess  # noqa: E402
_senv = {k: v for k, v in os.environ.items()
         if k not in ("PYTHONPATH", "AMENT_PREFIX_PATH", "CMAKE_PREFIX_PATH",
                      "COLCON_PREFIX_PATH", "LD_LIBRARY_PATH", "ROS_DISTRO",
                      "ROS_VERSION", "ROS_PYTHON_VERSION")
         and not k.startswith("RMW_")}
_senv["PATH"] = "/usr/bin:/bin"
_snippet = ("import sys; sys.path.insert(0, %r)\n"
            "import telemetry_sidecar as S\n"
            "try:\n"
            "    S.ConcreteRosSubscribeAdapter(ros_domain_id='0', system_domain_id='0',\n"
            "        topics={'readiness': '/mavlink_external_nav/status',\n"
            "                'extnav': '/external_nav/status'})\n"
            "    print('LAUNCHED')\n"
            "except S.RosAdapterUnavailable as e:\n"
            "    print('UNAVAILABLE:', e)\n"
            "except Exception as e:\n"
            "    print('CRASH:', type(e).__name__, e)\n") % HERE
_cp = subprocess.run([sys.executable, "-c", _snippet], capture_output=True,
                     text=True, env=_senv, timeout=60)
ck("无 rclpy(剥离环境) → RosAdapterUnavailable(明确 INCOMPLETE 语义,不炸 producer)",
   _cp.stdout.strip().startswith("UNAVAILABLE:"), True)
print(f"    ↳ {_cp.stdout.strip()[:100]}")

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
