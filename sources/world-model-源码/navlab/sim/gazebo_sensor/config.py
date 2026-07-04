from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from navlab.common.toml_values import (
    BoolWithSource,
    FloatWithSource,
    ValueWithSource,
    load_navlab_config,
    resolve_bool_value,
    resolve_float_value,
    resolve_str_value,
    section,
)
from navlab.sim.gazebo_sensor.x2.emulator import X2SerialEmulatorConfig

DEFAULT_X2_PROTOCOL_ENABLED = False
DEFAULT_X2_SCAN_SOURCE = "x2_virtual_serial"
DEFAULT_X2_VENDOR_PROFILE = "/workspace/profiles/x2-vendor-sim.yaml"
DEFAULT_X2_VIRTUAL_SERIAL_LINK = "/tmp/navlab_x2"
DEFAULT_X2_SCAN_IDEAL_TOPIC = "/scan_ideal"
DEFAULT_X2_VENDOR_SCAN_TOPIC = "/navlab/x2/vendor_scan"
DEFAULT_X2_SCAN_TOPIC = "/scan"
DEFAULT_X2_STATUS_TOPIC = "/sim/x2/status"
DEFAULT_X2_SAMPLE_RATE_HZ = 3000.0
DEFAULT_X2_SCAN_FREQUENCY_HZ = 7.0
DEFAULT_X2_SCAN_FREQUENCY_MIN_HZ = 4.0
DEFAULT_X2_SCAN_FREQUENCY_MAX_HZ = 8.0
DEFAULT_X2_SCAN_FREQUENCY_JITTER_HZ = 0.0
DEFAULT_X2_RANGE_MIN_M = 0.1
DEFAULT_X2_RANGE_MAX_M = 8.0
DEFAULT_X2_STATIC_RANGE_M = 1.5
DEFAULT_X2_RANGE_NOISE_STDDEV_M = 0.0
DEFAULT_X2_RANGE_NOISE_STDDEV_PER_M = 0.0
DEFAULT_X2_DROPOUT_RATE = 0.0
DEFAULT_X2_AUTO_START = True
DEFAULT_DOWN_RANGEFINDER_ENABLED = True
DEFAULT_DOWN_RANGEFINDER_SCAN_IDEAL_TOPIC = "/rangefinder/down/scan_ideal"
DEFAULT_DOWN_RANGEFINDER_RANGE_TOPIC = "/rangefinder/down/range"
DEFAULT_DOWN_RANGEFINDER_STATUS_TOPIC = "/rangefinder/down/status"
DEFAULT_DOWN_RANGEFINDER_VIRTUAL_SERIAL_LINK = "/tmp/navlab_benewake_tfmini"
DEFAULT_DOWN_RANGEFINDER_SERIAL_BAUD = "115200"
DEFAULT_DOWN_RANGEFINDER_FRAME_ID = "rangefinder_down_frame"
DEFAULT_DOWN_RANGEFINDER_RATE_HZ = 20.0
DEFAULT_DOWN_RANGEFINDER_MIN_M = 0.05
DEFAULT_DOWN_RANGEFINDER_MAX_M = 6.0
DEFAULT_SCAN_INTEGRITY_ENABLED = False
DEFAULT_SCAN_INTEGRITY_INPUT_SCAN_TOPIC = "/navlab/x2/scan_normalized"
DEFAULT_SCAN_INTEGRITY_OUTPUT_SCAN_TOPIC = "/scan"
DEFAULT_SCAN_INTEGRITY_STATUS_TOPIC = "/navlab/scan_integrity/status"
DEFAULT_SCAN_INTEGRITY_EVENTS_TOPIC = "/navlab/scan_integrity/events"
DEFAULT_SCAN_INTEGRITY_FAULT_TOPIC = "/navlab/scan_integrity/fault_injection"
DEFAULT_SCAN_INTEGRITY_ATTITUDE_SOURCE_TOPIC = "/imu"
DEFAULT_SCAN_INTEGRITY_ATTITUDE_SOURCE_TYPE = "imu"
DEFAULT_SCAN_INTEGRITY_RANGE_TOPIC = "/rangefinder/down/range"
DEFAULT_SCAN_INTEGRITY_BASE_FRAME_ID = "base_link"
DEFAULT_SCAN_INTEGRITY_SCAN_FRAME_ID = "base_scan"
DEFAULT_SCAN_INTEGRITY_SOFT_TILT_DEG = 3.0
DEFAULT_SCAN_INTEGRITY_HARD_TILT_DEG = 6.0
DEFAULT_SCAN_INTEGRITY_MAX_DROPPED_SCAN_RATIO = 0.05
DEFAULT_SCAN_INTEGRITY_MAX_CLIPPED_BEAM_RATIO = 0.20
DEFAULT_SCAN_INTEGRITY_MAX_SCAN_ATTITUDE_OFFSET_MS = 50.0
DEFAULT_SCAN_INTEGRITY_MAX_ATTITUDE_SOURCE_AGE_MS = 250.0
DEFAULT_SCAN_INTEGRITY_MIN_ATTITUDE_RATE_HZ = 20.0
DEFAULT_SCAN_INTEGRITY_FLOOR_HIT_GUARD_RANGE_M = 8.0
DEFAULT_SCAN_INTEGRITY_MIN_LIDAR_HEIGHT_M = 0.25
DEFAULT_SCAN_INTEGRITY_MIN_DOWNWARD_RAY_Z = 0.05
DEFAULT_SCAN_STABILIZATION_ENABLED = False
DEFAULT_SCAN_STABILIZATION_MODE = "bounded_2d_projection"
DEFAULT_SCAN_STABILIZATION_INPUT_SCAN_TOPIC = "/navlab/x2/scan_normalized"
DEFAULT_SCAN_STABILIZATION_OUTPUT_SCAN_TOPIC = "/scan"
DEFAULT_SCAN_STABILIZATION_STATUS_TOPIC = "/navlab/scan_stabilization/status"
DEFAULT_SCAN_STABILIZATION_EVENTS_TOPIC = "/navlab/scan_stabilization/events"
DEFAULT_SCAN_STABILIZATION_DEBUG_SCAN_TOPIC = "/navlab/scan_stabilization/debug_scan"
DEFAULT_SCAN_STABILIZATION_FAULT_TOPIC = "/navlab/scan_stabilization/fault_injection"
DEFAULT_SCAN_STABILIZATION_ATTITUDE_SOURCE_TOPIC = "/imu"
DEFAULT_SCAN_STABILIZATION_ATTITUDE_SOURCE_TYPE = "imu"
DEFAULT_SCAN_STABILIZATION_RANGE_TOPIC = "/rangefinder/down/range"
DEFAULT_SCAN_STABILIZATION_BASE_FRAME_ID = "base_link"
DEFAULT_SCAN_STABILIZATION_SCAN_FRAME_ID = "base_scan"
DEFAULT_SCAN_STABILIZATION_PASSTHROUGH_TILT_DEG = 3.0
DEFAULT_SCAN_STABILIZATION_COMPENSATION_TILT_DEG = 8.0
DEFAULT_SCAN_STABILIZATION_HARD_DROP_TILT_DEG = 10.0
DEFAULT_SCAN_STABILIZATION_MAX_VERTICAL_ERROR_M = 0.15
DEFAULT_SCAN_STABILIZATION_MAX_REJECTED_BEAM_RATIO = 0.35
DEFAULT_SCAN_STABILIZATION_MIN_RETAINED_BEAM_RATIO = 0.55
DEFAULT_SCAN_STABILIZATION_MAX_FLOOR_HIT_RISK_RATIO = 0.05
DEFAULT_SCAN_STABILIZATION_MAX_SCAN_ATTITUDE_OFFSET_MS = 50.0
DEFAULT_SCAN_STABILIZATION_MAX_ATTITUDE_SOURCE_AGE_MS = 250.0
DEFAULT_SCAN_STABILIZATION_MIN_ATTITUDE_RATE_HZ = 20.0
DEFAULT_SCAN_STABILIZATION_MIN_STABILIZED_SCAN_RATE_HZ = 5.0

