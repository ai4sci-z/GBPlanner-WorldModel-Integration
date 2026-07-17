#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0:自包含 MAVLink tlog STATUSTEXT 协议解码器(stdlib only,校验 CRC)。

不用 pymavlink:OPEN-2 候选实现栽在 pymavlink 环境依赖上。E0 手写最小解析器,
**校验 X25 CRC**(含 STATUSTEXT crc-extra=83),帧长/签名长/payload 结构均检查。

tlog 记录:[8B 大端 μs 时间戳][MAVLink v1(0xFE)或 v2(0xFD)帧]。
MAVLink v2 帧:magic len incompat compat seq sysid compid msgid(3,LE) payload crc(2,LE)
  [signature(13) 若 incompat&0x01]。CRC = X25 over [len..payload] + crc_extra。
MAVLink v1 帧:magic len seq sysid compid msgid(1) payload crc(2)。
STATUSTEXT = msgid 253,payload = severity(1) + text(char[50]) [+ id(uint16)+chunk_seq(uint8) 扩展]。

诚实边界:
  - 只对**已知 crc_extra 的 msgid**(此处 STATUSTEXT=253)做 CRC 校验;其它 msgid 结构上按
    len 前进但标 crc_unchecked(不冒充已校验)。
  - STATUSTEXT 文本只取固定字段 payload[1:51](空字节截断);不做散文猜测。
  - v2 扩展 id!=0(分块长消息)→ **fail-closed 标 unsupported_chunk,不拼入文本**(不支持重组)。
  - CRC/结构失败 → 计入结构化 invalid 计数,逐字节重同步;不静默吞。
