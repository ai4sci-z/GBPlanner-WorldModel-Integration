#!/usr/bin/env python3
# 世界一致性核查:采一帧 voxblox tsdf 点云,输出范围+轴对齐墙线直方图峰
# (迷宫墙轴对齐 → x/y 直方图强峰=墙线坐标,可与 maze.sdf 地标逐一对照,
#  检出 90°旋转/镜像/缩放/平移/旧图叠加)
import math
import sys
from collections import Counter

import rospy
import sensor_msgs.point_cloud2 as pc2
from sensor_msgs.msg import PointCloud2

topic = sys.argv[1] if len(sys.argv) > 1 else "/gbplanner_node/tsdf_pointcloud"
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
rospy.init_node("maze_geo_probe", anonymous=True)
try:
    msg = rospy.wait_for_message(topic, PointCloud2, timeout=timeout)
except Exception as exc:
    print("NO_MSG on %s (%s)" % (topic, exc))
    raise SystemExit(2)
pts = [(p[0], p[1], p[2]) for p in pc2.read_points(msg, field_names=("x", "y", "z"), skip_nans=True)
       if all(math.isfinite(v) for v in p[:3])]
if not pts:
    print("EMPTY cloud")
    raise SystemExit(2)
xs = [p[0] for p in pts]
ys = [p[1] for p in pts]
zs = [p[2] for p in pts]
print("frame=%s points=%d" % (msg.header.frame_id, len(pts)))
print("x:[%.2f,%.2f] y:[%.2f,%.2f] z:[%.2f,%.2f]" % (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
# 只取墙体高度带(z 0.3~2.5m,排地面/天花),0.2m 桶直方图找墙线
wall = [(x, y) for (x, y, z) in pts if 0.3 <= z <= 2.5]
print("wall_band_points=%d" % len(wall))
cx = Counter(round(x / 0.2) * 0.2 for x, _ in wall)
cy = Counter(round(y / 0.2) * 0.2 for _, y in wall)
print("x_wall_peaks(前8):", sorted([(round(k, 1), v) for k, v in cx.most_common(8)]))
print("y_wall_peaks(前8):", sorted([(round(k, 1), v) for k, v in cy.most_common(8)]))
