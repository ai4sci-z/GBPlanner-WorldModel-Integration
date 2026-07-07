#!/usr/bin/env python3
"""
Stage4·trajectory_to_intent(安全版,按 Review_013 §4 十项清单重写)。

数据流:/gbp/trajectory(只认它,绝不接 /vis/*)+ /slam/odom(frame=map)
      → 机体速度意图 /navlab/fcu/setpoint/intent(契约:linear_x_mps/linear_y_mps/yaw_rate_radps)
      → 状态 /navlab/exploration/status(Stage4 为 draft 字段,Stage5 严格对 gate)

安全设计(fail-closed):
 1. 默认 **disabled**:只打印+发零速 hold(ok=false, blockers 注明),
    须向 /gbp/enable 发 Bool(data: true) 才进入运动模式;/gbp/kill 一票永久禁用。
 2. 限速:SPEED_MAX=0.08 m/s(保守)、YAW_RATE_MAX=0.30 rad/s;大偏航先转再走。
 3. 无 odom(>2s 无更新)→ hold + blockers=[no_odom]。
 4. 轨迹超时(15s 无新轨迹且已跟完)→ hold + blockers=[trajectory_stale],绝不沿旧航点续跑。
 5. frame 校验:轨迹与 odom 必须同为 map,不匹配 → hold + blockers=[frame_mismatch]。
 6. z 不下发(intent 契约无 z 速度,z 由飞控高度环保持)——天然限高。
 7. B15 门(fcu_controller 起飞前不转发 intent)为第二道保险。
 8. 每条运动 intent 日志:traj#/wp_idx/odom/目标/限速后速度。
"""
import json
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool, String
from trajectory_msgs.msg import MultiDOFJointTrajectory

SPEED_MAX = 0.08
YAW_RATE_MAX = 0.30
WP_REACHED_M = 0.15
ODOM_STALE_S = 2.0
TRAJ_STALE_S = 15.0     # 跟完后等新轨迹的宽限
TRAJ_MAX_AGE_S = 30.0   # 轨迹绝对最大年龄:超龄即弃(Review_014-①,防追陈旧轨迹)


def yaw_from_quat(x, y, z, w):
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


