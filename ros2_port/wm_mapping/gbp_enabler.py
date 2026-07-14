#!/usr/bin/env python3
"""M5: publish /gbp/enable=true once the FCU controller reports ready.
The adapter's own five-condition latch stays the real safety gate; this
merely arms it after takeoff (mirrors the stage-4c/5a enable timing)."""
import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

rclpy.init()
node = Node('gbp_enabler')
pub = node.create_publisher(Bool, '/gbp/enable', 10)
state = {'ready': False}


def on_status(msg):
    try:
        d = json.loads(msg.data)
    except ValueError:
        return
    # same readiness test as the adapter's on_ctrl_status (ok OR ready)
    if d.get('ok') or d.get('ready'):
        state['ready'] = True


node.create_subscription(String, '/navlab/fcu/controller/status', on_status, 10)


def tick():
    m = Bool()
    m.data = bool(state['ready'])
    pub.publish(m)


node.create_timer(0.5, tick)
rclpy.spin(node)
