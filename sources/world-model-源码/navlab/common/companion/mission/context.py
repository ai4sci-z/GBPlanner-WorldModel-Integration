"""Shared state containers used by companion mission pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MissionClock:
    """Monotonic mission clock used to compute deterministic elapsed time."""

    started_at_monotonic: float = 0.0
    now_monotonic: float = 0.0

    @property
    def elapsed_sec(self) -> float:
        """Return non-negative seconds since the mission clock started."""

        return max(0.0, self.now_monotonic - self.started_at_monotonic)


@dataclass(slots=True)
class FcuState:
    """Latest flight controller state needed by mission stages."""

    mode: str = ""
    mode_number: int | None = None
    expected_mode_seen: bool = False
    armed: bool = False
    airborne: bool = False
    takeoff_ack_ok: bool = False
    target_system: int | None = None
    target_component: int | None = None


@dataclass(slots=True)
class NavState:
    """Latest navigation readiness and SLAM quality signals."""

    external_nav_ready: bool = False
    mavlink_external_nav_ready: bool = False
    fcu_local_position_ready: bool = False
    imu_ready: bool = False
    slam_quality: str = "unknown"
    slam_quality_good: bool = False
    slam_quality_reason: str = ""
    ready_elapsed_sec: float = 0.0
    slam_quality_loss_duration_sec: float = 0.0
    external_nav_loss_duration_sec: float = 0.0
    mavlink_external_nav_loss_duration_sec: float = 0.0
    fcu_local_position_loss_duration_sec: float = 0.0


@dataclass(slots=True)
class PoseState:
    """Latest local pose, yaw, and height estimates in mission units."""

    x_m: float | None = None
    y_m: float | None = None
    z_ned_m: float | None = None
    yaw_rad: float | None = None
    height_m: float | None = None
    fcu_local_height_m: float | None = None
    external_nav_height_m: float | None = None
    rangefinder_range_m: float | None = None
    rangefinder_relative_height_m: float | None = None
    target_z_ned_m: float | None = None


@dataclass(slots=True)
class CommandState:
    """MAVLink command counters and acknowledgement state."""

    sent_counts: dict[str, int] = field(default_factory=dict)
    accepted_command_ids: set[int] = field(default_factory=set)
    command_acks: list[dict[str, int]] = field(default_factory=list)


@dataclass(slots=True)
class HoverState:
    """Persistent state captured while entering and holding hover."""

    hold_x_m: float | None = None
    hold_y_m: float | None = None
    hold_yaw_rad: float | None = None
    phase_counts: dict[str, int] = field(default_factory=dict)
    started_at_monotonic: float | None = None
    airborne_elapsed_sec: float = 0.0
    hover_elapsed_sec: float = 0.0
    health_started_at_monotonic: float | None = None
    health_green_since_monotonic: float | None = None
    health_phase: str = "not_started"
    health_band: str = "yellow"
    health_reason: str = "hover_health_not_started"
    health_observed_sec: float = 0.0
    health_stable_sec: float = 0.0
    operator_confirm_allowed: bool = False
    operator_confirm_received: bool = False
    operator_confirm_started_at_monotonic: float | None = None
    body_ok: bool = False
    body_reason: str = ""


@dataclass(slots=True)
class LandingState:
    """Persistent state captured while executing the landing phase."""

    policy: str = "land_in_place"
    state: str = "not_started"
    started_at_monotonic: float | None = None
    elapsed_sec: float = 0.0
    blockers: list[str] = field(default_factory=list)
    land_command_sent: bool = False
    land_command_accepted: bool = False
    land_command_rejected: bool = False
    land_mode_seen: bool = False
    command_due: bool = False
    touchdown_confirmed: bool = False
    touchdown_ready: bool = False
    touchdown_confirmed_elapsed_sec: float | None = None
    descent_profile_ok: bool = False
    disarmed: bool = False
    disarmed_confirmed: bool = False
    motors_safe: bool = True
    disarm_due: bool = False


@dataclass(slots=True)
class MissionState:
    """Mutable state shared by all stages in a mission run."""

    active_stage: str = ""
    active_stage_index: int = 0
    completed_stages: list[str] = field(default_factory=list)
    phase_counts: dict[str, int] = field(default_factory=dict)
    aborted: bool = False
    terminal: bool = False
    fcu: FcuState = field(default_factory=FcuState)
    nav: NavState = field(default_factory=NavState)
    pose: PoseState = field(default_factory=PoseState)
    command: CommandState = field(default_factory=CommandState)
    hover: HoverState = field(default_factory=HoverState)
    landing: LandingState = field(default_factory=LandingState)


@dataclass(slots=True)
class MissionEvidence:
    """Rolling evidence store for stage results and diagnostics."""

    latest: dict[str, Any] = field(default_factory=dict)
    stage_results: list[dict[str, Any]] = field(default_factory=list)

    def remember_stage_result(
        self,
        *,
        stage: str,
        status: str,
        reason: str,
        fsm_state: str | None = None,
        blocker: str | None = None,
        evidence: dict[str, object] | None = None,
    ) -> None:
        """Record the latest result for one stage and retain recent history."""

        record = {
            "stage": stage,
            "status": status,
            "reason": reason,
            "fsm_state": fsm_state,
            "blocker": blocker,
            "evidence": dict(evidence or {}),
        }
        self.latest[stage] = record
        self.stage_results.append(record)
        self.stage_results = self.stage_results[-200:]


@dataclass(slots=True)
class MissionIO:
    """External adapters attached to a mission context."""

    command_adapter: object | None = None
    logger: object | None = None


@dataclass(slots=True)
class MissionContext:
    """Single object passed through mission stages and pipelines."""

    config: object | None = None
    clock: MissionClock = field(default_factory=MissionClock)
    state: MissionState = field(default_factory=MissionState)
    evidence: MissionEvidence = field(default_factory=MissionEvidence)
    fsm: object | None = None
    io: MissionIO = field(default_factory=MissionIO)


@dataclass(frozen=True, slots=True)
class MissionRuntimeSnapshot:
    """Typed runtime inputs used to refresh a mission context for one tick."""

    now_monotonic: float
    nav: NavState
    fcu: FcuState
    pose: PoseState
    hover: HoverState
    command: CommandState


@dataclass(frozen=True, slots=True)
class LandingRuntimeSnapshot:
    """Typed landing-state inputs used to refresh a mission context for one tick."""

    now_monotonic: float
    landing: LandingState


def apply_runtime_snapshot_to_context(ctx: MissionContext, snapshot: MissionRuntimeSnapshot) -> None:
    """Refresh mutable mission context state from one typed runtime snapshot."""

    ctx.clock.now_monotonic = snapshot.now_monotonic
    ctx.state.nav = snapshot.nav
    ctx.state.fcu = snapshot.fcu
    ctx.state.pose = snapshot.pose
    ctx.state.hover.airborne_elapsed_sec = snapshot.hover.airborne_elapsed_sec
    ctx.state.hover.hover_elapsed_sec = snapshot.hover.hover_elapsed_sec
    ctx.state.command = snapshot.command


def apply_landing_runtime_snapshot_to_context(ctx: MissionContext, snapshot: LandingRuntimeSnapshot) -> None:
    """Refresh mutable mission context landing state from one typed runtime snapshot."""

    ctx.clock.now_monotonic = snapshot.now_monotonic
    ctx.state.landing = snapshot.landing
