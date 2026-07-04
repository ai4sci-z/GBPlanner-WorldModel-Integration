"""Command adapter protocol used by executable mission stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from navlab.common.companion.mission.context import MissionContext


@dataclass(slots=True)
class MissionCommandRuntime:
    """Own command retry deadlines and sent-command counters."""

    next_mode_command: float = 0.0
    next_arm_command: float = 0.0
    next_takeoff_command: float = 0.0
    next_setpoint: float = 0.0
    next_land_command: float = 0.0
    next_disarm_command: float = 0.0
    setpoints_sent: int = 0
    sent_counts: dict[str, int] = field(default_factory=dict)

    def due(self, name: str, now_monotonic: float) -> bool:
        """Return whether a command retry deadline has elapsed."""

        return now_monotonic >= float(getattr(self, f"next_{name}"))

    def defer(self, name: str, next_monotonic: float) -> None:
        """Set the next allowed time for a command family."""

        setattr(self, f"next_{name}", next_monotonic)

    def count(self, name: str) -> None:
        """Increment one sent-command counter."""

        self.sent_counts[name] = self.sent_counts.get(name, 0) + 1

    def count_setpoint(self) -> None:
        """Increment setpoint and command counters for local position setpoints."""

        self.setpoints_sent += 1
        self.count("local_position_yaw_setpoint")


def request_mission_command(ctx: MissionContext, method_name: str) -> bool:
    """Call one optional command-adapter method attached to a mission context."""

    adapter = ctx.io.command_adapter
    method = getattr(adapter, method_name, None)
    if not callable(method):
        return False
    return bool(method(ctx))


class MissionCommandAdapter(Protocol):
    """Side-effect adapter for commands requested by pure mission stages."""

    def request_guided_mode(self, ctx: MissionContext) -> bool:
        """Request GUIDED mode and return whether a command was sent."""

        ...

    def request_arm(self, ctx: MissionContext) -> bool:
        """Request vehicle arming and return whether a command was sent."""

        ...

    def request_takeoff(self, ctx: MissionContext) -> bool:
        """Request takeoff and return whether a command was sent."""

        ...

    def send_hold_setpoint(self, ctx: MissionContext) -> bool:
        """Send a hover-hold setpoint and return whether a setpoint was sent."""

        ...

    def send_landing_descent_setpoint(self, ctx: MissionContext) -> bool:
        """Send a guided landing-descent setpoint."""

        ...

    def request_land(self, ctx: MissionContext) -> bool:
        """Request LAND mode or command and return whether a command was sent."""

        ...

    def request_disarm(self, ctx: MissionContext) -> bool:
        """Request disarm and return whether a command was sent."""

        ...
