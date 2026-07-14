#!/usr/bin/env python3
# Stage5c 失真补证探针(Review_017 §7.3):按 5s 分段输出对齐表
#   段 | wp(goal_id) | adapter intent 均值/角 | /ap/v1/cmd_vel 均值/角 | odom delta/角 | Δ(odom-intent)角
# 判读:①cmd_vel ≈ intent(桥接忠实转发);②Δ 角在运动段间近似恒定(= map↔NED 固定旋转,
#   方向关系稳定=无失真);Δ 角乱跳=失真。附 frontier/gbp 计数(去混流)。
import json
import math
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import String

DURATION_S = 240.0
SEG_S = 5.0

rclpy.init()
node = rclpy.create_node("stage5c_probe")
t0 = time.monotonic()


def now():
    return time.monotonic() - t0


class Seg:
    def __init__(self, idx):
        self.idx = idx
        self.ix = self.iy = self.i_n = 0
        self.cx = self.cy = self.c_n = 0
        self.odom0 = None
        self.odom1 = None
        self.goals = set()


S = {"frontier": 0, "gbp": 0, "status_frontier": 0, "status_gbp": 0, "odom_n": 0}
segs = {}


def seg():
    i = int(now() // SEG_S)
    if i not in segs:
        segs[i] = Seg(i)
    return segs[i]


def on_intent(m):
    try:
        d = json.loads(m.data)
    except Exception:
        return
    src = d.get("source", "")
    if src == "exploration_workflow":
        S["frontier"] += 1
        return
    if src != "gbp_traj_to_intent":
        return
    S["gbp"] += 1
    vx, vy = d.get("linear_x_mps", 0.0), d.get("linear_y_mps", 0.0)
    if abs(vx) + abs(vy) > 1e-6:
        s = seg()
        s.ix += vx
        s.iy += vy
        s.i_n += 1
        s.goals.add(d.get("goal_id", ""))


def on_cmdvel(m):
    lx, ly = m.twist.linear.x, m.twist.linear.y
    if abs(lx) + abs(ly) > 1e-6:
        s = seg()
        s.cx += lx
        s.cy += ly
        s.c_n += 1


def on_odom(m):
    S["odom_n"] += 1
    p = m.pose.pose.position
    s = seg()
    if s.odom0 is None:
        s.odom0 = (p.x, p.y)
    s.odom1 = (p.x, p.y)


def on_status(m):
    try:
        d = json.loads(m.data)
    except Exception:
        return
    st = d.get("strategy", "")
    if st == "frontier_lite":
        S["status_frontier"] += 1
    elif st == "gbplanner":
        S["status_gbp"] += 1


node.create_subscription(String, "/navlab/fcu/setpoint/intent", on_intent, 50)
# 注:不再订 /ap/v1/cmd_vel——micro-ROS agent 的端点匹配在多 participant 负载下退化
# (frame_contract 探针实测 97s 不匹配),每个 agent 话题的晚加入订阅者都会加剧;
# cmd_vel 消费证据已在 4b/4c/5c 首批定档,毋需每 run 重采。
node.create_subscription(Odometry, "/slam/odom", on_odom, qos_profile_sensor_data)
node.create_subscription(String, "/navlab/exploration/status", on_status, 50)
print("stage5c probe up (%.0fs, seg=%.0fs)" % (DURATION_S, SEG_S), flush=True)
while time.monotonic() - t0 < DURATION_S:
    rclpy.spin_once(node, timeout_sec=0.2)


def ang(x, y):
    return math.degrees(math.atan2(y, x))


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


print("=== STAGE5C_ALIGN_TABLE(仅运动段) ===", flush=True)
print("seg_t | goals | intent(vx,vy)ang | cmd_vel(vx,vy)ang | odom_d(dx,dy)ang | d_odom-intent", flush=True)
deltas = []
cmd_diffs = []
for i in sorted(segs):
    s = segs[i]
    if s.i_n == 0 or s.odom0 is None or s.odom1 is None:
        continue
    ivx, ivy = s.ix / s.i_n, s.iy / s.i_n
    dx, dy = s.odom1[0] - s.odom0[0], s.odom1[1] - s.odom0[1]
    if math.hypot(ivx, ivy) < 0.01 or math.hypot(dx, dy) < 0.03:
        continue
    ia = ang(ivx, ivy)
    oa = ang(dx, dy)
    d = wrap(oa - ia)
    deltas.append(d)
    cstr = "-"
    if s.c_n:
        cvx, cvy = s.cx / s.c_n, s.cy / s.c_n
        cstr = "(%.3f,%.3f)%.0f" % (cvx, cvy, ang(cvx, cvy))
        cmd_diffs.append(wrap(ang(cvx, cvy) - ia))
    print("%3d-%3ds | %s | (%.3f,%.3f)%.0f | %s | (%.3f,%.3f)%.0f | %+.0f" % (
        i * SEG_S, (i + 1) * SEG_S, ",".join(sorted(s.goals))[:28],
        ivx, ivy, ia, cstr, dx, dy, oa, d), flush=True)

print("=== STAGE5C_PROBE_SUMMARY ===", flush=True)
print("frontier_intent=%d gbp_intent=%d status_frontier=%d status_gbp=%d odom_n=%d" % (
    S["frontier"], S["gbp"], S["status_frontier"], S["status_gbp"], S["odom_n"]), flush=True)
if deltas:
    mean = sum(deltas) / len(deltas)
    spread = max(wrap(d - mean) for d in deltas) - min(wrap(d - mean) for d in deltas)
    print("moving_segments=%d delta_mean=%.0fdeg delta_spread=%.0fdeg (恒定=方向关系稳定/无失真)" % (
        len(deltas), mean, spread), flush=True)
    print("direction_consistency=%s" % ("STABLE" if spread <= 60 else "UNSTABLE"), flush=True)
if cmd_diffs:
    md = sum(abs(d) for d in cmd_diffs) / len(cmd_diffs)
    print("cmdvel_vs_intent_mean_absdiff=%.0fdeg (≈0=FCU 忠实转发)" % md, flush=True)
print("no_frontier_intent=%s" % (S["frontier"] == 0 and S["status_frontier"] == 0), flush=True)
