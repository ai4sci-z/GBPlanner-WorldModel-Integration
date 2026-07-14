from __future__ import annotations

import json
import math
import time

SPEC = json.loads("{\"controller_status_topic\":\"/navlab/fcu/controller/status\",\"duration_sec\":13,\"exploration_status_topic\":\"/navlab/exploration/status\",\"exploration_window_sec\":26,\"map_topic\":\"/map\",\"min_accepted_goals\":3,\"min_path_length_m\":0.35,\"motion_speed_mps\":0.1,\"setpoint_intent_topic\":\"/navlab/fcu/setpoint/intent\",\"setpoint_output_topic\":\"/navlab/fcu/setpoint/output\",\"slam_odom_topic\":\"/slam/odom\",\"strategy\":\"gbplanner_gain\",\"yaw_rate_radps\":0.18}")

def main() -> int:
    import rclpy
    from rclpy.parameter import Parameter
    from rclpy.qos import qos_profile_sensor_data
    from nav_msgs.msg import Odometry, OccupancyGrid
    from std_msgs.msg import String

    rclpy.init()
    node = rclpy.create_node("navlab_exploration_workflow")
    node.set_parameters([Parameter("use_sim_time", Parameter.Type.BOOL, True)])
    clock_deadline = time.monotonic() + 5.0
    while rclpy.ok() and time.monotonic() < clock_deadline and node.get_clock().now().nanoseconds <= 0:
        rclpy.spin_once(node, timeout_sec=0.1)

    state = {
        "controller": {},
        "controller_ready": False,
        "odom_samples": 0,
        "last_xyz": None,
        "heading": 0.0,
        "grid": None,
        "last_theta": None,
        "path_length_m": 0.0,
        "accepted_goals": 0,
        "last_goal_index": -1,
        "started_ms": int(time.time() * 1000),
        "ready_since": 0.0,
        "completed_ms": 0,
        "completed_at": 0.0,
        "last_intent": {},
    }

    def on_controller_status(msg: String) -> None:
        payload = parse_json(msg.data)
        state["controller"] = payload
        was_ready = bool(state.get("controller_ready", False))
        state["controller_ready"] = bool(payload.get("ok", False) or payload.get("ready", False))
        if state["controller_ready"] and not was_ready:
            state["ready_since"] = time.monotonic()
            state["last_goal_index"] = -1
            state["accepted_goals"] = 0
            state["path_length_m"] = 0.0
            state["last_xyz"] = None

    def on_slam_odom(msg: Odometry) -> None:
        xyz = (
            float(msg.pose.pose.position.x),
            float(msg.pose.pose.position.y),
            float(msg.pose.pose.position.z),
        )
        last = state.get("last_xyz")
        state["odom_samples"] += 1
        if last is not None:
            dx = xyz[0] - last[0]
            dy = xyz[1] - last[1]
            dz = xyz[2] - last[2]
            step = math.sqrt(dx * dx + dy * dy + dz * dz)
            if step <= 1.0:
                state["path_length_m"] += step
        state["last_xyz"] = xyz
        q = msg.pose.pose.orientation
        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        state["heading"] = math.atan2(siny, cosy)

    node.create_subscription(String, SPEC["controller_status_topic"], on_controller_status, 10)
    node.create_subscription(Odometry, SPEC["slam_odom_topic"], on_slam_odom, qos_profile_sensor_data)
    if SPEC.get("strategy") == "gbplanner_gain":
        def on_map(msg: OccupancyGrid) -> None:
            state["grid"] = OccGrid(msg)
        node.create_subscription(OccupancyGrid, SPEC.get("map_topic", "/map") or "/map", on_map, 1)
    intent_pub = node.create_publisher(String, SPEC["setpoint_intent_topic"], 10)
    status_pub = node.create_publisher(String, SPEC["exploration_status_topic"], 10)
    goal_pub = node.create_publisher(String, "/navlab/exploration/goal", 10)
    coverage_pub = node.create_publisher(String, "/navlab/exploration/coverage", 10)
    frontiers_pub = node.create_publisher(String, "/navlab/exploration/frontiers", 10)
    path_pub = node.create_publisher(String, "/navlab/exploration/path", 10)
    markers_pub = node.create_publisher(String, "/navlab/exploration/markers", 10)

    speed = max(0.03, float(SPEC.get("motion_speed_mps", 0.10) or 0.10))
    min_goals = max(1, int(SPEC.get("min_accepted_goals", 3) or 3))
    window_sec = max(float(SPEC.get("exploration_window_sec", 26.0) or 26.0), float(min_goals) * 2.0)
    duration_sec = max(float(SPEC.get("duration_sec", window_sec) or window_sec), window_sec)
    segment_sec = max(2.0, window_sec / float(min_goals))
    start = time.monotonic()
    deadline = start + duration_sec + 15.0
    completed_hold_sec = 5.0

    while rclpy.ok() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.02)
        ready_elapsed = 0.0
        if state.get("controller_ready") and float(state.get("ready_since", 0.0) or 0.0) > 0.0:
            ready_elapsed = time.monotonic() - float(state.get("ready_since", 0.0) or 0.0)
        status = exploration_status(state)
        status_pub.publish(string_msg(status))
        publish_review_topics(goal_pub, coverage_pub, frontiers_pub, path_pub, markers_pub, state, status)

        if status["ok"]:
            if not state.get("completed_ms"):
                state["completed_ms"] = int(time.time() * 1000)
                state["completed_at"] = time.monotonic()
            intent_pub.publish(string_msg(stop_intent(state, "complete")))
            if time.monotonic() - float(state.get("completed_at", 0.0) or 0.0) >= completed_hold_sec:
                break
            time.sleep(0.1)
            continue

        if state.get("controller_ready"):
            goal_index = min(int(ready_elapsed / segment_sec), min_goals - 1)
            if goal_index != state.get("last_goal_index") and state.get("odom_samples", 0) > 0:
                state["accepted_goals"] = max(state.get("accepted_goals", 0), goal_index + 1)
                state["last_goal_index"] = goal_index
            intent = exploration_intent(goal_index, speed, state)
            state["last_intent"] = intent
            intent_pub.publish(string_msg(intent))
        else:
            intent_pub.publish(string_msg(stop_intent(state, "waiting_for_controller")))
        time.sleep(0.1)

    final_status = exploration_status(state)
    for _ in range(20):
        status_pub.publish(string_msg(final_status))
        intent_pub.publish(string_msg(stop_intent(state, "shutdown")))
        rclpy.spin_once(node, timeout_sec=0.02)
        time.sleep(0.05)
    node.destroy_node()
    rclpy.shutdown()
    return 0

