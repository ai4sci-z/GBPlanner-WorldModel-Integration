#!/usr/bin/env python3
# 自写薄桥·ROS2 端(rclpy,跑在 jazzy 容器)。
# TCP client 连 localhost:7601(自动重连;帧=4字节大端长度+JSON):
#   出:订 /slam/odom -> {"type":"odom"}(限频 10Hz;frame 在此映射 map->world)
#       订 /scan(LaserScan)-> 极坐标转 xyz -> {"type":"cloud"}(限频 5Hz;2D 冒烟)
#   入:{"type":"traj"} -> 发布 /gbp/trajectory(trajectory_msgs/MultiDOFJointTrajectory)
import json
import socket
import struct
import threading
import time
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from trajectory_msgs.msg import MultiDOFJointTrajectory, MultiDOFJointTrajectoryPoint
from geometry_msgs.msg import Transform
from builtin_interfaces.msg import Duration


class ThinBridge(Node):
    def __init__(self):
        super().__init__("thinbridge_ros2")
        self.sock = None
        self.sock_lock = threading.Lock()
        self.stats = {"odom_out": 0, "cloud_out": 0, "traj_in": 0}
        self.last_odom = 0.0
        self.last_cloud = 0.0
        self.pub_traj = self.create_publisher(MultiDOFJointTrajectory, "/gbp/trajectory", 10)
        self.create_subscription(Odometry, "/slam/odom", self.on_odom, qos_profile_sensor_data)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        threading.Thread(target=self.conn_loop, daemon=True).start()
        self.create_timer(10.0, lambda: self.get_logger().info("stats: %s" % self.stats))
        # 3s ping 心跳:保活 + 快速暴露断链方向(哪端 send/recv 先报错)
        self.create_timer(3.0, lambda: self.send({"type": "ping", "t": time.time()}))
        self.get_logger().info("thinbridge_ros2 up: (/slam/odom,/scan)->tcp | tcp->/gbp/trajectory")

    # ---------- TCP ----------
    def conn_loop(self):
        buf = b""
        while True:
            if self.sock is None:
                try:
                    s = socket.create_connection(("127.0.0.1", 7601), timeout=5)
                    s.settimeout(1.0)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    with self.sock_lock:
                        self.sock = s
                    buf = b""
                    self.get_logger().info("connected to ros1 side :7601")
                except Exception as exc:
                    self.get_logger().warning("connect to :7601 failed (%r), retry in 2s" % exc)
                    time.sleep(2)
                    continue
            try:
                chunk = self.sock.recv(1 << 16)
                if not chunk:
                    raise ConnectionError("closed")
                buf += chunk
                while len(buf) >= 4:
                    n = struct.unpack(">I", buf[:4])[0]
                    if len(buf) < 4 + n:
                        break
                    payload, buf = buf[4:4 + n], buf[4 + n:]
                    # 单条坏消息只记日志,绝不断链
                    try:
                        self.on_frame(json.loads(payload))
                    except Exception as exc:
                        self.get_logger().error("on_frame failed: %r" % exc)
            except socket.timeout:
                continue
            except Exception as exc:
                self.get_logger().error("tcp link lost: %r (reconnecting)" % exc)
                with self.sock_lock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None

    def send(self, obj):
        data = json.dumps(obj).encode()
        frame = struct.pack(">I", len(data)) + data
        with self.sock_lock:
            if self.sock is None:
                return
            try:
                self.sock.sendall(frame)
            except Exception as exc:
                self.get_logger().error("send failed (%r), closing link" % exc)
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None

    # ---------- ROS2 -> TCP ----------
    def on_odom(self, m):
        now = time.monotonic()
        if now - self.last_odom < 0.1:  # 10Hz cap
            return
        self.last_odom = now
        p = m.pose.pose.position
        q = m.pose.pose.orientation
        v = m.twist.twist.linear
        self.send({
            "type": "odom",
            # frame 映射在桥层做:world-model 的 map -> gbplanner 的 world
            "frame": "world", "child": "rmf_obelix/base_link",
            "p": [p.x, p.y, p.z], "q": [q.x, q.y, q.z, q.w], "v": [v.x, v.y, v.z],
        })
        self.stats["odom_out"] += 1

    def on_scan(self, m):
        now = time.monotonic()
        if now - self.last_cloud < 0.2:  # 5Hz cap
            return
        self.last_cloud = now
        pts = []
        a = m.angle_min
        for r in m.ranges:
            if m.range_min < r < m.range_max and math.isfinite(r):
                pts.append([r * math.cos(a), r * math.sin(a), 0.0])
            a += m.angle_increment
        self.send({"type": "cloud", "frame": "rmf_obelix/rmf_obelix/velodyne", "points": pts})
        self.stats["cloud_out"] += 1

    # ---------- TCP -> ROS2 ----------
    # 注意:不能叫 handle——会覆盖 rclpy Node 内部的 handle 属性导致 __init__ 崩溃
    def on_frame(self, obj):
        if obj.get("type") != "traj":
            return
        msg = MultiDOFJointTrajectory()
        msg.header.stamp = self.get_clock().now().to_msg()
        # frame 映射:gbplanner 的 world -> world-model 的 map
        msg.header.frame_id = "map"
        for wp in obj.get("points", []):
            pt = MultiDOFJointTrajectoryPoint()
            tr = Transform()
            tr.translation.x = float(wp.get("x", 0.0))
            tr.translation.y = float(wp.get("y", 0.0))
            tr.translation.z = float(wp.get("z", 0.0))
            tr.rotation.x = float(wp.get("qx", 0.0))
            tr.rotation.y = float(wp.get("qy", 0.0))
            tr.rotation.z = float(wp.get("qz", 0.0))
            tr.rotation.w = float(wp.get("qw", 1.0))
            pt.transforms.append(tr)
            t = float(wp.get("t", 0.0))
            pt.time_from_start = Duration(sec=int(t), nanosec=int((t - int(t)) * 1e9))
            msg.points.append(pt)
        self.pub_traj.publish(msg)
        self.stats["traj_in"] += 1
        self.get_logger().info("traj -> /gbp/trajectory (%d wp)" % len(msg.points))


def main():
    rclpy.init()
    node = ThinBridge()
    rclpy.spin(node)


if __name__ == "__main__":
    main()
