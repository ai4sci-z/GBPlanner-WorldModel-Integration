from __future__ import annotations

import json
import math
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from typing import Any

BASE_IRIS_MOTOR_MULTIPLIER = 838.0


@dataclass(frozen=True, slots=True)
class AirframeDisturbanceProfile:
    name: str
    motor_count: int
    thrust_multipliers: tuple[float, ...]
    esc_lag_ms: tuple[float, ...]
    thrust_noise_std: float = 0.0
    thrust_noise_correlation_ms: float = 0.0
    motor_jitter_hz: float = 0.0
    imu_vibration_enabled: bool = False
    imu_gyro_noise_std_dps: float = 0.0
    imu_accel_noise_std_mps2: float = 0.0
    imu_vibration_freq_hz: float = 0.0
    imu_vibration_roll_pitch_amp_deg: float = 0.0
    seed: int = 12012

    def to_summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "motor_count": self.motor_count,
            "thrust_multipliers": list(self.thrust_multipliers),
            "esc_lag_ms": list(self.esc_lag_ms),
            "thrust_noise_std": self.thrust_noise_std,
            "thrust_noise_correlation_ms": self.thrust_noise_correlation_ms,
            "motor_jitter_hz": self.motor_jitter_hz,
            "imu_vibration_enabled": self.imu_vibration_enabled,
            "imu_gyro_noise_std_dps": self.imu_gyro_noise_std_dps,
            "imu_accel_noise_std_mps2": self.imu_accel_noise_std_mps2,
            "imu_vibration_freq_hz": self.imu_vibration_freq_hz,
            "imu_vibration_roll_pitch_amp_deg": self.imu_vibration_roll_pitch_amp_deg,
            "seed": self.seed,
        }


@dataclass(frozen=True, slots=True)
class AirframeDisturbanceGateThresholds:
    max_abs_thrust_multiplier_delta: float = 0.20
    max_esc_lag_ms: float = 120.0
    max_abs_roll_deg: float = 8.0
    max_abs_pitch_deg: float = 8.0
    max_rms_roll_deg: float = 3.0
    max_rms_pitch_deg: float = 3.0
    max_attitude_rate_dps: float = 120.0
    max_scan_drop_ratio: float = 0.20
    max_scan_compensated_ratio: float = 0.80
    max_floor_hit_rejected_ratio: float = 0.05
    min_stabilized_scan_rate_hz: float = 5.0
    min_slam_odom_rate_hz: float = 10.0
    max_map_artifact_score: float = 0.15
    max_external_nav_dropout_ratio: float = 0.05


PROFILE_LIBRARY: dict[str, AirframeDisturbanceProfile] = {
    "clean": AirframeDisturbanceProfile(
        name="clean",
        motor_count=4,
        thrust_multipliers=(1.0, 1.0, 1.0, 1.0),
        esc_lag_ms=(0.0, 0.0, 0.0, 0.0),
    ),
    "mild_bias": AirframeDisturbanceProfile(
        name="mild_bias",
        motor_count=4,
        thrust_multipliers=(0.99, 1.01, 1.0, 0.995),
        esc_lag_ms=(10.0, 15.0, 10.0, 15.0),
        thrust_noise_std=0.005,
    ),
    "nominal_realistic": AirframeDisturbanceProfile(
        name="nominal_realistic",
        motor_count=4,
        thrust_multipliers=(0.97, 1.03, 1.0, 0.98),
        esc_lag_ms=(20.0, 35.0, 25.0, 45.0),
        thrust_noise_std=0.015,
        thrust_noise_correlation_ms=80.0,
        motor_jitter_hz=35.0,
        imu_vibration_enabled=True,
        imu_gyro_noise_std_dps=0.8,
        imu_accel_noise_std_mps2=0.15,
        imu_vibration_freq_hz=80.0,
        imu_vibration_roll_pitch_amp_deg=0.4,
    ),
    "esc_lag": AirframeDisturbanceProfile(
        name="esc_lag",
        motor_count=4,
        thrust_multipliers=(1.0, 1.0, 1.0, 1.0),
        esc_lag_ms=(20.0, 55.0, 25.0, 60.0),
        thrust_noise_std=0.006,
    ),
    "vibration": AirframeDisturbanceProfile(
        name="vibration",
        motor_count=4,
        thrust_multipliers=(1.0, 1.0, 1.0, 1.0),
        esc_lag_ms=(10.0, 10.0, 10.0, 10.0),
        thrust_noise_std=0.01,
        motor_jitter_hz=80.0,
        imu_vibration_enabled=True,
        imu_gyro_noise_std_dps=1.2,
        imu_accel_noise_std_mps2=0.2,
        imu_vibration_freq_hz=90.0,
        imu_vibration_roll_pitch_amp_deg=0.7,
    ),
    "hard_bias": AirframeDisturbanceProfile(
        name="hard_bias",
        motor_count=4,
        thrust_multipliers=(0.84, 1.16, 1.0, 0.88),
        esc_lag_ms=(60.0, 110.0, 80.0, 120.0),
        thrust_noise_std=0.04,
        motor_jitter_hz=120.0,
        imu_vibration_enabled=True,
        imu_gyro_noise_std_dps=2.5,
        imu_accel_noise_std_mps2=0.45,
        imu_vibration_freq_hz=110.0,
        imu_vibration_roll_pitch_amp_deg=1.5,
    ),
}


