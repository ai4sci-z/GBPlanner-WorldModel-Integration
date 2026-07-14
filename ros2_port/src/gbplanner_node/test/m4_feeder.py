#!/usr/bin/env python3
"""M4 smoke feeder: synthetic room walls + odometry + TF for gbplanner_node,
then wait for /gbp/trajectory from the pci_trigger. Exit 0 iff a non-empty
trajectory arrives."""
import math
import struct
import sys
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import PointCloud2, PointField
from tf2_ros import TransformBroadcaster
from trajectory_msgs.msg import MultiDOFJointTrajectory

WORLD = 'world'
BODY = 'base_link'
TIMEOUT = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0


def room_cloud(node):
    """Open box around the robot: floor + 3 walls, one side open (frontier)."""
    pts = []
    for i in range(-40, 41):          # floor 8x8m @0.1m
        for j in range(-40, 41):
            pts.append((i * 0.1, j * 0.1, -0.5))
    for i in range(-40, 41):          # walls at x=+4, y=±4 up to z=2
        for k in range(0, 25):
            pts.append((4.0, i * 0.1, k * 0.1))
            pts.append((i * 0.1, 4.0, k * 0.1))
            pts.append((i * 0.1, -4.0, k * 0.1))
    data = b''.join(struct.pack('<fff', *p) for p in pts)
    m = PointCloud2()
    m.header.frame_id = BODY
    m.header.stamp = node.get_clock().now().to_msg()
    m.height, m.width = 1, len(pts)
    m.fields = [PointField(name=c, offset=o, datatype=7, count=1)
                for c, o in (('x', 0), ('y', 4), ('z', 8))]
    m.point_step, m.row_step = 12, 12 * len(pts)
    m.data = data
    m.is_dense = True
    return m


def main():
    rclpy.init()
    node = Node('m4_feeder')
    br = TransformBroadcaster(node)
    odom_pub = node.create_publisher(Odometry, '/odometry', 10)
    cloud_pub = node.create_publisher(
        PointCloud2, '/gbplanner_node/pointcloud', 5)
    got = {'n': 0}
    node.create_subscription(MultiDOFJointTrajectory, '/gbp/trajectory',
                             lambda m: got.__setitem__('n', len(m.points)),
                             10)

    t_end = time.monotonic() + TIMEOUT
    i = 0
    while time.monotonic() < t_end and got['n'] == 0:
        stamp = node.get_clock().now().to_msg()
        tf = TransformStamped()
        tf.header.stamp = stamp
        tf.header.frame_id = WORLD
        tf.child_frame_id = BODY
        tf.transform.translation.z = 1.0
        tf.transform.rotation.w = 1.0
        br.sendTransform(tf)

        odo = Odometry()
        odo.header.stamp = stamp
        odo.header.frame_id = WORLD
        odo.pose.pose.position.z = 1.0
        odo.pose.pose.orientation.w = 1.0
        odom_pub.publish(odo)

        if i % 5 == 0:
            cloud = room_cloud(node)
            cloud.header.stamp = stamp
            cloud_pub.publish(cloud)
        i += 1
        rclpy.spin_once(node, timeout_sec=0.1)

    print('TRAJ_POINTS=%d' % got['n'])
    sys.exit(0 if got['n'] > 0 else 1)


if __name__ == '__main__':
    main()
