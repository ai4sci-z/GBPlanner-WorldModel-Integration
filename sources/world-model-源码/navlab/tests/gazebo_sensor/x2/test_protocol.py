from __future__ import annotations

import math
import struct

import pytest

from navlab.sim.gazebo_sensor.x2.protocol import (
    DISTANCE_SCALE,
    PH,
    PH_BYTES,
    TRI_PACKMAXNODES,
    X2Sample,
    checksum_no_intensity,
    corrected_angle_from_raw_deg,
    decode_angle_raw,
    decode_distance_raw,
    encode_angle_deg,
    encode_distance_m,
    encode_packet,
    encode_scan_frequency_ct,
    encode_scan_packets,
    raw_angle_for_ideal_deg,
    triangle_angle_correction_deg,
)


def test_encode_distance_uses_sdk_scale_and_vendor_range_bounds() -> None:
    assert encode_distance_m(1.0) == DISTANCE_SCALE
    assert encode_distance_m(8.0) == 32000
    assert encode_distance_m(0.09) == 0
    assert encode_distance_m(8.01) == 0
    assert encode_distance_m(math.inf) == 0
    assert decode_distance_raw(4000) == 1.0


def test_encode_angle_uses_sdk_units() -> None:
    assert encode_angle_deg(0.0) == 1
    assert encode_angle_deg(90.0) == 11521
    assert encode_angle_deg(180.0) == 23041
    assert decode_angle_raw(encode_angle_deg(45.5)) == 45.5


def test_triangle_correction_matches_sdk_formula() -> None:
    assert triangle_angle_correction_deg(0) == 0.0
    assert triangle_angle_correction_deg(4000) == pytest.approx(-6.770, abs=0.01)


def test_raw_angle_inversion_round_trips_through_sdk_correction() -> None:
    ideal_angle = 45.0
    distance_raw = 4000

    raw_angle = raw_angle_for_ideal_deg(ideal_angle, distance_raw)
    corrected = corrected_angle_from_raw_deg(raw_angle, distance_raw)

    assert corrected == pytest.approx(ideal_angle, abs=1e-9)


def test_packet_layout_and_checksum() -> None:
    samples = (
        X2Sample(angle_deg=0.0, range_m=1.0),
        X2Sample(angle_deg=1.0, range_m=2.0),
        X2Sample(angle_deg=2.0, range_m=0.05),
        X2Sample(angle_deg=3.0, range_m=9.0),
    )

    packet = encode_packet(samples, scan_frequency_hz=7.0)
    header, ct, lsn, fsa, lsa, checksum = struct.unpack("<HBBHHH", packet[:10])
    distances = struct.unpack("<HHHH", packet[10:])

    assert packet[:2] == PH_BYTES
    assert header == PH
    assert ct == encode_scan_frequency_ct(7.0)
    assert lsn == len(samples)
    assert distances == (4000, 8000, 0, 0)
    assert fsa == encode_angle_deg(raw_angle_for_ideal_deg(0.0, 4000))
    assert lsa == encode_angle_deg(raw_angle_for_ideal_deg(3.0, 0))
    assert checksum == checksum_no_intensity(
        ct=ct,
        encoded_first_angle=fsa,
        encoded_last_angle=lsa,
        distances_raw=distances,
    )


def test_encode_scan_packets_splits_at_vendor_packet_limit() -> None:
    samples = tuple(X2Sample(angle_deg=float(index), range_m=1.0) for index in range(TRI_PACKMAXNODES + 1))

    packets = encode_scan_packets(samples)

    assert len(packets) == 2
    assert packets[0][2] == encode_scan_frequency_ct(7.0, ring_start=True)
    assert packets[1][2] == encode_scan_frequency_ct(7.0)
    assert packets[0][3] == TRI_PACKMAXNODES
    assert packets[1][3] == 1


def test_encode_packet_rejects_empty_or_too_large_chunks() -> None:
    with pytest.raises(ValueError, match="at least one sample"):
        encode_packet(())

    samples = tuple(X2Sample(angle_deg=float(index), range_m=1.0) for index in range(TRI_PACKMAXNODES + 1))
    with pytest.raises(ValueError, match="cannot exceed"):
        encode_packet(samples)
