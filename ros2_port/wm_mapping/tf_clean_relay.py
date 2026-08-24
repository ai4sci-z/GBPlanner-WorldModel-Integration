#!/usr/bin/env python3
"""Own the M5 planning frame and relay all unrelated healthy transforms.

A node in the world-model stack (pose_mirror suspect, frames base_scan +
imu_link) publishes single wall-clock-stamped TFs into an otherwise sim-time
tree. tf2's cache prunes by 'latest - cache_time', so ONE 1.78e9 sample makes
every later sim-time sample (~60s) 'too old' and the segment freezes -- our
esdf_server then never resolves TF at cloud timestamps (measured via
tf_dump.py, 2026-07-13). Filter them out instead of patching upstream here.

Cartographer is intentionally 2D, and the exploration runtime's
/external_nav/odom preserves z=0 even though it gates on /height/estimate.
The range-derived height was also zero in run 20260824T043724 while the FCU EKF
reported 0.45m. This relay therefore combines external-nav x/y/orientation with
the fresh, non-truth FCU sensor-fusion height from
/navlab/fcu/local_position_pose. It publishes that exact fused state as both
/gbp/planning_odom and map -> base_link on /tf_clean.
"""
import copy
import time

import rclpy
from geometry_msgs.msg import PoseStamped, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from tf2_msgs.msg import TFMessage

from planning_frame import (
    WALL_EPOCH_MIN,
    should_forward_tf,
    valid_external_nav_odom,
    valid_planning_height,
)


class PlanningFrameRelay(Node):
    def __init__(self):
        super().__init__('tf_clean_relay')
        self.tf_pub = self.create_publisher(TFMessage, '/tf_clean', 100)
        self.odom_pub = self.create_publisher(Odometry, '/gbp/planning_odom', 10)
        self.create_subscription(TFMessage, '/tf', self.on_tf, 100)
        self.create_subscription(
            Odometry, '/external_nav/odom', self.on_external_nav_odom, 10)
        self.create_subscription(
            PoseStamped, '/navlab/fcu/local_position_pose',
            self.on_fcu_local_position, 10)
        self.create_timer(10.0, self.report)
        self.fcu_height = None
        self.fcu_height_time = 0.0
        self.stats = {'forwarded': 0, 'wall_dropped': 0,
                      'planar_replaced': 0, 'planning_odom': 0,
                      'invalid_external_nav': 0, 'height_unavailable': 0,
                      'invalid_fcu_height': 0, 'planning_z_max': 0.0}
        self.get_logger().info(
            'planning frame relay: /external_nav/odom x/y + FCU EKF z -> '
            '/gbp/planning_odom + map->base_link on /tf_clean')

    def on_fcu_local_position(self, msg):
        height = msg.pose.position.z
        if valid_planning_height(height, 0.0):
            self.fcu_height = float(height)
            self.fcu_height_time = time.monotonic()
        else:
            # Do not retain a previously valid sample after FCU z diverges.
            self.fcu_height = None
            self.fcu_height_time = 0.0
            self.stats['invalid_fcu_height'] += 1

    def on_tf(self, msg):
        keep = []
        for transform in msg.transforms:
            if should_forward_tf(
                    transform.header.stamp.sec,
                    transform.header.frame_id,
                    transform.child_frame_id):
                keep.append(transform)
                continue
            if transform.header.stamp.sec >= WALL_EPOCH_MIN:
                self.stats['wall_dropped'] += 1
            elif (transform.header.frame_id == 'map' and
                  transform.child_frame_id == 'base_link'):
                self.stats['planar_replaced'] += 1
        if keep:
            self.stats['forwarded'] += len(keep)
            out = TFMessage()
            out.transforms = keep
            self.tf_pub.publish(out)

    def on_external_nav_odom(self, msg):
        position = msg.pose.pose.position
        orientation = msg.pose.pose.orientation
        if not valid_external_nav_odom(
                msg.header.frame_id,
                msg.child_frame_id,
                (position.x, position.y, position.z),
                (orientation.x, orientation.y, orientation.z, orientation.w)):
            self.stats['invalid_external_nav'] += 1
            return
        height_age = time.monotonic() - self.fcu_height_time
        if not valid_planning_height(self.fcu_height, height_age):
            self.stats['height_unavailable'] += 1
            return

        planning = copy.deepcopy(msg)
        planning.header.frame_id = 'map'
        planning.child_frame_id = 'base_link'
        planning.pose.pose.position.z = self.fcu_height
        self.odom_pub.publish(planning)

        transform = TransformStamped()
        transform.header = planning.header
        transform.child_frame_id = planning.child_frame_id
        transform.transform.translation.x = position.x
        transform.transform.translation.y = position.y
        transform.transform.translation.z = planning.pose.pose.position.z
        transform.transform.rotation = orientation
        tf_msg = TFMessage()
        tf_msg.transforms = [transform]
        self.tf_pub.publish(tf_msg)
        self.stats['planning_odom'] += 1
        self.stats['planning_z_max'] = max(
            self.stats['planning_z_max'], planning.pose.pose.position.z)

    def report(self):
        self.get_logger().info(
            'forwarded=%d wall_dropped=%d planar_replaced=%d '
            'planning_odom=%d invalid_external_nav=%d height_unavailable=%d '
            'invalid_fcu_height=%d planning_z_max=%.3f' % (
                self.stats['forwarded'], self.stats['wall_dropped'],
                self.stats['planar_replaced'], self.stats['planning_odom'],
                self.stats['invalid_external_nav'],
                self.stats['height_unavailable'],
                self.stats['invalid_fcu_height'], self.stats['planning_z_max']))


def main():
    rclpy.init()
    node = PlanningFrameRelay()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
