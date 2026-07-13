#!/usr/bin/env python3
"""Secondary acceptance evidence straight from live topics: sizes and z-span
of /voxblox/surface_pointcloud and /voxblox/esdf_pointcloud."""
import struct
import sys
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 70.0
OUT = sys.argv[2] if len(sys.argv) > 2 else '/out/live_stats.txt'

rclpy.init()
node = Node('live_stats')
best = {}


def zspan(msg):
    zo = next((f.offset for f in msg.fields if f.name == 'z'), None)
    if zo is None or msg.width == 0:
        return None
    zs = [struct.unpack_from('<f', msg.data, i * msg.point_step + zo)[0]
          for i in range(0, msg.width, max(1, msg.width // 2000))]
    return (min(zs), max(zs))


def mk(name):
    def cb(msg):
        pts = msg.width * msg.height
        if pts > best.get(name, {}).get('points', -1):
            best[name] = {'points': pts, 'zspan': zspan(msg),
                          'frame': msg.header.frame_id}
    return cb


node.create_subscription(PointCloud2, '/voxblox/surface_pointcloud',
                         mk('surface'), 5)
node.create_subscription(PointCloud2, '/voxblox/esdf_pointcloud',
                         mk('esdf_slice'), 5)

end = time.monotonic() + DUR
while time.monotonic() < end:
    rclpy.spin_once(node, timeout_sec=0.2)

with open(OUT, 'w') as f:
    for k, v in sorted(best.items()):
        f.write('%s: max_points=%d zspan=%s frame=%s\n'
                % (k, v['points'], v['zspan'], v['frame']))
    if not best:
        f.write('NO_VOXBLOX_OUTPUT_SEEN\n')
print(open(OUT).read())
