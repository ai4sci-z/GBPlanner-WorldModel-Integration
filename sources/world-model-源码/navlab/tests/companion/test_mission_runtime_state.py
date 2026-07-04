from __future__ import annotations

from navlab.common.companion.mission.mavlink_protocol import mavlink
from navlab.common.companion.mission.runtime_state import (
    MavlinkRuntimeCollections,
    MavlinkRuntimeState,
    MavlinkRuntimeUpdate,
    apply_bounded_mavlink_collections,
    external_nav_status_snapshot,
    mavlink_external_nav_status_snapshot,
    mavlink_runtime_update,
    mavlink_status_snapshot,
    parse_status_payload,
)


class _Msg:
    def __init__(self, msg_type: str, **fields: object) -> None:
        self._msg_type = msg_type
        for key, value in fields.items():
            setattr(self, key, value)

    def get_type(self) -> str:
        return self._msg_type

    def get_srcSystem(self) -> int:
        return int(getattr(self, "src_system", 1))

    def get_srcComponent(self) -> int:
        return int(getattr(self, "src_component", 1))


def _update(msg: _Msg):
    return mavlink_runtime_update(
        msg,
        mode_number=4,
        land_command_sent=False,
        mode_before_land=None,
        land_command_sent_time=None,
        started_at_monotonic=10.0,
        now_monotonic=12.0,
        ground_z_ned=None,
        ground_range_m=None,
        min_airborne_alt_m=0.1,
    )


def test_status_payload_parse_is_fail_closed() -> None:
    assert parse_status_payload("{bad") == {}
    assert parse_status_payload("[1, 2]") == {}
    assert parse_status_payload('{"ready": true}') == {"ready": True}


def test_external_nav_status_snapshot_extracts_ready_quality_and_event() -> None:
    snapshot = external_nav_status_snapshot(
        '{"ready":true,"state":"tracking","slam_quality":"good","slam_quality_good":true,'
        '"slam_quality_reason":"ok","height":{"z":0.44},'
        '"odom":{"input_topic":"/slam/odom","rate_hz":20,"rate_ok":true,"frame_ok":true,"age_ms":5}}',
        elapsed_sec=1.2345,
    )

    assert snapshot.ready is True
    assert snapshot.slam_quality_good is True
    assert snapshot.height_m == 0.44
    assert snapshot.event["input_topic"] == "/slam/odom"
    assert snapshot.event["elapsed_sec"] == 1.234


def test_mavlink_external_nav_and_status_snapshots() -> None:
    bridge = mavlink_external_nav_status_snapshot(
        '{"ready":true,"fcu_local_position_ready":true,"sent_count":10}',
        elapsed_sec=2.0,
    )
    status = mavlink_status_snapshot('{"mode_number":4,"armed":true}', mode_number=4)

    assert bridge.ready is True
    assert bridge.fcu_local_position_ready is True
    assert bridge.event["sent_count"] == 10
    assert status.expected_mode_seen is True
    assert status.armed_seen is True


def test_mavlink_runtime_update_extracts_mode_and_armed() -> None:
    update = _update(
        _Msg(
            "HEARTBEAT",
            autopilot=mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
            custom_mode=4,
            base_mode=mavlink.MAV_MODE_FLAG_SAFETY_ARMED,
            src_system=2,
            src_component=3,
        )
    )

    assert update.target_system == 2
    assert update.target_component == 3
    assert update.expected_mode_seen is True
    assert update.armed_seen is True


def test_mavlink_runtime_update_tracks_ack_and_collections() -> None:
    collections = MavlinkRuntimeCollections()
    update = _update(_Msg("COMMAND_ACK", command=mavlink.MAV_CMD_NAV_TAKEOFF, result=0))

    apply_bounded_mavlink_collections(collections, update)

    assert mavlink.MAV_CMD_NAV_TAKEOFF in collections.accepted_command_ids
    assert collections.command_acks == [{"command": mavlink.MAV_CMD_NAV_TAKEOFF, "result": 0}]


def test_mavlink_runtime_update_extracts_local_position_and_airborne() -> None:
    update = _update(_Msg("LOCAL_POSITION_NED", x=1.0, y=-2.0, z=-0.2, vz=0.01))

    assert update.current_x == 1.0
    assert update.current_y == -2.0
    assert update.current_z == -0.2
    assert update.ground_z_ned == -0.2
    assert update.airborne_seen is False or update.airborne_seen is None

    airborne = mavlink_runtime_update(
        _Msg("LOCAL_POSITION_NED", x=1.0, y=-2.0, z=-0.2, vz=0.01),
        mode_number=4,
        land_command_sent=False,
        mode_before_land=None,
        land_command_sent_time=None,
        started_at_monotonic=10.0,
        now_monotonic=12.0,
        ground_z_ned=0.0,
        ground_range_m=None,
        min_airborne_alt_m=0.1,
    )
    assert airborne.airborne_seen is True


