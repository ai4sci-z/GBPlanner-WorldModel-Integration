#!/usr/bin/env python3
"""Relay /tf -> /tf_clean, dropping wall-epoch-stamped transforms.

A node in the world-model stack (pose_mirror suspect, frames base_scan +
imu_link) publishes single wall-clock-stamped TFs into an otherwise sim-time
tree. tf2's cache prunes by 'latest - cache_time', so ONE 1.78e9 sample makes
every later sim-time sample (~60s) 'too old' and the segment freezes -- our
esdf_server then never resolves TF at cloud timestamps (measured via
tf_dump.py, 2026-07-13). Filter them out instead of patching upstream here.
"""
import rclpy
from rclpy.node import Node
from tf2_msgs.msg import TFMessage

WALL_EPOCH_MIN = 1e8  # sim time runs in tens of seconds; wall stamps ~1.78e9

rclpy.init()
node = Node('tf_clean_relay')
pub = node.create_publisher(TFMessage, '/tf_clean', 100)
dropped = {'n': 0, 'fwd': 0}


def cb(msg):
    keep = [t for t in msg.transforms
            if t.header.stamp.sec < WALL_EPOCH_MIN]
    dropped['n'] += len(msg.transforms) - len(keep)
    if keep:
        dropped['fwd'] += len(keep)
        out = TFMessage()
        out.transforms = keep
        pub.publish(out)


node.create_subscription(TFMessage, '/tf', cb, 100)
node.create_timer(10.0, lambda: node.get_logger().info(
    'forwarded %d, dropped %d wall-stamped' % (dropped['fwd'], dropped['n'])))
rclpy.spin(node)
