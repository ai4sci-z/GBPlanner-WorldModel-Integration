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
node, spins, shutdowns, factory = make_factory()
ad = S.ConcreteRosSubscribeAdapter(ros_domain_id="7", system_domain_id="7",
                                   node_factory=factory)
kinds = sorted({c[0] for c in node.calls})
ck("实际只出现 create_subscription", kinds, ["create_subscription"])
ck("恰两个订阅", len([c for c in node.calls if c[0] == "create_subscription"]), 2)
topics = sorted(c[2] for c in node.calls if c[0] == "create_subscription")
ck("订阅 topic 与契约一致", topics, sorted(S.ROS_SUBSCRIBE_TOPICS.values()))
ck("publisher/service/client/参数方法零调用",
   [c for c in node.calls if c[0] != "create_subscription"], [])

print("======== domain / callback / shutdown 语义 ========")
try:
    S.ConcreteRosSubscribeAdapter(ros_domain_id="7", system_domain_id="8",
                                  node_factory=factory)
    ck("domain 不一致拒绝", "被放行", "RosWriteRefused")
except S.RosWriteRefused:
    ck("domain 不一致拒绝", "RosWriteRefused", "RosWriteRefused")
# callback 只写内部队列
cb = node.subs[S.ROS_SUBSCRIBE_TOPICS["extnav"]]
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

print("======== rclpy 不可用语义(default factory)========")
try:
    S.ConcreteRosSubscribeAdapter(ros_domain_id="0", system_domain_id="0")
    got = "构造成功(本机竟有 rclpy?)"
except S.RosAdapterUnavailable as e:
    got = "RosAdapterUnavailable"
    print(f"    ↳ {e}")
except S.RosWriteRefused:
    got = "RosWriteRefused"
ck("宿主无 rclpy → RosAdapterUnavailable(明确 INCOMPLETE 语义,不炸 producer)",
   got, "RosAdapterUnavailable")

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
