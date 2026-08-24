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
        "POINTCLOUD_TOPIC=/wm/cloud3d\nEXTRINSIC=base_link:lidar3d_frame:0,0,0.10\n",
        encoding="utf-8",
    )
    (logs / "m5_gbp_node.log").write_text(
        "[MAPPROBE] res=0.20 ready=1\nFormed a graph with [12] vertices and [20] edges\n",
        encoding="utf-8",
    )
    (logs / "m5_pci.log").write_text("published 7 waypoints\n", encoding="utf-8")
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
        "POINTCLOUD_TOPIC=/cloud_in\nEXTRINSIC=base_link:lidar3d_frame:0,0,0.10\n",
        encoding="utf-8",
    )
    result = validate(run_dir, logs)
    assert result["ok"] is False
    assert "cloud3d_contract" in result["failures"]
