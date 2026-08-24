#!/usr/bin/env python3
"""Own the M5 planning frame and relay all unrelated healthy transforms.

A node in the world-model stack (pose_mirror suspect, frames base_scan +
imu_link) publishes single wall-clock-stamped TFs into an otherwise sim-time
tree. tf2's cache prunes by 'latest - cache_time', so ONE 1.78e9 sample makes
every later sim-time sample (~60s) 'too old' and the segment freezes -- our
esdf_server then never resolves TF at cloud timestamps (measured via
tf_dump.py, 2026-07-13). Filter them out instead of patching upstream here.

Cartographer is intentionally 2D, so its map -> base_link has z=0. WorldModel's
/external_nav/odom already combines that planar pose with the sensor-derived
/height/estimate. This relay makes that fused state the single owner of the M5
planning transform and publishes the same state as /gbp/planning_odom. The
planner and point-cloud TF therefore share one 3D pose; no controller clamp is
used to hide a zero-height planning state.
"""
import copy

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from tf2_msgs.msg import TFMessage

from planning_frame import WALL_EPOCH_MIN, should_forward_tf, valid_external_nav_odom


class PlanningFrameRelay(Node):
    def __init__(self):
        super().__init__('tf_clean_relay')
        self.tf_pub = self.create_publisher(TFMessage, '/tf_clean', 100)
        self.odom_pub = self.create_publisher(Odometry, '/gbp/planning_odom', 10)
        self.create_subscription(TFMessage, '/tf', self.on_tf, 100)
        self.create_subscription(
            Odometry, '/external_nav/odom', self.on_external_nav_odom, 10)
        self.create_timer(10.0, self.report)
        self.stats = {'forwarded': 0, 'wall_dropped': 0,
                      'planar_replaced': 0, 'planning_odom': 0,
                      'invalid_external_nav': 0}
        self.get_logger().info(
            'planning frame relay: /external_nav/odom -> '
            '/gbp/planning_odom + map->base_link on /tf_clean')

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

        planning = copy.deepcopy(msg)
        planning.header.frame_id = 'map'
        planning.child_frame_id = 'base_link'
        self.odom_pub.publish(planning)

        transform = TransformStamped()
        transform.header = planning.header
        transform.child_frame_id = planning.child_frame_id
        transform.transform.translation.x = position.x
        transform.transform.translation.y = position.y
        transform.transform.translation.z = position.z
        transform.transform.rotation = orientation
        tf_msg = TFMessage()
        tf_msg.transforms = [transform]
        self.tf_pub.publish(tf_msg)
        self.stats['planning_odom'] += 1

    def report(self):
        self.get_logger().info(
            'forwarded=%d wall_dropped=%d planar_replaced=%d '
            'planning_odom=%d invalid_external_nav=%d' % (
                self.stats['forwarded'], self.stats['wall_dropped'],
                self.stats['planar_replaced'], self.stats['planning_odom'],
                self.stats['invalid_external_nav']))


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
