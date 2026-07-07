#!/usr/bin/env python3
# Stage5·轴向校准探针:bootstrap 就绪后发纯平移 intent 序列(零 yaw),
# 记录 /slam/odom 与 /ap/v1/pose/filtered 各阶段位移向量 → 实测 intent→运动 映射。
# 阶段:hold 2s → +x 0.08 (10s) → hold 2s → +y 0.08 (10s) → hold 2s → 零速持续。
import json
import math
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import String

TOTAL_S = 220.0
V = 0.08
PHASES = [
    ("hold0", 2.0, 0.0, 0.0),
    ("plus_x", 10.0, V, 0.0),
    ("hold1", 2.0, 0.0, 0.0),
    ("plus_y", 10.0, 0.0, V),
    ("hold2", 2.0, 0.0, 0.0),
]

rclpy.init()
node = rclpy.create_node("cal_axis_probe")
t0 = time.monotonic()
S = {"ready": False, "ready_t": None, "odom": None, "ap": None,
     "phase_idx": -1, "phase_t0": None, "marks": [], "done": False}


def on_ctrl(m):
    try:
        d = json.loads(m.data)
    except Exception:
        return
    if not S["ready"] and (d.get("ok") or d.get("ready")):
        S["ready"] = True
        S["ready_t"] = time.monotonic()
        print("t=%.1f CONTROLLER READY -> start calibration sequence" % (time.monotonic() - t0), flush=True)


def on_odom(m):
    p = m.pose.pose.position
    S["odom"] = (p.x, p.y)


def on_ap(m):
    p = m.pose.position
    S["ap"] = (p.x, p.y)


node.create_subscription(String, "/navlab/fcu/controller/status", on_ctrl, 10)
node.create_subscription(Odometry, "/slam/odom", on_odom, qos_profile_sensor_data)
node.create_subscription(PoseStamped, "/ap/v1/pose/filtered", on_ap, qos_profile_sensor_data)
pub = node.create_publisher(String, "/navlab/fcu/setpoint/intent", 10)

print("cal_axis probe up: waiting controller ready", flush=True)
last_pub = 0.0
while time.monotonic() - t0 < TOTAL_S:
    rclpy.spin_once(node, timeout_sec=0.05)
    now = time.monotonic()
    if not S["ready"]:
        continue
    # 推进阶段
    el = now - S["ready_t"]
    acc = 0.0
    cur = None
    for i, (name, dur, vx, vy) in enumerate(PHASES):
        if el < acc + dur:
            cur = (i, name, vx, vy)
            break
        acc += dur
    if cur is None:
        cur = (len(PHASES), "zero_tail", 0.0, 0.0)
    i, name, vx, vy = cur
    if i != S["phase_idx"]:
        S["phase_idx"] = i
        S["marks"].append((name, now, S["odom"], S["ap"]))
        print("t=%.1f PHASE %s start odom=%s ap=%s" % (now - t0, name, S["odom"], S["ap"]), flush=True)
    if now - last_pub >= 0.4:
        last_pub = now
        intent = {"ok": True, "source": "cal_axis_probe", "strategy": "gbplanner",
                  "goal_id": "cal_%s" % name,
                  "linear_x_mps": vx, "linear_y_mps": vy, "yaw_rate_radps": 0.0}
        pub.publish(String(data=json.dumps(intent)))
    if i == len(PHASES) and not S["done"]:
        S["done"] = True
        print("=== CAL_SUMMARY ===", flush=True)
        for j in range(len(S["marks"]) - 1):
            n0, tt0, o0, a0 = S["marks"][j]
            n1, tt1, o1, a1 = S["marks"][j + 1]
            def d(p0, p1):
                if p0 is None or p1 is None:
                    return None
                return (round(p1[0] - p0[0], 3), round(p1[1] - p0[1], 3))
            do, da = d(o0, o1), d(a0, a1)
            ang = ""
            if do and (abs(do[0]) + abs(do[1])) > 0.02:
                ang = " odom_angle=%.0fdeg" % math.degrees(math.atan2(do[1], do[0]))
            print("phase=%s dur=%.1fs odom_delta=%s ap_delta=%s%s" % (n0, tt1 - tt0, do, da, ang), flush=True)
        print("=== CAL_DONE ===", flush=True)

if not S["done"]:
    print("CAL_INCOMPLETE ready=%s marks=%d" % (S["ready"], len(S["marks"])), flush=True)
