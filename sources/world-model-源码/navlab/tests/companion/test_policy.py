from __future__ import annotations

from navlab.common.companion.mission import (
    GateStatus,
    OperatorConfirmationRequirement,
    evaluate_deadline_policy,
    evaluate_operator_confirmations,
    evaluate_target_hard_cap_policy,
    merge_gate_statuses,
    reason_code,
)


def test_reason_code_normalizes_dynamic_text_shape() -> None:
    assert reason_code("Motor Debug: Arm Rejected!") == "motor_debug_arm_rejected"
    assert reason_code("  ") == "unknown_reason"


def test_operator_confirmations_return_stable_blockers() -> None:
    evaluation = evaluate_operator_confirmations(
        [
            OperatorConfirmationRequirement("manual_takeover", required=True, confirmed=True),
            OperatorConfirmationRequirement("kill_switch", required=True, confirmed=False),
            OperatorConfirmationRequirement("safe_area", required=False, confirmed=False),
        ]
    )

    assert evaluation.ok is False
    assert evaluation.blocked is True
    assert evaluation.blockers == ("operator_kill_switch_not_confirmed",)
    assert evaluation.to_dict()["checks"][1]["blocker"] == "operator_kill_switch_not_confirmed"
    assert evaluation.to_dict()["checks"][2]["ok"] is True


def test_deadline_policy_blocks_only_hard_cap_exceeded() -> None:
    before_target = evaluate_deadline_policy(elapsed_sec=3.0, target_sec=5.0, hard_cap_sec=8.0)
    after_target = evaluate_deadline_policy(elapsed_sec=6.0, target_sec=5.0, hard_cap_sec=8.0)
    after_hard_cap = evaluate_deadline_policy(elapsed_sec=9.0, target_sec=5.0, hard_cap_sec=8.0)

    assert before_target.ok is True
    assert before_target.reason_code == "deadline_target_not_met"
    assert after_target.ok is True
    assert after_target.reason_code == "deadline_target_met"
    assert after_hard_cap.ok is False
    assert after_hard_cap.blocked is True
    assert after_hard_cap.reason_code == "deadline_hard_cap_exceeded"


def test_target_hard_cap_policy_validates_internal_consistency() -> None:
    ok = evaluate_target_hard_cap_policy(target=0.10, hard_cap=0.15, name="hover_span")
    bad = evaluate_target_hard_cap_policy(target=0.20, hard_cap=0.15, name="hover_span")

    assert ok.ok is True
    assert ok.reason_code == "hover_span_valid"
    assert bad.ok is False
    assert bad.blockers == ("hover_span_target_exceeds_hard_cap",)


def test_merge_gate_statuses_preserves_blockers_and_warnings() -> None:
    merged = merge_gate_statuses(
        [
            GateStatus(ok=True, warnings=("slow_start",)),
            GateStatus(ok=False, blockers=("missing_scan",)),
        ]
    )

    assert merged.ok is False
    assert merged.blocked is True
    assert merged.blockers == ("missing_scan",)
    assert merged.warnings == ("slow_start",)
