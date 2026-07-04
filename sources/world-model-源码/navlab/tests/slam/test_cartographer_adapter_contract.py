from __future__ import annotations

from pathlib import Path


def test_cartographer_2d_adapter_marks_vertical_and_tilt_uncertain() -> None:
    source = Path(
        "navlab/common/slam/ros/localization/navlab_cartographer_adapter/src/navlab_cartographer_adapter_node.cpp"
    ).read_text(encoding="utf-8")

    for index in (14, 21, 28):
        assert f"odom.pose.covariance[{index}] = 9999.0" in source
        assert f"odom.twist.covariance[{index}] = 9999.0" in source


def test_cartographer_tf_is_isolated_from_global_tf() -> None:
    launch_files = [
        Path(
            "navlab/common/slam/ros/localization/navlab_cartographer_adapter/launch/navlab_cartographer_adapter.launch.py"
        ),
        Path("navlab/common/slam/ros/scenarios/navlab_slam_bringup/launch/navlab_slam_bringup.launch.py"),
    ]

    for launch_file in launch_files:
        source = launch_file.read_text(encoding="utf-8")
        assert 'default_value="/navlab/slam/tf"' in source
        assert '"tf_topic": LaunchConfiguration("cartographer_tf_topic")' in source
        assert '"publish_global_tf": LaunchConfiguration("publish_global_tf")' in source
        assert '"global_tf_topic": LaunchConfiguration("global_tf_topic")' in source
        assert '("/tf", LaunchConfiguration("cartographer_tf_topic"))' in source

    params = Path(
        "navlab/common/slam/ros/localization/navlab_cartographer_adapter/config/navlab_cartographer_adapter.params.yaml"
    ).read_text(encoding="utf-8")
    assert "tf_topic: /navlab/slam/tf" in params
    assert "publish_global_tf: false" in params
    assert "global_tf_topic: /tf" in params


def test_cartographer_adapter_reports_tf_reject_stability_metrics() -> None:
    source = Path(
        "navlab/common/slam/ros/localization/navlab_cartographer_adapter/src/navlab_cartographer_adapter_node.cpp"
    ).read_text(encoding="utf-8")

    for field in (
        "rejection_ratio",
        "max_observed_jump_m",
        "max_accepted_jump_m",
        "max_rejected_jump_m",
        "max_allowed_jump_m",
        "max_observed_yaw_z_jump",
        "max_accepted_yaw_z_jump",
        "max_rejected_yaw_z_jump",
        "max_allowed_yaw_z_jump",
        "publish_global_tf",
        "global_tf_topic",
    ):
        assert field in source

    assert "horizontal_jump_from_last" in source
    assert "yaw_z_jump_from_last" in source
    assert "publish_global_tf_from_transform" in source