def profile_from_library(name: str, *, seed: int | None = None) -> AirframeDisturbanceProfile:
    try:
        profile = PROFILE_LIBRARY[name]
    except KeyError as exc:
        raise ValueError(f"unknown airframe disturbance profile: {name}") from exc
    if seed is not None:
        profile = replace(profile, seed=seed)
    return profile


def validate_profile(
    profile: AirframeDisturbanceProfile,
    thresholds: AirframeDisturbanceGateThresholds | None = None,
    *,
    allow_hard_profile: bool = False,
) -> list[str]:
    thresholds = thresholds or AirframeDisturbanceGateThresholds()
    blockers: list[str] = []
    if profile.motor_count <= 0:
        blockers.append("airframe_disturbance_config_invalid: motor_count must be positive")
    if len(profile.thrust_multipliers) != profile.motor_count:
        blockers.append("airframe_disturbance_config_invalid: thrust_multipliers length must match motor_count")
    if len(profile.esc_lag_ms) != profile.motor_count:
        blockers.append("airframe_disturbance_config_invalid: esc_lag_ms length must match motor_count")
    for index, value in enumerate(profile.thrust_multipliers):
        if value <= 0.0:
            blockers.append(f"airframe_disturbance_config_invalid: thrust_multipliers[{index}] must be positive")
        if abs(value - 1.0) > thresholds.max_abs_thrust_multiplier_delta and not allow_hard_profile:
            blockers.append(f"airframe_thrust_multiplier_delta_too_high:motor_{index}")
    for index, value in enumerate(profile.esc_lag_ms):
        if value < 0.0:
            blockers.append(f"airframe_disturbance_config_invalid: esc_lag_ms[{index}] must be non-negative")
        if value > thresholds.max_esc_lag_ms and not allow_hard_profile:
            blockers.append(f"airframe_esc_lag_too_high:motor_{index}")
    for name, value in (
        ("thrust_noise_std", profile.thrust_noise_std),
        ("thrust_noise_correlation_ms", profile.thrust_noise_correlation_ms),
        ("motor_jitter_hz", profile.motor_jitter_hz),
        ("imu_gyro_noise_std_dps", profile.imu_gyro_noise_std_dps),
        ("imu_accel_noise_std_mps2", profile.imu_accel_noise_std_mps2),
        ("imu_vibration_freq_hz", profile.imu_vibration_freq_hz),
        ("imu_vibration_roll_pitch_amp_deg", profile.imu_vibration_roll_pitch_amp_deg),
    ):
        if value < 0.0:
            blockers.append(f"airframe_disturbance_config_invalid: {name} must be non-negative")
    return blockers


def apply_profile_to_iris_sdf(source: str, profile: AirframeDisturbanceProfile) -> tuple[str, dict[str, Any]]:
    validate = validate_profile(profile, allow_hard_profile=True)
    if validate:
        raise ValueError("; ".join(validate))
    root = ET.fromstring(source)
    controls = list(root.findall(".//control"))
    if len(controls) < profile.motor_count:
        raise ValueError(
            f"airframe_disturbance_profile_not_applied: expected {profile.motor_count} controls, found {len(controls)}"
        )
    applied: list[dict[str, Any]] = []
    for index, control in enumerate(controls[: profile.motor_count]):
        sign = -1.0 if (control.findtext("multiplier") or "").strip().startswith("-") else 1.0
        original_multiplier = float(control.findtext("multiplier") or sign * BASE_IRIS_MOTOR_MULTIPLIER)
        new_multiplier = sign * abs(original_multiplier) * profile.thrust_multipliers[index]
        _set_child_text(control, "multiplier", _fmt(new_multiplier))
        lag_ms = profile.esc_lag_ms[index]
        original_p_gain = float(control.findtext("p_gain") or control.findtext("vel_p_gain") or 0.20)
        _set_child_text(control, "escTimeConstantMs", _fmt(lag_ms))
        applied.append(
            {
                "channel": control.attrib.get("channel", str(index)),
                "jointName": control.findtext("jointName"),
                "original_multiplier": original_multiplier,
                "applied_multiplier": new_multiplier,
                "thrust_multiplier": profile.thrust_multipliers[index],
                "esc_lag_ms": lag_ms,
                "original_p_gain": original_p_gain,
                "esc_time_constant_ms": lag_ms,
                "esc_lag_model": "plugin_first_order",
            }
        )
    root.insert(
        0, ET.Comment(f"NavLab P12 airframe disturbance profile: {json.dumps(profile.to_summary(), sort_keys=True)}")
    )
    rendered = ET.tostring(root, encoding="unicode")
    if not rendered.startswith("<?xml"):
        rendered = "<?xml version='1.0'?>\n" + rendered
    return rendered + "\n", {"profile": profile.to_summary(), "applied_controls": applied}


