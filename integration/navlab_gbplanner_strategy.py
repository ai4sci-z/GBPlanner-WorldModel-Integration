#!/usr/bin/env python3
"""
navlab_gbplanner_strategy —— 把 GBPlanner 的"体积增益探索决策"落进 world-model。

背景(基于真实源码):world-model 的 exploration 任务现用 `frontier_lite` 策略,
其决策核心是 `pattern[goal_index % 3]` 按计时器循环 3 个写死动作,且**不订阅任何地图**
(见 exploration_workflow_runtime.py.tmpl)。这只是控制链路冒烟测试,不是探索算法。

本模块实现一个**真正读地图、按增益选路**的策略(GBPlanner 核心思想,2D 版):
  订阅 SLAM 的占据栅格 /map(nav_msgs/OccupancyGrid)→ 以机器人为中心,
  对 N 个方向做光线投射、数"未知"栅格(= 体积增益)→ 减转向惩罚 → 选增益最高且可达的方向 →
  发布朝该方向的运动意图 /navlab/fcu/setpoint/intent(沿用现有接口与验收闸门)。

这是 GBPlanner 集成的"决策内核"第一步(纯 ROS2,不需 ros1_bridge):把决策从
"闭眼按脚本动"换成"看地图、朝未知最多的方向走"。后续可换成完整 ros1_bridge + 3D voxblox。

作为 world-model 的新策略集成方式:exploration.yaml 里 `strategy: gbplanner_gain`。
"""
from __future__ import annotations
import json
import math
import time

# OccupancyGrid 取值约定
UNKNOWN = -1
FREE_MAX = 50      # < 50 视为空闲
OCC_MIN = 65       # >= 65 视为占据


class OccGrid:
    """对 nav_msgs/OccupancyGrid 的轻封装:世界坐标 <-> 栅格,状态查询。"""
    def __init__(self, msg):
        self.w = msg.info.width
        self.h = msg.info.height
        self.res = msg.info.resolution
        self.ox = msg.info.origin.position.x
        self.oy = msg.info.origin.position.y
        self.data = msg.data  # 长度 w*h,行优先

    def to_cell(self, x, y):
        i = int((x - self.ox) / self.res)
        j = int((y - self.oy) / self.res)
        return i, j

    def in_bounds(self, i, j):
        return 0 <= i < self.w and 0 <= j < self.h

    def val(self, i, j):
        if not self.in_bounds(i, j):
            return UNKNOWN
        return self.data[j * self.w + i]

    def is_free(self, x, y):
        v = self.val(*self.to_cell(x, y))
        return 0 <= v < FREE_MAX

    def is_occ(self, x, y):
        v = self.val(*self.to_cell(x, y))
        return v >= OCC_MIN

    def is_unknown(self, x, y):
        return self.val(*self.to_cell(x, y)) == UNKNOWN


def ray_unknown_count(grid: OccGrid, x0, y0, theta, max_range):
    """从 (x0,y0) 沿 theta 走,数沿途未知栅格数,遇占据停。= GBPlanner 体积增益的最小单元。"""
    step = grid.res * 0.5
    dx, dy = math.cos(theta), math.sin(theta)
    unknown = 0
    last = None
    t = step
    while t <= max_range:
        x, y = x0 + dx * t, y0 + dy * t
        i, j = grid.to_cell(x, y)
        if not grid.in_bounds(i, j):
            break
        if (i, j) != last:
            last = (i, j)
            v = grid.val(i, j)
            if v >= OCC_MIN:
                break              # 被挡,视线到此为止
            if v == UNKNOWN:
                unknown += 1       # 看见一个未知栅格
        t += step
    return unknown


def best_direction(grid: OccGrid, x0, y0, heading,
                   num_dirs=24, max_range=4.0, k_turn=0.8):
    """对 num_dirs 个方向算增益(扇形内多条射线累加),减转向惩罚,返回最优 (theta, gain, score)。"""
    best = None
    for k in range(num_dirs):
        theta = -math.pi + 2 * math.pi * k / num_dirs
        gain = 0.0
        for d in (-0.13, 0.0, 0.13):  # 扇形:每个方向 3 条射线
            gain += ray_unknown_count(grid, x0, y0, theta + d, max_range)
        gain *= grid.res * grid.res   # 乘单元面积 ~ 可见未知面积(2D 体积增益)
        dh = abs(theta - heading)
        if dh > math.pi:
            dh = 2 * math.pi - dh
        score = gain - k_turn * dh
        if best is None or score > best[2]:
            best = (theta, gain, score)
    return best  # (theta, gain, score)


