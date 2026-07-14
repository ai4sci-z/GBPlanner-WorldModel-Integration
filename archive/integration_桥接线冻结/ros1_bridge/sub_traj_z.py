#!/usr/bin/env python3
# rclpy 长驻订阅 /gbp/trajectory,打印每条轨迹的 wp 数与 z 范围(判据③:trajectory z 变化)。
import time

import rclpy
from trajectory_msgs.msg import MultiDOFJointTrajectory

rclpy.init()
node = rclpy.create_node("sub_traj_z")
t0 = time.monotonic()
got = {"n": 0}

def cb(m):
    got["n"] += 1
    zs = [pt.transforms[0].translation.z for pt in m.points if pt.transforms]
    if zs:
        print("TRAJ#%d wp=%d zmin=%.3f zmax=%.3f zspan=%.3f frame=%s" % (
            got["n"], len(m.points), min(zs), max(zs), max(zs) - min(zs), m.header.frame_id), flush=True)

node.create_subscription(MultiDOFJointTrajectory, "/gbp/trajectory", cb, 10)
while time.monotonic() - t0 < 120:
    rclpy.spin_once(node, timeout_sec=0.2)
print("RESULT count=%d" % got["n"], flush=True)
