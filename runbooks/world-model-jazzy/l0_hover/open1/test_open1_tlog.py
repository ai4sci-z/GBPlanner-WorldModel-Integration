#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0:open1_tlog 解码器环境无关单测。

只用内存合成的 MAVLink v2 STATUSTEXT 帧,不依赖 world-model 产物、不依赖 pymavlink。
验证确定性解码 + 汇总不变量。"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import open1_tlog as T  # noqa: E402

FAIL = 0


def ck(name, got, want):
    global FAIL
    if got == want:
        print(f"PASS: {name} [{got!r}]")
    else:
        print(f"FAIL: {name} 期望[{want!r}] 实得[{got!r}]")
        FAIL += 1


def build_tlog(records):
    """records = [(ts_us, severity, text)] → 合成 tlog bytes。"""
    return b"".join(T._build_v2_statustext_record(ts, sev, txt) for ts, sev, txt in records)


# 1 单条 STATUSTEXT 精确解码
one = build_tlog([(1_000_000, 4, "Arm: Accels inconsistent")])
got = list(T.iter_statustext(one))
ck("1 单条数量", len(got), 1)
ck("1 单条时间(unix秒)", got[0][0], 1.0)
ck("1 单条severity", got[0][1], 4)
ck("1 单条文本", got[0][2], "Arm: Accels inconsistent")

# 2 多条 + accel 计数 + 时窗
recs = [
    (1_000_000, 6, "ArduPilot Ready"),
    (2_000_000, 4, "Arm: Accels inconsistent"),
    (3_000_000, 4, "Arm: Accels inconsistent"),
    (4_000_000, 6, "EKF3 IMU0 origin set"),
    (5_000_000, 6, "Barometer 1 calibration complete"),
]
multi = build_tlog(recs)
s = T.summarize(multi)
ck("2 总数", s["statustext_total"], 5)
ck("2 accel计数", s["accels_inconsistent_count"], 2)
ck("2 时窗秒", s["window_sec"], 4.0)
ck("2 boot ardupilot_ready", s["boot_markers"]["ardupilot_ready"], True)
ck("2 boot ekf_origin_set", s["boot_markers"]["ekf_origin_set"], True)
ck("2 boot baro_calibrated", s["boot_markers"]["baro_calibrated"], True)

# 3 空 tlog / 无 STATUSTEXT(no-BIN 类:0 accel)
empty = build_tlog([])
s0 = T.summarize(empty)
ck("3 空总数", s0["statustext_total"], 0)
ck("3 空accel", s0["accels_inconsistent_count"], 0)
ck("3 空时窗", s0["window_sec"], 0.0)
ck("3 空ardupilot_ready", s0["boot_markers"]["ardupilot_ready"], False)

# 4 混入非 STATUSTEXT 帧(msgid 30 ATTITUDE)不被误计
non_st = struct.pack(">Q", 6_000_000) + bytes([0xFD, 4, 0, 0, 0, 1, 1]) + bytes([30, 0, 0]) + b"\x00\x00\x00\x00" + b"\x00\x00"
mixed = one + non_st + build_tlog([(7_000_000, 4, "Arm: Accels inconsistent")])
sm = T.summarize(mixed)
ck("4 混入非ST后仅计ST", sm["statustext_total"], 2)
ck("4 混入accel计数", sm["accels_inconsistent_count"], 2)

# 5 payload 截断(text 短于 50)按空字节切分
trunc = build_tlog([(8_000_000, 6, "DDS: Using UDP")])
gt = list(T.iter_statustext(trunc))
ck("5 截断文本正确", gt[0][2], "DDS: Using UDP")

# 6 bytes 与 path 两种入口一致
import tempfile
with tempfile.NamedTemporaryFile(delete=False, suffix=".tlog") as tf:
    tf.write(multi)
    tp = tf.name
try:
    ck("6 path入口与bytes一致", T.summarize(tp), T.summarize(multi))
finally:
    os.unlink(tp)

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
