from __future__ import annotations

import math
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

PH = 0x55AA
PH_BYTES = b"\xaa\x55"
TRI_PACKMAXNODES = 80

DISTANCE_SCALE = 4000
ANGLE_SCALE = 64
ANGLE_SHIFT = 1
CT_FREQUENCY_SCALE = 10

DEFAULT_SCAN_FREQUENCY_HZ = 7.0
DEFAULT_RANGE_MIN_M = 0.1
DEFAULT_RANGE_MAX_M = 8.0

LIDAR_CMD_SCAN = 0x60
LIDAR_CMD_FORCE_SCAN = 0x61
LIDAR_CMD_STOP = 0x65
LIDAR_CMD_RESET = 0x80


@dataclass(frozen=True, slots=True)
class X2Sample:
    angle_deg: float
    range_m: float


@dataclass(frozen=True, slots=True)
class X2EncodedSample:
    ideal_angle_deg: float
    raw_angle_deg: float
    distance_raw: int


def normalize_angle_deg(angle_deg: float) -> float:
    return angle_deg % 360.0


def encode_distance_m(
    range_m: float,
    *,
    range_min_m: float = DEFAULT_RANGE_MIN_M,
    range_max_m: float = DEFAULT_RANGE_MAX_M,
) -> int:
    if not math.isfinite(range_m) or range_m < range_min_m or range_m > range_max_m:
        return 0
    return max(0, min(0xFFFF, int(range_m * DISTANCE_SCALE)))


def decode_distance_raw(distance_raw: int) -> float:
    return distance_raw / DISTANCE_SCALE


def triangle_angle_correction_deg(distance_raw: int) -> float:
    if distance_raw <= 0:
        return 0.0
    distance_quarter_mm = distance_raw / 4.0
    correction_rad = math.atan(((21.8 * (155.3 - distance_quarter_mm)) / 155.3) / distance_quarter_mm)
    return math.degrees(correction_rad)


def raw_angle_for_ideal_deg(ideal_angle_deg: float, distance_raw: int) -> float:
    return normalize_angle_deg(ideal_angle_deg - triangle_angle_correction_deg(distance_raw))


def corrected_angle_from_raw_deg(raw_angle_deg: float, distance_raw: int) -> float:
    return normalize_angle_deg(raw_angle_deg + triangle_angle_correction_deg(distance_raw))


def encode_angle_deg(angle_deg: float) -> int:
    return ((int(normalize_angle_deg(angle_deg) * ANGLE_SCALE) << ANGLE_SHIFT) | 0x01) & 0xFFFF


def decode_angle_raw(encoded_angle: int) -> float:
    return (encoded_angle >> ANGLE_SHIFT) / ANGLE_SCALE


def encode_scan_frequency_ct(
    scan_frequency_hz: float = DEFAULT_SCAN_FREQUENCY_HZ,
    *,
    ring_start: bool = False,
) -> int:
    if not math.isfinite(scan_frequency_hz) or scan_frequency_hz <= 0:
        raise ValueError("scan_frequency_hz must be positive")
    ct = (int(scan_frequency_hz * CT_FREQUENCY_SCALE) << 1) | (0x01 if ring_start else 0x00)
    if ct > 0xFF:
        raise ValueError("scan_frequency_hz is too large for an X2 CT byte")
    return ct


def checksum_no_intensity(
    *,
    ct: int,
    encoded_first_angle: int,
    encoded_last_angle: int,
    distances_raw: Sequence[int],
) -> int:
    checksum = PH ^ encoded_first_angle
    for distance_raw in distances_raw:
        checksum ^= distance_raw
    checksum ^= (len(distances_raw) << 8) | ct
    checksum ^= encoded_last_angle
    return checksum & 0xFFFF


def split_samples(
    samples: Sequence[X2Sample],
    *,
    max_samples: int = TRI_PACKMAXNODES,
) -> Iterable[tuple[X2Sample, ...]]:
    if max_samples <= 0:
        raise ValueError("max_samples must be positive")
    for index in range(0, len(samples), max_samples):
        yield tuple(samples[index : index + max_samples])


def encode_samples(
    samples: Sequence[X2Sample],
    *,
    range_min_m: float = DEFAULT_RANGE_MIN_M,
    range_max_m: float = DEFAULT_RANGE_MAX_M,
) -> tuple[X2EncodedSample, ...]:
    encoded: list[X2EncodedSample] = []
    for sample in samples:
        distance_raw = encode_distance_m(sample.range_m, range_min_m=range_min_m, range_max_m=range_max_m)
        raw_angle = raw_angle_for_ideal_deg(sample.angle_deg, distance_raw)
        encoded.append(
            X2EncodedSample(
                ideal_angle_deg=normalize_angle_deg(sample.angle_deg),
                raw_angle_deg=raw_angle,
                distance_raw=distance_raw,
            )
        )
    return tuple(encoded)


def encode_packet(
    samples: Sequence[X2Sample],
    *,
    scan_frequency_hz: float = DEFAULT_SCAN_FREQUENCY_HZ,
    range_min_m: float = DEFAULT_RANGE_MIN_M,
    range_max_m: float = DEFAULT_RANGE_MAX_M,
    ring_start: bool = False,
) -> bytes:
    if not samples:
        raise ValueError("X2 packet requires at least one sample")
    if len(samples) > TRI_PACKMAXNODES:
        raise ValueError(f"X2 triangle packet cannot exceed {TRI_PACKMAXNODES} samples")

    ct = encode_scan_frequency_ct(scan_frequency_hz, ring_start=ring_start)
    encoded_samples = encode_samples(samples, range_min_m=range_min_m, range_max_m=range_max_m)
    distances_raw = tuple(sample.distance_raw for sample in encoded_samples)
    encoded_first_angle = encode_angle_deg(encoded_samples[0].raw_angle_deg)
    encoded_last_angle = encode_angle_deg(encoded_samples[-1].raw_angle_deg)
    checksum = checksum_no_intensity(
        ct=ct,
        encoded_first_angle=encoded_first_angle,
        encoded_last_angle=encoded_last_angle,
        distances_raw=distances_raw,
    )

    packet = bytearray()
    packet.extend(struct.pack("<HBBHHH", PH, ct, len(samples), encoded_first_angle, encoded_last_angle, checksum))
    for distance_raw in distances_raw:
        packet.extend(struct.pack("<H", distance_raw))
    return bytes(packet)


def encode_scan_packets(
    samples: Sequence[X2Sample],
    *,
    scan_frequency_hz: float = DEFAULT_SCAN_FREQUENCY_HZ,
    range_min_m: float = DEFAULT_RANGE_MIN_M,
    range_max_m: float = DEFAULT_RANGE_MAX_M,
) -> list[bytes]:
    packets: list[bytes] = []
    for index, chunk in enumerate(split_samples(samples)):
        packets.append(
            encode_packet(
                chunk,
                scan_frequency_hz=scan_frequency_hz,
                range_min_m=range_min_m,
                range_max_m=range_max_m,
                ring_start=index == 0,
            )
        )
    return packets
