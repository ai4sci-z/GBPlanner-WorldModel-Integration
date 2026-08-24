import json
from pathlib import Path

from validate_m5_run import validate


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def passing_fixture(tmp_path):
    run_dir = tmp_path / "run"
    logs = tmp_path / "logs"
    logs.mkdir()
    write_json(
        run_dir / "summary.json",
        {
            "ok": True,
            "status": "TASK_STATUS_OK",
            "exitCode": 0,
            "run_id": "fixture",
            "metrics": {"gate": {"controller": {"ready": True}, "setpoint": {"ready": True}}},
        },
    )
    write_json(
        run_dir / "probes" / "exploration_probe.json",
        {
            "ok": True,
            "samples": {
                "/navlab/exploration/status": {
                    "parsed": {
                        "strategy": "gbplanner",
                        "ok": True,
                        "traj_count": 2,
                        "accepted_goals": 3,
                        "min_accepted_goals": 3,
                        "blockers": [],
                    }
                },
                "/navlab/landing/status": {
                    "parsed": {
                        "ok": True,
                        "landed_confirmed": True,
                        "motors_safe": True,
                        "return_home": {"ok": True},
                    }
                },
            },
        },
    )
    (logs / "m5_stack_contract.log").write_text(
        "POINTCLOUD_TOPIC=/wm/cloud3d\n"
        "EXTRINSIC=base_link:lidar3d_frame:0,0,0.10\n"
        "ODOMETRY_TOPIC=/gbp/planning_odom\n"
        "ODOMETRY_HEIGHT_SOURCE=/navlab/fcu/local_position_pose:fcu_ekf_z\n"
        "PLANNING_TF=map:base_link:fcu_ekf_height\n"
        "PCI_POLICY=wait_for_enable,stop_after_first_path\n",
        encoding="utf-8",
    )
    (logs / "m5_gbp_node.log").write_text(
        "[MAPPROBE] res=0.20 ready=1\nFormed a graph with [12] vertices and [20] edges\n",
        encoding="utf-8",
    )
    (logs / "m5_pci.log").write_text(
        "published 7 waypoints\n"
        "first non-empty path published; trigger timer stopped\n",
        encoding="utf-8",
    )
    (logs / "m5_tf_relay.log").write_text(
        "forwarded=50 wall_dropped=0 planar_replaced=20 planning_odom=100 "
        "invalid_external_nav=0 height_unavailable=0 planning_z_max=0.453\n",
        encoding="utf-8",
    )
    (logs / "m5_adapter.log").write_text(
        "[INFO] [gbp_traj_to_intent]: INTENT traj#1 wp[1/7]=(0.50,0.10,0.45) "
        "odom=(0.10,0.02) dist=0.41 map_yaw=0.2 fcu_yaw=90.0 yaw_age=0.42 "
        "cmd_body=-13.8 -> v=(0.078,-0.019)\n",
        encoding="utf-8",
    )
    return run_dir, logs


def test_accepts_complete_same_run_evidence(tmp_path):
    run_dir, logs = passing_fixture(tmp_path)
    result = validate(run_dir, logs)
    assert result["ok"] is True
    assert result["failures"] == []


def test_rejects_missing_trajectory(tmp_path):
    run_dir, logs = passing_fixture(tmp_path)
    (logs / "m5_pci.log").write_text("planner returned empty path\n", encoding="utf-8")
    result = validate(run_dir, logs)
    assert result["ok"] is False
    assert "trajectory_published" in result["failures"]


def test_rejects_legacy_2d_cloud_contract(tmp_path):
    run_dir, logs = passing_fixture(tmp_path)
    (logs / "m5_stack_contract.log").write_text(
        "POINTCLOUD_TOPIC=/cloud_in\n"
        "EXTRINSIC=base_link:lidar3d_frame:0,0,0.10\n"
        "ODOMETRY_TOPIC=/gbp/planning_odom\n"
        "ODOMETRY_HEIGHT_SOURCE=/navlab/fcu/local_position_pose:fcu_ekf_z\n"
        "PLANNING_TF=map:base_link:fcu_ekf_height\n"
        "PCI_POLICY=wait_for_enable,stop_after_first_path\n",
        encoding="utf-8",
    )
    result = validate(run_dir, logs)
    assert result["ok"] is False
    assert "cloud3d_contract" in result["failures"]


def test_rejects_planar_odom_or_missing_one_shot_evidence(tmp_path):
    run_dir, logs = passing_fixture(tmp_path)
    contract = (logs / "m5_stack_contract.log").read_text(encoding="utf-8")
    (logs / "m5_stack_contract.log").write_text(
        contract.replace("ODOMETRY_TOPIC=/gbp/planning_odom", "ODOMETRY_TOPIC=/slam/odom"),
        encoding="utf-8",
    )
    (logs / "m5_pci.log").write_text("published 7 waypoints\n", encoding="utf-8")
    result = validate(run_dir, logs)
    assert result["ok"] is False
    assert "planning_odom_contract" in result["failures"]
    assert "pci_one_shot_observed" in result["failures"]


def test_rejects_missing_sensor_height_runtime_evidence(tmp_path):
    run_dir, logs = passing_fixture(tmp_path)
    (logs / "m5_tf_relay.log").write_text(
        "forwarded=50 wall_dropped=0 planar_replaced=20 planning_odom=0 "
        "invalid_external_nav=0 height_unavailable=20 planning_z_max=0.000\n",
        encoding="utf-8",
    )
    result = validate(run_dir, logs)
    assert result["ok"] is False
    assert "planning_odom_ready" in result["failures"]


def test_rejects_legacy_alignment_adapter_log(tmp_path):
    run_dir, logs = passing_fixture(tmp_path)
    (logs / "m5_adapter.log").write_text(
        "INTENT traj#1 wp[1/7]=(0.50,0.10,0.45) odom=(0.10,0.02) dist=0.41 "
        "Rpairs=4 map_ned=123 fcu_yaw=90 yaw_age=0.42 cmd_body=33 det=1 "
        "-> v=(0.067,0.043)\n",
        encoding="utf-8",
    )
    result = validate(run_dir, logs)
    assert result["ok"] is False
    assert "adapter_body_frame_observed" in result["failures"]
    assert result["evidence"]["body_frame_intent_count"] == 0
