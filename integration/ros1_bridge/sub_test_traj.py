#!/usr/bin/env python3
# 诊断对照组:rclpy 订阅 /gbp/trajectory,打印首条到达时间与计数。
import time
import rclpy
from trajectory_msgs.msg import MultiDOFJointTrajectory

rclpy.init()
node = rclpy.create_node("sub_test_traj")
t0 = time.monotonic()
got = {"n": 0}

def cb(m):
    got["n"] += 1
    if got["n"] == 1:
        print("FIRST_MSG_AT=%.2fs frame=%s" % (time.monotonic() - t0, m.header.frame_id), flush=True)

node.create_subscription(MultiDOFJointTrajectory, "/gbp/trajectory", cb, 10)
while time.monotonic() - t0 < 70:
    rclpy.spin_once(node, timeout_sec=0.2)
print("RESULT count=%d" % got["n"], flush=True)
