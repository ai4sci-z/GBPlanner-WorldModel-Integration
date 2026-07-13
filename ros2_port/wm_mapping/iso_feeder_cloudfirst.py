#!/usr/bin/env python3
"""Isolation feeder: fake /clock + /tf_clean + /cloud_in, then save_map.
Reproduces the exact mapper wiring without the simulator."""
import struct
import time

import rclpy
from rclpy.node import Node
from tf2_msgs.msg import TFMessage
from geometry_msgs.msg import TransformStamped
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import PointCloud2, PointField
from voxblox_msgs.srv import FilePath

rclpy.init()
n = Node('iso_feeder')
clk = n.create_publisher(Clock, '/clock', 10)
tfp = n.create_publisher(TFMessage, '/tf_clean', 50)
pcp = n.create_publisher(PointCloud2, '/cloud_in', 10)


def cloud(sec, nsec):
    pts = [(2.0 + 0.01 * i, -1.0 + 0.02 * i, 0.5) for i in range(100)]
    data = b''.join(struct.pack('<fff', *p) for p in pts)
    m = PointCloud2()
    m.header.stamp.sec = sec
    m.header.stamp.nanosec = nsec
    m.header.frame_id = 'base_scan'
    m.height, m.width = 1, 100
    m.fields = [PointField(name=c, offset=o, datatype=7, count=1)
                for c, o in (('x', 0), ('y', 4), ('z', 8))]
    m.point_step, m.row_step = 12, 1200
    m.data = data
    m.is_dense = True
    return m


for k in range(20):
    t = 50.0 + k * 0.5
    sec, nsec = int(t), int((t - int(t)) * 1e9)
    c = Clock()
    c.clock.sec, c.clock.nanosec = sec, nsec
    clk.publish(c)
    tf = TransformStamped()
    tf.header.stamp.sec, tf.header.stamp.nanosec = sec, nsec
    tf.header.frame_id, tf.child_frame_id = 'map', 'base_scan'
    tf.transform.rotation.w = 1.0
    if k >= 6:
        m = TFMessage()
        m.transforms = [tf]
        tfp.publish(m)
    pcp.publish(cloud(sec, nsec))
    time.sleep(0.4)

time.sleep(2)
cli = n.create_client(FilePath, '/voxblox/save_map')
print('svc:', cli.wait_for_service(timeout_sec=10))
fut = cli.call_async(FilePath.Request(file_path='/out/iso_test.voxblox'))
rclpy.spin_until_future_complete(n, fut, timeout_sec=15)
print('save:', fut.result())
