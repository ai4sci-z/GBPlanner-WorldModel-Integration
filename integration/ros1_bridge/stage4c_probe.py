#!/usr/bin/env python3
# Stage4c 归因探针:一个节点同订四路,产出"去混流 + 运动可归因"证据。
#  - /navlab/fcu/setpoint/intent : 按 source 分类计数(frontier=exploration_workflow 应为 0)
#  - /ap/v1/cmd_vel              : GBP 签名(|az|≈0.300 或 速度模长≈0.080/0.024;frontier 值域 0.10/0.06 不可能)
#  - /slam/odom                  : xy 路径累计;path_cmd_active = 仅在签名 cmd_vel 活跃 ±1.5s 窗口内累计(时间段对齐)
#  - /navlab/exploration/status  : 按 strategy 分类(frontier_lite 应为 0)
import json
import math
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import String

DURATION_S = 240.0
SIG_WINDOW_S = 1.5

rclpy.init()
node = rclpy.create_node("stage4c_probe")
t0 = time.monotonic()
S = {
    "frontier_intent": 0, "gbp_intent": 0, "gbp_motion_intent": 0, "other_intent": 0,
    "first_gbp_motion_t": None, "last_gbp_motion_t": None,
    "cmdvel_n": 0, "cmd_nonzero": 0, "gbp_sig": 0, "sig_first_t": None, "sig_last_t": None,
    "status_gbp": 0, "status_frontier": 0, "status_other": 0,
    "odom_n": 0, "path_total": 0.0, "path_from_first_gbp": 0.0, "path_cmd_active": 0.0,
    "last_xy": None, "z_max": -99.0,
}


def now():
    return time.monotonic() - t0


def on_intent(m):
    try:
        d = json.loads(m.data)
    except Exception:
        return
    src = d.get("source", "")
    if src == "exploration_workflow":
        S["frontier_intent"] += 1
        if S["frontier_intent"] <= 3:
            print("t=%.1f FRONTIER-INTENT(混流!) %s" % (now(), m.data[:160]), flush=True)
    elif src == "gbp_traj_to_intent":
        S["gbp_intent"] += 1
        v = abs(d.get("linear_x_mps", 0.0)) + abs(d.get("linear_y_mps", 0.0)) + abs(d.get("yaw_rate_radps", 0.0))
        if v > 1e-6:
            S["gbp_motion_intent"] += 1
            if S["first_gbp_motion_t"] is None:
                S["first_gbp_motion_t"] = now()
                print("t=%.1f FIRST-GBP-MOTION-INTENT %s" % (now(), m.data[:200]), flush=True)
            S["last_gbp_motion_t"] = now()
    else:
        S["other_intent"] += 1


def on_cmdvel(m):
    S["cmdvel_n"] += 1
    lx, ly, az = m.twist.linear.x, m.twist.linear.y, m.twist.angular.z
    if abs(lx) + abs(ly) + abs(az) > 1e-6:
        S["cmd_nonzero"] += 1
    spd = math.hypot(lx, ly)
    # GBP 签名:yaw 限幅 0.300 | 大偏航减速档 0.024 | 直行档 0.080(frontier=0.10/0.06,hold=0)
    if abs(abs(az) - 0.300) < 0.012 or abs(spd - 0.024) < 0.004 or abs(spd - 0.080) < 0.004:
        S["gbp_sig"] += 1
        if S["sig_first_t"] is None:
            S["sig_first_t"] = now()
        S["sig_last_t"] = now()
        if S["gbp_sig"] <= 8:
            print("t=%.1f cmd_vel lin=(%.3f,%.3f) ang.z=%.3f <<< GBP-SIGNATURE" % (now(), lx, ly, az), flush=True)


def on_odom(m):
    S["odom_n"] += 1
    p = m.pose.pose.position
    S["z_max"] = max(S["z_max"], p.z)
    if S["last_xy"] is not None:
        step = math.hypot(p.x - S["last_xy"][0], p.y - S["last_xy"][1])
        if step <= 1.0:
            S["path_total"] += step
            if S["first_gbp_motion_t"] is not None:
                S["path_from_first_gbp"] += step
            if S["sig_last_t"] is not None and now() - S["sig_last_t"] < SIG_WINDOW_S:
                S["path_cmd_active"] += step
    S["last_xy"] = (p.x, p.y)


def on_status(m):
    try:
        d = json.loads(m.data)
    except Exception:
        return
    st = d.get("strategy", "")
    if st == "gbplanner":
        S["status_gbp"] += 1
    elif st == "frontier_lite":
        S["status_frontier"] += 1
    else:
        S["status_other"] += 1


node.create_subscription(String, "/navlab/fcu/setpoint/intent", on_intent, 50)
node.create_subscription(TwistStamped, "/ap/v1/cmd_vel", on_cmdvel, qos_profile_sensor_data)
node.create_subscription(Odometry, "/slam/odom", on_odom, qos_profile_sensor_data)
node.create_subscription(String, "/navlab/exploration/status", on_status, 50)
print("stage4c probe up (%.0fs window)" % DURATION_S, flush=True)
while time.monotonic() - t0 < DURATION_S:
    rclpy.spin_once(node, timeout_sec=0.2)

print("=== STAGE4C_PROBE_SUMMARY ===", flush=True)
for k in ("frontier_intent", "gbp_intent", "gbp_motion_intent", "other_intent",
          "cmdvel_n", "cmd_nonzero", "gbp_sig",
          "status_gbp", "status_frontier", "status_other", "odom_n"):
    print("%s=%d" % (k, S[k]), flush=True)
print("path_total_m=%.4f" % S["path_total"], flush=True)
print("path_from_first_gbp_m=%.4f" % S["path_from_first_gbp"], flush=True)
print("path_cmd_active_m=%.4f" % S["path_cmd_active"], flush=True)
print("odom_z_max=%.3f" % S["z_max"], flush=True)
print("timeline first_gbp_motion_t=%s last_gbp_motion_t=%s sig_first_t=%s sig_last_t=%s" % (
    S["first_gbp_motion_t"], S["last_gbp_motion_t"], S["sig_first_t"], S["sig_last_t"]), flush=True)
no_frontier = S["frontier_intent"] == 0 and S["status_frontier"] == 0
print("no_frontier_intent=%s" % no_frontier, flush=True)
verdict = (no_frontier and S["gbp_motion_intent"] > 0 and S["gbp_sig"] > 0
           and S["path_cmd_active"] >= 0.10)
print("PROBE_VERDICT=%s" % ("PASS" if verdict else "FAIL"), flush=True)
