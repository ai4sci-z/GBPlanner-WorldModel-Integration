from __future__ import annotations

from pathlib import Path


def test_navlab_cartographer_lua_follows_official_ardupilot_baseline() -> None:
    config = Path(
        "navlab/common/slam/ros/localization/navlab_cartographer_adapter/config/navlab_cartographer_2d_diagnostic_odom.lua"
    ).read_text(encoding="utf-8")

    assert 'tracking_frame = "imu_link"' in config
    assert 'published_frame = "base_link"' in config
    assert "provide_odom_frame = true" in config
    assert "publish_frame_projected_to_2d = false" in config
    assert "use_odometry = true" in config
    assert "TRAJECTORY_BUILDER_2D.max_range = 30" in config
    assert "TRAJECTORY_BUILDER_2D.use_imu_data = false" in config
    assert "POSE_GRAPH.optimize_every_n_nodes = 30" in config


def test_unsafe_cartographer_odom_profile_cannot_be_selected_by_default_name() -> None:
    assert not Path(
        "navlab/common/slam/ros/localization/navlab_cartographer_adapter/config/navlab_cartographer_2d.lua"
    ).exists()


def test_navlab_cartographer_real_lua_keeps_no_truth_input_contract() -> None:
    config = Path(
        "navlab/common/slam/ros/localization/navlab_cartographer_adapter/config/navlab_cartographer_2d_real.lua"
    ).read_text(encoding="utf-8")

    assert 'tracking_frame = "imu_link"' in config
    assert 'published_frame = "base_link"' in config
    assert "provide_odom_frame = false" in config
    assert "use_odometry = false" in config
    assert "TRAJECTORY_BUILDER_2D.use_imu_data = true" in config
    assert "TRAJECTORY_BUILDER_2D.max_range = 8" in config
    assert "TRAJECTORY_BUILDER_2D.ceres_scan_matcher.translation_weight = 20" in config
    assert "TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.linear_search_window = 0.03" in config
    assert "TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.angular_search_window = math.rad(2.0)" in config
    assert "TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.translation_delta_cost_weight = 50." in config
    assert "POSE_GRAPH.optimize_every_n_nodes = 0" in config
    assert "POSE_GRAPH.constraint_builder.min_score = 0.85" in config


def test_navlab_cartographer_hover_lua_does_not_consume_synthetic_odom_prior() -> None:
    config = Path(
        "navlab/common/slam/ros/localization/navlab_cartographer_adapter/config/navlab_cartographer_2d_hover.lua"
    ).read_text(encoding="utf-8")

    assert "scan-reference odometry prior derived only from /scan" in config
    assert "Gazebo truth pose, fixed XY prior, or official maze-map localizer" in config
    assert 'published_frame = "base_link"' in config
    assert "provide_odom_frame = false" in config
    assert "use_odometry = true" in config
    assert "TRAJECTORY_BUILDER_2D.use_imu_data = true" in config
    assert "scan-led" in config
    assert "TRAJECTORY_BUILDER_2D.ceres_scan_matcher.translation_weight = 1." in config
    assert "TRAJECTORY_BUILDER_2D.ceres_scan_matcher.rotation_weight = 10." in config
    assert "TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.linear_search_window = 0.50" in config
    assert "TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.translation_delta_cost_weight = 1." in config
    assert "TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.rotation_delta_cost_weight = 10." in config
    assert "POSE_GRAPH.optimization_problem.local_slam_pose_translation_weight = 1e2" in config
    assert "POSE_GRAPH.optimization_problem.odometry_translation_weight = 1e4" in config
    assert "POSE_GRAPH.optimize_every_n_nodes = 30" in config


def test_slam_bringup_accepts_runtime_cartographer_config_directory() -> None:
    launch = Path(
        "navlab/common/slam/ros/scenarios/navlab_slam_bringup/launch/navlab_slam_bringup.launch.py"
    ).read_text(encoding="utf-8")

    assert '"cartographer_configuration_directory"' in launch
    assert 'LaunchConfiguration("cartographer_configuration_directory")' in launch
