from __future__ import annotations

import pytest

from navlab.common.slam.backends import SlamBackend, SlamBackendRegistry
from navlab.common.slam.config import RuntimeConfig
from navlab.common.slam.runtime import build_command


def test_slam_runtime_config_loads_cartographer_contract() -> None:
    config = RuntimeConfig.load("navlab/config.toml")

    assert config.backend == "cartographer"
    assert config.use_sim_time is True
    assert config.scan_topic == "/scan"
    assert config.imu_topic == "/imu"
    assert config.cartographer_odometry_topic == "/cartographer/odometry_input"
    assert config.cartographer_configuration_directory == ""
    assert config.publish_global_tf is True
    assert config.global_tf_topic == "/tf"
    assert config.odom_topic == "/slam/odom"
    assert config.external_nav_input_odom_topic == "/slam/odom"
    assert config.gazebo_truth_odom_topic == "/gazebo/truth/odom"
    assert config.uses_diagnostic_truth_for_external_nav is False


def test_cartographer_backend_generates_launch_command_from_runtime_config() -> None:
    command = build_command(config_path="navlab/config.toml")

    assert command[:4] == ["ros2", "launch", "navlab_slam_bringup", "navlab_slam_bringup.launch.py"]
    assert "launch_fake_odom:=false" in command
    assert "launch_cartographer_backend:=true" in command
    assert "use_sim_time:=true" in command
    assert "publish_placeholder_odom:=false" in command
    assert "scan_topic:=/scan" in command
    assert "imu_topic:=/imu" in command
    assert "laser_frame:=laser_frame" in command
    assert "laser_z:=0" in command
    assert "cartographer_odometry_topic:=/cartographer/odometry_input" in command
    assert "cartographer_configuration_directory:=" in command
    assert "cartographer_odometry_topic:=/odometry" not in command
    assert "publish_global_tf:=true" in command
    assert "global_tf_topic:=/tf" in command
    assert "odom_topic:=/slam/odom" in command
    assert "slam_status_topic:=/navlab/slam/status" in command
    assert "imu_source_topic:=/navlab/fcu_imu/data" in command
    assert "external_nav_input_odom_topic:=/slam/odom" in command
    assert "external_nav_input_odom_topic:=/gazebo/truth/odom" not in command


def test_slam_runtime_accepts_frame_id_aliases(tmp_path) -> None:
    config_path = tmp_path / "slam_runtime.toml"
    config_path.write_text(
        "\n".join(
            (
                "[slam.runtime]",
                'laser_frame_id = "base_scan"',
                'imu_frame_id = "imu_link"',
                'base_frame_id = "base_link"',
                'laser_z = "0.075077"',
            )
        ),
        encoding="utf-8",
    )

    config = RuntimeConfig.load(config_path)

    assert config.laser_frame == "base_scan"
    assert config.imu_frame == "imu_link"
    assert config.base_frame == "base_link"
    assert config.laser_z == "0.075077"


def test_slam_backend_registry_exposes_cartographer() -> None:
    assert "cartographer" in SlamBackendRegistry.names()
    assert SlamBackendRegistry.create("cartographer").BACKEND_NAME == "cartographer"


def test_slam_backend_registry_requires_backend_name() -> None:
    class MissingNameBackend(SlamBackend):
        def command(self, config: RuntimeConfig) -> list[str]:
            return []

    with pytest.raises(ValueError, match="MissingNameBackend must define BACKEND_NAME"):
        SlamBackendRegistry.register(MissingNameBackend)


def test_slam_backend_registry_rejects_duplicate_backend_name() -> None:
    class DuplicateCartographerBackend(SlamBackend):
        BACKEND_NAME = "cartographer"

        def command(self, config: RuntimeConfig) -> list[str]:
            return []

    with pytest.raises(ValueError, match="SLAM backend 'cartographer' is already registered"):
        SlamBackendRegistry.register(DuplicateCartographerBackend)