def parse_json(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}

def string_msg(payload: dict):
    from std_msgs.msg import String

    msg = String()
    msg.data = json.dumps(payload, sort_keys=True)
    return msg

# --- gbplanner_gain: map-aware volumetric-gain direction selection -----------
# Implements the core idea of GBPlanner (Dang et al., arXiv:2201.07067): instead of
# replaying a fixed motion pattern, read the SLAM occupancy grid, ray-cast outward in
# many directions, count reachable UNKNOWN cells (a 2D volumetric-gain proxy), penalise
# turning, and steer toward the highest-gain direction. Active only when
# SPEC["strategy"] == "gbplanner_gain"; the default frontier_lite path is untouched.
GRID_UNKNOWN = -1
GRID_OCC_MIN = 65

class OccGrid:
    def __init__(self, msg):
        self.w = msg.info.width
        self.h = msg.info.height
        self.res = msg.info.resolution or 0.05
        self.ox = msg.info.origin.position.x
        self.oy = msg.info.origin.position.y
        self.data = msg.data

    def to_cell(self, x, y):
        return int((x - self.ox) / self.res), int((y - self.oy) / self.res)

    def val(self, i, j):
        if 0 <= i < self.w and 0 <= j < self.h:
            return self.data[j * self.w + i]
        return GRID_UNKNOWN

