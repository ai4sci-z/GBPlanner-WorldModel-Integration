from __future__ import annotations

import errno
import json
import math
import os
import pty
import random
import termios
import time
import tty
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from navlab.sim.gazebo_sensor.x2.protocol import (
    DEFAULT_RANGE_MAX_M,
    DEFAULT_RANGE_MIN_M,
    DEFAULT_SCAN_FREQUENCY_HZ,
    LIDAR_CMD_FORCE_SCAN,
    LIDAR_CMD_RESET,
    LIDAR_CMD_SCAN,
    LIDAR_CMD_STOP,
    X2Sample,
    encode_scan_packets,
)

DEFAULT_VIRTUAL_SERIAL_LINK = Path("/tmp/navlab_x2")
DEFAULT_STATUS_TOPIC = "/sim/x2/status"
DEFAULT_SAMPLE_RATE_HZ = 3000.0

COMMAND_NAMES = {
    LIDAR_CMD_SCAN: "scan",
    LIDAR_CMD_FORCE_SCAN: "force_scan",
    LIDAR_CMD_STOP: "stop",
    LIDAR_CMD_RESET: "reset",
}


@dataclass(frozen=True, slots=True)
class X2SerialEmulatorConfig:
    virtual_serial_link: Path = DEFAULT_VIRTUAL_SERIAL_LINK
    scan_frequency_hz: float = DEFAULT_SCAN_FREQUENCY_HZ
    scan_frequency_min_hz: float = 4.0
    scan_frequency_max_hz: float = 8.0
    scan_frequency_jitter_hz: float = 0.0
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ
    range_min_m: float = DEFAULT_RANGE_MIN_M
    range_max_m: float = DEFAULT_RANGE_MAX_M
    status_topic: str = DEFAULT_STATUS_TOPIC
    replace_existing_link: bool = True
    random_seed: int | None = None


@dataclass(frozen=True, slots=True)
class X2SerialEmulatorStatus:
    source: str
    state: str
    virtual_serial_link: str
    slave_path: str | None
    scan_frequency_hz: float
    scan_frequency_min_hz: float
    scan_frequency_max_hz: float
    scan_frequency_jitter_hz: float
    latest_scan_frequency_hz: float
    sample_rate_hz: float
    range_min_m: float
    range_max_m: float
    random_seed: int | None
    packet_count: int
    byte_count: int
    command_count: int
    last_command: str | None
    last_command_byte: int | None
    updated_monotonic_sec: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, sort_keys=True)


def build_static_scan_samples(
    *,
    sample_count: int,
    range_m: float,
) -> tuple[X2Sample, ...]:
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    angle_step = 360.0 / sample_count
    return tuple(X2Sample(angle_deg=index * angle_step, range_m=range_m) for index in range(sample_count))


def samples_per_scan(*, sample_rate_hz: float, scan_frequency_hz: float) -> int:
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
    if not math.isfinite(scan_frequency_hz) or scan_frequency_hz <= 0:
        raise ValueError("scan_frequency_hz must be positive")
    return max(1, round(sample_rate_hz / scan_frequency_hz))


def jittered_scan_frequency_hz(
    *,
    base_hz: float,
    min_hz: float,
    max_hz: float,
    jitter_hz: float,
    rng: random.Random,
) -> float:
    if not math.isfinite(base_hz) or base_hz <= 0:
        raise ValueError("base_hz must be positive")
    if not math.isfinite(min_hz) or min_hz <= 0:
        raise ValueError("min_hz must be positive")
    if not math.isfinite(max_hz) or max_hz <= 0:
        raise ValueError("max_hz must be positive")
    if min_hz > max_hz:
        raise ValueError("min_hz must be <= max_hz")
    if jitter_hz < 0:
        raise ValueError("jitter_hz must be non-negative")
    if jitter_hz == 0:
        return min(max(base_hz, min_hz), max_hz)
    return min(max(base_hz + rng.uniform(-jitter_hz, jitter_hz), min_hz), max_hz)


