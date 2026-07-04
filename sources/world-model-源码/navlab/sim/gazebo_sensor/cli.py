from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from navlab.common.logging import configure_sim_logging, logger
from navlab.sim.gazebo_sensor.config import X2SensorRuntimeConfig
from navlab.sim.gazebo_sensor.x2.emulator import (
    X2SerialEmulator,
    X2SerialEmulatorConfig,
    samples_per_scan,
)
from navlab.sim.gazebo_sensor.x2.scan_source import IdealLaserScan, resample_ideal_scan_to_x2_samples


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the YDLidar X2 virtual serial emulator.")
    parser.add_argument("--runtime", action="store_true", help="Launch the full Gazebo/sensor runtime supervisor.")
    parser.add_argument("--duration-sec", type=float, default=0.0)
    parser.add_argument("--driver-smoke", action="store_true", help="Run emulator + vendor driver smoke acceptance.")
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--startup-timeout-sec", type=float, default=20.0)
    parser.add_argument("--log-file", type=Path)
    return parser


def run(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    configure_sim_logging(log_file=args.log_file)
    if args.runtime:
        from navlab.sim.gazebo_sensor.runtime import launch as launch_runtime

        runtime_args = []
        if args.log_file is not None:
            runtime_args.extend(["--log-file", str(args.log_file)])
        return launch_runtime(runtime_args)
    if args.driver_smoke:
        from navlab.sim.gazebo_sensor.x2.smoke import X2DriverSmokeConfig, execute_driver_smoke

        artifact_dir = args.artifact_dir or Path(
            f"artifacts/ros/x2_driver_smoke/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        return execute_driver_smoke(
            X2DriverSmokeConfig.from_config(
                artifact_dir=artifact_dir,
                duration_sec=max(1.0, args.duration_sec or 15.0),
                startup_timeout_sec=args.startup_timeout_sec,
            )
        )

    config = X2SensorRuntimeConfig.load()

    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
        from sensor_msgs.msg import LaserScan
        from std_msgs.msg import String
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "x2 sensor CLI requires ROS2 Python packages. Run it inside the Gazebo/sensor runtime image."
        ) from exc

    sample_count = samples_per_scan(
        sample_rate_hz=config.sample_rate_hz,
        scan_frequency_hz=config.scan_frequency_hz,
    )
    emulator = X2SerialEmulator(
        X2SerialEmulatorConfig(
            virtual_serial_link=config.virtual_serial_link,
            scan_frequency_hz=config.scan_frequency_hz,
            sample_rate_hz=config.sample_rate_hz,
            range_min_m=config.range_min_m,
            range_max_m=config.range_max_m,
            status_topic=config.status_topic,
        )
    )

    class X2SerialEmulatorNode(Node):
        def __init__(self) -> None:
            super().__init__("x2_serial_emulator")
            self._publisher = self.create_publisher(String, config.status_topic, 10)
            self._latest_samples = ()
            self._latest_scan_ideal_monotonic_sec: float | None = None
            self._started_at = time.monotonic()
            emulator.open()
            if config.auto_start:
                emulator.start_scanning()
            self.create_subscription(LaserScan, config.scan_ideal_topic, self._handle_scan_ideal, 10)
            self.create_timer(0.02, self._poll_commands)
            self.create_timer(max(0.001, 1.0 / config.scan_frequency_hz), self._write_scan)
            self.create_timer(0.5, self._publish_status)
            if args.duration_sec > 0:
                self.create_timer(0.1, self._stop_when_done)
            logger.info(
                "x2 emulator opened link={} slave={} status_topic={}",
                config.virtual_serial_link,
                emulator.slave_path,
                config.status_topic,
            )

        def _handle_scan_ideal(self, message: LaserScan) -> None:
            samples = resample_ideal_scan_to_x2_samples(
                IdealLaserScan(
                    ranges=tuple(float(value) for value in message.ranges),
                    angle_min_rad=float(message.angle_min),
                    angle_increment_rad=float(message.angle_increment),
                ),
                sample_count=sample_count,
                range_min_m=config.range_min_m,
                range_max_m=config.range_max_m,
                noise_stddev_m=config.range_noise_stddev_m,
                noise_stddev_per_m=config.range_noise_stddev_per_m,
                dropout_rate=config.dropout_rate,
                random_seed=config.random_seed,
            )
            if samples:
                self._latest_samples = samples
                self._latest_scan_ideal_monotonic_sec = time.monotonic()

        def destroy_node(self) -> bool:
            emulator.close()
            return super().destroy_node()

        def _poll_commands(self) -> None:
            data = emulator.poll_commands()
            if data:
                logger.debug("x2 emulator read {} command bytes state={}", len(data), emulator.status().state)

        def _write_scan(self) -> None:
            byte_count = emulator.write_scan_once(self._latest_samples)
            if byte_count:
                logger.debug("x2 emulator wrote {} bytes", byte_count)

        def _publish_status(self) -> None:
            message = String()
            status = emulator.status_dict()
            status["scan_source"] = (
                "gazebo_ideal" if self._latest_scan_ideal_monotonic_sec else "waiting_for_gazebo_ideal"
            )
            status["scan_ideal_topic"] = config.scan_ideal_topic
            status["range_noise_stddev_m"] = config.range_noise_stddev_m
            status["range_noise_stddev_per_m"] = config.range_noise_stddev_per_m
            status["dropout_rate"] = config.dropout_rate
            status["latest_scan_ideal_age_sec"] = (
                None
                if self._latest_scan_ideal_monotonic_sec is None
                else time.monotonic() - self._latest_scan_ideal_monotonic_sec
            )
            message.data = json.dumps(status, ensure_ascii=True, sort_keys=True)
            self._publisher.publish(message)

        def _stop_when_done(self) -> None:
            if time.monotonic() - self._started_at >= args.duration_sec:
                raise SystemExit(0)

    rclpy.init(args=None)
    node = X2SerialEmulatorNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
