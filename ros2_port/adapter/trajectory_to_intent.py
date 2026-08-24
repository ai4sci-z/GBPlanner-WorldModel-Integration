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
 6. z 闭环(M5):intent 增加可选字段 "z_m" = 当前目标航点期望绝对高度(米,向上为正,
    local 系)。运动 intent 带当前目标 wp 的 z;hold intent 在 last_z_m 已知时也带
    (防悬停高度跳回默认起飞高)。从未有合法 z 时不带该字段——控制器侧回退
    -takeoff_alt_m,行为与旧契约完全一致(向后兼容)。控制器侧对 z_m 做
    sanity(0.05<z<100)+ clamp(0.3,3.0),仍有硬限高。
    背景:m5_20260728T181620 实测,GBPlanner 3D 路径在规划高度过碰撞检查,
    但 z 被钉在 0.5m 贴地执行 → 蹭墙。
 7. B15 门(fcu_controller 起飞前不转发 intent)为第二道保险。
 8. 每条运动 intent 日志:traj#/wp_idx/odom/目标/限速后速度。
"""
import json
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool, String
from trajectory_msgs.msg import MultiDOFJointTrajectory

from intent_policy import (
    ACTIVE_TRAJECTORY_MAX_AGE_S,
    effective_fcu_yaw_age,
    map_velocity_to_body_frd,
    quaternion_yaw,
    valid_fcu_yaw,
    valid_odom_frames,
)

SPEED_MAX = 0.08
YAW_RATE_MAX = 0.30
WP_REACHED_M = 0.15
ODOM_STALE_S = 2.0
TRAJ_STALE_S = 15.0     # 跟完后等新轨迹的宽限
TRAJ_MAX_AGE_S = ACTIVE_TRAJECTORY_MAX_AGE_S

# Current fcu_controller intent is body FRD and is rotated to LOCAL_NED with
# FCU yaw downstream. Convert map velocity directly through the odometry
# map->base_link orientation. Two M5 bags proved that the numeric map/NED
# position relation contains an axis-swap reflection (det=-1), so a det=+1
# online rotation estimate is structurally invalid and must not drive motion.
SLAM_FROZEN_S = 4.0       # 运动指令活跃但 odom 位置基本不动 → slam_frozen blocker
FROZEN_EPS_M = 0.02       # "基本不动"阈值(SLAM 抖动 ±1cm,5a-2 实测)

def intent_z(wp_z, last_z):
    """M5 z闭环:选择 intent 可选字段 "z_m" 的值(纯函数,便于无 ROS 测试)。

    wp_z:  当前目标航点的 z(运动时),hold/无目标时传 None。
    last_z: 最近一次下发过的合法 z_m(self.last_z_m),从未有则 None。
    返回 float(应带 "z_m")或 None(不带字段,控制器回退 -takeoff_alt_m)。

    合法性与控制器侧 sanity 同口径:可转 float 且 0.05 < z < 100
    (NaN 任何比较为 False,天然被排除,无需 math.isnan)。
    wp_z 非法时回退 last_z(不让坏值把悬停高度打回默认)。
    """
    for cand in (wp_z, last_z):
        if cand is None:
            continue
        try:
            z = float(cand)
        except (TypeError, ValueError):
            continue
        if 0.05 < z < 100.0:
            return z
    return None


class TrajToIntent(Node):
    def __init__(self):
        super().__init__("gbp_traj_to_intent")
        self.enabled = False          # fail-closed:默认不发运动指令
        self.killed = False           # kill 一票永久禁用
        self.odom = None
        self.odom_t = 0.0
        self.map_yaw = None
        self.traj = None
        self.traj_t = 0.0
        self.traj_id = 0
        self.wp_idx = 0
        self.wp_done = 0              # 只计"运动到达"的 waypoint(诚实 accepted_goals)
        self.wp_prereached = 0        # 轨迹到手时已在起点阈值内的 wp(不计入 accepted_goals)
        self.path_len = 0.0
        self.last_xy = None
        self.last_z_m = None          # M5 z闭环:最近一次下发过的合法 z_m(hold 时保持)
        # Stage5a 严格 gate 所需的外部事实
        self.controller_ready = False   # /navlab/fcu/controller/status ok(bootstrap 含 takeoff)
        self.mixed_flow = False         # intent 总线上出现过非本适配器来源 → 永久闩锁
        self.ok_latched = False         # 五条件一旦达成即闩锁(尾段 stale blocker 不回撤已达成事实)
        self.fcu_yaw = None             # FCU body yaw in LOCAL_NED
        self.fcu_yaw_t = 0.0            # local-position-pose receive time
        self.fcu_yaw_reported_age_s = None  # true ATTITUDE age from external-nav status
        self.fcu_yaw_status_t = 0.0
        self.odom_hist = []             # [(t,x,y)] 1.5s 滑窗(slam_frozen 判定)
        self.last_move_cmd_t = 0.0      # 最近一次非零运动指令时刻
        self.frozen_since = None        # odom 位置基本不动的起始时刻

        self.pub_intent = self.create_publisher(String, "/navlab/fcu/setpoint/intent", 10)
        self.pub_status = self.create_publisher(String, "/navlab/exploration/status", 10)
        self.create_subscription(Odometry, "/slam/odom", self.on_odom, qos_profile_sensor_data)
        self.create_subscription(MultiDOFJointTrajectory, "/gbp/trajectory", self.on_traj, 10)
        self.create_subscription(Bool, "/gbp/enable", self.on_enable, 10)
        self.create_subscription(Bool, "/gbp/kill", self.on_kill, 10)
        self.create_subscription(String, "/navlab/fcu/controller/status", self.on_ctrl_status, 10)
        self.create_subscription(String, "/mavlink_external_nav/status", self.on_external_nav_status, 10)
        self.create_subscription(String, "/navlab/fcu/setpoint/intent", self.on_intent_bus, 50)
        self.create_subscription(PoseStamped, "/navlab/fcu/local_position_pose", self.on_lpp, qos_profile_sensor_data)
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
        orientation = m.pose.pose.orientation
        self.map_yaw = quaternion_yaw(
            orientation.x, orientation.y, orientation.z, orientation.w)
        p = m.pose.pose.position
        if self.last_xy is not None:
            self.path_len += math.hypot(p.x - self.last_xy[0], p.y - self.last_xy[1])
        self.last_xy = (p.x, p.y)
        now = time.monotonic()
        self.odom_hist.append((now, p.x, p.y))
        while self.odom_hist and now - self.odom_hist[0][0] > 1.5:
            self.odom_hist.pop(0)

    def on_traj(self, m):
        if not m.points:
            return
        self.traj = m
        self.traj_t = time.monotonic()
        self.traj_id += 1
        self.wp_idx = 0
        pre = 0
        # 诚实计数:轨迹到手时就已在阈值内的 wp 直接跳过,不算"到达"
        if self.odom is not None:
            p = self.odom.pose.pose.position
            while self.wp_idx < len(m.points):
                wp = m.points[self.wp_idx].transforms[0].translation
                if math.hypot(wp.x - p.x, wp.y - p.y) < WP_REACHED_M:
                    self.wp_idx += 1
                    pre += 1
                else:
                    break
        self.wp_prereached += pre
        self.get_logger().info("TRAJ#%d received: wp=%d frame=%s prereached=%d(不计accepted)" % (
            self.traj_id, len(m.points), m.header.frame_id, pre))

    def on_ctrl_status(self, m):
        try:
            d = json.loads(m.data)
        except Exception:
            return
        if d.get("ok") or d.get("ready"):
            self.controller_ready = True

    def on_external_nav_status(self, m):
        try:
            age_ms = float(json.loads(m.data).get("fcu_attitude_age_ms"))
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            return
        self.fcu_yaw_reported_age_s = age_ms / 1000.0
        self.fcu_yaw_status_t = time.monotonic()

    def on_intent_bus(self, m):
        try:
            d = json.loads(m.data)
        except Exception:
            return
        src = d.get("source", "")
        if src and src != "gbp_traj_to_intent" and not self.mixed_flow:
            self.mixed_flow = True
            self.get_logger().error("MIXED FLOW detected on intent bus: source=%s -> gate 永久闩死" % src)

    # ---------- core ----------
    def blockers(self):
        b = []
        if self.killed:
            b.append("killed")
        if not self.enabled:
            b.append("motion_disabled_fail_closed")
        if self.odom is None or time.monotonic() - self.odom_t > ODOM_STALE_S:
            b.append("no_odom")
        elif not valid_odom_frames(
                self.odom.header.frame_id, self.odom.child_frame_id):
            b.append("odom_frame_mismatch:%s->%s" % (
                self.odom.header.frame_id, self.odom.child_frame_id))
        elif self.map_yaw is None:
            b.append("invalid_map_orientation")
        if self.traj is None:
            b.append("no_trajectory")
        elif time.monotonic() - self.traj_t > TRAJ_MAX_AGE_S:
            b.append("trajectory_max_age")  # 超龄即弃,不沿旧航点续跑
        elif self.wp_idx >= len(self.traj.points) and time.monotonic() - self.traj_t > TRAJ_STALE_S:
            b.append("trajectory_stale")
        if self.traj is not None and self.traj.header.frame_id not in ("map",):
            b.append("frame_mismatch:%s" % self.traj.header.frame_id)
        if not valid_fcu_yaw(self.fcu_yaw, self.fcu_yaw_age_s()):
            b.append("no_fresh_fcu_yaw")
        return b

    def fcu_yaw_age_s(self):
        now = time.monotonic()
        return effective_fcu_yaw_age(
            now - self.fcu_yaw_t,
            self.fcu_yaw_reported_age_s,
            now - self.fcu_yaw_status_t,
        )

    def on_lpp(self, m):
        orientation = m.pose.orientation
        yaw = quaternion_yaw(
            orientation.x, orientation.y, orientation.z, orientation.w)
        if yaw is not None:
            self.fcu_yaw = yaw
            self.fcu_yaw_t = time.monotonic()

    def slam_frozen(self):
        # 运动指令活跃但 odom 位置基本不动(SLAM 失锁/顶墙卡死的典型形态)
        if time.monotonic() - self.last_move_cmd_t > 2.0 or len(self.odom_hist) < 2:
            self.frozen_since = None
            return False
        (t0, x0, y0), (t1, x1, y1) = self.odom_hist[0], self.odom_hist[-1]
        if t1 - t0 >= 1.0 and math.hypot(x1 - x0, y1 - y0) < FROZEN_EPS_M:
            if self.frozen_since is None:
                self.frozen_since = time.monotonic()
            return time.monotonic() - self.frozen_since > SLAM_FROZEN_S - 1.0
        self.frozen_since = None
        return False

    def tick(self):
        blockers = self.blockers()
        if self.slam_frozen():
            blockers = blockers + ["slam_frozen"]
        vx = vy = yaw_rate = 0.0
        wp_z = None                     # M5 z闭环:当前目标航点 z(仅运动分支置值)
        if not blockers:
            p = self.odom.pose.pose.position
            # waypoint 推进(到达判定;只计运动到达,预到达在 on_traj 已剔除)
            while self.wp_idx < len(self.traj.points):
                wp = self.traj.points[self.wp_idx].transforms[0].translation
                if math.hypot(wp.x - p.x, wp.y - p.y) < WP_REACHED_M:
                    self.wp_idx += 1
                    self.wp_done += 1
                    self.get_logger().warning("WP REACHED by motion: wp_done=%d" % self.wp_done)
                else:
                    break
            if self.wp_idx < len(self.traj.points):
                wp = self.traj.points[self.wp_idx].transforms[0].translation
                wp_z = wp.z             # M5 z闭环:规划高度随 intent 下发(碰撞检查过的高度)
                dx, dy = wp.x - p.x, wp.y - p.y
                dist = math.hypot(dx, dy)
                # 外环 PD(5c run3 验尸:P-only 在 2Hz 指令+1~2s 执行滞后下极限环 ±0.3m,
                # 0.15m 捕获圈差 4cm 套不住)→ 期望速度 = kp·误差 − kd·观测速度(阻尼),
                # 再叠加"胡萝卜不过 wp"限幅(近距比例减速)。
                vox = voy = 0.0
                if len(self.odom_hist) >= 2:
                    (t0h, x0h, y0h), (t1h, x1h, y1h) = self.odom_hist[0], self.odom_hist[-1]
                    if t1h - t0h >= 0.4:
                        vox, voy = (x1h - x0h) / (t1h - t0h), (y1h - y0h) / (t1h - t0h)
                # v6 = kp0.35/kd0.5(v2run1 wp捕获0→9 的唯一直证参数组;kp0.45 经 v2 批跑证伪)
                ex = 0.35 * dx - 0.5 * vox
                ey = 0.35 * dy - 0.5 * voy
                mag = math.hypot(ex, ey)
                forward = min(SPEED_MAX, 0.3 * dist, mag)
                # map PD direction -> body forward/right (FRD). The controller
                # owns the subsequent body->NED conversion using fresh FCU yaw.
                scale = forward / max(mag, 1e-6)
                vx_map, vy_map = ex * scale, ey * scale
                body_velocity = map_velocity_to_body_frd(
                    vx_map, vy_map, self.map_yaw)
                if body_velocity is None:
                    blockers = ["invalid_body_command"]
                    wp_z = None
                else:
                    vx, vy = body_velocity
                    cmd_heading = math.degrees(math.atan2(vy, vx))
                    yaw_rate = 0.0  # X2 360°lidar 无需对头;持续旋转曾致 SLAM 失锁(5a-1)
                    self.last_move_cmd_t = time.monotonic()
                    self.get_logger().info(
                        "INTENT traj#%d wp[%d/%d]=(%.2f,%.2f,%.2f) odom=(%.2f,%.2f) "
                        "dist=%.2f map_yaw=%.1f fcu_yaw=%.1f yaw_age=%.2f cmd_body=%.1f "
                        "-> v=(%.3f,%.3f)" % (
                            self.traj_id, self.wp_idx, len(self.traj.points), wp.x, wp.y, wp.z,
                            p.x, p.y, dist, math.degrees(self.map_yaw),
                            math.degrees(self.fcu_yaw), self.fcu_yaw_age_s(), cmd_heading,
                            vx, vy))
            else:
                blockers = ["awaiting_next_trajectory"]

        intent = {
            "ok": not blockers,
            "source": "gbp_traj_to_intent",
            "strategy": "gbplanner",
            "goal_id": "gbp_t%d_w%d" % (self.traj_id, self.wp_idx),
            "linear_x_mps": vx, "linear_y_mps": vy, "yaw_rate_radps": yaw_rate,
        }
        # M5 z闭环:运动带当前目标 wp 的 z;hold 在 last_z_m 已知时保持;
        # 从未有合法 z 时不带字段(控制器回退 -takeoff_alt_m,向后兼容)。
        # 对抗验证修正(2026-07-28):z_m 仅在 enabled 且未 killed 时附带——
        # 否则租约收回/降落期的 hold intent 会带着旧高度顶飞机对抗下降。
        if self.enabled and not self.killed:
            z_m = intent_z(wp_z, self.last_z_m)
            if z_m is not None:
                intent["z_m"] = z_m
                self.last_z_m = z_m
        self.pub_intent.publish(String(data=json.dumps(intent)))

        # Stage5a 严格 gate(Review_016 §3.3 五条件,Stage4c PASS 后启用):
        # external 去混流(mixed_flow 闩锁)+ takeoff/controller ready + 诚实 accepted_goals
        # + path 达标 + 无运行 blocker。达成即闩锁(尾段 trajectory_stale 不回撤已达成事实)。
        gate_ok_draft = (self.wp_done >= 3) and (self.path_len >= 0.35)
        if (not self.ok_latched and self.enabled and not self.killed
                and not self.mixed_flow and self.controller_ready
                and self.wp_done >= 3 and self.path_len >= 0.35
                and not blockers):
            self.ok_latched = True
            self.get_logger().warning(
                "GATE OK latched: wp_done=%d path=%.2fm controller_ready=%s mixed_flow=%s"
                % (self.wp_done, self.path_len, self.controller_ready, self.mixed_flow))
        status = {
            "claim": "evaluated" if self.ok_latched else "in_progress",
            "strategy": "gbplanner",
            "ok": self.ok_latched,
            "gate_ok_draft": gate_ok_draft,
            "blockers": blockers,
            "accepted_goals": self.wp_done,
            "min_accepted_goals": 3,
            "path_length_m": round(self.path_len, 4),
            "min_path_length_m": 0.35,
            "motion_speed_mps": SPEED_MAX,
            "enabled": self.enabled,
            "traj_count": self.traj_id,
            "wp_prereached_excluded": self.wp_prereached,
            "controller_ready": self.controller_ready,
            "mixed_flow": self.mixed_flow,
        }
        self.pub_status.publish(String(data=json.dumps(status)))


def main():
    rclpy.init()
    rclpy.spin(TrajToIntent())


if __name__ == "__main__":
    main()
