from __future__ import annotations

import argparse
import errno
import json
import logging
import math
import os
import pty
import termios
import time
import tty
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from navlab.sim.gazebo_sensor.config import DownRangefinderRuntimeConfig

DEFAULT_VIRTUAL_SERIAL_LINK = Path("/tmp/navlab_benewake_tfmini")
DEFAULT_BAUD = 115200
LOGGER = logging.getLogger("benewake_tfmini_serial")


@dataclass(frozen=True, slots=True)
class RangefinderReading:
    distance_m: float
    stamp_monotonic: float


@dataclass(frozen=True, slots=True)
class BenewakeTFminiStatus:
    source: str
    state: str
    virtual_serial_link: str
    slave_path: str | None
    frame_count: int
    byte_count: int
    latest_distance_m: float | None
    latest_input_age_sec: float | None
    rate_hz: float
    min_distance_m: float
    max_distance_m: float
    updated_monotonic_sec: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, sort_keys=True)


def encode_tfmini_frame(distance_m: float) -> bytes:
    if not math.isfinite(distance_m) or distance_m < 0:
        raise ValueError("distance_m must be a finite non-negative value")
    distance_cm = max(0, min(0xFFFF, int(round(distance_m * 100.0))))
    frame = bytearray(
        [
            0x59,
            0x59,
            distance_cm & 0xFF,
            distance_cm >> 8,
            0x01,
            0x01,
            0x07,
            0x00,
            0x00,
        ]
    )
    frame[8] = sum(frame[:8]) & 0xFF
    return bytes(frame)


def select_down_range_m(ranges: Sequence[float], *, min_m: float, max_m: float) -> float | None:
    valid = [float(value) for value in ranges if min_m <= float(value) <= max_m and math.isfinite(float(value))]
    if not valid:
        return None
    return min(valid)


def configure_logging(log_file: str | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


class BenewakeTFminiSerialEmulator:
    def __init__(
        self,
        *,
        virtual_serial_link: Path = DEFAULT_VIRTUAL_SERIAL_LINK,
        rate_hz: float = 20.0,
        min_distance_m: float = 0.05,
        max_distance_m: float = 6.0,
    ) -> None:
        self.virtual_serial_link = virtual_serial_link
        self.rate_hz = rate_hz
        self.min_distance_m = min_distance_m
        self.max_distance_m = max_distance_m
        self._master_fd: int | None = None
        self._slave_fd: int | None = None
        self._slave_path: str | None = None
        self._frame_count = 0
        self._byte_count = 0
        self._updated_monotonic_sec = time.monotonic()
        self._latest: RangefinderReading | None = None

    @property
    def slave_path(self) -> str | None:
        return self._slave_path

    @property
    def is_open(self) -> bool:
        return self._master_fd is not None and self._slave_fd is not None

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
        self._touch()

    def close(self) -> None:
        link_path = self.virtual_serial_link
        if link_path.is_symlink() and self._slave_path is not None and os.readlink(link_path) == self._slave_path:
            link_path.unlink()

        for fd in (self._master_fd, self._slave_fd):
            if fd is not None:
                os.close(fd)

        self._master_fd = None
        self._slave_fd = None
        self._slave_path = None
        self._touch()

    def update_distance(self, distance_m: float) -> None:
        if distance_m < self.min_distance_m or distance_m > self.max_distance_m or not math.isfinite(distance_m):
            return
        self._latest = RangefinderReading(distance_m=distance_m, stamp_monotonic=time.monotonic())
        self._touch()

    def write_latest_frame(self, *, max_age_sec: float = 1.0) -> int:
        self._require_open()
        if self._latest is None:
            return 0
        if time.monotonic() - self._latest.stamp_monotonic > max_age_sec:
            return 0
        frame = encode_tfmini_frame(self._latest.distance_m)
        assert self._master_fd is not None
        try:
            written = os.write(self._master_fd, frame)
        except BlockingIOError:
            return 0
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return 0
            raise
        self._frame_count += 1
        self._byte_count += written
        self._touch()
        return written

    def status(self) -> BenewakeTFminiStatus:
        latest_age = None if self._latest is None else time.monotonic() - self._latest.stamp_monotonic
        return BenewakeTFminiStatus(
            source="benewake_tfmini_serial_emulator",
            state="open" if self.is_open else "closed",
            virtual_serial_link=str(self.virtual_serial_link),
            slave_path=self._slave_path,
            frame_count=self._frame_count,
            byte_count=self._byte_count,
            latest_distance_m=None if self._latest is None else self._latest.distance_m,
            latest_input_age_sec=latest_age,
            rate_hz=self.rate_hz,
            min_distance_m=self.min_distance_m,
            max_distance_m=self.max_distance_m,
            updated_monotonic_sec=self._updated_monotonic_sec,
        )

    def status_dict(self) -> dict[str, object]:
        return asdict(self.status())

    def _require_open(self) -> None:
        if not self.is_open:
            raise RuntimeError("Benewake TFmini serial emulator is not open")

    def _link_slave_path(self, slave_path: str) -> None:
        link_path = self.virtual_serial_link
        if link_path.exists() or link_path.is_symlink():
            if not link_path.is_symlink():
                raise FileExistsError(f"{link_path} exists and is not a symlink")
            link_path.unlink()
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(slave_path)

    def _touch(self) -> None:
        self._updated_monotonic_sec = time.monotonic()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Benewake TFmini serial emulator for ArduPilot SITL Serial7.")
    parser.add_argument("--virtual-serial-link", type=Path)
    parser.add_argument("--duration-sec", type=float, default=0.0)
    parser.add_argument("--log-file")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    configure_logging(args.log_file)
    config = DownRangefinderRuntimeConfig.load()
    virtual_serial_link = args.virtual_serial_link or config.virtual_serial_link
    emulator = BenewakeTFminiSerialEmulator(
        virtual_serial_link=virtual_serial_link,
        rate_hz=config.rate_hz,
        min_distance_m=config.min_distance_m,
        max_distance_m=config.max_distance_m,
    )

    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
        from sensor_msgs.msg import LaserScan
    except ModuleNotFoundError as exc:
        raise SystemExit("Benewake TFmini serial emulator requires ROS2 packages.") from exc

    class BenewakeTFminiNode(Node):
        def __init__(self) -> None:
            super().__init__("benewake_tfmini_serial_emulator")
            self._started_at = time.monotonic()
            emulator.open()
            self.create_subscription(LaserScan, config.scan_ideal_topic, self._handle_scan, 10)
            self.create_timer(max(0.001, 1.0 / config.rate_hz), self._write_frame)
            self.create_timer(2.0, self._log_status)
            if args.duration_sec > 0:
                self.create_timer(0.1, self._stop_when_done)
            LOGGER.info(
                "Benewake TFmini serial emulator opened link=%s slave=%s scan_topic=%s",
                virtual_serial_link,
                emulator.slave_path,
                config.scan_ideal_topic,
            )

        def _handle_scan(self, msg: LaserScan) -> None:
            distance = select_down_range_m(msg.ranges, min_m=config.min_distance_m, max_m=config.max_distance_m)
            if distance is not None:
                emulator.update_distance(distance)

        def _write_frame(self) -> None:
            emulator.write_latest_frame()

        def _log_status(self) -> None:
            LOGGER.info("Benewake TFmini status %s", emulator.status().to_json())

        def _stop_when_done(self) -> None:
            if time.monotonic() - self._started_at >= args.duration_sec:
                raise SystemExit(0)

        def destroy_node(self) -> bool:
            emulator.close()
            return super().destroy_node()

    rclpy.init(args=None)
    node = BenewakeTFminiNode()
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
