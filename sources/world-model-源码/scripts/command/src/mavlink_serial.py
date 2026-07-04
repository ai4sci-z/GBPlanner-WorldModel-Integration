"""Bridge two serial ports in full duplex for MAVLink transport."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import serial

from src.command_logging import logger


@dataclass
class BridgeStats:
    a_to_b_bytes: int = 0
    b_to_a_bytes: int = 0


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    port_a: str = "/dev/ttyUSB1"
    baud_a: int = 115200
    port_b: str = "/dev/ttyUSB0"
    baud_b: int = 115200
    read_size: int = 1024
    log_file: str = ""
    log_level: str = "INFO"
    stats_interval: float = 5.0
    reconnect_delay: float = 2.0


def open_serial(port: str, baud: int) -> serial.Serial:
    return serial.Serial(
        port=port,
        baudrate=baud,
        timeout=0.1,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )


def forward(
    src: serial.Serial,
    dst: serial.Serial,
    direction: str,
    read_size: int,
    stop_event: threading.Event,
    stats: BridgeStats,
) -> None:
    while not stop_event.is_set():
        data = src.read(read_size)
        if not data:
            continue

        dst.write(data)
        dst.flush()

        if direction == "A->B":
            stats.a_to_b_bytes += len(data)
        else:
            stats.b_to_a_bytes += len(data)

        logger.debug("{} forwarded {} bytes", direction, len(data))


def log_stats(stop_event: threading.Event, stats: BridgeStats, interval: float) -> None:
    while not stop_event.wait(interval):
        logger.info("traffic A->B={} bytes B->A={} bytes", stats.a_to_b_bytes, stats.b_to_a_bytes)


def close_serial(port: serial.Serial | None) -> None:
    if not port:
        return

    try:
        if port.is_open:
            port.close()
    except Exception as exc:  # pragma: no cover - best effort close path
        logger.warning("close failed for {}: {}", getattr(port, "port", "unknown"), exc)


def run_bridge(config: BridgeConfig) -> None:
    while True:
        port_a: serial.Serial | None = None
        port_b: serial.Serial | None = None
        stop_event = threading.Event()
        stats = BridgeStats()

        try:
            logger.info("opening {} @ {}", config.port_a, config.baud_a)
            port_a = open_serial(config.port_a, config.baud_a)
            logger.info("opening {} @ {}", config.port_b, config.baud_b)
            port_b = open_serial(config.port_b, config.baud_b)
            logger.info("bridge ready: {} <-> {}", config.port_a, config.port_b)

            threads = [
                threading.Thread(
                    target=forward,
                    name="bridge-a-to-b",
                    args=(port_a, port_b, "A->B", config.read_size, stop_event, stats),
                    daemon=True,
                ),
                threading.Thread(
                    target=forward,
                    name="bridge-b-to-a",
                    args=(port_b, port_a, "B->A", config.read_size, stop_event, stats),
                    daemon=True,
                ),
                threading.Thread(
                    target=log_stats,
                    name="bridge-stats",
                    args=(stop_event, stats, config.stats_interval),
                    daemon=True,
                ),
            ]

            for thread in threads:
                thread.start()

            while all(thread.is_alive() for thread in threads[:2]):
                time.sleep(0.5)

            raise RuntimeError("bridge worker stopped unexpectedly")

        except KeyboardInterrupt:
            logger.info("stopped by user")
            stop_event.set()
            close_serial(port_a)
            close_serial(port_b)
            return
        except Exception as exc:
            logger.exception("bridge error: {}", exc)
            stop_event.set()
            close_serial(port_a)
            close_serial(port_b)
            logger.info("retrying in {:.1f} seconds", config.reconnect_delay)
            time.sleep(config.reconnect_delay)
