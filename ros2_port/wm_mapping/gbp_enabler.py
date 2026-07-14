#!/usr/bin/env python3
"""M5: publish /gbp/enable from a revocable lease (Review 001 P0-2).

Enable is true only while the FCU controller keeps renewing a strict
controller_ready status (exact state match, not a fuzzy ok-or-ready), and
drops within the lease TTL on degradation, landing, restart, or silence.
The adapter's own five-condition latch stays the second gate; this node is
the first, fail-closed one. Logic in enable_lease.py (unit-tested, 8 cases).
"""
import json
import os
import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enable_lease import EnableLease

rclpy.init()
node = Node('gbp_enabler')
pub = node.create_publisher(Bool, '/gbp/enable', 10)
lease = EnableLease(ttl_sec=3.0)
last_published = {'v': None}


def on_status(msg):
    try:
        d = json.loads(msg.data)
    except ValueError:
        return  # malformed frames never renew (and never revoke) the lease
    lease.observe(d, time.monotonic())


node.create_subscription(String, '/navlab/fcu/controller/status', on_status, 10)


def tick():
    m = Bool()
    m.data = lease.enabled(time.monotonic())
    pub.publish(m)
    if last_published['v'] != m.data:
        node.get_logger().info(f'/gbp/enable -> {m.data}')
        last_published['v'] = m.data


node.create_timer(0.5, tick)
try:
    rclpy.spin(node)
finally:
    # best-effort fail-closed on shutdown
    m = Bool()
    m.data = False
    try:
        pub.publish(m)
    except Exception:
        pass