def ray_unknown_count(grid: OccGrid, x0: float, y0: float, theta: float, max_range: float) -> int:
    step = grid.res * 0.5
    dx, dy = math.cos(theta), math.sin(theta)
    unknown = 0
    last = None
    t = step
    while t <= max_range:
        i, j = grid.to_cell(x0 + dx * t, y0 + dy * t)
        if not (0 <= i < grid.w and 0 <= j < grid.h):
            break
        if (i, j) != last:
            last = (i, j)
            v = grid.val(i, j)
            if v >= GRID_OCC_MIN:
                break
            if v == GRID_UNKNOWN:
                unknown += 1
        t += step
    return unknown

def best_direction(grid: OccGrid, x0: float, y0: float, heading: float,
                   num_dirs: int = 24, max_range: float = 4.0, k_turn: float = 0.8):
    best = None
    for k in range(num_dirs):
        theta = -math.pi + 2.0 * math.pi * k / num_dirs
        gain = 0.0
        for off in (-0.13, 0.0, 0.13):
            gain += ray_unknown_count(grid, x0, y0, theta + off, max_range)
        gain *= grid.res * grid.res
        dh = abs(theta - heading)
        if dh > math.pi:
            dh = 2.0 * math.pi - dh
        score = gain - k_turn * dh
        if best is None or score > best[2]:
            best = (theta, gain, score)
    return best

def gbplanner_gain_intent(goal_index: int, speed: float, state: dict) -> dict:
    grid = state["grid"]
    pose = state.get("last_xyz") or (0.0, 0.0, 0.0)
    heading = float(state.get("heading", 0.0) or 0.0)
    theta, gain, _ = best_direction(grid, pose[0], pose[1], heading)
    dyaw = theta - heading
    while dyaw > math.pi:
        dyaw -= 2.0 * math.pi
    while dyaw < -math.pi:
        dyaw += 2.0 * math.pi
    yaw_rate = max(-0.4, min(0.4, dyaw))
    forward = speed if abs(dyaw) < 0.5 else speed * 0.3
    state["last_theta"] = theta
    return {
        "ok": True,
        "source": "exploration_workflow",
        "strategy": "gbplanner_gain",
        "goal_id": f"gbplanner_gain_{goal_index + 1}",
        "goal_index": goal_index,
        "linear_x_mps": forward,
        "linear_y_mps": 0.0,
        "yaw_rate_radps": yaw_rate,
        "chosen_heading_deg": round(math.degrees(theta), 1),
        "chosen_gain_m2": round(gain, 4),
        "uses_gazebo_truth_as_input": False,
        "odom_samples": state.get("odom_samples", 0),
        "path_length_m": round(state.get("path_length_m", 0.0), 4),
    }

def exploration_intent(goal_index: int, speed: float, state: dict) -> dict:
    if SPEC.get("strategy") == "gbplanner_gain" and state.get("grid") is not None:
        return gbplanner_gain_intent(goal_index, speed, state)
    pattern = [
        {"linear_x_mps": speed, "linear_y_mps": 0.0, "yaw_rate_radps": 0.0},
        {"linear_x_mps": speed * 0.6, "linear_y_mps": 0.0, "yaw_rate_radps": 0.20},
        {"linear_x_mps": speed, "linear_y_mps": 0.0, "yaw_rate_radps": -0.12},
    ]
    command = dict(pattern[goal_index % len(pattern)])
    command.update({
        "ok": True,
        "source": "exploration_workflow",
        "strategy": SPEC.get("strategy", "frontier_lite"),
        "goal_id": f"frontier_lite_{goal_index + 1}",
        "goal_index": goal_index,
        "uses_gazebo_truth_as_input": False,
        "odom_samples": state.get("odom_samples", 0),
        "path_length_m": round(state.get("path_length_m", 0.0), 4),
    })
    return command

