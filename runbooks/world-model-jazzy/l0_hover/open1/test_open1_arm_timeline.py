#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1-04.1 · arm 时间线派生门。

G1 合成:载荷按 MAVLink 官方 wire 布局(字段按大小排序)手工打包为固定向量,
帧由冻结 build_frame 构造(显式传 crc_extra)。expected 由本测试的固定向量给出,
不由被测 derive 生成。
G2 真实回放:crc_extra 独立验证 = 五冻结 run 真 tlog 自证(真帧 bad_crc=0)
+ 判别性反证(故意 crc_extra+1 → 真帧必 CRC 失败);命令常量独立源 =
mission_summary(command:400/result:0 ∧ arm_ack_ok)。tlog 不在盘 → SKIP(不计 PASS)。
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import open1_arm_timeline as A  # noqa: E402
import open1_tlog as T  # noqa: E402

FAIL = 0
SKIP = 0


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def hb_payload(custom_mode=0, mtype=2, autopilot=3, base_mode=81, status=4, ver=3):
    return struct.pack("<I", custom_mode) + bytes([mtype, autopilot, base_mode, status, ver])


def cmdlong_payload(command, p1, target=1):
    return (struct.pack("<7f", p1, 0, 0, 0, 0, 0, 0) + struct.pack("<H", command)
            + bytes([target, 1, 0]))


def ack_payload(command, result):
    return struct.pack("<H", command) + bytes([result])


def rec(ts_us, msgid, payload, crc_extra, corrupt=False):
    return T.build_record(ts_us, T.build_frame(msgid, payload, crc_extra=crc_extra,
                                               corrupt_crc=corrupt))


print("======== G1 合成固定向量 ========")
blob = b"".join([
    rec(1_000_000, A.HEARTBEAT_MSGID, hb_payload(), 50),
    rec(2_000_000, A.COMMAND_LONG_MSGID, cmdlong_payload(400, 1.0), 152),   # arm request
    rec(3_000_000, A.COMMAND_ACK_MSGID, ack_payload(400, 0), 143),          # accepted
    rec(4_000_000, A.COMMAND_ACK_MSGID, ack_payload(400, 4), 143),          # reject(FAILED)
    rec(5_000_000, A.COMMAND_LONG_MSGID, cmdlong_payload(400, 0.0), 152),   # disarm request
    T.build_statustext_record(6_000_000, 2, "PreArm: check failed"),
    rec(7_000_000, A.COMMAND_LONG_MSGID, cmdlong_payload(22, 5.0), 152),    # 非 arm 命令:不入事件
    rec(8_000_000, A.HEARTBEAT_MSGID, hb_payload(), 50, corrupt=True),      # bad CRC
])
r = A.derive(blob)
kinds = [e["kind"] for e in r["events"]]
ck("事件序列(arm 链+statustext,heartbeat 只计数)",
   kinds, ["arm_request", "arm_ack_accepted", "arm_reject", "disarm_request", "statustext_reason"])
ck("arm_request 时戳", r["events"][0]["t_unix"], 2.0)
ck("arm_request param1", r["events"][0]["fields"]["params"][0], 1.0)
ck("ack accepted result", r["events"][1]["fields"]["result"], 0)
ck("reject result 保原值", r["events"][2]["fields"]["result"], 4)
ck("statustext 文本", r["events"][4]["fields"]["text"], "PreArm: check failed")
ck("heartbeat 计数", r["counters"]["heartbeat_valid"], 1)
ck("bad_crc 计数", r["counters"]["bad_crc"], 1)
ck("时戳全可靠", all(e["ts_reliable"] for e in r["events"]), True)

# v2 零截断:ACK 载荷截到 3 字节仍解析
r2 = A.derive(rec(1_000_000, A.COMMAND_ACK_MSGID, ack_payload(400, 0)[:3], 143))
ck("v2 零截断 ACK 可解析", r2["events"][0]["kind"], "arm_ack_accepted")

# 恢复模式:垃圾前缀 → 锚定帧时戳必须 UNKNOWN(不伪造时序)
r3 = A.derive(b"\xfd\x03garbage!!" + rec(9_000_000, A.COMMAND_LONG_MSGID,
                                         cmdlong_payload(400, 1.0), 152)
              + rec(10_000_000, A.COMMAND_ACK_MSGID, ack_payload(400, 0), 143))
first = r3["events"][0]
ck("恢复锚定事件 t_unix=UNKNOWN", first["t_unix"], A.UNKNOWN)
ck("恢复锚定 ts_reliable=False", first["ts_reliable"], False)
ck("unknown_time_events 计数", r3["counters"]["unknown_time_events"] >= 1, True)
ck("恢复后回到正常模式(次事件时戳可靠)", r3["events"][1]["t_unix"], 10.0)

# 截断尾
r4 = A.derive(rec(1_000_000, A.HEARTBEAT_MSGID, hb_payload(), 50) + b"\xfd\x09\x00")
ck("截断尾计数>0", r4["counters"]["truncated"] > 0, True)

print("======== G2 真实回放:crc_extra 自证 + 判别性反证 ========")
HOVER = "/home/ai4s/projects/world-model/artifacts/sim/hover"
RUNS = ["20260715T204428.255001623Z", "20260715T211927.641462689Z",
        "20260715T210849.272170331Z", "20260715T205113.276955543Z",
        "20260715T210149.482334513Z"]
ran = 0
for run in RUNS:
    p = os.path.join(HOVER, run, "sitl", "mav.tlog")
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        SKIP += 1
        print(f"SKIP: {run} tlog 不在盘/为空(不计 PASS)")
        continue
    ran += 1
    data = open(p, "rb").read()
    r = A.derive(data)
    c = r["counters"]
    ck(f"{run[:15]} 心跳真帧存在", c["heartbeat_valid"] > 0, True)
    ck(f"{run[:15]} 真帧 bad_crc==0(crc_extra 50/152/143 自证)", c["bad_crc"], 0)
    # 判别性反证:错误 crc_extra 必须打红真帧
    saved = dict(A.ARM_CRC_EXTRA)
    try:
        A.ARM_CRC_EXTRA[A.HEARTBEAT_MSGID] = 51
        rbad = A.derive(data)
        ck(f"{run[:15]} 错 crc_extra → 心跳 0 且 bad_crc>0(判别力)",
           (rbad["counters"]["heartbeat_valid"], rbad["counters"]["bad_crc"] > 0), (0, True))
    finally:
        A.ARM_CRC_EXTRA.clear(); A.ARM_CRC_EXTRA.update(saved)
# 命令常量独立源:full-pass run 的 arm 链必须在 tlog 中重现 mission_summary 主张
p0 = os.path.join(HOVER, RUNS[0], "sitl", "mav.tlog")
if os.path.exists(p0) and os.path.getsize(p0) > 0:
    r = A.derive(open(p0, "rb").read())
    kinds = [e["kind"] for e in r["events"]]
    ck("204428 tlog 含 arm_request(mission_summary sent arm=11 的独立重现)",
       "arm_request" in kinds, True)
    ck("204428 tlog 含 arm_ack_accepted(command 400/result 0 独立重现)",
       "arm_ack_accepted" in kinds, True)
print(f"[G2] RAN={ran} SKIP={SKIP}")

print("================================")
print(f"结果: FAIL={FAIL} SKIP={SKIP}")
sys.exit(1 if FAIL else 0)
