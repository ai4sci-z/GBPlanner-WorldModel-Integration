#!/usr/bin/env python3
# 校准 rosbag 离线提取:intent 相位时间线 + /slam/odom(map)与 /navlab/fcu/local_position_pose(NED)
# 逐秒轨迹与各相位位移向量(双坐标系对照,分离 SLAM 漂移 vs 物理运动)。
# 用法: python3 cal_bag_extract.py <rosbag_dir>
import json
import math
import sys

import rosbag2_py
from rclpy.serialization import deserialize_message
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String

bag = sys.argv[1]
try:
    reader = rosbag2_py.SequentialCompressionReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag, storage_id=""),
                rosbag2_py.ConverterOptions(input_serialization_format="cdr",
                                            output_serialization_format="cdr"))
except Exception:
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag, storage_id=""),
                rosbag2_py.ConverterOptions(input_serialization_format="cdr",
                                            output_serialization_format="cdr"))
types = {t.name: t.type for t in reader.get_all_topics_and_types()}

TOP_ODOM = "/slam/odom"
TOP_NED = "/navlab/fcu/local_position_pose"
TOP_INT = "/navlab/fcu/setpoint/intent"

odom = []   # (t, x, y)
ned = []    # (t, x, y, z)
phases = [] # (t, goal_id)
last_goal = None
t0 = None

while reader.has_next():
    topic, data, t_ns = reader.read_next()
    if topic not in (TOP_ODOM, TOP_NED, TOP_INT):
        continue
    t = t_ns / 1e9
    if t0 is None:
        t0 = t
    tr = t - t0
    if topic == TOP_ODOM:
        m = deserialize_message(data, Odometry)
        p = m.pose.pose.position
        odom.append((tr, p.x, p.y))
    elif topic == TOP_NED:
        m = deserialize_message(data, PoseStamped)
        p = m.pose.position
        ned.append((tr, p.x, p.y, p.z))
    else:
        m = deserialize_message(data, String)
        try:
            d = json.loads(m.data)
        except Exception:
            continue
        g = d.get("goal_id", "")
        if g != last_goal:
            last_goal = g
            phases.append((tr, g))

print("== 相位时间线(goal_id 变更) ==")
for tr, g in phases:
    print("t=%.1f %s" % (tr, g))

def at(series, t):
    best = None
    for row in series:
        if row[0] <= t:
            best = row
        else:
            break
    return best

def delta(series, t0_, t1_):
    a, b = at(series, t0_), at(series, t1_)
    if a is None or b is None:
        return None
    return tuple(round(b[i] - a[i], 3) for i in range(1, len(a)))

marks = [(tr, g) for tr, g in phases]
print("== 各相位位移(map=slam/odom | ned=local_position_pose) ==")
for i in range(len(marks)):
    tA = marks[i][0]
    tB = marks[i + 1][0] if i + 1 < len(marks) else (odom[-1][0] if odom else tA)
    dm = delta(odom, tA, tB)
    dn = delta(ned, tA, tB)
    ang_m = ang_n = ""
    if dm and math.hypot(dm[0], dm[1]) > 0.02:
        ang_m = " map_ang=%.0f" % math.degrees(math.atan2(dm[1], dm[0]))
    if dn and math.hypot(dn[0], dn[1]) > 0.02:
        ang_n = " ned_ang=%.0f" % math.degrees(math.atan2(dn[1], dn[0]))
    print("phase=%s %.1f→%.1f map_d=%s%s ned_d=%s%s" % (marks[i][1], tA, tB, dm, ang_m, dn, ang_n))

print("== 逐2秒轨迹(相位窗口附近) ==")
if phases:
    w0, w1 = phases[0][0] - 4, (phases[-1][0] + 16)
    t = w0
    while t <= w1:
        o = at(odom, t)
        n = at(ned, t)
        print("t=%.0f map=(%s) ned=(%s)" % (
            t,
            "%.2f,%.2f" % (o[1], o[2]) if o else "-",
            "%.2f,%.2f,%.2f" % (n[1], n[2], n[3]) if n else "-"))
        t += 2.0
