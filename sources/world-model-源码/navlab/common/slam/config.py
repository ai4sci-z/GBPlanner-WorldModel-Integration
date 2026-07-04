from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from navlab.common.toml_values import as_bool, as_str, load_navlab_config, nested_section

DEFAULT_BACKEND = "cartographer"
DEFAULT_CONFIG_PATH_ENV = "NAVLAB_SLAM_RUNTIME_CONFIG"


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    path: Path
    backend: str = DEFAULT_BACKEND
    use_sim_time: bool = True
    launch_package: str = "navlab_slam_bringup"
    launch_file: str = "navlab_slam_bringup.launch.py"
    launch_fake_odom: bool = False
    launch_cartographer_backend: bool = True
    publish_placeholder_odom: bool = False
    cartographer_configuration_directory: str = ""
    cartographer_configuration_basename: str = "navlab_cartographer_2d_real.lua"
    imu_source_mode: str = "topic"
    imu_source_topic: str = "/ap/imu/experimental/data"
    imu_source_label: str = "ardupilot_dds"
    imu_min_input_rate_hz: str = "4.0"
    require_imu_for_external_nav: bool = True
    require_height_for_external_nav: bool = True
    external_nav_input_odom_topic: str = "/odom"
    scan_topic: str = "/scan"
    imu_topic: str = "/imu"
    cartographer_odometry_topic: str = "/cartographer/odometry_input"
    cartographer_tf_topic: str = "/navlab/slam/tf"
    publish_global_tf: bool = False
    global_tf_topic: str = "/tf"
    cached_odom_publish_rate_hz: str = "10.0"
    odom_source_mode: str = "slam_tf"
    odom_topic: str = "/odom"
    slam_status_topic: str = "/navlab/slam/status"
    external_nav_status_topic: str = "/external_nav/status"
    gazebo_truth_odom_topic: str = "/gazebo/truth/odom"
    map_frame: str = "map"
    odom_frame: str = "odom"
    laser_frame: str = "laser_frame"
    imu_frame: str = "imu_link"
    base_frame: str = "base_link"
    laser_x: str = "0"
    laser_y: str = "0"
    laser_z: str = "0"
    laser_roll: str = "0"
    laser_pitch: str = "0"
    laser_yaw: str = "0"

    @classmethod
    def load(cls, path: str | Path | None = None, *, backend: str | None = None) -> RuntimeConfig:
        raw_path = path or os.environ.get(DEFAULT_CONFIG_PATH_ENV)
        config_path, data = load_navlab_config(raw_path)
        runtime = nested_section(data, "slam", "runtime")
        selected_backend = backend or as_str(runtime.get("backend"), DEFAULT_BACKEND)
        return cls(
            path=config_path,
            backend=selected_backend,
            use_sim_time=as_bool(runtime.get("use_sim_time"), True),
            launch_package=as_str(runtime.get("launch_package"), "navlab_slam_bringup"),
            launch_file=as_str(runtime.get("launch_file"), "navlab_slam_bringup.launch.py"),
            launch_fake_odom=as_bool(runtime.get("launch_fake_odom"), False),
            launch_cartographer_backend=as_bool(runtime.get("launch_cartographer_backend"), True),
            publish_placeholder_odom=as_bool(runtime.get("publish_placeholder_odom"), False),
            cartographer_configuration_directory=as_str(runtime.get("cartographer_configuration_directory"), ""),
            cartographer_configuration_basename=as_str(
                runtime.get("cartographer_configuration_basename"),
                "navlab_cartographer_2d_real.lua",
            ),
            imu_source_mode=as_str(runtime.get("imu_source_mode"), "topic"),
            imu_source_topic=as_str(runtime.get("imu_source_topic"), "/ap/imu/experimental/data"),
            imu_source_label=as_str(runtime.get("imu_source_label"), "ardupilot_dds"),
            imu_min_input_rate_hz=as_str(runtime.get("imu_min_input_rate_hz"), "4.0"),
            require_imu_for_external_nav=as_bool(runtime.get("require_imu_for_external_nav"), True),
            require_height_for_external_nav=as_bool(runtime.get("require_height_for_external_nav"), True),
            external_nav_input_odom_topic=as_str(runtime.get("external_nav_input_odom_topic"), "/odom"),
            scan_topic=as_str(runtime.get("scan_topic"), "/scan"),
            imu_topic=as_str(runtime.get("imu_topic"), "/imu"),
            cartographer_odometry_topic=as_str(
                runtime.get("cartographer_odometry_topic"),
                "/cartographer/odometry_input",
            ),
            cartographer_tf_topic=as_str(runtime.get("cartographer_tf_topic"), "/navlab/slam/tf"),
            publish_global_tf=as_bool(runtime.get("publish_global_tf"), False),
            global_tf_topic=as_str(runtime.get("global_tf_topic"), "/tf"),
            cached_odom_publish_rate_hz=as_str(runtime.get("cached_odom_publish_rate_hz"), "10.0"),
            odom_source_mode=as_str(runtime.get("odom_source_mode"), "slam_tf"),
            odom_topic=as_str(runtime.get("odom_topic"), "/odom"),
            slam_status_topic=as_str(runtime.get("slam_status_topic"), "/navlab/slam/status"),
            external_nav_status_topic=as_str(runtime.get("external_nav_status_topic"), "/external_nav/status"),
            gazebo_truth_odom_topic=as_str(runtime.get("gazebo_truth_odom_topic"), "/gazebo/truth/odom"),
            map_frame=as_str(runtime.get("map_frame"), as_str(runtime.get("map_frame_id"), "map")),
            odom_frame=as_str(runtime.get("odom_frame"), as_str(runtime.get("odom_frame_id"), "odom")),
            laser_frame=as_str(runtime.get("laser_frame"), as_str(runtime.get("laser_frame_id"), "laser_frame")),
            imu_frame=as_str(runtime.get("imu_frame"), as_str(runtime.get("imu_frame_id"), "imu_link")),
            base_frame=as_str(runtime.get("base_frame"), as_str(runtime.get("base_frame_id"), "base_link")),
            laser_x=as_str(runtime.get("laser_x"), "0"),
            laser_y=as_str(runtime.get("laser_y"), "0"),
            laser_z=as_str(runtime.get("laser_z"), "0"),
            laser_roll=as_str(runtime.get("laser_roll"), "0"),
            laser_pitch=as_str(runtime.get("laser_pitch"), "0"),
            laser_yaw=as_str(runtime.get("laser_yaw"), "0"),
        )

    @property
    def uses_diagnostic_truth_for_external_nav(self) -> bool:
        return self.external_nav_input_odom_topic == self.gazebo_truth_odom_topic

    def launch_argument_map(self) -> dict[str, Any]:
        return {
            "imu_source_mode": self.imu_source_mode,
            "use_sim_time": self.use_sim_time,
            "imu_source_topic": self.imu_source_topic,
            "imu_source_label": self.imu_source_label,
            "imu_min_input_rate_hz": self.imu_min_input_rate_hz,
            "publish_placeholder_odom": self.publish_placeholder_odom,
            "launch_fake_odom": self.launch_fake_odom,
            "launch_cartographer_backend": self.launch_cartographer_backend,
            "cartographer_configuration_directory": self.cartographer_configuration_directory,
            "cartographer_configuration_basename": self.cartographer_configuration_basename,
            "scan_topic": self.scan_topic,
            "imu_topic": self.imu_topic,
            "cartographer_odometry_topic": self.cartographer_odometry_topic,
            "cartographer_tf_topic": self.cartographer_tf_topic,
            "publish_global_tf": self.publish_global_tf,
            "global_tf_topic": self.global_tf_topic,
            "cached_odom_publish_rate_hz": self.cached_odom_publish_rate_hz,
            "odom_source_mode": self.odom_source_mode,
            "odom_topic": self.odom_topic,
            "slam_status_topic": self.slam_status_topic,
            "external_nav_status_topic": self.external_nav_status_topic,
            "map_frame": self.map_frame,
            "odom_frame": self.odom_frame,
            "laser_frame": self.laser_frame,
            "imu_frame": self.imu_frame,
            "base_frame": self.base_frame,
            "laser_x": self.laser_x,
            "laser_y": self.laser_y,
            "laser_z": self.laser_z,
            "laser_roll": self.laser_roll,
            "laser_pitch": self.laser_pitch,
            "laser_yaw": self.laser_yaw,
            "require_imu_for_external_nav": self.require_imu_for_external_nav,
            "external_nav_input_odom_topic": self.external_nav_input_odom_topic,
            "require_height_for_external_nav": self.require_height_for_external_nav,
        }


def ros_launch_bool(value: bool) -> str:
    return "true" if value else "false"


def launch_value(value: Any) -> str:
    if isinstance(value, bool):
        return ros_launch_bool(value)
    return str(value)