DEFAULT_AIRFRAME_DISTURBANCE_ENABLED = False
DEFAULT_AIRFRAME_DISTURBANCE_PROFILE = "clean"
DEFAULT_AIRFRAME_DISTURBANCE_INJECTION_LAYER = "gazebo_motor_model"
DEFAULT_AIRFRAME_DISTURBANCE_SEED = "12012"
DEFAULT_AIRFRAME_DISTURBANCE_MOTOR_COUNT = "4"
DEFAULT_AIRFRAME_DISTURBANCE_THRUST_MULTIPLIERS = "1.0,1.0,1.0,1.0"
DEFAULT_AIRFRAME_DISTURBANCE_ESC_LAG_MS = "0.0,0.0,0.0,0.0"
DEFAULT_AIRFRAME_DISTURBANCE_ESC_LAG_MODEL = "first_order"
DEFAULT_AIRFRAME_DISTURBANCE_THRUST_NOISE_STD = 0.0
DEFAULT_AIRFRAME_DISTURBANCE_THRUST_NOISE_CORRELATION_MS = 0.0
DEFAULT_AIRFRAME_DISTURBANCE_MOTOR_JITTER_HZ = 0.0
DEFAULT_AIRFRAME_DISTURBANCE_IMU_VIBRATION_ENABLED = False
DEFAULT_AIRFRAME_DISTURBANCE_IMU_INPUT_TOPIC = "/navlab/imu/raw"
DEFAULT_AIRFRAME_DISTURBANCE_IMU_OUTPUT_TOPIC = "/imu"
DEFAULT_AIRFRAME_DISTURBANCE_IMU_GYRO_NOISE_STD_DPS = 0.0
DEFAULT_AIRFRAME_DISTURBANCE_IMU_ACCEL_NOISE_STD_MPS2 = 0.0
DEFAULT_AIRFRAME_DISTURBANCE_IMU_VIBRATION_FREQ_HZ = 0.0
DEFAULT_AIRFRAME_DISTURBANCE_IMU_VIBRATION_ROLL_PITCH_AMP_DEG = 0.0
DEFAULT_AIRFRAME_DISTURBANCE_STATUS_TOPIC = "/navlab/airframe_disturbance/status"
DEFAULT_AIRFRAME_DISTURBANCE_EVENTS_TOPIC = "/navlab/airframe_disturbance/events"


@dataclass(slots=True)
class X2ProtocolConfig:
    enabled: BoolWithSource
    scan_source: ValueWithSource
    profile: ValueWithSource
    virtual_serial_link: ValueWithSource
    scan_ideal_topic: ValueWithSource
    vendor_scan_topic: ValueWithSource
    scan_topic: ValueWithSource
    status_topic: ValueWithSource
    sample_rate_hz: FloatWithSource
    scan_frequency_hz: FloatWithSource
    scan_frequency_min_hz: FloatWithSource
    scan_frequency_max_hz: FloatWithSource
    scan_frequency_jitter_hz: FloatWithSource
    range_min_m: FloatWithSource
    range_max_m: FloatWithSource
    static_range_m: FloatWithSource
    range_noise_stddev_m: FloatWithSource
    range_noise_stddev_per_m: FloatWithSource
    dropout_rate: FloatWithSource
    auto_start: BoolWithSource
    random_seed: ValueWithSource