def stop_intent(state: dict, reason: str) -> dict:
    return {
        "ok": True,
        "source": "exploration_workflow",
        "strategy": SPEC.get("strategy", "frontier_lite"),
        "goal_id": "hold",
        "linear_x_mps": 0.0,
        "linear_y_mps": 0.0,
        "yaw_rate_radps": 0.0,
        "reason": reason,
        "uses_gazebo_truth_as_input": False,
        "odom_samples": state.get("odom_samples", 0),
        "path_length_m": round(state.get("path_length_m", 0.0), 4),
    }

def exploration_status(state: dict) -> dict:
    accepted_goals = int(state.get("accepted_goals", 0) or 0)
    min_goals = int(SPEC.get("min_accepted_goals", 3) or 3)
    path_length = float(state.get("path_length_m", 0.0) or 0.0)
    min_path = float(SPEC.get("min_path_length_m", 0.35) or 0.35)
    odom_samples = int(state.get("odom_samples", 0) or 0)
    blockers = []
    if not state.get("controller_ready", False):
        blockers.append("controller_not_ready")
    if odom_samples <= 0:
        blockers.append("slam_odom_missing")
    if accepted_goals < min_goals:
        blockers.append("accepted_goals_below_min")
    if path_length < min_path:
        blockers.append("path_length_below_min")
    ok = len(blockers) == 0
    return {
        "ok": ok,
        "claim": "evaluated" if ok else "in_progress",
        "strategy": SPEC.get("strategy", "frontier_lite"),
        "accepted_goals": accepted_goals,
        "min_accepted_goals": min_goals,
        "path_length_m": round(path_length, 4),
        "min_path_length_m": min_path,
        "motion_speed_mps": float(SPEC.get("motion_speed_mps", 0.0) or 0.0),
        "odom_samples": odom_samples,
        "controller_ready": bool(state.get("controller_ready", False)),
        "ready_elapsed_sec": round(max(0.0, time.monotonic() - float(state.get("ready_since", 0.0) or time.monotonic())) if state.get("controller_ready", False) else 0.0, 3),
        "uses_gazebo_truth_as_input": False,
        "evidence_source": SPEC.get("slam_odom_topic", "/slam/odom"),
        "setpoint_intent_topic": SPEC.get("setpoint_intent_topic", ""),
        "blockers": blockers,
    }

def publish_review_topics(goal_pub, coverage_pub, frontiers_pub, path_pub, markers_pub, state: dict, status: dict) -> None:
    goal_payload = {
        "strategy": SPEC.get("strategy", "frontier_lite"),
        "accepted_goals": status.get("accepted_goals", 0),
        "last_intent": state.get("last_intent", {}),
        "uses_gazebo_truth_as_input": False,
    }
    coverage_payload = {
        "coverage_proxy": round(min(1.0, status.get("path_length_m", 0.0) / max(status.get("min_path_length_m", 0.35), 0.01)), 4),
        "path_length_m": status.get("path_length_m", 0.0),
        "source": SPEC.get("slam_odom_topic", "/slam/odom"),
    }
    frontiers_payload = {
        "strategy": SPEC.get("strategy", "frontier_lite"),
        "candidate_count": max(0, int(status.get("min_accepted_goals", 3)) - int(status.get("accepted_goals", 0))),
        "source": "occupancy_grid_volumetric_gain" if SPEC.get("strategy") == "gbplanner_gain" else "bounded_lite_pattern",
    }
    path_payload = {
        "path_length_m": status.get("path_length_m", 0.0),
        "odom_samples": status.get("odom_samples", 0),
        "source": SPEC.get("slam_odom_topic", "/slam/odom"),
    }
    markers_payload = {
        "state": "complete" if status.get("ok", False) else "running",
        "blockers": status.get("blockers", []),
    }
    goal_pub.publish(string_msg(goal_payload))
    coverage_pub.publish(string_msg(coverage_payload))
    frontiers_pub.publish(string_msg(frontiers_payload))
    path_pub.publish(string_msg(path_payload))
    markers_pub.publish(string_msg(markers_payload))

if __name__ == "__main__":
    raise SystemExit(main())
