from __future__ import annotations

import os
import random
import time
from pathlib import Path

from navlab.sim.gazebo_sensor.x2.emulator import (
    X2SerialEmulator,
    X2SerialEmulatorConfig,
    build_static_scan_samples,
    jittered_scan_frequency_hz,
    samples_per_scan,
)
from navlab.sim.gazebo_sensor.x2.protocol import LIDAR_CMD_SCAN, LIDAR_CMD_STOP, PH_BYTES


def _read_available(fd: int, *, min_bytes: int = 1, timeout_sec: float = 0.5) -> bytes:
    deadline = time.monotonic() + timeout_sec
    data = bytearray()
    while time.monotonic() < deadline:
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            time.sleep(0.01)
            continue
        if chunk:
            data.extend(chunk)
            if len(data) >= min_bytes:
                break
        else:
            time.sleep(0.01)
    return bytes(data)


def test_x2_serial_emulator_creates_and_removes_virtual_serial_link(tmp_path: Path) -> None:
    link_path = tmp_path / "navlab_x2"
    emulator = X2SerialEmulator(X2SerialEmulatorConfig(virtual_serial_link=link_path))

    emulator.open()

    assert link_path.is_symlink()
    assert emulator.slave_path is not None
    assert os.readlink(link_path) == emulator.slave_path

    emulator.close()

    assert not link_path.exists()
    assert emulator.status().state == "closed"


def test_x2_serial_emulator_handles_scan_and_stop_commands(tmp_path: Path) -> None:
    link_path = tmp_path / "navlab_x2"
    with X2SerialEmulator(X2SerialEmulatorConfig(virtual_serial_link=link_path)) as emulator:
        slave_fd = os.open(link_path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            os.write(slave_fd, bytes([LIDAR_CMD_SCAN]))
            assert emulator.poll_commands() == bytes([LIDAR_CMD_SCAN])
            assert emulator.status().state == "scanning"
            assert emulator.status().last_command == "scan"

            os.write(slave_fd, bytes([LIDAR_CMD_STOP]))
            assert emulator.poll_commands() == bytes([LIDAR_CMD_STOP])
            assert emulator.status().state == "stopped"
            assert emulator.status().last_command == "stop"
            assert emulator.status().command_count == 2
        finally:
            os.close(slave_fd)


def test_x2_serial_emulator_writes_valid_packets_to_virtual_serial_consumer(tmp_path: Path) -> None:
    link_path = tmp_path / "navlab_x2"
    samples = build_static_scan_samples(sample_count=4, range_m=1.0)
    with X2SerialEmulator(X2SerialEmulatorConfig(virtual_serial_link=link_path)) as emulator:
        slave_fd = os.open(link_path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            emulator.start_scanning()
            byte_count = emulator.write_scan_once(samples)
            data = _read_available(slave_fd, min_bytes=byte_count)
        finally:
            os.close(slave_fd)

    assert data.startswith(PH_BYTES)
    assert byte_count == 18
    assert len(data) == byte_count
    assert emulator.status().packet_count == 1
    assert emulator.status().byte_count == byte_count


def test_x2_serial_emulator_does_not_write_when_not_scanning(tmp_path: Path) -> None:
    link_path = tmp_path / "navlab_x2"
    samples = build_static_scan_samples(sample_count=4, range_m=1.0)
    with X2SerialEmulator(X2SerialEmulatorConfig(virtual_serial_link=link_path)) as emulator:
        assert emulator.write_scan_once(samples) == 0
        assert emulator.status().packet_count == 0


def test_samples_per_scan_uses_x2_sample_rate_over_scan_frequency() -> None:
    assert samples_per_scan(sample_rate_hz=3000.0, scan_frequency_hz=7.0) == 429


def test_jittered_scan_frequency_stays_inside_x2_bounds() -> None:
    rng = random.Random(7)

    values = [
        jittered_scan_frequency_hz(
            base_hz=7.0,
            min_hz=4.0,
            max_hz=8.0,
            jitter_hz=3.0,
            rng=rng,
        )
        for _ in range(20)
    ]

    assert min(values) >= 4.0
    assert max(values) <= 8.0
    assert len(set(values)) > 1


def test_x2_serial_emulator_status_reports_jitter_config(tmp_path: Path) -> None:
    link_path = tmp_path / "navlab_x2"
    config = X2SerialEmulatorConfig(
        virtual_serial_link=link_path,
        scan_frequency_hz=7.0,
        scan_frequency_min_hz=4.0,
        scan_frequency_max_hz=8.0,
        scan_frequency_jitter_hz=0.25,
        random_seed=9,
    )
    samples = build_static_scan_samples(sample_count=4, range_m=1.0)
    with X2SerialEmulator(config) as emulator:
        emulator.start_scanning()
        emulator.write_scan_once(samples)
        status = emulator.status()

    assert status.scan_frequency_jitter_hz == 0.25
    assert status.random_seed == 9
    assert 4.0 <= status.latest_scan_frequency_hz <= 8.0
