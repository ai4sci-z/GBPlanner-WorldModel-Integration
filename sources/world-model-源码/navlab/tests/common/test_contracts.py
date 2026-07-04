from __future__ import annotations

import json
from pathlib import Path

import pytest

from navlab.common.contracts import (
    TASK_RESULT_SCHEMA,
    ContractError,
    normalize_task_result,
    read_json_contract,
    write_json_contract,
)

ROOT = Path(__file__).resolve().parents[3]


def test_read_task_result_golden_contract() -> None:
    payload = read_json_contract(
        ROOT / "contracts/examples/orchestration/real_task_result.json",
        required_fields=("schemaVersion", "taskId", "ok", "blockers"),
    )

    assert payload["schemaVersion"] == TASK_RESULT_SCHEMA
    assert payload["taskId"] == "motor-debug"
    assert payload["blockers"][0]["code"] == "MAVLINK_ACK_REJECTED"


def test_normalize_legacy_runtime_summary_to_task_result(tmp_path: Path) -> None:
    summary = {
        "schema_version": "navlab.runtime.task_result.v1",
        "task": "motor-debug",
        "ok": False,
        "blocked": True,
        "blockers": ["motor_debug_arm_rejected:MAV_RESULT_FAILED"],
        "runtime_report": {"heartbeat_observed": True},
    }

    normalized = normalize_task_result(summary, summary_path=tmp_path / "summary.json")
    out = tmp_path / "task_result.json"
    write_json_contract(out, normalized)
    reloaded = json.loads(out.read_text(encoding="utf-8"))

    assert reloaded["schemaVersion"] == TASK_RESULT_SCHEMA
    assert reloaded["taskId"] == "motor-debug"
    assert reloaded["blockers"][0]["source"] == "mavlink"
    assert reloaded["details"]["runtime_report"]["heartbeat_observed"] is True


def test_contract_reader_rejects_missing_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ContractError):
        read_json_contract(path, required_fields=("schemaVersion",))
