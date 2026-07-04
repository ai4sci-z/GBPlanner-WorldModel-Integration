from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

from navlab.common.logging import configure_sim_logging, logger
from navlab.sim.gazebo_sensor.config import AirframeDisturbanceRuntimeConfig, load_airframe_disturbance_config


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish P12 airframe disturbance status and optional IMU vibration.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--log-file", type=Path)
    return parser


def _load_runtime(path: Path | None) -> dict[str, object]:
    config = load_airframe_disturbance_config(path)
    runtime = AirframeDisturbanceRuntimeConfig(
        enabled=config.enabled.value,
        profile=config.profile.value,
        injection_layer=config.injection_layer.value,
        seed=int(config.seed.value),
        motor_count=int(config.motor_count.value),
        thrust_multipliers=_float_tuple(config.thrust_multipliers.value),
        esc_lag_ms=_float_tuple(config.esc_lag_ms.value),
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
    return {key: getattr(runtime, key) for key in runtime.__dataclass_fields__}


def _float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in value.split(",") if item.strip())


def run(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    configure_sim_logging(log_file=args.log_file)
    runtime = _load_runtime(args.config)
    if not runtime["enabled"]:
        logger.info("P12 airframe disturbance runtime disabled")
        return 0
    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Imu
        from std_msgs.msg import String
    except ModuleNotFoundError as exc:
        raise SystemExit("airframe disturbance runtime requires ROS2 Python packages") from exc

    rng = random.Random(int(runtime["seed"]))

    class AirframeDisturbanceNode(Node):
        def __init__(self) -> None:
            super().__init__("navlab_airframe_disturbance_runtime")
            self._started = time.monotonic()
            self._input_count = 0
            self._output_count = 0
            self._noise_roll_pitch_samples: list[float] = []
            self._status_pub = self.create_publisher(String, str(runtime["status_topic"]), 10)
            self._events_pub = self.create_publisher(String, str(runtime["events_topic"]), 10)
            self._imu_pub = self.create_publisher(Imu, str(runtime["imu_output_topic"]), 10)
            self.create_subscription(Imu, str(runtime["imu_input_topic"]), self._handle_imu, qos_profile_sensor_data)
            self.create_timer(0.5, self._publish_status)
            self.create_timer(5.0, self._publish_heartbeat_event)
            self._publish_event("started")

        def _handle_imu(self, msg: Imu) -> None:
            self._input_count += 1
            out = Imu()
            out.header = msg.header
            out.orientation = msg.orientation
            out.orientation_covariance = msg.orientation_covariance
            out.angular_velocity = msg.angular_velocity
            out.angular_velocity_covariance = msg.angular_velocity_covariance
            out.linear_acceleration = msg.linear_acceleration
            out.linear_acceleration_covariance = msg.linear_acceleration_covariance
            if runtime["imu_vibration_enabled"]:
                t = time.monotonic() - self._started
                amp_rad = math.radians(float(runtime["imu_vibration_roll_pitch_amp_deg"]))
                phase = 2.0 * math.pi * float(runtime["imu_vibration_freq_hz"]) * t
                roll_noise = amp_rad * math.sin(phase) + rng.gauss(
                    0.0, math.radians(float(runtime["imu_gyro_noise_std_dps"])) * 0.01
                )
                pitch_noise = amp_rad * math.cos(phase) + rng.gauss(
                    0.0, math.radians(float(runtime["imu_gyro_noise_std_dps"])) * 0.01
                )
                qn = _quat_from_rpy(roll_noise, pitch_noise, 0.0)
                out.orientation.x, out.orientation.y, out.orientation.z, out.orientation.w = _quat_multiply(
                    (msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w),
                    qn,
                )
                gyro_std = math.radians(float(runtime["imu_gyro_noise_std_dps"]))
                accel_std = float(runtime["imu_accel_noise_std_mps2"])
                out.angular_velocity.x += rng.gauss(0.0, gyro_std)
                out.angular_velocity.y += rng.gauss(0.0, gyro_std)
                out.angular_velocity.z += rng.gauss(0.0, gyro_std * 0.5)
                out.linear_acceleration.x += rng.gauss(0.0, accel_std)
                out.linear_acceleration.y += rng.gauss(0.0, accel_std)
                out.linear_acceleration.z += rng.gauss(0.0, accel_std)
                self._noise_roll_pitch_samples.append(math.degrees(math.hypot(roll_noise, pitch_noise)))
                if len(self._noise_roll_pitch_samples) > 2000:
                    self._noise_roll_pitch_samples.pop(0)
            self._output_count += 1
            self._imu_pub.publish(out)

        def _publish_event(self, event: str) -> None:
            msg = String()
            msg.data = json.dumps({"event": event, "runtime": self._summary()}, sort_keys=True)
            self._events_pub.publish(msg)

        def _publish_heartbeat_event(self) -> None:
            self._publish_event("heartbeat")

        def _publish_status(self) -> None:
            msg = String()
            msg.data = json.dumps(self._summary(), sort_keys=True)
            self._status_pub.publish(msg)

        def _summary(self) -> dict[str, object]:
            samples = self._noise_roll_pitch_samples
            rms = math.sqrt(sum(x * x for x in samples) / len(samples)) if samples else 0.0
            return {
                "enabled": runtime["enabled"],
                "profile": runtime["profile"],
                "injection_layer": runtime["injection_layer"],
                "motor_count": runtime["motor_count"],
                "thrust_multipliers": list(runtime["thrust_multipliers"]),
                "esc_lag_ms_by_motor": list(runtime["esc_lag_ms"]),
                "esc_lag_model": runtime["esc_lag_model"],
                "thrust_noise_std": runtime["thrust_noise_std"],
                "motor_jitter_hz": runtime["motor_jitter_hz"],
                "imu_vibration_claim": "evaluated" if runtime["imu_vibration_enabled"] else "not_enabled",
                "imu_input_topic": runtime["imu_input_topic"],
                "imu_output_topic": runtime["imu_output_topic"],
                "imu_input_count": self._input_count,
                "imu_output_count": self._output_count,
                "attitude_noise_rms_deg": rms,
            }

    rclpy.init(args=None)
    node = AirframeDisturbanceNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


def _quat_from_rpy(roll: float, pitch: float, yaw: float) -> tuple[float, float, float, float]:
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def _quat_multiply(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
