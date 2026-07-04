"""Pure MAVLink protocol helpers shared by companion mission runtimes."""

from __future__ import annotations

from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mavlink

ARDUCOPTER_LAND_MODE_NUMBER = 9


def mode_number(mode_name: str) -> int:
    """Return the ArduCopter numeric mode id for a mode name."""

    requested = mode_name.upper()
    for number, name in mavutil.mode_mapping_acm.items():
        if name == requested:
            return int(number)
    supported = ", ".join(sorted(mavutil.mode_mapping_acm.values()))
    raise ValueError(f"unsupported ArduCopter mode {mode_name!r}; supported: {supported}")


def mavlink_param_id_to_str(value: object) -> str:
    """Normalize a MAVLink param_id field to a Python string."""

    if isinstance(value, bytes):
        return value.split(b"\x00", 1)[0].decode("ascii", errors="ignore")
    return str(value).rstrip("\x00")


def command_ack_success(command_acks: list[dict[str, int]], command_id: int) -> bool:
    """Return whether recent ACKs contain a successful result for a command."""

    return any(ack.get("command") == command_id and ack.get("result") == 0 for ack in command_acks)


def command_ack_accepted(
    command_acks: list[dict[str, int]],
    command_id: int,
    accepted_command_ids: set[int] | None = None,
) -> bool:
    """Return whether a command is accepted by ACK or persistent override."""

    return command_id in (accepted_command_ids or set()) or command_ack_success(command_acks, command_id)


def command_ack_rejected(command_acks: list[dict[str, int]], command_id: int) -> bool:
    """Return whether recent ACKs contain a non-success result for a command."""

    return any(ack.get("command") == command_id and ack.get("result") not in (0, None) for ack in command_acks)


def append_bounded_command_ack(
    command_acks: list[dict[str, int]],
    ack: dict[str, int],
    *,
    max_count: int = 240,
) -> None:
    """Append one command ACK and trim the list to the configured bound."""

    command_acks.append(ack)
    del command_acks[: max(0, len(command_acks) - max_count)]


__all__ = [
    "ARDUCOPTER_LAND_MODE_NUMBER",
    "append_bounded_command_ack",
    "command_ack_accepted",
    "command_ack_rejected",
    "command_ack_success",
    "mavlink",
    "mavlink_param_id_to_str",
    "mode_number",
]
