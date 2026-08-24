import json
from pathlib import Path

from validate_m5_terminal_failure import validate


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def fixture(tmp_path):
    run_dir = tmp_path / "run"
    logs = tmp_path / "logs"
    logs.mkdir()
    write_json(
        run_dir / "summary.json",
        {
            "ok": False,
            "status": "TASK_STATUS_ERROR",
            "exitCode": 1,
            "run_id": "terminal-fixture",
            "metrics": {"gate": {"controller": {"ready": True}}},
        },
    )
    write_json(
        run_dir / "probes" / "exploration_probe.json",
        {
            "ok": False,
            "samples": {
                "/navlab/exploration/status": {
                    "parsed": {
                        "strategy": "gbplanner",
                        "ok": False,
                        "terminal": True,
                        "claim": "failed",
                        "blockers": ["killed"],
                    }
                },
                "/navlab/landing/status": {
                    "parsed": {
                        "ok": True,
                        "state": "landing_complete",
                        "task_terminal": True,
                        "task_completed": False,
                        "task_failure_blockers": ["killed"],
                        "return_home": {"ok": True, "distance_to_home_m": 0.1},
                        "land_command_sent": True,
                        "land_mode_seen": True,
                        "touchdown_confirmed": True,
                        "disarmed": True,
                        "motors_safe": True,
                    }
                },
            },
        },
    )
    (logs / "m5_terminal_injector.log").write_text(
        json.dumps({"published": True, "controller_ready_seen": True, "reason": "killed"}) + "\n",
        encoding="utf-8",
    )
    return run_dir, logs


def test_accepts_failed_task_with_complete_safe_landing(tmp_path):
    run_dir, logs = fixture(tmp_path)
    result = validate(run_dir, logs)
    assert result["ok"] is True


def test_rejects_task_verdict_rewritten_to_success(tmp_path):
    run_dir, logs = fixture(tmp_path)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    summary.update({"ok": True, "status": "TASK_STATUS_OK", "exitCode": 0})
    write_json(run_dir / "summary.json", summary)
    result = validate(run_dir, logs)
    assert result["ok"] is False
    assert "task_verdict_remains_failed" in result["failures"]


def test_rejects_missing_touchdown_or_disarm(tmp_path):
    run_dir, logs = fixture(tmp_path)
    probe_path = run_dir / "probes" / "exploration_probe.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    landing = probe["samples"]["/navlab/landing/status"]["parsed"]
    landing["touchdown_confirmed"] = False
    landing["disarmed"] = False
    write_json(probe_path, probe)
    result = validate(run_dir, logs)
    assert result["ok"] is False
    assert "touchdown_confirmed" in result["failures"]
    assert "disarmed" in result["failures"]
