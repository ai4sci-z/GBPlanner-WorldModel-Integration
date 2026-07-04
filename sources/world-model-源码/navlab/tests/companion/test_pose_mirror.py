from __future__ import annotations

import json
from math import isclose, pi
from types import SimpleNamespace

from navlab.real.companion.nodes.pose_mirror import (
    MavlinkTelemetryStatus,
    NedPoseSample,
    PoseMirrorStatus,
    anchored_sim_stamp_nanoseconds,
    build_pose_stamped_fields,
    build_replay_transform_fields,
    default_replay_static_transforms,
    encode_mavlink_telemetry_status,
    encode_pose_mirror_status,
    filter_displayable_markers,
    marker_has_displayable_geometry,
    ned_to_gazebo_pose,
    next_imu_output_stamp_nanoseconds,
    next_monotonic_stamp_nanoseconds,
    normalize_mavlink_param_value,
    parse_ekf_source_set_from_statustext,
    stamp_fields_to_nanoseconds,
)


def test_ned_to_gazebo_pose_maps_forward_right_and_altitude() -> None:
    pose = ned_to_gazebo_pose(NedPoseSample(x_north_m=2.0, y_east_m=0.5, z_down_m=-0.8, yaw_rad=0.25))

    assert isclose(pose.x, 2.0)
    assert isclose(pose.y, 0.5)
    assert isclose(pose.z, 0.8)
    assert isclose(pose.yaw, 0.25)


def test_ned_to_gazebo_pose_keeps_landed_marker_above_floor() -> None:
    pose = ned_to_gazebo_pose(NedPoseSample(x_north_m=0.0, y_east_m=0.0, z_down_m=0.0), min_z_m=0.1)

    assert isclose(pose.z, 0.1)


def test_build_pose_stamped_fields_uses_yaw_quaternion() -> None:
    pose = ned_to_gazebo_pose(NedPoseSample(x_north_m=1.0, y_east_m=2.0, z_down_m=-0.5, yaw_rad=pi / 2))

    fields = build_pose_stamped_fields(pose)

    assert isclose(fields["x"], 1.0)
    assert isclose(fields["y"], 2.0)
    assert isclose(fields["z"], 0.5)
    assert isclose(fields["qz"], 2**0.5 / 2)
    assert isclose(fields["qw"], 2**0.5 / 2)


def test_replay_tf_helpers_connect_world_map_base_and_laser() -> None:
    pose = ned_to_gazebo_pose(NedPoseSample(x_north_m=1.0, y_east_m=2.0, z_down_m=-0.5, yaw_rad=pi / 2))
    dynamic = build_replay_transform_fields(
        parent_frame_id="navlab_world",
        child_frame_id="navlab_base_link",
        pose=pose,
    )
    static = default_replay_static_transforms(
        root_frame_id="navlab_world",
        map_frame_id="map",
        odom_frame_id="",
        sensor_base_frame_id="navlab_replay_base_link",
        laser_frame_id="navlab_replay_laser_frame",
        imu_frame_id="navlab_replay_imu_link",
        laser_x_m=0.05,
        laser_y_m=0.0,
        laser_z_m=0.13,
    )

    assert dynamic["parent_frame_id"] == "navlab_world"
    assert dynamic["child_frame_id"] == "navlab_base_link"
    assert dynamic["x"] == 1.0
    assert [(item.parent_frame_id, item.child_frame_id) for item in static] == [
        ("navlab_world", "map"),
        ("navlab_replay_base_link", "navlab_replay_laser_frame"),
        ("navlab_replay_base_link", "navlab_replay_imu_link"),
    ]
    assert static[1].x == 0.05
    assert static[1].z == 0.13


def test_anchored_sim_stamp_uses_scan_time_domain_and_stays_monotonic() -> None:
    anchor_ns = stamp_fields_to_nanoseconds(12, 100)
    candidate = anchored_sim_stamp_nanoseconds(
        anchor_stamp_ns=anchor_ns,
        anchor_monotonic=20.0,
        now_monotonic=20.25,
    )

    assert candidate == 12_250_000_100
    assert next_monotonic_stamp_nanoseconds(candidate_ns=99, previous_ns=100) == 101
    assert next_monotonic_stamp_nanoseconds(candidate_ns=200, previous_ns=100) == 200


def test_imu_output_stamp_stays_monotonic_when_scan_anchor_arrives_late() -> None:
    wall_clock_ns = stamp_fields_to_nanoseconds(100, 0)
    first_stamp = next_imu_output_stamp_nanoseconds(
        stamp_source_ns=None,
        stamp_source_monotonic=0.0,
        now_monotonic=10.0,
        node_clock_ns=wall_clock_ns,
        previous_output_ns=None,
    )
    anchored_stamp = next_imu_output_stamp_nanoseconds(
        stamp_source_ns=stamp_fields_to_nanoseconds(99, 0),
        stamp_source_monotonic=10.0,
        now_monotonic=10.1,
        node_clock_ns=stamp_fields_to_nanoseconds(100, 100),
        previous_output_ns=first_stamp,
    )

    assert first_stamp == wall_clock_ns
    assert anchored_stamp == wall_clock_ns + 1


