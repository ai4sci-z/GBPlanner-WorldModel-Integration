#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0 · G1 协议门:open1_tlog 解码器测试。

核心断言用**内存合成、带真实 X25 CRC**的 MAVLink 帧(环境无关,不依赖 world-model/pymavlink)。
覆盖:有效 v1/v2/签名帧通过;CRC/header/payload 损坏拒绝;截断/噪声/伪 magic;扩展分块 unsupported;
结构化 invalid 计数。另含独立"真实 tlog CRC 自证"段(在盘则断言 bad_crc=0,不在则 SKIP)。
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
    if got == want:
        print(f"PASS: {name} [{got!r}]")
    else:
        print(f"FAIL: {name} 期望[{want!r}] 实得[{got!r}]")
        UNIT_FAIL += 1


def ckr(name, got, want):
    global REPLAY_FAIL
    if got == want:
        print(f"PASS(replay): {name} [{got!r}]")
    else:
        print(f"FAIL(replay): {name} 期望[{want!r}] 实得[{got!r}]")
        REPLAY_FAIL += 1


print("======== G1 单元(环境无关,真实 CRC 合成帧) ========")

# 1 有效 v2 STATUSTEXT:CRC 通过 → 抽取
rec = T.build_statustext_record(1_000_000, 4, "Arm: Accels inconsistent")
out, stats = T.decode(rec)
ck("1 有效v2 抽取1条", len(out), 1)
ck("1 文本正确", out[0][2], "Arm: Accels inconsistent")
ck("1 severity", out[0][1], 4)
ck("1 时间unix", out[0][0], 1.0)
ck("1 stats valid", stats["statustext_valid"], 1)
ck("1 stats bad_crc", stats["statustext_bad_crc"], 0)

# 2 CRC 位翻转 → 拒绝(旧无校验实现会错误放行)
bad = T.build_statustext_record(2_000_000, 4, "Arm: Accels inconsistent", corrupt_crc=True)
out2, s2 = T.decode(bad)
ck("2 CRC坏 不抽取", len(out2), 0)
ck("2 CRC坏 计入bad_crc", s2["statustext_bad_crc"], 1)

# 3 payload 位翻转 → CRC 失配 → 拒绝
rec3 = bytearray(T.build_statustext_record(3_000_000, 4, "hello world"))
rec3[19] ^= 0x20  # 翻转 payload 内一字节(帧内 payload 起于偏移 8+10=18,+1 为文本首字节)
out3, s3 = T.decode(bytes(rec3))
ck("3 payload坏 不抽取", len(out3), 0)
ck("3 payload坏 bad_crc", s3["statustext_bad_crc"], 1)

# 4 header 位翻转(非 len 字段:seq)→ CRC 失配 → 拒绝
rec4 = bytearray(T.build_statustext_record(4_000_000, 4, "hello"))
rec4[8 + 4] ^= 0x10  # seq 位于 v2 帧偏移 4;record 前 8 字节为 ts
out4, s4 = T.decode(bytes(rec4))
ck("4 header坏 不抽取", len(out4), 0)
ck("4 header坏 bad_crc", s4["statustext_bad_crc"], 1)

# 5 截断(砍掉尾部 3 字节)→ truncated_tail,不抽取
trunc = T.build_statustext_record(5_000_000, 4, "hello")[:-3]
out5, s5 = T.decode(trunc)
ck("5 截断 不抽取", len(out5), 0)
ck("5 截断 truncated_tail>0", s5["truncated_tail"] > 0, True)

# 6 噪声/伪 magic(纯噪声,不含有效帧)→ 0 抽取(无假阳)
noise = bytes([0x11, 0x22, 0x33, 0xFD, 0xFF, 0x00, 0x77] * 20)
out6, s6 = T.decode(noise)
ck("6 纯噪声 0抽取", len(out6), 0)

# 7 前导噪声后仍恢复有效帧(重同步)
lead = b"\x00" + T.build_statustext_record(7_000_000, 4, "recovered")
out7, s7 = T.decode(lead)
ck("7 前导噪声后抽取1条", len(out7), 1)
ck("7 文本", out7[0][2], "recovered")
ck("7 resync_bytes>0", s7["resync_bytes"] > 0, True)

# 8 v2 签名帧(incompat&0x01,+13B 签名)→ CRC 通过 → 抽取
sig = T.build_statustext_record(8_000_000, 6, "signed frame", signed=True)
out8, s8 = T.decode(sig)
ck("8 签名帧 抽取1条", len(out8), 1)
ck("8 签名帧 文本", out8[0][2], "signed frame")

# 9 v1 帧(0xFE)→ CRC 通过 → 抽取
v1 = T.build_statustext_record(9_000_000, 5, "v1 frame", mavlink2=False)
out9, s9 = T.decode(v1)
ck("9 v1帧 抽取1条", len(out9), 1)
ck("9 v1帧 文本", out9[0][2], "v1 frame")

# 10 扩展分块(id!=0)→ unsupported_chunk,不拼入文本
chunk = T.build_statustext_record(10_000_000, 6, "long chunk", chunk_id=7, chunk_seq=0)
out10, s10 = T.decode(chunk)
ck("10 分块 不抽取为完整", len(out10), 0)
ck("10 分块 记 unsupported", s10["statustext_unsupported_chunk"], 1)

# 11 非分块(id=0,含固定字段)→ 正常抽取
nochunk = T.build_statustext_record(11_000_000, 6, "plain", chunk_id=0, chunk_seq=0)
out11, s11 = T.decode(nochunk)
ck("11 id=0 正常抽取", len(out11), 1)

# 12 多帧混合(有效+坏CRC+有效)计数正确
mix = (T.build_statustext_record(12_000_000, 4, "one")
       + T.build_statustext_record(12_500_000, 4, "bad", corrupt_crc=True)
       + T.build_statustext_record(13_000_000, 4, "two"))
out12, s12 = T.decode(mix)
ck("12 混合 抽取2条有效", len(out12), 2)
ck("12 混合 bad_crc=1", s12["statustext_bad_crc"], 1)

print("======== G1 真实 tlog CRC 自证(在盘断言 / 不在盘 SKIP) ========")
H = "/home/ai4s/projects/world-model/artifacts/sim/hover"
REAL = ["204428", "211927", "210849", "205113", "210149"]
paths = {ts: (glob.glob(f"{H}/20260715T{ts}*/sitl/mav.tlog") or [None])[0] for ts in REAL}
if not all(paths.values()):
    print("SKIP/UNVERIFIED: 部分真实 tlog 不在盘,跳过真实 CRC 自证(单元断言已独立通过)")
else:
    for ts, p in paths.items():
        s = T.summarize(p)["protocol_stats"]
        REPLAY_RAN += 1
        ckr(f"real {ts} bad_crc=0(全 STATUSTEXT 通过 CRC)", s["statustext_bad_crc"], 0)
        ckr(f"real {ts} truncated_tail=0", s["truncated_tail"], 0)
        ckr(f"real {ts} resync_bytes=0", s["resync_bytes"], 0)

print("================================")
print(f"G1 单元: FAIL={UNIT_FAIL}")
print(f"G1 真实回放: RAN={REPLAY_RAN} FAIL={REPLAY_FAIL}"
      + ("" if REPLAY_RAN else " (SKIP/UNVERIFIED)"))
sys.exit(1 if (UNIT_FAIL or REPLAY_FAIL) else 0)
