from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from navlab.common.logging import logger
from navlab.sim.gazebo_sensor.config import X2SensorRuntimeConfig


@dataclass(frozen=True, slots=True)
class X2DriverSmokeConfig:
    artifact_dir: Path
    duration_sec: float
    profile_path: Path
    virtual_serial_link: Path
    status_topic: str
    scan_topic: str
    scan_frequency_hz: float
    sample_rate_hz: float
    range_min_m: float
    range_max_m: float
    static_range_m: float = 1.5
    startup_timeout_sec: float = 20.0

    @classmethod
    def from_config(
        cls,
        *,
        artifact_dir: Path,
        duration_sec: float,
        startup_timeout_sec: float = 20.0,
    ) -> X2DriverSmokeConfig:
        runtime = X2SensorRuntimeConfig.load()
        return cls(
            artifact_dir=artifact_dir,
            duration_sec=duration_sec,
            profile_path=runtime.profile,
            virtual_serial_link=runtime.virtual_serial_link,
            status_topic=runtime.status_topic,
            scan_topic=runtime.scan_topic,
            scan_frequency_hz=runtime.scan_frequency_hz,
            sample_rate_hz=runtime.sample_rate_hz,
            range_min_m=runtime.range_min_m,
            range_max_m=runtime.range_max_m,
            static_range_m=runtime.static_range_m,
            startup_timeout_sec=startup_timeout_sec,
        )


@dataclass(slots=True)
class SmokeProcess:
    name: str
    command: list[str]
    process: subprocess.Popen[str]
    log_file: object

    def terminate(self) -> None:
        if self.process.poll() is None:
            logger.info("Terminating {} pid={}", self.name, self.process.pid)
            self.process.terminate()

    def wait_or_kill(self, *, timeout_sec: float = 5.0) -> None:
        try:
            if self.process.poll() is None:
                try:
                    self.process.wait(timeout=timeout_sec)
                except subprocess.TimeoutExpired:
                    logger.warning("{} did not exit in {}s; killing", self.name, timeout_sec)
                    self.process.kill()
                    self.process.wait(timeout=timeout_sec)
        finally:
            self.log_file.close()


def build_emulator_command(config: X2DriverSmokeConfig) -> list[str]:
    _ = config
    return [
        sys.executable,
        "-m",
        "navlab.sim.gazebo_sensor.cli",
    ]


def build_vendor_driver_command(config: X2DriverSmokeConfig) -> list[str]:
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
    ]


def build_rosbag_record_command(config: X2DriverSmokeConfig) -> list[str]:
    return [
        "ros2",
        "bag",
        "record",
        "-o",
        str(config.artifact_dir / "rosbag"),
        config.scan_topic,
        config.status_topic,
    ]


