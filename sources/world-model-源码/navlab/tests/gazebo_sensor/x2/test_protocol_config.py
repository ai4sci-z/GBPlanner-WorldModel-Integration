from __future__ import annotations

from pathlib import Path

import pytest

from navlab.sim.gazebo_sensor.config import (
    DownRangefinderRuntimeConfig,
    load_down_rangefinder_config,
    load_x2_protocol_config,
)


def test_x2_protocol_config_loads_vendor_defaults() -> None:
    config = load_x2_protocol_config()

    assert config.enabled.value is False
    assert config.profile.value == "/workspace/profiles/x2-vendor-sim.yaml"
    assert config.virtual_serial_link.value == "/tmp/navlab_x2"
    assert config.scan_ideal_topic.value == "/scan_ideal"
    assert config.vendor_scan_topic.value == "/navlab/x2/vendor_scan"
    assert config.scan_topic.value == "/scan"
    assert config.status_topic.value == "/sim/x2/status"
    assert config.sample_rate_hz.value == 3000.0
    assert config.scan_frequency_hz.value == 7.0
    assert config.scan_frequency_min_hz.value == 4.0
    assert config.scan_frequency_max_hz.value == 8.0
    assert config.scan_frequency_jitter_hz.value == 0.0
    assert config.range_min_m.value == 0.1
    assert config.range_max_m.value == 8.0
    assert config.range_noise_stddev_per_m.value == 0.0
    assert config.random_seed.value == ""


def test_x2_vendor_profile_matches_protocol_baseline() -> None:
    yaml = pytest.importorskip("yaml")

    profile_path = Path("docker/profiles/x2-vendor-sim.yaml")
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    params = profile["ydlidar_ros2_driver_node"]["ros__parameters"]

    assert params["use_sim_time"] is True
    assert params["port"] == "/tmp/navlab_x2"
    assert params["lidar_type"] == 1
    assert params["sample_rate"] == 3
    assert params["frequency"] == 7.0
    assert params["range_min"] == 0.1
    assert params["range_max"] == 8.0
    assert params["isSingleChannel"] is True
    assert params["intensity"] is False
    assert params["reversion"] is False
    assert params["inverted"] is False


def test_x2_runtime_config_passes_jitter_and_seed_to_emulator() -> None:
    from navlab.sim.gazebo_sensor.config import X2SensorRuntimeConfig

    runtime = X2SensorRuntimeConfig.load()
    emulator = runtime.emulator_config()

    assert emulator.scan_frequency_min_hz == 4.0
    assert emulator.scan_frequency_max_hz == 8.0
    assert emulator.scan_frequency_jitter_hz == 0.0
    assert emulator.random_seed is None


def test_down_rangefinder_config_loads_defaults_from_config_toml() -> None:
    config = load_down_rangefinder_config()

    assert config.enabled.value is True
    assert config.scan_ideal_topic.value == "/rangefinder/down/scan_ideal"
    assert config.range_topic.value == "/rangefinder/down/range"
    assert config.status_topic.value == "/rangefinder/down/status"
    assert config.virtual_serial_link.value == "/tmp/navlab_benewake_tfmini"
    assert config.serial_baud.value == "115200"
    assert config.frame_id.value == "rangefinder_down_frame"
    assert config.rate_hz.value == 20.0
    assert config.min_distance_m.value == 0.05
    assert config.max_distance_m.value == 6.0
    assert config.model_pose.value == "0 0 -0.02 0 1.5707963267948966 0"
    assert config.model_update_rate_hz.value == 20.0
    assert config.model_ray_count.value == "1"
    assert config.model_noise_stddev_m.value == 0.0


def test_down_rangefinder_runtime_config_is_fcu_peripheral_source() -> None:
    config = DownRangefinderRuntimeConfig.load()

    assert config.enabled is True
    assert config.virtual_serial_link == Path("/tmp/navlab_benewake_tfmini")
    assert config.serial_baud == 115200
