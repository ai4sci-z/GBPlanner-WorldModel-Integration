#!/usr/bin/env python3
# 诊断用:在指定环境发布 5 条 MultiDOFJointTrajectory 到 /gbp/trajectory(1Hz),
# 用于分辨"thin_ros2 发布的消息为何订阅端收不到"。
import rclpy
from trajectory_msgs.msg import MultiDOFJointTrajectory, MultiDOFJointTrajectoryPoint
from geometry_msgs.msg import Transform

rclpy.init()
node = rclpy.create_node("pub_test_traj")
pub = node.create_publisher(MultiDOFJointTrajectory, "/gbp/trajectory", 10)

count = {"n": 0}

def tick():
    m = MultiDOFJointTrajectory()
    m.header.stamp = node.get_clock().now().to_msg()
    m.header.frame_id = "map"
    pt = MultiDOFJointTrajectoryPoint()
    tr = Transform()
    tr.translation.x = 1.0 + count["n"]
    tr.rotation.w = 1.0
    pt.transforms.append(tr)
    m.points.append(pt)
    pub.publish(m)
    count["n"] += 1
    if count["n"] % 10 == 0 or count["n"] <= 3:
        print("published", count["n"], flush=True)
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    if count["n"] >= limit:
        raise SystemExit

node.create_timer(1.0, tick)
try:
    rclpy.spin(node)
except SystemExit:
    pass