"""
import struct

STATUSTEXT_MSGID = 253
# crc_extra 取自 MAVLink 通用方言(消息名+字段签名的 CRC 尾字节)。
# 仅登记本工具需要校验的 msgid;经真实 tlog 全量自证(见 test G1 real-replay)。
CRC_EXTRA = {STATUSTEXT_MSGID: 83}
_STATUSTEXT_FIXED_LEN = 51  # severity(1)+text(50);其后为扩展 id/chunk_seq


def x25_crc(buf, crc_extra=None):
    """MAVLink X25(CRC-16/MCRF4XX)。crc_extra 非 None 时作为尾字节喂入。纯函数。"""
    crc = 0xFFFF
    data = bytes(buf) + (bytes([crc_extra]) if crc_extra is not None else b"")
    for b in data:
        tmp = b ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


def _statustext_fields(payload):
    """返回 (severity, text, chunked:bool)。chunked=扩展 id!=0(不支持重组→上层标 unsupported)。"""
    severity = payload[0]
    text = payload[1:_STATUSTEXT_FIXED_LEN].split(b"\x00")[0].decode("ascii", "replace")
    chunked = False
    if len(payload) >= 53:  # 扩展存在:id(uint16)@51..52, chunk_seq@53
        ext_id = payload[51] | (payload[52] << 8)
        if ext_id != 0:
            chunked = True
    return severity, text, chunked


def decode(data):
    """顺序解析字节流,返回 (statustexts, stats)。
    statustexts = [(t_unix_sec, severity, text)](仅 CRC 校验通过且非分块的 STATUSTEXT)。
    stats = 结构化计数(诚实登记 valid/bad_crc/unsupported_chunk/unchecked/resync/truncated_tail)。"""
    if isinstance(data, str):
        with open(data, "rb") as f:
            data = f.read()
    data = bytes(data)
    i, n = 0, len(data)
    out = []
    stats = {
        "statustext_valid": 0,      # msgid 253 且 CRC 通过且非分块
        "statustext_bad_crc": 0,    # msgid 253 但 CRC 不符
        "statustext_unsupported_chunk": 0,  # msgid 253 CRC 通过但 id!=0 分块(不重组)
        "frames_crc_checked_ok": 0,  # 已知 crc_extra 且 CRC 通过的帧(含非 253,当前仅 253)
        "frames_unchecked": 0,      # 未知 crc_extra,按 len 前进(未校验)
        "resync_bytes": 0,          # 结构失败逐字节重同步跳过的字节
        "truncated_tail": 0,        # 尾部不足一帧的字节
    }
    while i + 8 <= n:
        if i + 9 > n:
            stats["truncated_tail"] += (n - i)
            break
        magic = data[i + 8]
        frame = None
        if magic == 0xFD and i + 8 + 10 <= n:
            ln = data[i + 9]
            incompat = data[i + 10]
            siglen = 13 if (incompat & 0x01) else 0
            total = 8 + 10 + ln + 2 + siglen
            if i + total <= n:
                msgid = data[i + 15] | (data[i + 16] << 8) | (data[i + 17] << 16)
                payload = data[i + 18: i + 18 + ln]
                crc_in = data[i + 18 + ln] | (data[i + 18 + ln + 1] << 8)
                body = data[i + 9: i + 18 + ln]  # len..payload
                frame = (msgid, payload, crc_in, body, total)
            elif i + total > n:
                stats["truncated_tail"] += (n - i)
                break
        elif magic == 0xFE and i + 8 + 6 <= n:
            ln = data[i + 9]
            total = 8 + 6 + ln + 2
            if i + total <= n:
                msgid = data[i + 13]
                payload = data[i + 14: i + 14 + ln]
                crc_in = data[i + 14 + ln] | (data[i + 14 + ln + 1] << 8)
                body = data[i + 9: i + 14 + ln]
                frame = (msgid, payload, crc_in, body, total)
            else:
                stats["truncated_tail"] += (n - i)
                break

        if frame is None:
            i += 1  # 伪 magic / 噪声:重同步
            stats["resync_bytes"] += 1
            continue

        msgid, payload, crc_in, body, total = frame
        ts = struct.unpack_from(">Q", data, i)[0] / 1e6
        if msgid in CRC_EXTRA:
            if x25_crc(body, CRC_EXTRA[msgid]) == crc_in:
                stats["frames_crc_checked_ok"] += 1
                if msgid == STATUSTEXT_MSGID and len(payload) >= 1:
                    _sev, text, chunked = _statustext_fields(payload)
                    if chunked:
                        stats["statustext_unsupported_chunk"] += 1
                    else:
                        stats["statustext_valid"] += 1
                        out.append((ts, _sev, text))
                i += total
                continue
            else:
                # CRC 不符:拒绝该帧(不抽取),按 len 跳过整帧——该帧结构完整(magic+len+落在缓冲内),
                # 逐字节重同步会把 payload 内的 0xFD(如 msgid 253 低字节)误当新帧而跳过后续有效帧。
                stats["statustext_bad_crc"] += (1 if msgid == STATUSTEXT_MSGID else 0)
                i += total
                continue
        else:
            # 未知 crc_extra:结构上按 len 前进,但不冒充已校验
            stats["frames_unchecked"] += 1
            i += total
            continue
    return out, stats


def iter_statustext(data):
    """只产出 CRC 校验通过、非分块的 STATUSTEXT (t_unix, severity, text)。"""
    out, _ = decode(data)
    for rec in out:
        yield rec


def summarize(data):
    """STATUSTEXT 汇总 + 结构化协议计数。accels_inconsistent 仅计 CRC 通过的帧。"""
    from collections import Counter
    out, stats = decode(data)
    counts = Counter(text for _t, _s, text in out)
    first = out[0][0] if out else None
    last = out[-1][0] if out else None
    return {
        "statustext_total": len(out),
        "window_sec": round((last - first), 3) if first is not None else 0.0,
        "accels_inconsistent_count": sum(v for k, v in counts.items() if "Accels inconsistent" in k),
        "markers_seen": {  # 仅"该 marker 文本出现",不升级为"完整 boot 完成"
            "ardupilot_ready_marker": any("ArduPilot Ready" in k for k in counts),
            "ekf_origin_set_marker": any("origin set" in k for k in counts),
            "baro_calibrated_marker": any("Barometer" in k and "calibration complete" in k for k in counts),
        },
        "distinct_texts": len(counts),
        "protocol_stats": stats,
    }


# ---------- 测试辅助:构造**规范有效**帧(计算真实 CRC) ----------
def build_frame(msgid, payload, *, mavlink2=True, signed=False, seq=0, sysid=1, compid=1,
                crc_extra=None, corrupt_crc=False):
    """构造单个 MAVLink 帧(含真实 X25 CRC)。corrupt_crc=True 时翻转 CRC 一位(反例用)。"""
    if crc_extra is None:
        crc_extra = CRC_EXTRA.get(msgid)
    if mavlink2:
        incompat = 0x01 if signed else 0x00
        hdr = bytes([0xFD, len(payload), incompat, 0, seq, sysid, compid,
                     msgid & 0xFF, (msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF])
    else:
        hdr = bytes([0xFE, len(payload), seq, sysid, compid, msgid & 0xFF])
    crc = x25_crc(hdr[1:] + payload, crc_extra)
    if corrupt_crc:
        crc ^= 0x0001
    frame = hdr + payload + struct.pack("<H", crc)
    if mavlink2 and signed:
        frame += b"\x00" * 13
    return frame


def build_record(ts_us, frame):
    return struct.pack(">Q", ts_us) + frame


def build_statustext_record(ts_us, severity, text, *, mavlink2=True, signed=False,
                            corrupt_crc=False, chunk_id=0, chunk_seq=0):
    tb = text.encode("ascii")[:50]
    payload = bytes([severity]) + tb
    if chunk_id or chunk_seq:  # 补足固定字段 + 扩展(测试分块)
        payload = bytes([severity]) + tb.ljust(50, b"\x00") + struct.pack("<H", chunk_id) + bytes([chunk_seq])
    frame = build_frame(STATUSTEXT_MSGID, payload, mavlink2=mavlink2, signed=signed,
                        crc_extra=83, corrupt_crc=corrupt_crc)
    return build_record(ts_us, frame)


if __name__ == "__main__":
    import sys
    import json
    print(json.dumps(summarize(sys.argv[1]), ensure_ascii=False, indent=2))
