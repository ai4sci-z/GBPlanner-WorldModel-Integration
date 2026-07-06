#!/usr/bin/env python3
# Stage4b 消费证据:实时订 /ap/v1/cmd_vel(fcu_controller 把 intent 速度直发这里),
# 打印每次速度变化样本;特征匹配:|angular.z-(-0.300)|<0.01 = 我们的限幅 yaw_rate。
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TwistStamped

rclpy.init()
node = rclpy.create_node("cmdvel_probe")
t0 = time.monotonic()
state = {"last": None, "n": 0, "gbp_hits": 0}

def cb(m):
    state["n"] += 1
    v = (round(m.twist.linear.x, 3), round(m.twist.linear.y, 3), round(m.twist.angular.z, 3))
    if v != state["last"]:
        state["last"] = v
        tag = ""
        if abs(m.twist.angular.z + 0.300) < 0.012 or abs(abs(m.twist.linear.x) - 0.024) < 0.004:
            state["gbp_hits"] += 1
            tag = "  <<< GBP-SIGNATURE"
        print("t=%.1f cmd_vel lin=(%.3f,%.3f) ang.z=%.3f%s" % (
            time.monotonic() - t0, m.twist.linear.x, m.twist.linear.y, m.twist.angular.z, tag), flush=True)

node.create_subscription(TwistStamped, "/ap/v1/cmd_vel", cb, qos_profile_sensor_data)
while time.monotonic() - t0 < 150:
    rclpy.spin_once(node, timeout_sec=0.2)
print("RESULT total=%d gbp_signature_hits=%d" % (state["n"], state["gbp_hits"]), flush=True)
