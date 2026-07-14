#!/usr/bin/env python3
# ROS1 侧采一帧 PointCloud2,报 z 分布(判据②:voxblox tsdf 是否 3D 体素)。
# 用法: ros1_cloud_z.py [topic] [timeout]
import math
import sys

import rospy
import sensor_msgs.point_cloud2 as pc2
from sensor_msgs.msg import PointCloud2

topic = sys.argv[1] if len(sys.argv) > 1 else "/gbplanner_node/tsdf_pointcloud"
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
rospy.init_node("cloud_z_probe_ros1", anonymous=True)
try:
    msg = rospy.wait_for_message(topic, PointCloud2, timeout=timeout)
except Exception as exc:
    print("NO_MSG on %s (%s)" % (topic, exc))
    raise SystemExit(2)
zs = [p[2] for p in pc2.read_points(msg, field_names=("x", "y", "z"), skip_nans=True)
      if math.isfinite(p[2])]
if zs:
    print("%s : points=%d zmin=%.3f zmax=%.3f zspan=%.3f -> %s" % (
        topic, len(zs), min(zs), max(zs), max(zs) - min(zs),
        "3D" if (max(zs) - min(zs)) > 0.3 else "FLAT"))
else:
    print("%s : no finite z" % topic)
