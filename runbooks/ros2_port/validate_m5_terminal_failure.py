#!/usr/bin/env python3
"""Validate a controlled M5 terminal failure and its safe landing suffix."""

import argparse
import json
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


def load_last_json_line(path, failures, label):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        failures.append(f"{label}_unreadable:{exc}")
        return {}
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    failures.append(f"{label}_json_missing")
    return {}


def validate(run_dir, stack_log_dir):
    failures = []
    summary = load_json(run_dir / "summary.json", failures, "summary")
    probe = load_json(
        run_dir / "probes" / "exploration_probe.json", failures, "exploration_probe"
    )
    injection = load_last_json_line(
        stack_log_dir / "m5_terminal_injector.log", failures, "terminal_injector"
    )
    samples = probe.get("samples") if isinstance(probe.get("samples"), dict) else {}
    exploration = nested(samples, "/navlab/exploration/status", "parsed") or {}
    landing = nested(samples, "/navlab/landing/status", "parsed") or {}

    checks = {
        "task_verdict_remains_failed": (
            summary.get("ok") is False
            and summary.get("status") not in (None, "TASK_STATUS_OK")
            and summary.get("exitCode") not in (None, 0)
        ),
        "controller_ready": nested(summary, "metrics", "gate", "controller", "ready") is True,
        "injection_published": injection.get("published") is True,
        "injection_after_controller_ready": injection.get("controller_ready_seen") is True,
        "adapter_strategy": exploration.get("strategy") == "gbplanner",
        "adapter_terminal": exploration.get("terminal") is True,
        "adapter_claim_failed": exploration.get("claim") == "failed",
        "adapter_not_ok": exploration.get("ok") is False,
        "adapter_killed_blocker": "killed" in (exploration.get("blockers") or []),
        "landing_ok": landing.get("ok") is True,
        "landing_task_terminal": landing.get("task_terminal") is True,
        "landing_task_not_completed": landing.get("task_completed") is False,
        "landing_preserves_failure": "killed" in (landing.get("task_failure_blockers") or []),
        "return_home_ok": nested(landing, "return_home", "ok") is True,
        "land_command_sent": landing.get("land_command_sent") is True,
        "land_mode_seen": landing.get("land_mode_seen") is True,
        "touchdown_confirmed": landing.get("touchdown_confirmed") is True,
        "disarmed": landing.get("disarmed") is True,
        "motors_safe": landing.get("motors_safe") is True,
    }
    failures.extend(name for name, ok in checks.items() if not ok)
    return {
        "schemaVersion": "gbplanner.m5.terminal_failure_acceptance.v1",
        "ok": not failures,
        "run_id": summary.get("run_id"),
        "checks": checks,
        "failures": failures,
        "evidence": {
            "task_status": summary.get("status"),
            "task_exit_code": summary.get("exitCode"),
            "exploration_blockers": exploration.get("blockers"),
            "landing_state": landing.get("state"),
            "return_home_distance_m": nested(landing, "return_home", "distance_to_home_m"),
            "descent_profile": landing.get("descent_profile"),
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