def test_mavlink_runtime_update_extracts_rangefinder_and_landed_state() -> None:
    range_update = _update(_Msg("DISTANCE_SENSOR", current_distance=44))
    landed_update = _update(_Msg("EXTENDED_SYS_STATE", landed_state=mavlink.MAV_LANDED_STATE_ON_GROUND))

    assert range_update.current_range_m == 0.44
    assert range_update.ground_range_m == 0.44
    assert landed_update.landed_state == mavlink.MAV_LANDED_STATE_ON_GROUND
    assert landed_update.landed_state_event == {"elapsed_sec": 2.0, "landed_state": 1}


def test_mavlink_runtime_state_owns_pose_mode_counts_and_landed_timeline() -> None:
    state = MavlinkRuntimeState()

    state.apply_update(
        MavlinkRuntimeUpdate(
            "HEARTBEAT",
            target_system=2,
            target_component=3,
            current_custom_mode=4,
            expected_mode_seen=True,
            armed_seen=True,
        ),
        now_monotonic=11.0,
    )
    state.apply_update(
        MavlinkRuntimeUpdate(
            "LOCAL_POSITION_NED",
            current_x=1.0,
            current_y=-2.0,
            current_z=-0.5,
            current_vz=0.1,
            ground_z_ned=0.0,
            airborne_seen=True,
        ),
        now_monotonic=12.0,
    )
    state.apply_update(
        MavlinkRuntimeUpdate(
            "EXTENDED_SYS_STATE",
            landed_state=mavlink.MAV_LANDED_STATE_ON_GROUND,
            landed_state_event={"elapsed_sec": 2.0, "landed_state": mavlink.MAV_LANDED_STATE_ON_GROUND},
        ),
        now_monotonic=13.0,
    )

    assert state.target_system == 2
    assert state.target_component == 3
    assert state.current_custom_mode == 4
    assert state.guided_seen_ever is True
    assert state.armed_seen_ever is True
    assert state.current_x == 1.0
    assert state.current_y == -2.0
    assert state.current_z == -0.5
    assert state.ground_z_ned == 0.0
    assert state.airborne_started == 12.0
    assert state.message_counts == {"HEARTBEAT": 1, "LOCAL_POSITION_NED": 1, "EXTENDED_SYS_STATE": 1}
    assert state.landed_state_timeline[-1]["landed_state"] == mavlink.MAV_LANDED_STATE_ON_GROUND


def test_mission_runtime_state_adapter_builds_hover_inputs_and_readiness_summary() -> None:
    from navlab.common.companion.mission.runtime_state import MissionRuntimeAdapterConfig, MissionRuntimeStateAdapter

    adapter = MissionRuntimeStateAdapter(started_at_monotonic=10.0)
    config = MissionRuntimeAdapterConfig(
        status_timeout_sec=1.0,
        require_external_nav=True,
        require_imu_status=True,
        simulate_mode_arm=False,
        takeoff_alt_m=0.45,
    )
    adapter.apply_external_nav_status(
        '{"ready":true,"state":"healthy","slam_quality":"good","slam_quality_good":true,'
        '"slam_quality_reason":"ok","height":{"z":0.44},"odom":{"rate_ok":true,"frame_ok":true}}',
        now_monotonic=11.0,
    )
    adapter.apply_mavlink_external_nav_status(
        '{"ready":true,"fcu_local_position_ready":true,"sent_count":3}',
        now_monotonic=11.0,
    )
    adapter.apply_imu_status('{"ready":true}', now_monotonic=11.0)
    adapter.apply_mavlink_status('{"mode_number":4,"armed":true}', mode_number=4)
    runtime = MavlinkRuntimeState(airborne_seen=True, airborne_started=10.5, current_x=1.0, current_y=2.0)
    collections = MavlinkRuntimeCollections(accepted_command_ids={mavlink.MAV_CMD_NAV_TAKEOFF})

    inputs = adapter.build_hover_inputs(
        now_monotonic=11.5,
        config=config,
        runtime=runtime,
        collections=collections,
        target_z_ned=-0.45,
        fcu_local_height_m=0.45,
        rangefinder_relative_height_m=0.43,
        hover_started_at_monotonic=11.0,
    )
    readiness = adapter.readiness_summary(now_monotonic=11.5, config=config)

    assert inputs.external_nav_ready is True
    assert inputs.mavlink_external_nav_ready is True
    assert inputs.fcu_local_position_ready is True
    assert inputs.imu_ready is True
    assert inputs.expected_mode_seen is True
    assert inputs.armed_seen is True
    assert inputs.takeoff_ack_ok is True
    assert inputs.hover_elapsed_sec == 0.5
    assert inputs.airborne_elapsed_sec == 1.0
    assert inputs.external_nav_height_m == 0.44
    assert readiness.external_nav_ready is True
    assert readiness.fcu_local_position_ready is True
    assert readiness.mavlink_external_nav_status["sent_count"] == 3
