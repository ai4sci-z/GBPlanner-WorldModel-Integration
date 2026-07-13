#!/usr/bin/env python3
"""Gate /cloud_in -> /cloud_gated. Deleting is not needed: once /out/gate_off
exists, forwarding stops. Lets the esdf_server's pointcloud queue drain before
save_map -- the port's canTransform(0.1s) blocking wait otherwise starves the
single-threaded executor and the service never answers (transformer.cc:162).
"""
import os

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2

FLAG = '/out/gate_off'

rclpy.init()
node = Node('cloud_gate')
pub = node.create_publisher(PointCloud2, '/cloud_gated', 5)
n = {'fwd': 0}


def cb(msg):
    if os.path.exists(FLAG):
        return
    n['fwd'] += 1
    pub.publish(msg)


node.create_subscription(PointCloud2, '/cloud_in', cb, qos_profile_sensor_data)
node.create_timer(10.0, lambda: node.get_logger().info(
    'gated-forwarded %d clouds' % n['fwd']))
rclpy.spin(node)