@dataclass(frozen=True, slots=True)
class X2SensorRuntimeConfig:
    enabled: bool
    scan_source: str
    profile: Path
    virtual_serial_link: Path
    scan_ideal_topic: str
    vendor_scan_topic: str
    scan_topic: str
    status_topic: str
    sample_rate_hz: float
    scan_frequency_hz: float
    scan_frequency_min_hz: float
    scan_frequency_max_hz: float
    scan_frequency_jitter_hz: float
    range_min_m: float
    range_max_m: float
    static_range_m: float
    range_noise_stddev_m: float
    range_noise_stddev_per_m: float
    dropout_rate: float
    auto_start: bool
    random_seed: int | None

    @classmethod
    def load(cls) -> X2SensorRuntimeConfig:
        config = load_x2_protocol_config()
        return cls(
            enabled=config.enabled.value,
            scan_source=config.scan_source.value,
            profile=Path(config.profile.value),
            virtual_serial_link=Path(config.virtual_serial_link.value),
            scan_ideal_topic=config.scan_ideal_topic.value,
            vendor_scan_topic=config.vendor_scan_topic.value,
            scan_topic=config.scan_topic.value,
            status_topic=config.status_topic.value,
            sample_rate_hz=config.sample_rate_hz.value,
            scan_frequency_hz=config.scan_frequency_hz.value,
            scan_frequency_min_hz=config.scan_frequency_min_hz.value,
            scan_frequency_max_hz=config.scan_frequency_max_hz.value,
            scan_frequency_jitter_hz=config.scan_frequency_jitter_hz.value,
            range_min_m=config.range_min_m.value,
            range_max_m=config.range_max_m.value,
            static_range_m=config.static_range_m.value,
            range_noise_stddev_m=config.range_noise_stddev_m.value,
            range_noise_stddev_per_m=config.range_noise_stddev_per_m.value,
            dropout_rate=config.dropout_rate.value,
            auto_start=config.auto_start.value,
            random_seed=_optional_int(config.random_seed.value),
        )

    def emulator_config(self) -> X2SerialEmulatorConfig:
        return X2SerialEmulatorConfig(
            virtual_serial_link=self.virtual_serial_link,
            scan_frequency_hz=self.scan_frequency_hz,
            scan_frequency_min_hz=self.scan_frequency_min_hz,
            scan_frequency_max_hz=self.scan_frequency_max_hz,
            scan_frequency_jitter_hz=self.scan_frequency_jitter_hz,
            sample_rate_hz=self.sample_rate_hz,
            range_min_m=self.range_min_m,
            range_max_m=self.range_max_m,
            status_topic=self.status_topic,
            random_seed=self.random_seed,
        )


@dataclass(slots=True)
class DownRangefinderConfig:
    enabled: BoolWithSource
    scan_ideal_topic: ValueWithSource
    range_topic: ValueWithSource
    status_topic: ValueWithSource
    virtual_serial_link: ValueWithSource
    serial_baud: ValueWithSource
    frame_id: ValueWithSource
    rate_hz: FloatWithSource
    min_distance_m: FloatWithSource
    max_distance_m: FloatWithSource
    model_pose: ValueWithSource
    model_update_rate_hz: FloatWithSource
    model_ray_count: ValueWithSource
    model_noise_stddev_m: FloatWithSource


@dataclass(frozen=True, slots=True)
class DownRangefinderRuntimeConfig:
    enabled: bool
    scan_ideal_topic: str
    range_topic: str
    status_topic: str
    virtual_serial_link: Path
    serial_baud: int
    frame_id: str
    rate_hz: float
    min_distance_m: float
    max_distance_m: float

    @classmethod
    def load(cls) -> DownRangefinderRuntimeConfig:
        config = load_down_rangefinder_config()
        return cls(
            enabled=config.enabled.value,
            scan_ideal_topic=config.scan_ideal_topic.value,
            range_topic=config.range_topic.value,
            status_topic=config.status_topic.value,
            virtual_serial_link=Path(config.virtual_serial_link.value),
            serial_baud=_required_int(config.serial_baud.value, key="serial_baud"),
            frame_id=config.frame_id.value,
            rate_hz=config.rate_hz.value,
            min_distance_m=config.min_distance_m.value,
            max_distance_m=config.max_distance_m.value,
        )


@dataclass(slots=True)
class ScanIntegrityConfig:
    enabled: BoolWithSource
    input_scan_topic: ValueWithSource
    output_scan_topic: ValueWithSource
    status_topic: ValueWithSource
    events_topic: ValueWithSource
    fault_injection_topic: ValueWithSource
    attitude_source_topic: ValueWithSource
    attitude_source_type: ValueWithSource
    range_topic: ValueWithSource
    base_frame_id: ValueWithSource
    scan_frame_id: ValueWithSource
    soft_tilt_deg: FloatWithSource
    hard_tilt_deg: FloatWithSource
    max_dropped_scan_ratio: FloatWithSource
    max_clipped_beam_ratio: FloatWithSource
    max_scan_attitude_time_offset_ms: FloatWithSource
    max_attitude_source_age_ms: FloatWithSource
    min_attitude_rate_hz: FloatWithSource
    floor_hit_guard_range_m: FloatWithSource
    min_lidar_height_m: FloatWithSource
    min_downward_ray_z: FloatWithSource


@dataclass(frozen=True, slots=True)
class ScanIntegrityRuntimeConfig:
    enabled: bool
    input_scan_topic: str
    output_scan_topic: str
    status_topic: str
    events_topic: str
    fault_injection_topic: str
    attitude_source_topic: str
    attitude_source_type: str
    range_topic: str
    base_frame_id: str
    scan_frame_id: str
    soft_tilt_deg: float
    hard_tilt_deg: float
    max_dropped_scan_ratio: float
    max_clipped_beam_ratio: float
    max_scan_attitude_time_offset_ms: float
    max_attitude_source_age_ms: float
    min_attitude_rate_hz: float
    floor_hit_guard_range_m: float
    min_lidar_height_m: float
    min_downward_ray_z: float

    @classmethod
    def load(cls) -> ScanIntegrityRuntimeConfig:
        config = load_scan_integrity_config()
        return cls(
            enabled=config.enabled.value,
            input_scan_topic=config.input_scan_topic.value,
            output_scan_topic=config.output_scan_topic.value,
            status_topic=config.status_topic.value,
            events_topic=config.events_topic.value,
            fault_injection_topic=config.fault_injection_topic.value,
            attitude_source_topic=config.attitude_source_topic.value,
            attitude_source_type=config.attitude_source_type.value,
            range_topic=config.range_topic.value,
            base_frame_id=config.base_frame_id.value,
            scan_frame_id=config.scan_frame_id.value,
            soft_tilt_deg=config.soft_tilt_deg.value,
            hard_tilt_deg=config.hard_tilt_deg.value,
            max_dropped_scan_ratio=config.max_dropped_scan_ratio.value,
            max_clipped_beam_ratio=config.max_clipped_beam_ratio.value,
            max_scan_attitude_time_offset_ms=config.max_scan_attitude_time_offset_ms.value,
            max_attitude_source_age_ms=config.max_attitude_source_age_ms.value,
            min_attitude_rate_hz=config.min_attitude_rate_hz.value,
            floor_hit_guard_range_m=config.floor_hit_guard_range_m.value,
            min_lidar_height_m=config.min_lidar_height_m.value,
            min_downward_ray_z=config.min_downward_ray_z.value,
        )


