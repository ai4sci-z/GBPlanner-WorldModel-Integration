#!/usr/bin/env python3
"""Continuously print FCU rangefinder MAVLink values from the serial port."""

from __future__ import annotations

import argparse
import time
from typing import Any

from pymavlink import mavutil

DEFAULT_DEVICE = "/dev/ttyUSB1"
DEFAULT_BAUD = 115200


def _orientation_name(value: int) -> str:
    enum = mavutil.mavlink.enums.get("MAV_SENSOR_ORIENTATION", {})
    entry = enum.get(value)
    return entry.name if entry else str(value)


def _distance_sensor_line(now: str, msg: Any) -> str:
    orientation = int(getattr(msg, "orientation", -1))
    current_cm = int(getattr(msg, "current_distance", -1))
    return (
        f"{now} DISTANCE_SENSOR "
        f"current_cm={current_cm} "
        f"current_m={current_cm / 100.0:.3f} "
        f"min_cm={getattr(msg, 'min_distance', -1)} "
        f"max_cm={getattr(msg, 'max_distance', -1)} "
        f"orientation={orientation}:{_orientation_name(orientation)} "
        f"quality={getattr(msg, 'signal_quality', -1)} "
        f"id={getattr(msg, 'id', -1)}"
    )


def _rangefinder_line(now: str, msg: Any) -> str:
    return (
        f"{now} RANGEFINDER "
        f"distance_m={float(getattr(msg, 'distance', 0.0)):.3f} "
        f"voltage={float(getattr(msg, 'voltage', 0.0)):.3f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch /dev/ttyUSB1 MAVLink RANGEFINDER and DISTANCE_SENSOR values.")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help=f"FCU serial device, default: {DEFAULT_DEVICE}")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"FCU baud rate, default: {DEFAULT_BAUD}")
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Seconds to read before exiting. Default 0 means run until Ctrl-C.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Read timeout seconds before printing a no-data line.",
    )
    args = parser.parse_args()

    print(f"reading {args.device} @ {args.baud}; Ctrl-C stop")
    print("lift/lower the vehicle and watch current_cm / distance_m\n")

    conn = mavutil.mavlink_connection(
        args.device,
        baud=args.baud,
        dialect="ardupilotmega",
        autoreconnect=False,
    )

    started = time.monotonic()
    try:
        while args.duration <= 0 or time.monotonic() - started < args.duration:
            msg = conn.recv_match(type=["RANGEFINDER", "DISTANCE_SENSOR"], blocking=True, timeout=args.timeout)
            now = time.strftime("%H:%M:%S")
            if msg is None:
                print(f"{now} timeout: no RANGEFINDER/DISTANCE_SENSOR msg")
                continue

            msg_type = msg.get_type()
            if msg_type == "DISTANCE_SENSOR":
                print(_distance_sensor_line(now, msg), flush=True)
            elif msg_type == "RANGEFINDER":
                print(_rangefinder_line(now, msg), flush=True)
    except KeyboardInterrupt:
        print("\nstopped")
        return 130
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