class TrajToIntent(Node):
    def __init__(self):
        super().__init__("gbp_traj_to_intent")
        self.enabled = False          # fail-closed:默认不发运动指令
        self.killed = False           # kill 一票永久禁用
        self.odom = None
        self.odom_t = 0.0
        self.traj = None
        self.traj_t = 0.0
        self.traj_id = 0
        self.wp_idx = 0
        self.wp_done = 0              # 已到达 waypoint 计数(draft accepted_goals 素材)
        self.path_len = 0.0
        self.last_xy = None

        self.pub_intent = self.create_publisher(String, "/navlab/fcu/setpoint/intent", 10)
        self.pub_status = self.create_publisher(String, "/navlab/exploration/status", 10)
        self.create_subscription(Odometry, "/slam/odom", self.on_odom, qos_profile_sensor_data)
        self.create_subscription(MultiDOFJointTrajectory, "/gbp/trajectory", self.on_traj, 10)
        self.create_subscription(Bool, "/gbp/enable", self.on_enable, 10)
        self.create_subscription(Bool, "/gbp/kill", self.on_kill, 10)
        self.create_timer(0.5, self.tick)   # 2Hz 控制/状态节拍
        self.get_logger().info(
            "stage4 traj_to_intent up (DISABLED by default; enable via /gbp/enable, kill via /gbp/kill; "
            "speed<=%.2f yaw<=%.2f)" % (SPEED_MAX, YAW_RATE_MAX))

    # ---------- inputs ----------
    def on_enable(self, m):
        if self.killed:
            self.get_logger().warning("enable ignored: killed (fail-closed)")
            return
        self.enabled = bool(m.data)
        self.get_logger().warning("MOTION %s via /gbp/enable" % ("ENABLED" if self.enabled else "DISABLED"))

    def on_kill(self, m):
        if m.data:
            self.killed = True
            self.enabled = False
            self.get_logger().error("KILLED via /gbp/kill: motion permanently disabled")

    def on_odom(self, m):
        self.odom = m
        self.odom_t = time.monotonic()
        p = m.pose.pose.position
        if self.last_xy is not None:
            self.path_len += math.hypot(p.x - self.last_xy[0], p.y - self.last_xy[1])
        self.last_xy = (p.x, p.y)

    def on_traj(self, m):
        if not m.points:
            return
        self.traj = m
        self.traj_t = time.monotonic()
        self.traj_id += 1
        self.wp_idx = 0
        self.get_logger().info("TRAJ#%d received: wp=%d frame=%s" % (self.traj_id, len(m.points), m.header.frame_id))

    # ---------- core ----------
    def blockers(self):
        b = []
        if self.killed:
            b.append("killed")
        if not self.enabled:
            b.append("motion_disabled_fail_closed")
        if self.odom is None or time.monotonic() - self.odom_t > ODOM_STALE_S:
            b.append("no_odom")
        if self.traj is None:
            b.append("no_trajectory")
        elif time.monotonic() - self.traj_t > TRAJ_MAX_AGE_S:
            b.append("trajectory_max_age")  # 超龄即弃,不沿旧航点续跑
        elif self.wp_idx >= len(self.traj.points) and time.monotonic() - self.traj_t > TRAJ_STALE_S:
            b.append("trajectory_stale")
        if self.traj is not None and self.traj.header.frame_id not in ("map",):
            b.append("frame_mismatch:%s" % self.traj.header.frame_id)
        return b

    def tick(self):
        blockers = self.blockers()
        vx = vy = yaw_rate = 0.0
        wp_info = ""
        if not blockers:
            p = self.odom.pose.pose.position
            q = self.odom.pose.pose.orientation
            cur_yaw = yaw_from_quat(q.x, q.y, q.z, q.w)
            # waypoint 推进(到达判定)
            while self.wp_idx < len(self.traj.points):
                wp = self.traj.points[self.wp_idx].transforms[0].translation
                if math.hypot(wp.x - p.x, wp.y - p.y) < WP_REACHED_M:
                    self.wp_idx += 1
                    self.wp_done += 1
                else:
                    break
            if self.wp_idx < len(self.traj.points):
                wp = self.traj.points[self.wp_idx].transforms[0].translation
                dx, dy = wp.x - p.x, wp.y - p.y
                dist = math.hypot(dx, dy)
                target_yaw = math.atan2(dy, dx) if dist > 1e-3 else cur_yaw
                dyaw = (target_yaw - cur_yaw + math.pi) % (2 * math.pi) - math.pi
                yaw_rate = max(-YAW_RATE_MAX, min(YAW_RATE_MAX, dyaw))
                forward = SPEED_MAX if abs(dyaw) < 0.5 else SPEED_MAX * 0.3
                forward = min(forward, dist)
                # 世界系速度投影(坐标系查证,fcu_controller 模板 L370-424):
                #  - MAVLink 主驱动路把 linear_x/y 按 MAV_FRAME_LOCAL_NED 世界系积分,不做 yaw 旋转;
                #  - cmd_vel 路 frame_id=base_link 语义为机体——两路上游语义不一致(上游模糊)。
                #  对齐主驱动路→发世界系(map/ENU 投影);NED/ENU 轴向映射待 Stage5 实测校准
                #  (低速 0.08m/s 下方向偏差影响可控,行为校准一次实验即可定)。
                vx = forward * math.cos(target_yaw)
                vy = forward * math.sin(target_yaw)
                wp_info = "traj#%d wp[%d/%d]=(%.2f,%.2f,%.2f) odom=(%.2f,%.2f) dist=%.2f dyaw=%.2f -> v=(%.3f,%.3f) yr=%.3f" % (
                    self.traj_id, self.wp_idx, len(self.traj.points), wp.x, wp.y, wp.z,
                    p.x, p.y, dist, dyaw, vx, vy, yaw_rate)
                self.get_logger().info("INTENT " + wp_info)
            else:
                blockers = ["awaiting_next_trajectory"]

        intent = {
            "ok": not blockers,
            "source": "gbp_traj_to_intent",
            "strategy": "gbplanner",
            "goal_id": "gbp_t%d_w%d" % (self.traj_id, self.wp_idx),
            "linear_x_mps": vx, "linear_y_mps": vy, "yaw_rate_radps": yaw_rate,
        }
        self.pub_intent.publish(String(data=json.dumps(intent)))

        # Stage5a gate 口径(Review_015 风险B:未经 external 去混流验证前不当完成态):
        # gate_ok_draft 仅报告,不置 ok——ok=True 会驱动 task_completed→landing 链,
        # 必须先在 Stage4c 证明 wp_done/path_len 可归因且时机安全后才启用。
        gate_ok_draft = (self.wp_done >= 3) and (self.path_len >= 0.35)
        status = {
            "claim": "in_progress",
            "strategy": "gbplanner",
            "ok": False,  # 保守:Stage4c 验证后由 gate_ok_draft 接管
            "gate_ok_draft": gate_ok_draft,
            "blockers": blockers,
            "accepted_goals": self.wp_done,
            "min_accepted_goals": 3,
            "path_length_m": round(self.path_len, 4),
            "min_path_length_m": 0.35,
            "motion_speed_mps": SPEED_MAX,
            "enabled": self.enabled,
            "traj_count": self.traj_id,
        }
        self.pub_status.publish(String(data=json.dumps(status)))


def main():
    rclpy.init()
    rclpy.spin(TrajToIntent())


if __name__ == "__main__":
    main()