@dataclass(slots=True)
class ScanStabilizationConfig:
    enabled: BoolWithSource
    mode: ValueWithSource
    input_scan_topic: ValueWithSource
    output_scan_topic: ValueWithSource
    status_topic: ValueWithSource
    events_topic: ValueWithSource
    debug_scan_topic: ValueWithSource
    fault_injection_topic: ValueWithSource
    attitude_source_topic: ValueWithSource
    attitude_source_type: ValueWithSource
    range_topic: ValueWithSource
    base_frame_id: ValueWithSource
    scan_frame_id: ValueWithSource
    passthrough_tilt_deg: FloatWithSource
    compensation_tilt_deg: FloatWithSource
    hard_drop_tilt_deg: FloatWithSource
    max_vertical_projection_error_m: FloatWithSource
    max_rejected_beam_ratio: FloatWithSource
    min_retained_beam_ratio: FloatWithSource
    max_floor_hit_risk_beam_ratio: FloatWithSource
    floor_hit_guard_range_m: FloatWithSource
    min_lidar_height_m: FloatWithSource
    min_downward_ray_z: FloatWithSource
    max_scan_attitude_time_offset_ms: FloatWithSource
    max_attitude_source_age_ms: FloatWithSource
    min_attitude_rate_hz: FloatWithSource
    min_stabilized_scan_rate_hz: FloatWithSource
    publish_debug_scan: BoolWithSource


@dataclass(frozen=True, slots=True)
class ScanStabilizationRuntimeConfig:
    enabled: bool
    mode: str
    input_scan_topic: str
    output_scan_topic: str
    status_topic: str
    events_topic: str
    debug_scan_topic: str
    fault_injection_topic: str
    attitude_source_topic: str
    attitude_source_type: str
    range_topic: str
    base_frame_id: str
    scan_frame_id: str
    passthrough_tilt_deg: float
    compensation_tilt_deg: float
    hard_drop_tilt_deg: float
    max_vertical_projection_error_m: float
    max_rejected_beam_ratio: float
    min_retained_beam_ratio: float
    max_floor_hit_risk_beam_ratio: float
    floor_hit_guard_range_m: float
    min_lidar_height_m: float
    min_downward_ray_z: float
    max_scan_attitude_time_offset_ms: float
    max_attitude_source_age_ms: float
    min_attitude_rate_hz: float
    min_stabilized_scan_rate_hz: float
    publish_debug_scan: bool

    @classmethod
    def load(cls) -> ScanStabilizationRuntimeConfig:
        config = load_scan_stabilization_config()
        return cls(
            enabled=config.enabled.value,
            mode=config.mode.value,
            input_scan_topic=config.input_scan_topic.value,
            output_scan_topic=config.output_scan_topic.value,
            status_topic=config.status_topic.value,
            events_topic=config.events_topic.value,
            debug_scan_topic=config.debug_scan_topic.value,
            fault_injection_topic=config.fault_injection_topic.value,
            attitude_source_topic=config.attitude_source_topic.value,
            attitude_source_type=config.attitude_source_type.value,
            range_topic=config.range_topic.value,
            base_frame_id=config.base_frame_id.value,
            scan_frame_id=config.scan_frame_id.value,
            passthrough_tilt_deg=config.passthrough_tilt_deg.value,
            compensation_tilt_deg=config.compensation_tilt_deg.value,
            hard_drop_tilt_deg=config.hard_drop_tilt_deg.value,
            max_vertical_projection_error_m=config.max_vertical_projection_error_m.value,
            max_rejected_beam_ratio=config.max_rejected_beam_ratio.value,
            min_retained_beam_ratio=config.min_retained_beam_ratio.value,
            max_floor_hit_risk_beam_ratio=config.max_floor_hit_risk_beam_ratio.value,
            floor_hit_guard_range_m=config.floor_hit_guard_range_m.value,
            min_lidar_height_m=config.min_lidar_height_m.value,
            min_downward_ray_z=config.min_downward_ray_z.value,
            max_scan_attitude_time_offset_ms=config.max_scan_attitude_time_offset_ms.value,
            max_attitude_source_age_ms=config.max_attitude_source_age_ms.value,
            min_attitude_rate_hz=config.min_attitude_rate_hz.value,
            min_stabilized_scan_rate_hz=config.min_stabilized_scan_rate_hz.value,
            publish_debug_scan=config.publish_debug_scan.value,
        )

    def validate(self) -> list[str]:
        blockers: list[str] = []
        if self.mode != "bounded_2d_projection":
            blockers.append("scan_stabilization_config_invalid: unsupported mode")
        if not (0.0 <= self.passthrough_tilt_deg < self.compensation_tilt_deg < self.hard_drop_tilt_deg):
            blockers.append("scan_stabilization_config_invalid: tilt thresholds must be ordered")
        for name, value in (
            ("max_rejected_beam_ratio", self.max_rejected_beam_ratio),
            ("min_retained_beam_ratio", self.min_retained_beam_ratio),
            ("max_floor_hit_risk_beam_ratio", self.max_floor_hit_risk_beam_ratio),
        ):
            if not (0.0 <= value <= 1.0):
                blockers.append(f"scan_stabilization_config_invalid: {name} must be in [0, 1]")
        if self.max_vertical_projection_error_m <= 0.0:
            blockers.append("scan_stabilization_config_invalid: max_vertical_projection_error_m must be positive")
        if self.max_attitude_source_age_ms <= 0.0:
            blockers.append("scan_stabilization_config_invalid: max_attitude_source_age_ms must be positive")
        if self.input_scan_topic == self.output_scan_topic:
            blockers.append("scan_stabilization_config_invalid: input and output scan topics must differ")
        return blockers

    def to_summary(self) -> dict[str, object]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


