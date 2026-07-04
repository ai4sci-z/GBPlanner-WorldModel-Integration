from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TASK_RESULT_SCHEMA = "navlab.orchestration.task_result.v1"
TASK_REQUEST_SCHEMA = "navlab.orchestration.task_request.v1"
DOCTOR_RESULT_SCHEMA = "navlab.orchestration.doctor_result.v1"
RUNTIME_TASK_RESULT_SCHEMA = "navlab.runtime.task_result.v1"


class ContractError(ValueError):
    pass


def read_json_contract(path: Path, *, required_fields: tuple[str, ...] = ()) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ContractError(f"contract must be a JSON object: {path}")
    validate_required_fields(payload, required_fields)
    return payload


def write_json_contract(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_required_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ContractError(f"missing contract fields: {', '.join(missing)}")


def normalize_task_result(summary: dict[str, Any], *, summary_path: Path | None = None) -> dict[str, Any]:
    task_id = str(summary.get("taskId") or summary.get("task_id") or summary.get("task") or "")
    if not task_id:
        raise ContractError("task result requires taskId, task_id, or task")

    blockers = [str(blocker) for blocker in summary.get("blockerCodes") or summary.get("blockers") or []]
    ok = bool(summary.get("ok", not blockers))
    artifact_dir = str(summary.get("artifactDir") or summary.get("artifact_dir") or "")
    normalized = {
        "schemaVersion": TASK_RESULT_SCHEMA,
        "taskId": task_id,
        "runId": str(summary.get("runId") or summary.get("run_id") or ""),
        "status": str(summary.get("status") or ("TASK_STATUS_OK" if ok else "TASK_STATUS_BLOCKED")),
        "ok": ok,
        "blocked": bool(summary.get("blocked", not ok)),
        "exitCode": int(summary.get("exitCode") or summary.get("exit_code") or (0 if ok else 20)),
        "artifactDir": artifact_dir,
        "summaryPath": str(summary.get("summaryPath") or summary.get("summary_path") or summary_path or ""),
        "blockers": [_blocker_object(blocker) for blocker in blockers],
        "warnings": list(summary.get("warnings") or []),
        "sourceEvidence": dict(summary.get("sourceEvidence") or summary.get("source_evidence") or {}),
        "mavlinkAcks": list(summary.get("mavlinkAcks") or summary.get("mavlink_acks") or []),
        "metrics": dict(summary.get("metrics") or {}),
        "evidence": dict(summary.get("evidence") or {}),
        "details": dict(summary.get("details") or summary),
    }
    return normalized


def _blocker_object(blocker: str) -> dict[str, str]:
    code = blocker.split(":", 1)[0] or "unknown_blocker"
    return {
        "code": code,
        "message": blocker,
        "source": _blocker_source(code),
    }


def _blocker_source(code: str) -> str:
    if "mavlink" in code or "ack" in code or "guided" in code or "motor_debug" in code:
        return "mavlink"
    if "operator" in code:
        return "operator"
    if "probe" in code:
        return "probe"
    if "rosbag" in code:
        return "rosbag"
    if "runtime" in code:
        return "runtime"
    return "runtime"