def estimate_disturbance_metrics(
    profile: AirframeDisturbanceProfile,
    thresholds: AirframeDisturbanceGateThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or AirframeDisturbanceGateThresholds()
    rng = random.Random(profile.seed)
    thrust_spread = max(profile.thrust_multipliers) - min(profile.thrust_multipliers)
    lag_spread = max(profile.esc_lag_ms) - min(profile.esc_lag_ms)
    noise = profile.thrust_noise_std + profile.imu_vibration_roll_pitch_amp_deg / 25.0
    max_abs_roll = 1.0 + thrust_spread * 42.0 + lag_spread * 0.018 + noise * 8.0 + rng.random() * 0.05
    max_abs_pitch = 1.1 + thrust_spread * 38.0 + lag_spread * 0.020 + noise * 8.0 + rng.random() * 0.05
    rms_roll = max_abs_roll * 0.38
    rms_pitch = max_abs_pitch * 0.40
    max_rate = 25.0 + lag_spread * 0.72 + profile.motor_jitter_hz * 0.18 + profile.imu_gyro_noise_std_dps * 6.0
    scan_drop_ratio = max(0.0, (max(max_abs_roll, max_abs_pitch) - 6.0) / 35.0)
    scan_compensated_ratio = min(0.8, max(0.0, (max(max_abs_roll, max_abs_pitch) - 3.0) / 8.0))
    floor_hit_ratio = min(0.2, scan_drop_ratio * 0.3 + profile.imu_vibration_roll_pitch_amp_deg * 0.01)
    map_artifact_score = min(1.0, scan_drop_ratio * 0.6 + floor_hit_ratio * 1.8 + profile.thrust_noise_std * 1.5)
    ok = (
        max_abs_roll <= thresholds.max_abs_roll_deg
        and max_abs_pitch <= thresholds.max_abs_pitch_deg
        and rms_roll <= thresholds.max_rms_roll_deg
        and rms_pitch <= thresholds.max_rms_pitch_deg
        and max_rate <= thresholds.max_attitude_rate_dps
        and scan_drop_ratio <= thresholds.max_scan_drop_ratio
        and scan_compensated_ratio <= thresholds.max_scan_compensated_ratio
        and floor_hit_ratio <= thresholds.max_floor_hit_rejected_ratio
        and map_artifact_score <= thresholds.max_map_artifact_score
    )
    blockers: list[str] = []
    if max_abs_roll > thresholds.max_abs_roll_deg:
        blockers.append("max_abs_roll_deg_too_high")
    if max_abs_pitch > thresholds.max_abs_pitch_deg:
        blockers.append("max_abs_pitch_deg_too_high")
    if max_rate > thresholds.max_attitude_rate_dps:
        blockers.append("max_attitude_rate_dps_too_high")
    if scan_drop_ratio > thresholds.max_scan_drop_ratio:
        blockers.append("scan_drop_ratio_too_high")
    if floor_hit_ratio > thresholds.max_floor_hit_rejected_ratio:
        blockers.append("floor_hit_rejected_ratio_too_high")
    if map_artifact_score > thresholds.max_map_artifact_score:
        blockers.append("map_artifact_risk_too_high")
    return {
        "ok": ok,
        "blockers": blockers,
        "flight_attitude_metrics": {
            "max_abs_roll_deg": round(max_abs_roll, 3),
            "max_abs_pitch_deg": round(max_abs_pitch, 3),
            "rms_roll_deg": round(rms_roll, 3),
            "rms_pitch_deg": round(rms_pitch, 3),
            "yaw_rate_dps": round(max_rate * 0.12, 3),
            "max_attitude_rate_dps": round(max_rate, 3),
        },
        "scan_stabilization": {
            "scan_drop_ratio": round(scan_drop_ratio, 4),
            "scan_compensated_ratio": round(scan_compensated_ratio, 4),
            "floor_hit_rejected_ratio": round(floor_hit_ratio, 4),
            "stabilized_scan_rate_hz": 7.0 if scan_drop_ratio < 0.25 else 3.5,
        },
        "slam": {
            "map_artifact_score": round(map_artifact_score, 4),
            "false_wall_risk_ok": map_artifact_score <= thresholds.max_map_artifact_score,
            "odom_rate_hz": 42.0 if scan_drop_ratio < 0.25 else 8.0,
        },
        "disturbance_source_metrics": {
            "thrust_spread": round(thrust_spread, 4),
            "esc_lag_spread_ms": round(lag_spread, 3),
            "imu_vibration_claim": "evaluated" if profile.imu_vibration_enabled else "not_enabled",
        },
    }


def _set_child_text(element: ET.Element, tag: str, text: str) -> None:
    child = element.find(tag)
    if child is None:
        child = ET.SubElement(element, tag)
    child.text = text


def _fmt(value: float) -> str:
    if math.isclose(value, round(value), abs_tol=1e-9):
        return str(int(round(value)))
    return f"{value:.6g}"
