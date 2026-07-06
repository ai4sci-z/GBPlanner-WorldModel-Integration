#!/usr/bin/env python3
# 3D 判据探针:枚举图上所有 PointCloud2 话题,订阅并统计 z 分布(min/max/std/点数)。
# z 有真实变化 = world-model 已有 3D 点云(Review_008 §3.2 判据①)。
import time
import struct as pystruct

import rclpy
from rclpy.qos import qos_profile_sensor_data, QoSProfile, QoSHistoryPolicy
from rosidl_runtime_py.utilities import get_message

rclpy.init()
node = rclpy.create_node("cloud_z_probe")
t0 = time.monotonic()

# 1) 找 PointCloud2 话题
targets = []
while time.monotonic() - t0 < 30 and not targets:
    for name, types in node.get_topic_names_and_types():
        if "sensor_msgs/msg/PointCloud2" in types:
            targets.append(name)
    if not targets:
        rclpy.spin_once(node, timeout_sec=0.3)
print("pointcloud2 topics:", targets, flush=True)
if not targets:
    print("RESULT=NO_POINTCLOUD2_TOPIC", flush=True)
    raise SystemExit(2)

# 2) 逐个订阅采样(publisher QoS 内省)
def analyze(name, timeout=25.0):
    holder = {"msg": None}
    infos = node.get_publishers_info_by_topic(name)
    qos = qos_profile_sensor_data
    if infos:
        src = infos[0].qos_profile
        qos = QoSProfile(history=QoSHistoryPolicy.KEEP_LAST, depth=5,
                         reliability=src.reliability, durability=src.durability)
    sub = node.create_subscription(get_message("sensor_msgs/msg/PointCloud2"), name,
                                   lambda m: holder.__setitem__("msg", m), qos)
    t1 = time.monotonic()
    while time.monotonic() - t1 < timeout and holder["msg"] is None:
        rclpy.spin_once(node, timeout_sec=0.2)
    node.destroy_subscription(sub)
    m = holder["msg"]
    if m is None:
        print("  %s : NO_MSG within %.0fs" % (name, timeout), flush=True)
        return
    # 找 z 字段 offset
    zoff, zdt = None, None
    for f in m.fields:
        if f.name == "z":
            zoff, zdt = f.offset, f.datatype
    n = m.width * m.height
    zs = []
    if zoff is not None and zdt == 7:  # FLOAT32
        import math
        step = m.point_step
        data = bytes(m.data)
        for i in range(0, min(n, 30000)):
            (z,) = pystruct.unpack_from("<f", data, i * step + zoff)
            if math.isfinite(z):  # 滤 NaN 与 ±inf(无回波方向的正常语义)
                zs.append(z)
    if zs:
        mean = sum(zs) / len(zs)
        std = (sum((z - mean) ** 2 for z in zs) / len(zs)) ** 0.5
        print("  %s : frame=%s points=%d finite=%d zmin=%.3f zmax=%.3f zstd=%.4f -> %s" % (
            name, m.header.frame_id, n, len(zs), min(zs), max(zs), std,
            "3D" if (max(zs) - min(zs)) > 0.3 else "FLAT/2D"), flush=True)
    else:
        print("  %s : frame=%s points=%d (no float32 z)" % (name, m.header.frame_id, n), flush=True)

for name in targets:
    analyze(name)
print("RESULT=DONE", flush=True)
