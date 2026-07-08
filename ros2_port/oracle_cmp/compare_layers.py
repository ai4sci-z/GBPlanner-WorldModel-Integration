#!/usr/bin/env python3
"""Voxel-level comparison of two voxblox TSDF layer files (.voxblox).

Zero-dependency: hand-parses the varint-delimited proto2 stream
(format: varint message_count, then [varint size + msg]*; msg[0]=LayerProto,
rest=BlockProto; TsdfVoxel = 3 uint32: distance f32 bits, weight f32 bits,
color RGBA — see voxblox/src/core/block.cc).

Usage: compare_layers.py oracle.voxblox port.voxblox [--max-abs 5e-2 --rms 1e-3]
Exit 0 = PASS, 1 = FAIL, 2 = parse error.
"""
import math
import struct
import sys


def read_varint(buf, pos):
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def parse_message(buf):
    """Generic proto2 field walk -> {field: [values]} (varint/fixed64/bytes)."""
    fields = {}
    pos = 0
    while pos < len(buf):
        key, pos = read_varint(buf, pos)
        fnum, wtype = key >> 3, key & 7
        if wtype == 0:
            val, pos = read_varint(buf, pos)
        elif wtype == 1:
            val = struct.unpack('<d', buf[pos:pos + 8])[0]
            pos += 8
        elif wtype == 2:
            ln, pos = read_varint(buf, pos)
            val = buf[pos:pos + ln]
            pos += ln
        elif wtype == 5:
            val = struct.unpack('<f', buf[pos:pos + 4])[0]
            pos += 4
        else:
            raise ValueError('unsupported wire type %d' % wtype)
        fields.setdefault(fnum, []).append(val)
    return fields


def parse_layer_file(path):
    buf = open(path, 'rb').read()
    pos = 0
    count, pos = read_varint(buf, pos)
    msgs = []
    while pos < len(buf) and len(msgs) < count:
        size, pos = read_varint(buf, pos)
        msgs.append(buf[pos:pos + size])
        pos += size
    if len(msgs) != count:
        raise ValueError('%s: expected %d messages, got %d' % (path, count, len(msgs)))

    hdr = parse_message(msgs[0])
    layer = {
        'voxel_size': hdr[1][0],
        'voxels_per_side': hdr[2][0],
        'type': hdr[3][0].decode() if 3 in hdr else '',
    }
    blocks = {}
    for m in msgs[1:]:
        f = parse_message(m)
        # voxel_data (field 7): proto2 unpacked -> many varints; packed -> bytes
        vdata = []
        for v in f.get(7, []):
            if isinstance(v, (bytes, bytearray)):
                p = 0
                while p < len(v):
                    x, p = read_varint(v, p)
                    vdata.append(x)
            else:
                vdata.append(v)
        origin = (f[3][0], f[4][0], f[5][0])
        bs = layer['voxel_size'] * layer['voxels_per_side']
        key = tuple(int(round(o / bs)) for o in origin)
        voxels = []
        for i in range(0, len(vdata), 3):
            d = struct.unpack('<f', struct.pack('<I', vdata[i]))[0]
            w = struct.unpack('<f', struct.pack('<I', vdata[i + 1]))[0]
            voxels.append((d, w))
        blocks[key] = voxels
    return layer, blocks


def zspan(blocks, layer, weight_eps):
    vps = int(layer['voxels_per_side'])
    vs = layer['voxel_size']
    zmin, zmax = None, None
    for key, voxels in blocks.items():
        for idx, (d, w) in enumerate(voxels):
            if w > weight_eps:
                lz = idx // (vps * vps)
                z = (key[2] * vps + lz + 0.5) * vs
                zmin = z if zmin is None else min(zmin, z)
                zmax = z if zmax is None else max(zmax, z)
    return (zmin, zmax)


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    max_abs_th = float(sys.argv[sys.argv.index('--max-abs') + 1]) if '--max-abs' in sys.argv else 5e-2
    rms_th = float(sys.argv[sys.argv.index('--rms') + 1]) if '--rms' in sys.argv else 1e-3
    weight_eps = 1e-6

    la, ba = parse_layer_file(a_path)
    lb, bb = parse_layer_file(b_path)
    print('A(oracle): %s  blocks=%d  layer=%s' % (a_path, len(ba), la))
    print('B(port):   %s  blocks=%d  layer=%s' % (b_path, len(bb), lb))

    fail = []
    if (la['voxel_size'], la['voxels_per_side'], la['type']) != \
       (lb['voxel_size'], lb['voxels_per_side'], lb['type']):
        fail.append('layer header mismatch')

    ka, kb = set(ba), set(bb)
    only_a, only_b = ka - kb, kb - ka
    print('block sets: common=%d  only_oracle=%d  only_port=%d' %
          (len(ka & kb), len(only_a), len(only_b)))
    if only_a or only_b:
        fail.append('block set differs (only_oracle=%d only_port=%d)' % (len(only_a), len(only_b)))

    n_obs_a = n_obs_b = n_obs_common = 0
    n_occ_a = n_occ_b = 0
    sum_sq = 0.0
    max_abs = 0.0
    n_cmp = 0
    obs_mismatch = 0
    occ_th = la['voxel_size']  # |d| < voxel_size counts as near-surface/occupied
    for key in ka & kb:
        va, vb = ba[key], bb[key]
        if len(va) != len(vb):
            fail.append('block %s voxel count differs' % (key,))
            continue
        for (da, wa), (db, wb) in zip(va, vb):
            oa, ob = wa > weight_eps, wb > weight_eps
            n_obs_a += oa
            n_obs_b += ob
            n_occ_a += oa and abs(da) < occ_th
            n_occ_b += ob and abs(db) < occ_th
            if oa != ob:
                obs_mismatch += 1
                continue
            if oa and ob:
                n_obs_common += 1
                diff = abs(da - db)
                sum_sq += diff * diff
                max_abs = max(max_abs, diff)
                n_cmp += 1
    rms = math.sqrt(sum_sq / n_cmp) if n_cmp else float('nan')

    za, zb = zspan(ba, la, weight_eps), zspan(bb, lb, weight_eps)
    print('observed voxels: oracle=%d port=%d common=%d obs_mismatch=%d (%.4f%%)' %
          (n_obs_a, n_obs_b, n_obs_common, obs_mismatch,
           100.0 * obs_mismatch / max(1, n_obs_a)))
    print('near-surface voxels (|d|<voxel): oracle=%d port=%d' % (n_occ_a, n_occ_b))
    print('zspan: oracle=%s port=%s' % (za, zb))
    print('distance diff over %d common observed voxels: RMS=%.6g max=%.6g' %
          (n_cmp, rms, max_abs))

    if n_obs_a and obs_mismatch / n_obs_a > 0.001:
        fail.append('observed-voxel set mismatch > 0.1%%: %d' % obs_mismatch)
    if not math.isnan(rms) and rms > rms_th:
        fail.append('RMS %.6g > %.6g' % (rms, rms_th))
    if max_abs > max_abs_th:
        fail.append('max abs %.6g > %.6g' % (max_abs, max_abs_th))

    if fail:
        print('VERDICT: FAIL'); [print(' -', f) for f in fail]
        sys.exit(1)
    print('VERDICT: PASS')


if __name__ == '__main__':
    main()
