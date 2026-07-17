#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0 · G1 协议门:open1_tlog 解码器测试(环境无关,不依赖 pymavlink)。

覆盖:原 12 项;A1 未知 incompat;A2 签名真实性;A3 伪长度/重同步七反例;
A4 独立 CRC 向量(公开已知值 + 独立实现 + 真实 ArduPilot 帧);真实 tlog 兼容性观察。
每反例打印 expected/actual。out 记录为四元组 (ts, sev, text, signature_status)。
"""
import glob
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import open1_tlog as T  # noqa: E402

UNIT_FAIL = 0
REPLAY_FAIL = 0
REPLAY_RAN = 0


def ck(name, got, want):
    global UNIT_FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        UNIT_FAIL += 1


def ckr(name, got, want):
    global REPLAY_FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}(replay): {name} expected={want!r} actual={got!r}")
    if not ok:
        REPLAY_FAIL += 1


print("======== G1 原 12 项(真实 CRC 合成帧) ========")
rec = T.build_statustext_record(1_000_000, 4, "Arm: Accels inconsistent")
out, st = T.decode(rec)
ck("1 有效v2 抽取1条", len(out), 1)
ck("1 文本", out[0][2], "Arm: Accels inconsistent")
ck("1 severity", out[0][1], 4)
ck("1 时间unix", out[0][0], 1.0)
ck("1 signature=UNSIGNED", out[0][3], "UNSIGNED")
ck("1 valid_statustext", st["valid_statustext"], 1)

bad = T.build_statustext_record(2_000_000, 4, "x", corrupt_crc=True)
o2, s2 = T.decode(bad)
ck("2 CRC坏 不抽取", len(o2), 0)
ck("2 crc_failed_frames", s2["crc_failed_frames"], 1)

r3 = bytearray(T.build_statustext_record(3_000_000, 4, "hello world"))
r3[19] ^= 0x20
o3, s3 = T.decode(bytes(r3))
ck("3 payload坏 不抽取", len(o3), 0)
ck("3 crc_failed", s3["crc_failed_frames"], 1)

r4 = bytearray(T.build_statustext_record(4_000_000, 4, "hello"))
r4[8 + 4] ^= 0x10  # seq
o4, s4 = T.decode(bytes(r4))
ck("4 header坏 不抽取", len(o4), 0)
ck("4 crc_failed", s4["crc_failed_frames"], 1)

trunc = T.build_statustext_record(5_000_000, 4, "hello")[:-3]
o5, s5 = T.decode(trunc)
ck("5 截断 不抽取", len(o5), 0)
ck("5 截断 truncated_candidates>0", s5["truncated_candidates"] > 0, True)

noise = bytes([0x11, 0x22, 0x33, 0xFD, 0xFF, 0x00, 0x77] * 20)
o6, s6 = T.decode(noise)
ck("6 纯噪声 0抽取", len(o6), 0)

lead = b"\x00" + T.build_statustext_record(7_000_000, 4, "recovered")
o7, s7 = T.decode(lead)
ck("7 前导噪声后抽取1条", len(o7), 1)
ck("7 文本", o7[0][2], "recovered")
ck("7 resync_bytes>0", s7["resync_bytes"] > 0, True)
ck("7 recovered_records>0", s7["recovered_records"] > 0, True)

v1 = T.build_statustext_record(9_000_000, 5, "v1 frame", mavlink2=False)
o9, s9 = T.decode(v1)
ck("9 v1帧 抽取1条", len(o9), 1)
ck("9 v1帧 文本", o9[0][2], "v1 frame")

chunk = T.build_statustext_record(10_000_000, 6, "long chunk", chunk_id=7, chunk_seq=0)
o10, s10 = T.decode(chunk)
ck("10 分块 不抽取", len(o10), 0)
ck("10 unsupported_chunked", s10["unsupported_chunked_statustext"], 1)

nochunk = T.build_statustext_record(11_000_000, 6, "plain", chunk_id=0, chunk_seq=0)
o11, s11 = T.decode(nochunk)
ck("11 id=0 正常抽取", len(o11), 1)

mix = (T.build_statustext_record(12_000_000, 4, "one")
       + T.build_statustext_record(12_500_000, 4, "bad", corrupt_crc=True)
       + T.build_statustext_record(13_000_000, 4, "two"))
o12, s12 = T.decode(mix)
ck("12 混合 抽取2条", len(o12), 2)
ck("12 crc_failed=1", s12["crc_failed_frames"], 1)

print("======== A1 未知 incompat flag ========")
for inc, expect_valid, label in [(0x00, 1, "合法0x00"), (0x01, 1, "合法signed0x01"),
                                 (0x02, 0, "未知0x02"), (0x03, 0, "组合0x03")]:
    sig = b"\x00" * 13 if (inc & 0x01) else b""
    r = T.build_statustext_record(20_000_000, 4, "acc", incompat=inc, signature=sig)
    o, s = T.decode(r)
    ck(f"A1 {label} 抽取数", len(o), expect_valid)
    if not expect_valid:
        ck(f"A1 {label} 记 unsupported_incompat_flags", s["unsupported_incompat_flags"], 1)
        ck(f"A1 {label} 不计 valid_crc", s["valid_crc_frames"], 0)
# 未知 flag 帧后合法帧仍能解析
combo = (T.build_statustext_record(20_000_001, 4, "skip", incompat=0x02)
         + T.build_statustext_record(20_000_002, 4, "after"))
oc, sc = T.decode(combo)
ck("A1 未知flag后合法帧恢复", [x[2] for x in oc], ["after"])

print("======== A2 签名真实性 ========")
r = T.build_statustext_record(30_000_000, 6, "signed text", incompat=0x01, signature=b"\x00" * 13)
o, s = T.decode(r)
ck("A2 13零签名 抽取", len(o), 1)
ck("A2 signature_status=UNVERIFIED", o[0][3], "UNVERIFIED")
ck("A2 signed_frames_unverified", s["signed_frames_unverified"], 1)
r = T.build_statustext_record(30_000_001, 6, "fake sig", incompat=0x01, signature=b"X" * 13)
o, s = T.decode(r)
ck("A2 伪签名 仍标 UNVERIFIED(不当已认证)", o[0][3] if o else None, "UNVERIFIED")
# 截断签名(signed bit 在但只给 5 字节)→ 帧不完整 → 不抽取
r = T.build_statustext_record(30_000_002, 6, "trunc sig", incompat=0x01, signature=b"S" * 5)
o, s = T.decode(r)
ck("A2 截断签名 不抽取", len(o), 0)
# signed bit 存在但整体长度不足(只到 header)
short = T.build_statustext_record(30_000_003, 6, "s", incompat=0x01, signature=b"\x00" * 13)[:14]
o, s = T.decode(short)
ck("A2 长度不足 不抽取", len(o), 0)
# signed 帧后接普通合法帧仍解析
seq2 = (T.build_statustext_record(30_000_004, 6, "sig1", incompat=0x01, signature=b"\x00" * 13)
        + T.build_statustext_record(30_000_005, 6, "plain2"))
o, s = T.decode(seq2)
ck("A2 签名帧后合法帧", [x[2] for x in o], ["sig1", "plain2"])

print("======== A3 伪长度/重同步七反例 ========")
def fake_hdr(ln):  # 声称超长的 v2 header,后附少量字节
    return struct.pack(">Q", 40_000_000) + bytes([0xFD, ln, 0, 0, 0, 1, 1, 99, 0, 0]) + b"\x00" * 5
good = T.build_statustext_record(40_000_100, 4, "later-valid")
cases = [
    ("A3-1 伪大长度后合法帧", fake_hdr(250) + good),
    ("A3-2 截断伪帧后合法帧", T.build_statustext_record(1, 4, "x")[:-4] + good),
    ("A3-3 噪声magic后合法帧", bytes([0x00, 0xFD, 0x11, 0x22]) + good),
    ("A3-4 payload内0xFD后合法帧",
     T.build_record(2, T.build_frame(T.STATUSTEXT_MSGID, bytes([4]) + b"a\xfdb", crc_extra=83)) + good),
    ("A3-5 CRC错帧后合法帧", T.build_statustext_record(3, 4, "z", corrupt_crc=True) + good),
    ("A3-6 连续两合法record", T.build_statustext_record(4, 4, "later-valid") + good),
]
for name, blob in cases:
    o, s = T.decode(blob)
    recovered = any(x[2] == "later-valid" for x in o)
    ck(name + " 恢复later-valid", recovered, True)
# A3-7 只有真正尾部截断才计 truncated_tail:合法帧 + 末尾 <MIN 残留
tail = T.build_statustext_record(5, 4, "done") + b"\x00\x00\x00"
o, s = T.decode(tail)
ck("A3-7 合法帧仍抽取", any(x[2] == "done" for x in o), True)
ck("A3-7 尾部残留计 truncated_tail", s["truncated_tail"] > 0, True)

print("======== A4 独立 CRC 向量(非本模块构造器 oracle) ========")
# A4.1 公开已知向量:CRC-16/MCRF4XX('123456789') == 0x6F91
ck("A4.1 公开向量 x25('123456789')", T.x25_crc(b"123456789"), 0x6F91)


def _indep_crc(buf, extra=None):
    # 独立实现:逐位反射(poly 0x8408),与模块 nibble 法不同代码路径
    data = bytes(buf) + (bytes([extra]) if extra is not None else b"")
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else (crc >> 1)
    return crc


ck("A4.2 独立实现与模块在公开向量一致", _indep_crc(b"123456789"), 0x6F91)
ck("A4.2 独立实现与模块在样本一致", _indep_crc(b"hello", 83), T.x25_crc(b"hello", 83))
# 用独立 CRC 构造 v1 帧(非 T.x25_crc 生成)→ 解码器应接受
_p = bytes([5]) + b"indep-v1"
_hdr1 = bytes([0xFE, len(_p), 0, 1, 1, T.STATUSTEXT_MSGID])
_v1 = struct.pack(">Q", 50_000_000) + _hdr1 + _p + struct.pack("<H", _indep_crc(_hdr1[1:] + _p, 83))
o, s = T.decode(_v1)
ck("A4.2 独立v1向量 抽取", [x[2] for x in o], ["indep-v1"])
# 翻转 payload → 拒绝
_bad = bytearray(_v1)
_bad[8 + 6] ^= 0x01
ck("A4.2 独立v1 翻payload→拒绝", len(T.decode(bytes(_bad))[0]), 0)
# A4.3 真实 ArduPilot v2 固定向量(ArduPilot SITL 产生,独立来源;wm 211927 tlog;文本 "Frame: ")
REAL_V2 = bytes.fromhex("000656ace15be714fd080000040101fd0000064672616d653a20abd1")
o, s = T.decode(REAL_V2)
ck("A4.3 真实固定向量 抽取文本", [x[2] for x in o], ["Frame: "])
for pos, tag in [(8 + 4, "header-seq"), (8 + 11, "payload"), (len(REAL_V2) - 1, "crc")]:
    b = bytearray(REAL_V2)
    b[pos] ^= 0x01
    ck(f"A4.3 真实向量翻{tag}→拒绝", len(T.decode(bytes(b))[0]), 0)

print("======== G1 真实 tlog 兼容性观察(非算法正确性证明;不在盘则 SKIP) ========")
H = "/home/ai4s/projects/world-model/artifacts/sim/hover"
REAL = ["204428", "211927", "210849", "205113", "210149"]
paths = {ts: (glob.glob(f"{H}/20260715T{ts}*/sitl/mav.tlog") or [None])[0] for ts in REAL}
if not all(paths.values()):
    print("SKIP/UNVERIFIED: 部分真实 tlog 不在盘(单元断言已独立通过)")
else:
    for ts, p in paths.items():
        s = T.summarize(p)["protocol_stats"]
        REPLAY_RAN += 1
        ckr(f"real {ts} crc_failed_frames=0(兼容性观察)", s["crc_failed_frames"], 0)

print("================================")
print(f"G1 单元: FAIL={UNIT_FAIL}")
print(f"G1 真实回放: RAN={REPLAY_RAN} FAIL={REPLAY_FAIL}" + ("" if REPLAY_RAN else " (SKIP/UNVERIFIED)"))
sys.exit(1 if (UNIT_FAIL or REPLAY_FAIL) else 0)
