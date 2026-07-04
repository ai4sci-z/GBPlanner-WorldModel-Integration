from __future__ import annotations

from navlab.sim.companion.mission.mavlink_commands import (
    append_bounded_command_ack,
    command_ack_accepted,
    command_ack_rejected,
    command_ack_success,
    command_disarm,
    command_land,
    mavlink,
    mavlink_param_id_to_str,
    request_param_read,
)


class _FakeMav:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def command_long_send(self, *args: object) -> None:
        self.calls.append(("command_long_send", args))

    def param_request_read_send(self, *args: object) -> None:
        self.calls.append(("param_request_read_send", args))


class _FakeConnection:
    def __init__(self) -> None:
        self.mav = _FakeMav()


def test_command_land_and_disarm_send_expected_mavlink_commands() -> None:
    land = _FakeConnection()
    command_land(land, 1, 1)
    assert land.mav.calls[0][1][2] == mavlink.MAV_CMD_NAV_LAND

    disarm = _FakeConnection()
    command_disarm(disarm, 1, 1, force=True)
    assert disarm.mav.calls[0][1][2] == mavlink.MAV_CMD_COMPONENT_ARM_DISARM
    assert disarm.mav.calls[0][1][5] == 21196


def test_param_read_and_param_id_helpers() -> None:
    conn = _FakeConnection()
    request_param_read(conn, 1, 1, "LAND_SPD_MS")

    assert conn.mav.calls[0][0] == "param_request_read_send"
    assert conn.mav.calls[0][1][2] == b"LAND_SPD_MS"
    assert conn.mav.calls[0][1][3] == -1
    assert mavlink_param_id_to_str(b"LAND_SPD_MS\x00\x00") == "LAND_SPD_MS"
    assert mavlink_param_id_to_str("LAND_ALT_LOW_M\x00") == "LAND_ALT_LOW_M"


def test_command_ack_helpers_track_recent_and_persistent_acceptance() -> None:
    acks: list[dict[str, int]] = []
    for _ in range(5):
        append_bounded_command_ack(acks, {"command": mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, "result": 0}, max_count=4)
    append_bounded_command_ack(acks, {"command": mavlink.MAV_CMD_NAV_TAKEOFF, "result": 0}, max_count=4)

    assert command_ack_success(acks, mavlink.MAV_CMD_NAV_TAKEOFF)
    assert command_ack_accepted(acks, mavlink.MAV_CMD_NAV_TAKEOFF)
    assert not command_ack_rejected(acks, mavlink.MAV_CMD_NAV_TAKEOFF)
    assert command_ack_accepted([], mavlink.MAV_CMD_NAV_TAKEOFF, {mavlink.MAV_CMD_NAV_TAKEOFF})

    append_bounded_command_ack(acks, {"command": mavlink.MAV_CMD_NAV_LAND, "result": 4}, max_count=4)
    assert command_ack_rejected(acks, mavlink.MAV_CMD_NAV_LAND)
