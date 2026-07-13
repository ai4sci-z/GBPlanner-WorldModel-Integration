#!/usr/bin/env python3
"""M2 slice5 wm-mapping driver (runs inside voxblox_ros2_port container).

Self-waiting: subscribes /cloud_in via rclpy (jazzy `ros2 topic echo` cannot
see rclpy publishers -- PORTABLE rule), prints the measured frame_id, verifies
TF map->cloud_frame on sim time, then hands control back to mapper.sh which
launches esdf_server + rviz2 and later calls save_map.
"""
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2


def main():
    wait_sec = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    rclpy.init()
    node = Node('slice5_probe', parameter_overrides=[
        rclpy.parameter.Parameter('use_sim_time', value=True)])
    got = {}

    def on_cloud(msg):
        got['frame'] = msg.header.frame_id
        got['width'] = msg.width

    node.create_subscription(PointCloud2, '/cloud_in', on_cloud,
                             qos_profile_sensor_data)
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline and 'frame' not in got:
        rclpy.spin_once(node, timeout_sec=0.5)
    if 'frame' not in got:
        print('CLOUD_TIMEOUT')
        sys.exit(1)
    print('CLOUD_FRAME=%s WIDTH=%d' % (got['frame'], got['width']))

    # TF check: map -> cloud frame (buffer fed by sim-time /tf)
    from tf2_ros import Buffer, TransformListener
    buf = Buffer()
    TransformListener(buf, node)
    tf_deadline = time.monotonic() + 30.0
    while time.monotonic() < tf_deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
        if buf.can_transform('map', got['frame'], rclpy.time.Time()):
            t = buf.lookup_transform('map', got['frame'], rclpy.time.Time())
            tr = t.transform.translation
            print('TF_OK map->%s at (%.2f, %.2f, %.2f)'
                  % (got['frame'], tr.x, tr.y, tr.z))
            return
    print('TF_MISSING map->%s' % got['frame'])
    sys.exit(2)


if __name__ == '__main__':
    main()
