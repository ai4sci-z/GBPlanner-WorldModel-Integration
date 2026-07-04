"""Pure mission policy helpers for task doctors and gates."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


def reason_code(value: str) -> str:
    """Normalize a human label into a stable lowercase snake_case reason code."""

    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unknown_reason"


@dataclass(frozen=True, slots=True)
class GateStatus:
    """Small common ok/blocked/warnings/blockers status shape."""

    ok: bool
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def blocked(self) -> bool:
        """Whether this gate blocks task progress."""

        return not self.ok or bool(self.blockers)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable gate status payload."""

        return {
            "ok": self.ok,
            "blocked": self.blocked,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class OperatorConfirmationRequirement:
    """One operator confirmation requirement and its observed value."""

    name: str
    required: bool
    confirmed: bool
    blocker: str | None = None

    def blocker_code(self) -> str:
        """Return the stable blocker code for this missing confirmation."""

        return self.blocker or f"operator_{reason_code(self.name)}_not_confirmed"


@dataclass(frozen=True, slots=True)
class OperatorConfirmationEvaluation:
    """Aggregate operator confirmation result."""

    ok: bool
    blocked: bool
    blockers: tuple[str, ...]
    checks: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable evaluation payload."""

        return {
            "ok": self.ok,
            "blocked": self.blocked,
            "blockers": list(self.blockers),
            "checks": list(self.checks),
        }


def evaluate_operator_confirmations(
    requirements: Iterable[OperatorConfirmationRequirement],
) -> OperatorConfirmationEvaluation:
    """Evaluate required operator confirmations without performing any IO."""

    blockers: list[str] = []
    checks: list[dict[str, object]] = []
    for requirement in requirements:
        missing = requirement.required and not requirement.confirmed
        blocker = requirement.blocker_code() if missing else None
        if blocker is not None:
            blockers.append(blocker)
        checks.append(
            {
                "name": requirement.name,
                "required": requirement.required,
                "confirmed": requirement.confirmed,
                "ok": not missing,
                "blocker": blocker,
            }
        )
    return OperatorConfirmationEvaluation(
        ok=not blockers,
        blocked=bool(blockers),
        blockers=tuple(blockers),
        checks=tuple(checks),
    )


@dataclass(frozen=True, slots=True)
class DeadlineEvaluation:
    """Evaluation for target duration and hard-cap deadline policies."""

    ok: bool
    blocked: bool
    elapsed_sec: float
    target_sec: float
    hard_cap_sec: float
    target_met: bool
    hard_cap_exceeded: bool
    reason_code: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable deadline evaluation payload."""

        return {
            "ok": self.ok,
            "blocked": self.blocked,
            "elapsed_sec": self.elapsed_sec,
            "target_sec": self.target_sec,
            "hard_cap_sec": self.hard_cap_sec,
            "target_met": self.target_met,
            "hard_cap_exceeded": self.hard_cap_exceeded,
            "reason_code": self.reason_code,
        }


def evaluate_deadline_policy(
    *,
    elapsed_sec: float,
    target_sec: float,
    hard_cap_sec: float,
) -> DeadlineEvaluation:
    """Evaluate elapsed time against a target and fail-closed hard cap."""

    target_met = elapsed_sec >= target_sec
    hard_cap_exceeded = elapsed_sec > hard_cap_sec
    if hard_cap_exceeded:
        code = "deadline_hard_cap_exceeded"
    elif target_met:
        code = "deadline_target_met"
    else:
        code = "deadline_target_not_met"
    return DeadlineEvaluation(
        ok=not hard_cap_exceeded,
        blocked=hard_cap_exceeded,
        elapsed_sec=elapsed_sec,
        target_sec=target_sec,
        hard_cap_sec=hard_cap_sec,
        target_met=target_met,
        hard_cap_exceeded=hard_cap_exceeded,
        reason_code=code,
    )


@dataclass(frozen=True, slots=True)
class TargetHardCapEvaluation:
    """Validation for target/hard-cap numeric policy pairs."""

    ok: bool
    blocked: bool
    target: float
    hard_cap: float
    reason_code: str
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable target/hard-cap payload."""

        return {
            "ok": self.ok,
            "blocked": self.blocked,
            "target": self.target,
            "hard_cap": self.hard_cap,
            "reason_code": self.reason_code,
            "blockers": list(self.blockers),
        }


def evaluate_target_hard_cap_policy(*, target: float, hard_cap: float, name: str) -> TargetHardCapEvaluation:
    """Validate that a target/hard-cap pair is positive and internally consistent."""

    code_prefix = reason_code(name)
    blockers: list[str] = []
    if target <= 0:
        blockers.append(f"{code_prefix}_target_not_positive")
    if hard_cap <= 0:
        blockers.append(f"{code_prefix}_hard_cap_not_positive")
    if target > hard_cap:
        blockers.append(f"{code_prefix}_target_exceeds_hard_cap")
    return TargetHardCapEvaluation(
        ok=not blockers,
        blocked=bool(blockers),
        target=target,
        hard_cap=hard_cap,
        reason_code=f"{code_prefix}_valid" if not blockers else blockers[0],
        blockers=tuple(blockers),
    )


def merge_gate_statuses(statuses: Sequence[GateStatus]) -> GateStatus:
    """Merge several gate statuses without hiding individual blocker codes."""

    blockers: list[str] = []
    warnings: list[str] = []
    ok = True
    for status in statuses:
        ok = ok and status.ok and not status.blocked
        blockers.extend(status.blockers)
        warnings.extend(status.warnings)
    return GateStatus(ok=ok and not blockers, blockers=tuple(blockers), warnings=tuple(warnings))
