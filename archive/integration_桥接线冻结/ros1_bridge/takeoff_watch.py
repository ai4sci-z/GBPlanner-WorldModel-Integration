#!/usr/bin/env python3
# 最小起飞观察:订 /ap/v1/pose/filtered(飞控位姿),每秒打一行 z——看它从 ~0 爬到 ~0.5
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import PoseStamped

rclpy.init()
node = rclpy.create_node("takeoff_watch")
t0 = time.monotonic()
S = {"z": None, "z0": None, "last": 0.0, "zmax": -9.9}


def cb(m):
    S["z"] = m.pose.position.z
    if S["z0"] is None:
        S["z0"] = S["z"]
    S["zmax"] = max(S["zmax"], S["z"])


node.create_subscription(PoseStamped, "/ap/v1/pose/filtered", cb, qos_profile_sensor_data)
print("takeoff_watch: 等 /ap/v1/pose/filtered(飞控位姿,NED 惯例:z 负=向上)…", flush=True)
while time.monotonic() - t0 < 180:
    rclpy.spin_once(node, timeout_sec=0.2)
    if S["z"] is not None and time.monotonic() - S["last"] >= 2.0:
        S["last"] = time.monotonic()
        print("t=%5.1fs  z=%.3f m(NED,负=向上)" % (time.monotonic() - t0, S["z"]), flush=True)
    if S["z0"] is not None and abs(S["z"] - S["z0"]) >= 0.3:
        print(">>> TAKEOFF CONFIRMED: |Δz|=%.2fm(%.2f→%.2f,NED 负=向上=离地)<<<" % (
            abs(S["z"] - S["z0"]), S["z0"], S["z"]), flush=True)
        break
print("takeoff_watch end.", flush=True)
