"""Compatibility API for sim companion missions.

Common mission core lives in :mod:`navlab.common.companion.mission`. This
package keeps the existing sim import path and adds the concrete SITL MAVLink
sender helpers that are not part of the common functional core.
"""

from __future__ import annotations

from navlab.common.companion import mission as _common_mission
from navlab.common.companion.mission import *  # noqa: F401,F403
from navlab.sim.companion.mission.mavlink_commands import (
    DEFAULT_ORIGIN_ALT_M,
    DEFAULT_ORIGIN_LAT_DEG,
    DEFAULT_ORIGIN_LON_DEG,
    LOCAL_POSITION_YAW_TYPE_MASK,
    MavlinkConnection,
    MavlinkSender,
    command_arm,
    command_disarm,
    command_land,
    command_takeoff,
    request_param_read,
    send_gcs_heartbeat,
    send_local_position_yaw_setpoint,
    set_arming_check,
    set_ekf_origin,
    set_home_position,
    set_mode,
)

_SIM_MAVLINK_EXPORTS = [
    "DEFAULT_ORIGIN_ALT_M",
    "DEFAULT_ORIGIN_LAT_DEG",
    "DEFAULT_ORIGIN_LON_DEG",
    "LOCAL_POSITION_YAW_TYPE_MASK",
    "MavlinkConnection",
    "MavlinkSender",
    "command_arm",
    "command_disarm",
    "command_land",
    "command_takeoff",
    "request_param_read",
    "send_gcs_heartbeat",
    "send_local_position_yaw_setpoint",
    "set_arming_check",
    "set_ekf_origin",
    "set_home_position",
    "set_mode",
]

__all__ = sorted(set(_common_mission.__all__) | set(_SIM_MAVLINK_EXPORTS))
