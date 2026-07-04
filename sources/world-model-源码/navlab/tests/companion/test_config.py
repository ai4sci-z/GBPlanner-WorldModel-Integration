from __future__ import annotations

import tomllib

from navlab.sim.companion.runtime.config import RuntimeConfig, load_config


def test_companion_config_reads_companion_section() -> None:
    config = load_config()

    assert config.stop_distance.value == 0.5
    assert config.console_log_level.value == "DEBUG"
    assert config.file_log_level.value == "INFO"


def test_runtime_config_world_markers_follow_navlab_quad_root() -> None:
    config = RuntimeConfig.load()
    world_argv = config.world_markers.argv()
    pose_argv = config.pose_mirror.argv()
    scan_argv = config.scan_features.argv()
    odom_argv = config.gazebo_truth_odom.argv()
    mission_argv = config.mission.argv()

    assert config.world_markers.root_model_name == "navlab_iq_quad"
    assert config.world_markers.frame_id == "navlab_world"
    assert "--root-model-name" in world_argv
    assert "navlab_iq_quad" in world_argv
    assert "--set-gazebo-pose" not in pose_argv
    assert "--world-name" not in pose_argv
    assert "--model-name" not in pose_argv
    assert config.pose_mirror.pose_frame_id == "navlab_world"
    assert config.pose_mirror.map_frame_id == "map"
    assert config.pose_mirror.odom_frame_id == ""
    assert config.pose_mirror.replay_base_frame_id == "navlab_replay_base_link"
    assert config.pose_mirror.replay_base_parent_frame_id == "navlab_world"
    assert config.pose_mirror.laser_frame_id == "navlab_replay_laser_frame"
    assert config.pose_mirror.replay_imu_frame_id == "navlab_replay_imu_link"
    assert config.pose_mirror.imu_frame_id == "imu_link"
    assert config.pose_mirror.laser_z_m == 0.12
    assert "--pose-frame-id" in pose_argv
    assert "--laser-z-m" in pose_argv
    assert "--front-center-deg" in scan_argv
    front_flag = scan_argv.index("--front-center-deg")
    rear_flag = scan_argv.index("--rear-center-deg")
    assert scan_argv[front_flag + 1] == "0.0"
    assert scan_argv[rear_flag + 1] == "180.0"
    assert config.gazebo_truth_bridge.autostart is True
    assert "dynamic_pose/info@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V" in config.gazebo_truth_bridge.bridge
    assert config.gazebo_truth_bridge.ros_topic == "/gazebo/tf"
    assert config.gazebo_truth_bridge.command() == [
        "ros2",
        "run",
        "ros_gz_bridge",
        "parameter_bridge",
        config.gazebo_truth_bridge.bridge,
        "--ros-args",
        "-r",
        "/world/navlab_iq_quad_figure8/dynamic_pose/info:=/gazebo/tf",
    ]
    assert config.gazebo_truth_odom.autostart is True
    assert config.gazebo_truth_odom.input_topic == "/gazebo/tf"
    assert config.gazebo_truth_odom.odom_topic == "/gazebo/truth/odom"
    index_flag = odom_argv.index("--transform-index")
    assert odom_argv[index_flag + 1] == "0"
    assert "--require-external-nav" in mission_argv
    assert "--require-imu-status" in mission_argv
    assert "--require-disarm" in mission_argv
    assert "--require-motors-safe" in mission_argv
    assert "--send-position-setpoints" in mission_argv
    assert config.mission.landing_status_topic == "/navlab/landing/status"
    assert config.mission.landing_intent_topic == "/navlab/landing/intent"
    assert config.mission.pre_land_hold_sec == 2.0
    assert config.mission.max_landing_duration_sec == 35.0
    assert config.mission.landing_policy == "ap_land_mode_after_hover"
    assert config.mission.landing_setpoint_lookahead_sec == 0.5
    assert config.mission.force_disarm_grace_sec == 3.0
    landing_status_flag = mission_argv.index("--landing-status-topic")
    landing_policy_flag = mission_argv.index("--landing-policy")
    landing_lookahead_flag = mission_argv.index("--landing-setpoint-lookahead-sec")
    force_disarm_grace_flag = mission_argv.index("--force-disarm-grace-sec")
    assert mission_argv[landing_status_flag + 1] == "/navlab/landing/status"
    assert mission_argv[landing_policy_flag + 1] == "ap_land_mode_after_hover"
    assert mission_argv[landing_lookahead_flag + 1] == "0.5"
    assert mission_argv[force_disarm_grace_flag + 1] == "3.0"
    for obsolete in (
        "--forward-speed-mps",
        "--avoid-forward-speed-mps",
        "--obstacle-detect-distance-m",
        "--obstacle-avoid-distance-m",
        "--scan-yaw-deg",
        "--scan-dwell-sec",
        "--pass-x-m",
        "--return-y-m",
        "--final-hold-sec",
        "--scan-features-topic",
        "--pose-topic",
        "--scan-timeout-sec",
        "--setpoint-lookahead-sec",
    ):
        assert obsolete not in mission_argv


def test_companion_runtime_config_uses_structured_fields_not_args_lists() -> None:
    data = tomllib.loads(open("navlab/config.toml", encoding="utf-8").read())
    runtime = data["companion"]["runtime"]

    for section_name, section in runtime.items():
        if isinstance(section, dict):
            assert "args" not in section, section_name


def test_companion_dependency_group_includes_numpy_for_ros_python() -> None:
    pyproject = tomllib.loads(open("navlab/pyproject.toml", encoding="utf-8").read())
    companion_deps = pyproject["dependency-groups"]["companion"]

    assert any(dep.startswith("numpy") for dep in companion_deps)