def execute_driver_smoke(config: X2DriverSmokeConfig) -> int:
    config.artifact_dir.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(config.artifact_dir / "rosbag", ignore_errors=True)
    _write_run_config(config)
    processes: list[SmokeProcess] = []
    try:
        processes.append(_start_process("x2_serial_emulator", build_emulator_command(config), config.artifact_dir))
        _wait_for_virtual_serial(config.virtual_serial_link, timeout_sec=config.startup_timeout_sec)
        processes.append(
            _start_process("ydlidar_ros2_driver", build_vendor_driver_command(config), config.artifact_dir)
        )
        _wait_for_topic(config.scan_topic, timeout_sec=config.startup_timeout_sec)
        rosbag_process = _start_process("rosbag_record", build_rosbag_record_command(config), config.artifact_dir)
        processes.append(rosbag_process)
        time.sleep(max(1.0, config.duration_sec))
        samples = collect_samples(config)
        rosbag_process.terminate()
        rosbag_process.wait_or_kill(timeout_sec=8.0)
        processes.remove(rosbag_process)
        _wait_for_file(config.artifact_dir / "rosbag" / "metadata.yaml", timeout_sec=8.0)
        summary = _build_summary(config, samples=samples)
        (config.artifact_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return 0 if summary["ok"] else 3
    except Exception as exc:
        logger.exception("X2 driver smoke failed")
        summary = {
            "ok": False,
            "error": str(exc),
            "config": _serializable_config(config),
        }
        (config.artifact_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return 20
    finally:
        for process in reversed(processes):
            process.terminate()
        for process in reversed(processes):
            process.wait_or_kill(timeout_sec=8.0)


def _start_process(name: str, command: list[str], artifact_dir: Path) -> SmokeProcess:
    log_path = artifact_dir / f"{name}.log"
    log_file = log_path.open("a", encoding="utf-8")
    logger.info("Starting {}: {}", name, " ".join(command))
    process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT, text=True)
    return SmokeProcess(name=name, command=command, process=process, log_file=log_file)


def _wait_for_virtual_serial(path: Path, *, timeout_sec: float) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if path.exists() or path.is_symlink():
            return
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for virtual serial link {path}")


def _wait_for_topic(topic: str, *, timeout_sec: float) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        result = subprocess.run(["ros2", "topic", "list"], check=False, text=True, capture_output=True)
        if result.returncode == 0 and topic in result.stdout.splitlines():
            return
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for ROS topic {topic}")


def _wait_for_file(path: Path, *, timeout_sec: float) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            return
        time.sleep(0.2)


def _run_capture(command: list[str], *, timeout_sec: float, output_path: Path) -> str:
    logger.debug("Running capture command: {}", " ".join(command))
    try:
        result = subprocess.run(command, check=False, text=True, capture_output=True, timeout=timeout_sec)
        return_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        return_code = 124
        stdout = _coerce_output(exc.stdout)
        stderr = _coerce_output(exc.stderr)
    output = f"COMMAND: {' '.join(command)}\nRETURN_CODE: {return_code}\n\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}\n"
    output_path.write_text(output, encoding="utf-8")
    return output


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def collect_samples(config: X2DriverSmokeConfig) -> dict[str, str]:
    return {
        "topic_list": _run_capture(
            ["ros2", "topic", "list"],
            timeout_sec=8.0,
            output_path=config.artifact_dir / "topic_list.txt",
        ),
        "scan_echo": _run_capture(
            ["ros2", "topic", "echo", "--once", "--full-length", config.scan_topic],
            timeout_sec=10.0,
            output_path=config.artifact_dir / "scan_echo.txt",
        ),
        "status_echo": _run_capture(
            ["ros2", "topic", "echo", "--once", "--full-length", config.status_topic],
            timeout_sec=10.0,
            output_path=config.artifact_dir / "status_echo.txt",
        ),
        "scan_info": _run_capture(
            ["ros2", "topic", "info", "-v", config.scan_topic],
            timeout_sec=8.0,
            output_path=config.artifact_dir / "scan_info.txt",
        ),
        "scan_hz": _run_capture(
            ["ros2", "topic", "hz", config.scan_topic, "--window", "5"],
            timeout_sec=12.0,
            output_path=config.artifact_dir / "scan_hz.txt",
        ),
    }


def _build_summary(config: X2DriverSmokeConfig, *, samples: dict[str, str]) -> dict[str, object]:
    scan_echo = samples["scan_echo"]
    scan_info = samples["scan_info"]
    status_echo = samples["status_echo"]
    topic_list = samples["topic_list"]
    scan_hz = samples["scan_hz"]
    frame_id_ok = "frame_id: laser_frame" in scan_echo
    range_min = _extract_float(scan_echo, "range_min")
    range_max = _extract_float(scan_echo, "range_max")
    range_min_ok = range_min is not None and abs(range_min - config.range_min_m) < 0.01
    range_max_ok = range_max is not None and abs(range_max - config.range_max_m) < 0.01
    publisher_ok = "ydlidar_ros2_driver" in scan_info
    emulator_not_scan_publisher = "x2_serial_emulator" not in scan_info
    status_ok = "x2_serial_emulator" in status_echo
    topic_list_ok = config.scan_topic in topic_list and config.status_topic in topic_list
    hz_ok = "average rate:" in scan_hz or "average rate" in scan_hz
    rosbag_metadata = config.artifact_dir / "rosbag" / "metadata.yaml"
    rosbag_ok = rosbag_metadata.is_file() and rosbag_metadata.stat().st_size > 0
    summary = {
        "ok": all(
            (
                topic_list_ok,
                frame_id_ok,
                range_min_ok,
                range_max_ok,
                publisher_ok,
                emulator_not_scan_publisher,
                status_ok,
                hz_ok,
                rosbag_ok,
            )
        ),
        "scan_source": "x2_virtual_serial_vendor_driver",
        "virtual_serial_link": str(config.virtual_serial_link),
        "profile_path": str(config.profile_path),
        "duration_sec": config.duration_sec,
        "topic_list_ok": topic_list_ok,
        "frame_id_ok": frame_id_ok,
        "range_min": range_min,
        "range_min_ok": range_min_ok,
        "range_max": range_max,
        "range_max_ok": range_max_ok,
        "publisher_ok": publisher_ok,
        "emulator_not_scan_publisher": emulator_not_scan_publisher,
        "status_ok": status_ok,
        "hz_ok": hz_ok,
        "rosbag_ok": rosbag_ok,
        "rosbag": str(config.artifact_dir / "rosbag"),
    }
    return summary


def _extract_float(text: str, key: str) -> float | None:
    match = re.search(rf"^\s*{re.escape(key)}:\s*([-+0-9.eE]+)", text, flags=re.MULTILINE)
    if not match:
        return None
    return float(match.group(1))


def _write_run_config(config: X2DriverSmokeConfig) -> None:
    (config.artifact_dir / "run_config.json").write_text(
        json.dumps(_serializable_config(config), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (config.artifact_dir / "commands.json").write_text(
        json.dumps(
            {
                "emulator": build_emulator_command(config),
                "vendor_driver": build_vendor_driver_command(config),
                "rosbag_record": build_rosbag_record_command(config),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _serializable_config(config: X2DriverSmokeConfig) -> dict[str, object]:
    payload = asdict(config)
    for key, value in list(payload.items()):
        if isinstance(value, Path):
            payload[key] = str(value)
    return payload