@dataclass(slots=True)
class AirframeDisturbanceConfig:
    enabled: BoolWithSource
    profile: ValueWithSource
    injection_layer: ValueWithSource
    seed: ValueWithSource
    motor_count: ValueWithSource
    thrust_multipliers: ValueWithSource
    esc_lag_ms: ValueWithSource
    esc_lag_model: ValueWithSource
    thrust_noise_std: FloatWithSource
    thrust_noise_correlation_ms: FloatWithSource
    motor_jitter_hz: FloatWithSource
    imu_vibration_enabled: BoolWithSource
    imu_input_topic: ValueWithSource
    imu_output_topic: ValueWithSource
    imu_gyro_noise_std_dps: FloatWithSource
    imu_accel_noise_std_mps2: FloatWithSource
    imu_vibration_freq_hz: FloatWithSource
    imu_vibration_roll_pitch_amp_deg: FloatWithSource
    status_topic: ValueWithSource
    events_topic: ValueWithSource


@dataclass(frozen=True, slots=True)
class AirframeDisturbanceRuntimeConfig:
    enabled: bool
    profile: str
    injection_layer: str
    seed: int
    motor_count: int
    thrust_multipliers: tuple[float, ...]
    esc_lag_ms: tuple[float, ...]
    esc_lag_model: str
    thrust_noise_std: float
    thrust_noise_correlation_ms: float
    motor_jitter_hz: float
    imu_vibration_enabled: bool
    imu_input_topic: str
    imu_output_topic: str
    imu_gyro_noise_std_dps: float
    imu_accel_noise_std_mps2: float
    imu_vibration_freq_hz: float
    imu_vibration_roll_pitch_amp_deg: float
    status_topic: str
    events_topic: str

    @classmethod
    def load(cls) -> AirframeDisturbanceRuntimeConfig:
        config = load_airframe_disturbance_config()
        return cls(
            enabled=config.enabled.value,
            profile=config.profile.value,
            injection_layer=config.injection_layer.value,
            seed=_required_int(config.seed.value, key="seed"),
            motor_count=_required_int(config.motor_count.value, key="motor_count"),
            thrust_multipliers=_float_tuple(config.thrust_multipliers.value, key="thrust_multipliers"),
            esc_lag_ms=_float_tuple(config.esc_lag_ms.value, key="esc_lag_ms"),
            esc_lag_model=config.esc_lag_model.value,
            thrust_noise_std=config.thrust_noise_std.value,
            thrust_noise_correlation_ms=config.thrust_noise_correlation_ms.value,
            motor_jitter_hz=config.motor_jitter_hz.value,
            imu_vibration_enabled=config.imu_vibration_enabled.value,
            imu_input_topic=config.imu_input_topic.value,
            imu_output_topic=config.imu_output_topic.value,
            imu_gyro_noise_std_dps=config.imu_gyro_noise_std_dps.value,
            imu_accel_noise_std_mps2=config.imu_accel_noise_std_mps2.value,
            imu_vibration_freq_hz=config.imu_vibration_freq_hz.value,
            imu_vibration_roll_pitch_amp_deg=config.imu_vibration_roll_pitch_amp_deg.value,
            status_topic=config.status_topic.value,
            events_topic=config.events_topic.value,
        )


def load_x2_protocol_config(path: str | Path | None = None) -> X2ProtocolConfig:
    config_file, config = load_navlab_config(path)
    raw_gazebo_sensor = section(config, "gazebo_sensor", path=config_file)
    raw_x2 = section(raw_gazebo_sensor, "x2_protocol", path=config_file, default={})
    return X2ProtocolConfig(
        enabled=resolve_bool_value(raw_x2, "enabled", DEFAULT_X2_PROTOCOL_ENABLED),
        scan_source=resolve_str_value(raw_x2, "scan_source", DEFAULT_X2_SCAN_SOURCE),
        profile=resolve_str_value(raw_x2, "profile", DEFAULT_X2_VENDOR_PROFILE),
        virtual_serial_link=resolve_str_value(raw_x2, "virtual_serial_link", DEFAULT_X2_VIRTUAL_SERIAL_LINK),
        scan_ideal_topic=resolve_str_value(raw_x2, "scan_ideal_topic", DEFAULT_X2_SCAN_IDEAL_TOPIC),
        vendor_scan_topic=resolve_str_value(raw_x2, "vendor_scan_topic", DEFAULT_X2_VENDOR_SCAN_TOPIC),
        scan_topic=resolve_str_value(raw_x2, "scan_topic", DEFAULT_X2_SCAN_TOPIC),
        status_topic=resolve_str_value(raw_x2, "status_topic", DEFAULT_X2_STATUS_TOPIC),
        sample_rate_hz=resolve_float_value(raw_x2, "sample_rate_hz", DEFAULT_X2_SAMPLE_RATE_HZ),
        scan_frequency_hz=resolve_float_value(raw_x2, "scan_frequency_hz", DEFAULT_X2_SCAN_FREQUENCY_HZ),
        scan_frequency_min_hz=resolve_float_value(
            raw_x2,
            "scan_frequency_min_hz",
            DEFAULT_X2_SCAN_FREQUENCY_MIN_HZ,
        ),
        scan_frequency_max_hz=resolve_float_value(
            raw_x2,
            "scan_frequency_max_hz",
            DEFAULT_X2_SCAN_FREQUENCY_MAX_HZ,
        ),
        scan_frequency_jitter_hz=resolve_float_value(
            raw_x2,
            "scan_frequency_jitter_hz",
            DEFAULT_X2_SCAN_FREQUENCY_JITTER_HZ,
        ),
        range_min_m=resolve_float_value(raw_x2, "range_min_m", DEFAULT_X2_RANGE_MIN_M),
        range_max_m=resolve_float_value(raw_x2, "range_max_m", DEFAULT_X2_RANGE_MAX_M),
        static_range_m=resolve_float_value(raw_x2, "static_range_m", DEFAULT_X2_STATIC_RANGE_M),
        range_noise_stddev_m=resolve_float_value(
            raw_x2,
            "range_noise_stddev_m",
            DEFAULT_X2_RANGE_NOISE_STDDEV_M,
        ),
        range_noise_stddev_per_m=resolve_float_value(
            raw_x2,
            "range_noise_stddev_per_m",
            DEFAULT_X2_RANGE_NOISE_STDDEV_PER_M,
        ),
        dropout_rate=resolve_float_value(raw_x2, "dropout_rate", DEFAULT_X2_DROPOUT_RATE),
        auto_start=resolve_bool_value(raw_x2, "auto_start", DEFAULT_X2_AUTO_START),
        random_seed=resolve_str_value(raw_x2, "random_seed", ""),
    )


