from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from navlab.common.logging import configure_sim_logging, logger
from navlab.common.process_manager import ProcessManager
from navlab.sim.gazebo_sensor.config import (
    AirframeDisturbanceRuntimeConfig,
    DownRangefinderRuntimeConfig,
    ScanIntegrityRuntimeConfig,
    ScanStabilizationRuntimeConfig,
    X2SensorRuntimeConfig,
)

VIRTUAL_SERIAL_STARTUP_TIMEOUT_SEC = 10.0


@dataclass(frozen=True, slots=True)
class X2SensorLaunchConfig:
    scan_source: str
    profile_path: Path
    virtual_serial_link: Path
    scan_ideal_topic: str
    vendor_scan_topic: str
    scan_topic: str
    status_topic: str
    scan_frequency_hz: float
    sample_rate_hz: float
    range_min_m: float
    range_max_m: float
    static_range_m: float
    auto_start: bool
    range_noise_stddev_m: float
    dropout_rate: float
    random_seed: int | None
    down_rangefinder_enabled: bool
    down_rangefinder_scan_ideal_topic: str
    down_rangefinder_frame_id: str
    scan_integrity_enabled: bool
    scan_stabilization_enabled: bool
    airframe_disturbance_enabled: bool

    @classmethod
    def from_config(cls) -> X2SensorLaunchConfig:
        runtime = X2SensorRuntimeConfig.load()
        down_rangefinder = DownRangefinderRuntimeConfig.load()
        scan_integrity = ScanIntegrityRuntimeConfig.load()
        scan_stabilization = ScanStabilizationRuntimeConfig.load()
        airframe_disturbance = AirframeDisturbanceRuntimeConfig.load()
        return cls(
            scan_source=runtime.scan_source,
            profile_path=runtime.profile,
            virtual_serial_link=runtime.virtual_serial_link,
            scan_ideal_topic=runtime.scan_ideal_topic,
            vendor_scan_topic=runtime.vendor_scan_topic,
            scan_topic=runtime.scan_topic,
            status_topic=runtime.status_topic,
            scan_frequency_hz=runtime.scan_frequency_hz,
            sample_rate_hz=runtime.sample_rate_hz,
            range_min_m=runtime.range_min_m,
            range_max_m=runtime.range_max_m,
            static_range_m=runtime.static_range_m,
            auto_start=runtime.auto_start,
            range_noise_stddev_m=runtime.range_noise_stddev_m,
            dropout_rate=runtime.dropout_rate,
            random_seed=None,
            down_rangefinder_enabled=down_rangefinder.enabled,
            down_rangefinder_scan_ideal_topic=down_rangefinder.scan_ideal_topic,
            down_rangefinder_frame_id=down_rangefinder.frame_id,
            scan_integrity_enabled=scan_integrity.enabled,
            scan_stabilization_enabled=scan_stabilization.enabled,
            airframe_disturbance_enabled=airframe_disturbance.enabled,
        )


def build_scan_ideal_bridge_command(config: X2SensorLaunchConfig) -> list[str]:
    return [
        "ros2",
        "run",
        "ros_gz_bridge",
        "parameter_bridge",
        f"{config.scan_ideal_topic}@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan",
        "--ros-args",
        "-p",
        "override_frame_id:=laser_frame",
    ]


def build_down_rangefinder_bridge_command(config: X2SensorLaunchConfig) -> list[str]:
    return [
        "ros2",
        "run",
        "ros_gz_bridge",
        "parameter_bridge",
        f"{config.down_rangefinder_scan_ideal_topic}@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan",
        "--ros-args",
        "-p",
        f"override_frame_id:={config.down_rangefinder_frame_id}",
    ]


def build_down_rangefinder_projection_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "navlab.sim.gazebo_sensor.range_projection",
    ]


def build_cloud_scan_projection_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "navlab.sim.gazebo_sensor.cloud_scan_projection",
    ]


