"""Deterministic scene + cloud packing shared by the ROS1 oracle and ROS2 port
publishers. Both sides import THIS file, so the PointCloud2 payload bytes are
identical by construction. No randomness, no time dependence.

Scene: an 8x8x3 m room (4 walls + floor) plus a square pillar, sampled on a
fixed grid. Sensor: 12 poses on a circle (identity rotation), cloud expressed
in the sensor frame as p_C = p_W - t (float32).
"""
import math
import struct

GRID = 0.08          # wall/floor sampling step (m)
ROOM = 4.0           # half extent in x/y
HEIGHT = 3.0
N_FRAMES = 12
SENSOR_Z = 1.2
CIRCLE_R = 1.5

_FRANGE = lambda a, b, s: [a + i * s for i in range(int((b - a) / s) + 1)]


def gen_world_points():
    pts = []
    zs = _FRANGE(0.0, HEIGHT, GRID)
    xs = _FRANGE(-ROOM, ROOM, GRID)
    # 4 walls
    for z in zs:
        for x in xs:
            pts.append((x, -ROOM, z))
            pts.append((x, ROOM, z))
            pts.append((-ROOM, x, z))
            pts.append((ROOM, x, z))
    # floor
    for x in _FRANGE(-ROOM, ROOM, GRID * 2):
        for y in _FRANGE(-ROOM, ROOM, GRID * 2):
            pts.append((x, y, 0.0))
    # pillar (square, 0.4 half-width at (1.5, 0.5)), all 4 faces
    for z in zs:
        for t in _FRANGE(-0.4, 0.4, GRID):
            pts.append((1.5 + t, 0.1, z))
            pts.append((1.5 + t, 0.9, z))
            pts.append((1.1, 0.5 + t, z))
            pts.append((1.9, 0.5 + t, z))
    return pts


def sensor_pose(k):
    """Frame k sensor position (identity rotation).

    Quantized to multiples of 1/1024 (exact binary fractions): libm trig may
    differ by 1 ulp between the noetic (20.04) and jazzy (24.04) containers,
    and the payload must be byte-identical on both sides.
    """
    ang = 2.0 * math.pi * k / N_FRAMES
    q = lambda v: round(v * 1024.0) / 1024.0
    return (q(CIRCLE_R * math.cos(ang)), q(CIRCLE_R * math.sin(ang)), SENSOR_Z)


_WORLD_PTS = None


def cloud_payload(k):
    """(data_bytes, n_points) for frame k, points in sensor frame, float32 xyz."""
    global _WORLD_PTS
    if _WORLD_PTS is None:
        _WORLD_PTS = gen_world_points()
    tx, ty, tz = sensor_pose(k)
    buf = bytearray()
    n = 0
    for (x, y, z) in _WORLD_PTS:
        buf += struct.pack('<fff', x - tx, y - ty, z - tz)
        n += 1
    return bytes(buf), n


if __name__ == '__main__':
    import hashlib
    total = hashlib.sha256()
    for k in range(N_FRAMES):
        data, n = cloud_payload(k)
        total.update(data)
        print('frame', k, 'points', n, 'sha8', hashlib.sha256(data).hexdigest()[:8])
    print('ALL_FRAMES_SHA', total.hexdigest()[:16])
