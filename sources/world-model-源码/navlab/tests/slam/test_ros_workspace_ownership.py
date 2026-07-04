from __future__ import annotations

from pathlib import Path


def test_slam_ros_packages_live_under_navlab_slam_without_src_wrapper() -> None:
    assert not Path("ros2_ws").exists()
    assert Path("navlab/common/interfaces/ydlidar_interfaces/package.xml").is_file()
    assert Path("navlab/common/slam/ros/localization/navlab_cartographer_adapter/package.xml").is_file()
    assert Path("navlab/common/slam/ros/bridges/navlab_external_nav_bridge/package.xml").is_file()
    assert Path("navlab/common/slam/ros/scenarios/navlab_slam_bringup/package.xml").is_file()
    assert Path("navlab/common/slam/ros/sensors/navlab_slam_imu_bridge/package.xml").is_file()


def test_companion_image_does_not_copy_slam_ros_workspace() -> None:
    companion_dockerfile = Path("docker/images/runtime/companion.Dockerfile").read_text(encoding="utf-8")
    slam_dockerfile = Path("docker/images/runtime/slam.Dockerfile").read_text(encoding="utf-8")

    assert "navlab-slam-cartographer" not in companion_dockerfile
    assert "navlab/common/slam/ros" not in companion_dockerfile
    assert "navlab/common/slam/ros" in slam_dockerfile
    assert "COPY navlab/common/interfaces/ydlidar_interfaces" in companion_dockerfile
    assert "COPY navlab/common/interfaces/ydlidar_interfaces" in slam_dockerfile
    assert "--base-paths navlab_interfaces" in companion_dockerfile
    assert "--base-paths navlab_slam_ros navlab_interfaces" in slam_dockerfile
