#!/usr/bin/env python3
"""Voxel-level comparison of two voxblox layer files (.voxblox): TSDF or ESDF.

Zero-dependency: hand-parses the varint-delimited proto2 stream
(format: varint message_count, then [varint size + msg]*; msg[0]=LayerProto,
rest=BlockProto).  Voxel layouts, from voxblox/src/core/block.cc:

  TsdfVoxel = 3 uint32: | f32 distance | f32 weight | color RGBA |
              observed  <=> weight > eps
  EsdfVoxel = 2 uint32: | f32 distance | 3x int8 parent | 8b flags |
              flags bit0=observed bit1=hallucinated bit2=in_queue bit3=fixed
              observed  <=> flags bit0

Layer kind comes from the LayerProto type string; --kind overrides it.

Usage: compare_layers.py oracle.voxblox port.voxblox [--kind tsdf|esdf]
                                                     [--max-abs 5e-2 --rms 1e-3]
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


WEIGHT_EPS = 1e-6
# stride in uint32 words, and how to tell "this voxel was actually observed"
VOXEL_KINDS = {
    'tsdf': (3, lambda words: u32_to_f32(words[1]) > WEIGHT_EPS),
    'esdf': (2, lambda words: bool(words[1] & 0b1)),
}


def u32_to_f32(x):
    return struct.unpack('<f', struct.pack('<I', x))[0]


def layer_kind(layer_type, override):
    if override:
        return override
    t = layer_type.lower()
    for kind in VOXEL_KINDS:
        if kind in t:
            return kind
    raise ValueError('cannot infer voxel kind from layer type %r; pass --kind' % layer_type)


def parse_layer_file(path, kind_override=None):
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
    layer['kind'] = layer_kind(layer['type'], kind_override)
    stride, is_observed = VOXEL_KINDS[layer['kind']]
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
        for i in range(0, len(vdata), stride):
            words = vdata[i:i + stride]
            voxels.append((u32_to_f32(words[0]), is_observed(words)))
        blocks[key] = voxels
    return layer, blocks


def zspan(blocks, layer):
    vps = int(layer['voxels_per_side'])
    vs = layer['voxel_size']
    zmin, zmax = None, None
    for key, voxels in blocks.items():
        for idx, (d, observed) in enumerate(voxels):
            if observed:
                lz = idx // (vps * vps)
                z = (key[2] * vps + lz + 0.5) * vs
                zmin = z if zmin is None else min(zmin, z)
                zmax = z if zmax is None else max(zmax, z)
    return (zmin, zmax)


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    max_abs_th = float(sys.argv[sys.argv.index('--max-abs') + 1]) if '--max-abs' in sys.argv else 5e-2
    rms_th = float(sys.argv[sys.argv.index('--rms') + 1]) if '--rms' in sys.argv else 1e-3
    kind = sys.argv[sys.argv.index('--kind') + 1] if '--kind' in sys.argv else None
    if kind is not None and kind not in VOXEL_KINDS:
        print('unknown --kind %r (expected: %s)' % (kind, '/'.join(VOXEL_KINDS)))
        sys.exit(2)

    la, ba = parse_layer_file(a_path, kind)
    lb, bb = parse_layer_file(b_path, kind)
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
        for (da, oa), (db, ob) in zip(va, vb):
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

    za, zb = zspan(ba, la), zspan(bb, lb)
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
