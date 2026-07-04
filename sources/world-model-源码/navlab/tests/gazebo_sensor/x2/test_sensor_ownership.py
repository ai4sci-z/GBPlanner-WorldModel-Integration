from __future__ import annotations

import re
from pathlib import Path

import pytest

from navlab.sim.gazebo_sensor.config import X2SensorRuntimeConfig, load_down_rangefinder_config


def test_x2_sensor_code_lives_under_sensor_package() -> None:
    assert Path("navlab/sim/gazebo_sensor/x2/protocol.py").is_file()
    assert Path("navlab/sim/gazebo_sensor/config.py").is_file()
    assert Path("navlab/sim/gazebo_sensor/x2/emulator.py").is_file()
    assert Path("navlab/sim/gazebo_sensor/cli.py").is_file()
    assert Path("navlab/sim/gazebo_sensor/runtime.py").is_file()
    assert Path("navlab/sim/gazebo_sensor/x2/scan_source.py").is_file()
    assert not Path("navlab/gazebo_sensor").exists()


def test_gazebo_sensor_docker_target_owns_vendor_driver_dependency() -> None:
    companion_dockerfile = Path("docker/images/runtime/companion.Dockerfile").read_text(encoding="utf-8")
    dockerfile = Path("docker/images/runtime/gazebo-sensor.Dockerfile").read_text(encoding="utf-8")

    assert "AS navlab-gazebo-sensor" in dockerfile
    assert "AS gazebo-sensor-python-builder" in dockerfile

    sensor_stage = dockerfile.split("AS navlab-gazebo-sensor", 1)[1]

    assert "third_party/YDLidar-SDK" in sensor_stage
    assert "third_party/ydlidar_ros2_driver" in sensor_stage
    assert "ros-${ROS_DISTRO}-ros-gz-bridge" in sensor_stage
    assert "navlab-gazebo-sensor" not in companion_dockerfile
    assert "third_party/ydlidar_ros2_driver" not in companion_dockerfile


def test_vendor_driver_uses_jazzy_compatible_parameter_declarations() -> None:
    source_path = Path("third_party/ydlidar_ros2_driver/src/ydlidar_ros2_driver_node.cpp")
    if not source_path.exists():
        pytest.skip("ydlidar_ros2_driver submodule is not initialized")

    source = source_path.read_text(encoding="utf-8")

    assert not re.search(r'declare_parameter\("[^"]+"\)', source)


def test_x2_compose_environment_is_scoped_to_gazebo_sensor_service() -> None:
    compose = Path("compose/docker-compose.yaml").read_text(encoding="utf-8")
    before_sensor, sensor_and_after = compose.split("  gazebo-sensor:", 1)
    sensor_stage, after_sensor = sensor_and_after.split("  fast-lio:", 1)

    assert "X2_MODE" in sensor_stage
    assert "X2_ARTIFACT_DIR" in sensor_stage
    assert "start-gazebo-sensor.sh" in sensor_stage
    assert "X2_VIRTUAL_SERIAL_LINK" not in sensor_stage
    assert "X2_STATUS_TOPIC" not in sensor_stage
    assert "X2_SCAN_IDEAL_TOPIC" not in sensor_stage
    assert "X2_SCAN_SOURCE" not in sensor_stage
    assert "X2_" not in before_sensor
    assert "X2_" not in after_sensor


def test_x2_sensor_runtime_config_reads_project_x2_protocol_section() -> None:
    config = X2SensorRuntimeConfig.load()

    assert config.virtual_serial_link.as_posix() == "/tmp/navlab_x2"
    assert config.status_topic == "/sim/x2/status"
    assert config.scan_topic == "/scan"
    assert config.scan_ideal_topic == "/scan_ideal"
    assert config.sample_rate_hz == 3000.0
    assert config.scan_frequency_hz == 7.0
    assert config.range_min_m == 0.1
    assert config.range_max_m == 8.0
    assert config.static_range_m == 1.5
    assert config.range_noise_stddev_m == 0.0
    assert config.dropout_rate == 0.0
    assert config.auto_start is True
    assert config.emulator_config().virtual_serial_link == config.virtual_serial_link


def test_replay_meshes_are_not_part_of_default_replay_path() -> None:
    assert not Path("docker/navlab_models/iris_with_standoffs").exists()
    assert not Path("docker/navlab_replay_meshes").exists()


def test_navlab_quad_model_owns_down_rangefinder_sensor() -> None:
    config = load_down_rangefinder_config()
    sdf = Path("docker/navlab_models/navlab_iq_quad/model.sdf").read_text(encoding="utf-8")

    assert '<include merge="true">' in sdf
    assert '<link name="rangefinder_down_link">' in sdf
    assert '<sensor name="rangefinder_down" type="gpu_lidar">' in sdf
    assert f"<pose>{config.model_pose.value}</pose>" in sdf
    assert f"<topic>{config.scan_ideal_topic.value}</topic>" in sdf
    assert f"<gz_frame_id>{config.frame_id.value}</gz_frame_id>" in sdf
    sensor_block = re.search(r'<sensor name="rangefinder_down" type="gpu_lidar">(.*?)</sensor>', sdf, re.DOTALL)
    assert sensor_block is not None
    update_rate = re.search(r"<update_rate>(.*?)</update_rate>", sensor_block.group(1))
    assert update_rate is not None
    assert float(update_rate.group(1)) == config.model_update_rate_hz.value
    assert f"<samples>{config.model_ray_count.value}</samples>" in sdf
    assert f"<max>{config.max_distance_m.value}</max>" in sdf
    assert f"<stddev>{config.model_noise_stddev_m.value}</stddev>" in sdf
