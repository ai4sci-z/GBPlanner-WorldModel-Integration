#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0 埋点:自包含 MAVLink tlog STATUSTEXT 确定性解码器(stdlib only)。

为什么不用 pymavlink:OPEN-2 的候选实现正是栽在 pymavlink 环境依赖上(节点级测试
mavlink=None 炸)。E0 的 STATUSTEXT 提取必须环境无关、可确定复现,故手写最小解析器。

tlog 记录格式(每帧):
  [8 字节大端 μs 时间戳][MAVLink v1(0xFE)或 v2(0xFD)帧]
MAVLink v2 帧:magic(1) len(1) incompat(1) compat(1) seq(1) sysid(1) compid(1)
  msgid(3, 小端) payload(len) crc(2) [signature(13) 若 incompat&0x01]
MAVLink v1 帧:magic(1) len(1) seq(1) sysid(1) compid(1) msgid(1) payload(len) crc(2)
STATUSTEXT = msgid 253,payload = severity(uint8) + text(char[50],空字节截断)。

限制(E0 诚实边界):
  - 不校验 CRC(仅做 STATUSTEXT 提取,失配时 i+=1 重同步);
  - v2 payload 截断(尾零省略)由按 len 读取 + 空字节切分吸收;
  - 不解析 STATUSTEXT 分块扩展字段(id/chunk_seq),ArduPilot 单帧 <=50 字符不受影响。
"""
import struct

STATUSTEXT_MSGID = 253


def iter_frames(data):
    """顺序产出 (ts_us, msgid, payload);失配则逐字节重同步。纯函数,不改输入。"""
    i, n = 0, len(data)
    while i + 8 < n:
        ts = struct.unpack_from(">Q", data, i)[0]
        magic = data[i + 8]
        if magic == 0xFD and i + 8 + 10 <= n:
            ln = data[i + 9]
            incompat = data[i + 10]
            total = 8 + 10 + ln + 2 + (13 if (incompat & 0x01) else 0)
            if i + total <= n:
                msgid = data[i + 15] | (data[i + 16] << 8) | (data[i + 17] << 16)
                payload = data[i + 18: i + 18 + ln]
                yield ts, msgid, payload
                i += total
                continue
        elif magic == 0xFE and i + 8 + 6 <= n:
            ln = data[i + 9]
            total = 8 + 6 + ln + 2
            if i + total <= n:
                msgid = data[i + 13]
                payload = data[i + 14: i + 14 + ln]
                yield ts, msgid, payload
                i += total
                continue
        i += 1  # 重同步


def iter_statustext(path_or_bytes):
    """产出 (t_unix_sec, severity:int, text:str)。接受文件路径或 bytes。"""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data = bytes(path_or_bytes)
    else:
        with open(path_or_bytes, "rb") as f:
            data = f.read()
    for ts, msgid, payload in iter_frames(data):
        if msgid == STATUSTEXT_MSGID and len(payload) >= 1:
            sev = payload[0]
            text = payload[1:].split(b"\x00")[0].decode("ascii", "replace")
            yield ts / 1e6, sev, text


def summarize(path_or_bytes):
    """STATUSTEXT 汇总:计数、时窗、accel-inconsistent 次数、关键 boot 标记出现与否。"""
    from collections import Counter
    counts = Counter()
    total = 0
    first = last = None
    for t, _sev, text in iter_statustext(path_or_bytes):
        total += 1
        counts[text] += 1
        if first is None:
            first = t
        last = t
    boot_markers = {
        "ardupilot_ready": any("ArduPilot Ready" in k for k in counts),
        "ekf_origin_set": any("origin set" in k for k in counts),
        "baro_calibrated": any("Barometer" in k and "calibration complete" in k for k in counts),
    }
    return {
        "statustext_total": total,
        "window_sec": round((last - first), 3) if first is not None else 0.0,
        "accels_inconsistent_count": sum(v for k, v in counts.items() if "Accels inconsistent" in k),
        "boot_markers": boot_markers,
        "distinct_texts": len(counts),
    }


def _build_v2_statustext_record(ts_us, severity, text):
    """测试辅助:构造一条 [ts][v2 STATUSTEXT] 记录(CRC 占位,解码器不校验)。"""
    tb = text.encode("ascii")[:50]
    payload = bytes([severity]) + tb
    ln = len(payload)
    frame = bytes([0xFD, ln, 0, 0, 0, 1, 1]) + bytes([STATUSTEXT_MSGID & 0xFF, 0, 0]) + payload + b"\x00\x00"
    return struct.pack(">Q", ts_us) + frame


if __name__ == "__main__":
    import sys
    import json
    print(json.dumps(summarize(sys.argv[1]), ensure_ascii=False, indent=2))
