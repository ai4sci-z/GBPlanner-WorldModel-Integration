#!/usr/bin/env python3
"""ROS1 (noetic) side: feed the deterministic frames to voxblox tsdf_server,
then call save_map. Run inside the gbplanner-ref container."""
import sys
import time

import rospy
import tf2_ros
from geometry_msgs.msg import TransformStamped
from sensor_msgs.msg import PointCloud2, PointField
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


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/oracle_tsdf.voxblox'
    rospy.init_node('cmp_feeder')
    br = tf2_ros.TransformBroadcaster()
    pub = rospy.Publisher('/pointcloud', PointCloud2, queue_size=2)
    time.sleep(2.0)  # let subscriber match

    for k in range(fc.N_FRAMES):
        # broadcast TF around the cloud stamp so the lookup always succeeds
        stamp = rospy.Time.now() + rospy.Duration(0.15)
        for _ in range(6):
            now = rospy.Time.now()
            br.sendTransform(tf_msg(k, now + rospy.Duration(0.3)))
            br.sendTransform(tf_msg(k, now))
            time.sleep(0.05)
        pub.publish(make_cloud(k, stamp))
        rospy.loginfo('frame %d published', k)
        time.sleep(0.9)  # give the integrator time before moving the sensor

    time.sleep(3.0)
    rospy.wait_for_service('/voxblox/save_map', timeout=20)
    save = rospy.ServiceProxy('/voxblox/save_map', FilePath)
    resp = save(out_path)
    rospy.loginfo('save_map -> %s (%s)', out_path, resp)


if __name__ == '__main__':
    main()
