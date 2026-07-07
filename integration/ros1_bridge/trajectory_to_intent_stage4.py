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
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool, String
from trajectory_msgs.msg import MultiDOFJointTrajectory

SPEED_MAX = 0.08
YAW_RATE_MAX = 0.30
WP_REACHED_M = 0.15
ODOM_STALE_S = 2.0
TRAJ_STALE_S = 15.0     # 跟完后等新轨迹的宽限
TRAJ_MAX_AGE_S = 30.0   # 轨迹绝对最大年龄:超龄即弃(Review_014-①,防追陈旧轨迹)

# Stage5cal 实测(stage5cal_axis_evidence + BIN GUIP/XKF1 验尸):
# fcu_controller MAVLink 主路把 intent (x,y) 不经旋转直接用作 NED (north,east) 位移;
# SLAM map 与 AP NED 之间 = 互换(反射)+ per-run 不定旋转(SLAM yaw 漂移)。
# 方案演进:固定表(5a-1 失败:偏角 per-run 变)→ 运动响应 EMA 闭环(5a-2 失败:
# 2~3s 响应滞后 × 每tick增益 = 延迟失稳,θ̂ 发散绕圈)→ 现行方案:
# **双坐标系同步观测 Procrustes**:/slam/odom(map)与 /navlab/fcu/local_position_pose
# (AP NED)同测同一物理运动,位移对 (Δmap,Δned) 正交最小二乘解 R_align(吃掉互换+
# 旋转+反射),零滞后、无需探测机动。yaw_rate 恒 0(X2 360°lidar 无需对头,
# 持续旋转是 5a-1 SLAM 失锁根因)。
import numpy as np

# EKF 修复(yaw同源+罗盘关)后系统实测映射≈恒等(6跑 Rang=4° det=+1):
# sender 直接把 map 坐标喂 AP,全链 map 自洽 → intent→map ≈ I,恒等为正确初值。
R_ALIGN_INIT = np.array([[1.0, 0.0], [0.0, 1.0]])
PAIR_MIN_STEP_M = 0.01    # 位移对最小步长(低于视为噪声不入账;慢爬也要能供数据)
M_DECAY = 0.995           # 累积矩阵缓慢遗忘(容忍 SLAM yaw 缓漂)
SLAM_FROZEN_S = 4.0       # 运动指令活跃但 odom 位置基本不动 → slam_frozen blocker
FROZEN_EPS_M = 0.02       # "基本不动"阈值(SLAM 抖动 ±1cm,5a-2 实测)


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
        self.wp_done = 0              # 只计"运动到达"的 waypoint(诚实 accepted_goals)
        self.wp_prereached = 0        # 轨迹到手时已在起点阈值内的 wp(不计入 accepted_goals)
        self.path_len = 0.0
        self.last_xy = None
        # Stage5a 严格 gate 所需的外部事实
        self.controller_ready = False   # /navlab/fcu/controller/status ok(bootstrap 含 takeoff)
        self.mixed_flow = False         # intent 总线上出现过非本适配器来源 → 永久闩锁
        self.ok_latched = False         # 五条件一旦达成即闩锁(尾段 stale blocker 不回撤已达成事实)
        # 双坐标系同步观测 → R_align(map位移 → ned位移)
        self.R_align = R_ALIGN_INIT.copy()
        self.M_acc = np.zeros((2, 2))   # Σ dn·dmᵀ(带遗忘)
        self.pair_count = 0
        self.lpp_hist = []              # [(t, ned_xy, map_xy)] ~1.2s 基线(慢爬也凑得出位移对)
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
        if self.traj is None:
            b.append("no_trajectory")
        elif time.monotonic() - self.traj_t > TRAJ_MAX_AGE_S:
            b.append("trajectory_max_age")  # 超龄即弃,不沿旧航点续跑
        elif self.wp_idx >= len(self.traj.points) and time.monotonic() - self.traj_t > TRAJ_STALE_S:
            b.append("trajectory_stale")
        if self.traj is not None and self.traj.header.frame_id not in ("map",):
            b.append("frame_mismatch:%s" % self.traj.header.frame_id)
        return b

    def on_lpp(self, m):
        # AP NED 位姿采样(~4Hz):与同刻 map 位置组成位移对(~1.2s 基线),Procrustes 更新 R_align
        if self.last_xy is None:
            return
        now = time.monotonic()
        ned = (m.pose.position.x, m.pose.position.y)
        map_xy = self.last_xy
        if self.lpp_hist:
            t0, ned0, map0 = self.lpp_hist[0]
            dn = np.array([ned[0] - ned0[0], ned[1] - ned0[1]])
            dm = np.array([map_xy[0] - map0[0], map_xy[1] - map0[1]])
            if np.hypot(*dn) > PAIR_MIN_STEP_M and np.hypot(*dm) > PAIR_MIN_STEP_M:
                self.M_acc = M_DECAY * self.M_acc + np.outer(dn, dm)
                self.pair_count += 1
                try:
                    U, _, Vt = np.linalg.svd(self.M_acc)
                    self.R_align = U @ Vt   # 正交(含反射)最优拟合:dn ≈ R_align·dm
                except np.linalg.LinAlgError:
                    pass
        self.lpp_hist.append((now, ned, map_xy))
        while self.lpp_hist and now - self.lpp_hist[0][0] > 1.2:
            self.lpp_hist.pop(0)

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
                dx, dy = wp.x - p.x, wp.y - p.y
                dist = math.hypot(dx, dy)
                # fcu 主路是"胡萝卜"位置目标(当前+v×2s):目标不得越过 wp(否则 0.15m
                # 到达圈套不住 ~0.3m/s 的追赶,7 跑实测 0.5m 极限环)→ 近距按比例减速。
                forward = min(SPEED_MAX, 0.4 * dist)
                # 期望 map 方向 → R_align(双坐标系 Procrustes 实测)→ intent(NED 分量)
                d = np.array([dx, dy]) / max(dist, 1e-6)
                v_ned = self.R_align @ (d * forward)
                vx, vy = float(v_ned[0]), float(v_ned[1])
                yaw_rate = 0.0  # X2 360°lidar 无需对头;持续旋转曾致 SLAM 失锁(5a-1)
                self.last_move_cmd_t = time.monotonic()
                ra = math.degrees(math.atan2(self.R_align[1, 0], self.R_align[0, 0]))
                self.get_logger().info(
                    "INTENT traj#%d wp[%d/%d]=(%.2f,%.2f,%.2f) odom=(%.2f,%.2f) dist=%.2f Rpairs=%d Rang=%.0f det=%.0f -> v=(%.3f,%.3f)" % (
                        self.traj_id, self.wp_idx, len(self.traj.points), wp.x, wp.y, wp.z,
                        p.x, p.y, dist, self.pair_count, ra, np.linalg.det(self.R_align), vx, vy))
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
