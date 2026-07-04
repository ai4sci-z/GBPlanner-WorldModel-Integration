from __future__ import annotations

import argparse
import math
import struct
from collections.abc import Sequence

from navlab.sim.gazebo_sensor.x2.protocol import (
    LIDAR_CMD_SCAN,
    PH_BYTES,
    corrected_angle_from_raw_deg,
    decode_angle_raw,
    decode_distance_raw,
)

HEADER_LEN = 10
MAX_PACKET_SAMPLES = 80
DEFAULT_BINS = 720


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge a real YDLidar X2/F2 serial stream to ROS /scan.")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--frame-id", default="laser_frame")
    parser.add_argument("--scan-topic", default="/scan")
    parser.add_argument("--range-min", type=float, default=0.10)
    parser.add_argument("--range-max", type=float, default=12.0)
    parser.add_argument("--bins", type=int, default=DEFAULT_BINS)
    parser.add_argument("--publish-min-samples", type=int, default=120)
    parser.add_argument("--read-chunk", type=int, default=4096)
    return parser.parse_args(argv)


def angle_delta_deg(start: float, end: float) -> float:
    delta = (end - start) % 360.0
    return delta if delta >= 0.0 else delta + 360.0


def _decode_packet(packet: bytes) -> tuple[bool, list[tuple[float, float]]]:
    if len(packet) < HEADER_LEN or packet[:2] != PH_BYTES:
        return False, []
    _ph, ct, sample_count, first_raw, last_raw, _checksum = struct.unpack_from("<HBBHHH", packet, 0)
    if sample_count <= 0 or sample_count > MAX_PACKET_SAMPLES:
        return False, []
    expected_len = HEADER_LEN + sample_count * 2
    if len(packet) < expected_len:
        return False, []
    first_angle = decode_angle_raw(first_raw)
    last_angle = decode_angle_raw(last_raw)
    span = angle_delta_deg(first_angle, last_angle)
    step = span / max(sample_count - 1, 1)
    samples: list[tuple[float, float]] = []
    for index in range(sample_count):
        distance_raw = struct.unpack_from("<H", packet, HEADER_LEN + index * 2)[0]
        distance_m = decode_distance_raw(distance_raw)
        raw_angle = (first_angle + step * index) % 360.0
        angle_deg = corrected_angle_from_raw_deg(raw_angle, distance_raw)
        samples.append((angle_deg, distance_m))
    ring_start = bool(ct & 0x01)
    return ring_start, samples


def _pack_scan(samples: list[tuple[float, float]], *, bins: int, range_min: float, range_max: float) -> list[float]:
    ranges = [math.inf] * bins
    for angle_deg, distance_m in samples:
        if not math.isfinite(distance_m) or distance_m < range_min or distance_m > range_max:
            continue
        angle_rad = math.radians(((angle_deg + 180.0) % 360.0) - 180.0)
        index = int((angle_rad + math.pi) / (2.0 * math.pi) * bins)
        index = max(0, min(bins - 1, index))
        if not math.isfinite(ranges[index]) or distance_m < ranges[index]:
            ranges[index] = distance_m
    return ranges


def run(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        import rclpy
        import serial
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import LaserScan
    except ModuleNotFoundError as exc:
        raise SystemExit("ydlidar_x2_scan_bridge requires ROS2 Python packages and pyserial.") from exc

    class X2ScanBridge(Node):
        def __init__(self) -> None:
            super().__init__("navlab_real_ydlidar_x2_scan_bridge")
            self._publisher = self.create_publisher(LaserScan, args.scan_topic, qos_profile_sensor_data)
            self._serial = serial.Serial(args.port, args.baud, timeout=0.02)
            self._serial.write(bytes([0xA5, LIDAR_CMD_SCAN]))
            self._serial.flush()
            self._buffer = bytearray()
            self._scan_samples: list[tuple[float, float]] = []
            self._scan_count = 0
            self.create_timer(0.01, self._poll)
            self.get_logger().info(f"real YDLidar bridge reading {args.port}@{args.baud} -> {args.scan_topic}")

        def destroy_node(self) -> bool:
            try:
                self._serial.close()
            finally:
                return super().destroy_node()

        def _poll(self) -> None:
            data = self._serial.read(args.read_chunk)
            if data:
                self._buffer.extend(data)
            self._drain_packets()

        def _drain_packets(self) -> None:
            while True:
                start = self._buffer.find(PH_BYTES)
                if start < 0:
                    del self._buffer[:-1]
                    return
                if start > 0:
                    del self._buffer[:start]
                if len(self._buffer) < HEADER_LEN:
                    return
                sample_count = self._buffer[3]
                if sample_count <= 0 or sample_count > MAX_PACKET_SAMPLES:
                    del self._buffer[:2]
                    continue
                packet_len = HEADER_LEN + sample_count * 2
                if len(self._buffer) < packet_len:
                    return
                packet = bytes(self._buffer[:packet_len])
                del self._buffer[:packet_len]
                ring_start, samples = _decode_packet(packet)
                if not samples:
                    continue
                if ring_start and len(self._scan_samples) >= args.publish_min_samples:
                    self._publish_scan()
                    self._scan_samples = []
                self._scan_samples.extend(samples)

        def _publish_scan(self) -> None:
            ranges = _pack_scan(
                self._scan_samples,
                bins=args.bins,
                range_min=args.range_min,
                range_max=args.range_max,
            )
            if not any(math.isfinite(value) for value in ranges):
                return
            msg = LaserScan()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = args.frame_id
            msg.angle_min = -math.pi
            msg.angle_max = math.pi
            msg.angle_increment = (msg.angle_max - msg.angle_min) / float(args.bins)
            msg.time_increment = 0.0
            msg.scan_time = 0.1
            msg.range_min = args.range_min
            msg.range_max = args.range_max
            msg.ranges = ranges
            self._publisher.publish(msg)
            self._scan_count += 1
            if self._scan_count % 20 == 1:
                valid = sum(1 for value in ranges if math.isfinite(value))
                self.get_logger().info(f"published real scan count={self._scan_count} valid_bins={valid}")

    rclpy.init(args=None)
    node = X2ScanBridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