def test_marker_filter_removes_empty_line_list_markers() -> None:
    empty_line_list = SimpleNamespace(type=5, action=0, points=[])
    odd_line_list = SimpleNamespace(type=5, action=0, points=[object()])
    valid_line_list = SimpleNamespace(type=5, action=0, points=[object(), object()])
    delete_marker = SimpleNamespace(type=5, action=2, points=[])

    assert marker_has_displayable_geometry(empty_line_list) is False
    assert marker_has_displayable_geometry(odd_line_list) is False
    assert marker_has_displayable_geometry(valid_line_list) is True
    assert marker_has_displayable_geometry(delete_marker) is True
    assert filter_displayable_markers([empty_line_list, odd_line_list, valid_line_list]) == [valid_line_list]


def test_encode_pose_mirror_status_is_json_with_expected_state() -> None:
    payload = encode_pose_mirror_status(
        PoseMirrorStatus(
            state="mirroring",
            local_position_present=True,
            local_position_age_ms=12.3456,
            set_pose_count=3,
            last_gazebo_x=1.0,
            last_gazebo_y=0.0,
            last_gazebo_z=0.8,
            last_yaw_rad=0.1,
            reason="set_pose_sent",
        )
    )

    data = json.loads(payload)
    assert data["state"] == "mirroring"
    assert data["local_position"]["present"] is True
    assert data["local_position"]["age_ms"] == 12.346
    assert data["set_pose_count"] == 3
    assert data["reason"] == "set_pose_sent"


def test_encode_mavlink_telemetry_status_is_json_with_message_counts() -> None:
    payload = encode_mavlink_telemetry_status(
        MavlinkTelemetryStatus(
            state="streaming",
            heartbeat_seen=True,
            target_system=1,
            target_component=1,
            armed=True,
            mode_number=4,
            mode_name="GUIDED",
            local_position_present=True,
            local_position_age_ms=12.3456,
            local_position_valid=True,
            active_source_set="SRC2",
            configured_external_nav_source_set="SRC1",
            observed_ekf_source_set="SRC2",
            observed_ekf_source_set_text="Using EKF Source Set 2",
            external_nav_seen_by_fcu=True,
            ekf_source_set_switch={
                "enabled": True,
                "target_source_set": "SRC1",
                "target_source_set_id": 1,
                "sent": True,
                "sent_count": 1,
                "ack_result": 0,
            },
            parameters={
                "GPS_TYPE": 0,
                "GPS1_TYPE": 0,
                "VISO_TYPE": 1,
                "EK3_SRC1_POSXY": 6,
                "EK3_SRC1_VELXY": 6,
                "EK3_SRC1_YAW": 6,
            },
            ekf_flags=[831],
            command_acks=[{"command": 400, "result": 0}],
            statustext=[{"severity": 6, "text": "Mode GUIDED"}],
            message_counts={"HEARTBEAT": 2, "LOCAL_POSITION_NED": 5},
        )
    )

    data = json.loads(payload)
    assert data["state"] == "streaming"
    assert data["heartbeat_seen"] is True
    assert data["armed"] is True
    assert data["mode"] == "GUIDED"
    assert data["mode_name"] == "GUIDED"
    assert data["local_position"]["age_ms"] == 12.346
    assert data["local_position_valid"] is True
    assert data["active_source_set"] == "SRC2"
    assert data["configured_external_nav_source_set"] == "SRC1"
    assert data["observed_ekf_source_set"] == "SRC2"
    assert data["observed_ekf_source_set_text"] == "Using EKF Source Set 2"
    assert data["external_nav_seen_by_fcu"] is True
    assert data["ekf_source_set_switch"]["target_source_set"] == "SRC1"
    assert data["ekf_source_set_switch"]["ack_result"] == 0
    assert data["parameters"]["GPS_TYPE"] == 0
    assert data["parameters"]["EK3_SRC1_POSXY"] == 6
    assert data["ekf"]["flags_seen"] == [831]
    assert data["command_acks"][0]["command"] == 400
    assert data["statustext"][0]["text"] == "Mode GUIDED"
    assert data["message_counts"]["LOCAL_POSITION_NED"] == 5


def test_parse_ekf_source_set_from_statustext() -> None:
    assert parse_ekf_source_set_from_statustext("Using EKF Source Set 2") == "SRC2"
    assert parse_ekf_source_set_from_statustext("EKF3 source set changed to 1") == "SRC1"
    assert parse_ekf_source_set_from_statustext("Mode GUIDED") is None


def test_normalize_mavlink_param_value_preserves_int_params() -> None:
    assert normalize_mavlink_param_value(6.0) == 6
    assert normalize_mavlink_param_value(1.5) == 1.5
    assert normalize_mavlink_param_value(b"GPS_TYPE\x00\x00") == "GPS_TYPE"
