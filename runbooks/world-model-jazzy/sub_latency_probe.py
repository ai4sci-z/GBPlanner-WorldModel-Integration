#!/usr/bin/env python3
# 容器内跑:订阅指定话题,记录 node 创建->publisher 匹配->首条消息 的真实耗时。
# 用法: sub_latency_probe.py <topic> [max_wait_sec]
import sys, time

topic = sys.argv[1]
max_wait = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

import rclpy
from rclpy.qos import qos_profile_sensor_data, QoSProfile, QoSHistoryPolicy
from rosidl_runtime_py.utilities import get_message

rclpy.init()
node = rclpy.create_node("navlab_sub_latency_probe")
t0 = time.monotonic()

# 1) 发现 topic type
topic_type = ""
while time.monotonic() - t0 < max_wait and not topic_type:
    for name, types in node.get_topic_names_and_types():
        if name == topic and types:
            topic_type = types[0]
            break
    if not topic_type:
        rclpy.spin_once(node, timeout_sec=0.1)
t_type = time.monotonic() - t0
print("type_discovered_at=%.2fs type=%s" % (t_type, topic_type), flush=True)
if not topic_type:
    print("RESULT=TYPE_NEVER_DISCOVERED", flush=True)
    sys.exit(3)

# 2) 订阅(publisher QoS 内省,同探针补丁逻辑)
sub_qos = qos_profile_sensor_data
infos = node.get_publishers_info_by_topic(topic)
if infos:
    src = infos[0].qos_profile
    sub_qos = QoSProfile(
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=max(1, getattr(src, "depth", 0) or 10),
        reliability=src.reliability,
        durability=src.durability,
    )
    print("publisher_qos: reliability=%s durability=%s" % (src.reliability, src.durability), flush=True)

holder = {"n": 0, "first": None}

def on_msg(msg):
    if holder["first"] is None:
        holder["first"] = time.monotonic() - t0
    holder["n"] += 1

sub = node.create_subscription(get_message(topic_type), topic, on_msg, sub_qos)
t_sub = time.monotonic() - t0
print("subscription_created_at=%.2fs" % t_sub, flush=True)

matched_at = None
last_report = 0.0
while time.monotonic() - t0 < max_wait:
    rclpy.spin_once(node, timeout_sec=0.1)
    el = time.monotonic() - t0
    pubs = node.count_publishers(topic)
    if matched_at is None and pubs > 0:
        matched_at = el
        print("graph_publisher_count>0_at=%.2fs" % el, flush=True)
    if holder["first"] is not None:
        print("RESULT=FIRST_MSG first_msg_at=%.2fs (after sub +%.2fs) count=%d" % (
            holder["first"], holder["first"] - t_sub, holder["n"]), flush=True)
        break
    if el - last_report >= 2.0:
        print("  t=%.1fs pubs=%d msgs=%d" % (el, pubs, holder["n"]), flush=True)
        last_report = el
else:
    pass

if holder["first"] is None:
    print("RESULT=NO_MSG_WITHIN %.1fs (pubs=%d)" % (max_wait, node.count_publishers(topic)), flush=True)
node.destroy_node()
rclpy.shutdown()