class X2SerialEmulator:
    def __init__(self, config: X2SerialEmulatorConfig | None = None) -> None:
        self.config = config or X2SerialEmulatorConfig()
        self._master_fd: int | None = None
        self._slave_fd: int | None = None
        self._slave_path: str | None = None
        self._state = "closed"
        self._packet_count = 0
        self._byte_count = 0
        self._command_count = 0
        self._last_command: str | None = None
        self._last_command_byte: int | None = None
        self._updated_monotonic_sec = time.monotonic()
        self._rng = random.Random(self.config.random_seed)
        self._latest_scan_frequency_hz = self.config.scan_frequency_hz

    @property
    def slave_path(self) -> str | None:
        return self._slave_path

    @property
    def is_open(self) -> bool:
        return self._master_fd is not None and self._slave_fd is not None

    @property
    def is_scanning(self) -> bool:
        return self._state == "scanning"

    def __enter__(self) -> X2SerialEmulator:
        self.open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def open(self) -> None:
        if self.is_open:
            return

        master_fd, slave_fd = pty.openpty()
        tty.setraw(slave_fd)
        attrs = termios.tcgetattr(slave_fd)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)
        os.set_blocking(master_fd, False)
        os.set_blocking(slave_fd, False)

        slave_path = os.ttyname(slave_fd)
        self._link_slave_path(slave_path)
        self._master_fd = master_fd
        self._slave_fd = slave_fd
        self._slave_path = slave_path
        self._state = "idle"
        self._touch()

    def close(self) -> None:
        link_path = self.config.virtual_serial_link
        if link_path.is_symlink() and self._slave_path is not None and os.readlink(link_path) == self._slave_path:
            link_path.unlink()

        for fd in (self._master_fd, self._slave_fd):
            if fd is not None:
                os.close(fd)

        self._master_fd = None
        self._slave_fd = None
        self._slave_path = None
        self._state = "closed"
        self._touch()

    def start_scanning(self) -> None:
        self._state = "scanning"
        self._touch()

    def stop_scanning(self) -> None:
        self._state = "stopped"
        self._touch()

    def reset(self) -> None:
        self._state = "idle"
        self._touch()

    def poll_commands(self) -> bytes:
        self._require_open()
        assert self._master_fd is not None
        chunks: list[bytes] = []
        while True:
            try:
                data = os.read(self._master_fd, 4096)
            except BlockingIOError:
                break
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    break
                raise
            if not data:
                break
            chunks.append(data)
            for byte in data:
                self._handle_command_byte(byte)
        return b"".join(chunks)

    def write_scan_once(self, samples: tuple[X2Sample, ...], *, require_scanning: bool = True) -> int:
        if require_scanning and not self.is_scanning:
            return 0
        self._latest_scan_frequency_hz = jittered_scan_frequency_hz(
            base_hz=self.config.scan_frequency_hz,
            min_hz=self.config.scan_frequency_min_hz,
            max_hz=self.config.scan_frequency_max_hz,
            jitter_hz=self.config.scan_frequency_jitter_hz,
            rng=self._rng,
        )
        packets = encode_scan_packets(
            samples,
            scan_frequency_hz=self._latest_scan_frequency_hz,
            range_min_m=self.config.range_min_m,
            range_max_m=self.config.range_max_m,
        )
        return self.write_packets(packets)

    def write_packets(self, packets: list[bytes]) -> int:
        self._require_open()
        assert self._master_fd is not None
        byte_count = 0
        for packet in packets:
            byte_count += os.write(self._master_fd, packet)
        self._packet_count += len(packets)
        self._byte_count += byte_count
        self._touch()
        return byte_count

    def status(self) -> X2SerialEmulatorStatus:
        return X2SerialEmulatorStatus(
            source="x2_serial_emulator",
            state=self._state,
            virtual_serial_link=str(self.config.virtual_serial_link),
            slave_path=self._slave_path,
            scan_frequency_hz=self.config.scan_frequency_hz,
            scan_frequency_min_hz=self.config.scan_frequency_min_hz,
            scan_frequency_max_hz=self.config.scan_frequency_max_hz,
            scan_frequency_jitter_hz=self.config.scan_frequency_jitter_hz,
            latest_scan_frequency_hz=self._latest_scan_frequency_hz,
            sample_rate_hz=self.config.sample_rate_hz,
            range_min_m=self.config.range_min_m,
            range_max_m=self.config.range_max_m,
            random_seed=self.config.random_seed,
            packet_count=self._packet_count,
            byte_count=self._byte_count,
            command_count=self._command_count,
            last_command=self._last_command,
            last_command_byte=self._last_command_byte,
            updated_monotonic_sec=self._updated_monotonic_sec,
        )

    def status_dict(self) -> dict[str, Any]:
        return asdict(self.status())

    def status_json(self) -> str:
        return self.status().to_json()

    def _link_slave_path(self, slave_path: str) -> None:
        link_path = self.config.virtual_serial_link
        link_path.parent.mkdir(parents=True, exist_ok=True)
        if link_path.exists() or link_path.is_symlink():
            if not self.config.replace_existing_link:
                raise FileExistsError(link_path)
            link_path.unlink()
        link_path.symlink_to(slave_path)

    def _handle_command_byte(self, byte: int) -> None:
        if byte not in COMMAND_NAMES:
            return
        self._command_count += 1
        self._last_command = COMMAND_NAMES[byte]
        self._last_command_byte = byte
        if byte in (LIDAR_CMD_SCAN, LIDAR_CMD_FORCE_SCAN):
            self._state = "scanning"
        elif byte == LIDAR_CMD_STOP:
            self._state = "stopped"
        elif byte == LIDAR_CMD_RESET:
            self._state = "idle"
        self._touch()

    def _require_open(self) -> None:
        if not self.is_open:
            raise RuntimeError("X2 serial emulator is not open")

    def _touch(self) -> None:
        self._updated_monotonic_sec = time.monotonic()
