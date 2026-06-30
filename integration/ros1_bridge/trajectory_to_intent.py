#!/usr/bin/env python3
"""
trajectory_to_intent —— 阶段4 桥接的 ROS2 侧"出口适配器"。

真版 GBPlanner(ROS1)经 PCI 把规划结果发成 trajectory_msgs/MultiDOFJointTrajectory
(话题 <robot>/command/trajectory,源码证实 pci_general.cpp:8 advertise)。ros1_bridge 把它
原样桥到 ROS2。本节点订阅它 + /slam/odom,把"下一航点"转成 world-model 的运动意图
/navlab/fcu/setpoint/intent(std_msgs/String JSON,沿用 exploration 现有接口与验收闸门),
strategy 标为 "gbplanner"。

这样:GBPlanner 在 ROS1 侧原样跑(含 voxblox 3D 建图 + RRG + 体积增益 + PCI),
跨桥只走标准消息类型,ROS2 侧只做"航点→机体速度意图"的薄转换,替换脚本式 frontier_lite。

注:这是阶段4 桥接的 ROS2 出口适配器;完整端到端还需 ①给 iq_quad 加 3D 雷达
产出 /pointcloud ②编译运行 ros1_bridge ③ROS1 侧跑 gbplanner_node+PCI。见同目录 README。
"""
from __future__ import annotations
import json
import math


def yaw_from_quat(x, y, z, w):
    siny = 2.0 * (w * z + x * y)
    cosy = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny, cosy)


def body_intent(cur_xyz, cur_yaw, wp_xyz, speed_max, yaw_rate_max):
    """把目标航点(世界系)转成机体系速度意图:朝航点对准+前进。"""
    dx = wp_xyz[0] - cur_xyz[0]
    dy = wp_xyz[1] - cur_xyz[1]
    dist = math.hypot(dx, dy)
    target_yaw = math.atan2(dy, dx) if dist > 1e-3 else cur_yaw
    dyaw = target_yaw - cur_yaw
    while dyaw > math.pi:
        dyaw -= 2.0 * math.pi
    while dyaw < -math.pi:
        dyaw += 2.0 * math.pi
    yaw_rate = max(-yaw_rate_max, min(yaw_rate_max, dyaw))
    # 先大致对准再前进,避免边转边冲
    forward = speed_max if abs(dyaw) < 0.5 else speed_max * 0.3
    forward = min(forward, dist)  # 接近航点时减速
    return forward, yaw_rate, dist, target_yaw


def main() -> int:
    import rclpy
    from rclpy.parameter import Parameter
    from rclpy.qos import qos_profile_sensor_data
    from nav_msgs.msg import Odometry
    from trajectory_msgs.msg import MultiDOFJointTrajectory
    from std_msgs.msg import String

    SPEC = {
        "trajectory_topic": "/rmf_obelix/command/trajectory",
        "slam_odom_topic": "/slam/odom",
        "setpoint_intent_topic": "/navlab/fcu/setpoint/intent",
        "exploration_status_topic": "/navlab/exploration/status",
        "speed_max_mps": 0.25,
        "yaw_rate_max_radps": 0.4,
        "waypoint_reached_m": 0.25,
    }

    rclpy.init()
    node = rclpy.create_node("navlab_gbplanner_trajectory_to_intent")
    node.set_parameters([Parameter("use_sim_time", Parameter.Type.BOOL, True)])

    state = {"pose": None, "yaw": 0.0, "wps": [], "wp_i": 0, "have_traj": False}

    def on_odom(msg: Odometry):
        p = msg.pose.pose
        q = p.orientation
        state["pose"] = (p.position.x, p.position.y, p.position.z)
        state["yaw"] = yaw_from_quat(q.x, q.y, q.z, q.w)

    def on_traj(msg: MultiDOFJointTrajectory):
        # 每个 point 的 transforms[0].translation 是一个航点(世界系)
        wps = []
        for pt in msg.points:
            if pt.transforms:
                t = pt.transforms[0].translation
                wps.append((t.x, t.y, t.z))
        if wps:
            state["wps"] = wps
            state["wp_i"] = 0
            state["have_traj"] = True

    node.create_subscription(Odometry, SPEC["slam_odom_topic"], on_odom, qos_profile_sensor_data)
    node.create_subscription(MultiDOFJointTrajectory, SPEC["trajectory_topic"], on_traj, 10)
    intent_pub = node.create_publisher(String, SPEC["setpoint_intent_topic"], 10)
    status_pub = node.create_publisher(String, SPEC["exploration_status_topic"], 10)

    speed_max = float(SPEC["speed_max_mps"])
    yaw_rate_max = float(SPEC["yaw_rate_max_radps"])
    reached = float(SPEC["waypoint_reached_m"])

    def publish(payload):
        m = String()
        m.data = json.dumps(payload, sort_keys=True)
        intent_pub.publish(m)

    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.05)
        blockers = []
        if state["pose"] is None:
            blockers.append("slam_odom_missing")
        if not state["have_traj"]:
            blockers.append("gbplanner_trajectory_missing")

        if not blockers:
            cur = state["pose"]
            # 跳过已到达的航点
            while state["wp_i"] < len(state["wps"]) - 1:
                wp = state["wps"][state["wp_i"]]
                if math.hypot(wp[0] - cur[0], wp[1] - cur[1]) <= reached:
                    state["wp_i"] += 1
                else:
                    break
            wp = state["wps"][state["wp_i"]]
            fwd, yaw_rate, dist, tyaw = body_intent(cur, state["yaw"], wp, speed_max, yaw_rate_max)
            publish({
                "ok": True, "source": "gbplanner_bridge", "strategy": "gbplanner",
                "goal_id": "gbplanner_wp_%d" % state["wp_i"],
                "linear_x_mps": round(fwd, 4), "linear_y_mps": 0.0,
                "yaw_rate_radps": round(yaw_rate, 4),
                "target_heading_deg": round(math.degrees(tyaw), 1),
                "waypoint_index": state["wp_i"], "waypoints_total": len(state["wps"]),
                "dist_to_wp_m": round(dist, 3),
                "uses_gazebo_truth_as_input": False,
            })
        else:
            publish({
                "ok": True, "source": "gbplanner_bridge", "strategy": "gbplanner",
                "goal_id": "hold", "linear_x_mps": 0.0, "linear_y_mps": 0.0,
                "yaw_rate_radps": 0.0, "reason": ",".join(blockers),
                "uses_gazebo_truth_as_input": False,
            })

    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
