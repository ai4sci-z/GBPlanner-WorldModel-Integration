from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from navlab.sim.companion.runtime.acceptance import scan_publisher_summary, write_summary
from navlab.sim.companion.runtime.hover_acceptance import write_hover_summary


def _metadata_for_counts(counts: dict[str, int]) -> str:
    topics = []
    for topic, count in counts.items():
        topics.append(
            {
                "topic_metadata": {
                    "name": topic,
                    "type": "std_msgs/msg/String",
                    "serialization_format": "cdr",
                    "offered_qos_profiles": "",
                },
                "message_count": count,
            }
        )
    return "rosbag2_bagfile_information:\n  topics_with_message_count:\n" + "\n".join(
        [
            "    - topic_metadata:\n"
            f"        name: {item['topic_metadata']['name']}\n"
            f"        type: {item['topic_metadata']['type']}\n"
            "        serialization_format: cdr\n"
            "        offered_qos_profiles: ''\n"
            f"      message_count: {item['message_count']}"
            for item in topics
        ]
    )


def _runtime_config(*, pose_args: tuple[str, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        imu_source_label="fcu_mavlink_navlab",
        pose_mirror=SimpleNamespace(argv=lambda: list(pose_args)),
    )


def _hover_runtime_config(*, pose_args: tuple[str, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        pose_mirror=SimpleNamespace(argv=lambda: list(pose_args)),
    )


def _odom_sample(label: str, *, x: float, y: float, z: float) -> str:
    return (
        f"{label}\n"
        "header:\n"
        "  frame_id: odom\n"
        "child_frame_id: base_link\n"
        "pose:\n"
        "  pose:\n"
        "    position:\n"
        f"      x: {x}\n"
        f"      y: {y}\n"
        f"      z: {z}\n"
    )


def _samples(
    *,
    pose_set_count: int = 0,
    pose_reason: str = "mavlink_local_position_observed",
    external_nav_input_topic: str = "/slam/odom",
) -> str:
    def section(label: str, payload: dict[str, object]) -> str:
        return f"{label}\ndata: '{json.dumps(payload, separators=(',', ':'))}'\n"

    return "".join(
        [
            section("MISSION_STATUS_SAMPLE", {"obstacle_detected": True}),
            section("MAVLINK_STATUS_SAMPLE", {"heartbeat_seen": True, "message_counts": {"RANGEFINDER": 3}}),
            section(
                "POSE_MIRROR_STATUS_SAMPLE",
                {
                    "state": "mirroring",
                    "set_pose_count": pose_set_count,
                    "reason": pose_reason,
                },
            ),
            section("IMU_STATUS_SAMPLE", {"state": "streaming_fcu_imu", "ready": True}),
            section(
                "SLAM_STATUS_SAMPLE",
                {
                    "ready": True,
                    "state": "publishing_tf_backed_odom",
                    "output": {"odom_topic": "/odom", "count": 10},
                },
            ),
            section(
                "EXTERNAL_STATUS_SAMPLE",
                {"state": "healthy", "ready": True, "odom": {"input_topic": external_nav_input_topic}},
            ),
            section("MAVLINK_EXTERNAL_NAV_STATUS_SAMPLE", {"state": "sending"}),
            _odom_sample("SLAM_ODOM_SAMPLE", x=1.0, y=0.5, z=0.45),
            _odom_sample("GAZEBO_TRUTH_ODOM_SAMPLE", x=1.1, y=0.55, z=0.46),
            section("SCAN_FEATURES_SAMPLE", {"front_clearance_m": 5.0}),
            section("SIM_LOG_SAMPLE", {"event": "ok"}),
            section(
                "X2_STATUS_SAMPLE",
                {
                    "source": "x2_serial_emulator",
                    "latest_scan_ideal_age_sec": 0.05,
                },
            ),
            section(
                "RANGEFINDER_DOWN_STATUS_SAMPLE",
                {
                    "state": "publishing",
                    "ready": True,
                    "source": "gazebo_down_range_projection",
                    "fcu_transport": "serial7_uart",
                    "fcu_rangefinder_source": "ardupilot_serial7_benewake_tfmini",
                    "rangefinder_simulation_fidelity": "benewake_serial_emulated",
                    "input_count": 12,
                    "latest_distance_m": 0.45,
                },
            ),
            "SCAN_TOPIC_INFO\n"
            "Type: sensor_msgs/msg/LaserScan\n"
            "Publisher count: 1\n"
            "Node name: ydlidar_ros2_driver_node\n"
            "Node namespace: /\n"
            "Topic type: sensor_msgs/msg/LaserScan\n"
            "Subscription count: 1\n"
            "Node name: scan_features_publisher\n"
            "Node namespace: /\n",
        ]
    )


def _hover_samples(*, slam_y: float = 0.05, truth_y: float = 0.04) -> str:
    def section(label: str, payload: dict[str, object]) -> str:
        return f"{label}\ndata: '{json.dumps(payload, separators=(',', ':'))}'\n"

    return "".join(
        [
            section("MAVLINK_STATUS_SAMPLE", {"heartbeat_seen": True, "message_counts": {"DISTANCE_SENSOR": 3}}),
            section("POSE_MIRROR_STATUS_SAMPLE", {"set_pose_count": 0, "reason": "mavlink_local_position_observed"}),
            section("IMU_STATUS_SAMPLE", {"state": "streaming_fcu_imu", "ready": True}),
            section("SLAM_STATUS_SAMPLE", {"ready": True, "state": "publishing_tf_backed_odom"}),
            section("GAZEBO_TRUTH_STATUS_SAMPLE", {"ready": True, "state": "publishing"}),
            section(
                "EXTERNAL_STATUS_SAMPLE",
                {"state": "healthy", "ready": True, "odom": {"input_topic": "/slam/odom"}},
            ),
            section("MAVLINK_EXTERNAL_NAV_STATUS_SAMPLE", {"state": "sending"}),
            section("X2_STATUS_SAMPLE", {"latest_scan_ideal_age_sec": 0.05}),
            section(
                "RANGEFINDER_DOWN_STATUS_SAMPLE",
                {
                    "state": "publishing",
                    "ready": True,
                    "source": "gazebo_down_range_projection",
                    "fcu_transport": "serial7_uart",
                    "fcu_rangefinder_source": "ardupilot_serial7_benewake_tfmini",
                    "rangefinder_simulation_fidelity": "benewake_serial_emulated",
                },
            ),
            _odom_sample("SLAM_ODOM_SAMPLE", x=0.05, y=slam_y, z=0.0),
            _odom_sample("GAZEBO_TRUTH_ODOM_SAMPLE", x=0.04, y=truth_y, z=0.0),
        ]
    )


def _write_hover_acceptance_inputs(tmp_path: Path) -> dict[str, object]:
    (tmp_path / "mission_summary.json").write_text(
        json.dumps(
            {
                "ok": True,
                "reason": "complete",
                "guided_seen": True,
                "armed_seen": True,
                "airborne_seen": True,
                "takeoff_ack_ok": True,
                "local_position_count": 12,
                "rangefinder_count": 3,
                "hover_hold_sec": 20.0,
                "phases_seen": ["wait_ready", "guided", "arm", "takeoff", "hover_settle", "hover_hold"],
                "hover_drift": {
                    "ok": True,
                    "quality": "tight",
                    "sample_count": 10,
                    "duration_sec": 20.0,
                    "duration_tolerance_sec": 0.25,
                    "horizontal_drift_m": 0.02,
                    "horizontal_span_m": 0.03,
                    "z_drift_m": 0.01,
                    "z_span_m": 0.02,
                },
                "hover_altitude_sources": {
                    "fcu_local_z_ned": -0.45,
                    "fcu_local_height_m": 0.45,
                    "external_nav_height_m": 0.44,
                    "rangefinder_range_m": 0.50,
                    "rangefinder_relative_height_m": 0.45,
                },
                "hover_altitude_crosscheck": {
                    "ok": True,
                    "sample_count": 10,
                    "target_alt_m": 0.45,
                    "tolerance_m": 0.08,
                    "sources": {
                        "fcu_local_z_ned": -0.45,
                        "fcu_local_height_m": 0.45,
                        "external_nav_height_m": 0.44,
                        "rangefinder_range_m": 0.50,
                        "rangefinder_relative_height_m": 0.45,
                    },
                    "diffs": {
                        "fcu_vs_external_abs_m": 0.01,
                        "fcu_vs_rangefinder_abs_m": 0.0,
                        "external_vs_rangefinder_abs_m": 0.01,
                        "fcu_target_error_m": 0.0,
                        "external_target_error_m": 0.01,
                        "rangefinder_target_error_m": 0.0,
                    },
                    "missing_sources": [],
                    "over_tolerance": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "gazebo_truth_trajectory.json").write_text(
        json.dumps(
            {
                "summary": {"sample_count": 2, "duration_sec": 20.0},
                "samples": [
                    {"x_m": 0.0, "y_m": 0.0},
                    {"x_m": 0.05, "y_m": 0.04},
                ],
            }
        ),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "message_counts": {
            "/odom": 10,
            "/external_nav/odom": 10,
            "/external_nav/status": 4,
            "/mavlink_external_nav/status": 4,
            "/navlab/fcu/local_position_pose": 8,
            "/rangefinder/down/status": 4,
        },
    }


def _write_acceptance_inputs(tmp_path: Path) -> dict[str, object]:
    (tmp_path / "rosbag").mkdir()
    counts = {
        "/scan": 10,
        "/scan_ideal": 12,
        "/sim/x2/status": 3,
        "/rangefinder/down/range": 7,
        "/rangefinder/down/status": 3,
        "/odom": 10,
        "/navlab/slam/status": 3,
        "/gazebo/truth/odom": 10,
        "/external_nav/odom": 10,
        "/scan_features": 2,
        "/navlab/mission/status": 4,
    }
    (tmp_path / "rosbag" / "metadata.yaml").write_text(_metadata_for_counts(counts), encoding="utf-8")
    (tmp_path / "mission_summary.json").write_text(
        json.dumps(
            {
                "phases_seen": [
                    "wait_ready",
                    "guided",
                    "arm",
                    "takeoff",
                    "hover_settle",
                    "forward",
                    "scan_left",
                    "scan_right",
                    "avoid",
                    "final_hold",
                ],
                "obstacle_detected": True,
                "avoidance_setpoint_sent": True,
                "scan_left_seen": True,
                "scan_right_seen": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "gazebo_truth_trajectory.json").write_text(
        json.dumps(
            {
                "schema": "navlab.gazebo_truth_trajectory.v1",
                "source_topic": "/gazebo/truth/odom",
                "summary": {
                    "sample_count": 2,
                    "duration_sec": 1.0,
                    "horizontal_path_length_m": 0.1,
                    "horizontal_displacement_m": 0.1,
                    "z_span_m": 0.02,
                },
                "samples": [],
            }
        ),
        encoding="utf-8",
    )
    rosbag_profile = {"ok": True, "message_counts": counts}
    return rosbag_profile


def test_scan_publisher_summary_reads_only_publishers() -> None:
    samples = """SCAN_TOPIC_INFO
Type: sensor_msgs/msg/LaserScan
Publisher count: 1
Node name: ydlidar_ros2_driver_node
Node namespace: /
Topic type: sensor_msgs/msg/LaserScan
Subscription count: 1
Node name: scan_features_publisher
Node namespace: /
"""

    summary = scan_publisher_summary(samples)

    assert summary["publisher_nodes"] == ["ydlidar_ros2_driver_node"]
    assert summary["vendor_driver_publisher"] is True
    assert summary["emulator_publisher"] is False


def test_write_summary_requires_x2_lidar_and_observation_mode(tmp_path: Path) -> None:
    rosbag_profile = _write_acceptance_inputs(tmp_path)
    (tmp_path / "samples.txt").write_text(_samples(), encoding="utf-8")

    rc = write_summary(
        artifact_dir=tmp_path,
        duration_sec=90.0,
        mission_rc=0,
        rosbag_profile=rosbag_profile,
        config=_runtime_config(),
        scan_source="x2_virtual_serial_vendor_driver",
    )

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert summary["ok"] is True
    assert summary["lidar_chain"]["scan_count"] == 10
    assert summary["lidar_chain"]["scan_ideal_count"] == 12
    assert summary["lidar_chain"]["x2_status_count"] == 3
    assert summary["x2_status"]["source"] == "x2_serial_emulator"
    assert summary["rangefinder_down_status"]["state"] == "publishing"
    assert summary["rangefinder_fcu_observed"] is True
    assert summary["rangefinder_serial_ok"] is True
    assert summary["rangefinder_simulation_fidelity"] == "benewake_serial_emulated"
    assert summary["gazebo_truth_trajectory"]["ok"] is True
    assert summary["gazebo_truth_trajectory"]["sample_count"] == 2
    assert summary["observation_mode"]["pose_mirror_observation_only"] is True
    assert summary["slam_odom_source"]["recorded"] is True
    assert summary["slam_status"]["ready"] is True
    assert summary["external_nav_input_topic"] == "/slam/odom"
    assert summary["external_nav_uses_slam_odom"] is True
    assert summary["external_nav_uses_gazebo_truth"] is False
    assert summary["slam_truth_comparison"]["available"] is True
    assert summary["slam_truth_comparison"]["horizontal_error_m"] > 0


def test_write_summary_fails_when_pose_mirror_can_set_gazebo_pose(tmp_path: Path) -> None:
    rosbag_profile = _write_acceptance_inputs(tmp_path)
    (tmp_path / "samples.txt").write_text(_samples(pose_set_count=2, pose_reason="set_pose_sent"), encoding="utf-8")

    rc = write_summary(
        artifact_dir=tmp_path,
        duration_sec=90.0,
        mission_rc=0,
        rosbag_profile=rosbag_profile,
        config=_runtime_config(pose_args=("--set-gazebo-pose",)),
        scan_source="x2_virtual_serial_vendor_driver",
    )

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert rc == 3
    assert summary["ok"] is False
    assert summary["observation_mode"]["pose_mirror_set_pose_disabled"] is False


def test_write_summary_does_not_require_obstacle_demo_phases_for_hover_gate(tmp_path: Path) -> None:
    rosbag_profile = _write_acceptance_inputs(tmp_path)
    (tmp_path / "mission_summary.json").write_text(
        json.dumps(
            {
                "phases_seen": [
                    "wait_ready",
                    "guided",
                    "arm",
                    "takeoff",
                    "hover_settle",
                ],
                "obstacle_detected": False,
                "avoidance_setpoint_sent": False,
                "scan_left_seen": False,
                "scan_right_seen": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "samples.txt").write_text(_samples(), encoding="utf-8")

    rc = write_summary(
        artifact_dir=tmp_path,
        duration_sec=90.0,
        mission_rc=0,
        rosbag_profile=rosbag_profile,
        config=_runtime_config(),
        scan_source="x2_virtual_serial_vendor_driver",
    )

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert summary["ok"] is True
    assert summary["hover_ok"] is True
    assert summary["forward_progress_ok"] is False
    assert summary["lateral_detour_ok"] is False


def test_write_summary_fails_when_external_nav_uses_gazebo_truth(tmp_path: Path) -> None:
    rosbag_profile = _write_acceptance_inputs(tmp_path)
    (tmp_path / "samples.txt").write_text(
        _samples(external_nav_input_topic="/gazebo/truth/odom"),
        encoding="utf-8",
    )

    rc = write_summary(
        artifact_dir=tmp_path,
        duration_sec=90.0,
        mission_rc=0,
        rosbag_profile=rosbag_profile,
        config=_runtime_config(),
        scan_source="x2_virtual_serial_vendor_driver",
    )

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert rc == 3
    assert summary["ok"] is False
    assert summary["external_nav_input_topic"] == "/gazebo/truth/odom"
    assert summary["external_nav_uses_gazebo_truth"] is True
    assert summary["diagnostic_external_nav_input"] is True


def test_hover_summary_requires_slam_truth_error_within_gate(tmp_path: Path) -> None:
    rosbag_profile = _write_hover_acceptance_inputs(tmp_path)
    (tmp_path / "samples.txt").write_text(_hover_samples(slam_y=0.05, truth_y=0.04), encoding="utf-8")

    rc = write_hover_summary(
        artifact_dir=tmp_path,
        duration_sec=90.0,
        mission_rc=0,
        rosbag_profile=rosbag_profile,
        config=_hover_runtime_config(),
        scan_source="x2_virtual_serial_vendor_driver",
        max_slam_truth_horizontal_error_m=0.35,
    )

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert summary["ok"] is True
    assert summary["slam_truth_error_ok"] is True
    assert summary["hover_drift_quality"] == "tight"
    assert summary["hover_altitude_crosscheck"]["ok"] is True
    assert summary["hover_altitude_sources"]["rangefinder_relative_height_m"] == 0.45


def test_hover_summary_fails_when_slam_truth_error_is_too_large(tmp_path: Path) -> None:
    rosbag_profile = _write_hover_acceptance_inputs(tmp_path)
    (tmp_path / "samples.txt").write_text(_hover_samples(slam_y=1.0, truth_y=0.04), encoding="utf-8")

    rc = write_hover_summary(
        artifact_dir=tmp_path,
        duration_sec=90.0,
        mission_rc=0,
        rosbag_profile=rosbag_profile,
        config=_hover_runtime_config(),
        scan_source="x2_virtual_serial_vendor_driver",
        max_slam_truth_horizontal_error_m=0.35,
    )

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert rc == 3
    assert summary["ok"] is False
    assert summary["slam_truth_error_ok"] is False
    assert summary["slam_truth_comparison"]["horizontal_error_m"] > 0.35
