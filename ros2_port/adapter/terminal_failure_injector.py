#!/usr/bin/env python3
"""Inject an explicit GBPlanner kill after the simulated FCU is ready."""

import argparse
import json
import time


def controller_ready(payload):
    """Return true only for the post-takeoff controller-ready contract."""
    if not isinstance(payload, dict):
        return False
    return payload.get("ready") is True and payload.get("bootstrap_ready") is True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay-sec", type=float, default=3.0)
    parser.add_argument("--ready-timeout-sec", type=float, default=120.0)
    args = parser.parse_args()
    if args.delay_sec < 0.0 or args.ready_timeout_sec <= 0.0:
        parser.error("delay must be non-negative and ready timeout must be positive")

    import rclpy
    from std_msgs.msg import Bool, String

    rclpy.init()
    node = rclpy.create_node("gbp_terminal_failure_injector")
    state = {"ready_at": None}

    def on_status(msg):
        try:
            payload = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError):
            return
        if state["ready_at"] is None and controller_ready(payload):
            state["ready_at"] = time.monotonic()

    node.create_subscription(String, "/navlab/fcu/controller/status", on_status, 10)
    publisher = node.create_publisher(Bool, "/gbp/kill", 10)
    deadline = time.monotonic() + args.ready_timeout_sec
    published = False
    while rclpy.ok() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
        ready_at = state["ready_at"]
        if ready_at is None or time.monotonic() - ready_at < args.delay_sec:
            continue
        for _ in range(10):
            publisher.publish(Bool(data=True))
            rclpy.spin_once(node, timeout_sec=0.1)
        published = True
        break

    evidence = {
        "schemaVersion": "gbplanner.m5.terminal_injection.v1",
        "published": published,
        "reason": "killed",
        "controller_ready_seen": state["ready_at"] is not None,
        "delay_sec": args.delay_sec,
    }
    print(json.dumps(evidence, sort_keys=True), flush=True)
    node.destroy_node()
    rclpy.shutdown()
    return 0 if published else 2


if __name__ == "__main__":
    raise SystemExit(main())