def load_down_rangefinder_config(path: str | Path | None = None) -> DownRangefinderConfig:
    config_file, config = load_navlab_config(path)
    raw_gazebo_sensor = section(config, "gazebo_sensor", path=config_file)
    raw_rangefinder = section(raw_gazebo_sensor, "down_rangefinder", path=config_file, default={})
    return DownRangefinderConfig(
        enabled=resolve_bool_value(raw_rangefinder, "enabled", DEFAULT_DOWN_RANGEFINDER_ENABLED),
        scan_ideal_topic=resolve_str_value(
            raw_rangefinder,
            "scan_ideal_topic",
            DEFAULT_DOWN_RANGEFINDER_SCAN_IDEAL_TOPIC,
        ),
        range_topic=resolve_str_value(raw_rangefinder, "range_topic", DEFAULT_DOWN_RANGEFINDER_RANGE_TOPIC),
        status_topic=resolve_str_value(raw_rangefinder, "status_topic", DEFAULT_DOWN_RANGEFINDER_STATUS_TOPIC),
        virtual_serial_link=resolve_str_value(
            raw_rangefinder,
            "virtual_serial_link",
            DEFAULT_DOWN_RANGEFINDER_VIRTUAL_SERIAL_LINK,
        ),
        serial_baud=resolve_str_value(
            raw_rangefinder,
            "serial_baud",
            DEFAULT_DOWN_RANGEFINDER_SERIAL_BAUD,
        ),
        frame_id=resolve_str_value(raw_rangefinder, "frame_id", DEFAULT_DOWN_RANGEFINDER_FRAME_ID),
        rate_hz=resolve_float_value(raw_rangefinder, "rate_hz", DEFAULT_DOWN_RANGEFINDER_RATE_HZ),
        min_distance_m=resolve_float_value(
            raw_rangefinder,
            "min_distance_m",
            DEFAULT_DOWN_RANGEFINDER_MIN_M,
        ),
        max_distance_m=resolve_float_value(
            raw_rangefinder,
            "max_distance_m",
            DEFAULT_DOWN_RANGEFINDER_MAX_M,
        ),
        model_pose=resolve_str_value(raw_rangefinder, "model_pose", "0 0 -0.02 0 1.5707963267948966 0"),
        model_update_rate_hz=resolve_float_value(raw_rangefinder, "model_update_rate_hz", 20.0),
        model_ray_count=resolve_str_value(raw_rangefinder, "model_ray_count", "1"),
        model_noise_stddev_m=resolve_float_value(raw_rangefinder, "model_noise_stddev_m", 0.0),
    )


def load_scan_integrity_config(path: str | Path | None = None) -> ScanIntegrityConfig:
    config_file, config = load_navlab_config(path)
    raw_gazebo_sensor = section(config, "gazebo_sensor", path=config_file)
    raw_integrity = section(raw_gazebo_sensor, "scan_integrity", path=config_file, default={})
    return ScanIntegrityConfig(
        enabled=resolve_bool_value(raw_integrity, "enabled", DEFAULT_SCAN_INTEGRITY_ENABLED),
        input_scan_topic=resolve_str_value(raw_integrity, "input_scan_topic", DEFAULT_SCAN_INTEGRITY_INPUT_SCAN_TOPIC),
        output_scan_topic=resolve_str_value(
            raw_integrity, "output_scan_topic", DEFAULT_SCAN_INTEGRITY_OUTPUT_SCAN_TOPIC
        ),
        status_topic=resolve_str_value(raw_integrity, "status_topic", DEFAULT_SCAN_INTEGRITY_STATUS_TOPIC),
        events_topic=resolve_str_value(raw_integrity, "events_topic", DEFAULT_SCAN_INTEGRITY_EVENTS_TOPIC),
        fault_injection_topic=resolve_str_value(
            raw_integrity, "fault_injection_topic", DEFAULT_SCAN_INTEGRITY_FAULT_TOPIC
        ),
        attitude_source_topic=resolve_str_value(
            raw_integrity, "attitude_source_topic", DEFAULT_SCAN_INTEGRITY_ATTITUDE_SOURCE_TOPIC
        ),
        attitude_source_type=resolve_str_value(
            raw_integrity, "attitude_source_type", DEFAULT_SCAN_INTEGRITY_ATTITUDE_SOURCE_TYPE
        ),
        range_topic=resolve_str_value(raw_integrity, "range_topic", DEFAULT_SCAN_INTEGRITY_RANGE_TOPIC),
        base_frame_id=resolve_str_value(raw_integrity, "base_frame_id", DEFAULT_SCAN_INTEGRITY_BASE_FRAME_ID),
        scan_frame_id=resolve_str_value(raw_integrity, "scan_frame_id", DEFAULT_SCAN_INTEGRITY_SCAN_FRAME_ID),
        soft_tilt_deg=resolve_float_value(raw_integrity, "soft_tilt_deg", DEFAULT_SCAN_INTEGRITY_SOFT_TILT_DEG),
        hard_tilt_deg=resolve_float_value(raw_integrity, "hard_tilt_deg", DEFAULT_SCAN_INTEGRITY_HARD_TILT_DEG),
        max_dropped_scan_ratio=resolve_float_value(
            raw_integrity, "max_dropped_scan_ratio", DEFAULT_SCAN_INTEGRITY_MAX_DROPPED_SCAN_RATIO
        ),
        max_clipped_beam_ratio=resolve_float_value(
            raw_integrity, "max_clipped_beam_ratio", DEFAULT_SCAN_INTEGRITY_MAX_CLIPPED_BEAM_RATIO
        ),
        max_scan_attitude_time_offset_ms=resolve_float_value(
            raw_integrity,
            "max_scan_attitude_time_offset_ms",
            DEFAULT_SCAN_INTEGRITY_MAX_SCAN_ATTITUDE_OFFSET_MS,
        ),
        max_attitude_source_age_ms=resolve_float_value(
            raw_integrity,
            "max_attitude_source_age_ms",
            DEFAULT_SCAN_INTEGRITY_MAX_ATTITUDE_SOURCE_AGE_MS,
        ),
        min_attitude_rate_hz=resolve_float_value(
            raw_integrity, "min_attitude_rate_hz", DEFAULT_SCAN_INTEGRITY_MIN_ATTITUDE_RATE_HZ
        ),
        floor_hit_guard_range_m=resolve_float_value(
            raw_integrity, "floor_hit_guard_range_m", DEFAULT_SCAN_INTEGRITY_FLOOR_HIT_GUARD_RANGE_M
        ),
        min_lidar_height_m=resolve_float_value(
            raw_integrity, "min_lidar_height_m", DEFAULT_SCAN_INTEGRITY_MIN_LIDAR_HEIGHT_M
        ),
        min_downward_ray_z=resolve_float_value(
            raw_integrity, "min_downward_ray_z", DEFAULT_SCAN_INTEGRITY_MIN_DOWNWARD_RAY_Z
        ),
    )


