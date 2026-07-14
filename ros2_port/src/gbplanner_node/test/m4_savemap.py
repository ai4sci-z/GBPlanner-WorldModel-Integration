#!/usr/bin/env python3
"""Call /gbplanner_node/save_map (map-state probe for M4 debugging)."""
import sys

import rclpy
from rclpy.node import Node
from voxblox_msgs.srv import FilePath

out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/m4_map.voxblox'
rclpy.init()
n = Node('m4_saver')
c = n.create_client(FilePath, '/gbplanner_node/save_map')
print('svc:', c.wait_for_service(timeout_sec=10))
f = c.call_async(FilePath.Request(file_path=out))
rclpy.spin_until_future_complete(n, f, timeout_sec=30)
print('save:', f.result())
