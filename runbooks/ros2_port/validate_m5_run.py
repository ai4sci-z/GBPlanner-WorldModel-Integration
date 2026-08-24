#!/usr/bin/env python3
"""Validate one M5 run against the project owner's fail-closed evidence gate."""

import argparse
import json
import re
import sys
from pathlib import Path


def nested(data, *keys):
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def load_json(path, failures, label):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{label}_unreadable:{exc}")
        return {}


def validate(run_dir, stack_log_dir):
    failures = []
    summary = load_json(run_dir / "summary.json", failures, "summary")
    probe = load_json(
        run_dir / "probes" / "exploration_probe.json", failures, "exploration_probe"
    )

    checks = {
        "summary_ok": summary.get("ok") is True,
        "task_status_ok": summary.get("status") == "TASK_STATUS_OK",
        "exit_code_zero": summary.get("exitCode") == 0,
        "probe_ok": probe.get("ok") is True,
        "controller_ready": nested(summary, "metrics", "gate", "controller", "ready") is True,
        "setpoint_ready": nested(summary, "metrics", "gate", "setpoint", "ready") is True,
    }

    samples = probe.get("samples") if isinstance(probe.get("samples"), dict) else {}
    exploration = nested(samples, "/navlab/exploration/status", "parsed") or {}
    landing = nested(samples, "/navlab/landing/status", "parsed") or {}
    checks.update(
        {
            "adapter_strategy": exploration.get("strategy") == "gbplanner",
            "adapter_ok": exploration.get("ok") is True,
            "adapter_trajectory": (exploration.get("traj_count") or 0) > 0,
            "adapter_goals": (exploration.get("accepted_goals") or 0)
            >= (exploration.get("min_accepted_goals") or 3),
            "adapter_unblocked": not exploration.get("blockers"),
            "landing_ok": landing.get("ok") is True,
            "landed_confirmed": landing.get("landed_confirmed") is True,
            "motors_safe": landing.get("motors_safe") is True,
            "return_home_ok": nested(landing, "return_home", "ok") is True,
        }
    )

    contract = (stack_log_dir / "m5_stack_contract.log").read_text(
        encoding="utf-8", errors="replace"
    ) if (stack_log_dir / "m5_stack_contract.log").is_file() else ""
    gbp_log = (stack_log_dir / "m5_gbp_node.log").read_text(
        encoding="utf-8", errors="replace"
    ) if (stack_log_dir / "m5_gbp_node.log").is_file() else ""
    pci_log = (stack_log_dir / "m5_pci.log").read_text(
        encoding="utf-8", errors="replace"
    ) if (stack_log_dir / "m5_pci.log").is_file() else ""
    tf_log = (stack_log_dir / "m5_tf_relay.log").read_text(
        encoding="utf-8", errors="replace"
    ) if (stack_log_dir / "m5_tf_relay.log").is_file() else ""

    graphs = [(int(v), int(e)) for v, e in re.findall(
        r"Formed a graph with \[(\d+)\] vertices and \[(\d+)\] edges", gbp_log
    )]
    trajectories = [int(n) for n in re.findall(r"published (\d+) waypoints", pci_log)]
    planning_odom_counts = [int(n) for n in re.findall(r"planning_odom=(\d+)", tf_log)]
    planning_z_maxima = [float(z) for z in re.findall(r"planning_z_max=([0-9.]+)", tf_log)]
    checks.update(
        {
            "cloud3d_contract": "POINTCLOUD_TOPIC=/wm/cloud3d" in contract,
            "lidar3d_extrinsic": "EXTRINSIC=base_link:lidar3d_frame:0,0,0.10" in contract,
            "planning_odom_contract": "ODOMETRY_TOPIC=/gbp/planning_odom" in contract,
            "planning_height_contract": (
                "ODOMETRY_HEIGHT_SOURCE=/navlab/fcu/local_position_pose:fcu_ekf_z" in contract
            ),
            "planning_tf_contract": (
                "PLANNING_TF=map:base_link:fcu_ekf_height" in contract
            ),
            "pci_one_shot_contract": (
                "PCI_POLICY=wait_for_enable,stop_after_first_path" in contract
            ),
            "planning_odom_ready": (
                any(count > 0 for count in planning_odom_counts)
                and any(z > 0.05 for z in planning_z_maxima)
            ),
            "pci_one_shot_observed": (
                "first non-empty path published; trigger timer stopped" in pci_log
            ),
            "voxblox_ready": bool(re.search(r"\[MAPPROBE\].*ready=1", gbp_log)),
            "rrg_nontrivial": any(vertices > 1 and edges > 0 for vertices, edges in graphs),
            "trajectory_published": any(points > 0 for points in trajectories),
        }
    )

    failures.extend(name for name, ok in checks.items() if not ok)
    return {
        "schemaVersion": "gbplanner.m5.acceptance.v1",
        "ok": not failures,
        "run_id": summary.get("run_id"),
        "checks": checks,
        "failures": failures,
        "evidence": {
            "max_rrg_vertices": max((v for v, _ in graphs), default=0),
            "max_rrg_edges": max((e for _, e in graphs), default=0),
            "max_trajectory_points": max(trajectories, default=0),
            "max_planning_odom_count": max(planning_odom_counts, default=0),
            "max_planning_z_m": max(planning_z_maxima, default=0.0),
            "accepted_goals": exploration.get("accepted_goals"),
            "path_length_m": exploration.get("path_length_m"),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--stack-log-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    result = validate(args.run_dir, args.stack_log_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 20


if __name__ == "__main__":
    sys.exit(main())