def load_scan_stabilization_config(path: str | Path | None = None) -> ScanStabilizationConfig:
    config_file, config = load_navlab_config(path)
    raw_gazebo_sensor = section(config, "gazebo_sensor", path=config_file)
    raw_stabilization = section(raw_gazebo_sensor, "scan_stabilization", path=config_file, default={})
    return ScanStabilizationConfig(
        enabled=resolve_bool_value(raw_stabilization, "enabled", DEFAULT_SCAN_STABILIZATION_ENABLED),
        mode=resolve_str_value(raw_stabilization, "mode", DEFAULT_SCAN_STABILIZATION_MODE),
        input_scan_topic=resolve_str_value(
            raw_stabilization, "input_scan_topic", DEFAULT_SCAN_STABILIZATION_INPUT_SCAN_TOPIC
        ),
        output_scan_topic=resolve_str_value(
            raw_stabilization, "output_scan_topic", DEFAULT_SCAN_STABILIZATION_OUTPUT_SCAN_TOPIC
        ),
        status_topic=resolve_str_value(raw_stabilization, "status_topic", DEFAULT_SCAN_STABILIZATION_STATUS_TOPIC),
        events_topic=resolve_str_value(raw_stabilization, "events_topic", DEFAULT_SCAN_STABILIZATION_EVENTS_TOPIC),
        debug_scan_topic=resolve_str_value(
            raw_stabilization, "debug_scan_topic", DEFAULT_SCAN_STABILIZATION_DEBUG_SCAN_TOPIC
        ),
        fault_injection_topic=resolve_str_value(
            raw_stabilization, "fault_injection_topic", DEFAULT_SCAN_STABILIZATION_FAULT_TOPIC
        ),
        attitude_source_topic=resolve_str_value(
            raw_stabilization,
            "attitude_source_topic",
            DEFAULT_SCAN_STABILIZATION_ATTITUDE_SOURCE_TOPIC,
        ),
        attitude_source_type=resolve_str_value(
            raw_stabilization,
            "attitude_source_type",
            DEFAULT_SCAN_STABILIZATION_ATTITUDE_SOURCE_TYPE,
        ),
        range_topic=resolve_str_value(raw_stabilization, "range_topic", DEFAULT_SCAN_STABILIZATION_RANGE_TOPIC),
        base_frame_id=resolve_str_value(raw_stabilization, "base_frame_id", DEFAULT_SCAN_STABILIZATION_BASE_FRAME_ID),
        scan_frame_id=resolve_str_value(raw_stabilization, "scan_frame_id", DEFAULT_SCAN_STABILIZATION_SCAN_FRAME_ID),
        passthrough_tilt_deg=resolve_float_value(
            raw_stabilization,
            "passthrough_tilt_deg",
            DEFAULT_SCAN_STABILIZATION_PASSTHROUGH_TILT_DEG,
        ),
        compensation_tilt_deg=resolve_float_value(
            raw_stabilization,
            "compensation_tilt_deg",
            DEFAULT_SCAN_STABILIZATION_COMPENSATION_TILT_DEG,
        ),
        hard_drop_tilt_deg=resolve_float_value(
            raw_stabilization,
            "hard_drop_tilt_deg",
            DEFAULT_SCAN_STABILIZATION_HARD_DROP_TILT_DEG,
        ),
        max_vertical_projection_error_m=resolve_float_value(
            raw_stabilization,
            "max_vertical_projection_error_m",
            DEFAULT_SCAN_STABILIZATION_MAX_VERTICAL_ERROR_M,
        ),
        max_rejected_beam_ratio=resolve_float_value(
            raw_stabilization,
            "max_rejected_beam_ratio",
            DEFAULT_SCAN_STABILIZATION_MAX_REJECTED_BEAM_RATIO,
        ),
        min_retained_beam_ratio=resolve_float_value(
            raw_stabilization,
            "min_retained_beam_ratio",
            DEFAULT_SCAN_STABILIZATION_MIN_RETAINED_BEAM_RATIO,
        ),
        max_floor_hit_risk_beam_ratio=resolve_float_value(
            raw_stabilization,
            "max_floor_hit_risk_beam_ratio",
            DEFAULT_SCAN_STABILIZATION_MAX_FLOOR_HIT_RISK_RATIO,
        ),
        floor_hit_guard_range_m=resolve_float_value(
            raw_stabilization,
            "floor_hit_guard_range_m",
            DEFAULT_SCAN_INTEGRITY_FLOOR_HIT_GUARD_RANGE_M,
        ),
        min_lidar_height_m=resolve_float_value(
            raw_stabilization,
            "min_lidar_height_m",
            DEFAULT_SCAN_INTEGRITY_MIN_LIDAR_HEIGHT_M,
        ),
        min_downward_ray_z=resolve_float_value(
            raw_stabilization,
            "min_downward_ray_z",
            DEFAULT_SCAN_INTEGRITY_MIN_DOWNWARD_RAY_Z,
        ),
        max_scan_attitude_time_offset_ms=resolve_float_value(
            raw_stabilization,
            "max_scan_attitude_time_offset_ms",
            DEFAULT_SCAN_STABILIZATION_MAX_SCAN_ATTITUDE_OFFSET_MS,
        ),
        max_attitude_source_age_ms=resolve_float_value(
            raw_stabilization,
            "max_attitude_source_age_ms",
            DEFAULT_SCAN_STABILIZATION_MAX_ATTITUDE_SOURCE_AGE_MS,
        ),
        min_attitude_rate_hz=resolve_float_value(
            raw_stabilization,
            "min_attitude_rate_hz",
            DEFAULT_SCAN_STABILIZATION_MIN_ATTITUDE_RATE_HZ,
        ),
        min_stabilized_scan_rate_hz=resolve_float_value(
            raw_stabilization,
            "min_stabilized_scan_rate_hz",
            DEFAULT_SCAN_STABILIZATION_MIN_STABILIZED_SCAN_RATE_HZ,
        ),
        publish_debug_scan=resolve_bool_value(raw_stabilization, "publish_debug_scan", False),
    )


