"""Mission FSM naming and timeline recording helpers."""

from __future__ import annotations

from dataclasses import dataclass

HOVER_PHASE_TO_MISSION_PHASE_STATE = {
    "wait_ready": "S1 wait_nav_ready",
    "guided": "S2 set_guided",
    "arm": "S3 arm",
    "takeoff": "S4 takeoff",
    "hover_settle": "S5 hover_settle",
    "hover_hold": "S6 hover_hold",
    "complete": "S7 pre_land_hold",
    "abort": "S_abort",
}

LANDING_STATE_TO_MISSION_PHASE_STATE = {
    "not_started": "S7 pre_land_hold",
    "task_body_complete": "S7 pre_land_hold",
    "pre_land_hold": "S7 pre_land_hold",
    "guided_descent": "legacy_guided_descent_diagnostic",
    "land_command_sent": "S8 command_land",
    "descent_monitoring": "S9 land_mode_monitor",
    "touchdown_candidate": "S10 touchdown_monitor",
    "disarm_requested": "S11 disarm_monitor",
    "landing_complete": "S12 landing_complete",
}


def mission_phase_state_for_hover_phase(phase: str) -> str:
    """Map a hover phase name to the public mission FSM state name."""

    return HOVER_PHASE_TO_MISSION_PHASE_STATE.get(phase, "S_abort")


def mission_phase_state_for_landing_state(landing_state: str) -> str:
    """Map a landing phase name to the public mission FSM state name."""

    return LANDING_STATE_TO_MISSION_PHASE_STATE.get(landing_state, "S_abort")


@dataclass(frozen=True, slots=True)
class MissionPhaseHistoryEntry:
    """One completed or current interval in the mission FSM timeline."""

    state: str
    entered_at_sec: float
    exited_at_sec: float | None
    duration_sec: float
    reason: str
    guard: str | None = None
    blocker: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of this timeline entry."""

        return {
            "state": self.state,
            "entered_at_sec": self.entered_at_sec,
            "exited_at_sec": self.exited_at_sec,
            "duration_sec": self.duration_sec,
            "reason": self.reason,
            "guard": self.guard,
            "blocker": self.blocker,
        }


@dataclass(frozen=True, slots=True)
class MissionPhaseSnapshot:
    """Point-in-time mission FSM state plus bounded transition history."""

    state: str
    state_entered_at_sec: float
    last_transition_reason: str
    blocker: str | None
    history: tuple[MissionPhaseHistoryEntry, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable snapshot for status and summary output."""

        return {
            "state": self.state,
            "state_entered_at_sec": self.state_entered_at_sec,
            "last_transition_reason": self.last_transition_reason,
            "blocker": self.blocker,
            "history": [entry.to_dict() for entry in self.history],
        }


class MissionPhaseRecorder:
    """Record mission FSM transitions against a monotonic start time."""

    def __init__(
        self,
        *,
        started_at_monotonic: float,
        initial_state: str = "S0 wait_runtime",
        reason: str = "controller_started",
    ) -> None:
        """Initialize the recorder at a monotonic mission start time."""

        self._started_at_monotonic = started_at_monotonic
        self._state = initial_state
        self._entered_at_sec = 0.0
        self._reason = reason
        self._guard: str | None = None
        self._blocker: str | None = None
        self._history: list[MissionPhaseHistoryEntry] = []

    @property
    def state(self) -> str:
        """Current public FSM state name."""

        return self._state

    @property
    def entered_at_sec(self) -> float:
        """Elapsed mission seconds at which the current state was entered."""

        return self._entered_at_sec

    @property
    def last_transition_reason(self) -> str:
        """Reason associated with the most recent transition or update."""

        return self._reason

    @property
    def blocker(self) -> str | None:
        """Current blocker reason when the FSM is blocked or aborted."""

        return self._blocker

    def transition(
        self,
        *,
        now_monotonic: float,
        state: str,
        reason: str,
        guard: str | None = None,
        blocker: str | None = None,
    ) -> None:
        """Move to a new FSM state or update metadata for the current state."""

        now_sec = max(0.0, now_monotonic - self._started_at_monotonic)
        if state == self._state:
            self._reason = reason
            self._guard = guard
            self._blocker = blocker
            return
        self._history.append(
            MissionPhaseHistoryEntry(
                state=self._state,
                entered_at_sec=self._entered_at_sec,
                exited_at_sec=now_sec,
                duration_sec=max(0.0, now_sec - self._entered_at_sec),
                reason=self._reason,
                guard=self._guard,
                blocker=self._blocker,
            )
        )
        self._history = self._history[-80:]
        self._state = state
        self._entered_at_sec = now_sec
        self._reason = reason
        self._guard = guard
        self._blocker = blocker

    def snapshot(self, *, now_monotonic: float) -> MissionPhaseSnapshot:
        """Build an immutable point-in-time FSM snapshot."""

        now_sec = max(0.0, now_monotonic - self._started_at_monotonic)
        current = MissionPhaseHistoryEntry(
            state=self._state,
            entered_at_sec=self._entered_at_sec,
            exited_at_sec=None,
            duration_sec=max(0.0, now_sec - self._entered_at_sec),
            reason=self._reason,
            guard=self._guard,
            blocker=self._blocker,
        )
        return MissionPhaseSnapshot(
            state=self._state,
            state_entered_at_sec=self._entered_at_sec,
            last_transition_reason=self._reason,
            blocker=self._blocker,
            history=(*self._history, current),
        )
