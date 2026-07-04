"""Typed MAVLink command helpers used by companion mission controllers."""

from __future__ import annotations

import math
import time
from typing import Protocol

from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mavlink

LOCAL_POSITION_YAW_TYPE_MASK = 2552
DEFAULT_ORIGIN_LAT_DEG = -35.363262
DEFAULT_ORIGIN_LON_DEG = 149.165237
DEFAULT_ORIGIN_ALT_M = 584.0


class MavlinkSender(Protocol):
    """Subset of pymavlink sender methods used by this package."""

    def set_mode_send(self, *args: object) -> None:
        """Send SET_MODE through the underlying MAVLink connection."""

        ...

    def command_long_send(self, *args: object) -> None:
        """Send COMMAND_LONG through the underlying MAVLink connection."""

        ...

    def heartbeat_send(self, *args: object) -> None:
        """Send HEARTBEAT through the underlying MAVLink connection."""

        ...

    def param_set_send(self, *args: object) -> None:
        """Send PARAM_SET through the underlying MAVLink connection."""

        ...

    def set_gps_global_origin_send(self, *args: object) -> None:
        """Send SET_GPS_GLOBAL_ORIGIN through the underlying MAVLink connection."""

        ...

    def param_request_read_send(self, *args: object) -> None:
        """Send PARAM_REQUEST_READ through the underlying MAVLink connection."""

        ...

    def set_position_target_local_ned_send(self, *args: object) -> None:
        """Send SET_POSITION_TARGET_LOCAL_NED through the underlying MAVLink connection."""

        ...


class MavlinkConnection(Protocol):
    """Subset of a pymavlink connection required by mission commands."""

    mav: MavlinkSender


def mode_number(mode_name: str) -> int:
    """Return the ArduCopter numeric mode id for a mode name."""

    requested = mode_name.upper()
    for number, name in mavutil.mode_mapping_acm.items():
        if name == requested:
            return int(number)
    supported = ", ".join(sorted(mavutil.mode_mapping_acm.values()))
    raise ValueError(f"unsupported ArduCopter mode {mode_name!r}; supported: {supported}")


def set_mode(connection: MavlinkConnection, target_system: int, mode_number: int) -> None:
    """Request an ArduCopter custom mode using SET_MODE and DO_SET_MODE."""

    connection.mav.set_mode_send(target_system, mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_number)
    connection.mav.command_long_send(
        target_system,
        mavlink.MAV_COMP_ID_AUTOPILOT1,
        mavlink.MAV_CMD_DO_SET_MODE,
        0,
        mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_number,
        0,
        0,
        0,
        0,
        0,
    )


def send_gcs_heartbeat(connection: MavlinkConnection) -> None:
    """Send a GCS heartbeat so the autopilot sees an active peer."""

    connection.mav.heartbeat_send(
        mavlink.MAV_TYPE_GCS,
        mavlink.MAV_AUTOPILOT_INVALID,
        0,
        0,
        mavlink.MAV_STATE_ACTIVE,
    )


def set_arming_check(connection: MavlinkConnection, target_system: int, target_component: int, value: int) -> None:
    """Set the ARMING_CHECK parameter to the given integer value."""

    connection.mav.param_set_send(
        target_system,
        target_component,
        b"ARMING_CHECK",
        float(value),
        mavlink.MAV_PARAM_TYPE_INT32,
    )


def set_ekf_origin(
    connection: MavlinkConnection,
    target_system: int,
    lat_deg: float,
    lon_deg: float,
    alt_m: float,
) -> None:
    """Set the EKF global origin from latitude, longitude, and altitude."""

    connection.mav.set_gps_global_origin_send(
        target_system,
        int(lat_deg * 1e7),
        int(lon_deg * 1e7),
        int(alt_m * 1000.0),
        int(time.monotonic() * 1_000_000),
    )


def set_home_position(
    connection: MavlinkConnection,
    target_system: int,
    target_component: int,
    lat_deg: float,
    lon_deg: float,
    alt_m: float,
) -> None:
    """Set the autopilot home position via MAV_CMD_DO_SET_HOME."""

    connection.mav.command_long_send(
        target_system,
        target_component,
        mavlink.MAV_CMD_DO_SET_HOME,
        0,
        0,
        0,
        0,
        0,
        lat_deg,
        lon_deg,
        alt_m,
    )


def command_arm(connection: MavlinkConnection, target_system: int, target_component: int, force_arm: bool) -> None:
    """Send MAV_CMD_COMPONENT_ARM_DISARM with the arm flag set."""

    connection.mav.command_long_send(
        target_system,
        target_component,
        mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        1,
        21196 if force_arm else 0,
        0,
        0,
        0,
        0,
        0,
    )


def command_disarm(
    connection: MavlinkConnection,
    target_system: int,
    target_component: int,
    *,
    force: bool = False,
) -> None:
    """Send MAV_CMD_COMPONENT_ARM_DISARM with the arm flag cleared."""

    force_magic = 21196 if force else 0
    connection.mav.command_long_send(
        target_system,
        target_component,
        mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        0,
        force_magic,
        0,
        0,
        0,
        0,
        0,
    )


def command_takeoff(
    connection: MavlinkConnection,
    target_system: int,
    target_component: int,
    altitude_m: float,
) -> None:
    """Send MAV_CMD_NAV_TAKEOFF for the requested relative altitude."""

    connection.mav.command_long_send(
        target_system,
        target_component,
        mavlink.MAV_CMD_NAV_TAKEOFF,
        0,
        0,
        0,
        0,
        math.nan,
        0,
        0,
        altitude_m,
    )


def command_land(connection: MavlinkConnection, target_system: int, target_component: int) -> None:
    """Send MAV_CMD_NAV_LAND in the current position."""

    connection.mav.command_long_send(
        target_system,
        target_component,
        mavlink.MAV_CMD_NAV_LAND,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )


def request_param_read(connection: MavlinkConnection, target_system: int, target_component: int, name: str) -> None:
    """Request one named parameter from the autopilot."""

    connection.mav.param_request_read_send(
        target_system,
        target_component,
        name.encode("ascii"),
        -1,
    )


def send_local_position_yaw_setpoint(
    connection: MavlinkConnection,
    target_system: int,
    target_component: int,
    x_ned_m: float,
    y_ned_m: float,
    z_ned_m: float,
    yaw_rad: float,
) -> None:
    """Send a local-NED position target with yaw and zero velocity terms."""

    connection.mav.set_position_target_local_ned_send(
        int(time.monotonic() * 1000),
        target_system,
        target_component,
        mavlink.MAV_FRAME_LOCAL_NED,
        LOCAL_POSITION_YAW_TYPE_MASK,
        x_ned_m,
        y_ned_m,
        z_ned_m,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        yaw_rad,
        0.0,
    )


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
