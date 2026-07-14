#!/usr/bin/env python3
# 阶段3·dry-run:订 /gbp/trajectory + /slam/odom,只打印跟踪量,不发任何 intent。
# 输出:waypoint 数/首末 wp、当前目标 wp、distance、yaw_error、建议 vx/yaw_rate(限幅)。
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from trajectory_msgs.msg import MultiDOFJointTrajectory

SPEED_MAX = 0.10      # m/s(对齐 frontier_lite motion_speed_mps)
YAW_RATE_MAX = 0.30   # rad/s


def yaw_from_quat(x, y, z, w):
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


class DryRun(Node):
    def __init__(self):
        super().__init__("traj_dryrun")
        self.odom = None
        self.traj = None
        self.traj_stamp = 0.0
        self.create_subscription(Odometry, "/slam/odom", self.on_odom, qos_profile_sensor_data)
        self.create_subscription(MultiDOFJointTrajectory, "/gbp/trajectory", self.on_traj, 10)
        self.create_timer(1.0, self.tick)
        self.get_logger().info("dry-run up: printing only, publishing NOTHING")

    def on_odom(self, m):
        self.odom = m

    def on_traj(self, m):
        self.traj = m
        self.traj_stamp = time.monotonic()
        n = len(m.points)
        first = m.points[0].transforms[0].translation if n and m.points[0].transforms else None
        last = m.points[-1].transforms[0].translation if n and m.points[-1].transforms else None
        dur = m.points[-1].time_from_start.sec + m.points[-1].time_from_start.nanosec * 1e-9 if n else 0.0
        self.get_logger().info(
            "TRAJ frame=%s wp=%d dur=%.1fs first=(%.2f,%.2f,%.2f) last=(%.2f,%.2f,%.2f)" % (
                m.header.frame_id, n, dur,
                first.x if first else 0, first.y if first else 0, first.z if first else 0,
                last.x if last else 0, last.y if last else 0, last.z if last else 0))

    def tick(self):
        if self.odom is None or self.traj is None or not self.traj.points:
            self.get_logger().info("waiting: odom=%s traj=%s" % (self.odom is not None, self.traj is not None))
            return
        p = self.odom.pose.pose.position
        q = self.odom.pose.pose.orientation
        cur_yaw = yaw_from_quat(q.x, q.y, q.z, q.w)
        # 目标=按收到轨迹后经过时间对应的 waypoint(与 time_from_start 对齐)
        elapsed = time.monotonic() - self.traj_stamp
        target = self.traj.points[-1]
        for pt in self.traj.points:
            t = pt.time_from_start.sec + pt.time_from_start.nanosec * 1e-9
            if t >= elapsed:
                target = pt
                break
        wp = target.transforms[0].translation
        dx, dy, dz = wp.x - p.x, wp.y - p.y, wp.z - p.z
        dist = math.hypot(dx, dy)
        target_yaw = math.atan2(dy, dx) if dist > 1e-3 else cur_yaw
        dyaw = (target_yaw - cur_yaw + math.pi) % (2 * math.pi) - math.pi
        yaw_rate = max(-YAW_RATE_MAX, min(YAW_RATE_MAX, dyaw))
        vx = min(SPEED_MAX if abs(dyaw) < 0.5 else SPEED_MAX * 0.3, dist)
        self.get_logger().info(
            "DRY wp=(%.2f,%.2f,%.2f) cur=(%.2f,%.2f,%.2f) dist=%.2f dz=%.2f yaw_err=%.2f -> vx=%.3f yaw_rate=%.3f (NOT published)" % (
                wp.x, wp.y, wp.z, p.x, p.y, p.z, dist, dz, dyaw, vx, yaw_rate))


def main():
    rclpy.init()
    rclpy.spin(DryRun())


if __name__ == "__main__":
    main()
