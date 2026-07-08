#!/usr/bin/env python3
"""ROS2 (jazzy) side: feed the SAME deterministic frames to the ported voxblox
tsdf_server, then call save_map. Run inside the voxblox_ros2_deps container."""
import sys
import time

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped
from sensor_msgs.msg import PointCloud2, PointField
from tf2_ros import TransformBroadcaster
from voxblox_msgs.srv import FilePath

import frames_common as fc

SENSOR_FRAME = 'cmp_sensor'
WORLD_FRAME = 'world'


def make_cloud(k, stamp):
    data, n = fc.cloud_payload(k)
    msg = PointCloud2()
    msg.header.stamp = stamp
    msg.header.frame_id = SENSOR_FRAME
    msg.height = 1
    msg.width = n
    msg.fields = [
        PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
    ]
    msg.is_bigendian = False
    msg.point_step = 12
    msg.row_step = 12 * n
    msg.data = data
    msg.is_dense = True
    return msg


def tf_msg(k, stamp):
    tx, ty, tz = fc.sensor_pose(k)
    t = TransformStamped()
    t.header.stamp = stamp
    t.header.frame_id = WORLD_FRAME
    t.child_frame_id = SENSOR_FRAME
    t.transform.translation.x = tx
    t.transform.translation.y = ty
    t.transform.translation.z = tz
    t.transform.rotation.w = 1.0
    return t


def stamp_plus(node, sec):
    return (node.get_clock().now() + Duration(seconds=sec)).to_msg()


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/port_tsdf.voxblox'
    rclpy.init()
    node = Node('cmp_feeder')
    br = TransformBroadcaster(node)
    # ROS2 port subscribes the PRIVATE name <node>/pointcloud
    # (generate_private_name in tsdf_server.cc), unlike ROS1's public /pointcloud.
    pub = node.create_publisher(PointCloud2, '/voxblox_node/pointcloud', 2)
    time.sleep(2.0)

    for k in range(fc.N_FRAMES):
        cloud_stamp = stamp_plus(node, 0.15)
        for _ in range(6):
            br.sendTransform(tf_msg(k, stamp_plus(node, 0.3)))
            br.sendTransform(tf_msg(k, stamp_plus(node, 0.0)))
            time.sleep(0.05)
        pub.publish(make_cloud(k, cloud_stamp))
        node.get_logger().info('frame %d published' % k)
        time.sleep(0.9)

    time.sleep(3.0)
    cli = node.create_client(FilePath, '/voxblox_node/save_map')
    if not cli.wait_for_service(timeout_sec=20.0):
        raise RuntimeError('save_map service not available')
    fut = cli.call_async(FilePath.Request(file_path=out_path))
    rclpy.spin_until_future_complete(node, fut, timeout_sec=30.0)
    node.get_logger().info('save_map -> %s (%s)' % (out_path, fut.result()))


if __name__ == '__main__':
    main()
