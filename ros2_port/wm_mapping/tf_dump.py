#!/usr/bin/env python3
"""Record every TF segment seen on /tf and /tf_static for N seconds:
parent->child, sample count, first/last stamp. Answers 'which segment of the
map->base_scan chain stops publishing' with data instead of guesses."""
import sys
import time
from collections import defaultdict

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from tf2_msgs.msg import TFMessage

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 80.0
OUT = sys.argv[2] if len(sys.argv) > 2 else '/out/tf_dump.txt'
TOPIC = sys.argv[3] if len(sys.argv) > 3 else '/tf'

rclpy.init()
node = Node('tf_dump')
seen = defaultdict(lambda: [0, None, None, ''])  # n, first, last, src


def mk(src):
    def cb(msg):
        for t in msg.transforms:
            k = (t.header.frame_id, t.child_frame_id)
            s = t.header.stamp.sec + t.header.stamp.nanosec * 1e-9
            e = seen[k]
            e[0] += 1
            e[1] = s if e[1] is None else min(e[1], s)
            e[2] = s if e[2] is None else max(e[2], s)
            e[3] = src
    return cb


node.create_subscription(TFMessage, TOPIC, mk(TOPIC), 100)
node.create_subscription(
    TFMessage, '/tf_static', mk('static'),
    QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL,
               reliability=ReliabilityPolicy.RELIABLE))

end = time.monotonic() + DUR
while time.monotonic() < end:
    rclpy.spin_once(node, timeout_sec=0.2)

with open(OUT, 'w') as f:
    f.write('%-28s -> %-28s %6s %10s %10s %s\n'
            % ('parent', 'child', 'n', 'first', 'last', 'src'))
    for (p, c), (n, a, b, src) in sorted(seen.items()):
        f.write('%-28s -> %-28s %6d %10.2f %10.2f %s\n' % (p, c, n, a, b, src))
print(open(OUT).read())
