#!/usr/bin/env python3
# 自写薄桥·ROS1 端(rospy,跑在 gbplanner 容器内)。
# TCP server :7601(帧=4字节大端长度+JSON):
#   出:订 /rmf_obelix/command/trajectory -> {"type":"traj",...} 推给所有客户端
#   入:{"type":"odom"} -> 发布 /wm/odom(nav_msgs/Odometry)
#       {"type":"cloud"} -> 发布 /wm/points(sensor_msgs/PointCloud2, xyz32)
# 设计依据(实测契约):trajectory 事件式、waypoint 只有位姿;gbplanner 期望
# odometry frame=world/child=rmf_obelix/base_link(阶段4 再 remap 接入)。
import json
import socket
import struct
import threading

import rospy
import sensor_msgs.point_cloud2 as pc2
import tf2_ros
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import PointCloud2
from std_msgs.msg import Header
from trajectory_msgs.msg import MultiDOFJointTrajectory

clients = []
lock = threading.Lock()
stats = {"traj_out": 0, "odom_in": 0, "cloud_in": 0}
tf_broadcaster = None  # set in main(); odom -> world->base_link TF(GBPlanner 需要 TF tree)


def send_all(obj):
    data = json.dumps(obj).encode()
    frame = struct.pack(">I", len(data)) + data
    with lock:
        dead = []
        for c in clients:
            try:
                c.sendall(frame)
            except Exception as exc:
                rospy.logerr("thinbridge: sendall failed (%r), dropping client", exc)
                dead.append(c)
        for d in dead:
            clients.remove(d)
            try:
                d.close()
            except Exception:
                pass


def on_traj(msg):
    pts = []
    for p in msg.points:
        if not p.transforms:
            continue
        t = p.transforms[0]
        pts.append({
            "x": t.translation.x, "y": t.translation.y, "z": t.translation.z,
            "qx": t.rotation.x, "qy": t.rotation.y, "qz": t.rotation.z, "qw": t.rotation.w,
            "t": p.time_from_start.to_sec(),
        })
    send_all({"type": "traj", "frame": msg.header.frame_id, "points": pts})
    stats["traj_out"] += 1
    rospy.loginfo("thinbridge: traj -> tcp (%d wp, total %d)", len(pts), stats["traj_out"])


def reader(conn, pub_odom, pub_cloud):
    buf = b""
    while not rospy.is_shutdown():
        try:
            chunk = conn.recv(1 << 16)
        except Exception as exc:
            rospy.logerr("thinbridge: reader recv failed (%r)", exc)
            break
        if not chunk:
            rospy.logwarn("thinbridge: client sent FIN (clean close)")
            break
        buf += chunk
        while len(buf) >= 4:
            n = struct.unpack(">I", buf[:4])[0]
            if len(buf) < 4 + n:
                break
            payload, buf = buf[4:4 + n], buf[4 + n:]
            try:
                obj = json.loads(payload)
            except Exception:
                continue
            kind = obj.get("type")
            if kind == "ping":
                # 心跳:原样回 pong(不占用发布通道)
                try:
                    pong = json.dumps({"type": "pong", "t": obj.get("t")}).encode()
                    conn.sendall(struct.pack(">I", len(pong)) + pong)
                except Exception as exc:
                    rospy.logerr("thinbridge: pong send failed (%r)", exc)
                    break
            elif kind == "odom":
                m = Odometry()
                m.header.stamp = rospy.Time.now()
                m.header.frame_id = obj.get("frame", "world")
                m.child_frame_id = obj.get("child", "rmf_obelix/base_link")
                p = obj.get("p", [0, 0, 0])
                q = obj.get("q", [0, 0, 0, 1])
                m.pose.pose.position.x, m.pose.pose.position.y, m.pose.pose.position.z = p
                (m.pose.pose.orientation.x, m.pose.pose.orientation.y,
                 m.pose.pose.orientation.z, m.pose.pose.orientation.w) = q
                v = obj.get("v", [0, 0, 0])
                m.twist.twist.linear.x, m.twist.twist.linear.y, m.twist.twist.linear.z = v
                pub_odom.publish(m)
                # 同步广播 world->base_link 动态 TF(阶段2.6:GBPlanner/voxblox 需要
                # TF tree;原仿真由 RotorS 发,消费 /wm/* 时由桥补,时间戳同 odom)
                if tf_broadcaster is not None:
                    t = TransformStamped()
                    t.header.stamp = m.header.stamp
                    t.header.frame_id = m.header.frame_id
                    t.child_frame_id = m.child_frame_id
                    t.transform.translation.x, t.transform.translation.y, t.transform.translation.z = p
                    (t.transform.rotation.x, t.transform.rotation.y,
                     t.transform.rotation.z, t.transform.rotation.w) = q
                    tf_broadcaster.sendTransform(t)
                stats["odom_in"] += 1
            elif kind == "cloud":
                header = Header()
                header.stamp = rospy.Time.now()
                header.frame_id = obj.get("frame", "rmf_obelix/rmf_obelix/velodyne")
                cloud = pc2.create_cloud_xyz32(header, obj.get("points", []))
                pub_cloud.publish(cloud)
                stats["cloud_in"] += 1
    with lock:
        if conn in clients:
            clients.remove(conn)


def main():
    global tf_broadcaster
    rospy.init_node("thinbridge_ros1")
    tf_broadcaster = tf2_ros.TransformBroadcaster()
    pub_odom = rospy.Publisher("/wm/odom", Odometry, queue_size=10)
    pub_cloud = rospy.Publisher("/wm/points", PointCloud2, queue_size=5)
    rospy.Subscriber("/rmf_obelix/command/trajectory", MultiDOFJointTrajectory, on_traj)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 7601))
    srv.listen(5)

    def acceptor():
        # 注:环境里 socket 默认超时可能被三方库设置,accept 会周期性抛 timeout;
        # 曾因 break 导致 acceptor 线程死亡 -> 客户端断线后永远无法重连(2k 实测锁定)。
        while not rospy.is_shutdown():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except Exception as exc:
                rospy.logerr("thinbridge: accept failed (%r), keep accepting", exc)
                continue
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            rospy.loginfo("thinbridge: client connected %s", addr)
            with lock:
                clients.append(conn)
            threading.Thread(target=reader, args=(conn, pub_odom, pub_cloud), daemon=True).start()

    threading.Thread(target=acceptor, daemon=True).start()

    def heartbeat(_):
        rospy.loginfo("thinbridge stats: %s clients=%d", stats, len(clients))

    rospy.Timer(rospy.Duration(10), heartbeat)
    rospy.loginfo("thinbridge_ros1 up: tcp :7601 | traj->tcp | tcp->(/wm/odom,/wm/points)")
    rospy.spin()


if __name__ == "__main__":
    main()
