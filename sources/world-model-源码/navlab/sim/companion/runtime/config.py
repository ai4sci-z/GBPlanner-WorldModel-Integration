from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

from navlab.common.toml_values import (
    FloatWithSource,
    ValueWithSource,
    as_bool,
    as_str,
    load_navlab_config,
    nested_section,
    resolve_float_value,
    resolve_navlab_config_file,
    resolve_str_value,
    section,
)

DEFAULT_CONFIG = Path("navlab/config.toml")
DEFAULT_NAVLAB_COMPANION_IMAGE = "navlab/companion:humble-latest"
DEFAULT_STOP_DISTANCE = 0.5
DEFAULT_CONSOLE_LOG_LEVEL = "DEBUG"
DEFAULT_FILE_LOG_LEVEL = "INFO"
DEFAULT_WORLD_POSE_TOPIC = "/sim/uav_pose"
DEFAULT_WORLD_FRAME_ID = "navlab_world"
DEFAULT_WORLD_FILE = "/workspace/docker/worlds/navlab_iq_quad_figure8.sdf"
DEFAULT_GAZEBO_TRUTH_GZ_POSE_TOPIC = "/world/navlab_iq_quad_figure8/dynamic_pose/info"
DEFAULT_GAZEBO_TRUTH_TF_TOPIC = "/gazebo/tf"