def main() -> int:
    import rclpy
    from rclpy.parameter import Parameter
    from rclpy.qos import qos_profile_sensor_data
    from nav_msgs.msg import Odometry, OccupancyGrid
    from std_msgs.msg import String

    # 运行参数(由 world-model 注入;给默认值便于独立测试)
    SPEC = {
        "controller_status_topic": "/navlab/fcu/controller/status",
        "slam_odom_topic": "/slam/odom",
        "map_topic": "/map",
        "setpoint_intent_topic": "/navlab/fcu/setpoint/intent",
        "exploration_status_topic": "/navlab/exploration/status",
        "motion_speed_mps": 0.25,
        "min_accepted_goals": 3,
        "exploration_window_sec": 40.0,
        "duration_sec": 150.0,
        "min_path_length_m": 0.35,
        "max_range_m": 4.0,
    }

    rclpy.init()
    node = rclpy.create_node("navlab_gbplanner_strategy")
    node.set_parameters([Parameter("use_sim_time", Parameter.Type.BOOL, True)])

    state = {"grid": None, "pose": None, "heading": 0.0, "ready": False,
             "path_len": 0.0, "last_xyz": None, "accepted_goals": 0, "last_theta": None}

    def on_status(msg: String):
        try:
            p = json.loads(msg.data)
        except Exception:
            p = {}
        state["ready"] = bool(p.get("ok") or p.get("ready"))

    def on_odom(msg: Odometry):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        z = msg.pose.pose.position.z
        q = msg.pose.pose.orientation
        # yaw from quaternion
        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        state["heading"] = math.atan2(siny, cosy)
        state["pose"] = (x, y, z)
        last = state["last_xyz"]
        if last is not None:
            step = math.dist((x, y, z), last)
            if step <= 1.0:
                state["path_len"] += step
        state["last_xyz"] = (x, y, z)

    def on_map(msg: OccupancyGrid):
        state["grid"] = OccGrid(msg)

    node.create_subscription(String, SPEC["controller_status_topic"], on_status, 10)
    node.create_subscription(Odometry, SPEC["slam_odom_topic"], on_odom, qos_profile_sensor_data)
    node.create_subscription(OccupancyGrid, SPEC["map_topic"], on_map, 1)
    intent_pub = node.create_publisher(String, SPEC["setpoint_intent_topic"], 10)
    status_pub = node.create_publisher(String, SPEC["exploration_status_topic"], 10)
    goal_pub = node.create_publisher(String, "/navlab/exploration/goal", 10)

    speed = float(SPEC["motion_speed_mps"])
    max_range = float(SPEC["max_range_m"])
    min_goals = int(SPEC["min_accepted_goals"])
    deadline = time.monotonic() + float(SPEC["duration_sec"]) + 15.0

    def publish_status(blockers, theta, gain):
        ok = (len(blockers) == 0 and state["accepted_goals"] >= min_goals
              and state["path_len"] >= float(SPEC["min_path_length_m"]))
        status_pub.publish(_s({
            "ok": ok, "strategy": "gbplanner_gain",
            "accepted_goals": state["accepted_goals"], "min_accepted_goals": min_goals,
            "path_length_m": round(state["path_len"], 4),
            "chosen_heading_deg": None if theta is None else round(math.degrees(theta), 1),
            "chosen_gain_m2": round(gain, 4),
            "uses_gazebo_truth_as_input": False, "blockers": blockers,
        }))

    while rclpy.ok() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        blockers = []
        if not state["ready"]:
            blockers.append("controller_not_ready")
        if state["pose"] is None:
            blockers.append("slam_odom_missing")
        if state["grid"] is None:
            blockers.append("map_missing")

        if state["ready"] and state["pose"] is not None and state["grid"] is not None:
            x, y, _ = state["pose"]
            theta, gain, _ = best_direction(state["grid"], x, y, state["heading"],
                                            max_range=max_range)
            # 朝最优方向:转头对准 + 前进
            dyaw = theta - state["heading"]
            while dyaw > math.pi: dyaw -= 2 * math.pi
            while dyaw < -math.pi: dyaw += 2 * math.pi
            yaw_rate = max(-0.4, min(0.4, dyaw))
            fwd = speed if abs(dyaw) < 0.5 else speed * 0.3  # 先大致对准再前进
            intent_pub.publish(_s({
                "ok": True, "source": "gbplanner_gain", "strategy": "gbplanner_gain",
                "goal_id": "gain_max", "linear_x_mps": fwd, "linear_y_mps": 0.0,
                "yaw_rate_radps": yaw_rate, "uses_gazebo_truth_as_input": False,
                "chosen_gain_m2": round(gain, 4),
            }))
            goal_pub.publish(_s({"strategy": "gbplanner_gain",
                                 "heading_deg": round(math.degrees(theta), 1),
                                 "gain_m2": round(gain, 4)}))
            # 计数:朝向显著切换一次记一个 accepted goal
            if state["last_theta"] is None or abs(theta - state["last_theta"]) > 0.3:
                state["accepted_goals"] += 1
                state["last_theta"] = theta
            publish_status(blockers, theta, gain)
        else:
            intent_pub.publish(_s({"ok": True, "strategy": "gbplanner_gain",
                                   "goal_id": "hold", "linear_x_mps": 0.0,
                                   "linear_y_mps": 0.0, "yaw_rate_radps": 0.0,
                                   "reason": ",".join(blockers)}))
            publish_status(blockers, None, 0.0)
        time.sleep(0.1)

    node.destroy_node()
    rclpy.shutdown()
    return 0


def _s(payload):
    from std_msgs.msg import String
    m = String()
    m.data = json.dumps(payload, sort_keys=True)
    return m


if __name__ == "__main__":
    raise SystemExit(main())