def load_airframe_disturbance_config(path: str | Path | None = None) -> AirframeDisturbanceConfig:
    config_file, config = load_navlab_config(path)
    raw_gazebo_sensor = section(config, "gazebo_sensor", path=config_file)
    raw_disturbance = section(raw_gazebo_sensor, "airframe_disturbance", path=config_file, default={})
    return AirframeDisturbanceConfig(
        enabled=resolve_bool_value(
            raw_disturbance,
            "enabled",
            DEFAULT_AIRFRAME_DISTURBANCE_ENABLED,
        ),
        profile=resolve_str_value(raw_disturbance, "profile", DEFAULT_AIRFRAME_DISTURBANCE_PROFILE),
        injection_layer=resolve_str_value(
            raw_disturbance,
            "injection_layer",
            DEFAULT_AIRFRAME_DISTURBANCE_INJECTION_LAYER,
        ),
        seed=resolve_str_value(raw_disturbance, "seed", DEFAULT_AIRFRAME_DISTURBANCE_SEED),
        motor_count=resolve_str_value(raw_disturbance, "motor_count", DEFAULT_AIRFRAME_DISTURBANCE_MOTOR_COUNT),
        thrust_multipliers=resolve_str_value(
            raw_disturbance,
            "thrust_multipliers",
            DEFAULT_AIRFRAME_DISTURBANCE_THRUST_MULTIPLIERS,
        ),
        esc_lag_ms=resolve_str_value(
            raw_disturbance,
            "esc_lag_ms",
            DEFAULT_AIRFRAME_DISTURBANCE_ESC_LAG_MS,
        ),
        esc_lag_model=resolve_str_value(
            raw_disturbance,
            "esc_lag_model",
            DEFAULT_AIRFRAME_DISTURBANCE_ESC_LAG_MODEL,
        ),
        thrust_noise_std=resolve_float_value(
            raw_disturbance,
            "thrust_noise_std",
            DEFAULT_AIRFRAME_DISTURBANCE_THRUST_NOISE_STD,
        ),
        thrust_noise_correlation_ms=resolve_float_value(
            raw_disturbance,
            "thrust_noise_correlation_ms",
            DEFAULT_AIRFRAME_DISTURBANCE_THRUST_NOISE_CORRELATION_MS,
        ),
        motor_jitter_hz=resolve_float_value(
            raw_disturbance,
            "motor_jitter_hz",
            DEFAULT_AIRFRAME_DISTURBANCE_MOTOR_JITTER_HZ,
        ),
        imu_vibration_enabled=resolve_bool_value(
            raw_disturbance,
            "imu_vibration_enabled",
            DEFAULT_AIRFRAME_DISTURBANCE_IMU_VIBRATION_ENABLED,
        ),
        imu_input_topic=resolve_str_value(
            raw_disturbance,
            "imu_input_topic",
            DEFAULT_AIRFRAME_DISTURBANCE_IMU_INPUT_TOPIC,
        ),
        imu_output_topic=resolve_str_value(
            raw_disturbance,
            "imu_output_topic",
            DEFAULT_AIRFRAME_DISTURBANCE_IMU_OUTPUT_TOPIC,
        ),
        imu_gyro_noise_std_dps=resolve_float_value(
            raw_disturbance,
            "imu_gyro_noise_std_dps",
            DEFAULT_AIRFRAME_DISTURBANCE_IMU_GYRO_NOISE_STD_DPS,
        ),
        imu_accel_noise_std_mps2=resolve_float_value(
            raw_disturbance,
            "imu_accel_noise_std_mps2",
            DEFAULT_AIRFRAME_DISTURBANCE_IMU_ACCEL_NOISE_STD_MPS2,
        ),
        imu_vibration_freq_hz=resolve_float_value(
            raw_disturbance,
            "imu_vibration_freq_hz",
            DEFAULT_AIRFRAME_DISTURBANCE_IMU_VIBRATION_FREQ_HZ,
        ),
        imu_vibration_roll_pitch_amp_deg=resolve_float_value(
            raw_disturbance,
            "imu_vibration_roll_pitch_amp_deg",
            DEFAULT_AIRFRAME_DISTURBANCE_IMU_VIBRATION_ROLL_PITCH_AMP_DEG,
        ),
        status_topic=resolve_str_value(
            raw_disturbance,
            "status_topic",
            DEFAULT_AIRFRAME_DISTURBANCE_STATUS_TOPIC,
        ),
        events_topic=resolve_str_value(
            raw_disturbance,
            "events_topic",
            DEFAULT_AIRFRAME_DISTURBANCE_EVENTS_TOPIC,
        ),
    )


def _optional_int(value: str) -> int | None:
    if value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("Invalid value for 'random_seed': expected an integer") from exc


def _required_int(value: str, *, key: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid value for '{key}': expected an integer") from exc


def _float_tuple(value: str, *, key: str) -> tuple[float, ...]:
    try:
        return tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid value for '{key}': expected comma-separated floats") from exc