def build_emulator_command(config: X2SensorLaunchConfig) -> list[str]:
    _ = config
    return [
        sys.executable,
        "-m",
        "navlab.sim.gazebo_sensor.cli",
    ]


def build_vendor_driver_command(config: X2SensorLaunchConfig) -> list[str]:
    return [
        "ros2",
        "run",
        "ydlidar_ros2_driver",
        "ydlidar_ros2_driver_node",
        "--ros-args",
        "--params-file",
        str(config.profile_path),
        "-p",
        "use_sim_time:=true",
        "-r",
        f"scan:={config.vendor_scan_topic}",
    ]


def build_scan_time_normalizer_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "navlab.sim.gazebo_sensor.scan_time_normalizer",
    ]


def build_scan_integrity_filter_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "navlab.sim.gazebo_sensor.scan_integrity",
    ]


def build_scan_stabilization_filter_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "navlab.sim.gazebo_sensor.scan_stabilization",
    ]


def build_airframe_disturbance_runtime_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "navlab.sim.gazebo_sensor.airframe_disturbance_runtime",
    ]


def wait_for_virtual_serial_link(path: Path, *, timeout_sec: float = VIRTUAL_SERIAL_STARTUP_TIMEOUT_SEC) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for virtual serial link {path}")


class X2SensorRuntime:
    def __init__(self, config: X2SensorLaunchConfig) -> None:
        self._config = config
        self._manager = ProcessManager()
        self._stopping = False

    def start(self) -> int:
        logger.info("Starting X2 sensor runtime scan_source={}", self._config.scan_source)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        self._start_processes()
        try:
            while not self._stopping:
                for process in self._manager.processes:
                    rc = process.poll()
                    if rc is not None:
                        logger.warning("{} exited early rc={}; stopping sensor runtime", process.name, rc)
                        return rc or 1
                time.sleep(1.0)
        finally:
            self._manager.stop_all(timeout_sec=8.0)
        return 0

    def _start_processes(self) -> None:
        self._manager.start_subprocess("scan_ideal_bridge", build_scan_ideal_bridge_command(self._config))
        if self._config.down_rangefinder_enabled:
            self._manager.start_subprocess(
                "down_rangefinder_bridge",
                build_down_rangefinder_bridge_command(self._config),
            )
            self._manager.start_subprocess(
                "down_rangefinder_projection",
                build_down_rangefinder_projection_command(),
            )
        if self._config.airframe_disturbance_enabled:
            self._manager.start_subprocess(
                "airframe_disturbance_runtime",
                build_airframe_disturbance_runtime_command(),
            )
        if self._config.scan_source != "x2_virtual_serial":
            logger.info("scan_source={} starts only the ideal scan bridge", self._config.scan_source)
            return
        self._manager.start_subprocess("cloud_scan_projection", build_cloud_scan_projection_command())
        self._manager.start_subprocess("x2_serial_emulator", build_emulator_command(self._config))
        wait_for_virtual_serial_link(self._config.virtual_serial_link)
        self._manager.start_subprocess("x2_scan_time_normalizer", build_scan_time_normalizer_command())
        if self._config.scan_stabilization_enabled:
            self._manager.start_subprocess("scan_stabilization_filter", build_scan_stabilization_filter_command())
        elif self._config.scan_integrity_enabled:
            self._manager.start_subprocess("scan_integrity_filter", build_scan_integrity_filter_command())
        self._manager.start_subprocess("ydlidar_ros2_driver", build_vendor_driver_command(self._config))

    def _handle_signal(self, signum: int, _frame: object) -> None:
        logger.info("Received signal {}; stopping X2 sensor runtime", signum)
        self._stopping = True


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the NavLab Gazebo X2 sensor runtime.")
    parser.add_argument("--log-file", type=Path)
    return parser


def launch(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    configure_sim_logging(log_file=args.log_file)
    return X2SensorRuntime(X2SensorLaunchConfig.from_config()).start()


def main() -> int:
    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