def _float(value: Any, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _append_flag(argv: list[str], flag: str, value: str | int | float) -> None:
    argv.extend([flag, str(value)])


def _append_optional_flag(argv: list[str], flag: str, value: str) -> None:
    if value:
        argv.extend([flag, value])


def _append_bool_flag(argv: list[str], flag: str, value: bool) -> None:
    if value:
        argv.append(flag)


def _append_boolean_optional_flag(argv: list[str], flag: str, value: bool) -> None:
    argv.append(flag if value else f"--no-{flag.removeprefix('--')}")


@dataclass(frozen=True, slots=True)
class RuntimeNodeConfig:
    autostart: bool = True


@dataclass(frozen=True, slots=True)
class EndpointNodeConfig(RuntimeNodeConfig):
    endpoint: str = ""


@dataclass(frozen=True, slots=True)
class WorldMarkersConfig(RuntimeNodeConfig):
    world_file: str = DEFAULT_WORLD_FILE
    topic: str = "/sim/markers"
    pose_topic: str = DEFAULT_WORLD_POSE_TOPIC
    frame_id: str = DEFAULT_WORLD_FRAME_ID
    root_model_name: str = "navlab_iq_quad"
    rate_hz: float = 1.0

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> WorldMarkersConfig:
        return cls(
            autostart=as_bool(data.get("autostart"), True),
            world_file=as_str(data.get("world_file"), DEFAULT_WORLD_FILE),
            topic=as_str(data.get("topic"), "/sim/markers"),
            pose_topic=as_str(data.get("pose_topic"), DEFAULT_WORLD_POSE_TOPIC),
            frame_id=as_str(data.get("frame_id"), DEFAULT_WORLD_FRAME_ID),
            root_model_name=as_str(data.get("root_model_name"), "navlab_iq_quad"),
            rate_hz=_float(data.get("rate_hz"), 1.0),
        )

    def argv(self) -> list[str]:
        argv: list[str] = []
        _append_flag(argv, "--world-file", self.world_file)
        _append_flag(argv, "--topic", self.topic)
        _append_flag(argv, "--pose-topic", self.pose_topic)
        _append_flag(argv, "--frame-id", self.frame_id)
        _append_flag(argv, "--root-model-name", self.root_model_name)
        _append_flag(argv, "--rate", self.rate_hz)
        return argv


@dataclass(frozen=True, slots=True)
class ScanFeaturesConfig(RuntimeNodeConfig):
    scan_topic: str = "/scan"
    features_topic: str = "/scan_features"
    nearest_point_topic: str = "/scan_nearest_point"
    front_center_deg: float = 0.0
    left_center_deg: float = 90.0
    right_center_deg: float = -90.0
    rear_center_deg: float = 180.0
    front_half_width_deg: float = 15.0
    side_half_width_deg: float = 20.0
    rear_half_width_deg: float = 20.0

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> ScanFeaturesConfig:
        return cls(
            autostart=as_bool(data.get("autostart"), True),
            scan_topic=as_str(data.get("scan_topic"), "/scan"),
            features_topic=as_str(data.get("features_topic"), "/scan_features"),
            nearest_point_topic=as_str(data.get("nearest_point_topic"), "/scan_nearest_point"),
            front_center_deg=_float(data.get("front_center_deg"), 0.0),
            left_center_deg=_float(data.get("left_center_deg"), 90.0),
            right_center_deg=_float(data.get("right_center_deg"), -90.0),
            rear_center_deg=_float(data.get("rear_center_deg"), 180.0),
            front_half_width_deg=_float(data.get("front_half_width_deg"), 15.0),
            side_half_width_deg=_float(data.get("side_half_width_deg"), 20.0),
            rear_half_width_deg=_float(data.get("rear_half_width_deg"), 20.0),
        )

    def argv(self) -> list[str]:
        argv: list[str] = []
        _append_flag(argv, "--scan-topic", self.scan_topic)
        _append_flag(argv, "--features-topic", self.features_topic)
        _append_flag(argv, "--nearest-point-topic", self.nearest_point_topic)
        _append_flag(argv, "--front-center-deg", self.front_center_deg)
        _append_flag(argv, "--left-center-deg", self.left_center_deg)
        _append_flag(argv, "--right-center-deg", self.right_center_deg)
        _append_flag(argv, "--rear-center-deg", self.rear_center_deg)
        _append_flag(argv, "--front-half-width-deg", self.front_half_width_deg)
        _append_flag(argv, "--side-half-width-deg", self.side_half_width_deg)
        _append_flag(argv, "--rear-half-width-deg", self.rear_half_width_deg)
        return argv


@dataclass(frozen=True, slots=True)
class GazeboTruthBridgeConfig(RuntimeNodeConfig):
    bridge: str = f"{DEFAULT_GAZEBO_TRUTH_GZ_POSE_TOPIC}@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V"
    ros_topic: str = DEFAULT_GAZEBO_TRUTH_TF_TOPIC

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> GazeboTruthBridgeConfig:
        return cls(
            autostart=as_bool(data.get("autostart"), True),
            bridge=as_str(
                data.get("bridge"), f"{DEFAULT_GAZEBO_TRUTH_GZ_POSE_TOPIC}@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V"
            ),
            ros_topic=as_str(data.get("ros_topic"), DEFAULT_GAZEBO_TRUTH_TF_TOPIC),
        )

    def command(self) -> list[str]:
        gz_topic = self.bridge.split("@", 1)[0]
        return [
            "ros2",
            "run",
            "ros_gz_bridge",
            "parameter_bridge",
            self.bridge,
            "--ros-args",
            "-r",
            f"{gz_topic}:={self.ros_topic}",
        ]


@dataclass(frozen=True, slots=True)
class GazeboTruthOdomConfig(RuntimeNodeConfig):
    input_topic: str = DEFAULT_GAZEBO_TRUTH_TF_TOPIC
    odom_topic: str = "/gazebo/truth/odom"
    status_topic: str = "/gazebo/truth/status"
    frame_id: str = "odom"
    child_frame_id: str = "base_link"
    gazebo_child_frame_id: str = ""
    transform_index: int = 0
    timeout_sec: float = 1.0

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> GazeboTruthOdomConfig:
        return cls(
            autostart=as_bool(data.get("autostart"), True),
            input_topic=as_str(data.get("input_topic"), DEFAULT_GAZEBO_TRUTH_TF_TOPIC),
            odom_topic=as_str(data.get("odom_topic"), "/gazebo/truth/odom"),
            status_topic=as_str(data.get("status_topic"), "/gazebo/truth/status"),
            frame_id=as_str(data.get("frame_id"), "odom"),
            child_frame_id=as_str(data.get("child_frame_id"), "base_link"),
            gazebo_child_frame_id=as_str(data.get("gazebo_child_frame_id"), ""),
            transform_index=_int(data.get("transform_index"), 0),
            timeout_sec=_float(data.get("timeout_sec"), 1.0),
        )

    def argv(self) -> list[str]:
        argv: list[str] = []
        _append_flag(argv, "--input-topic", self.input_topic)
        _append_flag(argv, "--odom-topic", self.odom_topic)
        _append_flag(argv, "--status-topic", self.status_topic)
        _append_flag(argv, "--frame-id", self.frame_id)
        _append_flag(argv, "--child-frame-id", self.child_frame_id)
        _append_optional_flag(argv, "--gazebo-child-frame-id", self.gazebo_child_frame_id)
        _append_flag(argv, "--transform-index", self.transform_index)
        _append_flag(argv, "--timeout-sec", self.timeout_sec)
        return argv


@dataclass(frozen=True, slots=True)
class PoseMirrorConfig(EndpointNodeConfig):
    pose_topic: str = DEFAULT_WORLD_POSE_TOPIC
    pose_frame_id: str = DEFAULT_WORLD_FRAME_ID
    map_frame_id: str = "map"
    odom_frame_id: str = ""
    sensor_base_frame_id: str = "navlab_replay_base_link"
    replay_base_frame_id: str = "navlab_replay_base_link"
    replay_base_parent_frame_id: str = DEFAULT_WORLD_FRAME_ID
    laser_frame_id: str = "navlab_replay_laser_frame"
    replay_imu_frame_id: str = "navlab_replay_imu_link"
    laser_x_m: float = 0.05
    laser_y_m: float = 0.0
    laser_z_m: float = 0.12
    laser_yaw_rad: float = 0.0
    constraint_list_topic: str = "/constraint_list"
    replay_constraints_topic: str = "/navlab/replay/constraint_markers"
    status_topic: str = "/navlab/pose_mirror/status"
    mavlink_status_topic: str = "/navlab/mavlink/status"
    fallback_pose_topic: str = "/navlab/fcu/local_position_pose"
    imu_topic: str = "/navlab/fcu_imu/data"
    imu_status_topic: str = "/navlab/fcu_imu/status"
    imu_frame_id: str = "imu_link"
    imu_source_label: str = "fcu_mavlink_navlab"
    imu_stamp_source_topic: str = "/scan"
    imu_min_rate_hz: float = 4.0
    allow_raw_imu: bool = False
    synthetic_imu_when_mavlink_missing: bool = True
    rate_hz: float = 10.0
    stream_rate_hz: float = 10.0
    timeout_sec: float = 1.0
    reconnect_sec: float = 2.0
    stale_reconnect_sec: float = 5.0
    z_offset_m: float = 0.0
    min_z_m: float = 0.1

    @classmethod
    def from_toml(cls, data: dict[str, Any], *, imu_source_label: str) -> PoseMirrorConfig:
        frames = nested_section(data, "frames")
        laser_mount = nested_section(data, "laser_mount")
        imu = nested_section(data, "imu")
        timing = nested_section(data, "timing")
        return cls(
            autostart=as_bool(data.get("autostart"), True),
            endpoint=as_str(data.get("endpoint"), "tcp:mavlink-router:5760"),
            pose_topic=as_str(data.get("pose_topic"), DEFAULT_WORLD_POSE_TOPIC),
            pose_frame_id=as_str(frames.get("pose_frame_id"), DEFAULT_WORLD_FRAME_ID),
            map_frame_id=as_str(frames.get("map_frame_id"), "map"),
            odom_frame_id=as_str(frames.get("odom_frame_id"), ""),
            sensor_base_frame_id=as_str(frames.get("sensor_base_frame_id"), "navlab_replay_base_link"),
            replay_base_frame_id=as_str(frames.get("replay_base_frame_id"), "navlab_replay_base_link"),
            replay_base_parent_frame_id=as_str(frames.get("replay_base_parent_frame_id"), DEFAULT_WORLD_FRAME_ID),
            laser_frame_id=as_str(frames.get("laser_frame_id"), "navlab_replay_laser_frame"),
            replay_imu_frame_id=as_str(frames.get("replay_imu_frame_id"), "navlab_replay_imu_link"),
            imu_frame_id=as_str(imu.get("frame_id"), "imu_link"),
            laser_x_m=_float(laser_mount.get("x_m"), 0.05),
            laser_y_m=_float(laser_mount.get("y_m"), 0.0),
            laser_z_m=_float(laser_mount.get("z_m"), 0.12),
            laser_yaw_rad=_float(laser_mount.get("yaw_rad"), 0.0),
            constraint_list_topic=as_str(data.get("constraint_list_topic"), "/constraint_list"),
            replay_constraints_topic=as_str(data.get("replay_constraints_topic"), "/navlab/replay/constraint_markers"),
            status_topic=as_str(data.get("status_topic"), "/navlab/pose_mirror/status"),
            mavlink_status_topic=as_str(data.get("mavlink_status_topic"), "/navlab/mavlink/status"),
            fallback_pose_topic=as_str(data.get("fallback_pose_topic"), "/navlab/fcu/local_position_pose"),
            imu_topic=as_str(imu.get("topic"), "/navlab/fcu_imu/data"),
            imu_status_topic=as_str(imu.get("status_topic"), "/navlab/fcu_imu/status"),
            imu_source_label=as_str(imu.get("source_label"), imu_source_label),
            imu_stamp_source_topic=as_str(imu.get("stamp_source_topic"), "/scan"),
            imu_min_rate_hz=_float(imu.get("min_rate_hz"), 4.0),
            allow_raw_imu=as_bool(imu.get("allow_raw"), False),
            synthetic_imu_when_mavlink_missing=as_bool(imu.get("synthetic_when_mavlink_missing"), True),
            rate_hz=_float(timing.get("rate_hz"), 10.0),
            stream_rate_hz=_float(timing.get("stream_rate_hz"), 10.0),
            timeout_sec=_float(timing.get("timeout_sec"), 1.0),
            reconnect_sec=_float(timing.get("reconnect_sec"), 2.0),
            stale_reconnect_sec=_float(timing.get("stale_reconnect_sec"), 5.0),
            z_offset_m=_float(data.get("z_offset_m"), 0.0),
            min_z_m=_float(data.get("min_z_m"), 0.1),
        )

    def argv(self) -> list[str]:
        argv: list[str] = []
        _append_flag(argv, "--endpoint", self.endpoint)
        _append_flag(argv, "--pose-topic", self.pose_topic)
        _append_flag(argv, "--pose-frame-id", self.pose_frame_id)
        _append_flag(argv, "--map-frame-id", self.map_frame_id)
        _append_flag(argv, "--odom-frame-id", self.odom_frame_id)
        _append_flag(argv, "--sensor-base-frame-id", self.sensor_base_frame_id)
        _append_flag(argv, "--replay-base-frame-id", self.replay_base_frame_id)
        _append_flag(argv, "--replay-base-parent-frame-id", self.replay_base_parent_frame_id)
        _append_flag(argv, "--laser-frame-id", self.laser_frame_id)
        _append_flag(argv, "--replay-imu-frame-id", self.replay_imu_frame_id)
        _append_flag(argv, "--laser-x-m", self.laser_x_m)
        _append_flag(argv, "--laser-y-m", self.laser_y_m)
        _append_flag(argv, "--laser-z-m", self.laser_z_m)
        _append_flag(argv, "--laser-yaw-rad", self.laser_yaw_rad)
        _append_flag(argv, "--constraint-list-topic", self.constraint_list_topic)
        _append_flag(argv, "--replay-constraints-topic", self.replay_constraints_topic)
        _append_flag(argv, "--status-topic", self.status_topic)
        _append_flag(argv, "--mavlink-status-topic", self.mavlink_status_topic)
        _append_optional_flag(argv, "--fallback-pose-topic", self.fallback_pose_topic)
        _append_flag(argv, "--imu-topic", self.imu_topic)
        _append_flag(argv, "--imu-status-topic", self.imu_status_topic)
        _append_flag(argv, "--imu-frame-id", self.imu_frame_id)
        _append_flag(argv, "--imu-source-label", self.imu_source_label)
        _append_optional_flag(argv, "--imu-stamp-source-topic", self.imu_stamp_source_topic)
        _append_flag(argv, "--imu-min-rate-hz", self.imu_min_rate_hz)
        _append_bool_flag(argv, "--allow-raw-imu", self.allow_raw_imu)
        _append_bool_flag(argv, "--synthetic-imu-when-mavlink-missing", self.synthetic_imu_when_mavlink_missing)
        _append_flag(argv, "--rate-hz", self.rate_hz)
        _append_flag(argv, "--stream-rate-hz", self.stream_rate_hz)
        _append_flag(argv, "--timeout-sec", self.timeout_sec)
        _append_flag(argv, "--reconnect-sec", self.reconnect_sec)
        _append_flag(argv, "--stale-reconnect-sec", self.stale_reconnect_sec)
        _append_flag(argv, "--z-offset-m", self.z_offset_m)
        _append_flag(argv, "--min-z-m", self.min_z_m)
        return argv


@dataclass(frozen=True, slots=True)
class ImuBridgeConfig(EndpointNodeConfig):
    imu_topic: str = "/imu/data"
    status_topic: str = "/imu/status"
    frame_id: str = "fcu_imu"
    source_label: str = "fcu_mavlink"
    rate_hz: float = 50.0
    stream_rate_hz: float = 50.0
    timeout_sec: float = 0.5
    min_rate_hz: float = 4.0
    allow_raw_imu: bool = False

    @classmethod
    def from_toml(cls, data: dict[str, Any], *, imu_source_label: str) -> ImuBridgeConfig:
        return cls(
            autostart=as_bool(data.get("autostart"), False),
            endpoint=as_str(data.get("endpoint"), "tcp:mavlink-router:5760"),
            imu_topic=as_str(data.get("imu_topic"), "/imu/data"),
            status_topic=as_str(data.get("status_topic"), "/imu/status"),
            frame_id=as_str(data.get("frame_id"), "fcu_imu"),
            source_label=as_str(data.get("source_label"), imu_source_label),
            rate_hz=_float(data.get("rate_hz"), 50.0),
            stream_rate_hz=_float(data.get("stream_rate_hz"), 50.0),
            timeout_sec=_float(data.get("timeout_sec"), 0.5),
            min_rate_hz=_float(data.get("min_rate_hz"), 4.0),
            allow_raw_imu=as_bool(data.get("allow_raw_imu"), False),
        )

    def argv(self) -> list[str]:
        argv: list[str] = []
        _append_flag(argv, "--endpoint", self.endpoint)
        _append_flag(argv, "--imu-topic", self.imu_topic)
        _append_flag(argv, "--status-topic", self.status_topic)
        _append_flag(argv, "--frame-id", self.frame_id)
        _append_flag(argv, "--source-label", self.source_label)
        _append_flag(argv, "--rate-hz", self.rate_hz)
        _append_flag(argv, "--stream-rate-hz", self.stream_rate_hz)
        _append_flag(argv, "--timeout-sec", self.timeout_sec)
        _append_flag(argv, "--min-rate-hz", self.min_rate_hz)
        _append_bool_flag(argv, "--allow-raw-imu", self.allow_raw_imu)
        return argv


@dataclass(frozen=True, slots=True)
class ExternalNavSenderConfig(EndpointNodeConfig):
    odom_topic: str = "/external_nav/odom"
    status_topic: str = "/mavlink_external_nav/status"
    rate_hz: float = 20.0
    quality: int = 100
    reset_counter: int = 0
    source_system: int = 191
    use_fcu_roll_pitch: bool = True
    local_position_pose_topic: str = "/navlab/fcu/local_position_pose"
    max_horizontal_speed_mps: float = 0.0
    max_yaw_rate_radps: float = 0.0

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> ExternalNavSenderConfig:
        return cls(
            autostart=as_bool(data.get("autostart"), True),
            endpoint=as_str(data.get("endpoint"), "tcp:127.0.0.1:5762"),
            odom_topic=as_str(data.get("odom_topic"), "/external_nav/odom"),
            status_topic=as_str(data.get("status_topic"), "/mavlink_external_nav/status"),
            rate_hz=_float(data.get("rate_hz"), 20.0),
            quality=_int(data.get("quality"), 100),
            reset_counter=_int(data.get("reset_counter"), 0),
            source_system=_int(data.get("source_system"), 191),
            use_fcu_roll_pitch=as_bool(data.get("use_fcu_roll_pitch"), True),
            local_position_pose_topic=as_str(data.get("local_position_pose_topic"), "/navlab/fcu/local_position_pose"),
            max_horizontal_speed_mps=_float(data.get("max_horizontal_speed_mps"), 0.0),
            max_yaw_rate_radps=_float(data.get("max_yaw_rate_radps"), 0.0),
        )

    def argv(self) -> list[str]:
        argv: list[str] = []
        _append_flag(argv, "--endpoint", self.endpoint)
        _append_flag(argv, "--odom-topic", self.odom_topic)
        _append_flag(argv, "--status-topic", self.status_topic)
        _append_flag(argv, "--rate-hz", self.rate_hz)
        _append_flag(argv, "--quality", self.quality)
        _append_flag(argv, "--reset-counter", self.reset_counter)
        _append_flag(argv, "--source-system", self.source_system)
        _append_bool_flag(argv, "--use-fcu-roll-pitch", self.use_fcu_roll_pitch)
        _append_optional_flag(argv, "--local-position-pose-topic", self.local_position_pose_topic)
        _append_flag(argv, "--max-horizontal-speed-mps", self.max_horizontal_speed_mps)
        _append_flag(argv, "--max-yaw-rate-radps", self.max_yaw_rate_radps)
        return argv


@dataclass(frozen=True, slots=True)
class MissionNodeConfig(EndpointNodeConfig):
    duration_sec: float = 90.0
    summary_file: str = ""
    mode: str = "GUIDED"
    takeoff_alt_m: float = 0.30
    min_airborne_alt_m: float = 0.10
    preflight_ready_sec: float = 5.0
    hover_settle_sec: float = 2.0
    hover_altitude_tolerance_m: float = 0.18
    hover_hold_sec: float = 20.0
    max_horizontal_drift_m: float = 1.0
    hover_span_target_m: float = 1.0
    hover_span_hard_cap_m: float = 1.0
    max_altitude_drift_m: float = 0.6
    origin_lat_deg: float = -35.363262
    origin_lon_deg: float = 149.165237
    origin_alt_m: float = 584.0
    source_system: int = 255
    source_component: int = 190
    status_topic: str = "/navlab/mission/status"
    landing_status_topic: str = "/navlab/landing/status"
    landing_intent_topic: str = "/navlab/landing/intent"
    sim_log_topic: str = "/sim/log"
    external_nav_status_topic: str = "/external_nav/status"
    imu_status_topic: str = "/imu/status"
    mavlink_status_topic: str = "/navlab/mavlink/status"
    status_timeout_sec: float = 1.0
    setpoint_rate_hz: float = 5.0
    landing_policy: str = "ap_land_mode_after_hover"
    pre_land_hold_sec: float = 2.0
    max_landing_duration_sec: float = 35.0
    landing_setpoint_lookahead_sec: float = 0.5
    touchdown_altitude_m: float = 0.12
    touchdown_vertical_speed_mps: float = 0.08
    force_disarm_grace_sec: float = 3.0
    require_external_nav: bool = True
    require_imu_status: bool = True
    require_disarm: bool = True
    require_motors_safe: bool = True
    send_position_setpoints: bool = True
    disable_arming_checks: bool = True
    force_arm: bool = True
    simulate_mode_arm: bool = False

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> MissionNodeConfig:
        return cls(
            autostart=as_bool(data.get("autostart"), False),
            endpoint=as_str(data.get("endpoint"), "tcp:127.0.0.1:5763"),
            duration_sec=_float(data.get("duration_sec"), 90.0),
            summary_file=as_str(data.get("summary_file"), ""),
            mode=as_str(data.get("mode"), "GUIDED"),
            takeoff_alt_m=_float(data.get("takeoff_alt_m"), 0.30),
            min_airborne_alt_m=_float(data.get("min_airborne_alt_m"), 0.10),
            preflight_ready_sec=_float(data.get("preflight_ready_sec"), 5.0),
            hover_settle_sec=_float(data.get("hover_settle_sec"), 2.0),
            hover_altitude_tolerance_m=_float(data.get("hover_altitude_tolerance_m"), 0.18),
            hover_hold_sec=_float(data.get("hover_hold_sec"), 20.0),
            max_horizontal_drift_m=_float(data.get("max_horizontal_drift_m"), 1.0),
            hover_span_target_m=_float(
                data.get("hover_span_target_m"),
                _float(data.get("max_horizontal_drift_m"), 1.0),
            ),
            hover_span_hard_cap_m=_float(
                data.get("hover_span_hard_cap_m"),
                _float(data.get("max_horizontal_drift_m"), 1.0),
            ),
            max_altitude_drift_m=_float(data.get("max_altitude_drift_m"), 0.6),
            origin_lat_deg=_float(data.get("origin_lat_deg"), -35.363262),
            origin_lon_deg=_float(data.get("origin_lon_deg"), 149.165237),
            origin_alt_m=_float(data.get("origin_alt_m"), 584.0),
            source_system=_int(data.get("source_system"), 255),
            source_component=_int(data.get("source_component"), 190),
            status_topic=as_str(data.get("status_topic"), "/navlab/mission/status"),
            landing_status_topic=as_str(data.get("landing_status_topic"), "/navlab/landing/status"),
            landing_intent_topic=as_str(data.get("landing_intent_topic"), "/navlab/landing/intent"),
            sim_log_topic=as_str(data.get("sim_log_topic"), "/sim/log"),
            external_nav_status_topic=as_str(data.get("external_nav_status_topic"), "/external_nav/status"),
            imu_status_topic=as_str(data.get("imu_status_topic"), "/imu/status"),
            mavlink_status_topic=as_str(data.get("mavlink_status_topic"), "/navlab/mavlink/status"),
            status_timeout_sec=_float(data.get("status_timeout_sec"), 1.0),
            setpoint_rate_hz=_float(data.get("setpoint_rate_hz"), 5.0),
            landing_policy=as_str(data.get("landing_policy"), "ap_land_mode_after_hover"),
            pre_land_hold_sec=_float(data.get("pre_land_hold_sec"), 2.0),
            max_landing_duration_sec=_float(data.get("max_landing_duration_sec"), 35.0),
            landing_setpoint_lookahead_sec=_float(data.get("landing_setpoint_lookahead_sec"), 0.5),
            touchdown_altitude_m=_float(data.get("touchdown_altitude_m"), 0.12),
            touchdown_vertical_speed_mps=_float(data.get("touchdown_vertical_speed_mps"), 0.08),
            force_disarm_grace_sec=_float(data.get("force_disarm_grace_sec"), 3.0),
            require_external_nav=as_bool(data.get("require_external_nav"), True),
            require_imu_status=as_bool(data.get("require_imu_status"), True),
            require_disarm=as_bool(data.get("require_disarm"), True),
            require_motors_safe=as_bool(data.get("require_motors_safe"), True),
            send_position_setpoints=as_bool(data.get("send_position_setpoints"), True),
            disable_arming_checks=as_bool(data.get("disable_arming_checks"), True),
            force_arm=as_bool(data.get("force_arm"), True),
            simulate_mode_arm=as_bool(data.get("simulate_mode_arm"), False),
        )

    def argv(self, *, duration_sec: float | None = None, summary_file: str | None = None) -> list[str]:
        argv: list[str] = []
        _append_flag(argv, "--endpoint", self.endpoint)
        _append_flag(argv, "--duration-sec", self.duration_sec if duration_sec is None else duration_sec)
        _append_optional_flag(argv, "--summary-file", self.summary_file if summary_file is None else summary_file)
        _append_flag(argv, "--mode", self.mode)
        _append_flag(argv, "--takeoff-alt-m", self.takeoff_alt_m)
        _append_flag(argv, "--min-airborne-alt-m", self.min_airborne_alt_m)
        _append_flag(argv, "--preflight-ready-sec", self.preflight_ready_sec)
        _append_flag(argv, "--hover-settle-sec", self.hover_settle_sec)
        _append_flag(argv, "--hover-altitude-tolerance-m", self.hover_altitude_tolerance_m)
        _append_flag(argv, "--hover-hold-sec", self.hover_hold_sec)
        _append_flag(argv, "--max-horizontal-drift-m", self.max_horizontal_drift_m)
        _append_flag(argv, "--hover-span-target-m", self.hover_span_target_m)
        _append_flag(argv, "--hover-span-hard-cap-m", self.hover_span_hard_cap_m)
        _append_flag(argv, "--max-altitude-drift-m", self.max_altitude_drift_m)
        _append_flag(argv, "--origin-lat-deg", self.origin_lat_deg)
        _append_flag(argv, "--origin-lon-deg", self.origin_lon_deg)
        _append_flag(argv, "--origin-alt-m", self.origin_alt_m)
        _append_flag(argv, "--source-system", self.source_system)
        _append_flag(argv, "--source-component", self.source_component)
        _append_flag(argv, "--status-topic", self.status_topic)
        _append_flag(argv, "--landing-status-topic", self.landing_status_topic)
        _append_flag(argv, "--landing-intent-topic", self.landing_intent_topic)
        _append_flag(argv, "--sim-log-topic", self.sim_log_topic)
        _append_flag(argv, "--external-nav-status-topic", self.external_nav_status_topic)
        _append_flag(argv, "--imu-status-topic", self.imu_status_topic)
        _append_flag(argv, "--mavlink-status-topic", self.mavlink_status_topic)
        _append_flag(argv, "--status-timeout-sec", self.status_timeout_sec)
        _append_flag(argv, "--setpoint-rate-hz", self.setpoint_rate_hz)
        _append_flag(argv, "--landing-policy", self.landing_policy)
        _append_flag(argv, "--pre-land-hold-sec", self.pre_land_hold_sec)
        _append_flag(argv, "--max-landing-duration-sec", self.max_landing_duration_sec)
        _append_flag(argv, "--landing-setpoint-lookahead-sec", self.landing_setpoint_lookahead_sec)
        _append_flag(argv, "--touchdown-altitude-m", self.touchdown_altitude_m)
        _append_flag(argv, "--touchdown-vertical-speed-mps", self.touchdown_vertical_speed_mps)
        _append_flag(argv, "--force-disarm-grace-sec", self.force_disarm_grace_sec)
        _append_boolean_optional_flag(argv, "--require-external-nav", self.require_external_nav)
        _append_boolean_optional_flag(argv, "--require-imu-status", self.require_imu_status)
        _append_boolean_optional_flag(argv, "--require-disarm", self.require_disarm)
        _append_boolean_optional_flag(argv, "--require-motors-safe", self.require_motors_safe)
        _append_boolean_optional_flag(argv, "--send-position-setpoints", self.send_position_setpoints)
        _append_boolean_optional_flag(argv, "--disable-arming-checks", self.disable_arming_checks)
        _append_bool_flag(argv, "--force-arm", self.force_arm)
        _append_bool_flag(argv, "--simulate-mode-arm", self.simulate_mode_arm)
        return argv


@dataclass(slots=True)
class CompanionConfig:
    stop_distance: FloatWithSource
    console_log_level: ValueWithSource
    file_log_level: ValueWithSource


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    path: Path
    imu_source_label: str
    world_markers: WorldMarkersConfig
    scan_features: ScanFeaturesConfig
    gazebo_truth_bridge: GazeboTruthBridgeConfig
    gazebo_truth_odom: GazeboTruthOdomConfig
    pose_mirror: PoseMirrorConfig
    imu_bridge: ImuBridgeConfig
    external_nav_sender: ExternalNavSenderConfig
    mission: MissionNodeConfig

    @classmethod
    def load(cls, path: str | Path | None = None) -> RuntimeConfig:
        config_path = resolve_config_path(path)
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        runtime = nested_section(data, "companion", "runtime")
        imu_source_label = as_str(runtime.get("imu_source_label"), "fcu_mavlink_navlab")
        return cls(
            path=config_path,
            imu_source_label=imu_source_label,
            world_markers=WorldMarkersConfig.from_toml(nested_section(runtime, "world_markers")),
            scan_features=ScanFeaturesConfig.from_toml(nested_section(runtime, "scan_features")),
            gazebo_truth_bridge=GazeboTruthBridgeConfig.from_toml(nested_section(runtime, "gazebo_truth_bridge")),
            gazebo_truth_odom=GazeboTruthOdomConfig.from_toml(nested_section(runtime, "gazebo_truth_odom")),
            pose_mirror=PoseMirrorConfig.from_toml(
                nested_section(runtime, "pose_mirror"),
                imu_source_label=imu_source_label,
            ),
            imu_bridge=ImuBridgeConfig.from_toml(
                nested_section(runtime, "imu_bridge"),
                imu_source_label=imu_source_label,
            ),
            external_nav_sender=ExternalNavSenderConfig.from_toml(nested_section(runtime, "external_nav_sender")),
            mission=MissionNodeConfig.from_toml(nested_section(runtime, "mission")),
        )


def resolve_config_path(path: str | Path | None = None) -> Path:
    raw = path or os.environ.get("NAVLAB_RUNTIME_CONFIG") or DEFAULT_CONFIG
    return resolve_navlab_config_file(raw)


def load_config(path: str | Path | None = None) -> CompanionConfig:
    config_file, config = load_navlab_config(path)
    raw_companion = section(config, "companion", path=config_file)
    raw_logging = section(raw_companion, "logging", path=config_file, default={})
    return CompanionConfig(
        stop_distance=resolve_float_value(raw_companion, "stop_distance", DEFAULT_STOP_DISTANCE),
        console_log_level=resolve_str_value(raw_logging, "console_level", DEFAULT_CONSOLE_LOG_LEVEL),
        file_log_level=resolve_str_value(raw_logging, "file_level", DEFAULT_FILE_LOG_LEVEL),
    )
